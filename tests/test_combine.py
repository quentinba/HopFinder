"""
Test de non-régression du solveur combine (NNLS).

Bases jouets où la bonne réponse est connue d'avance :
  - deux houblons portant chacun UNE molécule de la note -> blend 50/50
  - note mono-molécule -> un seul houblon à 100 %
  - molécule qu'aucun houblon ne fournit -> blend vide + orphelin
Si un refactor casse le comportement du NNLS, ces tests le détectent.
"""
import os
import tempfile
import pytest

from hopmatch import matching
from hopmatch.schema import connect, init_db


def _toy_db():
    """Base minimale insérée à la main (pas de fixtures)."""
    path = os.path.join(tempfile.mkdtemp(), "toy.db")
    con = connect(path)
    init_db(con)
    con.executemany("INSERT INTO molecules VALUES (?,?,?,?)",
                    [("molx", "x", None, None), ("moly", "y", None, None)])
    for v in ("hopA", "hopB"):
        con.execute("INSERT INTO hops VALUES (?,?,?,?)", (v, v, "test", "toy"))
    rows = [
        # hopA porte molx (50% huile), total_oil 1.0
        ("hopA", "molx", 50, 50, "pct_oil", "toy", "ok", ""),
        ("hopA", "total_oil", 1.0, 1.0, "ml_100g", "toy", "ok", ""),
        # hopB porte moly (50% huile), total_oil 1.0
        ("hopB", "moly", 50, 50, "pct_oil", "toy", "ok", ""),
        ("hopB", "total_oil", 1.0, 1.0, "ml_100g", "toy", "ok", ""),
    ]
    con.executemany("INSERT INTO hop_composition VALUES (?,?,?,?,?,?,?,?)", rows)
    con.executemany("INSERT INTO aroma_notes VALUES (?,?,?,?)", [
        ("t5050", "molx", 1.0, "toy"), ("t5050", "moly", 1.0, "toy"),
        ("tsingle", "molx", 1.0, "toy"),
        ("torphan", "molz", 1.0, "toy"),
    ])
    con.commit()
    return con


@pytest.fixture(scope="module")
def con():
    c = _toy_db()
    yield c
    c.close()


def test_5050_blend(con):
    r = matching.combine(con, "t5050", max_hops=3)
    blend = {b["variety"]: b["proportion"] for b in r["blend"]}
    assert set(blend) == {"hopA", "hopB"}
    assert 0.4 <= blend["hopA"] <= 0.6
    assert 0.4 <= blend["hopB"] <= 0.6
    assert r["residual"] < 0.1          # les deux molécules couvertes


def test_single_hop(con):
    r = matching.combine(con, "tsingle", max_hops=3)
    assert [b["variety"] for b in r["blend"]] == ["hopA"]
    assert r["blend"][0]["proportion"] == pytest.approx(1.0)


def test_orphan_no_blend(con):
    r = matching.combine(con, "torphan", max_hops=3)
    assert r["blend"] == []
    assert "molz" in r["orphan"]
    assert r["coverage"] == 0
