"""
GUI Streamlit : les mêmes modes que le CLI (amplify/contrast/combine/by-descriptor),
en lecture seule contre une base déjà construite. Ne touche pas à l'ingestion
(crawl/build/ingest-*) : ça reste le rôle du CLI (`hopmatch build`, `hopmatch
crawl-barthhaas`...). N'importe que `matching`/`schema`, jamais `ingest`.

Lancer : streamlit run src/hopmatch/app.py [-- --db chemin/vers/aromahops.db]
"""
from __future__ import annotations
import os
import sys

import streamlit as st

from hopmatch import matching
from hopmatch.schema import connect

DEFAULT_DB = "aromahops.db"


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


def _notes(con) -> list[str]:
    return sorted(r[0] for r in con.execute("SELECT DISTINCT note FROM aroma_notes"))


def _descriptors(con) -> list[str]:
    return sorted(r[0] for r in con.execute("SELECT DISTINCT descriptor FROM hop_descriptors"))


def _amplify(con, note):
    st.sidebar.subheader("Options")
    use_oav = st.sidebar.checkbox("--oav (prior de seuil, approx.)", value=False)
    biotransform = st.sidebar.checkbox(
        "--biotransform (fermentation levure standard)", value=False)
    r = matching.amplify(con, note, use_oav=use_oav, biotransform=biotransform)

    st.metric("Couverture moléculaire", f"{r['coverage']*100:.0f}%")
    if r["biotransform"]:
        st.info("Hypothèse active : fermentation levure standard "
                "(géraniol→citronellol, linalol→alpha-terpinéol).")
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
        use_container_width=True, hide_index=True)


def _contrast(con):
    # contrast n'a de note_descriptors curés que pour les 7 notes littérature
    # (voir matching.contrast) : les notes auto-dérivées de FooDB n'en ont pas et
    # ça ne peut pas être dérivé fiablement (données FooDB majoritairement
    # génériques, cf. docs/DATA_SOURCES.md). Plutôt qu'échouer sur ces notes-là,
    # on laisse l'utilisateur décrire sa note à la main avec le vocabulaire réel
    # de la roue d'arôme (même source que by-descriptor) — généralise contrast à
    # n'importe quelle note sans rien inventer.
    source = st.radio("Décrire la note via", ["note curée (amorce littérature)",
                                              "sélection manuelle de descripteurs"])
    if source.startswith("note"):
        notes = _notes(con)
        if not notes:
            st.error("Aucune note en base."); return
        note = st.selectbox("Note", notes)
        try:
            r = matching.contrast(con, note=note)
        except ValueError as e:
            st.error(str(e)); return
    else:
        selected = st.multiselect("Descripteurs de la note à contraster", _descriptors(con))
        if not selected:
            st.write("Choisis au moins un descripteur."); return
        r = matching.contrast(con, descriptors=selected)

    st.caption("Cible d'affinité : " + ", ".join(r["affinity_target"]))
    if not r["ranked"]:
        st.write("Aucun houblon ne recoupe cette cible.")
        return
    st.dataframe(
        [{"Houblon": h["name"], "Score": h["score"],
          "Contraste via": ", ".join(h["contrast_via"]), "Sources": h["sources"]}
         for h in r["ranked"]],
        use_container_width=True, hide_index=True)

    st.subheader("Proposer un blend")
    max_hops = st.slider("Nombre de houblons max", 1, 6, 3)
    if source.startswith("note"):
        blend = matching.contrast_blend(con, note=note, max_hops=max_hops)
    else:
        blend = matching.contrast_blend(con, descriptors=selected, max_hops=max_hops)
    if not blend["blend"]:
        st.write("Aucune combinaison trouvée.")
        return
    st.dataframe(
        [{"Houblon": h["name"], "Couvre": ", ".join(h["covers"]), "Sources": h["sources"]}
         for h in blend["blend"]],
        use_container_width=True, hide_index=True)
    if blend["residual"]:
        st.warning("Non couvert par le blend : " + ", ".join(blend["residual"]))


def _combine(con, note):
    st.sidebar.subheader("Options")
    max_hops = st.sidebar.slider("max_hops (taille du blend)", 1, 6, 3)
    biotransform = st.sidebar.checkbox(
        "--biotransform (fermentation levure standard)", value=False)
    r = matching.combine(con, note, max_hops=max_hops, biotransform=biotransform)

    col1, col2 = st.columns(2)
    col1.metric("Couverture", f"{r['coverage']*100:.0f}%")
    col2.metric("Résidu (distance à la cible)", r["residual"])
    if r["biotransform"]:
        st.info("Hypothèse active : fermentation levure standard "
                "(géraniol→citronellol, linalol→alpha-terpinéol).")
    if r["orphan"]:
        st.warning("Irréductible (aucun houblon ne peut fournir) : "
                   + ", ".join(r["orphan"]))
    if not r["blend"]:
        st.write("Aucune combinaison trouvée.")
        return
    st.dataframe(
        [{"Houblon": h["name"], "Proportion": f"{h['proportion']*100:.1f}%"}
         for h in r["blend"]],
        use_container_width=True, hide_index=True)


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
                    use_container_width=True, hide_index=True)


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

    mode = st.sidebar.radio("Mode", ["amplify", "contrast", "combine", "by-descriptor"])

    if mode == "by-descriptor":
        st.header("Découverte par descripteurs")
        _by_descriptor(con)
        return

    if mode == "contrast":
        st.header("contrast")
        _contrast(con)
        return

    notes = _notes(con)
    if not notes:
        st.error("Aucune note en base."); st.stop()
    note = st.sidebar.selectbox("Note", notes)

    st.header(f"{mode} — {note}")
    if mode == "amplify":
        _amplify(con, note)
    elif mode == "combine":
        _combine(con, note)


if __name__ == "__main__":
    main()
