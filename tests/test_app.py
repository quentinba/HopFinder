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

from hopmatch.schema import connect, init_db

APP_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "hopmatch", "app.py")


def _build_toy_db(path):
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
    con.executemany("INSERT INTO hop_aroma_intensity VALUES (?,?,?,?)", [
        ("hopa", "citrus", 80.0, "toy"), ("hopa", "woody", 20.0, "toy"),
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


def test_app_loads_with_no_exception_default_home_mode(toy_cwd):
    # "home" (Accueil) est le mode par défaut (premier de la liste du radio) —
    # front page résumant les 4 outils, avec un bouton "Ouvrir" par outil.
    at = _app()
    at.run()
    assert not at.exception
    assert at.title[0].value == "hopmatch"
    assert at.sidebar.radio[0].value == "home"
    assert len(at.button) == 4

def test_home_open_button_switches_to_target_mode(toy_cwd):
    at = _app()
    at.run()
    at.button(key="home_open_amplify").click().run()
    assert not at.exception
    assert at.sidebar.radio[0].value == "amplify"
    assert "mynote" in [o for o in at.sidebar.selectbox[0].options]

def test_sidebar_shows_db_stats(toy_cwd):
    # T6 backlog : contexte base (nombre de houblons/notes/descripteurs)
    # visible en barre latérale, avec les vrais chiffres de la base jouet
    # (2 houblons, 2 notes, 2 descripteurs distincts : citrus/woody/floral -> 3).
    at = _app()
    at.run()
    assert not at.exception
    stats_caption = next(c.value for c in at.sidebar.caption if "hops" in c.value)
    assert "2 hops" in stats_caption
    assert "2 notes" in stats_caption
    assert "3 descriptors" in stats_caption

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
    assert not at.exception
    assert any("Hopa" in e.label for e in at.expander)
    assert at.sidebar.radio[0].value == "amplify"  # toujours sur la même page

def test_amplify_mode_renders_ranked_table(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    assert not at.exception
    assert len(at.dataframe) >= 1

def test_amplify_results_table_includes_purpose_column(toy_cwd):
    # T-purpose backlog (demande utilisateur 2026-08-19) : colonne Purpose
    # dans le tableau de résultats amplify/contrast -- rendu ligne par ligne
    # (st.columns + st.badge, pas st.dataframe : seul st.badge s'adapte aux
    # deux thèmes, voir _render_hop_rows/_purpose_badge).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    assert not at.exception
    assert any(c.value == "Purpose" for c in at.caption)
    assert any("-badge[" in m.value and "Aromatic" in m.value for m in at.markdown)

def test_hop_detail_expander_includes_purpose_badge_and_aroma_wheel(toy_cwd):
    # T-purpose backlog : "include the aroma wheel as well, basically the
    # same content than what is on the browse page" -- badge + roue d'arôme
    # (Vega-Lite, non structuré par AppTest -> vérifié via UnknownElement,
    # même approche que la heatmap by-descriptor).
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
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

def test_amplify_warns_on_low_molecular_coverage(toy_cwd):
    # "lownote" (fixture, ~1% de couverture) : voir _build_toy_db.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    at.sidebar.selectbox[0].set_value("lownote").run()
    assert not at.exception
    assert any("Low molecular coverage" in w.value for w in at.warning)

def test_amplify_no_low_coverage_warning_when_coverage_high(toy_cwd):
    # "lownote" trie avant "mynote" alphabétiquement -> sélection explicite,
    # pas de dépendance à l'ordre par défaut du selectbox.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("amplify").run()
    at.sidebar.selectbox[0].set_value("mynote").run()
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

def test_by_descriptor_mode_shows_comparison_heatmap_for_multiple_hops(toy_cwd):
    # T4 backlog : grille de comparaison (houblon x descripteur) dès que
    # >=2 houblons recoupent la sélection ; "citrus"+"floral" recoupe hopa
    # ET hopb dans la base jouet (by_descriptor matche l'union, pas
    # l'intersection). AppTest ne structure pas les graphiques Vega-Lite
    # (st.altair_chart) : on vérifie leur présence via UnknownElement, faute
    # d'accesseur dédié -- au moins 2 désormais (la heatmap ET l'iframe
    # toujours présente de `app._inject_background`, voir le test suivant).
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("citrus").select("floral").run()
    assert not at.exception
    assert any("Descriptor profile comparison" in c.value for c in at.caption)
    assert len([n for n in at.main if isinstance(n, UnknownElement)]) >= 2

def test_by_descriptor_mode_hides_heatmap_for_single_hop(toy_cwd):
    # Un seul houblon recoupé -> rien à comparer, pas de grille (juste
    # l'expander habituel). Exactement 1 UnknownElement attendu (l'iframe
    # toujours présente de `app._inject_background`), pas 0 : ce n'est plus
    # un st.markdown/CSS mais un st.iframe (seul moyen de faire réagir le
    # fond au sélecteur de thème Streamlit sans dépendre d'un rerun Python,
    # voir CLAUDE.md) -- présent sur CHAQUE page, indépendamment du mode.
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    assert not any("Descriptor profile comparison" in c.value for c in at.caption)
    assert len([n for n in at.main if isinstance(n, UnknownElement)]) == 1

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
