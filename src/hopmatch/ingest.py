"""
Ingestion des données dans aromahops.db.

RÉEL (tourne ici) :
  - build_from_fixtures : reconstruit la base depuis data/fixtures/{barthhaas,yakima}
  - seed_reference       : charge molécules + amorce note→molécule/descripteur
  - crawl_barthhaas      : moissonne barthhaas.com (réseau ; requests+bs4)

SCAFFOLD (à finir dans TON environnement — voir docstrings et README) :
  - crawl_yakima         : Yakima est un front SPA → extraction DOM à ajuster
  - ingest_foodb         : dump bulk FooDB local (gros fichiers, hors sandbox)
  - ingest_flavornet     : scrape du site statique Flavornet
"""
from __future__ import annotations
import glob
import os
import sqlite3

from . import parsers, reference
from .schema import init_db, validate_and_repair, DROP_COMPOUNDS


# --------------------------------------------------------------------------- #
# Référence (couche note) — amorce
# --------------------------------------------------------------------------- #
def seed_reference(con: sqlite3.Connection) -> None:
    con.executemany("INSERT OR REPLACE INTO molecules VALUES (?,?,?,?)",
                    [(c, o, t, cid) for c, (o, t, cid) in reference.MOLECULES.items()])
    con.executemany("INSERT OR REPLACE INTO aroma_notes VALUES (?,?,?,?)",
                    [(n, m, w, "seed:litt")
                     for n, prof in reference.AROMA_NOTES.items() for m, w in prof.items()])
    con.executemany("INSERT OR REPLACE INTO note_descriptors VALUES (?,?)",
                    [(n, d) for n, ds in reference.NOTE_DESCRIPTORS.items() for d in ds])


# --------------------------------------------------------------------------- #
# Houblon depuis fixtures
# --------------------------------------------------------------------------- #
def _ingest_variety(con, variety, name, region, comp, descriptors, source, repair=True):
    comp = {c: v for c, v in comp.items() if c not in DROP_COMPOUNDS}
    comp, confidence, notes = validate_and_repair(comp, repair=repair)

    row = con.execute("SELECT sources FROM hops WHERE variety=?", (variety,)).fetchone()
    if row:
        srcs = sorted(set(row[0].split(",")) | {source})
        con.execute("UPDATE hops SET sources=? WHERE variety=?", (",".join(srcs), variety))
    else:
        con.execute("INSERT INTO hops VALUES (?,?,?,?)", (variety, name, region, source))

    for compound, (vmin, vmax, unit) in comp.items():
        con.execute("INSERT OR REPLACE INTO hop_composition VALUES (?,?,?,?,?,?,?,?)",
                    (variety, compound, vmin, vmax, unit, source, confidence, "; ".join(notes)))
    for d in descriptors:
        con.execute("INSERT OR REPLACE INTO hop_descriptors VALUES (?,?,?)", (variety, d, source))
    return confidence


def build_from_fixtures(fixture_root: str, out_db: str) -> None:
    from .schema import connect
    con = connect(out_db)
    init_db(con)
    seed_reference(con)
    stats = {"ok": 0, "repaired": 0, "suspect": 0}
    for source, labels in parsers.LABELS_BY_SOURCE.items():
        for path in sorted(glob.glob(os.path.join(fixture_root, source, "*.txt"))):
            variety = os.path.splitext(os.path.basename(path))[0]
            text = open(path, encoding="utf-8").read()
            comp = parsers.parse_composition(text, labels)
            desc = parsers.parse_descriptors(text)
            conf = _ingest_variety(con, variety, variety.capitalize(),
                                   parsers.parse_region(text), comp, desc, source)
            stats[conf] += 1
    con.commit()
    _summary(con, stats)
    con.close()


def _summary(con, stats):
    nh = con.execute("SELECT COUNT(*) FROM hops").fetchone()[0]
    nm = con.execute("SELECT COUNT(*) FROM hop_composition").fetchone()[0]
    print(f"Base : {nh} houblons, {nm} mesures "
          f"(ok={stats['ok']} repaired={stats['repaired']} suspect={stats['suspect']}).")
    multi = con.execute("SELECT variety, sources FROM hops WHERE sources LIKE '%,%'").fetchall()
    if multi:
        print("Multi-sources :", ", ".join(f"{v}[{s}]" for v, s in multi))


# --------------------------------------------------------------------------- #
# Crawl BarthHaas (réseau réel)
# --------------------------------------------------------------------------- #
def crawl_barthhaas(out_db: str, sleep: float = 1.5, limit: int | None = None) -> None:
    import time, re, requests
    from bs4 import BeautifulSoup
    from .schema import connect
    BASE = "https://www.barthhaas.com"
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con)
    ov = requests.get(f"{BASE}/hops-and-products/hop-varieties-overview",
                      timeout=30, headers={"User-Agent": "hopmatch/0.1 (research)"}).text
    seen, slugs = set(), []
    for url, slug in re.findall(r'href="([^"]*?/hops-and-products/hops/([^"/]+))"', ov):
        if slug not in seen:
            seen.add(slug)
            slugs.append((slug, url if url.startswith("http") else BASE + url))
    if limit:
        slugs = slugs[:limit]
    print(f"BarthHaas : {len(slugs)} variétés")
    for slug, url in slugs:
        try:
            html = requests.get(url, timeout=30,
                                headers={"User-Agent": "hopmatch/0.1 (research)"}).text
            text = BeautifulSoup(html, "html.parser").get_text("\n")
            comp = parsers.parse_composition(text, parsers.BARTHHAAS_LABELS)
            if comp:
                _ingest_variety(con, slug, slug.replace("-", " ").title(),
                                parsers.parse_region(text), comp,
                                parsers.parse_descriptors(text), "barthhaas")
                print(f"  ok {slug} ({len(comp)})")
        except Exception as e:  # noqa
            print(f"  !! {slug}: {e}")
        time.sleep(sleep)
    con.commit(); con.close()


# --------------------------------------------------------------------------- #
# SCAFFOLDS — à compléter dans ton environnement (voir README "Passer à Claude Code")
# --------------------------------------------------------------------------- #
def crawl_yakima(out_db: str, **kw) -> None:
    """
    SCAFFOLD. Yakima Chief (yakimachief.com/variety/{slug}) rend les valeurs dans
    le HTML mais via un front type SPA. Étapes à implémenter :
      1. lister les slugs depuis /hop-varieties (ou l'API interne si trouvée) ;
      2. pour chaque page, extraire le bloc 'TYPICAL BREWING VALUES' + 'Aroma Profile'
         via sélecteurs BeautifulSoup (les valeurs sont dans des éléments distincts) ;
      3. passer le texte extrait à parsers.parse_composition(text, YAKIMA_LABELS)
         et parsers.parse_descriptors(text), puis _ingest_variety(..., 'yakima').
    Si requests ne renvoie qu'un shell JS : basculer sur playwright (headless).
    """
    raise NotImplementedError(
        "crawl_yakima : scaffold — voir docstring et README (tâche Claude Code).")


def ingest_foodb(out_db: str, foodb_csv_dir: str, **kw) -> None:
    """
    SCAFFOLD. Remplace l'amorce note→molécule par le dump bulk FooDB (foodb.ca).
    Étapes :
      1. lire Food.csv, Compound.csv, Content.csv (gros → lecture par chunks) ;
      2. pour un aliment, récupérer ses composés ; joindre au seuil (FlavorDB2)
         et à Flavornet (odeur-actif) via PubChem CID / InChIKey ;
      3. pondérer par prior de seuil (1/seuil), PAS un OAV (pas de concentration
         fiable — cf. tools/audit_foodb.py) ; écrire dans aroma_notes.
    Hors sandbox car les fichiers FooDB sont volumineux et locaux.
    """
    raise NotImplementedError(
        "ingest_foodb : scaffold — voir tools/audit_foodb.py et README (tâche Claude Code).")


def ingest_flavornet(out_db: str, **kw) -> None:
    """
    SCAFFOLD. Flavornet (flavornet.org) : ~738 composés odeur-actifs (GC-O) avec
    descripteur + CAS. Site HTML statique → scrape simple. Sert de whitelist
    'sensoriellement présent' pour filtrer les molécules muettes.
    """
    raise NotImplementedError(
        "ingest_flavornet : scaffold — voir README (tâche Claude Code).")
