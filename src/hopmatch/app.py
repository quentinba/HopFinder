"""
GUI Streamlit : les modes du CLI (amplify/contrast/by-descriptor) +
un mode "browse" propre à la GUI pour parcourir la base brute (houblon par
houblon), en lecture seule contre une base déjà construite. Ne touche pas à
l'ingestion (crawl/build/ingest-*) : ça reste le rôle du CLI (`hopmatch
build`, `hopmatch crawl-barthhaas`...). N'importe que `matching`/`schema`,
jamais `ingest`.

Lancer : streamlit run src/hopmatch/app.py [-- --db chemin/vers/aromahops.db]
"""
from __future__ import annotations
import math
import os
import sys
from datetime import datetime

import altair as alt
import streamlit as st

from hopmatch import matching
from hopmatch.schema import connect

DEFAULT_DB = "aromahops.db"

# Libellés GUI affichés à l'utilisateur, distincts des clés internes ("mode")
# qui pilotent le dispatch et restent stables (CLI/tests/URLs internes non
# concernés — habillage d'affichage uniquement, demandé par l'utilisateur).
MODE_LABELS = {
    "amplify": "HopFinder - Amplify",
    "contrast": "HopFinder - Contrast",
    "by-descriptor": "Hopfinder from Descriptors",
    "browse": "Browse hop composition",
}


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


def _amplify(con, note):
    st.sidebar.subheader("Options")
    use_oav = st.sidebar.checkbox(
        "--oav (prior de puissance olfactive)", value=False,
        help="Pondère chaque molécule par 1/seuil olfactif quand ce seuil est "
             "connu (~14 molécules d'huile de houblon courantes : myrcène, "
             "géraniol, thiols... — les autres molécules ne sont pas affectées). "
             "Approximatif : pas une mesure de concentration réelle, juste une "
             "correction pour qu'une molécule très odorante à faible seuil ne "
             "soit pas éclipsée par une molécule ubiquitaire mais peu odorante. "
             "Change le classement sur environ 1 note sur 6 (mesuré sur la base "
             "réelle).")
    top = st.sidebar.slider("Nombre de résultats", 1, 30, 8)
    # note_descriptors est vide par défaut pour toute note (pas d'amorce
    # littérature, cf. reference.py) : sans sélection manuelle ici, la couche
    # descripteurs ne peut jamais contribuer au score.
    selected_desc = st.multiselect(
        "Descripteurs de la note (optionnel — active la couche descripteurs)",
        _descriptors(con))
    r = matching.amplify(con, note, use_oav=use_oav,
                         descriptors=selected_desc or None, top=top)

    st.metric("Couverture moléculaire", f"{r['coverage']*100:.0f}%")
    if not r.get("has_descriptors", True):
        st.caption("Pas de descripteurs pour cette note : score 100% moléculaire "
                  "(pas de w_desc appliqué).")
    if r["coverage"] < matching.LOW_COVERAGE_WARNING_THRESHOLD:
        st.warning(
            f"Couverture moléculaire faible ({r['coverage']*100:.0f}%) : le classement "
            "moléculaire seul risque d'être dominé par une seule molécule commune à "
            "beaucoup d'aliments, pas par la signature propre de cette note (la chimie "
            "de l'huile de houblon recoupe peu la plupart des arômes alimentaires, voir "
            "CLAUDE.md). **Ajoutez le plus de descripteurs possible** ci-dessus pour un "
            "résultat plus fiable.")
    if r["orphan"]:
        st.warning("Orphelines (portées par l'ajout, pas le houblon) : "
                   + ", ".join(r["orphan"]))
    if not r["ranked"]:
        st.write("Aucun houblon ne recoupe cette note.")
        return
    st.dataframe(
        [{"Houblon": h["name"], "Score": h["score"], "Mol.": h["mol"], "Desc.": h["desc"],
          "Contribue via": ", ".join(h["why"]), "Sources": h["sources"]}
         for h in r["ranked"]],
        width="stretch", hide_index=True)

    st.subheader("Proposer un blend")
    if not r["has_descriptors"]:
        st.caption("Pas de descripteurs pour cette note : aucun blend possible "
                  "(sélectionne des descripteurs ci-dessus).")
    else:
        max_hops = st.slider("Nombre de houblons max", 1, 5, 5, key="amplify_blend_max_hops")
        blend_r = matching.amplify_blend(con, note, use_oav=use_oav,
                                         descriptors=selected_desc or None, max_hops=max_hops)
        _render_blends(blend_r["blends"])


_VIA_LABELS = {"top": "meilleur candidat", "pairing": "pairing BeerMaverick réel",
              "coverage": "repli couverture (pas de donnée BeerMaverick)"}


def _render_blends(blends: list[dict]) -> None:
    """Rendu partagé amplify_blend/contrast_blend (T33 backlog) : plusieurs
    tailles de blend affichées côte à côte plutôt qu'un seul "meilleur" blend
    — chaque houblon signale sa provenance (fréquence RÉELLE de pairing
    BeerMaverick vs. repli par couverture), jamais caché derrière un score
    unique fusionné."""
    if not blends:
        st.write("Aucune combinaison trouvée.")
        return
    for b in blends:
        st.write(f"**Taille {b['size']}**")
        st.dataframe(
            [{"Houblon": h["name"], "Couvre": ", ".join(h["covers"]) or "(rien de nouveau)",
              "Origine": _VIA_LABELS[h["via"]], "Sources": h["sources"]}
             for h in b["hops"]],
            width="stretch", hide_index=True)
        if b["residual"]:
            st.caption("Non couvert : " + ", ".join(b["residual"]))


def _contrast(con):
    # contrast a besoin de note_descriptors pour une note, table vide par
    # défaut (pas d'amorce littérature dans ce projet, cf. reference.py) —
    # l'utilisateur décrit donc sa note à la main avec le vocabulaire réel de
    # la roue d'arôme (même source que by-descriptor), ce qui fonctionne pour
    # n'importe quelle note sans rien inventer.
    selected = st.multiselect("Descripteurs de la note à contraster", _descriptors(con))
    top = st.sidebar.slider("Nombre de résultats", 1, 30, 8)
    if not selected:
        st.write("Choisis au moins un descripteur."); return
    r = matching.contrast(con, descriptors=selected, top=top)

    st.caption("Cible d'affinité : " + ", ".join(r["affinity_target"]))
    if r["unmapped"]:
        st.caption(":material/info: Pas de carte d'affinité pour : "
                  + ", ".join(r["unmapped"]) + " (ignorés, sans effet sur la cible).")
    if not r["ranked"]:
        st.write("Aucun houblon ne recoupe cette cible.")
        return
    st.dataframe(
        [{"Houblon": h["name"], "Score": h["score"],
          "Contraste via": ", ".join(h["contrast_via"]), "Sources": h["sources"]}
         for h in r["ranked"]],
        width="stretch", hide_index=True)

    st.subheader("Proposer un blend")
    max_hops = st.slider("Nombre de houblons max", 1, 5, 5, key="contrast_blend_max_hops")
    blend_r = matching.contrast_blend(con, descriptors=selected, max_hops=max_hops)
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
    alphabétique stable, mêmes positions d'un houblon à l'autre. BarthHaas n'a pas cette donnée : `intensity` vide pour
    les houblons non couverts, pas de roue affichée dans ce cas (voir
    `_browse`), pas de valeur inventée.

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
    pas de superposition à comparer."""
    if not vocabulary:
        return None
    n = len(vocabulary)
    r_max = 130.0
    half_extent = r_max + 45.0

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
        lx, ly = (r_max + 20) * math.cos(angle), (r_max + 20) * math.sin(angle)
        labels.append({"x": lx, "y": ly, "Descripteur": d})

    poly = []
    for i, d in enumerate(vocabulary):
        val = intensity.get(d, 0.0)
        x, y = _xy(i, val)
        poly.append({"x": x, "y": y, "Descripteur": d, "Intensité": val, "Ordre": i})
    poly.append(dict(poly[0], Ordre=n))  # referme le polygone

    domain = [-half_extent, half_extent]
    x_enc = alt.X("x:Q", axis=None, scale=alt.Scale(domain=domain))
    y_enc = alt.Y("y:Q", axis=None, scale=alt.Scale(domain=domain))

    grid = (
        alt.Chart(alt.Data(values=spokes))
        .mark_rule(strokeWidth=1, stroke="#3a3a38")
        .encode(x=x_enc, y=y_enc, x2="x2:Q", y2="y2:Q")
    )
    polygon_line = (
        alt.Chart(alt.Data(values=poly))
        .mark_line(color="#2a78d6", strokeWidth=2, order=True)
        .encode(x=x_enc, y=y_enc, order="Ordre:Q")
    )
    points = (
        alt.Chart(alt.Data(values=poly[:-1]))
        .mark_point(filled=True, size=45, color="#2a78d6")
        .encode(x=x_enc, y=y_enc,
               tooltip=["Descripteur:N", alt.Tooltip("Intensité:Q", format=".0f")])
    )
    text = (
        alt.Chart(alt.Data(values=labels))
        .mark_text(fontSize=10)
        .encode(x=x_enc, y=y_enc, text="Descripteur:N")
    )
    return (
        (grid + polygon_line + points + text)
        .properties(width=360, height=360)
        .configure_view(strokeWidth=0)
    )


def _browse(con):
    """Mode propre à la GUI (pas d'équivalent CLI) : consulter un houblon
    directement — composition + descripteurs + sources — sans passer par
    amplify/contrast/by-descriptor (T5 backlog). Affiche aussi la roue
    d'arôme quantitative (T26) et les associations houblon<->houblon
    (T25, voir `_hop_associations`)."""
    hops, comp, hop_desc, _ = matching.load(con)
    query = st.text_input("Rechercher (nom ou variété)")
    varieties = sorted(hops, key=lambda v: hops[v]["name"].lower())
    if query:
        q = query.strip().lower()
        varieties = [v for v in varieties if q in hops[v]["name"].lower() or q in v]
    st.caption(f"{len(varieties)} houblon(s)")
    if not varieties:
        st.write("Aucun houblon ne correspond à cette recherche.")
        return

    selected = st.selectbox("Houblon", varieties, format_func=lambda v: hops[v]["name"])
    h = hops[selected]
    st.subheader(h["name"])
    st.caption(f"Région : {h['region'] or 'inconnue'} · Sources : {h['sources']}")

    descs = sorted(hop_desc.get(selected, set()))
    st.write("**Descripteurs :** " + (", ".join(descs) if descs else "aucun enregistré"))
    intensity = matching.hop_aroma_intensity(con, selected)
    # any(...) > 0, pas juste `if intensity :` : au moins une variété réelle
    # (admiral, vérifié en direct) a une entrée sensory_values existante mais
    # entièrement à 0 côté YCH — cohérent avec la corruption déjà documentée
    # de cette variété précise (voir _is_plausible_brewing_entry) ; un dict
    # non vide mais tout à zéro n'est pas une donnée exploitable.
    if intensity and any(v > 0 for v in intensity.values()):
        st.altair_chart(_aroma_wheel(intensity, _intensity_vocabulary(con)), width="content")
    else:
        st.caption("Pas de roue d'arôme quantitative pour cette variété "
                   "(donnée Yakima non disponible ou non exploitable ici — "
                   "BarthHaas seul, variété non couverte, ou entrée YCH "
                   "corrompue comme pour Admiral).")

    hcomp = comp.get(selected, {})
    rows = sorted(
        ({"Composé": c, "Valeur": round(v["mid"], 3), "Unité": v["unit"],
          "Sources": ", ".join(v["sources"])}
         for c, v in hcomp.items() if c not in _NON_AROMA_DISPLAY and v["mid"] is not None),
        key=lambda r: -r["Valeur"])
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.write("Aucune composition enregistrée.")

    st.divider()
    _hop_associations(con, hops, selected)


def _hop_associations(con, hops: dict, selected: str) -> None:
    """Associations houblon<->houblon (T25 backlog) : trois relations
    différentes, chacune affichée avec sa propre source — ne jamais les
    présenter comme interchangeables (similarité YCH != co-usage recette
    BeerMaverick != choix éditorial BeerMaverick)."""
    similar = matching.hop_similar_varieties(con, selected)
    st.write("**Variétés similaires (Yakima)**")
    if similar:
        st.write(", ".join(hops[v]["name"] for v in similar if v in hops))
    else:
        st.caption("Aucune suggestion Yakima pour cette variété.")

    pairings = matching.hop_pairings(con, selected)
    st.write("**Associations fréquentes en recette (BeerMaverick — agrégateur, "
             "analyse de recettes publiées, pas une mesure de labo)**")
    if pairings:
        st.dataframe(
            [{"Houblon": hops[p["variety"]]["name"] if p["variety"] in hops else p["name"],
              "Fréquence relative": p["frequency"]} for p in pairings],
            width="stretch", hide_index=True)
    else:
        st.caption("Aucune donnée BeerMaverick pour cette variété (volume de "
                   "recettes insuffisant chez eux, ou variété non couverte).")

    subs = matching.hop_substitutions(con, selected)
    st.write("**Substitutions suggérées (BeerMaverick — choix éditorial de "
             "brasseurs expérimentés, pas une mesure)**")
    if subs:
        st.write(", ".join(
            hops[s["variety"]]["name"] if s["variety"] in hops else s["name"] for s in subs))
    else:
        st.caption("Aucune donnée BeerMaverick pour cette variété.")


_MAX_HEATMAP_HOPS = 12


def _descriptor_heatmap(ranked):
    """Grille houblon x descripteur (présence), pour comparer visuellement
    plusieurs candidats d'un coup (T4 backlog). Une teinte, présence/absence —
    pas un radar : les descripteurs sont un ensemble binaire par houblon (pas
    une quantité), un radar déformerait par l'aire pour un gain de lisibilité
    nul ; une grille compare exactement les mêmes données sans cette
    distorsion (voir la table forme/usage du skill dataviz : « grille ->
    heatmap, une teinte »)."""
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
        {"Houblon": h["name"], "Descripteur": d,
         "Présent": "oui" if d in h["all_descriptors"] else "non"}
        for h in shown for d in descriptor_order
    ]
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_rect(stroke="white", strokeWidth=2)
        .encode(
            x=alt.X("Houblon:N", sort=hop_order, title=None,
                    axis=alt.Axis(labelAngle=-45, labelOverlap=False, labelLimit=200)),
            y=alt.Y("Descripteur:N", sort=descriptor_order, title=None,
                    axis=alt.Axis(labelOverlap=False)),
            color=alt.Color(
                "Présent:N",
                scale=alt.Scale(domain=["oui", "non"], range=["#2a78d6", "#f2f1ee"]),
                legend=alt.Legend(title="Descripteur présent")),
            tooltip=["Houblon:N", "Descripteur:N", "Présent:N"],
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
    selected = st.multiselect("Descripteurs", descriptors)
    top = st.sidebar.slider("Nombre de houblons affichés", 1, 30, 10)
    if not selected:
        st.write("Choisis au moins un descripteur.")
        return
    ranked = matching.by_descriptor(con, selected, top=top)
    if not ranked:
        st.write("Aucun houblon ne recoupe ces descripteurs.")
        return

    heatmap = _descriptor_heatmap(ranked)
    if heatmap is not None:
        chart, hidden = heatmap
        st.caption("Comparaison des profils de descripteurs" +
                   (f" (12 premiers sur {len(ranked)})" if hidden else ""))
        st.altair_chart(chart, width="stretch")

    for h in ranked:
        with st.expander(
                f"{h['name']} — recoupe {', '.join(h['matched_descriptors'])} "
                f"[{h['sources']}]"):
            st.caption("Tous les descripteurs : " + ", ".join(h["all_descriptors"]))
            if h["compounds"]:
                st.dataframe(
                    [{"Composé": c["compound"], "Valeur": round(c["mid"], 2),
                      "Unité": c["unit"], "Sources": ", ".join(c["sources"])}
                     for c in h["compounds"][:8]],
                    width="stretch", hide_index=True)


def main():
    st.set_page_config(page_title="hopmatch", page_icon="🌿")
    st.title("hopmatch")
    st.caption("Note olfactive → molécules → houblons")

    db_path = _db_path()
    if not os.path.exists(db_path):
        st.error(f"Base introuvable : `{db_path}`. Construire la base côté CLI d'abord "
                 f"(`hopmatch build`, ou `crawl-barthhaas`/`crawl-yakima`/`ingest-*`).")
        st.stop()
    con = _connection(db_path)

    # Contexte base (T6 backlog) : la construction se fait entièrement en CLI,
    # hors de la vue GUI — sans ça, rien n'indique si la base ouverte est la
    # démo (`hopmatch build`, 4 houblons) ou une base réelle, ni sa fraîcheur.
    stats = _stats(con)
    modified = datetime.fromtimestamp(_db_version(db_path)).strftime("%Y-%m-%d %H:%M")
    st.sidebar.caption(
        f"**{db_path}** — {stats['hops']} houblons, {stats['notes']} notes, "
        f"{stats['descriptors']} descripteurs · modifiée {modified}")

    mode = st.sidebar.radio(
        "Mode", ["amplify", "contrast", "by-descriptor", "browse"],
        format_func=lambda m: MODE_LABELS[m])

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
        st.error("Aucune note en base."); st.stop()
    note = st.sidebar.selectbox("Note", notes)

    st.header(f"{MODE_LABELS[mode]} — {note}")
    _amplify(con, note)


if __name__ == "__main__":
    main()
