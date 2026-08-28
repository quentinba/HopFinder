"""Schéma SQLite (EAV, multi-sources) + validation/réparation des compositions."""
from __future__ import annotations
import sqlite3

SCHEMA = """
-- purpose : "aromatic"|"bittering"|"both"|NULL -- seule BeerMaverick classe
-- explicitement un houblon par usage (« Purpose: Aroma/Bittering/Dual », voir
-- parsers.parse_beermaverick_purpose) ; ni BarthHaas ni Yakima n'ont ce champ.
-- NULL = variété non couverte par BeerMaverick (jamais déduit de l'alpha acide
-- ou d'un autre proxy -- ce serait fabriquer une donnée, voir CLAUDE.md).
-- Métadonnées d'identité (T106) : cultivar/breeder/release_year/pedigree en
-- texte libre (sourcées Yakima pour cultivar, curation manuelle pour
-- breeder/release_year/pedigree -- voir data/mappings/hop_breeder_
-- pedigree.yaml, prose BeerMaverick trop hétérogène pour un parseur fiable).
-- is_experimental/is_organic/is_blend : booléens Yakima (imported_fields.
-- experimental/organic/blend) en 0/1, NULL si la variété n'est pas couverte
-- par Yakima -- jamais 0 par défaut (affirmerait "non expérimental" sans
-- preuve).
-- description/description_source (T107) : texte éditorial MARKETING du
-- producteur (imported_fields.description, Yakima Algolia, 153/153
-- variétés) -- nettoyé en markdown à l'ingestion (parsers.clean_yakima_
-- description), jamais le HTML brut. `description_source` littéral
-- ("yakima") pour permettre l'attribution explicite en GUI même si une
-- autre source de description apparaissait un jour.
CREATE TABLE hops (
    variety TEXT PRIMARY KEY, name TEXT, region TEXT, sources TEXT, purpose TEXT,
    cultivar TEXT, breeder TEXT, release_year INTEGER, pedigree TEXT,
    is_experimental INTEGER, is_organic INTEGER, is_blend INTEGER,
    description TEXT, description_source TEXT
);
CREATE TABLE hop_composition (
    variety TEXT, compound TEXT, vmin REAL, vmax REAL, unit TEXT, source TEXT,
    confidence TEXT, notes TEXT,
    PRIMARY KEY (variety, compound, source)
);
CREATE TABLE hop_descriptors (
    variety TEXT, descriptor TEXT, source TEXT,
    PRIMARY KEY (variety, descriptor, source)
);
-- Roue d'arôme QUANTITATIVE (T26 backlog). Yakima uniquement : intensité 0-100
-- par descripteur (imported_fields.sensory_values/aroma_values, Algolia YCH),
-- une donnée réelle distincte de la simple présence/absence de hop_descriptors
-- (voir ingest.crawl_yakima et parsers.parse_yakima_hit). BarthHaas n'a pas
-- cette donnée -> jamais peuplée pour cette source, pas de valeur inventée.
CREATE TABLE hop_aroma_intensity (
    variety TEXT, descriptor TEXT, intensity REAL, source TEXT,
    PRIMARY KEY (variety, descriptor, source)
);
-- Associations houblon<->houblon (T25 backlog), chacune avec sa propre source
-- affichée en GUI (browse) : trois relations différentes, pas interchangeables.
-- similar_variety/paired_variety/substitute_variety = notre propre slug variety
-- SI reconnu (jointure normalisée sur nom, voir ingest._resolve_hop_variety),
-- sinon NULL (le nom brut *_name reste toujours renseigné, jamais perdu).
CREATE TABLE hop_similar (
    -- Yakima : imported_fields.similar_varieties (UID Contentstack, résolu
    -- directement via le même crawl_yakima -> toujours une variété interne
    -- connue, jamais de nom brut hors catalogue Yakima).
    variety TEXT, similar_variety TEXT, source TEXT,
    PRIMARY KEY (variety, similar_variety, source)
);
CREATE TABLE hop_pairings (
    -- BeerMaverick : "Hop Pairings" (fréquence relative d'association dans des
    -- recettes réelles, agrégée par eux depuis des bières publiées -- PAS une
    -- mesure de labo, à afficher avec cette réserve).
    variety TEXT, paired_name TEXT, paired_variety TEXT, frequency REAL, source TEXT,
    PRIMARY KEY (variety, paired_name, source)
);
CREATE TABLE hop_substitutions (
    -- BeerMaverick : "Hop Substitutions" (choix de brasseurs expérimentés,
    -- éditorial -- PAS une mesure).
    variety TEXT, substitute_name TEXT, substitute_variety TEXT, source TEXT,
    PRIMARY KEY (variety, substitute_name, source)
);
CREATE TABLE molecules (
    compound TEXT PRIMARY KEY, odor TEXT, threshold_ppb REAL, pubchem_cid INTEGER
);
CREATE TABLE aroma_notes (
    note TEXT, molecule TEXT, weight REAL, source TEXT, PRIMARY KEY (note, molecule)
);
CREATE TABLE note_descriptors (
    note TEXT, descriptor TEXT, PRIMARY KEY (note, descriptor)
);
-- Whitelist Flavornet (composés odeur-actifs GC-O) : sert à filtrer FooDB
-- (ingest_foodb), pas à la couche de matching note->molécules (`molecules`).
CREATE TABLE flavornet_compounds (
    cas TEXT PRIMARY KEY, compound TEXT, descriptors TEXT
);
-- Seuils olfactifs FlavorDB2, bornés à la whitelist Flavornet. Source dédiée,
-- lue directement par ingest_foodb (jamais de repli sur l'amorce manuelle
-- reference.MOLECULES pour cette décision de poids).
CREATE TABLE flavordb2_thresholds (
    cas TEXT PRIMARY KEY, compound TEXT, threshold_ppb REAL
);
-- Résolution CAS -> PubChem CID (le "liant" entre les mondes note/houblon/
-- molécule). cid NULL = résolution tentée mais échouée (pour ne pas
-- re-solliciter PubChem inutilement à chaque run).
CREATE TABLE pubchem_cids (
    cas TEXT PRIMARY KEY, cid INTEGER
);
"""

# Styles BJCP (T81, épique A) : source `beerjson/bjcp-json` (BeerJSON 2.01),
# téléchargée à l'ingestion, jamais committée (même pattern que le dump
# FooDB). Millésimes 2021/2015 JAMAIS fusionnés (même règle que Yakima/
# BarthHaas) -- coexistent via `guideline_year`, clé primaire composite.
# Ce n'est PAS une mesure de recette (voir `style_recipe_stats`, épique B,
# beer-analytics) -- une fourchette de référence éditoriale BJCP.
# 17/110 styles (2021) n'ont aucune vital stat (héritent du style de base
# choisi par le brasseur, ex. specialty/fruit/historical) : NULL, jamais 0.
# Constante SÉPARÉE de `SCHEMA` (plutôt qu'inline) : `ingest.ingest_beer_
# styles` doit pouvoir créer CETTE seule table sur une base déjà peuplée par
# d'anciens crawls (voir `ensure_table`) sans passer par `init_db`, qui DROP
# + recrée TOUT -- ça viderait `hops`/`hop_composition`/etc. d'une base
# réelle qui n'a jamais eu cette table.
BEER_STYLES_SCHEMA = """
CREATE TABLE beer_styles (
    style_id TEXT, guideline_year INTEGER, category_id TEXT, category TEXT,
    name TEXT, type TEXT, tags TEXT,
    og_min REAL, og_max REAL, fg_min REAL, fg_max REAL,
    abv_min REAL, abv_max REAL, ibu_min REAL, ibu_max REAL,
    srm_min REAL, srm_max REAL,
    overall_impression TEXT, aroma TEXT, appearance TEXT, flavor TEXT,
    mouthfeel TEXT, comments TEXT, history TEXT, ingredients TEXT,
    style_comparison TEXT, examples TEXT, category_description TEXT,
    source TEXT,
    PRIMARY KEY (style_id, guideline_year)
);
"""
SCHEMA += BEER_STYLES_SCHEMA

# Houblon -> style, ÉDITORIAL (T83, épique A) : suggestion d'un producteur
# (Yakima `imported_fields.beer_types`) ou d'un agrégateur de recettes
# (BeerMaverick, section "Beer Styles using {Hop} Hops") -- PAS une mesure,
# PAS du BJCP (vocabulaire libre de la source). `style_label` = l'étiquette
# BRUTE telle qu'écrite par la source (ex. BeerMaverick écrit parfois
# "Pale Ales" au pluriel là où Yakima écrit "Pale Ale" -- gardées comme deux
# lignes distinctes, jamais fusionnées au jugé). `style_id` = l'id BJCP
# SEULEMENT si la correspondance est certaine (`data/mappings/beer_style_
# aliases.yaml`, T84), NULL sinon -- ne jamais rattacher au jugé. Constante
# séparée (même raison que `BEER_STYLES_SCHEMA` juste au-dessus) : plusieurs
# ingesteurs (`crawl_yakima`, `ingest_beermaverick`) doivent pouvoir créer
# CETTE seule table sur une base déjà peuplée, sans passer par `init_db`.
HOP_BEER_STYLES_SCHEMA = """
CREATE TABLE hop_beer_styles (
    variety TEXT, style_label TEXT, style_id TEXT, source TEXT,
    PRIMARY KEY (variety, style_label, source)
);
"""
SCHEMA += HOP_BEER_STYLES_SCHEMA

# Distributions RÉELLES observées dans des recettes publiées (T85, épique B) --
# beer-analytics.com, agrégateur de recettes homebrew, PAS du BJCP (voir
# `beer_styles` ci-dessus) ni une mesure de labo. `metric` in
# {abv, ibu, og, fg, srm}, un bin par ligne (`bin_low`/`bin_high` = bornes de
# l'intervalle pandas source, `count` = nombre de recettes dans ce bin) --
# des HISTOGRAMMES PRÉ-BINNÉS avec outliers déjà retirés côté beer-analytics
# (`remove_outliers(..., 0.02)`), jamais un vrai percentile dérivable (GUI :
# "observed distribution", jamais "P5-P95"). `style_id` = notre id BJCP via
# `data/mappings/beer_style_aliases.yaml` (T84), NULL si non résolu (leurs
# styles ne sont pas tous BJCP) -- jamais deviné. Constante séparée (même
# raison que BEER_STYLES_SCHEMA/HOP_BEER_STYLES_SCHEMA) : `ingest_beer_
# analytics` doit pouvoir créer cette seule table sur une base déjà peuplée.
STYLE_RECIPE_STATS_SCHEMA = """
CREATE TABLE style_recipe_stats (
    style_id TEXT, style_slug TEXT, metric TEXT,
    bin_low REAL, bin_high REAL, count INTEGER,
    source TEXT, fetched_at TEXT,
    PRIMARY KEY (style_slug, metric, bin_low)
);
"""
SCHEMA += STYLE_RECIPE_STATS_SCHEMA

# alpha_acid/beta_acid retirés de ce filtre (2026-08-19, demande utilisateur) :
# non-aromatiques (jamais utilisés dans le scoring moléculaire, qui n'itère
# que sur les molécules de la NOTE -- aucune note FooDB ne référence jamais
# ces clés spécifiques au houblon), mais des stats clé attendues à l'affichage
# (browse + détail par houblon), voir CLAUDE.md/app._render_key_stats.
DROP_COMPOUNDS = {"polyphenols"}  # jamais produit par un parseur (dead entry, inoffensif)


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(
        "DROP TABLE IF EXISTS hops; DROP TABLE IF EXISTS hop_composition;"
        "DROP TABLE IF EXISTS hop_descriptors; DROP TABLE IF EXISTS hop_aroma_intensity;"
        "DROP TABLE IF EXISTS hop_similar; DROP TABLE IF EXISTS hop_pairings;"
        "DROP TABLE IF EXISTS hop_substitutions;"
        "DROP TABLE IF EXISTS molecules;"
        "DROP TABLE IF EXISTS aroma_notes; DROP TABLE IF EXISTS note_descriptors;"
        "DROP TABLE IF EXISTS flavornet_compounds; DROP TABLE IF EXISTS flavordb2_thresholds;"
        "DROP TABLE IF EXISTS pubchem_cids;"
        "DROP TABLE IF EXISTS beer_styles;"
        "DROP TABLE IF EXISTS hop_beer_styles;"
        "DROP TABLE IF EXISTS style_recipe_stats;")
    con.executescript(SCHEMA)


def ensure_table(con: sqlite3.Connection, table_name: str, create_sql: str) -> None:
    """Crée `table_name` si elle est absente, SANS toucher aux autres tables
    -- contrairement à `init_db` (qui DROP + recrée TOUT). Pour ajouter une
    table neuve (T81 et les tickets suivants qui en ajoutent, voir BACKLOG.md
    §1bis) à une base déjà peuplée par d'anciens crawls sans perdre leurs
    données. `create_sql` doit rester identique au DDL correspondant dans
    `SCHEMA` (les deux sont la même chaîne, ex. `BEER_STYLES_SCHEMA`)."""
    if not con.execute(
        "SELECT name FROM sqlite_master WHERE name=?", (table_name,)
    ).fetchone():
        con.executescript(create_sql)


# Colonnes T106 en dict {nom: type SQL} -- même liste que le `CREATE TABLE
# hops` ci-dessus, PARTAGÉE avec `ensure_columns` (voir `ingest.crawl_yakima`)
# pour qu'un rebuild complet (init_db) et une migration sur base existante
# produisent exactement le même schéma, jamais une définition dupliquée qui
# pourrait diverger.
HOP_IDENTITY_COLUMNS = {
    "cultivar": "TEXT", "breeder": "TEXT", "release_year": "INTEGER", "pedigree": "TEXT",
    "is_experimental": "INTEGER", "is_organic": "INTEGER", "is_blend": "INTEGER",
}

# T107, même principe que HOP_IDENTITY_COLUMNS ci-dessus.
HOP_DESCRIPTION_COLUMNS = {"description": "TEXT", "description_source": "TEXT"}


def ensure_columns(con: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
    """Ajoute à `table_name` les colonnes de `columns` ({nom: type SQL}) qui
    n'existent pas encore, via `ALTER TABLE ... ADD COLUMN` -- pendant
    `SANS toucher aux lignes existantes`, contrairement à `init_db` (DROP +
    recrée TOUT). Même besoin que `ensure_table` (T81) mais pour des COLONNES
    ajoutées à une table qui existe déjà (T106 : `hops` sur une base réelle
    déjà peuplée). `ALTER TABLE ADD COLUMN` est pleinement supporté par
    SQLite pour des colonnes simples sans contrainte NOT NULL/DEFAULT non
    constant -- le ticket T106 dit « ALTER impossible » au sens de « ne pas
    compter sur `init_db` pour ça », pas une limite réelle de SQLite."""
    existing = {row["name"] for row in con.execute(f"PRAGMA table_info({table_name})")}
    for name, sql_type in columns.items():
        if name not in existing:
            con.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {sql_type}")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def validate_and_repair(comp: dict[str, tuple], repair: bool = True
                        ) -> tuple[dict[str, tuple], str, list[str]]:
    """
    Valide/répare une composition {compound: (vmin, vmax, unit)}.
    Retourne (comp, confidence, notes). confidence ∈ {ok, repaired, suspect}.

    Détecte l'inversion myrcène/caryophyllène (fréquente dans les datasets scrappés :
    le caryophyllène dépasse rarement ~15 %). Ne s'applique qu'aux données brutes ;
    inoffensif sur des sources propres (BarthHaas/Yakima passent en 'ok').
    """
    notes: list[str] = []
    comp = dict(comp)

    def mx(c):
        return comp.get(c, (None, None, None))[1]

    # négatifs
    if any((v is not None and v < 0) for c in comp for v in comp[c][:2] if v is not None):
        return comp, "suspect", ["valeur négative"]

    car, myr = mx("caryophyllene"), mx("myrcene")
    if car is not None and car > 25 and (myr is None or myr < 10):
        if repair and "caryophyllene" in comp and "myrcene" in comp:
            comp["myrcene"], comp["caryophyllene"] = comp["caryophyllene"], comp["myrcene"]
            notes.append(f"swap myrcène/caryophyllène (car={car}%)")
        elif repair:  # une seule des deux présente
            comp["myrcene"] = comp.pop("caryophyllene")
            notes.append(f"caryophyllène={car}% relabellisé myrcène")
        else:
            return comp, "suspect", [f"caryophyllène implausible ({car}%)"]

    # cohérence de somme (sur les 5 grands terpènes en % d'huile)
    big = ["myrcene", "humulene", "caryophyllene", "farnesene", "geraniol"]
    known = [mx(c) for c in big if mx(c) is not None]
    if len(known) >= 3 and not (30 <= sum(known) <= 130):
        return comp, "suspect", notes + [f"somme terpènes hors bornes ({sum(known):.0f}%)"]

    return comp, ("repaired" if notes else "ok"), notes
