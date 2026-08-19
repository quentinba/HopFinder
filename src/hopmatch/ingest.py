"""
Ingestion des données dans aromahops.db.

RÉEL (tourne ici) :
  - build_from_fixtures : reconstruit la base depuis data/fixtures/{barthhaas,yakima}
  - seed_reference       : charge molécules + amorce note→molécule/descripteur
  - crawl_barthhaas      : moissonne barthhaas.com (réseau ; requests+bs4)
  - ingest_flavornet     : moissonne flavornet.org (réseau ; requests+bs4)
  - resolve_pubchem_cids : résout CAS->CID PubChem pour la whitelist Flavornet (réseau ;
                           requests), le "liant" structural entre les 3 mondes
  - download_foodb_dump  : télécharge+extrait le dump bulk FooDB si absent localement
                           (réseau ; requests ; appelé automatiquement par ingest_foodb)
  - ingest_foodb         : ingère un dump bulk FooDB local (le télécharge si besoin),
                           filtré par la whitelist Flavornet (nécessite ingest_flavornet
                           au préalable)
  - ingest_flavordb2     : moissonne cosylab.iiitd.edu.in/flavordb2 (réseau ; requests+bs4),
                           seuils olfactifs bornés à la whitelist Flavornet, accès direct
                           par CID si resolve_pubchem_cids a tourné
  - crawl_yakima         : moissonne yakimachief.com via son index Algolia (réseau ;
                           requests seul, pas de navigateur — voir docstring) — écrit
                           aussi hop_similar (variétés similaires curées par YCH)
  - ingest_beermaverick  : moissonne beermaverick.com (réseau ; requests, HTML statique,
                           pas de navigateur), pairings/substitutions houblon<->houblon
                           (agrégateur, pas une mesure de labo — voir docstring)
"""
from __future__ import annotations
import glob
import os
import re
import sqlite3

from . import parsers, reference
from .schema import init_db, validate_and_repair, DROP_COMPOUNDS


# --------------------------------------------------------------------------- #
# Référence (couche molécule/descripteur — pas de notes, voir reference.py)
# --------------------------------------------------------------------------- #
def seed_reference(con: sqlite3.Connection) -> None:
    """Charge les propriétés molécule (reference.MOLECULES : odeur/seuil/CID).
    Ne seed plus aucune note : toutes les notes viennent d'ingest_foodb."""
    con.executemany("INSERT OR REPLACE INTO molecules VALUES (?,?,?,?)",
                    [(c, o, t, cid) for c, (o, t, cid) in reference.MOLECULES.items()])


# --------------------------------------------------------------------------- #
# Houblon depuis fixtures
# --------------------------------------------------------------------------- #
def _ingest_variety(con, variety, name, region, comp, descriptors, source, repair=True,
                    aroma_intensity=None):
    comp = {c: v for c, v in comp.items() if c not in DROP_COMPOUNDS}
    comp, confidence, notes = validate_and_repair(comp, repair=repair)

    row = con.execute("SELECT sources, name FROM hops WHERE variety=?", (variety,)).fetchone()
    if row:
        existing_sources, existing_name = row
        existing_source_set = set(existing_sources.split(","))
        srcs = sorted(existing_source_set | {source})
        # `name` n'était mis à jour QU'à la création (jamais sur fusion) --
        # bug signalé par l'utilisateur (2026-08-19) : un houblon
        # barthhaas+yakima gardait pour toujours le nom du premier crawl
        # ingéré, ex. "Mosaic® Brand" (Yakima, avec son suffixe marketing
        # "Brand", voir _strip_yakima_brand_suffix) même une fois BarthHaas
        # fusionné, qui a le nom plus propre "Mosaic®" (vérifié en direct
        # sur leur page réelle). Politique : BarthHaas (source primaire,
        # cf. CLAUDE.md) l'emporte toujours sur conflit ; sinon, seule une
        # RÉINGESTION DE LA MÊME SOURCE (`existing_source_set <= {source}`,
        # aucune autre source n'a jamais touché cette variété) peut
        # rafraîchir le nom -- jamais une source secondaire qui écraserait
        # silencieusement un nom déjà posé par une autre source.
        if source == "barthhaas" or existing_source_set <= {source}:
            new_name = name
        else:
            new_name = existing_name
        con.execute("UPDATE hops SET sources=?, name=? WHERE variety=?",
                    (",".join(srcs), new_name, variety))
    else:
        # purpose=NULL à la création : seul ingest_beermaverick le renseigne
        # (via UPDATE, après coup) -- aucune autre source ne l'a.
        con.execute("INSERT INTO hops VALUES (?,?,?,?,?)", (variety, name, region, source, None))

    for compound, (vmin, vmax, unit) in comp.items():
        con.execute("INSERT OR REPLACE INTO hop_composition VALUES (?,?,?,?,?,?,?,?)",
                    (variety, compound, vmin, vmax, unit, source, confidence, "; ".join(notes)))
    for d in descriptors:
        d = reference.DESCRIPTOR_ALIASES.get(d, d)
        con.execute("INSERT OR REPLACE INTO hop_descriptors VALUES (?,?,?)", (variety, d, source))
    # aroma_intensity : optionnel, seule la roue quantitative Yakima (T26
    # backlog) l'alimente pour l'instant — BarthHaas/fixtures n'ont pas cette
    # donnée, pas de valeur inventée en son absence.
    for d, val in (aroma_intensity or {}).items():
        d = reference.DESCRIPTOR_ALIASES.get(d, d)
        con.execute("INSERT OR REPLACE INTO hop_aroma_intensity VALUES (?,?,?,?)",
                    (variety, d, val, source))
    return confidence


# Alias de région pour la réconciliation cross-source (2026-08-19, demande
# utilisateur -- signalé sur "Amarillo" en double dans le sélecteur Browse) :
# BarthHaas et Yakima nomment parfois le même pays différemment ("Great
# Britain" vs "United Kingdom"). Volontairement TRÈS restreint : ne couvre
# QUE les libellés vérifiés en direct sur les paires effectivement dupliquées
# (Challenger/Fuggle/Target) -- ne jamais élargir sans vérifier qu'il s'agit
# bien du même pays, sous peine de fusionner deux crops RÉELLEMENT distincts
# (voir _find_variety_by_name_region ci-dessous pour le cas contraire).
_REGION_ALIASES_FOR_MERGE = {"united kingdom": "great britain"}


def _normalize_region_for_merge(region: str | None) -> str | None:
    if not region:
        return None
    r = region.strip().lower()
    return _REGION_ALIASES_FOR_MERGE.get(r, r)


def _find_variety_by_name_region(con, name: str | None, region: str | None) -> str | None:
    """Résout un doublon cross-source (BarthHaas <-> Yakima) pour la MÊME
    variété dans la MÊME région, quand les deux sources utilisent des slugs
    différents pour le même houblon (ex. BarthHaas 'wye-challenger' vs
    Yakima 'challenger', tous deux "Challenger"/Royaume-Uni) -- root cause
    vérifiée en direct : aucun mécanisme de réconciliation cross-source
    n'existait au-delà du slug exact/dépréfixage marque, contrairement à la
    résolution BeerMaverick (`_resolve_hop_variety`). 5 paires concernées,
    trouvées en auditant `hops` pour des `name` strictement identiques après
    ingestion réelle : Challenger, Fuggle, Hallertauer Tradition, Hersbrucker
    Spät, Target -- toutes MÊME nom ET MÊME région (à l'alias GB/UK près).

    NE fusionne PAS Amarillo/Perle/Saaz/Northern Brewer malgré un nom
    identique : vérifié en direct sur l'API Algolia Yakima (imported_fields
    country_code + cultivar) que ce sont deux CROPS RÉELLEMENT distincts du
    même cultivar, cultivés dans des pays différents (ex. Amarillo VGXP01
    US **et** Allemagne) -- même famille de cas que Perle US/Allemagne ou
    Saaz US/Tchéquie, déjà volontairement gardés séparés. La correspondance
    stricte sur la RÉGION (pas seulement le nom) est donc la garantie
    explicite de ne jamais fusionner deux régions différentes -- si la
    région ne correspond pas (ou est absente d'un côté), retourne None."""
    norm_region = _normalize_region_for_merge(region)
    if not name or not norm_region:
        return None
    target_name = name.strip().lower()
    for row in con.execute("SELECT variety, name, region FROM hops"):
        if (row["name"].strip().lower() == target_name
                and _normalize_region_for_merge(row["region"]) == norm_region):
            return row["variety"]
    return None


def merge_hop_varieties(con, keep: str, drop: str) -> None:
    """Fusionne DEUX clés `variety` déjà présentes en base sous une seule
    (`keep`) -- réparation ponctuelle pour les houblons split AVANT ce
    correctif (`_find_variety_by_name_region` ne joue qu'à l'ingestion,
    jamais rétroactivement sur des lignes déjà écrites). Utilisé une seule
    fois (2026-08-19) pour les 5 paires réelles trouvées sur la base
    existante : Challenger, Fuggle, Hallertauer Tradition, Hersbrucker Spät,
    Target -- voir `tools/merge_duplicate_hops.py`.

    Déplace TOUTES les tables référençant `variety` (composition,
    descripteurs, roue d'arôme, associations houblon<->houblon dans les DEUX
    sens) vers `keep`, fusionne `sources` (union) et `purpose`
    (`COALESCE(keep, drop)` -- un seul des deux avait une valeur réelle dans
    les 5 cas vérifiés, jamais un conflit à trancher), puis supprime la ligne
    `drop`. `INSERT OR IGNORE` partout où la clé primaire inclut `variety`
    (évite un conflit si `keep` a par hasard déjà une ligne pour le même
    (compound/descriptor/source) que `drop` -- ne devrait pas arriver entre
    deux sources différentes vu le schéma EAV par source, mais reste un
    filet de sécurité plutôt qu'un crash)."""
    if keep == drop:
        return
    if not con.execute("SELECT 1 FROM hops WHERE variety=?", (drop,)).fetchone():
        return  # déjà fusionné (idempotent)
    keep_row = con.execute("SELECT sources, purpose FROM hops WHERE variety=?", (keep,)).fetchone()
    drop_row = con.execute("SELECT sources, purpose FROM hops WHERE variety=?", (drop,)).fetchone()
    if keep_row is None or drop_row is None:
        return

    con.execute(
        "INSERT OR IGNORE INTO hop_composition SELECT ?, compound, vmin, vmax, unit, "
        "source, confidence, notes FROM hop_composition WHERE variety=?", (keep, drop))
    con.execute(
        "INSERT OR IGNORE INTO hop_descriptors SELECT ?, descriptor, source "
        "FROM hop_descriptors WHERE variety=?", (keep, drop))
    con.execute(
        "INSERT OR IGNORE INTO hop_aroma_intensity SELECT ?, descriptor, intensity, source "
        "FROM hop_aroma_intensity WHERE variety=?", (keep, drop))
    con.execute(
        "INSERT OR IGNORE INTO hop_similar SELECT ?, similar_variety, source "
        "FROM hop_similar WHERE variety=?", (keep, drop))
    con.execute(
        "INSERT OR IGNORE INTO hop_similar SELECT variety, ?, source "
        "FROM hop_similar WHERE similar_variety=?", (keep, drop))
    con.execute(
        "INSERT OR IGNORE INTO hop_pairings SELECT ?, paired_name, paired_variety, "
        "frequency, source FROM hop_pairings WHERE variety=?", (keep, drop))
    con.execute("UPDATE hop_pairings SET paired_variety=? WHERE paired_variety=?", (keep, drop))
    con.execute(
        "INSERT OR IGNORE INTO hop_substitutions SELECT ?, substitute_name, "
        "substitute_variety, source FROM hop_substitutions WHERE variety=?", (keep, drop))
    con.execute("UPDATE hop_substitutions SET substitute_variety=? WHERE substitute_variety=?",
               (keep, drop))

    srcs = sorted(set(keep_row["sources"].split(",")) | set(drop_row["sources"].split(",")))
    purpose = keep_row["purpose"] if keep_row["purpose"] is not None else drop_row["purpose"]
    con.execute("UPDATE hops SET sources=?, purpose=? WHERE variety=?",
               (",".join(srcs), purpose, keep))

    for table in ("hop_composition", "hop_descriptors", "hop_aroma_intensity",
                  "hop_similar", "hop_pairings", "hop_substitutions"):
        con.execute(f"DELETE FROM {table} WHERE variety=?", (drop,))
    con.execute("DELETE FROM hop_similar WHERE similar_variety=?", (drop,))
    con.execute("DELETE FROM hops WHERE variety=?", (drop,))


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
    """
    Le slug d'URL BarthHaas colle parfois ®/™ au mot précédent sans séparateur
    ("Citra®" -> `.../hops/citrar`, pas `.../citra`) — voir
    `_fix_barthhaas_trademark_slug` pour le détail complet (9 variétés
    touchées, vérifié en direct). `variety` (clé interne) est corrigé via
    cette fonction, comparé au <h1> réel de chaque page ; `name` vient
    directement de ce <h1> (plus fidèle que l'ancien `slug.title()`, qui
    reproduisait aussi l'artefact et perdait les accents/casse d'origine).
    """
    import time, re, requests
    from bs4 import BeautifulSoup
    from .schema import connect
    BASE = "https://www.barthhaas.com"
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()
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
    for i, (slug, url) in enumerate(slugs, 1):
        try:
            html = requests.get(url, timeout=30,
                                headers={"User-Agent": "hopmatch/0.1 (research)"}).text
            soup = BeautifulSoup(html, "html.parser")
            h1 = soup.find("h1")
            h1_title = h1.get_text(strip=True) if h1 else None
            text = soup.get_text("\n")
            comp = parsers.parse_composition(text, parsers.BARTHHAAS_LABELS)
            if comp:
                variety = _fix_barthhaas_trademark_slug(slug, h1_title)
                # T59 (2026-08-19, demande utilisateur) : ®/™/© retirés du nom
                # affiché (`parsers.strip_trademark_symbols`), pas seulement du
                # slug de réconciliation -- voir sa docstring pour le détail.
                name = parsers.strip_trademark_symbols(h1_title) or slug.replace("-", " ").title()
                region = parsers.parse_region(text)
                # Doublon cross-source par nom+région (2026-08-19, voir
                # _find_variety_by_name_region) : seulement si la clé directe
                # n'existe pas déjà -- jamais de recherche par nom quand le
                # slug exact/dépréfixé matche déjà, pour ne jamais dévier
                # d'une correspondance certaine vers une correspondance
                # heuristique.
                if not con.execute("SELECT 1 FROM hops WHERE variety=?", (variety,)).fetchone():
                    merged = _find_variety_by_name_region(con, name, region)
                    if merged:
                        variety = merged
                _ingest_variety(con, variety, name, region, comp,
                                parsers.parse_descriptors(text), "barthhaas")
                print(f"  ok {slug} ({len(comp)})"
                     + (f" -> variety corrigée en {variety!r}" if variety != slug else ""))
        except Exception as e:  # noqa
            print(f"  !! {slug}: {e}")
        if i % 10 == 0:
            con.commit()
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
        init_db(con); seed_reference(con); con.commit()
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
# PubChem (réseau réel) — le "liant" : résolution CAS -> CID structurale
# --------------------------------------------------------------------------- #
def resolve_pubchem_cids(out_db: str, sleep: float = 0.25, timeout: float = 15.0) -> None:
    """
    Résout le PubChem CID de chaque composé de la whitelist Flavornet (table
    pubchem_cids : cas -> cid), via l'endpoint PUG-REST 'name' (qui accepte un
    CAS comme synonyme — vérifié : '78-70-6' -> 6549 pour le linalol,
    '140-67-0' -> 8815 pour l'estragole, exactement le CID déjà connu de
    methyl-chavicol dans reference.MOLECULES).

    C'est la clé structurale qui remplace deux mécanismes texte/heuristique :
      1. `_canonical_compound` peut fusionner un synonyme Flavornet/FooDB avec
         le vocabulaire houblon PAR IDENTITÉ CHIMIQUE (même CID), plutôt que
         par une table d'alias manuelle ou un dépréfixage grec ;
      2. `ingest_flavordb2` peut aller directement à la fiche FlavorDB2 par
         CID (`/molecules_details?id=<cid>`, endpoint natif du site) sans
         recherche par nom exact (qui ratait 488/734 composés sur un run réel,
         les synonymes/casse ne matchant pas toujours).

    Repli si le CAS ne résout rien : le nom Flavornet du composé, puis les
    variantes de `parsers.pubchem_name_fallbacks` (lettre grecque épelée,
    préfixe stéréochimique retiré — vérifié sur un run réel : 8/14 CAS
    initialement sans CID se résolvent ainsi, ex. 'δ-cadinol' seulement en
    'delta-cadinol', PubChem n'indexant pas le symbole grec comme synonyme).
    Le reste est laissé sans CID plutôt que de deviner une variante non vérifiée.

    Idempotent : ne resollicite PubChem que pour les CAS pas encore en base
    (cid NULL inclus, pour ne pas re-tenter en boucle une résolution échouée).
    Respecte la limite d'usage PubChem (5 req/s conseillées) via `sleep`.
    """
    import requests
    import time
    import urllib.parse
    from .schema import connect
    URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{}/cids/JSON"

    def _lookup(query: str) -> int | None:
        resp = requests.get(URL.format(urllib.parse.quote(query)), timeout=timeout,
                            headers={"User-Agent": "hopmatch/0.1 (research)"})
        if resp.status_code == 200:
            cids = resp.json().get("IdentifierList", {}).get("CID", [])
            if cids:
                return cids[0]
        return None

    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()

    known = {r[0] for r in con.execute("SELECT cas FROM pubchem_cids")}
    targets = [(r["cas"], r["compound"]) for r in
              con.execute("SELECT cas, compound FROM flavornet_compounds")
              if r["cas"] not in known]
    if not targets:
        print("PubChem : rien à résoudre (déjà fait, ou flavornet_compounds vide)."); con.close(); return
    print(f"PubChem : résolution de {len(targets)} CAS -> CID")

    found, via_name, errors = 0, 0, 0
    for i, (cas, compound) in enumerate(targets, 1):
        cid = None
        try:
            cid = _lookup(cas)
            if cid is None:
                for variant in parsers.pubchem_name_fallbacks(compound):
                    time.sleep(sleep)
                    cid = _lookup(variant)
                    if cid:
                        via_name += 1
                        break
        except Exception as e:  # noqa
            # Erreur réseau transitoire : NE PAS enregistrer ce CAS comme "traité"
            # (cid NULL) — sinon plus jamais retenté au prochain run. On le laisse
            # simplement hors de `pubchem_cids` pour cette exécution.
            print(f"  !! {cas} ({compound}): {e}")
            errors += 1
            time.sleep(sleep)
            continue
        if cid:
            found += 1
        con.execute("INSERT OR REPLACE INTO pubchem_cids VALUES (?,?)", (cas, cid))
        if i % 25 == 0:
            con.commit()
        time.sleep(sleep)
    con.commit(); con.close()
    print(f"PubChem : {found}/{len(targets)} CAS résolus en CID ({via_name} via repli sur le nom)"
          + (f", {errors} erreurs réseau (à retenter)." if errors else "."))


# --------------------------------------------------------------------------- #
# FlavorDB2 (réseau réel) — seuils olfactifs, bornés à la whitelist Flavornet
# --------------------------------------------------------------------------- #
def ingest_flavordb2(out_db: str, sleep: float = 0.3, timeout: float = 30.0) -> None:
    """
    FlavorDB2 (cosylab.iiitd.edu.in/flavordb2) : seuils olfactifs par molécule.
    Pas de dump bulk ni d'API JSON stable pour les seuils (le seul JSON bulk du
    site est un graphe d'imports entre aliments, sans rapport).

    PRIORITÉ AU CID DIRECT (resolve_pubchem_cids doit avoir tourné avant, sinon
    dégrade gracieusement) : `/molecules_details?id=<cid>` est l'endpoint natif
    du site — si on connaît déjà le CID PubChem du composé (table
    pubchem_cids, résolu depuis son CAS Flavornet), on saute directement la
    fiche détail, sans recherche par nom. Repli sur la recherche par nom
    (`/molecules?common_name=`) uniquement pour les CAS sans CID résolu — c'est
    ce repli, utilisé seul avant, qui ratait 488/734 composés sur un run réel
    (synonymes/casse qui ne matchent pas exactement). La fiche détail contient
    le CAS et un champ 'Aroma threshold values' en texte libre.

    Bornée à la whitelist Flavornet (table flavornet_compounds, ~734 composés)
    plutôt qu'un crawl des 25 595 molécules de FlavorDB2 : c'est tout ce dont
    hopmatch peut utiliser, et ça évite de solliciter inutilement leur serveur
    pour des dizaines de milliers de molécules hors sujet.

    Écrit dans `flavordb2_thresholds`, PAS dans `molecules` : pas de repli sur
    l'amorce manuelle `reference.MOLECULES` (14 seuils saisis à la main) — soit
    FlavorDB2 confirme un seuil, soit la molécule reste sans seuil pour
    `ingest_foodb`. Une molécule sans correspondance ou sans seuil publié est
    simplement ignorée (comptée, pas devinée) : voir parsers.parse_flavordb2_threshold
    pour le garde-fou contre les textes sans unité reconnue (ex. un pourcentage
    de composition confondu avec un seuil pour le myrcène).
    """
    import time
    import requests
    from .schema import connect
    BASE = "https://cosylab.iiitd.edu.in/flavordb2"
    HEADERS = {"User-Agent": "hopmatch/0.1 (research)"}
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()

    known = {r[0] for r in con.execute("SELECT cas FROM flavordb2_thresholds")}
    targets = [r for r in con.execute("SELECT cas, compound FROM flavornet_compounds")
              if r["cas"] not in known]
    if not con.execute("SELECT 1 FROM flavornet_compounds LIMIT 1").fetchone():
        con.close()
        raise RuntimeError(
            "flavornet_compounds est vide : lancer ingest_flavornet avant ingest_flavordb2.")
    if not targets:
        print("FlavorDB2 : rien à traiter (déjà fait pour toute la whitelist Flavornet).")
        con.close(); return
    cids = {r["cas"]: r["cid"] for r in
           con.execute("SELECT cas, cid FROM pubchem_cids WHERE cid IS NOT NULL")}
    print(f"FlavorDB2 : recherche de seuils pour {len(targets)} composés restants "
          f"(sur {len(known) + len(targets)} au total)"
          + (f", {len(cids)} CID PubChem déjà résolus (accès direct)" if cids else
             " — resolve_pubchem_cids n'a pas tourné, repli 100% recherche par nom"))

    found, via_cid, no_match, no_threshold, errors = 0, 0, 0, 0, 0
    for i, row in enumerate(targets, 1):
        cas, compound = row["cas"], row["compound"]
        threshold = None
        cid = cids.get(cas)
        if cid is not None:
            via_cid += 1
        try:
            if cid is None:
                html = requests.get(f"{BASE}/molecules", params={"common_name": compound, "page": 1},
                                    timeout=timeout, headers=HEADERS).text
                cid = next((c for name, c in parsers.parse_flavordb2_search(html)
                           if name.lower() == compound.lower()), None)
            if cid is not None:
                time.sleep(sleep)
                detail_html = requests.get(f"{BASE}/molecules_details", params={"id": cid},
                                           timeout=timeout, headers=HEADERS).text
                _, threshold = parsers.parse_flavordb2_detail(detail_html)
        except Exception as e:  # noqa
            # Erreur réseau transitoire (timeout, etc.) : NE PAS enregistrer comme
            # "traité" — sinon ce CAS ne serait plus jamais retenté au prochain run.
            print(f"  !! {compound}: {e}")
            errors += 1
            time.sleep(sleep)
            continue

        # Toujours enregistrer une tentative aboutie (seuil trouvé ou NULL confirmé) :
        # marque le CAS comme traité pour ne pas le refaire à la prochaine exécution,
        # et le commit périodique ci-dessous évite de perdre le travail déjà fait si
        # le commit final échoue (ex. coupure disque/réseau, synchronisation cloud —
        # observé en usage réel).
        con.execute("INSERT OR REPLACE INTO flavordb2_thresholds VALUES (?,?,?)",
                    (cas, compound, threshold))
        if threshold is not None:
            found += 1
        elif cid is None:
            no_match += 1
        else:
            no_threshold += 1
        if i % 25 == 0:
            con.commit()
        time.sleep(sleep)
    con.commit(); con.close()
    print(f"FlavorDB2 : {found} seuils trouvés ({via_cid} via CID PubChem direct) "
          f"| {no_match} sans correspondance | {no_threshold} sans seuil publié"
          + (f" | {errors} erreurs réseau (à retenter)." if errors else "."))


# --------------------------------------------------------------------------- #
# Crawl Yakima Chief (réseau réel) — via Algolia, pas de HTML/checkpoint
# --------------------------------------------------------------------------- #
def crawl_yakima(out_db: str, limit: int | None = None, timeout: float = 30.0) -> None:
    """
    Yakima Chief (yakimachief.com/hop-varieties). Le site a un vrai rempart
    anti-bot devant le HTML (Vercel Security Checkpoint) : `requests` seul ne
    passe jamais, même avec un User-Agent de navigateur réel (vérifié). MAIS le
    site s'appuie sur Algolia (InstantSearch) pour lister/chercher les variétés,
    avec une clé de recherche PUBLIQUE exposée côté client (clé Algolia
    "search-only", conçue pour être visible dans le JS du navigateur, en
    lecture seule) : on interroge cet index Algolia directement, en HTTP simple,
    sans navigateur ni checkpoint.

    Une seule requête ramène les ~152 variétés, chacune avec sa composition déjà
    structurée en JSON (imported_fields.brewing_values, low/ave/high) ET sa roue
    d'arôme (imported_fields.aromas) — pas de parsing HTML/texte requis pour
    cette source, contrairement à BarthHaas. Voir parsers.parse_yakima_hit.

    Écrit aussi `hop_similar` (T25 backlog) depuis imported_fields.similar_varieties
    (Yakima uniquement : variétés similaires/substituts curées par YCH lui-même,
    référencées par uid Contentstack, résolues ici contre le lot complet).

    Fragile par nature (clé/index/champs non documentés publiquement, peuvent
    changer sans préavis si YCH modifie son frontend) — si ça casse, ouvrir
    https://www.yakimachief.com/hop-varieties dans un navigateur, onglet réseau,
    et retrouver la requête POST vers *.algolia.net.
    """
    import requests
    from .schema import connect
    ALGOLIA_URL = "https://9L63CAKQTR-dsn.algolia.net/1/indexes/*/queries"
    ALGOLIA_PARAMS = {"x-algolia-api-key": "7805da050ed9c904a85c95e81ec8181c",
                      "x-algolia-application-id": "9L63CAKQTR"}
    BODY = {"requests": [{
        "indexName": "contentstack--name-asc",
        "filters": '_content_type:"variety" AND environment:"production" '
                   'AND publish_details.locale:"en-us"',
        "hitsPerPage": 1000, "page": 0, "query": "",
    }]}
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()

    resp = requests.post(ALGOLIA_URL, params=ALGOLIA_PARAMS, json=BODY,
                         timeout=timeout, headers={"User-Agent": "hopmatch/0.1 (research)"})
    resp.raise_for_status()
    hits = resp.json()["results"][0]["hits"]
    if limit:
        hits = hits[:limit]
    print(f"Yakima Chief : {len(hits)} variétés (Algolia)")

    # Les variétés déposées ont un slug '-brand' (ex. 'citra-brand') qui ne
    # fusionnerait jamais avec le slug BarthHaas ('citra'). On déprefixe SAUF
    # collision avec un autre slug du même lot : le catalogue YCH a aussi de
    # vrais doublons de SKU sans rapport avec les marques (ex. 'perle' ET
    # 'perle-per03' coexistent déjà) — dans ce cas on n'y touche pas, pour ne
    # pas fusionner silencieusement deux fiches distinctes.
    raw_slugs = {(hit.get("url") or "").rsplit("/", 1)[-1] for hit in hits}

    def _dealias(slug: str) -> str:
        if slug.endswith("-brand"):
            stripped = slug[: -len("-brand")]
            if stripped and stripped not in raw_slugs:
                return stripped
        return slug

    # uid -> variety FINALE (après dépréfixage marque ET fusion nom+région,
    # voir _find_variety_by_name_region), pour résoudre
    # imported_fields.similar_varieties (T25 backlog) : Contentstack
    # référence les variétés similaires PAR uid, pas par slug. Construite
    # progressivement PENDANT la boucle d'ingestion (pas en amont sur le
    # seul dépréfixage) -- sinon un hit dont la variety fusionne (ex.
    # "hallertauer-tradition" -> "hallertau-tradition" si BarthHaas a déjà
    # tourné) laisserait `hop_similar` référencer la clé pré-fusion, jamais
    # écrite dans `hops` (bug potentiel identifié en écrivant ce correctif,
    # jamais laissé passer). L'écriture de `hop_similar` elle-même attend la
    # fin de la boucle (deuxième passe) : une variété peut référencer une
    # autre variété plus loin dans la liste des hits.
    uid_to_variety: dict[str, str] = {}
    similar_by_uid: dict[str, list[str]] = {}

    stats = {"ok": 0, "repaired": 0, "suspect": 0}
    skipped = 0
    for hit in hits:
        variety, name, region, comp, descriptors, aroma_intensity = parsers.parse_yakima_hit(hit)
        variety = _dealias(variety)
        if not variety or not comp:
            skipped += 1; continue
        # Doublon cross-source par nom+région (2026-08-19, voir
        # _find_variety_by_name_region) : même logique que crawl_barthhaas,
        # seulement en repli quand la clé directe (dépréfixée) n'existe pas
        # déjà -- symétrique et indépendant de l'ordre des deux crawls.
        if not con.execute("SELECT 1 FROM hops WHERE variety=?", (variety,)).fetchone():
            merged = _find_variety_by_name_region(con, name, region)
            if merged:
                variety = merged
        conf = _ingest_variety(con, variety, name, region, comp, descriptors, "yakima",
                               aroma_intensity=aroma_intensity)
        stats[conf] += 1
        if hit.get("uid"):
            uid_to_variety[hit["uid"]] = variety
        similar_by_uid[hit.get("uid")] = [
            sim.get("uid") for sim in (hit.get("imported_fields") or {}).get("similar_varieties") or []]

    for uid, variety in uid_to_variety.items():
        for sim_uid in similar_by_uid.get(uid, []):
            sim_variety = uid_to_variety.get(sim_uid)
            if sim_variety and sim_variety != variety:
                con.execute("INSERT OR REPLACE INTO hop_similar VALUES (?,?,?)",
                            (variety, sim_variety, "yakima"))
    con.commit(); con.close()
    print(f"  ok={stats['ok']} repaired={stats['repaired']} suspect={stats['suspect']}"
          + (f" | {skipped} sans composition exploitable (ignorées)" if skipped else ""))


# --------------------------------------------------------------------------- #
# BeerMaverick (réseau réel, T25 backlog) — pairing/substitution
# --------------------------------------------------------------------------- #
_HOP_NAME_STOPWORDS_RE = re.compile(r"\b(brand|hops?|nz|us|ma)\b")


def _normalize_hop_key(s: str) -> str:
    """Clé de réconciliation nom<->variety, tolérante aux habillages
    commerciaux (®/™, 'Brand', 'NZ Hops'...) qui diffèrent entre sources —
    même esprit que la normalisation de descripteurs, appliquée ici aux noms
    de houblon plutôt qu'aux arômes."""
    s = s.lower()
    s = re.sub(r"[®™©]", "", s)
    s = _HOP_NAME_STOPWORDS_RE.sub("", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def _fix_barthhaas_trademark_slug(slug: str, h1_title: str | None) -> str:
    """BarthHaas transforme parfois ®/™ en un « r »/« tm » collé DIRECTEMENT au
    mot précédent dans son propre slug d'URL — vérifié en direct sur le
    catalogue réel (crawl complet des 97 pages, comparaison slug URL vs
    <h1> réel de chaque fiche) : `/hops-and-products/hops/citrar` alors que
    le <h1> de la page dit "Citra®", `.../mosaicr` pour "Mosaic®", etc.
    9 variétés touchées (citra, ekuanot, loral, mosaic, sabro, summit, azacca,
    talus, bru-1) + amarillo (suffixe cultivar après le "r" collé :
    `amarillor-vgxp01-cv` -> "Amarillo®" + code produit "VGXP01", absent du
    <h1> réel). Cette clé erronée empêchait la fusion multi-source avec Yakima
    (qui utilise la forme propre "citra"/"mosaic"...) : chaque houblon
    apparaissait deux fois (une fiche BarthHaas sans thiols fusionnés, une
    fiche Yakima sans les thiols BarthHaas), silencieusement.

    Le suffixe après le "r"/"tm" collé (cf. amarillo) est ENTIÈREMENT retiré,
    pas seulement le "r" — vérifié en direct sur la réingestion réelle :
    conserver "-vgxp01-cv" (première version de cette fonction) empêchait la
    fusion avec Yakima ("amarillo-brand-ama04" déjà dépréfixé en "amarillo"
    de son côté). "VGXP01" est un code cultivar/SKU interne BarthHaas absent
    du <h1> — même situation que le "AMA04" que Yakima dépréfixe déjà de son
    propre côté pour la même variété, donc le même traitement s'applique.

    PAS une troncature générique d'un « r » final — de vrais houblons finissent
    légitimement par « r » (Saazer, Glacier, Endeavour, Challenger, Cluster,
    Pioneer...) et ne doivent jamais être touchés. La correction n'est appliquée
    QUE quand le <h1> réel de la page CONFIRME, par sa propre forme normalisée,
    que le slug COMMENCE PAR ce nom + "r"/"tm" collé — jamais une supposition
    sur la forme du mot seul. `h1_title` absent (échec de parsing) -> slug
    inchangé, filet de sécurité plutôt qu'une correction hasardeuse."""
    if not h1_title:
        return slug
    clean = _normalize_hop_key(h1_title)
    if not clean:
        return slug
    for suffix in ("r", "tm"):
        glued = clean + suffix
        if slug == glued or slug.startswith(glued + "-"):
            return clean
    return slug


def _build_hop_name_index(con) -> dict[str, str]:
    """{clé normalisée: variety} depuis variety ET name — pour réconcilier un
    slug/nom EXTERNE (BeerMaverick) vers notre propre catalogue, sans jamais
    fabriquer de houblon : une entrée non reconnue reste non reconnue."""
    index: dict[str, str] = {}
    for variety, name in con.execute("SELECT variety, name FROM hops"):
        index.setdefault(_normalize_hop_key(variety), variety)
        index.setdefault(_normalize_hop_key(name), variety)
    return index


def _resolve_hop_variety(index: dict[str, str], candidate: str) -> str | None:
    return index.get(_normalize_hop_key(candidate))


# Tags BeerMaverick QUI NE SONT PAS des descripteurs d'arôme réels — mesuré sur
# un crawl complet des 142 pages réconciliées (131 tags distincts au total) :
# adjectifs de qualité génériques ("mild", "clean", "smooth"...), classification
# de style plutôt qu'arôme ("noble", "bohemian"), ou tag circulaire/vide de sens
# pour un descripteur de houblon ("hoppy"). Filtrés à l'ingestion plutôt que
# laissés polluer `hop_descriptors` avec du bruit non-olfactif — même esprit que
# la whitelist Flavornet pour FooDB (`ingest_foodb`), un filtre AVANT écriture,
# pas une correction après coup.
_BEERMAVERICK_TAG_DROPLIST = {
    "balsamic", "bohemian", "clean", "cognac", "cream", "crisp", "delicate",
    "fresh", "green", "green_fruit", "hoppy", "mellow", "mild", "mojito",
    "neutral", "noble", "pleasant", "pungent", "smooth", "sweet", "sweet_fruit",
    "tangy", "wild", "yogurt", "zest",
}


def _normalize_beermaverick_tag(tag: str) -> str | None:
    """Underscore->espace puis résolution alias (`reference.DESCRIPTOR_ALIASES` —
    vrais renommages du même concept) ; les sous-familles réelles (raspberry,
    jasmine, curry...) restent des entrées distinctes dans
    `reference.CONTRAST_AFFINITY`, pas écrasées ici — voir le commentaire de ce
    fichier pour le détail. None si le tag est dans `_BEERMAVERICK_TAG_DROPLIST`
    (pas un descripteur d'arôme)."""
    if tag in _BEERMAVERICK_TAG_DROPLIST:
        return None
    d = tag.replace("_", " ")
    return reference.DESCRIPTOR_ALIASES.get(d, d)


# Vocabulaire brut BeerMaverick ("Aroma"/"Bittering"/"Dual", voir
# parsers.parse_beermaverick_purpose) -> notre propre vocabulaire à 3
# catégories (demande utilisateur explicite : "bittering, aromatic and
# both"). "Dual" -> "both", pas "dual" : nom choisi côté hopmatch, pas une
# retranscription du libellé source.
_BEERMAVERICK_PURPOSE_MAP = {"aroma": "aromatic", "bittering": "bittering", "dual": "both"}


def _normalize_beermaverick_purpose(raw: str | None) -> str | None:
    """None si absent ou si la valeur ne fait pas partie des 3 catégories
    connues (`_BEERMAVERICK_PURPOSE_MAP`) -- jamais deviné depuis un texte
    inattendu, plutôt laisser `purpose` NULL (comme les autres champs
    optionnels BeerMaverick)."""
    if not raw:
        return None
    return _BEERMAVERICK_PURPOSE_MAP.get(raw.strip().lower())


def ingest_beermaverick(out_db: str, limit: int | None = None, sleep: float = 1.0,
                        timeout: float = 30.0) -> None:
    """
    beermaverick.com (T25 backlog) : associations houblon<->houblon absentes de
    BarthHaas/Yakima — « Hop Pairings » (fréquence relative dans des recettes
    publiées analysées par eux) et « Hop Substitutions » (choix éditorial de
    brasseurs expérimentés). AGRÉGATEUR, pas une mesure de labo indépendante
    comme BarthHaas/Yakima — GUI affiche cette réserve, jamais mélangé aux
    couches de score (`matching`).

    HTML servi normalement côté serveur (`robots.txt` : `Disallow:` vide,
    vérifié), pas de rempart anti-bot. Une investigation précédente avait
    écarté BeerMaverick à cause de leur endpoint interne `/api/js/?hop=<id>`,
    explicitement documenté "internal use" (voir docs/BACKLOG.md) — mais LA
    MÊME donnée (pairings ET substitutions) est en fait déjà dans le HTML
    statique de chaque page `/hop/{slug}/`, exactement comme BarthHaas :
    aucun besoin de cet endpoint. Voir parsers.parse_beermaverick_pairings/
    parse_beermaverick_substitutions.

    Réconciliation par nom normalisé (`_resolve_hop_variety`) : sur les 318
    pages du sitemap BeerMaverick, 143/203 de nos variétés ont une page
    correspondante (mesuré). Les pages BeerMaverick sans équivalent chez nous
    sont simplement ignorées (skip, pas de houblon fabriqué). Le houblon-cible
    d'une substitution est réconcilié via le slug BeerMaverick (fiable,
    fourni par leur propre lien) ; le houblon-cible d'un pairing seulement via
    son nom affiché (leur graphique ne fournit pas de slug) — `paired_variety`/
    `substitute_variety` restent NULL si non reconnus, mais `paired_name`/
    `substitute_name` (texte brut) sont TOUJOURS renseignés, rien n'est perdu.

    Écrit aussi des DESCRIPTEURS dans `hop_descriptors` (source='beermaverick',
    coexiste avec barthhaas/yakima — `matching.load` les union sans distinction
    de source) depuis le bloc « Tags: #pine #dank... » de chaque page — un
    vocabulaire RÉEL bien plus riche que la liste courte `aromas` de Yakima
    (vérifié en direct sur Chinook/Columbus : Yakima ne tague aucun des deux
    "dank", BeerMaverick le fait pour les deux, correctement, alors que Mosaic/
    Simcoe n'ont PAS ce tag chez eux non plus — cohérent avec l'usage brassicole
    réel). Filtré (`_BEERMAVERICK_TAG_DROPLIST`) puis normalisé
    (`_normalize_beermaverick_tag`) — voir `parsers.parse_beermaverick_tags`.

    Écrit aussi `hops.purpose` (aromatic/bittering/both) depuis la ligne
    « Purpose: » du tableau Analyses de chaque page — SEULE source trouvée
    qui classe explicitement un houblon par usage (ni BarthHaas ni Yakima
    n'ont ce champ, vérifié en direct). Voir
    `parsers.parse_beermaverick_purpose`/`_normalize_beermaverick_purpose`.
    """
    import time, requests
    from .schema import connect
    BASE = "https://beermaverick.com"
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()

    sitemap = requests.get(f"{BASE}/beerm-sitemap.xml", timeout=timeout,
                           headers={"User-Agent": "hopmatch/0.1 (research)"}).text
    slugs = sorted(set(re.findall(r"beermaverick\.com/hop/([a-z0-9-]+)/", sitemap)))
    if limit:
        slugs = slugs[:limit]
    print(f"BeerMaverick : {len(slugs)} pages houblon (sitemap)")

    index = _build_hop_name_index(con)
    covered = skipped = n_pairings = n_subs = n_tags = n_purpose = 0
    for i, slug in enumerate(slugs, 1):
        variety = _resolve_hop_variety(index, slug)
        if not variety:
            skipped += 1
            continue
        try:
            html = requests.get(f"{BASE}/hop/{slug}/", timeout=timeout,
                                headers={"User-Agent": "hopmatch/0.1 (research)"}).text
        except Exception as e:  # noqa
            print(f"  !! {slug}: {e}"); continue
        for name, freq in parsers.parse_beermaverick_pairings(html):
            paired = _resolve_hop_variety(index, name)
            con.execute("INSERT OR REPLACE INTO hop_pairings VALUES (?,?,?,?,?)",
                        (variety, name, paired, freq, "beermaverick"))
            n_pairings += 1
        for sub_slug, sub_name in parsers.parse_beermaverick_substitutions(html):
            sub_variety = (_resolve_hop_variety(index, sub_slug)
                          or _resolve_hop_variety(index, sub_name))
            con.execute("INSERT OR REPLACE INTO hop_substitutions VALUES (?,?,?,?)",
                        (variety, sub_name, sub_variety, "beermaverick"))
            n_subs += 1
        for raw_tag in parsers.parse_beermaverick_tags(html):
            d = _normalize_beermaverick_tag(raw_tag)
            if d is None:
                continue
            con.execute("INSERT OR REPLACE INTO hop_descriptors VALUES (?,?,?)",
                        (variety, d, "beermaverick"))
            n_tags += 1
        purpose = _normalize_beermaverick_purpose(parsers.parse_beermaverick_purpose(html))
        if purpose is not None:
            con.execute("UPDATE hops SET purpose=? WHERE variety=?", (purpose, variety))
            n_purpose += 1
        covered += 1
        if i % 10 == 0:
            con.commit()
        time.sleep(sleep)
    con.commit(); con.close()
    print(f"  {covered} variétés couvertes ({skipped} pages sans équivalent local), "
         f"{n_pairings} pairings, {n_subs} substitutions, {n_tags} descripteurs, "
         f"{n_purpose} purpose (aromatic/bittering/both).")


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


def _hop_cid_map() -> dict[int, str]:
    """PubChem CID -> nom houblon canonique, pour les entrées de reference.MOLECULES
    dont le CID est connu (identité chimique, pas un nom de compagnie)."""
    return {cid: compound for compound, (_, _, cid) in reference.MOLECULES.items() if cid}


def _build_cas_to_hop_name(con) -> dict[str, str]:
    """Précalcule {cas: nom houblon} pour tous les CAS déjà résolus en CID
    (table pubchem_cids, cf. resolve_pubchem_cids) dont le CID correspond à un
    composé du vocabulaire houblon. Vide si resolve_pubchem_cids n'a pas tourné
    (dégrade gracieusement vers l'heuristique de _canonical_compound)."""
    hop_cids = _hop_cid_map()
    if not hop_cids:
        return {}
    out = {}
    for r in con.execute("SELECT cas, cid FROM pubchem_cids WHERE cid IS NOT NULL"):
        hop_name = hop_cids.get(r["cid"])
        if hop_name:
            out[r["cas"]] = hop_name
    return out


def _canonical_compound(cas: str, name: str, cas_to_hop_name: dict[str, str]) -> str:
    """
    Aligne un nom de composé Flavornet/FooDB sur le vocabulaire houblon existant,
    pour éviter deux pièges d'honnêteté (coverage/orphan) : la même molécule
    listée deux fois sous deux noms (double comptage), ou une ORPHELINE
    artificielle alors que le houblon la fournit sous un autre nom.

    PRIORITÉ À L'IDENTITÉ STRUCTURALE (cas_to_hop_name, résolu via PubChem CID
    par resolve_pubchem_cids + _build_cas_to_hop_name) : fiable, ne repose sur
    aucune supposition de nommage. Exemple vérifié : le CAS de l'estragole
    (140-67-0) résout au même CID PubChem (8815) que methyl-chavicol dans
    reference.MOLECULES — la fusion est un FAIT chimique, pas un devinage.

    Repli sur les heuristiques historiques UNIQUEMENT si le CID n'est pas
    résolu (resolve_pubchem_cids pas lancé, ou CAS introuvable sur PubChem) :
    alias manuels restants (reference.ALIASES — n'a plus que les agrégations
    sans CID propre comme 'thiols', qui ne sont pas une vraie molécule unique
    mais un regroupement de composés mesurés ensemble côté houblon) puis
    dépréfixage grec (β-caryophyllene -> caryophyllene). On ne renomme que
    vers une forme reconnue ; sinon le nom Flavornet est gardé tel quel.
    """
    if cas in cas_to_hop_name:
        return cas_to_hop_name[cas]
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


FOODB_DUMP_URL = "https://foodb.ca/public/system/downloads/foodb_2020_4_7_csv.tar.gz"
FOODB_DUMP_DIR = "data/foodb_2020_04_07_csv"


def _extract_foodb_tarball(tar_path: str, extract_root: str) -> None:
    """Extraction pure (testable sans réseau) : sépare le téléchargement de son
    dépaquetage. `filter="data"` (PEP 706) écarte les chemins absolus/`..` d'une
    archive malveillante — défense en profondeur pour un fichier tiers distant.

    Mode `"r:*"` (auto-détection), PAS `"r:gz"` : vérifié sur le fichier réel
    (`file` + `tar -tvf`) que `foodb_2020_4_7_csv.tar.gz` est en fait un tar
    NON compressé malgré son nom (`.tar.gz` trompeur côté foodb.ca — même le
    magic number diffère : `._foodb_2020_04_07_csv` en tête, pas 0x1f 0x8b).
    `"r:gz"` échouait donc systématiquement (`BadGzipFile`) quel que soit le
    téléchargement ; `"r:*"` fonctionne pour ce cas réel et resterait correct
    si foodb.ca compressait un jour vraiment le fichier."""
    import tarfile
    with tarfile.open(tar_path, "r:*") as tar:
        tar.extractall(extract_root, filter="data")


def download_foodb_dump(dest_dir: str = FOODB_DUMP_DIR, url: str = FOODB_DUMP_URL,
                        force: bool = False) -> str:
    """
    Télécharge et extrait le dump bulk FooDB (foodb.ca) s'il n'est pas déjà présent
    localement, pour que `ingest_foodb` fonctionne sans étape manuelle de
    téléchargement. Dump figé au 2020-04-07 (dernière version publique du site,
    vérifié : `foodb.ca/public/system/downloads/...` répond 200 sans authentification),
    ~950 Mo (malgré le nom `.tar.gz`, c'est un tar NON compressé côté serveur —
    vérifié via `file`/`tar -tvf` sur le fichier réel, voir `_extract_foodb_tarball`
    — donc extrait ~950 Mo aussi, pas de gain de compression à attendre). Licence
    **CC BY-NC-SA (non commerciale)** — voir CLAUDE.md/README, ce script ne
    contourne aucune protection, le lien est celui exposé publiquement par le site.

    Idempotent : si `dest_dir/Food.csv` existe déjà, ne retélécharge rien (sauf
    `force=True`). Le tar.gz est écrit dans un fichier temporaire (jamais dans
    `dest_dir` directement) pour ne jamais laisser un dump partiel/corrompu passer
    pour un dump valide si le téléchargement est interrompu.
    """
    import requests
    import tempfile

    food_csv = os.path.join(dest_dir, "Food.csv")
    if os.path.exists(food_csv) and not force:
        print(f"FooDB : dump déjà présent dans {dest_dir!r}, pas de retéléchargement.")
        return dest_dir

    print("FooDB : dump non trouvé localement, téléchargement depuis foodb.ca "
         "(~950 Mo, licence CC BY-NC-SA non commerciale)...")
    extract_root = os.path.dirname(os.path.normpath(dest_dir)) or "."
    os.makedirs(extract_root, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".tar.gz", dir=extract_root)
    os.close(fd)
    try:
        with requests.get(url, stream=True, timeout=60,
                          headers={"User-Agent": "hopmatch/0.1 (research)"}) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded, next_report = 0, 100_000_000
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded >= next_report:
                        pct = f" ({100*downloaded/total:.0f}%)" if total else ""
                        print(f"  {downloaded/1e6:.0f} Mo téléchargés{pct}...")
                        next_report += 100_000_000
        print("FooDB : extraction...")
        _extract_foodb_tarball(tmp_path, extract_root)
    finally:
        os.remove(tmp_path)
    if not os.path.exists(food_csv):
        raise RuntimeError(
            f"Extraction terminée mais {food_csv!r} introuvable : structure d'archive "
            f"inattendue (le tar.gz FooDB a changé de disposition ? vérifier "
            f"{extract_root!r} manuellement).")
    print(f"FooDB : dump prêt dans {dest_dir!r}.")
    return dest_dir


def ingest_foodb(out_db: str, foodb_csv_dir: str | None = None,
                 notes: dict[str, str] | None = None, all_foods: bool = True,
                 chunksize: int = 300_000) -> None:
    """
    Peuple note->molécule depuis le dump bulk FooDB (foodb.ca), FILTRÉ via la
    whitelist Flavornet (ingest_flavornet doit avoir tourné avant : sinon >90%
    des ~6000 composés/aliment sont du bruit nutritionnel, cf. CLAUDE.md et
    tools/audit_foodb.py). Seule source de notes du pipeline (pas d'amorce
    littérature à fusionner : reference.AROMA_NOTES/NOTE_DESCRIPTORS/
    NOTE_TO_FOODB ont existé puis ont été retirés une fois ce pipeline
    suffisant — décision explicite : une seule source de vérité par note).

    `foodb_csv_dir` : dossier du dump CSV déjà extrait. Si `None` (défaut),
    `download_foodb_dump()` le télécharge et l'extrait automatiquement dans
    `FOODB_DUMP_DIR` (idempotent : ne retélécharge pas s'il est déjà présent) —
    l'utilisateur n'a plus besoin de récupérer le dump à la main.

    `notes` : {note: nom Food.csv} — surcharge de nommage OPTIONNELLE et
    ADDITIVE (vide par défaut) : ajoute une note sous un nom choisi (fusionnant
    alors le profil `all_foods`, s'il en génère un pour le même aliment, avec
    ce nom-là AUSSI — les deux noms coexistent, ni l'un ni l'autre n'écrase
    l'autre : `food_entries` est une LISTE de (food_id, note, is_curated), pas
    un dict par food_id, précisément pour permettre à un même aliment de porter
    plusieurs notes plutôt que la dernière écrite gagne silencieusement).

    `all_foods` (True par défaut) : parcourt tout `Food.csv` (~1000 aliments
    sur le dump 2020-04-07) et crée une note par aliment, nom = celui de
    Food.csv en minuscule. Pipeline non supervisé : rien dans le
    filtrage/pondération FooDB n'est spécifique à une note en particulier.

    **Filtre de distinctivité** (n'épargne QUE les entrées de `notes`, si
    fournies — sinon s'applique à tout) : un aliment est écarté s'il n'a AUCUN
    composé à concentration mesurée (`foodb:conc`) — vérifié sur le dump réel
    que deux aliments sans rapport (capers/chervil) partagent 99,2% de leurs
    composés listés (FooDB cite souvent un gabarit générique plutôt qu'une
    composition mesurée pour cet aliment précis) ; sans concentration, tout
    retombe sur la table de seuils GLOBALE, donnant des poids identiques à deux
    aliments sans lien. Sur le dump 2020-04-07 (all_foods, sans surcharge
    `notes`) : 345 des 847 candidats avec au moins un composé whitelisté (41%)
    écartés par ce filtre (992 aliments au total, 141 sans aucun composé
    whitelisté — voir `no_hit` ci-dessous, ~510 notes distinctes conservées).
    Limite honnête : aucune note (curée ou non) n'a de `note_descriptors` par
    défaut désormais — `amplify` fonctionne en scoring
    molécules-seules pour toutes, `contrast` par `note` lève une ValueError
    explicite (matching.contrast) plutôt qu'un résultat vide silencieux ;
    `contrast` reste utilisable via une sélection manuelle de descripteurs
    (`matching.contrast(descriptors=[...])`, indépendante des notes).
    `all_foods=False` restreint à `notes` seul (démo/tests rapides).

    Poids : concentration (mg/100g, familles d'unités comparables uniquement, cf.
    parsers.mass_mg_per_100g) là où elle existe, sinon prior de seuil (1/seuil_ppb,
    depuis `flavordb2_thresholds` UNIQUEMENT — jamais l'amorce manuelle
    reference.MOLECULES, voir ingest_flavordb2), sinon présence pure. Jamais
    d'OAV (pas de concentration fiable pour la majorité des composés).
    """
    import pandas as pd
    from .schema import connect

    if foodb_csv_dir is None:
        foodb_csv_dir = download_foodb_dump()
    notes = notes or {}
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()

    cas_to_hop_name = _build_cas_to_hop_name(con)
    flavornet = {r["cas"]: (_canonical_compound(r["cas"], r["compound"], cas_to_hop_name), r["descriptors"])
                for r in con.execute("SELECT cas, compound, descriptors FROM flavornet_compounds")}
    if not flavornet:
        con.close()
        raise RuntimeError(
            "flavornet_compounds est vide : lancer ingest_flavornet avant ingest_foodb "
            "(whitelist odeur-active requise pour filtrer FooDB).")
    whitelist = {cas: compound for cas, (compound, _) in flavornet.items()}
    odor_by_compound = {compound: desc for compound, desc in flavornet.values()}
    # Seuils : uniquement flavordb2_thresholds (source sourcée), JAMAIS l'amorce
    # manuelle reference.MOLECULES — voir ingest_flavordb2 et le README pour le
    # pourquoi (mélanger un seuil réel et un seuil deviné casserait la
    # traçabilité du palier de poids). WHERE explicite : la table contient aussi
    # des lignes à seuil NULL (CAS traités par ingest_flavordb2 sans seuil publié,
    # pour ne pas les retenter à chaque run) — pas des seuils à utiliser.
    thresholds = {r["compound"]: r["threshold_ppb"] for r in
                 con.execute("SELECT compound, threshold_ppb FROM flavordb2_thresholds "
                             "WHERE threshold_ppb IS NOT NULL")}

    fdf = pd.read_csv(_find_csv(foodb_csv_dir, "food"), usecols=["id", "name"])
    # Liste de (food_id, note, is_curated), PAS un dict food_id->note : un même
    # aliment peut légitimement porter DEUX notes distinctes (ex. "mangue",
    # curée + fusionnée à l'amorce littérature, ET "mango", auto-dérivée pure
    # FooDB) — la surcharge de nommage `notes` est additive, pas un
    # remplacement. Un dict écraserait silencieusement l'une des deux.
    food_entries: list[tuple[int, str, bool]] = []
    for note, food_name in notes.items():
        m = fdf[fdf["name"].str.lower() == food_name.lower()]
        if m.empty:
            print(f"  !! {note!r} : aliment {food_name!r} introuvable dans Food.csv, ignoré")
            continue
        food_entries.append((int(m.iloc[0]["id"]), note, True))
    n_curated = len(food_entries)
    if all_foods:
        for _, r in fdf.iterrows():
            food_entries.append((int(r["id"]), str(r["name"]).strip().lower(), False))
    if not food_entries:
        print("Aucun aliment résolu, rien à ingérer."); con.close(); return

    cdf = pd.read_csv(_find_csv(foodb_csv_dir, "compound"))
    cas_col = _resolve_cas_column(cdf)
    cdf["_cas"] = cdf[cas_col].astype(str).str.strip()
    cdf = cdf[cdf["_cas"].isin(whitelist)]
    compound_id_to_cas = dict(zip(cdf["id"], cdf["_cas"]))
    target_food_ids = {fid for fid, _, _ in food_entries}
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
    # groupby unique (au lieu d'un filtre par aliment répété dans la boucle) :
    # nécessaire dès que food_entries passe de 7 à ~1000+ entrées.
    by_food = {fid: g for fid, g in best.groupby("food_id")}

    written, no_hit, no_signal, kept_curated, kept_auto = 0, [], [], 0, 0
    for food_id, note, is_curated in food_entries:
        sub = by_food.get(food_id)
        if sub is None or sub.empty:
            no_hit.append(note); continue
        recs = []
        for _, r in sub.iterrows():
            cas = compound_id_to_cas[r["source_id"]]
            compound = whitelist[cas]
            recs.append((compound, r["mass"] if pd.notna(r["mass"]) else None,
                        thresholds.get(compound)))
        # Filtre de distinctivité (notes auto-dérivées uniquement) : vérifié sur le
        # dump réel (foodb_impact_check-style) que deux aliments sans rapport
        # (capers/chervil) partagent 99,2% de leurs composés listés (5961/6011) —
        # FooDB cite souvent un gabarit générique plutôt qu'une composition mesurée.
        # Sans concentration réelle, tout tombe en palier seuil/présence, calculé
        # depuis la table de seuils GLOBALE : deux aliments au même ensemble de
        # composés produisent alors des poids identiques, sans signal food-specific.
        # Exiger >=1 composé en palier concentration (mesure réelle pour CET aliment,
        # pas un seuil partagé) écarte ce bruit.
        if not is_curated:
            has_conc = any(mass and mass > 0 for _, mass, _ in recs)
            if not has_conc:
                no_signal.append(note); continue
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
        if is_curated:
            kept_curated += 1
        else:
            kept_auto += 1
    con.commit(); con.close()
    # kept_curated + kept_auto (comptés au fil de la boucle, pas dérivés par
    # soustraction) : une version antérieure dérivait "aliments gardés" par
    # soustraction et avait donné un total FAUX (647 au lieu de 506 sur un run
    # réel — un des deux motifs d'exclusion n'était jamais soustrait).
    print(f"FooDB : {written} liens note->molécule ingérés sur "
         f"{kept_curated + kept_auto} aliments "
         f"({kept_curated} curés, {kept_auto} auto-dérivés distinctifs de Food.csv).")
    if no_signal:
        print(f"  {len(no_signal)} aliments auto-dérivés écartés : aucun composé à concentration "
             f"mesurée (que du bruit générique FooDB, cf. docstring).")
    if no_hit:
        if len(no_hit) <= 15:
            print("  aucun composé whitelisté pour :", ", ".join(no_hit))
        else:
            print(f"  aucun composé whitelisté pour {len(no_hit)} aliments (aucun composé "
                 f"Flavornet trouvé, ignorés).")
