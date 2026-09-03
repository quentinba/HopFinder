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

# Quels houblons sont réellement utilisés pour un style, et combien (T86,
# épique B) -- beer-analytics.com, `popular-hops.json` (part de recettes,
# série temporelle, T86 en garde la dernière valeur ET une moyenne 24 mois --
# deux questions différentes, jamais l'une n'écrase l'autre) et
# `popular-hops-amount.json` (dosage, boxplot q1/median/q3). `usage_type` :
# le ticket anticipait deux issues possibles pour les onglets "Used for"
# (Any/Bittering/Aroma/Dry-Hop) de la page de style -- filtrage CLIENT (rien
# à capturer) ou VRAIES URLs distinctes (capturer la ventilation, "la donnée
# la plus intéressante de ce ticket", texte du ticket lui-même). Vérifié en
# direct (reverse engineering du bundle JS `/static/app.js`, T86) : ce sont
# de vraies requêtes avec un paramètre `?filter=...` sur la MÊME URL de
# chart, payloads réellement différents (ex. Citra "bittering" vs "any" :
# valeurs distinctes, pas juste une réétiquette). D'où `usage_type` ajouté à
# la clé primaire du ticket original (qui ne l'avait pas, rédigée avant
# cette vérification) -- "any" = onglet "Any" (aucun filtre), sinon
# aroma/bittering/dry-hop. `style_id` = notre id BJCP via `data/mappings/
# beer_style_aliases.yaml` (T84/T85), `variety` = notre clé houblon via
# `ingest._resolve_hop_variety`, tous deux NULL si non résolus.
STYLE_HOP_USAGE_SCHEMA = """
CREATE TABLE style_hop_usage (
    style_slug TEXT, style_id TEXT, hop_name TEXT, variety TEXT, usage_type TEXT,
    recipes_pct_latest REAL, recipes_pct_avg24m REAL,
    amount_q1 REAL, amount_median REAL, amount_q3 REAL,
    source TEXT, fetched_at TEXT,
    PRIMARY KEY (style_slug, hop_name, usage_type)
);
"""
SCHEMA += STYLE_HOP_USAGE_SCHEMA

# Paires de houblons réellement co-utilisées pour un style (T87, épique B) --
# beer-analytics.com, `hop-pairings.json` (une seule URL, PAS de filtre
# any/aroma/bittering/dry-hop côté HTML -- vérifié en direct, section sans
# `data-chart-navigation`, contrairement à `popular-hops*.json`/T86). Trace
# `box` par houblon partenaire : `share_*` = distribution de la part de
# charge houblon (`amount_percent`) de CE partenaire dans les recettes qui
# combinent les deux -- pas une fréquence de recette. ⚠ CE SONT DES PAIRES
# UNIQUEMENT (`calculate_hop_pairings` côté beer-analytics = JOIN
# `rh1.kind_id != rh2.kind_id`, seuil 20 recettes) -- ne jamais dériver un
# triplet de trois paires, ce serait une invention (T93 est le seul chemin
# vers des triplets). `style_id`/`variety` résolus comme T85/T86.
STYLE_HOP_PAIRINGS_SCHEMA = """
CREATE TABLE style_hop_pairings (
    style_slug TEXT, style_id TEXT, hop_name TEXT, variety TEXT,
    share_q1 REAL, share_median REAL, share_q3 REAL, share_mean REAL,
    source TEXT, fetched_at TEXT,
    PRIMARY KEY (style_slug, hop_name)
);
"""
SCHEMA += STYLE_HOP_PAIRINGS_SCHEMA

# Où un houblon est réellement utilisé dans le procédé, et combien (T88,
# épique B, socle empirique de T99) -- beer-analytics.com, pages
# `/hops/<purpose>/<slug>/` (purpose = aroma/bittering/dual-purpose, lu
# depuis le sitemap réel, JAMAIS deviné -- une 4e catégorie d'URL existe,
# `/hops/flavors/<terme>/`, ce sont des pages de DESCRIPTEUR D'ARÔME, pas
# des houblons, vérifié en direct et exclue). `usage-types.json` (recipes_
# count par étape : Mash/First Wort/Boil/Aroma/Dry Hop -- vocabulaire BRUT
# de la source, jamais renommé/normalisé) + `amount-used-per-use.json`
# (boxplot q1/median/q3 par étape, même 5 clés). ⚠ `Aroma` ici ≠ whirlpool :
# couvre les additions tardives fin d'ébullition/flameout selon les formats
# de recette importés par beer-analytics -- jamais renommé "Whirlpool" en
# GUI, jamais fusionné avec le `Whirlpool` de MMuM (T126, champ distinct
# d'une autre source, coexiste sans fusion). `variety` résolu via `ingest.
# _resolve_hop_variety`, NULL si non résolu (leurs slugs ne couvrent pas
# nos 189 variétés, taux de résolution rapporté comme ailleurs).
#
# `typical-styles-relative.json` (styles typiques d'un houblon, listé par
# le ticket) N'A PAS de colonne ici : ne s'indexe pas par `use_type` comme
# le reste de cette table (c'est une relation houblon->style, pas houblon->
# étape) -- le `CREATE TABLE` du ticket ne lui réservait aucune place.
# Donnée réelle et valable (vérifiée en direct), mais hors du schéma tel
# qu'écrit -- voir T131 (nouveau ticket, backlog) plutôt qu'une table
# inventée ici sans le demander.
HOP_USAGE_STATS_SCHEMA = """
CREATE TABLE hop_usage_stats (
    variety TEXT, hop_name TEXT, use_type TEXT, recipes_count INTEGER,
    amount_q1 REAL, amount_median REAL, amount_q3 REAL,
    source TEXT, fetched_at TEXT,
    PRIMARY KEY (variety, use_type, source)
);
"""
SCHEMA += HOP_USAGE_STATS_SCHEMA

# T93 (épique C, 2026-09-03) : combinaisons de houblons RÉELLEMENT observées
# ensemble dans une même recette (`recipes.db`, MMuM, T91/T92) -- table
# DÉRIVÉE, calculée par `ingest.compute_frequent_hop_combinations` (lit
# `recipes.db`, écrit ici dans `aromahops.db`, jamais l'inverse -- D4).
# `combo` : varietys membres TRIÉES alphabétiquement puis jointes par "|"
# (ex. "citra|mosaic|simcoe") -- forme canonique unique par ensemble, pas de
# colonnes variety_a/b/c/d qui laisseraient des NULL selon `size`.
# `size` : 2, 3 ou 4 -- JAMAIS dérivé d'un autre `size` (un triplet n'est
# JAMAIS reconstruit depuis 3 paires, uniquement compté quand les 3 houblons
# apparaissent ENSEMBLE dans une même recette, voir BACKLOG.md T93).
# `style_id` : BJCP style_id, NULL = toutes recettes confondues -- colonne
# PRÉSENTE mais TOUJOURS NULL pour l'instant (2026-09-03) : `recipes.
# style_id` n'est peuplé par AUCUN ticket actuel (T91 l'a explicitement
# laissé hors périmètre), donc un filtre par style ne peut structurellement
# rien retourner tant qu'une réconciliation style_raw -> style_id n'existe
# pas -- colonne gardée pour ne pas re-migrer le schéma le jour où elle
# arrive, jamais un filtre qui ferait semblant de marcher.
# `stage` : 'boil'/'whirlpool'/'first_wort'/'dry_hop' (vocabulaire
# `recipe_hops.stage`, T91) ou NULL = toutes étapes confondues (vue
# PRINCIPALE du ticket). Apport ORIGINAL signalé par le ticket : "les 3
# houblons qu'on retrouve ensemble EN DRY HOP" -- ni beer-analytics ni le
# hop-finder russe ne le calculent.
# `support` : nombre de recettes contenant ce combo (dans la tranche
# style_id/stage considérée) ; `total_recipes` : dénominateur RÉEL de cette
# tranche (recettes avec au moins un houblon résolu) -- jamais un nombre
# global fixe réutilisé entre tranches de tailles différentes.
# `lift` = P(combo) / product(P(chaque membre seul)) -- MÊME logique que la
# pondération TF-IDF de `matching.molecular_scores` (le myrcène ubiquitaire
# ne doit pas dominer par simple fréquence) ; trié dessus par défaut côté
# `matching.frequent_hop_combinations`, JAMAIS sur le support brut seul
# (Citra+Mosaic dominerait partout, pas parce qu'ils s'accordent).
HOP_COMBINATIONS_SCHEMA = """
CREATE TABLE hop_combinations (
    combo TEXT, size INTEGER, style_id TEXT, stage TEXT,
    support INTEGER, total_recipes INTEGER, lift REAL,
    source TEXT, computed_at TEXT,
    PRIMARY KEY (combo, size, style_id, stage)
);
"""
SCHEMA += HOP_COMBINATIONS_SCHEMA

# T126 (2026-09-03, épique C) : "comment ce houblon est réellement ajouté"
# -- répartition des additions RÉELLES d'une variety (corpus MMuM,
# `recipes.db`) sur les 11 classes chronologiques de `reference.
# ADDITION_TIMING_BINS`, calculée par `ingest.compute_hop_addition_timing`
# (lit `recipes.db`, écrit ici -- D4, jamais l'inverse). Une ligne PAR
# CLASSE NON VIDE (représentation creuse -- une classe sans aucune addition
# pour cette variety n'a simplement pas de ligne, jamais un `count=0`
# explicite). `total_additions`/`total_recipes` RÉPÉTÉS sur chaque ligne de
# la même variety (dénormalisé, même convention que `hop_usage_stats` --
# simplifie la lecture, `matching.hop_addition_timing` n'a besoin que d'une
# seule requête). Seuil de fiabilité (20 additions minimum pour afficher le
# graphique, ticket) appliqué CÔTÉ GUI, jamais ici -- l'ingestion écrit
# TOUJOURS la donnée brute, même pour une variety sous le seuil (la GUI
# affiche alors un effectif à la place du graphique, jamais un silence).
HOP_ADDITION_TIMING_SCHEMA = """
CREATE TABLE hop_addition_timing (
    variety TEXT, bin TEXT, count INTEGER,
    total_additions INTEGER, total_recipes INTEGER,
    source TEXT, computed_at TEXT,
    PRIMARY KEY (variety, bin)
);
"""
SCHEMA += HOP_ADDITION_TIMING_SCHEMA

# T91 (2026-08-30, D4 tranchée) : corpus BRUT de recettes (MMuM, puis
# Brewfather/DIY Dog) -- fichier `recipes.db` SÉPARÉ d'`aromahops.db`,
# jamais référencé par `app._fetch_remote_db`, jamais dans `SCHEMA`/
# `init_db` ci-dessus. Les commandes d'agrégation (T92/T93, T126/T127)
# LISENT `recipes.db` et écrivent leurs résultats dans `aromahops.db` --
# les deux bases ne communiquent jamais autrement qu'à la lecture.
# `uid` = f"{source}-{source_id}" (déterministe, `ingest.ingest_mmum`) --
# permet un ré-import idempotent (INSERT OR REPLACE) sans dépendre d'un
# AUTOINCREMENT qui romprait entre deux passes de crawl partielles.
# `style_id`/`variety` restent NULL à l'ingestion T91 (résolution BJCP et
# houblon respectivement hors périmètre de ce ticket -- voir T92 pour
# `variety`, aucun ticket encore ouvert pour `style_id` sur les recettes).
# `stage` (`recipe_hops`) dérivé de `Typ`/du bloc d'origine MMuM --
# `first_wort`/`boil`/`whirlpool`/`dry_hop`, ou NULL si `Typ` est une valeur
# non reconnue (JAMAIS deviné, voir `parsers.parse_mmum_recipe`) ;
# `addition_type` garde toujours la valeur brute allemande, y compris pour
# un `Typ` non reconnu -- aucune perte d'information même quand `stage`
# reste NULL.
# `product_form` (T92, 2026-09-03, colonne ajoutée après le premier
# passage T91 -- `ensure_columns` dans `ingest.reconcile_mmum_hop_
# varieties`, jamais un `init_recipes_db` qui viderait le corpus déjà
# crawlé) : forme de PRODUIT distincte de la variété de base, ex. "cryo" --
# un houblon Cryo n'a JAMAIS `variety` = la variété de base correspondante
# (concentration ~2x mesurée sur les lots YCH, CLAUDE.md) : `variety` reste
# NULL et `product_form="cryo"` le signale explicitement plutôt que de
# fusionner silencieusement deux compositions différentes.
# ⚠ `ingest_mmum` écrit `recipe_hops` par colonnes NOMMÉES (pas
# `VALUES (?,?,...)` positionnel) pour ne jamais dépendre de l'ordre/de la
# présence de `product_form` -- mais `INSERT OR REPLACE` reste un
# remplacement COMPLET de la ligne : un RE-crawl MMuM (`ingest_mmum` relancé
# après un premier passage déjà réconcilié par T92) remet `variety`/
# `product_form` à NULL pour les recettes retouchées, comme `variety`
# l'était déjà avant ce ticket -- `reconcile_mmum_hop_varieties` doit être
# relancé après tout re-crawl, jamais supposé stable entre deux passages.
RECIPES_SCHEMA = """
CREATE TABLE IF NOT EXISTS recipes (
    uid TEXT PRIMARY KEY, source TEXT, source_id TEXT,
    name TEXT, author TEXT, brewed_on TEXT,
    style_raw TEXT, style_id TEXT,
    og_plato REAL, og_sg REAL, fg_sg REAL, abv REAL,
    ibu REAL, ebc REAL, srm REAL, imported_at TEXT
);
CREATE TABLE IF NOT EXISTS recipe_hops (
    recipe_uid TEXT, seq INTEGER, hop_name TEXT, variety TEXT,
    stage TEXT, addition_type TEXT, time_min REAL,
    amount_g REAL, alpha REAL, product_form TEXT,
    PRIMARY KEY (recipe_uid, seq)
);
"""


def init_recipes_db(con: sqlite3.Connection) -> None:
    """Initialise `recipes.db` (T91) -- `CREATE TABLE IF NOT EXISTS`,
    JAMAIS de `DROP` (contrairement à `init_db` ci-dessus, qui vide et
    recrée tout `aromahops.db`) : un rebuild ne doit jamais effacer le
    corpus brut déjà crawlé (~2 400 requêtes réseau à 1 s d'écart pour le
    reconstituer). Idempotent, appelable à chaque `ingest.ingest_mmum` sans
    risque sur une base déjà peuplée."""
    con.executescript(RECIPES_SCHEMA)


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
        "DROP TABLE IF EXISTS style_recipe_stats;"
        "DROP TABLE IF EXISTS style_hop_usage;"
        "DROP TABLE IF EXISTS style_hop_pairings;"
        "DROP TABLE IF EXISTS hop_usage_stats;"
        "DROP TABLE IF EXISTS hop_combinations;"
        "DROP TABLE IF EXISTS hop_addition_timing;")
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
