"""Schéma SQLite (EAV, multi-sources) + validation/réparation des compositions."""
from __future__ import annotations
import sqlite3

SCHEMA = """
-- purpose : "aromatic"|"bittering"|"both"|NULL -- seule BeerMaverick classe
-- explicitement un houblon par usage (« Purpose: Aroma/Bittering/Dual », voir
-- parsers.parse_beermaverick_purpose) ; ni BarthHaas ni Yakima n'ont ce champ.
-- NULL = variété non couverte par BeerMaverick (jamais déduit de l'alpha acide
-- ou d'un autre proxy -- ce serait fabriquer une donnée, voir CLAUDE.md).
CREATE TABLE hops (
    variety TEXT PRIMARY KEY, name TEXT, region TEXT, sources TEXT, purpose TEXT
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

DROP_COMPOUNDS = {"alpha_acid", "beta_acid", "polyphenols"}  # non aromatiques


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
        "DROP TABLE IF EXISTS pubchem_cids;")
    con.executescript(SCHEMA)


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
