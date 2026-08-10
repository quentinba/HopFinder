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
    for v, desc in (("hopa", ["citrus", "woody"]), ("hopb", ["floral"])):
        con.execute("INSERT INTO hops VALUES (?,?,?,?)", (v, v.title(), "test", "toy"))
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


def test_app_loads_with_no_exception_default_amplify_mode(toy_cwd):
    at = _app()
    at.run()
    assert not at.exception
    assert at.title[0].value == "hopmatch"
    # "amplify" est le mode par défaut (premier de la liste du radio)
    assert "mynote" in [o for o in at.sidebar.selectbox[0].options]

def test_sidebar_shows_db_stats(toy_cwd):
    # T6 backlog : contexte base (nombre de houblons/notes/descripteurs)
    # visible en barre latérale, avec les vrais chiffres de la base jouet
    # (2 houblons, 1 note, 2 descripteurs distincts : citrus/woody/floral -> 3).
    at = _app()
    at.run()
    assert not at.exception
    stats_caption = next(c.value for c in at.sidebar.caption if "houblons" in c.value)
    assert "2 houblons" in stats_caption
    assert "1 notes" in stats_caption
    assert "3 descripteurs" in stats_caption

def test_amplify_mode_renders_ranked_table(toy_cwd):
    at = _app()
    at.run()
    assert not at.exception
    assert len(at.dataframe) >= 1

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
        assert any("introuvable" in e.value for e in at.error)
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
    assert any("cible d'affinité" in c.value.lower() for c in at.caption)
    assert len(at.dataframe) >= 1

def test_combine_mode_renders_metrics(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("combine").run()
    assert not at.exception
    note_select = at.sidebar.selectbox[0]
    note_select.set_value("mynote").run()
    assert not at.exception
    assert len(at.metric) >= 2  # couverture + résidu

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
    # d'accesseur dédié.
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("citrus").select("floral").run()
    assert not at.exception
    assert any("Comparaison des profils" in c.value for c in at.caption)
    assert any(isinstance(n, UnknownElement) for n in at.main)

def test_by_descriptor_mode_hides_heatmap_for_single_hop(toy_cwd):
    # Un seul houblon recoupé -> rien à comparer, pas de grille (juste
    # l'expander habituel).
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    assert not any("Comparaison des profils" in c.value for c in at.caption)
    assert not any(isinstance(n, UnknownElement) for n in at.main)

def test_browse_mode_shows_hop_composition_and_descriptors(toy_cwd):
    # T5 backlog : consulter un houblon (composition + descripteurs) sans
    # passer par amplify/combine/by-descriptor.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    assert not at.exception
    at.selectbox[0].set_value("hopa").run()
    assert not at.exception
    assert any("Hopa" in s.value for s in at.subheader)
    assert any("citrus" in m.value and "woody" in m.value for m in at.markdown)
    assert len(at.dataframe) >= 1

def test_browse_mode_search_filters_hop_list(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    assert not at.exception
    at.text_input[0].set_value("hopb").run()
    assert not at.exception
    caption = next(c.value for c in at.caption if "houblon(s)" in c.value)
    assert "1 houblon(s)" in caption
    # .options renvoie le libellé affiché (format_func), pas le code brut.
    options = at.selectbox[0].options
    assert options == ["Hopb"]
