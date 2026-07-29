"""
Ingestion des données dans aromahops.db.

RÉEL (tourne ici) :
  - build_from_fixtures : reconstruit la base depuis data/fixtures/{barthhaas,yakima}
  - seed_reference       : charge molécules + amorce note→molécule/descripteur
  - crawl_barthhaas      : moissonne barthhaas.com (réseau ; requests+bs4)
  - ingest_flavornet     : moissonne flavornet.org (réseau ; requests+bs4)
  - ingest_foodb         : ingère un dump bulk FooDB local, filtré par la whitelist
                           Flavornet (nécessite ingest_flavornet au préalable)

SCAFFOLD (à finir dans TON environnement — voir docstrings et README) :
  - crawl_yakima         : Yakima est un front SPA → extraction DOM à ajuster
"""
from __future__ import annotations
import glob
import os
import re
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
        d = reference.DESCRIPTOR_ALIASES.get(d, d)
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
# Flavornet (réseau réel) — whitelist odeur-active, pour filtrer FooDB
# --------------------------------------------------------------------------- #
def ingest_flavornet(out_db: str, timeout: float = 30.0) -> None:
    """
    Flavornet (flavornet.org) : ~738 composés odeur-actifs (GC-O), triés par indice
    de Kovats sur une page HTML statique unique (pas de pagination). Sert de
    whitelist 'sensoriellement présent' pour filtrer FooDB (ingest_foodb) — ne
    touche pas à la couche `molecules` utilisée par le matching note->houblon.
    """
    import requests
    from .schema import connect
    URL = "http://www.flavornet.org/d_kovats_ov101.html"
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con)
    html = requests.get(URL, timeout=timeout,
                        headers={"User-Agent": "hopmatch/0.1 (research)"}).text
    rows = parsers.parse_flavornet(html)
    con.executemany(
        "INSERT OR REPLACE INTO flavornet_compounds VALUES (?,?,?)",
        [(cas, compound, ", ".join(descriptors)) for cas, compound, descriptors in rows])
    con.commit()
    n = con.execute("SELECT COUNT(*) FROM flavornet_compounds").fetchone()[0]
    con.close()
    dupes = len(rows) - n
    msg = f"Flavornet : {n} composés odeur-actifs (CAS uniques) ingérés"
    print(msg + (f", {dupes} doublons CAS fusionnés." if dupes else "."))


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


def _find_csv(folder: str, name: str) -> str:
    hits = glob.glob(os.path.join(folder, f"{name}.csv")) + \
           glob.glob(os.path.join(folder, f"{name.capitalize()}.csv"))
    if not hits:
        raise FileNotFoundError(f"{name}.csv introuvable dans {folder}")
    return hits[0]


_CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
_GREEK_PREFIX_RE = re.compile(r"^(?:alpha|beta|gamma|delta|α|β|γ|δ)[-\s]*", re.I)
_KNOWN_HOP_COMPOUNDS = ({c for c, _ in parsers.BARTHHAAS_LABELS.values()} |
                        {c for c, _ in parsers.YAKIMA_LABELS.values()} |
                        set(reference.MOLECULES) | set(reference.ALIASES.values())) - DROP_COMPOUNDS


def _canonical_compound(name: str) -> str:
    """
    Aligne un nom de composé Flavornet/FooDB sur le vocabulaire houblon existant,
    pour éviter deux pièges d'honnêteté (coverage/orphan) :
      1. synonymes explicites connus (reference.ALIASES, ex. estragole/methyl-
         chavicol, même CAS 140-67-0) — sinon la même molécule apparaît deux fois
         dans aroma_notes (une fois via l'amorce, une fois via FooDB) et est
         double-comptée ;
      2. préfixe grec (β-caryophyllene, α-humulene) que le vocabulaire houblon
         (parsers.BARTHHAAS_LABELS etc.) n'utilise pas (caryophyllene, humulene) —
         sinon la molécule devient une ORPHELINE artificielle alors que le houblon
         la fournit bien, sous son nom simple.
    On ne renomme que vers une forme reconnue ; sinon le nom Flavornet est gardé tel quel.
    """
    name = reference.ALIASES.get(name, name)
    stripped = _GREEK_PREFIX_RE.sub("", name).strip()
    return stripped if stripped != name and stripped in _KNOWN_HOP_COMPOUNDS else name


def _resolve_cas_column(cdf) -> str:
    """
    Détecte la colonne CAS réelle par taux de correspondance au format CAS
    (\\d-\\d-\\d), plutôt que de supposer 'cas_number' fiable. Nécessaire : sur le
    dump foodb 2020-04-07, la colonne 'cas_number' de Compound.csv contient en
    fait des SMILES (ex. Linalool -> 'CC(C)=CCCC(C)(O)C=C') et le vrai CAS
    ('78-70-6') est décalé sous 'description' — bug d'export en amont, vérifié
    sur ~15000/70000 lignes. Filet défensif générique si un futur dump est propre.
    """
    best_col, best_hits = "cas_number", -1
    for col in cdf.columns:
        if col == "id":
            continue
        hits = cdf[col].astype(str).str.strip().str.match(_CAS_RE).sum()
        if hits > best_hits:
            best_col, best_hits = col, hits
    return best_col


def _tier_weight(mass, thr, conc_max, thr_max):
    """
    Poids en 3 paliers disjoints, du plus au moins fiable — pas de mélange
    d'unités (mg/100g vs 1/seuil_ppb ne sont pas comparables) :
      (0.67, 1.0]  concentration fiable (mg/100g), classée par magnitude relative
      (0.33, 0.67] pas de concentration mais seuil olfactif connu (prior de puissance)
      0.15         présence seule (ni concentration ni seuil)
    """
    if mass is not None and mass > 0:
        return 0.67 + 0.33 * (mass / conc_max if conc_max else 1.0)
    if thr:
        return 0.33 + 0.34 * ((1.0 / thr) / thr_max if thr_max else 1.0)
    return 0.15


def ingest_foodb(out_db: str, foodb_csv_dir: str,
                 notes: dict[str, str] | None = None, chunksize: int = 300_000) -> None:
    """
    Remplace/enrichit l'amorce note->molécule par le dump bulk FooDB (foodb.ca),
    FILTRÉ via la whitelist Flavornet (ingest_flavornet doit avoir tourné avant :
    sinon >90% des ~6000 composés/aliment sont du bruit nutritionnel, cf. CLAUDE.md
    et tools/audit_foodb.py).

    `notes` : {note: nom Food.csv} à ingérer, défaut reference.NOTE_TO_FOODB (les
    seules correspondances propres identifiées sur le dump 2020-04-07 ; yuzu/rose/
    pin-resine restent volontairement hors mapping, voir le commentaire associé).

    FUSIONNE avec l'amorce existante par (note, molécule) au lieu de l'effacer :
    FooDB est lacunaire (14-16% des liens ont une concentration, cf. audit) et peut
    rater des composés-signature que l'amorce littérature connaît. Écraser l'amorce
    perdrait cette information ; on ne remplace donc que les molécules que FooDB
    fournit réellement, molécule par molécule (voir aussi _canonical_compound : les
    synonymes/préfixes grecs Flavornet sont réalignés sur le vocabulaire houblon
    existant, pour fusionner plutôt que dupliquer une même molécule sous deux noms).

    Poids : concentration (mg/100g, familles d'unités comparables uniquement, cf.
    parsers.mass_mg_per_100g) là où elle existe, sinon prior de seuil (1/seuil_ppb,
    depuis les seuils déjà connus dans `molecules`), sinon présence pure. Jamais
    d'OAV (pas de concentration fiable pour la majorité des composés).
    """
    import pandas as pd
    from .schema import connect

    notes = notes or reference.NOTE_TO_FOODB
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con)

    flavornet = {r["cas"]: (_canonical_compound(r["compound"]), r["descriptors"])
                for r in con.execute("SELECT cas, compound, descriptors FROM flavornet_compounds")}
    if not flavornet:
        con.close()
        raise RuntimeError(
            "flavornet_compounds est vide : lancer ingest_flavornet avant ingest_foodb "
            "(whitelist odeur-active requise pour filtrer FooDB).")
    whitelist = {cas: compound for cas, (compound, _) in flavornet.items()}
    odor_by_compound = {compound: desc for compound, desc in flavornet.values()}
    thresholds = {r["compound"]: r["threshold_ppb"] for r in
                 con.execute("SELECT compound, threshold_ppb FROM molecules "
                             "WHERE threshold_ppb IS NOT NULL")}

    fdf = pd.read_csv(_find_csv(foodb_csv_dir, "food"), usecols=["id", "name"])
    food_id_to_note = {}
    for note, food_name in notes.items():
        m = fdf[fdf["name"].str.lower() == food_name.lower()]
        if m.empty:
            print(f"  !! {note!r} : aliment {food_name!r} introuvable dans Food.csv, ignoré")
            continue
        food_id_to_note[int(m.iloc[0]["id"])] = note
    if not food_id_to_note:
        print("Aucun aliment résolu, rien à ingérer."); con.close(); return

    cdf = pd.read_csv(_find_csv(foodb_csv_dir, "compound"))
    cas_col = _resolve_cas_column(cdf)
    cdf["_cas"] = cdf[cas_col].astype(str).str.strip()
    cdf = cdf[cdf["_cas"].isin(whitelist)]
    compound_id_to_cas = dict(zip(cdf["id"], cdf["_cas"]))
    target_food_ids = set(food_id_to_note)
    target_compound_ids = set(compound_id_to_cas)

    usecols = ["source_type", "food_id", "source_id", "orig_content", "orig_unit"]
    chunks = []
    for chunk in pd.read_csv(_find_csv(foodb_csv_dir, "content"), usecols=usecols,
                             chunksize=chunksize, low_memory=False):
        sub = chunk[(chunk["source_type"].astype(str).str.lower() == "compound") &
                    chunk["food_id"].isin(target_food_ids) &
                    chunk["source_id"].isin(target_compound_ids)]
        if len(sub):
            chunks.append(sub)
    if not chunks:
        print("Aucun composé odeur-actif (whitelist Flavornet) trouvé pour ces aliments.")
        con.close(); return
    content = pd.concat(chunks, ignore_index=True)
    content["mass"] = [parsers.mass_mg_per_100g(v, u) for v, u in
                       zip(content["orig_content"], content["orig_unit"])]
    best = content.groupby(["food_id", "source_id"])["mass"].max().reset_index()

    written, no_hit = 0, []
    for food_id, note in food_id_to_note.items():
        sub = best[best["food_id"] == food_id]
        if sub.empty:
            no_hit.append(note); continue
        recs = []
        for _, r in sub.iterrows():
            cas = compound_id_to_cas[r["source_id"]]
            compound = whitelist[cas]
            recs.append((compound, r["mass"] if pd.notna(r["mass"]) else None,
                        thresholds.get(compound)))
        conc_max = max((m for _, m, _ in recs if m is not None), default=0.0)
        thr_max = max((1.0 / t for _, _, t in recs if t), default=0.0)
        for compound, mass, thr in recs:
            w = _tier_weight(mass, thr, conc_max, thr_max)
            tier = "conc" if (mass and mass > 0) else ("thr" if thr else "presence")
            con.execute("INSERT OR REPLACE INTO aroma_notes VALUES (?,?,?,?)",
                        (note, compound, round(w, 3), f"foodb:{tier}"))
            con.execute("INSERT OR IGNORE INTO molecules VALUES (?,?,?,?)",
                        (compound, odor_by_compound.get(compound), None, None))
            written += 1
    con.commit(); con.close()
    print(f"FooDB : {written} liens note->molécule ingérés sur {len(food_id_to_note)} aliments.")
    if no_hit:
        print("  aucun composé whitelisté pour :", ", ".join(no_hit))
