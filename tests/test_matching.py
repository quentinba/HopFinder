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
        # mirrors l'ancienne note "rose" : citronellol jamais mesuré côté
        # houblon (nécessite --biotransform pour être couvert via géraniol).
        ("_rose", "geraniol", 1.0, "test"),
        ("_rose", "citronellol", 0.9, "test"),
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

def test_combine_returns_blend_and_residual(db):
    r = matching.combine(db, "_passion", max_hops=2)
    assert "residual" in r
    assert isinstance(r["blend"], list)

def test_orphans_flagged(db):
    r = matching.amplify(db, "_citrus")
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

def test_hop_compound_biotransform():
    assert matching.hop_compound("citronellol") == "citronellol"  # sans le flag, pas de redirection
    assert matching.hop_compound("citronellol", biotransform=True) == "geraniol"
    assert matching.hop_compound("alpha-terpineol", biotransform=True) == "linalool"
    assert matching.hop_compound("myrcene", biotransform=True) == "myrcene"  # hors portée, inchangé

def test_coverage_biotransform_unlocks_alpha_terpineol(db):
    # aucune note de démo ne demande alpha-terpineol : profil ad hoc pour vérifier
    # la voie linalol->alpha-terpinéol indépendamment de géraniol->citronellol
    _, comp, _, _ = matching.load(db)
    profile = {"alpha-terpineol": 1.0}
    _, orphan_off, _ = matching.coverage(profile, comp)
    assert "alpha-terpineol" in orphan_off

    producible_on, orphan_on, _ = matching.coverage(profile, comp, biotransform=True)
    assert "alpha-terpineol" in producible_on
    assert "alpha-terpineol" not in orphan_on

def test_coverage_biotransform_unlocks_citronellol(db):
    _, comp, _, _ = matching.load(db)
    profile = matching.get_note(db, "_rose")
    _, orphan_off, _ = matching.coverage(profile, comp)
    assert "citronellol" in orphan_off  # aucun houblon ne mesure le citronellol

    producible_on, orphan_on, _ = matching.coverage(profile, comp, biotransform=True)
    assert "citronellol" in producible_on
    assert "citronellol" not in orphan_on

def test_combine_biotransform_removes_citronellol_from_residual(db):
    r_off = matching.combine(db, "_rose", max_hops=2)
    r_on = matching.combine(db, "_rose", max_hops=2, biotransform=True)
    assert "citronellol" in r_off["orphan"]
    assert "citronellol" not in r_on["orphan"]
    assert r_off["biotransform"] is False
    assert r_on["biotransform"] is True

def test_amplify_biotransform_flag_echoed(db):
    r = matching.amplify(db, "_rose", biotransform=True)
    assert r["biotransform"] is True

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

def test_contrast_blend_covers_target_within_max_hops(db):
    r = matching.contrast_blend(db, note="_citrus", max_hops=2)
    assert len(r["blend"]) <= 2
    assert set(r["covered"]) | set(r["residual"]) == set(r["affinity_target"])
    covered_via_blend = set()
    for h in r["blend"]:
        covered_via_blend.update(h["covers"])
    assert covered_via_blend == set(r["covered"])

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
