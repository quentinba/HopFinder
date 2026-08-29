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
import bisect
import io
import itertools
import json
import math
import os
import re
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

# Logo (T-D14b, 2026-08-24, spec Claude Design -- "HopFinder Logo Options",
# lockup 1d "Stacked" choisi par l'utilisateur parmi 4 options présentées).
# REMPLACE l'ancien raster `assets/logo.png` (2026-08-22, fond crème opaque)
# -- `_LOGO_PATH` garde son RÔLE ("le fichier source du logo affiché en
# sidebar/hero") mais pointe maintenant sur `assets/mini_logo_square.png`,
# déjà un simple contour vert sur fond TRANSPARENT (T78) -- appliqué en `mask-
# image` CSS (voir `_logo_html`), teinté par le thème via `light-dark()`,
# même technique à un seul asset que le fond d'écran (T-D02) : plus besoin
# de deux fichiers clair/sombre ni de la mise en garde du 1er essai T78
# ("transparent logo doesn't work in dark theme" -- un `<img>` PNG collé
# tel quel n'a pas ce problème pour un MASQUE recoloré dynamiquement, à la
# différence d'un fond fixe imprimé dans les pixels).
_LOGO_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "mini_logo_square.png")

# Icône d'onglet navigateur (favicon). T-D14b (2026-08-24) : passe de la
# marque nue transparente (T78) au variant "patch" (1b, cercle sauge + marque
# crème) -- demandé par la spec elle-même pour tout lockup nu en dessous de
# ~24px ("the bare mark loses its silhouette... if you pick 1a or 1d for the
# lockup, use the 1b patch as the favicon", et 1d est le choix retenu
# ci-dessus). Généré une fois (`mini_logo_square.png` recoloré + composé sur
# un disque sage, script ponctuel, pas de dépendance PIL au runtime pour ce
# fichier) -- statique, PAS le mécanisme `light-dark()` du logo principal :
# un favicon ne peut pas réagir au thème de l'app au moment où le navigateur
# le charge, une seule teinte fixe pour les deux thèmes (déjà lisible sur
# fond clair ET sombre de barre d'onglets, vérifié en direct).
_TAB_ICON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "favicon_patch.png")

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
    "styles": "Beer styles",
    "style-hops": "Hops for a style",
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
    {
        "mode": "styles",
        "icon": ":material/local_bar:",
        "tagline": "BJCP style reference",
        "description": (
            "Pick a BJCP 2021 style directly: the official vital statistics "
            "range (ABV, IBU, OG, FG, SRM) and the full descriptive text "
            "(aroma, appearance, flavor, mouthfeel, history...). An "
            "editorial style guideline (BJCP), not a measurement of real "
            "recipes."
        ),
    },
    {
        "mode": "style-hops",
        "icon": ":material/join_inner:",
        "tagline": "Recipes x aroma, side by side",
        "description": (
            "Pick a BJCP style and see two rankings side by side: how "
            "often each hop is actually used in that style's recipes "
            "(beer-analytics.com), and how well each hop matches the "
            "style's typical aroma descriptors (pre-filled from the BJCP "
            "text, freely editable). The hops that rank well on aroma but "
            "are rarely used in the style's real recipes are highlighted "
            "separately — a combination neither tool this was inspired by "
            "computes."
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
    ("2026-08-29", "Browse a hop now sorts by Popularity by default (so "
                   "the hop dropdown shows recipe counts right away), and "
                   "the \"Minimum recipes\" filter only appears when a "
                   "Popularity sort is actually active, in both Browse a "
                   "hop and From descriptors."),
    ("2026-08-29", "New \"Hops for a style\" tool: pick a BJCP style and see "
                   "two rankings side by side -- real recipe frequency "
                   "(beer-analytics.com) and aroma relevance (typical "
                   "descriptors, pre-filled from the BJCP text and freely "
                   "editable). Hops that rank well on aroma but have no "
                   "measured usage in that style's real recipes get their "
                   "own highlighted section, right up top."),
    ("2026-08-29", "Browse a hop now has a \"Recommended usage\" card, right "
                   "after the aroma wheel: where brewers actually use this "
                   "hop by process stage (real recipe share from beer-"
                   "analytics.com) side by side with an early-use index "
                   "estimated from its composition (YCH \"survivable "
                   "compounds\" rules) -- two separate layers, never "
                   "blended, with a note when they genuinely diverge."),
    ("2026-08-29", "Beer styles now overlays the official BJCP range with "
                   "the observed distribution from real published recipes "
                   "(beer-analytics.com) on the same chart for ABV, IBU, "
                   "OG, FG and color -- a terracotta band for the official "
                   "range, sage bars for the observed histogram. Falls "
                   "back to the plain range bar (no fabricated histogram) "
                   "for the styles beer-analytics doesn't cover."),
    ("2026-08-29", "Browse a hop and From descriptors both gained a "
                   "\"Sort by\" toggle (Name/Popularity or Relevance/"
                   "Popularity) plus a minimum-recipes filter, using real "
                   "recipe counts from beer-analytics.com. Hops beer-"
                   "analytics doesn't cover are never treated as "
                   "\"unpopular\" — they're grouped separately as "
                   "\"no popularity data\" and never hidden by the filter."),
    ("2026-08-27", "Browse a hop now has a collapsed \"Producer description\" "
                   "section right under the identity metadata, with the "
                   "hop's own marketing description from Yakima Chief Hops "
                   "(cleaned up from their raw HTML, links included) — "
                   "clearly labeled as producer marketing text, not a "
                   "neutral characterization."),
    ("2026-08-27", "Browse a hop now shows identity metadata right under "
                   "the hop's name: cultivar code, breeder, release year "
                   "and pedigree (cross/lineage) when known, plus badges "
                   "for Experimental, Organic and Blend varieties. Sourced "
                   "from Yakima Chief (cultivar/experimental/organic/blend) "
                   "and hand-reviewed from BeerMaverick's variety history "
                   "pages (breeder/release year/pedigree) — missing fields "
                   "are simply left out, never shown as a dash."),
    ("2026-08-27", "Browse a hop now shows a fourth association block: "
                   "editorial beer-style suggestions from Yakima and "
                   "BeerMaverick (e.g. \"American Pale Ale (18B)\"), grouped "
                   "by source and clearly marked as an editorial suggestion, "
                   "not a measured recipe frequency."),
    ("2026-08-27", "New \"Beer styles\" tool: browse any BJCP 2021 style "
                   "(110 of them) by category then name, see its official "
                   "vital statistics (ABV/IBU/OG/FG/color) as a range plus "
                   "a visual bar, the full descriptive text (aroma, "
                   "appearance, flavor, mouthfeel, history...), and its "
                   "commercial examples. Two independent unit toggles at "
                   "the top let you pick EBC or SRM for color and °Plato "
                   "or SG for density, so any combination works (e.g. SRM "
                   "with °Plato). Each range bar also shows its low/high "
                   "value written right at its two ends."),
    ("2026-08-27", "Compare Hops' detailed composition chart now shows each "
                   "compound's chemical category (Hydrocarbons/Oxygen "
                   "containing/Sulfur compounds, and the finer Monoterpenes/"
                   "Sesquiterpenes/etc. below that) in two narrow columns, "
                   "with a coloured bracket connecting each group of "
                   "compounds to its category and a clear divider line "
                   "between adjacent categories — the category/compound "
                   "names themselves stay plain text, leaning on the "
                   "bracket colour and dividers instead. This chart is back "
                   "to matching the width of the chart above it (its "
                   "legend was dropped as redundant — the same one already "
                   "appears twice higher up on this page). The browser-tab "
                   "icon is now the plain orange hop mark with no "
                   "background, matching the sidebar logo. The \"Oxygen "
                   "cont.\" category label is now spelled out in full as "
                   "\"Oxygen containing comp.\". A stray \"Hops\" was "
                   "removed from 7 BarthHaas hop names (e.g. \"Luna Hops\" "
                   "→ \"Luna\") — the \"- NZ Hops\" supplier qualifier on "
                   "11 New Zealand varieties is untouched."),
    ("2026-08-26", "The hop-engraving background image is now visible, but "
                   "discreetly, in both light and dark mode (it was "
                   "nearly invisible at first, then too prominent once "
                   "fixed — now toned down). Every chart (aroma-wheel "
                   "radars, Compare Hops barplots, By-descriptor heatmap) "
                   "now has an opaque background matching its surrounding "
                   "card instead of a mismatched default, which also fixes "
                   "the radar's axis labels sometimes being unreadable. "
                   "Compare Hops' \"Principal info\" barplot now has the "
                   "same alternating background bands as the detailed "
                   "composition chart to separate categories, and its "
                   "grouped bars are now properly centered within each "
                   "band (they used to hug one side) regardless of how "
                   "many hops are compared."),
    ("2026-08-26", "Compare Hops: hop colours/legend order now follow the "
                   "order hops were picked in the multiselect, not "
                   "alphabetical order. Detailed composition chart: fixed a "
                   "hop at the database minimum for a compound (e.g. "
                   "Columbus's thiols) becoming invisible under Min-max/"
                   "Quantile normalization; the Log-scale axis now stays "
                   "anchored to the whole database's range instead of "
                   "zooming into whichever hops are selected; its "
                   "scale-tick gridlines are now visible in light mode "
                   "(previously dark-mode only, and toned down in dark "
                   "mode after being too bright) and the bars no longer "
                   "have a stray dark outline."),
    ("2026-08-24", "The \"Normalization\" dropdown's help text (Compare "
                   "Hops, detailed composition chart) now lists None/Log/"
                   "Min-max/Quantile one per line instead of one dense "
                   "paragraph."),
    ("2026-08-24", "Fixed the multi-hop aroma-wheel radar's legend, which "
                   "had silently gone missing (a Vega-Lite quirk from an "
                   "earlier fix); the detailed composition chart's compound "
                   "order now stays the same (myrcene first) no matter "
                   "which normalization is selected, instead of reshuffling "
                   "every time; its \"Smells like\"/\"Process\" hint is now "
                   "two lines instead of one; and Browse a hop's redundant "
                   "search box was removed — the \"Hop\" dropdown already "
                   "filters as you type."),
    ("2026-08-24", "Compare Hops' detailed composition chart's log-scale "
                   "toggle became a \"Normalization\" dropdown (None / "
                   "Min-max / Quantile / Log): min-max and quantile place "
                   "each hop's compound value relative to every hop's "
                   "known value for that same compound across the whole "
                   "database, so small and large compounds become directly "
                   "comparable (the exact amount is still on hover); the "
                   "aroma-wheel radar's dots are smaller and less bulky; "
                   "and the aroma wheel's caption is now two lines instead "
                   "of one long run-on sentence."),
    ("2026-08-24", "Another round on the aroma-wheel radar and detailed "
                   "composition chart: the radar is bigger again (500px) "
                   "with thinner outlines so it reads less busy; the "
                   "detailed composition chart's logarithmic-scale toggle "
                   "now draws actual bars (it briefly fell back to dots, "
                   "a Vega-Lite log-scale limitation) with the alternating "
                   "background bands correctly visible again; and a "
                   "duplicated \"Hover a label for its definition\" line "
                   "under Compare Hops' aroma wheel was removed."),
    ("2026-08-24", "Fixed the aroma-wheel radar's shaded fill, which wasn't "
                   "tracing the polygon shape correctly; resized the radar "
                   "for a better fit on both mobile and desktop; added a "
                   "logarithmic scale toggle to Compare Hops' detailed "
                   "composition chart to see small compounds better; "
                   "capitalized compound names on that chart's axis (and "
                   "used a real β symbol for beta-pinene); and made the "
                   "favicon's hop icon bigger."),
    ("2026-08-24", "Follow-up polish on the new visual design: a wider, "
                   "actually-distinguishable colour palette for Compare "
                   "Hops' charts (5 hops no longer collapse into shades of "
                   "the same colour); the aroma-wheel radar keeps a "
                   "constant size regardless of hop name length, with an "
                   "abbreviated legend at the bottom; the detailed "
                   "composition chart is now horizontal with a computed "
                   "height so it scrolls instead of compressing at 5 hops; "
                   "the intensity heatmap switched from a terracotta ramp "
                   "(which read as \"button\") to a sage one; and a new "
                   "logo lockup everywhere the logo appears."),
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


@st.cache_data
def _logo_mask_data_uri(path: str, _version: float) -> str | None:
    """T-D14b (2026-08-24, spec Claude Design, lockup "1d — Stacked" choisi
    par l'utilisateur parmi 4 options) : encode `_LOGO_PATH` en data URI pour
    un `mask-image` CSS. AUCUN traitement PIL nécessaire ici, contrairement à
    `_background_mask_data_uri` : le fichier (`assets/mini_logo_square.png`,
    déjà retravaillé en T78) a DÉJÀ le bon canal alpha (contour opaque, fond
    transparent) -- lu tel quel. Mis en cache par mtime, `None` si absent."""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# Fond des cartes de section (`_panel()`/`_panel_expander()`), même valeur
# que `secondaryBackgroundColor` (`.streamlit/config.toml`) et que le CSS
# `light-dark(#ebddc5, #2e2b25)` de `_TYPOGRAPHY_STYLE` juste en dessous --
# réutilisé comme fond EXPLICITE (`chart.properties(background=...)`) de
# chaque graphique Vega-Lite (2026-08-26, retour utilisateur en direct :
# "the background color of the plots should fit the background color of the
# boxes in the application"). Root cause vérifiée : `theme="streamlit"` cale
# le fond par défaut d'un graphique sur `backgroundColor` (le fond de PAGE),
# PAS `secondaryBackgroundColor` (le fond des cartes `_panel()`) -- deux
# tons crème/sombre subtilement différents, un rectangle visible autour de
# chaque graphique dès que le fond d'écran (T-D02) devient net. Fixé en
# fixant le fond de CHAQUE graphique à ce même token, pas en désactivant le
# thème Streamlit (`theme=None` a été essayé puis abandonné ailleurs dans ce
# fichier, voir `_compare_dual_axis_barplot`/T-D09 -- écraserait aussi les
# couleurs catégorielles/grille déjà correctement héritées du thème). Garder
# synchronisé avec `_TYPOGRAPHY_STYLE`/`.streamlit/config.toml` si la palette
# change.
_PANEL_BG_LIGHT = "#ebddc5"
_PANEL_BG_DARK = "#2e2b25"


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
/* Fond des graphiques Vega-Lite EN CSS PUR, `!important` (2026-08-26, retour
   utilisateur en direct : le fond calculé côté Python -- `chart.properties(
   background=panel_bg)`, voir `_PANEL_BG_LIGHT`/`_PANEL_BG_DARK` -- restait
   parfois DÉSYNCHRONISÉ du thème réellement affiché après un bascule Light/
   Dark/System, car `st.context.theme.type` (lu au moment du calcul du
   graphique) ne se met à jour qu'après une VRAIE interaction widget, jamais
   instantanément comme le sélecteur de thème lui-même -- piège déjà
   documenté ailleurs dans ce fichier pour le fond d'écran T50). Vega-Lite
   pose sa couleur de fond en `style="background-color: ..."` À MÊME le
   `<svg>` racine (vérifié en direct, `svg.style.backgroundColor`) -- un
   attribut `style` INLINE, qu'une règle de feuille de style ne bat
   normalement PAS, sauf avec `!important` (ce que fait cette règle) :
   celle-ci gagne alors TOUJOURS, quelle que soit la valeur (parfois
   périmée) que Python avait posée dans la spec Vega-Lite. `light-dark()`
   résout sur `color-scheme` (hérité de `.stApp`, mis à jour INSTANTANÉMENT
   par le sélecteur Streamlit, sans rerun Python) -- même mécanisme fiable
   que `_inject_background`/la règle `_panel()` ci-dessus, jamais de
   décalage possible. `chart.properties(background=...)` (Python) reste en
   place dans chaque fonction de graphique : sert de repli pour un export
   PNG/SVG du graphique (le bouton de téléchargement Vega-Lite utilise la
   spec, pas le DOM/CSS live) -- cette règle CSS ne fait que garantir que
   l'AFFICHAGE À L'ÉCRAN ne dépend plus jamais de la fraîcheur de
   `theme.type`. */
[data-testid="stVegaLiteChart"] svg {
    background-color: light-dark(#ebddc5, #2e2b25) !important;
}
/* T-D14b (2026-08-24, spec Claude Design, lockup "1d — Stacked") : la
   marque (`.hf-logo-mark`) est un `mask-image` (voir `_logo_mask_data_uri`/
   `_logo_html`) recoloré par thème -- même technique à un seul asset que le
   fond d'écran (T-D02), teinte terracotta (accent d'interaction, §8.1),
   PAS la sauge du reste de la roue d'arôme : le logo est chrome de marque,
   pas une donnée. Le mot-symbole reprend Caprasimo (déjà réservé au h1).*/
.hf-logo-mark {
    display: inline-block;
    background-color: light-dark(#c67139, #f6a06b);
    -webkit-mask-size: contain; mask-size: contain;
    -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
    -webkit-mask-position: center; mask-position: center;
}
.hf-logo-word {
    font-family: 'Caprasimo', Figtree, sans-serif;
    color: light-dark(#201e1d, #f9f4ed);
    line-height: 1;
}
/* T82 (2026-08-27) : barre de range sous chaque `st.metric` de vital
   statistic BJCP (`_range_bar_html`) -- piste neutre (mêmes tokens que
   `borderColor`, cohérent avec les séparateurs déjà utilisés ailleurs),
   remplissage soit une teinte sage neutre (ABV/IBU/OG/FG), soit la couleur
   SRM réelle calculée en Python (`_srm_color`, posée en inline `style=`
   par appel -- ce n'est PAS une mesure fixe comme le reste de la palette
   Organic, voir sa docstring). `.hf-range-wrap` (retour utilisateur en
   direct, même jour : les bornes min/max doivent aussi apparaître ÉCRITES
   au-dessus de chaque extrémité de la portion colorée, pas seulement dans
   `st.metric` à gauche) réserve la place au-dessus de la piste pour ces 2
   étiquettes -- `padding-top` plutôt qu'une hauteur fixe, la piste garde sa
   position naturelle en dessous. */
.hf-range-wrap {
    position: relative;
    padding-top: 18px;
}
.hf-range-track {
    position: relative;
    height: 6px;
    border-radius: 3px;
    background-color: light-dark(#dcd3c4, #474238);
}
.hf-range-fill {
    position: absolute;
    top: 0;
    bottom: 0;
    border-radius: 3px;
}
/* Étiquette de borne -- ancrée à l'extrémité correspondante de la piste
   (`left: N%`). Chaque étiquette grandit VERS L'EXTÉRIEUR du segment coloré
   -- `translateX(-100%)` (le texte finit pile à l'ancre, donc s'étend vers
   la GAUCHE) pour la borne min, `translateX(0)` (le texte commence pile à
   l'ancre, s'étend vers la DROITE) pour la borne max (2026-08-27, retour
   utilisateur en direct : une fourchette étroite faisait chevaucher les
   deux étiquettes quand chacune grandissait vers l'INTÉRIEUR l'une vers
   l'autre -- "right adjust the lower end and left adjust the higher range
   value" ; les grandir vers l'extérieur au contraire les écarte TOUJOURS,
   quelle que soit l'étroitesse du segment, sans jamais les faire se
   chevaucher). `translateX(-50%)` (centré) écarté : ferait déborder
   l'étiquette côté extérieur sur les valeurs proches de 0%/100% du
   domaine. */
.hf-range-label {
    position: absolute;
    top: 0;
    font-size: 0.75rem;
    color: light-dark(#56633f, #aebf92);
    white-space: nowrap;
}
.hf-range-label-min { transform: translateX(-100%); }
.hf-range-label-max { transform: translateX(0); }
/* T82 -- voir le commentaire sur `hf_vital_stats` dans `app._styles` :
   police de `st.metric` réduite UNIQUEMENT dans ce conteneur (5 fourchettes
   min-max côte à côte tronquaient à la taille par défaut), jamais les
   autres `st.metric` de l'app. */
div[class*="st-key-hf_vital_stats"] [data-testid="stMetricValue"] {
    font-size: 1.5rem;
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
    background-color: light-dark(__LIGHT_TINT__, __DARK_TINT__);
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


# Teinte du masque de fond (2026-08-26, retour utilisateur en direct : "in
# dark mode we can barely see it and in light mode we don't see it at all").
# ÉTAIT `secondaryBackgroundColor` (`#ebddc5`/`#2e2b25`, "raised surface"
# token) -- vérifié PAR LE CALCUL avant de changer quoi que ce soit (pas
# supposé) : cette teinte ne diffère du fond RÉEL de la page
# (`backgroundColor`, `#f5ead8`/`#201e1d`) que de 10-19 sur 255 par canal,
# quelle que soit l'opacité appliquée -- un simple bump d'opacité (ce que
# l'utilisateur suggérait comme piste) ne peut PAS rendre visible un masque
# dont la couleur est presque IDENTIQUE au fond qu'il recouvre, l'opacité ne
# fait qu'atténuer un écart déjà minuscule. Remplacé par `grayColor`
# (`.streamlit/config.toml`, un token du thème existant, pas une teinte
# choisie à la main) : écart de 77-98/255 avec le fond réel dans les DEUX
# thèmes, un ordre de grandeur plus contrasté, tout en restant un GRIS neutre
# (cohérent avec l'esprit "gravure" du masque, pas une couleur d'accent).
# Opacité PAR THÈME (`__LIGHT_TINT__`/`__DARK_TINT__` en rgba, voir
# `_inject_background` -- `opacity` seul ne peut pas varier par thème sans
# JS, contrairement à l'alpha d'une couleur `light-dark()`) : plus haute en
# clair (`_BACKGROUND_OPACITY_LIGHT`) qu'en sombre
# (`_BACKGROUND_OPACITY_DARK`), demande utilisateur explicite ("more for the
# light mode"). Garder synchronisé avec `.streamlit/config.toml` si la
# palette change.
_GRAY_LIGHT_RGB = "161, 151, 134"  # grayColor clair = #a19786
_GRAY_DARK_RGB = "130, 121, 106"   # grayColor sombre = #82796a
# Rabaissée (2026-08-26, retour utilisateur en direct juste après : "the
# background image is not transparent enough, let's make it more discrete")
# -- le passage à `grayColor` ci-dessus a résolu le vrai problème (contraste
# quasi nul avec l'ancien token), mais avec CE contraste bien plus élevé,
# les mêmes 0.55/0.45 qui rendaient l'image simplement VISIBLE la rendaient
# maintenant trop présente/distrayante. Réduites tout en gardant le même
# écart clair > sombre déjà établi (plus haute en clair, cf. commentaire
# ci-dessus).
_BACKGROUND_OPACITY_LIGHT = 0.28
_BACKGROUND_OPACITY_DARK = 0.22


def _logo_html(mark_px: int, word_px: int) -> str:
    """T-D14b (2026-08-24, spec Claude Design -- lockup "1d — Stacked",
    choisi par l'utilisateur parmi 4 options présentées dans "HopFinder Logo
    Options.dc.html") : marque au-dessus du mot-symbole, aligné à GAUCHE (pas
    centré -- habitude asymétrique du système Organic, spec §3/§5, "flush
    left, not centred"). Remplace `st.image(_LOGO_PATH, ...)` -- un `mask-
    image` CSS ne peut pas être appliqué à un widget `st.image` natif, d'où
    `st.html`. Repli silencieux sur le mot-symbole seul si l'asset masque est
    absent (même garde que `_inject_background` pour le fond d'écran)."""
    word = f'<div class="hf-logo-word" style="font-size:{word_px}px;">HopFinder</div>'
    if not os.path.exists(_LOGO_PATH):
        return word
    mask_uri = _logo_mask_data_uri(_LOGO_PATH, os.path.getmtime(_LOGO_PATH))
    if mask_uri is None:
        return word
    mark_style = (f"width:{mark_px}px; height:{mark_px}px; "
                  f"-webkit-mask-image:url('{mask_uri}'); mask-image:url('{mask_uri}');")
    mark = f'<div class="hf-logo-mark" style="{mark_style}"></div>'
    gap = max(6, word_px // 3)
    return (f'<div style="display:flex; flex-direction:column; align-items:flex-start; '
           f'gap:{gap}px;">{mark}{word}</div>')


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
    de `.stApp`, en hérite directement, sans script.

    La gravure n'est plus qu'un MASQUE alpha (voir `_background_mask_data_
    uri`) peint d'un gris neutre du thème (`grayColor`, voir `_GRAY_LIGHT_RGB`/
    `_GRAY_DARK_RGB` -- PAS `secondaryBackgroundColor` comme au premier passage
    T-D02, voir le commentaire de ces constantes pour le pourquoi du
    changement) à une opacité PROPRE À CHAQUE THÈME (`_BACKGROUND_OPACITY_
    LIGHT`/`_BACKGROUND_OPACITY_DARK`, bakée dans l'alpha rgba de la couleur
    -- `opacity` seul est un scalaire, ne peut pas varier par thème sans JS)
    -- un seul asset pour les deux thèmes, jamais de négatif couleur à
    générer. `position: fixed`
    sur un pseudo-élément `::before` (pas `background-image` direct sur
    `stAppViewContainer`) : évite tout recalcul de `background-size: cover`
    au changement de contenu (le piège de zoom déjà rencontré avec
    `background-attachment: local`, voir l'historique) -- `position: fixed`
    sur un pseudo-élément est stable par construction, ancré au viewport.
    `z-index` posé sur le contenu (`stAppViewBlockContainer`) et l'en-tête
    (`stHeader`) pour rester au-dessus du masque, qui n'occupe que
    `z-index: 0`."""
    # `st.markdown(unsafe_allow_html=True)` pour la typographie/panels, PAS
    # `st.html()` (2026-08-26, bug trouvé en direct) : `_TYPOGRAPHY_STYLE`
    # (quelques Ko) disparaissait SILENCIEUSEMENT du DOM (aucune exception)
    # dès qu'un `st.html()` distinct portant le bloc de fond (~1,7 Mo, base64
    # de l'image masque) était rendu dans la MÊME page -- vérifié que ce
    # n'était pas une histoire de taille de payload concaténé (même en
    # appelant `st.html()` deux fois séparément, un seul des deux survivait
    # dans le DOM final, peu importe l'ordre) : Streamlit semble fusionner/
    # écraser deux éléments `st.html()` consécutifs plutôt que d'en garder
    # deux distincts. Un TYPE D'ÉLÉMENT DIFFÉRENT (`st.markdown` pour l'un,
    # `st.html` pour l'autre) n'est plus sujet à cette fusion -- vérifié en
    # direct après ce changement.
    st.markdown(_TYPOGRAPHY_STYLE, unsafe_allow_html=True)
    if os.path.exists(_BACKGROUND_PATH):
        version = os.path.getmtime(_BACKGROUND_PATH)
        mask_uri = _background_mask_data_uri(_BACKGROUND_PATH, version)
        if mask_uri is not None:
            st.html(
                _BACKGROUND_STYLE_TEMPLATE
                .replace("__MASK_URI__", mask_uri)
                .replace("__LIGHT_TINT__", f"rgba({_GRAY_LIGHT_RGB}, {_BACKGROUND_OPACITY_LIGHT})")
                .replace("__DARK_TINT__", f"rgba({_GRAY_DARK_RGB}, {_BACKGROUND_OPACITY_DARK})")
            )


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


def _render_hop_identity(h: dict) -> None:
    """T106 (2026-08-27) : métadonnées d'identité -- cultivar/breeder/
    release_year (Yakima pour cultivar/is_*, curation manuelle BeerMaverick
    pour breeder/release_year/pedigree, voir data/mappings/hop_breeder_
    pedigree.yaml et ingest._write_hop_identity) et pedigree. Badges
    experimental/organic/blend SEULEMENT quand `1` (jamais affiché sur `0`
    ou `None` -- `0` signifierait "confirmé non expérimental", une
    affirmation qu'on n'a pas). Ligne de texte pour cultivar/breeder/année :
    un champ absent est simplement OMIS de la ligne (jamais de "—", demande
    explicite du ticket -- contrairement au reste de la GUI où "—" marque
    une valeur absente, ici la ligne entière disparaît silencieusement pour
    un houblon sans aucune métadonnée d'identité plutôt que d'afficher une
    ligne de tirets peu utile)."""
    badges = []
    if h.get("is_experimental") == 1:
        badges.append(("Experimental", "orange", ":material/science:"))
    if h.get("is_organic") == 1:
        badges.append(("Organic", "green", ":material/eco:"))
    if h.get("is_blend") == 1:
        badges.append(("Blend", "gray", ":material/call_merge:"))
    if badges:
        with st.container(horizontal=True):
            for label, color, icon in badges:
                st.badge(label, color=color, icon=icon)

    parts = []
    if h.get("cultivar"):
        parts.append(f"Cultivar: {h['cultivar']}")
    if h.get("breeder"):
        parts.append(f"Breeder: {h['breeder']}")
    if h.get("release_year"):
        parts.append(f"Released: {h['release_year']}")
    if parts:
        st.caption(" · ".join(parts))
    if h.get("pedigree"):
        st.caption(f"Pedigree: {h['pedigree']}")


def _render_hop_description(h: dict) -> None:
    """T107 (2026-08-27) : description éditoriale du producteur
    (`imported_fields.description`, Yakima Algolia, nettoyée en markdown --
    `parsers.clean_yakima_description`, jamais le HTML brut). `st.expander`
    REPLIÉ (`_panel_expander`, niveau "Detail" de la hiérarchie à trois
    surfaces T-D04, toujours à l'intérieur d'une carte de section) --
    demande explicite du ticket : c'est du texte MARKETING d'un vendeur,
    jamais présenté comme une caractérisation neutre, même esprit que la
    réserve affichée sur les pairings BeerMaverick. Absent -> rien affiché
    (pas d'expander vide)."""
    if not h.get("description"):
        return
    source_label = {"yakima": "Yakima Chief Hops"}.get(h.get("description_source"), h.get("description_source"))
    with _panel_expander("Producer description"):
        st.caption(f":material/info: Producer description ({source_label}) — "
                  "marketing text from the hop's producer, not a neutral characterization.")
        st.markdown(h["description"])


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
    # Deux phrases sur deux lignes (2026-08-24, retour utilisateur explicite)
    # -- `st.caption` rend du markdown, donc un retour à la ligne markdown
    # ("  \n", deux espaces avant le saut) plutôt qu'un simple "\n" (ignoré
    # par le rendu markdown, aurait recollé les deux phrases sur une ligne).
    if source == "barthhaas":
        return (":material/info: Hover a label for its definition.  \n"
                "Aroma wheel source: BarthHaas (rescaled to a comparable "
                "0-100 range from their own 0-8 scale).")
    return (":material/info: Hover a label for its definition.  \n"
           "Aroma wheel source: Yakima Chief Hop Sensory Ballot.")


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
    # `panel_bg` (2026-08-26, voir `_PANEL_BG_LIGHT`/`_PANEL_BG_DARK` pour le
    # pourquoi complet) : fond EXPLICITE du graphique, pour qu'il se fonde
    # dans la carte `_panel()` qui l'entoure plutôt que d'afficher le fond
    # de PAGE par défaut de `theme="streamlit"`.
    panel_bg = _PANEL_BG_DARK if dark else _PANEL_BG_LIGHT
    # "axis labels at body colour" -- tokens `textColor` réels du thème.
    text_color = "#f9f4ed" if dark else "#201e1d"
    # 8.3 (2026-08-24, retour Claude Design) : "axis spokes at border
    # colour" -- alignés sur les tokens `borderColor` réels du thème
    # (config.toml), pas une teinte de contraste choisie à part.
    grid_color = "#474238" if dark else "#dcd3c4"
    # T-D09/8.1 (2026-08-24, retour Claude Design sur la 1ere passe) : le
    # premier essai de ce ticket avait mis la roue mono-houblon en accent
    # TERRACOTTA -- faux au regard du §8.1 de la spec, qui réserve le
    # terracotta au job "interaction" (boutons/sélection/focus/slider) et
    # assigne la couche descripteurs/roue d'arôme à la voix SAUGE. Corrigé en
    # sauge (mêmes tons que `greenColor`, cohérent avec les chips "fine" T-D05/
    # T-D06) -- un ton par thème (comme avant), pas de `light-dark()` ici
    # (marks Altair "libres", voir docstring de la fonction).
    accent = "#aebf92" if dark else "#7a8a5e"

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
    # T-D09/8.3 (2026-08-24, spec Claude Design, "fill = sage at 25%, stroke
    # = sage") -- `mark_area` CASSÉ ici, corrigé 2026-08-24 (retour
    # utilisateur en direct, capture d'écran à l'appui) : sur des coordonnées
    # x/y libres (pas un axe temporel/catégoriel avec ligne de base), `mark_
    # area` remplit vers le bord du graphique le plus proche plutôt que de
    # refermer le polygone entre les points -- d'où les pointes/triangles
    # aberrants observés (jamais l'étoile fermée attendue). `mark_line` avec
    # `interpolate="linear-closed"` (relie premier et dernier point) +
    # `filled=True` (bascule le remplissage sur `fill`, pas `stroke`, pour un
    # mark line) est le mécanisme Vega-Lite correct pour un polygone fermé
    # sur x/y arbitraires -- `strokeOpacity=0` cache le contour propre à
    # CETTE couche (déjà dessiné, net, par `polygon_line` juste après).
    polygon_fill = (
        alt.Chart(alt.Data(values=poly))
        .mark_line(interpolate="linear-closed", filled=True, fill=accent,
                  fillOpacity=0.25, strokeOpacity=0, order=True)
        .encode(x=x_enc, y=y_enc, order="Order:Q")
    )
    # Trait affiné 2 -> 1.5px (2026-08-24, retour utilisateur explicite,
    # même échange que le passage à 500px : "reducing the size of the line
    # could help reduce the bulkyness of the plot").
    polygon_line = (
        alt.Chart(alt.Data(values=poly))
        .mark_line(color=accent, strokeWidth=1.5, order=True)
        .encode(x=x_enc, y=y_enc, order="Order:Q")
    )
    # size 60 -> 30 (2026-08-24, retour utilisateur explicite : "reduce the
    # size of the points/scatter of the spider chart, it's a bit bulky").
    points = (
        alt.Chart(alt.Data(values=poly[:-1]))
        .mark_point(filled=True, size=30, color=accent)
        .encode(x=x_enc, y=y_enc,
               tooltip=["Descriptor:N", alt.Tooltip("Intensity:Q", format=".0f")])
    )
    text = (
        alt.Chart(alt.Data(values=labels))
        .mark_text(fontSize=12, color=text_color)
        .encode(x=x_enc, y=y_enc, text="Descriptor:N",
               tooltip=["Descriptor:N", "Definition:N"])
    )
    # Taille réduite de 480 à 340px (2026-08-24, retour utilisateur en
    # direct, capture d'écran mobile à l'appui : "the spider plot is too
    # big, on mobile we don't see it full because of the large size") --
    # 480 -> 340 -> 400px -> **500px** (2026-08-24, encore retouché le même
    # jour, retour utilisateur explicite : "let's increase to 500 px
    # instead of 400"). La géométrie interne (`r_max`/`half_extent`,
    # calculée en unités de domaine, pas en pixels) est simplement mise à
    # l'échelle par Vega-Lite, aucun changement de la trigonométrie
    # ci-dessus nécessaire à chaque fois.
    return (
        (grid + polygon_fill + polygon_line + points + text)
        .properties(width=500, height=500, background=panel_bg)
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
    # Champ de recherche texte libre RETIRÉ (2026-08-24, retour utilisateur
    # explicite : "the 'Hop' search bar already has completion functionality"
    # -- `st.selectbox` filtre déjà par frappe (tape-à-tape natif Streamlit),
    # un second champ texte au-dessus était une redondance pure, jamais un
    # filtre supplémentaire (mêmes critères nom/variété que la complétion du
    # selectbox lui-même).
    # T108 : tri par popularité réelle (beer-analytics.com, hop_usage_stats)
    # en plus du tri alphabétique. Popularité PAR DÉFAUT (2026-08-29, retour
    # utilisateur explicite en revue : "so that the dropdown menu is more
    # informative by default" -- le sélecteur "Hop" affiche déjà le nombre
    # de recettes dans son libellé quand ce mode est actif, voir
    # `_format_hop` plus bas). Filtre "quasi jamais utilisé" désactivé par
    # défaut (0 = tout montrer) et affiché SEULEMENT en mode Popularité
    # (retour utilisateur : "otherwise it make no sense to display it" --
    # il n'a aucun effet en tri par nom, ni sur ce qui est montré ni sur
    # l'ordre).
    popularity = matching.hop_popularity(con)
    with _panel():
        sort_mode = st.segmented_control("Sort by", ["Name", "Popularity"],
                                         default="Popularity", key="browse_sort_mode",
                                         required=True)
        min_recipes = 0
        if sort_mode == "Popularity":
            min_recipes = st.slider(
                "Minimum recipes (popularity filter, 0 = show all)", 0, 200, 0,
                key="browse_min_recipes",
                help="Hides hops with fewer than this many recipes on beer-analytics.com. "
                     "Hops with no popularity data at all are never hidden by this filter.")
    varieties = [v for v in hops
                if min_recipes == 0 or popularity.get(v) is None or popularity[v] >= min_recipes]
    if not varieties:
        st.write("No hop matches the current filter.")
        return
    if sort_mode == "Popularity":
        # houblons avec donnée de popularité d'abord (part de recettes
        # décroissante), puis houblons SANS donnée -- groupe "no data" séparé,
        # jamais mélangé au tri numérique avec un 0 implicite (T108).
        with_data = sorted((v for v in varieties if v in popularity), key=lambda v: -popularity[v])
        without_data = sorted((v for v in varieties if v not in popularity),
                              key=lambda v: hops[v]["name"].lower())
        varieties = with_data + without_data
    else:
        varieties = sorted(varieties, key=lambda v: hops[v]["name"].lower())

    def _format_hop(v):
        label = hops[v]["name"]
        if sort_mode == "Popularity":
            count = popularity.get(v)
            label += f" ({count:,} recipes)" if count is not None else " (no popularity data)"
        return label

    selected = st.selectbox("Hop", varieties, format_func=_format_hop, key="browse_hop")
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
        # T106 : identité (cultivar/breeder/release_year/pedigree, badges
        # experimental/organic/blend) -- "juste sous le nom du houblon, avant
        # les key stats" (ticket), placée après purpose/region qui ont une
        # exigence utilisateur antérieure et plus forte d'être EN PREMIER.
        _render_hop_identity(h)
        # T107 : description éditoriale -- "sous les métadonnées de T106"
        # (ticket), donc ici, avant key stats.
        _render_hop_description(h)
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

    # T99 : "Recommended usage", après la roue d'arôme (ticket : "nouvelle
    # carte app._panel(), après la roue d'arôme").
    with _panel():
        _recommended_usage_panel(con, hops, comp, selected)

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
    """Associations houblon<->houblon (T25 backlog, +1 avec T83) : QUATRE
    relations différentes, chacune affichée avec sa propre source — ne
    jamais les présenter comme interchangeables (similarité YCH != co-usage
    recette BeerMaverick != choix éditorial BeerMaverick substitutions !=
    suggestion de style éditoriale Yakima/BeerMaverick). Toutes les listes
    (hors le tableau "Frequent recipe pairings", qui porte une fréquence
    numérique) en chips `_descriptor_chips` (2026-08-27, retour utilisateur
    en direct : cohérence visuelle avec le bloc Descriptors juste au-dessus,
    jamais de texte brut à côté de pilules colorées sur la même carte)."""
    similar = matching.hop_similar_varieties(con, selected)
    st.write("**Similar varieties (Yakima)**")
    if similar:
        # `_descriptor_chips` (2026-08-27, retour utilisateur en direct :
        # "sometimes you are using plain text but should use small tags such
        # as in Descriptors") -- même pilule sage que les descripteurs,
        # cohérence visuelle sur toute la carte "Database similarity and
        # substitution" plutôt qu'un mélange texte brut/chips.
        st.markdown(_descriptor_chips([hops[v]["name"] for v in similar if v in hops]))
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
        st.markdown(_descriptor_chips([
            hops[s["variety"]]["name"] if s["variety"] in hops else s["name"] for s in subs]))
    else:
        st.caption("No BeerMaverick data for this variety.")

    # T83 (2026-08-27, priorité utilisateur explicite "super important") :
    # QUATRIÈME relation, grouped par source comme les descripteurs
    # (`_descriptors_grouped_by_source`) -- Yakima et BeerMaverick ne sont
    # JAMAIS fusionnés (même règle que les 3 relations ci-dessus). Réserve
    # systématique : suggestion éditoriale d'un producteur/agrégateur, PAS
    # une fréquence mesurée en recettes réelles (ça, c'est l'épique B à
    # venir, `style_hop_usage`/beer-analytics — à ne pas confondre).
    styles = matching.hop_beer_styles(con, selected)
    st.write("**Beer styles (editorial suggestion — Yakima/BeerMaverick, "
             "not a measured recipe frequency)**")
    if styles:
        _SOURCE_LABELS = {"yakima": "Yakima", "beermaverick": "BeerMaverick"}
        by_source: dict[str, list[str]] = {}
        for s in styles:
            label = f"{s['label']} ({s['style_id']})" if s["style_id"] else s["label"]
            by_source.setdefault(_SOURCE_LABELS.get(s["source"], s["source"]), []).append(label)
        st.markdown("  \n".join(f"**{src}:** " + _descriptor_chips(labels)
                                for src, labels in by_source.items()))
    else:
        st.caption("No editorial style suggestion for this variety.")


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
# T-D09/8.3 (2026-08-24, retour Claude Design sur la 1ere passe -- "the
# terracotta ramp made 'max intensity' and 'this is a button' the same
# colour") : 5 paliers pris de `chartSequentialColors` (config.toml, rampe
# sauge UNI-teinte, jamais confondue avec terracotta = interaction) --
# remplace le premier essai terracotta de ce même ticket, gardé UN seul
# tour. "absent" aligné sur le fond Organic (`#f5ead8`), "present" (noir)
# inchangé (voir ci-dessus). Légende déjà à labels explicites ("absent"/
# "present"/"0-20"/...), pas juste une barre de dégradé -- l'échelle est
# ordinale/discrète (`Bucket:N`), pas continue, donc déjà conforme à "give
# the legend explicit value labels" sans changement de code supplémentaire.
_INTENSITY_BUCKET_COLORS = ["#f5ead8", "#000000", "#e1eecc", "#aebf92", "#728157", "#3d472b", "#272e1b"]


def _intensity_bucket(value: float) -> str:
    for hi in (20, 40, 60, 80):
        if value < hi:
            return f"{hi - 20}-{hi}"
    return "80-100"


def _heatmap_chart(shown, hop_order, descriptor_order):
    """Une grille houblon x descripteur pour LE SOUS-ENSEMBLE de
    descripteurs donné -- factorisé pour être appelé une fois par section
    (roue quantitative / autres descripteurs, voir `_descriptor_heatmap`)."""
    panel_bg = _PANEL_BG_DARK if st.context.theme.type == "dark" else _PANEL_BG_LIGHT
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
        .properties(width=alt.Step(45), height=alt.Step(18), background=panel_bg)
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
        # T108 : tri par popularité réelle (beer-analytics.com, hop_usage_stats)
        # EN PLUS du tri par pertinence -- pertinence reste le défaut ici
        # (contrairement à Browse, voir son commentaire : ce mode existe
        # justement pour trier par pertinence aromatique, la popularité est
        # un ajout secondaire, pas d'argument "dropdown plus informatif" ici
        # puisqu'il n'y a pas de sélecteur de houblon). Filtre "quasi jamais
        # utilisé" affiché SEULEMENT en mode Popularité (2026-08-29, retour
        # utilisateur explicite : "otherwise it make no sense to display it"
        # -- sans effet en tri par pertinence).
        sort_mode = st.segmented_control("Sort by", ["Relevance", "Popularity"],
                                         default="Relevance", key="by_descriptor_sort_mode",
                                         required=True)
        min_recipes = 0
        if sort_mode == "Popularity":
            min_recipes = st.slider(
                "Minimum recipes (popularity filter, 0 = show all)", 0, 200, 0,
                key="by_descriptor_min_recipes",
                help="Hides hops with fewer than this many recipes on beer-analytics.com. "
                     "Hops with no popularity data at all are never hidden by this filter.")
    if not text_selected and not wheel_selected:
        with _panel():
            st.write("Choose at least one descriptor.")
        return
    r = matching.by_descriptor(con, text_selected, wheel_descriptors=wheel_selected, top=top)
    ranked = r["ranked"]
    total_matches = r["total_matches"]
    if not ranked:
        with _panel():
            st.write("No hop overlaps with these descriptors.")
        return

    popularity = matching.hop_popularity(con)
    if sort_mode == "Popularity" and total_matches > len(ranked):
        # Trier par popularité doit porter sur TOUT le recoupement, pas
        # seulement les `top` premiers déjà coupés par pertinence -- sinon
        # "sort by popularity" ne ferait que réordonner un sous-ensemble
        # choisi par un critère différent, pas le vrai palmarès popularité
        # parmi tout ce qui matche réellement les descripteurs.
        r = matching.by_descriptor(con, text_selected, wheel_descriptors=wheel_selected,
                                   top=total_matches)
        ranked = r["ranked"]

    n_before_filter = len(ranked)
    if min_recipes > 0:
        ranked = [h for h in ranked
                 if popularity.get(h["variety"]) is None or popularity[h["variety"]] >= min_recipes]
    n_hidden_by_filter = n_before_filter - len(ranked)

    if sort_mode == "Popularity":
        # houblons avec donnée de popularité d'abord (part de recettes
        # décroissante), puis houblons SANS donnée -- groupe "no data" séparé,
        # jamais mélangé au tri numérique avec un 0 implicite (T108).
        with_data = sorted((h for h in ranked if h["variety"] in popularity),
                           key=lambda h: -popularity[h["variety"]])
        without_data = [h for h in ranked if h["variety"] not in popularity]
        ranked = with_data + without_data
    ranked = ranked[:top]

    if total_matches > len(ranked) or n_hidden_by_filter > 0:
        # Transparence sur la troncature (2026-08-20, revue de code — même
        # principe que `contrast`/T56 : jamais laisser croire que "Number of
        # hops shown" couvre tout le recoupement réel).
        parts = [f"Showing {len(ranked)} of {total_matches} hops overlapping these descriptors"]
        if n_hidden_by_filter > 0:
            parts.append(f"{n_hidden_by_filter} hidden by the popularity filter")
        with _panel():
            st.caption(" — ".join(parts) + ". Raise \"Number of hops shown\" or lower the "
                      "popularity filter above to see more.")

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
            # T108 : transparence du tri popularité -- montré uniquement quand
            # ce tri est actif, même esprit que le caption quant_score ci-dessus
            # (jamais un réordonnancement silencieux).
            if sort_mode == "Popularity":
                pop_count = popularity.get(h["variety"])
                st.caption(f"Popularity: {pop_count:,} recipes (beer-analytics.com)"
                          if pop_count is not None else
                          "Popularity: no data (beer-analytics.com does not cover this hop)")
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
# houblons). T-D09 (2026-08-23, spec Claude Design §8) : remplace l'ancienne
# palette Vega "tableau10" par `chartCategoricalColors` (config.toml).
# **Corrigé le 2026-08-24** (retour Claude Design sur ce premier essai) :
# les 5 teintes Organic "chaudes" choisies au premier tour (terracotta/sauge/
# terracotta foncé/sauge clair/neutre chaud) ne différaient qu'en VALEUR, pas
# en TEINTE -- cinq houblons se seraient effondrés en nuances de rouille sur
# le radar, un vrai défaut signalé avant même d'être testé en direct avec 5
# houblons. Nouvelle palette (spec §8.2) : 5 teintes réparties sur le cercle
# chromatique, encore dans le registre Organic (tons moyens, pas saturés),
# ORDONNÉES pour que les cas à 2/3 houblons (les plus fréquents) tombent sur
# les paires les plus robustes -- bleu/orange (denim/terracotta) survit à
# toute forme de daltonisme. Chaque teinte clarifie ≥3:1 sur LES DEUX fonds
# (`#f5ead8` clair ET `#201e1d` sombre) -- `chartCategoricalColors` ne peut
# pas être fixé par thème, donc jamais un ton d'extrémité de rampe (`#402310`/
# `#f0fae1`), qui échouerait sur l'un des deux fonds.
_COMPARE_PALETTE = ["#4f86b8", "#c67139", "#7f9455", "#d9a441", "#a5678a"]
# La spec §8.2 suggérait aussi un `strokeDash` distinct par série sur le
# radar, en plus de la couleur -- ESSAYÉ puis RETIRÉ (2026-08-24, retour
# utilisateur en direct : "using different shape of lines per hop in the
# radar is not working at all... it's a mess"). Le motif pointillé rendait
# les polygones illisibles là où ils se croisent (l'inverse du but), la
# nouvelle palette (5 teintes déjà réparties sur le cercle chromatique,
# testée séparément et jugée bonne) suffit seule -- ne pas réintroduire de
# `strokeDash` sans un nouveau retour explicite.
_COMPARE_MAX_HOPS = 5

# T-D09b (2026-08-24, spec Claude Design §8.3, retour utilisateur : "the
# radar shrinks when a hop has a long name") -- abréviation du suffixe de
# désambiguïsation (`matching._disambiguate_hop_names`, T60) DANS LA LÉGENDE
# SEULEMENT du radar Compare, jamais dans les tooltips/tableaux/autres pages
# (le nom complet y reste, voir `_legend_abbr_expr` -- une expression Vega
# `labelExpr`, pas une transformation des données elles-mêmes). Ensemble
# FERMÉ vérifié en direct sur la base réelle (`SELECT DISTINCT region FROM
# hops`, 13 valeurs, 2026-08-24) -- pas une supposition de codes ISO.
_REGION_ABBR = {
    "Australia": "AU", "China": "CN", "Czech Republic": "CZ", "France": "FR",
    "Germany": "DE", "Great Britain": "GB", "Japan": "JP", "New Zealand": "NZ",
    "Poland": "PL", "Slovenia": "SI", "Styrian (Slovenia/Austria)": "SI/AT",
    "United Kingdom": "GB", "United States": "US",
}


def _abbreviate_region_suffix(name: str) -> str:
    """"Saaz (Czech Republic)" -> "Saaz · CZ" ; un nom sans suffixe de
    désambiguïsation (pas de collision, T60) est renvoyé tel quel."""
    m = re.match(r"^(.*) \(([^)]+)\)$", name)
    if not m:
        return name
    base, region = m.groups()
    return f"{base} · {_REGION_ABBR.get(region, region)}"


def _legend_abbr_expr(names: list[str]) -> str:
    """Expression Vega `labelExpr` -- réécrit UNIQUEMENT le texte affiché
    dans la légende (`datum.label`), jamais les données/tooltips sous-jacents.
    Chaîne de ternaires par nom réellement présent dans la sélection courante
    (au plus 5, `_COMPARE_MAX_HOPS`) -- pas une regex Vega, `labelExpr`
    n'exécute qu'une expression Vega simple, jamais du JS/Python arbitraire."""
    expr = "datum.label"
    for name in names:
        short = _abbreviate_region_suffix(name)
        if short != name:
            expr = f"datum.label === {json.dumps(name)} ? {json.dumps(short)} : ({expr})"
    return expr

# Largeur PARTAGÉE, littérale (pas de Step ni de "stretch") des 2 barplots
# de Compare Hops (2026-08-19, retour utilisateur en direct : "I would like
# all 3 plots to be the same width... ensure the spider plot is properly
# scaled (not narrow)"). Root cause du désalignement initial : les 3
# graphiques utilisaient 3 stratégies de largeur DIFFÉRENTES --
# `width="content"` figé à 480px pour le radar (petit, carré) vs
# `width="stretch"` (rempli le conteneur, beaucoup plus large) pour les
# barplots avec une largeur interne `alt.Step(70)` (dépend du nombre de
# catégories, pas de la largeur du conteneur). Résultat : trois largeurs
# incohérentes. Corrigé À L'ÉPOQUE en fixant une largeur numérique EXPLICITE,
# IDENTIQUE sur les 3 (`properties(width=_COMPARE_CHART_WIDTH)`).
#
# **Revu le 2026-08-24** (retour utilisateur en direct, capture d'écran
# mobile à l'appui : "the spider plot is too big, on mobile we don't see it
# full because of the large size") -- le radar utilise désormais SA PROPRE
# taille (`_COMPARE_RADAR_SIZE`, voir plus bas), plus `_COMPARE_CHART_WIDTH`.
# Le "same width" de 2026-08-19 visait le radar À CETTE ÉPOQUE trop ÉTROIT
# par rapport aux barplots (largeur "content" ratée, pas une largeur voulue
# petite) -- l'exigence utilisateur ACTUELLE, plus récente et plus précise,
# porte sur la taille MOBILE du radar spécifiquement, jamais sur les
# barplots (délibérément larges/défilants, T-D09c) : les deux graphiques ne
# sont plus jamais côte à côte dans la mise en page (chacun dans sa propre
# carte de section, T-D04), l'alignement pixel entre eux n'a plus de valeur
# fonctionnelle réelle.
_COMPARE_CHART_WIDTH = 700
# 500px (voir `_aroma_wheel` pour l'historique complet des tailles
# essayées -- 480 -> 340 -> 400 -> 500, retour utilisateur explicite à
# chaque étape) -- même valeur que le radar mono-houblon pour rester
# cohérent entre les deux versions du composant.
_COMPARE_RADAR_SIZE = 500

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


def _compare_field_db_values(comp: dict, field: str, absolute: bool) -> list[float]:
    """Toutes les valeurs CONNUES d'UN composé à travers TOUT `comp` (toutes
    les variétés de la base, pas seulement les houblons sélectionnés dans
    Compare Hops) -- socle de la normalisation min-max/quantile (2026-08-24,
    demande utilisateur explicite : "for each molecule you look at the known
    value across all hops in the database"). Même conversion d'unité
    (`absolute`, voir `_compare_detail_value`) que la barre affichée --
    mélanger des valeurs en % d'huile avec des valeurs absolues ml/100g pour
    un même composé fausserait complètement le classement."""
    values = []
    for hcomp in comp.values():
        v = _compare_detail_value(hcomp, field, absolute)
        if v is not None:
            values.append(v)
    return values


# Plancher de position normalisée (2026-08-26, bug signalé par l'utilisateur :
# "if I enter Columbus and Nugget, without normalization Columbus has a Thiol
# data, but with normalization we lose it"). Root cause vérifiée en direct :
# Columbus porte le thiol MINIMUM connu de toute la base (0.7 ug_kg, sur 22
# houblons mesurés) -- `_normalize_minmax` renvoyait donc exactement 0.0, et
# `mark_bar` (`_compare_detail_barplot`) a un `x2` implicite à la valeur DE
# DONNÉE 0 en mode linéaire (jamais au minimum du domaine) : une barre dont
# `Value == 0` a `x == x2`, largeur nulle, INVISIBLE -- exactement le même
# mécanisme déjà documenté et corrigé pour l'échelle log (`_log_scale_and_
# baseline`), mais jamais traité côté Min-max/Quantile jusqu'ici. Un houblon
# au minimum de la base n'est pas une donnée absente (elle EST là, `RawValue`
# le montre au survol) -- seule la barre doit rester visible. Plancher
# arbitrairement petit (2% de la largeur du domaine [0, 1]) : assez fin pour
# ne pas fausser visuellement une comparaison entre deux vraies valeurs
# proches du minimum, assez large pour rester un trait visible/survolable.
_COMPARE_MIN_NORMALIZED_POSITION = 0.02


def _normalize_minmax(value: float, db_values: list[float]) -> float:
    """Position min-max de `value` dans `db_values` (0 = minimum connu de la
    base pour ce composé, 1 = maximum). Cas dégénéré (une seule valeur
    connue dans toute la base, ou toutes identiques -- `hi == lo`) : 1.0
    plutôt qu'une division par zéro -- ce houblon EST le maximum (et le
    minimum) connu, une barre pleine plutôt qu'un 0.5 arbitraire qui
    suggérerait une position "moyenne" non fondée sur rien. Résultat plancé
    à `_COMPARE_MIN_NORMALIZED_POSITION` (jamais exactement 0.0) -- voir le
    commentaire de cette constante : une position à 0 rendrait une barre
    invisible (largeur nulle) dans `_compare_detail_barplot`, alors que la
    donnée existe bel et bien (houblon au minimum connu, pas une donnée
    manquante)."""
    lo, hi = min(db_values), max(db_values)
    if hi == lo:
        return 1.0
    return max((value - lo) / (hi - lo), _COMPARE_MIN_NORMALIZED_POSITION)


def _normalize_quantile(value: float, db_values: list[float]) -> float:
    """Rang quantile de `value` dans `db_values` (0 = parmi les plus bas
    connus, 1 = parmi les plus hauts), moyenne des rangs bas/haut
    (`bisect_left`/`bisect_right`) pour rester correct sur des valeurs à
    égalité plutôt qu'un rang arbitraire entre doublons. Cas dégénéré (une
    seule valeur connue dans toute la base) : 1.0, même raison que
    `_normalize_minmax`. Même plancher `_COMPARE_MIN_NORMALIZED_POSITION`
    (même raison : une position à 0 -- possible ici sur une base à un seul
    élément connu avant le cas dégénéré ci-dessus, ou par construction si
    jamais `bisect_left` renvoyait 0 ET `bisect_right` aussi -- resterait une
    barre invisible dans `_compare_detail_barplot`)."""
    n = len(db_values)
    if n <= 1:
        return 1.0
    sorted_values = sorted(db_values)
    lo = bisect.bisect_left(sorted_values, value)
    hi = bisect.bisect_right(sorted_values, value)
    return max((lo + hi) / (2 * n), _COMPARE_MIN_NORMALIZED_POSITION)


# T99 : les 4 agrégats "survivables" YCH réellement présents dans
# `hop_composition` (voir CLAUDE.md "Ce que les agrégats BarthHaas
# contiennent" -- `isobutyrate` recouvre 3 des 8 survivables Yakima Chief,
# `thiols` en recouvre 3 aussi, `linalool`/`geraniol` sont chacun un
# composé unique). Le méthyl géranate (composé le plus abondant des
# survivables sur les lots YCH testés, voir CLAUDE.md) N'EST couvert par
# AUCUN de nos agrégats -- absent de cette liste, trou documenté, jamais
# comblé par une estimation.
_RECOMMENDED_USAGE_CHEMICAL_COMPOUNDS = ["linalool", "geraniol", "isobutyrate", "thiols"]

# Ordre d'affichage des 5 étapes réelles de `hop_usage_stats` (T88,
# beer-analytics.com) -- vérifié en direct (`SELECT DISTINCT use_type`),
# procédé chaud -> froid.
_USAGE_STAGE_ORDER = ["Mash", "First Wort", "Boil", "Aroma", "Dry Hop"]


def _chemical_earliness_index_all(hops: dict, comp: dict) -> dict[str, dict]:
    """T99, couche (b) CHIMIQUE : pour chaque houblon de la base, indice
    dérivé des règles 1/2 du handbook YCH 2022 (voir CLAUDE.md) appliquées
    à NOS mesures -- PAS une mesure directe des survivables (l'API de lot
    YCH a été explicitement écartée comme socle, voir CLAUDE.md : "source
    ABANDONNÉE comme socle systématique"). Moyenne du rang quantile PAR
    COMPOSÉ (`_RECOMMENDED_USAGE_CHEMICAL_COMPOUNDS`) sur TOUTE la base --
    réutilise `_normalize_quantile`/`_compare_field_db_values`/
    `_compare_detail_value` déjà écrits pour Compare Hops (ticket : "ne pas
    en réécrire un"), jamais une normalisation ad hoc. Indice élevé ->
    plutôt whirlpool/dry hop en fermentation active (règles 1 et 4) ; bas ->
    plutôt réservé au dry hop post-fermentation (règle 2).

    Composé sans mesure pour un houblon donné -> simplement omis de SA
    moyenne (jamais un 0 fabriqué qui tirerait l'indice vers le bas
    artificiellement). Houblon sans AUCUN des 4 composés mesurés -> absent
    du dict, jamais un indice fabriqué à partir de rien.

    Calcule les valeurs DB-wide de chaque composé UNE SEULE FOIS
    (`_compare_field_db_values`) puis les réutilise pour chaque houblon,
    plutôt que de les recalculer pour chacun des n houblons (O(n) au lieu
    de O(n^2))."""
    db_values = {c: _compare_field_db_values(comp, c, absolute=False)
                for c in _RECOMMENDED_USAGE_CHEMICAL_COMPOUNDS}
    out: dict[str, dict] = {}
    for v in hops:
        hcomp = comp.get(v, {})
        positions, used = [], []
        for c in _RECOMMENDED_USAGE_CHEMICAL_COMPOUNDS:
            value = _compare_detail_value(hcomp, c, absolute=False)
            if value is None:
                continue
            positions.append(_normalize_quantile(value, db_values[c]))
            used.append(c)
        if positions:
            out[v] = {"index": sum(positions) / len(positions), "compounds": used}
    return out


def _usage_share_db_values(usage_all: dict[str, dict], use_type: str) -> list[float]:
    """Toutes les parts (`share`) connues d'UNE étape (`use_type`) à travers
    TOUS les houblons de `hop_usage_breakdown_all` -- socle du rang
    quantile de "à quel point CE houblon est-il plus/moins utilisé en
    whirlpool que la moyenne de la base", même mécanisme que
    `_compare_field_db_values` côté composés (T99, divergence)."""
    return [rec[use_type]["share"] for rec in usage_all.values() if use_type in rec]


def _recommended_usage_panel(con, hops: dict, comp: dict, variety: str) -> None:
    """T99 : panneau "Recommended usage" dans Browse, DEUX couches jamais
    fusionnées :
    (a) EMPIRIQUE -- `hop_usage_stats` (T88), ce que font réellement les
        brasseurs, aucune modélisation.
    (b) CHIMIQUE -- indice dérivé des règles YCH appliqué à nos mesures,
        étiqueté "estimated from composition" partout, jamais présenté au
        même niveau qu'une donnée mesurée (même traitement que le préfixe
        `Inferred:` de `infer_purpose_from_alpha_acid`).

    **Livrable réel du ticket** : les signaler CÔTE À CÔTE et pointer les
    divergences plutôt que les cacher -- "un houblon chimiquement 'tardif'
    mais massivement utilisé en whirlpool est l'information la plus
    intéressante de la page". Détecté ici en comparant le rang quantile
    DB-wide de l'indice chimique de ce houblon à celui de sa part
    "Aroma" (whirlpool) empirique -- sous la médiane de la base pour l'un,
    au-dessus pour l'autre -- plutôt qu'un seuil absolu arbitraire (même
    logique DB-relative que le reste de cette normalisation)."""
    st.subheader("Recommended usage")
    breakdown = matching.hop_usage_breakdown(con, variety)
    chem_all = _chemical_earliness_index_all(hops, comp)
    chem = chem_all.get(variety)
    if not breakdown and chem is None:
        st.caption("No usage data (empirical or chemical) for this variety.")
        return

    col_a, col_b = st.columns(2)
    with col_a:
        st.write("**Where brewers actually use it**")
        st.caption("Share of recipes by process stage (beer-analytics.com) -- observed, not modeled.")
        if breakdown:
            rows = [{"Stage": stage, "Share": breakdown[stage]["share"],
                    "Recipes": breakdown[stage]["recipes_count"]}
                   for stage in _USAGE_STAGE_ORDER if stage in breakdown]
            st.dataframe(rows, width="stretch", hide_index=True, column_config={
                "Share": st.column_config.NumberColumn(format="percent"),
                "Recipes": st.column_config.NumberColumn(format="%d"),
            })
        else:
            st.caption("No beer-analytics.com data for this variety.")
    with col_b:
        st.write("**Estimated from composition**")
        st.caption("YCH \"survivable compounds\" rules applied to our own measurements "
                  "-- not a lab measurement of this hop.")
        if chem is not None:
            st.metric("Early-use index (whirlpool / active dry hop)", f"{chem['index']:.0%}")
            st.caption("Quantile rank of " + ", ".join(chem["compounds"]) +
                      " vs. every hop in the database. High = favors whirlpool/active "
                      "fermentation dry hop (rules 1 & 4); low = better reserved for "
                      "post-fermentation dry hop (rule 2). Estimated from composition, "
                      "not a lab measurement -- methyl geranate (the most abundant "
                      "survivable on tested YCH lots) is not covered by any of our "
                      "aggregates.")
        else:
            st.caption("No linalool/geraniol/isobutyrate/thiols measurement for this variety.")

    if chem is not None and "Aroma" in breakdown:
        chem_db_values = [c["index"] for c in chem_all.values()]
        usage_all = matching.hop_usage_breakdown_all(con)
        aroma_db_values = _usage_share_db_values(usage_all, "Aroma")
        chem_rank = _normalize_quantile(chem["index"], chem_db_values)
        aroma_rank = _normalize_quantile(breakdown["Aroma"]["share"], aroma_db_values)
        if chem_rank < 0.5 and aroma_rank >= 0.5:
            st.info(":material/priority_high: Divergence: this hop's composition leans "
                   "toward late (post-fermentation) dry hop, yet it's used in whirlpool/"
                   "aroma additions more than most hops in the database. Not an error -- "
                   "brewers may be using it that way on purpose (or for reasons this "
                   "index doesn't capture, e.g. bittering contribution, cost, tradition).")
        elif chem_rank >= 0.5 and aroma_rank < 0.5:
            st.info(":material/priority_high: Divergence: this hop's composition leans "
                   "toward early use (whirlpool/active fermentation dry hop), yet it's "
                   "used in whirlpool/aroma additions less than most hops in the "
                   "database -- brewers may be favoring straight dry hop instead.")


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
    # `gridColor` explicite (2026-08-26, retour utilisateur en direct : les
    # lignes de grille des ticks étaient visibles en thème SOMBRE mais
    # totalement invisibles en thème CLAIR) -- la couleur de grille par
    # défaut de `theme="streamlit"` n'a jamais été pensée pour le fond crème
    # de la palette Organic (contraste quasi nul contre `#f5ead8`). Clair :
    # token `borderColor` réel (`#dcd3c4`, `.streamlit/config.toml`). Sombre :
    # PAS ce même token (`#474238`) -- essayé d'abord, signalé trop
    # contrasté/clair en direct contre le fond sombre (`#201e1d`/`#2e2b25`) ;
    # assombri à mi-chemin entre ce token et le fond (`#34302b`, jamais une
    # teinte de contraste choisie au hasard).
    dark = st.context.theme.type == "dark"
    grid_color = "#34302b" if dark else "#dcd3c4"
    # `panel_bg` (2026-08-26, voir `_PANEL_BG_LIGHT`/`_PANEL_BG_DARK`) : fond
    # explicite du graphique, pour qu'il se fonde dans la carte `_panel()`
    # qui l'entoure au lieu du fond de PAGE par défaut de `theme="streamlit"`.
    panel_bg = _PANEL_BG_DARK if dark else _PANEL_BG_LIGHT
    # Bande alternée (2026-08-26, retour utilisateur explicite : "reuse the
    # 2nd barplot alternated background color to separate axis categories
    # for the 1st barplot as well") -- même mécanisme et même teinte "6%
    # neutral" que `_compare_detail_barplot` (voir son docstring), tourné à
    # 90° : une bande PLEINE HAUTEUR (`y=0`/`y2=height`, pas `x`/`x2` comme
    # sur l'autre barplot -- ici `Field` est sur X, catégoriel, pas Y) tous
    # les deux champs.
    band_color = "#f9f4ed" if dark else "#201e1d"
    height = 320
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
    # `paddingOuter=0.2` (2026-08-26, retour utilisateur en direct : la bande
    # alternée -- voir plus bas -- ne "collait" pas aux groupes de barres,
    # quel que soit le nombre de houblons comparés) : marge visuelle entre
    # chaque groupe de barres et le bord de sa bande, plutôt que des barres
    # collées aux bords (défaut Vega-Lite pour un `xOffset` sans padding
    # explicite).
    offset_enc = alt.XOffset("Hop:N", scale=alt.Scale(domain=list(colors.keys()), paddingOuter=0.2))
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
    layers = [
        alt.Chart(alt.Data(values=[{"Field": f} for i, f in enumerate(field_order) if i % 2 == 1]))
        .mark_rect(opacity=0.06, color=band_color)
        .encode(x=x_enc, y=alt.value(0), y2=alt.value(height)),
    ]
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
                   y=alt.Y("Value:Q", title=primary_title,
                          axis=alt.Axis(gridColor=grid_color))))
    if secondary_rows:
        layers.append(
            alt.Chart(alt.Data(values=secondary_rows)).mark_bar()
            .encode(x=x_enc, xOffset=offset_enc, color=color_enc, tooltip=tooltip,
                   y=alt.Y("Value:Q", title=secondary_title,
                          axis=alt.Axis(gridColor=grid_color))))
    if not primary_rows and not secondary_rows:
        # `layers` contient TOUJOURS au moins la bande alternée désormais --
        # ne plus tester `not layers` (ne serait plus jamais vrai) pour
        # décider s'il y a réellement quelque chose à tracer.
        return None
    chart = alt.layer(*layers).resolve_scale(y="independent")
    return chart.properties(width=_COMPARE_CHART_WIDTH, height=height, background=panel_bg)


def _compound_display_label(compound: str) -> str:
    """Nom AFFICHÉ d'un composé sur l'axe de `_compare_detail_barplot`
    (2026-08-24, demande utilisateur explicite : "put capital letters...
    and use an actual beta symbol for beta-pinene") -- jamais la clé de
    donnée `Field` elle-même (inchangée, réutilisée pour les bandes
    alternées/le survol/le tooltip/`matching.compound_descriptors`, etc.).

    `beta-pinene` traité à PART -- **bug trouvé en vérification live** :
    `"beta-pinene".replace("beta-", "β-")` puis `.upper()` sur le premier
    caractère met le β en MAJUSCULE grecque (Β), visuellement indissociable
    d'un simple "B" latin dans la plupart des polices -- l'inverse du but
    ("an actual beta symbol"). Convention chimique réelle respectée à la
    place : le préfixe grec reste TOUJOURS en minuscule (β-pinene), jamais
    capitalisé, quelle que soit sa position dans le libellé."""
    if compound.startswith("beta-"):
        return "β-" + compound[len("beta-"):]
    return compound[:1].upper() + compound[1:]


# Catégories chimiques du barplot 2 (2026-08-26/27, demande utilisateur
# explicite, mapping "HYDROCARBONS / OXYGEN CONTAINING / SULFUR CONTAINING"
# fourni, recoupé composé par composé contre `reference.PROCESS_SURVIVAL`
# (T74) -- REUTILISE cette structure plutôt que d'en dupliquer une nouvelle :
# la taxonomie class/subclass y est déjà sourcée (Scott Janish, *The New
# IPA*, figure "Chemical compositions of the essential oils of hops") et
# vérifiée composé par composé pour les 11 champs réels de `hop_composition`.
# Seule divergence avec le mapping fourni : `PROCESS_SURVIVAL` regroupe
# esters ET cétones sous UNE sous-classe ("Other (ketones, esters,
# aldehydes, epoxides)", confidence="low") -- BarthHaas n'indique jamais
# QUELLE molécule précise compose "isobutyrate"/"ketones", les séparer en
# deux sous-classes distinctes serait une supposition non vérifiable (même
# réserve déjà documentée pour le refus de deviner un CID PubChem sur un nom
# flou).
#
# Historique de ce composant (retours utilisateur successifs en
# vérification live, avant la version actuelle) :
# (1) 1er essai : colonne "classe" REMPLIE d'une couleur pleine -- signalé
#     par l'utilisateur comme un DOUBLON de code couleur ("there is already
#     a color code (per hop color)"), retiré.
# (2) Raccourcir les libellés trop longs ("Ketones & esters", "Monoterpenols")
#     pour les faire tenir sur UNE ligne pivotée -- signalé insuffisant par
#     l'utilisateur lui-même ("enforce that all text... fits the space
#     allocated... don't hesitate to use \\n") : retiré au profit du multi-
#     ligne RÉEL (3).
# (3) `mark_text(lineBreak="\\n")` scinde un libellé multi-mots sur son
#     ESPACE naturel (vérifié en direct, isolé hors Streamlit -- voir le
#     commentaire de `_compare_category_gutter` -- que `lineBreak` doit être
#     posé EXPLICITEMENT, Vega-Lite n'auto-détecte pas un "\\n" nu) -- une
#     fois pivoté à 90°, chaque ligne devient une COLONNE côte à côte plutôt
#     qu'un empilement vertical. Seuls les MOTS UNIQUES sans espace
#     ("Sesquiterpenes", "Monoterpenes", "Thiols") ne peuvent pas être
#     scindés proprement ; `_CATEGORY_ROW_HEIGHT_FLOOR` garantit qu'ils
#     tiennent malgré tout, même sur un groupe d'une seule ligne.
# (4) 2026-08-27, second retour utilisateur -- couleur+contour sur le
#     texte de classe/sous-classe/composé, `\\n` multi-ligne pivoté --
#     ESSAYÉ puis RETIRÉ au (5) ci-dessous, voir son détail (une régression
#     de rendu Vega-Lite propre au texte pivoté multi-ligne, pas juste un
#     choix esthétique annulé).
# (5) 2026-08-27, TROISIÈME retour utilisateur -- 8 points, tous traités
#     ensemble ici :
#     - "the plot is now super wide, doesn't enter in a PC screen" +
#       "duplication of legends" -- LA MÊME cause : `resolve_scale(color=
#       "independent")` avait été posé sur la couche INTERNE de
#       `_compare_detail_barplot` (`alt.layer(*layers)`) pour isoler le
#       "Class" de `compound_label` (alors teinté par catégorie, voir (4))
#       du "Hop" des barres -- mais `resolve_scale` à ce niveau rend TOUTES
#       les couches indépendantes LES UNES DES AUTRES, pas seulement de
#       `compound_label` : la barre primaire ET la barre secondaire (même
#       champ "Hop", même domaine) se sont retrouvées avec 2 échelles/
#       légendes SÉPARÉES au lieu d'UNE partagée -- d'où la légende "Hop"
#       DUPLIQUÉE, chacune ajoutant sa propre largeur de légende au rendu
#       final (la vraie cause du "super wide", pas la largeur nominale du
#       graphique lui-même). Résolu à la racine par (6) ci-dessous : sans
#       teinte de catégorie sur `compound_label`, il n'y a plus qu'UN SEUL
#       canal "color" (Hop) dans cette couche -- `resolve_scale(color=...)`
#       n'est plus nécessaire ici du tout, seul `x="independent"` (barre
#       primaire/secondaire, préexistant) reste.
#     - "increase a bit the size of the main categories... exactly the mean
#       of the size of the categories and the label name" --
#       `_CATEGORY_SUBCLASS_FONT_SIZE` n'est plus une constante indépendante
#       mais `(_CATEGORY_CLASS_FONT_SIZE + _CATEGORY_COMPOUND_FONT_SIZE) /
#       2`, calculée -- garantit la moyenne EXACTE demandée, jamais
#       approximée à la main.
#     - "separation between subcategories is still not super visible" --
#       `_run_boundary_rules` (inchangée dans son mécanisme) rendue plus
#       contrastée : `strokeWidth` doublé (1 -> 2) et couleur portée à
#       `text_color` (opaque, même teinte que le texte neutre) plutôt que
#       `grid_color` (pensé pour un quadrillage discret, pas une frontière
#       de catégorie -- les 2 usages n'ont pas la même exigence de
#       contraste).
#     - "remove the colored text with contour, it doesn't work... rely on
#       the colored bars and better separation" -- RETIRÉ entièrement : le
#       texte de classe/sous-classe/composé redevient `text_color` neutre
#       statique, sans `color=` encodé ni `stroke`. Le "colored bar" =
#       LA BRACKET (`_compare_category_gutter`, inchangée, reste teintée
#       par classe) ; la séparation renforcée ci-dessus complète le signal
#       visuel sans dépendre de la couleur du texte.
#     - "Monoterpene alcohols is not centered on its box" -- root cause
#       RÉELLE trouvée en isolant le rendu hors Streamlit (page Vega-Embed
#       minimale, comme pour le bug du barplot log T-D09c) : Vega ne fait
#       PAS pivoter le décalage inter-lignes d'un texte multi-ligne
#       (`lineBreak`) AVEC le glyphe -- le décalage `lineHeight` reste
#       appliqué en axe Y du document AVANT rotation, donc un bloc 2-lignes
#       pivoté à 90° se retrouve désaxé et chevauche la ligne voisine (
#       constaté noir sur blanc : "Monoterpene\\nalcohols" débordait
#       visiblement sur la ligne de "Sesquiterpenes" juste en dessous).
#       PAS une limite de centrage seule -- une limite de rendu Vega pour
#       la combinaison (multi-ligne + pivoté) tout court. Le multi-ligne
#       (`lineBreak`, introduit au tour précédent) est donc entièrement
#       ABANDONNÉ : tous les libellés repassent à UNE seule ligne,
#       raccourcis si besoin (voir juste en dessous) -- `align="center"`/
#       `baseline="middle"` posés explicitement (au lieu du défaut Vega-Lite)
#       centrent alors correctement un libellé à une ligne.
#     - "'Sulfur compounds' should be renamed 'Sulfur comps.'" -- ce
#       raccourci, combiné à l'abandon du multi-ligne ci-dessus, permet
#       aussi de raccourcir "Oxygen containing" -> "Oxygen cont." (même
#       style d'abréviation) : les 3 classes ET les 5 sous-classes tiennent
#       maintenant TOUTES sur une ligne, mesuré empiriquement (page de test
#       isolée) -- 69.5px pour le mot le plus long ("Sesquiterpenes"),
#       jamais plus.
#     - "reduce the width allocated to categories and subcategories" -- une
#       fois le texte redescendu à 1 ligne (fini le besoin de 2 colonnes de
#       texte côte à côte après pivot), l'épaisseur RÉELLE d'une ligne
#       pivotée mesurée (11.5px à ces tailles de police) rend les anciennes
#       largeurs (38/50px) très excessives -- réduites à 20/22px
#       (`_COMPARE_CATEGORY_CLASS_WIDTH`/`_COMPARE_CATEGORY_SUBCLASS_WIDTH`).
#     - "in main, barplot 2 is the same width as barplot 1 -- keep this"
#       -- `_COMPARE_DETAIL_BAR_WIDTH` (nouveau) retire la largeur du
#       gutter de `_COMPARE_CHART_WIDTH` pour la seule zone des BARRES de
#       ce barplot, pour que la largeur TOTALE (gutter + barres) reste
#       identique à `_COMPARE_CHART_WIDTH` -- donc identique au barplot 1
#       ("Principal info", qui n'a pas de gutter et utilise `_COMPARE_
#       CHART_WIDTH` en entier), au lieu de s'y ajouter en plus.
_CATEGORY_SUBCLASS_DISPLAY = {
    "Monoterpene alcohols": "Monoterpenols",
    "Other (ketones, esters, aldehydes, epoxides)": "Ketones/esters",
}
_CATEGORY_CLASS_DISPLAY = {
    "Oxygen containing": "Oxygen containing comp.",  # T125 (2026-08-27) : libellé complet, la place a été confirmée par l'utilisateur
    "Sulfur compounds": "Sulfur comp.",  # 2026-08-27, 4e retour : "comps." débordait encore de sa boîte
}
_CATEGORY_UNCATEGORIZED = "Uncategorized"
# Couleur "classe" -- 3 teintes prises dans les 5 dernières entrées de
# `chartCategoricalColors` (.streamlit/config.toml), JAMAIS dans les 5
# premières : `_COMPARE_PALETTE` (couleur par houblon, dans la MÊME vue)
# n'utilise que les 5 premières (`_COMPARE_MAX_HOPS`) -- confondre la
# couleur d'une catégorie chimique avec la couleur d'identité d'un houblon
# affiché juste à côté serait trompeur. Depuis (5) ci-dessus, sert
# UNIQUEMENT à teinter la "bracket" (`_compare_category_gutter`) -- plus
# aucun texte n'est teinté par catégorie (voir (5)).
_CATEGORY_CLASS_COLORS = {
    "Hydrocarbons": "#2f6f6a",           # teal
    "Oxygen containing": "#8c491a",      # deep terracotta
    "Sulfur compounds": "#56633f",       # deep sage
    _CATEGORY_UNCATEGORIZED: "#82796a",  # warm neutral -- ne devrait jamais s'afficher (T74 couvre les 11 composés réels)
}
# Largeur des 2 colonnes du gutter -- réduite au minimum utile (5) : texte à
# UNE seule ligne pivotée (~11.5px d'épaisseur mesurée), plus la fine
# bracket colorée sur la colonne sous-classe.
_COMPARE_CATEGORY_CLASS_WIDTH = 20
_COMPARE_CATEGORY_SUBCLASS_WIDTH = 22
# Largeur de la bracket colorée, à l'extrémité GAUCHE de la colonne
# sous-classe (contre la colonne classe) -- un simple repère visuel, jamais
# un canal de donnée à lui seul.
_CATEGORY_BRACKET_WIDTH = 4
# Plancher de hauteur de ligne -- garantit qu'un groupe d'UNE SEULE ligne
# (le pire cas : n'importe quel houblon peut, selon sa composition mesurée,
# laisser une sous-classe/classe entière réduite à 1 seul composé présent)
# reste assez haut pour loger le plus long libellé à une ligne
# ("Sesquiterpenes", 69.5px mesuré empiriquement en direct -- page de test
# Vega-Embed isolée, voir l'historique (5) ci-dessus). S'applique en PLUS de
# la formule habituelle (`n_hops * 14 + 18`, `_compare_detail_barplot`) via
# `max(...)` -- ne la réduit jamais, l'augmente seulement quand elle serait
# insuffisante.
_CATEGORY_ROW_HEIGHT_FLOOR = 78
_CATEGORY_CLASS_FONT_SIZE = 13
_CATEGORY_COMPOUND_FONT_SIZE = 12
# Moyenne EXACTE des 2 tailles ci-dessus (demande utilisateur explicite :
# "exactly the mean of the size of the categories... and the label name") --
# calculée, jamais approximée à la main.
_CATEGORY_SUBCLASS_FONT_SIZE = (_CATEGORY_CLASS_FONT_SIZE + _CATEGORY_COMPOUND_FONT_SIZE) / 2
# Largeur de la colonne "noms de composés" (2026-08-27, 4e retour
# utilisateur : "the plot is still too wide, reduce it... to be as large as
# the first barplot") -- root cause RÉELLE du dépassement persistant malgré
# `_COMPARE_DETAIL_BAR_WIDTH` (voir son historique) : les noms de composés
# étaient un `mark_text` custom positionné sur l'axe Y natif rendu invisible
# (`labelOpacity=0`), gardé UNIQUEMENT pour que Vega-Lite réserve la MÊME
# marge gauche qu'avant -- mais cette marge est calculée par Vega-Lite lui-
# même (taille dépendante du contenu, ex. "Caryophyllene") et s'ajoute EN
# PLUS de la largeur `width` déclarée, donc EN PLUS de tout calcul basé sur
# `_COMPARE_CHART_WIDTH` -- jamais pris en compte par `_COMPARE_DETAIL_BAR_
# WIDTH`, d'où le dépassement qui persistait. Corrigé en sortant les noms de
# composés dans leur PROPRE colonne `hconcat` (4e panneau, largeur EXPLICITE
# comme les 2 du gutter) : le barplot de barres n'a alors plus AUCUN axe Y
# natif (`axis=None` pur, aucune marge implicite), toute la largeur reste
# comptée. Largeur mesurée empiriquement (page de test isolée) : "Caryo
# phyllene" (le plus long nom réel), 63.9px -- marge de sécurité modeste.
_COMPARE_CATEGORY_COMPOUND_WIDTH = 72
# Nombre de jointures `hconcat` entre les 4 panneaux (classe | sous-classe |
# noms de composés | barres), chacune espacée de 2px (`alt.hconcat(...,
# spacing=2)`) -- utilisé pour calculer `_COMPARE_DETAIL_BAR_WIDTH`
# ci-dessous.
_COMPARE_DETAIL_HCONCAT_SPACING = 2
# Surcoût de largeur RENDU mesuré empiriquement (2026-08-27, en direct dans
# le navigateur, `svg.getAttribute("width")`) une fois la légende retirée
# (voir `color_enc` de `_compare_detail_barplot`, "legend=None") et les 4
# largeurs de panneau posées : le SVG final restait à 728px pour 700
# déclarés (28px de trop), alors que le barplot 1 (une seule vue, PAS un
# `hconcat`) rend EXACTEMENT sa largeur déclarée sans surcoût. Un `hconcat`
# semble ajouter un petit padding par panneau (4 panneaux ici) au-delà de
# `spacing` -- jamais confirmé dans la doc Vega-Lite, mesuré directement
# plutôt que supposé. Soustrait de `_COMPARE_DETAIL_BAR_WIDTH` pour que la
# largeur RENDUE (pas seulement déclarée) corresponde à celle du barplot 1,
# demande utilisateur explicite : "reduce it... to be as large as the
# first barplot".
_COMPARE_DETAIL_HCONCAT_OVERHEAD = 28
# Largeur de la seule zone "barres" du barplot détaillé (2026-08-27, demande
# utilisateur explicite : "in main, barplot 2 is the same width as barplot
# 1 -- keep this") -- `_COMPARE_CHART_WIDTH` MOINS le gutter ET la colonne
# de noms de composés (classe + sous-classe + noms + 3 jointures `hconcat`)
# MOINS le surcoût mesuré ci-dessus, pour que la largeur TOTALE RENDUE
# (gutter + noms + barres) reste égale à `_COMPARE_CHART_WIDTH` -- comme le
# barplot 1 ("Principal info", `_compare_dual_axis_barplot`) qui n'a pas de
# gutter et utilise `_COMPARE_CHART_WIDTH` en entier -- jamais gutter/noms
# EN PLUS de cette largeur, ce qui rendait le graphique plus large que
# l'écran.
_COMPARE_DETAIL_BAR_WIDTH = (_COMPARE_CHART_WIDTH - _COMPARE_CATEGORY_CLASS_WIDTH
                            - _COMPARE_CATEGORY_SUBCLASS_WIDTH - _COMPARE_CATEGORY_COMPOUND_WIDTH
                            - 3 * _COMPARE_DETAIL_HCONCAT_SPACING - _COMPARE_DETAIL_HCONCAT_OVERHEAD)


def _compound_category(compound: str) -> tuple[str, str, str]:
    """(classe, sous-classe BRUTE, sous-classe AFFICHÉE) pour `compound` --
    lecture pure de `matching.process_survival` (T74), voir le commentaire
    au-dessus de `_CATEGORY_SUBCLASS_DISPLAY`. Composé non mappé (ne devrait
    jamais arriver sur les composés réels actuels) -> les 3 valeurs valent
    `_CATEGORY_UNCATEGORIZED`, jamais un crash ni un groupe fabriqué qui
    semblerait sourcé."""
    info = matching.process_survival(compound)
    if info is None:
        return _CATEGORY_UNCATEGORIZED, _CATEGORY_UNCATEGORIZED, _CATEGORY_UNCATEGORIZED
    subclass = info["subclass"]
    return info["class"], subclass, _CATEGORY_SUBCLASS_DISPLAY.get(subclass, subclass)


def _category_group_order() -> dict[tuple[str, str], int]:
    """Ordre canonique (classe, sous-classe brute) -- position de première
    apparition dans `reference.PROCESS_SURVIVAL` (ordre d'INSERTION du dict,
    garanti en Python 3.7+), utilisé pour grouper les composés du barplot 2
    PAR CATÉGORIE CHIMIQUE plutôt que par valeur brute (2026-08-26, demande
    utilisateur explicite : "add the categories of molecules... make
    something very easy to read and understand the categories"). Calculé
    une seule fois au chargement du module -- la taxonomie ne change qu'au
    code, jamais aux données d'un houblon particulier."""
    order: dict[tuple[str, str], int] = {}
    for info in matching.reference.PROCESS_SURVIVAL.values():
        key = (info["class"], info["subclass"])
        if key not in order:
            order[key] = len(order)
    return order


_CATEGORY_GROUP_ORDER = _category_group_order()


def _contiguous_runs(field_order: list[str], keys: list) -> list[tuple[int, int]]:
    """Paires (index de début, index de fin INCLUS) des runs contigus de
    `keys` identiques dans `field_order` (`keys` aligné index-à-index) --
    brique de base pour les labels de groupe ET pour la "bracket" colorée
    (`_compare_category_gutter`)."""
    runs = []
    i, n = 0, len(field_order)
    while i < n:
        j = i
        while j + 1 < n and keys[j + 1] == keys[i]:
            j += 1
        runs.append((i, j))
        i = j + 1
    return runs


def _contiguous_group_labels(field_order: list[str], keys: list, labels: list[str]
                             ) -> list[tuple[str, str, bool]]:
    """Une entrée (Field ANCRE, label AFFICHÉ, `on_boundary`) par run contigu
    de `keys` identiques dans `field_order` (`keys`/`labels` alignés index-à-
    index sur `field_order` -- `labels` peut différer de `keys`, ex. sous-
    classe raccourcie pour l'affichage vs sous-classe brute pour le
    regroupement). Un SEUL label par groupe de lignes consécutives -- pas
    une ligne par composé, ce qui répéterait un texte pivoté à 90° sur
    chaque ligne d'un même groupe et le ferait se chevaucher avec lui-même
    verticalement.

    2026-08-27, 3e retour utilisateur ("Oxygen cont.", "Monoterpenols" et
    "Ketones/esters" pas centrés) -- root cause vérifiée en direct : l'ancre
    `i + (j - i) // 2` (division entière) retombe TOUJOURS sur une ligne
    RÉELLE, correcte pour un run à nombre IMPAIR de lignes (la ligne du
    milieu existe réellement, ex. Sesquiterpenes à 3 lignes -> Caryophyllene)
    mais biaisée vers le HAUT pour un run à nombre PAIR (le vrai centre
    géométrique tombe exactement à la FRONTIÈRE entre les 2 lignes du
    milieu, sur aucune ligne réelle -- ex. Oxygen containing, 4 lignes :
    vrai centre entre Geraniol et Ketones, PAS sur Geraniol seul).
    `on_boundary=True` (run pair) signale à l'appelant d'ancrer le texte via
    `bandPosition=1` sur la PREMIÈRE des 2 lignes du milieu -- le BAS de
    cette ligne coïncide exactement avec la frontière, donc avec le vrai
    centre (vérifié hors Streamlit avant intégration, isolé comme les autres
    mécanismes `bandPosition` de ce fichier). `on_boundary=False` (run
    impair) : ancre normale (`bandPosition` par défaut, déjà correcte)."""
    out = []
    for i, j in _contiguous_runs(field_order, keys):
        n = j - i + 1
        if n % 2 == 1:
            mid = i + n // 2
            out.append((field_order[mid], labels[mid], False))
        else:
            mid = i + n // 2 - 1
            out.append((field_order[mid], labels[mid], True))
    return out


def _contiguous_group_spans(field_order: list[str], keys: list
                            ) -> list[tuple[str, str]]:
    """(Field de début, Field de fin) par run contigu de `keys` identiques
    -- pour la "bracket" colorée de `_compare_category_gutter`, qui doit
    couvrir EXACTEMENT la plage d'un groupe (du haut de sa première ligne au
    bas de sa dernière), pas seulement son point milieu. Repose sur
    `alt.Y(..., bandPosition=0)`/`alt.Y2(..., bandPosition=1)` (Vega-Lite
    v5+, vérifié disponible et correct hors Streamlit avant intégration --
    voir le commentaire de `_compare_category_gutter`) plutôt qu'un
    empilement de rects pleine-largeur par ligne (aurait remis en place le
    "color code" de remplissage que l'utilisateur a explicitement demandé de
    retirer)."""
    return [(field_order[i], field_order[j]) for i, j in _contiguous_runs(field_order, keys)]


def _category_color_scale() -> alt.Scale:
    """Échelle couleur "classe chimique" partagée entre `_compare_category_
    gutter` (texte classe/sous-classe + bracket) et `_compare_detail_
    barplot` (noms de composés sur l'axe Y, 2026-08-27) -- un seul objet de
    référence pour ce mapping, jamais reconstruit différemment à 2 endroits."""
    return alt.Scale(domain=list(_CATEGORY_CLASS_COLORS.keys()),
                     range=list(_CATEGORY_CLASS_COLORS.values()))


def _compare_category_gutter(field_order: list[str], height: int,
                             grid_color: str, text_color: str
                             ) -> tuple[alt.Chart, alt.Chart] | None:
    """Les 2 colonnes "catégorie chimique" (classe, sous-classe) affichées à
    GAUCHE de `_compare_detail_barplot` par l'appelant, via `alt.hconcat`
    (2026-08-26/27, demande utilisateur explicite, mapping fourni recoupé
    contre `reference.PROCESS_SURVIVAL` -- voir le commentaire au-dessus de
    `_CATEGORY_SUBCLASS_DISPLAY`). Retourne `None` si `field_order` est vide,
    sinon `(class_chart, subclass_chart)`, chacun SANS `background` -- cette
    propriété est TOPLEVEL-ONLY pour Altair (une erreur explicite si posée
    sur un sous-spec d'un `hconcat`) : l'appelant l'applique une seule fois
    sur le `hconcat` final, pas ici. L'assemblage final (`hconcat` avec
    `detail_chart`) reste aussi chez l'appelant, pas ici, pour éviter un
    `hconcat` imbriqué dans un autre. MÊME domaine `field_order`/MÊME
    `height` que le barplot principal -- Vega-Lite calcule alors des
    positions de bande identiques dans les vues juxtaposées (un alignement
    ligne-à-ligne fiable).

    Design retenu après plusieurs retours utilisateur en vérification live
    -- voir le commentaire complet au-dessus de `_CATEGORY_SUBCLASS_DISPLAY`
    pour l'historique (notamment (5), qui a fait marche arrière sur le
    texte teinté+contour du tour précédent). État ACTUEL :
    - **Colonne "classe"** ET **colonne "sous-classe"** : texte NEUTRE
      (`text_color`, statique -- ni teinte de catégorie ni contour, retirés
      au (5) : "remove the colored text with contour... rely on the
      colored bars and better separation"), `align="center"`/
      `baseline="middle"` posés EXPLICITEMENT (le défaut Vega-Lite ne
      centre pas forcément un texte pivoté sur son ancre -- vérifié en
      direct que ces 2 propriétés le garantissent). `_CATEGORY_CLASS_FONT_
      SIZE` > `_CATEGORY_SUBCLASS_FONT_SIZE` (celle-ci = moyenne EXACTE
      avec `_CATEGORY_COMPOUND_FONT_SIZE`, voir cette constante).
    - **Bracket** : seul élément encore COLORÉ par catégorie (`_category_
      color_scale`) -- fine bande verticale (`_CATEGORY_BRACKET_WIDTH`) au
      bord gauche de la colonne sous-classe, s'étendant EXACTEMENT du haut
      de la première ligne au bas de la dernière ligne d'un run de
      sous-classe contigu (`_contiguous_group_spans`, `alt.Y(bandPosition=
      0)`/`alt.Y2(bandPosition=1)` -- vérifié fiable hors Streamlit avant
      intégration) : répond à la demande explicite "we need brackets or at
      least vertical bar to help visual mapping between compound name and
      sub-categories", et sert maintenant de repère catégoriel PRINCIPAL
      depuis (5) (texte redevenu neutre).
    - **Séparateurs de run** : un `mark_rule` HORIZONTAL à CHAQUE frontière
      de run (`_contiguous_runs`, bandPosition=1 sur le dernier composé du
      run), `strokeWidth=2`/`text_color` (opaque -- pas `grid_color`, pensé
      pour un quadrillage discret, insuffisant ici : "separation between
      subcategories is still not super visible") -- la classe/sous-classe
      précédente partage parfois la MÊME teinte que la suivante (2
      sous-classes d'une même classe), donc le changement de couleur seul
      ne suffit pas à signaler la frontière ; ce trait EXPLICITE le fait,
      indépendamment de la couleur.
    - Texte pivoté à 90°, ancré à la ligne du milieu de chaque run contigu
      (`_contiguous_group_labels`) -- jamais répété sur chaque ligne. Un
      `mark_rule` vertical neutre (grid_color) à la frontière de chaque
      colonne sépare les 3 zones (classe / sous-classe / composés+barres)."""
    if not field_order:
        return None
    classes = [_compound_category(f)[0] for f in field_order]
    class_display = [_CATEGORY_CLASS_DISPLAY.get(c, c) for c in classes]
    raw_subclasses = [_compound_category(f)[1] for f in field_order]
    display_subclasses = [_compound_category(f)[2] for f in field_order]

    y_scale = alt.Scale(domain=field_order)
    class_color_scale = _category_color_scale()

    def _run_boundary_rules(keys: list, width: float) -> alt.Chart:
        """Un `mark_rule` HORIZONTAL par frontière entre 2 runs contigus de
        `keys` (toutes sauf la dernière, qui n'a rien après elle) -- voir
        "Séparateurs de run" ci-dessus."""
        runs = _contiguous_runs(field_order, keys)
        boundary_rows = [{"Field": field_order[j]} for _, j in runs[:-1]]
        return (alt.Chart(alt.Data(values=boundary_rows)).mark_rule(color=text_color, strokeWidth=2)
               .encode(y=alt.Y("Field:N", scale=y_scale, axis=None, bandPosition=1),
                      x=alt.value(0), x2=alt.value(width)))

    def _label_layers(entries: list[tuple[str, str, bool]], x_value: float,
                      **text_kwargs) -> list[alt.Chart]:
        """1 ou 2 couches `mark_text` selon `_contiguous_group_labels` :
        les runs à nombre IMPAIR de lignes (ancre normale) et les runs à
        nombre PAIR (ancre `bandPosition=1`, voir cette fonction) ne
        peuvent PAS partager la même couche -- `bandPosition` est une
        propriété de SPEC, pas encodable par ligne de données ; vérifié hors
        Streamlit que les combiner correctement (au lieu de forcer `band
        Position=1` partout, qui aurait décalé les runs impairs) exige bien
        2 couches distinctes."""
        centered = [{"Field": f, "Label": lbl} for f, lbl, on_boundary in entries if not on_boundary]
        on_boundary_rows = [{"Field": f, "Label": lbl} for f, lbl, on_boundary in entries if on_boundary]
        layers = []
        if centered:
            layers.append(alt.Chart(alt.Data(values=centered)).mark_text(**text_kwargs)
                          .encode(y=alt.Y("Field:N", scale=y_scale, axis=None),
                                 x=alt.value(x_value), text="Label:N"))
        if on_boundary_rows:
            layers.append(alt.Chart(alt.Data(values=on_boundary_rows)).mark_text(**text_kwargs)
                          .encode(y=alt.Y("Field:N", scale=y_scale, axis=None, bandPosition=1),
                                 x=alt.value(x_value), text="Label:N"))
        return layers

    class_label_layers = _label_layers(
        _contiguous_group_labels(field_order, classes, class_display),
        _COMPARE_CATEGORY_CLASS_WIDTH / 2,
        angle=90, fontSize=_CATEGORY_CLASS_FONT_SIZE, fontWeight=700,
        align="center", baseline="middle", color=text_color)
    class_boundaries = _run_boundary_rules(classes, _COMPARE_CATEGORY_CLASS_WIDTH)
    class_divider = (
        alt.Chart(alt.Data(values=[{}])).mark_rule(color=grid_color, strokeWidth=1)
        .encode(x=alt.value(_COMPARE_CATEGORY_CLASS_WIDTH),
               y=alt.value(0), y2=alt.value(height)))
    class_chart = alt.layer(*class_label_layers, class_boundaries, class_divider).properties(
        width=_COMPARE_CATEGORY_CLASS_WIDTH, height=height)

    # Bracket : une ligne par run de SOUS-CLASSE contigu (pas de classe --
    # une sous-classe ne s'étend jamais sur 2 classes, ce niveau est donc
    # déjà le plus fin utile), teinte = classe parente du run (prise sur son
    # premier composé, tous les composés d'un même run partagent la même
    # classe par construction).
    subclass_spans = _contiguous_group_spans(field_order, raw_subclasses)
    bracket_rows = []
    for start, end in subclass_spans:
        cls = _compound_category(start)[0]
        bracket_rows.append({"Start": start, "End": end, "Class": cls})
    bracket = (
        alt.Chart(alt.Data(values=bracket_rows))
        .mark_rect()
        .encode(y=alt.Y("Start:N", scale=y_scale, axis=None, bandPosition=0),
               y2=alt.Y2("End:N", bandPosition=1),
               x=alt.value(0), x2=alt.value(_CATEGORY_BRACKET_WIDTH),
               color=alt.Color("Class:N", scale=class_color_scale, legend=None),
               tooltip=[alt.Tooltip("Class:N", title="Class")]))
    subclass_label_layers = _label_layers(
        _contiguous_group_labels(field_order, raw_subclasses, display_subclasses),
        _CATEGORY_BRACKET_WIDTH + (_COMPARE_CATEGORY_SUBCLASS_WIDTH - _CATEGORY_BRACKET_WIDTH) / 2,
        angle=90, fontSize=_CATEGORY_SUBCLASS_FONT_SIZE, align="center", baseline="middle",
        color=text_color)
    subclass_boundaries = _run_boundary_rules(raw_subclasses, _COMPARE_CATEGORY_SUBCLASS_WIDTH)
    subclass_divider = (
        alt.Chart(alt.Data(values=[{}])).mark_rule(color=grid_color, strokeWidth=1)
        .encode(x=alt.value(_COMPARE_CATEGORY_SUBCLASS_WIDTH),
               y=alt.value(0), y2=alt.value(height)))
    subclass_chart = alt.layer(bracket, *subclass_label_layers, subclass_boundaries,
                               subclass_divider).properties(
        width=_COMPARE_CATEGORY_SUBCLASS_WIDTH, height=height)

    return class_chart, subclass_chart


def _compare_compound_names_column(field_order: list[str], height: int,
                                   grid_color: str, text_color: str) -> alt.Chart:
    """Colonne "noms de composés" affichée entre le gutter et les barres de
    `_compare_detail_barplot`, via `alt.hconcat` (2026-08-27, 4e retour
    utilisateur -- voir le commentaire de `_COMPARE_CATEGORY_COMPOUND_
    WIDTH` pour la root cause du dépassement de largeur que cette colonne
    corrige). MÊME domaine `field_order`/MÊME `height` que le gutter et le
    barplot de barres -- alignement ligne-à-ligne fiable, un mark_text PAR
    LIGNE (pas de regroupement -- chaque composé est sa propre ligne, pas
    de multi-lignes à centrer comme dans `_compare_category_gutter`).
    `align="right"` : le nom colle contre la frontière avec les barres,
    comme un axe Y classique. Texte neutre (`text_color`, statique) --
    jamais teinté par catégorie ni contourné, voir l'historique de
    `_CATEGORY_SUBCLASS_DISPLAY`."""
    y_scale = alt.Scale(domain=field_order)
    label = (
        alt.Chart(alt.Data(values=[{"Field": f, "Label": _compound_display_label(f)}
                                   for f in field_order]))
        .mark_text(align="right", baseline="middle", dx=-4,
                  fontSize=_CATEGORY_COMPOUND_FONT_SIZE, color=text_color)
        .encode(y=alt.Y("Field:N", scale=y_scale, axis=None, title=None),
               x=alt.value(_COMPARE_CATEGORY_COMPOUND_WIDTH), text="Label:N"))
    divider = (
        alt.Chart(alt.Data(values=[{}])).mark_rule(color=grid_color, strokeWidth=1)
        .encode(x=alt.value(_COMPARE_CATEGORY_COMPOUND_WIDTH),
               y=alt.value(0), y2=alt.value(height)))
    return alt.layer(label, divider).properties(
        width=_COMPARE_CATEGORY_COMPOUND_WIDTH, height=height)


def _compare_detail_barplot(rows: list[dict], primary_fields: list[str], primary_title: str,
                            secondary_fields: list[str], secondary_title: str,
                            colors: dict[str, str],
                            descriptors: dict[str, str] | None = None,
                            process_notes: dict[str, str] | None = None,
                            log_scale: bool = False,
                            x_domain: tuple[float, float] | None = None,
                            value_tooltip_title: str | None = None,
                            raw_value_title: str | None = None,
                            primary_db_values: list[float] | None = None,
                            secondary_db_values: list[float] | None = None):
    """T-D09c (2026-08-24, spec Claude Design §8.3, retour utilisateur sur le
    premier essai de ce ticket) : version HORIZONTALE de
    `_compare_dual_axis_barplot`, réservée au seul barplot "Detailed
    composition" (2e graphique de Compare Hops, jusqu'à 11 composés x 5
    houblons) -- "five adjacent thin bars per compound, read left-to-right,
    is the hardest possible arrangement to compare". Le barplot "Principal
    info" (4 champs seulement) garde l'ancienne disposition verticale
    (`_compare_dual_axis_barplot`), pas concerné par ce ticket.

    Composés sur Y (`yOffset` par houblon), valeur sur X -- inverse de
    `_compare_dual_axis_barplot`. Même contrat `rows`/`descriptors`/
    `process_notes` que la fonction sœur (voir sa docstring pour le détail
    du mécanisme de survol par couche rect invisible, ici tournée de 90°).

    Hauteur CALCULÉE (`24 + n_compounds * (n_hops * 14 + 18)`) plutôt que
    fixe : les barres gardent une épaisseur constante quel que soit le
    nombre de houblons/composés, la carte défile au lieu de se comprimer.

    Composés triés par valeur MAXIMALE décroissante (séparément par groupe
    d'échelle -- primaire puis secondaire, ex. thiols toujours en dernier :
    unités différentes, ml/100g vs µg/kg, comparer leurs maxima bruts n'aurait
    pas de sens) -- les composés qui différencient le plus les houblons
    remontent en haut.

    Bande alternée (un `mark_rect` à 6% neutre derrière un groupe de composé
    sur deux) : "this is what actually separates the groups" -- posée EN
    PREMIER (donc sous tout le reste). `x`/`x2` fixés à `0`/`_COMPARE_CHART_
    WIDTH` en dur (pas une expression Vega `{"expr": "width"}`, plus fragile)
    puisque la largeur du graphique est déjà une constante partagée
    (`_COMPARE_CHART_WIDTH`) -- même trick pour la couche de survol
    "Smells like"/"Process", elle aussi tournée de 90°.

    `log_scale` (2026-08-24, demande utilisateur explicite : "some compounds
    are in too small quantity to have discrimination on the barplot... a
    logarithmic scale toggle") : bascule les DEUX échelles X (primaire ET
    secondaire -- thiols inclus, même défaut) sur `type="log"`. Une valeur
    de 0 est INVALIDE sur une échelle log (Vega-Lite ne peut pas placer un
    point à log(0)) -- ces lignes sont retirées AVANT le tracé si `log_scale`
    est actif, jamais affichées comme une barre nulle fabriquée ; l'aide du
    toggle (`app._compare`) le signale explicitement, honnêteté d'abord.

    **`mark_bar` + échelle log, root cause TROUVÉE en reproduisant le bug
    HORS Streamlit** (page HTML minimale, Vega-Embed seul, spec Vega-Lite
    écrite à la main, 2026-08-24 -- 2 tentatives précédentes insuffisantes :
    `scale.zero=False` explicitement ignoré par Vega-Lite sur une échelle
    log ; un `scale.domain` positif explicite laissait le graphique VIDE
    quand même). Isolé via `view.scale('x').domain()` dans la page de test :
    le DOMAINE de l'échelle était correct, le problème est ailleurs --
    `mark_bar` calcule sa ligne de base en fixant implicitement `x2` à la
    valeur DE DONNÉE 0 (jamais au minimum du domaine de l'échelle), et
    `log(0) = -Infinity` rend la largeur de la barre invalide. Corrigé en
    fournissant `x2` explicitement (`alt.X2Datum`, une CONSTANTE, pas un
    champ) égale au minimum du domaine choisi (`_log_scale_and_baseline`,
    10% EN DESSOUS de la plus petite valeur réelle -- une barre dont la
    valeur est EXACTEMENT ce minimum aurait une largeur nulle sinon,
    invisible) : chaque barre part de CE minimum plutôt que de 0, un calcul
    valide sur une échelle log. `mark_bar` reste utilisé dans les DEUX
    modes désormais (barres, jamais des points -- essayé puis abandonné :
    "I want barplot not scatterplot", retour utilisateur explicite). En
    mode linéaire (`log_scale=False`), aucun `x2` n'est fourni, le
    comportement par défaut (barres depuis 0) reste inchangé.

    `x_domain`/`value_tooltip_title`/`raw_value_title` (2026-08-24, retour
    utilisateur explicite : le simple toggle log ci-dessus remplacé côté
    `_compare` par un menu déroulant "Normalization" -- None / Min-max /
    Quantile / Log). Min-max et Quantile ne changent RIEN ici -- ce sont des
    modes LINÉAIRES ordinaires (`log_scale=False`), la transformation a déjà
    eu lieu côté APPELANT (`app._compare`, voir `_normalize_minmax`/
    `_normalize_quantile`) sur `rows[i]["Value"]`, qui arrive donc déjà dans
    [0, 1]. Cette fonction n'a besoin de savoir que DEUX choses en plus du
    cas linéaire brut : (1) `x_domain=(0, 1)` fige le domaine des DEUX
    échelles X plutôt que de laisser Vega-Lite zoomer sur l'étendue réelle
    des seuls houblons SÉLECTIONNÉS -- un domaine auto-zoomé rendrait le
    "0 = minimum de la base / 1 = maximum" affiché par le titre de l'axe
    FAUX pour la sélection courante (2 barres qui semblent aux extrêmes du
    graphique alors qu'elles sont en réalité proches l'une de l'autre dans
    la vraie base) ; (2) `raw_value_title`, ajoute la valeur BRUTE (avant
    normalisation, stockée par l'appelant dans `rows[i]["RawValue"]`) comme
    2e ligne de tooltip -- la normalisation cache sinon complètement
    l'amplitude réelle (myrcène 3.2 ml/100g et thiols 0.0004 µg/kg
    deviennent tous deux "0.81", ce qui serait malhonnête sans le chiffre
    brut à côté). Pas de trick `X2Datum` nécessaire pour ces deux modes :
    contrairement à log(0), une valeur normalisée de 0 est un point valide
    sur une échelle linéaire, `x2` implicite à 0 fonctionne nativement."""
    if not rows:
        return None
    descriptors = descriptors or {}
    process_notes = process_notes or {}
    if log_scale:
        rows = [r for r in rows if r["Value"] > 0]
        if not rows:
            return None
    hop_names = list(colors.keys())
    n_hops = len(hop_names)

    # Tri PAR CATÉGORIE CHIMIQUE d'abord (2026-08-26, demande utilisateur
    # explicite -- voir `_compound_category`/`_CATEGORY_GROUP_ORDER`), PUIS
    # sur `RawValue` (valeur BRUTE, avant normalisation min-max/quantile --
    # absente en mode None/Log, `Value` EST déjà la valeur brute dans ces 2
    # cas, `.get(..., r["Value"])` couvre les deux) comme départage DANS
    # chaque groupe (2026-08-24, retour utilisateur explicite : "I want you
    # to keep the same order of molecules across different normalisations...
    # Myrcene as first element" -- toujours respecté : Myrcene reste en tête
    # de son groupe "Monoterpenes", premier groupe canonique). Sans le tri
    # par catégorie, les composés d'une même famille chimique (ex. les 4
    # sesquiterpènes) se retrouvaient dispersés sur l'axe selon leur seule
    # concentration, rendant la nouvelle colonne de catégorie (`_compare_
    # category_gutter`) illisible -- des groupes non contigus sur l'axe.
    def _sorted_by_max(fields: list[str]) -> list[str]:
        present = [f for f in fields if any(r["Field"] == f for r in rows)]

        def sort_key(f: str) -> tuple[int, float]:
            cls, subclass, _ = _compound_category(f)
            idx = _CATEGORY_GROUP_ORDER.get((cls, subclass), len(_CATEGORY_GROUP_ORDER))
            max_val = max(r.get("RawValue", r["Value"]) for r in rows if r["Field"] == f)
            return (idx, -max_val)

        return sorted(present, key=sort_key)

    field_order = _sorted_by_max(primary_fields) + _sorted_by_max(secondary_fields)
    if not field_order:
        return None
    n_compounds = len(field_order)
    # `max(..., _CATEGORY_ROW_HEIGHT_FLOOR)` (2026-08-27, demande utilisateur
    # explicite -- voir le commentaire de cette constante) : la formule
    # habituelle (`n_hops * 14 + 18`) seule pouvait laisser un groupe d'une
    # seule ligne trop bas pour loger le texte pivoté de sa catégorie/sous-
    # catégorie sans chevaucher son voisin -- s'applique à TOUTES les lignes
    # (une seule hauteur de bande pour tout le graphique), pas seulement
    # celles d'un petit groupe, d'où un effet visible même sur un graphique
    # sans lien avec la catégorie qui en avait besoin.
    row_height = max(n_hops * 14 + 18, _CATEGORY_ROW_HEIGHT_FLOOR)
    height = 24 + n_compounds * row_height

    dark = st.context.theme.type == "dark"
    # Bande alternée "6% neutral" (spec §8.3) : le vrai fond de carte est
    # `light-dark(#ebddc5, #2e2b25)` (voir `_TYPOGRAPHY_STYLE`) -- marks
    # Altair "libres" ici aussi, un ton par thème plutôt que `light-dark()`
    # (CSS uniquement).
    band_color = "#f9f4ed" if dark else "#201e1d"
    # `grid_color` (2026-08-26, retour utilisateur en direct, même cause et
    # même correctif que `_compare_dual_axis_barplot` ci-dessus : invisible en
    # clair avec la couleur par défaut de `theme="streamlit"`, puis signalé
    # trop clair/contrasté en sombre avec le token `borderColor` -- assombri
    # à mi-chemin vers le fond).
    grid_color = "#34302b" if dark else "#dcd3c4"
    # `panel_bg` (2026-08-26, voir `_PANEL_BG_LIGHT`/`_PANEL_BG_DARK`) : fond
    # explicite du graphique, pour qu'il se fonde dans la carte `_panel()`
    # qui l'entoure au lieu du fond de PAGE par défaut de `theme="streamlit"`.
    panel_bg = _PANEL_BG_DARK if dark else _PANEL_BG_LIGHT
    # Le séparateur de barre "background-coloured" (`stroke_color`, ancienne
    # spec §8.3) a été RETIRÉ (2026-08-26, retour utilisateur en direct :
    # "it look like you added a black contour on the bar... Remove these") --
    # `st.context.theme.type` reste parfois bloqué sur son ancienne valeur
    # tant qu'aucune VRAIE interaction widget n'a eu lieu (piège déjà
    # documenté ailleurs dans ce fichier, T51 addendum 2) : un rerun avec un
    # theme.type resté "dark" alors que l'app est visuellement en clair
    # donnait un contour SOMBRE sur un fond clair -- lu à tort comme un
    # contour noir permanent plutôt qu'un artefact de thème. Aucune barre
    # n'a besoin d'un contour pour rester lisible (la couleur de remplissage
    # suffit, comme le barplot 1 juste au-dessus, qui n'en a jamais eu).
    # `text_color` : même formule que `band_color` ci-dessus (valeurs
    # identiques), variable séparée pour ne pas mélanger deux usages
    # sémantiquement différents (bande de fond vs texte neutre).
    text_color = "#f9f4ed" if dark else "#201e1d"

    # Noms de composés : PLUS un `mark_text` custom sur un axe Y natif rendu
    # invisible (`labelOpacity=0`, ancienne technique) -- root cause du
    # dépassement de largeur persistant (2026-08-27, 4e retour utilisateur :
    # voir `_COMPARE_CATEGORY_COMPOUND_WIDTH`) : cet axe natif, même
    # invisible, réservait une marge gauche dont la taille (dépendante du
    # contenu, ex. "Caryophyllene") s'ajoutait EN PLUS de toute largeur
    # déclarée. Les noms de composés vivent maintenant dans leur PROPRE
    # colonne `hconcat` (`_compare_compound_names_column`, même mécanisme
    # que les 2 colonnes du gutter), donc CE barplot n'a plus AUCUN axe Y
    # natif : `axis=None` pur, aucune marge implicite.
    y_enc = alt.Y("Field:N", scale=alt.Scale(domain=field_order), title=None, axis=None)
    y_offset_enc = alt.YOffset("Hop:N", scale=alt.Scale(domain=hop_names))
    # `legend=None` (2026-08-27, 5e retour utilisateur explicite : "you can
    # remove the legend from the 2nd barplot since it's the same legend
    # than the 2 other plots from this tool") -- la légende "Hop" est déjà
    # affichée sur le radar ET sur le barplot 1 ("Principal info") juste
    # au-dessus sur la même page, redondante ici. Retirer la légende de CE
    # SEUL barplot élimine aussi la marge droite que Vega-Lite lui
    # réservait EN PLUS de la largeur déclarée du `hconcat` (`_COMPARE_
    # DETAIL_BAR_WIDTH`) -- vérifié en direct (`svg.getAttribute("width")`)
    # que cette marge de légende, PAS un excès de largeur déclarée, était la
    # cause du dépassement de largeur qui persistait malgré `_COMPARE_
    # DETAIL_BAR_WIDTH` (700 déclaré, 800 rendu avec la légende ; 700 rendu
    # sans elle, exactement comme le barplot 1).
    color_enc = alt.Color("Hop:N", scale=alt.Scale(domain=hop_names, range=list(colors.values())),
                          legend=None)
    tooltip = ["Hop:N", "Field:N",
              alt.Tooltip("Value:Q", format=".2f", title=value_tooltip_title or "Value")]
    if raw_value_title and any("RawValue" in r for r in rows):
        # 4 chiffres significatifs, zéros de fin tronqués ("~g") : les
        # valeurs brutes vont de ~0.0004 (thiols, µg/kg) à ~40 (myrcène, %
        # d'huile) -- un format fixe (".2f") écraserait les petites à "0.00".
        tooltip.append(alt.Tooltip("RawValue:Q", format=".4~g", title=raw_value_title))
    if any(f in descriptors for f in field_order):
        tooltip.append(alt.Tooltip("Descriptors:N", title="Smells like"))
        rows = [dict(r, Descriptors=descriptors.get(r["Field"], "—")) for r in rows]
    if any(f in process_notes for f in field_order):
        tooltip.append(alt.Tooltip("Process:N", title="Process"))
        rows = [dict(r, Process=process_notes.get(r["Field"], "—")) for r in rows]

    primary_rows = [r for r in rows if r["Field"] in primary_fields]
    secondary_rows = [r for r in rows if r["Field"] in secondary_fields]

    # T-D09c/log (2026-08-24, retour utilisateur en direct : "I want barplot
    # not scatterplot... just apply a log scale on both axis") -- 4e passe.
    # Root cause enfin isolée en la reproduisant DANS UNE PAGE HTML minimale
    # (Vega-Embed seul, hors Streamlit, spec Vega-Lite écrite à la main) :
    # `mark_bar` calcule sa ligne de base en fixant implicitement `x2` à la
    # valeur DE DONNÉE 0 (pas au minimum du domaine de l'échelle) -- passée
    # à travers une échelle log, `log(0)` vaut `-Infinity`, donc la largeur
    # de la barre devient invalide et RIEN ne se dessine, quel que soit le
    # `scale.domain` fourni par ailleurs (déjà correct, vérifié directement
    # via `view.scale('x').domain()` dans la page de test -- le problème est
    # dans le calcul de `x2`, pas dans le domaine de l'échelle). Fixé en
    # fournissant `x2` EXPLICITEMENT comme une valeur constante (`X2Datum`,
    # PAS un champ de données) égale au minimum du domaine choisi -- chaque
    # barre part alors de CE minimum plutôt que de 0, un calcul valide sur
    # une échelle log. Confirmé en direct sur la page de test minimale avant
    # d'appliquer ici. Minimum du domaine pris 10% EN DESSOUS de la plus
    # petite valeur réelle (`* 0.9`) plutôt qu'égal à elle : une barre dont
    # la valeur est EXACTEMENT le minimum du domaine aurait une largeur
    # nulle (x == x2), invisible -- la marge de 10% garantit un filet visible
    # même pour le plus petit composé.
    # `db_values` (2026-08-26, retour utilisateur explicite en direct : "keep
    # the thiol axis to start at 0 even with the normalisations, for some
    # reason you decided to start the axis at the minimal value") -- le
    # domaine calculé UNIQUEMENT sur `values` (les houblons SÉLECTIONNÉS)
    # rendait le bas de l'axe dépendant de la sélection courante : avec 1-2
    # houblons choisis dont les thiols sont proches l'un de l'autre (ex.
    # Columbus 0.7 µg/kg), le domaine se réduisait à une fenêtre minuscule
    # autour de CES valeurs précises -- visuellement "l'axe démarre sur la
    # valeur choisie", pas sur une référence stable. `db_values` (toutes les
    # valeurs connues de CE composé sur TOUTE la base, même source que
    # `_compare_field_db_values`/Min-max) élargit le domaine à la vraie plage
    # existante -- le bas de l'axe reste ancré près du minimum RÉEL de la
    # base (le plus proche de 0 qu'un log puisse représenter, `log(0)` restant
    # indéfini), stable quelle que soit la sélection, au lieu de l'arbitraire
    # minimum LOCAL des houblons actuellement affichés.
    def _log_scale_and_baseline(values: list[float],
                                db_values: list[float] | None = None) -> tuple[alt.Scale, float]:
        reference = list(values) + list(db_values or [])
        domain_min = min(reference) * 0.9
        return alt.Scale(type="log", domain=[domain_min, max(reference)]), domain_min

    # `x_domain` (Min-max/Quantile, voir docstring) fige le domaine plutôt
    # que de laisser Vega-Lite l'auto-zoomer sur les seuls houblons
    # sélectionnés -- sans quoi "0 = minimum de la base" au titre de l'axe
    # deviendrait faux dès que la sélection ne couvre pas tout l'intervalle.
    linear_scale = (alt.Scale(type="linear", domain=list(x_domain)) if x_domain
                    else alt.Scale(type="linear"))
    if log_scale and primary_rows:
        x_scale_primary, x2_primary = _log_scale_and_baseline(
            [r["Value"] for r in primary_rows], primary_db_values)
    else:
        x_scale_primary, x2_primary = linear_scale, None
    if log_scale and secondary_rows:
        x_scale_secondary, x2_secondary = _log_scale_and_baseline(
            [r["Value"] for r in secondary_rows], secondary_db_values)
    else:
        x_scale_secondary, x2_secondary = linear_scale, None

    layers = [
        alt.Chart(alt.Data(values=[{"Field": f} for i, f in enumerate(field_order) if i % 2 == 1]))
        .mark_rect(opacity=0.06, color=band_color)
        .encode(y=y_enc, x=alt.value(0), x2=alt.value(_COMPARE_DETAIL_BAR_WIDTH)),
    ]
    resolved_fields = [f for f in field_order if f in descriptors or f in process_notes]
    if resolved_fields:
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
            .encode(y=y_enc, x=alt.value(0), x2=alt.value(_COMPARE_DETAIL_BAR_WIDTH),
                   tooltip=rect_tooltip))
    if primary_rows:
        primary_encoding = dict(
            y=y_enc, yOffset=y_offset_enc, color=color_enc, tooltip=tooltip,
            # Axe primaire explicitement en haut (2026-08-24, retour
            # utilisateur en direct : Vega-Lite plaçait par défaut l'axe
            # secondaire -- thiols, un seul composé tout en bas de la
            # grille -- en haut, sans rapport visuel avec sa propre barre) :
            # orienté pour que chaque axe reste proche de ce qu'il annote.
            x=alt.X("Value:Q", title=primary_title,
                   axis=alt.Axis(orient="top", gridColor=grid_color),
                   scale=x_scale_primary))
        if x2_primary is not None:
            primary_encoding["x2"] = alt.X2Datum(x2_primary)
        layers.append(
            alt.Chart(alt.Data(values=primary_rows))
            .mark_bar()
            .encode(**primary_encoding))
    if secondary_rows:
        secondary_encoding = dict(
            y=y_enc, yOffset=y_offset_enc, color=color_enc, tooltip=tooltip,
            x=alt.X("Value:Q", title=secondary_title,
                   axis=alt.Axis(orient="bottom", gridColor=grid_color),
                   scale=x_scale_secondary))
        if x2_secondary is not None:
            secondary_encoding["x2"] = alt.X2Datum(x2_secondary)
        layers.append(
            alt.Chart(alt.Data(values=secondary_rows))
            .mark_bar()
            .encode(**secondary_encoding))
    if len(layers) <= 1:
        return None
    chart = alt.layer(*layers).resolve_scale(x="independent")
    gutter = _compare_category_gutter(field_order, height, grid_color, text_color)
    compound_names = _compare_compound_names_column(field_order, height, grid_color, text_color)
    if gutter is not None:
        # `background` est une propriété TOPLEVEL-ONLY pour Altair (erreur
        # explicite si posée sur un sous-spec d'un `hconcat`, vue en direct
        # en écrivant ce ticket) -- posée UNE SEULE FOIS sur le `hconcat`
        # final, pas sur `detail_chart` ni les 3 colonnes de gauche
        # séparément. `_COMPARE_DETAIL_BAR_WIDTH` (pas `_COMPARE_CHART_
        # WIDTH`) pour que la largeur TOTALE du `hconcat` (gutter + noms +
        # barres) reste égale à `_COMPARE_CHART_WIDTH`, comme le barplot 1
        # ("Principal info", demande utilisateur explicite : "keep the
        # same width as barplot 1").
        class_chart, subclass_chart = gutter
        detail_chart = chart.properties(width=_COMPARE_DETAIL_BAR_WIDTH, height=height)
        # `resolve_scale(color="independent")` -- BUG réel trouvé sur
        # signalement direct de l'utilisateur ("you changed the initial
        # color palette for the bars... removed labels, e.g. Thiols") :
        # sans lui, `hconcat` PARTAGE par défaut le canal `color` entre TOUS
        # ses sous-specs -- `subclass_chart` l'encode sur "Class" (4
        # catégories chimiques) et `detail_chart` sur "Hop" (jusqu'à 5
        # houblons), donc Vega-Lite fusionnait les deux domaines/palettes en
        # UNE seule échelle : les barres se coloraient avec la palette de
        # catégorie chimique au lieu de la palette Hop (`colors`), et au
        # moins une valeur du domaine fusionné n'avait plus de couleur
        # valide dans le range fusionné -- rendant son mark invisible
        # (symptôme observé : la ligne "Thiols" disparue). `color=
        # "independent"` force chaque sous-spec à garder SA PROPRE échelle
        # de couleur, comme voulu depuis le départ. `compound_names` n'a
        # aucun canal "color" encodé (texte neutre statique) donc ne
        # participe à aucun risque de fusion/duplication ici.
        return alt.hconcat(class_chart, subclass_chart, compound_names, detail_chart,
                           spacing=2, background=panel_bg
                           ).resolve_scale(color="independent")
    return chart.properties(width=_COMPARE_CHART_WIDTH, height=height, background=panel_bg)


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
    # `panel_bg` (2026-08-26, voir `_PANEL_BG_LIGHT`/`_PANEL_BG_DARK`) : fond
    # explicite du graphique, pour qu'il se fonde dans la carte `_panel()`
    # qui l'entoure au lieu du fond de PAGE par défaut de `theme="streamlit"`.
    panel_bg = _PANEL_BG_DARK if dark else _PANEL_BG_LIGHT
    # "axis labels at body colour" -- tokens `textColor` réels du thème.
    text_color = "#f9f4ed" if dark else "#201e1d"
    # 8.3 (2026-08-24, retour Claude Design) : "axis spokes at border
    # colour" -- alignés sur les tokens `borderColor` réels du thème
    # (config.toml), pas une teinte de contraste choisie à part.
    grid_color = "#474238" if dark else "#dcd3c4"

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
    # T-D09b (2026-08-24, spec Claude Design §8.3) : légende en bas
    # (horizontale, 2 colonnes) -- l'ancienne légende à droite volait de la
    # largeur au polygone, faisant "rétrécir" le radar dès qu'un nom de
    # houblon long (désambiguïsation régionale, T60) apparaissait dans la
    # sélection. `labelExpr` réécrit UNIQUEMENT le texte affiché (voir
    # `_legend_abbr_expr`) -- le nom complet reste dans le tooltip des points
    # (`Hop:N`, inchangé plus bas).
    color_enc = alt.Color(
        "Hop:N", scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())),
        legend=alt.Legend(title="Hop", orient="bottom", direction="horizontal", columns=2,
                          labelLimit=160, labelExpr=_legend_abbr_expr(list(colors.keys())),
                          # Le canal `color` est partagé avec `polygon_fill`
                          # (18% d'opacité, voir plus bas) -- sans ceci, Vega-
                          # Lite hérite cette opacité pour la PASTILLE de
                          # légende elle-même, la rendant illisible (vérifié
                          # en direct : pastilles quasi blanches). Forcée à
                          # pleine opacité, indépendamment du mark source.
                          symbolOpacity=1))

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
    # Traits affinés (2026-08-24, retour utilisateur explicite, "reducing
    # the size of the line could help reduce the bulkyness of the plot") --
    # 5/2 -> 3.5/1.5, même ratio hover/repos conservé.
    line_width = alt.condition(hover, alt.value(3.5), alt.value(1.5))
    point_opacity = alt.condition(hover, alt.value(1.0), alt.value(0.55))
    # (110, 50) -> (55, 25) (2026-08-24, même retour que `_aroma_wheel` : "the
    # points/scatter... is a bit bulky" -- taille = aire en px^2, ~moitié pour
    # un rayon perceptiblement plus fin, cohérent avec la réduction de trait).
    point_size = alt.condition(hover, alt.value(55), alt.value(25))

    grid = (
        alt.Chart(alt.Data(values=spokes))
        .mark_rule(strokeWidth=1, stroke=grid_color)
        .encode(x=x_enc, y=y_enc, x2="x2:Q", y2="y2:Q")
    )
    # T-D09/8.3 (2026-08-24, spec Claude Design, "Overlays: categorical
    # scale, 18% fills") -- posée avant la ligne (donc dessous dans
    # l'empilement SVG), pas de survol dédié dessus (le hover reste porté
    # par `points`, voir plus bas). `strokeDash` par série suggéré par la
    # même phrase de la spec, essayé puis retiré (voir le commentaire
    # au-dessus de `_COMPARE_PALETTE`) -- couleur seule (palette élargie)
    # suffit.
    #
    # `mark_area` CASSÉ ici, corrigé 2026-08-24 (retour utilisateur en
    # direct, capture d'écran à l'appui, même défaut que `_aroma_wheel` --
    # voir sa docstring pour le détail complet) : sur des x/y libres,
    # `mark_area` remplit vers le bord du graphique le plus proche plutôt
    # que de refermer chaque polygone -- 5 pointes/triangles aberrants
    # mélangés au lieu de 5 étoiles fermées. `mark_line(interpolate=
    # "linear-closed", filled=True)` est le mécanisme Vega-Lite correct pour
    # un polygone fermé par série sur x/y arbitraires -- `filled=True` sur
    # un mark `line` bascule le sens du canal `color` de "stroke" (défaut
    # pour ce type de mark) vers "fill", donc `color=color_enc` ici suffit à
    # remplir chaque polygone de sa propre teinte, PAS besoin d'un canal
    # `fill=` séparé.
    #
    # Un canal `fill_enc` (`alt.Fill`, DISTINCT de `color_enc`) avait été
    # introduit ici, `legend=None` pour éviter une 2e légende -- CASSÉ,
    # signalé par l'utilisateur ("we lost the legend in the spider plot") :
    # `fill`/`color` réfèrent le MÊME champ ("Hop:N") avec un domaine/une
    # plage IDENTIQUES -- Vega-Lite fusionne leurs légendes en une seule
    # (scale partagée détectée), et le conflit "disable" (`fill_enc` en
    # demande une désactivée, `color_enc` une active) se résolvait en
    # DÉSACTIVANT la légende fusionnée entière (`WARN Conflicting legend
    # property "disable" (true and false)` en console, jamais remarqué avant
    # que l'utilisateur ne signale la légende manquante). Revenu à `color=
    # color_enc` PARTOUT (même canal que `polygon_line`/`points`, un seul
    # champ, une seule légende, aucun conflit possible) -- `symbolOpacity=1`
    # sur `color_enc` (voir plus haut) reste nécessaire : SANS lui, la
    # pastille de légende hériterait le `fillOpacity=0.18` de CETTE couche.
    polygon_fill = (
        alt.Chart(alt.Data(values=poly_rows))
        .mark_line(interpolate="linear-closed", filled=True, fillOpacity=0.18,
                  strokeOpacity=0, order=True)
        .encode(x=x_enc, y=y_enc, order="Order:Q", color=color_enc, detail="Hop:N")
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
        .mark_text(fontSize=12, color=text_color)
        .encode(x=x_enc, y=y_enc, text="Descriptor:N",
               tooltip=["Descriptor:N", "Definition:N"])
    )
    # T-D09b : `width`/`height` explicites (carré, radius constant quel que
    # soit le nom sélectionné, `_COMPARE_RADAR_SIZE` -- voir son commentaire,
    # revu 2026-08-24 pour tenir sur mobile) + `autosize` fit-x/contains=
    # padding -- la marge nécessaire à la légende du bas est prise sur le
    # CONTENEUR, pas sur la zone de tracé (sinon le polygone rétrécirait à
    # nouveau, cette fois à cause de la hauteur de légende plutôt que de sa
    # largeur).
    return (
        (grid + polygon_fill + polygon_line + points + text)
        .properties(width=_COMPARE_RADAR_SIZE, height=_COMPARE_RADAR_SIZE,
                   background=panel_bg,
                   autosize=alt.AutoSizeParams(type="fit-x", contains="padding"))
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
    # Couleur/légende par ORDRE DE SÉLECTION (2026-08-26, retour utilisateur
    # explicite : "I would like the Hop order in the legend to be kept, and
    # not use the alphabetical order to assign colors") -- REVIREMENT sur la
    # décision T-D09/§8.2 ("stable per-hop colour", 2026-08-24) qui triait
    # alphabétiquement (`sorted(selected)`) précisément pour qu'un houblon
    # garde la même couleur qu'on le sélectionne en premier ou en second.
    # `selected` (renvoyé par `st.multiselect` dans l'ORDRE OÙ l'utilisateur a
    # ajouté chaque houblon, jamais retrié par le widget lui-même) est
    # désormais utilisé tel quel : le premier houblon choisi est toujours la
    # première couleur/entrée de légende, quel que soit son nom -- au prix de
    # la stabilité précédente (retirer puis rajouter un houblon dans un ordre
    # différent change maintenant sa couleur), assumé par ce revirement.
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
            # 2026-08-24, retour utilisateur en direct : caption dupliquée --
            # `_aroma_wheel_source_caption` inclut déjà "Hover a label for its
            # definition." dans son propre texte (préfixe partagé par les 2
            # variantes de source), cette 2e ligne répétait donc la même
            # phrase deux fois de suite. Retirée, seule la caption source
            # reste (elle porte déjà l'information complète).
            st.caption(_aroma_wheel_source_caption(source))
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
        # `theme=None` (2026-08-26, retour utilisateur en direct : la bande
        # alternée -- ajoutée le jour même, voir `_compare_dual_axis_
        # barplot` -- ne "collait" pas aux groupes de barres, quel que soit
        # le nombre de houblons comparés). Root cause isolée en reproduisant
        # HORS Streamlit (même technique que le bug du barplot log-scale,
        # voir plus haut dans ce fichier -- spec Vega-Lite exportée via
        # `chart.to_dict()`, servie par `vegaEmbed()` seul dans une page de
        # test, mesures `getBoundingClientRect()` sur les marks réels) :
        # avec CE spec exact, `theme="streamlit"` (T-D01/T-D09, dernier
        # `theme=None` retiré du projet, voir CLAUDE.md) décale
        # systématiquement le sous-groupe de barres (`xOffset`) vers la
        # droite de sa bande catégorielle -- ~19px de marge à gauche contre
        # ~8px à droite, mesuré identiquement sur les 4 catégories, peu
        # importe `paddingOuter` -- alors que `theme=None` (ou n'importe
        # quel Vega-Embed hors Streamlit) centre parfaitement le même spec.
        # PAS le même bug que T-D01 (qui concernait des COULEURS écrasées
        # par le thème global) -- ici c'est la GÉOMÉTRIE du sous-scale
        # `xOffset` qui est faussée par le thème Streamlit, jamais documenté
        # avant faute d'avoir eu un repère visuel (la bande alternée) pour
        # le remarquer. Seul CE graphique (grouped bars + xOffset) a besoin
        # de `theme=None` -- tout le reste (couleurs, grille, fond) est déjà
        # explicite dans cette fonction, rien à perdre en désactivant le
        # thème Streamlit ici.
        st.altair_chart(principal_chart, width="content", theme=None)
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
        abs_col, norm_col = st.columns(2)
        with abs_col:
            show_absolute = st.toggle(
                "Show absolute amount (ml/100g) instead of % of oil",
                value=True, key="compare_absolute_oil")
        # Menu déroulant "Normalization" (2026-08-24, remplace le toggle log
        # binaire précédent -- demande utilisateur explicite, le toggle ne
        # convainquait pas : "Rather than a log scale toggle I would like
        # you to implement something more complex... a dropdown menu where
        # you choose a normalization... for each molecule you look at the
        # known value across all hops in the database and apply minmax or
        # quantile normalisation"). "None" reste le défaut -- la lecture la
        # plus directe (unité réelle, comportement historique) prime tant
        # que rien n'est demandé. "Log" reprend la représentation EXISTANTE
        # à l'identique (voir `_compare_detail_barplot`, jamais retouchée
        # ici). "Min-max"/"Quantile" : transformation calculée juste en bas,
        # sur TOUTE la base (`comp`, pas `selected` seul) -- voir
        # `_compare_field_db_values`/`_normalize_minmax`/`_normalize_
        # quantile`.
        with norm_col:
            # Une ligne par option (2026-08-24, retour utilisateur explicite :
            # "format the 'Normalization' infobox to use \n to separate the
            # normalisations descriptions") -- même mécanisme que les autres
            # captions multi-lignes de cette session (roue d'arôme, infobox
            # "Smells like"/"Process") : retour à la ligne MARKDOWN ("  \n"),
            # un simple "\n" est ignoré par le rendu markdown du tooltip
            # `help=`. Un paragraphe unique mélangeant les 4 options obligeait
            # à relire toute la phrase pour retrouver celle qui intéressait.
            help_lines = [
                "How each compound's bar is scaled:",
                "\"None\": raw amount/% of oil, the most direct reading.",
                "\"Log\": stretches the low end of the scale so small "
                "compounds (ketones, isobutyrate...) aren't flattened by a "
                "much larger one (myrcene, thiols...) — zero-value bars "
                "can't be shown on a log scale and are dropped when this "
                "is on.",
                "\"Min-max\": where this hop's value sits between the "
                "lowest and highest value known for that compound across "
                "the whole database — makes small and large compounds "
                "directly comparable, at the cost of hiding the actual "
                "amount (still shown on hover).",
                "\"Quantile\": same idea as min-max, but this hop's "
                "percentile rank among all known values for that compound "
                "instead of its raw position between the extremes — less "
                "swayed by a single outlier hop.",
            ]
            normalization = st.selectbox(
                "Normalization", ["None", "Min-max", "Quantile", "Log"],
                index=0, key="compare_detail_normalization",
                help="  \n".join(help_lines))
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
    log_scale = normalization == "Log"
    x_domain = value_tooltip_title = raw_value_title = None
    if normalization in ("Min-max", "Quantile"):
        # Normalise PAR COMPOSÉ, sur les valeurs connues de TOUTE la base
        # (`comp`, jamais seulement `selected`) -- demande utilisateur
        # explicite ("look at the known value across all hops in the
        # database"). `RawValue` gardé à côté de `Value` (normalisé) pour le
        # tooltip -- voir `_compare_detail_barplot`, `raw_value_title`.
        normalize = _normalize_minmax if normalization == "Min-max" else _normalize_quantile
        for field in present_oil_compounds + thiols_fields:
            db_values = _compare_field_db_values(comp, field, show_absolute)
            if not db_values:
                continue
            for row in detail_rows:
                if row["Field"] == field:
                    row["RawValue"] = row["Value"]
                    row["Value"] = normalize(row["RawValue"], db_values)
        # Domaine FIGÉ à [0, 1] (pas l'auto-zoom Vega-Lite habituel) : sinon
        # "0 = minimum de la base" au titre de l'axe deviendrait faux dès que
        # la sélection courante ne couvre pas tout l'intervalle réel.
        x_domain = (0.0, 1.0)
        value_tooltip_title = ("Min-max position" if normalization == "Min-max"
                               else "Quantile rank")
        raw_value_title = "Raw value (unit varies by compound)"
    axis_label = {
        "None": "Amount (ml/100g)" if show_absolute else "Percent of oil (%)",
        "Log": "Amount (ml/100g)" if show_absolute else "Percent of oil (%)",
        "Min-max": "Min-max position (0 = lowest in DB, 1 = highest)",
        "Quantile": "Quantile rank (0 = lowest in DB, 1 = highest)",
    }[normalization]
    primary_title = axis_label
    secondary_title = ("Thiols (µg/kg)" if normalization in ("None", "Log") else axis_label)
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
    # `primary_db_values`/`secondary_db_values` (2026-08-26, retour
    # utilisateur explicite -- voir `_log_scale_and_baseline`) : SEULEMENT en
    # mode Log, sinon calcul inutile (Min-max/Quantile ont déjà `db_values`
    # par composé plus haut ; None/Log-désactivé n'en ont pas besoin).
    primary_db_values = secondary_db_values = None
    if log_scale:
        primary_db_values = [v for f in present_oil_compounds
                             for v in _compare_field_db_values(comp, f, show_absolute)]
        secondary_db_values = [v for f in thiols_fields
                               for v in _compare_field_db_values(comp, f, show_absolute)]
    # T-D09c (2026-08-24, spec Claude Design §8.3) : rotation horizontale,
    # voir `_compare_detail_barplot` -- réservée à CE barplot (le "Principal
    # info" ci-dessus, 4 champs seulement, garde la disposition verticale).
    detail_chart = _compare_detail_barplot(
        detail_rows, present_oil_compounds, primary_title,
        thiols_fields, secondary_title, colors, descriptors=descriptors,
        process_notes=process_notes, log_scale=log_scale, x_domain=x_domain,
        value_tooltip_title=value_tooltip_title, raw_value_title=raw_value_title,
        primary_db_values=primary_db_values, secondary_db_values=secondary_db_values)
    if detail_chart is not None:
        # `theme=None` (2026-08-26, même correctif et même root cause que
        # le barplot "Principal info" ci-dessus -- voir son commentaire
        # complet) : ce barplot groupe aussi ses barres par houblon via un
        # canal offset (`yOffset` ici, pas `xOffset`, mais le même
        # mécanisme Vega-Lite sous-jacent), et souffrait du même décalage
        # asymétrique sous `theme="streamlit"`. Vérifié en direct après ce
        # changement : barres centrées dans leur bande catégorielle, quel
        # que soit le nombre de houblons comparés.
        st.altair_chart(detail_chart, width="content", theme=None)
        if descriptors or process_notes:
            # 2 lignes, une par niveau d'info (2026-08-24, retour utilisateur
            # explicite : "use 2 lines for the two information level 'Smells
            # like' and 'Process'") -- même mécanisme que `_aroma_wheel_
            # source_caption` (retour à la ligne MARKDOWN "  \n", un simple
            # "\n" est ignoré par le rendu markdown de `st.caption`). Chaque
            # ligne conditionnée à sa propre présence (`descriptors`/
            # `process_notes` peuvent être vides indépendamment selon les
            # composés affichés) -- jamais une ligne vide affichée pour rien.
            caption_lines = []
            if descriptors:
                caption_lines.append(
                    "Hover a bar, or the space near/below a compound's label, "
                    "for its Flavornet odor descriptors (\"Smells like\") — "
                    "not every compound has an entry.")
            if process_notes:
                caption_lines.append(
                    "\"Process\" notes are a qualitative prior (Scott Janish, "
                    "The New IPA) on whether a compound survives boiling/"
                    "fermentation — never a measured transfer rate, never "
                    "used in any score.")
            with _panel():
                st.caption(":material/info: " + "  \n".join(caption_lines))
        if process_notes:
            _process_survival_legend()
    else:
        with _panel():
            st.write("No detailed composition data for the selected hops.")
    if missing_oil:
        with _panel():
            st.caption(":material/info: Total oil unknown for: " + ", ".join(sorted(set(missing_oil)))
                      + " — their % of oil composition can't be converted to an absolute amount.")


# --------------------------------------------------------------------------- #
# Mode GUI "Beer styles" (T82, épique A)
# --------------------------------------------------------------------------- #
def _category_sort_key(item: tuple[str, str]) -> tuple:
    """Clé de tri catégorie BJCP : NUMÉRIQUE sur `category_id` ("2" avant
    "10", pas l'inverse -- demande explicite du ticket). Cas non prévu par
    le ticket, trouvé en construisant cette page : 4 styles provisoires
    (Argentine/Brazilian/Italian/New Zealand Styles) partagent tous le
    MÊME `category_id` littéral `"X"` (pas numérique) -- groupés APRÈS
    toutes les catégories numériques, triés entre eux par nom (seul moyen
    de les distinguer, `category_id` seul ne suffit pas ici)."""
    category_id, category = item
    try:
        return (0, int(category_id), "")
    except (TypeError, ValueError):
        return (1, 0, category or "")


# Rampe de couleur SRM (paille -> ambre -> brun -> quasi-noir) : une mesure
# de couleur réelle, légitimement INDÉPENDANTE de `_COMPARE_PALETTE`/tokens
# Organic (qui codent une identité houblon/catégorie chimique, pas une
# grandeur physique -- ticket T82 explicite). Bornes de la base réelle :
# srm_max plafonne à 40 sur les 110 styles 2021 ; dernier point d'ancrage
# posé à 50 pour garder une marge sans jamais clamper une vraie donnée.
_SRM_COLOR_STOPS = [
    (0.0, "#f3e5ab"), (8.0, "#f0a500"), (20.0, "#b85c00"),
    (35.0, "#5c3317"), (50.0, "#140a05"),
]


def _srm_color(srm: float | None) -> str:
    """Couleur hex approximative pour une valeur SRM -- interpolation
    linéaire RGB entre les points d'ancrage de `_SRM_COLOR_STOPS`. `None`
    (jamais recalculé sur `NULL`, l'appelant ne passe ici que si `srm_min`/
    `srm_max` sont tous les deux non-NULL) -> gris neutre, ne devrait pas
    s'afficher en pratique."""
    if srm is None:
        return "#a19786"
    srm = max(_SRM_COLOR_STOPS[0][0], min(srm, _SRM_COLOR_STOPS[-1][0]))
    for (lo_v, lo_c), (hi_v, hi_c) in zip(_SRM_COLOR_STOPS, _SRM_COLOR_STOPS[1:]):
        if lo_v <= srm <= hi_v:
            t = (srm - lo_v) / (hi_v - lo_v) if hi_v > lo_v else 0.0
            lo_rgb = tuple(int(lo_c[i:i + 2], 16) for i in (1, 3, 5))
            hi_rgb = tuple(int(hi_c[i:i + 2], 16) for i in (1, 3, 5))
            rgb = tuple(round(lo_rgb[i] + (hi_rgb[i] - lo_rgb[i]) * t) for i in range(3))
            return "#{:02x}{:02x}{:02x}".format(*rgb)
    return _SRM_COLOR_STOPS[-1][1]  # au-delà du dernier point d'ancrage (clampé ci-dessus)


def _range_bar_html(vmin: float, vmax: float, domain: tuple[float, float],
                    min_text: str, max_text: str, color: str | None = None) -> str:
    """Barre `[vmin, vmax]` positionnée dans `domain` (borne fixe par
    critère -- voir `_VITAL_STAT_SPECS` -- PAS auto-zoomée sur ce seul
    style : une fourchette étroite au milieu d'un critère large doit se
    lire comme "modérée", pas comme "occupe toute la barre"). `color` :
    teinte sage neutre par défaut (`.hf-range-fill` en CSS), ou la couleur
    SRM réelle calculée par l'appelant pour ce seul critère (T82,
    `_srm_color`). Largeur plancher (`max(..., 1.0)`) : une fourchette nulle
    ou très étroite (ex. IBU 0-0) resterait invisible sinon.

    `min_text`/`max_text` (2026-08-27, retour utilisateur en direct : les
    bornes doivent aussi être écrites au-dessus de chaque extrémité de la
    portion colorée, pas seulement dans `st.metric` à gauche) -- déjà
    formatées par l'appelant (même `fmt` que la valeur `st.metric`, jamais
    reformatées ici séparément, pour ne jamais afficher deux précisions
    différentes pour la même valeur)."""
    dmin, dmax = domain
    span = dmax - dmin
    left = max(0.0, min(100.0, (vmin - dmin) / span * 100))
    right = max(0.0, min(100.0, (vmax - dmin) / span * 100))
    width = max(right - left, 1.0)
    style = f"left:{left:.2f}%; width:{width:.2f}%;"
    if color:
        style += f" background-color:{color};"
    else:
        style += " background-color: light-dark(#7f9455, #aebf92);"
    return (
        '<div class="hf-range-wrap">'
        f'<span class="hf-range-label hf-range-label-min" style="left:{left:.2f}%;">{min_text}</span>'
        f'<span class="hf-range-label hf-range-label-max" style="left:{right:.2f}%;">{max_text}</span>'
        f'<div class="hf-range-track"><div class="hf-range-fill" style="{style}"></div></div>'
        '</div>')


# (label, colonne min, colonne max, formateur, domaine fixe d'affichage)
# Domaines choisis pour couvrir confortablement les 110 styles 2021 réels
# (abv_max jusqu'à 14, ibu_max jusqu'à 100, og_max jusqu'à 1.13, fg_max
# jusqu'à 1.04, srm_max jusqu'à 40 -- voir BACKLOG.md T81/T82) avec une
# marge, sans jamais clamper une vraie donnée à l'affichage.
_VITAL_STAT_SPECS = [
    ("ABV", "abv_min", "abv_max", lambda v: f"{v:.1f}%", (0.0, 15.0)),
    ("IBU", "ibu_min", "ibu_max", lambda v: f"{v:.0f}", (0.0, 105.0)),
    ("OG", "og_min", "og_max", lambda v: f"{v:.3f}", (1.000, 1.140)),
    ("FG", "fg_min", "fg_max", lambda v: f"{v:.3f}", (0.995, 1.045)),
    ("SRM", "srm_min", "srm_max", lambda v: f"{v:.1f}", (0.0, 42.0)),
]

# EBC = SRM x ce facteur -- formule déjà établie dans ce projet pour la
# conversion inverse (CLAUDE.md/BACKLOG.md T91, ingestion MMuM : "Farbe en
# EBC -> SRM : SRM = EBC / 1.97"), pas une valeur inventée pour ce ticket.
_EBC_PER_SRM = 1.97


def _sg_to_plato(sg: float) -> float:
    """Densité spécifique -> degrés Plato -- polynôme cubique standard ASBC
    (formule établie de l'industrie brassicole, pas une approximation
    improvisée pour ce ticket ; vérifié : SG 1.050 -> ~12.4°P, cohérent avec
    les tables de référence usuelles). Appliqué à OG ET FG (2026-08-27,
    demande utilisateur explicite : "toggle density in optical density
    versus plato... Plato make sense to use in some cases") -- pour FG,
    c'est l'« extrait apparent » conventionnel de tout logiciel de brassage
    (BeerSmith, Brewer's Friend...), pas une seconde mesure : la présence
    d'alcool fausse la relation densité<->sucre réelle, mais c'est la
    convention établie partout, pas une invention de ce ticket."""
    return -616.868 + 1111.14 * sg - 630.272 * sg ** 2 + 135.997 * sg ** 3


def _style_observed_vs_official_chart(bins: list[dict], vmin: float, vmax: float,
                                      domain: tuple[float, float], x_title: str):
    """Histogramme des recettes RÉELLEMENT brassées (`style_recipe_stats`,
    beer-analytics.com, T85) + bande translucide pour la fourchette
    OFFICIELLE BJCP `[vmin, vmax]` (T81), sur le MÊME domaine fixe que
    `_range_bar_html` (T105 : "sur le même axe... jamais moyennées, jamais
    fusionnées" -- deux encodages visuels distincts, jamais recalculées en
    un seul chiffre). Couleurs : sauge pour l'histogramme observé (même
    langage que le remplissage par défaut de `_range_bar_html`, "donnée
    mesurée"), terracotta translucide pour la bande BJCP (référence
    prescriptive, distincte). L'histogramme est PRÉ-BINNÉ ET ÉCRÊTÉ côté
    beer-analytics (outliers déjà retirés) -- jamais un percentile
    dérivable, rappelé en `st.caption` par l'appelant, pas ici (le chart
    reste réutilisable sans dépendre d'un texte GUI en anglais précis)."""
    dark = st.context.theme.type == "dark"
    sage = "#aebf92" if dark else "#7f9455"
    terracotta = "#f6a06b" if dark else "#c67139"
    # `y2=alt.Y2Datum(0)` EXPLICITE -- piège Vega-Lite réel, vérifié en
    # direct (T105) : `mark_bar` avec `x`/`x2` (bins de largeur variable) ET
    # seulement `y` (sans `y2`) ne redescend PAS automatiquement à 0 comme un
    # bar chart classique `x:nominal, y:quantitative` -- chaque bin rendait
    # un petit carré flottant à la hauteur de sa valeur au lieu d'une vraie
    # barre. Même famille de piège que `x2=alt.X2Datum(domain_min)` déjà
    # documenté pour `_compare_dual_axis_barplot` (log scale), symétrique ici
    # sur l'axe Y avec une échelle linéaire.
    bars = alt.Chart(alt.Data(values=bins)).mark_bar(color=sage, opacity=0.85).encode(
        x=alt.X("bin_low:Q", scale=alt.Scale(domain=list(domain)), title=x_title),
        x2="bin_high:Q",
        y=alt.Y("count:Q", title="Recipes"),
        y2=alt.Y2Datum(0),
        tooltip=[alt.Tooltip("bin_low:Q", title="From", format=".3g"),
                alt.Tooltip("bin_high:Q", title="To", format=".3g"),
                alt.Tooltip("count:Q", title="Recipes")],
    )
    band = alt.Chart(alt.Data(values=[{"lo": vmin, "hi": vmax}])).mark_rect(
        color=terracotta, opacity=0.28,
    ).encode(x=alt.X("lo:Q", scale=alt.Scale(domain=list(domain))), x2="hi:Q")
    return (band + bars).properties(height=130)


def _vital_stat_row(row, use_ebc: bool, use_plato: bool, observed: dict[str, list[dict]] | None = None) -> None:
    """5 `st.metric` (ABV/IBU/OG/FG/SRM, ou EBC/Plato selon les toggles) +
    barre de range, UNE LIGNE PAR CRITÈRE (2026-08-27, retour utilisateur en
    direct : 5 colonnes côte à côte tronquaient les fourchettes, ex.
    "2.8%…" -- "explore the different elements into multiple lines").
    `st.columns([2, 3])` par ligne (label+valeur | barre) plutôt que 5
    `st.metric` pleine largeur empilés (aurait été disproportionné) --
    vérifié en direct que 2/5 de la largeur suffit à la plus longue
    fourchette réelle ("1.028–1.038").

    `use_ebc`/`use_plato` (2026-08-27, deux toggles SÉPARÉS -- demande
    utilisateur explicite : "separate the EBC/SRM et Plato/SG. Il peut
    arriver de vouloir utiliser EBC et Plato en meme temps", ex. EBC+SG ou
    SRM+Plato) : SRM->EBC (`_EBC_PER_SRM`) et SG->Plato (`_sg_to_plato`)
    indépendants l'un de l'autre -- les deux seuls critères qui diffèrent
    RÉELLEMENT entre systèmes (ABV/IBU sont identiques partout). La couleur
    de la barre SRM (`_srm_color`) reste calculée sur la VRAIE valeur SRM
    (source de vérité en base) quel que soit l'affichage choisi -- convertir
    n'est qu'un habillage d'unité, jamais une seconde mesure.

    Les 17/110 styles réels sans AUCUNE vital stat (héritent du style de
    base choisi par le brasseur -- vérifié : toujours les 5 NULL ensemble,
    jamais partiellement, voir BACKLOG.md T82) affichent "—" et UNE SEULE
    `st.caption` partagée sous la ligne, jamais une barre vide (qui
    laisserait croire à zéro)."""
    has_vitals = row["abv_min"] is not None
    for label, min_key, max_key, fmt, domain in _VITAL_STAT_SPECS:
        metric_key = label.lower()  # capturé AVANT toute mutation de `label` ci-dessous
        vmin, vmax = row[min_key], row[max_key]
        srm_mid = (vmin + vmax) / 2 if (label == "SRM" and vmin is not None
                                        and vmax is not None) else None
        # T105 : bins observés (style_recipe_stats) convertis dans la MÊME
        # unité que la fourchette BJCP affichée -- sinon les deux encodages
        # ne s'aligneraient plus sur le même axe une fois EBC/°Plato actif.
        bins = [dict(b) for b in (observed or {}).get(metric_key, [])]
        if label == "SRM" and use_ebc:
            label, fmt = "EBC", (lambda v: f"{v:.0f}")
            domain = (domain[0] * _EBC_PER_SRM, domain[1] * _EBC_PER_SRM)
            if vmin is not None:
                vmin, vmax = vmin * _EBC_PER_SRM, vmax * _EBC_PER_SRM
            for b in bins:
                b["bin_low"] *= _EBC_PER_SRM; b["bin_high"] *= _EBC_PER_SRM
        elif label in ("OG", "FG"):
            if use_plato:
                label, fmt = f"{label} (°P)", (lambda v: f"{v:.1f}")
                domain = (_sg_to_plato(domain[0]), _sg_to_plato(domain[1]))
                if vmin is not None:
                    vmin, vmax = _sg_to_plato(vmin), _sg_to_plato(vmax)
                for b in bins:
                    b["bin_low"] = _sg_to_plato(b["bin_low"])
                    b["bin_high"] = _sg_to_plato(b["bin_high"])
            else:
                label = f"{label} (SG)"
        label_col, bar_col = st.columns([2, 3], vertical_alignment="center")
        with label_col:
            st.metric(label, f"{fmt(vmin)}–{fmt(vmax)}" if vmin is not None else "—")
        with bar_col:
            if vmin is not None and vmax is not None:
                if bins:
                    st.altair_chart(_style_observed_vs_official_chart(
                        bins, vmin, vmax, domain, label), width="stretch")
                else:
                    st.html(_range_bar_html(vmin, vmax, domain, fmt(vmin), fmt(vmax),
                                            color=_srm_color(srm_mid) if srm_mid is not None else None))
    if not has_vitals:
        st.caption(
            "This style has no vital statistics of its own — it inherits them "
            "from the base style the brewer chose to build on (e.g. a fruit "
            "beer entered on top of an American Wheat Beer follows that base "
            "style's range).")


def _style_text_expander(label: str, text: str | None) -> None:
    """Un `st.expander` replié par bloc de texte descriptif -- rien si le
    champ est absent (styles X1/X2 notamment : `examples` totalement
    absent, `style_comparison` absent aussi -- jamais un expander vide)."""
    if not text:
        return
    with _panel_expander(label):
        st.write(text)


def _styles(con) -> None:
    """Mode GUI "Beer styles" (T82) : consulter un style BJCP 2021
    directement -- vital statistics officielles + texte descriptif complet
    (`beer_styles`, T81). Référence éditoriale, PAS une mesure de recettes
    réelles (voir l'épique B à venir, `style_recipe_stats`/beer-analytics).

    Navigation en cascade catégorie -> style (ticket explicite), catégorie
    triée numériquement sur `category_id` -- voir `_category_sort_key`."""
    # Deux toggles SÉPARÉS (2026-08-27, demande utilisateur explicite : "For
    # the units I would like you to separate the EBC/SRM et Plato/SG. Il
    # peut arriver de vouloir utiliser EBC et Plato en meme temps" -- un
    # brasseur peut légitimement vouloir EBC+SG ou SRM+Plato, pas seulement
    # les deux paires "assorties") -- PAS un seul toggle Metric/Imperial
    # bundlé (essayé d'abord, ticket a changé d'avis en cours de route).
    # ABV/IBU sont identiques dans les deux systèmes, donc pas concernés.
    # EBC et °Plato par défaut (demande explicite : "By default I would
    # like you to use EBC not SRM").
    color_cols = st.columns(2)
    with color_cols[0]:
        use_ebc = st.segmented_control(
            "Color", ["EBC", "SRM"], default="EBC", key="styles_color_units", required=True,
            help="EBC (European Brewery Convention) vs SRM (Standard Reference "
                 "Method, US-centric) — same measurement, different scale.") == "EBC"
    with color_cols[1]:
        use_plato = st.segmented_control(
            "Density", ["°Plato", "SG"], default="°Plato", key="styles_density_units",
            required=True,
            help="°Plato (used almost everywhere outside the US) vs specific "
                 "gravity (SG, US-centric) for OG/FG.") == "°Plato"

    categories = sorted(
        {(r["category_id"], r["category"]) for r in
         con.execute("SELECT DISTINCT category_id, category FROM beer_styles")},
        key=_category_sort_key)
    if not categories:
        st.write("No style in the database yet — run `hopmatch ingest-styles` first.")
        return

    category_id, category = st.selectbox(
        "Category", categories, format_func=lambda c: f"{c[0]} - {c[1]}", key="styles_category")

    style_rows = con.execute(
        "SELECT style_id, name FROM beer_styles WHERE category_id=? AND category=? "
        "ORDER BY style_id", (category_id, category)).fetchall()
    style_id, style_name = st.selectbox(
        "Style", [(r["style_id"], r["name"]) for r in style_rows],
        format_func=lambda s: f"{s[0]} - {s[1]}", key="styles_style")

    row = con.execute(
        "SELECT * FROM beer_styles WHERE style_id=? AND category_id=? AND category=?",
        (style_id, category_id, category)).fetchone()
    if row is None:
        st.write("Style not found.")
        return

    with _panel():
        st.subheader(f"{row['style_id']} - {row['name']}")
        tags = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
        if tags:
            # sage neutre ("green", jamais terracotta -- réservé à
            # l'interaction ailleurs dans la GUI, voir `_confidence_strip`).
            # `_descriptor_chips` (2026-08-27, retour utilisateur en direct :
            # un `st.badge` par tag, un par ligne, "takes too much space")
            # -- UNE chaîne markdown avec toutes les pills, rendue en un
            # seul `st.markdown`, qui s'enroule naturellement sur la largeur
            # disponible au lieu d'empiler une ligne par tag.
            st.markdown(_descriptor_chips(tags))

    with _panel():
        st.write("**Vital statistics**")
        # `hf_vital_stats` (2026-08-27, trouvé en vérifiant en direct dans le
        # navigateur -- voir `_TYPOGRAPHY_STYLE`) : une fourchette min-max
        # ("1.028–1.038") est plus longue que les valeurs simples que
        # `st.metric` affiche ailleurs dans la GUI (déjà un piège connu ici,
        # voir `_render_key_stats`). Conteneur dédié pour cibler UNIQUEMENT
        # ce bloc en CSS (jamais les autres `st.metric` de l'app, ex.
        # `_render_key_stats`) si la police par défaut redevient trop large
        # -- ligne-par-critère (`_vital_stat_row`) laisse déjà bien plus de
        # place que l'ancien layout à 5 colonnes côte à côte.
        # T105 : distribution RÉELLEMENT brassée (style_recipe_stats,
        # beer-analytics.com, T85) superposée à la fourchette BJCP quand
        # elle existe pour ce style -- `matching.style_observed_distribution`
        # renvoie {} si beer-analytics ne couvre pas ce style, jamais un
        # histogramme fabriqué (voir `_vital_stat_row`, repli silencieux sur
        # la simple barre BJCP dans ce cas).
        observed = matching.style_observed_distribution(con, row["style_id"])
        with st.container(key="hf_vital_stats"):
            _vital_stat_row(row, use_ebc, use_plato, observed)
        if observed:
            # Légende explicite (ticket T105) + rappel obligatoire : c'est un
            # histogramme PRÉ-BINNÉ ET ÉCRÊTÉ côté beer-analytics, jamais un
            # vrai percentile (même réserve que style_recipe_stats/T85).
            st.caption(":material/info: Terracotta band = official BJCP range. "
                      "Sage bars = observed distribution in real published "
                      "recipes (beer-analytics.com) — a pre-binned, clipped "
                      "histogram, not a percentile. They can diverge; that's "
                      "the point, not an error.")

    with _panel():
        if row["overall_impression"]:
            st.write(row["overall_impression"])
        else:
            st.caption("No overall impression recorded for this style.")
        _style_text_expander("Aroma", row["aroma"])
        _style_text_expander("Appearance", row["appearance"])
        _style_text_expander("Flavor", row["flavor"])
        _style_text_expander("Mouthfeel", row["mouthfeel"])
        _style_text_expander("Comments", row["comments"])
        _style_text_expander("History", row["history"])
        _style_text_expander("Ingredients", row["ingredients"])
        _style_text_expander("Style comparison", row["style_comparison"])

    examples = [e.strip() for e in (row["examples"] or "").split(",") if e.strip()]
    if examples:
        with _panel():
            st.write("**Commercial examples**")
            # `_source_chips` (gris neutre, même mécanisme d'enroulement que
            # `_descriptor_chips` ci-dessus -- voir son commentaire).
            st.markdown(_source_chips(examples))


_STYLE_HOPS_USAGE_TYPES = {"Any": "any", "Bittering": "bittering", "Aroma": "aroma",
                          "Dry hop": "dry-hop"}


def _style_hops(con) -> None:
    """T103 : mode "Hops for a style" -- la fonctionnalité la plus originale
    du backlog (aucun des deux outils qui l'ont inspiré ne fait ce
    croisement). Deux classements CÔTE À CÔTE pour un style BJCP donné :
    (1) fréquence RÉELLE (`matching.style_hop_frequency`, T86, beer-
    analytics.com -- ce que font les brasseurs) et (2) pertinence
    AROMATIQUE (`matching.by_descriptor` lancé sur les descripteurs
    typiques du style -- ce que dit la chimie/roue d'arôme). **Le
    livrable réel** : les houblons bien classés en (2) mais ABSENTS de (1)
    -- pertinents aromatiquement, jamais mesurés dans ce style -- dans SA
    PROPRE carte dédiée, jamais fondue en annexe d'un tableau combiné.
    Placée SOUS les deux classements côte à côte (2026-08-29, retour
    utilisateur en revue -- le lecteur voit d'abord les deux classements
    bruts, puis le point de divergence qui en découle), les trois cartes
    partageant le même fond opaque `_panel()`.

    Descripteurs typiques PRÉ-REMPLIS depuis le texte BJCP
    (`matching.style_typical_descriptors`) mais librement ÉDITABLES --
    recommandation explicite du ticket plutôt qu'une extraction automatique
    opaque imposée (précédent FooDB déjà rejeté deux fois, voir CLAUDE.md).

    Sélecteur catégorie/style dupliqué de `_styles` (T82) plutôt que
    factorisé -- la logique tient en une quinzaine de lignes, et ça évite
    de toucher `_styles` (stable, déjà testé) pour un gain de réutilisation
    marginal."""
    categories = sorted(
        {(r["category_id"], r["category"]) for r in
         con.execute("SELECT DISTINCT category_id, category FROM beer_styles")},
        key=_category_sort_key)
    if not categories:
        st.write("No style in the database yet — run `hopmatch ingest-styles` first.")
        return
    category_id, category = st.selectbox(
        "Category", categories, format_func=lambda c: f"{c[0]} - {c[1]}", key="style_hops_category")
    style_rows = con.execute(
        "SELECT style_id, name FROM beer_styles WHERE category_id=? AND category=? "
        "ORDER BY style_id", (category_id, category)).fetchall()
    style_id, style_name = st.selectbox(
        "Style", [(r["style_id"], r["name"]) for r in style_rows],
        format_func=lambda s: f"{s[0]} - {s[1]}", key="style_hops_style")

    with _panel():
        st.subheader(f"{style_id} - {style_name}")
        usage_type_label = st.segmented_control(
            "Usage stage (real recipe frequency)", list(_STYLE_HOPS_USAGE_TYPES),
            default="Any", key="style_hops_usage_type", required=True,
            help="Filters the real-frequency ranking to hops used at this stage "
                 "specifically (beer-analytics.com). The aroma-relevance ranking "
                 "is unaffected -- it doesn't depend on process stage.")
        # `key` inclut `style_id` : changer de style doit réinitialiser le
        # pré-remplissage (sinon la sélection éditée d'un style précédent
        # resterait affichée, sans rapport avec le nouveau style choisi).
        prefilled = matching.style_typical_descriptors(con, style_id)
        descriptors = st.multiselect(
            "Typical descriptors for this style", _descriptors(con), default=prefilled,
            key=f"style_hops_descriptors_{style_id}",
            help="Pre-filled from this style's BJCP aroma/flavor/ingredients text "
                 "(literal word match against the real descriptor vocabulary) -- "
                 "freely editable, never a filter you're locked into.")
        top = st.slider("Number of hops shown per ranking", 5, 30, 15, key="style_hops_top")

    usage_type = _STYLE_HOPS_USAGE_TYPES[usage_type_label]
    frequency = matching.style_hop_frequency(con, style_id, usage_type)
    if not descriptors:
        with _panel():
            st.write("Choose at least one typical descriptor above (or edit the pre-filled list).")
        return
    relevance_ranked = matching.by_descriptor(con, descriptors, top=top)["ranked"]

    if not frequency and not relevance_ranked:
        with _panel():
            st.write("No data (real frequency or aroma relevance) for this style/selection.")
        return

    # Deux cartes DE MÊME NIVEAU côte à côte (2026-08-29, retour utilisateur
    # en revue : même fond opaque `_panel()` que la section "rare &
    # relevant" ci-dessous, pour la cohérence visuelle -- `_panel(cols[i])`,
    # même mécanisme que les cartes de la page Home, voir son commentaire).
    col_freq, col_rel = st.columns(2)
    with _panel(col_freq):
        st.write(f"**Real frequency ({usage_type_label.lower()} usage in this style)**")
        st.caption("Share of this style's recipes using each hop (beer-analytics.com) "
                  "-- observed, not modeled.")
        if frequency:
            freq_rows = sorted(frequency.items(), key=lambda kv: -(kv[1]["share_avg24m"] or 0))[:top]
            st.dataframe(
                [{"Hop": d["hop_name"], "Recipe share": d["share_avg24m"]} for _, d in freq_rows],
                width="stretch", hide_index=True,
                column_config={"Recipe share": st.column_config.NumberColumn(format="percent")})
        else:
            st.caption(f"No beer-analytics.com data for this style at the "
                      f"'{usage_type_label}' stage.")
    with _panel(col_rel):
        st.write("**Aroma relevance (typical descriptors)**")
        st.caption("Hops whose real aroma wheel/descriptors best match the typical "
                  "descriptors selected above -- see \"From descriptors\" for the "
                  "full method.")
        if relevance_ranked:
            st.dataframe(
                [{"Hop": h["name"], "Matched descriptors": len(h["matched_descriptors"])}
                 for h in relevance_ranked],
                width="stretch", hide_index=True,
                column_config={"Matched descriptors": st.column_config.NumberColumn()})
        else:
            st.caption("No hop matches the selected descriptors.")

    # Livrable réel du ticket : pertinent aromatiquement (dans le
    # classement ci-dessus) ET absent de la fréquence réelle mesurée --
    # calculé SEULEMENT si `frequency` a au moins une ligne pour ce style/
    # usage_type (sinon "absent" ne voudrait rien dire : on n'a simplement
    # AUCUNE donnée beer-analytics pour ce style, pas la confirmation que
    # ces houblons y sont rares -- honnêteté d'abord). Placée SOUS les deux
    # classements (2026-08-29, retour utilisateur en revue) -- toujours sa
    # propre carte, jamais fondue avec les deux ci-dessus.
    if frequency:
        rare_relevant = [h for h in relevance_ranked if h["variety"] not in frequency]
        if rare_relevant:
            with _panel():
                st.subheader(":material/priority_high: Aromatically relevant, "
                             "rarely used in this style")
                st.caption(
                    "Ranks well on the typical-descriptor match above, but has no "
                    f"measured recipe usage in this style at the '{usage_type_label}' "
                    "stage (beer-analytics.com). Possibly overlooked — or there's a "
                    "real reason (cost, availability, tradition) this comparison "
                    "doesn't capture.")
                st.dataframe(
                    [{"Hop": h["name"],
                      "Matched descriptors": ", ".join(h["matched_descriptors"])}
                     for h in rare_relevant],
                    width="stretch", hide_index=True,
                    column_config={"Matched descriptors": st.column_config.ListColumn()})


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
    # Logo en tête de sidebar. T-D14b (2026-08-24) : `st.html`/`_logo_html`
    # (lockup "Stacked") remplace `st.image` (PAS `st.logo` -- déjà écarté
    # avant ce ticket : son plafond de taille intégré, 32px de haut max même
    # en "large", rendait un logo minuscule). 96px de marque : large mais
    # reste dans la largeur par défaut de la sidebar Streamlit (~336px).
    st.sidebar.html(_logo_html(mark_px=96, word_px=34))

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
                          "compare": "Explore — ", "styles": "Explore — ",
                          "style-hops": "Explore — "}
    mode = st.sidebar.radio(
        "Mode", ["home", "amplify", "contrast", "by-descriptor", "browse", "compare", "styles",
                "style-hops"],
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
        # `main()` en tête commune. T-D14b (2026-08-24) : lockup "Stacked"
        # (`_logo_html`) à taille "hero", remplace le raster `st.image`.
        st.html(_logo_html(mark_px=160, word_px=56))
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
    if mode == "styles":
        _styles(con)
        return
    if mode == "style-hops":
        _style_hops(con)
        return
    # "amplify" : seul mode restant après les dispatches explicites
    # ci-dessus -- la sélection de note vit désormais DANS `_amplify` (page
    # principale, pas la sidebar, voir son commentaire), donc plus rien à
    # faire ici que le header, comme les autres modes.
    _amplify(con)


if __name__ == "__main__":
    main()
