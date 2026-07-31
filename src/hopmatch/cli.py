"""CLI hopmatch : construire la base et interroger les trois modes."""
from __future__ import annotations
import argparse
import os

from . import ingest, matching
from .schema import connect

DEFAULT_DB = "aromahops.db"
FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "data", "fixtures")


def _print_amplify(r):
    print(f"\n[AMPLIFY] {r['note']}  — couverture moléculaire {r['coverage']*100:.0f}%")
    if r.get("biotransform"):
        print("  (hypothèse : fermentation levure standard, géraniol->citronellol)")
    if not r.get("has_descriptors", True):
        print("  (pas de descripteurs pour cette note : score 100% moléculaire)")
    if r["orphan"]:
        print("  orphelines (ajout requis) :", ", ".join(r["orphan"]))
    for i, h in enumerate(r["ranked"], 1):
        print(f"  {i:<2}{h['name']:<14}{h['score']:>6}  (mol {h['mol']} / desc {h['desc']})"
              f"  {', '.join(h['why'])}  [{h['sources']}]")


def _print_contrast(r):
    print(f"\n[CONTRAST] {r['note']}  — cible d'affinité : {', '.join(r['affinity_target'])}")
    for i, h in enumerate(r["ranked"], 1):
        print(f"  {i:<2}{h['name']:<14}{h['score']:>6}  via {', '.join(h['contrast_via'])}")


def _print_contrast_blend(r):
    print(f"\n[CONTRAST-BLEND] {r['note']}  — cible d'affinité : {', '.join(r['affinity_target'])}")
    if not r["blend"]:
        print("  aucune combinaison trouvée.")
    for h in r["blend"]:
        print(f"  {h['name']:<14}couvre {', '.join(h['covers'])}")
    if r["residual"]:
        print("  non couvert :", ", ".join(r["residual"]))


def _print_combine(r):
    print(f"\n[COMBINE] {r['note']}  — couverture {r['coverage']*100:.0f}% "
          f"| résidu {r['residual']}")
    if r.get("biotransform"):
        print("  (hypothèse : fermentation levure standard, géraniol->citronellol)")
    if not r["blend"]:
        print("  aucune combinaison trouvée.");
    for h in r["blend"]:
        print(f"  {h['proportion']*100:5.1f}%  {h['name']}")
    if r["orphan"]:
        print("  irréductible (aucun houblon ne fournit) :", ", ".join(r["orphan"]))


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

    for name in ("amplify", "combine"):
        s = sub.add_parser(name, help=f"cas d'usage : {name}")
        s.add_argument("note")
        s.add_argument("--db", default=DEFAULT_DB)
        if name == "amplify":
            s.add_argument("--oav", action="store_true", help="prior de seuil (approx.)")
        if name == "combine":
            s.add_argument("--max-hops", type=int, default=3)
        s.add_argument("--biotransform", action="store_true",
                       help="suppose une fermentation levure standard "
                            "(géraniol->citronellol, portée limitée)")

    for name in ("contrast", "contrast-blend"):
        s = sub.add_parser(name, help="cas d'usage : contraster"
                                     + (" (combinaison parcimonieuse)" if "blend" in name else ""))
        s.add_argument("note", nargs="?", default=None,
                       help="note avec note_descriptors déjà peuplé ; omis si --descriptors fourni")
        s.add_argument("--descriptors",
                       help="sélection manuelle de descripteurs séparés par virgule (contourne "
                            "note_descriptors, généralise à toute note — voir `hopmatch descriptors`), "
                            "ex: citrus,tropical")
        s.add_argument("--db", default=DEFAULT_DB)
        if name == "contrast-blend":
            s.add_argument("--max-hops", type=int, default=3)

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

    con = connect(a.db)
    try:
        if a.cmd == "list":
            notes = [r[0] for r in con.execute("SELECT DISTINCT note FROM aroma_notes")]
            hops = [r[0] for r in con.execute("SELECT name FROM hops")]
            print("Notes :", ", ".join(sorted(notes)))
            print("Houblons :", ", ".join(sorted(hops)))
        elif a.cmd == "amplify":
            _print_amplify(matching.amplify(con, a.note.lower(), use_oav=a.oav,
                                            biotransform=a.biotransform))
        elif a.cmd in ("contrast", "contrast-blend"):
            descriptors = ([d.strip().lower() for d in a.descriptors.split(",") if d.strip()]
                          if a.descriptors else None)
            note = a.note.lower() if a.note else None
            if a.cmd == "contrast":
                _print_contrast(matching.contrast(con, note, descriptors))
            else:
                _print_contrast_blend(matching.contrast_blend(
                    con, note, descriptors, max_hops=a.max_hops))
        elif a.cmd == "combine":
            _print_combine(matching.combine(con, a.note.lower(), max_hops=a.max_hops,
                                            biotransform=a.biotransform))
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
