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

def test_normalize_hop_key_strips_trademark_and_brand_words():
    # "Mosaic® Brand" (Yakima) et "mosaic" (slug BeerMaverick) doivent
    # converger vers la même clé pour se réconcilier (T25 backlog).
    assert ingest._normalize_hop_key("Mosaic® Brand") == ingest._normalize_hop_key("mosaic")
    assert ingest._normalize_hop_key("Nelson Sauvin™  Brand - NZ Hops") == \
        ingest._normalize_hop_key("nelson-sauvin")

def test_resolve_hop_variety_matches_by_variety_or_name(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.execute("INSERT INTO hops VALUES (?,?,?,?)",
               ("mosaic-brand", "Mosaic® Brand", "United States", "yakima"))
    con.commit()
    index = ingest._build_hop_name_index(con)
    # via le slug BeerMaverick (proche de variety, pas identique)
    assert ingest._resolve_hop_variety(index, "mosaic") == "mosaic-brand"
    # via le nom affiché (avec habillage commercial différent)
    assert ingest._resolve_hop_variety(index, "Mosaic") == "mosaic-brand"

def test_resolve_hop_variety_none_for_unknown_hop(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.commit()
    assert ingest._resolve_hop_variety(ingest._build_hop_name_index(con), "adeena") is None

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
    # "basilic" : nom donné via `notes` (surcharge additive) ; "mango" : auto-dérivé
    # de Food.csv en minuscule, jamais mentionné dans `notes` -> preuve que
    # all_foods=True dépasse bien la liste passée dans `notes`.
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


def test_extract_foodb_tarball_places_csvs_at_expected_path(tmp_path):
    import tarfile
    src_dir = tmp_path / "src" / "foodb_2020_04_07_csv"
    src_dir.mkdir(parents=True)
    (src_dir / "Food.csv").write_text("id,name\n1,Mango\n")
    tar_path = tmp_path / "foodb_2020_4_7_csv.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(src_dir, arcname="foodb_2020_04_07_csv")

    extract_root = tmp_path / "extracted"
    extract_root.mkdir()
    ingest._extract_foodb_tarball(str(tar_path), str(extract_root))

    extracted_csv = extract_root / "foodb_2020_04_07_csv" / "Food.csv"
    assert extracted_csv.exists()
    assert "Mango" in extracted_csv.read_text()


def test_download_foodb_dump_skips_if_already_present(tmp_path, monkeypatch):
    dest = tmp_path / "already_here"
    dest.mkdir()
    (dest / "Food.csv").write_text("id,name\n1,Mango\n")

    def _boom(*a, **k):
        raise AssertionError("ne doit pas faire de requête réseau si le dump existe déjà")
    monkeypatch.setattr("requests.get", _boom)

    result = ingest.download_foodb_dump(dest_dir=str(dest))
    assert result == str(dest)


def _foodb_fixture_with_generic_food(tmp_path):
    """3e aliment ('Generic Herb') dont le seul composé listé n'a aucune
    concentration mesurée (que du bruit générique, cf. capers/chervil)."""
    pd.DataFrame({"id": [1, 2, 3], "name": ["Sweet basil", "Mango", "Generic Herb"]}).to_csv(
        tmp_path / "Food.csv", index=False)
    pd.DataFrame({"id": [10, 11], "cas_number": ["78-70-6", "5989-27-5"]}).to_csv(
        tmp_path / "Compound.csv", index=False)
    pd.DataFrame({
        "source_type": ["Compound", "Compound", "Compound"], "food_id": [1, 2, 3],
        "source_id": [10, 11, 10], "orig_content": [5.0, 3.0, 0.0],
        "orig_unit": ["mg/100g", "mg/100g", "mg/100g"],
    }).to_csv(tmp_path / "Content.csv", index=False)
    return tmp_path


def test_ingest_foodb_drops_auto_derived_note_without_any_concentration(tmp_path):
    db_path = tmp_path / "test.db"
    con = connect(str(db_path))
    init_db(con)
    con.execute("INSERT INTO flavornet_compounds VALUES (?,?,?)",
               ("78-70-6", "linalool", "floral, citrus"))
    con.execute("INSERT INTO flavornet_compounds VALUES (?,?,?)",
               ("5989-27-5", "limonene", "citrus"))
    con.commit(); con.close()

    foodb_dir = _foodb_fixture_with_generic_food(tmp_path)
    ingest.ingest_foodb(str(db_path), str(foodb_dir), notes={"basilic": "Sweet basil"})

    con = connect(str(db_path))
    notes = {r[0] for r in con.execute("SELECT DISTINCT note FROM aroma_notes")}
    con.close()
    assert "mango" in notes           # auto-dérivé, avec concentration -> gardé
    assert "generic herb" not in notes  # auto-dérivé, sans concentration -> écarté


def test_ingest_foodb_keeps_curated_note_even_without_concentration(tmp_path):
    db_path = tmp_path / "test.db"
    con = connect(str(db_path))
    init_db(con)
    con.execute("INSERT INTO flavornet_compounds VALUES (?,?,?)",
               ("78-70-6", "linalool", "floral, citrus"))
    con.commit(); con.close()

    foodb_dir = _foodb_fixture_with_generic_food(tmp_path)
    # "curé" pointé directement sur l'aliment sans concentration : la fusion
    # avec l'amorce littérature ne doit jamais s'effacer, filtre ou pas.
    ingest.ingest_foodb(str(db_path), str(foodb_dir), notes={"herbe-curee": "Generic Herb"})

    con = connect(str(db_path))
    notes = {r[0] for r in con.execute("SELECT DISTINCT note FROM aroma_notes")}
    con.close()
    assert "herbe-curee" in notes


def test_ingest_foodb_curated_and_auto_names_coexist_for_same_food(tmp_path):
    # "basilic" (curé, fusionné à l'amorce littérature) et "sweet basil" (nom
    # brut FooDB, auto-dérivé) doivent tous les deux exister : la surcharge de
    # nommage est additive, elle ne doit jamais faire disparaître la note
    # auto-dérivée au profit de la note curée (cf. retour utilisateur réel :
    # "mango" absent, seule "mangue" présente).
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
    assert "basilic" in notes
    assert "sweet basil" in notes
