"""CLI hopmatch : construire la base et interroger les modes (amplify/contrast/by-descriptor)."""
from __future__ import annotations
import argparse
import os

from . import ingest, matching
from .schema import connect

DEFAULT_DB = "aromahops.db"
FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fixtures")


def _split_descriptors(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def _print_amplify(r):
    print(f"\n[AMPLIFY] {r['note']}  — couverture moléculaire {r['coverage']*100:.0f}%")
    if r.get("use_oav"):
        print("  (--oav actif : molécules à seuil olfactif bas pondérées plus fort, "
              "prior de puissance approximatif — pas une mesure de concentration réelle)")
    if not r.get("has_descriptors", True):
        print("  (pas de descripteurs pour cette note : score 100% moléculaire)")
    if r["coverage"] < matching.LOW_COVERAGE_WARNING_THRESHOLD:
        print(f"  ATTENTION : couverture moléculaire faible ({r['coverage']*100:.0f}%) — "
              "le classement moléculaire seul risque d'être dominé par une seule molécule "
              "commune à beaucoup d'aliments, pas par la signature propre de cette note "
              "(chimie de l'huile de houblon peu recoupante, voir CLAUDE.md). Ajoutez le "
              "plus de descripteurs possible (--descriptors) pour un résultat plus fiable.")
    if r["orphan"]:
        print("  orphelines (ajout requis) :", ", ".join(r["orphan"]))
    for i, h in enumerate(r["ranked"], 1):
        print(f"  {i:<2}{h['name']:<14}{h['score']:>6}  (mol {h['mol']} / desc {h['desc']})"
              f"  {', '.join(h['why'])}  [{h['sources']}]")


def _print_contrast(r):
    print(f"\n[CONTRAST] {r['note']}  — cible d'affinité : {', '.join(r['affinity_target'])}")
    if r.get("unmapped"):
        print("  (pas de carte d'affinité pour :", ", ".join(r["unmapped"]),
             "— ignorés, pas d'effet sur la cible)")
    for i, h in enumerate(r["ranked"], 1):
        print(f"  {i:<2}{h['name']:<14}{h['score']:>6}  via {', '.join(h['contrast_via'])}")


def _print_blends(blends):
    if not blends:
        print("  aucune combinaison trouvée.")
        return
    for b in blends:
        print(f"  -- taille {b['size']} --")
        for h in b["hops"]:
            via = {"top": "meilleur candidat", "pairing": "pairing BeerMaverick réel",
                  "coverage": "repli couverture, pas de donnée BeerMaverick",
                  "relevance": "houblon pertinent en plus, rien de neuf à couvrir"}[h["via"]]
            print(f"    {h['name']:<14}couvre {', '.join(h['covers']) or '(rien de nouveau)'}"
                 f"  [{via}]")
        if b["residual"]:
            print("    non couvert :", ", ".join(b["residual"]))


def _print_contrast_blend(r):
    print(f"\n[CONTRAST-BLEND] {r['note']}  — cible d'affinité : {', '.join(r['affinity_target'])}")
    if r.get("unmapped"):
        print("  (pas de carte d'affinité pour :", ", ".join(r["unmapped"]),
             "— ignorés, pas d'effet sur la cible)")
    _print_blends(r["blends"])


def _print_amplify_blend(r):
    print(f"\n[AMPLIFY-BLEND] {r['note']}")
    if not r["has_descriptors"]:
        print("  pas de descripteurs pour cette note : aucun blend possible "
             "(voir --descriptors).")
        return
    print(f"  cible descripteurs : {', '.join(r['target_descriptors'])}")
    _print_blends(r["blends"])


def _print_by_descriptor(ranked, selected):
    print(f"\n[BY-DESCRIPTOR] {', '.join(selected)}")
    if not ranked:
        print("  aucun houblon ne recoupe ces descripteurs.")
    for i, h in enumerate(ranked, 1):
        print(f"  {i:<2}{h['name']:<14}recoupe {', '.join(h['matched_descriptors'])}"
              f"  (tous : {', '.join(h['all_descriptors'])})  [{h['sources']}]")
        for c in h["compounds"][:6]:
            print(f"        {c['compound']:<18}{c['mid']:.2f} {c['unit']}"
                  f"  ({', '.join(c['sources'])})")


def main(argv=None):
    p = argparse.ArgumentParser(prog="hopmatch")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="construire la base depuis les fixtures")
    b.add_argument("--fixtures", default=FIXTURES)
    b.add_argument("--db", default=DEFAULT_DB)

    c = sub.add_parser("crawl-barthhaas", help="moissonner barthhaas.com")
    c.add_argument("--db", default=DEFAULT_DB)
    c.add_argument("--limit", type=int)

    cy = sub.add_parser("crawl-yakima", help="moissonner yakimachief.com (via son index Algolia)")
    cy.add_argument("--db", default=DEFAULT_DB)
    cy.add_argument("--limit", type=int)

    fn = sub.add_parser("ingest-flavornet", help="moissonner flavornet.org (whitelist odeur-active)")
    fn.add_argument("--db", default=DEFAULT_DB)

    pc = sub.add_parser("resolve-pubchem-cids", help="résoudre CAS->CID PubChem (whitelist Flavornet)")
    pc.add_argument("--db", default=DEFAULT_DB)
    pc.add_argument("--sleep", type=float, default=0.25)

    fb = sub.add_parser("ingest-foodb", help="ingérer le dump FooDB (filtré par la whitelist Flavornet) ; "
                                             "téléchargé automatiquement si absent")
    fb.add_argument("foodb_dir", nargs="?", default=None,
                    help="dossier du dump FooDB CSV déjà extrait ; omis = téléchargé "
                         "automatiquement (~950 Mo, licence CC BY-NC-SA non commerciale)")
    fb.add_argument("--db", default=DEFAULT_DB)

    f2 = sub.add_parser("ingest-flavordb2", help="seuils olfactifs FlavorDB2 (bornés à la whitelist Flavornet)")
    f2.add_argument("--db", default=DEFAULT_DB)
    f2.add_argument("--sleep", type=float, default=0.3)

    bm = sub.add_parser("ingest-beermaverick",
                        help="moissonner beermaverick.com (pairings/substitutions houblon<->houblon, "
                             "agrégateur — pas une mesure de labo)")
    bm.add_argument("--db", default=DEFAULT_DB)
    bm.add_argument("--sleep", type=float, default=1.0)
    bm.add_argument("--limit", type=int)

    am = sub.add_parser("amplify", help="cas d'usage : amplify")
    am.add_argument("note")
    am.add_argument("--db", default=DEFAULT_DB)
    am.add_argument("--oav", action="store_true",
                    help="pondère chaque molécule par un prior de puissance olfactive "
                         "(1/seuil connu, ~14 molécules d'huile de houblon courantes — "
                         "myrcène, géraniol, thiols... ; les autres molécules ne sont pas "
                         "affectées). Approximatif : pas une mesure de concentration "
                         "réelle (aucune donnée de concentration fiable ne l'alimente), "
                         "juste une correction pour qu'une molécule très odorante à faible "
                         "seuil ne soit pas éclipsée par une molécule ubiquitaire mais peu "
                         "odorante. Change le classement sur ~1 note sur 6 (mesuré).")
    am.add_argument("--descriptors",
                    help="active la couche descripteurs pour cette note (vide par "
                         "défaut, pas d'amorce littérature) : sélection manuelle sur "
                         "le vocabulaire réel — voir `hopmatch descriptors` — séparés "
                         "par virgule, ex: herbal,woody")

    amb = sub.add_parser("amplify-blend",
                         help="cas d'usage : amplify, blends de taille croissante "
                              "(1-5, priorité fréquence réelle BeerMaverick)")
    amb.add_argument("note")
    amb.add_argument("--db", default=DEFAULT_DB)
    amb.add_argument("--oav", action="store_true")
    amb.add_argument("--descriptors",
                     help="cible du blend (vocabulaire réel, comme amplify) — requis en "
                          "pratique, un blend n'a rien à couvrir sans descripteurs")
    amb.add_argument("--max-hops", type=int, default=5)

    for name in ("contrast", "contrast-blend"):
        s = sub.add_parser(name, help="cas d'usage : contraster"
                                     + (" (blends de taille croissante)" if "blend" in name else ""))
        s.add_argument("note", nargs="?", default=None,
                       help="note avec note_descriptors déjà peuplé ; omis si --descriptors fourni")
        s.add_argument("--descriptors",
                       help="sélection manuelle de descripteurs séparés par virgule (contourne "
                            "note_descriptors, généralise à toute note — voir `hopmatch descriptors`), "
                            "ex: citrus,tropical")
        s.add_argument("--db", default=DEFAULT_DB)
        if name == "contrast-blend":
            s.add_argument("--max-hops", type=int, default=5,
                           help="1-5 : houblons choisis par fréquence réelle de pairing "
                                "BeerMaverick en priorité, repli couverture si aucune "
                                "donnée réelle (voir matching._pairing_grown_blends)")

    lst = sub.add_parser("list", help="lister notes et houblons")
    lst.add_argument("--db", default=DEFAULT_DB)

    ds = sub.add_parser("descriptors", help="lister le vocabulaire de descripteurs disponible")
    ds.add_argument("--db", default=DEFAULT_DB)

    bd = sub.add_parser("by-descriptor", help="houblons recoupant des descripteurs choisis (découverte)")
    bd.add_argument("descriptors", help="descripteurs séparés par virgule, ex: citrus,tropical")
    bd.add_argument("--db", default=DEFAULT_DB)
    bd.add_argument("--top", type=int, default=10)

    a = p.parse_args(argv)

    if a.cmd == "build":
        ingest.build_from_fixtures(a.fixtures, a.db); return 0
    if a.cmd == "crawl-barthhaas":
        ingest.crawl_barthhaas(a.db, limit=a.limit); return 0
    if a.cmd == "crawl-yakima":
        ingest.crawl_yakima(a.db, limit=a.limit); return 0
    if a.cmd == "ingest-flavornet":
        ingest.ingest_flavornet(a.db); return 0
    if a.cmd == "resolve-pubchem-cids":
        ingest.resolve_pubchem_cids(a.db, sleep=a.sleep); return 0
    if a.cmd == "ingest-foodb":
        ingest.ingest_foodb(a.db, a.foodb_dir); return 0
    if a.cmd == "ingest-flavordb2":
        ingest.ingest_flavordb2(a.db, sleep=a.sleep); return 0
    if a.cmd == "ingest-beermaverick":
        ingest.ingest_beermaverick(a.db, limit=a.limit, sleep=a.sleep); return 0

    con = connect(a.db)
    try:
        if a.cmd == "list":
            notes = [r[0] for r in con.execute("SELECT DISTINCT note FROM aroma_notes")]
            hops = [r[0] for r in con.execute("SELECT name FROM hops")]
            print("Notes :", ", ".join(sorted(notes)))
            print("Houblons :", ", ".join(sorted(hops)))
        elif a.cmd == "amplify":
            descriptors = _split_descriptors(a.descriptors)
            _print_amplify(matching.amplify(con, a.note.lower(), use_oav=a.oav,
                                            descriptors=descriptors))
        elif a.cmd == "amplify-blend":
            descriptors = _split_descriptors(a.descriptors)
            _print_amplify_blend(matching.amplify_blend(
                con, a.note.lower(), use_oav=a.oav, descriptors=descriptors,
                max_hops=a.max_hops))
        elif a.cmd in ("contrast", "contrast-blend"):
            descriptors = _split_descriptors(a.descriptors)
            note = a.note.lower() if a.note else None
            if a.cmd == "contrast":
                _print_contrast(matching.contrast(con, note, descriptors))
            else:
                _print_contrast_blend(matching.contrast_blend(
                    con, note, descriptors, max_hops=a.max_hops))
        elif a.cmd == "descriptors":
            ds = [r[0] for r in con.execute("SELECT DISTINCT descriptor FROM hop_descriptors")]
            print("Descripteurs :", ", ".join(sorted(ds)))
        elif a.cmd == "by-descriptor":
            selected = [d.strip().lower() for d in a.descriptors.split(",") if d.strip()]
            _print_by_descriptor(matching.by_descriptor(con, selected, top=a.top), selected)
    except (KeyError, ValueError) as e:
        print(e); return 1
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
