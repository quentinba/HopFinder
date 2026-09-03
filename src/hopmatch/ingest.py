"""
Ingestion des données dans aromahops.db (+ recipes.db pour ingest_mmum, D4).

RÉEL (tourne ici) :
  - ingest_mmum          : moissonne maischemalzundmehr.de (réseau ; requests seul), corpus
                           BRUT de recettes -> recipes.db (fichier SÉPARÉ, jamais aromahops.db)
  - reconcile_mmum_hop_varieties : résout recipe_hops.hop_name -> variety dans recipes.db
                           (réseau pour le dictionnaire d'alias beer-analytics, cache-first ;
                           aromahops.db lue seule, jamais modifiée)
  - compute_frequent_hop_combinations : combinaisons de houblons réellement co-observées
                           en recette (lit recipes.db, écrit hop_combinations dans
                           aromahops.db -- pas de réseau)
  - compute_hop_addition_timing : répartition réelle des additions d'un houblon sur les
                           11 classes chronologiques (lit recipes.db, écrit
                           hop_addition_timing dans aromahops.db -- pas de réseau)
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
from .schema import (init_db, validate_and_repair, DROP_COMPOUNDS, ensure_table, ensure_columns,
                     BEER_STYLES_SCHEMA, HOP_BEER_STYLES_SCHEMA, HOP_IDENTITY_COLUMNS,
                     HOP_DESCRIPTION_COLUMNS, STYLE_RECIPE_STATS_SCHEMA, STYLE_HOP_USAGE_SCHEMA,
                     STYLE_HOP_PAIRINGS_SCHEMA, HOP_USAGE_STATS_SCHEMA)

MAPPINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "mappings")


def _load_yaml_mapping(filename: str) -> dict[str, str]:
    """Charge un fichier `data/mappings/*.yaml` (dict plat str->str) --
    voir `crawl_barthhaas` (T79, 2026-08-22) pour son usage : mapping
    revu et confirmé par l'utilisateur, jamais régénéré/deviné à
    l'exécution. Import `yaml` local (extra `crawl`, comme
    `requests`/`beautifulsoup4` -- inutile pour l'app déployée qui ne lit
    que la base déjà construite, jamais ce fichier)."""
    import yaml
    with open(os.path.join(MAPPINGS_DIR, filename), encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


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
        con.execute(
            "INSERT INTO hops (variety, name, region, sources, purpose) VALUES (?,?,?,?,?)",
            (variety, name, region, source, None))

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
    jamais rétroactivement sur des lignes déjà écrites). Utilisé une
    première fois (2026-08-19) pour les 5 paires trouvées à l'époque
    (Challenger, Fuggle, Hallertauer Tradition, Hersbrucker Spät, Target --
    voir `tools/merge_duplicate_hops.py`), puis étendue (2026-08-29,
    signalé par l'utilisateur en direct sur l'onglet Survivables -- barres
    "Dolcita"/"Perle Germany" mal ordonnées) aux 4 tables T85-T88 qui
    n'existaient pas encore au premier passage (`hop_usage_stats`,
    `hop_beer_styles`, `style_hop_usage`, `style_hop_pairings`) : 2
    nouvelles paires réelles trouvées (Dolcita US, Perle Germany), toutes
    deux avec des lignes orphelines dans au moins une de ces 4 tables que
    l'ancienne version de cette fonction aurait silencieusement perdues
    (ni migrées vers `keep`, ni supprimées avec `drop` -- restées
    référencer une `variety` disparue de `hops`). Root cause de CES deux
    paires spécifiques non élucidée avec certitude (le garde-fou
    `_find_variety_by_name_region` est appelé symétriquement par les deux
    crawlers et semble correct à la lecture) -- traité comme les 5
    précédentes, en réparation rétroactive plutôt qu'en correctif
    d'ingestion, faute d'avoir pu reproduire la séquence exacte
    d'ingestion historique.

    Déplace TOUTES les tables référençant `variety` (composition,
    descripteurs, roue d'arôme, associations houblon<->houblon dans les DEUX
    sens, usage par étape de procédé et par style, styles éditoriaux)
    vers `keep`, fusionne `sources` (union) et `purpose`
    (`COALESCE(keep, drop)` -- un seul des deux avait une valeur réelle dans
    les 5 cas vérifiés, jamais un conflit à trancher), puis supprime la ligne
    `drop`. `INSERT OR IGNORE`/`UPDATE OR IGNORE` partout (évite un conflit
    si `keep` a par hasard déjà une ligne pour la même clé que `drop` -- ne
    devrait pas arriver entre deux sources différentes vu le schéma EAV par
    source, mais reste un filet de sécurité plutôt qu'un crash)."""
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
    # T85-T88 (beer-analytics.com, épique B) : ajoutées après le premier
    # passage de cette fonction (2026-08-19), voir docstring. `hop_usage_
    # stats`/`hop_beer_styles` ont `variety` dans leur clé primaire (même
    # schéma INSERT OR IGNORE + DELETE que les 6 tables ci-dessus).
    # `style_hop_usage`/`style_hop_pairings` clés sur (style_slug, hop_name,
    # ...) SANS `variety` -- un simple UPDATE suffit, `OR IGNORE` en filet
    # de sécurité si jamais `keep` ET `drop` avaient chacun une ligne pour
    # la même clé primaire (non observé sur les 2 paires réelles traitées
    # ici, mais pas structurellement impossible).
    con.execute(
        "INSERT OR IGNORE INTO hop_usage_stats SELECT ?, hop_name, use_type, recipes_count, "
        "amount_q1, amount_median, amount_q3, source, fetched_at "
        "FROM hop_usage_stats WHERE variety=?", (keep, drop))
    con.execute(
        "INSERT OR IGNORE INTO hop_beer_styles SELECT ?, style_label, style_id, source "
        "FROM hop_beer_styles WHERE variety=?", (keep, drop))
    con.execute("UPDATE OR IGNORE style_hop_usage SET variety=? WHERE variety=?", (keep, drop))
    con.execute("UPDATE OR IGNORE style_hop_pairings SET variety=? WHERE variety=?", (keep, drop))

    srcs = sorted(set(keep_row["sources"].split(",")) | set(drop_row["sources"].split(",")))
    purpose = keep_row["purpose"] if keep_row["purpose"] is not None else drop_row["purpose"]
    con.execute("UPDATE hops SET sources=?, purpose=? WHERE variety=?",
               (",".join(srcs), purpose, keep))

    for table in ("hop_composition", "hop_descriptors", "hop_aroma_intensity",
                  "hop_similar", "hop_pairings", "hop_substitutions",
                  "hop_usage_stats", "hop_beer_styles"):
        con.execute(f"DELETE FROM {table} WHERE variety=?", (drop,))
    con.execute("DELETE FROM hop_similar WHERE similar_variety=?", (drop,))
    con.execute("DELETE FROM style_hop_usage WHERE variety=?", (drop,))
    con.execute("DELETE FROM style_hop_pairings WHERE variety=?", (drop,))
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

    Descripteurs BarthHaas (T79, 2026-08-22, demande utilisateur explicite,
    après capture d'écran montrant des descripteurs réels ("Lemon",
    "Cranberry"...) jamais trouvés jusque-là) : `parsers.parse_descriptors`
    (paragraphe "AROMA PROFILE") reste appelé pour compatibilité mais ne
    renvoie quasi jamais rien sur le site réel (texte libre, jamais miné —
    voir sa docstring). Les VRAIS descripteurs viennent de deux extractions
    structurées DISTINCTES sur la même page, jamais essayées avant :
    `parsers.parse_barthhaas_tastes` (liste `<li>` qualitative, ex.
    "Lemon", "Cranberry") -> `hop_descriptors`, et `parsers.
    parse_barthhaas_aroma_wheel` (roue quantitative 12 catégories) ->
    `hop_aroma_intensity`. Chacune passe par un mapping REVU ET CONFIRMÉ
    PAR L'UTILISATEUR (`data/mappings/*.yaml`, jamais deviné/régénéré à
    l'exécution) avant insertion -- voir `_load_yaml_mapping` et
    CLAUDE.md, T79, pour le détail complet des décisions.
    """
    import time, re, requests
    from bs4 import BeautifulSoup
    from .schema import connect
    BASE = "https://www.barthhaas.com"
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()
    desc_map = _load_yaml_mapping("barthhaas_descriptor_aliases.yaml")
    category_map = _load_yaml_mapping("barthhaas_aroma_wheel_categories.yaml")
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
                # T123 (2026-08-27) : suffixe "Hops" nu (habillage marketing
                # de leur <h1>, ex. "Luna Hops") retiré via `parsers.
                # strip_bare_hops_suffix` -- voir sa docstring pour la garde
                # contre les vrais qualificatifs à tiret ("- NZ Hops").
                name = (parsers.strip_trademark_symbols(parsers.strip_bare_hops_suffix(h1_title))
                       or slug.replace("-", " ").title())
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
                # T79 : mots bruts ("lemon", "cranberry"...) mappés via le
                # fichier revu par l'utilisateur -- mot absent du mapping =
                # utilisé tel quel (déjà canonique, ou nouveau terme
                # délibérément gardé, voir data/mappings/*.yaml).
                tastes = parsers.parse_barthhaas_tastes(html)
                descriptors = sorted({desc_map.get(word, word) for _, word in tastes})
                # T79 (2026-08-23, bug trouvé en direct par l'utilisateur : un
                # descripteur "analyses" sans rapport avec l'arôme, présent sur
                # 4 houblons). `parsers.parse_descriptors(text)` -- l'ancien
                # parseur "paragraphe AROMA PROFILE" -- retiré d'ici : sur le
                # texte APLATI de la page réelle (`soup.get_text`), la barre
                # d'onglets ("Aroma Profile" / "Analyses", tabs SANS rapport
                # avec le contenu arôme) suit immédiatement le sous-titre
                # "Typical Aroma Profile" que la fonction saute déjà -- "Analyses"
                # (un seul mot, ni virgule ni point) passe alors ses deux
                # garde-fous et ressort comme un faux descripteur à un mot.
                # Vérifié en direct (bobek/brewers-gold/pahtotm/saaz-late) :
                # confirmé, ce n'est JAMAIS le vrai contenu "AROMA PROFILE"
                # (le site n'expose plus cette section en liste courte depuis
                # T79, voir le docstring de la fonction) -- toujours redondant
                # ou faux sur le crawl réel, jamais une perte de données utile.
                # `parse_descriptors` reste utilisé par `build_from_fixtures`
                # (fixtures figées, contrôlées, format court d'origine).
                wheel = parsers.parse_barthhaas_aroma_wheel(html) or {}
                aroma_intensity = {category_map[cat]: val for cat, val in wheel.items()
                                   if cat in category_map}
                _ingest_variety(con, variety, name, region, comp, descriptors, "barthhaas",
                                aroma_intensity=aroma_intensity)
                print(f"  ok {slug} ({len(comp)} composés, {len(descriptors)} descripteurs, "
                     f"{len(aroma_intensity)} catégories roue)"
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


# T83 (2026-08-27) : houblon -> style éditorial, deux sources (Yakima
# `beer_types`, BeerMaverick "Beer Styles using X Hops") -- même table,
# jamais fusionnées (source tracée par ligne). Partagé entre `crawl_yakima`
# et `ingest_beermaverick` pour ne pas dupliquer la résolution via T84.
def _write_hop_beer_styles(con: sqlite3.Connection, variety: str, labels: list[str],
                           source: str, alias_map: dict[str, str | None]) -> None:
    """Écrit une ligne `hop_beer_styles` par étiquette BRUTE de `labels` --
    `style_id` résolu via `alias_map` (`data/mappings/beer_style_aliases.
    yaml`, T84) SEULEMENT si l'étiquette y est explicitement listée, `NULL`
    sinon (une étiquette absente du YAML -- pas encore triée à la main --
    reste `NULL`, jamais devinée par fuzzy-matching)."""
    for label in labels:
        style_id = alias_map.get(label)
        con.execute("INSERT OR REPLACE INTO hop_beer_styles VALUES (?,?,?,?)",
                    (variety, label, style_id, source))


# --------------------------------------------------------------------------- #
# Crawl Yakima Chief (réseau réel) — via Algolia, pas de HTML/checkpoint
# --------------------------------------------------------------------------- #
def _bool_to_sqlite(value) -> int | None:
    """bool Python -> 0/1 SQLite, `None` inchangé (T106) -- jamais de `0` par
    défaut pour une donnée absente, qui affirmerait à tort « non
    expérimental »/« non bio »/« pas un blend »."""
    return None if value is None else int(bool(value))


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
    else:
        ensure_table(con, "hop_beer_styles", HOP_BEER_STYLES_SCHEMA)  # base existante : ne PAS la vider
        ensure_columns(con, "hops", HOP_IDENTITY_COLUMNS)  # T106 : ajoute cultivar/breeder/... sans vider hops
        ensure_columns(con, "hops", HOP_DESCRIPTION_COLUMNS)  # T107 : ajoute description/description_source
    style_aliases = _load_yaml_mapping("beer_style_aliases.yaml")

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
        # T106 : métadonnées d'identité (imported_fields.cultivar/experimental/
        # organic/blend) -- SEULE Yakima les porte (vérifié en direct : absentes
        # de imported_fields BarthHaas). Booléens Python -> 0/1 SQLite ; `cultivar`
        # absent (None) pour les variétés désignées seulement par un code HBC/YCH
        # (vérifié en direct, 4/153) -> NULL, jamais fabriqué.
        imported = hit.get("imported_fields") or {}
        con.execute(
            "UPDATE hops SET cultivar=?, is_experimental=?, is_organic=?, is_blend=? WHERE variety=?",
            (imported.get("cultivar"),
             _bool_to_sqlite(imported.get("experimental")),
             _bool_to_sqlite(imported.get("organic")),
             _bool_to_sqlite(imported.get("blend")),
             variety))
        # T107 : description éditoriale (imported_fields.description, HTML réel
        # -- vraies balises <p>/<br>/<em>/<a>, vérifié en direct sur 153/153
        # variétés) -- nettoyée en markdown par parsers.clean_yakima_description,
        # jamais le HTML brut stocké/affiché. Texte marketing d'un vendeur,
        # jamais présenté comme neutre (attribution GUI explicite, voir _browse).
        description = parsers.clean_yakima_description(imported.get("description"))
        if description is not None:
            con.execute("UPDATE hops SET description=?, description_source=? WHERE variety=?",
                       (description, "yakima", variety))
        beer_types = imported.get("beer_types") or []
        if beer_types:
            _write_hop_beer_styles(con, variety, beer_types, "yakima", style_aliases)
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


_CULTIVAR_BASE_NAME_RE = re.compile(r" - | \(")


def _cultivar_base_name(name: str) -> str:
    """Nom de cultivar sans suffixe de marque/licencié (T106) -- ex. « Kohatu -
    NZ Hops » -> « Kohatu », « Pacifica (Marque Déposée) - MacHops » ->
    « Pacifica ». `hops` porte plusieurs lignes distinctes pour un même
    cultivar quand il est vendu sous des crops/marques différents (ex.
    « Amarillo » (US, barthhaas+yakima) ET « Amarillo » (Germany, yakima
    seul) partagent le même `name` ; « Motueka - NZ Hops » et « Motueka -
    MacHops » ne diffèrent que par le licencié Yakima) -- même généalogie,
    donc breeder/release_year/pedigree (`data/mappings/hop_breeder_
    pedigree.yaml`, T106) doivent s'appliquer aux DEUX lignes, pas seulement
    à celle que `_resolve_hop_variety` a fait correspondre à la page
    BeerMaverick source. Séparateur strict (` - `/` (`, espace obligatoire) --
    ne coupe jamais un nom réellement composé d'un trait d'union sans espace
    (ex. « Wai-iti », vérifié en direct : aucun faux positif sur les 203
    variétés réelles de la base)."""
    return _CULTIVAR_BASE_NAME_RE.split(name, maxsplit=1)[0].strip()


def _write_hop_identity(con, breeder_pedigree: dict) -> int:
    """T106 : applique `breeder_pedigree` ({cultivar de base: {breeder,
    release_year, pedigree}}, curation manuelle -- voir data/mappings/hop_
    breeder_pedigree.yaml, prose BeerMaverick trop hétérogène pour un
    parseur fiable) à TOUTES les lignes `hops` existantes, par CULTIVAR DE
    BASE (`_cultivar_base_name`) -- pas seulement aux variétés qu'un crawl a
    individuellement résolues depuis une page BeerMaverick : une variété-
    sœur (même cultivar, crop/licencié différent, ex. Motueka NZ Hops/
    MacHops) partage la même généalogie et doit recevoir la même donnée.
    Retourne le nombre de variétés mises à jour."""
    n = 0
    for row in con.execute("SELECT variety, name FROM hops"):
        entry = breeder_pedigree.get(_cultivar_base_name(row["name"]))
        if not entry:
            continue
        con.execute(
            "UPDATE hops SET breeder=?, release_year=?, pedigree=? WHERE variety=?",
            (entry.get("breeder"), entry.get("release_year"), entry.get("pedigree"), row["variety"]))
        n += 1
    return n


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
    else:
        ensure_table(con, "hop_beer_styles", HOP_BEER_STYLES_SCHEMA)  # base existante : ne PAS la vider
        ensure_columns(con, "hops", HOP_IDENTITY_COLUMNS)  # T106 : ajoute cultivar/breeder/... sans vider hops
    style_aliases = _load_yaml_mapping("beer_style_aliases.yaml")

    sitemap = requests.get(f"{BASE}/beerm-sitemap.xml", timeout=timeout,
                           headers={"User-Agent": "hopmatch/0.1 (research)"}).text
    slugs = sorted(set(re.findall(r"beermaverick\.com/hop/([a-z0-9-]+)/", sitemap)))
    if limit:
        slugs = slugs[:limit]
    print(f"BeerMaverick : {len(slugs)} pages houblon (sitemap)")

    index = _build_hop_name_index(con)
    covered = skipped = n_pairings = n_subs = n_tags = n_purpose = n_styles = 0
    for i, slug in enumerate(slugs, 1):
        variety = _resolve_hop_variety(index, slug)
        if not variety:
            skipped += 1
            continue
        try:
            resp = requests.get(f"{BASE}/hop/{slug}/", timeout=timeout,
                               headers={"User-Agent": "hopmatch/0.1 (research)"})
            # BeerMaverick ne déclare pas de charset dans son en-tête
            # Content-Type ("text/html" nu) -- `requests` retombe alors sur
            # ISO-8859-1 par défaut HTTP (RFC 2616) même si le contenu réel
            # est UTF-8, corrompant tout caractère non-ASCII (ex. "Kölsch"
            # -> "KÃ¶lsch", trouvé en vérifiant les styles T83 en direct sur
            # la base réelle, 2026-08-27). `.apparent_encoding` détecte le
            # VRAI encodage par analyse du contenu (chardet/charset-
            # normalizer), fiable ici (contenu HTML normal, pas binaire).
            resp.encoding = resp.apparent_encoding
            html = resp.text
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
        styles = parsers.parse_beermaverick_styles(html)
        if styles:
            _write_hop_beer_styles(con, variety, styles, "beermaverick", style_aliases)
            n_styles += len(styles)
        covered += 1
        if i % 10 == 0:
            con.commit()
        time.sleep(sleep)

    n_identity = _write_hop_identity(con, _load_yaml_mapping("hop_breeder_pedigree.yaml"))

    con.commit(); con.close()
    print(f"  identité (breeder/release_year/pedigree) : {n_identity} variétés")
    print(f"  {covered} variétés couvertes ({skipped} pages sans équivalent local), "
         f"{n_pairings} pairings, {n_subs} substitutions, {n_tags} descripteurs, "
         f"{n_purpose} purpose (aromatic/bittering/both), {n_styles} style labels.")


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


# --------------------------------------------------------------------------- #
# Styles BJCP (T81, épique A)
# --------------------------------------------------------------------------- #
BJCP_STYLES_URL_TEMPLATE = (
    "https://raw.githubusercontent.com/beerjson/bjcp-json/main/styles/"
    "bjcp_styleguide-{year}.json"
)
BJCP_CACHE_DIR = "data/cache/bjcp"
# Seul le millésime 2021 existe réellement dans `beerjson/bjcp-json` (vérifié
# en direct le 2026-08-27 -- voir BACKLOG.md T81). Un `--year 2015` doit
# échouer avec un message clair, jamais retomber silencieusement sur 2021 :
# vérifié AVANT tout appel réseau (pas de dépendance à un 404 distant pour
# détecter ce cas).
BJCP_SUPPORTED_YEARS = {2021}


def download_bjcp_styles(year: int = 2021, dest_dir: str = BJCP_CACHE_DIR,
                         force: bool = False) -> str:
    """
    Télécharge le styleguide BJCP (`beerjson/bjcp-json`, BeerJSON 2.01) pour
    `year` s'il n'est pas déjà en cache, et renvoie le chemin du fichier JSON
    local. Jamais committé (même pattern que `download_foodb_dump`) --
    `dest_dir` par défaut sous `data/cache/bjcp/`, un fichier par millésime
    (`bjcp_styleguide-2021.json`) pour ne jamais fusionner deux millésimes au
    téléchargement.

    Idempotent : si le fichier est déjà présent, ne retélécharge rien (sauf
    `force=True`). Écrit dans un fichier temporaire puis renomme (jamais
    directement dans `dest_dir`) pour ne jamais laisser un fichier partiel/
    corrompu passer pour un cache valide si le téléchargement est interrompu.
    """
    import requests
    import tempfile

    if year not in BJCP_SUPPORTED_YEARS:
        raise ValueError(
            f"BJCP {year} : ce millésime n'existe pas dans beerjson/bjcp-json "
            f"(seuls {sorted(BJCP_SUPPORTED_YEARS)} sont disponibles) -- "
            f"vérifié le 2026-08-27, voir BACKLOG.md T81. Pas de repli "
            f"silencieux sur 2021.")

    dest_path = os.path.join(dest_dir, f"bjcp_styleguide-{year}.json")
    if os.path.exists(dest_path) and not force:
        print(f"BJCP {year} : déjà en cache ({dest_path!r}), pas de retéléchargement.")
        return dest_path

    url = BJCP_STYLES_URL_TEMPLATE.format(year=year)
    print(f"BJCP {year} : téléchargement depuis {url!r}...")
    os.makedirs(dest_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=dest_dir)
    os.close(fd)
    try:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "hopmatch/0.1 (research)"})
        resp.raise_for_status()
        with open(tmp_path, "wb") as f:
            f.write(resp.content)
        os.replace(tmp_path, dest_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    print(f"BJCP {year} : {dest_path!r} prêt.")
    return dest_path


def ingest_beer_styles(out_db: str, year: int = 2021,
                       cache_dir: str = BJCP_CACHE_DIR, force_download: bool = False) -> None:
    """
    Télécharge (si besoin) et ingère le styleguide BJCP `year` dans
    `beer_styles` (table T81) -- `parsers.parse_beerjson_styles` fait le gros
    du travail, cette fonction ajoute `guideline_year` (le parseur ne sait
    pas quel millésime il lit) et écrit en base.

    Millésimes JAMAIS fusionnés (même règle que Yakima/BarthHaas) : chaque
    appel avec un `year` différent ajoute ses propres lignes via `INSERT OR
    REPLACE` sur (style_id, guideline_year), sans toucher aux autres
    millésimes déjà en base.
    """
    import json

    path = download_bjcp_styles(year=year, dest_dir=cache_dir, force=force_download)
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    rows = parsers.parse_beerjson_styles(payload)

    con = sqlite3.connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con)  # base totalement neuve -- même garde que les autres crawlers
    else:
        ensure_table(con, "beer_styles", BEER_STYLES_SCHEMA)  # base existante : ne PAS la vider
    for row in rows:
        con.execute(
            "INSERT OR REPLACE INTO beer_styles VALUES "
            "(:style_id, :guideline_year, :category_id, :category, :name, :type, :tags, "
            ":og_min, :og_max, :fg_min, :fg_max, :abv_min, :abv_max, :ibu_min, :ibu_max, "
            ":srm_min, :srm_max, :overall_impression, :aroma, :appearance, :flavor, "
            ":mouthfeel, :comments, :history, :ingredients, :style_comparison, :examples, "
            ":category_description, :source)",
            {**row, "guideline_year": year})
    con.commit()
    n_no_vitals = sum(1 for r in rows if r["og_min"] is None and r["ibu_min"] is None
                      and r["abv_min"] is None and r["srm_min"] is None and r["fg_min"] is None)
    print(f"BJCP {year} : {len(rows)} styles ingérés dans {out_db!r} "
         f"({n_no_vitals} sans vital stats, héritent du style de base).")
    con.close()


# --------------------------------------------------------------------------- #
# beer-analytics.com (T85, épique B) -- statistiques de recettes publiées
# --------------------------------------------------------------------------- #
BEER_ANALYTICS_BASE = "https://www.beer-analytics.com"
BEER_ANALYTICS_CACHE_DIR = "data/cache/beer_analytics"

# chart -> metric stockée dans style_recipe_stats.metric
BEER_ANALYTICS_HISTOGRAM_CHARTS = {
    "abv-histogram": "abv",
    "ibu-histogram": "ibu",
    "original-gravity-histogram": "og",
    "final-gravity-histogram": "fg",
    "color-srm-histogram": "srm",
}

# page de style : deux segments après /styles/ (catégorie + style), jamais la
# page catégorie seule (un seul segment, ex. /styles/ipa/) ni l'index
# /styles/ -- vérifié en direct sur le sitemap réel (123 URLs de style ;
# un premier comptage à 159 incluait par erreur les pages catégorie seules,
# corrigé T85 le 2026-08-28, voir BACKLOG.md).
_BA_STYLE_PAGE_RE = re.compile(
    r"https://www\.beer-analytics\.com(/styles/[a-z0-9-]+/[a-z0-9-]+/)")

# page de houblon : /hops/<purpose>/<slug>/ -- purpose vaut aroma/bittering/
# dual-purpose (435 pages réelles), JAMAIS deviné (T88, lu depuis le
# sitemap). ⚠ Exclut explicitement /hops/flavors/<terme>/ (184 pages) --
# ce ne sont PAS des houblons mais des pages de DESCRIPTEUR D'ARÔME
# (ex. /hops/flavors/apricot/, /hops/flavors/black-pepper/), vérifié en
# direct sur le sitemap réel.
_BA_HOP_PAGE_RE = re.compile(
    r"https://www\.beer-analytics\.com(/hops/(?!flavors/)[a-z0-9-]+/[a-z0-9-]+/)")


def _beer_analytics_cache_filename(path: str) -> str:
    """Chemin `path` (ex. `/styles/ipa/american-ipa/charts/abv-histogram.
    json`, ou avec query string T86 `.../popular-hops.json?filter=aroma`)
    aplati en nom de fichier cache -- `/` -> `_`, extension du fichier
    conservée (déterminée sur la partie AVANT `?`, jamais après -- bug réel
    trouvé en direct : sans ça, `....json?filter=aroma` ne se termine plus
    par `.json` littéralement, tombait dans le repli `.html` alors que le
    contenu réel est du JSON). Query string sanitisée en suffixe de nom de
    fichier (`?`/`=`/`&` -> `_`, séparateur `__`) plutôt qu'ignorée -- deux
    filtres différents du même chart (`?filter=aroma` vs `?filter=
    bittering`) doivent avoir des entrées de cache DISTINCTES, jamais
    partager la même (collision réelle sinon, ces deux URLs renvoient des
    payloads différents, vérifié en direct T86)."""
    base, _, query = path.partition("?")
    last_segment = base.rsplit("/", 1)[-1]
    if "." in last_segment:
        stem, ext = base.rsplit(".", 1)
    else:
        stem, ext = base, "html"
    flat = stem.strip("/").replace("/", "_")
    if query:
        flat += "__" + re.sub(r"[^a-zA-Z0-9_-]", "_", query)
    return f"{flat}.{ext}"


def _beer_analytics_fetch(path: str, cache_dir: str = BEER_ANALYTICS_CACHE_DIR,
                          timeout: float = 30.0, sleep: float = 1.0) -> str:
    """GET cache-first sur `BEER_ANALYTICS_BASE + path` (T85/T89 : cache
    disque OBLIGATOIRE, une seule passe réelle, `User-Agent` identifiable).
    Aucun délai sur un hit de cache -- seul un fetch réseau réel attend
    `sleep` secondes. Écrit le cache via fichier temporaire + `os.replace`
    (même garde que `download_bjcp_styles`) : un téléchargement interrompu ne
    doit jamais laisser un fichier partiel passer pour un cache valide.
    Utilisée aussi bien pour les pages HTML de style (découverte des charts)
    que pour les charts JSON eux-mêmes (voir `_beer_analytics_get`) -- même
    mécanisme de cache pour les deux, le ticket ne distinguait que les
    charts mais rien ne justifie de refetcher les pages HTML à chaque run."""
    import tempfile
    import time

    import requests

    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, _beer_analytics_cache_filename(path))
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return f.read()

    resp = requests.get(BEER_ANALYTICS_BASE + path, timeout=timeout,
                        headers={"User-Agent": "hopmatch/0.1 (research)"})
    resp.raise_for_status()
    text = resp.text
    fd, tmp_path = tempfile.mkstemp(dir=cache_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, cache_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    time.sleep(sleep)
    return text


def _beer_analytics_get(path: str, **kwargs) -> dict:
    """`_beer_analytics_fetch` + `json.loads` -- pour les endpoints charts
    (toujours JSON), voir `parsers.plotly_traces`/`parse_pandas_interval`
    pour l'exploitation du payload."""
    import json
    return json.loads(_beer_analytics_fetch(path, **kwargs))


def ingest_beer_analytics(out_db: str, limit: int | None = None, sleep: float = 1.0,
                          timeout: float = 30.0) -> None:
    """
    beer-analytics.com (T85, fondation de l'épique B) : distributions RÉELLES
    (ABV/IBU/OG/FG/SRM) observées dans des recettes homebrew publiées, par
    style -- table `style_recipe_stats`. Agrégateur de recettes, PAS du BJCP
    (`beer_styles`) ni une mesure de labo -- réserve à afficher partout où
    cette donnée apparaît (T89).

    URLs de charts jamais construites à la main (`parsers.discover_beer_
    analytics_charts`, voir sa docstring) : parsées depuis le HTML de chaque
    page de style (`data-chart="..."`), le segment de catégorie de l'URL
    diffère du slug de page affiché.

    `style_id` résolu via `data/mappings/beer_style_aliases.yaml` (T84, même
    fichier, nouvel usage sur le nom de style anglais `<h1>` -- voir
    `parsers.parse_beer_analytics_style_name`) -- `NULL` si absent du fichier
    ou non résolu, jamais deviné par similarité de texte.

    Histogrammes PRÉ-BINNÉS avec outliers déjà retirés côté beer-analytics --
    `style_recipe_stats` stocke les bins bruts (`bin_low`/`bin_high`/`count`),
    jamais un percentile dérivé (impossible à calculer honnêtement depuis des
    bins agrégés, voir CLAUDE.md/BACKLOG.md T85).
    """
    from .schema import connect
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()
    else:
        ensure_table(con, "style_recipe_stats", STYLE_RECIPE_STATS_SCHEMA)  # base existante : ne PAS la vider
    style_aliases = _load_yaml_mapping("beer_style_aliases.yaml")

    sitemap = _beer_analytics_fetch("/sitemap.xml", timeout=timeout, sleep=sleep)
    style_paths = sorted(set(_BA_STYLE_PAGE_RE.findall(sitemap)))
    if limit:
        style_paths = style_paths[:limit]
    print(f"beer-analytics : {len(style_paths)} pages de style (sitemap)")

    from datetime import datetime, timezone
    fetched_at = datetime.now(timezone.utc).isoformat()

    n_resolved = n_unresolved = n_bins = 0
    unresolved_names: set[str] = set()
    for i, style_path in enumerate(style_paths, 1):
        try:
            html = _beer_analytics_fetch(style_path, timeout=timeout, sleep=sleep)
        except Exception as e:  # noqa
            print(f"  !! {style_path}: {e}"); continue
        charts = parsers.discover_beer_analytics_charts(html)
        style_name = parsers.parse_beer_analytics_style_name(html)
        style_id = style_aliases.get(style_name) if style_name else None
        if style_id:
            n_resolved += 1
        else:
            n_unresolved += 1
            if style_name:
                unresolved_names.add(style_name)
        style_slug = style_path.strip("/").rsplit("/", 1)[-1]

        for chart_name, metric in BEER_ANALYTICS_HISTOGRAM_CHARTS.items():
            chart_path = charts.get(chart_name)
            if not chart_path:
                continue
            try:
                payload = _beer_analytics_get(chart_path, timeout=timeout, sleep=sleep)
            except Exception as e:  # noqa
                print(f"  !! {chart_path}: {e}"); continue
            traces = parsers.plotly_traces(payload)
            if not traces:
                continue
            trace = traces[0]
            for x, y in zip(trace["x"], trace["y"]):
                bin_low, bin_high = parsers.parse_pandas_interval(x)
                con.execute(
                    "INSERT OR REPLACE INTO style_recipe_stats VALUES (?,?,?,?,?,?,?,?)",
                    (style_id, style_slug, metric, bin_low, bin_high, int(y),
                     "beer-analytics", fetched_at))
                n_bins += 1
        if i % 10 == 0:
            con.commit()
    con.commit(); con.close()
    print(f"  {n_resolved} style_id résolus, {n_unresolved} non résolus, {n_bins} bins écrits")
    if unresolved_names:
        preview = ", ".join(sorted(unresolved_names)[:10])
        print(f"  noms de style non résolus (aperçu) : {preview}"
             + (f" (+{len(unresolved_names) - 10} autres)" if len(unresolved_names) > 10 else ""))


# --------------------------------------------------------------------------- #
# beer-analytics.com (T86) -- quels houblons pour quel style, et combien
# --------------------------------------------------------------------------- #
# Onglets réels "Used for" (Any/Bittering/Aroma/Dry-Hop) sur les charts
# popular-hops*.json -- vérifié en direct par reverse engineering du bundle
# JS (`/static/app.js`, T86) : PAS un filtrage client (le ticket envisageait
# les deux issues), ce sont de vraies requêtes GET avec un paramètre
# `?filter=<valeur>` sur la MÊME URL de chart (`Chart.load({filter: i})` ->
# `getRequest(this.chartUrl, {filter: i}, ...)` dans le bundle minifié).
# "any" = onglet "Any" = AUCUN paramètre (pas de filtre littéral "any" côté
# site). Ordre choisi = ordre de découverte du DOM (voir data-filter="" en
# premier dans le HTML de American IPA).
BEER_ANALYTICS_HOP_USAGE_TYPES = ("any", "bittering", "aroma", "dry-hop")


def ingest_style_hop_usage(out_db: str, limit: int | None = None, sleep: float = 1.0,
                           timeout: float = 30.0) -> None:
    """
    beer-analytics.com (T86) : quels houblons sont réellement utilisés pour
    un style, et combien -- table `style_hop_usage`. Réutilise les mêmes
    pages de style que T85 (`_beer_analytics_fetch` cache-first : aucun
    refetch réseau pour le HTML déjà en cache) mais ajoute deux charts par
    style ET par onglet d'usage (`BEER_ANALYTICS_HOP_USAGE_TYPES`, voir sa
    docstring) : `popular-hops.json` (part de recettes, SÉRIE TEMPORELLE --
    `parsers.parse_time_series_trace` garde la dernière valeur ET une
    moyenne 24 mois, deux questions différentes, jamais l'une n'écrase
    l'autre) et `popular-hops-amount.json` (dosage, boxplot q1/median/q3 via
    `parsers.parse_box_trace`).

    ⚠ `usage_type` fait partie de la clé primaire de `style_hop_usage`
    (`schema.STYLE_HOP_USAGE_SCHEMA`) -- absent du `CREATE TABLE` initialement
    écrit dans le ticket T86 (rédigé avant la vérification ci-dessus), ajouté
    une fois confirmé que la ventilation par usage est une vraie donnée
    distincte et pas un filtrage client (voir schema.py pour le détail).

    `style_id`/`variety` résolus comme T85/BeerMaverick (`data/mappings/
    beer_style_aliases.yaml`, `ingest._resolve_hop_variety`) -- `NULL` si non
    résolus, jamais deviné. `hop_name` reste TOUJOURS renseigné en texte brut
    même sans `variety` résolue (rien n'est perdu).
    """
    from datetime import datetime, timezone
    from .schema import connect
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()
    else:
        ensure_table(con, "style_hop_usage", STYLE_HOP_USAGE_SCHEMA)  # base existante : ne PAS la vider
    style_aliases = _load_yaml_mapping("beer_style_aliases.yaml")
    index = _build_hop_name_index(con)

    sitemap = _beer_analytics_fetch("/sitemap.xml", timeout=timeout, sleep=sleep)
    style_paths = sorted(set(_BA_STYLE_PAGE_RE.findall(sitemap)))
    if limit:
        style_paths = style_paths[:limit]
    print(f"beer-analytics (hop usage) : {len(style_paths)} pages de style (sitemap)")

    fetched_at = datetime.now(timezone.utc).isoformat()
    n_resolved_style = n_unresolved_style = n_rows = n_variety_resolved = n_variety_total = 0
    for i, style_path in enumerate(style_paths, 1):
        try:
            html = _beer_analytics_fetch(style_path, timeout=timeout, sleep=sleep)
        except Exception as e:  # noqa
            print(f"  !! {style_path}: {e}"); continue
        charts = parsers.discover_beer_analytics_charts(html)
        style_name = parsers.parse_beer_analytics_style_name(html)
        style_id = style_aliases.get(style_name) if style_name else None
        if style_id:
            n_resolved_style += 1
        else:
            n_unresolved_style += 1
        style_slug = style_path.strip("/").rsplit("/", 1)[-1]

        pct_path = charts.get("popular-hops")
        amount_path = charts.get("popular-hops-amount")
        if not pct_path and not amount_path:
            continue

        for usage_type in BEER_ANALYTICS_HOP_USAGE_TYPES:
            suffix = "" if usage_type == "any" else f"?filter={usage_type}"
            pct_by_hop: dict[str, tuple] = {}
            if pct_path:
                try:
                    payload = _beer_analytics_get(pct_path + suffix, timeout=timeout, sleep=sleep)
                    for trace in parsers.plotly_traces(payload):
                        pct_by_hop[trace["name"]] = parsers.parse_time_series_trace(trace)
                except Exception as e:  # noqa
                    print(f"  !! {pct_path}{suffix}: {e}")
            amount_by_hop: dict[str, tuple] = {}
            if amount_path:
                try:
                    payload = _beer_analytics_get(amount_path + suffix, timeout=timeout, sleep=sleep)
                    for trace in parsers.plotly_traces(payload):
                        amount_by_hop[trace["name"]] = parsers.parse_box_trace(trace)
                except Exception as e:  # noqa
                    print(f"  !! {amount_path}{suffix}: {e}")
            for hop_name in sorted(set(pct_by_hop) | set(amount_by_hop)):
                variety = _resolve_hop_variety(index, hop_name)
                n_variety_total += 1
                if variety:
                    n_variety_resolved += 1
                latest, avg24m = pct_by_hop.get(hop_name, (None, None))
                q1, median, q3 = amount_by_hop.get(hop_name, (None, None, None))
                con.execute(
                    "INSERT OR REPLACE INTO style_hop_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (style_slug, style_id, hop_name, variety, usage_type,
                     latest, avg24m, q1, median, q3, "beer-analytics", fetched_at))
                n_rows += 1
        if i % 10 == 0:
            con.commit()
    con.commit(); con.close()
    print(f"  {n_resolved_style} style_id résolus, {n_unresolved_style} non résolus")
    print(f"  {n_variety_resolved}/{n_variety_total} houblons résolus vers une variety, "
         f"{n_rows} lignes écrites")


# --------------------------------------------------------------------------- #
# beer-analytics.com (T87) -- paires de houblons réellement co-utilisées
# --------------------------------------------------------------------------- #
def ingest_style_hop_pairings(out_db: str, limit: int | None = None, sleep: float = 1.0,
                              timeout: float = 30.0) -> None:
    """
    beer-analytics.com (T87) : quelles paires de houblons sont réellement
    co-utilisées pour un style -- table `style_hop_pairings`. Réutilise les
    pages de style déjà en cache (T85/T86) mais UN SEUL chart par style,
    `hop-pairings.json` -- vérifié en direct : contrairement à `popular-
    hops*.json` (T86), cette section n'a PAS de `data-chart-navigation`
    (pas d'onglet any/aroma/bittering/dry-hop), une seule URL suffit.

    Une trace `box` par houblon partenaire (`parsers.parse_box_trace`, même
    format que `popular-hops-amount.json`) : `share_*` = distribution de la
    part de charge houblon (`amount_percent`) de CE partenaire dans les
    recettes qui combinent les deux houblons -- PAS une fréquence de
    recette. ⚠ Ce sont des PAIRES uniquement (`calculate_hop_pairings` côté
    beer-analytics = JOIN sur deux houblons distincts, seuil 20 recettes) --
    ne jamais dériver un triplet de trois paires ici, ce serait une
    invention (voir schema.STYLE_HOP_PAIRINGS_SCHEMA).

    `style_id`/`variety` résolus comme T85/T86 (`data/mappings/beer_style_
    aliases.yaml`, `ingest._resolve_hop_variety`), `NULL` si non résolus.
    """
    from datetime import datetime, timezone
    from .schema import connect
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()
    else:
        ensure_table(con, "style_hop_pairings", STYLE_HOP_PAIRINGS_SCHEMA)  # base existante : ne PAS la vider
    style_aliases = _load_yaml_mapping("beer_style_aliases.yaml")
    index = _build_hop_name_index(con)

    sitemap = _beer_analytics_fetch("/sitemap.xml", timeout=timeout, sleep=sleep)
    style_paths = sorted(set(_BA_STYLE_PAGE_RE.findall(sitemap)))
    if limit:
        style_paths = style_paths[:limit]
    print(f"beer-analytics (hop pairings) : {len(style_paths)} pages de style (sitemap)")

    fetched_at = datetime.now(timezone.utc).isoformat()
    n_resolved_style = n_unresolved_style = n_rows = n_variety_resolved = n_variety_total = 0
    for i, style_path in enumerate(style_paths, 1):
        try:
            html = _beer_analytics_fetch(style_path, timeout=timeout, sleep=sleep)
        except Exception as e:  # noqa
            print(f"  !! {style_path}: {e}"); continue
        charts = parsers.discover_beer_analytics_charts(html)
        style_name = parsers.parse_beer_analytics_style_name(html)
        style_id = style_aliases.get(style_name) if style_name else None
        if style_id:
            n_resolved_style += 1
        else:
            n_unresolved_style += 1
        style_slug = style_path.strip("/").rsplit("/", 1)[-1]

        pairings_path = charts.get("hop-pairings")
        if not pairings_path:
            continue
        try:
            payload = _beer_analytics_get(pairings_path, timeout=timeout, sleep=sleep)
        except Exception as e:  # noqa
            print(f"  !! {pairings_path}: {e}"); continue
        for trace in parsers.plotly_traces(payload):
            hop_name = trace.get("name")
            if not hop_name:
                continue
            variety = _resolve_hop_variety(index, hop_name)
            n_variety_total += 1
            if variety:
                n_variety_resolved += 1
            q1, median, q3 = parsers.parse_box_trace(trace)
            mean = (trace.get("mean") or [None])[0]
            con.execute(
                "INSERT OR REPLACE INTO style_hop_pairings VALUES (?,?,?,?,?,?,?,?,?,?)",
                (style_slug, style_id, hop_name, variety, q1, median, q3, mean,
                 "beer-analytics", fetched_at))
            n_rows += 1
        if i % 10 == 0:
            con.commit()
    con.commit(); con.close()
    print(f"  {n_resolved_style} style_id résolus, {n_unresolved_style} non résolus")
    print(f"  {n_variety_resolved}/{n_variety_total} houblons résolus vers une variety, "
         f"{n_rows} lignes écrites")


# --------------------------------------------------------------------------- #
# beer-analytics.com (T88) -- où un houblon est réellement utilisé, et combien
# --------------------------------------------------------------------------- #
def ingest_hop_usage_stats(out_db: str, limit: int | None = None, sleep: float = 1.0,
                           timeout: float = 30.0) -> None:
    """
    beer-analytics.com (T88, socle empirique de T99) : où un houblon est
    réellement utilisé dans le procédé (Mash/First Wort/Boil/Aroma/Dry Hop,
    vocabulaire BRUT de la source, jamais renommé) et combien -- table
    `hop_usage_stats`. Pages `/hops/<purpose>/<slug>/` énumérées depuis le
    sitemap (`_BA_HOP_PAGE_RE`, voir sa docstring pour le piège `/hops/
    flavors/...` exclu -- ce sont des pages de descripteur d'arôme, pas des
    houblons).

    Deux charts par houblon : `usage-types.json` (trace `bar`, `x` = étape,
    `y` = nombre de recettes -> `recipes_count`) et `amount-used-per-use.
    json` (une trace `box` par étape, `parsers.parse_box_trace` -> `amount_
    q1/median/q3`) -- jointes par le nom d'étape (`trace["name"]` côté
    boxplot == `trace["x"][i]` côté bar, vérifié en direct : les 5 mêmes
    clés dans le même ordre sur Citra).

    ⚠ `typical-styles-relative.json` (listé par le ticket, "les styles
    typiques de ce houblon") n'est PAS capturé ici : c'est une relation
    houblon->style, pas houblon->étape, et n'a nulle part où aller dans le
    `CREATE TABLE` du ticket (voir schema.HOP_USAGE_STATS_SCHEMA) -- donnée
    réelle et vérifiée, mais hors du schéma tel qu'écrit. Voir T131
    (nouveau ticket backlog) plutôt qu'une table inventée sans le demander.

    `variety` résolu via `ingest._resolve_hop_variety`, `NULL` si non
    résolu -- leurs 435 pages houblon ne couvrent pas nos 203 variétés 1:1,
    taux de résolution rapporté comme pour BeerMaverick (143/203).
    """
    from datetime import datetime, timezone
    from .schema import connect
    con = connect(out_db)
    if not con.execute("SELECT name FROM sqlite_master WHERE name='hops'").fetchone():
        init_db(con); seed_reference(con); con.commit()
    else:
        ensure_table(con, "hop_usage_stats", HOP_USAGE_STATS_SCHEMA)  # base existante : ne PAS la vider
    index = _build_hop_name_index(con)

    sitemap = _beer_analytics_fetch("/sitemap.xml", timeout=timeout, sleep=sleep)
    hop_paths = sorted(set(_BA_HOP_PAGE_RE.findall(sitemap)))
    if limit:
        hop_paths = hop_paths[:limit]
    print(f"beer-analytics (hop usage stats) : {len(hop_paths)} pages houblon (sitemap)")

    fetched_at = datetime.now(timezone.utc).isoformat()
    n_variety_resolved = n_variety_total = n_rows = 0
    for i, hop_path in enumerate(hop_paths, 1):
        try:
            html = _beer_analytics_fetch(hop_path, timeout=timeout, sleep=sleep)
        except Exception as e:  # noqa
            print(f"  !! {hop_path}: {e}"); continue
        charts = parsers.discover_beer_analytics_charts(html)
        hop_name = parsers.parse_beer_analytics_hop_name(html)
        if not hop_name:
            continue
        variety = _resolve_hop_variety(index, hop_name)
        n_variety_total += 1
        if variety:
            n_variety_resolved += 1

        counts_path = charts.get("usage-types")
        amount_path = charts.get("amount-used-per-use")
        if not counts_path and not amount_path:
            continue

        counts_by_use: dict[str, int] = {}
        if counts_path:
            try:
                payload = _beer_analytics_get(counts_path, timeout=timeout, sleep=sleep)
                traces = parsers.plotly_traces(payload)
                if traces:
                    counts_by_use = dict(zip(traces[0].get("x") or [], traces[0].get("y") or []))
            except Exception as e:  # noqa
                print(f"  !! {counts_path}: {e}")
        amount_by_use: dict[str, tuple] = {}
        if amount_path:
            try:
                payload = _beer_analytics_get(amount_path, timeout=timeout, sleep=sleep)
                for trace in parsers.plotly_traces(payload):
                    amount_by_use[trace["name"]] = parsers.parse_box_trace(trace)
            except Exception as e:  # noqa
                print(f"  !! {amount_path}: {e}")

        for use_type in sorted(set(counts_by_use) | set(amount_by_use)):
            recipes_count = counts_by_use.get(use_type)
            q1, median, q3 = amount_by_use.get(use_type, (None, None, None))
            con.execute(
                "INSERT OR REPLACE INTO hop_usage_stats VALUES (?,?,?,?,?,?,?,?,?)",
                (variety, hop_name, use_type, recipes_count, q1, median, q3,
                 "beer-analytics", fetched_at))
            n_rows += 1
        if i % 10 == 0:
            con.commit()
    con.commit(); con.close()
    print(f"  {n_variety_resolved}/{n_variety_total} houblons résolus vers une variety, "
         f"{n_rows} lignes écrites")


# --------------------------------------------------------------------------- #
# MMuM (maischemalzundmehr.de) -- corpus brut de recettes (T91, épique C)
# --------------------------------------------------------------------------- #
MMUM_BASE = "https://www.maischemalzundmehr.de"
MMUM_CACHE_DIR = "data/cache/mmum"
# Borne haute par défaut : ids observés jusqu'à 2290 le 2026-08-30 (vérifié
# en direct -- id 2290 a une vraie recette, 2300/2350 sont des trous), une
# marge de 100 au-delà pour couvrir les recettes ajoutées depuis sans
# refaire cette vérification à chaque run.
MMUM_DEFAULT_END = 2400


def _mmum_fetch(source_id: int, cache_dir: str = MMUM_CACHE_DIR,
                timeout: float = 30.0, sleep: float = 1.0) -> str:
    """GET cache-first sur `MMUM_BASE + /export_json.php?id=<source_id>`
    (même mécanisme que `_beer_analytics_fetch` : cache disque obligatoire,
    `User-Agent` identifiable, `sleep` uniquement sur un fetch réseau réel,
    jamais sur un hit de cache). Écrit le texte BRUT tel quel, y compris
    pour un "trou" (id sans recette -- réponse HTTP 200 avec un court
    message HTML, PAS un 404 : `raise_for_status()` ne le détecte donc pas,
    la détection se fait à la désérialisation JSON côté `ingest_mmum`) --
    mettre en cache un trou évite de le refetcher à chaque run futur."""
    import tempfile
    import time

    import requests

    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{source_id}.json")
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return f.read()

    resp = requests.get(f"{MMUM_BASE}/export_json.php?id={source_id}", timeout=timeout,
                        headers={"User-Agent": "hopmatch/0.1 (research)"})
    resp.raise_for_status()
    text = resp.text
    fd, tmp_path = tempfile.mkstemp(dir=cache_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, cache_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    time.sleep(sleep)
    return text


def ingest_mmum(out_db: str = "recipes.db", start: int = 1, end: int = MMUM_DEFAULT_END,
                sleep: float = 1.0, timeout: float = 30.0, limit: int | None = None,
                cache_dir: str = MMUM_CACHE_DIR) -> None:
    """T91 : corpus BRUT de recettes MMuM -- `recipes`/`recipe_hops` dans
    `recipes.db` (D4, fichier SÉPARÉ d'`aromahops.db`, jamais référencé par
    `app._fetch_remote_db`). Balaye `start..end` (bornes incluses), un GET
    par id (`_mmum_fetch`, cache-first, 1 requête/s par défaut) ; un id sans
    recette ("trou" -- réponse HTML courte, PAS un 404, voir `_mmum_fetch`)
    est détecté à l'échec de désérialisation JSON et sauté proprement, le
    balayage continue sur le reste de la plage (les ids valides ne sont PAS
    contigus, ex. 2290 a une vraie recette alors que 2200/2300 sont des
    trous -- vérifié en direct le 2026-08-30).

    `limit`, s'il est fourni, borne le NOMBRE D'IDS SCANNÉS (pas le nombre
    de recettes trouvées) -- même sémantique que `limit` dans les autres
    fonctions `ingest_*` de ce module (teste un sous-ensemble sans attendre
    la passe complète).

    Toute la conversion d'unité et la dérivation de stade viennent de
    `parsers.parse_mmum_recipe` (fonction pure, testée séparément sur
    fixtures) -- cette fonction ne fait QUE crawler/cacher/écrire.

    ⚠ **Périmètre de ce ticket : MMuM seul.** Le second corpus optionnel
    (BrewDog DIY Dog, ~400 recettes) mentionné par le ticket T91 comme
    « même ticket si le temps le permet » n'est PAS fait ici -- source et
    structure différentes (pas un export JSON par id), traité comme un
    complément séparé plutôt que d'élargir ce crawl déjà substantiel
    (~2400 requêtes). Voir BACKLOG.md pour le suivi."""
    import json
    from datetime import datetime, timezone

    from .schema import connect, init_recipes_db

    con = connect(out_db)
    init_recipes_db(con)
    fetched_at = datetime.now(timezone.utc).isoformat()

    ids = list(range(start, end + 1))
    if limit:
        ids = ids[:limit]

    n_recipes = n_holes = n_errors = n_hop_rows = 0
    stage_counts: dict[str | None, int] = {}
    for i, source_id in enumerate(ids, 1):
        try:
            text = _mmum_fetch(source_id, cache_dir=cache_dir, timeout=timeout, sleep=sleep)
        except Exception as e:  # noqa
            print(f"  !! id={source_id}: {e}")
            n_errors += 1
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            n_holes += 1
            continue

        parsed = parsers.parse_mmum_recipe(payload, source_id=str(source_id))
        r = parsed["recipe"]
        con.execute(
            "INSERT OR REPLACE INTO recipes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (r["uid"], r["source"], r["source_id"], r["name"], r["author"], r["brewed_on"],
             r["style_raw"], r["style_id"], r["og_plato"], r["og_sg"], r["fg_sg"], r["abv"],
             r["ibu"], r["ebc"], r["srm"], fetched_at))
        con.execute("DELETE FROM recipe_hops WHERE recipe_uid=?", (r["uid"],))
        for h in parsed["hops"]:
            # Colonnes NOMMÉES (pas `VALUES (?,?,...)` positionnel) --
            # `product_form` (T92) reste absent ici (toujours NULL à
            # l'ingestion, rempli par `reconcile_mmum_hop_varieties`) sans
            # dépendre de sa position dans `schema.RECIPES_SCHEMA`.
            con.execute(
                "INSERT INTO recipe_hops "
                "(recipe_uid, seq, hop_name, variety, stage, addition_type, time_min, "
                "amount_g, alpha) VALUES (?,?,?,?,?,?,?,?,?)",
                (r["uid"], h["seq"], h["hop_name"], h["variety"], h["stage"],
                 h["addition_type"], h["time_min"], h["amount_g"], h["alpha"]))
            n_hop_rows += 1
            stage_counts[h["stage"]] = stage_counts.get(h["stage"], 0) + 1
        n_recipes += 1
        if i % 20 == 0:
            con.commit()
    con.commit(); con.close()

    avg = n_hop_rows / n_recipes if n_recipes else 0.0
    print(f"MMuM : {n_recipes} recettes ingérées ({n_holes} trous, {n_errors} erreurs réseau "
         f"sur {len(ids)} ids scannés), {n_hop_rows} additions de houblon ({avg:.1f}/recette)")
    print(f"  répartition des stades : {dict(sorted(stage_counts.items(), key=lambda kv: str(kv[0])))}")


# --------------------------------------------------------------------------- #
# Réconciliation nom-de-recette -> variety (T92, épique C)
# --------------------------------------------------------------------------- #
BEER_ANALYTICS_HOPS_CSV_URL = (
    "https://raw.githubusercontent.com/scheb/beer-analytics/master/recipe_db/data/hops.csv")
BEER_ANALYTICS_HOPS_CSV_CACHE = "data/cache/beer_analytics_hops.csv"

# Décorations de FORME DE PRODUIT qui ne changent PAS la variété sous-jacente
# (« Pellets », « T90 »/« Typ 90 », « Hopfen » -- mot allemand générique pour
# « houblon », jamais un nom de variété -- « Dolden » -- « cônes », houblon en
# fleur entière -- « Teil »/« TeilN » -- « partie N » d'un houblonnage en
# plusieurs temps) -- vérifié sur le corpus MMuM réel (T92, 2026-09-03).
# JAMAIS « Cryo » ici : voir `_recipe_hop_is_cryo`, un produit Cryo N'EST PAS
# la variété de base (concentration ~2x mesurée sur les lots YCH, CLAUDE.md).
_RECIPE_HOP_DECORATION_RE = re.compile(
    r"\b(pellets?|t-?90|typ\s?90|type\s?90|hopfen|hops?|dolden|teil\s?\d*)\b", re.IGNORECASE)
# Contenu entre parenthèses/crochets ("(US) 2018", "[12% AA]") : quasi
# toujours une annotation d'origine/millésime/pureté, jamais une partie du
# nom de variété -- vérifié sur les ~630 noms bruts distincts du corpus.
_RECIPE_HOP_PAREN_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
# Millésime de récolte HORS parenthèses ("Citra (US) 2017" -> les parens
# retirées ci-dessus laissent "2017" bare) -- 4 chiffres commençant par 19/20,
# jamais un code de houblon réel dans ce corpus (vérifié : les codes numériques
# réels, "HBC 630"/"X07270", ne sont jamais des nombres à 4 chiffres nus
# commençant par 19/20).
_RECIPE_HOP_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# Pourcentage d'alpha-acide ("7.9% Alpha", "[12% AA]" déjà couvert ci-dessus
# par les crochets, mais aussi hors crochets) et annotations de température/
# durée ("15min @70°C") -- bruit de brassage, jamais un nom de houblon.
_RECIPE_HOP_PCT_RE = re.compile(r"\d+[.,]?\d*\s*%(\s*(alpha|aa))?", re.IGNORECASE)
_RECIPE_HOP_TEMP_TIME_RE = re.compile(r"\d+\s*°?c\b|\d+\s*min\b", re.IGNORECASE)
# "#1"/"#2" (parties d'un houblonnage fractionné, comme "Teil N" ci-dessus).
_RECIPE_HOP_HASH_RE = re.compile(r"#\s?\d+")
# Frontière lettre->chiffre collée sans séparateur ("Idaho7" -> "Idaho 7",
# "HBC630" -> "HBC 630") -- `_normalize_hop_key` traite déjà les caractères
# non alphanumériques comme séparateurs, mais un chiffre collé à une lettre
# reste un seul token sans cette insertion explicite d'espace. Appliquée
# APRÈS `_RECIPE_HOP_DECORATION_RE` (pas avant) : sinon "T90" ("Typ 90")
# deviendrait "T 90" AVANT que la décoration ne puisse le reconnaître comme
# un bloc "t-?90" glué -- bug réel trouvé en écrivant les tests de ce ticket.
_RECIPE_HOP_LETTER_DIGIT_RE = re.compile(r"(?<=[a-zA-Z])(?=\d)")
# Translittération allemande standard -- `_normalize_hop_key` ne fait que
# séparer les caractères non-ASCII (ü/ö/ä/ß traités comme des séparateurs,
# pas translittérés), ce qui casse le rapprochement entre l'orthographe
# allemande d'origine ("Hüll Melon") et sa forme déjà translittérée dans
# notre catalogue ("Huell Melon") -- bug trouvé en mesurant le taux de
# résolution réel sur le corpus (T92, 2026-09-03).
_RECIPE_HOP_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _normalize_recipe_hop_name(name: str) -> str:
    """Normalisation SPÉCIFIQUE à la réconciliation de noms de RECETTE (T92)
    -- bien plus bruts que les slugs BeerMaverick/beer-analytics déjà
    couverts par `_normalize_hop_key` (texte libre saisi à la main par des
    brasseurs amateurs, jamais un slug d'URL structuré). Fonction SÉPARÉE de
    `_normalize_hop_key` plutôt qu'une extension de celle-ci : les
    régressions potentielles (translittération, décorations retirées) ne
    doivent JAMAIS affecter la résolution BeerMaverick/beer-analytics déjà
    en production et testée séparément.

    Pipeline, dans cet ordre (chaque étape vérifiée nécessaire en mesurant
    le taux de résolution réel sur le corpus MMuM, jamais ajoutée au
    jugé) : translittération umlaut -> retrait parenthèses/crochets ->
    retrait millésime -> retrait %/température/durée -> retrait "#N" ->
    retrait des décorations de forme de produit -> frontière lettre/chiffre
    (APRÈS les décorations, voir `_RECIPE_HOP_LETTER_DIGIT_RE`) ->
    `_normalize_hop_key` (minuscule, symboles déposés, ponctuation ->
    tirets)."""
    cleaned = name.lower().translate(_RECIPE_HOP_UMLAUT_MAP)
    cleaned = _RECIPE_HOP_PAREN_RE.sub(" ", cleaned)
    cleaned = _RECIPE_HOP_YEAR_RE.sub(" ", cleaned)
    cleaned = _RECIPE_HOP_PCT_RE.sub(" ", cleaned)
    cleaned = _RECIPE_HOP_TEMP_TIME_RE.sub(" ", cleaned)
    cleaned = _RECIPE_HOP_HASH_RE.sub(" ", cleaned)
    cleaned = _RECIPE_HOP_DECORATION_RE.sub(" ", cleaned)
    cleaned = _RECIPE_HOP_LETTER_DIGIT_RE.sub(" ", cleaned)
    return _normalize_hop_key(cleaned)


def _recipe_hop_is_cryo(name: str) -> bool:
    """T92 : un produit Cryo (concentré de lupuline) N'EST PAS la variété de
    base -- concentration ~2x mesurée sur les lots YCH (CLAUDE.md, section
    API de lot YCH). Sous-chaîne simple (PAS `\\bcryo\\b`) : le corpus réel
    colle parfois "Cryo" directement au nom sans séparateur ("AmarilloCryo",
    "MosaicCryo", vérifié en direct) -- une frontière de mot ne matcherait
    pas ces cas."""
    return "cryo" in name.lower()


def _build_recipe_hop_index(con) -> dict[str, str]:
    """T92 : index {clé normalisée -> variety} SPÉCIFIQUE à la résolution de
    noms de recette, PAS une réutilisation de `_build_hop_name_index`
    (BeerMaverick/beer-analytics) -- deux différences essentielles, toutes
    deux trouvées en mesurant le taux de résolution réel sur le corpus MMuM
    (2026-09-03) :

    1. **Clés construites avec `_normalize_recipe_hop_name`, pas
       `_normalize_hop_key`.** Un nom de catalogue qui porte encore un
       umlaut brut (ex. "Hallertauer Mittelfrüh", "Hersbrucker Spät" --
       toutes nos variétés ne sont pas translittérées comme "Huell Melon")
       produit deux clés DIFFÉRENTES selon la fonction : `_normalize_hop_key`
       traite "ü" comme un simple séparateur ("hallertauer-mittelfr-h"),
       `_normalize_recipe_hop_name` le translittère ("hallertauer-
       mittelfrueh") -- avec `_build_hop_name_index`, un nom de recette tapé
       EXACTEMENT comme le catalogue (même orthographe allemande) ne
       matchait jamais directement, silencieusement.
    2. **Collision de nom -> AMBIGUË, jamais un choix arbitraire.**
       `_build_hop_name_index` prend le premier houblon rencontré en cas de
       nom dupliqué (`setdefault`, ordre d'itération SQL arbitraire) --
       acceptable pour BeerMaverick/beer-analytics qui résolvent depuis un
       slug de page déjà désambiguïsé côté source. Pour un nom de recette
       BRUT sans indication de région ("Saaz", "Northern Brewer" -- 2 lignes
       chacune, crops US/Europe réellement distincts), ce même mécanisme
       attribuait silencieusement 111 additions réelles à un crop arbitraire
       (souvent le crop US, minoritaire, plutôt que le crop traditionnel
       européen archi-dominant dans ce corpus germanophone -- bug trouvé en
       vérifiant le détail des lignes résolues, pas seulement le taux
       global). Une clé qui correspond à PLUSIEURS varietys DISTINCTES est
       donc exclue de l'index retourné -- jamais résolue, même traitement
       que "Golding"/"Styrian Golding" (ambiguïté déjà documentée comme
       volontairement non résolue, voir data/mappings/hop_name_
       aliases.yaml)."""
    seen: dict[str, set[str]] = {}
    for row in con.execute("SELECT variety, name FROM hops"):
        for raw_key in (row["variety"], row["name"]):
            key = _normalize_recipe_hop_name(raw_key)
            if key:
                seen.setdefault(key, set()).add(row["variety"])
    return {key: next(iter(varieties)) for key, varieties in seen.items() if len(varieties) == 1}


def resolve_recipe_hop_name(index: dict[str, str], alt_name_index: dict[str, str],
                            manual_index: dict[str, str], raw_name: str | None
                            ) -> tuple[str | None, str | None]:
    """T92 : (variety, product_form) pour `raw_name`, un nom de houblon BRUT
    de recette (MMuM ou futur corpus). Fonction PURE (dicts déjà construits
    par l'appelant, `reconcile_mmum_hop_varieties`) -- testée séparément de
    tout accès réseau/DB.

    Ordre de résolution, chacun essayé seulement si le précédent échoue :
    1. `raw_name` contient "cryo" -> `(None, "cryo")`, JAMAIS résolu vers la
       variété de base (voir `_recipe_hop_is_cryo`).
    2. `data/mappings/hop_name_aliases.yaml` (`manual_index`, cas allemands
       curés à la main -- voir le fichier pour la liste des cas
       volontairement PAS mappés faute d'une correspondance sans ambiguïté).
    3. Correspondance DIRECTE contre `index` (notre propre catalogue,
       `_build_recipe_hop_index` -- variety ET name, ambiguïté-consciente,
       voir sa docstring).
    4. `recipe_db/data/hops.csv` (beer-analytics, `alt_name_index` : alias
       normalisé -> nom CANONIQUE beer-analytics) puis re-résolution de ce
       nom canonique contre `index` -- un alias qui ne correspond à aucun
       houblon de NOTRE catalogue n'apporte rien (ex. beer-analytics connaît
       "Solero" mais notre base ne le mesure pas).

    `raw_name` vide/None ou entièrement composé de décorations (ex. une
    chaîne qui ne contient QUE "Pellets") -> `(None, None)`, jamais une
    correspondance fabriquée. Aucune correspondance trouvée à aucune étape
    -> `(None, None)` -- le nom brut reste dans `recipe_hops.hop_name`,
    exclu du calcul de combinaisons (T93)."""
    if not raw_name or not raw_name.strip():
        return None, None
    if _recipe_hop_is_cryo(raw_name):
        return None, "cryo"
    key = _normalize_recipe_hop_name(raw_name)
    if not key:
        return None, None
    if key in manual_index:
        return manual_index[key], None
    variety = index.get(key)
    if variety:
        return variety, None
    canonical = alt_name_index.get(key)
    if canonical:
        variety = index.get(_normalize_recipe_hop_name(canonical))
        if variety:
            return variety, None
    return None, None


def download_beer_analytics_hops_csv(dest_path: str = BEER_ANALYTICS_HOPS_CSV_CACHE,
                                     force: bool = False) -> str:
    """Télécharge (si absent) `recipe_db/data/hops.csv`
    (`github.com/scheb/beer-analytics`, GPLv3) -- dictionnaire d'alias de
    noms de houblons curé À LA MAIN par un tiers (435 lignes, colonnes
    `name;use;origin;substitutes;aromas;alt_names;alt_names_extra`,
    vérifié en direct le 2026-09-03, 48528 octets -- exactement ce que
    BACKLOG.md T85 documentait déjà). Jamais committé (même pattern que
    `download_bjcp_styles`/`download_foodb_dump`), fichier temporaire +
    `os.replace` pour ne jamais laisser un téléchargement interrompu passer
    pour un cache valide. Idempotent : ne retélécharge rien si `dest_path`
    existe déjà (sauf `force=True`)."""
    import tempfile

    import requests

    if os.path.exists(dest_path) and not force:
        return dest_path
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    resp = requests.get(BEER_ANALYTICS_HOPS_CSV_URL, timeout=30,
                        headers={"User-Agent": "hopmatch/0.1 (research)"})
    resp.raise_for_status()
    fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(dest_path))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(resp.content)
        os.replace(tmp_path, dest_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    return dest_path


def reconcile_mmum_hop_varieties(recipes_db: str = "recipes.db", aroma_db: str = "aromahops.db",
                                 hops_csv_path: str | None = None) -> None:
    """T92 : résout `recipe_hops.hop_name` (brut, MMuM) -> `variety` (notre
    catalogue) DANS `recipes.db` -- `aromahops.db` n'est JAMAIS modifiée
    par cette fonction (lue seule pour construire l'index de résolution,
    voir D4 : les deux bases ne communiquent qu'à la LECTURE, T93/T126/T127
    liront `recipes.db` réconciliée pour écrire leurs propres résultats
    dans `aromahops.db`).

    Ajoute la colonne `product_form` à `recipe_hops` si absente
    (`ensure_columns`, jamais un `init_recipes_db` qui viderait le corpus
    déjà crawlé) -- distincte de `variety`, voir `schema.RECIPES_SCHEMA`
    pour pourquoi un produit Cryo ne doit jamais écraser la variété de base.

    Peut être relancée sans risque après un re-crawl `ingest_mmum` partiel
    (idempotente, réécrit `variety`/`product_form` pour TOUTES les lignes
    -- jamais un état qui dépend de l'ordre d'exécution)."""
    from .schema import connect, ensure_columns

    aroma_con = connect(aroma_db)
    index = _build_recipe_hop_index(aroma_con)
    valid_varieties = {r[0] for r in aroma_con.execute("SELECT variety FROM hops")}
    aroma_con.close()

    if hops_csv_path is None:
        hops_csv_path = download_beer_analytics_hops_csv()
    with open(hops_csv_path, encoding="utf-8") as f:
        ba_rows = parsers.parse_beer_analytics_hops_csv(f.read())
    alt_name_index: dict[str, str] = {}
    for row in ba_rows:
        for alias in row["alt_names"]:
            alt_name_index.setdefault(_normalize_recipe_hop_name(alias), row["name"])

    manual_aliases = _load_yaml_mapping("hop_name_aliases.yaml")
    bad_targets = {v for v in manual_aliases.values() if v not in valid_varieties}
    if bad_targets:
        raise ValueError(
            f"data/mappings/hop_name_aliases.yaml : variety(s) inexistante(s) dans "
            f"aromahops.db : {sorted(bad_targets)} -- corriger le fichier, jamais une "
            f"faute de frappe silencieuse.")
    manual_index = {_normalize_recipe_hop_name(k): v for k, v in manual_aliases.items()}

    con = connect(recipes_db)
    ensure_columns(con, "recipe_hops", {"product_form": "TEXT"})
    rows = con.execute("SELECT recipe_uid, seq, hop_name FROM recipe_hops").fetchall()

    n_resolved = n_cryo = n_unresolved = 0
    unresolved_counts: dict[str, int] = {}
    for i, (recipe_uid, seq, hop_name) in enumerate(rows, 1):
        variety, product_form = resolve_recipe_hop_name(index, alt_name_index, manual_index,
                                                        hop_name)
        if variety:
            n_resolved += 1
        elif product_form == "cryo":
            n_cryo += 1
        else:
            n_unresolved += 1
            if hop_name:
                unresolved_counts[hop_name] = unresolved_counts.get(hop_name, 0) + 1
        con.execute("UPDATE recipe_hops SET variety=?, product_form=? "
                   "WHERE recipe_uid=? AND seq=?", (variety, product_form, recipe_uid, seq))
        if i % 500 == 0:
            con.commit()
    con.commit(); con.close()

    total = len(rows)
    print(f"MMuM réconciliation (T92) : {n_resolved}/{total} additions résolues vers une "
         f"variety ({n_resolved / total:.1%}), {n_cryo} produits Cryo (jamais vers la variété "
         f"de base), {n_unresolved} non résolues.")
    top = sorted(unresolved_counts.items(), key=lambda kv: -kv[1])[:15]
    print(f"  noms non résolus les plus fréquents : {top}")


# --------------------------------------------------------------------------- #
# Combinaisons de houblons fréquentes (T93, épique C)
# --------------------------------------------------------------------------- #
_RECIPE_STAGES = ("first_wort", "boil", "whirlpool", "dry_hop")


def compute_frequent_hop_combinations(recipes_db: str = "recipes.db", out_db: str = "aromahops.db",
                                      sizes: tuple[int, ...] = (2, 3, 4),
                                      min_support: int = 20) -> None:
    """T93 : combinaisons de houblons RÉELLEMENT co-observées dans une même
    recette -- lit `recipe_hops` (déjà réconciliée, T92 ; `variety IS NULL`
    exclues) dans `recipes_db`, écrit `hop_combinations` dans `out_db`
    (D4 : jamais l'inverse, `aromahops.db` reste la seule base servie par
    l'app). Table intégralement DÉRIVÉE -- `DELETE FROM hop_combinations`
    puis recalcul complet à chaque appel, jamais une mise à jour partielle
    qui dépendrait de l'état d'un appel précédent.

    **Une recette = un ENSEMBLE de varietys distinctes** (dédupliqué -- un
    Citra en boil ET en dry hop compte une fois dans la tranche `stage=
    None`, voir ci-dessous pour les tranches par stade).

    **5 tranches calculées** : `stage=None` (toutes étapes confondues,
    tranche PRINCIPALE du ticket) + une par valeur RÉELLE de
    `recipe_hops.stage` (`_RECIPE_STAGES` -- "les 3 houblons qu'on retrouve
    ensemble EN DRY HOP", apport signalé par le ticket comme absent de
    beer-analytics et du hop-finder russe). Pour une tranche par stade,
    l'ensemble d'une recette ne contient QUE les varietys utilisées à CE
    stade précis -- une recette sans aucune addition à ce stade n'y
    contribue simplement pas (ni au numérateur ni au dénominateur).

    **Algorithme** : énumération DIRECTE des sous-ensembles de taille
    `size` RÉELLEMENT présents dans chaque itemset de recette
    (`itertools.combinations` sur l'ensemble trié de la recette) --
    **jamais un triplet dérivé de 3 paires** (garde-fou explicite du
    ticket) : un triplet n'existe dans le résultat QUE s'il apparaît tel
    quel dans au moins `min_support` recettes.

    **`lift`** = P(combo) / produit(P(chaque membre seul)), calculé sur le
    `total_recipes` RÉEL de la tranche (dénominateur propre à chaque
    tranche stade/taille, jamais un total global réutilisé partout) -- même
    logique que la pondération TF-IDF de `matching.molecular_scores` (le
    houblon ubiquitaire ne doit pas dominer par simple fréquence brute).

    `style_id` toujours NULL dans cette passe (voir `schema.
    HOP_COMBINATIONS_SCHEMA` : `recipes.style_id` n'est peuplé par aucun
    ticket actuel)."""
    import itertools
    from collections import Counter
    from datetime import datetime, timezone

    from .schema import connect, ensure_table, HOP_COMBINATIONS_SCHEMA

    recipes_con = connect(recipes_db)
    rows = recipes_con.execute(
        "SELECT recipe_uid, variety, stage FROM recipe_hops WHERE variety IS NOT NULL").fetchall()
    recipes_con.close()

    slices: dict[str | None, dict[str, set[str]]] = {None: {}}
    for stage in _RECIPE_STAGES:
        slices[stage] = {}
    for recipe_uid, variety, stage in rows:
        slices[None].setdefault(recipe_uid, set()).add(variety)
        if stage in _RECIPE_STAGES:
            slices[stage].setdefault(recipe_uid, set()).add(variety)

    con = connect(out_db)
    ensure_table(con, "hop_combinations", HOP_COMBINATIONS_SCHEMA)
    con.execute("DELETE FROM hop_combinations")
    computed_at = datetime.now(timezone.utc).isoformat()

    n_rows = 0
    for stage, itemsets_by_recipe in slices.items():
        itemsets = list(itemsets_by_recipe.values())
        total_recipes = len(itemsets)
        if total_recipes == 0:
            continue
        singleton_counts: Counter = Counter()
        for items in itemsets:
            singleton_counts.update(items)
        for size in sizes:
            combo_counts: Counter = Counter()
            for items in itemsets:
                if len(items) < size:
                    continue
                for combo in itertools.combinations(sorted(items), size):
                    combo_counts[combo] += 1
            for combo, support in combo_counts.items():
                if support < min_support:
                    continue
                p_joint = support / total_recipes
                p_product = 1.0
                for v in combo:
                    p_product *= singleton_counts[v] / total_recipes
                lift = p_joint / p_product
                con.execute(
                    "INSERT OR REPLACE INTO hop_combinations VALUES (?,?,?,?,?,?,?,?,?)",
                    ("|".join(combo), size, None, stage, support, total_recipes, lift,
                     "mmum", computed_at))
                n_rows += 1
    con.commit(); con.close()
    print(f"T93 : {n_rows} combinaisons écrites (min_support={min_support}, tailles={sizes}, "
         f"{len(slices)} tranches stade dont 'toutes étapes confondues')")


# --------------------------------------------------------------------------- #
# "Comment ce houblon est réellement ajouté" (T126, épique C)
# --------------------------------------------------------------------------- #
def _classify_addition_timing(addition_type: str | None, time_min: float | None) -> str | None:
    """T126 : une des 11 classes de `reference.ADDITION_TIMING_BINS` pour
    UNE addition MMuM (`recipe_hops.addition_type`/`time_min`), ou `None`
    si elle ne correspond à aucune classe reconnue -- `addition_type` hors
    des 4 valeurs connues (`Standard`/`Whirlpool`/`Vorderwuerze`/
    `Stopfhopfen`, voir `parsers.parse_mmum_recipe`/`_MMUM_TYP_TO_STAGE`)
    ou `Standard` sans `time_min` exploitable. JAMAIS deviné -- une
    addition non classifiée compte quand même dans `total_additions`
    (`compute_hop_addition_timing`), simplement absente de tout bin.

    Bornes vérifiées sur le corpus COMPLET réconcilié (2026-09-03, 5935
    additions) : `Whirlpool` a TOUJOURS `time_min == 0` (677/677) -- le
    temps n'y est pas porteur d'information, seule la catégorie compte."""
    if addition_type == "Vorderwuerze":
        return "First wort"
    if addition_type == "Whirlpool":
        return "Whirlpool"
    if addition_type == "Stopfhopfen":
        return "Dry hop"
    if addition_type != "Standard" or time_min is None:
        return None
    if time_min >= 60:
        return "Boil 60+ min"
    if time_min >= 31:
        return "Boil 31-59 min"
    if time_min == 30:
        return "Boil 30 min"
    if time_min >= 16:
        return "Boil 16-29 min"
    if time_min == 15:
        return "Boil 15 min"
    if time_min >= 6:
        return "Boil 6-14 min"
    if time_min >= 1:
        return "Boil 1-5 min"
    if time_min == 0:
        return "Flameout (0 min)"
    return None  # temps négatif : jamais observé, jamais deviné


def compute_hop_addition_timing(recipes_db: str = "recipes.db", out_db: str = "aromahops.db") -> None:
    """T126 : répartition RÉELLE des additions d'une variety sur les 11
    classes chronologiques de `reference.ADDITION_TIMING_BINS` -- lit
    `recipe_hops` (T92, `variety IS NULL` exclues) dans `recipes_db`, écrit
    `hop_addition_timing` dans `out_db` (D4, jamais l'inverse). Table
    intégralement DÉRIVÉE -- `DELETE` puis recalcul complet à chaque appel.

    `total_additions` = TOUTES les additions résolues de cette variety, y
    compris celles qui ne classifient dans AUCUN bin (`_classify_addition_
    timing` -> `None`) -- le dénominateur reflète la vraie population de
    données, pas seulement ce qui a pu être classé. `total_recipes` =
    nombre de recettes DISTINCTES (une variety ajoutée 3 fois dans la même
    recette ne compte qu'une fois pour ce total, cohérent avec le "n = 47
    additions in 31 recipes" du ticket).

    Aucun seuil de fiabilité appliqué ici (voir `schema.HOP_ADDITION_
    TIMING_SCHEMA`) -- toutes les varietys avec au moins une addition
    résolue reçoivent une ligne, même sous 20 additions : c'est à la GUI de
    décider d'afficher le graphique ou un simple effectif."""
    from collections import Counter
    from datetime import datetime, timezone

    from .schema import connect, ensure_table, HOP_ADDITION_TIMING_SCHEMA

    recipes_con = connect(recipes_db)
    rows = recipes_con.execute(
        "SELECT recipe_uid, variety, addition_type, time_min FROM recipe_hops "
        "WHERE variety IS NOT NULL").fetchall()
    recipes_con.close()

    bin_counts: dict[str, Counter] = {}
    total_additions: dict[str, int] = {}
    recipe_uids: dict[str, set[str]] = {}
    for recipe_uid, variety, addition_type, time_min in rows:
        total_additions[variety] = total_additions.get(variety, 0) + 1
        recipe_uids.setdefault(variety, set()).add(recipe_uid)
        bin_ = _classify_addition_timing(addition_type, time_min)
        if bin_ is not None:
            bin_counts.setdefault(variety, Counter())[bin_] += 1

    con = connect(out_db)
    ensure_table(con, "hop_addition_timing", HOP_ADDITION_TIMING_SCHEMA)
    con.execute("DELETE FROM hop_addition_timing")
    computed_at = datetime.now(timezone.utc).isoformat()

    n_rows = 0
    for variety, total in total_additions.items():
        total_recipes = len(recipe_uids[variety])
        for bin_, count in bin_counts.get(variety, {}).items():
            con.execute("INSERT INTO hop_addition_timing VALUES (?,?,?,?,?,?,?)",
                       (variety, bin_, count, total, total_recipes, "mmum", computed_at))
            n_rows += 1
    con.commit(); con.close()
    print(f"T126 : {n_rows} lignes écrites pour {len(total_additions)} varietys "
         f"({sum(total_additions.values())} additions résolues au total)")
