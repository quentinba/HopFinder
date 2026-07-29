import pandas as pd

from hopmatch import ingest
from hopmatch.schema import connect, init_db


def test_canonical_compound_prefers_structural_cid_match():
    # 'estragole' (CAS 140-67-0) résout au même CID PubChem (8815) que
    # methyl-chavicol dans reference.MOLECULES -> fusion structurale, pas texte.
    cas_to_hop_name = {"140-67-0": "methyl-chavicol"}
    assert ingest._canonical_compound("140-67-0", "estragole", cas_to_hop_name) == "methyl-chavicol"

def test_canonical_compound_falls_back_to_greek_prefix_without_cid():
    # CID pas résolu (dict vide) -> repli sur le dépréfixage grec historique.
    assert ingest._canonical_compound("87-44-5", "β-caryophyllene", {}) == "caryophyllene"

def test_canonical_compound_falls_back_to_manual_alias_for_aggregation():
    # 'thiols' est une agrégation côté houblon, pas une molécule avec CID propre
    # -> reste géré par reference.ALIASES même quand le CID n'aide pas.
    assert ingest._canonical_compound("51755-83-0", "3-mercaptohexanol", {}) == "thiols"

def test_canonical_compound_keeps_unknown_name_untouched():
    assert ingest._canonical_compound("000-00-0", "some-obscure-compound", {}) == "some-obscure-compound"

def test_build_cas_to_hop_name_from_pubchem_cids_table():
    from hopmatch.schema import connect, init_db
    con = connect(":memory:")
    init_db(con)
    con.execute("INSERT INTO pubchem_cids VALUES (?,?)", ("78-70-6", 6549))   # linalool
    con.execute("INSERT INTO pubchem_cids VALUES (?,?)", ("000-00-0", None))  # non résolu
    mapping = ingest._build_cas_to_hop_name(con)
    assert mapping["78-70-6"] == "linalool"
    assert "000-00-0" not in mapping
    con.close()


def _foodb_fixture(tmp_path):
    pd.DataFrame({"id": [1, 2], "name": ["Sweet basil", "Mango"]}).to_csv(
        tmp_path / "Food.csv", index=False)
    pd.DataFrame({"id": [10, 11], "cas_number": ["78-70-6", "5989-27-5"]}).to_csv(
        tmp_path / "Compound.csv", index=False)
    pd.DataFrame({
        "source_type": ["Compound", "Compound"], "food_id": [1, 2], "source_id": [10, 11],
        "orig_content": [5.0, 3.0], "orig_unit": ["mg/100g", "mg/100g"],
    }).to_csv(tmp_path / "Content.csv", index=False)
    return tmp_path


def test_ingest_foodb_all_foods_adds_notes_beyond_curated_mapping(tmp_path):
    db_path = tmp_path / "test.db"
    con = connect(str(db_path))
    init_db(con)
    con.execute("INSERT INTO flavornet_compounds VALUES (?,?,?)",
               ("78-70-6", "linalool", "floral, citrus"))
    con.execute("INSERT INTO flavornet_compounds VALUES (?,?,?)",
               ("5989-27-5", "limonene", "citrus"))
    con.commit(); con.close()

    foodb_dir = _foodb_fixture(tmp_path)
    ingest.ingest_foodb(str(db_path), str(foodb_dir), notes={"basilic": "Sweet basil"})

    con = connect(str(db_path))
    notes = {r[0] for r in con.execute("SELECT DISTINCT note FROM aroma_notes")}
    con.close()
    # "basilic" : nom curé (surcharge NOTE_TO_FOODB-style) ; "mango" : auto-dérivé
    # de Food.csv en minuscule, jamais mentionné dans `notes` -> preuve que
    # all_foods=True dépasse bien la liste curée.
    assert "basilic" in notes
    assert "mango" in notes


def test_ingest_foodb_curated_only_when_all_foods_false(tmp_path):
    db_path = tmp_path / "test.db"
    con = connect(str(db_path))
    init_db(con)
    con.execute("INSERT INTO flavornet_compounds VALUES (?,?,?)",
               ("78-70-6", "linalool", "floral, citrus"))
    con.execute("INSERT INTO flavornet_compounds VALUES (?,?,?)",
               ("5989-27-5", "limonene", "citrus"))
    con.commit(); con.close()

    foodb_dir = _foodb_fixture(tmp_path)
    ingest.ingest_foodb(str(db_path), str(foodb_dir), notes={"basilic": "Sweet basil"},
                        all_foods=False)

    con = connect(str(db_path))
    notes = {r[0] for r in con.execute("SELECT DISTINCT note FROM aroma_notes")}
    con.close()
    assert "basilic" in notes
    assert "mango" not in notes
