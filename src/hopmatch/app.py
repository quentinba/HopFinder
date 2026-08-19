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
_BACKGROUND_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "assets", "background.png")

# Libellés GUI affichés à l'utilisateur, distincts des clés internes ("mode")
# qui pilotent le dispatch et restent stables (CLI/tests/URLs internes non
# concernés — habillage d'affichage uniquement, demandé par l'utilisateur).
MODE_LABELS = {
    "home": "Home",
    "amplify": "HopFinder - Amplify",
    "contrast": "HopFinder - Contrast",
    "by-descriptor": "HopFinder from Descriptors",
    "browse": "Browse hop informations",
}

# Page d'accueil (front page) : résumé des outils, avec accès direct à chacun.
_TOOL_SUMMARIES = [
    {
        "mode": "amplify",
        "icon": ":material/trending_up:",
        "tagline": "Extend an addition",
        "description": (
            "The addition (yuzu, basil...) is already in the beer — find a hop "
            "that **extends** its character rather than reproducing it. Combines "
            "molecular similarity (TF-IDF) with aroma-wheel overlap. Also "
            "proposes blends of 1 to 5 hops actually used together in recipes "
            "(BeerMaverick)."
        ),
    },
    {
        "mode": "contrast",
        "icon": ":material/contrast:",
        "tagline": "Pair by contrast",
        "description": (
            "Looks for a hop with a **complementary** profile (bright citrus "
            "under a dank/resinous hop), not a similar one — via a descriptor "
            "affinity map, never molecular. Same multi-size blends as Amplify, "
            "prioritizing real recipe pairing frequency."
        ),
    },
    {
        "mode": "by-descriptor",
        "icon": ":material/search:",
        "tagline": "Discovery by descriptors",
        "description": (
            "No note required: pick descriptors directly (citrus, tropical, "
            "dank...) and see which hops best match the real aroma wheel "
            "(BarthHaas/Yakima/BeerMaverick)."
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


def _db_path() -> str:
    if "--db" in sys.argv:
        return sys.argv[sys.argv.index("--db") + 1]
    return DEFAULT_DB


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


def _inject_background() -> None:
    """Image de fond derrière le contenu principal (demande utilisateur),
    assombrie par un voile semi-transparent COULEUR DU THÈME (pas une
    couleur fixe) pour rester lisible en clair ET en sombre -- même logique
    que `_aroma_wheel` : `st.context.theme.type` est la seule info de thème
    exposée par Streamlit, palette choisie à la main pour les deux cas.
    Cible `[data-testid="stAppViewContainer"]` (zone de contenu), pas la
    sidebar : elle garde son fond plein pour que la navigation reste nette.

    Deux ajustements du 2026-08-19 (retour utilisateur sur la première
    version) : (1) négatif couleur en thème sombre plutôt qu'un simple voile
    (voir `_background_data_uri`) ; (2) `background-attachment: fixed` +
    `center top` retiré -- avec `fixed`, la taille de l'image se calcule par
    rapport au VIEWPORT (pas au contenu, souvent bien plus haut qu'un seul
    écran une fois défilé), donc `cover` n'affichait jamais que la tranche du
    haut, toujours la même en défilant. Sans `fixed` (comportement par
    défaut, l'image défile avec le contenu), `cover` se recalcule par
    rapport à la hauteur RÉELLE de la page -- on voit donc bien plus de la
    hauteur de l'illustration en descendant. `background-position: right
    top` cadre sur la partie droite de l'image (jugée plus réussie par
    l'utilisateur) plutôt que le centre."""
    if not os.path.exists(_BACKGROUND_PATH):
        return
    dark = st.context.theme.type == "dark"
    uri = _background_data_uri(_BACKGROUND_PATH, os.path.getmtime(_BACKGROUND_PATH), dark)
    if uri is None:
        return
    veil = "rgba(14,17,23,0.72)" if dark else "rgba(255,255,255,0.86)"
    st.markdown(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image: linear-gradient({veil}, {veil}), url("{uri}");
            background-size: cover;
            background-position: right top;
            background-repeat: no-repeat;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def _purpose_badge(purpose: str | None) -> None:
    if purpose is None:
        st.badge("Unknown", color="gray", icon=":material/help:")
        return
    st.badge(_PURPOSE_LABELS.get(purpose, purpose), color=_PURPOSE_COLORS.get(purpose, "gray"),
             icon=_PURPOSE_ICONS.get(purpose))


def _render_hop_rows(rows: list[dict], columns: list[tuple[str, str]]) -> None:
    """Rendu ligne par ligne (pas `st.dataframe`) : nécessaire pour la colonne
    Purpose colorée via `st.badge` (couleurs sémantiques Streamlit, seul
    rendu par cellule qui s'adapte aux deux thèmes — voir `_purpose_badge`).
    Réutilisé par les tableaux de résultats amplify/contrast ET les tableaux
    de blend. `rows` : dicts avec une clé "name" + les clés référencées par
    `columns` ([(en-tête, clé)]) ; une colonne dont la clé est "purpose" se
    rend en badge plutôt qu'en texte."""
    widths = [3] + [2] * len(columns)
    header_cols = st.columns(widths)
    header_cols[0].caption("Hop")
    for col, (header, _) in zip(header_cols[1:], columns):
        col.caption(header)
    for row in rows:
        cols = st.columns(widths, vertical_alignment="center")
        cols[0].write(row["name"])
        for col, (_, field) in zip(cols[1:], columns):
            if field == "purpose":
                with col:
                    _purpose_badge(row.get("purpose"))
            else:
                col.write(row.get(field, ""))


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
    que par navigation."""
    st.subheader("Hop details")
    for row in rows:
        v = row["variety"]
        with st.expander(f"{row['name']} — {row['caption']}"):
            _purpose_badge(hops[v].get("purpose"))
            st.caption(f"Sources: {hops[v]['sources']}")
            descs = sorted(hop_desc.get(v, set()))
            st.write("**Descriptors:** " + (", ".join(descs) if descs else "none recorded"))
            intensity = matching.hop_aroma_intensity(con, v)
            if intensity and any(val > 0 for val in intensity.values()):
                st.altair_chart(_aroma_wheel(intensity, _intensity_vocabulary(con)),
                                width="content", theme=None)
            hcomp = comp.get(v, {})
            crows = sorted(
                ({"Compound": c, "Value": round(cv["mid"], 3), "Unit": cv["unit"],
                  "Sources": ", ".join(cv["sources"])}
                 for c, cv in hcomp.items()
                 if c not in _NON_AROMA_DISPLAY and cv["mid"] is not None),
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


def _amplify(con, note):
    st.sidebar.subheader("Options")
    use_oav = st.sidebar.checkbox(
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
            "chemistry rarely overlaps with food aromas, see CLAUDE.md). "
            "**Add as many descriptors as possible** above for a more "
            "reliable result.")
    if r["orphan"]:
        st.warning("Orphans (carried by the addition, not the hop): "
                   + ", ".join(r["orphan"]))
    if not r["ranked"]:
        st.write("No hop overlaps with this note.")
        return
    _render_hop_rows(
        [dict(h, why_str=", ".join(h["why"]) or "—") for h in r["ranked"]],
        [("Score", "score"), ("Mol.", "mol"), ("Desc.", "desc"), ("Purpose", "purpose"),
        ("Contributes via", "why_str"), ("Sources", "sources")])

    hops, comp, hop_desc, _ = matching.load(con)
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
        _render_blends(blend_r["blends"])


_VIA_LABELS = {"top": "top candidate", "chosen": "base hop (chosen)",
              "complement": "opposite purpose (aromatic/bittering complement)",
              "pairing": "relevant + BeerMaverick pairing (top 10)",
              "coverage": "coverage fallback (no relevant pairing)",
              "relevance": "relevant extra hop (nothing new to cover)"}


def _render_blends(blends: list[dict]) -> None:
    """Rendu partagé amplify_blend/contrast_blend (T33 backlog) : plusieurs
    tailles de blend affichées côte à côte plutôt qu'un seul "meilleur" blend
    — chaque houblon signale sa provenance (fréquence RÉELLE de pairing
    BeerMaverick vs. repli par couverture), jamais caché derrière un score
    unique fusionné. Colonne Purpose (T-purpose backlog) : depuis la taille
    2, le mécanisme garantit au moins 1 aromatique + 1 amérisant puis ne
    recrute plus que des aromatiques (voir `matching._pairing_grown_blends`)
    — la colonne rend cette structure visible plutôt que de la laisser
    implicite."""
    if not blends:
        st.write("No combination found.")
        return
    for b in blends:
        st.write(f"**Size {b['size']}**")
        rows = [dict(h, covers_str=", ".join(h["covers"]) or "(nothing new)",
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
    top = st.sidebar.slider("Number of results", 1, 30, 8)
    if not selected:
        st.write("Choose at least one descriptor."); return
    r = matching.contrast(con, descriptors=selected, top=top)

    st.caption("Affinity target: " + ", ".join(r["affinity_target"]))
    if r["unmapped"]:
        st.caption(":material/info: No affinity mapping for: "
                  + ", ".join(r["unmapped"]) + " (ignored, no effect on the target).")
    if not r["ranked"]:
        st.write("No hop overlaps with this target.")
        return
    _render_hop_rows(
        [dict(h, contrast_via_str=", ".join(h["contrast_via"])) for h in r["ranked"]],
        [("Score", "score"), ("Purpose", "purpose"), ("Contrasts via", "contrast_via_str"),
        ("Sources", "sources")])

    hops, comp, hop_desc, _ = matching.load(con)
    _hop_detail_expanders(con, hops, comp, hop_desc, [
        {"variety": h["variety"], "name": h["name"],
         "caption": f"score {h['score']} — contrasts via {', '.join(h['contrast_via'])}"}
        for h in r["ranked"]])

    st.subheader("Propose a blend")
    base = _select_base_hop(r["ranked"], key="contrast_base_hop")
    # Toujours 5 (décision utilisateur) : pas de curseur.
    blend_r = matching.contrast_blend(con, descriptors=selected, max_hops=5, base_variety=base)
    _render_blends(blend_r["blends"])


_NON_AROMA_DISPLAY = {"total_oil", "alpha_acid", "beta_acid"}


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
        labels.append({"x": lx, "y": ly, "Descriptor": d})

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
        .encode(x=x_enc, y=y_enc, text="Descriptor:N")
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
    (T25, voir `_hop_associations`)."""
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
    st.subheader(h["name"])
    # purpose EN PREMIER, avant région/sources (demande utilisateur explicite :
    # "should appear in the browser information as a main/top information").
    _purpose_badge(h.get("purpose"))
    st.caption(f"Region: {h['region'] or 'unknown'} · Sources: {h['sources']}")

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
    else:
        st.caption("No quantitative aroma wheel for this variety "
                   "(Yakima data unavailable or unusable here — BarthHaas "
                   "only, variety not covered, or corrupted YCH entry as "
                   "with Admiral).")

    hcomp = comp.get(selected, {})
    rows = sorted(
        ({"Compound": c, "Value": round(v["mid"], 3), "Unit": v["unit"],
          "Sources": ", ".join(v["sources"])}
         for c, v in hcomp.items() if c not in _NON_AROMA_DISPLAY and v["mid"] is not None),
        key=lambda r: -r["Value"])
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.write("No composition recorded.")

    st.divider()
    _hop_associations(con, hops, selected)


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


def _descriptor_heatmap(ranked):
    """Grille houblon x descripteur (présence), pour comparer visuellement
    plusieurs candidats d'un coup (T4 backlog). Une teinte, présence/absence —
    pas un radar : les descripteurs sont un ensemble binaire par houblon (pas
    une quantité), un radar déformerait par l'aire pour un gain de lisibilité
    nul ; une grille compare exactement les mêmes données sans cette
    distorsion (voir la table forme/usage du skill dataviz : « grille ->
    heatmap, une teinte »). Champs Vega en anglais ("Hop"/"Descriptor"/
    "Present") : visibles au survol (tooltip), cohérent avec le passage de la
    GUI à l'anglais (2026-08-19)."""
    if len(ranked) < 2:
        return None
    shown = ranked[:_MAX_HEATMAP_HOPS]
    hop_order = [h["name"] for h in shown]
    freq = {}
    for h in shown:
        for d in h["all_descriptors"]:
            freq[d] = freq.get(d, 0) + 1
    descriptor_order = sorted(freq, key=lambda d: (-freq[d], d))
    rows = [
        {"Hop": h["name"], "Descriptor": d,
         "Present": "yes" if d in h["all_descriptors"] else "no"}
        for h in shown for d in descriptor_order
    ]
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_rect(stroke="white", strokeWidth=2)
        .encode(
            x=alt.X("Hop:N", sort=hop_order, title=None,
                    axis=alt.Axis(labelAngle=-45, labelOverlap=False, labelLimit=200)),
            y=alt.Y("Descriptor:N", sort=descriptor_order, title=None,
                    axis=alt.Axis(labelOverlap=False)),
            color=alt.Color(
                "Present:N",
                scale=alt.Scale(domain=["yes", "no"], range=["#2a78d6", "#f2f1ee"]),
                legend=alt.Legend(title="Descriptor present")),
            tooltip=["Hop:N", "Descriptor:N", "Present:N"],
        )
        # largeur/hauteur au pas (pas "container") : le nombre de lignes/colonnes
        # varie avec la sélection, une largeur fixe tronque les libellés en
        # silence (labelOverlap les faisait disparaître un sur deux, vérifié
        # en direct avec 10 houblons).
        .properties(width=alt.Step(45), height=alt.Step(18))
    )
    return chart, len(ranked) - len(shown)


def _by_descriptor(con):
    descriptors = _descriptors(con)
    selected = st.multiselect("Descriptors", descriptors)
    top = st.sidebar.slider("Number of hops shown", 1, 30, 10)
    if not selected:
        st.write("Choose at least one descriptor.")
        return
    ranked = matching.by_descriptor(con, selected, top=top)
    if not ranked:
        st.write("No hop overlaps with these descriptors.")
        return

    heatmap = _descriptor_heatmap(ranked)
    if heatmap is not None:
        chart, hidden = heatmap
        st.caption("Descriptor profile comparison" +
                   (f" (first 12 of {len(ranked)})" if hidden else ""))
        st.altair_chart(chart, width="stretch")

    for h in ranked:
        with st.expander(
                f"{h['name']} — matches {', '.join(h['matched_descriptors'])} "
                f"[{h['sources']}]"):
            _purpose_badge(h.get("purpose"))
            st.caption("All descriptors: " + ", ".join(h["all_descriptors"]))
            if h["compounds"]:
                st.dataframe(
                    [{"Compound": c["compound"], "Value": round(c["mid"], 2),
                      "Unit": c["unit"], "Sources": ", ".join(c["sources"])}
                     for c in h["compounds"][:8]],
                    width="stretch", hide_index=True)


def main():
    st.set_page_config(page_title="hopmatch", page_icon="🌿")
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
    st.title("hopmatch")
    st.caption("Aroma note → molecules → hops")

    db_path = _db_path()
    if not os.path.exists(db_path):
        st.error(f"Database not found: `{db_path}`. Build the database on the "
                 f"CLI side first (`hopmatch build`, or "
                 f"`crawl-barthhaas`/`crawl-yakima`/`ingest-*`).")
        st.stop()
    con = _connection(db_path)

    # Contexte base (T6 backlog) : la construction se fait entièrement en CLI,
    # hors de la vue GUI — sans ça, rien n'indique si la base ouverte est la
    # démo (`hopmatch build`, 4 houblons) ou une base réelle, ni sa fraîcheur.
    stats = _stats(con)
    modified = datetime.fromtimestamp(_db_version(db_path)).strftime("%Y-%m-%d %H:%M")
    st.sidebar.caption(
        f"**{db_path}** — {stats['hops']} hops, {stats['notes']} notes, "
        f"{stats['descriptors']} descriptors · modified {modified}")

    mode = st.sidebar.radio(
        "Mode", ["home", "amplify", "contrast", "by-descriptor", "browse"],
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

    notes = _notes(con)
    if not notes:
        st.error("No notes in the database."); st.stop()
    note = st.sidebar.selectbox("Note", notes)

    st.header(f"{MODE_LABELS[mode]} — {note}")
    _amplify(con, note)


if __name__ == "__main__":
    main()
