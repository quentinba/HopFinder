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

def test_parse_barthhaas_tastes():
    # gabarit calqué sur la page réelle 'admiral' (vérifié en direct,
    # 2026-08-22, T79) : liste <li> structurée, JAMAIS du texte libre.
    html = """
    <ul class="section-card-text__tastes spacer-mb-32">
        <li class="zitrus">Lemon</li>
        <li class="rote-beeren">Cranberry</li>
        <li class="sahnekaramell">Cream</li>
        <li class="wurzig">Pepper</li>
        <li class="krautig">Mate Tea</li>
    </ul>
    """
    assert parsers.parse_barthhaas_tastes(html) == [
        ("zitrus", "lemon"), ("rote-beeren", "cranberry"), ("sahnekaramell", "cream"),
        ("wurzig", "pepper"), ("krautig", "mate tea"),
    ]

def test_parse_barthhaas_tastes_returns_empty_list_when_absent():
    assert parsers.parse_barthhaas_tastes("<div>no tastes here</div>") == []

def test_parse_barthhaas_aroma_wheel():
    # gabarit calqué sur la page réelle 'admiral' (vérifié en direct,
    # 2026-08-22, T79) : data-rose-labels sur un conteneur, data-values sur
    # le <canvas> hero (toujours identique au bloc "Typical" plus bas,
    # vérifié sur plusieurs variétés).
    html = """
    <div class="hp__hero__product-image" data-rose-labels="citrus,sweet fruits,green fruits,berries &amp; curant,cream caramel,woody aromatic,menthol,herbal,spicy,grassy-hay,vegetal,floral">
        <canvas data-values="3,6,4,6,1,3,3,6,1,5,4,1"></canvas>
    </div>
    """
    result = parsers.parse_barthhaas_aroma_wheel(html)
    assert result == {
        "citrus": 3.0, "sweet fruits": 6.0, "green fruits": 4.0, "berries & curant": 6.0,
        "cream caramel": 1.0, "woody aromatic": 3.0, "menthol": 3.0, "herbal": 6.0,
        "spicy": 1.0, "grassy-hay": 5.0, "vegetal": 4.0, "floral": 1.0,
    }

def test_parse_barthhaas_aroma_wheel_returns_none_when_absent():
    assert parsers.parse_barthhaas_aroma_wheel("<div>no wheel here</div>") is None

def test_parse_barthhaas_aroma_wheel_returns_none_on_label_value_count_mismatch():
    html = ('<div data-rose-labels="citrus,floral">'
           '<canvas data-values="1,2,3"></canvas></div>')
    assert parsers.parse_barthhaas_aroma_wheel(html) is None

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
    variety, name, region, comp, descriptors, _ = parsers.parse_yakima_hit(hit)
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

def test_strip_yakima_brand_suffix_removes_standalone_brand_word():
    # signalé par l'utilisateur (2026-08-19) : "Mosaic® Brand" (Yakima)
    # alors que BarthHaas affiche juste "Mosaic®" pour la même variété --
    # "Brand" est un artefact marketing Yakima, pas le nom réel.
    assert parsers._strip_yakima_brand_suffix("Mosaic® Brand") == "Mosaic®"
    assert parsers._strip_yakima_brand_suffix("Citra® Brand") == "Citra®"
    assert parsers._strip_yakima_brand_suffix("Bravo™ Brand") == "Bravo™"

def test_strip_yakima_brand_suffix_handles_parenthesized_form():
    # un seul cas vu en direct sur l'API réelle (Galaxy) : "(Brand)" au lieu
    # de "Brand" tout court.
    assert parsers._strip_yakima_brand_suffix("Galaxy™ (Brand)") == "Galaxy™"

def test_strip_yakima_brand_suffix_keeps_real_qualifiers():
    # "- NZ Hops"/"- MacHops"/"Organic" sont de VRAIS qualificatifs
    # distinguant des variantes régionales -- seul le mot "Brand" doit
    # disparaître, jamais ce qui l'entoure (vérifié sur l'API réelle).
    assert (parsers._strip_yakima_brand_suffix("Kohatu® Brand - NZ Hops")
           == "Kohatu® - NZ Hops")
    assert (parsers._strip_yakima_brand_suffix("Nectaron® Organic Brand - NZ Hops")
           == "Nectaron® Organic - NZ Hops")
    assert (parsers._strip_yakima_brand_suffix("Waimea™ Brand - MacHops")
           == "Waimea™ - MacHops")

def test_strip_yakima_brand_suffix_leaves_names_without_brand_untouched():
    assert parsers._strip_yakima_brand_suffix("Admiral") == "Admiral"
    assert parsers._strip_yakima_brand_suffix(None) is None

def test_strip_bare_hops_suffix_removes_standalone_marketing_word():
    # T123 (2026-08-27) : "Hops" est l'habillage marketing du <h1> BarthHaas
    # pour 7 variétés (Dolcita, Huell Classic, Luna, Ariana, Eclipse,
    # El Dorado, Krush), jamais une partie du nom de la variété.
    assert parsers.strip_bare_hops_suffix("Luna Hops") == "Luna"
    assert parsers.strip_bare_hops_suffix("Dolcita Hops") == "Dolcita"
    assert parsers.strip_bare_hops_suffix("Huell Classic Hops") == "Huell Classic"

def test_strip_bare_hops_suffix_keeps_hyphen_qualified_suppliers():
    # "- NZ Hops" (fournisseur NZ Hops Ltd, T51) est un vrai qualificatif --
    # jamais retiré, même si le nom se termine bien par "Hops".
    assert (parsers.strip_bare_hops_suffix("Kohatu - NZ Hops")
           == "Kohatu - NZ Hops")
    assert (parsers.strip_bare_hops_suffix("Nelson Sauvin - NZ Hops")
           == "Nelson Sauvin - NZ Hops")
    # tiret interne SANS espaces autour (cultivar réel) n'est pas la séquence
    # qualificative " - " -- doit quand même déclencher la garde ici car la
    # vraie séquence " - NZ Hops" est bien présente par ailleurs.
    assert (parsers.strip_bare_hops_suffix("Wai-iti - NZ Hops")
           == "Wai-iti - NZ Hops")

def test_strip_bare_hops_suffix_leaves_names_without_suffix_untouched():
    assert parsers.strip_bare_hops_suffix("Admiral") == "Admiral"
    assert parsers.strip_bare_hops_suffix("Citra") == "Citra"
    assert parsers.strip_bare_hops_suffix(None) is None

def test_parse_yakima_hit_strips_brand_suffix_from_display_name():
    hit = {
        "url": "/variety/mosaic-brand",
        "imported_fields": {"display_name": "Mosaic® Brand", "country_name": "United States"},
    }
    _, name, _, _, _, _ = parsers.parse_yakima_hit(hit)
    # T59 (2026-08-19) : le ® est aussi retiré désormais (strip_trademark_symbols),
    # pas seulement "Brand" -- voir tests dédiés ci-dessous.
    assert name == "Mosaic"

def test_strip_trademark_symbols_removes_registered_and_tm_and_copyright():
    # T59 (demande utilisateur, 2026-08-19) : "I see some ® or ™ in the name
    # of some results of hop. Could you remove this from the name..."
    assert parsers.strip_trademark_symbols("Citra®") == "Citra"
    assert parsers.strip_trademark_symbols("Ella™") == "Ella"
    assert parsers.strip_trademark_symbols("Foo©") == "Foo"

def test_strip_trademark_symbols_keeps_real_qualifiers_and_collapses_spaces():
    # "El Dorado® Hops" -> le symbole disparaît, "Hops" (un vrai qualificatif,
    # pas un artefact) reste, espaces résultants recollapsés à un seul.
    assert parsers.strip_trademark_symbols("El Dorado® Hops") == "El Dorado Hops"
    assert parsers.strip_trademark_symbols("Nectaron® - NZ Hops") == "Nectaron - NZ Hops"

def test_strip_trademark_symbols_leaves_names_without_symbol_untouched():
    assert parsers.strip_trademark_symbols("Admiral") == "Admiral"
    assert parsers.strip_trademark_symbols(None) is None
    assert parsers.strip_trademark_symbols("") == ""

def test_parse_yakima_hit_strips_trademark_symbol_from_display_name():
    hit = {
        "url": "/variety/citra",
        "imported_fields": {"display_name": "Citra®", "country_name": "United States"},
    }
    _, name, _, _, _, _ = parsers.parse_yakima_hit(hit)
    assert name == "Citra"

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
    _, _, _, comp, _, _ = parsers.parse_yakima_hit(hit)
    assert comp["total_oil"] == (1.2, 2.1, "ml_100g")  # PEL02, pas ARO01

def test_parse_yakima_hit_falls_back_to_con02_without_pel02():
    hit = {
        "url": "/variety/blend-x",
        "imported_fields": {
            "display_name": "Blend X", "aromas": [],
            "brewing_values": [{"code": "CON02", "myrcene": {"low": 10, "ave": 12, "high": 14}}],
        },
    }
    _, _, _, comp, _, _ = parsers.parse_yakima_hit(hit)
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
    _, _, _, comp, _, _ = parsers.parse_yakima_hit(hit)
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
    _, _, _, comp, _, _ = parsers.parse_yakima_hit(hit)
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
    _, _, _, comp, _, _ = parsers.parse_yakima_hit(hit)
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
    _, _, _, comp, _, _ = parsers.parse_yakima_hit(hit)
    assert comp["total_oil"] == (1.0, 1.7, "ml_100g")

def test_parse_yakima_hit_aroma_intensity_matches_selected_product_form():
    # gabarit trimmé d'un vrai hit Algolia YCH (variété Mosaic, vérifié en
    # direct) : sensory_values couvre un sous-ensemble des codes brewing_values
    # (ici CON04 et PEL02 seulement), avec un vocabulaire plus large que
    # `aromas` (ex. "Vegetal"/"Pomme" absents de la liste courte). L'entrée
    # PEL02 doit être choisie car c'est la forme retenue pour la composition.
    hit = {
        "url": "/variety/mosaic",
        "imported_fields": {
            "display_name": "Mosaic", "aromas": ["Berry", "Citrus", "Tropical", "Stone Fruit"],
            "brewing_values": [
                {"code": "CON04", "alpha": {"low": 11.5, "ave": 12.25, "high": 13}},
                {"code": "PEL02", "alpha": {"low": 11.5, "ave": 12.25, "high": 13},
                 "myrcene": {"low": 50, "ave": 55, "high": 60}},
            ],
            "sensory_values": [
                {"code": "CON04", "sensory_value_items": [
                    {"aroma": "Citrus", "aroma_intensity": 93},
                    {"aroma": "Woody", "aroma_intensity": 85},
                ]},
                {"code": "PEL02", "sensory_value_items": [
                    {"aroma": "Citrus", "aroma_intensity": 90},
                    {"aroma": "Tropical", "aroma_intensity": 70},
                    {"aroma": "Vegetal", "aroma_intensity": 26},
                ]},
            ],
            "aroma_values": [{"aroma": "Citrus", "aroma_intensity": 999}],  # ne doit PAS être utilisé
        },
    }
    _, _, _, _, _, aroma_intensity = parsers.parse_yakima_hit(hit)
    assert aroma_intensity == {"citrus": 90.0, "tropical": 70.0, "vegetal": 26.0}

def test_parse_yakima_hit_aroma_intensity_falls_back_to_variety_level():
    # aucune entrée sensory_values ne correspond au code produit choisi (ou
    # sensory_values absent) -> repli sur aroma_values (niveau variété).
    hit = {
        "url": "/variety/no-sensory-match",
        "imported_fields": {
            "display_name": "No Sensory Match", "aromas": [],
            "brewing_values": [{"code": "PEL02", "myrcene": {"low": 10, "ave": 12, "high": 14}}],
            "aroma_values": [{"aroma": "Earthy", "aroma_intensity": 42}],
        },
    }
    _, _, _, _, _, aroma_intensity = parsers.parse_yakima_hit(hit)
    assert aroma_intensity == {"earthy": 42.0}

def test_parse_beermaverick_pairings():
    # gabarit trimmé d'une vraie page beermaverick.com/hop/mosaic/ (vérifié en
    # direct) : le graphique "Hop Pairings" est un Chart.js embarqué dans le
    # HTML statique, pas besoin de leur endpoint interne.
    html = """
    <h2>Hop Pairings <span class="borderme">with Mosaic Hops</span></h2>
    <p>...</p>
    <center><canvas id="commonChart" width="350" height="125"></canvas></center>
    <script type="pmdelayedscript">
    var ctx = document.getElementById('commonChart').getContext('2d');
    var data = {
    labels: ['Citra ','Simcoe ','El Dorado ','Amarillo ','Galaxy ','Azacca ',],
    datasets: [{
    data: [77,27,17,16,16,11,],
    backgroundColor: ["rgba(46, 134, 193, 1)"],
    }]
    }
    var myBarChart = new Chart(ctx, {type: 'horizontalBar', data: data});
    </script>
    """
    assert parsers.parse_beermaverick_pairings(html) == [
        ("Citra", 77.0), ("Simcoe", 27.0), ("El Dorado", 17.0),
        ("Amarillo", 16.0), ("Galaxy", 16.0), ("Azacca", 11.0),
    ]

def test_parse_beermaverick_pairings_absent_returns_empty():
    # variétés à faible volume de recettes (ex. Admiral, vérifié en direct) :
    # la section "Hop Pairings" est absente du HTML, pas juste vide.
    html = "<h2>Beer Styles using Admiral Hops</h2><p>English IPA & Ale.</p>"
    assert parsers.parse_beermaverick_pairings(html) == []

def test_parse_beermaverick_substitutions():
    # gabarit trimmé de la même vraie page Mosaic.
    html = """
    <h2><span class="borderme">Mosaic</span> Hop Substitutions</h2>
    <p>Experienced brewers have chosen the following hop varieties as substitutions of Mosaic:</p>
    <ul><li><a href="/hop/citra/">Citra</a></li><li><a href="/hop/simcoe/"> Simcoe</a></li></ul>
    """
    assert parsers.parse_beermaverick_substitutions(html) == [
        ("citra", "Citra"), ("simcoe", "Simcoe"),
    ]

def test_parse_beermaverick_substitutions_absent_returns_empty():
    assert parsers.parse_beermaverick_substitutions("<p>rien ici</p>") == []

def test_parse_beermaverick_tags():
    # gabarit trimmé d'une vraie page beermaverick.com/hop/chinook/ (vérifié
    # en direct) : Chinook y est bien tagué "dank", contrairement à Yakima qui
    # ne le tague sur aucun des deux (voir CLAUDE.md).
    html = """
    <p><b>Tags:</b> <em style="color:#666;" >
    <a href="/hops/tag/pine/" class="text-muted" >#pine</a>&nbsp;
    <a href="/hops/tag/resin/" class="text-muted" >#resin</a>&nbsp;
    <a href="/hops/tag/grapefruit/" class="text-muted" >#grapefruit</a>&nbsp;
    <a href="/hops/tag/spicy/" class="text-muted" >#spicy</a>&nbsp;
    <a href="/hops/tag/dank/" class="text-muted" >#dank</a>&nbsp;
    <a href="/hops/tag/cannabis/" class="text-muted" >#cannabis</a>&nbsp;
    </em></p>
    """
    assert parsers.parse_beermaverick_tags(html) == [
        "pine", "resin", "grapefruit", "spicy", "dank", "cannabis",
    ]

def test_parse_beermaverick_tags_absent_returns_empty():
    assert parsers.parse_beermaverick_tags("<p>rien ici</p>") == []

def test_parse_beermaverick_purpose():
    # gabarit trimmé d'une vraie page beermaverick.com/hop/citra/ (vérifié en
    # direct, T-purpose backlog).
    html = """
    <figure class="wp-block-table"><table>
    <tr><th>Purpose:</th><td><strong><a href="https://beermaverick.com/types-of-hops-aroma-noble-bittering-dual-purpose/">Dual</a></strong></td></tr>
    <tr><th>Country:</th><td>United States of America (USA)</td></tr>
    """
    assert parsers.parse_beermaverick_purpose(html) == "Dual"

def test_parse_beermaverick_purpose_absent_returns_none():
    assert parsers.parse_beermaverick_purpose("<p>rien ici</p>") is None

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
