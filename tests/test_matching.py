import os, tempfile
import pytest
from hopmatch import ingest, matching, reference
from hopmatch.schema import connect

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

def test_merge_multisource(db):
    # Citra doit fusionner β-pinène (yakima) + thiols (barthhaas)
    _, comp, _, _ = matching.load(db)
    assert comp["citra"]["beta-pinene"]["sources"] == ["yakima"]
    assert comp["citra"]["thiols"]["sources"] == ["barthhaas"]
    assert set(comp["citra"]["myrcene"]["sources"]) == {"barthhaas", "yakima"}

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
    # de valeur inventée.
    assert matching.hop_aroma_intensity(db, "citra") == {}

def test_hop_aroma_intensity_reads_inserted_rows(db):
    db.execute("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)",
              ("citra", "citrus", 90.0, "yakima"))
    db.commit()
    assert matching.hop_aroma_intensity(db, "citra") == {"citrus": 90.0}
    db.execute("DELETE FROM hop_aroma_intensity WHERE variety='citra'")
    db.commit()

def test_hop_similar_varieties_empty_without_yakima_data(db):
    assert matching.hop_similar_varieties(db, "citra") == []

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
    # choisir "mosaic" doit être respecté même si citra vient avant en
    # pertinence pure.
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
    # simcoe a la fréquence la + haute (99) mais mosaic est plus pertinent
    # (score 20 vs 20, mais mosaic précède simcoe dans le classement --
    # cf. test ci-dessus) : mosaic doit gagner malgré sa fréquence + basse.
    db.executemany("INSERT INTO hop_pairings VALUES (?,?,?,?,?)", [
        ("saazer", "Simcoe", "simcoe", 99.0, "beermaverick"),
        ("saazer", "Mosaic", "mosaic", 10.0, "beermaverick"),
    ])
    db.commit()
    try:
        r = matching.contrast_blend(db, descriptors=["citrus", "floral"], max_hops=2,
                                    base_variety="saazer")
        assert r["blends"][1]["hops"][0]["variety"] == "saazer"
        second = r["blends"][1]["hops"][1]
        assert second["variety"] == "mosaic"
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
        # partenaire -- vérifie explicitement qu'un top_n=0 l'exclut et
        # retombe sur couverture/pertinence.
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

def test_contrast_blend_propagates_unmapped(db):
    r = matching.contrast_blend(db, descriptors=["citrus", "nonexistent-descriptor"])
    assert r["unmapped"] == ["nonexistent-descriptor"]
