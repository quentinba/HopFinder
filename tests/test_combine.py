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


def _adversarial_topk_db():
    """
    Base jouet où le sous-ensemble des `max_hops` plus gros poids du NNLS
    complet (l'ancienne heuristique, T10 du backlog) est strictement moins bon
    qu'une sélection gloutonne avant (matching pursuit) — trouvée par
    recherche aléatoire sur la vraie base (`docs/BACKLOG.md#T10`), rejouée ici
    en dur avec des pourcentages ronds. NNLS complet donne un poids fort à h4
    et h1 (résidu ~0.71) alors que h0+h3 fait ~0.51 : sans le "meilleur des
    deux", combine() choisirait le pire sous-ensemble.
    """
    path = os.path.join(tempfile.mkdtemp(), "toy_adversarial.db")
    con = connect(path)
    init_db(con)
    con.executemany("INSERT INTO molecules VALUES (?,?,?,?)",
                    [(f"m{i}", f"m{i}", None, None) for i in range(5)])
    hops = ["h0", "h1", "h2", "h3", "h4", "h5"]
    for h in hops:
        con.execute("INSERT INTO hops VALUES (?,?,?,?)", (h, h, "test", "toy"))
        con.execute("INSERT INTO hop_composition VALUES (?,?,?,?,?,?,?,?)",
                     (h, "total_oil", 1.0, 1.0, "ml_100g", "toy", "ok", ""))
    # lignes = m0..m4, colonnes = h0..h5 (% huile)
    pct = [
        [59, 55, 69,  0,  0,  0],
        [ 0,  0, 90, 89,  0, 69],
        [ 0,  0,  0, 96,  0, 58],
        [95,  0, 81,  0, 73, 81],
        [84, 97, 71, 98,  0,  0],
    ]
    rows = [(hops[j], f"m{i}", pct[i][j], pct[i][j], "pct_oil", "toy", "ok", "")
            for i in range(5) for j in range(6) if pct[i][j] > 0]
    con.executemany("INSERT INTO hop_composition VALUES (?,?,?,?,?,?,?,?)", rows)
    con.executemany("INSERT INTO aroma_notes VALUES (?,?,?,?)", [
        ("tadversarial", f"m{i}", w, "toy")
        for i, w in enumerate([0.21, 0.08, 0.44, 0.72, 0.78])
    ])
    con.commit()
    return con


def test_forward_selection_beats_topk_truncation():
    con = _adversarial_topk_db()
    try:
        r = matching.combine(con, "tadversarial", max_hops=2)
    finally:
        con.close()
    picked = {b["variety"] for b in r["blend"]}
    # la troncature "top-K du NNLS complet" choisirait h4+h1 (résidu ~0.71) ;
    # la sélection gloutonne avant trouve h0+h3 (résidu ~0.51) — combine()
    # doit garder le meilleur des deux, jamais le pire.
    assert picked == {"h0", "h3"}
    assert r["residual"] < 0.6
