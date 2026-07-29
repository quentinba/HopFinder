import os, tempfile
import pytest
from hopmatch import ingest, matching
from hopmatch.schema import connect

FIX = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")

@pytest.fixture(scope="module")
def db():
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    ingest.build_from_fixtures(FIX, path)
    con = connect(path)
    yield con
    con.close()

def test_merge_multisource(db):
    # Citra doit fusionner β-pinène (yakima) + thiols (barthhaas)
    _, comp, _, _ = matching.load(db)
    assert comp["citra"]["beta-pinene"]["sources"] == ["yakima"]
    assert comp["citra"]["thiols"]["sources"] == ["barthhaas"]
    assert set(comp["citra"]["myrcene"]["sources"]) == {"barthhaas", "yakima"}

def test_amplify_ranks(db):
    r = matching.amplify(db, "yuzu")
    assert r["ranked"], "au moins un houblon"
    assert 0 <= r["coverage"] <= 1

def test_combine_returns_blend_and_residual(db):
    r = matching.combine(db, "fruit-passion", max_hops=2)
    assert "residual" in r
    assert isinstance(r["blend"], list)

def test_orphans_flagged(db):
    r = matching.amplify(db, "yuzu")
    # limonène n'existe pas dans le houblon -> orphelin
    assert "limonene" in r["orphan"]

def test_by_descriptor_matches_and_ranks(db):
    r = matching.by_descriptor(db, ["citrus", "tropical"])
    varieties = [h["variety"] for h in r]
    assert set(varieties) == {"citra", "mosaic", "simcoe"}  # saazer n'a ni l'un ni l'autre
    for h in r:
        assert set(h["matched_descriptors"]) <= {"citrus", "tropical"}
        assert set(h["matched_descriptors"]) <= set(h["all_descriptors"])
    # tous à 2 descripteurs recoupés ici -> tie-break par total_oil réconcilié desc
    # (fixtures : simcoe 1.75 > citra 1.7 > mosaic 1.625 ml/100g)
    assert [h["variety"] for h in r] == ["simcoe", "citra", "mosaic"]

def test_by_descriptor_normalizes_aliases(db):
    # "stonefruit"/"citrus fruit" doivent se comporter comme leurs formes canoniques
    r_alias = matching.by_descriptor(db, ["citrus fruit"])
    r_canon = matching.by_descriptor(db, ["citrus"])
    assert [h["variety"] for h in r_alias] == [h["variety"] for h in r_canon]

def test_by_descriptor_no_match(db):
    assert matching.by_descriptor(db, ["nonexistent-descriptor"]) == []
