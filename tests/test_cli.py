"""
Tests de fumée pour le câblage CLI (argparse -> matching) et son dispatch.
Aucun test n'existait pour cli.py (T3 du backlog, docs/BACKLOG.md) : la
logique de dispatch (bon sous-module appelé avec les bons arguments,
formatage/retour d'erreur) n'était vérifiée que manuellement jusqu'ici.

Base jouet écrite sur disque (pas en mémoire) : cli.main() ouvre sa propre
connexion via `--db <chemin>`, donc `matching.load()` doit pouvoir relire
depuis un fichier réel, pas une connexion déjà ouverte par le test.
"""
import os
import tempfile

import pytest

from hopmatch.cli import main
from hopmatch.schema import connect, init_db


@pytest.fixture()
def db_path():
    path = os.path.join(tempfile.mkdtemp(), "toy.db")
    con = connect(path)
    init_db(con)
    con.executemany("INSERT INTO molecules VALUES (?,?,?,?)",
                    [("molx", "x", None, None), ("moly", "y", None, None)])
    purpose = {"hopa": "aromatic", "hopb": "bittering"}
    for v, desc in (("hopa", ["citrus", "woody"]), ("hopb", ["floral"])):
        con.execute("INSERT INTO hops VALUES (?,?,?,?,?)",
                    (v, v.title(), "test", "toy", purpose[v]))
        for d in desc:
            con.execute("INSERT INTO hop_descriptors VALUES (?,?,?)", (v, d, "toy"))
    rows = [
        ("hopa", "molx", 50, 50, "pct_oil", "toy", "ok", ""),
        ("hopa", "total_oil", 1.0, 1.0, "ml_100g", "toy", "ok", ""),
        ("hopb", "moly", 50, 50, "pct_oil", "toy", "ok", ""),
        ("hopb", "total_oil", 1.0, 1.0, "ml_100g", "toy", "ok", ""),
    ]
    con.executemany("INSERT INTO hop_composition VALUES (?,?,?,?,?,?,?,?)", rows)
    con.executemany("INSERT INTO aroma_notes VALUES (?,?,?,?)", [
        ("mynote", "molx", 1.0, "toy"), ("mynote", "moly", 0.5, "toy"),
    ])
    con.commit()
    con.close()
    return path


def test_list(db_path, capsys):
    assert main(["list", "--db", db_path]) == 0
    out = capsys.readouterr().out
    assert "mynote" in out
    assert "Hopa" in out and "Hopb" in out


def test_descriptors(db_path, capsys):
    assert main(["descriptors", "--db", db_path]) == 0
    out = capsys.readouterr().out
    assert "citrus" in out and "floral" in out and "woody" in out


def test_amplify_dispatches_and_prints_ranking(db_path, capsys):
    assert main(["amplify", "mynote", "--db", db_path]) == 0
    out = capsys.readouterr().out
    assert "[AMPLIFY] mynote" in out
    assert "Hopa" in out  # molx (poids 1.0) > moly (poids 0.5) -> hopa en tête

def test_amplify_blend_dispatches(db_path, capsys):
    assert main(["amplify-blend", "mynote", "--db", db_path,
                "--descriptors", "citrus,woody", "--max-hops", "2"]) == 0
    out = capsys.readouterr().out
    assert "[AMPLIFY-BLEND] mynote" in out
    assert "cible descripteurs : citrus, woody" in out

def test_amplify_blend_without_descriptors_reports_no_blend(db_path, capsys):
    assert main(["amplify-blend", "mynote", "--db", db_path]) == 0
    out = capsys.readouterr().out
    assert "aucun blend possible" in out

def test_amplify_unknown_note_returns_1(db_path, capsys):
    assert main(["amplify", "not-a-note", "--db", db_path]) == 1
    out = capsys.readouterr().out
    assert "Note inconnue" in out

def test_amplify_warns_on_low_molecular_coverage(db_path, capsys):
    # note à couverture quasi nulle : une grosse molécule orpheline (10.0)
    # domine largement une petite productible (0.1) -> couverture ~1%, bien
    # sous LOW_COVERAGE_WARNING_THRESHOLD (20%).
    con = connect(db_path)
    con.executemany("INSERT INTO aroma_notes VALUES (?,?,?,?)", [
        ("lownote", "molx", 0.1, "toy"), ("lownote", "bigorphan", 10.0, "toy"),
    ])
    con.commit(); con.close()
    assert main(["amplify", "lownote", "--db", db_path]) == 0
    out = capsys.readouterr().out
    assert "ATTENTION" in out and "couverture moléculaire faible" in out

def test_amplify_no_low_coverage_warning_when_coverage_high(db_path, capsys):
    # "mynote" (fixture) : 100% de couverture -> pas d'avertissement.
    assert main(["amplify", "mynote", "--db", db_path]) == 0
    out = capsys.readouterr().out
    assert "ATTENTION" not in out

def test_amplify_with_manual_descriptors(db_path, capsys):
    assert main(["amplify", "mynote", "--db", db_path,
                "--descriptors", "citrus,woody"]) == 0
    out = capsys.readouterr().out
    assert "[AMPLIFY] mynote" in out
    assert "pas de descripteurs pour cette note" not in out

def test_by_descriptor_dispatches(db_path, capsys):
    assert main(["by-descriptor", "citrus", "--db", db_path]) == 0
    out = capsys.readouterr().out
    assert "[BY-DESCRIPTOR] citrus" in out
    assert "Hopa" in out
    assert "Hopb" not in out  # hopb n'a pas "citrus"

def test_contrast_without_note_or_descriptors_returns_1(db_path, capsys):
    assert main(["contrast", "--db", db_path]) == 1
    out = capsys.readouterr().out
    assert "descriptors" in out or "note_descriptors" in out

def test_contrast_with_descriptors_dispatches(db_path, capsys):
    assert main(["contrast", "--db", db_path, "--descriptors", "citrus"]) == 0
    out = capsys.readouterr().out
    assert "[CONTRAST] citrus" in out

def test_contrast_blend_dispatches(db_path, capsys):
    assert main(["contrast-blend", "--db", db_path,
                "--descriptors", "citrus", "--max-hops", "2"]) == 0
    out = capsys.readouterr().out
    assert "[CONTRAST-BLEND] citrus" in out

def test_missing_subcommand_errors(db_path):
    with pytest.raises(SystemExit):
        main(["--db", db_path])
