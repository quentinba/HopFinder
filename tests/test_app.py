"""
Tests de fumée pour la GUI Streamlit (T3 du backlog, docs/BACKLOG.md) via
`streamlit.testing.v1.AppTest` — exécute réellement app.py (import, requêtes
SQLite, rendu des éléments) sans navigateur, et vérifie l'absence d'exception
pour chacun des quatre modes plutôt qu'une simple compilation syntaxique.

`app.py` lit son chemin de base via `DEFAULT_DB = "aromahops.db"` (chemin
relatif au cwd, cf. `_db_path`) : chaque test chdir dans un dossier temporaire
contenant une base jouet nommée ainsi, pour reproduire l'usage réel
(`streamlit run src/hopmatch/app.py` depuis la racine du projet).
"""
import os
import tempfile

import pytest

# streamlit n'est installé que via l'extra [ui] (pas [dev]) — voir README,
# section installation. `pip install -e ".[dev]"` seul (le flux documenté
# pour lancer pytest) ne l'installe donc pas : ce module se saute proprement
# plutôt que de faire échouer toute la suite si l'extra [ui] est absent.
st_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = st_testing.AppTest

from hopmatch import matching
from hopmatch.schema import connect, init_db

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "hopmatch", "app.py")


def _build_toy_db(path):
    con = connect(path)
    init_db(con)
    con.executemany("INSERT INTO molecules VALUES (?,?,?,?)",
                    [("molx", "x", None, None), ("moly", "y", None, None)])
    # purpose=None pour hopc (demande utilisateur 2026-08-19 : "AA% mean...
    # can be used to infer the aromatic/bittering status") : pas de purpose
    # BeerMaverick réel côté fixture -> repli sur l'acide alpha, voir
    # matching.resolve_purpose/ALPHA_ACID_BITTERING_THRESHOLD_PCT (7.0%).
    purpose = {"hopa": "aromatic", "hopb": "bittering", "hopc": None,
              "twina": None, "twinb": None}
    # noms/régions custom (pas juste v.title()) pour "twina"/"twinb" : même
    # nom affiché ("Twins"), région différente -- reproduit le cas réel
    # Amarillo®/Perle/Saaz (2026-08-19, voir matching._disambiguate_hop_names).
    custom_name_region = {"twina": ("Twins", "Region A"), "twinb": ("Twins", "Region B")}
    # descripteur distinct de "citrus"/"woody"/"floral" pour hopc : ne doit
    # pas interférer avec les tests by-descriptor préexistants qui comptent
    # sur "citrus" pour ne matcher QUE hopa (single-hop, pas de heatmap).
    for v, desc in (("hopa", ["citrus", "woody"]), ("hopb", ["floral"]), ("hopc", ["resinous"]),
                    ("twina", []), ("twinb", [])):
        name, region = custom_name_region.get(v, (v.title(), "test"))
        con.execute("INSERT INTO hops VALUES (?,?,?,?,?)",
                    (v, name, region, "toy", purpose[v]))
        for d in desc:
            con.execute("INSERT INTO hop_descriptors VALUES (?,?,?)", (v, d, "toy"))
    rows = [
        ("hopa", "molx", 50, 50, "pct_oil", "toy", "ok", ""),
        ("hopa", "total_oil", 1.0, 1.0, "ml_100g", "toy", "ok", ""),
        ("hopb", "moly", 50, 50, "pct_oil", "toy", "ok", ""),
        ("hopb", "total_oil", 1.0, 1.0, "ml_100g", "toy", "ok", ""),
        # 14.5% > seuil 7.0% -> inféré "bittering" pour hopc (pas de purpose
        # BeerMaverick réel dans cette fixture, voir ci-dessus).
        ("hopc", "alpha_acid", 14.0, 15.0, "pct", "toy", "ok", ""),
        ("hopc", "beta_acid", 4.0, 5.0, "pct", "toy", "ok", ""),
        ("hopc", "co_humulone", 20.0, 24.0, "pct", "toy", "ok", ""),
        ("hopc", "total_oil", 1.5, 1.5, "ml_100g", "toy", "ok", ""),
    ]
    con.executemany("INSERT INTO hop_composition VALUES (?,?,?,?,?,?,?,?)", rows)
    con.executemany("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)", [
        # T79 4e addendum (2026-08-23) : source "yakima" (pas "toy" comme le
        # reste de la fixture) -- le toggle GUI Yakima<>BarthHaas de
        # `app._aroma_wheel_toggle` ne reconnaît que ces deux noms de source
        # littéraux (seuls noms réels en production), une source "toy"
        # générique y serait invisible.
        ("hopa", "citrus", 80.0, "yakima"), ("hopa", "woody", 20.0, "yakima"),
    ])
    con.executemany("INSERT INTO aroma_notes VALUES (?,?,?,?)", [
        ("mynote", "molx", 1.0, "toy"), ("mynote", "moly", 0.5, "toy"),
        # couverture quasi nulle (~1%) : une grosse molécule orpheline (10.0)
        # domine largement une petite productible (0.1) — pour tester
        # l'avertissement de couverture faible sans dépendre du timing du
        # cache mtime-based (voir _db_version) sur un insert après coup.
        ("lownote", "molx", 0.1, "toy"), ("lownote", "bigorphan", 10.0, "toy"),
    ])
    con.commit()
    con.close()


@pytest.fixture()
def toy_cwd():
    """chdir dans un dossier temporaire avec aromahops.db peuplée ; restaure le cwd après."""
    tmpdir = tempfile.mkdtemp()
    _build_toy_db(os.path.join(tmpdir, "aromahops.db"))
    old_cwd = os.getcwd()
    os.chdir(tmpdir)
    try:
        yield tmpdir
    finally:
        os.chdir(old_cwd)


def _app():
    # default_timeout généreux : le premier run d'AppTest paie un coût d'import
    # streamlit/hopmatch non représentatif d'un run Streamlit normal déjà démarré.
    return AppTest.from_file(APP_PATH, default_timeout=20)


from hopmatch import app  # noqa: E402 -- après le skip conditionnel sur [ui], voir plus haut


def test_fetch_remote_db_returns_true_if_already_present(tmp_path):
    db = tmp_path / "already-there.db"
    db.write_bytes(b"x")
    assert app._fetch_remote_db(str(db)) is True


def test_fetch_remote_db_returns_false_when_secrets_unavailable(tmp_path, monkeypatch):
    # Reproduit `StreamlitSecretNotFoundError` (dev local sans secrets.toml,
    # vérifié en direct que `st.secrets.get(...)` lève dans ce cas précis
    # plutôt que de renvoyer None comme un dict normal) -- capturé largement
    # dans `_fetch_remote_db`, jamais une exception qui casserait la page.
    db = tmp_path / "missing-no-secrets.db"

    class RaisingSecrets:
        def get(self, key):
            raise RuntimeError("no secrets.toml")

    monkeypatch.setattr(app.st, "secrets", RaisingSecrets())
    assert app._fetch_remote_db(str(db)) is False
    assert not db.exists()


def test_fetch_remote_db_returns_false_when_url_or_token_missing(tmp_path, monkeypatch):
    db = tmp_path / "missing-partial-secrets.db"
    monkeypatch.setattr(app.st, "secrets", {"DB_DOWNLOAD_URL": "https://example.invalid/db"})
    assert app._fetch_remote_db(str(db)) is False
    assert not db.exists()


def test_fetch_remote_db_downloads_and_writes_file_on_success(tmp_path, monkeypatch):
    db = tmp_path / "downloaded.db"
    monkeypatch.setattr(app.st, "secrets", {
        "DB_DOWNLOAD_URL": "https://example.invalid/repos/x/y/contents/aromahops.db",
        "DB_DOWNLOAD_TOKEN": "fake-token",
    })

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"fake-db-bytes"

    def fake_urlopen(req, timeout=60):
        assert req.get_header("Authorization") == "Bearer fake-token"
        return FakeResponse()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert app._fetch_remote_db(str(db)) is True
    assert db.read_bytes() == b"fake-db-bytes"


def test_app_loads_with_no_exception_default_home_mode(toy_cwd):
    # "home" (Accueil) est le mode par défaut (premier de la liste du radio) —
    # front page résumant les 5 outils (T58 : "Compare Hops" ajouté le
    # 2026-08-19), avec un bouton "Ouvrir" par outil.
    at = _app()
    at.run()
    assert not at.exception
    # T78 addendum (2026-08-22, demande utilisateur explicite) : le
    # st.title("HopFinder") texte a été retiré (redondant avec le logo
    # image + le st.header par page, voir app.main) -- le logo (image, pas
    # de type AppTest dédié distinct de st.image) et le header de la page
    # restent les signaux vérifiables ici.
    assert at.header[0].value == "Home"
    assert at.sidebar.radio[0].value == "home"
    assert len(at.button) == 5

def test_home_open_button_switches_to_target_mode(toy_cwd):
    at = _app()
    at.run()
    at.button(key="home_open_amplify").click().run()
    assert not at.exception
    assert at.sidebar.radio[0].value == "amplify"
    # Note sur la page principale, pas la sidebar (2026-08-20, correctif
    # mobile -- voir app._amplify).
    assert "mynote" in [o for o in at.selectbox[0].options]

def test_sidebar_shows_db_stats(toy_cwd):
    # T6 backlog : contexte base (nombre de houblons/notes/descripteurs)
    # visible en barre latérale, avec les vrais chiffres de la base jouet
    # (5 houblons -- hopa/hopb/hopc + twina/twinb ajoutés pour couvrir
    # l'inférence de purpose et la désambiguïsation de noms dupliqués,
    # 2026-08-19 --, 2 notes, 4 descripteurs distincts :
    # citrus/woody/floral/resinous).
    at = _app()
    at.run()
    assert not at.exception
    stats_caption = next(c.value for c in at.sidebar.caption if "hops" in c.value)
    assert "5 hops" in stats_caption
    assert "2 notes" in stats_caption
    assert "4 descriptors" in stats_caption

def test_amplify_shows_inline_hop_detail_expander_without_navigating(toy_cwd):
    # Remplace l'ancien bouton "ouvrir dans Browse" par ligne de résultat :
    # signalé par l'utilisateur, cliquer dessus faisait perdre la page
    # amplify en cours (résultats + blend) sans moyen d'y revenir. Désormais
    # un détail par houblon s'affiche directement en expander sur la page
    # courante (même esprit que la liste d'expanders de by-descriptor), sans
    # navigation.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    # T76 (2026-08-22) : couche descripteurs devenue la couche principale,
    # couche moléculaire décochée par défaut -- ni "lownote" ni "mynote"
    # n'ont de suggestion auto-remplie (INGREDIENT_DESCRIPTORS ne couvre que
    # de vrais noms d'ingrédients), donc rien ne se classe sans activer
    # explicitement une couche. Coche la couche moléculaire ici (comme les
    # autres tests de fumée ci-dessous) plutôt que sélectionner un
    # descripteur, pour rester indépendant du vocabulaire fixture exact.
    at.segmented_control[0].set_value("Both").run()  # T76 3e addendum : segmented_control remplace les 2 cases
    assert not at.exception
    assert any("Hopa" in e.label for e in at.expander)
    assert at.sidebar.radio[0].value == "amplify"  # toujours sur la même page

def test_amplify_mode_renders_ranked_table(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    at.segmented_control[0].set_value("Both").run()  # T76 3e addendum : segmented_control remplace les 2 cases
    assert not at.exception
    assert len(at.dataframe) >= 1

def test_amplify_results_table_includes_purpose_column(toy_cwd):
    # T-purpose backlog (demande utilisateur 2026-08-19) : colonne Purpose
    # dans le tableau de résultats amplify/contrast. Rendu en vrai
    # `st.dataframe` depuis le 2026-08-20 (signalé sur mobile : l'ancien
    # rendu ligne par ligne via `st.columns` s'empilait verticalement sur
    # petit écran, voir `_render_hop_rows`) -- texte simple ("Aromatic")
    # plutôt qu'un `st.badge` coloré, qu'un tableau ne peut pas rendre par
    # cellule. `_purpose_badge` reste utilisé (et testé) ailleurs, voir
    # test_hop_detail_expander_includes_purpose_badge_and_aroma_wheel.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    at.segmented_control[0].set_value("Both").run()  # T76 3e addendum : segmented_control remplace les 2 cases
    assert not at.exception
    df = at.dataframe[0].value
    assert "Purpose" in df.columns
    assert "Aromatic" in df["Purpose"].tolist()

def test_hop_detail_expander_includes_purpose_badge_and_aroma_wheel(toy_cwd):
    # T-purpose backlog : "include the aroma wheel as well, basically the
    # same content than what is on the browse page" -- badge + roue d'arôme
    # (Vega-Lite, non structuré par AppTest -> vérifié via UnknownElement,
    # même approche que la heatmap by-descriptor).
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    at.segmented_control[0].set_value("Both").run()  # T76 3e addendum : segmented_control remplace les 2 cases
    assert not at.exception
    assert any("-badge[" in m.value for m in at.markdown)
    assert any(isinstance(n, UnknownElement) for n in at.main)

def test_amplify_blend_base_hop_selector_appears_with_descriptors(toy_cwd):
    # Décision utilisateur (2026-08-19) : houblon de base du blend choisi par
    # l'utilisateur plutôt qu'imposé (le score est souvent homogène).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    base_select = at.selectbox(key="amplify_base_hop")
    assert "Hopa" in base_select.options

def test_amplify_blend_renders_each_size_in_its_own_container(toy_cwd):
    # Demande utilisateur (2026-08-19) : "it's visually difficult to
    # separate blend n1/n2...n5" -- chaque taille de blend rendue dans son
    # propre st.container(border=True) (voir _render_blends). AppTest
    # n'expose pas la bordure elle-même (propriété de rendu, pas de donnée
    # structurée) : on vérifie que le contenu de chaque taille (en-tête +
    # tableau de houblons) continue de se rendre sans exception après ce
    # changement de mise en page.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    assert any("Size 1" in m.value for m in at.markdown)

def test_amplify_warns_on_low_molecular_coverage(toy_cwd):
    # "lownote" (fixture, un seul molécule productible : "molx" -- voir
    # _build_toy_db) : avertissement recentré (T76, 2026-08-22) sur le VRAI
    # cas dégénéré ("<=1 molécule productible") plutôt que sur un seuil de
    # pourcentage qui se déclenchait pour toute la base sans exception (voir
    # app._amplify). Couche moléculaire optionnelle, décochée par défaut
    # depuis T76 -- activée explicitement ici.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    # Note sur la page principale, pas la sidebar (2026-08-20, correctif
    # mobile -- voir app._amplify).
    at.selectbox[0].set_value("lownote").run()
    at.segmented_control[0].set_value("Both").run()  # T76 3e addendum : segmented_control remplace les 2 cases
    assert not at.exception
    assert any("producible molecule" in w.value for w in at.warning)

def test_amplify_no_low_coverage_warning_when_coverage_high(toy_cwd):
    # "lownote" trie avant "mynote" alphabétiquement -> sélection explicite,
    # pas de dépendance à l'ordre par défaut du selectbox. "mynote" a 2
    # molécules productibles (molx, moly) -- pas de cas dégénéré (T76).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    # Note sur la page principale, pas la sidebar (2026-08-20, correctif
    # mobile -- voir app._amplify).
    at.selectbox[0].set_value("mynote").run()
    at.segmented_control[0].set_value("Both").run()  # T76 3e addendum : segmented_control remplace les 2 cases
    assert not at.exception
    assert not any("Low molecular coverage" in w.value for w in at.warning)

def test_missing_db_shows_error_not_exception():
    # cwd SANS aromahops.db : doit afficher st.error proprement (st.stop()),
    # jamais lever une exception non gérée.
    tmpdir = tempfile.mkdtemp()
    old_cwd = os.getcwd()
    os.chdir(tmpdir)
    try:
        at = _app()
        at.run()
        assert not at.exception
        assert any("not found" in e.value for e in at.error)
    finally:
        os.chdir(old_cwd)

def test_contrast_mode_with_manual_descriptors(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("contrast").run()
    assert not at.exception
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    # cible d'affinité de "citrus" (CONTRAST_AFFINITY) = resinous/woody/herbal ;
    # "woody" est un vrai descripteur de hopa dans la base jouet -> apparaît
    # dans le tableau de résultats plutôt que dans la légende elle-même.
    assert any("affinity target" in c.value.lower() for c in at.caption)
    assert len(at.dataframe) >= 1
    assert any("Hopa" in e.label for e in at.expander)  # détail par houblon, sans navigation
    assert at.selectbox(key="contrast_base_hop") is not None

def test_contrast_target_pills_are_preselected_from_affinity_map(toy_cwd):
    # Demande utilisateur explicite (2026-08-19) : "pre-tick proposed
    # contrast note but let the user modify them" -- les pills doivent être
    # pré-cochées avec EXACTEMENT la proposition automatique dès qu'un
    # descripteur de note est choisi, sans action supplémentaire.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("contrast").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    # 2 widgets pills désormais : cible d'affinité (T57) + purpose (T61).
    assert len(at.pills) == 2
    target_pills = at.pills(key="contrast_target_pills_('citrus',)")
    assert set(target_pills.options) == set(matching.CONTRAST_CORE_CATEGORIES)
    assert set(target_pills.value) == {"resinous", "woody", "herbal"}

def test_contrast_purpose_pills_are_preselected_on_both(toy_cwd):
    # T61, demande utilisateur explicite : "pre-selecting both bittering and
    # aromatic but... let user add a filter on this purpose".
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("contrast").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    purpose_pills = at.pills(key="contrast_purpose_pills")
    assert set(purpose_pills.options) == {"aromatic", "bittering"}
    assert set(purpose_pills.value) == {"aromatic", "bittering"}

def test_contrast_unticking_purpose_pill_excludes_other_role(toy_cwd):
    # cible "citrus" -> resinous/woody/herbal : hopa (descripteur "woody",
    # purpose RÉEL "aromatic") ET hopc (descripteur "resinous", pas de
    # purpose réel mais alpha_acid=14.5% -> INFÉRÉ "bittering", seuil 7.0%)
    # matchent tous deux avant filtrage. Décocher "bittering" (ne garder que
    # "aromatic") doit exclure hopc, garder hopa.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("contrast").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    assert any("Hopa" in e.label for e in at.expander)
    assert any("Hopc" in e.label for e in at.expander)  # avant filtrage
    at.pills(key="contrast_purpose_pills").set_value(["aromatic"]).run()
    assert not at.exception
    assert any("Hopa" in e.label for e in at.expander)
    assert not any("Hopc" in e.label for e in at.expander)  # inféré bittering -> exclu

def test_contrast_unticking_a_pill_narrows_results_to_that_note_only(toy_cwd):
    # Bug signalé par l'utilisateur (Saaz noyé pour "tropical") reproduit
    # avec la fixture : "citrus" propose resinous/woody/herbal -- hopa
    # ("woody") ET hopc ("resinous") matchent tous deux au départ. Décocher
    # "resinous" (ne garder que woody+herbal) doit exclure hopc, ne laissant
    # que hopa -- exactement le contrôle demandé par l'utilisateur.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("contrast").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    assert any("Hopc" in e.label for e in at.expander)  # avant : hopc matche via "resinous"
    at.pills[0].set_value(["woody", "herbal"]).run()
    assert not at.exception
    assert any("affinity target: herbal, woody" in c.value.lower() for c in at.caption)
    assert any("Hopa" in e.label for e in at.expander)
    assert not any("Hopc" in e.label for e in at.expander)  # exclu : ne matchait que "resinous"

def test_contrast_shows_truncation_caption_when_more_matches_than_shown(toy_cwd):
    # Signalé par l'utilisateur (2026-08-19) : Saaz introuvable pour
    # "tropical"/"mango" même en augmentant "Number of results" au max --
    # la troncature était silencieuse. Cible "citrus" (CONTRAST_AFFINITY)
    # = resinous/woody/herbal -> hopa ("woody") ET hopc ("resinous")
    # recoupent tous deux dans la fixture -- avec "Number of results"
    # ramené à 1, un seul est affiché mais la légende doit signaler les 2.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("contrast").run()
    at.multiselect[0].select("citrus").run()
    # Curseur sur la page principale, pas la sidebar (2026-08-20, correctif
    # mobile -- voir app._amplify).
    at.slider[0].set_value(1).run()
    assert not at.exception
    assert any("Showing 1 of 2 hops" in c.value for c in at.caption)

def test_by_descriptor_mode_lists_matching_hop(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    assert not at.exception
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    # hopa a "citrus", hopb non -> hopa doit apparaître dans un expander
    assert any("Hopa" in e.label for e in at.expander)
    assert not any("Hopb" in e.label for e in at.expander)

def test_by_descriptor_wheel_pills_appear_and_contribute_to_match(toy_cwd):
    # Demande utilisateur explicite (2026-08-19) : "propose a section here
    # user can click on the boxes corresponding to aroma wheel flavors" --
    # st.pills pour le sous-vocabulaire à intensité mesurée (citrus/woody
    # dans la fixture, voir _build_toy_db). Sélectionner UNIQUEMENT via les
    # pills (pas le multiselect) doit produire exactement le même filtrage
    # catégorique qu'avant -- union avec la sélection générale, pas un
    # mécanisme séparé.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    assert not at.exception
    assert len(at.pills) == 1
    assert set(at.pills[0].options) == {"citrus", "woody"}
    at.pills[0].set_value(["citrus"]).run()
    assert not at.exception
    assert any("Hopa" in e.label for e in at.expander)
    assert not any("Hopb" in e.label for e in at.expander)

def test_by_descriptor_shows_quantitative_refinement_when_intensity_available(toy_cwd):
    # hopa a une intensité mesurée pour "citrus" (80.0, voir _build_toy_db) --
    # la transparence explicite (jamais un réordonnancement silencieux, voir
    # matching.by_descriptor) doit apparaître dans son expander de détail.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.pills[0].set_value(["citrus"]).run()
    assert not at.exception
    assert any("Quantitative refinement: 80/100" in c.value and "citrus" in c.value
              for c in at.caption)

def test_by_descriptor_heatmap_separates_wheel_and_other_descriptor_sections(toy_cwd):
    # Addendum 2026-08-19 (retour utilisateur explicite : "separate
    # descriptors from quantitative aroma wheel values in two section in
    # the heatmap") -- citrus+floral recoupe hopa (citrus/woody, tous deux
    # dans hop_aroma_intensity de la fixture -> section roue) ET hopb
    # (floral, hors du vocabulaire roue de la fixture -> section "other").
    # Les deux captions/sections doivent apparaître séparément.
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("citrus").select("floral").run()
    assert not at.exception
    assert any("Aroma wheel descriptors" in c.value for c in at.caption)
    assert any("Other descriptors" in c.value for c in at.caption)
    # iframe de fond + 2 heatmaps (roue + other) au minimum.
    assert len([n for n in at.main if isinstance(n, UnknownElement)]) >= 3

def test_by_descriptor_mode_hides_heatmap_for_single_hop(toy_cwd):
    # Un seul houblon recoupé -> rien à comparer, pas de grille (juste
    # l'expander habituel). Exactement 2 UnknownElement attendus : l'iframe
    # toujours présente de `app._inject_background` (ce n'est plus un
    # st.markdown/CSS mais un st.iframe, seul moyen de faire réagir le fond au
    # sélecteur de thème Streamlit sans dépendre d'un rerun Python, voir
    # CLAUDE.md) -- présent sur CHAQUE page, indépendamment du mode -- PLUS la
    # roue d'arôme (st.altair_chart, Vega-Lite non structuré par AppTest) de
    # hopa dans l'expander de détail, ajoutée au tool by-descriptor le
    # 2026-08-19 (demande utilisateur : "The aroma wheel is missing from the
    # from descriptor tool").
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    assert not any("Aroma wheel descriptors" in c.value for c in at.caption)
    assert not any("Other descriptors" in c.value for c in at.caption)
    assert len([n for n in at.main if isinstance(n, UnknownElement)]) == 2

def test_browse_mode_shows_hop_composition_and_descriptors(toy_cwd):
    # T5 backlog : consulter un houblon (composition + descripteurs) sans
    # passer par amplify/contrast/by-descriptor.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    assert not at.exception
    at.selectbox[0].set_value("hopa").run()
    assert not at.exception
    assert any("Hopa" in s.value for s in at.subheader)
    assert any("citrus" in m.value and "woody" in m.value for m in at.markdown)
    assert len(at.dataframe) >= 1

def test_browse_shows_purpose_badge_as_top_info(toy_cwd):
    # T-purpose backlog (demande utilisateur explicite : "should appear in
    # the browser information as a main/top information") -- badge juste
    # après le nom du houblon, avant région/sources.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopa").run()
    assert not at.exception
    assert any("-badge[" in m.value and "Aromatic" in m.value for m in at.markdown)

def test_browse_mode_search_filters_hop_list(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    assert not at.exception
    at.text_input[0].set_value("hopb").run()
    assert not at.exception
    caption = next(c.value for c in at.caption if "hop(s)" in c.value)
    assert "1 hop(s)" in caption
    # .options renvoie le libellé affiché (format_func), pas le code brut.
    options = at.selectbox[0].options
    assert options == ["Hopb"]

def test_browse_disambiguates_duplicate_hop_names_by_region(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    assert not at.exception
    at.text_input[0].set_value("twins").run()  # twina/twinb : même nom, régions différentes
    assert not at.exception
    options = at.selectbox[0].options
    assert set(options) == {"Twins (Region A)", "Twins (Region B)"}

def test_compare_requires_at_least_one_hop(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    assert not at.exception
    assert any("Choose at least one hop" in w.value for w in at.markdown)

def test_compare_shows_no_wheel_data_caption_for_hops_without_intensity(toy_cwd):
    # hopa a une roue d'arôme (citrus/woody, voir _build_toy_db) ; hopc n'en
    # a aucune -- doit apparaître explicitement en avertissement (T79, 4e
    # addendum, 2026-08-23 : st.warning plutôt qu'une caption discrète),
    # jamais un polygone à 0 fabriqué (T58, 2026-08-19).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    at.multiselect[0].select("Hopa").select("Hopc").run()
    assert not at.exception
    warning = next(w.value for w in at.warning if "Not in the Yakima database" in w.value)
    assert "Hopc" in warning
    assert "Hopa" not in warning

def test_compare_renders_principal_barplot_when_data_present(toy_cwd):
    # hopc a alpha_acid/beta_acid/co_humulone/total_oil complets (voir
    # _build_toy_db) -> le barplot 1 doit se rendre (pas de message "no data").
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    at.multiselect[0].select("Hopc").run()
    assert not at.exception
    assert not any("No principal composition data" in m.value for m in at.markdown)
    assert len([n for n in at.main if isinstance(n, UnknownElement)]) >= 1

def test_compare_shows_no_detailed_data_message_when_absent(toy_cwd):
    # hopa/hopc n'ont aucun composé de la liste "détaillée" (myrcène...) dans
    # la fixture -- message honnête plutôt qu'un graphique vide.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    at.multiselect[0].select("Hopa").select("Hopc").run()
    assert not at.exception
    assert any("No detailed composition data" in m.value for m in at.markdown)

def test_browse_shows_key_stats_metrics(toy_cwd):
    # Demande utilisateur explicite (2026-08-19) : "il manque un élément
    # principale : les infos les plus importantes de yakima : i) ALPHA ACIDS
    # % and it's fraction of cohumulone ii) BETA ACIDS % et iii) TOTAL OIL
    # ml/100g" -- _render_key_stats, hopc porte les 4 valeurs dans la fixture.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopc").run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Alpha acids"] == "14.5%"
    assert metrics["Beta acids"] == "4.5%"
    assert metrics["Co-humulone (% of AA)"] == "22%"
    assert metrics["Total oil (ml/100g)"] == "1.5"

def test_browse_key_stats_show_dash_when_missing(toy_cwd):
    # hopa n'a aucune composition alpha_acid/beta_acid/co_humulone dans la
    # fixture -- jamais une valeur inventée, "—" explicite (voir
    # _render_key_stats).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopa").run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Alpha acids"] == "—"
    assert metrics["Co-humulone (% of AA)"] == "—"

def test_browse_purpose_badge_shows_inferred_when_no_real_purpose(toy_cwd):
    # hopc n'a pas de purpose BeerMaverick réel dans la fixture mais un
    # acide alpha de 14.5% (>> seuil 7.0%) -- doit s'afficher "Inferred:
    # Bittering", jamais "Unknown" (demande utilisateur explicite : "instead
    # of unknown for the purpose, use infered:aromatic and infered:bittering").
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopc").run()
    assert not at.exception
    assert any("-badge[" in m.value and "Inferred: Bittering" in m.value for m in at.markdown)

def test_by_descriptor_expander_shows_inferred_purpose_and_key_stats(toy_cwd):
    # Même couverture que Browse, mais dans l'expander de détail
    # by-descriptor (demande utilisateur : "ainsi que dans les détails des
    # houblons proposés pour les autres outils").
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("resinous").run()
    assert not at.exception
    assert any("Hopc" in e.label for e in at.expander)
    assert any("-badge[" in m.value and "Inferred: Bittering" in m.value for m in at.markdown)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Alpha acids"] == "14.5%"
