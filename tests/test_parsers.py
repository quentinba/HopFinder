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
