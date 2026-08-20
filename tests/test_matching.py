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
    con.execute("INSERT INTO hops VALUES (?,?,?,?,?)", ("high", "High", "test", "toy", None))
    con.execute("INSERT INTO hops VALUES (?,?,?,?,?)", ("low", "Low", "test", "toy", None))
    con.execute("INSERT INTO hops VALUES (?,?,?,?,?)", ("nodata", "NoData", "test", "toy", None))
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
    con.execute("INSERT INTO hops VALUES (?,?,?,?,?)", ("papaya-hop", "PapayaHop", "test", "toy", None))
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
    # Vocabulaire fixe de `hop_aroma_intensity` (T26), tel que documenté dans
    # reference.py -- si un futur re-crawl Yakima renomme/ajoute une
    # catégorie sans mettre à jour AROMA_WHEEL_DEFINITIONS, ce test échoue
    # plutôt que de laisser un label du radar sans tooltip en silence (voir
    # `app._aroma_wheel`/`_aroma_wheel_compare`, `Definition` vide par
    # défaut via `.get(d, "")`).
    expected = {
        "apple", "berry", "citrus", "dried fruit", "earthy", "floral",
        "grassy", "herbal", "melon", "spicy", "stone fruit",
        "sweet aromatic", "tropical", "vegetal", "woody",
    }
    assert set(reference.AROMA_WHEEL_DEFINITIONS) == expected
    assert all(isinstance(v, str) and v.strip() for v in reference.AROMA_WHEEL_DEFINITIONS.values())

def test_contrast_blend_propagates_unmapped(db):
    r = matching.contrast_blend(db, descriptors=["citrus", "nonexistent-descriptor"])
    assert r["unmapped"] == ["nonexistent-descriptor"]
