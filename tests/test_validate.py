from hopmatch.schema import validate_and_repair

def test_swap_myrcene_caryophyllene():
    # cas type Citra scrappé sale : caryophyllène=70 impossible
    comp = {"myrcene": (0.7, 1.0, "pct_oil"), "caryophyllene": (60, 70, "pct_oil"),
            "humulene": (7, 12, "pct_oil")}
    fixed, conf, notes = validate_and_repair(comp)
    assert conf == "repaired"
    assert fixed["myrcene"][1] == 70          # récupéré
    assert fixed["caryophyllene"][1] == 1.0

def test_clean_data_passes():
    comp = {"myrcene": (50, 70, "pct_oil"), "caryophyllene": (4, 8, "pct_oil"),
            "humulene": (7, 12, "pct_oil")}
    _, conf, _ = validate_and_repair(comp)
    assert conf == "ok"

def test_negative_flagged():
    comp = {"myrcene": (-55, -50, "pct_oil")}
    _, conf, _ = validate_and_repair(comp)
    assert conf == "suspect"
