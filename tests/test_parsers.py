from hopmatch import parsers

def test_parse_range():
    assert parsers.parse_range("28.6 - 66%") == (28.6, 66.0)
    assert parsers.parse_range("up to 2.8 ml/100 g") == (0.0, 2.8)
    assert parsers.parse_range("0.2 - 1 ml/100 g") == (0.2, 1.0)
    assert parsers.parse_range("up to 28.7") == (0.0, 28.7)

def test_barthhaas_composition():
    text = "MYRCENE\n28.6 - 66%\nLINALOOL\n0.5 - 1.1%\nTHIOLS (µG/KG)\nup to 28.7\n"
    comp = parsers.parse_composition(text, parsers.BARTHHAAS_LABELS)
    assert comp["myrcene"] == (28.6, 66.0, "pct_oil")
    assert comp["linalool"] == (0.5, 1.1, "pct_oil")
    assert comp["thiols"] == (0.0, 28.7, "ug_kg")

def test_yakima_pinene_and_descriptors():
    text = "B-PINENE\n0.6 - 1%\nMYRCENE\n50 - 70%\nAROMA PROFILE\nCitrus, Stone Fruit\n"
    comp = parsers.parse_composition(text, parsers.YAKIMA_LABELS)
    assert comp["beta-pinene"] == (0.6, 1.0, "pct_oil")
    assert comp["myrcene"] == (50.0, 70.0, "pct_oil")
    assert parsers.parse_descriptors(text) == ["citrus", "stone fruit"]

def test_parse_descriptors_rejects_barthhaas_prose_paragraph():
    # gabarit calqué sur le site BarthHaas réel (variété 'admiral', vérifié en
    # direct) : un sous-titre 'Typical Aroma Profile' puis un PARAGRAPHE, pas
    # une liste courte -> aucun descripteur inventé depuis du texte libre.
    text = ("Aroma Profile\nTypical Aroma Profile\n"
           "The flavour profile of Admiral in the raw hops is characterised by "
           "green grassy and nuances, fruit tea and sweet ripe kiwi. Also "
           "refreshing citrus along with versatile herbal and earthy aromas "
           "contribute to the overall impression.\nAnalyses\n")
    assert parsers.parse_descriptors(text) == []

def test_parse_descriptors_skips_crop_year_before_prose():
    # gabarit calqué sur la variété 'tango' (vérifié en direct) : une année de
    # récolte brute s'intercale AVANT le sous-titre.
    text = ("Aroma Profile\n2023\nTypical Aroma Profile\n"
           "Some descriptive paragraph about the hop.\nAnalyses\n")
    assert parsers.parse_descriptors(text) == []

def test_parse_descriptors_still_works_if_barthhaas_gives_a_clean_list():
    # si une variété a effectivement une liste courte après le sous-titre
    # (pas de point final), elle reste extraite normalement.
    text = "Aroma Profile\nTypical Aroma Profile\nCitrus, Herbal\nAnalyses\n"
    assert parsers.parse_descriptors(text) == ["citrus", "herbal"]

def test_parse_flavornet():
    # gabarit calqué sur d_kovats_ov101.html (RI x4, lien CAS, descripteurs)
    html = """
    <table>
    <tr><td class=sh>527</td><td>505</td><td>[596]</td><td>716</td><td class=ch>
        <a href="info/75-18-3.html">Linalool</a></td><td class=sm>floral, citrus</td></tr>
    <tr><td class=sh>500</td><td>500</td><td>500</td><td>500</td><td class=ch>
        <a href="info/109-66-0.html">pentane</a></td><td class=sm>alkane</td></tr>
    </table>
    """
    rows = parsers.parse_flavornet(html)
    assert rows == [
        ("75-18-3", "linalool", ["floral", "citrus"]),
        ("109-66-0", "pentane", ["alkane"]),
    ]

def test_mass_mg_per_100g():
    assert parsers.mass_mg_per_100g(3.2, "mg/100g") == 3.2
    assert parsers.mass_mg_per_100g(3.2, "mg/100 g fresh weight") == 3.2
    assert parsers.mass_mg_per_100g(12.15, "mg/kg") == 1.215
    assert parsers.mass_mg_per_100g(2499, "IU") is None    # pas une masse
    assert parsers.mass_mg_per_100g(0.0001, "ppb") is None  # échelle différente
    assert parsers.mass_mg_per_100g(None, "mg/100g") is None

def test_parse_flavordb2_threshold():
    # échantillons réels observés sur cosylab.iiitd.edu.in/flavordb2
    assert parsers.parse_flavordb2_threshold("4 to 10 ppb") == 7.0
    assert parsers.parse_flavordb2_threshold("Detection at 64 to 90 ppb") == 77.0
    assert parsers.parse_flavordb2_threshold("Detection at 28 ppm in water") == 28000.0
    assert parsers.parse_flavordb2_threshold("5 ppb") == 5.0
    assert parsers.parse_flavordb2_threshold("Detection at 11 ppb to 2.2 ppm; l-form, 40 ppb") == 11.0
    # pièges : pas d'unité reconnue -> pas de seuil (surtout pas un pourcentage)
    assert parsers.parse_flavordb2_threshold(
        "Aroma characteristics at 10%; terpy, herbaceous, woody with a rosy celery and carrot nuance") is None
    assert parsers.parse_flavordb2_threshold(
        "cooling menthol with a penetrating minty eucalyptus note") is None
    assert parsers.parse_flavordb2_threshold("") is None

def test_parse_flavordb2_search():
    html = """
    <table id="molecules"><tbody>
    <tr><td class="text-capitalize">Linalool</td>
        <td><a href="https://pubchem.ncbi.nlm.nih.gov/compound/6549">6549</a></td></tr>
    <tr><td class="text-capitalize">(+)-Linalool</td>
        <td><a href="https://pubchem.ncbi.nlm.nih.gov/compound/443158">443158</a></td></tr>
    </tbody></table>
    """
    assert parsers.parse_flavordb2_search(html) == [
        ("Linalool", 6549), ("(+)-Linalool", 443158),
    ]

def test_parse_flavordb2_detail():
    html = """
    <table>
      <tr><th>CAS:</th><td>22564-99-4, 78-70-6</td></tr>
    </table>
    <div class="panel-collapse collapse">
      <ul class="list-group">
        <li class="list-group-item"><strong>Aroma threshold values:</strong> 4 to 10 ppb</li>
        <li class="list-group-item"><strong>Taste threshold values:</strong> 5 ppm, apple</li>
      </ul>
    </div>
    """
    cas_list, threshold = parsers.parse_flavordb2_detail(html)
    assert cas_list == ["22564-99-4", "78-70-6"]
    assert threshold == 7.0  # seul le seuil AROME est retenu, pas le goût

def test_parse_yakima_hit():
    # gabarit trimmé d'un vrai hit Algolia YCH (variété Admiral)
    hit = {
        "url": "/variety/admiral",
        "imported_fields": {
            "display_name": "Admiral",
            "country_name": "United Kingdom",
            "aromas": ["Orange", "Resinous", "Tea"],
            "brewing_values": [
                {
                    "name": "HopAroma", "code": "ARO01",
                    "alpha": {"low": 54, "ave": 58, "high": 62},
                    "beta": {"low": 14, "ave": 16, "high": 18},
                    "oil": {"low": 5, "ave": 7, "high": 9},
                    "b_pinene": {"low": 0.5, "ave": 0.8, "high": 1},
                    "myrcene": {"low": 48, "ave": 51, "high": 54},
                    "linalool": {"low": 0.3, "ave": 0.6, "high": 0.8},
                    "caryophyllene": {"low": 4, "ave": 8, "high": 12},
                    "farnesene": {"low": 0.1, "ave": 0.6, "high": 1},
                    "humulene": {"low": 12, "ave": 15, "high": 18},
                    "geraniol": {"low": 0.6, "ave": 0.9, "high": 1.2},
                    "silinene": {"low": None, "ave": None, "high": None},
                },
                {
                    "name": "Type 90 Hop Pellets", "code": "PEL02",
                    "alpha": {"low": 13, "ave": 14.5, "high": 16},
                    "myrcene": {"low": 39, "ave": 43.5, "high": 48},
                },
            ],
        },
    }
    variety, name, region, comp, descriptors = parsers.parse_yakima_hit(hit)
    assert variety == "admiral"
    assert name == "Admiral"
    assert region == "United Kingdom"
    assert descriptors == ["orange", "resinous", "tea"]
    # Ce gabarit est la variété Admiral RÉELLE (vérifié en direct sur l'index
    # Algolia YCH). PEL02 (Type 90 Pellets) gagne par priorité normale (voir
    # _BREWING_VALUE_PRIORITY) — pas seulement parce que ARO01 (HopAroma) a un
    # alpha 54-62% chimiquement impossible (aucune variété commerciale ne
    # dépasse ~25%, cf. test dédié à la plausibilité), mais parce que PEL02 est
    # la forme préférée par défaut de toute façon.
    assert comp["myrcene"] == (39.0, 48.0, "pct_oil")
    assert comp["alpha_acid"] == (13.0, 16.0, "pct")
    assert "beta-pinene" not in comp   # absent de l'entrée PEL02 de ce gabarit
    assert "total_oil" not in comp     # idem
    assert "selinene" not in comp  # low/high = None -> pas ingéré

def test_parse_yakima_hit_prefers_pel02_over_everything():
    # vérifié sur les 152 variétés réelles de l'index Algolia YCH : PEL02
    # (Type 90 Pellets, la forme que le brasseur utilise réellement) existe
    # sur 148/152 ; ARO01 n'existe que sur 1/152 (admiral, et corrompue). PEL02
    # doit gagner même face à un ARO01 par ailleurs parfaitement plausible —
    # ce n'est pas juste un repli sur échec de plausibilité, c'est la priorité
    # normale (`_BREWING_VALUE_PRIORITY`).
    hit = {
        "url": "/variety/normal-hop",
        "imported_fields": {
            "display_name": "Normal Hop", "aromas": [],
            "brewing_values": [
                {"code": "ARO01", "alpha": {"low": 10, "ave": 12, "high": 14},
                 "oil": {"low": 1, "ave": 1.5, "high": 2}},
                {"code": "PEL02", "alpha": {"low": 11, "ave": 13, "high": 15},
                 "oil": {"low": 1.2, "ave": 1.6, "high": 2.1}},
            ],
        },
    }
    _, _, _, comp, _ = parsers.parse_yakima_hit(hit)
    assert comp["total_oil"] == (1.2, 2.1, "ml_100g")  # PEL02, pas ARO01

def test_parse_yakima_hit_falls_back_to_con02_without_pel02():
    hit = {
        "url": "/variety/blend-x",
        "imported_fields": {
            "display_name": "Blend X", "aromas": [],
            "brewing_values": [{"code": "CON02", "myrcene": {"low": 10, "ave": 12, "high": 14}}],
        },
    }
    _, _, _, comp, _ = parsers.parse_yakima_hit(hit)
    assert comp["myrcene"] == (10.0, 14.0, "pct_oil")

def test_parse_yakima_hit_avoids_derivative_products_like_cryo_or_co2_extract():
    # PEL06 (Cryo Hops, lupuline concentrée) et EXT01 (extrait CO2) sont des
    # produits dérivés à composition fondamentalement différente (alpha/huile
    # bien plus concentrés) — pas "le même houblon dans un autre emballage".
    # Ne doivent être choisis que si RIEN d'autre n'existe pour la variété.
    hit = {
        "url": "/variety/derivative-only",
        "imported_fields": {
            "display_name": "Derivative Only", "aromas": [],
            "brewing_values": [
                {"code": "EXT01", "alpha": {"low": 58, "ave": 61, "high": 64},
                 "oil": {"low": 3, "ave": 4.5, "high": 6}},
                {"code": "PEL06", "alpha": {"low": 21, "ave": 24.5, "high": 28},
                 "oil": {"low": 2, "ave": 4, "high": 6}},
                {"code": "PEL02", "alpha": {"low": 10, "ave": 13, "high": 16},
                 "oil": {"low": 1, "ave": 2, "high": 3}},
            ],
        },
    }
    _, _, _, comp, _ = parsers.parse_yakima_hit(hit)
    assert comp["total_oil"] == (1.0, 3.0, "ml_100g")  # PEL02, pas EXT01/PEL06

def test_parse_yakima_hit_rejects_implausible_aro01_in_favor_of_other_plausible_entry():
    # ARO01 (implausible, alpha 54-62%) et PEL06 (Cryo, un produit dérivé donc
    # hors _BREWING_VALUE_PRIORITY mais plausible) : aucun code prioritaire
    # n'est utilisable ici, donc on retombe sur "la première entrée plausible
    # qui reste" (PEL06) plutôt que sur ARO01 malgré son rang de priorité —
    # la plausibilité prime toujours sur la position dans la liste.
    hit = {
        "url": "/variety/admiral-like",
        "imported_fields": {
            "display_name": "Admiral-like", "aromas": [],
            "brewing_values": [
                {"code": "ARO01", "alpha": {"low": 54, "ave": 58, "high": 62},
                 "oil": {"low": 5, "ave": 7, "high": 9}},
                {"code": "PEL06", "alpha": {"low": 21, "ave": 24.5, "high": 28},
                 "oil": {"low": 2, "ave": 4, "high": 6}},
            ],
        },
    }
    _, _, _, comp, _ = parsers.parse_yakima_hit(hit)
    assert comp["total_oil"] == (2.0, 6.0, "ml_100g")  # PEL06, pas ARO01

def test_parse_yakima_hit_uses_sole_implausible_entry_as_last_resort():
    # aucune entrée plausible du tout : on préfère quand même la retenir
    # (variété suspecte) plutôt que la faire disparaître silencieusement de
    # la base — comportement volontairement conservé de la version précédente.
    hit = {
        "url": "/variety/admiral",
        "imported_fields": {
            "display_name": "Admiral", "aromas": [],
            "brewing_values": [
                {"code": "ARO01", "alpha": {"low": 54, "ave": 58, "high": 62},
                 "oil": {"low": 5, "ave": 7, "high": 9},
                 "myrcene": {"low": 48, "ave": 51, "high": 54}},
            ],
        },
    }
    _, _, _, comp, _ = parsers.parse_yakima_hit(hit)
    assert comp["total_oil"] == (5.0, 9.0, "ml_100g")

def test_parse_yakima_hit_pel02_implausible_falls_back_to_con02():
    # la plausibilité s'applique à N'IMPORTE QUEL code, pas seulement ARO01.
    hit = {
        "url": "/variety/bad-pel02",
        "imported_fields": {
            "display_name": "Bad Pel02", "aromas": [],
            "brewing_values": [
                {"code": "PEL02", "alpha": {"low": 50, "ave": 55, "high": 60},
                 "oil": {"low": 5, "ave": 7, "high": 9}},
                {"code": "CON02", "alpha": {"low": 13, "ave": 14.5, "high": 16},
                 "oil": {"low": 1, "ave": 1.4, "high": 1.7}},
            ],
        },
    }
    _, _, _, comp, _ = parsers.parse_yakima_hit(hit)
    assert comp["total_oil"] == (1.0, 1.7, "ml_100g")

def test_pubchem_name_fallbacks():
    # échantillons réels : CAS non résolus par PubChem, noms Flavornet en cause
    assert parsers.pubchem_name_fallbacks("δ-cadinol") == ["δ-cadinol", "delta-cadinol"]
    assert parsers.pubchem_name_fallbacks("(r)-linden ether") == \
        ["(r)-linden ether", "linden ether"]
    # les deux replis s'appliquent : lettre grecque épelée ET préfixe stéréo retiré
    assert parsers.pubchem_name_fallbacks("(r)-β-citronellol") == [
        "(r)-β-citronellol", "(r)-beta-citronellol", "β-citronellol", "beta-citronellol"]
    # rien à corriger -> une seule variante (le nom lui-même)
    assert parsers.pubchem_name_fallbacks("hexadecanol") == ["hexadecanol"]
