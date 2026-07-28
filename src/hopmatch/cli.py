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
    if r["orphan"]:
        print("  orphelines (ajout requis) :", ", ".join(r["orphan"]))
    for i, h in enumerate(r["ranked"], 1):
        print(f"  {i:<2}{h['name']:<14}{h['score']:>6}  (mol {h['mol']} / desc {h['desc']})"
              f"  {', '.join(h['why'])}  [{h['sources']}]")


def _print_contrast(r):
    print(f"\n[CONTRAST] {r['note']}  — cible d'affinité : {', '.join(r['affinity_target'])}")
    for i, h in enumerate(r["ranked"], 1):
        print(f"  {i:<2}{h['name']:<14}{h['score']:>6}  via {', '.join(h['contrast_via'])}")


def _print_combine(r):
    print(f"\n[COMBINE] {r['note']}  — couverture {r['coverage']*100:.0f}% "
          f"| résidu {r['residual']}")
    if not r["blend"]:
        print("  aucune combinaison trouvée."); 
    for h in r["blend"]:
        print(f"  {h['proportion']*100:5.1f}%  {h['name']}")
    if r["orphan"]:
        print("  irréductible (aucun houblon ne fournit) :", ", ".join(r["orphan"]))


def main(argv=None):
    p = argparse.ArgumentParser(prog="hopmatch")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="construire la base depuis les fixtures")
    b.add_argument("--fixtures", default=FIXTURES)
    b.add_argument("--db", default=DEFAULT_DB)

    c = sub.add_parser("crawl-barthhaas", help="moissonner barthhaas.com")
    c.add_argument("--db", default=DEFAULT_DB)
    c.add_argument("--limit", type=int)

    for name in ("amplify", "contrast", "combine"):
        s = sub.add_parser(name, help=f"cas d'usage : {name}")
        s.add_argument("note")
        s.add_argument("--db", default=DEFAULT_DB)
        if name == "amplify":
            s.add_argument("--oav", action="store_true", help="prior de seuil (approx.)")
        if name == "combine":
            s.add_argument("--max-hops", type=int, default=3)

    lst = sub.add_parser("list", help="lister notes et houblons")
    lst.add_argument("--db", default=DEFAULT_DB)

    a = p.parse_args(argv)

    if a.cmd == "build":
        ingest.build_from_fixtures(a.fixtures, a.db); return 0
    if a.cmd == "crawl-barthhaas":
        ingest.crawl_barthhaas(a.db, limit=a.limit); return 0

    con = connect(a.db)
    try:
        if a.cmd == "list":
            notes = [r[0] for r in con.execute("SELECT DISTINCT note FROM aroma_notes")]
            hops = [r[0] for r in con.execute("SELECT name FROM hops")]
            print("Notes :", ", ".join(sorted(notes)))
            print("Houblons :", ", ".join(sorted(hops)))
        elif a.cmd == "amplify":
            _print_amplify(matching.amplify(con, a.note.lower(), use_oav=a.oav))
        elif a.cmd == "contrast":
            _print_contrast(matching.contrast(con, a.note.lower()))
        elif a.cmd == "combine":
            _print_combine(matching.combine(con, a.note.lower(), max_hops=a.max_hops))
    except KeyError as e:
        print(e); return 1
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
