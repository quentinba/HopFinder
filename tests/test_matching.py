import os, tempfile
import pytest
from hopmatch import ingest, matching, reference
from hopmatch.schema import connect, init_db

FIX = os.path.join(os.path.dirname(__file__), "..", "data", "fixtures")

@pytest.fixture(scope="module")
def db():
    # build_from_fixtures ne seed plus aucune note (reference.AROMA_NOTES/
    # NOTE_DESCRIPTORS ont été retirés, cf. reference.py) : les notes de test
    # sont insérées ici directement, comme des données de test locales plutôt
    # que via une amorce littérature globale.
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    ingest.build_from_fixtures(FIX, path)
    con = connect(path)
    con.executemany("INSERT INTO aroma_notes VALUES (?,?,?,?)", [
        # mirrors l'ancienne note "yuzu" : limonene absent du houblon (orphelin
        # garanti), linalool/myrcene présents dans les fixtures.
        ("_citrus", "limonene", 1.0, "test"),
        ("_citrus", "linalool", 0.7, "test"),
        ("_citrus", "myrcene", 0.4, "test"),
        # mirrors l'ancienne note "fruit-passion" : thiols (barthhaas only).
        ("_passion", "thiols", 1.0, "test"),
        ("_passion", "myrcene", 0.3, "test"),
    ])
    con.executemany("INSERT INTO note_descriptors VALUES (?,?)", [
        ("_citrus", "citrus"), ("_citrus", "floral"),
    ])
    con.commit()
    yield con
    con.close()

def test_disambiguate_hop_names_appends_region_only_on_name_collision():
    # T60 (2026-08-19) : "you either need to remove duplicate or modify the
    # name base on the provenance" -- la provenance (région) est facile à
    # retrouver (déjà dans `hops.region`, vérifiée en direct via l'API
    # Algolia Yakima pour Amarillo/Perle/Saaz/Northern Brewer, T53/T54), donc
    # modification du nom retenue plutôt que suppression : ces paires sont
    # deux crops RÉELLEMENT distincts (même cultivar, pays différent), pas
    # un doublon accidentel -- fusionner perdrait la distinction de terroir.
    hops = {
        "amarillo": {"name": "Amarillo®", "region": "United States"},
        "amarillo-brand-ama04": {"name": "Amarillo®", "region": "Germany"},
        "citra": {"name": "Citra®", "region": "United States"},  # pas de collision
    }
    matching._disambiguate_hop_names(hops)
    assert hops["amarillo"]["name"] == "Amarillo® (United States)"
    assert hops["amarillo-brand-ama04"]["name"] == "Amarillo® (Germany)"
    assert hops["citra"]["name"] == "Citra®"

def test_disambiguate_hop_names_skips_collision_without_region():
    # Filet de sécurité : si la région manque d'un côté, pas de suffixe
    # fabriqué -- le nom reste ambigu plutôt qu'un libellé "(None)".
    hops = {
        "a": {"name": "Foo", "region": None},
        "b": {"name": "Foo", "region": "Germany"},
    }
    matching._disambiguate_hop_names(hops)
    assert hops["a"]["name"] == "Foo"
    assert hops["b"]["name"] == "Foo (Germany)"

def test_load_applies_disambiguation_to_returned_hops(tmp_path):
    # `load()` doit être la SEULE source de vérité : tout consommateur
    # (amplify/contrast/by_descriptor/blends/CLI/GUI) voit déjà le nom
    # désambiguïsé sans code répété ailleurs.
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "nb-us", "Northern Brewer", "United States", {}, [], "yakima")
    ingest._ingest_variety(con, "nb-de", "Northern Brewer", "Germany", {}, [], "yakima")
    con.commit()
    hops, _, _, _ = matching.load(con)
    assert hops["nb-us"]["name"] == "Northern Brewer (United States)"
    assert hops["nb-de"]["name"] == "Northern Brewer (Germany)"

def test_merge_multisource(db):
    # Citra doit fusionner β-pinène (yakima) + thiols (barthhaas)
    _, comp, _, _ = matching.load(db)
    assert comp["citra"]["beta-pinene"]["sources"] == ["yakima"]
    assert comp["citra"]["thiols"]["sources"] == ["barthhaas"]
    assert set(comp["citra"]["myrcene"]["sources"]) == {"barthhaas", "yakima"}

def test_similar_hops_by_composition_ranks_closest_first(db):
    # T67 (2026-08-21) : Mosaic partage plus de composés-signature avec Citra
    # (thiols, isobutyrate, beta-pinene -- via la fusion barthhaas/yakima) que
    # Simcoe/Saazer -> doit ressortir premier, jamais le houblon requêté
    # lui-même.
    ranked = matching.similar_hops_by_composition(db, "citra")
    varieties = [r["variety"] for r in ranked]
    assert "citra" not in varieties
    assert varieties[0] == "mosaic"
    assert varieties == sorted(varieties, key=lambda v: -next(
        r["similarity"] for r in ranked if r["variety"] == v))
    for r in ranked:
        assert 0 < r["similarity"] <= 100
        assert r["shared_compounds"]

def test_similar_hops_by_composition_penalizes_incomplete_coverage(db):
    # T67 addendum (2026-08-21, signalé par l'utilisateur en direct sur
    # données réelles : Callista, BarthHaas seul et donc partiellement
    # mesuré, ressortait #1 pour Citra devant Mosaic malgré une couverture
    # complète -- le cosinus pur ignore les dimensions manquantes, un
    # houblon moins mesuré ne devrait jamais dépasser un houblon à
    # couverture complète). Simcoe (yakima seul, sans thiols/isobutyrate/
    # ketones -- composés BarthHaas) a un cosinus brut élevé avec Citra
    # (mêmes proportions sur les composés partagés) mais une couverture
    # incomplète -- le score final doit refléter cette pénalité, pas
    # seulement le cosinus.
    ranked = {r["variety"]: r for r in matching.similar_hops_by_composition(db, "citra")}
    assert ranked["mosaic"]["coverage"] == 100.0
    assert ranked["simcoe"]["coverage"] < 100.0
    # similarity == cosinus * coverage : jamais plus élevée qu'une
    # couverture à 100% ne le permettrait pour un cosinus équivalent ou
    # inférieur.
    assert ranked["simcoe"]["similarity"] < ranked["mosaic"]["similarity"]

def test_similar_hops_by_composition_unknown_variety_returns_empty(db):
    assert matching.similar_hops_by_composition(db, "does-not-exist") == []

def test_similar_hops_by_composition_no_composition_returns_empty(tmp_path):
    # Houblon en base mais sans aucune ligne hop_composition -- rien à
    # comparer, pas d'erreur (repli honnête, même principe que amplify()
    # sur une note sans molécule productible).
    con = connect(str(tmp_path / "t.db"))
    init_db(con)
    ingest._ingest_variety(con, "empty", "Empty Hop", "Nowhere", {}, [], "test")
    con.commit()
    assert matching.similar_hops_by_composition(con, "empty") == []

def test_similar_hops_by_aroma_wheel_ranks_and_penalizes_coverage(db):
    # T68 (2026-08-21, demande utilisateur : "we also could use the
    # quantitative aroma wheel scores right?"). Mosaic (3/3 catégories,
    # valeurs proches de citra) doit dominer Simcoe (2/3, tropical très
    # différent) -- même principe de pénalité de couverture que la couche
    # moléculaire (T67 addendum).
    db.executemany("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)", [
        ("citra", "citrus", 80.0, "yakima"), ("citra", "tropical", 70.0, "yakima"),
        ("citra", "floral", 20.0, "yakima"),
        ("mosaic", "citrus", 75.0, "yakima"), ("mosaic", "tropical", 65.0, "yakima"),
        ("mosaic", "floral", 25.0, "yakima"),
        ("simcoe", "citrus", 80.0, "yakima"), ("simcoe", "tropical", 10.0, "yakima"),
    ])
    db.commit()
    try:
        ranked = matching.similar_hops_by_aroma_wheel(db, "citra")
        varieties = [r["variety"] for r in ranked]
        assert "citra" not in varieties
        assert varieties[0] == "mosaic"
        assert "saazer" not in varieties  # aucune donnée hop_aroma_intensity
        ranked_by_v = {r["variety"]: r for r in ranked}
        assert ranked_by_v["mosaic"]["coverage"] == 100.0
        assert ranked_by_v["simcoe"]["coverage"] < 100.0
        assert ranked_by_v["simcoe"]["similarity"] < ranked_by_v["mosaic"]["similarity"]
    finally:
        db.execute("DELETE FROM hop_aroma_intensity WHERE variety IN ('citra','mosaic','simcoe')")
        db.commit()

def test_similar_hops_by_aroma_wheel_empty_without_data(db):
    assert matching.similar_hops_by_aroma_wheel(db, "citra") == []

def test_similar_hops_combines_layers_averaging_only_available_ones(db):
    # T68 : combinaison = moyenne des couches actives ayant une donnée pour
    # CE candidat -- Saazer n'a que la couche moléculaire (aucune ligne
    # hop_aroma_intensity) et doit quand même apparaître, `layers_used`
    # honnête, similarité combinée == similarité moléculaire seule (moyenne
    # à un seul terme), jamais un score pénalisé pour une donnée absente.
    db.executemany("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)", [
        ("citra", "citrus", 80.0, "yakima"), ("citra", "tropical", 70.0, "yakima"),
        ("citra", "floral", 20.0, "yakima"),
        ("mosaic", "citrus", 75.0, "yakima"), ("mosaic", "tropical", 65.0, "yakima"),
        ("mosaic", "floral", 25.0, "yakima"),
    ])
    db.commit()
    try:
        both = {r["variety"]: r for r in matching.similar_hops(db, "citra")}
        assert both["mosaic"]["layers_used"] == ["aroma_wheel", "molecular"]
        assert both["mosaic"]["similarity"] == round(
            (both["mosaic"]["molecular_similarity"] + both["mosaic"]["aroma_wheel_similarity"]) / 2, 1)
        assert both["saazer"]["layers_used"] == ["molecular"]
        assert both["saazer"]["aroma_wheel_similarity"] is None
        assert both["saazer"]["similarity"] == both["saazer"]["molecular_similarity"]

        mol_only = {r["variety"]: r for r in
                   matching.similar_hops(db, "citra", use_aroma_wheel=False)}
        assert mol_only["mosaic"]["layers_used"] == ["molecular"]
        assert mol_only["mosaic"]["similarity"] == mol_only["mosaic"]["molecular_similarity"]

        assert matching.similar_hops(db, "citra", use_molecular=False,
                                     use_aroma_wheel=False) == []
    finally:
        db.execute("DELETE FROM hop_aroma_intensity WHERE variety IN ('citra','mosaic')")
        db.commit()

def test_compound_descriptors_resolves_via_cid_cas_chain(db):
    # T70 (2026-08-21) : jointure par IDENTITÉ STRUCTURALE (CID PubChem
    # reference.MOLECULES -> CAS pubchem_cids -> descripteurs
    # flavornet_compounds), pas par nom de chaîne -- reproduit ici avec le
    # vrai CID myrcène (31253, reference.MOLECULES) sur un CAS de test.
    # "herbal (Janish, The New IPA)" ajouté en plus (T73) : "herb" absent de
    # "balsamic, must, spice" -> pas déjà couvert, catégorie ajoutée et citée.
    db.executemany("INSERT INTO pubchem_cids VALUES (?,?)", [("123-35-3", 31253)])
    db.executemany("INSERT INTO flavornet_compounds VALUES (?,?,?)",
                   [("123-35-3", "myrcene", "balsamic, must, spice")])
    db.commit()
    try:
        # "nonexistent" absent du vocabulaire houblon -> absent du résultat.
        assert matching.compound_descriptors(db, ["myrcene", "nonexistent"]) == {
            "myrcene": "balsamic, must, spice; herbal (Janish, The New IPA)"}
    finally:
        db.execute("DELETE FROM pubchem_cids WHERE cas='123-35-3'")
        db.execute("DELETE FROM flavornet_compounds WHERE cas='123-35-3'")
        db.commit()

def test_compound_descriptors_falls_back_to_janish_without_cas_resolution(db):
    # T73 (2026-08-21, "The New IPA" de Scott Janish, p.22) : CID connu
    # (reference.MOLECULES) mais aucune ligne pubchem_cids pour ce CID
    # (resolve_pubchem_cids pas lancé/CAS introuvable) -> Flavornet ne
    # répond rien, mais reference.JANISH_COMPOUND_CATEGORIES a une entrée
    # pour myrcene ("herbal") -> repli, toujours cité explicitement, jamais
    # confondu avec une donnée Flavornet.
    assert matching.compound_descriptors(db, ["myrcene"]) == {
        "myrcene": "herbal (Janish, The New IPA)"}

def test_compound_descriptors_absent_without_any_resolution(db):
    # selinene : CID connu mais ni CAS résolu (pubchem_cids vide) ni entrée
    # reference.JANISH_COMPOUND_CATEGORIES (absent du tableau du livre,
    # vérifié en direct sur les 12 catégories) -> absent des deux sources,
    # pas de valeur inventée.
    assert matching.compound_descriptors(db, ["selinene"]) == {}

def test_compound_descriptors_thiols_resolves_only_via_janish(db):
    # T73 : thiols n'a pas de CID propre (agrégation, reference.ALIASES) --
    # ne peut donc JAMAIS passer par Flavornet, quelle que soit la base.
    # reference.JANISH_COMPOUND_CATEGORIES a une entrée sourcée sur le 4MMP
    # (composé listé "Berry & Currant" dans le livre, déjà agrégé sous
    # "thiols" par ALIASES) -- seule résolution possible pour ce composé,
    # jamais silencieusement absent.
    assert matching.compound_descriptors(db, ["thiols"]) == {
        "thiols": "berry & currant (Janish, The New IPA)"}

def test_compound_descriptors_dedups_janish_category_already_covered(db):
    # T73 : si le descripteur Flavornet couvre DÉJÀ la catégorie du livre
    # (comparaison par racine de 4 lettres -- "herb"), la catégorie Janish
    # n'est PAS ajoutée en double -- même mécanisme vérifié en production
    # sur caryophyllene/humulene/farnesene (déjà couverts par "wood"/
    # "spice" Flavornet, aucun ajout visible). "FIXTURE-herbXX" : chaîne
    # délibérément synthétique/imprononçable (PAS une vraie donnée
    # Flavornet, pour ne jamais pouvoir être confondue avec une vraie
    # valeur produit -- signalé par l'utilisateur sur un choix précédent,
    # "herbal, minty", qui pouvait à tort ressembler à une donnée réelle),
    # ne contient QUE la racine "herb" nécessaire pour exercer le dédoublonnage.
    db.executemany("INSERT INTO pubchem_cids VALUES (?,?)", [("123-35-3", 31253)])
    db.executemany("INSERT INTO flavornet_compounds VALUES (?,?,?)",
                   [("123-35-3", "myrcene", "FIXTURE-herbXX")])
    db.commit()
    try:
        assert matching.compound_descriptors(db, ["myrcene"]) == {"myrcene": "FIXTURE-herbXX"}
    finally:
        db.execute("DELETE FROM pubchem_cids WHERE cas='123-35-3'")
        db.execute("DELETE FROM flavornet_compounds WHERE cas='123-35-3'")
        db.commit()

def test_process_survival_all_hop_composition_compounds_have_a_decision(db):
    # T74 (2026-08-21, "The New IPA" de Scott Janish, figure "Chemical
    # compositions of the essential oils of hops") : chaque composé
    # DISTINCT réellement présent dans hop_composition doit être soit
    # mappé (reference.PROCESS_SURVIVAL), soit explicitement exclu
    # (matching.NON_AROMA_DISPLAY -- acides alpha/bêta, co-humulone, huile
    # totale, qui ne sont pas des composants de l'huile essentielle). Ce
    # test échoue dès qu'un composé nouveau apparaît sans décision prise --
    # jamais un oubli silencieux.
    compounds = {r[0] for r in db.execute("SELECT DISTINCT compound FROM hop_composition")}
    undecided = compounds - set(matching.reference.PROCESS_SURVIVAL) - matching.NON_AROMA_DISPLAY
    assert not undecided, f"composé(s) sans décision de survie au procédé : {undecided}"

def test_process_survival_excludes_non_essential_oil_compounds():
    # Acides alpha/bêta, co-humulone, huile totale : pas des composants de
    # l'huile essentielle (isomérisation à l'ébullition, sans rapport avec
    # la volatilité/solubilité qui gouverne le reste de la table) -- ne
    # reçoivent JAMAIS d'annotation, même par accident.
    for c in matching.NON_AROMA_DISPLAY:
        assert matching.process_survival(c) is None

def test_process_survival_returns_none_for_unmapped_compound():
    # limonene : dans reference.MOLECULES (molécule d'huile de houblon
    # connue) mais JAMAIS mesuré dans hop_composition par BarthHaas/Yakima
    # actuellement (vérifié en direct, 2026-08-21) -- pas d'entrée ici, une
    # annotation qui ne s'afficherait jamais serait une entrée morte. Les
    # 11 composés RÉELLEMENT présents sont tous mappés avec certitude (voir
    # test_process_survival_all_hop_composition_compounds_have_a_decision) --
    # aucun composé réel n'est donc "juste absent du tableau Janish" dans
    # cette base. "nonexistent" : hors vocabulaire houblon.
    assert matching.process_survival("limonene") is None
    assert matching.process_survival("nonexistent") is None

def test_process_survival_returns_full_structure_for_mapped_compound():
    # myrcene : monoterpène (Janish) -- les 4 champs demandés (classe/sous-
    # classe/annotation/confiance) présents, `confidence` DANS la structure
    # (pas seulement en commentaire) pour que la GUI puisse afficher une
    # réserve visible. Annotation quantifiée (2026-08-27, Scott Janish, The
    # New IPA, relayé par l'utilisateur) : ~50% de perte à 10 min de boil,
    # quasi totale à 60 min -- partagée avec linalool (même comportement),
    # jamais avec beta-pinène (même sous-classe mais donnée non établie).
    info = matching.process_survival("myrcene")
    assert info == {"class": "Hydrocarbons", "subclass": "Monoterpenes",
                    "annotation": "boil-sensitive, survives whirlpool", "confidence": "high"}

def test_process_survival_low_confidence_entries_flagged():
    # isobutyrate/ketones : agrégats BarthHaas sans molécule nominative
    # précise dans le livre -- confidence="low" explicite, pas une
    # affirmation au même niveau que les composés individuellement
    # identifiés (ex. myrcene, confidence="high").
    for c in ("isobutyrate", "ketones"):
        assert matching.process_survival(c)["confidence"] == "low"

def test_process_survival_never_contains_a_numeric_value():
    # Contrainte non négociable du ticket : aucune valeur numérique nulle
    # part dans la structure (pas de taux de transfert, pas de
    # multiplicateur) -- vérifié directement sur les valeurs de tous les
    # champs de toutes les entrées.
    for entry in matching.reference.PROCESS_SURVIVAL.values():
        for value in entry.values():
            assert isinstance(value, str)
            assert not any(ch.isdigit() for ch in value)

def test_process_survival_every_annotation_has_an_explanation():
    # 2026-08-21 (suite directe de T74, demande utilisateur : "I'm not sure
    # to understand the difference [between] 'direct traces, contribute via
    # oxydation' [and] 'survive boiling'") : chaque annotation DISTINCTE
    # réellement utilisée dans PROCESS_SURVIVAL doit avoir une explication
    # -- échoue si une nouvelle annotation est ajoutée sans sa légende.
    annotations = {v["annotation"] for v in matching.reference.PROCESS_SURVIVAL.values()}
    missing = annotations - set(matching.reference.PROCESS_SURVIVAL_EXPLANATIONS)
    assert not missing, f"annotation(s) sans explication : {missing}"

def test_process_survival_never_consulted_by_any_scoring_path(db, monkeypatch):
    # T74, point de vigilance soulevé par l'utilisateur en direct (relecture
    # externe) : "Le test « résultats identiques avant/après » est là pour
    # attraper ça [l'annotation transformée en critère de sélection]." Un
    # test qui compare juste des valeurs attendues FIGÉES (comme le reste de
    # la suite existante, déjà vert avant/après T74) n'attrape qu'un
    # changement qui modifie CES valeurs précises -- pas un futur appel
    # ajouté par erreur qui laisserait le classement inchangé par coïncidence.
    # Preuve structurelle plus forte : on rend `matching.process_survival`
    # EXPLOSIF (n'importe quel appel lève), puis on fait tourner amplify/
    # contrast/by_descriptor sur les mêmes note/descripteurs que le reste de
    # la suite -- si l'un d'eux consultait PROCESS_SURVIVAL, même sans
    # changer le résultat final, ce test échouerait immédiatement.
    def _boom(compound):
        raise AssertionError(f"process_survival() appelé depuis un chemin de score pour {compound!r}")
    monkeypatch.setattr(matching, "process_survival", _boom)
    matching.amplify(db, "_citrus")
    matching.contrast(db, descriptors=["citrus", "floral"])
    matching.by_descriptor(db, ["citrus", "tropical"])

def test_amplify_ranks(db):
    r = matching.amplify(db, "_citrus")
    assert r["ranked"], "au moins un houblon"
    assert 0 <= r["coverage"] <= 1

def test_orphans_flagged(db):
    r = matching.amplify(db, "_citrus")
    # limonène n'existe pas dans le houblon -> orphelin
    assert "limonene" in r["orphan"]

def test_hop_aroma_intensity_empty_without_yakima_sensory_data(db):
    # fixtures (texte BarthHaas/Yakima) n'alimentent pas hop_aroma_intensity
    # (donnée Algolia YCH uniquement, voir ingest.crawl_yakima) -> vide, pas
    # de valeur inventée. T79 : signature étendue à (valeurs, source) pour
    # exposer la provenance résolue -- source `None` quand rien n'existe.
    assert matching.hop_aroma_intensity(db, "citra") == ({}, None)

def test_hop_aroma_intensity_reads_inserted_rows(db):
    db.execute("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)",
              ("citra", "citrus", 90.0, "yakima"))
    db.commit()
    assert matching.hop_aroma_intensity(db, "citra") == ({"citrus": 90.0}, "yakima")
    db.execute("DELETE FROM hop_aroma_intensity WHERE variety='citra'")
    db.commit()

def test_resolve_aroma_intensity_empty_by_source():
    assert matching.resolve_aroma_intensity({}) == ({}, None)

def test_resolve_aroma_intensity_defaults_to_yakima_over_barthhaas():
    by_source = {"yakima": {"citrus": 50.0}, "barthhaas": {"citrus": 4.0}}
    assert matching.resolve_aroma_intensity(by_source) == ({"citrus": 50.0}, "yakima")

def test_resolve_aroma_intensity_rescales_barthhaas_from_0_8_to_0_100():
    # T79 : BarthHaas mesure sur 0-8, jamais mélangé tel quel avec l'échelle
    # 0-100 de Yakima -- remis à l'échelle uniquement quand c'est la source
    # RÉELLEMENT utilisée (ici, seule source dispo).
    by_source = {"barthhaas": {"citrus": 4.0, "floral": 8.0}}
    values, source = matching.resolve_aroma_intensity(by_source)
    assert source == "barthhaas"
    assert values == {"citrus": 50.0, "floral": 100.0}

def test_resolve_aroma_intensity_prefer_falls_back_silently_when_absent():
    # `prefer="barthhaas"` mais ce houblon n'a QUE du Yakima -- jamais un
    # houblon vidé par un choix de toggle qui ne s'applique pas ici.
    by_source = {"yakima": {"citrus": 50.0}}
    assert matching.resolve_aroma_intensity(by_source, prefer="barthhaas") == (
        {"citrus": 50.0}, "yakima")

def test_resolve_aroma_intensity_prefer_honored_when_available():
    by_source = {"yakima": {"citrus": 50.0}, "barthhaas": {"citrus": 4.0}}
    values, source = matching.resolve_aroma_intensity(by_source, prefer="barthhaas")
    assert source == "barthhaas"
    assert values == {"citrus": 50.0}

def test_resolve_aroma_intensity_skips_degenerate_all_zero_preferred_source():
    # T79 addendum (signalé en direct par l'utilisateur sur Admiral) : une
    # entrée Yakima PRÉSENTE mais entièrement à 0 (cas corrompu documenté,
    # voir docs/DATA_SOURCES.md) n'est pas une vraie mesure -- l'ordre de
    # préférence par défaut doit sauter par-dessus et retomber
    # automatiquement sur BarthHaas, jamais afficher une roue vide alors
    # qu'une donnée réelle existe.
    by_source = {"yakima": {"citrus": 0.0, "floral": 0.0}, "barthhaas": {"citrus": 4.0}}
    values, source = matching.resolve_aroma_intensity(by_source)
    assert source == "barthhaas"
    assert values == {"citrus": 50.0}

def test_resolve_aroma_intensity_all_sources_degenerate_falls_back_to_default_order():
    # Si AUCUNE source n'est exploitable, on ne plante pas et on retombe sur
    # l'ordre de préférence classique (peu importe laquelle, le résultat est
    # dégénéré de toute façon).
    by_source = {"yakima": {"citrus": 0.0}, "barthhaas": {"citrus": 0.0}}
    values, source = matching.resolve_aroma_intensity(by_source)
    assert source == "yakima"
    assert values == {"citrus": 0.0}

def test_select_aroma_intensity_returns_exact_source_no_fallback():
    # T79 4e addendum (2026-08-23) : contrairement à resolve_aroma_intensity,
    # jamais de repli automatique -- "barthhaas" absent ici doit renvoyer {},
    # pas basculer silencieusement sur yakima.
    by_source = {"yakima": {"citrus": 50.0}}
    assert matching.select_aroma_intensity(by_source, "barthhaas") == {}
    assert matching.select_aroma_intensity(by_source, "yakima") == {"citrus": 50.0}

def test_select_aroma_intensity_rescales_barthhaas():
    by_source = {"barthhaas": {"citrus": 4.0, "floral": 8.0}}
    assert matching.select_aroma_intensity(by_source, "barthhaas") == {
        "citrus": 50.0, "floral": 100.0}

def test_select_aroma_intensity_empty_on_degenerate_all_zero_source():
    by_source = {"yakima": {"citrus": 0.0, "floral": 0.0}}
    assert matching.select_aroma_intensity(by_source, "yakima") == {}

def test_default_aroma_wheel_source_yakima_when_usable():
    by_source = {"yakima": {"citrus": 50.0}, "barthhaas": {"citrus": 4.0}}
    assert matching.default_aroma_wheel_source(by_source) == "yakima"

def test_default_aroma_wheel_source_falls_back_to_barthhaas_when_yakima_degenerate():
    # Admiral -- entrée Yakima présente mais corrompue à 0, BarthHaas réel.
    by_source = {"yakima": {"citrus": 0.0}, "barthhaas": {"citrus": 4.0}}
    assert matching.default_aroma_wheel_source(by_source) == "barthhaas"

def test_default_aroma_wheel_source_stays_yakima_when_neither_usable():
    by_source = {"yakima": {"citrus": 0.0}, "barthhaas": {"citrus": 0.0}}
    assert matching.default_aroma_wheel_source(by_source) == "yakima"

def test_default_aroma_wheel_source_for_varieties_yakima_when_any_usable():
    all_intensity = {
        "hopa": {"yakima": {"citrus": 0.0}},
        "hopb": {"yakima": {"citrus": 50.0}},
    }
    assert matching.default_aroma_wheel_source_for_varieties(
        all_intensity, ["hopa", "hopb"]) == "yakima"

def test_default_aroma_wheel_source_for_varieties_barthhaas_when_all_yakima_missing():
    all_intensity = {
        "hopa": {"yakima": {"citrus": 0.0}},
        "hopb": {"barthhaas": {"citrus": 4.0}},
    }
    assert matching.default_aroma_wheel_source_for_varieties(
        all_intensity, ["hopa", "hopb"]) == "barthhaas"

def test_aroma_wheel_vocabulary_full_without_source_filter(db):
    db.execute("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)",
              ("_fixture_vocab_full", "citrus", 50.0, "yakima"))
    db.commit()
    vocab = matching.aroma_wheel_vocabulary(db)
    assert "citrus" in vocab
    assert vocab == sorted(vocab)
    db.execute("DELETE FROM hop_aroma_intensity WHERE variety='_fixture_vocab_full'")
    db.commit()

def test_aroma_wheel_vocabulary_restricted_to_given_sources(db):
    db.executemany("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)", [
        ("_fixture_vocab_bh", "menthol", 3.0, "barthhaas"),
        ("_fixture_vocab_yk", "melon", 10.0, "yakima"),
    ])
    db.commit()
    bh_vocab = matching.aroma_wheel_vocabulary(db, {"barthhaas"})
    assert "menthol" in bh_vocab
    assert "melon" not in bh_vocab
    yk_vocab = matching.aroma_wheel_vocabulary(db, {"yakima"})
    assert "melon" in yk_vocab
    db.execute("DELETE FROM hop_aroma_intensity WHERE variety IN "
              "('_fixture_vocab_bh','_fixture_vocab_yk')")
    db.commit()

def test_load_aroma_intensity_groups_by_variety_then_source(db):
    # noms de variété fictifs (jamais dans les fixtures) pour ne toucher
    # aucune donnée réelle utilisée par d'autres tests de ce module partagé.
    db.executemany("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)", [
        ("_fixture_multi_source", "citrus", 50.0, "yakima"),
        ("_fixture_multi_source", "citrus", 4.0, "barthhaas"),
        ("_fixture_bh_only", "spicy", 6.0, "barthhaas"),
    ])
    db.commit()
    out = matching.load_aroma_intensity(db)
    assert out["_fixture_multi_source"] == {"yakima": {"citrus": 50.0}, "barthhaas": {"citrus": 4.0}}
    assert out["_fixture_bh_only"] == {"barthhaas": {"spicy": 6.0}}
    db.execute("DELETE FROM hop_aroma_intensity WHERE variety IN "
              "('_fixture_multi_source','_fixture_bh_only')")
    db.commit()

def test_hop_similar_varieties_empty_without_yakima_data(db):
    assert matching.hop_similar_varieties(db, "citra") == []

def test_hop_popularity_sums_recipes_count_across_use_types(db):
    db.executemany("INSERT INTO hop_usage_stats VALUES (?,?,?,?,?,?,?,?,?)", [
        ("_fixture_popular", "Fixture Popular", "Boil", 100, None, None, None, "test", "2026"),
        ("_fixture_popular", "Fixture Popular", "Dry Hop", 50, None, None, None, "test", "2026"),
        # recipes_count NULL (chart présent mais dosage seul résolu, T88) --
        # jamais compté comme 0, simplement ignoré dans la somme.
        ("_fixture_partial", "Fixture Partial", "Boil", None, 0.2, 0.3, 0.4, "test", "2026"),
    ])
    db.commit()
    out = matching.hop_popularity(db)
    assert out["_fixture_popular"] == 150
    # aucune ligne avec un recipes_count exploitable -> absent du dict,
    # jamais un 0 fabriqué (T108 : "no data" doit rester distinct de 0).
    assert "_fixture_partial" not in out
    assert "_fixture_never_seen" not in out
    db.execute("DELETE FROM hop_usage_stats WHERE variety IN "
              "('_fixture_popular','_fixture_partial')")
    db.commit()

def test_hop_usage_breakdown_computes_share_per_use_type(db):
    db.executemany("INSERT INTO hop_usage_stats VALUES (?,?,?,?,?,?,?,?,?)", [
        ("_fixture_usage", "Fixture Usage", "Boil", 75, None, None, None, "test", "2026"),
        ("_fixture_usage", "Fixture Usage", "Dry Hop", 25, None, None, None, "test", "2026"),
    ])
    db.commit()
    out = matching.hop_usage_breakdown(db, "_fixture_usage")
    assert out == {
        "Boil": {"recipes_count": 75, "share": 0.75},
        "Dry Hop": {"recipes_count": 25, "share": 0.25},
    }
    # houblon non couvert -> dict vide, jamais une répartition fabriquée.
    assert matching.hop_usage_breakdown(db, "_fixture_never_seen") == {}
    all_breakdowns = matching.hop_usage_breakdown_all(db)
    assert all_breakdowns["_fixture_usage"] == out
    db.execute("DELETE FROM hop_usage_stats WHERE variety='_fixture_usage'")
    db.commit()

def test_style_hop_frequency_filters_to_resolvable_varieties(db):
    db.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES (?,?,?,?,?)",
              ("_fixture_freq_hop", "Fixture Freq Hop", "test", "toy", None))
    db.executemany("INSERT INTO style_hop_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("fixture-style", "_fixture_style2", "Fixture Freq Hop", "_fixture_freq_hop", "any",
         0.3, 0.25, 0.1, 0.2, 0.3, "test", "2026"),
        # variety sans correspondance dans `hops` (T86 : ~90% de résolution,
        # pas 100%) -> exclue par le JOIN, jamais fabriquée.
        ("fixture-style", "_fixture_style2", "Unresolved Hop", "_fixture_unresolved", "any",
         0.1, 0.1, None, None, None, "test", "2026"),
    ])
    db.commit()
    out = matching.style_hop_frequency(db, "_fixture_style2", "any")
    assert out == {"_fixture_freq_hop": {"hop_name": "Fixture Freq Hop",
                                         "share_latest": 0.3, "share_avg24m": 0.25}}
    # usage_type sans ligne -> dict vide, jamais un 0 fabriqué.
    assert matching.style_hop_frequency(db, "_fixture_style2", "dry-hop") == {}
    db.execute("DELETE FROM style_hop_usage WHERE style_id='_fixture_style2'")
    db.execute("DELETE FROM hops WHERE variety='_fixture_freq_hop'")
    db.commit()

def test_style_typical_descriptors_matches_whole_words_only(db):
    db.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES (?,?,?,?,?)",
              ("_fixture_word_hop", "Fixture Word Hop", "test", "toy", None))
    db.executemany("INSERT INTO hop_descriptors VALUES (?,?,?)", [
        ("_fixture_word_hop", "pine", "test"),
        ("_fixture_word_hop", "pineapple", "test"),
    ])
    db.execute(
        "INSERT INTO beer_styles (style_id, guideline_year, aroma, flavor, ingredients) "
        "VALUES (?,?,?,?,?)",
        ("_fixture_style3", 2021, "Citrus and pineapple aroma.", "Not much else.", None))
    db.commit()
    out = matching.style_typical_descriptors(db, "_fixture_style3")
    assert "citrus" in out       # déjà dans le vocabulaire fixture (build_from_fixtures)
    assert "pineapple" in out
    # "pine" ne doit JAMAIS matcher via la sous-chaîne contenue dans
    # "pineapple" -- recherche mot entier, pas une sous-chaîne.
    assert "pine" not in out
    assert matching.style_typical_descriptors(db, "_fixture_never_seen") == []
    db.execute("DELETE FROM beer_styles WHERE style_id='_fixture_style3'")
    db.execute("DELETE FROM hop_descriptors WHERE variety='_fixture_word_hop'")
    db.execute("DELETE FROM hops WHERE variety='_fixture_word_hop'")
    db.commit()

def test_style_observed_distribution_groups_bins_by_metric_sorted(db):
    db.executemany("INSERT INTO style_recipe_stats VALUES (?,?,?,?,?,?,?,?)", [
        ("_fixture_style", "american-ipa", "abv", 6.0, 6.5, 20, "test", "2026"),
        ("_fixture_style", "american-ipa", "abv", 5.5, 6.0, 10, "test", "2026"),
        ("_fixture_style", "american-ipa", "ibu", 40.0, 50.0, 5, "test", "2026"),
    ])
    db.commit()
    out = matching.style_observed_distribution(db, "_fixture_style")
    assert out["abv"] == [
        {"bin_low": 5.5, "bin_high": 6.0, "count": 10},
        {"bin_low": 6.0, "bin_high": 6.5, "count": 20},
    ]
    assert out["ibu"] == [{"bin_low": 40.0, "bin_high": 50.0, "count": 5}]
    # aucune ligne pour ce style -> dict vide, jamais un histogramme fabriqué
    assert matching.style_observed_distribution(db, "_fixture_never_seen") == {}
    db.execute("DELETE FROM style_recipe_stats WHERE style_id='_fixture_style'")
    db.commit()

def test_hop_similar_varieties_reads_inserted_rows(db):
    db.execute("INSERT INTO hop_similar VALUES (?,?,?)", ("citra", "mosaic", "yakima"))
    db.commit()
    assert matching.hop_similar_varieties(db, "citra") == ["mosaic"]
    db.execute("DELETE FROM hop_similar WHERE variety='citra'")
    db.commit()

def test_hop_pairings_empty_without_beermaverick_data(db):
    assert matching.hop_pairings(db, "citra") == []

def test_hop_pairings_sorted_by_frequency_desc(db):
    db.executemany("INSERT INTO hop_pairings VALUES (?,?,?,?,?)", [
        ("citra", "Simcoe", "simcoe", 27.0, "beermaverick"),
        ("citra", "Mosaic", "mosaic", 77.0, "beermaverick"),
        ("citra", "Obscure Hop", None, 5.0, "beermaverick"),  # non réconcilié
    ])
    db.commit()
    r = matching.hop_pairings(db, "citra")
    assert [p["name"] for p in r] == ["Mosaic", "Simcoe", "Obscure Hop"]
    assert r[0]["variety"] == "mosaic"
    assert r[2]["variety"] is None  # nom brut conservé même sans réconciliation
    db.execute("DELETE FROM hop_pairings WHERE variety='citra'")
    db.commit()

def test_hop_substitutions_empty_without_beermaverick_data(db):
    assert matching.hop_substitutions(db, "citra") == []

def test_hop_substitutions_reads_inserted_rows(db):
    db.execute("INSERT INTO hop_substitutions VALUES (?,?,?,?)",
              ("citra", "Mosaic", "mosaic", "beermaverick"))
    db.commit()
    assert matching.hop_substitutions(db, "citra") == [{"name": "Mosaic", "variety": "mosaic"}]
    db.execute("DELETE FROM hop_substitutions WHERE variety='citra'")
    db.commit()

def test_amplify_use_oav_flag_echoed(db):
    r = matching.amplify(db, "_citrus", use_oav=True)
    assert r["use_oav"] is True
    assert matching.amplify(db, "_citrus")["use_oav"] is False

# T75 (2026-08-21, demande utilisateur explicite) : --oav résout désormais
# ses seuils EN DIRECT depuis FlavorDB2 (CID reference.MOLECULES -> CAS
# pubchem_cids -> seuil flavordb2_thresholds), jamais depuis un seuil codé
# en dur (retiré de reference.MOLECULES, mis à None partout). La base
# fixture (citra/mosaic/simcoe/saazer) a `pubchem_cids`/`flavordb2_
# thresholds` VIDES (comme pour compound_descriptors, T71/T73) -- ces tests
# insèrent des lignes de test ciblées puis les retirent, même pattern déjà
# établi. Note "_citrus" (myrcene=0.4, linalool=0.7, limonene=1.0 orphelin) :
# producible = {myrcene, linalool} sur cette base fixture.
_MYRCENE_CAS, _MYRCENE_CID = "123-35-3", 31253  # reference.MOLECULES['myrcene'][2]
_LINALOOL_CAS, _LINALOOL_CID = "78-70-6", 6549  # reference.MOLECULES['linalool'][2]

def test_oav_thresholds_resolves_via_cid_cas_chain(db):
    db.executemany("INSERT INTO pubchem_cids VALUES (?,?)",
                   [(_MYRCENE_CAS, _MYRCENE_CID)])
    db.executemany("INSERT INTO flavordb2_thresholds VALUES (?,?,?)",
                   [(_MYRCENE_CAS, "myrcene", 13.0)])
    db.commit()
    try:
        assert matching.oav_thresholds(db, ["myrcene", "linalool", "nonexistent"]) == {"myrcene": 13.0}
    finally:
        db.execute("DELETE FROM pubchem_cids WHERE cas=?", (_MYRCENE_CAS,))
        db.execute("DELETE FROM flavordb2_thresholds WHERE cas=?", (_MYRCENE_CAS,))
        db.commit()

def test_oav_thresholds_never_falls_back_to_hardcoded_reference_value(db, monkeypatch):
    # Contrainte non négociable du ticket : même si reference.MOLECULES
    # portait encore un seuil (il ne devrait plus, mais on le vérifie
    # explicitement au cas où une régression le réintroduirait), sans ligne
    # pubchem_cids/flavordb2_thresholds correspondante, oav_thresholds() ne
    # doit RIEN renvoyer pour ce composé -- jamais un repli sur reference.MOLECULES.
    patched = dict(reference.MOLECULES)
    patched["myrcene"] = (patched["myrcene"][0], 999.0, patched["myrcene"][2])
    monkeypatch.setattr(reference, "MOLECULES", patched)
    assert matching.oav_thresholds(db, ["myrcene"]) == {}

def test_oav_coverage_100pct_when_all_contributing_molecules_have_thresholds(db):
    db.executemany("INSERT INTO pubchem_cids VALUES (?,?)",
                   [(_MYRCENE_CAS, _MYRCENE_CID), (_LINALOOL_CAS, _LINALOOL_CID)])
    db.executemany("INSERT INTO flavordb2_thresholds VALUES (?,?,?)",
                   [(_MYRCENE_CAS, "myrcene", 13.0), (_LINALOOL_CAS, "linalool", 6.0)])
    db.commit()
    try:
        r = matching.amplify(db, "_citrus", use_oav=True)
        assert r["oav_coverage"] == 1.0
        assert r["oav_uncovered"] == []
    finally:
        db.execute("DELETE FROM pubchem_cids WHERE cas IN (?,?)", (_MYRCENE_CAS, _LINALOOL_CAS))
        db.execute("DELETE FROM flavordb2_thresholds WHERE cas IN (?,?)", (_MYRCENE_CAS, _LINALOOL_CAS))
        db.commit()

def test_oav_coverage_below_100pct_when_a_major_molecule_lacks_a_threshold(db):
    # Seul linalool (poids 0.7, le plus gros contributeur de "_citrus") a un
    # seuil ; myrcene (poids 0.4) n'en a pas -> couverture < 100%, myrcene
    # rapporté comme non couvert.
    db.executemany("INSERT INTO pubchem_cids VALUES (?,?)", [(_LINALOOL_CAS, _LINALOOL_CID)])
    db.executemany("INSERT INTO flavordb2_thresholds VALUES (?,?,?)",
                   [(_LINALOOL_CAS, "linalool", 6.0)])
    db.commit()
    try:
        r = matching.amplify(db, "_citrus", use_oav=True)
        assert 0 < r["oav_coverage"] < 1.0
        assert r["oav_coverage"] == pytest.approx(0.7 / 1.1)
        assert r["oav_uncovered"] == ["myrcene"]
        assert r["oav_coverage"] < matching.OAV_LOW_COVERAGE_WARNING_THRESHOLD
    finally:
        db.execute("DELETE FROM pubchem_cids WHERE cas=?", (_LINALOOL_CAS,))
        db.execute("DELETE FROM flavordb2_thresholds WHERE cas=?", (_LINALOOL_CAS,))
        db.commit()

def test_oav_coverage_none_and_uncovered_empty_when_oav_disabled(db):
    # Calculé UNIQUEMENT si use_oav=True -- pas de sens (ni de coût) sinon.
    r = matching.amplify(db, "_citrus", use_oav=False)
    assert r["oav_coverage"] is None
    assert r["oav_uncovered"] == []

def test_molecular_scores_neutral_multiplier_for_molecule_without_threshold(db):
    # Contrainte non négociable : une molécule ABSENTE de `thresholds` (donc
    # sans entrée pubchem_cids/flavordb2_thresholds en base, jamais devinée)
    # doit produire EXACTEMENT la même contribution qu'avec use_oav=False --
    # jamais un multiplicateur autre que neutre (1.0) inventé.
    profile = matching.get_note(db, "_citrus")
    _, comp, _, _ = matching.load(db)
    without_oav = matching.molecular_scores(profile, comp, use_oav=False)
    with_oav_no_thresholds = matching.molecular_scores(profile, comp, use_oav=True, thresholds={})
    assert without_oav == with_oav_no_thresholds

def test_amplify_scores_without_oav_unaffected_by_flavordb2_data(db):
    # Insérer des seuils FlavorDB2 réels ne doit RIEN changer quand
    # use_oav=False -- la feature est un prior optionnel, pas une correction
    # silencieuse du score par défaut.
    r_before = matching.amplify(db, "_citrus", use_oav=False)
    db.executemany("INSERT INTO pubchem_cids VALUES (?,?)",
                   [(_MYRCENE_CAS, _MYRCENE_CID), (_LINALOOL_CAS, _LINALOOL_CID)])
    db.executemany("INSERT INTO flavordb2_thresholds VALUES (?,?,?)",
                   [(_MYRCENE_CAS, "myrcene", 13.0), (_LINALOOL_CAS, "linalool", 6.0)])
    db.commit()
    try:
        r_after = matching.amplify(db, "_citrus", use_oav=False)
        assert r_before["ranked"] == r_after["ranked"]
    finally:
        db.execute("DELETE FROM pubchem_cids WHERE cas IN (?,?)", (_MYRCENE_CAS, _LINALOOL_CAS))
        db.execute("DELETE FROM flavordb2_thresholds WHERE cas IN (?,?)", (_MYRCENE_CAS, _LINALOOL_CAS))
        db.commit()

def test_biotransform_removed_no_double_counting_path(db):
    # Non-régression : --biotransform a été retiré (2026-08-12) car il faisait
    # compter deux fois la même mesure de géraniol (une fois comme "geraniol",
    # une fois redirigée comme "citronellol") sur toute note demandant les
    # deux — vérifie qu'il n'existe plus aucun paramètre biotransform sur les
    # fonctions concernées, pour empêcher une réintroduction accidentelle du
    # même bug plutôt qu'une correction à la racine.
    import inspect
    for fn in (matching.hop_compound, matching.amount, matching.specificity,
              matching.coverage, matching.molecular_scores, matching.amplify):
        assert "biotransform" not in inspect.signature(fn).parameters
    assert not hasattr(reference, "BIOTRANSFORMATIONS")

def test_by_descriptor_matches_and_ranks(db):
    r = matching.by_descriptor(db, ["citrus", "tropical"])["ranked"]
    varieties = [h["variety"] for h in r]
    assert set(varieties) == {"citra", "mosaic", "simcoe"}  # saazer n'a ni l'un ni l'autre
    for h in r:
        assert set(h["matched_descriptors"]) <= {"citrus", "tropical"}
        assert set(h["matched_descriptors"]) <= set(h["all_descriptors"])
    # tous à 2 descripteurs recoupés ici -> tie-break par total_oil réconcilié desc
    # (fixtures : simcoe 1.75 > citra 1.7 > mosaic 1.625 ml/100g)
    assert [h["variety"] for h in r] == ["simcoe", "citra", "mosaic"]

def test_by_descriptor_total_matches_counts_before_truncation(db):
    # 2026-08-20, revue de code -- `total_matches` (même principe que
    # `contrast`, T56) doit refléter le compte AVANT troncature à `top`,
    # jamais juste len(ranked).
    full = matching.by_descriptor(db, ["citrus", "tropical"], top=10)
    truncated = matching.by_descriptor(db, ["citrus", "tropical"], top=1)
    assert full["total_matches"] == 3
    assert truncated["total_matches"] == 3
    assert len(truncated["ranked"]) == 1

def test_by_descriptor_normalizes_aliases(db):
    # "stonefruit"/"citrus fruit" doivent se comporter comme leurs formes canoniques
    r_alias = matching.by_descriptor(db, ["citrus fruit"])["ranked"]
    r_canon = matching.by_descriptor(db, ["citrus"])["ranked"]
    assert [h["variety"] for h in r_alias] == [h["variety"] for h in r_canon]

def test_by_descriptor_no_match(db):
    r = matching.by_descriptor(db, ["nonexistent-descriptor"])
    assert r["ranked"] == []
    assert r["total_matches"] == 0

def _build_intensity_db(tmp_path):
    """Base isolée avec `hop_aroma_intensity` (T26, Yakima uniquement) --
    `build_from_fixtures` n'en peuple pas (seul `crawl_yakima`, réseau réel,
    l'alimente), donc les tests du tri quantitatif (2026-08-19) ont besoin
    de leur propre petite base plutôt que du fixture `db` partagé du module."""
    con = connect(str(tmp_path / "intensity.db"))
    init_db(con)
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES (?,?,?,?,?)", ("high", "High", "test", "toy", None))
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES (?,?,?,?,?)", ("low", "Low", "test", "toy", None))
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES (?,?,?,?,?)", ("nodata", "NoData", "test", "toy", None))
    for v in ("high", "low", "nodata"):
        con.execute("INSERT INTO hop_descriptors VALUES (?,?,?)", (v, "citrus", "toy"))
    con.executemany("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)", [
        ("high", "citrus", 90.0, "yakima"), ("low", "citrus", 10.0, "yakima"),
        # "nodata" n'a AUCUNE ligne d'intensité (pas de couverture Yakima) --
        # doit rester classé après "high"/"low" plutôt que traité comme 0.
    ])
    con.commit()
    return con

def test_by_descriptor_quantitative_tier_sorts_by_intensity_within_categorical_tie(tmp_path):
    # Les 3 houblons recoupent tous "citrus" (même palier catégorique, 1
    # descripteur) -- le tri quantitatif (roue passée explicitement) départage :
    # "high" (90) avant "low" (10) avant "nodata" (aucune donnée, jamais
    # traité comme 0).
    con = _build_intensity_db(tmp_path)
    r = matching.by_descriptor(con, ["citrus"], wheel_descriptors=["citrus"])["ranked"]
    assert [h["variety"] for h in r] == ["high", "low", "nodata"]
    assert r[0]["quant_score"] == 90.0
    assert r[1]["quant_score"] == 10.0
    assert r[2]["quant_score"] is None

def test_by_descriptor_without_wheel_descriptors_has_no_quant_score(tmp_path):
    # Repli documenté : sans `wheel_descriptors`, aucun raffinement
    # quantitatif -- comportement catégorique pur (pré-T54), même avec des
    # houblons ayant des données d'intensité disponibles.
    con = _build_intensity_db(tmp_path)
    r = matching.by_descriptor(con, ["citrus"])["ranked"]
    assert all(h["quant_score"] is None for h in r)

def test_by_descriptor_categorical_match_count_still_takes_priority(tmp_path):
    # Un houblon avec MOINS de recoupement catégorique ne doit jamais dépasser
    # un houblon avec plus de descripteurs recoupés, même si son intensité
    # quantitative est plus haute -- la couche catégorique reste prioritaire.
    con = _build_intensity_db(tmp_path)
    con.execute("INSERT INTO hop_descriptors VALUES (?,?,?)", ("low", "woody", "toy"))
    con.commit()
    r = matching.by_descriptor(con, ["citrus", "woody"], wheel_descriptors=["citrus"])["ranked"]
    assert r[0]["variety"] == "low"  # 2 descripteurs recoupés, même avec une intensité plus basse
    assert set(r[0]["matched_descriptors"]) == {"citrus", "woody"}

def test_by_descriptor_quant_score_only_averages_wheel_descriptors(tmp_path):
    # Le score quantitatif ne moyenne QUE les descripteurs de la ROUE
    # (`wheel_descriptors`) présents dans les données du houblon -- jamais
    # tous les axes de sa roue d'arôme, ni les descripteurs texte.
    con = _build_intensity_db(tmp_path)
    con.execute("INSERT INTO hop_descriptors VALUES (?,?,?)", ("high", "woody", "toy"))
    con.execute("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)",
               ("high", "woody", 0.0, "yakima"))
    con.commit()
    r = matching.by_descriptor(con, ["citrus"], wheel_descriptors=["citrus"])["ranked"]
    high = next(h for h in r if h["variety"] == "high")
    assert high["quant_score"] == 90.0  # pas la moyenne avec "woody"=0
    assert high["quant_descriptors"] == ["citrus"]

def test_by_descriptor_text_descriptor_is_the_only_categorical_filter(tmp_path):
    # Bug signalé par l'utilisateur (2026-08-19) en testant en direct roue
    # [tropical, citrus, floral] + descripteur texte "papaya" : un houblon
    # recoupant les 3 termes de la roue mais PAS "papaya" ressortait quand
    # même, mélangé AVANT des houblons "papaya" réels -- "the qualitative
    # textual descriptor is not a priority over the wheel aroma descriptor
    # selected". Désormais : `wheel_descriptors` ne filtre JAMAIS quand un
    # descripteur texte est fourni, seul `selected` (texte) filtre.
    con = _build_intensity_db(tmp_path)  # high/low/nodata portent tous "citrus"
    con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES (?,?,?,?,?)", ("papaya-hop", "PapayaHop", "test", "toy", None))
    con.execute("INSERT INTO hop_descriptors VALUES (?,?,?)", ("papaya-hop", "papaya", "toy"))
    con.commit()
    r = matching.by_descriptor(con, ["papaya"], wheel_descriptors=["citrus", "tropical", "floral"])["ranked"]
    # SEUL "papaya-hop" recoupe le descripteur texte -- "high"/"low"/"nodata"
    # (qui ne recoupent que la roue, pas "papaya") sont exclus des résultats,
    # jamais mélangés dedans même avec une intensité "citrus" élevée.
    assert [h["variety"] for h in r] == ["papaya-hop"]

def test_by_descriptor_falls_back_to_wheel_as_filter_when_no_text_descriptor(tmp_path):
    # Sans AUCUN descripteur texte (seulement des pills roue cochées),
    # `wheel_descriptors` sert de repli pour filtrer -- sinon rien ne
    # filtrerait du tout.
    con = _build_intensity_db(tmp_path)
    r = matching.by_descriptor(con, [], wheel_descriptors=["citrus"])["ranked"]
    assert {h["variety"] for h in r} == {"high", "low", "nodata"}

def test_contrast_requires_note_or_descriptors(db):
    with pytest.raises(ValueError):
        matching.contrast(db)

def test_contrast_raises_for_note_without_curated_descriptors(db):
    # aucune note_descriptors pour une note qui n'existe pas / non curée
    with pytest.raises(ValueError):
        matching.contrast(db, note="pas-une-note-curee")

def test_contrast_manual_descriptors_match_note_based_equivalent(db):
    # "_citrus" a note_descriptors = ["citrus", "floral"] (insérées par la
    # fixture `db`) -> passer les mêmes descripteurs à la main doit reproduire
    # exactement la même cible/rang : la sélection manuelle et note_descriptors
    # sont deux chemins vers le même calcul, pas deux logiques différentes.
    r_note = matching.contrast(db, note="_citrus")
    r_manual = matching.contrast(db, descriptors=["citrus", "floral"])
    assert r_manual["affinity_target"] == r_note["affinity_target"]
    assert [h["variety"] for h in r_manual["ranked"]] == [h["variety"] for h in r_note["ranked"]]

def test_contrast_manual_descriptors_generalize_beyond_curated_notes(db):
    # aucune note requise du tout : la sélection manuelle fonctionne pour
    # n'importe quel descripteur du vocabulaire réel, note existante ou non.
    r = matching.contrast(db, descriptors=["woody"])
    assert r["affinity_target"] == sorted(set(reference.CONTRAST_AFFINITY["woody"]))

def test_contrast_affinity_target_matches_contrast_default_computation():
    # Le helper exposé pour la GUI (pré-cocher la proposition, 2026-08-19)
    # doit calculer EXACTEMENT la même cible que le calcul interne par défaut
    # de `contrast` -- pas une seconde logique divergente.
    target, unmapped = matching.contrast_affinity_target(["tropical"])
    assert target == set(reference.CONTRAST_AFFINITY["tropical"])
    assert unmapped == []

def test_contrast_affinity_target_reports_unmapped_descriptors():
    target, unmapped = matching.contrast_affinity_target(["tropical", "not-a-real-descriptor"])
    assert unmapped == ["not-a-real-descriptor"]
    assert target == set(reference.CONTRAST_AFFINITY["tropical"])

def test_contrast_target_descriptors_overrides_automatic_affinity(db):
    # Demande utilisateur explicite (2026-08-19) : "let the user chose which
    # one he want to keep... rather than imposing the mapping" -- l'exemple
    # concret donné (Saaz noyé parmi les houblons dank/resinous pour
    # "tropical") : restreindre la cible à "spicy" seul doit exclure tout
    # houblon qui ne recoupe QUE dank/resinous, même s'il recoupait la cible
    # complète auto-calculée.
    r_auto = matching.contrast(db, descriptors=["citrus"])
    r_restricted = matching.contrast(db, descriptors=["citrus"], target_descriptors=["woody"])
    assert r_restricted["affinity_target"] == ["woody"]
    # cible restreinte : chaque résultat ne peut recouper QUE "woody".
    for h in r_restricted["ranked"]:
        assert set(h["contrast_via"]) <= {"woody"}
    # non-régression : le calcul automatique (sans target_descriptors) reste
    # inchangé, toujours la cible complète de "citrus".
    assert r_auto["affinity_target"] == sorted(set(reference.CONTRAST_AFFINITY["citrus"]))

def test_contrast_target_descriptors_empty_list_yields_no_matches(db):
    # Cas limite explicite : l'utilisateur décoche TOUT -> aucune cible,
    # aucun résultat (pas une erreur, pas un repli silencieux sur le calcul
    # automatique -- `[]` est une cible valide, juste vide).
    r = matching.contrast(db, descriptors=["citrus"], target_descriptors=[])
    assert r["affinity_target"] == []
    assert r["ranked"] == []

def test_purpose_matches_filter_both_matches_either_role():
    # T61 (2026-08-19) : un houblon "both" satisfait le filtre dès qu'AU
    # MOINS un des deux rôles demandés lui correspond.
    assert matching._purpose_matches_filter("both", {"aromatic"})
    assert matching._purpose_matches_filter("both", {"bittering"})
    assert matching._purpose_matches_filter("both", {"aromatic", "bittering"})
    assert matching._purpose_matches_filter("aromatic", {"aromatic"})
    assert not matching._purpose_matches_filter("aromatic", {"bittering"})
    assert not matching._purpose_matches_filter(None, {"aromatic", "bittering"})

def test_contrast_purposes_filters_by_resolved_purpose(db):
    # T61, demande utilisateur explicite : "add another menu for purpose...
    # pre-selecting both bittering and aromatic but... let user add a
    # filter". Fixture : citra/mosaic/simcoe/saazer matchent tous "citrus,
    # floral" à score 20.0 (voir test_by_descriptor_categorical_match_count_
    # still_takes_priority pour les valeurs total_oil) ; aucun n'a de purpose
    # RÉEL (BeerMaverick) mais tous ont un alpha_acid connu -> purpose
    # INFÉRÉ (seuil 7.0%) : saazer (4.45%) -> aromatic, citra/mosaic/simcoe
    # (12-13%) -> bittering. Filtrer sur "aromatic" seul ne doit garder QUE
    # saazer.
    r = matching.contrast(db, descriptors=["citrus", "floral"], purposes=["aromatic"])
    assert [h["variety"] for h in r["ranked"]] == ["saazer"]
    assert r["total_matches"] == 1

def test_contrast_purposes_none_means_no_filter(db):
    # Repli documenté : `purposes=None` (par défaut) -- comportement
    # inchangé, rétrocompatible CLI.
    r_unfiltered = matching.contrast(db, descriptors=["citrus", "floral"])
    r_explicit_none = matching.contrast(db, descriptors=["citrus", "floral"], purposes=None)
    assert ([h["variety"] for h in r_unfiltered["ranked"]] ==
           [h["variety"] for h in r_explicit_none["ranked"]])
    assert len(r_unfiltered["ranked"]) == 4

def test_contrast_purposes_excludes_unknown_purpose(db):
    # Un houblon sans purpose résolvable du tout (ni réel, ni acide alpha
    # connu pour inférer) doit être EXCLU dès qu'un filtre purpose est actif
    # -- jamais inclus par défaut sous prétexte d'absence de donnée.
    db.execute("DELETE FROM hop_composition WHERE variety='saazer' AND compound='alpha_acid'")
    db.commit()
    try:
        r = matching.contrast(db, descriptors=["citrus", "floral"], purposes=["aromatic"])
        assert r["ranked"] == []
    finally:
        db.execute("INSERT INTO hop_composition VALUES (?,?,?,?,?,?,?,?)",
                  ("saazer", "alpha_acid", 3.9, 5.0, "pct", "barthhaas", "ok", ""))
        db.commit()

def test_contrast_blend_propagates_purposes_filter(db):
    # Le pool de candidats du blend doit refléter le même filtre purpose que
    # le tableau de résultats -- jamais un houblon exclu du tableau mais
    # présent dans le blend.
    r = matching.contrast_blend(db, descriptors=["citrus", "floral"], purposes=["aromatic"],
                                max_hops=1)
    all_varieties = {h["variety"] for b in r["blends"] for h in b["hops"]}
    assert all_varieties <= {"saazer"}

def test_contrast_blend_propagates_target_descriptors_override(db):
    # Le blend doit viser la MÊME cible restreinte que le tableau de
    # résultats, pas recalculer la cible complète séparément.
    r = matching.contrast_blend(db, descriptors=["citrus"], target_descriptors=["woody"],
                                max_hops=1)
    assert r["affinity_target"] == ["woody"]

def test_contrast_breaks_score_ties_by_total_oil_deterministically(db):
    # Signalé par l'utilisateur (2026-08-19) : Saaz n'apparaissait jamais
    # pour "tropical"/"mango" même en augmentant `top` -- root cause : sur
    # une égalité de score massive (beaucoup de houblons ne recoupant qu'UN
    # seul descripteur de la cible), l'ordre dépendait de l'itération SQL,
    # pas d'un critère pertinent. citra/mosaic/simcoe sont tous à score 20.0
    # sur "citrus,floral" (fixture) -- désormais départagés par total_oil
    # desc (fixtures : simcoe 1.75 > citra 1.7 > mosaic 1.625 ml/100g),
    # reproductible d'un appel à l'autre.
    r = matching.contrast(db, descriptors=["citrus", "floral"])
    tied = [h["variety"] for h in r["ranked"] if h["score"] == 20.0]
    assert tied == ["simcoe", "citra", "mosaic"]
    # déterminisme : deux appels donnent EXACTEMENT le même ordre.
    r2 = matching.contrast(db, descriptors=["citrus", "floral"])
    assert [h["variety"] for h in r["ranked"]] == [h["variety"] for h in r2["ranked"]]

def test_contrast_exposes_total_matches_before_truncation(db):
    # `total_matches` (nouveau, 2026-08-19) permet à la GUI de signaler une
    # troncature ("showing N of total") au lieu de la laisser silencieuse --
    # 4 houblons recoupent "citrus,floral" sur la fixture, `top` par défaut
    # (8) ne tronque rien ici, mais un `top` plus petit doit quand même
    # rapporter le total réel, pas le nombre tronqué.
    r_full = matching.contrast(db, descriptors=["citrus", "floral"])
    assert r_full["total_matches"] == len(r_full["ranked"]) == 4
    r_truncated = matching.contrast(db, descriptors=["citrus", "floral"], top=2)
    assert r_truncated["total_matches"] == 4
    assert len(r_truncated["ranked"]) == 2

def test_contrast_blend_returns_growing_sizes_with_via_provenance(db):
    # T33 backlog : plusieurs tailles de blend (1..max_hops), pas un seul
    # blend "optimal" -- chaque taille rapporte sa propre couverture/résidu.
    r = matching.contrast_blend(db, note="_citrus", max_hops=2)
    assert [b["size"] for b in r["blends"]] == list(range(1, len(r["blends"]) + 1))
    assert len(r["blends"]) <= 2
    target = set(r["affinity_target"])
    for b in r["blends"]:
        assert set(b["covered"]) | set(b["residual"]) == target
        assert len(b["hops"]) == b["size"]
        covered_via_hops = set()
        for h in b["hops"]:
            covered_via_hops.update(h["covers"])
        assert covered_via_hops == set(b["covered"])
    # aucune donnée hop_pairings dans la base fixture -> jamais "pairing" ;
    # le premier houblon d'une taille 1 est toujours "top" (pas de notion de
    # pairing pour un seul houblon).
    all_via = {h["via"] for b in r["blends"] for h in b["hops"]}
    assert "pairing" not in all_via
    assert r["blends"][0]["hops"][0]["via"] == "top"

def test_contrast_blend_prefers_real_pairing_over_coverage_gain(db):
    # Démontre le renversement de priorité demandé par l'utilisateur : la
    # fréquence RÉELLE de pairing BeerMaverick doit l'emporter sur la
    # couverture, même quand le houblon "réellement associé" n'ajoute AUCUNE
    # couverture nouvelle (cas extrême, le plus probant). Sur la base fixture,
    # taille 1 = saazer (couvre herbal+spicy) ; sans donnée réelle, taille 2 =
    # citra par couverture (ajoute "woody"). En insérant un pairing réel
    # saazer<->mosaic (mosaic ne couvre QUE "herbal", déjà couvert par saazer
    # -> gain de couverture nul), mosaic doit quand même gagner la taille 2.
    db.execute("INSERT INTO hop_pairings VALUES (?,?,?,?,?)",
              ("saazer", "Mosaic", "mosaic", 90.0, "beermaverick"))
    db.commit()
    try:
        r = matching.contrast_blend(db, note="_citrus", max_hops=2)
        assert r["blends"][1]["hops"][0]["variety"] == "saazer"
        second = r["blends"][1]["hops"][1]
        assert second["variety"] == "mosaic"
        assert second["via"] == "pairing"
        # "covers" = couverture PROPRE du houblon (herbal), pas le gain marginal
        # pour le blend -- déjà couvert par saazer, d'où "covered" inchangé :
        assert second["covers"] == ["herbal"]
        assert r["blends"][1]["covered"] == r["blends"][0]["covered"]  # aucun gain réel
    finally:
        db.execute("DELETE FROM hop_pairings WHERE variety='saazer'")
        db.commit()

def test_contrast_blend_keeps_growing_past_full_or_stuck_coverage(db):
    # Signalé par l'utilisateur : les blends s'arrêtaient toujours à taille 1
    # (dès qu'un seul houblon couvrait toute la cible, ou que rien de plus
    # n'était couvrable). Décision : ne plus s'arrêter tôt, toujours grandir
    # jusqu'à max_hops (ou épuisement du pool), le houblon suivant étant
    # choisi par pertinence globale (via="relevance") quand il n'apporte ni
    # fréquence réelle ni gain de couverture. Sur "citrus,floral" (fixture),
    # aucun houblon ne couvre "earthy"/"resinous" -> le résidu reste bloqué
    # dès la taille 2, mais la croissance continue jusqu'à épuisement (4
    # houblons pertinents au total dans la base fixture).
    r = matching.contrast_blend(db, descriptors=["citrus", "floral"], max_hops=5)
    sizes = [b["size"] for b in r["blends"]]
    assert sizes == [1, 2, 3, 4]  # épuisement du pool, pas un arrêt anticipé
    assert r["blends"][2]["residual"] == r["blends"][1]["residual"]  # résidu bloqué
    assert r["blends"][2]["hops"][-1]["via"] == "relevance"
    assert r["blends"][3]["hops"][-1]["via"] == "relevance"

def test_contrast_blend_base_variety_overrides_top_pick(db):
    # Décision utilisateur (2026-08-19) : le score est souvent homogène
    # (plusieurs houblons ex-aequo "meilleur candidat"), donc l'utilisateur
    # choisit lui-même le houblon de base plutôt que `candidates[0]` imposé.
    # Sur "citrus,floral" (fixture), citra/mosaic/simcoe sont tous à 20.0 --
    # choisir "mosaic" doit être respecté même si un autre houblon (simcoe,
    # voir le tri secondaire par total_oil dans matching.contrast) vient
    # avant en pertinence pure.
    r = matching.contrast_blend(db, descriptors=["citrus", "floral"], max_hops=1,
                                base_variety="mosaic")
    assert r["blends"][0]["hops"][0]["variety"] == "mosaic"
    assert r["blends"][0]["hops"][0]["via"] == "chosen"

def test_contrast_blend_base_variety_falls_back_to_top_when_absent(db):
    # base_variety hors des candidats (variété inconnue ou non pertinente
    # pour cette cible) -> repli sur candidates[0], pas d'erreur.
    r = matching.contrast_blend(db, descriptors=["citrus", "floral"], max_hops=1,
                                base_variety="does-not-exist")
    assert r["blends"][0]["hops"][0]["via"] == "top"

def test_contrast_blend_mixes_relevance_and_pairing_not_pure_frequency(db):
    # Renversement méthodologique demandé par l'utilisateur : la fréquence
    # BeerMaverick ne doit plus, seule, décider de l'addition suivante --
    # parmi les candidats dans le TOP-N pairing du houblon de base, il faut
    # prendre le plus PERTINENT, pas celui de plus haute fréquence brute.
    # citra/mosaic/simcoe sont tous à score 20.0 (ex-aequo catégorique) ;
    # depuis le tri secondaire par total_oil (2026-08-19, voir
    # matching.contrast), l'ordre de pertinence sur cette cible est
    # simcoe > citra > mosaic (fixtures : simcoe 1.75 > citra 1.7 > mosaic
    # 1.625 ml/100g). mosaic a la fréquence la + haute (99) mais simcoe est
    # plus pertinent : simcoe doit gagner malgré sa fréquence + basse (10).
    db.executemany("INSERT INTO hop_pairings VALUES (?,?,?,?,?)", [
        ("saazer", "Mosaic", "mosaic", 99.0, "beermaverick"),
        ("saazer", "Simcoe", "simcoe", 10.0, "beermaverick"),
    ])
    db.commit()
    try:
        r = matching.contrast_blend(db, descriptors=["citrus", "floral"], max_hops=2,
                                    base_variety="saazer")
        assert r["blends"][1]["hops"][0]["variety"] == "saazer"
        second = r["blends"][1]["hops"][1]
        assert second["variety"] == "simcoe"
        assert second["via"] == "pairing"
    finally:
        db.execute("DELETE FROM hop_pairings WHERE variety='saazer'")
        db.commit()

def test_pairing_top_n_excludes_low_ranked_partners(db):
    # "top N" du pairing, pas "n'importe quelle fréquence positive" : un
    # partenaire hors du top N ne doit pas déclencher via="pairing" même
    # s'il a une fréquence enregistrée.
    db.execute("INSERT INTO hop_pairings VALUES (?,?,?,?,?)",
              ("saazer", "Mosaic", "mosaic", 5.0, "beermaverick"))
    db.commit()
    try:
        r = matching.contrast_blend(db, descriptors=["citrus", "floral"], max_hops=2,
                                    base_variety="saazer", top_candidates=30)
        second = r["blends"][1]["hops"][1]
        # pairing_top_n par défaut (10) laisse largement passer ce seul
        # partenaire -- vérifié explicitement ici (assertion manquante avant
        # revue de code du 2026-08-20 : `second` était calculé mais jamais
        # vérifié, laissant ce chemin par défaut non testé) -- puis qu'un
        # top_n=0 l'exclut et retombe sur couverture/pertinence, ci-dessous.
        assert second["variety"] == "mosaic"
        assert second["via"] == "pairing"
        from hopmatch.matching import _pairing_grown_blends, contrast
        cr = contrast(db, descriptors=["citrus", "floral"], top=30)
        target = set(cr["affinity_target"])
        candidates = [dict(h, covers=set(h["contrast_via"])) for h in cr["ranked"]]
        blends = _pairing_grown_blends(db, candidates, target, max_hops=2,
                                       base_variety="saazer", pairing_top_n=0)
        assert blends[1]["hops"][1]["via"] != "pairing"
    finally:
        db.execute("DELETE FROM hop_pairings WHERE variety='saazer'")
        db.commit()

# --------------------------------------------------------------------------- #
# purpose inféré depuis l'acide alpha (demande utilisateur 2026-08-19 : "AA%
# mean... can be used to infer the aromatic/bittering status", pour
# l'affichage GUI uniquement -- jamais pour la structure des blends).
# --------------------------------------------------------------------------- #

def test_infer_purpose_from_alpha_acid_below_threshold_is_aromatic():
    assert matching.infer_purpose_from_alpha_acid({"alpha_acid": {"mid": 5.0}}) == "aromatic"

def test_infer_purpose_from_alpha_acid_at_or_above_threshold_is_bittering():
    assert matching.infer_purpose_from_alpha_acid({"alpha_acid": {"mid": 7.0}}) == "bittering"
    assert matching.infer_purpose_from_alpha_acid({"alpha_acid": {"mid": 14.0}}) == "bittering"

def test_infer_purpose_from_alpha_acid_none_without_data():
    assert matching.infer_purpose_from_alpha_acid({}) is None
    assert matching.infer_purpose_from_alpha_acid({"alpha_acid": {"mid": None}}) is None

def test_resolve_purpose_prefers_real_purpose_over_inference():
    # même avec un acide alpha qui suggérerait "bittering" (12%), le purpose
    # RÉEL (BeerMaverick) l'emporte toujours, jamais écrasé par l'inférence.
    purpose, inferred = matching.resolve_purpose("aromatic", {"alpha_acid": {"mid": 12.0}})
    assert purpose == "aromatic"
    assert inferred is False

def test_resolve_purpose_falls_back_to_inference_when_real_purpose_missing():
    purpose, inferred = matching.resolve_purpose(None, {"alpha_acid": {"mid": 5.0}})
    assert purpose == "aromatic"
    assert inferred is True

def test_resolve_purpose_stays_none_without_any_data():
    purpose, inferred = matching.resolve_purpose(None, {})
    assert purpose is None
    assert inferred is False

# --------------------------------------------------------------------------- #
# purpose (aromatic/bittering/both) -- blends structurés (décision utilisateur
# 2026-08-19 : "at least 1 aromatic and 1 bittering as a first proposal (n=2)
# and then propose blends picking only aromatic hops that pairs well with the
# other aromatic hop (not the bittering)").
# --------------------------------------------------------------------------- #

def _cand(variety, covers):
    return {"variety": variety, "name": variety.title(), "sources": "test", "covers": set(covers)}

def test_purpose_structured_blend_forces_bittering_complement_at_size_two(db):
    candidates = [_cand("aroma1", {"a"}), _cand("bitter1", {"b"}), _cand("aroma2", {"c"})]
    purpose = {"aroma1": "aromatic", "bitter1": "bittering", "aroma2": "aromatic"}
    r = matching._pairing_grown_blends(db, candidates, {"a", "b", "c"}, max_hops=4,
                                       base_variety="aroma1", purpose_by_variety=purpose)
    assert [h["variety"] for h in r[0]["hops"]] == ["aroma1"]
    assert r[0]["hops"][0]["via"] == "chosen"
    assert [h["variety"] for h in r[1]["hops"]] == ["aroma1", "bitter1"]
    assert r[1]["hops"][1]["via"] == "complement"

def test_purpose_structured_blend_size_three_plus_aromatic_only(db):
    # à partir de la taille 3, seuls des houblons aromatiques -- jamais un
    # deuxième houblon amérisant, même s'il en restait un dans le pool.
    candidates = [_cand("aroma1", {"a"}), _cand("bitter1", {"b"}), _cand("bitter2", {"d"}),
                 _cand("aroma2", {"c"})]
    purpose = {"aroma1": "aromatic", "bitter1": "bittering", "bitter2": "bittering",
              "aroma2": "aromatic"}
    r = matching._pairing_grown_blends(db, candidates, {"a", "b", "c", "d"}, max_hops=4,
                                       base_variety="aroma1", purpose_by_variety=purpose)
    assert [h["variety"] for h in r[2]["hops"]] == ["aroma1", "bitter1", "aroma2"]
    assert r[2]["hops"][2]["via"] != "complement"
    for b in r:
        purposes_in_blend = [purpose[h["variety"]] for h in b["hops"]]
        assert purposes_in_blend.count("bittering") <= 1

def test_purpose_structured_blend_stops_when_aromatic_pool_exhausted(db):
    # deux houblons amérisants disponibles mais un seul aromatique en dehors
    # de la base -> le blend s'arrête à taille 2 (pas de 3e houblon
    # amérisant ajouté juste pour atteindre max_hops).
    candidates = [_cand("aroma1", {"a"}), _cand("bitter1", {"b"}), _cand("bitter2", {"c"})]
    purpose = {"aroma1": "aromatic", "bitter1": "bittering", "bitter2": "bittering"}
    r = matching._pairing_grown_blends(db, candidates, {"a", "b", "c"}, max_hops=5,
                                       base_variety="aroma1", purpose_by_variety=purpose)
    assert len(r) == 2  # pas de taille 3 : plus aucun candidat aromatique

def test_purpose_structured_blend_dual_purpose_base_skips_forced_complement(db):
    # un houblon "both" à la base satisfait déjà les deux rôles -> pas de
    # complément forcé à la taille 2, croissance aromatique directe.
    candidates = [_cand("dual1", {"a"}), _cand("aroma1", {"b"}), _cand("bitter1", {"c"})]
    purpose = {"dual1": "both", "aroma1": "aromatic", "bitter1": "bittering"}
    r = matching._pairing_grown_blends(db, candidates, {"a", "b", "c"}, max_hops=3,
                                       base_variety="dual1", purpose_by_variety=purpose)
    assert r[1]["hops"][1]["variety"] == "aroma1"
    assert r[1]["hops"][1]["via"] != "complement"
    # "bitter1" (le seul candidat amérisant restant) n'est jamais recruté
    assert all(h["variety"] != "bitter1" for b in r for h in b["hops"])

def test_purpose_structured_blend_falls_back_when_no_complement_candidate(db):
    # base aromatique mais AUCUN candidat amérisant dans le pool -> repli
    # honnête sur la croissance générique, pas d'erreur, pas de blend
    # tronqué par manque de donnée purpose.
    candidates = [_cand("aroma1", {"a"}), _cand("aroma2", {"b"})]
    purpose = {"aroma1": "aromatic", "aroma2": "aromatic"}
    r = matching._pairing_grown_blends(db, candidates, {"a", "b"}, max_hops=2,
                                       base_variety="aroma1", purpose_by_variety=purpose)
    assert [h["variety"] for h in r[1]["hops"]] == ["aroma1", "aroma2"]
    assert r[1]["hops"][1]["via"] != "complement"

def test_purpose_structured_blend_falls_back_when_base_purpose_unknown(db):
    # rôle de base inconnu (pas de donnée BeerMaverick pour ce houblon) ->
    # comportement générique inchangé, même si un AUTRE candidat a un rôle
    # connu (on n'ancre jamais la structure sur un houblon qu'on n'a pas
    # choisi comme base).
    candidates = [_cand("x1", {"a"}), _cand("x2", {"b"})]
    purpose = {"x2": "aromatic"}  # x1 (la base) absent -> rôle inconnu
    r = matching._pairing_grown_blends(db, candidates, {"a", "b"}, max_hops=2,
                                       base_variety="x1", purpose_by_variety=purpose)
    assert r[1]["hops"][1]["via"] != "complement"

def test_purpose_structured_blend_without_purpose_data_matches_prior_behavior(db):
    # purpose_by_variety omis (None) -> strictement le comportement générique
    # préexistant, jamais de via="complement".
    r = matching.contrast_blend(db, descriptors=["citrus", "floral"], max_hops=4,
                                base_variety="saazer")
    all_via = {h["via"] for b in r["blends"] for h in b["hops"]}
    assert "complement" not in all_via

def test_contrast_blend_wires_real_purpose_data_end_to_end(db):
    # vérifie le branchement complet (contrast_blend -> matching.load ->
    # hops.purpose -> _pairing_grown_blends), pas seulement l'unité isolée.
    db.execute("UPDATE hops SET purpose='aromatic' WHERE variety='saazer'")
    db.execute("UPDATE hops SET purpose='bittering' WHERE variety='citra'")
    db.commit()
    try:
        r = matching.contrast_blend(db, descriptors=["citrus", "floral"], max_hops=2,
                                    base_variety="saazer")
        assert [h["variety"] for h in r["blends"][1]["hops"]] == ["saazer", "citra"]
        assert r["blends"][1]["hops"][1]["via"] == "complement"
        assert r["blends"][1]["hops"][1]["purpose"] == "bittering"
    finally:
        db.execute("UPDATE hops SET purpose=NULL WHERE variety IN ('saazer','citra')")
        db.commit()

def test_amplify_falls_back_to_pure_molecular_score_without_descriptors(db):
    # "_passion" n'a pas de note_descriptors (contrairement à "_citrus") : sans
    # garde-fou, le score par défaut plafonnerait à w_mol*100=50 pour un houblon
    # pourtant parfait sur le plan moléculaire, ce qui se lirait à tort comme
    # "aucun houblon ne recoupe les descripteurs" plutôt que "cette note n'a
    # aucun descripteur enregistré". Vérifie que has_descriptors est signalé et
    # que le score n'est pas plafonné artificiellement.
    r = matching.amplify(db, "_passion")
    assert r["has_descriptors"] is False
    assert all(h["desc"] == 0 for h in r["ranked"])
    top = r["ranked"][0]
    assert top["score"] == pytest.approx(round(100 * top["mol"], 1))

def test_amplify_uses_descriptors_when_available(db):
    r = matching.amplify(db, "_citrus")
    assert r["has_descriptors"] is True

def test_amplify_manual_descriptors_activates_desc_layer(db):
    # "_passion" n'a pas de note_descriptors -> sans descriptors=, desc=0 partout
    # (déjà couvert par test_amplify_falls_back_to_pure_molecular_score_without_descriptors).
    # Avec descriptors= fourni à la main, la couche descripteurs doit contribuer.
    r = matching.amplify(db, "_passion", descriptors=["citrus", "tropical"])
    assert r["has_descriptors"] is True
    assert any(h["desc"] > 0 for h in r["ranked"])

def test_amplify_blend_without_descriptors_returns_empty_with_flag(db):
    # "_passion" sans descriptors= : rien à couvrir par un blend -> pas
    # d'erreur, juste has_descriptors=False et blends vide (même esprit que
    # le repli honnête d'amplify()).
    r = matching.amplify_blend(db, "_passion")
    assert r["has_descriptors"] is False
    assert r["blends"] == []

def test_amplify_blend_targets_note_descriptors_not_molecules(db):
    # T31/T32 backlog : la cible du blend est le descripteur (comme
    # contrast_blend), PAS la molécule -- pas de NNLS/reconstruction
    # moléculaire (voir combine(), retiré). "_passion" n'a pas de
    # note_descriptors propres -> sélection manuelle.
    r = matching.amplify_blend(db, "_passion", descriptors=["citrus", "tropical"], max_hops=2)
    assert r["has_descriptors"] is True
    assert r["target_descriptors"] == ["citrus", "tropical"]
    target = set(r["target_descriptors"])
    assert [b["size"] for b in r["blends"]] == list(range(1, len(r["blends"]) + 1))
    for b in r["blends"]:
        assert set(b["covered"]) | set(b["residual"]) == target
        covered_via_hops = set()
        for h in b["hops"]:
            covered_via_hops.update(h["covers"])
        assert covered_via_hops == set(b["covered"])
        # "covers" ne doit contenir QUE des descripteurs de la cible, jamais
        # de molécule (why d'amplify() reste dans un champ séparé, pas repris ici).
        for h in b["hops"]:
            assert set(h["covers"]) <= target

def test_amplify_manual_descriptors_override_note_descriptors(db):
    # "_citrus" a note_descriptors=["citrus","floral"] -> passer une sélection
    # manuelle différente doit primer dessus (même contrat que contrast()).
    r_manual = matching.amplify(db, "_citrus", descriptors=["woody"])
    r_note = matching.amplify(db, "_citrus")
    assert r_manual != r_note

def test_molecular_scores_matches_naive_specificity_computation(db):
    # Non-régression pour le cache de specificity() dans molecular_scores()
    # (perf : O(n_houblons) au lieu de O(n_houblons²), voir le commentaire dans
    # matching.py) : compare au calcul naïf non mis en cache, molécule par
    # molécule, houblon par houblon, pour vérifier que la mise en cache ne
    # change RIEN au résultat (specificity ne dépend que de la molécule/comp,
    # jamais du houblon en cours de scoring).
    _, comp, _, _ = matching.load(db)
    profile = matching.get_note(db, "_citrus")
    scores = matching.molecular_scores(profile, comp)

    max_amt = {m: max((matching.amount(h, m, comp) for h in comp), default=0.0)
              for m in profile}
    for h in comp:
        contribs = {}
        for m, w in profile.items():
            a = matching.amount(h, m, comp)
            if a <= 0 or not max_amt[m]:
                continue
            contribs[m] = w * (a / max_amt[m]) * matching.specificity(m, comp)
        if contribs:
            assert h in scores
            assert scores[h][0] == pytest.approx(sum(contribs.values()))
        else:
            assert h not in scores

def test_contrast_flags_unmapped_descriptors_without_dropping_mapped_ones(db):
    # "citrus" a une entrée CONTRAST_AFFINITY, "nonexistent-descriptor" n'en a
    # aucune -> doit apparaître dans `unmapped` sans empêcher "citrus" de
    # produire une cible d'affinité normalement (pas de suppression totale).
    r = matching.contrast(db, descriptors=["citrus", "nonexistent-descriptor"])
    assert r["unmapped"] == ["nonexistent-descriptor"]
    assert r["affinity_target"] == sorted(set(reference.CONTRAST_AFFINITY["citrus"]))

def test_contrast_full_real_vocabulary_has_no_unmapped_descriptor():
    # Vérifie que CONTRAST_AFFINITY couvre bien tout le vocabulaire réel
    # hop_descriptors observé sur la base construite — non-régression pour
    # l'extension de couverture (T2 du backlog, puis élargi de 38 à 104
    # descripteurs par l'ingestion des tags BeerMaverick, voir
    # ingest.ingest_beermaverick/_normalize_beermaverick_tag et CLAUDE.md).
    real_vocabulary = {
        "anise", "apple", "apricot", "banana", "berry", "black currant",
        "black pepper", "blackberry", "blossom", "blueberry", "bubblegum",
        "candied fruit", "candy", "caramel", "cedar", "chamomile", "cherry",
        "chocolate", "cinnamon", "citrus", "clove", "coconut", "cucumber",
        "curry", "dank", "dark fruit", "dill", "dried fruit", "earthy",
        "elderberry", "eucalyptus", "fennel", "fig", "floral", "fruity",
        "garlic", "geranium", "ginger", "gooseberry", "grapefruit", "grapes",
        "grassy", "green tea", "guava", "hay", "herbal", "hibiscus", "honey",
        "honeydew", "incense", "jasmine", "lavender", "leather", "lemon",
        "lemongrass", "licorice", "lilac", "lime", "loganberry", "lychee",
        "magnolia", "mandarin", "mango", "marmalade", "melon", "menthol",
        "mint", "molasses", "nectar", "nutmeg", "oak", "onion", "orange",
        "papaya", "passion fruit", "peach", "pear", "pepper", "pine",
        "pineapple", "plum", "potpourri", "raspberry", "redberry", "redcurrant",
        "resinous", "rose", "sage", "sauvignon blanc", "spicy", "stone fruit",
        "strawberry", "sweet aromatic", "tangerine", "tea", "thyme", "tobacco",
        "toffee", "tropical", "vanilla", "watermelon", "white wine", "wine",
        "woody",
    }
    assert real_vocabulary <= set(reference.CONTRAST_AFFINITY)
    # toutes les valeurs restent dans le noyau fermé des 10 catégories cœur
    # (pas de chaîne de dépendance vers un descripteur étroit lui-même non couvert)
    core = {"citrus", "tropical", "floral", "stone fruit", "herbal", "woody",
           "resinous", "spicy", "dank", "earthy"}
    for targets in reference.CONTRAST_AFFINITY.values():
        assert set(targets) <= core

def test_aroma_wheel_definitions_reexported_identically_from_reference():
    # Même garde-fou que CONTRAST_CORE_CATEGORIES (T62, revue de code du
    # 2026-08-20 : AROMA_WHEEL_DEFINITIONS n'avait aucun test avant) --
    # vérifie que la chaîne de ré-export reference -> matching n'a pas
    # divergé (app.py ne lit jamais `reference` directement, voir
    # matching.py).
    assert matching.AROMA_WHEEL_DEFINITIONS is reference.AROMA_WHEEL_DEFINITIONS

def test_aroma_wheel_definitions_cover_exactly_the_15_intensity_categories():
    # Vocabulaire de `hop_aroma_intensity` (T26, 15 catégories Yakima +
    # "menthol" ajoutée en T79 pour BarthHaas -- voir reference.py) : si un
    # futur re-crawl Yakima/BarthHaas renomme/ajoute une catégorie sans
    # mettre à jour AROMA_WHEEL_DEFINITIONS, ce test échoue plutôt que de
    # laisser un label du radar sans tooltip en silence (voir
    # `app._aroma_wheel`/`_aroma_wheel_compare`, `Definition` vide par
    # défaut via `.get(d, "")`).
    expected = {
        "apple", "berry", "citrus", "dried fruit", "earthy", "floral",
        "grassy", "herbal", "melon", "spicy", "stone fruit",
        "sweet aromatic", "tropical", "vegetal", "woody", "menthol",
    }
    assert set(reference.AROMA_WHEEL_DEFINITIONS) == expected
    assert all(isinstance(v, str) and v.strip() for v in reference.AROMA_WHEEL_DEFINITIONS.values())

def test_contrast_blend_propagates_unmapped(db):
    r = matching.contrast_blend(db, descriptors=["citrus", "nonexistent-descriptor"])
    assert r["unmapped"] == ["nonexistent-descriptor"]

def test_ingredient_descriptors_keys_and_terms_match_real_vocabulary(db):
    # T76 (2026-08-22) : garde-fou de non-régression pour
    # `reference.INGREDIENT_DESCRIPTORS` (amorce IA de pré-remplissage
    # descripteurs sur `amplify`, voir le commentaire au-dessus du dict) --
    # doit rester en permanence : (1) exactement les notes réelles de
    # `aroma_notes` en clé (aucune manquante, aucune orpheline/mal
    # orthographiée) ; (2) chaque terme de chaque valeur dans le vocabulaire
    # réel `hop_descriptors` (jamais un terme inventé). `db` (fixture module)
    # n'a que les hops/notes des fixtures, pas les 506 notes réelles de
    # production -- ce test vérifie donc la cohérence STRUCTURELLE (types,
    # absence de terme halluciné dans le sous-ensemble présent) plutôt que la
    # couverture exacte des 506 clés, qui dépend de la base réelle et n'a
    # de sens qu'en dehors de la fixture de test.
    for ingredient, terms in reference.INGREDIENT_DESCRIPTORS.items():
        assert isinstance(terms, list), ingredient
        assert 0 <= len(terms) <= 4, (ingredient, terms)
        assert len(terms) == len(set(terms)), (ingredient, terms)  # pas de doublon
    # Vocabulaire : vérifié contre la base RÉELLE (aromahops.db), pas la
    # fixture -- c'est elle qui a servi à l'authoring, et c'est elle que la
    # GUI interroge réellement (`app._descriptors`).
    import os
    real_db_path = os.path.join(os.path.dirname(__file__), "..", "aromahops.db")
    if os.path.exists(real_db_path):
        from hopmatch.schema import connect
        real_con = connect(real_db_path)
        real_notes = {r[0] for r in real_con.execute("SELECT DISTINCT note FROM aroma_notes")}
        real_desc_prod = {r[0] for r in real_con.execute("SELECT DISTINCT descriptor FROM hop_descriptors")}
        assert set(reference.INGREDIENT_DESCRIPTORS) == real_notes
        for ingredient, terms in reference.INGREDIENT_DESCRIPTORS.items():
            for t in terms:
                assert t in real_desc_prod, (ingredient, t)

def test_descriptor_families_keys_match_real_vocabulary(db):
    # T129 (2026-08-29) : garde-fou explicitement demandé par le ticket --
    # "toute clé de reference.DESCRIPTOR_FAMILIES existe réellement dans le
    # vocabulaire hop_descriptors". Un seul sens (clés ⊆ vocabulaire), PAS
    # l'inverse -- contrairement à INGREDIENT_DESCRIPTORS ci-dessus, le
    # ticket ne demande pas une couverture à 100% obligatoire : un futur mot
    # ingéré (nouveau crawl) doit rester utilisable dans le sélecteur plat
    # existant sans faire échouer ce test avant d'être trié à la main.
    assert all(isinstance(v, str) and v.strip() for v in reference.DESCRIPTOR_FAMILIES.values())
    import os
    real_db_path = os.path.join(os.path.dirname(__file__), "..", "aromahops.db")
    if os.path.exists(real_db_path):
        from hopmatch.schema import connect
        real_con = connect(real_db_path)
        real_desc_prod = {r[0] for r in real_con.execute("SELECT DISTINCT descriptor FROM hop_descriptors")}
        for descriptor, family in reference.DESCRIPTOR_FAMILIES.items():
            assert descriptor in real_desc_prod, (descriptor, family)

def test_descriptor_sources_groups_by_variety_and_descriptor(db):
    # T77 (2026-08-22, demande utilisateur explicite -- confusion vérifiée
    # en direct sur "enigma" en production : "berry"/"raspberry" venaient
    # de BeerMaverick, jamais de BarthHaas, alors que la colonne "Sources"
    # des tableaux de résultats n'a toujours reflété que `hops.sources`
    # (provenance de la COMPOSITION) -- `matching.descriptor_sources`
    # comble ce trou de provenance PAR DESCRIPTEUR. Fixture : citra/citrus
    # a RÉELLEMENT deux sources (barthhaas ET yakima, vérifié en direct sur
    # la base construite) -- un vrai cas multi-source, pas fabriqué pour ce
    # test.
    src = matching.descriptor_sources(db)
    assert src["citra"]["citrus"] == {"barthhaas", "yakima"}
    # Un descripteur mono-source reste un set à un seul élément, pas une
    # chaîne nue -- l'appelant (`app.py`) fait toujours `sorted(...)`/`for s
    # in ...`, jamais une comparaison directe à une string.
    assert isinstance(src["citra"]["citrus"], set)
    # Variété/descripteur absent de hop_descriptors -> absent du dict
    # (jamais une entrée vide inventée) -- `.get(variety, {}).get(d, set())`
    # côté appelant gère ce cas.
    assert "nonexistent" not in src
