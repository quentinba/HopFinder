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
import itertools
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

# Logo (demande utilisateur, 2026-08-22) : image fournie par l'utilisateur
# (fond crème opaque). Une version fond-transparent a été essayée puis
# retirée le même jour (2e addendum) : "it doesn't work in dark theme" --
# constaté en direct par l'utilisateur dans l'app déployée (contrairement à
# l'aperçu composité statique utilisé pour la valider, voir CLAUDE.md) ;
# fond original CONSERVÉ tel quel désormais, jamais modifié.
_LOGO_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "logo.png")

# Icône d'onglet navigateur (favicon), demande utilisateur explicite le même
# jour : "Use this for the table logo" [sic, "tab logo"] -- image DISTINCTE
# du logo principal (assets/mini_logo.jpeg, fond noir, icône houblon seule,
# fournie par l'utilisateur), plus adaptée qu'un lockup horizontal large à
# un favicon carré minuscule. `mini_logo_square.png` -- recadrage carré
# CENTRÉ SUR L'ICÔNE (pas sur le canevas 1408×768, décalé) : bbox du contenu
# calculé par seuil de luminosité (>25/255) pour trouver le centre réel de
# l'icône avant de découper, jamais un simple crop au centre géométrique du
# fichier source.
_TAB_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "mini_logo_square.png")

# Libellés GUI affichés à l'utilisateur, distincts des clés internes ("mode")
# qui pilotent le dispatch et restent stables (CLI/tests/URLs internes non
# concernés — habillage d'affichage uniquement, demandé par l'utilisateur).
# T-D12 (2026-08-23, spec Claude Design : "drop the 'HopFinder - ' prefix in
# page titles (the logo is right there)") -- libellés RACCOURCIS, utilisés à
# la fois pour le h1 de chaque page et le libellé de nav en sidebar (spec :
# "Sidebar labels stay descriptive"). Clés internes (`mode`) inchangées --
# voir la règle §0 de la spec, "Internal mode keys... may not [change]".
MODE_LABELS = {
    "home": "Home",
    "amplify": "Amplify",
    "contrast": "Contrast",
    "by-descriptor": "From descriptors",
    "browse": "Browse a hop",
    "compare": "Compare hops",
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

# T-D12 (2026-08-23, spec Claude Design) : lookup mode -> résumé, pour le
# "one-line purpose" + l'expander "How does this work?" affichés en tête de
# CHAQUE page d'outil (`main()`) -- avant, `_TOOL_SUMMARIES` n'était consommé
# que par `_home` (la longue description ne vivait QUE sur Home, jamais sur
# la page de l'outil lui-même).
_TOOL_SUMMARY_BY_MODE = {t["mode"]: t for t in _TOOL_SUMMARIES}

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
    ("2026-08-23", "New visual design across the whole app (warm cream/"
                   "terracotta/sage palette, new typography, a redesigned "
                   "background): coverage/orphan-molecule/truncation "
                   "warnings are now compact colored chips instead of "
                   "stacked alert boxes; purpose, descriptors and data "
                   "sources render as small pills everywhere; result "
                   "tables show a real progress bar for scores and no "
                   "longer truncate long contributor/source lists; charts "
                   "share one consistent color palette; hop detail panels "
                   "follow the same fixed order everywhere; and the "
                   "busiest tool pages (Amplify, Contrast) group their "
                   "inputs into side-by-side columns to fit more on "
                   "screen."),
    ("2026-08-23", "Fixes and refinements to the BarthHaas integration: "
                   "aroma wheel source is now an explicit Yakima/BarthHaas "
                   "toggle everywhere a spider chart appears (Browse, "
                   "Amplify/Contrast/By-descriptor detail, Compare Hops), "
                   "defaulting to Yakima unless it's missing for that hop "
                   "(then BarthHaas), with a warning naming any hop missing "
                   "from the currently selected database instead of just "
                   "showing an empty chart. Descriptor lists in Browse and "
                   "hop-detail views are now grouped one line per source "
                   "instead of annotating every single word. Also corrected "
                   "two BarthHaas descriptor data issues: a stray \"analyses\" "
                   "entry from a parsing bug, and \"camomile blossom\" "
                   "restored as its own term instead of being collapsed into "
                   "\"chamomile\"."),
    ("2026-08-22", "BarthHaas now contributes real aroma data: a "
                   "qualitative descriptor list and a quantitative aroma "
                   "wheel (rescaled to match Yakima's 0-100 scale), "
                   "previously undiscovered on their site. Each hop's "
                   "spider chart resolves to one source automatically "
                   "(never blended), with a manual BarthHaas/Yakima toggle "
                   "next to every spider chart (Browse, Amplify/Contrast/"
                   "By-descriptor detail, and Compare Hops)."),
    ("2026-08-22", "Added the HopFinder logo (sidebar on every page, and "
                   "the top of the Home page) and a matching browser tab "
                   "icon; removed the redundant \"HopFinder\" title and "
                   "\"Aroma note → molecules → hops\" caption that used to "
                   "sit above each tool's own heading."),
    ("2026-08-22", "\"Sources\" split into \"Composition sources\" and "
                   "\"Descriptor sources\" everywhere both appear (Amplify, "
                   "Contrast, blends, By-descriptor, Browse) — a hop's "
                   "aroma tags often come from a different source than its "
                   "composition data, and showing one label for both was "
                   "misleading."),
    ("2026-08-22", "Amplify: results table now splits \"Molecular "
                   "contributors\" and \"Descriptor contributors\" into "
                   "separate columns (each shown only when that layer "
                   "actually counts), and a new \"How to rank hops?\" "
                   "Descriptors/Both/Molecular-only control replaces the "
                   "old nested checkboxes."),
    ("2026-08-22", "Contrast: new optional \"Ingredient\" picker at the top "
                   "auto-fills the descriptor list below (editable), same "
                   "AI-assisted mapping as Amplify — no need to type "
                   "descriptors by hand anymore."),
    ("2026-08-22", "Amplify reworked: pick an \"Ingredient\" and its typical "
                   "aroma descriptors now auto-fill (editable) as the main "
                   "signal; molecular similarity + --oav become an optional "
                   "checkbox instead of the default."),
    ("2026-08-22", "Amplify: new \"How does the molecular score work?\" "
                   "expander explains the TF-IDF + --oav math step by step, "
                   "and the --oav checkbox now defaults on/off per note "
                   "based on that note's own --oav coverage, instead of "
                   "always defaulting on."),
    ("2026-08-22", "--oav thresholds are now resolved live from FlavorDB2 "
                   "(never hardcoded) and Amplify shows an --oav coverage "
                   "caption/warning naming any molecule left at a neutral "
                   "weight for lack of a sourced threshold."),
    ("2026-08-21", "Added a \"What do these Process labels mean?\" legend "
                   "next to the Process badge (Browse and Compare Hops), "
                   "explaining e.g. why sesquiterpenes say \"contributes "
                   "via oxidation\" instead of \"survives boiling\"."),
    ("2026-08-21", "New \"Process\" badge on Browse and Compare Hops: which "
                   "compounds actually survive to dry hop vs. mostly vanish "
                   "on a 60-min boil, sourced from Scott Janish's The New "
                   "IPA — a qualitative prior, never a numeric transfer "
                   "rate, never used in any score."),
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
    st.caption(f"{stats['hops']} hops, {stats['notes']} notes, "
              f"{stats['descriptors']} descriptors available. Choose a tool:")
    # T-D13 (2026-08-23, spec Claude Design : "Home is a launcher, not a
    # changelog page... 2 lines max of description") -- la longue prose par
    # outil (`tool["description"]`) est retirée d'ici, déplacée dans
    # l'expander "How does this work?" de CHAQUE page d'outil (`main()`,
    # voir `_TOOL_SUMMARY_BY_MODE`) : la carte Home ne garde que titre +
    # tagline + bouton, le lecteur qui clique "Open" trouve le détail
    # au bon endroit plutôt que de le lire deux fois.
    cols = st.columns(2)
    for i, tool in enumerate(_TOOL_SUMMARIES):
        with _panel(cols[i % 2]):
            st.subheader(f"{tool['icon']} {MODE_LABELS[tool['mode']]}")
            st.caption(tool["tagline"])
            if st.button("Open", key=f"home_open_{tool['mode']}",
                        icon=":material/arrow_forward:"):
                # Streamlit interdit de modifier st.session_state["mode"] une
                # fois le widget radio (key="mode") déjà instancié dans CE run
                # -- clé de relais consommée en tout début de main(), avant la
                # création du radio, sur le run suivant.
                st.session_state["_next_mode"] = tool["mode"]
                st.rerun()

    # T-D13 (2026-08-23, spec Claude Design) : "Recent updates" replié dans
    # un expander plutôt qu'une section pleine page en bas de Home ("Home is
    # a launcher, not a changelog page") -- contenu de `_RECENT_UPDATES`
    # inchangé, juste replié par défaut. Plus de `st.divider()` (spec §3 :
    # "no st.divider() at all -- the surface change already separates").
    with _panel_expander("Recent updates"):
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


@st.cache_data
def _cached_intensity_vocabulary_for_sources(_con, db_path: str, _version: float,
                                             sources: tuple[str, ...]) -> list[str]:
    return matching.aroma_wheel_vocabulary(_con, set(sources))


def _intensity_vocabulary_for_sources(con, sources: set[str]) -> list[str]:
    # T79 addendum (signalé en direct par l'utilisateur : "Melon/stone
    # fruit/earthy/dried fruit are not existing in the brathaas chart,
    # hence you should remove these categories") -- axes du graphique
    # restreints aux catégories que LA/LES source(s) réellement affichée(s)
    # peuvent porter (voir `matching.aroma_wheel_vocabulary`), plutôt que le
    # vocabulaire complet 16 catégories toutes sources confondues (celui-ci
    # reste utilisé tel quel par `_intensity_vocabulary`/les pills de
    # sélection `by-descriptor`, source-agnostiques par nature).
    if not sources:
        return _intensity_vocabulary(con)
    db_path = _db_path()
    return _cached_intensity_vocabulary_for_sources(
        con, db_path, _db_version(db_path), tuple(sorted(sources)))


def _stats(con) -> dict:
    db_path = _db_path()
    return _cached_stats(con, db_path, _db_version(db_path))


@st.cache_data
def _background_mask_data_uri(path: str, _version: float) -> str | None:
    """Convertit l'image de fond en MASQUE alpha (PNG, alpha = 255 -
    luminance, RGB non pertinent pour un `mask-image`) au lieu d'une photo
    couleur -- Design Claude (T-D02, 2026-08-23, spec `DESIGN_SPEC.md` §4).
    Remplace l'ancien double payload couleur/négatif (`_background_data_uri`,
    JPEG normal + JPEG inversé par PIL) : un seul asset, la COULEUR vient
    désormais du thème CSS (`var(--secondary-background-color)` posée par
    `_inject_background`), pas de l'image -- la gravure se reteinte donc
    seule par thème, en CSS pur, sans script ni deuxième fichier. Mis en
    cache par mtime (même schéma que `_cached_stats`/etc.) ; `None` si le
    fichier est absent (image optionnelle, pas d'erreur bloquante)."""
    if not os.path.exists(path):
        return None
    luminance = Image.open(path).convert("L")
    alpha = luminance.point(lambda p: 255 - p)
    mask = Image.merge("RGBA", (alpha, alpha, alpha, alpha))
    buf = io.BytesIO()
    mask.save(buf, format="PNG", optimize=True)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# T-D03 (2026-08-23, spec Claude Design `DESIGN_SPEC.md` §3) : Caprasimo
# (h1 SEULEMENT -- "at h3 inside a dense results panel it becomes noise")
# et `tabular-nums` (alignement des chiffres en colonne, tableaux/metrics)
# sont les deux seules choses que `.streamlit/config.toml` ne peut pas
# exprimer (une seule police de titre pour TOUS les niveaux). INCONDITIONNEL
# (pas dans le template du masque ci-dessous, qui lui dépend de la présence
# du fichier image) -- la typographie ne doit jamais dépendre d'un asset
# optionnel.
_TYPOGRAPHY_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Caprasimo&display=swap');
[data-testid="stAppViewContainer"] h1 { font-family: 'Caprasimo', Figtree, sans-serif; }
[data-testid="stDataFrame"], [data-testid="stMetricValue"] {
    font-variant-numeric: tabular-nums;
}
/* T-D04 (2026-08-23, spec Claude Design §5) : fond opaque des cartes de
   section `_panel()`/`_panel_expander()` -- `st.container(border=True)`/
   `st.expander` n'ont PAS de fond opaque nativement (vérifié en direct :
   background rgba(0,0,0,0) même sous le thème Organic), seule la bordure
   et le radius (`baseRadius`, config.toml) viennent du thème. `light-dark()`
   plutôt qu'une variable CSS de thème (aucune n'existe, voir le docstring
   de `_inject_background`) -- même valeurs que la surface "raised" du
   thème (`secondaryBackgroundColor`, §3 : "Raised surface (widgets, cards,
   table header)"). Ciblage par SOUS-CHAÎNE de classe `st-key-panel_...`
   (seul hook stable pour un `st.container(border=True)`, voir `_panel`). */
div[class*="st-key-panel_"], details[class*="st-key-panel_"] {
    background-color: light-dark(#ebddc5, #2e2b25);
}
</style>
"""

_BACKGROUND_STYLE_TEMPLATE = """
<style>
[data-testid="stAppViewContainer"] { position: relative; }
[data-testid="stAppViewContainer"]::before {
    content: "";
    position: fixed;
    inset: 0;
    background-color: light-dark(__LIGHT_GROUND__, __DARK_GROUND__);
    opacity: 0.35;
    mask-image: url("__MASK_URI__");
    -webkit-mask-image: url("__MASK_URI__");
    mask-size: cover;
    -webkit-mask-size: cover;
    mask-position: center;
    -webkit-mask-position: center;
    mask-repeat: no-repeat;
    -webkit-mask-repeat: no-repeat;
    pointer-events: none;
    z-index: 0;
}
[data-testid="stAppViewContainer"] > .stAppViewBlockContainer,
[data-testid="stHeader"] { position: relative; z-index: 1; }
</style>
"""


# Ground colors du thème (`.streamlit/config.toml`, `secondaryBackgroundColor`
# clair/sombre) -- dupliqués ici en dur car AUCUNE variable CSS équivalente
# n'existe pour les récupérer sans JS (vérifié en direct, voir le docstring
# de `_inject_background`). Garder synchronisé avec `.streamlit/config.toml`
# si la palette change.
_GROUND_LIGHT = "#ebddc5"
_GROUND_DARK = "#2e2b25"


def _inject_background() -> None:
    """Image de fond derrière le contenu principal (demande utilisateur,
    T50). Réécrite en pure CSS (T-D02, 2026-08-23, spec Claude Design
    `DESIGN_SPEC.md` §4) : remplace le pipeline JS/PIL précédent (script
    injecté dans un `st.iframe` lisant `getComputedStyle` sur `.stApp` pour
    détecter le thème, deux images base64 -- normale et négatif couleur --
    voir l'historique complet de CE choix dans les versions antérieures de
    ce docstring, conservées dans l'historique git).

    **La spec proposait `var(--secondary-background-color)` -- vérifié en
    direct que cette variable (et toute variable CSS de couleur de thème)
    N'EXISTE PAS dans le DOM Streamlit réel (1.60.0)** : Streamlit peint ses
    couleurs via des classes "Emotion" (CSS-in-JS) qui embarquent des hex
    littéraux dans les règles générées, jamais de variable CSS exposée sur
    `:root`/`.stApp` (`getPropertyValue` renvoie `""` pour les 4 noms
    plausibles testés). Contournement qui respecte quand même la contrainte
    "aucun JS" de la spec : la fonction CSS native `light-dark(clair,
    sombre)`, qui résout sur la propriété CSS `color-scheme` -- OR `.stApp`
    a déjà un `color-scheme` calculé qui se met à jour INSTANTANÉMENT au
    sélecteur Light/Dark/System de Streamlit (fait déjà établi lors du
    premier pipeline JS, voir l'historique) et `color-scheme` est une
    propriété HÉRITÉE : le pseudo-élément `::before` du masque, descendant
    de `.stApp`, en hérite directement, sans script. `_GROUND_LIGHT`/
    `_GROUND_DARK` : les mêmes hex que `secondaryBackgroundColor` du thème
    (`.streamlit/config.toml`), dupliqués en dur puisqu'aucune variable ne
    les expose.

    La gravure n'est plus qu'un MASQUE alpha (voir `_background_mask_data_
    uri`) peint de la couleur du thème à 35% d'opacité -- un seul asset pour
    les deux thèmes, jamais de négatif couleur à générer. `position: fixed`
    sur un pseudo-élément `::before` (pas `background-image` direct sur
    `stAppViewContainer`) : évite tout recalcul de `background-size: cover`
    au changement de contenu (le piège de zoom déjà rencontré avec
    `background-attachment: local`, voir l'historique) -- `position: fixed`
    sur un pseudo-élément est stable par construction, ancré au viewport.
    `z-index` posé sur le contenu (`stAppViewBlockContainer`) et l'en-tête
    (`stHeader`) pour rester au-dessus du masque, qui n'occupe que
    `z-index: 0`."""
    html = _TYPOGRAPHY_STYLE
    if os.path.exists(_BACKGROUND_PATH):
        version = os.path.getmtime(_BACKGROUND_PATH)
        mask_uri = _background_mask_data_uri(_BACKGROUND_PATH, version)
        if mask_uri is not None:
            html += (
                _BACKGROUND_STYLE_TEMPLATE
                .replace("__MASK_URI__", mask_uri)
                .replace("__LIGHT_GROUND__", _GROUND_LIGHT)
                .replace("__DARK_GROUND__", _GROUND_DARK)
            )
    st.html(html)


_panel_counter = itertools.count()


def _panel(host=None, **kwargs):
    """Carte de SECTION à fond opaque (voir `_TYPOGRAPHY_STYLE`) -- T-D04
    (2026-08-23, spec Claude Design `DESIGN_SPEC.md` §5) : "one card per
    *logical section*... Never around a single st.write/st.caption. Never
    nested inside another card." Contrairement au premier passage de ce
    mécanisme (T80, abandonné -- voir CLAUDE.md), `_panel()` n'est PLUS
    appelé autour de chaque ligne de texte : seulement autour d'un bloc de
    section complet (inputs d'un outil, résultats, blends...). Clé
    `panel_N` (compteur réinitialisé à chaque rerun -- `app.py` est le
    script principal, réexécuté en entier à chaque interaction, donc l'ordre
    d'appel -- et les clés qui en découlent -- reste stable pour un état de
    page donné). `host` (optionnel) : conteneur/colonne parent, par défaut
    `st` (top niveau de la page) -- `_panel(cols[i])` pour une carte à
    l'intérieur d'une colonne."""
    host = host or st
    return host.container(border=True, key=f"panel_{next(_panel_counter)}", **kwargs)


def _panel_expander(label: str, **kwargs):
    """Même traitement que `_panel()` mais pour `st.expander` (accepte
    directement `key=`) -- le niveau "Detail" de la hiérarchie à trois
    surfaces (spec §5) : TOUJOURS à l'intérieur d'une carte de section,
    jamais imbriqué (pas d'expander dans un expander)."""
    return st.expander(label, key=f"panel_{next(_panel_counter)}", **kwargs)


def _confidence_strip(chips: list[tuple[str, str, str]]) -> None:
    """T-D05 (spec Claude Design §7) : remplace la pile `st.warning`/
    `st.caption` (couverture moléculaire, couverture --oav, troncature de
    résultats, avertissements de source) par UNE ligne de chips `st.badge`
    sous la carte d'inputs. `chips` : liste de (label, color, help) --
    `color` sage="green" ("fine", qualification honnête normale) ou
    terracotta="orange" ("read this", vaut la peine d'être noté) -- JAMAIS
    rouge, aucune de ces informations n'est une erreur. L'explication
    complète va dans `help=` (tooltip natif `st.badge`, pas un paragraphe
    affiché en dur). Rien n'est rendu si `chips` est vide (pas de carte
    vide)."""
    if not chips:
        return
    with _panel():
        with st.container(horizontal=True):
            for label, color, help_text in chips:
                st.badge(label, color=color, help=help_text)


# purpose (aromatic/bittering/both) : SEULE donnée BeerMaverick classant un
# houblon par usage (voir CLAUDE.md, section BeerMaverick) — demande
# utilisateur explicite (2026-08-19) : affichée comme info PRINCIPALE en
# Browse, et en colonne colorée sur les résultats amplify/contrast/blends.
# Couleurs `st.badge` (tokens sémantiques Streamlit, PAS des hex littéraux) :
# seule façon vérifiée de s'adapter au thème clair/sombre à la fois — un
# `pandas.Styler`/CSS littéral ne le ferait pas (couleur figée, ne s'inverse
# pas avec le thème).
_PURPOSE_LABELS = {"aromatic": "Aromatic", "bittering": "Bittering", "both": "Aromatic + Bittering"}
# T-D06 (spec Claude Design §7) : "aromatic = sage, bittering = terracotta,
# both = outlined with both" -- `st.badge` n'a qu'une seule variante remplie
# (pas de vrai contour bicolore possible sans CSS par instance, hors de
# portée de `st.badge` qui n'accepte pas de `key=`) : "both" passe donc en
# gris neutre (ni sage ni terracotta, jamais confondu avec un seul rôle),
# `Inferred:` rendu en italique (Markdown supporté par le label `st.badge`)
# pour rester "visuellement plus faible qu'une donnée mesurée" comme demandé,
# sans inventer une 4e couleur. Remplace l'ancien vert/orange/VIOLET --
# `violetColor` du thème Organic (`#728157`) est en réalité un ton sauge
# quasi identique à `greenColor` (`#7a8a5e`), "both" et "aromatic" étaient
# donc déjà visuellement indissociables avant ce ticket.
_PURPOSE_COLORS = {"aromatic": "green", "bittering": "orange", "both": "gray"}
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


def _descriptors_grouped_by_source(desc_by_source: dict[str, set[str]]) -> dict[str, list[str]]:
    """Inverse `{descripteur: {sources}}` (voir `matching.descriptor_sources`)
    en `{source: [descripteurs triés]}` -- demande utilisateur explicite
    (2026-08-23) : "one line per source (in bold) and list all the
    descriptors from that source", en remplacement du format `mot (source)`
    répété (trop verbeux dès qu'un houblon a beaucoup de descripteurs, ex.
    Citra : 15 mots x annotation individuelle vs 3 lignes groupées). Un
    descripteur porté par plusieurs sources apparaît sous CHACUNE d'elles
    (aucune perte d'information par rapport au format mot-par-mot -- juste
    regroupé différemment)."""
    by_source: dict[str, list[str]] = {}
    for d, srcs in desc_by_source.items():
        for s in (srcs or {"unknown"}):
            by_source.setdefault(s, []).append(d)
    return {s: sorted(ds) for s, ds in sorted(by_source.items())}


def _descriptor_chips(labels: list[str]) -> str:
    """Pills de descripteur (T-D06, spec Claude Design §7) -- "sage pill,
    used for every descriptor everywhere". `st.badge` est documenté comme un
    simple raccourci pour la directive Markdown `:color-badge[texte]` (voir
    sa docstring) : on l'utilise directement en chaîne plutôt qu'un appel
    `st.badge` par mot, pour pouvoir aligner N chips sur une seule ligne
    `st.markdown`/`st.caption` sans conteneur horizontal séparé."""
    return " ".join(f":green-badge[{label}]" for label in labels)


def _source_chips(labels: list[str]) -> str:
    """Pills de provenance (T-D06) -- "muted pills, one per source" : gris
    neutre, même mécanisme que `_descriptor_chips`."""
    return " ".join(f":gray-badge[{label}]" for label in labels)


def _purpose_badge(purpose: str | None, inferred: bool = False) -> None:
    if purpose is None:
        st.badge("Unknown", color="gray", icon=":material/help:")
        return
    label = _purpose_label(purpose, inferred)
    # T-D06 : italique pour un purpose INFÉRÉ -- "visually weaker than
    # measured data, on purpose" (spec §7) -- `_purpose_label` (texte brut,
    # partagé avec `_render_hop_rows`/`st.dataframe`, où le Markdown ne se
    # rend pas) reste inchangé, l'italique n'est appliquée qu'ici, au badge.
    if inferred:
        label = f"*{label}*"
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


def _render_hop_rows(rows: list[dict], columns: list[tuple]) -> None:
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
    par cellule, seulement du texte/nombre/liste) au profit d'un texte simple
    ("Aromatic"/"Inferred: Bittering"/...) via `_purpose_label` -- partagé
    avec `_purpose_badge`, qui reste inchangé et utilisé partout ailleurs
    (Browse, expanders de détail amplify/contrast/by-descriptor) : ces
    emplacements affichent un SEUL purpose à la fois, pas un tableau, donc
    le problème d'empilement mobile ne s'y pose pas.

    T-D07 (spec Claude Design §7, 2026-08-23) : `column_config` explicite au
    lieu d'une jointure `", ".join(...)` tronquée à l'affichage --
    `ProgressColumn` pour un score 0-100 ("score"), `NumberColumn` (format
    percent) pour une fraction 0-1 ("fraction"), `ListColumn` pour une liste
    de contributeurs/sources (les valeurs correspondantes doivent être de
    vraies listes Python désormais, plus des chaînes pré-jointes), Purpose
    en colonne étroite dédiée ("purpose").

    Réutilisé par les tableaux de résultats amplify/contrast/similar-hops ET
    les tableaux de blend. `rows` : dicts avec une clé "name" + les clés
    référencées par `columns`. Chaque entrée de `columns` : `(en-tête, clé)`
    pour du texte simple, ou `(en-tête, clé, kind)` avec `kind` dans
    {"score", "fraction", "list", "purpose"} pour un rendu typé -- "purpose"
    résout la clé en texte via `_purpose_label` (utilise aussi
    "purpose_inferred" si présent, voir `_row_with_purpose`), les autres
    passent la valeur telle quelle à `column_config`."""
    column_config: dict = {"Hop": st.column_config.TextColumn(pinned=True)}
    table_rows = []
    for row in rows:
        entry = {"Hop": row["name"]}
        for col in columns:
            header, field = col[0], col[1]
            kind = col[2] if len(col) > 2 else "text"
            if kind == "purpose":
                entry[header] = _purpose_label(row.get("purpose"), row.get("purpose_inferred", False))
                column_config[header] = st.column_config.TextColumn(width="small")
            else:
                entry[header] = row.get(field, "")
                if kind == "score":
                    column_config[header] = st.column_config.ProgressColumn(
                        format="%.1f", min_value=0, max_value=100)
                elif kind == "fraction":
                    column_config[header] = st.column_config.NumberColumn(format="percent")
                elif kind == "list":
                    column_config[header] = st.column_config.ListColumn()
        table_rows.append(entry)
    st.dataframe(table_rows, width="stretch", hide_index=True, column_config=column_config)


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


def _process_survival_label(compound: str) -> str | None:
    """Libellé "Process" (badge de survie au procédé, T74, 2026-08-21,
    demande utilisateur explicite : "Un lecteur qui voit « myrcène 48 % »
    sur une fiche doit savoir que ce chiffre compte en dry hop et devient
    largement caduc sur une ébullition de 60 minutes") pour un composé, ou
    `None` si non mappé (`matching.process_survival`, jamais un placeholder
    "unknown" -- même principe que "Smells like" absent).

    Confiance BASSE rendue EXPLICITEMENT visible par un suffixe (demande
    utilisateur : "rendu visuellement distinct (grisé, ou suffixe
    explicite)" -- suffixe retenu, un `st.dataframe` ne permet pas de
    griser une cellule individuelle ; cohérent avec le préfixe "Inferred:"
    déjà utilisé pour `_purpose_label` sur une réserve de même nature).
    Confiance moyenne/haute affichées telles quelles, sans suffixe -- seule
    la confiance BASSE est explicitement demandée comme visuellement
    distincte."""
    info = matching.process_survival(compound)
    if info is None:
        return None
    label = info["annotation"]
    if info["confidence"] == "low":
        label += " (low confidence)"
    return label


def _process_survival_legend() -> None:
    """Légende "What do these Process labels mean?" (2026-08-21, demande
    utilisateur explicite : la différence entre "direct traces, contributes
    via oxidation" et "survives boiling" n'est pas évidente sans la chimie
    sous-jacente -- "I'm not sure to understand the difference"). Une
    phrase par annotation DISTINCTE (`reference.PROCESS_SURVIVAL_
    EXPLANATIONS`), dérivée des annotations RÉELLEMENT utilisées dans
    `reference.PROCESS_SURVIVAL` (jamais une entrée orpheline si une
    annotation change un jour). `st.expander` replié par défaut -- pas de
    bruit visuel pour qui ne se pose pas la question, disponible pour qui
    se la pose."""
    with st.expander("What do these Process labels mean?"):
        for annotation in sorted({v["annotation"] for v in matching.reference.PROCESS_SURVIVAL.values()}):
            explanation = matching.reference.PROCESS_SURVIVAL_EXPLANATIONS.get(annotation)
            if explanation:
                st.write(f"**{annotation}** — {explanation}")


# T79, 4e addendum (2026-08-23, demande utilisateur explicite : "put a
# Toggle button Yakima <> Brathaas. Put on Yakima by default... if the hop
# is missing... a warning message explaining that the hop arome wheel is
# not in this database") : REMPLACE le mécanisme précédent (résolution
# automatique + case à cocher "prefer BarthHaas" optionnelle, masquée sauf
# si les deux sources existent) -- l'utilisateur veut un choix EXPLICITE
# et TOUJOURS visible, avec un avertissement clair quand la source
# choisie ne couvre pas le(s) houblon(s) affiché(s), plutôt qu'un repli
# silencieux vers l'autre source ou une roue qui disparaît sans
# explication. Toujours PAS de choix par houblon dans les vues à N
# houblons (heatmap by-descriptor, scoring `similar_hops`) -- la
# résolution automatique (`matching.resolve_aroma_intensity`) y reste
# inchangée, ce toggle ne concerne que l'AFFICHAGE d'une roue (houblon
# unique partout, ou Compare où un seul toggle s'applique à tous les
# houblons sélectionnés à la fois).
def _aroma_wheel_toggle(default_source: str, key: str) -> str:
    """Toggle Yakima<>BarthHaas explicite (`st.segmented_control`, cohérent
    avec le "How to rank hops?" d'Amplify -- un choix EXCLUSIF entre peu
    d'options, pas une case à cocher). `default_source` ne fixe que la
    valeur INITIALE du widget (voir `matching.default_aroma_wheel_source`/
    `..._for_varieties`) -- l'utilisateur reste libre de basculer,
    `required=True` pour ne jamais retomber sur `None` (un choix est
    toujours actif)."""
    default_label = "BarthHaas" if default_source == "barthhaas" else "Yakima"
    choice = st.segmented_control("Aroma wheel source", ["Yakima", "BarthHaas"],
                                  default=default_label, key=key, required=True)
    return "barthhaas" if choice == "BarthHaas" else "yakima"


def _aroma_wheel_source_caption(source: str) -> str:
    if source == "barthhaas":
        return (":material/info: Hover a label for its definition. Aroma wheel source: "
                "BarthHaas (rescaled to a comparable 0-100 range from their own 0-8 scale).")
    return (":material/info: Hover a label for its definition. Aroma wheel source: "
           "Yakima Chief Hop Sensory Ballot.")


def _aroma_wheel_missing_warning(missing_names: list[str], source: str) -> None:
    """Chip listant les houblons affichés qui n'ont PAS de lecture exploitable
    dans la source ACTUELLEMENT choisie par le toggle -- demande utilisateur
    explicite (2026-08-23), aussi bien pour un houblon unique (liste à 1
    élément) que pour Compare Hops (plusieurs). T-D05 (spec Claude Design) :
    `st.badge` terracotta au lieu d'un `st.warning` plein cadre -- appelée
    depuis des surfaces variées (panel, expander) qui fournissent déjà leur
    propre carte, donc pas de `_confidence_strip`/`_panel()` ici (jamais de
    carte imbriquée)."""
    if not missing_names:
        return
    label = "BarthHaas" if source == "barthhaas" else "Yakima"
    st.badge(f"Not in the {label} database: {', '.join(missing_names)}",
             color="orange", icon=":material/info:")


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
    # T77 (2026-08-22, demande utilisateur explicite -- confusion vérifiée
    # en direct sur "enigma" : "the source is barthhaas... does berry come
    # from this only?") : `st.caption(f"Sources: {hops[v]['sources']}")`,
    # affichée juxtaposée à la liste des descripteurs, laissait croire que
    # cette provenance couvrait AUSSI les descripteurs -- `hops[v]['sources']`
    # n'a toujours été que la provenance de la COMPOSITION (`hops` table).
    # Descripteurs groupés par LEUR PROPRE source (`hop_descriptors.source`,
    # jamais gardée par `hop_desc` -- simple `set[str]` utilisé pour des
    # opérations d'ensemble ailleurs, voir `matching.descriptor_sources`).
    # T-D10 (2026-08-23) a depuis déplacé "Composition: ..." en dernier dans
    # l'ordre fixe (voir plus bas) -- toujours sa PROPRE ligne, jamais
    # rapprochée des descripteurs, pour la même raison.
    desc_src = matching.descriptor_sources(con)
    all_intensity = matching.load_aroma_intensity(con)
    for row in rows:
        v = row["variety"]
        with st.expander(f"{row['name']} — {row['caption']}"):
            # T-D10 (2026-08-23, spec Claude Design §7) : ordre FIXE -- "purpose
            # chip -> key stats -> wheel block -> descriptors by source ->
            # composition table -> sources" -- identique dans
            # `_hop_detail_expanders`/`_browse`/`_by_descriptor`.
            purpose, inferred = matching.resolve_purpose(hops[v].get("purpose"), comp.get(v, {}))
            _purpose_badge(purpose, inferred)
            _render_key_stats(comp.get(v, {}))
            by_source = all_intensity.get(v, {})
            source = _aroma_wheel_toggle(matching.default_aroma_wheel_source(by_source),
                                         key=f"aroma_source_expander_{v}")
            intensity = matching.select_aroma_intensity(by_source, source)
            if intensity:
                vocab = _intensity_vocabulary_for_sources(con, {source})
                st.altair_chart(_aroma_wheel(intensity, vocab), width="content")
                st.caption(_aroma_wheel_source_caption(source))
            else:
                _aroma_wheel_missing_warning([hops[v]["name"]], source)
            descs = sorted(hop_desc.get(v, set()))
            if descs:
                # T79 addendum (2026-08-23, même demande que Browse : "one
                # line per source (in bold)... bold for the 'Descriptor' and
                # the name of the source, not the notes themselves").
                desc_by_source = _descriptors_grouped_by_source(desc_src.get(v, {}))
                st.markdown("**Descriptors**  \n" + "  \n".join(
                    f"**{s}:** " + _descriptor_chips(ds) for s, ds in desc_by_source.items()))
            else:
                st.write("**Descriptors:** none recorded")
            hcomp = comp.get(v, {})
            crows = sorted(
                ({"Compound": c, "Value": round(cv["mid"], 3), "Unit": cv["unit"],
                  "Sources": ", ".join(cv["sources"]),
                  "Smells like": compound_smells.get(c, "—"),
                  "Process": _process_survival_label(c) or "—"}
                 for c, cv in hcomp.items()
                 if c not in matching.NON_AROMA_DISPLAY and cv["mid"] is not None),
                key=lambda r: -r["Value"])
            if crows:
                st.dataframe(crows[:8], width="stretch", hide_index=True)
            # T-D06 (spec Claude Design §7) : pills grises, une par source.
            st.caption("Composition: " + _source_chips(hops[v]["sources"].split(",")))


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


def _molecular_score_explainer() -> None:
    """Explication du score moléculaire TF-IDF + --oav (T76, 2026-08-22,
    demande utilisateur explicite : "How this score is working in practice?
    ... Can you explain me more precisely how the amplify function is
    working on a molecular perspective" -- suite directe de T75, l'ajout de
    la couverture --oav ayant révélé que le mécanisme lui-même n'était pas
    clair). Contenu statique (ne dépend pas de la note sélectionnée),
    `st.expander` replié par défaut -- même principe que `_process_survival_
    legend` (T74) : pas de bruit pour qui ne se pose pas la question.

    Adapté d'un brouillon fourni par l'utilisateur, avec DEUX corrections
    factuelles apportées avant publication (jamais republié tel quel sans
    vérification, cohérent avec la discipline du projet) :
    (1) le brouillon citait "thiols, cétones, isobutyrate" comme groupe
    touché par le biais de neutralité --oav ; vérifié dans reference.py :
    seuls les thiols sont dans `reference.MOLECULES` (CID=None -> jamais de
    seuil --oav) ; "ketones"/"isobutyrate" n'existent que côté `PROCESS_
    SURVIVAL`/`JANISH_COMPOUND_CATEGORIES` (badge Process, T74), pas dans le
    scoring moléculaire/--oav -- affirmation corrigée pour ne citer QUE les
    thiols, dont c'est vérifiable ci-dessous.
    (2) l'exemple chiffré du brouillon affirmait "l'écart se resserre" avec
    --oav (1,20× cité comme le cas AVEC --oav contre 1,44× SANS) ; recalculé
    à la main ET par script (`amount`/`specificity` réels sur les mêmes
    chiffres) : c'est l'inverse -- SANS --oav le ratio A/B est 1,20 (B
    atteint 83,4% de A), AVEC --oav il est 1,44 (B tombe à 69,7% de A) --
    l'écart s'élargit ici, pas l'inverse. Narration corrigée en conséquence ;
    le reste de l'arithmétique du brouillon (TF/IDF/multiplicateurs/totaux)
    était juste, revérifié terme à terme."""
    with st.expander("How does the molecular score work? (TF-IDF + --oav explained)"):
        st.markdown(
            "**The problem.** Simply counting shared molecules doesn't work: "
            "myrcene is present, at high amounts, in almost every hop — it "
            "would dominate every ranking regardless of which note you're "
            "matching, the same way \"the\"/\"a\" would dominate a plain "
            "word-count search. The molecular score borrows a fix from text "
            "search (TF-IDF): a molecule's weight depends on how much of it "
            "a hop has *relative to other hops*, and how *rare* it is across "
            "hops — never on its raw quantity alone.")
        st.markdown(
            "| Text search | hopmatch |\n"
            "|---|---|\n"
            "| Query | The note (e.g. mango) |\n"
            "| Document | A hop |\n"
            "| Word | A molecule |\n"
            "| Corpus | The ~189 hops |\n"
            "| Stop word (\"the\", \"a\") | Myrcene — present almost "
            "everywhere, at high doses |")
        st.markdown("**Per molecule, per hop:**")
        st.latex(r"\text{contribution} = \text{note\_weight} \times TF \times IDF \times OAV")
        st.markdown(
            "- **note_weight** — how much this molecule matters for *this* "
            "note. Fixed, identical for every hop.\n"
            "- **TF** (term frequency) — `hop's amount ÷ richest hop's "
            "amount`, for *that molecule specifically*, across all hops. "
            "Between 0 and 1: \"what fraction of the record holder do I "
            "reach?\" Answers *am I rich in this molecule?* — not *how much "
            "do I have in absolute ppm.*\n"
            "- **IDF** (inverse document frequency) — "
            "`log(n_hops ÷ (1 + hops that have it)) + 1`. Answers *is this "
            "molecule informative?* A molecule in nearly every hop (myrcene) "
            "scores low; a rare one scores high. Same value for every hop — "
            "it's a property of the molecule, not the hop.\n"
            "- **OAV** (only with `--oav`, else 1.0) — "
            "`30 ÷ perception threshold (ppb)`. Answers *how little of it "
            "does it take to smell?* 30 ppb is an arbitrary reference point: "
            "a molecule with exactly that threshold gets a neutral 1.0×.")
        st.markdown("**What `--oav` does, and doesn't, do**")
        st.markdown(
            "- **It never filters anything.** A molecule with no sourced "
            "threshold doesn't disappear from the score — it gets exactly "
            "1.0× and keeps its full TF×IDF weight. `--oav` only changes "
            "*how loud* a molecule counts, never *whether* it counts.\n"
            "- **The direction is inverted — the usual source of "
            "confusion.** A *low* threshold means a *potent* molecule, so it "
            "gets a *high* multiplier: dividing by the threshold flips the "
            "sign for you.")
        st.markdown(
            "| Molecule | Threshold | 30 ÷ threshold |\n"
            "|---|---|---|\n"
            "| Geraniol | 39.5 ppb | 0.76 — mildly discounted |\n"
            "| β-pinene | 140 ppb | 0.21 — heavily discounted |\n"
            "| Thiols *(illustrative — see note below)* | ~0.06 ppb | "
            "500 — would be massively amplified |")
        st.markdown(
            "β-pinene is \"loud in concentration, quiet in perception\" — "
            "`--oav` corrects for that. **Known current bias:** thiols are "
            "hopmatch's most potent tracked compound by far, but they have "
            "no individually resolvable PubChem CID in this project's data — "
            "BarthHaas reports them as one combined field covering several "
            "molecules — so `--oav` can't resolve a sourced threshold for "
            "them either, and they stay stuck at the neutral 1.0× shown "
            "above instead of the outsized multiplier their real potency "
            "would justify. This is a data-source limitation, not a bug.")
        st.markdown(
            "**Illustrative example** *(hypothetical numbers, not real hop "
            "data — for teaching the mechanic only)*. A note weighing "
            "geraniol 0.332, myrcene 0.10, β-pinene 0.15, and two candidate "
            "hops:")
        st.markdown(
            "| | Geraniol | Myrcene | β-pinene |\n"
            "|---|---|---|---|\n"
            "| Hop A | 0.031 *(record holder)* | 0.40 | 0.005 |\n"
            "| Hop B | 0.010 | 0.65 *(record holder)* | 0.029 *(record holder)* |\n"
            "| Present in | 60/189 hops | 185/189 hops | 45/189 hops |\n"
            "| Threshold | 39.5 ppb | 13 ppb | 140 ppb |")
        st.markdown(
            "**Step 1 — raw amounts.** A = 0.436, B = 0.689. B \"wins\", but "
            "only because myrcene reads in much bigger raw numbers — exactly "
            "the failure mode TF-IDF exists to fix.\n\n"
            "**Step 2 — TF**, each molecule rescaled 0–1 against its own "
            "record holder: A → geraniol 1.00, myrcene 0.62, β-pinene 0.17. "
            "B → geraniol 0.32, myrcene 1.00, β-pinene 1.00.\n\n"
            "**Step 3 — IDF**: geraniol 2.13, myrcene 1.02 *(nearly neutral "
            "— it's everywhere)*, β-pinene 2.44.\n\n"
            "**Step 4 — contribution, without `--oav`.** "
            "A = 0.332×1.00×2.13 + 0.10×0.62×1.02 + 0.15×0.17×2.44 "
            "= 0.707 + 0.063 + 0.062 = **0.832**. "
            "B = 0.332×0.32×2.13 + 0.10×1.00×1.02 + 0.15×1.00×2.44 "
            "= 0.226 + 0.102 + 0.366 = **0.694**. A now leads — the "
            "raw-quantity \"winner\" B has dropped to second.\n\n"
            "**Step 5 — with `--oav`** (multipliers 0.76 / 2.31 / 0.21): "
            "A = 0.537 + 0.146 + 0.013 = **0.696**. "
            "B = 0.172 + 0.236 + 0.077 = **0.485**. A still leads — and the "
            "gap *widens*, not narrows: B's biggest asset was β-pinene "
            "(TF 1.00), and that's exactly the molecule `--oav` penalizes "
            "hardest here, since it takes a lot of it to actually smell it. "
            "OAV doesn't uniformly flatten every hop — it depends on which "
            "specific molecule each candidate happens to lean on.\n\n"
            "**Final normalization.** The best-scoring hop is always "
            "rescaled to exactly 100; every other hop is shown *relative to "
            "it*. Without `--oav`, B reaches 83.4% of A's score; with "
            "`--oav`, only 69.7%. A score of 100 means \"the best match "
            "among these candidates,\" never \"a perfect match\" in any "
            "absolute sense.")


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
    # T-D04 (2026-08-23, spec Claude Design) : "one card per logical
    # section... the input block". `panel_a` réutilisé (Streamlit permet de
    # rouvrir un `with` sur le MÊME conteneur plusieurs fois) à travers toute
    # la zone d'input de cet outil, malgré la logique métier interposée.
    panel_a = _panel()
    # T-D14 (2026-08-23, spec Claude Design §5, "group each tool's controls
    # into columns inside the inputs card") : Ingredient + "How to rank
    # hops?" côte à côte -- `rank_mode_col` créée ici, remplie plus bas (une
    # fois `rank_mode` calculé), Streamlit permet d'écrire dans un
    # conteneur déjà créé hors de son ordre d'apparition dans le code (même
    # principe que la réouverture de `panel_a` lui-même).
    with panel_a:
        note_col, rank_mode_col = st.columns(2)
    # T76 (2026-08-22, demande utilisateur explicite -- reframe complet du
    # tool) : "Note" renommé "Ingredient" en GUI ("note" ne parlait pas à
    # l'utilisateur -- c'est l'ADDITION réellement mise dans la recette,
    # ex. mangue, basilic). `note`/`aroma_notes`/le paramètre CLI restent
    # inchangés en interne (portée du renommage = label GUI uniquement,
    # même principe déjà appliqué au vocabulaire anglais de app.py).
    with note_col:
        note = st.selectbox("Ingredient", notes,
                            help="The actual addition put in the beer recipe "
                                 "(a fruit, herb, spice...).")

    hops, comp, hop_desc, _ = matching.load(con)
    # T77 (2026-08-22, demande utilisateur explicite -- confusion vérifiée
    # en direct sur "enigma" : "berry"/"raspberry" venaient de BeerMaverick,
    # jamais de BarthHaas, alors que la colonne "Sources" affichait
    # "barthhaas" seul -- provenance de la COMPOSITION, pas des
    # descripteurs) : provenance PAR DESCRIPTEUR, séparée de "sources"
    # (composition). Voir `matching.descriptor_sources`.
    desc_src = matching.descriptor_sources(con)
    profile = matching.get_note(con, note)
    producible, _, _ = matching.coverage(profile, comp)

    # Couche descripteurs = COUCHE PRINCIPALE désormais (T76, demande
    # utilisateur explicite : "I want you to put as a first layer the
    # descriptors and as an optional layer the molecular" -- la couche
    # moléculaire est jugée "less straightforward and more geeky/uncertain
    # empirically", donc plus le comportement par défaut). Pré-remplie
    # depuis `reference.INGREDIENT_DESCRIPTORS` (amorce IA T76, PAS une
    # dérivation FooDB -- voir le commentaire au-dessus du dict dans
    # reference.py) : jamais imposée, `key=f"desc_{note}"` -- un widget par
    # ingrédient, l'utilisateur garde la main pour éditer/vider librement, y
    # compris en revenant sur un ingrédient déjà visité dans la session
    # (mémorisé via session_state, même mécanisme que `use_oav_{note}` T76).
    _suggested_desc = [d for d in matching.reference.INGREDIENT_DESCRIPTORS.get(note, [])
                       if d in _descriptors(con)]
    with panel_a:
        if _suggested_desc:
            st.caption(f"Prefilled from {note}'s typical aroma (AI-assisted "
                      "suggestion, not measured data) — feel free to edit.")
        else:
            st.caption(f"No auto-suggested descriptors for {note} yet — add any "
                      "that apply manually, or rely on the molecular layer below.")
        selected_desc = st.multiselect(
            "Aroma descriptors", _descriptors(con), default=_suggested_desc,
            key=f"desc_{note}")

    # T76 3e addendum (2026-08-22, demande utilisateur explicite : "I have
    # the feeling these two buttons are not super clear/ergonomic" -- au
    # sujet des deux cases précédentes, "Also use molecular similarity" +
    # sa sous-case "Use only the molecular layer" qui n'apparaissait que si
    # la première était cochée). Remplacées par UN SEUL `st.segmented_
    # control` à 3 états mutuellement exclusifs -- correspond directement
    # aux 3 seules combinaisons `w_mol`/`w_desc` réellement utilisées (0/1,
    # 0.5/0.5, 1/0), plus conforme aux conventions Streamlit du projet
    # (segmented_control préféré à une case/un radio pour ce genre de choix)
    # qu'une case qui n'apparaît que si une autre case précise est cochée.
    # `required=True` : jamais de désélection vers `None` (un des 3 états
    # est toujours actif). Défaut "Descriptors" (couche principale, T76) --
    # PAS "Both", pour ne rien changer au comportement par défaut déjà en
    # place (moléculaire toujours opt-in).
    with rank_mode_col:
        rank_mode = st.segmented_control(
            "How to rank hops?", ["Descriptors", "Both", "Molecular only"],
            default="Descriptors", required=True, key=f"rank_mode_{note}",
            help="**Descriptors** — aroma tags only (see above), the default, "
                 "most reliable signal. **Both** — blends in molecular "
                 "similarity too (which hops share this ingredient's actual "
                 "aroma MOLECULES, not just its descriptor tags — see the "
                 "explainer below). **Molecular only** — ranks purely by "
                 "shared molecules, ignoring descriptor tags entirely, without "
                 "losing your descriptor selection above.")
    use_molecular = rank_mode in ("Both", "Molecular only")
    molecular_only = rank_mode == "Molecular only"

    # T76 addendum (2026-08-22, demande utilisateur explicite : "should
    # appear even if the molecular score is not ticked because user should
    # be informed before taking the decision to activate it or not") --
    # explainer + contexte de couverture affichés INCONDITIONNELLEMENT
    # (avant, dans le `if use_molecular:` ci-dessous, donc invisibles tant
    # que la case n'était pas déjà cochée -- à l'envers de leur but, qui est
    # d'aider À DÉCIDER de cocher ou non).
    with panel_a:
        _molecular_score_explainer()
        # T76 : distribution RÉELLE mesurée sur 44 ingrédients effectivement
        # courants en brassage (étude T76) -- remplace l'ancien `st.warning`
        # "Low molecular coverage" qui se déclenchait pour LITTÉRALEMENT
        # toutes les notes de toute la base (`LOW_COVERAGE_WARNING_
        # THRESHOLD`=20%, or la couverture ne dépasse jamais ~12% nulle part,
        # y compris sur les ingrédients réellement pertinents -- un
        # "avertissement" qui ne varie jamais n'avertit de rien). Contexte
        # factuel affiché systématiquement plutôt qu'un seuil binaire alarmant.
        st.caption(
            "For reference: on real beer ingredients (fruits, herbs, "
            "spices), molecular coverage typically falls between 4% and "
            "12% (measured on a curated sample) — hop oil chemistry only "
            "ever tracks a handful of any ingredient's real aroma "
            "molecules, so a low number here is normal, not a sign of "
            "missing data. The descriptor layer above is the more "
            "reliable signal on its own.")

    # T-D14 (spec Claude Design §5) : --oav (si applicable) + "Number of
    # results" côte à côte -- même mécanisme de colonne différée que
    # Ingredient/"How to rank hops?" ci-dessus.
    with panel_a:
        oav_col, results_col = st.columns(2)
    use_oav = False
    if use_molecular:
        # T76 (2026-08-22, demande utilisateur explicite) : la case --oav se
        # pré-coche/décoche désormais AUTOMATIQUEMENT par note plutôt qu'une
        # valeur fixe `True` pour tout le monde, à partir de la couverture
        # --oav RÉELLE de cette note précise -- calculée ici, EN AMONT de la
        # case, donc dupliquée avec ce que `matching.amplify` recalculera
        # juste en dessous (coût négligeable : une note, ~200 houblons,
        # mêmes requêtes déjà bon marché que celles mesurées ~30-50ms pour
        # toute la base en T-perf). `key=f"use_oav_{note}"` : un widget
        # Streamlit distinct par note (pas juste par label) -- change de
        # note recalcule un nouveau défaut informé par CETTE note, tout en
        # gardant en mémoire (session_state) un override manuel si
        # l'utilisateur revient sur une note déjà visitée.
        if producible:
            _oav_thr_preview = matching.oav_thresholds(con, list(producible))
            _oav_cov_preview, _ = matching.oav_coverage(profile, comp, _oav_thr_preview)
        else:
            _oav_cov_preview = None
        default_oav = bool(producible) and _oav_cov_preview is not None \
            and _oav_cov_preview >= matching.OAV_LOW_COVERAGE_WARNING_THRESHOLD

        with oav_col:
            use_oav = st.checkbox(
                "--oav (olfactory power prior)", value=default_oav, key=f"use_oav_{note}",
                help="Weights each molecule by 1/threshold when that threshold is "
                     "known. Thresholds are resolved live from FlavorDB2 (PubChem "
                     "CID → CAS → sourced threshold), never from a hardcoded value — "
                     "molecules without a sourced FlavorDB2 threshold get a neutral "
                     "weight (1x), never a guessed one. Approximate: not "
                     "a real concentration measurement, just a correction so a very "
                     "potent molecule with a low threshold isn't drowned out by a "
                     "ubiquitous but barely odorous one. Changes the ranking on "
                     "about 1 note in 6 (measured on the real database). Pre-checked "
                     "only when this note's own --oav coverage is high enough to "
                     "trust (see the caption below once enabled) — untick/tick "
                     "freely to compare.")

    with results_col:
        top = st.slider("Number of results", 1, 30, 8)

    # T76 : plus de repli implicite "pas de descripteurs -> 100% moléculaire"
    # ici -- ce repli reste dans `matching.amplify` (`has_descriptors`) pour
    # le cas "moléculaire activé + aucun descripteur", mais si l'utilisateur
    # a EXPLICITEMENT décoché la couche moléculaire ET n'a aucun descripteur,
    # il n'y a structurellement rien à classer : le dire plutôt que de
    # laisser `matching.amplify` retomber silencieusement sur 100%
    # moléculaire malgré la case décochée (ce qui contredirait le choix
    # explicite de l'utilisateur).
    if not use_molecular and not selected_desc:
        with _panel():
            st.write("No descriptors selected and the molecular layer is off — "
                     "nothing to rank. Add descriptors above, or enable the "
                     "molecular layer.")
        return

    if not use_molecular:
        w_mol, w_desc = 0.0, 1.0
    elif molecular_only:
        w_mol, w_desc = 1.0, 0.0
    else:
        w_mol, w_desc = 0.5, 0.5
    r = matching.amplify(con, note, w_mol=w_mol, w_desc=w_desc, use_oav=use_oav,
                         descriptors=selected_desc or None, top=top)

    # T-D05 (spec Claude Design §7) : la pile `st.metric`/`st.caption`/
    # `st.warning` d'origine devient une ligne de chips `_confidence_strip`
    # sous la carte d'inputs -- sage="fine", terracotta="read this", jamais
    # de rouge (aucune de ces qualifications n'est une erreur), explication
    # complète dans `help=` plutôt qu'en paragraphe affiché en dur.
    chips: list[tuple[str, str, str]] = []
    if use_molecular:
        chips.append((
            f"Molecular coverage {r['coverage']*100:.0f}%", "green",
            "Share of this ingredient's producible molecules that real hop "
            "composition data actually covers. For real brewing additions this "
            "typically sits at 4-12% (measured across 44 common additions) — hop "
            "oil chemistry simply doesn't overlap most food aromas. Not a warning "
            "by itself, the descriptor layer above is always the primary signal."))
        if not r.get("has_descriptors", True):
            chips.append((
                "100% molecular (no descriptors)", "orange",
                "This ingredient has no descriptors selected: the score is 100% "
                "molecular (w_desc not applied)."))
        if use_oav and r.get("oav_coverage") is not None:
            oav_ok = r["oav_coverage"] >= matching.OAV_LOW_COVERAGE_WARNING_THRESHOLD
            oav_help = (
                "Share of the molecular score coming from molecules with a "
                "threshold sourced live from FlavorDB2 (PubChem CID → CAS → "
                "threshold); the rest gets a neutral (1x) weight, never a guessed "
                "threshold.")
            if not oav_ok:
                oav_help += (f" Uncovered here: {', '.join(r['oav_uncovered'])} — "
                            "for those, --oav has no effect (neutral 1x weight), "
                            "so its correction is only partial.")
            chips.append((f"OAV coverage {r['oav_coverage']*100:.0f}%",
                         "green" if oav_ok else "orange", oav_help))
        # T76 : avertissement recentré sur le VRAI cas dégénéré (1 seule
        # molécule productible -- le classement se réduit alors à un simple
        # tri par quantité brute de CETTE molécule, cf. le cas géraniol/
        # Talus/Ekuanot documenté en T69) plutôt que sur un seuil de
        # pourcentage qui se déclenchait pour toute la base sans exception.
        if len(producible) <= 1:
            chips.append((
                "Single-molecule ranking", "orange",
                f"Only {next(iter(producible)) if producible else 'no molecule'} is "
                "a producible molecule for this ingredient: the molecular ranking "
                "alone just reflects who has the most of it, not this ingredient's "
                "real signature. The descriptor layer above is the more reliable "
                "signal here."))
        # T76 addendum : orphelines = molécules de la note qu'AUCUN houblon ne
        # produit -- un concept purement moléculaire (`coverage()`), sans rapport
        # avec la couche descripteurs. N'a de sens que si la couche moléculaire
        # est activée.
        if r["orphan"]:
            chips.append((f"{len(r['orphan'])} orphan molecule(s)", "orange",
                         "Carried by the addition, not the hop: " + ", ".join(r["orphan"])))
    if r["total_matches"] > len(r["ranked"]):
        chips.append((
            f"Showing {len(r['ranked'])} of {r['total_matches']}", "orange",
            "More hops overlap this ingredient than are shown — raise \"Number of "
            "results\" above to see them all."))
    _confidence_strip(chips)
    if not r["ranked"]:
        with _panel():
            st.write("No hop overlaps with this note.")
        return
    # T76 addendum (2026-08-22, demande utilisateur explicite : "we are
    # missing the descriptor contribution... create two distinctive columns
    # 'Molecular contributors' and 'Descriptor contributors'... activate the
    # columns only if the respective scores are activated") : l'ancienne
    # colonne unique "Contributes via" ne montrait QUE `h["why"]`
    # (contributeurs moléculaires, `molecular_scores`) même quand la couche
    # descripteurs pesait dans le score -- jamais quels descripteurs de la
    # note avaient effectivement recoupé ceux du houblon
    # (`descriptor_overlap`, jamais exposé nommément avant, juste une
    # fraction numérique dans "Desc."). Calculé ici (pas dans matching.py) :
    # simple recoupement d'ensembles déjà chargés (`selected_desc`,
    # `hop_desc`), pas une nouvelle notion de score.
    #
    # "activées" = pèsent RÉELLEMENT dans le score final, pas juste
    # "cochées" : `show_desc_col` exige `w_desc > 0` EN PLUS de `has_
    # descriptors`, pour couvrir le cas "Use only the molecular layer" ---
    # descripteurs sélectionnés (`has_descriptors=True`) mais explicitement
    # mis à w_desc=0 par ce choix -- sinon la colonne "Descriptor
    # contributors" resterait affichée pour une couche qui ne compte plus du
    # tout, exactement le problème signalé pour "Mol."/"Contributes via" un
    # tour plus tôt.
    show_mol_col = use_molecular
    show_desc_col = r.get("has_descriptors", False) and w_desc > 0
    desc_set = set(selected_desc)
    # T-D07 (spec Claude Design §7) : "score" -> ProgressColumn 0-100,
    # "fraction" -> NumberColumn percent (0-1), "list" -> ListColumn (vraies
    # listes Python, plus de `", ".join(...)` tronqué à l'affichage).
    _columns = [("Score", "score", "score")]
    if show_mol_col:
        _columns.append(("Mol.", "mol", "fraction"))
    if show_desc_col:
        _columns.append(("Desc.", "desc", "fraction"))
    _columns.append(("Purpose", "purpose", "purpose"))
    if show_mol_col:
        _columns.append(("Molecular contributors", "mol_why", "list"))
    if show_desc_col:
        _columns.append(("Descriptor contributors", "desc_why", "list"))
        _columns.append(("Descriptor sources", "desc_src", "list"))
    # T77 addendum : "Sources" renommée "Composition sources" -- n'a
    # toujours été que la provenance de la COMPOSITION (`hops.sources`,
    # ex. "barthhaas"), jamais celle des descripteurs -- le nom générique
    # laissait croire le contraire (source de la confusion signalée).
    _columns.append(("Composition sources", "sources_list", "list"))

    def _row(h):
        overlap = sorted(desc_set & hop_desc.get(h["variety"], set()))
        d_src = sorted({s for d in overlap for s in desc_src.get(h["variety"], {}).get(d, set())})
        return dict(_row_with_purpose(h, hops, comp),
                   mol_why=h["why"], desc_why=overlap, desc_src=d_src,
                   sources_list=h["sources"].split(","))

    _render_hop_rows([_row(h) for h in r["ranked"]], _columns)

    def _contrib_caption(h):
        parts = []
        if show_mol_col:
            parts.append(f"molecular: {', '.join(h['why']) or '(none)'}")
        if show_desc_col:
            overlap = sorted(desc_set & hop_desc.get(h["variety"], set()))
            parts.append(f"descriptors: {', '.join(overlap) or '(none)'}")
        return f"score {h['score']} — via {'; '.join(parts) or '(none)'}"

    _hop_detail_expanders(con, hops, comp, hop_desc, [
        {"variety": h["variety"], "name": h["name"], "caption": _contrib_caption(h)}
        for h in r["ranked"]])

    with _panel():
        st.subheader("Propose a blend")
        if not r["has_descriptors"]:
            st.caption("No descriptors for this note: no blend possible "
                      "(select descriptors above).")
        else:
            base = _select_base_hop(r["ranked"], key="amplify_base_hop")
    if r["has_descriptors"]:
        # Toujours 5 (décision utilisateur) : pas de curseur, un blend à 5
        # tailles complet reste peu coûteux à calculer et laisse voir toutes
        # les options d'un coup plutôt que de forcer un choix a priori.
        blend_r = matching.amplify_blend(con, note, w_mol=w_mol, w_desc=w_desc, use_oav=use_oav,
                                         descriptors=selected_desc or None, max_hops=5,
                                         base_variety=base)
        _render_blends(blend_r["blends"], hops, comp, desc_src)


_VIA_LABELS = {"top": "top candidate", "chosen": "base hop (chosen)",
              "complement": "opposite purpose (aromatic/bittering complement)",
              "pairing": "relevant + BeerMaverick pairing (top 10)",
              "coverage": "coverage fallback (no relevant pairing)",
              "relevance": "relevant extra hop (nothing new to cover)"}


def _render_blends(blends: list[dict], hops: dict, comp: dict,
                   desc_src: dict[str, dict[str, set[str]]]) -> None:
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
        with _panel():
            st.write("No combination found.")
        return
    # Une carte de section `_panel()` par taille de blend (demande
    # utilisateur, "it's visually difficult to separate blend n1/n2...n5" --
    # pas de séparation visuelle entre les tailles avant, juste des blocs
    # st.write/_render_hop_rows qui s'enchaînaient). La carte délimite chaque
    # blend au moins aussi clairement que des lignes horizontales.
    for b in blends:
        with _panel():
            st.write(f"**Size {b['size']}**")
            rows = []
            for h in b["hops"]:
                d_src = sorted({s for d in h["covers"] for s in desc_src.get(h["variety"], {}).get(d, set())})
                rows.append(dict(_row_with_purpose(h, hops, comp),
                                covers=sorted(h["covers"]), desc_src=d_src,
                                via_label=_VIA_LABELS[h["via"]],
                                sources_list=h["sources"].split(",")))
            # T77 (2026-08-22) : même split composition/descripteurs -- voir
            # `matching.descriptor_sources`. T-D07 : listes Python typées
            # ("list") au lieu de chaînes pré-jointes -- voir `_render_hop_rows`.
            _render_hop_rows(rows, [("Covers", "covers", "list"), ("Purpose", "purpose", "purpose"),
                                    ("Origin", "via_label"), ("Descriptor sources", "desc_src", "list"),
                                    ("Composition sources", "sources_list", "list")])
            if b["residual"]:
                st.caption("Not covered: " + ", ".join(b["residual"]))


def _contrast(con):
    # contrast a besoin de note_descriptors pour une note, table vide par
    # défaut (pas d'amorce littérature dans ce projet, cf. reference.py) —
    # l'utilisateur décrit donc sa note à la main avec le vocabulaire réel de
    # la roue d'arôme (même source que by-descriptor), ce qui fonctionne pour
    # n'importe quelle note sans rien inventer.
    #
    # T76 addendum (2026-08-22, demande utilisateur explicite : "deploy this
    # automatic descriptor definition in the contrast section... add the
    # ingredient box at the very beginning of the contrast tool so the
    # descriptors are more easily filled") : même amorce `reference.
    # INGREDIENT_DESCRIPTORS` que sur Amplify, mais OPTIONNELLE ici
    # (`index=None`/`placeholder`, rien de sélectionné par défaut) --
    # contrairement à Amplify, contrast n'a jamais eu besoin d'un ingrédient
    # précis (juste des descripteurs), donc pas question d'en imposer un ;
    # ne sert qu'à préremplir la liste ci-dessous, toujours éditable.
    panel_a = _panel()
    with panel_a:
        ingredient = st.selectbox(
            "Ingredient (optional)", _notes(con), index=None,
            placeholder="Pick an ingredient to prefill descriptors below — or skip "
                       "and choose descriptors directly")
    _suggested_desc = [d for d in matching.reference.INGREDIENT_DESCRIPTORS.get(ingredient, [])
                       if d in _descriptors(con)] if ingredient else []
    with panel_a:
        if ingredient:
            if _suggested_desc:
                st.caption(f"Prefilled from {ingredient}'s typical aroma (AI-assisted "
                          "suggestion, not measured data) — feel free to edit.")
            else:
                st.caption(f"No auto-suggested descriptors for {ingredient} yet — "
                          "add any that apply manually below.")
        selected = st.multiselect("Descriptors of the note to contrast", _descriptors(con),
                                  default=_suggested_desc, key=f"contrast_desc_{ingredient}")

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
        # T-D14 (2026-08-23, spec Claude Design §5) : les deux jeux de pills
        # côte à côte -- les seuls deux "filtres" de la carte d'inputs, une
        # paire naturelle.
        with panel_a:
            target_col, purpose_col = st.columns(2)
        with target_col:
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
        with purpose_col:
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
    with panel_a:
        top = st.slider("Number of results", 1, 100, 8)
    if not selected:
        with _panel():
            st.write("Choose at least one descriptor.")
        return
    r = matching.contrast(con, descriptors=selected, target_descriptors=target_selected,
                         purposes=purposes_selected, top=top)

    with _panel():
        # T-D06 (spec Claude Design §7) : "descriptor chip -- ... used for
        # every descriptor everywhere (..., contrast targets)".
        st.caption("Affinity target: "
                  + (_descriptor_chips(sorted(r["affinity_target"])) or "(none selected)"))
        if r["unmapped"]:
            st.caption(":material/info: No affinity mapping for: "
                      + ", ".join(r["unmapped"]) + " (ignored, no effect on the target).")
        if not r["ranked"]:
            st.write("No hop overlaps with this target.")
        if r["total_matches"] > len(r["ranked"]):
            # Transparence sur la troncature (2026-08-19, demande utilisateur) :
            # jamais laisser croire que `top` couvre tout le recoupement réel --
            # même principe que la couverture moléculaire faible ou les
            # molécules orphelines ailleurs dans la GUI.
            st.caption(f"Showing {len(r['ranked'])} of {r['total_matches']} hops overlapping "
                      "this target — raise \"Number of results\" above to see more "
                      "(many hops often tie on score; see Contrasts via below for what each "
                      "one actually matches).")
    if not r["ranked"]:
        return
    hops, comp, hop_desc, _ = matching.load(con)
    # T77 (2026-08-22) : même split composition/descripteurs qu'Amplify --
    # voir `matching.descriptor_sources`.
    desc_src = matching.descriptor_sources(con)

    def _contrast_row(h):
        d_src = sorted({s for d in h["contrast_via"] for s in desc_src.get(h["variety"], {}).get(d, set())})
        return dict(_row_with_purpose(h, hops, comp), contrast_via=h["contrast_via"],
                   desc_src=d_src, sources_list=h["sources"].split(","))

    # T-D07 (spec Claude Design §7) : listes Python typées ("list") au lieu
    # de chaînes pré-jointes -- voir `_render_hop_rows`.
    _render_hop_rows(
        [_contrast_row(h) for h in r["ranked"]],
        [("Score", "score", "score"), ("Purpose", "purpose", "purpose"),
        ("Contrasts via", "contrast_via", "list"),
        ("Descriptor sources", "desc_src", "list"), ("Composition sources", "sources_list", "list")])

    _hop_detail_expanders(con, hops, comp, hop_desc, [
        {"variety": h["variety"], "name": h["name"],
         "caption": f"score {h['score']} — contrasts via {', '.join(h['contrast_via'])}"}
        for h in r["ranked"]])

    with _panel():
        st.subheader("Propose a blend")
        base = _select_base_hop(r["ranked"], key="contrast_base_hop")
    # Toujours 5 (décision utilisateur) : pas de curseur. `target_descriptors`/
    # `purposes` propagés (2026-08-19) : le blend doit viser la même cible et
    # respecter le même filtre purpose que le tableau de résultats ci-dessus.
    blend_r = matching.contrast_blend(con, descriptors=selected, target_descriptors=target_selected,
                                      purposes=purposes_selected, max_hops=5, base_variety=base)
    _render_blends(blend_r["blends"], hops, comp, desc_src)


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
    # T-D09 (2026-08-23, spec Claude Design §8) : accent terracotta (config.toml
    # `primaryColor`) au lieu d'un bleu générique sans rapport avec la palette
    # Organic -- un ton par thème (comme avant), pas de `light-dark()` ici (marks
    # Altair "libres", voir docstring de la fonction).
    accent = "#f6a06b" if dark else "#c67139"

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
    # T-D04/T-D10 (2026-08-23, spec Claude Design) : ordre FIXE -- "purpose
    # chip -> key stats -> wheel block -> descriptors by source ->
    # composition table -> sources" -- identique dans
    # `_browse`/`_hop_detail_expanders`/`_by_descriptor`. Une carte par étape
    # (T-D04, "one card per logical section") plutôt qu'une seule carte
    # fourre-tout comme avant T-D10.
    with _panel():
        st.subheader(h["name"])
        # purpose EN PREMIER (demande utilisateur explicite : "should appear
        # in the browser information as a main/top information").
        purpose, inferred = matching.resolve_purpose(h.get("purpose"), hcomp)
        _purpose_badge(purpose, inferred)
        st.caption(f"Region: {h['region'] or 'unknown'}")
        # Alpha/beta acids, co-humulone, total oil : demande utilisateur explicite
        # (2026-08-19), "il manque un élément principal : les infos les plus
        # importantes de yakima" -- voir `_render_key_stats`.
        _render_key_stats(hcomp)
    # T-D08 (2026-08-23, spec Claude Design) : "chart and its Yakima/BarthHaas
    # toggle in one bordered block, ... source caption directly under the
    # chart, missing-source warning inside the block".
    with _panel():
        by_source = matching.load_aroma_intensity(con).get(selected, {})
        source = _aroma_wheel_toggle(matching.default_aroma_wheel_source(by_source),
                                     key=f"aroma_source_browse_{selected}")
        intensity = matching.select_aroma_intensity(by_source, source)
        if intensity:
            # T-D01 (2026-08-23, spec Claude Design) : `theme=None` retiré --
            # `_aroma_wheel` prend désormais ses couleurs de `_chart_theme()`
            # (palette du thème natif Streamlit, voir T-D09), plus besoin
            # d'écarter le thème Vega-Lite par défaut pour éviter un conflit de
            # couleurs codées en dur.
            vocab = _intensity_vocabulary_for_sources(con, {source})
            st.altair_chart(_aroma_wheel(intensity, vocab), width="content")
            st.caption(_aroma_wheel_source_caption(source))
        else:
            _aroma_wheel_missing_warning([h["name"]], source)

    # T77 (2026-08-22, demande utilisateur explicite -- confusion vérifiée en
    # direct sur "enigma" : "the source is barthhaas... does berry come from
    # this only?") : jamais juxtaposer la provenance de COMPOSITION à celle
    # des descripteurs. Chaque descripteur annoté par SA PROPRE source
    # (`hop_descriptors.source`, voir `matching.descriptor_sources`).
    with _panel():
        descs = sorted(hop_desc.get(selected, set()))
        desc_src = matching.descriptor_sources(con)
        if descs:
            # T79 addendum (2026-08-23, demande utilisateur explicite : "do one
            # line per source (in bold)... It will reduce the amount of text
            # and clarity") -- une ligne groupée par source plutôt qu'une
            # annotation `mot (source)` répétée à chaque descripteur.
            by_source = _descriptors_grouped_by_source(desc_src.get(selected, {}))
            st.markdown("**Descriptors**  \n" + "  \n".join(
                f"**{s}:** " + _descriptor_chips(ds) for s, ds in by_source.items()))
        else:
            st.write("**Descriptors:** none recorded")

    # "Smells like" (T72, 2026-08-21, demande utilisateur explicite : le
    # tooltip Flavornet ajouté sur le barplot Compare Hops (T71) doit AUSSI
    # apparaître ici -- voir `_all_compound_descriptors`).
    compound_smells = _all_compound_descriptors(con, comp)
    rows = sorted(
        ({"Compound": c, "Value": round(v["mid"], 3), "Unit": v["unit"],
          "Sources": ", ".join(v["sources"]), "Smells like": compound_smells.get(c, "—"),
          "Process": _process_survival_label(c) or "—"}
         for c, v in hcomp.items() if c not in matching.NON_AROMA_DISPLAY and v["mid"] is not None),
        key=lambda r: -r["Value"])
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
        if any(r["Process"] != "—" for r in rows):
            with _panel():
                st.caption(":material/info: \"Process\" is a qualitative prior (Scott Janish, "
                          "The New IPA), not a measured transfer rate — it depends on equipment, "
                          "contact time, temperature and yeast. Never used in any score.")
                _process_survival_legend()
    else:
        with _panel():
            st.write("No composition recorded.")
    # T-D06/T-D10 (spec Claude Design §7) : "source attribution" en DERNIER
    # dans l'ordre fixe -- pills grises, une par source. `h['sources']` :
    # chaîne "barthhaas,yakima" (table `hops`, voir `matching.load`).
    with _panel():
        st.caption("Composition: " + _source_chips(h["sources"].split(",")))

    # Titre commun aux 3 relations éditoriales (2026-08-21, demande
    # utilisateur explicite : "the 'Similar varieties (Yakima)' is not a
    # main title as compared with 'Similar hops (by molecular
    # composition)'... add a title 'Database similarity and
    # substitution'") -- ce titre couvre `_hop_associations` (3 sous-titres
    # de poids égal, `st.write("**...**")`, inchangé).
    with _panel():
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
    with _panel():
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
    # T-D07 (spec Claude Design §7) : "score" -> ProgressColumn 0-100 (les 3
    # similarités sont déjà des pourcentages 0-100, `None` si la couche est
    # inactive pour ce houblon -- rendu en cellule vide, jamais un 0
    # fabriqué), "list" -> ListColumn -- voir `_render_hop_rows`.
    if len(layers) == 2:
        columns = [("Combined similarity", "similarity", "score"),
                  ("Molecular similarity", "molecular_similarity", "score"),
                  ("Aroma wheel similarity", "aroma_wheel_similarity", "score")]
    elif layers == {"molecular"}:
        columns = [("Molecular similarity", "similarity", "score")]
    else:
        columns = [("Aroma wheel similarity", "similarity", "score")]
    columns.append(("Purpose", "purpose", "purpose"))
    if "molecular" in layers:
        columns.append(("Shared signature compounds", "shared_compounds", "list"))
    if "aroma_wheel" in layers:
        columns.append(("Shared aroma categories", "shared_descriptors", "list"))
    columns.append(("Sources", "sources_list", "list"))

    rows = []
    for h in similar:
        row = dict(_row_with_purpose(h, hops, comp))
        row["sources_list"] = h["sources"].split(",")
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
# paliers croissants (0-100 réel, `hop_aroma_intensity`) pour les cellules
# avec donnée -- discrétisé plutôt qu'un dégradé continu Vega, pour rester
# lisible sur une petite cellule de grille (voir T-D09 ci-dessous pour la
# palette).
_INTENSITY_BUCKET_ORDER = ["absent", "present", "0-20", "20-40", "40-60", "60-80", "80-100"]
# T-D09 (2026-08-23, spec Claude Design §8, "heatmap on the sequential
# accent ramp") : 5 paliers pris de `chartSequentialColors` (config.toml,
# rampe terracotta crème -> brun foncé) à la place de l'ancien dégradé de
# bleu codé en dur ; "absent" aligné sur le fond Organic (`#f5ead8`) plutôt
# qu'un gris neutre générique, "present" (noir) inchangé (voir ci-dessus).
_INTENSITY_BUCKET_COLORS = ["#f5ead8", "#000000", "#ffe1d0", "#f6a06b", "#b2622d", "#643312", "#2e2b25"]


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
    panel_a = _panel()
    with panel_a:
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
    with panel_a:
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
        with _panel():
            st.write("Choose at least one descriptor.")
        return
    r = matching.by_descriptor(con, text_selected, wheel_descriptors=wheel_selected, top=top)
    ranked = r["ranked"]
    if not ranked:
        with _panel():
            st.write("No hop overlaps with these descriptors.")
        return
    if r["total_matches"] > len(ranked):
        # Transparence sur la troncature (2026-08-20, revue de code — même
        # principe que `contrast`/T56 : jamais laisser croire que "Number of
        # hops shown" couvre tout le recoupement réel).
        with _panel():
            st.caption(f"Showing {len(ranked)} of {r['total_matches']} hops overlapping these "
                      "descriptors — raise \"Number of hops shown\" above to see more.")

    _, comp, _, _ = matching.load(con)
    compound_smells = _all_compound_descriptors(con, comp)
    # T77 (2026-08-22, demande utilisateur explicite -- confusion vérifiée
    # en direct sur "enigma" : "the source is barthhaas... does berry come
    # from this only?") : `[{h['sources']}]` dans l'en-tête d'expander (ci-
    # dessous) juxtaposait "matches berry, raspberry" à une provenance de
    # COMPOSITION (`hops.sources`) -- laissait croire à tort qu'elle couvrait
    # aussi les descripteurs. Voir `matching.descriptor_sources`.
    desc_src = matching.descriptor_sources(con)

    heatmap = _descriptor_heatmap(ranked, intensity_vocab)
    if heatmap is not None:
        wheel_chart, other_chart, hidden = heatmap
        suffix = f" (first 12 of {len(ranked)})" if hidden else ""
        if wheel_chart is not None:
            with _panel():
                st.caption("Aroma wheel descriptors — shaded by measured intensity (Yakima), "
                          "black where a hop carries the descriptor but has no quantitative "
                          "reading for it" + suffix)
            st.altair_chart(wheel_chart, width="stretch")
        if other_chart is not None:
            with _panel():
                st.caption("Other descriptors — categorical only, no quantitative intensity "
                          "data exists for these (black = present)" + suffix)
            st.altair_chart(other_chart, width="stretch")

    # T79 (2026-08-22) : `all_intensity` chargé une seule fois pour toute la
    # page, réutilisé par le toggle BarthHaas/Yakima de chaque expander
    # ci-dessous -- même mécanisme que `_hop_detail_expanders`/`_browse`.
    all_intensity = matching.load_aroma_intensity(con)

    for h in ranked:
        hcomp = comp.get(h["variety"], {})
        with st.expander(f"{h['name']} — matches {', '.join(h['matched_descriptors'])}"):
            # T-D10 (2026-08-23, spec Claude Design §7) : ordre FIXE -- "purpose
            # chip -> key stats -> wheel block -> descriptors by source ->
            # composition table -> sources" -- identique dans
            # `_browse`/`_hop_detail_expanders`/`_by_descriptor`.
            purpose, inferred = matching.resolve_purpose(h.get("purpose"), hcomp)
            _purpose_badge(purpose, inferred)
            _render_key_stats(hcomp)
            # Transparence sur le tri quantitatif (2026-08-19, "propose a 2
            # layer results ordering... inside this selection, propose a
            # ordered result... based on the aroma wheel descriptors") --
            # jamais un réordonnancement silencieux : dit explicitement CE
            # QUI a été moyenné, ou l'absence de donnée exploitable, pour que
            # l'utilisateur puisse vérifier pourquoi ce houblon est classé où
            # il est parmi ceux à même nombre de descripteurs recoupés. Restée
            # collée au bloc roue (juste avant) : ce texte l'explique.
            if h["quant_score"] is not None:
                src_label = "BarthHaas" if h.get("intensity_source") == "barthhaas" else "Yakima"
                st.caption(f"Quantitative refinement: {h['quant_score']:.0f}/100 avg. "
                          f"intensity on {', '.join(h['quant_descriptors'])} ({src_label})")
            elif wheel_selected:
                st.caption("Quantitative refinement: no aroma-wheel intensity data for "
                          "this hop (neither Yakima nor BarthHaas covers it, or the "
                          "only entry present is a corrupted all-zero YCH reading).")
            # Roue d'arôme quantitative (demande utilisateur 2026-08-19 : "The
            # aroma wheel is missing from the from descriptor tool") -- même
            # rendu que `_browse`/`_hop_detail_expanders`. T79 (2026-08-22) : le score de
            # classement (`h["intensity"]`/`h["intensity_source"]`, ci-dessus)
            # reste la résolution AUTOMATIQUE de `matching.by_descriptor`
            # (jamais de toggle sur le classement lui-même, voir T79) -- ce
            # rendu de roue, en revanche, est un "single hop spider chart" au
            # même titre que `_hop_detail_expanders`/`_browse`, donc porte son
            # propre toggle BarthHaas/Yakima (demande utilisateur explicite,
            # T79). Peut donc afficher une source DIFFÉRENTE de celle utilisée
            # pour le score juste au-dessus -- attendu, chaque caption cite
            # explicitement sa propre source.
            by_source = all_intensity.get(h["variety"], {})
            source = _aroma_wheel_toggle(matching.default_aroma_wheel_source(by_source),
                                         key=f"aroma_source_by_desc_{h['variety']}")
            intensity = matching.select_aroma_intensity(by_source, source)
            if intensity:
                vocab = _intensity_vocabulary_for_sources(con, {source})
                st.altair_chart(_aroma_wheel(intensity, vocab), width="content")
                st.caption(_aroma_wheel_source_caption(source))
            else:
                _aroma_wheel_missing_warning([h["name"]], source)
            # T79 addendum (2026-08-23, même demande que Browse/les
            # expanders : "one line per source (in bold)... bold for the
            # 'Descriptor' and the name of the source, not the notes
            # themselves").
            desc_by_source = _descriptors_grouped_by_source(
                {d: desc_src.get(h["variety"], {}).get(d, set()) for d in h["all_descriptors"]})
            st.caption("**All descriptors**  \n" + "  \n".join(
                f"**{s}:** " + _descriptor_chips(ds) for s, ds in desc_by_source.items()))
            if h["compounds"]:
                st.dataframe(
                    [{"Compound": c["compound"], "Value": round(c["mid"], 2),
                      "Unit": c["unit"], "Sources": ", ".join(c["sources"]),
                      "Smells like": compound_smells.get(c["compound"], "—"),
                      "Process": _process_survival_label(c["compound"]) or "—"}
                     for c in h["compounds"][:8]],
                    width="stretch", hide_index=True)
            match_src = sorted({s for d in h["matched_descriptors"]
                               for s in desc_src.get(h["variety"], {}).get(d, set())})
            # T-D06/T-D10 (spec Claude Design §7) : "source attribution" en
            # DERNIER dans l'ordre fixe -- pills grises, une par source.
            st.caption("Matched descriptors sourced from: "
                      + (_source_chips(match_src) if match_src else "unknown")
                      + " — composition sourced from: "
                      + _source_chips(h["sources"].split(",")))


# T58 (2026-08-19, demande utilisateur, inspiré de
# https://beermaverick.com/hops/hop-comparison-tool/) : palette CATÉGORIELLE
# (pas divergente -- "Spectral" suggéré par l'utilisateur est une palette
# ColorBrewer pensée pour un gradient autour d'un centre neutre, pas adaptée
# à des houblons sans ordre naturel entre eux) -- 5 premières teintes (max 5
# houblons). T-D09 (2026-08-23, spec Claude Design §8, "stable per-hop
# colour... shared _chart_theme()") : remplace l'ancienne palette Vega
# "tableau10" (bleu/orange/rouge/sarcelle/vert générique) par
# `chartCategoricalColors` (config.toml) -- alterne teinte ET valeur dès les
# 2 premières entrées (terracotta/sauge) pour rester distinguable même en
# niveaux de gris, cohérent avec le reste de la palette Organic plutôt qu'un
# jeu de couleurs sans rapport avec le thème.
_COMPARE_PALETTE = ["#c67139", "#7a8a5e", "#8c491a", "#aebf92", "#82796a"]
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
                               descriptors: dict[str, str] | None = None,
                               process_notes: dict[str, str] | None = None):
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
    survol plus large que le seul label, pas plus fragile à positionner.

    `process_notes` (T74, 2026-08-21, demande utilisateur explicite --
    annotation de survie au procédé, `app._process_survival_label`) : même
    contrat que `descriptors`, ajouté EN PLUS (pas à la place) dans le même
    tooltip et la même couche rect -- deux informations indépendantes sur le
    même composé, jamais fusionnées en une seule chaîne (l'une vient de
    Flavornet/Janish -- ce que le composé SENT --, l'autre est un prior de
    brassage -- CE QUI EN SURVIT au procédé -- aucun rapport de source entre
    les deux)."""
    if not rows:
        return None
    descriptors = descriptors or {}
    process_notes = process_notes or {}
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
    if any(f in process_notes for f in field_order):
        tooltip.append(alt.Tooltip("Process:N", title="Process"))
        rows = [dict(r, Process=process_notes.get(r["Field"], "—")) for r in rows]

    primary_rows = [r for r in rows if r["Field"] in primary_fields]
    secondary_rows = [r for r in rows if r["Field"] in secondary_fields]
    layers = []
    resolved_fields = [f for f in field_order if f in descriptors or f in process_notes]
    if resolved_fields:
        # Couche invisible EN PREMIER (sous les barres, voir docstring) :
        # une colonne pleine hauteur par composé résolu (Smells like ET/OU
        # Process), cible de survol en dehors d'une barre précise.
        rect_tooltip = ["Field:N"]
        if descriptors:
            rect_tooltip.append(alt.Tooltip("Descriptors:N", title="Smells like"))
        if process_notes:
            rect_tooltip.append(alt.Tooltip("Process:N", title="Process"))
        layers.append(
            alt.Chart(alt.Data(values=[{"Field": f, "Descriptors": descriptors.get(f, "—"),
                                       "Process": process_notes.get(f, "—")}
                                       for f in resolved_fields]))
            .mark_rect(opacity=0.001)
            .encode(x=x_enc, tooltip=rect_tooltip))
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
    with _panel():
        selected = st.multiselect(
            f"Hops to compare (up to {_COMPARE_MAX_HOPS})", options,
            format_func=lambda v: hops[v]["name"], max_selections=_COMPARE_MAX_HOPS)
        if not selected:
            st.write("Choose at least one hop.")
    if not selected:
        return
    colors = {hops[v]["name"]: _COMPARE_PALETTE[i] for i, v in enumerate(selected)}

    with _panel():
        st.subheader("Aroma wheel")
    # T79, 4e addendum (2026-08-23, demande utilisateur explicite) : jusqu'à
    # 5 houblons superposés sur UN SEUL graphique -- un toggle PAR houblon
    # n'aurait pas de sens ici, un SEUL toggle s'applique à TOUS les
    # houblons sélectionnés à la fois (plus de repli automatique par
    # houblon : la source choisie est UNIFORME sur tout le graphique --
    # un houblon qui ne l'a pas est explicitement listé en avertissement,
    # jamais silencieusement replié sur l'autre source).
    all_intensity = matching.load_aroma_intensity(con)
    default_source = matching.default_aroma_wheel_source_for_varieties(all_intensity, selected)
    # `key` dépend de `selected` (comme T57/T61, `contrast_target_pills_...`)
    # -- `default=` d'un widget Streamlit ne s'applique QU'À LA CRÉATION du
    # widget sous cette clé, jamais recalculé sur un rerun si la clé ne
    # change pas. Une clé fixe aurait gelé le premier défaut calculé (ex.
    # "barthhaas" pour Admiral seul) même après avoir ajouté un houblon
    # Yakima à la sélection -- changer la sélection doit recalculer le
    # défaut, tout en gardant un choix manuel tant que la sélection ne
    # change pas.
    source = _aroma_wheel_toggle(default_source,
                                 key=f"aroma_source_compare_{tuple(sorted(selected))}")
    intensities = {}
    missing = []
    for v in selected:
        intensity = matching.select_aroma_intensity(all_intensity.get(v, {}), source)
        if intensity:
            intensities[hops[v]["name"]] = intensity
        else:
            missing.append(hops[v]["name"])
    vocabulary = _intensity_vocabulary_for_sources(con, {source} if intensities else set())
    chart = _aroma_wheel_compare(intensities, vocabulary, colors)
    if chart is not None:
        st.altair_chart(chart, width="content")
        with _panel():
            st.caption(_aroma_wheel_source_caption(source))
            st.caption(":material/info: Hover a label for its definition.")
    if missing:
        with _panel():
            _aroma_wheel_missing_warning(missing, source)

    with _panel():
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
        with _panel():
            st.write("No principal composition data for the selected hops.")

    with _panel():
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
    with _panel():
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
    # Badge de survie au procédé (T74, 2026-08-21, demande utilisateur
    # explicite) : même mécanisme que `descriptors` ci-dessus, ajouté EN
    # PLUS dans le même tooltip/couche rect (voir docstring de
    # `_compare_dual_axis_barplot`) -- deux infos indépendantes par composé.
    process_notes = {c: label for c in present_oil_compounds + thiols_fields
                     if (label := _process_survival_label(c)) is not None}
    detail_chart = _compare_dual_axis_barplot(
        detail_rows, present_oil_compounds, primary_title,
        thiols_fields, "Thiols (µg/kg)", colors, descriptors=descriptors,
        process_notes=process_notes)
    if detail_chart is not None:
        st.altair_chart(detail_chart, width="content")
        if descriptors or process_notes:
            with _panel():
                st.caption(":material/info: Hover a bar, or the space near/below "
                          "a compound's label, for its Flavornet odor descriptors "
                          "and process survival notes (not every compound has an "
                          "entry). \"Process\" is a qualitative prior (Scott "
                          "Janish, The New IPA) — never a measured transfer rate, "
                          "never used in any score.")
        if process_notes:
            _process_survival_legend()
    else:
        with _panel():
            st.write("No detailed composition data for the selected hops.")
    if missing_oil:
        with _panel():
            st.caption(":material/info: Total oil unknown for: " + ", ".join(sorted(set(missing_oil)))
                      + " — their % of oil composition can't be converted to an absolute amount.")


def main():
    # Nom d'affichage GUI = "HopFinder" (demande utilisateur 2026-08-19,
    # renommage d'affichage seulement -- le paquet/CLI restent "hopmatch",
    # voir CLAUDE.md et le sous-titre de README.md).
    st.set_page_config(page_title="HopFinder", page_icon=_TAB_ICON_PATH)
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
    # Titre texte "HopFinder" + caption "Aroma note → molecules → hops"
    # RETIRÉS (2026-08-22, demande utilisateur explicite) : redondants avec
    # le logo et avec le `st.title(MODE_LABELS[mode])` déjà affiché par
    # chaque page d'outil ("HopFinder - Amplify"...) -- "there is already
    # the name of the tool at the top that is enough". Logo en tête de page
    # principale d'abord affiché sur TOUTES les pages, puis RESTREINT À LA
    # SEULE PAGE HOME (même jour, addendum -- demande utilisateur explicite :
    # "remove the hopfinder logo from the top of all tools... I want it
    # only on i) the left panel... ii) on the top of the home page...
    # iii) on github") -- voir la branche `mode == "home"` plus bas.

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
    # Logo en tête de sidebar (2026-08-22, demande utilisateur explicite) --
    # `st.image` directement dans le flux de la sidebar (PAS `st.logo`,
    # retiré : son plafond de taille intégré, 32px de haut max même en
    # "large", rendait un logo minuscule -- "in the sidebar it should be
    # bigger than currently"). `width=260` : large mais reste dans la
    # largeur par défaut de la sidebar Streamlit (~336px) sans déborder.
    st.sidebar.image(_LOGO_PATH, width=260)

    # T-D11 (2026-08-23, spec Claude Design §6) : "Sidebar order: logo ->
    # navigation -> collapsed 'Database' popover... -> licence/contact
    # caption at the very bottom, muted, small. The DB line is diagnostic
    # information; it should not be the second thing in the panel."
    # `st.navigation`/`st.Page` essayé et écarté (demanderait de retravailler
    # le relais `_next_mode` pour un gain surtout cosmétique), et le repli
    # "deux `st.radio` groupés" AUSSI écarté après coup : deux widgets
    # Streamlit distincts ne partagent pas d'état visuel -- cliquer un mode
    # dans un groupe laisse l'AUTRE radio affiché comme sélectionné même
    # après un changement de page (état chacun pour soi côté frontend),
    # source de confusion pire que l'absence de groupement. Repli plus
    # simple et sûr, toujours dans l'esprit de la spec (garder LE radio
    # existant, un seul widget = un seul état) : `format_func` préfixe
    # chaque libellé par son groupe ("HopFinder — Amplify", "Explore —
    # Browse a hop") -- la lecture reste groupée sans dupliquer le widget.
    _MODE_GROUP_PREFIX = {"amplify": "HopFinder — ", "contrast": "HopFinder — ",
                          "by-descriptor": "HopFinder — ", "browse": "Explore — ",
                          "compare": "Explore — "}
    mode = st.sidebar.radio(
        "Mode", ["home", "amplify", "contrast", "by-descriptor", "browse", "compare"],
        format_func=lambda m: _MODE_GROUP_PREFIX.get(m, "") + MODE_LABELS[m], key="mode")

    with st.sidebar.popover("Database", icon=":material/database:", width="stretch"):
        stats = _stats(con)
        modified = datetime.fromtimestamp(_db_version(db_path)).strftime("%Y-%m-%d %H:%M")
        st.caption(
            f"**{db_path}** — {stats['hops']} hops, {stats['notes']} notes, "
            f"{stats['descriptors']} descriptors · modified {modified}")
        # Signalé par l'utilisateur (2026-08-23) : la popover ne nommait que
        # le fichier local (`aromahops.db`), aucune des sources externes
        # réellement utilisées pour le construire -- voir CLAUDE.md, section
        # "Réalité des données", pour le détail complet de chacune.
        st.caption(
            "Built from: **BarthHaas** & **Yakima Chief** (hop composition, "
            "aroma wheels) · **BeerMaverick** (pairings, substitutions, "
            "purpose, descriptor tags) · **FooDB** (ingredient molecules) · "
            "**Flavornet** & **FlavorDB2** (odor-active compounds, "
            "thresholds) · **PubChem** (compound identity).")

    st.sidebar.caption(
        "Code MIT · [data licenses](https://github.com/quentinba/HopFinder"
        "#licences) · [quentin4313@gmail.com](mailto:quentin4313@gmail.com)")

    if mode == "home":
        # Logo affiché seulement ICI (page Home), pas sur les autres pages
        # d'outil -- voir le commentaire plus haut sur son retrait de
        # `main()` en tête commune.
        st.image(_LOGO_PATH, width=420)
        st.title(MODE_LABELS[mode])
        _home(con)
        return

    # T-D12 (2026-08-23, spec Claude Design) : "h1 title... + one-line
    # purpose from _TOOL_SUMMARIES[...]['tagline'] + inputs card +
    # confidence strip + result cards... Move the long method prose out of
    # the page body into each tool's own 'How does this work?' expander."
    # Identique pour les 5 pages d'outil -- factorisé ici plutôt que répété
    # dans chaque `if mode == ...`.
    st.title(MODE_LABELS[mode])
    summary = _TOOL_SUMMARY_BY_MODE[mode]
    st.caption(summary["tagline"])
    with _panel_expander("How does this work?"):
        st.write(summary["description"])

    if mode == "by-descriptor":
        _by_descriptor(con)
        return
    if mode == "contrast":
        _contrast(con)
        return
    if mode == "browse":
        _browse(con)
        return
    if mode == "compare":
        _compare(con)
        return
    # "amplify" : seul mode restant après les dispatches explicites
    # ci-dessus -- la sélection de note vit désormais DANS `_amplify` (page
    # principale, pas la sidebar, voir son commentaire), donc plus rien à
    # faire ici que le header, comme les autres modes.
    _amplify(con)


if __name__ == "__main__":
    main()
