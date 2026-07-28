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
