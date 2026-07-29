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
    # composition prise sur ARO01 (HopAroma), pas PEL02, malgré son myrcène différent
    assert comp["myrcene"] == (48.0, 54.0, "pct_oil")
    assert comp["beta-pinene"] == (0.5, 1.0, "pct_oil")
    assert comp["total_oil"] == (5.0, 9.0, "ml_100g")
    assert comp["alpha_acid"] == (54.0, 62.0, "pct")
    assert "selinene" not in comp  # low/high = None -> pas ingéré

def test_parse_yakima_hit_falls_back_without_aro01():
    hit = {
        "url": "/variety/blend-x",
        "imported_fields": {
            "display_name": "Blend X", "aromas": [],
            "brewing_values": [{"code": "PEL02", "myrcene": {"low": 10, "ave": 12, "high": 14}}],
        },
    }
    _, _, _, comp, _ = parsers.parse_yakima_hit(hit)
    assert comp["myrcene"] == (10.0, 14.0, "pct_oil")
