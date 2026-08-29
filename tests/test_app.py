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
        con.execute("INSERT INTO hops (variety, name, region, sources, purpose) VALUES (?,?,?,?,?)",
                    (v, name, region, "toy", purpose[v]))
        for d in desc:
            con.execute("INSERT INTO hop_descriptors VALUES (?,?,?)", (v, d, "toy"))
    rows = [
        ("hopa", "molx", 50, 50, "pct_oil", "toy", "ok", ""),
        ("hopa", "total_oil", 1.0, 1.0, "ml_100g", "toy", "ok", ""),
        # T99 : composé "survivable" (linalool) uniquement sur hopa -- teste
        # la couche chimique du panneau "Recommended usage" sans toucher au
        # nombre total de recettes hop_usage_stats des autres tests (T108,
        # valeurs 10,000/5 pinnées ailleurs -- voir plus bas dans ce fichier).
        ("hopa", "linalool", 30, 30, "pct_oil", "toy", "ok", ""),
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
    # T82 : deux styles jouets pour tester le mode "Beer styles" -- category_id
    # "2" et "10" (pas "1"/"2") pour vérifier le tri NUMÉRIQUE ("2" avant "10",
    # jamais l'inverse lexicographique) ; "10A" sans AUCUNE vital stat pour
    # tester la branche "—" + caption partagée (voir app._vital_stat_row).
    style_cols = ("style_id", "guideline_year", "category_id", "category", "name", "type",
                 "tags", "og_min", "og_max", "fg_min", "fg_max", "abv_min", "abv_max",
                 "ibu_min", "ibu_max", "srm_min", "srm_max", "overall_impression", "aroma",
                 "appearance", "flavor", "mouthfeel", "comments", "history", "ingredients",
                 "style_comparison", "examples", "category_description", "source")
    style_rows = [
        {"style_id": "2A", "guideline_year": 2021, "category_id": "2", "category": "Test Lager",
         "name": "Test Lager Style", "type": "beer", "tags": "crisp, pale",
         "og_min": 1.044, "og_max": 1.056, "fg_min": 1.008, "fg_max": 1.013,
         "abv_min": 4.5, "abv_max": 6.0, "ibu_min": 18.0, "ibu_max": 30.0,
         "srm_min": 3.0, "srm_max": 6.0,
         # T103 : "citrus"/"floral" ajoutés au texte "aroma" (vocabulaire
         # jouet réel citrus/woody/floral/resinous, voir plus haut) --
         # teste le pré-remplissage `matching.style_typical_descriptors`
         # sans casser le texte affiché ailleurs (aucun test n'attendait le
         # texte exact "Light malt aroma." seul).
         "overall_impression": "A clean, crisp toy lager.",
         "aroma": "Light malt aroma with a touch of citrus and floral hop character.",
         "appearance": None, "flavor": "Clean, balanced.", "mouthfeel": None,
         "comments": None, "history": None, "ingredients": None, "style_comparison": None,
         "examples": "Example One, Example Two", "category_description": None, "source": "bjcp-json"},
        {"style_id": "10A", "guideline_year": 2021, "category_id": "10", "category": "Test Wheat",
         "name": "Test Wheat Style", "type": "beer", "tags": None,
         "og_min": None, "og_max": None, "fg_min": None, "fg_max": None,
         "abv_min": None, "abv_max": None, "ibu_min": None, "ibu_max": None,
         "srm_min": None, "srm_max": None,
         "overall_impression": "Inherits from its base style.", "aroma": None,
         "appearance": None, "flavor": None, "mouthfeel": None,
         "comments": None, "history": None, "ingredients": None, "style_comparison": None,
         "examples": None, "category_description": None, "source": "bjcp-json"},
    ]
    con.executemany(
        f"INSERT INTO beer_styles VALUES ({','.join(':' + c for c in style_cols)})", style_rows)
    # T105 : distribution observée (style_recipe_stats) pour "2A" uniquement
    # -- "10A" reste sans AUCUNE donnée observée (teste le repli silencieux
    # sur la simple barre BJCP, voir app._vital_stat_row).
    con.executemany("INSERT INTO style_recipe_stats VALUES (?,?,?,?,?,?,?,?)", [
        ("2A", "test-lager-style", "abv", 4.5, 5.0, 30, "test", "2026"),
        ("2A", "test-lager-style", "abv", 5.0, 5.5, 70, "test", "2026"),
    ])
    # T103 : fréquence réelle (style_hop_usage) pour "2A"/"any" -- SEULEMENT
    # hopa (descripteur "citrus", matche le texte "aroma" ci-dessus). hopb
    # (descripteur "floral", matche AUSSI le texte "aroma") N'A AUCUNE ligne
    # ici -- teste la section "aromatically relevant, rarely used"
    # (app._style_hops) : hopb doit y apparaître, hopa non. hopc (descripteur
    # "resinous", ne matche PAS le texte "aroma") reste hors des deux
    # classements. "10A" reste sans AUCUNE ligne (teste le repli silencieux
    # complet, aucune section "rare & relevant" fabriquée sans donnée réelle).
    con.executemany("INSERT INTO style_hop_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("test-lager-style", "2A", "Hopa", "hopa", "any", 0.4, 0.35, None, None, None,
         "test", "2026"),
    ])
    # T106 : métadonnées d'identité -- hopa porte tout (cultivar/breeder/
    # release_year/pedigree + is_experimental=1), hopb seulement is_organic=1,
    # hopc rien du tout (teste l'omission silencieuse de la ligne entière,
    # pas de "—", voir app._render_hop_identity).
    con.execute(
        "UPDATE hops SET cultivar=?, breeder=?, release_year=?, pedigree=?, is_experimental=1 "
        "WHERE variety='hopa'",
        ("HBC 999", "Toy Breeding Co.", 2020, "Cross between Toya and Toyb."))
    con.execute("UPDATE hops SET is_organic=1 WHERE variety='hopb'")
    # T107 : description éditoriale -- hopa seulement (hopb/hopc restent
    # NULL, teste l'absence d'expander).
    con.execute(
        "UPDATE hops SET description=?, description_source='yakima' WHERE variety='hopa'",
        ("Toy hop known for its citrus profile.\n\nGreat in Toy IPAs.",))
    # T108 : popularité (hop_usage_stats) -- hopa très populaire (10000
    # recettes), hopb peu populaire (5 recettes, sous le seuil filtre par
    # défaut du test), hopc SANS AUCUNE donnée (jamais dans hop_usage_stats)
    # -- teste les 3 cas : donnée forte, donnée faible, absence de donnée.
    con.executemany("INSERT INTO hop_usage_stats VALUES (?,?,?,?,?,?,?,?,?)", [
        ("hopa", "Hopa", "Boil", 10000, None, None, None, "test", "2026"),
        ("hopb", "Hopb", "Boil", 5, None, None, None, "test", "2026"),
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
    # image + le titre de page, voir app.main) -- le logo (image, pas
    # de type AppTest dédié distinct de st.image) et le titre de la page
    # restent les signaux vérifiables ici. T-D03 (2026-08-23, spec Claude
    # Design) : le titre de page est passé de `st.header` (h2) à `st.title`
    # (h1, un seul par page, exigence de la spec).
    assert at.title[0].value == "Home"
    assert at.sidebar.radio[0].value == "home"
    assert len(at.button) == 8  # T117 : "Survivables" ajouté aux 7 outils existants

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
    # T-D05 (2026-08-23, spec Claude Design) : la pile st.warning est devenue
    # une ligne de chips `st.badge` (`app._confidence_strip`) -- `st.badge`
    # se rend en AppTest comme un élément markdown portant la directive
    # `:color-badge[label]`, le texte d'explication n'est plus affiché en
    # dur (déplacé dans `help=`, non exposé par AppTest) : on vérifie donc
    # le LABEL du chip, plus la phrase complète.
    assert any("Single-molecule ranking" in md.value for md in at.markdown)

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
    # T-D06 (spec Claude Design) : la cible d'affinité est désormais rendue
    # en pills sage (`app._descriptor_chips`, directives Markdown
    # `:green-badge[...]`) plutôt qu'une liste "a, b" en texte brut.
    assert any(":green-badge[herbal]" in c.value and ":green-badge[woody]" in c.value
              for c in at.caption)
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

def test_by_descriptor_sort_by_popularity_reorders_results(toy_cwd):
    # T108 : hopa (10000 recettes) et hopb (5 recettes) recoupent tous deux
    # au moins un descripteur choisi -- tri "Popularity" doit passer hopa
    # devant hopb, contrairement au tri "Relevance" par défaut.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("citrus").select("floral").run()
    assert not at.exception
    labels = [e.label for e in at.expander]
    assert any(l.startswith("Hopa") for l in labels)
    assert any(l.startswith("Hopb") for l in labels)

    at.segmented_control[0].set_value("Popularity").run()
    assert not at.exception
    names = [e.label.split(" —")[0] for e in at.expander]
    assert names.index("Hopa") < names.index("Hopb")
    assert any("Popularity: 10,000 recipes" in c.value for c in at.caption)
    assert any("Popularity: 5 recipes" in c.value for c in at.caption)

def test_by_descriptor_popularity_filter_never_hides_no_data_hops(toy_cwd):
    # hopc (descripteur "resinous") n'a aucune donnée hop_usage_stats --
    # le filtre popularité (seuil > 0) ne doit jamais l'exclure.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("citrus").select("floral").select("resinous").run()
    # le slider "Minimum recipes" ne s'affiche qu'en mode Popularity
    # (2026-08-29, retour utilisateur : "otherwise it make no sense to
    # display it") -- absent tant que "Relevance" (défaut) est actif.
    at.segmented_control(key="by_descriptor_sort_mode").set_value("Popularity").run()
    at.slider[1].set_value(10).run()
    assert not at.exception
    labels = " ".join(e.label for e in at.expander)
    assert "Hopb" not in labels  # 5 recettes, sous le seuil -> exclu
    assert "Hopa" in labels      # 10000 recettes -> reste
    assert "Hopc" in labels      # aucune donnée -> jamais exclu

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
    # l'expander habituel). Exactement 1 UnknownElement attendu : la roue
    # d'arôme (st.altair_chart, Vega-Lite non structuré par AppTest) de
    # hopa dans l'expander de détail, ajoutée au tool by-descriptor le
    # 2026-08-19 (demande utilisateur : "The aroma wheel is missing from the
    # from descriptor tool"). T-D02 (2026-08-23, spec Claude Design) :
    # `app._inject_background` est passé de `st.iframe` (JS) à `st.html`
    # (CSS pure, `light-dark()`) -- ne compte plus comme UnknownElement.
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("by-descriptor").run()
    at.multiselect[0].select("citrus").run()
    assert not at.exception
    assert not any("Aroma wheel descriptors" in c.value for c in at.caption)
    assert not any("Other descriptors" in c.value for c in at.caption)
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

def test_browse_recommended_usage_shows_both_layers_when_available(toy_cwd):
    # T99 : hopa a à la fois une donnée empirique (hop_usage_stats, "Boil"
    # 10000 recettes, voir _build_toy_db/T108) ET une donnée chimique
    # (linalool, ajouté pour ce ticket) -- les deux couches doivent
    # s'afficher, jamais fusionnées.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopa").run()
    assert not at.exception
    assert any(s.value == "Recommended usage" for s in at.subheader)
    assert any("Where brewers actually use it" in m.value for m in at.markdown)
    assert any("Estimated from composition" in m.value for m in at.markdown)
    # seul composé chimique connu pour hopa dans la fixture (T99) -- seul
    # houblon à le porter, donc rang quantile dégénéré (n=1) -> 100%.
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Early-use index (whirlpool / active dry hop)"] == "100%"
    assert any("linalool" in c.value for c in at.caption)
    # table empirique : la seule étape connue pour hopa est "Boil" -- repérée
    # par sa colonne "Stage" (unique à cette table) plutôt qu'un index
    # positionnel, fragile face aux autres tableaux de la page (composition,
    # similar hops...).
    usage_df = next(df.value for df in at.dataframe if "Stage" in df.value.columns)
    assert "Boil" in usage_df["Stage"].tolist()

def test_browse_recommended_usage_falls_back_silently_without_any_data(toy_cwd):
    # hopc : aucune ligne hop_usage_stats (voir _build_toy_db/T108) ET aucun
    # des 4 composés chimiques T99 (alpha_acid/beta_acid/co_humulone/
    # total_oil seulement) -- message honnête unique, pas un tableau vide
    # fabriqué ni un indice inventé.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopc").run()
    assert not at.exception
    assert any(s.value == "Recommended usage" for s in at.subheader)
    assert any("No usage data (empirical or chemical) for this variety." in c.value
              for c in at.caption)
    assert "Early-use index (whirlpool / active dry hop)" not in {m.label for m in at.metric}

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

def test_browse_shows_hop_identity_metadata_and_badges(toy_cwd):
    # T106 : cultivar/breeder/release_year/pedigree en ligne de texte,
    # badge "Experimental" (is_experimental=1, voir _build_toy_db).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopa").run()
    assert not at.exception
    assert any("-badge[" in m.value and "Experimental" in m.value for m in at.markdown)
    assert any("HBC 999" in c.value and "Toy Breeding Co." in c.value and "2020" in c.value
              for c in at.caption)
    assert any("Cross between Toya and Toyb." in c.value for c in at.caption)

def test_browse_hop_identity_badge_matches_boolean_flag(toy_cwd):
    # hopb : is_organic=1 seulement -- badge "Organic", jamais "Experimental"/"Blend".
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopb").run()
    assert not at.exception
    assert any("-badge[" in m.value and "Organic" in m.value for m in at.markdown)
    assert not any("-badge[" in m.value and "Experimental" in m.value for m in at.markdown)

def test_browse_hop_identity_omits_line_entirely_when_absent(toy_cwd):
    # hopc : aucune métadonnée d'identité -- pas de ligne "—" fabriquée,
    # la ligne cultivar/breeder/année disparaît silencieusement (demande
    # explicite du ticket T106, contrairement au reste de la GUI).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopc").run()
    assert not at.exception
    assert not any("Cultivar:" in c.value or "Breeder:" in c.value or "Pedigree:" in c.value
                  for c in at.caption)
    assert not any("-badge[" in m.value and
                  ("Experimental" in m.value or "Organic" in m.value or "Blend" in m.value)
                  for m in at.markdown)
    assert not any(e.label == "Producer description" for e in at.expander)

def test_browse_shows_producer_description_in_collapsed_expander(toy_cwd):
    # T107 : hopa porte une description -- expander "Producer description",
    # attribution explicite (Yakima Chief Hops), texte nettoyé affiché.
    # (page a aussi un expander "How does this work?" à part -- non testé ici.)
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopa").run()
    assert not at.exception
    matches = [e for e in at.expander if e.label == "Producer description"]
    assert len(matches) == 1
    desc_expander = matches[0]
    assert any("Yakima Chief Hops" in c.value and "marketing text" in c.value
              for c in desc_expander.caption)
    assert any("citrus profile" in m.value for m in desc_expander.markdown)

def test_browse_hides_description_expander_when_absent(toy_cwd):
    # hopb : is_organic=1 mais aucune description -- pas d'expander "Producer
    # description" (le "How does this work?" générique reste présent).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.selectbox[0].set_value("hopb").run()
    assert not at.exception
    assert not any(e.label == "Producer description" for e in at.expander)

def test_browse_mode_lists_all_hops_without_a_search_box(toy_cwd):
    # Champ de recherche texte libre retiré (2026-08-24, retour utilisateur
    # explicite : "the 'Hop' search bar already has completion functionality"
    # -- redondant avec le tape-à-tape natif du `st.selectbox`). Le
    # selectbox liste désormais TOUJOURS tous les houblons de la base, sans
    # filtre préalable à appliquer soi-même.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    # tri "Name" explicite (2026-08-29 : "Popularity" est désormais le
    # défaut, voir test_browse_sort_by_popularity_groups_no_data_hops_
    # separately) -- ce test porte sur "toujours tous les houblons, aucun
    # filtre texte préalable", indépendant du mode de tri par défaut.
    at.segmented_control[0].set_value("Name").run()
    assert not at.exception
    assert len(at.text_input) == 0
    # .options renvoie le libellé affiché (format_func), pas le code brut.
    options = at.selectbox[0].options
    assert options == ["Hopa", "Hopb", "Hopc", "Twins (Region A)", "Twins (Region B)"]

def test_browse_sort_by_popularity_groups_no_data_hops_separately(toy_cwd):
    # T108 : hopa (10000 recettes) > hopb (5 recettes) > groupe "no data"
    # (hopc/twina/twinb, jamais mélangé au tri numérique avec un 0 implicite).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.segmented_control[0].set_value("Popularity").run()
    assert not at.exception
    options = at.selectbox[0].options
    assert options == [
        "Hopa (10,000 recipes)", "Hopb (5 recipes)",
        "Hopc (no popularity data)",
        "Twins (Region A) (no popularity data)", "Twins (Region B) (no popularity data)",
    ]

def test_browse_popularity_filter_never_hides_no_data_hops(toy_cwd):
    # seuil 10 : exclut hopb (5 recettes, mesuré sous le seuil) mais PAS
    # hopc/twina/twinb (aucune donnée -- jamais traité comme "impopulaire").
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    at.slider[0].set_value(10).run()
    assert not at.exception
    options = at.selectbox[0].options
    assert "Hopb" not in " ".join(options)
    assert any(o.startswith("Hopa") for o in options)
    assert any(o.startswith("Hopc") for o in options)

def test_browse_disambiguates_duplicate_hop_names_by_region(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("browse").run()
    # tri "Name" explicite (2026-08-29 : "Popularity", désormais le défaut,
    # append un suffixe "(N recipes)"/"(no popularity data)" au libellé --
    # ce test porte sur la désambiguïsation par région, indépendante du
    # mode de tri).
    at.segmented_control[0].set_value("Name").run()
    assert not at.exception
    # twina/twinb : même nom, régions différentes -- les deux doivent
    # apparaître, désambiguïsées, dans la liste COMPLÈTE (pas de recherche
    # à appliquer, voir le test ci-dessus).
    options = at.selectbox[0].options
    assert {"Twins (Region A)", "Twins (Region B)"} <= set(options)

def test_compare_requires_at_least_one_hop(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    assert not at.exception
    assert any("Choose at least one hop" in w.value for w in at.markdown)

def test_compare_shows_no_wheel_data_caption_for_hops_without_intensity(toy_cwd):
    # hopa a une roue d'arôme (citrus/woody, voir _build_toy_db) ; hopc n'en
    # a aucune -- doit apparaître explicitement en avertissement (T79, 4e
    # addendum, 2026-08-23 : d'abord st.warning, puis T-D05 -- spec Claude
    # Design -- converti en chip `st.badge`, rendu comme markdown en
    # AppTest, jamais un polygone à 0 fabriqué, T58, 2026-08-19).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    at.multiselect[0].select("Hopa").select("Hopc").run()
    assert not at.exception
    warning = next(md.value for md in at.markdown if "Not in the Yakima database" in md.value)
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
    # hopb/hopc n'ont aucun composé de la liste "détaillée" (myrcène...) dans
    # la fixture -- message honnête plutôt qu'un graphique vide. hopa écarté
    # ici depuis T99 (2026-08-29) : porte désormais "linalool" (composé
    # "survivable" réel, dans `_COMPARE_DETAIL_OIL_COMPOUNDS`) pour tester
    # la couche chimique du panneau "Recommended usage" -- hopb/moly reste
    # fictif, hors de la liste "détaillée", même invariant que hopa/hopc
    # avant ce ticket.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    at.multiselect[0].select("Hopb").select("Hopc").run()
    assert not at.exception
    assert any("No detailed composition data" in m.value for m in at.markdown)

def test_compare_blend_explorer_hidden_for_a_single_hop(toy_cwd):
    # T102 : une "blend" a besoin d'au moins 2 houblons -- jamais affiché
    # pour une sélection d'un seul.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    at.multiselect[0].select("Hopa").run()
    assert not at.exception
    assert not any(s.value.startswith("Blend Explorer") for s in at.subheader)

def test_compare_blend_explorer_renders_chart_and_flags_missing_hop(toy_cwd):
    # hopa (linalool=30) contribue au blend, hopb (moly, hors des 4 composés
    # survivables) n'a AUCUNE des 4 mesures -- doit apparaître dans la
    # caption "No survivable-compound data for", jamais silencieusement
    # traité comme 0.
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    at.multiselect[0].select("Hopa").select("Hopb").run()
    assert not at.exception
    assert any(s.value.startswith("Blend Explorer") for s in at.subheader)
    assert any("No survivable-compound data for: Hopb" in c.value for c in at.caption)
    assert len([n for n in at.main if isinstance(n, UnknownElement)]) >= 1

def test_compare_blend_explorer_honest_when_no_hop_has_survivable_data(toy_cwd):
    # hopb (moly)/hopc (alpha/beta/co-humulone/total_oil) : NI l'un ni
    # l'autre n'a un des 4 composés survivables -- message honnête plutôt
    # qu'un graphique vide, et les deux listés comme manquants.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("compare").run()
    at.multiselect[0].select("Hopb").select("Hopc").run()
    assert not at.exception
    assert any(s.value.startswith("Blend Explorer") for s in at.subheader)
    assert any("None of the selected hops has any of these 4 compounds measured" in m.value
              for m in at.markdown)
    caption = next(c.value for c in at.caption if "No survivable-compound data for" in c.value)
    assert "Hopb" in caption and "Hopc" in caption

def test_chemical_earliness_index_all_averages_quantile_rank_per_compound():
    # T99, couche chimique : moyenne du rang quantile PAR COMPOSÉ sur toute
    # la base (réutilise _normalize_quantile, jamais une normalisation
    # ad hoc réécrite pour l'occasion).
    comp = {
        "hopx": {"linalool": {"mid": 10.0, "unit": "pct_oil"},
                "geraniol": {"mid": 1.0, "unit": "pct_oil"}},
        "hopy": {"linalool": {"mid": 2.0, "unit": "pct_oil"}},
        "hopz": {},
    }
    hops = {"hopx": {}, "hopy": {}, "hopz": {}}
    out = app._chemical_earliness_index_all(hops, comp)
    # hopz n'a aucun des 4 composés -> absent, jamais un indice fabriqué.
    assert set(out) == {"hopx", "hopy"}
    assert out["hopx"]["compounds"] == ["linalool", "geraniol"]
    # linalool : hopx (10.0) > hopy (2.0) dans la base [10.0, 2.0] -> rang
    # (bisect_left=1 + bisect_right=2)/(2*2) = 0.75 pour hopx.
    # geraniol : SEUL connu (hopx) -> cas dégénéré n=1 -> 1.0.
    assert out["hopx"]["index"] == pytest.approx((0.75 + 1.0) / 2)
    assert out["hopy"]["compounds"] == ["linalool"]
    assert out["hopy"]["index"] == pytest.approx(0.25)

def test_usage_share_db_values_collects_one_stage_across_varieties():
    usage_all = {
        "hopx": {"Aroma": {"share": 0.6, "recipes_count": 60},
                "Boil": {"share": 0.4, "recipes_count": 40}},
        "hopy": {"Boil": {"share": 1.0, "recipes_count": 10}},
    }
    assert app._usage_share_db_values(usage_all, "Aroma") == [0.6]
    assert sorted(app._usage_share_db_values(usage_all, "Boil")) == [0.4, 1.0]

def test_survivable_compound_positions_all_matches_chemical_index_inputs():
    # T117 : même socle que _chemical_earliness_index_all (T99), vérifié
    # avec les mêmes chiffres que test_chemical_earliness_index_all_
    # averages_quantile_rank_per_compound (0.75/1.0/0.25) pour garantir que
    # le refactor n'a rien changé au calcul par composé.
    comp = {
        "hopx": {"linalool": {"mid": 10.0, "unit": "pct_oil"},
                "geraniol": {"mid": 1.0, "unit": "pct_oil"}},
        "hopy": {"linalool": {"mid": 2.0, "unit": "pct_oil"}},
        "hopz": {},
    }
    hops = {"hopx": {}, "hopy": {}, "hopz": {}}
    out = app._survivable_compound_positions_all(hops, comp)
    assert set(out) == {"hopx", "hopy"}
    assert out["hopx"] == {"linalool": pytest.approx(0.75), "geraniol": pytest.approx(1.0)}
    assert out["hopy"] == {"linalool": pytest.approx(0.25)}

def test_survivable_buckets_uses_terciles_among_covered_hops():
    totals = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0, "e": 5.0, "f": 6.0}
    out = app._survivable_buckets(totals)
    assert out["a"] == "Low" and out["b"] == "Low"
    assert out["c"] == "Medium" and out["d"] == "Medium"
    assert out["e"] == "High" and out["f"] == "High"

def test_survivable_buckets_degenerate_below_three_all_high():
    # terciles n'ont pas de sens sous 3 valeurs -- tout le monde "High"
    # plutôt qu'un tercile fabriqué sur trop peu de données.
    assert app._survivable_buckets({"a": 1.0, "b": 2.0}) == {"a": "High", "b": "High"}

def test_normalize_minmax_floors_the_true_database_minimum():
    # 2026-08-26, bug utilisateur : "if I enter Columbus and Nugget, without
    # normalization Columbus has a Thiol data, but with normalization we lose
    # it" -- Columbus porte le thiol MINIMUM connu de toute la base,
    # `_normalize_minmax` renvoyait donc exactement 0.0, et
    # `_compare_detail_barplot` rend une barre `Value == 0` invisible (`x2`
    # implicite à 0 en mode linéaire, largeur nulle). Le plancher
    # `_COMPARE_MIN_NORMALIZED_POSITION` garde la barre visible.
    db_values = [0.7, 5.15, 32.6]
    assert app._normalize_minmax(0.7, db_values) == app._COMPARE_MIN_NORMALIZED_POSITION

def test_normalize_quantile_floors_a_near_zero_rank():
    # Même plancher que `_normalize_minmax` -- un rang quantile proche de 0
    # (mais jamais exactement 0 par construction, contrairement à min-max)
    # sur une base à forte cardinalité resterait une barre quasi invisible.
    db_values = list(range(1, 201))
    assert app._normalize_quantile(1, db_values) == app._COMPARE_MIN_NORMALIZED_POSITION

def test_compare_detail_barplot_log_scale_domain_uses_whole_database_range():
    # 2026-08-26, retour utilisateur explicite : "keep the thiol axis to
    # start at 0 even with the normalisations, for some reason you decided to
    # start the axis at the minimal value" -- le domaine log calculé
    # uniquement sur les houblons SÉLECTIONNÉS rétrécissait à une fenêtre
    # minuscule autour de leurs propres valeurs (ex. Columbus seul, thiols
    # 0.7 -> domaine [0.63, 0.7]). `secondary_db_values` (toutes les valeurs
    # connues de ce composé sur toute la base) élargit le domaine à la vraie
    # plage existante, stable quelle que soit la sélection.
    rows = [{"Hop": "Columbus", "Field": "thiols", "Value": 0.7}]
    colors = {"Columbus": "#000"}
    chart = app._compare_detail_barplot(
        rows, [], "Amount", ["thiols"], "Thiols (ug/kg)", colors,
        log_scale=True, secondary_db_values=[0.7, 5.15, 32.6])
    # 2026-08-26 (ticket catégories chimiques) : le chart racine est
    # désormais un `hconcat` (colonnes classe/sous-classe + le barplot
    # détaillé lui-même, en dernier) -- le barplot avec ses couches "bar"
    # reste le DERNIER élément de ce `hconcat`.
    detail = chart.to_dict()["hconcat"][-1]
    bar_layer = next(layer for layer in detail["layer"]
                     if layer.get("mark", {}).get("type") == "bar")
    domain = bar_layer["encoding"]["x"]["scale"]["domain"]
    assert domain[0] == pytest.approx(0.7 * 0.9)
    assert domain[1] == 32.6

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

def test_styles_mode_sorts_categories_numerically_not_lexicographically(toy_cwd):
    # category_id "2" doit précéder "10" (tri numérique explicite du ticket
    # T82) -- un tri lexicographique naïf mettrait "10" avant "2".
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("styles").run()
    assert not at.exception
    options = at.selectbox[0].options  # options = display strings ("id - name"), pas les tuples bruts
    assert options.index("2 - Test Lager") < options.index("10 - Test Wheat")

def test_styles_mode_renders_vital_stats_tags_and_examples_for_complete_style(toy_cwd):
    # Metric (EBC/°Plato) est la valeur par défaut du toggle (demande
    # utilisateur explicite : "By default I would like you to use EBC not
    # SRM") -- OG/FG/SRM s'affichent donc converties, ABV/IBU inchangés.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("styles").run()
    at.selectbox(key="styles_category").set_value(("2", "Test Lager")).run()
    at.selectbox(key="styles_style").set_value(("2A", "Test Lager Style")).run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["ABV"] == "4.5%–6.0%"
    assert metrics["IBU"] == "18–30"
    assert metrics["OG (°P)"] == "11.0–13.8"
    assert metrics["FG (°P)"] == "2.1–3.3"
    assert metrics["EBC"] == "6–12"  # 3.0/6.0 SRM x 1.97, arrondi à l'entier
    assert any("-badge[crisp]" in m.value for m in at.markdown)
    assert any("-badge[Example One]" in m.value for m in at.markdown)
    # "Aroma"/"Flavor" présents dans la fixture -> expanders rendus ;
    # "Appearance"/"Mouthfeel" (None) -> jamais un expander vide.
    expander_labels = {e.label for e in at.expander}
    assert "Aroma" in expander_labels and "Flavor" in expander_labels
    assert "Appearance" not in expander_labels and "Mouthfeel" not in expander_labels

def test_styles_mode_color_and_density_toggles_switch_independently(toy_cwd):
    # Deux toggles SÉPARÉS (2026-08-27, demande utilisateur explicite :
    # "separate the EBC/SRM et Plato/SG. Il peut arriver de vouloir
    # utiliser EBC et Plato en meme temps") -- vérifie qu'on peut bien
    # obtenir une combinaison "mixte" (SRM + °Plato), pas seulement les
    # deux paires assorties Metric/Imperial.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("styles").run()
    at.selectbox(key="styles_category").set_value(("2", "Test Lager")).run()
    at.selectbox(key="styles_style").set_value(("2A", "Test Lager Style")).run()
    at.segmented_control(key="styles_color_units").set_value("SRM").run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["SRM"] == "3.0–6.0"
    assert metrics["OG (°P)"] == "11.0–13.8"  # densité restée en Plato (défaut)
    assert metrics["FG (°P)"] == "2.1–3.3"

def test_styles_mode_density_toggle_shows_sg(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("styles").run()
    at.selectbox(key="styles_category").set_value(("2", "Test Lager")).run()
    at.selectbox(key="styles_style").set_value(("2A", "Test Lager Style")).run()
    at.segmented_control(key="styles_density_units").set_value("SG").run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["OG (SG)"] == "1.044–1.056"
    assert metrics["FG (SG)"] == "1.008–1.013"
    assert metrics["EBC"] == "6–12"  # couleur restée en EBC (défaut)

def test_styles_mode_shows_observed_distribution_legend_when_beer_analytics_covers_style(toy_cwd):
    # T105 : "2A" a des bins style_recipe_stats pour "abv" -- la légende
    # explicite (bande BJCP vs histogramme observé) doit apparaître.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("styles").run()
    at.selectbox(key="styles_category").set_value(("2", "Test Lager")).run()
    at.selectbox(key="styles_style").set_value(("2A", "Test Lager Style")).run()
    assert not at.exception
    assert any("Terracotta band = official BJCP range" in c.value
              and "beer-analytics.com" in c.value for c in at.caption)
    assert any(m.label == "ABV" for m in at.metric)  # metric inchangé, voir test ci-dessus

def test_styles_mode_falls_back_silently_without_observed_data(toy_cwd):
    # "10A" : aucune ligne style_recipe_stats -- pas de légende T105, jamais
    # d'histogramme fabriqué (repli silencieux sur la simple barre BJCP,
    # de toute façon absente ici puisque "10A" n'a aucune vital stat).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("styles").run()
    at.selectbox(key="styles_category").set_value(("10", "Test Wheat")).run()
    at.selectbox(key="styles_style").set_value(("10A", "Test Wheat Style")).run()
    assert not at.exception
    assert not any("official BJCP range" in c.value for c in at.caption)

def test_styles_mode_shows_dash_and_shared_caption_when_no_vital_stats(toy_cwd):
    # "10A" : les 17 styles réels sans vital stats (specialty/fruit/...)
    # doivent afficher "—", jamais une barre vide qui ferait croire à zéro.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("styles").run()
    at.selectbox(key="styles_category").set_value(("10", "Test Wheat")).run()
    at.selectbox(key="styles_style").set_value(("10A", "Test Wheat Style")).run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert all(metrics[label] == "—"
              for label in ("ABV", "IBU", "OG (°P)", "FG (°P)", "EBC"))
    assert any("inherits" in c.value.lower() for c in at.caption)

def test_style_hops_highlights_relevant_hop_absent_from_real_usage(toy_cwd):
    # T103 : "2A" -- descripteurs pré-remplis ("citrus"/"floral", trouvés
    # littéralement dans le texte "aroma" de la fixture) recoupent hopa
    # (citrus) ET hopb (floral). Seul hopa a une ligne style_hop_usage/"any"
    # -- hopb doit ressortir dans la section "aromatically relevant, rarely
    # used", jamais hopa (qui a une vraie fréquence mesurée).
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("style-hops").run()
    at.selectbox(key="style_hops_category").set_value(("2", "Test Lager")).run()
    at.selectbox(key="style_hops_style").set_value(("2A", "Test Lager Style")).run()
    assert not at.exception
    prefill = at.multiselect(key="style_hops_descriptors_2A")
    assert set(prefill.value) == {"citrus", "floral"}
    assert any("rarely used in this style" in s.value for s in at.subheader)
    dataframes = [df.value for df in at.dataframe]
    rare_df = next(df for df in dataframes if "Matched descriptors" in df.columns
                   and "Recipe share" not in df.columns and len(df) == 1)
    assert rare_df["Hop"].tolist() == ["Hopb"]
    freq_df = next(df for df in dataframes if "Recipe share" in df.columns)
    assert freq_df["Hop"].tolist() == ["Hopa"]
    assert freq_df["Recipe share"].tolist() == [0.35]

def test_style_hops_falls_back_silently_without_typical_descriptors(toy_cwd):
    # "10A" : aroma/flavor/ingredients tous None dans la fixture ->
    # `style_typical_descriptors` renvoie [] -> message explicite plutôt
    # qu'un classement vide ou une exception.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("style-hops").run()
    at.selectbox(key="style_hops_category").set_value(("10", "Test Wheat")).run()
    at.selectbox(key="style_hops_style").set_value(("10A", "Test Wheat Style")).run()
    assert not at.exception
    assert at.multiselect(key="style_hops_descriptors_10A").value == []
    assert any("Choose at least one typical descriptor" in m.value for m in at.markdown)
    assert not any("rarely used in this style" in s.value for s in at.subheader)

def test_survivables_mode_shows_per_compound_coverage_and_only_covered_hops(toy_cwd):
    # T117 : hopa (linalool=30, ajouté pour T99) est le SEUL houblon jouet
    # avec un des 4 composés survivables -- 1/5 houblons couverts, le
    # reste (hopb/hopc/twina/twinb) jamais compté comme 0.
    from streamlit.testing.v1.element_tree import UnknownElement
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("survivables").run()
    assert not at.exception
    assert any("1 of 5 hops" in c.value for c in at.caption)
    assert any("Linalool 1/5" in c.value and "Geraniol 0/5" in c.value
              for c in at.caption)
    # un seul houblon couvert -> cas dégénéré (< 3 valeurs), tercile
    # impossible -> "High" par défaut (voir _survivable_buckets).
    assert at.pills(key="survivables_bucket_filter").value == ["High", "Medium", "Low"]
    assert len([n for n in at.main if isinstance(n, UnknownElement)]) >= 1

def test_survivables_mode_shows_ych_rules_infobox(toy_cwd):
    # 2026-08-29, retour utilisateur en revue : les 4 règles YCH citées
    # comme contexte, jamais appliquées automatiquement au calcul.
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("survivables").run()
    assert not at.exception
    assert any("YCH handbook rules" in m.value for m in at.markdown)
    assert any("biotransformation" in m.value for m in at.markdown)

def test_survivables_mode_filters_by_bucket(toy_cwd):
    at = _app()
    at.run()
    at.sidebar.radio[0].set_value("survivables").run()
    at.pills(key="survivables_bucket_filter").set_value(["Low"]).run()
    assert not at.exception
    # hopa (seul houblon couvert) est en "High" (cas dégénéré) -> absent du
    # filtre "Low" seul seulement -- message honnête, pas un graphique vide.
    assert any("No hop in the selected bucket" in m.value for m in at.markdown)
