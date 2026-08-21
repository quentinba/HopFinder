"""
GUI Streamlit : les modes du CLI (amplify/contrast/by-descriptor) +
un mode "browse" propre à la GUI pour parcourir la base brute (houblon par
houblon), en lecture seule contre une base déjà construite. Ne touche pas à
l'ingestion (crawl/build/ingest-*) : ça reste le rôle du CLI (`hopmatch
build`, `hopmatch crawl-barthhaas`...). N'importe que `matching`/`schema`,
jamais `ingest`.

Texte utilisateur (labels/captions/warnings) en ANGLAIS depuis 2026-08-19
(décision utilisateur explicite, scope confirmé : GUI uniquement — CLI et
commentaires/docstrings restent en français, cf. CLAUDE.md). Avant cette
date, toute la GUI était en français.

Lancer : streamlit run src/hopmatch/app.py [-- --db chemin/vers/aromahops.db]
"""
from __future__ import annotations
import base64
import io
import math
import os
import sys
from datetime import datetime

import altair as alt
import streamlit as st
from PIL import Image

from hopmatch import matching
from hopmatch.schema import connect

DEFAULT_DB = "aromahops.db"

# Image de fond (demande utilisateur, 2026-08-19) : gravure houblon fournie
# par l'utilisateur, stockée hors de src/ (assets/, à la racine du dépôt) --
# chemin résolu depuis __file__ pour rester correct quel que soit le cwd
# d'où `streamlit run` est lancé.
# `background_zoomed.png` (pas `background.png`) : demande utilisateur
# explicite -- un crop déjà cadré par l'utilisateur, affiché FIXE (attaché au
# viewport, jamais recalculé par `cover` contre une hauteur de page qui
# change), pour ne plus jamais changer de niveau de zoom d'une interaction à
# l'autre (signalé : "each time you change something it change the image
# zoom" avec l'ancienne image + `background-attachment: local`, qui
# recalcule `cover` contre la hauteur RÉELLE, donc VARIABLE, du contenu).
_BACKGROUND_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "background_zoomed.png")

# Libellés GUI affichés à l'utilisateur, distincts des clés internes ("mode")
# qui pilotent le dispatch et restent stables (CLI/tests/URLs internes non
# concernés — habillage d'affichage uniquement, demandé par l'utilisateur).
MODE_LABELS = {
    "home": "Home",
    "amplify": "HopFinder - Amplify",
    "contrast": "HopFinder - Contrast",
    "by-descriptor": "HopFinder from Descriptors",
    "browse": "Browse hop informations",
    "compare": "Compare Hops",
}

# Page d'accueil (front page) : résumé des outils, avec accès direct à chacun.
_TOOL_SUMMARIES = [
    {
        "mode": "amplify",
        "icon": ":material/trending_up:",
        "tagline": "Extend an addition",
        "description": (
            "The addition (yuzu, basil...) is already in the beer — find a hop "
            "that **extends** its character. Combines molecular similarity "
            "(TF-IDF — weighs each shared molecule by how distinctive it is "
            "across hops, so a rare compound counts more than one present in "
            "almost every hop like myrcene) with aroma-wheel overlap (only "
            "active if you manually add descriptors matching your addition "
            "below, e.g. \"citrus\", \"berry\" for strawberry — this turns on a "
            "second, independent scoring layer). Also proposes blends of 1 to "
            "5 hops actually used together in recipes (BeerMaverick)."
        ),
    },
    {
        "mode": "contrast",
        "icon": ":material/contrast:",
        "tagline": "Pair by contrast",
        "description": (
            "Looks for a hop with a **complementary** profile (bright citrus "
            "under a dank/resinous hop), not a similar one. Uses a "
            "hand-curated affinity dictionary (e.g. citrus → resinous/woody/"
            "herbal) that maps each descriptor of your addition to its "
            "complementary counterparts — a culinary-pairing heuristic, not "
            "sourced data, and never molecular. Same multi-size blends as "
            "Amplify, prioritizing real recipe pairing frequency."
        ),
    },
    {
        "mode": "by-descriptor",
        "icon": ":material/search:",
        "tagline": "Discovery by descriptors",
        "description": (
            "Pick descriptors directly (citrus, tropical, dank...) and see "
            "which hops best match the real aroma wheel (BarthHaas/Yakima/"
            "BeerMaverick)."
        ),
    },
    {
        "mode": "browse",
        "icon": ":material/database:",
        "tagline": "Explore a hop",
        "description": (
            "Look up a hop directly: measured composition, descriptors, "
            "quantitative aroma wheel (Yakima), purpose (aromatic/bittering), "
            "similar varieties and real recipe pairings (BeerMaverick)."
        ),
    },
    {
        "mode": "compare",
        "icon": ":material/compare_arrows:",
        "tagline": "Side by side",
        "description": (
            "Pick up to 5 hops and compare them directly: an overlaid aroma-"
            "wheel radar (Yakima, where available), and two bar charts — "
            "alpha/beta acids, co-humulone and total oil, then the detailed "
            "oil compounds — each colored consistently per hop."
        ),
    },
]

# "Recent updates" en bas de la page d'accueil (2026-08-21, demande
# utilisateur explicite : "add ... a summary of last implemented features
# from the most recent to the oldest ... rely on github commit for that").
# Le plus récent en tête ; chaque résumé écrit à partir de l'HISTORIQUE GIT
# RÉEL (`git log`, voir CLAUDE.md pour le détail complet de chaque ticket
# T-numéroté cité) -- PAS une traduction automatique des messages de commit
# à l'exécution : ceux-ci sont en français (convention CLI/commit, voir
# Conventions dans CLAUDE.md), incompatible avec le texte GUI qui doit rester
# en anglais, et une traduction automatique en direct ne serait pas fiable.
# Curée à la main, comme le journal CLAUDE.md, mise à jour manuellement à
# chaque nouvelle fonctionnalité livrée (pas régénérée dynamiquement) --
# un `git log` en direct exigerait aussi que `.git` soit présent dans le
# conteneur déployé, ce qui n'est pas garanti.
_RECENT_UPDATES = [
    ("2026-08-21", "Compound odor descriptors cross-checked against Scott "
                   "Janish's The New IPA flavor-category table; missing "
                   "categories added and clearly cited — e.g. thiols now "
                   "shows \"berry & currant\", previously blank."),
    ("2026-08-21", "Flavornet odor descriptors ('Smells like') now also shown "
                   "in the compound tables on Browse, and in the per-hop "
                   "details under Amplify/Contrast/HopFinder from Descriptors "
                   "— not just the Compare Hops chart."),
    ("2026-08-21", "Compare Hops: hover a compound (or its bar) in the "
                   "detailed composition chart for its Flavornet odor "
                   "descriptors — e.g. myrcene doesn't automatically mean "
                   "\"green\", see what it actually smells like."),
    ("2026-08-21", "Compare Hops: toggle to show the detailed composition "
                   "barplot as an absolute amount (ml/100g) instead of % of "
                   "oil, so two hops can't silently swap rank just because "
                   "their total oil differs."),
    ("2026-08-21", "Browse: new \"Similar hops\" section ranks hops by molecular "
                   "composition and/or quantitative aroma wheel intensity, with "
                   "each layer independently toggleable."),
    ("2026-08-20", "Amplify/Contrast/blend result tables render as real "
                   "scrollable tables instead of stacking vertically on mobile."),
    ("2026-08-20", "Tool inputs (note selector, sliders) moved from the sidebar "
                   "to the main page — the sidebar is collapsed by default on "
                   "mobile."),
    ("2026-08-20", "Deployed on Streamlit Community Cloud."),
    ("2026-08-19", "New \"Compare Hops\" tool: overlaid aroma-wheel radar and "
                   "composition bar charts for up to 5 hops side by side."),
    ("2026-08-19", "Purpose (aromatic/bittering) shown for every hop, inferred "
                   "from alpha acid when not directly known from BeerMaverick."),
    ("2026-08-19", "Contrast: the complementary target descriptors and purpose "
                   "filter are now user-editable, not just auto-computed."),
    ("2026-08-19", "GUI translated to English; hop engraving background image "
                   "added."),
    ("2026-08-18", "Multi-size blend suggestions (1 to 5 hops) for Amplify and "
                   "Contrast, prioritizing real recipe pairing frequency "
                   "(BeerMaverick)."),
    ("2026-08-18", "Descriptor vocabulary expanded from 38 to 104 terms via "
                   "BeerMaverick tags."),
]


def _home(con) -> None:
    stats = _stats(con)
    st.write(f"{stats['hops']} hops, {stats['notes']} notes, "
            f"{stats['descriptors']} descriptors available. Choose a tool:")
    cols = st.columns(2)
    for i, tool in enumerate(_TOOL_SUMMARIES):
        with cols[i % 2].container(border=True):
            st.subheader(f"{tool['icon']} {MODE_LABELS[tool['mode']]}")
            st.caption(tool["tagline"])
            st.write(tool["description"])
            if st.button("Open", key=f"home_open_{tool['mode']}",
                        icon=":material/arrow_forward:"):
                # Streamlit interdit de modifier st.session_state["mode"] une
                # fois le widget radio (key="mode") déjà instancié dans CE run
                # -- clé de relais consommée en tout début de main(), avant la
                # création du radio, sur le run suivant.
                st.session_state["_next_mode"] = tool["mode"]
                st.rerun()

    st.divider()
    st.subheader("Recent updates")
    st.caption("Most recent first.")
    st.markdown("\n\n".join(f"**{date}** — {summary}"
                            for date, summary in _RECENT_UPDATES))


def _db_path() -> str:
    if "--db" in sys.argv:
        return sys.argv[sys.argv.index("--db") + 1]
    return DEFAULT_DB


# Bootstrap de la base sur un déploiement distant (Streamlit Community Cloud,
# 2026-08-20, demande utilisateur) : le système de fichiers d'un conteneur
# Community Cloud est éphémère -- reconstruit à chaque réveil après mise en
# veille -- donc `aromahops.db` n'existe jamais localement au premier lancement
# d'une session. Reconstruire la base en direct sur ce réveil (crawl BarthHaas/
# Yakima/BeerMaverick + dump FooDB ~950 Mo) est exclu : trop lent pour un
# réveil utilisateur (minutes, pas secondes), et un scraping systématique
# répété depuis une IP cloud partagée risque un blocage/rate-limit côté
# sources. À la place, la base est construite UNE FOIS en local (`hopmatch
# build`/`crawl-*`/`ingest-*`, inchangé) puis hébergée à part, dans un dépôt
# GitHub PRIVÉ (pas le dépôt de code, public) -- ce module ne fait que la
# télécharger si elle est absente, via l'API Contents de GitHub (accepte un
# jeton en repli sur `raw.githubusercontent.com`, qui ne sert pas les dépôts
# privés). Secrets lus depuis `st.secrets` (jamais commités, configurés dans
# le tableau de bord Streamlit Cloud) -- absents en développement local sans
# `.streamlit/secrets.toml`, où `st.secrets` lève une exception plutôt que de
# se comporter comme un dict vide (vérifié en direct) : capturé largement,
# ce n'est pas une erreur, juste "pas de source distante configurée ici".
_DB_SOURCE_URL_SECRET = "DB_DOWNLOAD_URL"
_DB_SOURCE_TOKEN_SECRET = "DB_DOWNLOAD_TOKEN"


@st.cache_resource
def _fetch_remote_db(db_path: str) -> bool:
    """Télécharge `aromahops.db` depuis la source distante configurée
    (`st.secrets`) si elle existe et que le fichier est absent localement.
    `@st.cache_resource` (pas juste le test `os.path.exists` fait par
    l'appelant) : plusieurs sessions utilisateur peuvent atteindre `main()`
    en parallèle sur le même conteneur fraîchement réveillé, avant que le
    premier téléchargement ait fini d'écrire le fichier -- le cache partagé
    de `st.cache_resource` garantit un seul téléchargement réel, les autres
    sessions attendent son résultat plutôt que de déclencher chacune leur
    propre écriture concurrente. Retourne `True` si la base est présente
    après cet appel (déjà là, ou téléchargée avec succès), `False` sinon
    (rien de configuré, ou échec réseau -- jamais d'exception qui casserait
    le rendu de la page)."""
    if os.path.exists(db_path):
        return True
    try:
        url = st.secrets.get(_DB_SOURCE_URL_SECRET)
        token = st.secrets.get(_DB_SOURCE_TOKEN_SECRET)
    except Exception:
        # Pas de secrets.toml du tout (dev local) -- `st.secrets.get(...)`
        # lève dans ce cas précis au lieu de renvoyer None, vérifié en
        # direct (`StreamlitSecretNotFoundError`, sous-classe d'OSError).
        return False
    if not url or not token:
        return False
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3.raw",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        st.error(f"Failed to download the database from the configured source: {e}")
        return False
    with open(db_path, "wb") as f:
        f.write(data)
    return True


def _connection(db_path: str):
    # Pas de @st.cache_resource : sqlite3 refuse d'utiliser une connexion hors
    # de son thread d'origine, or Streamlit peut réexécuter le script dans un
    # thread différent d'une interaction à l'autre. Ouvrir une connexion par
    # exécution est le choix sûr — coût négligible pour SQLite local.
    return connect(db_path)


def _db_version(db_path: str) -> float:
    """mtime du fichier — clé de cache pour `_notes`/`_descriptors`/`_stats` :
    invalide le cache exactement quand la base a été reconstruite (CLI, dans
    un autre terminal pendant que la GUI tourne), ni plus tôt (pas de TTL
    arbitraire qui resservirait des données périmées) ni plus tard."""
    return os.path.getmtime(db_path)


@st.cache_data
def _cached_notes(_con, db_path: str, _version: float) -> list[str]:
    # `_con`/underscore : Streamlit ne hache pas les paramètres préfixés `_`
    # (une connexion sqlite3 n'est de toute façon pas hachable) ; `db_path`
    # + `_version` (mtime, voir _db_version) sont les vraies clés de cache.
    return sorted(r[0] for r in _con.execute("SELECT DISTINCT note FROM aroma_notes"))


@st.cache_data
def _cached_descriptors(_con, db_path: str, _version: float) -> list[str]:
    return sorted(r[0] for r in _con.execute("SELECT DISTINCT descriptor FROM hop_descriptors"))


@st.cache_data
def _cached_intensity_vocabulary(_con, db_path: str, _version: float) -> list[str]:
    return sorted(r[0] for r in _con.execute("SELECT DISTINCT descriptor FROM hop_aroma_intensity"))


@st.cache_data
def _cached_stats(_con, db_path: str, _version: float) -> dict:
    return {
        "hops": _con.execute("SELECT COUNT(*) FROM hops").fetchone()[0],
        "notes": _con.execute("SELECT COUNT(DISTINCT note) FROM aroma_notes").fetchone()[0],
        "descriptors": _con.execute(
            "SELECT COUNT(DISTINCT descriptor) FROM hop_descriptors").fetchone()[0],
    }


def _notes(con) -> list[str]:
    db_path = _db_path()
    return _cached_notes(con, db_path, _db_version(db_path))


def _descriptors(con) -> list[str]:
    db_path = _db_path()
    return _cached_descriptors(con, db_path, _db_version(db_path))


def _intensity_vocabulary(con) -> list[str]:
    db_path = _db_path()
    return _cached_intensity_vocabulary(con, db_path, _db_version(db_path))


def _stats(con) -> dict:
    db_path = _db_path()
    return _cached_stats(con, db_path, _db_version(db_path))


@st.cache_data
def _background_data_uri(path: str, _version: float, invert: bool) -> str | None:
    """Convertit l'image de fond en data URI base64 (JPEG), mise en cache
    par (mtime, invert) (même schéma que `_cached_stats`/etc.). Recompressé
    en JPEG qualité 82 : le PNG fourni (~3.1 Mo, texture papier + hachures
    fines qui compressent mal en PNG) tombe à ~360 Ko une fois réencodé,
    négligeable une fois inliné en base64 dans le HTML d'une app locale.
    None si le fichier est absent (image optionnelle, pas d'erreur bloquante
    si `assets/background.png` n'existe pas).

    `invert` (2026-08-19, signalé par l'utilisateur : l'image ne convenait
    qu'au thème clair, un simple voile sombre par-dessus ne suffisait pas en
    thème sombre) : négatif couleur (`ImageOps.invert`) plutôt qu'un
    deuxième fichier statique à maintenir -- l'illustration fournie est un
    dessin au trait noir sur fond crème, son négatif exact est un fond
    quasi-noir avec un trait clair, ce qui donne un résultat propre pour le
    thème sombre (vérifié visuellement, pas de dominante de teinte
    parasite malgré la teinte sépia d'origine)."""
    if not os.path.exists(path):
        return None
    im = Image.open(path).convert("RGB")
    if invert:
        from PIL import ImageOps
        im = ImageOps.invert(im)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=82, optimize=True)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


_BACKGROUND_SCRIPT_TEMPLATE = """
<script>
(function() {
    var doc = window.parent.document;
    var lightVeil = "__LIGHT_VEIL__";
    var darkVeil = "__DARK_VEIL__";
    var normalUri = "__NORMAL_URI__";
    var invertedUri = "__INVERTED_URI__";

    function apply() {
        var stApp = doc.querySelector(".stApp");
        var target = doc.querySelector('[data-testid="stAppViewContainer"]');
        if (!stApp || !target) return;
        var dark = getComputedStyle(stApp).colorScheme === "dark";
        var veil = dark ? darkVeil : lightVeil;
        var uri = dark ? invertedUri : normalUri;
        target.style.backgroundImage =
            'linear-gradient(' + veil + ', ' + veil + '), url("' + uri + '")';
        target.style.backgroundSize = "cover";
        target.style.backgroundPosition = "center center";
        target.style.backgroundAttachment = "fixed";
        target.style.backgroundRepeat = "no-repeat";
    }

    apply();
    var stApp = doc.querySelector(".stApp");
    if (stApp) {
        new MutationObserver(apply).observe(stApp, {attributes: true, attributeFilter: ["class"]});
    }
    window.parent.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", apply);
})();
</script>
"""


def _inject_background() -> None:
    """Image de fond derrière le contenu principal (demande utilisateur).

    **Troisième passage (2026-08-19) : les deux correctifs précédents ne
    marchaient toujours pas, signalé par l'utilisateur ("changing theme
    doesn't change the image used"). Root cause enfin identifiée pour de bon,
    en inspectant le DOM/CSS réel en direct plutôt qu'en supposant :**

    Le passage précédent utilisait `@media (prefers-color-scheme: dark)` en
    CSS pur -- ça suit la préférence OS, PAS le sélecteur Light/Dark/System
    du menu Streamlit. Or `st.context.theme.type` (tenté avant ça, tout
    premier passage) ne se synchronise qu'après plusieurs reruns réels (le
    sélecteur est un état 100% côté client, aucun rerun immédiat). AUCUNE
    des deux méthodes ne suit donc le sélecteur Streamlit de façon fiable et
    instantanée.

    Trouvé en inspectant le DOM en direct (`getComputedStyle`) : l'élément
    `.stApp` a une propriété CSS `color-scheme` calculée qui, elle,
    se met à jour INSTANTANÉMENT quand on choisit Light/Dark/System dans le
    menu Streamlit (vérifié : "dark" -> clic "Light" -> "light", sans AUCUN
    rerun Python entretemps) -- Streamlit la pilote par une classe
    Emotion générée dynamiquement (nom non stable d'une session à l'autre,
    donc pas utilisable comme sélecteur CSS direct), mais la propriété
    CSS *calculée* qui en résulte, elle, est stable et lisible.

    `color-scheme` n'est cependant utilisable qu'en valeur `<color>` (via
    `light-dark()`), pas pour choisir entre deux `background-image`/`url()`
    entières -- aucune solution CSS pure ne permet ce choix. Solution
    retenue : `st.iframe` (PAS `st.markdown` -- un `<script>` injecté via
    `st.markdown(unsafe_allow_html=True)` NE S'EXÉCUTE JAMAIS, vérifié en
    direct) avec une chaîne HTML brute, qui exécute du JS avec accès
    same-origin à la page parente (documenté : "HTML strings... are
    embedded as-is in an iframe that allows JavaScript execution and
    same-origin access to the Streamlit app"). Le script lit `color-scheme`
    sur `.stApp` DANS LE PARENT (`window.parent.document`), applique le
    fond directement en JS (pas de CSS injecté séparément), et observe les
    changements de `class` sur `.stApp` (`MutationObserver`) -- c'est ce
    changement de classe Emotion qui accompagne chaque bascule de thème,
    réagit donc instantanément à CHAQUE bascule (System/Light/Dark), sans
    dépendre d'un rerun Python. Écoute aussi le changement OS
    (`matchMedia(...).addEventListener`) pour le cas "System" + OS qui
    change en cours de session. Iframe rendue à hauteur quasi nulle (pas de
    contenu visible voulu, juste le script).

    Fond scindé en deux variantes (normale/négatif, voir
    `_background_data_uri`) choisies par le script selon `dark`, jamais par
    médiaquery CSS ni par `st.context.theme.type` désormais.

    **Quatrième passage (2026-08-19, même jour) : l'utilisateur a signalé que
    le niveau de zoom de l'image changeait à chaque interaction.** Cause :
    `background-attachment: local` sur `stMain` (le passage précédent) fait
    recalculer `background-size: cover` contre le `scrollHeight` RÉEL de
    `stMain`, qui change à chaque page/résultat affiché -- l'image "respire"
    visiblement d'une interaction à l'autre, jamais un vrai zoom figé.
    Corrigé en repassant `background-attachment: fixed` (ancré au VIEWPORT,
    constant tant que la fenêtre n'est pas redimensionnée) sur
    `[data-testid="stAppViewContainer"]` -- PAS `stMain` : `fixed` sur un
    élément qui défile lui-même (`overflow-y: auto`) a un rendu
    cross-browser incohérent (le fond peut soit rester figé soit défiler
    selon le moteur) ; `stAppViewContainer`, qui fait toujours exactement la
    hauteur du viewport et ne défile jamais lui-même (voir passage
    précédent), est la cible correcte pour un fond réellement figé.
    Utilise désormais `background_zoomed.png` (pas `background.png`) --
    demande utilisateur explicite : un crop déjà recadré par l'utilisateur,
    affiché tel quel (`background-position: center center`) plutôt que
    recadré côté CSS (`right top` n'a plus de sens ici, cible déjà cadrée en
    amont)."""
    if not os.path.exists(_BACKGROUND_PATH):
        return
    version = os.path.getmtime(_BACKGROUND_PATH)
    normal_uri = _background_data_uri(_BACKGROUND_PATH, version, invert=False)
    inverted_uri = _background_data_uri(_BACKGROUND_PATH, version, invert=True)
    if normal_uri is None or inverted_uri is None:
        return
    html = (
        _BACKGROUND_SCRIPT_TEMPLATE
        .replace("__LIGHT_VEIL__", "rgba(255,255,255,0.86)")
        .replace("__DARK_VEIL__", "rgba(14,17,23,0.72)")
        .replace("__NORMAL_URI__", normal_uri)
        .replace("__INVERTED_URI__", inverted_uri)
    )
    st.iframe(html, height=1)


# purpose (aromatic/bittering/both) : SEULE donnée BeerMaverick classant un
# houblon par usage (voir CLAUDE.md, section BeerMaverick) — demande
# utilisateur explicite (2026-08-19) : affichée comme info PRINCIPALE en
# Browse, et en colonne colorée sur les résultats amplify/contrast/blends.
# Couleurs `st.badge` (tokens sémantiques Streamlit, PAS des hex littéraux) :
# seule façon vérifiée de s'adapter au thème clair/sombre à la fois — un
# `pandas.Styler`/CSS littéral ne le ferait pas (couleur figée, ne s'inverse
# pas avec le thème).
_PURPOSE_LABELS = {"aromatic": "Aromatic", "bittering": "Bittering", "both": "Aromatic + Bittering"}
_PURPOSE_COLORS = {"aromatic": "green", "bittering": "orange", "both": "violet"}
_PURPOSE_ICONS = {"aromatic": ":material/local_florist:", "bittering": ":material/local_bar:",
                  "both": ":material/join_full:"}


def _purpose_label(purpose: str | None, inferred: bool = False) -> str:
    """Libellé texte du purpose -- factorisé hors de `_purpose_badge`
    (2026-08-20) pour être partagé avec `_render_hop_rows`, qui n'a plus de
    rendu par cellule coloré (voir son commentaire)."""
    if purpose is None:
        return "Unknown"
    label = _PURPOSE_LABELS.get(purpose, purpose)
    if inferred:
        # demande utilisateur explicite (2026-08-19) : "instead of unknown
        # for the purpose, use infered:aromatic and infered:bittering" --
        # voir matching.resolve_purpose. Même couleur/icône que le purpose
        # RÉEL (BeerMaverick) : le préfixe "Inferred:" suffit à distinguer
        # une estimation (78% d'accord avec BeerMaverick, voir
        # matching.ALPHA_ACID_BITTERING_THRESHOLD_PCT) d'une donnée mesurée,
        # sans avoir besoin d'une palette de couleurs séparée.
        return f"Inferred: {label}"
    return label


def _purpose_badge(purpose: str | None, inferred: bool = False) -> None:
    if purpose is None:
        st.badge("Unknown", color="gray", icon=":material/help:")
        return
    label = _purpose_label(purpose, inferred)
    st.badge(label, color=_PURPOSE_COLORS.get(purpose, "gray"), icon=_PURPOSE_ICONS.get(purpose))


def _row_with_purpose(entry: dict, hops: dict, comp: dict) -> dict:
    """Résout le purpose EFFECTIF (réel BeerMaverick, ou inféré depuis
    l'acide alpha -- voir `matching.resolve_purpose`) pour une ligne de
    résultat/blend, sans jamais toucher au `purpose` "brut" stocké côté
    `hops`/scoring (utilisé lui pour la structure des blends, jamais pour
    l'affichage inféré). `entry` doit porter "variety" et "purpose" (brut,
    potentiellement None)."""
    v = entry["variety"]
    purpose, inferred = matching.resolve_purpose(entry.get("purpose"), comp.get(v, {}))
    return dict(entry, purpose=purpose, purpose_inferred=inferred)


def _render_hop_rows(rows: list[dict], columns: list[tuple[str, str]]) -> None:
    """Rendu en vrai tableau (`st.dataframe`) -- PAS `st.columns` par ligne
    comme avant (2026-08-20, signalé par l'utilisateur sur téléphone : "the
    table result of amplify and contrast does not render as table on mobile
    phone"). Root cause vérifiée : Streamlit empile automatiquement
    `st.columns` à la verticale sous une certaine largeur d'écran
    (comportement responsive natif de Streamlit, pas un bug de cette app) --
    chaque "ligne" de houblon redescendait alors en une pile de lignes
    séparées (nom, puis score sur sa propre ligne, puis purpose...), plus du
    tout un tableau une fois la sidebar/le contenu compressés sur mobile.
    `st.dataframe` reste un vrai tableau HTML sur toutes les tailles d'écran
    (défilement horizontal au lieu d'empilement vertical).

    Contrepartie acceptée par l'utilisateur : la colonne Purpose perd son
    `st.badge` coloré (un tableau ne peut pas rendre un widget arbitraire
    par cellule, seulement du texte/nombre) au profit d'un texte simple
    ("Aromatic"/"Inferred: Bittering"/...) via `_purpose_label` -- partagé
    avec `_purpose_badge`, qui reste inchangé et utilisé partout ailleurs
    (Browse, expanders de détail amplify/contrast/by-descriptor) : ces
    emplacements affichent un SEUL purpose à la fois, pas un tableau, donc
    le problème d'empilement mobile ne s'y pose pas.

    Réutilisé par les tableaux de résultats amplify/contrast ET les tableaux
    de blend. `rows` : dicts avec une clé "name" + les clés référencées par
    `columns` ([(en-tête, clé)]) ; une colonne dont la clé est "purpose" est
    résolue en texte (utilise aussi "purpose_inferred" si présent, voir
    `_row_with_purpose`)."""
    table_rows = []
    for row in rows:
        entry = {"Hop": row["name"]}
        for header, field in columns:
            if field == "purpose":
                entry[header] = _purpose_label(row.get("purpose"), row.get("purpose_inferred", False))
            else:
                entry[header] = row.get(field, "")
        table_rows.append(entry)
    st.dataframe(table_rows, width="stretch", hide_index=True)


def _render_key_stats(hcomp: dict) -> None:
    """Les 3 stats les plus importantes d'un houblon pour un brasseur --
    Alpha Acids/Beta Acids/Total Oil --, PLUS Co-humulone (% des acides
    alpha) quand disponible, demande utilisateur EXPLICITE (2026-08-19) :
    "il manque un élément principal : les infos les plus importantes de
    yakima". Mises en avant en `st.metric` plutôt que noyées dans le
    tableau de composition générique trié par valeur (qui les exclut
    désormais, voir `matching.NON_AROMA_DISPLAY`) -- ce ne sont pas juste des
    composés d'arôme comme les autres, ce sont les stats qu'un brasseur
    regarde en premier. Ces 3(4) valeurs étaient auparavant absentes de LA
    BASE ELLE-MÊME (pas juste filtrées à l'affichage) : `alpha_acid`/
    `beta_acid` étaient dans `schema.DROP_COMPOUNDS` ("non aromatiques",
    hors du scoring moléculaire) -- retirées de ce filtre au même moment
    (voir CLAUDE.md), elles sont maintenant réellement stockées.
    Co-humulone (`co_h` côté API Algolia YCH) : Yakima UNIQUEMENT, absent du
    HTML BarthHaas (vérifié en direct) -- "—" si non disponible pour cette
    variété, jamais une valeur inventée."""
    alpha = hcomp.get("alpha_acid", {}).get("mid")
    beta = hcomp.get("beta_acid", {}).get("mid")
    co_h = hcomp.get("co_humulone", {}).get("mid")
    oil = hcomp.get("total_oil", {}).get("mid")
    cols = st.columns(4)
    cols[0].metric("Alpha acids", f"{alpha:.1f}%" if alpha is not None else "—")
    cols[1].metric("Beta acids", f"{beta:.1f}%" if beta is not None else "—")
    # unité/qualificatif dans le LABEL (police plus petite, tolère le texte
    # long) plutôt que dans la valeur -- "1.4 ml/100g"/"41% of AA" en valeur
    # débordait et se tronquait en "1.4 ml/1…" (constaté en direct dans le
    # navigateur, largeur de colonne st.metric fixe).
    cols[2].metric("Co-humulone (% of AA)", f"{co_h:.0f}%" if co_h is not None else "—")
    cols[3].metric("Total oil (ml/100g)", f"{oil:.1f}" if oil is not None else "—")


def _all_compound_descriptors(con, comp: dict) -> dict[str, str]:
    """Descripteurs Flavornet par composé (T72, 2026-08-21, demande
    utilisateur explicite : le tooltip "Smells like" ajouté sur le barplot
    Compare Hops (T71) doit AUSSI apparaître dans les tableaux de
    composition texte -- Browse, `_hop_detail_expanders`
    (amplify/contrast), `_by_descriptor` -- pas seulement le barplot).
    Calculé UNE FOIS par rendu de page sur TOUS les composés présents dans
    `comp` (la table compound -> descripteurs ne dépend pas du houblon
    affiché) plutôt qu'une requête par houblon dans chaque boucle
    d'expander. `matching.compound_descriptors` réutilisé tel quel (même
    jointure CID PubChem -> CAS -> `flavornet_compounds`, voir sa
    docstring) -- pas une deuxième implémentation."""
    all_compounds = sorted({c for h in comp.values() for c in h if c not in matching.NON_AROMA_DISPLAY})
    return matching.compound_descriptors(con, all_compounds)


def _hop_detail_expanders(con, hops: dict, comp: dict, hop_desc: dict, rows: list[dict]) -> None:
    """Détail par houblon en expander, sous le tableau de résultats.
    Remplace l'ancien bouton de navigation directe vers Browse hop
    informations (T39) : signalé par l'utilisateur, cliquer dessus faisait
    perdre la page amplify/contrast en cours (résultats + blend), sans moyen
    d'y revenir — remplacé par un détail affiché DANS la page courante, sans
    navigation ni perte d'état, même esprit que la liste d'expanders sous la
    heatmap de `_by_descriptor` (demandé explicitement par l'utilisateur en
    exemple : "similar to the detailed list of hops below the from
    description heatmap"). `rows` : dicts avec "variety"/"name"/"caption"
    (texte affiché dans l'en-tête de l'expander, ex. score/contribution).

    Inclut désormais (2026-08-19, demande utilisateur "include the aroma
    wheel as well, basically the same content than what is on the browse
    page") : purpose, sources, descripteurs, roue d'arôme quantitative
    (identique à `_browse`, via `con` — d'où le nouveau paramètre) et
    composition — même contenu que la page Browse, en sous-section plutôt
    que par navigation.

    Colonne "Smells like" (T72, 2026-08-21) : voir `_all_compound_descriptors`
    -- calculée UNE FOIS ici (pas par houblon dans la boucle)."""
    st.subheader("Hop details")
    compound_smells = _all_compound_descriptors(con, comp)
    for row in rows:
        v = row["variety"]
        with st.expander(f"{row['name']} — {row['caption']}"):
            purpose, inferred = matching.resolve_purpose(hops[v].get("purpose"), comp.get(v, {}))
            _purpose_badge(purpose, inferred)
            st.caption(f"Sources: {hops[v]['sources']}")
            _render_key_stats(comp.get(v, {}))
            descs = sorted(hop_desc.get(v, set()))
            st.write("**Descriptors:** " + (", ".join(descs) if descs else "none recorded"))
            intensity = matching.hop_aroma_intensity(con, v)
            if intensity and any(val > 0 for val in intensity.values()):
                st.altair_chart(_aroma_wheel(intensity, _intensity_vocabulary(con)),
                                width="content", theme=None)
                st.caption(":material/info: Hover a label for its definition "
                          "(Yakima Chief Hop Sensory Ballot).")
            hcomp = comp.get(v, {})
            crows = sorted(
                ({"Compound": c, "Value": round(cv["mid"], 3), "Unit": cv["unit"],
                  "Sources": ", ".join(cv["sources"]),
                  "Smells like": compound_smells.get(c, "—")}
                 for c, cv in hcomp.items()
                 if c not in matching.NON_AROMA_DISPLAY and cv["mid"] is not None),
                key=lambda r: -r["Value"])
            if crows:
                st.dataframe(crows[:8], width="stretch", hide_index=True)


def _select_base_hop(ranked: list[dict], key: str) -> str:
    """Houblon de base du blend (taille 1), choisi par l'UTILISATEUR plutôt
    qu'imposé (décision 2026-08-19) : signalé en direct que le score de
    contrast/amplify est souvent homogène — plusieurs houblons ex-aequo
    "meilleur candidat" (ex. citra/mosaic/simcoe tous à 20.0 sur une cible
    "citrus,floral" typique) — le classement seul ne désigne donc pas un
    choix évident parmi les ex-aequo."""
    options = [h["variety"] for h in ranked]
    names = {h["variety"]: h["name"] for h in ranked}
    return st.selectbox("Base hop for the blend", options,
                        format_func=lambda v: names[v], key=key)


def _amplify(con):
    # Tous les inputs de l'outil (note incluse) sur la page principale, pas
    # dans la sidebar (2026-08-20, signalé par l'utilisateur en testant sur
    # téléphone : "the note for amplify is in the panel, not the tool page" --
    # la sidebar Streamlit est repliée par défaut sur mobile, donc un input
    # qui n'existe QUE là est invisible sans un tap supplémentaire sur le
    # menu hamburger, contrairement au bureau où elle reste toujours visible.
    # Même traitement pour `contrast`/`by-descriptor` (curseur "Number of
    # results"/"Number of hops shown"), déjà passés de la sidebar à la page
    # principale au même moment -- la sidebar ne garde plus que la
    # NAVIGATION (choix de l'outil) et les infos globales de la base, jamais
    # un input propre à un outil précis.
    notes = _notes(con)
    if not notes:
        st.error("No notes in the database.")
        st.stop()
    note = st.selectbox("Note", notes)
    use_oav = st.checkbox(
        "--oav (olfactory power prior)", value=True,
        help="Weights each molecule by 1/threshold when that threshold is "
             "known (~14 common hop oil molecules: myrcene, geraniol, "
             "thiols... — other molecules are unaffected). Approximate: not "
             "a real concentration measurement, just a correction so a very "
             "potent molecule with a low threshold isn't drowned out by a "
             "ubiquitous but barely odorous one. Changes the ranking on "
             "about 1 note in 6 (measured on the real database). Enabled by "
             "default (user request): a real, measured effect, not noise — "
             "disable it to compare without.")
    # note_descriptors est vide par défaut pour toute note (pas d'amorce
    # littérature, cf. reference.py) : sans sélection manuelle ici, la couche
    # descripteurs ne peut jamais contribuer au score.
    selected_desc = st.multiselect(
        "Note descriptors (optional — activates the descriptor layer)",
        _descriptors(con))
    top = st.slider("Number of results", 1, 30, 8)
    r = matching.amplify(con, note, use_oav=use_oav,
                         descriptors=selected_desc or None, top=top)

    st.metric("Molecular coverage", f"{r['coverage']*100:.0f}%")
    if not r.get("has_descriptors", True):
        st.caption("No descriptors for this note: 100% molecular score "
                  "(w_desc not applied).")
    if r["coverage"] < matching.LOW_COVERAGE_WARNING_THRESHOLD:
        st.warning(
            f"Low molecular coverage ({r['coverage']*100:.0f}%): the molecular "
            "ranking alone risks being dominated by a single molecule common "
            "to many foods, not by this note's own signature (hop oil "
            "chemistry rarely overlaps with food aromas). "
            "**Add as many descriptors as possible** above for a more "
            "reliable result.")
    if r["orphan"]:
        st.warning("Orphans (carried by the addition, not the hop): "
                   + ", ".join(r["orphan"]))
    if not r["ranked"]:
        st.write("No hop overlaps with this note.")
        return
    hops, comp, hop_desc, _ = matching.load(con)
    _render_hop_rows(
        [dict(_row_with_purpose(h, hops, comp), why_str=", ".join(h["why"]) or "—")
         for h in r["ranked"]],
        [("Score", "score"), ("Mol.", "mol"), ("Desc.", "desc"), ("Purpose", "purpose"),
        ("Contributes via", "why_str"), ("Sources", "sources")])

    _hop_detail_expanders(con, hops, comp, hop_desc, [
        {"variety": h["variety"], "name": h["name"],
         "caption": f"score {h['score']} — via {', '.join(h['why']) or '(none)'}"}
        for h in r["ranked"]])

    st.subheader("Propose a blend")
    if not r["has_descriptors"]:
        st.caption("No descriptors for this note: no blend possible "
                  "(select descriptors above).")
    else:
        base = _select_base_hop(r["ranked"], key="amplify_base_hop")
        # Toujours 5 (décision utilisateur) : pas de curseur, un blend à 5
        # tailles complet reste peu coûteux à calculer et laisse voir toutes
        # les options d'un coup plutôt que de forcer un choix a priori.
        blend_r = matching.amplify_blend(con, note, use_oav=use_oav,
                                         descriptors=selected_desc or None, max_hops=5,
                                         base_variety=base)
        _render_blends(blend_r["blends"], hops, comp)


_VIA_LABELS = {"top": "top candidate", "chosen": "base hop (chosen)",
              "complement": "opposite purpose (aromatic/bittering complement)",
              "pairing": "relevant + BeerMaverick pairing (top 10)",
              "coverage": "coverage fallback (no relevant pairing)",
              "relevance": "relevant extra hop (nothing new to cover)"}


def _render_blends(blends: list[dict], hops: dict, comp: dict) -> None:
    """Rendu partagé amplify_blend/contrast_blend (T33 backlog) : plusieurs
    tailles de blend affichées côte à côte plutôt qu'un seul "meilleur" blend
    — chaque houblon signale sa provenance (fréquence RÉELLE de pairing
    BeerMaverick vs. repli par couverture), jamais caché derrière un score
    unique fusionné. Colonne Purpose (T-purpose backlog) : depuis la taille
    2, le mécanisme garantit au moins 1 aromatique + 1 amérisant puis ne
    recrute plus que des aromatiques (voir `matching._pairing_grown_blends`)
    — la colonne rend cette structure visible plutôt que de la laisser
    implicite. `hops`/`comp` : nécessaires pour résoudre "Inferred: ..." sur
    les houblons du blend sans purpose BeerMaverick réel (voir
    `matching.resolve_purpose`) -- la STRUCTURE du blend, elle, continue de
    n'utiliser QUE le purpose réel (`purpose_by_variety` côté
    `_pairing_grown_blends`), jamais l'inférence : ceci est un affichage
    a posteriori, pas une entrée du mécanisme de sélection."""
    if not blends:
        st.write("No combination found.")
        return
    # Un st.container(border=True) par taille de blend (demande utilisateur,
    # "it's visually difficult to separate blend n1/n2...n5" -- pas de
    # séparation visuelle entre les tailles avant, juste des blocs
    # st.write/_render_hop_rows qui s'enchaînaient). Pas un st.dataframe/
    # st.table : `_render_hop_rows` rend le Purpose en st.badge par cellule
    # (seul widget qui s'adapte aux deux thèmes clair/sombre, voir plus
    # haut) -- un vrai tableau perdrait cette coloration. Le conteneur
    # bordé délimite chaque blend au moins aussi clairement que des lignes
    # horizontales, sans ce compromis.
    for b in blends:
        with st.container(border=True):
            st.write(f"**Size {b['size']}**")
            rows = [dict(_row_with_purpose(h, hops, comp),
                        covers_str=", ".join(h["covers"]) or "(nothing new)",
                        via_label=_VIA_LABELS[h["via"]])
                   for h in b["hops"]]
            _render_hop_rows(rows, [("Covers", "covers_str"), ("Purpose", "purpose"),
                                    ("Origin", "via_label"), ("Sources", "sources")])
            if b["residual"]:
                st.caption("Not covered: " + ", ".join(b["residual"]))


def _contrast(con):
    # contrast a besoin de note_descriptors pour une note, table vide par
    # défaut (pas d'amorce littérature dans ce projet, cf. reference.py) —
    # l'utilisateur décrit donc sa note à la main avec le vocabulaire réel de
    # la roue d'arôme (même source que by-descriptor), ce qui fonctionne pour
    # n'importe quelle note sans rien inventer.
    selected = st.multiselect("Descriptors of the note to contrast", _descriptors(con))

    # Cible d'affinité MODIFIABLE (2026-08-19, demande utilisateur explicite :
    # "we should orient the complementary aroma by pre-selecting them but let
    # the user chose which one he want to keep... rather than imposing the
    # mapping" -- exemple donné : pour "tropical"/"mango", ne garder que
    # "spicy" pour retrouver un houblon noble comme Saaz, autrement noyé sous
    # les houblons dank/resinous plus nombreux). `contrast_affinity_target`
    # calcule la proposition (identique à ce que `contrast()` calculerait
    # seul) ; st.pills pré-coche cette proposition mais reste librement
    # modifiable -- untick pour exclure, ou coche un des 10 catégories cœur
    # non proposées pour élargir. Options = les 10 catégories cœur
    # (`CONTRAST_AFFINITY`, valeurs jamais en dehors de ce jeu fermé, voir
    # reference.py) : "there is not much" (même raisonnement que les pills de
    # la roue d'arôme en by-descriptor), toutes tiennent sur une ligne.
    # `key` dépend de `selected` : changer les descripteurs de la note doit
    # RECALCULER la proposition (nouvelle pré-sélection), alors qu'une
    # modification manuelle par l'utilisateur doit survivre aux reruns tant
    # que les descripteurs de la note ne changent pas eux-mêmes -- Streamlit
    # ne réinitialise un widget à son `default` que si sa `key` change.
    proposed_target, _ = matching.contrast_affinity_target(selected)
    target_selected = sorted(proposed_target)
    purposes_selected = ["aromatic", "bittering"]
    if selected:
        st.caption("Complementary notes to target (pre-selected from the affinity map — "
                  "untick to exclude, or add more)")
        target_selected = st.pills(
            "Complementary notes to target", matching.CONTRAST_CORE_CATEGORIES,
            selection_mode="multi",
            default=sorted(proposed_target), label_visibility="collapsed",
            key=f"contrast_target_pills_{tuple(sorted(selected))}") or []

        # Filtre par purpose (T61, 2026-08-19, demande utilisateur explicite :
        # "add another menu for purpose, it would be pre-selecting both
        # bittering and aromatic but we should let user add a filter on this
        # purpose"). Pré-coché sur les deux (aucun filtrage par défaut,
        # comportement identique à avant ce ticket) ; untick un rôle pour ne
        # garder que l'autre. "both" (aromatique ET amérisant réels)
        # satisfait le filtre dès qu'AU MOINS un des deux est coché --
        # jamais une 3e case séparée (voir `matching._purpose_matches_filter`).
        # Un purpose totalement inconnu (ni réel ni inférable depuis l'acide
        # alpha) est exclu dès qu'un filtre est actif, quel qu'il soit --
        # jamais inclus par défaut faute de donnée.
        st.caption("Purpose (pre-selected on both — untick to keep only one)")
        purposes_selected = st.pills(
            "Purpose", ["aromatic", "bittering"], selection_mode="multi",
            default=["aromatic", "bittering"], label_visibility="collapsed",
            key="contrast_purpose_pills") or []

    # Plafond relevé de 30 à 100 (2026-08-19, signalé par l'utilisateur :
    # Saaz introuvable pour "tropical"/"mango" même au plafond précédent) --
    # la cible d'affinité n'a souvent que 3-4 descripteurs (voir
    # reference.CONTRAST_AFFINITY), donc le score (`100 * recoupés / cible`)
    # ne prend que 3-4 valeurs distinctes : des égalités massives (des
    # dizaines de houblons ne recoupant qu'UN descripteur de la cible) sont
    # la norme, pas l'exception -- 30 ne suffisait pas à sortir un houblon
    # "un seul recoupement" comme Saaz d'une égalité de ~84 houblons sur une
    # base réelle. Voir aussi le tri secondaire par total_oil dans
    # `matching.contrast` (rend l'égalité déterministe, pas seulement le
    # plafond relevé). Page principale, pas la sidebar (2026-08-20, voir le
    # commentaire de `_amplify` -- même correctif mobile pour les 3 outils).
    top = st.slider("Number of results", 1, 100, 8)
    if not selected:
        st.write("Choose at least one descriptor."); return
    r = matching.contrast(con, descriptors=selected, target_descriptors=target_selected,
                         purposes=purposes_selected, top=top)

    st.caption("Affinity target: " + (", ".join(r["affinity_target"]) or "(none selected)"))
    if r["unmapped"]:
        st.caption(":material/info: No affinity mapping for: "
                  + ", ".join(r["unmapped"]) + " (ignored, no effect on the target).")
    if not r["ranked"]:
        st.write("No hop overlaps with this target.")
        return
    if r["total_matches"] > len(r["ranked"]):
        # Transparence sur la troncature (2026-08-19, demande utilisateur) :
        # jamais laisser croire que `top` couvre tout le recoupement réel --
        # même principe que la couverture moléculaire faible ou les
        # molécules orphelines ailleurs dans la GUI.
        st.caption(f"Showing {len(r['ranked'])} of {r['total_matches']} hops overlapping "
                  "this target — raise \"Number of results\" above to see more "
                  "(many hops often tie on score; see Contrasts via below for what each "
                  "one actually matches).")
    hops, comp, hop_desc, _ = matching.load(con)
    _render_hop_rows(
        [dict(_row_with_purpose(h, hops, comp), contrast_via_str=", ".join(h["contrast_via"]))
         for h in r["ranked"]],
        [("Score", "score"), ("Purpose", "purpose"), ("Contrasts via", "contrast_via_str"),
        ("Sources", "sources")])

    _hop_detail_expanders(con, hops, comp, hop_desc, [
        {"variety": h["variety"], "name": h["name"],
         "caption": f"score {h['score']} — contrasts via {', '.join(h['contrast_via'])}"}
        for h in r["ranked"]])

    st.subheader("Propose a blend")
    base = _select_base_hop(r["ranked"], key="contrast_base_hop")
    # Toujours 5 (décision utilisateur) : pas de curseur. `target_descriptors`/
    # `purposes` propagés (2026-08-19) : le blend doit viser la même cible et
    # respecter le même filtre purpose que le tableau de résultats ci-dessus.
    blend_r = matching.contrast_blend(con, descriptors=selected, target_descriptors=target_selected,
                                      purposes=purposes_selected, max_hops=5, base_variety=base)
    _render_blends(blend_r["blends"], hops, comp)


def _aroma_wheel(intensity: dict[str, float], vocabulary: list[str]):
    """Roue d'arôme QUANTITATIVE pour UN houblon (T26 backlog, « comme
    BeerMaverick/Yakima »). Rayon = intensité 0-100 réelle
    (`hop_aroma_intensity`, imported_fields.sensory_values/aroma_values côté
    Algolia YCH) — PAS une présence/absence : une première version binaire
    (hop_descriptors, 38 termes plats) a été rejetée en direct par
    l'utilisateur comme non informative, à raison — la vraie donnée
    quantitative existe et était simplement non exploitée (voir
    `parsers.parse_yakima_hit`, contrairement à BarthHaas qui n'a pas cette
    donnée du tout côté HTML statique, voir docs/DATA_SOURCES.md). Vocabulaire
    fixe à 15 termes (mesuré sur la base réelle : mêmes 15 catégories sur
    94/151 variétés Yakima, 12-15/15 couvertes par houblon) -> ordre
    alphabétique stable, mêmes positions d'un houblon à l'autre. Un des 15
    axes ("Pomme") était mal étiqueté en français côté source Yakima même
    sous le filtre de locale en-us — corrigé à l'ingestion
    (`reference.DESCRIPTOR_ALIASES["pomme"] = "apple"`, voir CLAUDE.md), donc
    entièrement anglais désormais. BarthHaas n'a pas cette donnée : `intensity`
    vide pour les houblons non couverts, pas de roue affichée dans ce cas
    (voir `_browse`), pas de valeur inventée.

    Rendu en polygone fermé (« radar »/spider chart, comme les profils de
    stats de joueur — demandé par l'utilisateur) plutôt qu'un camembert à
    rayon variable : une première version en `mark_arc` (theta+radius encodés
    tous les deux) ressemblait à une cible et s'est aussi révélée buguée en
    direct (Vega-Lite ne balaie qu'un demi-cercle par défaut dans cette
    combinaison, même avec un `scale.range` explicite à 2π — non résolu,
    abandonné plutôt que creusé plus loin). Coordonnées x/y calculées ici en
    Python (trigonométrie simple), pas via des transforms Vega — plus robuste
    et vérifiable, `mark_arc` n'a pas de mode polygone natif adapté à ce
    rendu. L'objection du T4 backlog contre les radars (distorsion par l'aire
    en comparaison MULTI-houblons) ne s'applique pas ici : un seul polygone,
    pas de superposition à comparer.

    Couleurs explicitement adaptées au thème (`st.context.theme.type`) : les
    marks Altair "libres" (`mark_rule`/`mark_text` sans encodage de couleur)
    ne suivent PAS automatiquement le thème Streamlit contrairement aux
    axes/légendes natifs — signalé en direct par l'utilisateur (grille et
    libellés restaient dans une teinte sombre fixe, illisible en thème
    sombre). `st.context.theme` n'expose que `.type` (pas les couleurs
    réelles du thème, vérifié dans le code source Streamlit) : palette de
    contraste choisie à la main pour les deux cas plutôt que devinée.

    Champs Vega ("Descriptor"/"Intensity", pas "Descripteur"/"Intensité")
    délibérément en anglais : Vega-Lite affiche le nom de champ tel quel comme
    libellé de tooltip au survol, donc visible par l'utilisateur — cohérent
    avec le passage de la GUI à l'anglais (2026-08-19)."""
    if not vocabulary:
        return None
    dark = st.context.theme.type == "dark"
    text_color = "#f2f2f0" if dark else "#1a1a18"
    grid_color = "#5a5a56" if dark else "#3a3a38"
    accent = "#4da3ff" if dark else "#2a78d6"

    n = len(vocabulary)
    r_max = 170.0  # agrandi (demande utilisateur) — était 130
    label_radius = r_max + 30
    half_extent = label_radius + 40

    def _xy(i: int, value: float) -> tuple[float, float]:
        angle = (i / n) * 2 * math.pi - math.pi / 2
        r = (max(0.0, min(value, 100.0)) / 100.0) * r_max
        return r * math.cos(angle), r * math.sin(angle)

    spokes = []
    labels = []
    for i, d in enumerate(vocabulary):
        angle = (i / n) * 2 * math.pi - math.pi / 2
        ex, ey = r_max * math.cos(angle), r_max * math.sin(angle)
        spokes.append({"x": 0.0, "y": 0.0, "x2": ex, "y2": ey})
        lx, ly = label_radius * math.cos(angle), label_radius * math.sin(angle)
        labels.append({"x": lx, "y": ly, "Descriptor": d,
                       "Definition": matching.AROMA_WHEEL_DEFINITIONS.get(d, "")})

    poly = []
    for i, d in enumerate(vocabulary):
        val = intensity.get(d, 0.0)
        x, y = _xy(i, val)
        poly.append({"x": x, "y": y, "Descriptor": d, "Intensity": val, "Order": i})
    poly.append(dict(poly[0], Order=n))  # referme le polygone

    domain = [-half_extent, half_extent]
    x_enc = alt.X("x:Q", axis=None, scale=alt.Scale(domain=domain))
    y_enc = alt.Y("y:Q", axis=None, scale=alt.Scale(domain=domain))

    grid = (
        alt.Chart(alt.Data(values=spokes))
        .mark_rule(strokeWidth=1, stroke=grid_color)
        .encode(x=x_enc, y=y_enc, x2="x2:Q", y2="y2:Q")
    )
    polygon_line = (
        alt.Chart(alt.Data(values=poly))
        .mark_line(color=accent, strokeWidth=2, order=True)
        .encode(x=x_enc, y=y_enc, order="Order:Q")
    )
    points = (
        alt.Chart(alt.Data(values=poly[:-1]))
        .mark_point(filled=True, size=60, color=accent)
        .encode(x=x_enc, y=y_enc,
               tooltip=["Descriptor:N", alt.Tooltip("Intensity:Q", format=".0f")])
    )
    text = (
        alt.Chart(alt.Data(values=labels))
        .mark_text(fontSize=14, color=text_color)
        .encode(x=x_enc, y=y_enc, text="Descriptor:N",
               tooltip=["Descriptor:N", "Definition:N"])
    )
    return (
        (grid + polygon_line + points + text)
        .properties(width=480, height=480)
        .configure_view(strokeWidth=0)
    )


def _browse(con):
    """Mode propre à la GUI (pas d'équivalent CLI) : consulter un houblon
    directement — composition + descripteurs + sources — sans passer par
    amplify/contrast/by-descriptor (T5 backlog). Affiche aussi la roue
    d'arôme quantitative (T26), le purpose (T-purpose, EN INFO PRINCIPALE
    demandé par l'utilisateur) et les associations houblon<->houblon
    (T25, voir `_hop_associations`).

    `hops[v]["name"]` est déjà désambiguïsé par région en cas de collision
    (`matching._disambiguate_hop_names`, appliqué dans `load()` -- T60,
    2026-08-19) : plus besoin d'un mécanisme séparé ici, ni ailleurs dans la
    GUI (amplify/contrast/by-descriptor en profitent aussi automatiquement)."""
    hops, comp, hop_desc, _ = matching.load(con)
    query = st.text_input("Search (name or variety)", key="browse_search")
    varieties = sorted(hops, key=lambda v: hops[v]["name"].lower())
    if query:
        q = query.strip().lower()
        varieties = [v for v in varieties if q in hops[v]["name"].lower() or q in v]
    st.caption(f"{len(varieties)} hop(s)")
    if not varieties:
        st.write("No hop matches this search.")
        return

    selected = st.selectbox("Hop", varieties, format_func=lambda v: hops[v]["name"],
                            key="browse_hop")
    h = hops[selected]
    hcomp = comp.get(selected, {})
    st.subheader(h["name"])
    # purpose EN PREMIER, avant région/sources (demande utilisateur explicite :
    # "should appear in the browser information as a main/top information").
    purpose, inferred = matching.resolve_purpose(h.get("purpose"), hcomp)
    _purpose_badge(purpose, inferred)
    st.caption(f"Region: {h['region'] or 'unknown'} · Sources: {h['sources']}")
    # Alpha/beta acids, co-humulone, total oil : demande utilisateur explicite
    # (2026-08-19), "il manque un élément principal : les infos les plus
    # importantes de yakima" -- voir `_render_key_stats`.
    _render_key_stats(hcomp)

    descs = sorted(hop_desc.get(selected, set()))
    st.write("**Descriptors:** " + (", ".join(descs) if descs else "none recorded"))
    intensity = matching.hop_aroma_intensity(con, selected)
    # any(...) > 0, pas juste `if intensity :` : au moins une variété réelle
    # (admiral, vérifié en direct) a une entrée sensory_values existante mais
    # entièrement à 0 côté YCH — cohérent avec la corruption déjà documentée
    # de cette variété précise (voir _is_plausible_brewing_entry) ; un dict
    # non vide mais tout à zéro n'est pas une donnée exploitable.
    if intensity and any(v > 0 for v in intensity.values()):
        # theme=None : par défaut st.altair_chart applique le thème
        # "streamlit" (config Vega-Lite globale) qui écrase les couleurs
        # explicites choisies à la main dans _aroma_wheel pour s'adapter au
        # clair/sombre -- vérifié en direct (labels illisibles en thème
        # sombre malgré la palette choisie) : c'est ce thème global qui gagne
        # sur les couleurs de mark, pas un mauvais choix de couleur.
        st.altair_chart(_aroma_wheel(intensity, _intensity_vocabulary(con)),
                        width="content", theme=None)
        st.caption(":material/info: Hover a label for its definition "
                  "(Yakima Chief Hop Sensory Ballot).")
    else:
        st.caption("No quantitative aroma wheel for this variety "
                   "(Yakima data unavailable or unusable here — BarthHaas "
                   "only, variety not covered, or corrupted YCH entry as "
                   "with Admiral).")

    # "Smells like" (T72, 2026-08-21, demande utilisateur explicite : le
    # tooltip Flavornet ajouté sur le barplot Compare Hops (T71) doit AUSSI
    # apparaître ici -- voir `_all_compound_descriptors`).
    compound_smells = _all_compound_descriptors(con, comp)
    rows = sorted(
        ({"Compound": c, "Value": round(v["mid"], 3), "Unit": v["unit"],
          "Sources": ", ".join(v["sources"]), "Smells like": compound_smells.get(c, "—")}
         for c, v in hcomp.items() if c not in matching.NON_AROMA_DISPLAY and v["mid"] is not None),
        key=lambda r: -r["Value"])
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.write("No composition recorded.")

    st.divider()
    # Titre commun aux 3 relations éditoriales (2026-08-21, demande
    # utilisateur explicite : "the 'Similar varieties (Yakima)' is not a
    # main title as compared with 'Similar hops (by molecular
    # composition)'... add a title 'Database similarity and
    # substitution'") -- ce titre couvre `_hop_associations` (3 sous-titres
    # de poids égal, `st.write("**...**")`, inchangé).
    st.subheader("Database similarity and substitution")
    _hop_associations(con, hops, selected)

    # Section calculée à PART, même niveau de titre que ci-dessus (T68
    # addendum, 2026-08-21, demande utilisateur explicite : "'Similar hops
    # (computed from measured data)' should be the same title level than
    # 'Database similarity and substitution' with a separator just
    # before") -- un `st.divider()` marque la frontière entre les relations
    # ÉDITORIALES (Yakima/BeerMaverick, ci-dessus) et cette relation
    # CALCULÉE (`similar_hops`), toutes deux `st.subheader` désormais :
    # deux sections soeurs plutôt qu'une section unique où la calculée
    # ressortait comme un sous-item parmi les éditoriales.
    st.divider()
    _similar_hops_section(con, hops, comp, selected)


# Libellés GUI -> clés `matching.similar_hops(use_molecular=/use_aroma_wheel=)`.
_SIMILARITY_LAYER_OPTIONS = {"Molecular composition": "molecular",
                             "Aroma wheel intensity": "aroma_wheel"}


def _similar_hops_section(con, hops: dict, comp: dict, selected: str) -> None:
    """Section "Similar hops" en bas de Browse (T67, 2026-08-21, demande
    utilisateur explicite), ORDONNÉE de la plus proche à la moins proche —
    calculée depuis les données mesurées, distincte des trois relations
    éditoriales/recette déjà affichées par `_hop_associations` juste
    au-dessus (jamais fusionnées).

    **Deux couches indépendantes, activables séparément (T68, 2026-08-21,
    demande utilisateur explicite : "we also could use the quantitative
    aroma wheel scores right?... allow the used to toogle molecular and/or
    aroma_wheel layers").** Molecular composition (`hop_composition`,
    `matching.similar_hops_by_composition`) et Aroma wheel intensity
    (`hop_aroma_intensity`, T26, Yakima uniquement,
    `matching.similar_hops_by_aroma_wheel`) — même méthode
    (`matching._coverage_penalized_cosine`) appliquée à deux jeux de
    données différents (chimie mesurée vs perception sensorielle Yakima),
    jamais mélangées en un seul vecteur : `matching.similar_hops` les
    combine par MOYENNE des couches actives ayant une donnée pour chaque
    candidat, jamais une moyenne qui compte silencieusement une couche
    manquante comme 0. Les deux actives par défaut (`st.pills`, comme le
    filtre Purpose de `contrast` — même widget, même raison : peu
    d'options, tiennent sur une ligne)."""
    st.subheader("Similar hops (computed from measured data)")
    st.caption("Cosine similarity, per-compound/per-category normalized and "
              "specificity-weighted, then scaled by data Coverage (the "
              "fraction of this hop's own measured axes the candidate also "
              "has data for, so a partially-measured hop can't outrank a "
              "fully-measured one just because cosine ignores what's "
              "missing). Not an editorial/recipe relation like the "
              "associations above.")
    layer_labels = st.pills(
        "Similarity layers", list(_SIMILARITY_LAYER_OPTIONS), selection_mode="multi",
        default=list(_SIMILARITY_LAYER_OPTIONS), label_visibility="collapsed",
        key="similar_hops_layers") or []
    layers = {_SIMILARITY_LAYER_OPTIONS[label] for label in layer_labels}
    if not layers:
        st.caption("Select at least one layer above.")
        return
    similar = matching.similar_hops(con, selected, use_molecular="molecular" in layers,
                                    use_aroma_wheel="aroma_wheel" in layers)
    if not similar:
        st.caption("No comparable data for this variety in the selected layer(s).")
        return

    # En-têtes de colonne EXPLICITES par couche (2026-08-21, signalé par
    # l'utilisateur en direct : avec une seule couche active, la colonne de
    # score restait titrée génériquement "Similarity" sans dire laquelle --
    # ambigu, à tort lisible comme un mismatch entre le score affiché et le
    # nom de la couche sélectionnée). Aucune ambiguïté possible désormais :
    # le nom de la couche est TOUJOURS dans le libellé de sa propre colonne.
    if len(layers) == 2:
        columns = [("Combined similarity", "similarity"),
                  ("Molecular similarity", "mol_str"), ("Aroma wheel similarity", "wheel_str")]
    elif layers == {"molecular"}:
        columns = [("Molecular similarity", "similarity")]
    else:
        columns = [("Aroma wheel similarity", "similarity")]
    columns.append(("Purpose", "purpose"))
    if "molecular" in layers:
        columns.append(("Shared signature compounds", "shared_compounds_str"))
    if "aroma_wheel" in layers:
        columns.append(("Shared aroma categories", "shared_descriptors_str"))
    columns.append(("Sources", "sources"))

    rows = []
    for h in similar:
        row = dict(_row_with_purpose(h, hops, comp))
        row["mol_str"] = ("—" if h["molecular_similarity"] is None
                          else str(h["molecular_similarity"]))
        row["wheel_str"] = ("—" if h["aroma_wheel_similarity"] is None
                            else str(h["aroma_wheel_similarity"]))
        row["shared_compounds_str"] = ", ".join(h["shared_compounds"]) or "—"
        row["shared_descriptors_str"] = ", ".join(h["shared_descriptors"]) or "—"
        rows.append(row)
    _render_hop_rows(rows, columns)


def _hop_associations(con, hops: dict, selected: str) -> None:
    """Associations houblon<->houblon (T25 backlog) : trois relations
    différentes, chacune affichée avec sa propre source — ne jamais les
    présenter comme interchangeables (similarité YCH != co-usage recette
    BeerMaverick != choix éditorial BeerMaverick)."""
    similar = matching.hop_similar_varieties(con, selected)
    st.write("**Similar varieties (Yakima)**")
    if similar:
        st.write(", ".join(hops[v]["name"] for v in similar if v in hops))
    else:
        st.caption("No Yakima suggestion for this variety.")

    pairings = matching.hop_pairings(con, selected)
    st.write("**Frequent recipe pairings (BeerMaverick — aggregator, "
             "analysis of published recipes, not a lab measurement)**")
    if pairings:
        st.dataframe(
            [{"Hop": hops[p["variety"]]["name"] if p["variety"] in hops else p["name"],
              "Relative frequency": p["frequency"]} for p in pairings],
            width="stretch", hide_index=True)
    else:
        st.caption("No BeerMaverick data for this variety (insufficient "
                   "recipe volume on their end, or variety not covered).")

    subs = matching.hop_substitutions(con, selected)
    st.write("**Suggested substitutions (BeerMaverick — editorial choice "
             "of experienced brewers, not a measurement)**")
    if subs:
        st.write(", ".join(
            hops[s["variety"]]["name"] if s["variety"] in hops else s["name"] for s in subs))
    else:
        st.caption("No BeerMaverick data for this variety.")


_MAX_HEATMAP_HOPS = 12

# Buckets de teinte pour la heatmap (2026-08-19, demande utilisateur :
# "propose a ordered result in a quantitative heatmap based on the aroma
# wheel descriptors"). "absent" = pas dans hop_descriptors (fond neutre,
# comme l'ancienne teinte "no") ; "present" = présent côté hop_descriptors
# MAIS sans intensité mesurée pour CE houblon (BarthHaas seul, ou variété
# Yakima non couverte -- voir `matching.hop_aroma_intensity` -- ou, dans la
# section "Other descriptors", un descripteur hors du vocabulaire à 15
# catégories de la roue, qui n'aura JAMAIS de donnée quantitative). NOIR
# (pas gris, cf. addendum 2026-08-19 -- retour utilisateur : le gris se
# lisait comme un NaN/valeur manquante plutôt que comme "présent") ; 5
# paliers de bleu croissant (0-100 réel, `hop_aroma_intensity`) pour les
# cellules avec donnée -- discrétisé plutôt qu'un dégradé continu Vega, pour
# rester lisible sur une petite cellule de grille (mêmes tons que
# `_aroma_wheel`/l'accent existant #2a78d6, palier le plus saturé = ce bleu).
_INTENSITY_BUCKET_ORDER = ["absent", "present", "0-20", "20-40", "40-60", "60-80", "80-100"]
_INTENSITY_BUCKET_COLORS = ["#f2f1ee", "#000000", "#dbe9fb", "#aecdf2", "#7fb0e8", "#4d92dd", "#2a78d6"]


def _intensity_bucket(value: float) -> str:
    for hi in (20, 40, 60, 80):
        if value < hi:
            return f"{hi - 20}-{hi}"
    return "80-100"


def _heatmap_chart(shown, hop_order, descriptor_order):
    """Une grille houblon x descripteur pour LE SOUS-ENSEMBLE de
    descripteurs donné -- factorisé pour être appelé une fois par section
    (roue quantitative / autres descripteurs, voir `_descriptor_heatmap`)."""
    rows = []
    for h in shown:
        for d in descriptor_order:
            present = d in h["all_descriptors"]
            val = h["intensity"].get(d) if present else None
            if not present:
                bucket, detail = "absent", "not present"
            elif val is None:
                bucket, detail = "present", "present (no quantitative data)"
            else:
                bucket, detail = _intensity_bucket(val), f"{val:.0f}/100"
            rows.append({"Hop": h["name"], "Descriptor": d, "Bucket": bucket, "Detail": detail})
    return (
        alt.Chart(alt.Data(values=rows))
        .mark_rect(stroke="white", strokeWidth=2)
        .encode(
            x=alt.X("Hop:N", sort=hop_order, title=None,
                    axis=alt.Axis(labelAngle=-45, labelOverlap=False, labelLimit=200)),
            y=alt.Y("Descriptor:N", sort=descriptor_order, title=None,
                    axis=alt.Axis(labelOverlap=False)),
            color=alt.Color(
                "Bucket:N",
                scale=alt.Scale(domain=_INTENSITY_BUCKET_ORDER, range=_INTENSITY_BUCKET_COLORS),
                legend=alt.Legend(title="Intensity")),
            tooltip=["Hop:N", "Descriptor:N", "Detail:N"],
        )
        # largeur/hauteur au pas (pas "container") : le nombre de lignes/colonnes
        # varie avec la sélection, une largeur fixe tronque les libellés en
        # silence (labelOverlap les faisait disparaître un sur deux, vérifié
        # en direct avec 10 houblons).
        .properties(width=alt.Step(45), height=alt.Step(18))
    )


def _descriptor_heatmap(ranked, intensity_vocab):
    """Grille houblon x descripteur, pour comparer visuellement plusieurs
    candidats d'un coup (T4 backlog). Grille plutôt qu'un radar : les
    descripteurs restent un ensemble par houblon, un radar déformerait par
    l'aire pour un gain de lisibilité nul (voir la table forme/usage du
    skill dataviz : « grille -> heatmap »).

    Teinte À DEUX NIVEAUX (2026-08-19, demande utilisateur explicite --
    "propose a ordered result in a quantitative heatmap based on the aroma
    wheel descriptors") : shadée par l'intensité MESURÉE
    (`hop_aroma_intensity`, T26, Yakima uniquement, 0-100 réel) quand elle
    existe pour ce houblon/descripteur -- sinon repli sur les DEUX états
    catégoriques d'origine (présent sans donnée / absent), jamais une
    valeur inventée. `h["intensity"]` vient directement de
    `matching.by_descriptor` (déjà chargé pour le tri quantitatif, voir
    `_by_descriptor`) -- pas de requête supplémentaire ici.

    DEUX SECTIONS SÉPARÉES (2026-08-19, addendum -- retour utilisateur
    explicite : "separate descriptors from quantitative aroma wheel values
    in two section in the heatmap") : les descripteurs qui PEUVENT avoir une
    donnée quantitative (`intensity_vocab`, les 15 catégories de la roue)
    forment une première grille ; tous les autres descripteurs catégoriques
    (BarthHaas/Yakima/BeerMaverick, ex. "pine"/"grapefruit"/"dank" --
    JAMAIS de donnée quantitative possible pour eux, quel que soit le
    houblon) forment une seconde grille distincte -- mélanger les deux
    laissait croire que l'absence de nuance bleue pour un descripteur
    catégorique-only était un trou de données Yakima plutôt qu'une
    impossibilité structurelle. Chaque section retourne `None` si vide
    (ex. aucun descripteur roue parmi les houblons affichés).

    Champs Vega en anglais ("Hop"/"Descriptor"/"Detail") : visibles au
    survol (tooltip), cohérent avec le passage de la GUI à l'anglais
    (2026-08-19)."""
    if len(ranked) < 2:
        return None
    shown = ranked[:_MAX_HEATMAP_HOPS]
    hop_order = [h["name"] for h in shown]
    freq = {}
    for h in shown:
        for d in h["all_descriptors"]:
            freq[d] = freq.get(d, 0) + 1
    wheel_set = set(intensity_vocab)
    wheel_order = sorted((d for d in freq if d in wheel_set), key=lambda d: (-freq[d], d))
    other_order = sorted((d for d in freq if d not in wheel_set), key=lambda d: (-freq[d], d))
    wheel_chart = _heatmap_chart(shown, hop_order, wheel_order) if wheel_order else None
    other_chart = _heatmap_chart(shown, hop_order, other_order) if other_order else None
    return wheel_chart, other_chart, len(ranked) - len(shown)


def _by_descriptor(con):
    # Descripteurs TEXTE (vocabulaire complet à 104 termes) : SEUL filtre
    # catégorique (2026-08-19, revirement -- décision utilisateur après
    # avoir testé en direct roue [tropical, citrus, floral] + texte "papaya" :
    # un houblon ne recoupant que la roue ressortait quand même mélangé
    # AVANT des houblons "papaya" réels, jugé moins précis que voulu --
    # "the qualitative textual descriptor is not a priority over the wheel
    # aroma descriptor selected"). Un houblon DOIT recouper au moins un
    # descripteur texte pour apparaître, dès qu'il y en a un de choisi.
    descriptors = _descriptors(con)
    text_selected = st.multiselect("Descriptors", descriptors)

    # Roue d'arôme QUANTITATIVE : ne FILTRE plus, sert uniquement à NOTER
    # (moyenne d'intensité mesurée) les houblons déjà retenus par les
    # descripteurs texte ci-dessus -- "pre-select all hops having this
    # descriptor and then score the hops that match this based on the
    # average score of the wheel descriptor inputed" (demande utilisateur).
    # st.pills (pas un multiselect) : "small number of options that fit on
    # one line" (15 catégories fixes, voir `_aroma_wheel`) -- plus
    # visible/cliquable que de les chercher dans le multiselect texte.
    intensity_vocab = _intensity_vocabulary(con)
    wheel_selected = []
    if intensity_vocab:
        st.caption("Aroma wheel flavors (optional — scores the results above by measured "
                  "intensity; does not filter them, except as a fallback when no text "
                  "descriptor is chosen)")
        wheel_selected = st.pills("Aroma wheel flavors", intensity_vocab,
                                  selection_mode="multi", label_visibility="collapsed",
                                  key="by_descriptor_wheel_pills") or []
    # Page principale, pas la sidebar (2026-08-20, voir le commentaire de
    # `_amplify` -- même correctif mobile pour les 3 outils).
    top = st.slider("Number of hops shown", 1, 30, 10)
    if not text_selected and not wheel_selected:
        st.write("Choose at least one descriptor.")
        return
    r = matching.by_descriptor(con, text_selected, wheel_descriptors=wheel_selected, top=top)
    ranked = r["ranked"]
    if not ranked:
        st.write("No hop overlaps with these descriptors.")
        return
    if r["total_matches"] > len(ranked):
        # Transparence sur la troncature (2026-08-20, revue de code — même
        # principe que `contrast`/T56 : jamais laisser croire que "Number of
        # hops shown" couvre tout le recoupement réel).
        st.caption(f"Showing {len(ranked)} of {r['total_matches']} hops overlapping these "
                  "descriptors — raise \"Number of hops shown\" above to see more.")

    _, comp, _, _ = matching.load(con)
    compound_smells = _all_compound_descriptors(con, comp)

    heatmap = _descriptor_heatmap(ranked, intensity_vocab)
    if heatmap is not None:
        wheel_chart, other_chart, hidden = heatmap
        suffix = f" (first 12 of {len(ranked)})" if hidden else ""
        if wheel_chart is not None:
            st.caption("Aroma wheel descriptors — shaded by measured intensity (Yakima), "
                      "black where a hop carries the descriptor but has no quantitative "
                      "reading for it" + suffix)
            st.altair_chart(wheel_chart, width="stretch")
        if other_chart is not None:
            st.caption("Other descriptors — categorical only, no quantitative intensity "
                      "data exists for these (black = present)" + suffix)
            st.altair_chart(other_chart, width="stretch")

    for h in ranked:
        hcomp = comp.get(h["variety"], {})
        with st.expander(
                f"{h['name']} — matches {', '.join(h['matched_descriptors'])} "
                f"[{h['sources']}]"):
            purpose, inferred = matching.resolve_purpose(h.get("purpose"), hcomp)
            _purpose_badge(purpose, inferred)
            _render_key_stats(hcomp)
            st.caption("All descriptors: " + ", ".join(h["all_descriptors"]))
            # Transparence sur le tri quantitatif (2026-08-19, "propose a 2
            # layer results ordering... inside this selection, propose a
            # ordered result... based on the aroma wheel descriptors") --
            # jamais un réordonnancement silencieux : dit explicitement CE
            # QUI a été moyenné, ou l'absence de donnée exploitable, pour que
            # l'utilisateur puisse vérifier pourquoi ce houblon est classé où
            # il est parmi ceux à même nombre de descripteurs recoupés.
            if h["quant_score"] is not None:
                st.caption(f"Quantitative refinement: {h['quant_score']:.0f}/100 avg. "
                          f"intensity on {', '.join(h['quant_descriptors'])} (Yakima)")
            elif wheel_selected:
                st.caption("Quantitative refinement: no aroma-wheel intensity data for "
                          "this hop (BarthHaas only, or variety not covered by Yakima).")
            # Roue d'arôme quantitative (demande utilisateur 2026-08-19 : "The
            # aroma wheel is missing from the from descriptor tool") -- même
            # rendu que `_browse`/`_hop_detail_expanders` (theme=None, voir
            # leur commentaire pour la raison), absente si Yakima ne couvre
            # pas la variété ou si l'entrée est corrompue (ex. Admiral).
            # `h["intensity"]` réutilise directement ce que `by_descriptor` a
            # déjà chargé pour le score quantitatif -- pas une deuxième requête.
            intensity = h["intensity"]
            if intensity and any(val > 0 for val in intensity.values()):
                st.altair_chart(_aroma_wheel(intensity, _intensity_vocabulary(con)),
                                width="content", theme=None)
                st.caption(":material/info: Hover a label for its definition "
                          "(Yakima Chief Hop Sensory Ballot).")
            if h["compounds"]:
                st.dataframe(
                    [{"Compound": c["compound"], "Value": round(c["mid"], 2),
                      "Unit": c["unit"], "Sources": ", ".join(c["sources"]),
                      "Smells like": compound_smells.get(c["compound"], "—")}
                     for c in h["compounds"][:8]],
                    width="stretch", hide_index=True)


# T58 (2026-08-19, demande utilisateur, inspiré de
# https://beermaverick.com/hops/hop-comparison-tool/) : palette CATÉGORIELLE
# (pas divergente -- "Spectral" suggéré par l'utilisateur est une palette
# ColorBrewer pensée pour un gradient autour d'un centre neutre, pas adaptée
# à des houblons sans ordre naturel entre eux) -- Vega/Altair "tableau10",
# moderne et conçue pour du nominal, 5 premières teintes (max 5 houblons).
_COMPARE_PALETTE = ["#4c78a8", "#f58518", "#e45756", "#72b7b2", "#54a24b"]
_COMPARE_MAX_HOPS = 5

# Largeur PARTAGÉE, littérale (pas de Step ni de "stretch") des 3 graphiques
# de Compare Hops (2026-08-19, retour utilisateur en direct : "I would like
# all 3 plots to be the same width... ensure the spider plot is properly
# scaled (not narrow)"). Root cause du désalignement initial : les 3
# graphiques utilisaient 3 stratégies de largeur DIFFÉRENTES --
# `width="content"` figé à 480px pour le radar (petit, carré) vs
# `width="stretch"` (rempli le conteneur, beaucoup plus large) pour les
# barplots avec une largeur interne `alt.Step(70)` (dépend du nombre de
# catégories, pas de la largeur du conteneur). Résultat : trois largeurs
# incohérentes. Corrigé en fixant une largeur numérique EXPLICITE, IDENTIQUE
# sur les 3 (`properties(width=_COMPARE_CHART_WIDTH)`), rendue avec
# `width="content"` partout (jamais "stretch", qui écraserait cette largeur
# explicite) -- seul moyen de garantir un alignement pixel-perfect entre un
# radar carré à domaine quantitatif fixe et deux barplots à échelle de bande
# catégorielle (nombre de catégories différent entre les deux : 4 vs jusqu'à
# 11 -- un `width` numérique fixe, pas un `Step` par catégorie, est
# nécessaire pour que Vega-Lite recalcule lui-même la largeur de bande en
# fonction du nombre de catégories tout en gardant le total identique).
_COMPARE_CHART_WIDTH = 700

# Composés "détaillés" du barplot 2 = tout hop_composition SAUF les 4 champs
# "principaux" du barplot 1 (`matching.NON_AROMA_DISPLAY`) -- ordre fixe pour rester
# stable d'une sélection de houblons à l'autre plutôt qu'un tri alphabétique
# qui changerait selon quels composés sont présents.
_COMPARE_DETAIL_OIL_COMPOUNDS = ["myrcene", "humulene", "caryophyllene", "farnesene",
                                "linalool", "geraniol", "beta-pinene", "selinene",
                                "isobutyrate", "ketones"]
# thiols : SEUL composé de la liste "détaillée" en µg/kg (tous les autres
# sont en % d'huile, pct_oil) -- piège d'unité découvert en écrivant ce
# ticket (l'utilisateur n'avait signalé le mélange % / % de % / ml-100g que
# pour le barplot 1) : mélanger thiols (~0.06 µg/kg) avec myrcène (~40%
# d'huile) sur le même axe écraserait sa barre. Même traitement à double
# axe que le barplot 1, jamais fusionné sur le même axe que le reste.
_COMPARE_THIOLS_COMPOUND = "thiols"


def _compare_principal_values(hcomp: dict) -> dict[str, float | None]:
    """Les 4 infos "principales" pour UN houblon, prêtes pour le barplot 1.
    `co_humulone` est stocké en base comme "% DES acides alpha" (`pct`, mais
    une fraction DE `alpha_acid`, pas du houblon total) -- converti ici en %
    ABSOLU du houblon (`alpha_acid_pct * co_humulone_pct_of_AA / 100`) pour
    partager une seule échelle "%" avec alpha/beta (demande utilisateur
    explicite, T58 : "you will need to convert the % of % into %"). `None`
    si un des deux termes manque -- jamais une conversion approximative sur
    une donnée absente."""
    alpha = hcomp.get("alpha_acid", {}).get("mid")
    beta = hcomp.get("beta_acid", {}).get("mid")
    co_h_of_aa = hcomp.get("co_humulone", {}).get("mid")
    co_h_abs = alpha * co_h_of_aa / 100 if alpha is not None and co_h_of_aa is not None else None
    oil = hcomp.get("total_oil", {}).get("mid")
    # "\n" dans les deux libellés longs (pas juste une longue chaîne) :
    # signalé en direct par l'utilisateur -- ces labels étaient tronqués/
    # illisibles sur l'axe X du barplot 1. Vega-Lite ne scinde PAS
    # nativement un "\n" littéral dans un label d'axe (vérifié en direct :
    # présent dans le JSON de la spec, mais rendu sur une seule ligne quand
    # même) -- `axis.labelExpr: split(...)` côté `_compare_dual_axis_barplot`
    # convertit la chaîne en tableau de lignes au moment du rendu, seul
    # mécanisme qui fonctionne. "Total oil (ml/100g)" scindé pour la même
    # raison de lisibilité que "Co-humulone", pas juste ce dernier (retour
    # utilisateur explicite : "similarly for the co-humulone").
    return {"Alpha acids": alpha, "Beta acids": beta,
           "Co-humulone\n(% of hop)": co_h_abs, "Total oil\n(ml/100g)": oil}


def _compare_detail_value(hcomp: dict, compound: str, absolute: bool) -> float | None:
    """Valeur d'UN composé du barplot 2 pour UN houblon, en % d'huile (par
    défaut) ou en quantité absolue ml/100g (`absolute=True`, bascule
    2026-08-21, demande utilisateur explicite -- reprend une suggestion
    lue telle quelle : convertir `% d'huile × huile_totale / 100`, EXACTEMENT
    la même conversion que `matching.amount()` applique déjà pour l'unité
    `pct_oil` côté scoring, réappliquée ici pour l'affichage). Composés en
    dehors de `pct_oil` (thiols, en µg/kg) ne sont JAMAIS convertis, quel
    que soit `absolute` -- déjà une quantité absolue. `None` si le composé
    est absent, OU si `absolute=True` et que `total_oil` de ce houblon est
    inconnu (aucune conversion possible) -- jamais une valeur fabriquée."""
    rec = hcomp.get(compound)
    if not rec or rec.get("mid") is None:
        return None
    if not absolute or rec.get("unit") != "pct_oil":
        return rec["mid"]
    oil = hcomp.get("total_oil", {}).get("mid")
    if oil is None:
        return None
    return rec["mid"] * oil / 100.0


_COMPARE_LABEL_ANGLE = -45


def _compare_dual_axis_barplot(rows: list[dict], primary_fields: list[str], primary_title: str,
                               secondary_fields: list[str], secondary_title: str,
                               colors: dict[str, str],
                               descriptors: dict[str, str] | None = None):
    """Barplot groupé par houblon (`xOffset`) sur un axe "Field" catégoriel
    partagé, à DOUBLE ÉCHELLE Y : `primary_fields` sur l'axe gauche,
    `secondary_fields` sur l'axe droit (2026-08-19, T58 -- demande
    utilisateur explicite : "we will mix %, % of % and ml/100g... use double
    scale for this one"). `rows` : liste de {"Hop", "Field", "Value"} --
    `Value` déjà en unité finale (co-humulone déjà converti en % absolu par
    l'appelant), AUCUNE valeur `None` (filtrée par l'appelant, jamais une
    barre à 0 fabriquée pour une donnée absente).

    Deux couches (`alt.layer(...).resolve_scale(y="independent")`) --
    Vega-Lite ne fait pas de double axe nativement sur une seule couche. Les
    DEUX couches partagent le même `scale.domain` explicite sur `x` (tous
    les champs, primaires ET secondaires) : sans ça, chaque couche
    recalculerait son propre domaine `x` depuis son SOUS-ENSEMBLE de
    données seulement, désalignant les groupes de barres entre les deux
    couches.

    Angle FIXE (`_COMPARE_LABEL_ANGLE`, -45°) partagé par les DEUX barplots
    (2026-08-19, retour utilisateur en direct -- "the angle of the X axis of
    the 2 barplot is not the same"). Un premier correctif avait laissé le
    barplot 1 à -20° (4 catégories courtes) et forcé -45° seulement sur le
    barplot 2 (jusqu'à 11 catégories) -- incohérent visuellement d'un
    graphique à l'autre alors que rien n'empêche -45° de convenir aux deux.
    `labelOverlap=False` (2026-08-19, retour utilisateur -- "the last
    barplot is still missing 1/2 labels, FORCE THE DISPLAY OF ALL LABELS") :
    par défaut Vega-Lite MASQUE silencieusement un label qu'il calcule comme
    se chevauchant avec son voisin plutôt que de les superposer -- exactement
    la cause du "1 label sur 2" constaté. `labelOverlap=False` désactive ce
    calcul et force l'affichage de TOUS les labels, quitte à ce qu'ils se
    chevauchent légèrement à forte densité de catégories (préférable à un
    label silencieusement absent, même principe d'honnêteté que le reste de
    la GUI -- jamais rien de caché sans le signaler). `labelAlign="right"`/
    `labelBaseline="middle"` : sans ça, un label pivoté reste ancré en son
    CENTRE plutôt qu'en son extrémité proche du tick, donc visuellement
    désaligné de la graduation qu'il annote (piège Vega-Lite connu sur les
    labels pivotés).

    `descriptors` (T70, 2026-08-21, demande utilisateur explicite -- "sur le
    barplot, myrcene est une chaîne nue... un tooltip sur chaque label de
    composé", `matching.compound_descriptors`) : optionnel, {Field:
    descripteurs Flavornet}. Deux effets si fourni : (1) ajouté à la fin du
    tooltip existant des BARRES elles-mêmes ("—" si ce composé précis n'a
    pas d'entrée -- jamais omis pour ne pas laisser croire à un champ
    absent du schéma, mais jamais une valeur inventée non plus) ; (2) une
    couche RECT invisible (`opacity` quasi nulle, PAS exactement 0 --
    certains moteurs Vega n'attachent pas d'écouteur de survol à une
    opacité strictement nulle) couvrant toute la hauteur du graphique pour
    CHAQUE composé résolu, posée EN PREMIER (donc sous les barres dans
    l'empilement SVG) : survoler une barre déclenche son tooltip habituel
    (Hop/Field/Value, inchangé), survoler l'espace autour (y compris près
    du label d'axe en bas, hors de portée d'une barre précise) déclenche
    le tooltip "Smells like" -- pas de survol dédié sur le LABEL D'AXE lui-
    même (Vega-Lite n'expose aucun canal d'encodage sur le texte d'axe
    natif, contrairement à la roue d'arôme qui dessine ses propres labels
    en `mark_text` avec coordonnées calculées à la main) : cette colonne
    invisible pleine hauteur est le substitut robuste retenu, une cible de
    survol plus large que le seul label, pas plus fragile à positionner."""
    if not rows:
        return None
    descriptors = descriptors or {}
    field_order = primary_fields + secondary_fields
    axis_kwargs = {
        "labelAngle": _COMPARE_LABEL_ANGLE,
        "labelLimit": 300,
        "labelLineHeight": 12,
        "labelOverlap": False,
        "labelAlign": "right",
        "labelBaseline": "middle",
        # Vega-Lite ne coupe pas automatiquement un label sur un "\n" littéral
        # (constaté en direct : le JSON contient bien le vrai caractère, mais le
        # rendu restait tronqué sur une seule ligne) -- `labelExpr` doit renvoyer
        # un TABLEAU de chaînes pour que le mark texte sous-jacent bascule en
        # rendu multi-lignes ; `split()` fait exactement ça.
        "labelExpr": "split(datum.label, '\\n')",
    }
    x_enc = alt.X("Field:N", scale=alt.Scale(domain=field_order), title=None,
                  axis=alt.Axis(**axis_kwargs))
    offset_enc = alt.XOffset("Hop:N", scale=alt.Scale(domain=list(colors.keys())))
    color_enc = alt.Color("Hop:N", scale=alt.Scale(domain=list(colors.keys()),
                                                   range=list(colors.values())))
    tooltip = ["Hop:N", "Field:N", alt.Tooltip("Value:Q", format=".2f")]
    if any(f in descriptors for f in field_order):
        tooltip.append(alt.Tooltip("Descriptors:N", title="Smells like"))
        rows = [dict(r, Descriptors=descriptors.get(r["Field"], "—")) for r in rows]

    primary_rows = [r for r in rows if r["Field"] in primary_fields]
    secondary_rows = [r for r in rows if r["Field"] in secondary_fields]
    layers = []
    resolved_fields = [f for f in field_order if f in descriptors]
    if resolved_fields:
        # Couche invisible EN PREMIER (sous les barres, voir docstring) :
        # une colonne pleine hauteur par composé résolu, cible de survol
        # pour "Smells like" en dehors d'une barre précise.
        layers.append(
            alt.Chart(alt.Data(values=[{"Field": f, "Descriptors": descriptors[f]}
                                       for f in resolved_fields]))
            .mark_rect(opacity=0.001)
            .encode(x=x_enc, tooltip=["Field:N", alt.Tooltip("Descriptors:N", title="Smells like")]))
    if primary_rows:
        layers.append(
            alt.Chart(alt.Data(values=primary_rows)).mark_bar()
            .encode(x=x_enc, xOffset=offset_enc, color=color_enc, tooltip=tooltip,
                   y=alt.Y("Value:Q", title=primary_title)))
    if secondary_rows:
        layers.append(
            alt.Chart(alt.Data(values=secondary_rows)).mark_bar()
            .encode(x=x_enc, xOffset=offset_enc, color=color_enc, tooltip=tooltip,
                   y=alt.Y("Value:Q", title=secondary_title)))
    if not layers:
        return None
    chart = layers[0] if len(layers) == 1 else alt.layer(*layers).resolve_scale(y="independent")
    return chart.properties(width=_COMPARE_CHART_WIDTH, height=320)


def _aroma_wheel_compare(intensities: dict[str, dict[str, float]], vocabulary: list[str],
                         colors: dict[str, str]):
    """Version multi-houblons de `_aroma_wheel` (T58, 2026-08-19) : plusieurs
    polygones superposés (jusqu'à 5, un par houblon, couleur cohérente avec
    les barplots) sur les mêmes 15 axes/mêmes coordonnées calculées à la
    main (voir `_aroma_wheel` pour le détail de la géométrie et pourquoi
    `mark_arc` a été abandonné). `intensities` : {Hop (nom affiché déjà
    désambiguïsé) -> {descriptor: intensité}}, UNIQUEMENT les houblons ayant
    une donnée exploitable -- l'appelant filtre les houblons sans couverture
    Yakima et le signale explicitement (honnêteté d'abord), jamais un
    polygone à 0 fabriqué ici.

    Ne contredit PAS le rejet du radar en T4 (`by-descriptor`, comparaison
    de descripteurs BINAIRES où l'aire déforme sans info) : ici les axes
    sont des intensités QUANTITATIVES réelles sur un vocabulaire fixe, le
    cas d'usage pour lequel un radar overlay est justifié -- c'est aussi ce
    que fait BeerMaverick sur son propre outil de comparaison."""
    if not vocabulary or not intensities:
        return None
    dark = st.context.theme.type == "dark"
    text_color = "#f2f2f0" if dark else "#1a1a18"
    grid_color = "#5a5a56" if dark else "#3a3a38"

    n = len(vocabulary)
    r_max = 170.0
    label_radius = r_max + 30
    half_extent = label_radius + 40

    def _xy(i: int, value: float) -> tuple[float, float]:
        angle = (i / n) * 2 * math.pi - math.pi / 2
        r = (max(0.0, min(value, 100.0)) / 100.0) * r_max
        return r * math.cos(angle), r * math.sin(angle)

    spokes, labels = [], []
    for i, d in enumerate(vocabulary):
        angle = (i / n) * 2 * math.pi - math.pi / 2
        ex, ey = r_max * math.cos(angle), r_max * math.sin(angle)
        spokes.append({"x": 0.0, "y": 0.0, "x2": ex, "y2": ey})
        lx, ly = label_radius * math.cos(angle), label_radius * math.sin(angle)
        labels.append({"x": lx, "y": ly, "Descriptor": d,
                       "Definition": matching.AROMA_WHEEL_DEFINITIONS.get(d, "")})

    poly_rows = []
    for hop_name, intensity in intensities.items():
        pts = []
        for i, d in enumerate(vocabulary):
            val = intensity.get(d, 0.0)
            x, y = _xy(i, val)
            pts.append({"x": x, "y": y, "Hop": hop_name, "Descriptor": d,
                       "Intensity": val, "Order": i})
        pts.append(dict(pts[0], Order=n))
        poly_rows.extend(pts)

    domain = [-half_extent, half_extent]
    x_enc = alt.X("x:Q", axis=None, scale=alt.Scale(domain=domain))
    y_enc = alt.Y("y:Q", axis=None, scale=alt.Scale(domain=domain))
    color_enc = alt.Color("Hop:N", scale=alt.Scale(domain=list(colors.keys()),
                                                   range=list(colors.values())),
                          legend=alt.Legend(title="Hop"))

    # Surlignage au survol (demande utilisateur, 2026-08-19) : `hover`, un
    # selection_point Vega-Lite standard (`on="mouseover"`, `nearest=True`),
    # attaché à `points` (cible d'accroche -- cercles pleins de taille 50,
    # bien plus faciles à survoler avec précision qu'un simple trait de
    # ligne) et référencé en CONDITION dans `polygon_line`, layer SŒUR de la
    # même composition `layer` -- pattern standard Vega-Lite (cf. exemple
    # officiel "interactive multi-line tooltip") : un paramètre de sélection
    # déclaré sur une couche reste visible aux couches sœurs, pas besoin de
    # le redéclarer. `empty=True` (comportement par défaut) : tant qu'aucun
    # survol n'a eu lieu, la condition est vraie pour TOUS les houblons
    # (opacité pleine par défaut, rien de grisé avant interaction).
    #
    # Opacité des houblons NON survolés remontée de 0.15 à 0.55 (retour
    # utilisateur en direct : "all the non mouseover lines are not
    # visible" -- 0.15 les rendait quasi invisibles, contraire à l'objectif
    # qui est de FAIRE RESSORTIR le houblon survolé, pas de masquer les
    # autres). Pas de contrôle de z-index (mettre le trait survolé
    # visuellement AU-DESSUS des autres) : Vega-Lite compile un
    # `mark_line` multi-séries (`detail="Hop:N"`) en UN SEUL mark, dont
    # l'ordre d'empilement des sous-tracés est figé à la compilation par
    # l'ordre du domaine `color` -- il n'existe pas de canal d'encodage
    # Vega-Lite pour un z-index RÉACTIF au survol (le canal `order` ne
    # contrôle que l'ordre des points LE LONG d'un même tracé, pas
    # l'empilement entre tracés). Compensé par un contraste fort
    # (opacité pleine + trait 2.5x plus épais) plutôt qu'un vrai passage
    # au premier plan.
    # `clear="mouseout"` explicite : par défaut Vega-Lite ne réinitialise
    # PAS la sélection quand le curseur quitte le graphique (constaté en
    # direct -- le dernier houblon survolé restait en surbrillance figée
    # après être sorti de la zone du radar), seul le prochain survol la
    # met à jour. `mouseout` (déclenché quand le pointeur quitte tout
    # l'élément SVG du graphique, pas juste un point) rétablit l'état par
    # défaut (tout à opacité pleine) dès qu'on quitte le radar.
    hover = alt.selection_point(fields=["Hop"], on="mouseover", nearest=True, empty=True,
                                clear="mouseout")
    line_opacity = alt.condition(hover, alt.value(1.0), alt.value(0.55))
    line_width = alt.condition(hover, alt.value(5), alt.value(2))
    point_opacity = alt.condition(hover, alt.value(1.0), alt.value(0.55))
    point_size = alt.condition(hover, alt.value(110), alt.value(50))

    grid = (
        alt.Chart(alt.Data(values=spokes))
        .mark_rule(strokeWidth=1, stroke=grid_color)
        .encode(x=x_enc, y=y_enc, x2="x2:Q", y2="y2:Q")
    )
    polygon_line = (
        alt.Chart(alt.Data(values=poly_rows))
        .mark_line(order=True)
        .encode(x=x_enc, y=y_enc, order="Order:Q", color=color_enc, detail="Hop:N",
               opacity=line_opacity, strokeWidth=line_width)
    )
    points = (
        alt.Chart(alt.Data(values=[r for r in poly_rows if r["Order"] < n]))
        .mark_point(filled=True)
        .encode(x=x_enc, y=y_enc, color=color_enc, opacity=point_opacity, size=point_size,
               tooltip=["Hop:N", "Descriptor:N", alt.Tooltip("Intensity:Q", format=".0f")])
        .add_params(hover)
    )
    text = (
        alt.Chart(alt.Data(values=labels))
        .mark_text(fontSize=14, color=text_color)
        .encode(x=x_enc, y=y_enc, text="Descriptor:N",
               tooltip=["Descriptor:N", "Definition:N"])
    )
    return (
        (grid + polygon_line + points + text)
        .properties(width=_COMPARE_CHART_WIDTH, height=_COMPARE_CHART_WIDTH)
        .configure_view(strokeWidth=0)
    )


def _compare(con):
    """Nouvel outil GUI "Compare Hops" (T58, 2026-08-19, demande utilisateur
    explicite, inspiré de https://beermaverick.com/hops/hop-comparison-tool/
    -- fonctionnalité de référence, pas le design). Jusqu'à 5 houblons, une
    couleur cohérente par houblon sur les 3 graphiques (radar + 2 barplots),
    voir `_COMPARE_PALETTE`."""
    hops, comp, hop_desc, _ = matching.load(con)
    options = sorted(hops, key=lambda v: hops[v]["name"].lower())
    selected = st.multiselect(
        f"Hops to compare (up to {_COMPARE_MAX_HOPS})", options,
        format_func=lambda v: hops[v]["name"], max_selections=_COMPARE_MAX_HOPS)
    if not selected:
        st.write("Choose at least one hop.")
        return
    colors = {hops[v]["name"]: _COMPARE_PALETTE[i] for i, v in enumerate(selected)}

    st.subheader("Aroma wheel")
    vocabulary = _intensity_vocabulary(con)
    intensities = {}
    no_wheel_data = []
    for v in selected:
        intensity = matching.hop_aroma_intensity(con, v)
        if intensity and any(val > 0 for val in intensity.values()):
            intensities[hops[v]["name"]] = intensity
        else:
            no_wheel_data.append(hops[v]["name"])
    chart = _aroma_wheel_compare(intensities, vocabulary, colors)
    if chart is not None:
        st.altair_chart(chart, width="content", theme=None)
        st.caption(":material/info: Hover a label for its definition "
                  "(Yakima Chief Hop Sensory Ballot).")
    if no_wheel_data:
        st.caption(":material/info: No quantitative aroma wheel data for: "
                  + ", ".join(no_wheel_data) +
                  " (BarthHaas only, or variety not covered by Yakima).")

    st.subheader("Principal info")
    principal_rows = []
    for v in selected:
        name = hops[v]["name"]
        for field, value in _compare_principal_values(comp.get(v, {})).items():
            if value is not None:
                principal_rows.append({"Hop": name, "Field": field, "Value": value})
    principal_chart = _compare_dual_axis_barplot(
        principal_rows, ["Alpha acids", "Beta acids", "Co-humulone\n(% of hop)"], "Percent (%)",
        ["Total oil\n(ml/100g)"], "Total oil (ml/100g)", colors)
    if principal_chart is not None:
        st.altair_chart(principal_chart, width="content")
    else:
        st.write("No principal composition data for the selected hops.")

    st.subheader("Detailed composition")
    # Bascule relatif/absolu (2026-08-21, demande utilisateur explicite,
    # suggestion reprise telle quelle : "Compare Hops separates total oil...
    # from composition (% of oil)... the reader has both numbers in front of
    # them but in two different charts, and has to do the multiplication in
    # their head"). ON par défaut : deux houblons à 48%/35% de myrcène
    # peuvent s'inverser en absolu si leur huile totale (barplot "Principal
    # info" juste au-dessus) diffère assez -- répondre directement à
    # l'écran plutôt que de laisser le lecteur faire le calcul. Aucune
    # nouvelle donnée : `total_oil` est déjà réconcilié par `matching.load()`
    # (même valeur que la barre "Total oil" du barplot principal). Thiols
    # exclus de la conversion (déjà en µg/kg, absolu dans les deux modes --
    # `_compare_detail_value` ne convertit que l'unité `pct_oil`).
    show_absolute = st.toggle(
        "Show absolute amount (ml/100g) instead of % of oil",
        value=True, key="compare_absolute_oil")
    present_oil_compounds = [c for c in _COMPARE_DETAIL_OIL_COMPOUNDS
                             if any(comp.get(v, {}).get(c, {}).get("mid") is not None
                                    for v in selected)]
    detail_rows = []
    missing_oil = []
    for v in selected:
        name = hops[v]["name"]
        hcomp = comp.get(v, {})
        for c in present_oil_compounds:
            val = _compare_detail_value(hcomp, c, show_absolute)
            if val is not None:
                detail_rows.append({"Hop": name, "Field": c, "Value": val})
            elif show_absolute and hcomp.get(c, {}).get("mid") is not None:
                # Composé mesuré (% d'huile) mais `total_oil` inconnu pour CE
                # houblon -- pas de conversion possible, jamais une barre
                # fabriquée à partir d'une huile totale devinée.
                missing_oil.append(name)
        thiols_val = _compare_detail_value(hcomp, _COMPARE_THIOLS_COMPOUND, show_absolute)
        if thiols_val is not None:
            detail_rows.append({"Hop": name, "Field": _COMPARE_THIOLS_COMPOUND, "Value": thiols_val})
    thiols_fields = [_COMPARE_THIOLS_COMPOUND] if any(
        r["Field"] == _COMPARE_THIOLS_COMPOUND for r in detail_rows) else []
    primary_title = "Amount (ml/100g)" if show_absolute else "Percent of oil (%)"
    # Tooltip descripteurs par composé (T70, 2026-08-21, demande utilisateur
    # explicite -- "myrcene est une chaîne nue, rien ne dit qu'elle couvre
    # vert, herbacé, résineux et pin", même pattern que la roue d'arôme) :
    # jointure CAS via `matching.compound_descriptors`, jamais par nom de
    # chaîne. Pas tous les composés n'ont une entrée Flavornet (734 composés
    # -- voir sa docstring) : `_compare_dual_axis_barplot` affiche "—" pour
    # ceux non résolus, jamais une valeur inventée.
    descriptors = matching.compound_descriptors(con, present_oil_compounds + thiols_fields)
    detail_chart = _compare_dual_axis_barplot(
        detail_rows, present_oil_compounds, primary_title,
        thiols_fields, "Thiols (µg/kg)", colors, descriptors=descriptors)
    if detail_chart is not None:
        st.altair_chart(detail_chart, width="content")
        if descriptors:
            st.caption(":material/info: Hover a bar, or the space near/below "
                      "a compound's label, for its Flavornet odor descriptors "
                      "(not every compound has an entry).")
    else:
        st.write("No detailed composition data for the selected hops.")
    if missing_oil:
        st.caption(":material/info: Total oil unknown for: " + ", ".join(sorted(set(missing_oil)))
                  + " — their % of oil composition can't be converted to an absolute amount.")


def main():
    # Nom d'affichage GUI = "HopFinder" (demande utilisateur 2026-08-19,
    # renommage d'affichage seulement -- le paquet/CLI restent "hopmatch",
    # voir CLAUDE.md et le sous-titre de README.md).
    st.set_page_config(page_title="HopFinder", page_icon="🌿")
    _inject_background()
    if "_next_mode" in st.session_state:
        # Relais utilisé par la page d'accueil (_home) : Streamlit interdit
        # de modifier st.session_state["mode"] une fois le widget radio
        # (key="mode") déjà instancié dans CE run -- consommé ici, avant sa
        # création. (L'ancien relais _next_browse_hop, pour la navigation
        # directe résultat -> Browse, a été retiré en T-nav-v2 : il faisait
        # perdre le contexte de la page amplify/contrast en cours, remplacé
        # par des expanders de détail affichés directement sur place — voir
        # `_hop_detail_expanders`.)
        st.session_state["mode"] = st.session_state.pop("_next_mode")
    st.title("HopFinder")
    st.caption("Aroma note → molecules → hops")

    db_path = _db_path()
    if not os.path.exists(db_path):
        _fetch_remote_db(db_path)
    if not os.path.exists(db_path):
        st.error(f"Database not found: `{db_path}`. Build the database on the "
                 f"CLI side first (`hopmatch build`, or "
                 f"`crawl-barthhaas`/`crawl-yakima`/`ingest-*`), or configure "
                 f"`{_DB_SOURCE_URL_SECRET}`/`{_DB_SOURCE_TOKEN_SECRET}` in "
                 f"`st.secrets` to fetch a pre-built one.")
        st.stop()
    con = _connection(db_path)

    # Contexte base (T6 backlog) : la construction se fait entièrement en CLI,
    # hors de la vue GUI — sans ça, rien n'indique si la base ouverte est la
    # démo (`hopmatch build`, 4 houblons) ou une base réelle, ni sa fraîcheur.
    # Lien GitHub en tête de sidebar (`st.sidebar.page_link`) ajouté le
    # 2026-08-19 puis RETIRÉ le 2026-08-20 (demande utilisateur, une fois le
    # déploiement Streamlit Community Cloud en place) : Streamlit Cloud
    # affiche déjà sa propre icône GitHub, cliquable, en haut à droite de la
    # barre d'outils de l'app déployée -- redondant avec un second lien
    # ajouté à la main. Licence/contact restent en sidebar (voir ci-dessous) :
    # cette info-là n'a pas d'équivalent dans le chrome Streamlit.
    # Licence/contact visible dans l'app elle-même, pas seulement dans le
    # README du dépôt (2026-08-20, demande utilisateur -- déploiement public
    # sur des données en partie non-commerciales, FooDB/FlavorDB2 CC BY-NC-SA)
    # : la personne concernée par un signalement de licence regarde l'app
    # déployée, pas nécessairement le dépôt GitHub associé.
    st.sidebar.caption(
        "Code MIT · [data licenses](https://github.com/quentinba/HopFinder"
        "#licences) · [quentin4313@gmail.com](mailto:quentin4313@gmail.com)")

    stats = _stats(con)
    modified = datetime.fromtimestamp(_db_version(db_path)).strftime("%Y-%m-%d %H:%M")
    st.sidebar.caption(
        f"**{db_path}** — {stats['hops']} hops, {stats['notes']} notes, "
        f"{stats['descriptors']} descriptors · modified {modified}")

    mode = st.sidebar.radio(
        "Mode", ["home", "amplify", "contrast", "by-descriptor", "browse", "compare"],
        format_func=lambda m: MODE_LABELS[m], key="mode")

    if mode == "home":
        st.header(MODE_LABELS[mode])
        _home(con)
        return

    if mode == "by-descriptor":
        st.header(MODE_LABELS[mode])
        _by_descriptor(con)
        return

    if mode == "contrast":
        st.header(MODE_LABELS[mode])
        _contrast(con)
        return

    if mode == "browse":
        st.header(MODE_LABELS[mode])
        _browse(con)
        return

    if mode == "compare":
        st.header(MODE_LABELS[mode])
        _compare(con)
        return

    # "amplify" : seul mode restant après les dispatches explicites
    # ci-dessus -- la sélection de note vit désormais DANS `_amplify` (page
    # principale, pas la sidebar, voir son commentaire), donc plus rien à
    # faire ici que le header, comme les autres modes.
    st.header(MODE_LABELS[mode])
    _amplify(con)


if __name__ == "__main__":
    main()
