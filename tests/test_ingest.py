import copy
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from hopmatch import ingest, parsers
from hopmatch.schema import connect, init_db

FIXTURES_DIR = Path(__file__).parent / "fixtures"


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

def test_fix_barthhaas_trademark_slug_strips_glued_r():
    # cas réel vérifié en direct : slug BarthHaas "citrar" alors que le <h1>
    # de la page dit "Citra®" -- le ® a été collé en "r" sans séparateur.
    assert ingest._fix_barthhaas_trademark_slug("citrar", "Citra®") == "citra"
    assert ingest._fix_barthhaas_trademark_slug("mosaicr", "Mosaic®") == "mosaic"
    assert ingest._fix_barthhaas_trademark_slug("ekuanotr", "Ekuanot®") == "ekuanot"

def test_fix_barthhaas_trademark_slug_strips_glued_tm():
    assert ingest._fix_barthhaas_trademark_slug("azaccatm", "Azacca™") == "azacca"
    assert ingest._fix_barthhaas_trademark_slug("talustm", "Talus™") == "talus"

def test_fix_barthhaas_trademark_slug_drops_suffix_after_glue_for_merge():
    # "amarillor-vgxp01-cv" : le "r" collé est suivi d'un code cultivar
    # ("VGXP01") absent du <h1> réel -- tout le suffixe est retiré, pas
    # seulement le "r", pour permettre la fusion avec la clé Yakima "amarillo"
    # (vérifié en direct : conserver le suffixe empêchait la fusion).
    assert ingest._fix_barthhaas_trademark_slug(
        "amarillor-vgxp01-cv", "Amarillo®") == "amarillo"

def test_fix_barthhaas_trademark_slug_never_touches_real_hop_names_ending_in_r():
    # NON-RÉGRESSION : de vrais houblons finissent légitimement en "r" et ne
    # doivent jamais être tronqués (Saazer, Glacier, Endeavour, Challenger,
    # Cluster, Pioneer...) -- la correction ne s'applique QUE quand le <h1>
    # réel confirme exactement le motif nom+r/tm collé, jamais par supposition.
    for slug, h1 in [("saazer", "Saazer"), ("glacier", "Glacier"),
                     ("endeavour", "Endeavour"), ("challenger", "Challenger"),
                     ("cluster", "Cluster"), ("pioneer", "Pioneer")]:
        assert ingest._fix_barthhaas_trademark_slug(slug, h1) == slug

def test_fix_barthhaas_trademark_slug_missing_h1_leaves_slug_unchanged():
    # pas de <h1> parsé (échec réseau/structure) -> filet de sécurité, pas de
    # correction hasardeuse.
    assert ingest._fix_barthhaas_trademark_slug("citrar", None) == "citrar"

def test_resolve_hop_variety_matches_by_variety_or_name(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES (?,?,?,?,?)",
               ("mosaic-brand", "Mosaic® Brand", "United States", "yakima", None))
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

def test_ingest_variety_barthhaas_overwrites_yakima_name_on_merge(tmp_path):
    # bug signalé par l'utilisateur (2026-08-19) : le nom n'était mis à jour
    # qu'à la création, jamais sur fusion -- un houblon ingéré par Yakima
    # PUIS BarthHaas gardait pour toujours le nom Yakima ("Mosaic® Brand"),
    # même une fois BarthHaas fusionné avec son nom plus propre ("Mosaic®").
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "mosaic", "Mosaic® Brand", "United States", {}, [], "yakima")
    ingest._ingest_variety(con, "mosaic", "Mosaic®", "Germany", {}, [], "barthhaas")
    row = con.execute("SELECT name, sources FROM hops WHERE variety='mosaic'").fetchone()
    assert row[0] == "Mosaic®"
    assert set(row[1].split(",")) == {"yakima", "barthhaas"}

def test_ingest_variety_yakima_never_overwrites_barthhaas_name_on_merge(tmp_path):
    # l'inverse : BarthHaas ingéré en premier, Yakima ensuite -- BarthHaas
    # (source primaire) doit rester le nom affiché.
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "mosaic", "Mosaic®", "Germany", {}, [], "barthhaas")
    ingest._ingest_variety(con, "mosaic", "Mosaic® Brand", "United States", {}, [], "yakima")
    row = con.execute("SELECT name FROM hops WHERE variety='mosaic'").fetchone()
    assert row[0] == "Mosaic®"

def test_ingest_variety_same_source_reingestion_refreshes_name(tmp_path):
    # variété SANS BarthHaas : une réingestion Yakima (ex. après un correctif
    # de parsing comme le retrait du suffixe "Brand") doit pouvoir rafraîchir
    # le nom -- rien d'autre ne le protège puisqu'aucune autre source ne l'a
    # jamais touché.
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "kohatu", "Kohatu® Brand - NZ Hops", "New Zealand", {}, [], "yakima")
    ingest._ingest_variety(con, "kohatu", "Kohatu® - NZ Hops", "New Zealand", {}, [], "yakima")
    row = con.execute("SELECT name FROM hops WHERE variety='kohatu'").fetchone()
    assert row[0] == "Kohatu® - NZ Hops"

def test_find_variety_by_name_region_merges_same_name_same_region(tmp_path):
    # bug signalé par l'utilisateur (2026-08-19, "there is two Amarillo
    # entry... check why and fix it for this hop and other if it exists") :
    # 5 paires réelles vérifiées en direct sur la base réingérée (Challenger,
    # Fuggle, Hallertauer Tradition, Hersbrucker Spät, Target) portaient un
    # `name` STRICTEMENT identique entre BarthHaas et Yakima mais un slug
    # `variety` différent (ex. "wye-challenger" vs "challenger") -- jamais
    # fusionnées faute de mécanisme de réconciliation cross-source au-delà du
    # slug exact/dépréfixage marque (contrairement à `_resolve_hop_variety`
    # pour BeerMaverick).
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "wye-challenger", "Challenger", "Great Britain", {}, [], "barthhaas")
    assert ingest._find_variety_by_name_region(con, "Challenger", "United Kingdom") == "wye-challenger"

def test_find_variety_by_name_region_tolerates_gb_uk_alias():
    # BarthHaas dit "Great Britain", Yakima dit "United Kingdom" pour le même
    # pays -- vérifié en direct sur les 3 paires concernées (Challenger,
    # Fuggle, Target). Alias volontairement restreint à ce cas précis.
    assert ingest._normalize_region_for_merge("Great Britain") == \
        ingest._normalize_region_for_merge("United Kingdom")

def test_find_variety_by_name_region_none_when_region_differs(tmp_path):
    # NE fusionne PAS Amarillo US et Amarillo Allemagne : vérifié en direct
    # sur l'API Algolia Yakima (imported_fields.country_code) que ce sont
    # deux crops RÉELLEMENT distincts du même cultivar (VGXP01), même
    # famille de cas que Perle US/Allemagne ou Saaz US/Tchéquie déjà gardés
    # séparés à raison -- une région différente doit bloquer la fusion.
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "amarillo", "Amarillo®", "United States", {}, [], "barthhaas")
    assert ingest._find_variety_by_name_region(con, "Amarillo®", "Germany") is None

def test_find_variety_by_name_region_none_without_region(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "challenger", "Challenger", None, {}, [], "yakima")
    assert ingest._find_variety_by_name_region(con, "Challenger", None) is None

def test_merge_hop_varieties_moves_composition_descriptors_and_sources(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "wye-challenger", "Challenger", "Great Britain",
                           {"myrcene": (40, 50, "pct_oil")}, ["citrus"], "barthhaas")
    ingest._ingest_variety(con, "challenger", "Challenger", "United Kingdom",
                           {"caryophyllene": (5, 6, "pct_oil")}, ["woody"], "yakima")
    con.execute("UPDATE hops SET purpose=? WHERE variety=?", ("both", "challenger"))
    con.commit()
    ingest.merge_hop_varieties(con, keep="wye-challenger", drop="challenger")
    hop = con.execute("SELECT sources, purpose FROM hops WHERE variety='wye-challenger'").fetchone()
    assert set(hop["sources"].split(",")) == {"barthhaas", "yakima"}
    assert hop["purpose"] == "both"
    assert con.execute("SELECT 1 FROM hops WHERE variety='challenger'").fetchone() is None
    compounds = {r["compound"] for r in
                con.execute("SELECT compound FROM hop_composition WHERE variety='wye-challenger'")}
    assert compounds == {"myrcene", "caryophyllene"}
    descriptors = {r["descriptor"] for r in
                  con.execute("SELECT descriptor FROM hop_descriptors WHERE variety='wye-challenger'")}
    assert descriptors == {"citrus", "woody"}

def test_merge_hop_varieties_redirects_relations_pointing_at_dropped_key(tmp_path):
    # les associations houblon<->houblon (hop_similar/hop_pairings/
    # hop_substitutions) référençant la variety supprimée DEPUIS un AUTRE
    # houblon doivent être redirigées vers la survivante, pas laissées en
    # référence morte.
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "wye-challenger", "Challenger", "Great Britain", {}, [], "barthhaas")
    ingest._ingest_variety(con, "challenger", "Challenger", "United Kingdom", {}, [], "yakima")
    ingest._ingest_variety(con, "citra", "Citra®", "United States", {}, [], "barthhaas")
    con.execute("INSERT INTO hop_similar VALUES (?,?,?)", ("citra", "challenger", "yakima"))
    con.commit()
    ingest.merge_hop_varieties(con, keep="wye-challenger", drop="challenger")
    row = con.execute("SELECT similar_variety FROM hop_similar WHERE variety='citra'").fetchone()
    assert row["similar_variety"] == "wye-challenger"

def test_merge_hop_varieties_idempotent_when_already_merged(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "wye-challenger", "Challenger", "Great Britain", {}, [], "barthhaas")
    con.commit()
    ingest.merge_hop_varieties(con, keep="wye-challenger", drop="challenger")  # drop absente -> no-op
    assert con.execute("SELECT 1 FROM hops WHERE variety='wye-challenger'").fetchone() is not None

def test_normalize_beermaverick_tag_drops_non_aroma_quality_words():
    # "mild"/"clean"/"hoppy"... ne sont pas des descripteurs d'arôme (voir
    # _BEERMAVERICK_TAG_DROPLIST) -> None, jamais écrits dans hop_descriptors.
    for tag in ("mild", "clean", "hoppy", "noble", "bohemian"):
        assert ingest._normalize_beermaverick_tag(tag) is None

def test_normalize_beermaverick_tag_applies_underscore_and_alias():
    # "resin" est un vrai renommage du même concept que "resinous" (DESCRIPTOR_ALIASES).
    assert ingest._normalize_beermaverick_tag("resin") == "resinous"
    # "cannabis" est un quasi-synonyme de "dank" en terminologie houblon.
    assert ingest._normalize_beermaverick_tag("cannabis") == "dank"
    # underscore -> espace avant résolution alias ("tropical fruit" -> "tropical" existait déjà).
    assert ingest._normalize_beermaverick_tag("tropical_fruit") == "tropical"

def test_normalize_beermaverick_tag_keeps_subfamily_terms_distinct():
    # les sous-familles réelles (raspberry, jasmine...) restent des descripteurs
    # à part entière, pas écrasées vers leur catégorie cœur (contrairement aux
    # vrais renommages ci-dessus) -> voir reference.CONTRAST_AFFINITY.
    assert ingest._normalize_beermaverick_tag("raspberry") == "raspberry"
    assert ingest._normalize_beermaverick_tag("black_pepper") == "black pepper"

def test_normalize_beermaverick_purpose_maps_known_values():
    assert ingest._normalize_beermaverick_purpose("Aroma") == "aromatic"
    assert ingest._normalize_beermaverick_purpose("Bittering") == "bittering"
    assert ingest._normalize_beermaverick_purpose("Dual") == "both"
    # insensible à la casse (texte brut extrait du HTML, pas normalisé en amont)
    assert ingest._normalize_beermaverick_purpose("dual") == "both"

def test_normalize_beermaverick_purpose_unknown_or_absent_returns_none():
    assert ingest._normalize_beermaverick_purpose(None) is None
    assert ingest._normalize_beermaverick_purpose("") is None
    assert ingest._normalize_beermaverick_purpose("Noble") is None

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


def _bjcp_fixture_payload() -> dict:
    with open(FIXTURES_DIR / "bjcp_sample.json", encoding="utf-8") as f:
        return json.load(f)


def test_parse_beerjson_styles_returns_one_row_per_style():
    rows = parsers.parse_beerjson_styles(_bjcp_fixture_payload())
    assert {r["style_id"] for r in rows} == {"21A", "28A", "X1"}


def test_parse_beerjson_styles_extracts_vital_stats_with_correct_unit():
    # 21A : style complet, les 5 vital stats sont présentes avec leur unité
    # attendue (sg/%/IBUs/SRM) -- valeurs réelles vérifiées sur bjcp-json.
    rows = {r["style_id"]: r for r in parsers.parse_beerjson_styles(_bjcp_fixture_payload())}
    s = rows["21A"]
    assert s["og_min"] == 1.056 and s["og_max"] == 1.07
    assert s["fg_min"] == 1.008 and s["fg_max"] == 1.014
    assert s["abv_min"] == 5.5 and s["abv_max"] == 7.5
    assert s["ibu_min"] == 40 and s["ibu_max"] == 70
    assert s["srm_min"] == 6 and s["srm_max"] == 14


def test_parse_beerjson_styles_leaves_vital_stats_null_never_zero_when_absent():
    # 28A (Brett Beer) : un des 17 styles réels sans AUCUNE vital stat --
    # hérite du style de base choisi par le brasseur, ce n'est PAS un trou de
    # données à combler par 0.
    rows = {r["style_id"]: r for r in parsers.parse_beerjson_styles(_bjcp_fixture_payload())}
    s = rows["28A"]
    for field in ("og_min", "og_max", "fg_min", "fg_max", "abv_min", "abv_max",
                  "ibu_min", "ibu_max", "srm_min", "srm_max"):
        assert s[field] is None, f"{field} devrait être NULL, jamais 0"


def test_parse_beerjson_styles_raises_on_unexpected_unit():
    # unité inattendue (ex. "plato" au lieu de "sg") -- doit échouer
    # bruyamment plutôt qu'écrire une valeur dans la mauvaise unité.
    payload = _bjcp_fixture_payload()
    style = next(s for s in payload["beerjson"]["styles"] if s["style_id"] == "21A")
    style = copy.deepcopy(style)
    style["original_gravity"]["minimum"]["unit"] = "plato"
    payload = {"beerjson": {"version": payload["beerjson"]["version"],
                            "styles": [style]}}
    with pytest.raises(ValueError, match="unité inattendue"):
        parsers.parse_beerjson_styles(payload)


def test_parse_beerjson_styles_normalizes_gravity_off_by_1000_bug():
    # T82 : style réel X2 ("IPA Argenta") porte og/fg en 1055/1065/1008/1015
    # (unité "sg" correcte, virgule décimale omise côté bjcp-json) -- décision
    # utilisateur : normaliser (/1000) toute valeur sg > 10.
    payload = _bjcp_fixture_payload()
    style = next(s for s in payload["beerjson"]["styles"] if s["style_id"] == "21A")
    style = copy.deepcopy(style)
    style["style_id"] = "X2"
    style["original_gravity"] = {"minimum": {"unit": "sg", "value": 1055},
                                 "maximum": {"unit": "sg", "value": 1065}}
    style["final_gravity"] = {"minimum": {"unit": "sg", "value": 1008},
                              "maximum": {"unit": "sg", "value": 1015}}
    payload = {"beerjson": {"version": payload["beerjson"]["version"], "styles": [style]}}
    rows = parsers.parse_beerjson_styles(payload)
    s = rows[0]
    assert s["og_min"] == 1.055 and s["og_max"] == 1.065
    assert s["fg_min"] == 1.008 and s["fg_max"] == 1.015


def test_parse_beerjson_styles_leaves_plausible_gravity_values_untouched():
    # garde-fou : une vraie densité (toujours < 2) ne doit jamais être divisée.
    rows = {r["style_id"]: r for r in parsers.parse_beerjson_styles(_bjcp_fixture_payload())}
    s = rows["21A"]
    assert s["og_min"] == 1.056  # pas 0.001056


def test_parse_beerjson_styles_maps_leaked_spanish_keys_to_english_fields():
    # X1 : style provisoire aux clés espagnoles qui ont fuité (sabor,
    # historia, ingredientes, impresion_general, aspecto, sensacion_en_boca,
    # comentarios) -- doivent remplir les champs anglais correspondants,
    # jamais rester orphelines ni écraser une valeur anglaise déjà présente.
    payload = _bjcp_fixture_payload()
    x1 = next(s for s in payload["beerjson"]["styles"] if s["style_id"] == "X1")
    rows = {r["style_id"]: r for r in parsers.parse_beerjson_styles(payload)}
    s = rows["X1"]
    assert s["flavor"] == x1["sabor"]
    assert s["history"] == x1["historia"]
    assert s["ingredients"] == x1["ingredientes"]
    assert s["overall_impression"] == x1["impresion_general"]
    assert s["appearance"] == x1["aspecto"]
    assert s["mouthfeel"] == x1["sensacion_en_boca"]
    assert s["comments"] == x1["comentarios"]


def test_parse_beerjson_styles_leaked_key_never_overwrites_real_english_value():
    # garde-fou : un style qui aurait À LA FOIS "flavor" (anglais) et "sabor"
    # (fuite) ne doit jamais laisser "sabor" écraser "flavor" -- même si ce
    # cas n'existe pas dans les données réelles actuelles.
    payload = {"beerjson": {"version": 2.01, "styles": [
        {"style_id": "ZZ", "name": "Test", "category": "Test", "category_id": "99",
         "type": "beer", "flavor": "real english value", "sabor": "should be ignored"},
    ]}}
    rows = parsers.parse_beerjson_styles(payload)
    assert rows[0]["flavor"] == "real english value"


def test_parse_beerjson_styles_sets_source_to_bjcp_json():
    rows = parsers.parse_beerjson_styles(_bjcp_fixture_payload())
    assert all(r["source"] == "bjcp-json" for r in rows)


def test_download_bjcp_styles_rejects_unsupported_year_without_network_call():
    # 2015 n'existe pas dans beerjson/bjcp-json -- doit échouer AVANT tout
    # appel réseau (pas de dépendance à un 404 distant pour ce cas).
    with pytest.raises(ValueError, match="2015"):
        ingest.download_bjcp_styles(year=2015)


def test_ingest_beer_styles_creates_table_without_wiping_existing_data(tmp_path, monkeypatch):
    # base déjà peuplée (hops) mais sans encore la table beer_styles (le cas
    # réel d'une base construite avant T81) -- ingest_beer_styles doit créer
    # SEULEMENT beer_styles, jamais vider hops via init_db.
    db_path = tmp_path / "test.db"
    con = connect(str(db_path))
    init_db(con)
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES ('citra', 'Citra', 'United States', 'yakima', NULL)")
    con.execute("DROP TABLE beer_styles")
    con.commit(); con.close()

    monkeypatch.setattr(ingest, "download_bjcp_styles",
                        lambda year=2021, dest_dir=None, force=False:
                            str(FIXTURES_DIR / "bjcp_sample.json"))
    ingest.ingest_beer_styles(str(db_path), year=2021)

    con = connect(str(db_path))
    hops = [r[0] for r in con.execute("SELECT variety FROM hops")]
    n_styles = con.execute("SELECT count(*) FROM beer_styles").fetchone()[0]
    con.close()
    assert hops == ["citra"]  # pas vidé par un init_db caché
    assert n_styles == 3


def test_beer_style_aliases_yaml_values_exist_in_real_bjcp_styles():
    # T84 : garde-fou de non-régression pour data/mappings/beer_style_
    # aliases.yaml -- toute valeur non-null doit être un style_id RÉEL de
    # beer_styles (jamais un id inventé/mal recopié à la main). Même
    # principe que test_ingredient_descriptors_keys_and_terms_match_real_
    # vocabulary : vérifié contre la base réelle (aromahops.db) si
    # présente, aucun appel réseau.
    mapping = ingest._load_yaml_mapping("beer_style_aliases.yaml")
    assert mapping, "le fichier ne doit jamais être vide"
    db_path = os.path.join(os.path.dirname(__file__), "..", "aromahops.db")
    if not os.path.exists(db_path):
        return
    con = connect(db_path)
    real_style_ids = {r[0] for r in con.execute("SELECT DISTINCT style_id FROM beer_styles")}
    con.close()
    for label, style_id in mapping.items():
        if style_id is not None:
            assert style_id in real_style_ids, (label, style_id)


def test_write_hop_beer_styles_resolves_known_label_and_nulls_unknown(tmp_path):
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.commit()
    alias_map = {"American Pale Ale": "18B", "Lager": None}
    ingest._write_hop_beer_styles(con, "citra", ["American Pale Ale", "Lager"], "yakima", alias_map)
    rows = {r[0]: r[1] for r in con.execute(
        "SELECT style_label, style_id FROM hop_beer_styles WHERE variety='citra'")}
    assert rows == {"American Pale Ale": "18B", "Lager": None}


def test_write_hop_beer_styles_leaves_null_for_label_absent_from_alias_map(tmp_path):
    # une étiquette pas encore triée à la main (absente du YAML T84) reste
    # NULL -- jamais devinée par correspondance approximative.
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.commit()
    ingest._write_hop_beer_styles(con, "citra", ["Some New Label"], "yakima", {})
    row = con.execute(
        "SELECT style_id FROM hop_beer_styles WHERE variety='citra' AND style_label='Some New Label'"
    ).fetchone()
    assert row[0] is None


def test_write_hop_beer_styles_keeps_sources_separate_for_same_label(tmp_path):
    # Yakima et BeerMaverick peuvent tous les deux suggérer "IPA" pour le
    # même houblon -- deux lignes distinctes (source tracée par ligne),
    # jamais fusionnées en une seule.
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.commit()
    ingest._write_hop_beer_styles(con, "citra", ["IPA"], "yakima", {})
    ingest._write_hop_beer_styles(con, "citra", ["IPA"], "beermaverick", {})
    rows = con.execute(
        "SELECT source FROM hop_beer_styles WHERE variety='citra' AND style_label='IPA'").fetchall()
    assert {r[0] for r in rows} == {"yakima", "beermaverick"}


def test_write_hop_beer_styles_creates_table_without_wiping_existing_data(tmp_path):
    # même piège que T81 (beer_styles) : hop_beer_styles doit pouvoir être
    # créée sur une base déjà peuplée sans passer par init_db (qui viderait
    # hops/hop_composition/etc.).
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES ('citra', 'Citra', 'United States', 'yakima', NULL)")
    con.execute("DROP TABLE hop_beer_styles")
    con.commit(); con.close()

    from hopmatch.schema import ensure_table, HOP_BEER_STYLES_SCHEMA
    con = connect(str(tmp_path / "t.db"))
    ensure_table(con, "hop_beer_styles", HOP_BEER_STYLES_SCHEMA)
    ingest._write_hop_beer_styles(con, "citra", ["IPA"], "yakima", {})
    con.commit()
    hops = [r[0] for r in con.execute("SELECT variety FROM hops")]
    con.close()
    assert hops == ["citra"]


# --------------------------------------------------------------------------- #
# T106 -- métadonnées d'identité (cultivar/breeder/release_year/pedigree/
# is_experimental/is_organic/is_blend)
# --------------------------------------------------------------------------- #

def test_ensure_columns_creates_hops_identity_columns_without_wiping_existing_data(tmp_path):
    # même piège que ensure_table (T81), mais pour des COLONNES ajoutées à
    # une table qui existe déjà -- une base réelle construite avant T106 n'a
    # pas encore cultivar/breeder/etc.
    from hopmatch.schema import ensure_columns, HOP_IDENTITY_COLUMNS
    con = connect(str(tmp_path / "t.db"))
    con.execute("CREATE TABLE hops (variety TEXT PRIMARY KEY, name TEXT, region TEXT, sources TEXT, purpose TEXT)")
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES ('citra', 'Citra', 'United States', 'yakima', NULL)")
    con.commit()

    ensure_columns(con, "hops", HOP_IDENTITY_COLUMNS)
    con.commit()
    cols = {r["name"] for r in con.execute("PRAGMA table_info(hops)")}
    assert cols >= {"cultivar", "breeder", "release_year", "pedigree",
                    "is_experimental", "is_organic", "is_blend"}
    row = con.execute("SELECT variety, name, cultivar FROM hops WHERE variety='citra'").fetchone()
    con.close()
    assert row["name"] == "Citra"
    assert row["cultivar"] is None

    # idempotent : un second appel ne doit pas lever (colonnes déjà présentes)
    con = connect(str(tmp_path / "t.db"))
    ensure_columns(con, "hops", HOP_IDENTITY_COLUMNS)
    con.close()


def test_bool_to_sqlite_never_defaults_missing_to_zero():
    # jamais 0 par défaut pour une donnée absente -- affirmerait à tort
    # "non expérimental"/"non bio"/"pas un blend".
    assert ingest._bool_to_sqlite(True) == 1
    assert ingest._bool_to_sqlite(False) == 0
    assert ingest._bool_to_sqlite(None) is None


def test_cultivar_base_name_strips_brand_suffix_but_not_real_hyphen():
    assert ingest._cultivar_base_name("Kohatu - NZ Hops") == "Kohatu"
    assert ingest._cultivar_base_name("Motueka - MacHops") == "Motueka"
    assert ingest._cultivar_base_name("Pacifica (Marque Déposée) - MacHops") == "Pacifica"
    # trait d'union sans espace autour -> partie du nom réel, jamais coupé
    assert ingest._cultivar_base_name("Wai-iti - NZ Hops") == "Wai-iti"
    assert ingest._cultivar_base_name("Amarillo") == "Amarillo"


def test_write_hop_identity_applies_to_sibling_variety_rows_sharing_cultivar(tmp_path):
    # bug réel trouvé en vérifiant T106 en direct : deux crops distincts du
    # même cultivar (ex. Amarillo US vs Amarillo Germany) partagent le même
    # `name` mais sont deux lignes `hops` séparées -- seule UNE des deux est
    # résolue depuis la page BeerMaverick source (l'autre doit recevoir la
    # même généalogie, pas rester NULL par accident d'ordre de crawl).
    from hopmatch.schema import ensure_columns, HOP_IDENTITY_COLUMNS
    con = connect(str(tmp_path / "t.db"))
    con.execute("CREATE TABLE hops (variety TEXT PRIMARY KEY, name TEXT, region TEXT, sources TEXT, purpose TEXT)")
    ensure_columns(con, "hops", HOP_IDENTITY_COLUMNS)
    con.execute("INSERT INTO hops (variety, name, region, sources) VALUES "
               "('amarillo', 'Amarillo', 'United States', 'barthhaas,yakima')")
    con.execute("INSERT INTO hops (variety, name, region, sources) VALUES "
               "('amarillo-brand-ama04', 'Amarillo', 'Germany', 'yakima')")
    con.execute("INSERT INTO hops (variety, name, region, sources) VALUES "
               "('citra', 'Citra', 'United States', 'yakima')")
    con.commit()

    mapping = {"Amarillo": {"breeder": "Virgil Gamache Farms", "pedigree": "Discovered 1990"}}
    n = ingest._write_hop_identity(con, mapping)
    con.commit()
    rows = {r["variety"]: dict(r) for r in con.execute("SELECT * FROM hops")}
    con.close()

    assert n == 2
    assert rows["amarillo"]["breeder"] == "Virgil Gamache Farms"
    assert rows["amarillo-brand-ama04"]["breeder"] == "Virgil Gamache Farms"
    assert rows["amarillo"]["pedigree"] == "Discovered 1990"
    # release_year absent du mapping (jamais deviné) -> NULL, pas 0/fabriqué
    assert rows["amarillo"]["release_year"] is None
    # variété sans entrée dans le mapping -> colonnes inchangées (NULL)
    assert rows["citra"]["breeder"] is None


# --------------------------------------------------------------------------- #
# T107 -- description éditoriale (hops.description/description_source)
# --------------------------------------------------------------------------- #

def test_ensure_columns_creates_hops_description_columns_without_wiping_existing_data(tmp_path):
    # même piège que T106 (ensure_table/ensure_columns) : une base réelle
    # construite avant T107 n'a pas encore description/description_source.
    from hopmatch.schema import ensure_columns, HOP_DESCRIPTION_COLUMNS
    con = connect(str(tmp_path / "t.db"))
    con.execute("CREATE TABLE hops (variety TEXT PRIMARY KEY, name TEXT, region TEXT, sources TEXT, purpose TEXT)")
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES ('citra', 'Citra', 'United States', 'yakima', NULL)")
    con.commit()

    ensure_columns(con, "hops", HOP_DESCRIPTION_COLUMNS)
    con.commit()
    cols = {r["name"] for r in con.execute("PRAGMA table_info(hops)")}
    assert cols >= {"description", "description_source"}
    row = con.execute("SELECT name, description FROM hops WHERE variety='citra'").fetchone()
    con.close()
    assert row["name"] == "Citra"
    assert row["description"] is None


# --------------------------------------------------------------------------- #
# T85 -- beer-analytics.com (style_recipe_stats)
# --------------------------------------------------------------------------- #

_BA_SITEMAP_FIXTURE = (
    "<?xml version=\"1.0\"?><urlset><url><loc>"
    "https://www.beer-analytics.com/styles/india-pale-ale/american-ipa/"
    "</loc></url></urlset>")

_BA_STYLE_PAGE_FIXTURE = (
    "<html><body><h1>American IPA</h1>"
    '<div data-chart="/styles/ipa/american-ipa/charts/abv-histogram.json"></div>'
    '<div data-chart="/styles/ipa/american-ipa/charts/ibu-histogram.json"></div>'
    "</body></html>")

# gabarit réduit (ticket T85 : "un seul trace, 3 bins") -- forme réelle
# vérifiée en direct sur abv-histogram/American IPA (2026-08-27).
_BA_ABV_CHART_FIXTURE = json.dumps({
    "data": [{"x": ["(5.0, 5.3]", "(5.3, 5.6]", "(5.6, 5.9]"], "y": [10, 20, 5], "type": "bar"}],
    "layout": {"template": "unused, jamais parsé"},
})
_BA_IBU_CHART_FIXTURE = json.dumps({
    "data": [{"x": ["(30.0, 40.0]"], "y": [7], "type": "bar"}],
    "layout": {},
})

_BA_FIXTURES = {
    "/sitemap.xml": _BA_SITEMAP_FIXTURE,
    # page fetchée à l'URL du SITEMAP (catégorie longue "india-pale-ale"),
    # alors que les data-chart qu'elle contient pointent vers la catégorie
    # COURTE "ipa" -- exactement l'écart documenté par le ticket T85.
    "/styles/india-pale-ale/american-ipa/": _BA_STYLE_PAGE_FIXTURE,
    "/styles/ipa/american-ipa/charts/abv-histogram.json": _BA_ABV_CHART_FIXTURE,
    "/styles/ipa/american-ipa/charts/ibu-histogram.json": _BA_IBU_CHART_FIXTURE,
}


def test_ingest_beer_analytics_writes_bins_and_resolves_style_id(tmp_path, monkeypatch):
    # aucun appel réseau : _beer_analytics_fetch et _load_yaml_mapping mockés.
    monkeypatch.setattr(ingest, "_beer_analytics_fetch", lambda path, **kw: _BA_FIXTURES[path])
    monkeypatch.setattr(ingest, "_load_yaml_mapping", lambda filename: {"American IPA": "21B"})

    db_path = str(tmp_path / "t.db")
    ingest.ingest_beer_analytics(db_path)

    con = connect(db_path)
    rows = [dict(r) for r in con.execute(
        "SELECT style_id, style_slug, metric, bin_low, bin_high, count, source "
        "FROM style_recipe_stats ORDER BY metric, bin_low")]
    con.close()
    assert rows == [
        {"style_id": "21B", "style_slug": "american-ipa", "metric": "abv",
         "bin_low": 5.0, "bin_high": 5.3, "count": 10, "source": "beer-analytics"},
        {"style_id": "21B", "style_slug": "american-ipa", "metric": "abv",
         "bin_low": 5.3, "bin_high": 5.6, "count": 20, "source": "beer-analytics"},
        {"style_id": "21B", "style_slug": "american-ipa", "metric": "abv",
         "bin_low": 5.6, "bin_high": 5.9, "count": 5, "source": "beer-analytics"},
        {"style_id": "21B", "style_slug": "american-ipa", "metric": "ibu",
         "bin_low": 30.0, "bin_high": 40.0, "count": 7, "source": "beer-analytics"},
    ]

def test_ingest_beer_analytics_leaves_style_id_null_when_unresolved(tmp_path, monkeypatch):
    # aucun alias connu -> style_id NULL, jamais deviné par similarité.
    monkeypatch.setattr(ingest, "_beer_analytics_fetch", lambda path, **kw: _BA_FIXTURES[path])
    monkeypatch.setattr(ingest, "_load_yaml_mapping", lambda filename: {})

    db_path = str(tmp_path / "t.db")
    ingest.ingest_beer_analytics(db_path)

    con = connect(db_path)
    style_ids = {r[0] for r in con.execute("SELECT DISTINCT style_id FROM style_recipe_stats")}
    con.close()
    assert style_ids == {None}

def test_ingest_beer_analytics_creates_table_without_wiping_existing_data(tmp_path, monkeypatch):
    # même piège que T81/T83/T106/T107 : style_recipe_stats doit pouvoir être
    # créée sur une base déjà peuplée sans passer par init_db.
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) "
               "VALUES ('citra', 'Citra', 'United States', 'yakima', NULL)")
    con.execute("DROP TABLE style_recipe_stats")
    con.commit(); con.close()

    monkeypatch.setattr(ingest, "_beer_analytics_fetch", lambda path, **kw: _BA_FIXTURES[path])
    monkeypatch.setattr(ingest, "_load_yaml_mapping", lambda filename: {"American IPA": "21B"})
    ingest.ingest_beer_analytics(str(tmp_path / "t.db"))

    con = connect(str(tmp_path / "t.db"))
    hops = [r[0] for r in con.execute("SELECT variety FROM hops")]
    n_bins = con.execute("SELECT COUNT(*) FROM style_recipe_stats").fetchone()[0]
    con.close()
    assert hops == ["citra"]
    assert n_bins == 4

def test_beer_analytics_cache_filename_flattens_path():
    assert ingest._beer_analytics_cache_filename(
        "/styles/ipa/american-ipa/charts/abv-histogram.json"
    ) == "styles_ipa_american-ipa_charts_abv-histogram.json"
    assert ingest._beer_analytics_cache_filename(
        "/styles/ipa/american-ipa/"
    ) == "styles_ipa_american-ipa.html"

def test_beer_analytics_cache_filename_keeps_json_extension_with_query_string():
    # T86 : bug réel trouvé en direct -- "....json?filter=aroma" ne se
    # termine plus par ".json" littéralement, tombait dans le repli ".html"
    # (contenu réellement JSON) avant correction.
    assert ingest._beer_analytics_cache_filename(
        "/styles/ipa/american-ipa/charts/popular-hops.json?filter=aroma"
    ) == "styles_ipa_american-ipa_charts_popular-hops__filter_aroma.json"

def test_beer_analytics_cache_filename_distinguishes_different_query_strings():
    # deux filtres différents du même chart -> entrées de cache DISTINCTES,
    # jamais une collision (payloads réellement différents, vérifié en direct).
    a = ingest._beer_analytics_cache_filename(
        "/styles/ipa/american-ipa/charts/popular-hops.json?filter=aroma")
    b = ingest._beer_analytics_cache_filename(
        "/styles/ipa/american-ipa/charts/popular-hops.json?filter=bittering")
    c = ingest._beer_analytics_cache_filename(
        "/styles/ipa/american-ipa/charts/popular-hops.json")
    assert len({a, b, c}) == 3

def test_beer_analytics_fetch_uses_disk_cache_and_skips_network_on_hit(tmp_path, monkeypatch):
    # `requests`/`time` sont importés LOCALEMENT dans _beer_analytics_fetch
    # (même style que le reste du module) -- patcher le module `requests`
    # global fonctionne quand même (même objet partagé via sys.modules).
    import requests as _requests
    calls = []
    class FakeResponse:
        text = "cached content"
        def raise_for_status(self): pass
    def fake_get(url, timeout, headers):
        calls.append(url)
        return FakeResponse()
    monkeypatch.setattr(_requests, "get", fake_get)

    cache_dir = str(tmp_path / "cache")
    text1 = ingest._beer_analytics_fetch("/styles/ipa/american-ipa/", cache_dir=cache_dir, sleep=0)
    text2 = ingest._beer_analytics_fetch("/styles/ipa/american-ipa/", cache_dir=cache_dir, sleep=0)
    assert text1 == "cached content"
    assert text2 == "cached content"
    assert len(calls) == 1  # deuxième appel = hit de cache, aucun 2e GET réseau


# --------------------------------------------------------------------------- #
# T86 -- beer-analytics.com (style_hop_usage)
# --------------------------------------------------------------------------- #

_BA_STYLE_PAGE_WITH_HOP_USAGE_FIXTURE = (
    "<html><body><h1>American IPA</h1>"
    '<div data-chart="/styles/ipa/american-ipa/charts/popular-hops.json"></div>'
    '<div data-chart="/styles/ipa/american-ipa/charts/popular-hops-amount.json"></div>'
    "</body></html>")


def _ba_pct_chart(citra_last, centennial_last):
    # gabarit trimmé d'une vraie trace popular-hops.json (scattergl, série
    # temporelle) -- deux houblons, quelques mois seulement (le parseur ne
    # dépend pas d'une longueur fixe, voir parsers.parse_time_series_trace).
    return json.dumps({
        "data": [
            {"name": "Citra", "type": "scattergl", "y": [0.30, 0.32, citra_last]},
            {"name": "Centennial", "type": "scattergl", "y": [0.20, 0.21, centennial_last]},
        ],
        "layout": {"template": "unused"},
    })


def _ba_amount_chart(citra_median):
    return json.dumps({
        "data": [
            {"name": "Citra", "type": "box", "q1": [0.2], "median": [citra_median], "q3": [0.5]},
            {"name": "Centennial", "type": "box", "q1": [0.1], "median": [0.15], "q3": [0.2]},
        ],
        "layout": {},
    })


_BA_HOP_USAGE_FIXTURES = {
    "/sitemap.xml": _BA_SITEMAP_FIXTURE,
    "/styles/india-pale-ale/american-ipa/": _BA_STYLE_PAGE_WITH_HOP_USAGE_FIXTURE,
    "/styles/ipa/american-ipa/charts/popular-hops.json": _ba_pct_chart(0.36, 0.21),
    "/styles/ipa/american-ipa/charts/popular-hops.json?filter=bittering":
        _ba_pct_chart(0.21, 0.16),
    "/styles/ipa/american-ipa/charts/popular-hops.json?filter=aroma": _ba_pct_chart(0.40, 0.25),
    "/styles/ipa/american-ipa/charts/popular-hops.json?filter=dry-hop": _ba_pct_chart(0.45, 0.10),
    "/styles/ipa/american-ipa/charts/popular-hops-amount.json": _ba_amount_chart(0.36),
    "/styles/ipa/american-ipa/charts/popular-hops-amount.json?filter=bittering":
        _ba_amount_chart(0.18),
    "/styles/ipa/american-ipa/charts/popular-hops-amount.json?filter=aroma": _ba_amount_chart(0.40),
    "/styles/ipa/american-ipa/charts/popular-hops-amount.json?filter=dry-hop": _ba_amount_chart(0.50),
}


def test_ingest_style_hop_usage_writes_one_row_per_usage_type(tmp_path, monkeypatch):
    # aucun appel réseau : _beer_analytics_fetch/_get et _load_yaml_mapping mockés.
    monkeypatch.setattr(ingest, "_beer_analytics_fetch",
                        lambda path, **kw: _BA_HOP_USAGE_FIXTURES[path])
    monkeypatch.setattr(ingest, "_beer_analytics_get",
                        lambda path, **kw: json.loads(_BA_HOP_USAGE_FIXTURES[path]))
    monkeypatch.setattr(ingest, "_load_yaml_mapping", lambda filename: {"American IPA": "21A"})

    db_path = str(tmp_path / "t.db")
    ingest.ingest_style_hop_usage(db_path)

    con = connect(db_path)
    rows = {r["usage_type"]: dict(r) for r in con.execute(
        "SELECT * FROM style_hop_usage WHERE style_slug='american-ipa' AND hop_name='Citra'")}
    con.close()

    assert set(rows) == {"any", "bittering", "aroma", "dry-hop"}
    # "quoi maintenant" (dernière valeur) DIFFÉRENT par usage_type -- pas
    # un simple filtrage client qui renverrait la même chose partout.
    assert rows["any"]["recipes_pct_latest"] == 0.36
    assert rows["bittering"]["recipes_pct_latest"] == 0.21
    assert rows["aroma"]["recipes_pct_latest"] == 0.40
    assert rows["dry-hop"]["recipes_pct_latest"] == 0.45
    # style_id résolu, propagé à chaque ligne
    assert all(r["style_id"] == "21A" for r in rows.values())
    # dosage (boxplot) capturé séparément de la part de recettes -- même ligne
    assert rows["any"]["amount_median"] == 0.36
    assert rows["bittering"]["amount_median"] == 0.18

def test_ingest_style_hop_usage_resolves_variety_and_avg24m(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "_beer_analytics_fetch",
                        lambda path, **kw: _BA_HOP_USAGE_FIXTURES[path])
    monkeypatch.setattr(ingest, "_beer_analytics_get",
                        lambda path, **kw: json.loads(_BA_HOP_USAGE_FIXTURES[path]))
    monkeypatch.setattr(ingest, "_load_yaml_mapping", lambda filename: {"American IPA": "21A"})

    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) "
               "VALUES ('citra', 'Citra', 'United States', 'yakima', NULL)")
    con.commit(); con.close()

    ingest.ingest_style_hop_usage(str(tmp_path / "t.db"))

    con = connect(str(tmp_path / "t.db"))
    row = con.execute("SELECT * FROM style_hop_usage WHERE hop_name='Citra' AND usage_type='any'").fetchone()
    unresolved = con.execute("SELECT variety FROM style_hop_usage WHERE hop_name='Centennial' "
                             "AND usage_type='any'").fetchone()
    con.close()
    assert row["variety"] == "citra"
    # 3 points fournis par la fixture -> moyenne des 3 (fenêtre 24 mois pas
    # atteinte, jamais comblée artificiellement)
    assert row["recipes_pct_avg24m"] == pytest.approx((0.30 + 0.32 + 0.36) / 3)
    # Centennial absent de `hops` dans ce test -> variety NULL, jamais deviné
    assert unresolved["variety"] is None

def test_ingest_style_hop_usage_creates_table_without_wiping_existing_data(tmp_path, monkeypatch):
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) "
               "VALUES ('citra', 'Citra', 'United States', 'yakima', NULL)")
    con.execute("DROP TABLE style_hop_usage")
    con.commit(); con.close()

    monkeypatch.setattr(ingest, "_beer_analytics_fetch",
                        lambda path, **kw: _BA_HOP_USAGE_FIXTURES[path])
    monkeypatch.setattr(ingest, "_beer_analytics_get",
                        lambda path, **kw: json.loads(_BA_HOP_USAGE_FIXTURES[path]))
    monkeypatch.setattr(ingest, "_load_yaml_mapping", lambda filename: {"American IPA": "21A"})
    ingest.ingest_style_hop_usage(str(tmp_path / "t.db"))

    con = connect(str(tmp_path / "t.db"))
    hops = [r[0] for r in con.execute("SELECT variety FROM hops")]
    n = con.execute("SELECT COUNT(*) FROM style_hop_usage").fetchone()[0]
    con.close()
    assert hops == ["citra"]
    assert n == 8  # 2 houblons x 4 usage_type
