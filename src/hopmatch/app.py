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
    max_hops = st.slider("Nombre de houblons max", 1, 6, 3)
    blend = matching.contrast_blend(con, descriptors=selected, max_hops=max_hops)
    if not blend["blend"]:
        st.write("Aucune combinaison trouvée.")
        return
    st.dataframe(
        [{"Houblon": h["name"], "Couvre": ", ".join(h["covers"]), "Sources": h["sources"]}
         for h in blend["blend"]],
        width="stretch", hide_index=True)
    if blend["residual"]:
        st.warning("Non couvert par le blend : " + ", ".join(blend["residual"]))


_NON_AROMA_DISPLAY = {"total_oil", "alpha_acid", "beta_acid"}


def _browse(con):
    """Mode propre à la GUI (pas d'équivalent CLI) : consulter un houblon
    directement — composition + descripteurs + sources — sans passer par
    amplify/contrast/by-descriptor (T5 backlog)."""
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
