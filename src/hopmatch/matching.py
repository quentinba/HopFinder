"""
Moteur de matching :

  amplify(note)   — houblons qui PROLONGENT un ajout (molécules + descripteurs)
  contrast(note)  — houblons qui CONTRASTENT bien (affinités descripteurs)
  by_descriptor() — découverte par vocabulaire, sans note requise

Choix de conception (cf. discussion) : pas d'OAV quantitatif (pas de concentration
fiable). Le seuil sert de prior de puissance, la couche descripteurs est primaire,
et la couche moléculaire tourne en similarité normalisée-par-composé (TF-IDF), pas
en cosinus pseudo-OAV.

`combine()` (cas B — recomposer un profil par combinaison NNLS de houblons) a été
retiré : mesuré sur les 506 notes réelles de la base, aucune ne dépassait 20% de
couverture (max observé 12%, médiane 1.3%) — la chimie de l'huile de houblon ne
recoupe tout simplement pas la plupart des arômes alimentaires. Pire, sur les notes
à un seul composé « producible » (la majorité), NNLS retombe sur un système à une
seule équation : n'importe quel houblon portant ce composé atteint un résidu
artificiel de 0.0, ce qui affichait une fausse confiance (« 100% Talus, résidu
0.0 ») sans rapport avec la couverture réelle (~1.7%). Décision utilisateur du
2026-08-12 après vérification en direct sur plusieurs notes.

Option `biotransform` implémentée puis retirée (2026-08-12, décision utilisateur) :
redirigeait une molécule demandée par la note vers son précurseur mesuré côté
houblon (géraniol->citronellol, linalol->alpha-terpinéol). Retirée pour un vrai
bug, pas juste une hypothèse fragile : les 29 notes réelles demandant du
citronellol demandent TOUTES aussi du géraniol, donc la même mesure de géraniol
comptait deux fois dans le score (double comptage, pas une seconde source
d'évidence) — vérifié en direct, ça changeait le rang #1 sur plusieurs notes.
Voir `reference.py` pour le détail complet.
"""
from __future__ import annotations
import math
import re
import sqlite3

from . import reference

REFERENCE_THRESHOLD_PPB = 30.0


# --------------------------------------------------------------------------- #
# Chargement + réconciliation multi-sources
# --------------------------------------------------------------------------- #
def _mid(lo, hi):
    xs = [x for x in (lo, hi) if x is not None]
    return sum(xs) / len(xs) if xs else None


def _disambiguate_hop_names(hops: dict) -> None:
    """Désambiguïse EN PLACE `hops[v]["name"]` par région, uniquement en cas
    de collision de nom réelle (2026-08-19, T60 -- demande utilisateur :
    "you either need to remove duplicate or modify the name base on the
    provenance... modify the name" puisque la provenance -- région -- est
    facile à retrouver, déjà stockée dans `hops.region` et vérifiée en
    direct via l'API Algolia Yakima pour Amarillo/Perle/Saaz/Northern
    Brewer, T53/T54). Ex. deux entrées "Northern Brewer" (US vs Allemagne,
    deux `variety_code` Yakima RÉELS pour la même variété cultivée dans deux
    pays différents, pas un doublon accidentel -- les VRAIS doublons de slug
    pour la MÊME région, ex. Challenger/Fuggle, sont déjà fusionnés à
    l'ingestion, voir `ingest.merge_hop_varieties`/`_find_variety_by_name_region`,
    T53) deviennent "Northern Brewer (United States)"/"Northern Brewer
    (Germany)" -- jamais fusionnées (perdrait la distinction de terroir
    réelle), jamais laissées ambiguës.

    Appliqué UNE FOIS ici, dans `load()` -- la seule source de `hops` pour
    TOUT le reste (amplify/contrast/by_descriptor/blends/CLI/GUI) : chaque
    consommateur voit déjà le nom désambiguïsé sans code répété ailleurs.
    Ancien code équivalent (`app._disambiguated_hop_labels`, calculait une
    table de libellés séparée seulement pour le sélecteur Browse) retiré :
    plus nécessaire une fois la désambiguïsation faite à la source."""
    by_name: dict[str, list[str]] = {}
    for v, h in hops.items():
        by_name.setdefault(h["name"], []).append(v)
    for v, h in hops.items():
        if len(by_name[h["name"]]) > 1 and h.get("region"):
            h["name"] = f"{h['name']} ({h['region']})"


def load(con: sqlite3.Connection):
    hops = {r["variety"]: dict(r) for r in con.execute("SELECT * FROM hops")}
    _disambiguate_hop_names(hops)
    raw: dict = {}
    for r in con.execute("SELECT * FROM hop_composition WHERE confidence != 'suspect'"):
        raw.setdefault(r["variety"], {}).setdefault(r["compound"], []).append(
            (_mid(r["vmin"], r["vmax"]), r["unit"], r["source"]))
    comp = {}
    for v, cmap in raw.items():
        comp[v] = {}
        for compound, recs in cmap.items():
            mids = [m for m, _, _ in recs if m is not None]
            comp[v][compound] = {
                "mid": sum(mids) / len(mids) if mids else None,
                "unit": recs[0][1],
                "sources": sorted({s for _, _, s in recs}),
            }
    hop_desc: dict = {}
    for r in con.execute("SELECT variety, descriptor FROM hop_descriptors"):
        hop_desc.setdefault(r["variety"], set()).add(r["descriptor"])
    mols = {r["compound"]: dict(r) for r in con.execute("SELECT * FROM molecules")}
    return hops, comp, hop_desc, mols


def descriptor_sources(con) -> dict[str, dict[str, set[str]]]:
    """{variety: {descripteur: {sources}}} -- provenance PAR DESCRIPTEUR
    (T77, 2026-08-22, demande utilisateur explicite : "the source is
    barthhaas... does berry come from this only?" -- confusion vérifiée en
    direct sur "enigma" : la colonne "Sources" des tableaux de résultats
    n'a JAMAIS reflété que `hops.sources` (provenance de la COMPOSITION,
    ex. "barthhaas"), alors que `hop_desc` (`load()`, un simple `set[str]`
    de noms de descripteurs) ne garde PAS le `source` de `hop_descriptors` --
    "berry"/"raspberry" pour enigma viennent en réalité de BeerMaverick
    (tags de sa page produit), jamais de BarthHaas, qui ne fournit ZÉRO
    descripteur d'arôme fiable dans ce projet (voir docs/DATA_SOURCES.md).
    Fonction séparée plutôt qu'un enrichissement de `hop_desc` dans `load()`
    : `hop_desc` est un `set[str]` utilisé pour des opérations d'ensemble
    (`&`, `descriptor_overlap`) dans de nombreux appelants -- changer sa
    forme casserait ce pattern partout ; ce besoin de provenance est
    localisé à l'affichage (app.py), pas au scoring."""
    out: dict = {}
    for r in con.execute("SELECT variety, descriptor, source FROM hop_descriptors"):
        out.setdefault(r["variety"], {}).setdefault(r["descriptor"], set()).add(r["source"])
    return out


# Seuil d'acide alpha (%) séparant aromatic de bittering/both, demande
# utilisateur (2026-08-19) : "AA% mean... can be used to infer the
# aromatic/bittering status". PAS un seuil deviné/manuel -- mesuré sur les
# 142 houblons ayant À LA FOIS un `purpose` RÉEL (BeerMaverick) et un acide
# alpha connu (scan du seuil qui maximise l'accord aromatic vs
# bittering+both) : 7.0% est le meilleur séparateur trouvé, 78% d'accord
# avec le classement BeerMaverick réel (79 vrais positifs, 32 vrais
# négatifs, 20 faux positifs, 11 faux négatifs) — imparfait (chevauchement
# réel important : des houblons "aromatic" mesurés vont jusqu'à 17,5%
# d'alpha, des "bittering" descendent à 5%), mais cohérent avec la
# convention brassicole usuelle (~7-8%). D'où le label "Inferred:" en GUI,
# jamais présenté comme une donnée mesurée au même titre que BeerMaverick.
ALPHA_ACID_BITTERING_THRESHOLD_PCT = 7.0


def infer_purpose_from_alpha_acid(comp_for_variety: dict) -> str | None:
    """Devine aromatic/bittering depuis l'acide alpha moyen (mid, déjà
    réconcilié multi-sources par `load`) quand aucun `purpose` RÉEL
    (BeerMaverick) n'existe. Toujours binaire (jamais "both" — le seuil
    empirique ne sépare que 2 classes, voir `ALPHA_ACID_BITTERING_
    THRESHOLD_PCT`). None si l'acide alpha lui-même est absent (rien pour
    deviner)."""
    rec = comp_for_variety.get("alpha_acid")
    if not rec or rec.get("mid") is None:
        return None
    return "bittering" if rec["mid"] >= ALPHA_ACID_BITTERING_THRESHOLD_PCT else "aromatic"


def resolve_purpose(purpose: str | None, comp_for_variety: dict) -> tuple[str | None, bool]:
    """(purpose_effectif, est_inféré) pour L'AFFICHAGE uniquement. Le
    `purpose` RÉEL (BeerMaverick) l'emporte toujours ; repli sur l'acide
    alpha SEULEMENT s'il est absent. Jamais utilisé pour piloter la
    STRUCTURE des blends (aromatic+bittering garantis, voir
    `_pairing_grown_blends`/`purpose_by_variety`) — une estimation
    imparfaite (78% d'accord, pas une mesure) reste utile à l'affichage
    plutôt qu'un "Unknown" sans aucune piste, du moment qu'elle reste
    étiquetée comme telle (`est_inféré=True`), mais ne doit jamais devenir
    silencieusement une garantie de structure de blend."""
    if purpose is not None:
        return purpose, False
    inferred = infer_purpose_from_alpha_acid(comp_for_variety)
    return inferred, inferred is not None


def _purpose_matches_filter(resolved_purpose: str | None, purposes: set[str]) -> bool:
    """Un houblon "both" satisfait le filtre dès que L'UN des deux rôles est
    demandé (il EST aromatique ET amérisant, pas un troisième état à part) --
    jamais de correspondance pour un purpose totalement inconnu (`None`, ni
    réel ni inférable faute d'acide alpha connu) : un filtre actif exclut ce
    qu'il ne peut pas classer, plutôt que de l'inclure par défaut (T61,
    2026-08-19)."""
    if resolved_purpose is None:
        return False
    if resolved_purpose == "both":
        return bool(purposes & {"aromatic", "bittering"})
    return resolved_purpose in purposes


def hop_compound(m: str) -> str:
    """Résout un nom de molécule côté note vers le composé à chercher côté houblon
    (`reference.ALIASES`, ex. agrégations mesurées ensemble comme "thiols")."""
    return reference.ALIASES.get(m, m)


def oav_thresholds(con, molecules: list[str]) -> dict[str, float]:
    """{molécule (nom CÔTÉ NOTE, ex. "4mmp") : seuil olfactif ppb} pour
    `--oav`, résolu EN DIRECT depuis FlavorDB2 (T75, 2026-08-21, demande
    utilisateur explicite -- "update the thresholds according to flavordb2...
    don't consider oav when we don't have any, put none... never to the old
    hardcoded literals"). MÊME jointure structurale que `compound_
    descriptors` (T71/T73) : CID PubChem depuis `reference.MOLECULES` -> CAS
    via `pubchem_cids` -> seuil via `flavordb2_thresholds` -- pas une
    deuxième implémentation de la même idée, un besoin symétrique.

    Remplace l'ancien mécanisme (seuils SAISIS À LA MAIN dans `reference.
    MOLECULES`, seedés une fois dans la table `molecules` par `seed_
    reference`, jamais revus depuis). Root cause vérifiée en direct
    (2026-08-21) avant ce changement : pour les 14 molécules jusque-là
    curées, `flavordb2_thresholds` (734 composés, `ingest_flavordb2`) porte
    déjà un seuil RÉEL pour 5 d'entre elles -- caryophyllène (64 codé en dur
    vs 77.0 chez FlavorDB2), géraniol (4 vs 39.5, x10 !), linalol (6 vs
    7.0), beta-pinène (140 vs 140.0, identique -- la valeur en dur en avait
    probablement été recopiée à l'origine), citronellol (8 vs 11.0) --
    c'est-à-dire que le scoring utilisait un chiffre DIFFÉRENT de celui que
    ce même projet avait déjà scrapé et stocké, sans que personne ne le
    sache en regardant un résultat. Les 9 autres (dont myrcène) n'ont
    simplement AUCUN seuil FlavorDB2 -- vérifié en DIRECT sur le site réel
    pour myrcène/humulène/farnésène/limonène/terpinolène/géranial (pas
    seulement en base) : myrcène n'a qu'une COMPOSITION en % ("Aroma
    characteristics at 10%..."), farnésène/terpinolène pareil, géranial
    n'a qu'une description sans nombre, humulène n'a carrément aucune
    section seuil, limonène n'a qu'un seuil de GOÛT (pas d'arôme) -- confirmé
    comportement correct de `parsers.parse_flavordb2_threshold`, PAS un bug
    de correspondance de nom/CAS/CID.

    Molécule sans CID connu (ex. "thiols", agrégation sans molécule unique
    -- voir `reference.ALIASES`), CAS non résolu, ou seuil FlavorDB2 absent
    -> ABSENTE du dict retourné, JAMAIS une valeur de repli (ni l'ancien
    seuil codé en dur, ni une estimation). `molecular_scores` traite une
    molécule absente d'ici comme un multiplicateur neutre (1.0), jamais une
    exclusion du score -- voir sa docstring."""
    out = {}
    for m in molecules:
        cid = reference.MOLECULES.get(hop_compound(m), (None, None, None))[2]
        if not cid:
            continue
        cas_row = con.execute("SELECT cas FROM pubchem_cids WHERE cid=?", (cid,)).fetchone()
        if not cas_row:
            continue
        thr_row = con.execute(
            "SELECT threshold_ppb FROM flavordb2_thresholds WHERE cas=?", (cas_row[0],)).fetchone()
        if thr_row and thr_row[0] is not None:
            out[m] = thr_row[0]
    return out


def amount(variety: str, molecule: str, comp) -> float:
    rec = comp.get(variety, {}).get(hop_compound(molecule))
    if not rec or rec["mid"] is None:
        return 0.0
    if rec["unit"] == "pct_oil":
        oil = comp.get(variety, {}).get("total_oil")
        return (rec["mid"] / 100.0) * ((oil["mid"] if oil else 1.0) or 1.0)
    return rec["mid"]


def specificity(molecule: str, comp) -> float:
    c = hop_compound(molecule)
    n = len(comp)
    n_with = sum(1 for h in comp if comp[h].get(c) and comp[h][c]["mid"])
    return math.log(n / (1 + n_with)) + 1.0


def get_note(con, note: str) -> dict[str, float]:
    rows = con.execute("SELECT molecule, weight FROM aroma_notes WHERE note=?", (note,)).fetchall()
    if not rows:
        avail = [r[0] for r in con.execute("SELECT DISTINCT note FROM aroma_notes")]
        raise KeyError(f"Note inconnue : {note!r}. Dispo : {', '.join(sorted(avail))}")
    return {r["molecule"]: r["weight"] for r in rows}


def get_note_descriptors(con, note: str) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT descriptor FROM note_descriptors WHERE note=?", (note,))}


# T79 (2026-08-22, demande utilisateur explicite) : BarthHaas alimente
# désormais aussi `hop_aroma_intensity` (roue "rose chart", voir
# `parsers.parse_barthhaas_aroma_wheel`/`ingest.crawl_barthhaas`), sur une
# échelle DIFFÉRENTE de celle de Yakima -- 0-8 environ (mesuré : min 0.0,
# max 8.0 EXACTEMENT sur les 1164 valeurs des 97 variétés BarthHaas, jamais
# dépassé -> traité comme le plafond réel de leur échelle, pas une
# supposition), contre 0-100 pour Yakima (mesuré : moyenne ~39). Un bug
# RÉEL a été trouvé en vérifiant en direct après le premier crawl complet :
# l'ancienne requête `SELECT descriptor, intensity FROM hop_aroma_intensity
# WHERE variety=?` ne filtrait PAS par source -- pour un houblon à double
# source (ex. citra, mosaic), une catégorie partagée entre les deux
# (ex. "citrus") pouvait être silencieusement écrasée par la dernière ligne
# lue, mélangeant DANS LE MÊME polygone des axes à des échelles
# incompatibles (visuellement : roue déformée ; en scoring, `by_descriptor`
# moyenne des intensités brutes -> un houblon BarthHaas-only aurait
# artificiellement toujours un score écrasé, peu importe son intensité
# RELATIVE réelle).
#
# Politique retenue (demande utilisateur explicite, "no per-hop choice" par
# défaut, un TOGGLE seulement là où un houblon UNIQUE est affiché) :
# jamais de mélange DANS un même houblon -- une seule source à la fois,
# entière, pour un houblon donné. Par défaut (`prefer=None`) : Yakima si
# disponible, sinon BarthHaas (remise à l'échelle 0-100, jamais les valeurs
# brutes 0-8 telles quelles) -- jamais les deux mélangées catégorie par
# catégorie. `prefer` permet un override explicite (le toggle GUI) --
# retombe silencieusement sur l'autre source si celle demandée n'existe
# pas pour ce houblon (jamais un houblon vidé par un choix utilisateur qui
# ne s'applique pas ici), la source RÉELLEMENT utilisée est toujours
# renvoyée pour affichage (jamais caché à l'utilisateur, même principe que
# T77 "Descriptor sources").
BARTHHAAS_AROMA_WHEEL_MAX = 8.0


def load_aroma_intensity(con) -> dict[str, dict[str, dict[str, float]]]:
    """{variety: {source: {catégorie: intensité BRUTE}}} -- UNE requête pour
    toute la base, RAW (pas encore résolu/remis à l'échelle) : sert de socle
    commun à `hop_aroma_intensity` (un houblon) et aux 3 consommateurs en
    masse (`by_descriptor`, `similar_hops_by_aroma_wheel`, `similar_hops`),
    qui faisaient chacun leur propre `SELECT ... FROM hop_aroma_intensity`
    sans filtre de source avant ce correctif (T79)."""
    out: dict[str, dict[str, dict[str, float]]] = {}
    for r in con.execute("SELECT variety, source, descriptor, intensity FROM hop_aroma_intensity"):
        out.setdefault(r["variety"], {}).setdefault(r["source"], {})[r["descriptor"]] = r["intensity"]
    return out


# seuil par défaut du filtre "quasi jamais utilisé" (T108) -- ajustable en
# GUI, cette valeur n'est qu'un point de départ suggéré par le ticket.
DEFAULT_MIN_POPULARITY_RECIPES = 50


def hop_popularity(con) -> dict[str, int]:
    """{variety: nombre total de recettes} depuis `hop_usage_stats` (T88,
    beer-analytics.com) -- SOMME de `recipes_count` sur les 5 `use_type`
    (Mash/First Wort/Boil/Aroma/Dry Hop) d'un même houblon, un proxy de
    popularité relative (pas un compte de recettes UNIQUES : une recette
    utilisant un houblon à la fois en Boil et en Dry Hop compte deux fois --
    acceptable pour un TRI/FILTRE relatif, jamais présenté comme "nombre de
    recettes"). Une `variety` absente de ce dict n'a AUCUNE ligne
    `hop_usage_stats` (houblon non résolu côté beer-analytics, voir T88) --
    à distinguer d'une popularité mesurée comme faible, jamais traité comme
    0 par l'appelant (voir T108 : groupe "no data" séparé, pas un 0
    implicite en bas d'un tri)."""
    out: dict[str, int] = {}
    for r in con.execute(
        "SELECT variety, SUM(recipes_count) AS total FROM hop_usage_stats "
        "WHERE variety IS NOT NULL AND recipes_count IS NOT NULL GROUP BY variety"):
        out[r["variety"]] = r["total"]
    return out


def hop_usage_breakdown_all(con) -> dict[str, dict[str, dict]]:
    """{variety: {use_type: {"recipes_count", "share"}}} depuis
    `hop_usage_stats` (T88, beer-analytics.com) pour TOUTES les variétés
    couvertes, en un seul passage SQL -- `share` = part de `recipes_count`
    de ce `use_type` sur le TOTAL des 5 `use_type` (Mash/First Wort/Boil/
    Aroma/Dry Hop) de CE houblon. AUCUNE modélisation : un fait observé
    directement, part réelle de recettes par étape du procédé (T99, couche
    empirique). Variété sans ligne, ou dont le total vaut 0, absente du
    dict -- jamais une répartition uniforme fabriquée pour un houblon non
    couvert."""
    by_variety: dict[str, list[tuple[str, int]]] = {}
    for r in con.execute(
        "SELECT variety, use_type, recipes_count FROM hop_usage_stats "
        "WHERE recipes_count IS NOT NULL"):
        by_variety.setdefault(r["variety"], []).append((r["use_type"], r["recipes_count"]))
    out: dict[str, dict[str, dict]] = {}
    for v, rows in by_variety.items():
        total = sum(c for _, c in rows)
        if total == 0:
            continue
        out[v] = {ut: {"recipes_count": c, "share": c / total} for ut, c in rows}
    return out


def hop_usage_breakdown(con, variety: str) -> dict[str, dict]:
    """{use_type: {"recipes_count", "share"}} pour UN houblon -- voir
    `hop_usage_breakdown_all` (T99). Dict vide si le houblon n'est pas
    couvert par beer-analytics.com."""
    return hop_usage_breakdown_all(con).get(variety, {})


def style_observed_distribution(con, style_id: str) -> dict[str, list[dict]]:
    """{metric: [{"bin_low", "bin_high", "count"}, ...]} depuis
    `style_recipe_stats` (T85, beer-analytics.com) pour un `style_id` BJCP
    donné, bins triés par `bin_low` -- métriques en minuscules telles que
    stockées (`abv`/`ibu`/`og`/`fg`/`srm`). Histogramme PRÉ-BINNÉ avec
    outliers déjà retirés côté beer-analytics -- jamais un percentile
    dérivable (T105 : afficher "observed distribution", jamais "P5-P95").
    Un `style_id` sans aucune ligne (style non résolu côté beer-analytics,
    ou non couvert par leur crawl) renvoie un dict vide, jamais un
    histogramme vide fabriqué."""
    out: dict[str, list[dict]] = {}
    for r in con.execute(
        "SELECT metric, bin_low, bin_high, count FROM style_recipe_stats "
        "WHERE style_id=? ORDER BY metric, bin_low", (style_id,)):
        out.setdefault(r["metric"], []).append(
            {"bin_low": r["bin_low"], "bin_high": r["bin_high"], "count": r["count"]})
    return out


# T86 a résolu ~90,3% des `variety` de `style_hop_usage` vers un `variety`
# de `hops` (le reste : houblons trop rares côté beer-analytics ou noms
# ambigus non réconciliés, données réelles mais non exploitables ici) --
# JOIN explicite plutôt qu'un filtre applicatif, jamais une variété
# fabriquée pour combler le reste (T103, croisement avec `by_descriptor`
# qui n'opère que sur `hops`).
def style_hop_frequency(con, style_id: str, usage_type: str = "any") -> dict[str, dict]:
    """{variety: {"hop_name", "share_latest", "share_avg24m"}} depuis
    `style_hop_usage` (T86, beer-analytics.com) pour un `style_id` BJCP et
    un `usage_type` donnés ("any"/"bittering"/"aroma"/"dry-hop") -- part de
    recettes de CE STYLE utilisant ce houblon, PAS une pertinence
    aromatique (voir `style_typical_descriptors`/`by_descriptor` pour ça,
    T103). Dict vide si le style n'est pas couvert par beer-analytics pour
    ce `usage_type`."""
    out: dict[str, dict] = {}
    for r in con.execute(
        "SELECT s.variety, s.hop_name, s.recipes_pct_latest, s.recipes_pct_avg24m "
        "FROM style_hop_usage s JOIN hops h ON s.variety = h.variety "
        "WHERE s.style_id=? AND s.usage_type=?", (style_id, usage_type)):
        out[r["variety"]] = {"hop_name": r["hop_name"], "share_latest": r["recipes_pct_latest"],
                             "share_avg24m": r["recipes_pct_avg24m"]}
    return out


def style_typical_descriptors(con, style_id: str) -> list[str]:
    """Pré-remplissage (T103) des descripteurs typiques d'un style : mots du
    vocabulaire RÉEL `hop_descriptors` (138 termes) trouvés littéralement
    dans le texte BJCP officiel du style (`aroma`/`flavor`/`ingredients`,
    T81, curé et écrit par des humains) -- PAS une dérivation statistique/
    co-occurrence comme les essais FooDB déjà rejetés deux fois (voir
    CLAUDE.md, "Descripteurs auto-dérivés de FooDB testés et rejetés").
    Recherche insensible à la casse, sur mot entier (`\\b...\\b`, pour que
    "ale" ne matche pas dans "pale"). PRÉ-REMPLISSAGE ÉDITABLE côté GUI
    (ticket : "la seconde [option], pré-remplie et éditable" plutôt qu'une
    extraction automatique opaque) -- jamais un filtre imposé.

    Liste vide si le style est inconnu, ou si aucun terme du vocabulaire
    n'apparaît dans son texte -- jamais une liste fabriquée."""
    row = con.execute(
        "SELECT aroma, flavor, ingredients FROM beer_styles WHERE style_id=?",
        (style_id,)).fetchone()
    if row is None:
        return []
    text = " ".join(row[f] or "" for f in ("aroma", "flavor", "ingredients")).lower()
    vocabulary = (r[0] for r in con.execute("SELECT DISTINCT descriptor FROM hop_descriptors"))
    return sorted(d for d in vocabulary if re.search(rf"\b{re.escape(d)}\b", text))


def _usable_aroma_readings(values: dict[str, float]) -> bool:
    """Une entrée `hop_aroma_intensity` "présente mais entièrement à 0" (le
    cas corrompu déjà documenté côté Yakima, ex. `admiral`, voir
    `docs/DATA_SOURCES.md`) n'est PAS une vraie mesure exploitable -- même
    convention que les appelants GUI (`any(val > 0 ...)`), factorisée ici
    pour T79 addendum (voir `resolve_aroma_intensity`)."""
    return bool(values) and any(v > 0 for v in values.values())


def resolve_aroma_intensity(by_source: dict[str, dict[str, float]],
                            prefer: str | None = None) -> tuple[dict[str, float], str | None]:
    """Résout LA source à utiliser pour UN houblon (jamais un mélange de
    deux) à partir de `{source: {catégorie: intensité brute}}` (voir
    `load_aroma_intensity`) -- renvoie (intensités sur 0-100, source
    utilisée) ; (`{}`, `None`) si `by_source` est vide. `prefer` (le
    toggle GUI) retombe silencieusement sur l'autre source dispo si la
    source demandée n'existe pas pour CE houblon précis.

    T79 addendum (signalé en direct par l'utilisateur sur Admiral) : l'ordre
    de préférence par défaut (Yakima puis BarthHaas) sautait par-dessus une
    entrée Yakima PRÉSENTE mais entièrement corrompue à 0 (cas documenté
    `docs/DATA_SOURCES.md`) -- la roue s'affichait alors vide plutôt que de
    retomber automatiquement sur BarthHaas, pourtant disponible et réel.
    L'ordre de préférence (`prefer` d'abord si fourni, puis Yakima, puis les
    autres sources) ne retient désormais que la PREMIÈRE source à la fois
    présente ET exploitable (`_usable_aroma_readings`) ; si AUCUNE source
    n'est exploitable (toutes vides/à 0), repli sur l'ancien comportement
    (peu importe laquelle, le résultat est dégénéré de toute façon -- jamais
    une exception, jamais un houblon qui disparaît)."""
    if not by_source:
        return {}, None
    order = ([prefer] if prefer else []) + ["yakima"] + [s for s in by_source if s not in (prefer, "yakima")]
    source = next((s for s in order if s in by_source and _usable_aroma_readings(by_source[s])), None)
    if source is None:
        source = prefer if prefer in by_source else ("yakima" if "yakima" in by_source else next(iter(by_source)))
    values = by_source[source]
    if source == "barthhaas":
        values = {d: min(100.0, v * 100.0 / BARTHHAAS_AROMA_WHEEL_MAX) for d, v in values.items()}
    return values, source


def select_aroma_intensity(by_source: dict[str, dict[str, float]], source: str) -> dict[str, float]:
    """Intensités pour EXACTEMENT la `source` demandée -- JAMAIS de repli
    automatique vers l'autre source, contrairement à `resolve_aroma_
    intensity` (qui reste utilisé tel quel pour le SCORE/tri, voir
    `by_descriptor`/`similar_hops*`). 2026-08-23 (demande utilisateur
    explicite) : pour l'AFFICHAGE de la roue d'arôme, Yakima/BarthHaas
    devient un TOGGLE explicite ("Yakima <> BarthHaas") plutôt qu'une
    préférence avec repli silencieux -- l'appelant doit pouvoir savoir que
    la source choisie ne couvre PAS ce houblon (pour afficher un
    avertissement, voir `app._aroma_wheel_missing_warning`) au lieu de
    voir apparaître l'autre source sans prévenir. `{}` si `source` est
    absente ou dégénérée (aucune valeur > 0, cas corrompu documenté) pour
    ce houblon. Remise à l'échelle 0-8->0-100 uniquement pour BarthHaas,
    comme `resolve_aroma_intensity`."""
    values = by_source.get(source, {})
    if not _usable_aroma_readings(values):
        return {}
    if source == "barthhaas":
        return {d: min(100.0, v * 100.0 / BARTHHAAS_AROMA_WHEEL_MAX) for d, v in values.items()}
    return dict(values)


def default_aroma_wheel_source(by_source: dict[str, dict[str, float]]) -> str:
    """Valeur INITIALE du toggle Yakima<>BarthHaas pour UN houblon affiché
    seul (Browse, détail Amplify/Contrast/By-descriptor) : Yakima par
    défaut, sauf si Yakima est absent/dégénéré ET que BarthHaas, lui, est
    exploitable pour ce houblon précis -- alors BarthHaas (2026-08-23,
    demande utilisateur explicite, même logique que l'ancien repli
    automatique de `resolve_aroma_intensity`, désormais exprimée comme un
    simple choix de valeur par défaut d'un widget explicite plutôt qu'un
    repli caché à l'affichage)."""
    if not _usable_aroma_readings(by_source.get("yakima", {})) and \
            _usable_aroma_readings(by_source.get("barthhaas", {})):
        return "barthhaas"
    return "yakima"


def default_aroma_wheel_source_for_varieties(
        all_intensity: dict[str, dict[str, dict[str, float]]], varieties: list[str]) -> str:
    """Valeur INITIALE du toggle pour Compare Hops (plusieurs houblons sur
    UN graphique partagé, un SEUL toggle pour tous -- voir `app._compare`) :
    Yakima par défaut, sauf si AUCUN des houblons sélectionnés n'a de
    lecture Yakima exploitable ET qu'AU MOINS un a une lecture BarthHaas
    exploitable -- alors BarthHaas (2026-08-23, demande utilisateur
    explicite : "if both/all hops are missing from yakima, put brathaas
    results if at least one hop is existing in this database")."""
    any_yakima = any(_usable_aroma_readings(all_intensity.get(v, {}).get("yakima", {})) for v in varieties)
    any_barthhaas = any(_usable_aroma_readings(all_intensity.get(v, {}).get("barthhaas", {})) for v in varieties)
    if not any_yakima and any_barthhaas:
        return "barthhaas"
    return "yakima"


def aroma_wheel_vocabulary(con, sources: set[str] | frozenset[str] | None = None) -> list[str]:
    """Catégories distinctes de `hop_aroma_intensity`, éventuellement
    restreintes aux SOURCES données. T79 addendum (signalé en direct par
    l'utilisateur) : BarthHaas ne couvre que 12 des 16 catégories connues
    (voir `data/mappings/barthhaas_aroma_wheel_categories.yaml`) -- afficher
    le vocabulaire COMPLET (16, comportement historique) sur une roue
    résolue en BarthHaas dessine 4 axes Yakima-only (melon/earthy/stone
    fruit/dried fruit) TOUJOURS à zéro pour cette source, un bruit visuel
    trompeur (laisse croire à une absence de donnée plutôt qu'à une
    catégorie inexistante côté BarthHaas). `sources=None` renvoie le
    vocabulaire complet -- comportement inchangé pour les usages
    source-agnostiques (ex. les pills de sélection `by-descriptor`, qui
    filtrent/notent sans jamais rendre de roue elles-mêmes)."""
    if not sources:
        return sorted(r[0] for r in con.execute("SELECT DISTINCT descriptor FROM hop_aroma_intensity"))
    placeholders = ",".join("?" * len(sources))
    rows = con.execute(
        f"SELECT DISTINCT descriptor FROM hop_aroma_intensity WHERE source IN ({placeholders})",
        tuple(sources))
    return sorted(r[0] for r in rows)


def hop_aroma_intensity(con, variety: str, prefer: str | None = None) -> tuple[dict[str, float], str | None]:
    """Roue d'arôme QUANTITATIVE d'UN houblon (T26 backlog ; multi-source
    depuis T79, voir le commentaire au-dessus de `BARTHHAAS_AROMA_WHEEL_MAX`)
    -- {descriptor: intensité 0-100}, JAMAIS un mélange Yakima/BarthHaas
    dans le même houblon. Renvoie (intensités, source utilisée) ; ({}, None)
    pour un houblon sans aucune donnée. `prefer` = override explicite
    (toggle GUI), retombe silencieusement sur l'autre source si absente ici."""
    by_source: dict[str, dict[str, float]] = {}
    for r in con.execute(
            "SELECT source, descriptor, intensity FROM hop_aroma_intensity WHERE variety=?", (variety,)):
        by_source.setdefault(r["source"], {})[r["descriptor"]] = r["intensity"]
    return resolve_aroma_intensity(by_source, prefer)


def compound_descriptors(con, compounds: list[str]) -> dict[str, str]:
    """{composé (vocabulaire houblon, ex. "myrcene") : descripteurs odeur
    Flavornet (GC-O, anglais, ex. "balsamic, must, spice")} pour un tooltip
    par composé (T70, 2026-08-21, demande utilisateur explicite -- "myrcene
    est une chaîne nue... rien ne dit qu'elle couvre vert, herbacé,
    résineux et pin", même pattern que les tooltips de la roue d'arôme
    Yakima sur `AROMA_WHEEL_DEFINITIONS`).

    Jointure par IDENTITÉ STRUCTURALE (CID PubChem -> CAS -> `flavornet_
    compounds`), PAS par nom : `reference.MOLECULES[c][2]` donne le CID
    PubChem du composé (curé, ~14 molécules d'huile de houblon courantes) ;
    `pubchem_cids` (déjà peuplée par `ingest.resolve_pubchem_cids`, table
    cas<->cid) résout ce CID vers son CAS ; `flavornet_compounds` (734
    composés odeur-actifs GC-O, `ingest.ingest_flavornet`) donne enfin les
    descripteurs pour ce CAS -- même principe d'identité chimique (CID/CAS)
    que `ingest._canonical_compound`/`_build_cas_to_hop_name` à
    l'ingestion, jamais un rapprochement par nom de chaîne.

    Composé absent de `reference.MOLECULES` (ex. "isobutyrate", "ketones"
    -- agrégations non individuellement curées), CID inconnu, ou CAS sans
    entrée Flavornet -> Flavornet n'apporte rien pour ce composé (pas une
    entrée vide/inventée), mais voir ci-dessous pour un second repli.

    **Complété par `reference.JANISH_COMPOUND_CATEGORIES`** (T73,
    2026-08-21, demande utilisateur explicite : croiser chaque composé
    contre le tableau "Compound Descriptions" de Scott Janish, The New IPA,
    et ajouter ce qui manque). Source DISTINCTE de Flavornet (livre de
    brassage, pas une mesure GC-O) -- jamais fusionnée sans attribution :
    ajoutée à la fin de la chaîne, séparée par "; ", explicitement citée
    "(Janish, The New IPA)". N'ajoute une catégorie QUE si elle n'est pas
    déjà représentée par un mot Flavornet existant (comparaison par racine
    de 4 lettres, ex. "wood" (Flavornet) couvre déjà "Woody" (livre) --
    évite un doublon plutôt qu'une simple vérification d'égalité stricte,
    qui laisserait passer des quasi-synonymes). Seul répondant de dernier
    recours pour un composé sans AUCUNE résolution Flavornet (ex. "thiols",
    qui n'a pas de CID propre -- voir `reference.ALIASES` -- et qui obtient
    ici sa toute première étiquette, "berry & currant", via le composé
    4MMP explicitement listé dans cette catégorie par le livre)."""
    out = {}
    for c in compounds:
        parts = []
        cid = reference.MOLECULES.get(c, (None, None, None))[2]
        if cid:
            cas_row = con.execute("SELECT cas FROM pubchem_cids WHERE cid=?", (cid,)).fetchone()
            if cas_row:
                desc_row = con.execute(
                    "SELECT descriptors FROM flavornet_compounds WHERE cas=?", (cas_row[0],)).fetchone()
                if desc_row and desc_row[0]:
                    parts.append(desc_row[0])
        existing = parts[0].lower() if parts else ""
        missing_categories = [cat for cat in reference.JANISH_COMPOUND_CATEGORIES.get(c, [])
                              if cat[:4].lower() not in existing]
        if missing_categories:
            parts.append(", ".join(missing_categories) + " (Janish, The New IPA)")
        if parts:
            out[c] = "; ".join(parts)
    return out


def process_survival(compound: str) -> dict[str, str] | None:
    """Annotation de survie au procédé pour `compound` (T74, 2026-08-21,
    demande utilisateur explicite -- lecture pure de
    `reference.PROCESS_SURVIVAL`, aucune requête DB : contrairement à
    `compound_descriptors`, cette info ne dépend d'aucune donnée houblon
    (c'est une propriété de la MOLÉCULE, pas du houblon qui la porte).

    Retourne {"class", "subclass", "annotation", "confidence"} ou `None` si
    `compound` n'est pas dans `reference.PROCESS_SURVIVAL` (composé non
    mappé, ou explicitement exclu -- alpha_acid/beta_acid/co_humulone/
    total_oil, voir `NON_AROMA_DISPLAY` -- ne s'y trouvent jamais) : JAMAIS
    une valeur par défaut fabriquée, contrainte explicite de ce ticket
    ("Fonction de lookup renvoyant None pour un composé non mappé, jamais
    une valeur par défaut"). Purement informatif -- n'est appelé par AUCUN
    chemin de scoring (`molecular_scores`/`amplify`/`contrast`/
    `by_descriptor`), uniquement par la GUI pour l'affichage."""
    return reference.PROCESS_SURVIVAL.get(compound)


def compound_survival(compound: str, stage: str) -> dict[str, str] | None:
    """T119 (2026-08-29) : survie de `compound` à un `stage` de procédé
    donné (`stage` in {"boil", "whirlpool", "afdh", "pfdh"}) -- question
    PLUS FINE que `process_survival` ci-dessus (qui donne une annotation
    par CLASSE de composé, pas par stade). Lecture pure de
    `reference.PROCESS_STAGE_SURVIVAL`, aucune requête DB -- même
    justification que `process_survival` : c'est une propriété de la
    molécule/du procédé, pas du houblon qui la porte.

    Retourne `{"state", "source", "note"}` -- `state` in {"kept", "partial",
    "lost", "precursor"}, ordinal QUALITATIF, jamais un pourcentage inventé
    (aucune source ne donne de facteur de survie chiffré réel). Retourne
    `None` si `compound` n'est pas dans la matrice (composé hors du
    périmètre des 11 de `reference.PROCESS_SURVIVAL`) OU si `stage` n'est
    pas l'un des 4 stades reconnus -- JAMAIS une valeur par défaut
    fabriquée, même contrainte que `process_survival`. Purement informatif
    -- n'est appelé par AUCUN chemin de scoring, uniquement par la GUI."""
    return reference.PROCESS_STAGE_SURVIVAL.get(compound, {}).get(stage)


_PLAN_STAGES = frozenset({"boil", "whirlpool", "afdh", "pfdh"})


def hopping_plan_coverage(con, plan: list[tuple[str, str]]) -> list[dict]:
    """T120 (2026-08-30) : couverture composé par composé d'un plan de
    houblonnage `plan = [(variety, stage), ...]` (un même houblon peut
    apparaître à plusieurs stades). **On constate, on ne propose pas** --
    aucun solveur, aucune optimisation.

    Périmètre composé = EXACTEMENT les 11 de `reference.PROCESS_STAGE_
    SURVIVAL` (celui de T119), dans son ordre d'insertion (même ordre que
    le 2e barplot de Compare Hops -- les deux vues doivent se lire pareil,
    T121).

    Une entrée par composé :
    `{"compound", "state": "delivered"|"presumed_absent", "delivered_by":
    [{"variety", "stage", "amount", "unit"}], "precursor_by": [...même
    forme...], "survival": "kept"|"partial"|None, "measured_source_missing"}`.

    **Règle de combinaison** : un composé est `delivered` si au moins un
    couple (houblon, stade) du plan a (a) une valeur mesurée NON NULLE pour
    ce composé (`matching.load` -- déjà réconcilié multi-sources, moyenne
    des milieux) ET (b) un `state` T119 valant "kept" ou "partial" à ce
    stade. `survival` reflète alors le meilleur des états contributeurs
    ("kept" prime sur "partial" si le plan mélange les deux). Un couple
    dont le `state` T119 vaut "precursor" ne livre PAS le composé lui-même
    -- il est reporté séparément dans `precursor_by` (T119 : "il ne livre
    pas le composé, il en génère un autre" -- ex. humulène au boil ne
    devient jamais "delivered", même mesuré, mais apparaît dans
    `precursor_by` pour signaler l'arôme épicé/boisé généré par oxydation).
    Un couple dont le `state` T119 vaut "lost", ou sans valeur mesurée, ou
    hors matrice T119 (composé/stade inconnu), ne contribue à rien.

    **Doctrine « a priori »** (décision utilisateur, intro de l'épique
    procédé) : l'ABSENCE de ligne `hop_composition` est traitée comme « a
    priori absent », jamais comme « inconnu » -- `state="presumed_absent"`
    est donc la valeur par défaut d'un composé qu'aucun couple ne livre,
    PAS une 3e valeur "unknown". **Seule nuance conservée** :
    `measured_source_missing=True` quand AUCUNE des sources qui mesurent ce
    composé quelque part dans la base n'a jamais mesuré NE SERAIT-CE QU'UN
    AUTRE composé pour l'un des houblons du plan (concrètement : isobutyrate/
    ketones/thiols ne viennent que de BarthHaas -- un houblon totalement
    absent du catalogue BarthHaas, càd sans AUCUNE ligne `hop_composition`
    de source barthhaas pour ce houblon, n'a pas été « mesuré à ~0 », il n'a
    pas été regardé). Seulement calculé quand `state="presumed_absent"` --
    si le composé est déjà `delivered` par un autre couple du plan, la
    question ne se pose pas pour ce composé. `False` par construction si
    aucune source ne mesure jamais ce composé nulle part dans la base (cas
    dégénéré, ne devrait pas arriver sur les 11 composés réels du
    périmètre)."""
    hops, comp, hop_desc, mols = load(con)
    for _, stage in plan:
        if stage not in _PLAN_STAGES:
            raise ValueError(f"stade de procédé inconnu : {stage!r} (attendu {sorted(_PLAN_STAGES)})")

    compound_sources: dict[str, set[str]] = {}
    for v_comp in comp.values():
        for compound, info in v_comp.items():
            compound_sources.setdefault(compound, set()).update(info.get("sources", ()))

    varieties_in_plan = {variety for variety, _ in plan}
    variety_sources: dict[str, set[str]] = {}
    for v in varieties_in_plan:
        seen: set[str] = set()
        for info in comp.get(v, {}).values():
            seen.update(info.get("sources", ()))
        variety_sources[v] = seen

    out = []
    for compound in reference.PROCESS_STAGE_SURVIVAL:
        delivered_by, precursor_by, survival_states = [], [], []
        for variety, stage in plan:
            entry = comp.get(variety, {}).get(compound)
            if not entry or entry["mid"] in (None, 0):
                continue
            surv = compound_survival(compound, stage)
            if surv is None:
                continue
            row = {"variety": variety, "stage": stage, "amount": entry["mid"], "unit": entry["unit"]}
            if surv["state"] in ("kept", "partial"):
                delivered_by.append(row)
                survival_states.append(surv["state"])
            elif surv["state"] == "precursor":
                precursor_by.append(row)
        state = "delivered" if delivered_by else "presumed_absent"
        survival = "kept" if "kept" in survival_states else ("partial" if survival_states else None)
        missing_source = False
        if state == "presumed_absent":
            sources_for_compound = compound_sources.get(compound, set())
            missing_source = bool(sources_for_compound) and not any(
                variety_sources.get(v, set()) & sources_for_compound for v in varieties_in_plan)
        out.append({"compound": compound, "state": state, "delivered_by": delivered_by,
                   "precursor_by": precursor_by, "survival": survival,
                   "measured_source_missing": missing_source})
    return out


def hop_similar_varieties(con, variety: str) -> list[str]:
    """Variétés similaires/substituts curées par Yakima (T25 backlog,
    `hop_similar`) — toujours une `variety` de notre propre catalogue (résolue
    à l'ingestion, voir `ingest.crawl_yakima`), jamais un nom brut hors
    catalogue. Vide si non couvert (BarthHaas seul, ou pas de suggestion YCH)."""
    return [r[0] for r in con.execute(
        "SELECT similar_variety FROM hop_similar WHERE variety=?", (variety,))]


def hop_pairings(con, variety: str) -> list[dict]:
    """Associations fréquentes en recette (T25 backlog, `hop_pairings`,
    BeerMaverick — AGRÉGATEUR, pas une mesure de labo, à afficher avec cette
    réserve). Triées par fréquence décroissante. `variety` (clé interne, pour
    lien cliquable) est None si le nom affiché par BeerMaverick n'a pas pu
    être réconcilié avec notre catalogue (voir `ingest._resolve_hop_variety`)
    — `name` (texte brut) reste toujours renseigné."""
    rows = con.execute(
        "SELECT paired_name, paired_variety, frequency FROM hop_pairings "
        "WHERE variety=? ORDER BY frequency DESC", (variety,))
    return [{"name": r["paired_name"], "variety": r["paired_variety"],
             "frequency": r["frequency"]} for r in rows]


def hop_substitutions(con, variety: str) -> list[dict]:
    """Substitutions suggérées (T25 backlog, `hop_substitutions`, BeerMaverick
    — choix éditorial de brasseurs expérimentés, pas une mesure). Même
    contrat que `hop_pairings` pour `variety`/`name`."""
    rows = con.execute(
        "SELECT substitute_name, substitute_variety FROM hop_substitutions WHERE variety=?",
        (variety,))
    return [{"name": r["substitute_name"], "variety": r["substitute_variety"]} for r in rows]


def hop_beer_styles(con, variety: str) -> list[dict]:
    """Styles éditoriaux suggérés pour ce houblon (T83 backlog,
    `hop_beer_styles`) -- vocabulaire libre d'une source (Yakima
    `imported_fields.beer_types`, ou BeerMaverick "Beer Styles using X
    Hops"), PAS une fréquence mesurée en recettes réelles (voir l'épique B,
    `style_hop_usage`, pour ça). `style_id` (BJCP, `data/mappings/beer_
    style_aliases.yaml`, T84) est `None` quand l'étiquette n'a pas de
    correspondance BJCP certaine -- affiché tel quel, jamais deviné.
    Chaque ligne garde sa `source` : les deux sources ne sont JAMAIS
    fusionnées (même règle que `hop_similar`/`hop_pairings`/`hop_
    substitutions`, voir CLAUDE.md)."""
    rows = con.execute(
        "SELECT style_label, style_id, source FROM hop_beer_styles WHERE variety=? "
        "ORDER BY source, style_label", (variety,))
    return [{"label": r["style_label"], "style_id": r["style_id"], "source": r["source"]}
           for r in rows]


def _normalize_descriptors(descriptors: list[str]) -> set[str]:
    """Vocabulaire réel `hop_descriptors` (comme `by_descriptor`), pas inventé —
    même normalisation utilisée par `amplify`/`contrast` pour une sélection
    manuelle de descripteurs."""
    return {reference.DESCRIPTOR_ALIASES.get(d.strip().lower(), d.strip().lower())
           for d in descriptors if d.strip()}


# --------------------------------------------------------------------------- #
# Couches de score
# --------------------------------------------------------------------------- #
def molecular_scores(note_profile, comp, use_oav=False, thresholds=None):
    """Similarité moléculaire normalisée-par-composé (TF-IDF). -> {variety: (score, contribs)}.

    `use_oav` : multiplie la contribution d'une molécule par un PRIOR DE PUISSANCE
    (REFERENCE_THRESHOLD_PPB / seuil olfactif) quand son seuil est connu.
    Ce n'est PAS un OAV réel (aucune concentration mesurée) : juste une réponse
    à « molécule X et Y ont la même quantité normalisée, mais X a un seuil
    olfactif 10x plus bas — laquelle pèse le plus dans l'odeur perçue ? ».
    Vérifié sur la base réelle : change le classement complet sur ~18% des notes et
    le houblon #1 sur ~15% (échantillon de 40 notes) — un effet réel, pas un bruit.

    `thresholds` (T75, 2026-08-21 -- remplace l'ancien paramètre `mols` sur
    la table `molecules` seedée une fois pour toutes depuis des seuils
    codés en dur) : {molécule: seuil ppb}, déjà résolu par `oav_thresholds`
    EN DIRECT depuis FlavorDB2 pour les molécules de CETTE note précise --
    voir sa docstring pour le détail complet (root cause de l'ancien
    mécanisme, seuils qui divergeaient silencieusement de FlavorDB2).
    Molécule absente de `thresholds` -> multiplicateur NEUTRE (1.0), jamais
    une exclusion du score : cohérent avec le repli déjà en place pour
    `use_oav=False`."""
    max_amt = {m: max((amount(h, m, comp) for h in comp), default=0.0)
              for m in note_profile}
    # specificity(m, comp) ne dépend PAS du houblon `h` — seulement de la molécule
    # et de `comp` dans son ensemble. Précalculée une fois par molécule ici (même
    # principe que max_amt juste au-dessus) plutôt que recalculée à chaque paire
    # (houblon, molécule) : passait par une boucle interne O(n_houblons) à CHAQUE
    # itération de la boucle externe `for h in comp`, donc O(n_houblons²) au total.
    # Mesuré sur la base réelle (203 houblons) : amplify() ~1s avant, ~30-50ms
    # après, résultat identique (spécificité est une fonction pure de la molécule,
    # pas du houblon scoré).
    spec = {m: specificity(m, comp) for m in note_profile}
    out = {}
    for h in comp:
        contribs = {}
        for m, w in note_profile.items():
            a = amount(h, m, comp)
            if a <= 0 or not max_amt[m]:
                continue
            s = w * (a / max_amt[m]) * spec[m]
            if use_oav and thresholds:
                thr = thresholds.get(m)
                s *= (REFERENCE_THRESHOLD_PPB / thr) if thr else 1.0
            contribs[m] = s
        if contribs:
            out[h] = (sum(contribs.values()), sorted(contribs, key=lambda x: -contribs[x]))
    return out


def descriptor_overlap(note_desc: set[str], hop_desc: set[str]) -> float:
    """Fraction des descripteurs de la note présents dans le houblon (rappel)."""
    return len(note_desc & hop_desc) / len(note_desc) if note_desc else 0.0


# Seuil d'avertissement "couverture moléculaire faible" (CLI/GUI, pas utilisé
# pour le scoring lui-même). Mesuré sur les 506 notes réelles : la couverture
# ne dépasse JAMAIS 12% sur toute la base (médiane 1,3%) — la chimie de
# l'huile de houblon recoupe peu la plupart des arômes alimentaires (voir
# CLAUDE.md, section "But" — même constat qui a mené au retrait de combine()).
# En dessous de ce seuil, le classement moléculaire risque de dégénérer en un
# simple tri par quantité brute d'UNE molécule commune (souvent le géraniol,
# présent dans énormément d'aliments sans rapport) plutôt que de refléter la
# signature propre de la note — vérifié en direct : 163/506 notes n'ont QUE le
# géraniol comme molécule productible, et les 2 houblons les plus riches en
# géraniol de toute la base (Talus®, Ekuanot®) raflent #1 sur 44% des notes
# classées quand aucun descripteur n'est fourni. Un seuil à 20% flagge la quasi-
# totalité du corpus réel — c'est le reflet honnête des données, pas un seuil
# mal choisi (voir la discussion complète dans docs/BACKLOG.md).
LOW_COVERAGE_WARNING_THRESHOLD = 0.20


def coverage(note_profile, comp):
    """Molécules de la note couvrables par ≥1 houblon, et orphelines."""
    producible = {m for m in note_profile
                  if any(comp[h].get(hop_compound(m)) for h in comp)}
    orphan = [m for m in note_profile if m not in producible]
    tot = sum(note_profile.values()) or 1
    cov = sum(w for m, w in note_profile.items() if m in producible) / tot
    return producible, orphan, cov


# Seuil d'avertissement "couverture --oav faible" (T75, 2026-08-21, demande
# utilisateur explicite -- "métrique de couverture OAV... sur le modèle
# exact de LOW_COVERAGE_WARNING_THRESHOLD"). Distinct de LOW_COVERAGE_
# WARNING_THRESHOLD ci-dessus (celui-là = fraction du poids de note
# couverte par au moins UN houblon, peu importe --oav ; celui-ci = parmi les
# molécules PRODUCIBLES seulement, fraction dont le multiplicateur --oav
# vient d'un seuil FlavorDB2 RÉEL plutôt que neutre). Mesuré empiriquement
# sur les 258 notes réelles ayant au moins une molécule productible (même
# méthodologie que le seuil ci-dessus) APRÈS le passage à des seuils résolus
# en direct depuis FlavorDB2 (`oav_thresholds`, plus les anciens seuils
# codés en dur) : médiane 100%, moyenne 91% -- la plupart des notes sont
# largement couvertes (contrairement à LOW_COVERAGE_WARNING_THRESHOLD, où
# la couverture ne dépasse JAMAIS 12%). 80% flagge 50/258 notes réelles
# (19%) -- une minorité significative mais pas la quasi-totalité du corpus
# comme l'autre seuil : reflet honnête d'une réalité différente (certaines
# molécules ont un vrai seuil FlavorDB2, d'autres non), pas un seuil choisi
# au hasard. Exemple réel vérifié : "cottonseed" (18%) -- producible =
# {humulene, farnesene, geraniol, myrcene}, seul geraniol a un seuil réel ;
# humulène/farnésène/myrcène (les 3 plus gros contributeurs de poids)
# tournent à multiplicateur neutre.
OAV_LOW_COVERAGE_WARNING_THRESHOLD = 0.80


def oav_coverage(note_profile: dict[str, float], comp: dict,
                 thresholds: dict[str, float]) -> tuple[float, list[str]]:
    """(fraction du poids de note PRODUCTIBLE couverte par un seuil --oav
    RÉEL, molécules productibles SANS seuil triées par poids de note
    décroissant -- les plus contributrices d'abord, même esprit que les
    molécules orphelines déjà rapportées ailleurs). Restreint aux molécules
    PRODUCTIBLES (pas la note entière comme `coverage()` ci-dessus) : une
    molécule orpheline ne contribue de toute façon à AUCUN score, --oav ou
    pas -- la mélanger ici confondrait deux problèmes distincts (couverture
    moléculaire globale vs couverture --oav des molécules qui comptent déjà
    dans le score). Note sans aucune molécule productible -> (1.0, []) :
    rien à pondérer, pas un faux avertissement."""
    producible, _, _ = coverage(note_profile, comp)
    if not producible:
        return 1.0, []
    with_threshold = [m for m in producible if thresholds.get(m)]
    without_threshold = [m for m in producible if not thresholds.get(m)]
    tot = sum(note_profile[m] for m in producible) or 1
    cov = sum(note_profile[m] for m in with_threshold) / tot
    without_threshold.sort(key=lambda m: -note_profile[m])
    return cov, without_threshold


# --------------------------------------------------------------------------- #
# CAS A — amplify
# --------------------------------------------------------------------------- #
def amplify(con, note: str, w_mol: float = 0.5, w_desc: float = 0.5, use_oav=False, top=8,
           descriptors: list[str] | None = None):
    """
    `descriptors` : sélection manuelle par l'utilisateur des descripteurs de la
    note, sur le vocabulaire réel `hop_descriptors` (comme `contrast`/
    `by_descriptor`) — prioritaire sur `note_descriptors` si fourni. Seul moyen
    d'activer la couche descripteurs pour une note puisque `note_descriptors`
    est vide par défaut pour toutes (pas d'amorce littérature, pas de
    dérivation fiable depuis FooDB — voir reference.py/docs/DATA_SOURCES.md).
    Éphémère : n'écrit rien dans `note_descriptors`, ne vaut que pour cet appel.

    `oav_coverage`/`oav_uncovered` (T75, 2026-08-21, demande utilisateur
    explicite -- métrique de transparence sur --oav, sur le modèle exact de
    `coverage`/`orphan`) : calculés UNIQUEMENT si `use_oav=True` (sinon
    `None`/`[]` -- pas de calcul ni de sens hors --oav). Voir `oav_coverage`
    pour le détail complet."""
    hops, comp, hop_desc, _ = load(con)
    profile = get_note(con, note)
    ndesc = _normalize_descriptors(descriptors) if descriptors else get_note_descriptors(con, note)
    # note_descriptors est vide par défaut pour TOUTE note désormais (pas d'amorce
    # littérature, cf. reference.py) : sans ce garde-fou, la couche descripteurs
    # calcule silencieusement ds=0 pour chaque houblon et le score plafonne à
    # w_mol*100 (50 par défaut) sans que rien ne l'indique — lisible à tort comme
    # "aucun houblon ne partage les descripteurs de la note" plutôt que "cette
    # note n'a aucun descripteur enregistré". Repli honnête : score 100%
    # moléculaire (w_mol=1) quand il n'y a structurellement rien à recouper.
    has_descriptors = bool(ndesc)
    if not has_descriptors:
        w_mol, w_desc = 1.0, 0.0

    # T75 : seuils --oav résolus EN DIRECT depuis FlavorDB2 pour les molécules
    # de CETTE note (jamais les anciens seuils codés en dur) -- calculé
    # seulement si use_oav, une requête de plus par note sinon inutile.
    oav_thr = oav_thresholds(con, list(profile)) if use_oav else {}
    mol = molecular_scores(profile, comp, use_oav=use_oav, thresholds=oav_thr)
    mmax = max((s for s, _ in mol.values()), default=1.0) or 1.0

    ranked = []
    for h in hops:
        ms = (mol.get(h, (0, []))[0] / mmax)
        ds = descriptor_overlap(ndesc, hop_desc.get(h, set()))
        score = w_mol * ms + w_desc * ds
        if score > 0:
            ranked.append({"variety": h, "name": hops[h]["name"], "score": round(100 * score, 1),
                           "mol": round(ms, 2), "desc": round(ds, 2),
                           "why": mol.get(h, (0, []))[1][:4], "sources": hops[h]["sources"],
                           "purpose": hops[h].get("purpose")})
    ranked.sort(key=lambda r: -r["score"])
    _, orphan, cov = coverage(profile, comp)
    oav_cov, oav_uncovered = oav_coverage(profile, comp, oav_thr) if use_oav else (None, [])
    return {"mode": "amplify", "note": note, "coverage": cov, "orphan": orphan,
           "use_oav": use_oav, "has_descriptors": has_descriptors,
           "oav_coverage": oav_cov, "oav_uncovered": oav_uncovered,
           "total_matches": len(ranked), "ranked": ranked[:top]}


# --------------------------------------------------------------------------- #
# CAS A — contrast (piloté par les affinités descripteurs, pas les molécules)
# --------------------------------------------------------------------------- #
# Les 10 catégories "cœur" : le seul jeu de valeurs possibles dans
# CONTRAST_AFFINITY (maillage fermé, voir reference.py) -- calculé une fois
# ici plutôt que de laisser app.py importer `reference` directement (app.py
# n'importe que `matching`/`schema`, jamais les modules de données bruts).
CONTRAST_CORE_CATEGORIES: list[str] = sorted(set().union(*reference.CONTRAST_AFFINITY.values()))

# Définitions des 15 catégories de la roue d'arôme (voir reference.py pour le
# détail/sourçage) -- même raison de ré-export que ci-dessus, app.py n'importe
# jamais `reference` directement.
AROMA_WHEEL_DEFINITIONS: dict[str, str] = reference.AROMA_WHEEL_DEFINITIONS


def contrast_affinity_target(descriptors: list[str]) -> tuple[set[str], list[str]]:
    """Calcule la cible d'affinité PROPOSÉE (`reference.CONTRAST_AFFINITY`)
    pour une sélection de descripteurs de note, sans toucher à la base --
    factorisé hors de `contrast()` (2026-08-19, demande utilisateur : "we
    should orient the complementary aroma by pre-selecting them but let the
    user chose which one he want to keep") pour que la GUI puisse afficher
    cette proposition AVANT de lancer la recherche, comme pré-cochée d'une
    case à cocher modifiable plutôt qu'imposée. Retourne (target, unmapped) --
    `unmapped` : les descripteurs saisis sans aucune entrée dans
    `CONTRAST_AFFINITY` (signalé explicitement, jamais silencieux)."""
    ndesc = _normalize_descriptors(descriptors)
    target: set[str] = set()
    for d in ndesc:
        target.update(reference.CONTRAST_AFFINITY.get(d, []))
    unmapped = sorted(d for d in ndesc if d not in reference.CONTRAST_AFFINITY)
    return target, unmapped


def contrast(con, note: str | None = None, descriptors: list[str] | None = None,
            target_descriptors: list[str] | None = None, purposes: list[str] | None = None, top=8):
    """
    `note` : nécessite que `note_descriptors` contienne déjà des descripteurs
    pour cette note — lève ValueError sinon. Aucune note n'en a par défaut
    (pas d'amorce littérature dans ce projet, cf. reference.py : dériver ça
    depuis FooDB a été tenté et rejeté, données trop génériques, voir
    docs/DATA_SOURCES.md) ; `note_descriptors` reste peuplable manuellement
    (hors de ce module) pour qui veut ce raccourci sur une note précise.

    `descriptors` : sélection manuelle par l'utilisateur (contourne
    note_descriptors entièrement) — le chemin normal de `contrast`, fonctionne
    pour N'IMPORTE QUELLE note tant que l'utilisateur sait décrire son goût
    avec le vocabulaire réel de la roue d'arôme (même vocabulaire que
    `by_descriptor`, grounded sur `hop_descriptors`, pas inventé). Prioritaire
    sur `note` si les deux sont fournis.

    `target_descriptors` (2026-08-19, demande utilisateur explicite --
    "let the user choose which one he wants to keep... rather than imposing
    the mapping") : REMPLACE la cible normalement calculée automatiquement
    depuis `CONTRAST_AFFINITY` par cet ensemble choisi à la main. Cas d'usage
    typique : `tropical` propose ["dank", "resinous", "spicy"], mais
    l'utilisateur ne veut que "spicy" (ex. pour retrouver un houblon noble
    comme Saaz, noyé sous des houblons dank/resinous plus nombreux) -- la
    GUI pré-coche la proposition (`contrast_affinity_target`) dans une case
    à cocher modifiable, PUIS passe la sélection (potentiellement réduite)
    ici. `None` (par défaut) = comportement inchangé, calcul automatique
    complet -- rétrocompatible pour le CLI et tout appel direct de l'API qui
    ne connaît pas ce raffinement.

    Retourne aussi `unmapped` : les descripteurs choisis qui n'ont AUCUNE
    entrée dans `reference.CONTRAST_AFFINITY` (couvre les 38 descripteurs
    réels de la base construite au moment de l'écriture, mais un futur crawl
    peut en révéler un nouveau) — signalés explicitement plutôt que de
    disparaître en silence dans une cible d'affinité vide, pour ne pas laisser
    croire à tort qu'aucun houblon ne contraste avec un descripteur donné.

    **Tri à trois niveaux** (2026-08-19, signalé par l'utilisateur : Saaz
    n'apparaissait pas pour "tropical"/"mango" même en augmentant `top` au
    maximum de la GUI). Root cause vérifiée en direct : Saaz recoupe bien la
    cible (`spicy`, un des 3 descripteurs cœur de "tropical"), mais SEULEMENT
    1/3 -- score 33.3, la même valeur que 83 AUTRES houblons sur une base
    réelle (`target` n'a que 3-4 valeurs de score possibles, `100 * |hit| /
    |target|`, donc des égalités massives sont la norme, pas l'exception).
    Sans second critère, l'ordre à l'intérieur d'une égalité dépendait de
    l'ordre d'itération SQL de `hops` (ni alphabétique, ni pertinent) --
    Saaz tombait à la position ~74 par pur hasard d'ordonnancement, hors de
    portée du plafond GUI (30). Ajout d'un tri secondaire par `total_oil`
    réconcilié desc (même proxy d'intensité aromatique qu'`by_descriptor`),
    puis `variety` asc en dernier recours (déterminisme total) -- rend le
    classement REPRODUCTIBLE et explicable au lieu d'arbitraire, mais NE
    garantit pas qu'un houblon donné dans une égalité massive apparaisse
    dans les `top` premiers : c'est `total_matches` (ci-dessous) qui rend
    cette limite visible plutôt que silencieuse.

    `total_matches` (nouveau) : nombre TOTAL de houblons recoupant la cible
    AVANT troncature à `top` -- la GUI l'utilise pour signaler explicitement
    une troncature (« showing 8 of 91 matches ») plutôt que de laisser
    croire que `top` couvre tout.

    `purposes` (2026-08-19, T61, demande utilisateur explicite -- "we should
    add another menu for purpose, it would be pre-selecting both bittering
    and aromatic but we should let user add a filter on this purpose") :
    filtre les résultats sur le purpose EFFECTIF (`resolve_purpose` -- réel
    BeerMaverick, ou inféré depuis l'acide alpha en son absence, EXACTEMENT
    la même résolution que ce que la GUI affiche déjà par ligne, jamais un
    filtre sur une valeur différente de ce qui est montré). `None` (par
    défaut) = aucun filtre, comportement inchangé, rétrocompatible CLI. Un
    houblon "both" satisfait le filtre dès qu'AU MOINS un des deux rôles
    demandés lui correspond (voir `_purpose_matches_filter`) ; un purpose
    totalement inconnu (ni réel ni inférable) est exclu dès qu'un filtre est
    actif. Appliqué ICI (dans `matching.contrast`, pas après coup côté GUI)
    pour que `total_matches`/le tri/la troncature à `top` restent cohérents
    avec ce que l'utilisateur voit réellement -- un filtrage GUI a posteriori
    aurait faussé le message de troncature (T56) et pu cacher des résultats
    qui auraient dû compter dans `total_matches`.
    """
    hops, comp, hop_desc, _ = load(con)
    purposes_set = set(purposes) if purposes is not None else None
    if descriptors:
        ndesc = _normalize_descriptors(descriptors)
        label = ", ".join(sorted(ndesc)) if ndesc else "(vide)"
    elif note:
        ndesc = get_note_descriptors(con, note)
        if not ndesc:
            raise ValueError(
                f"contrast indisponible pour {note!r} : pas de descripteurs dans "
                f"note_descriptors pour cette note (table vide par défaut, aucune "
                f"amorce littérature dans ce projet). Passer `descriptors=` pour "
                f"décrire la note à la main (voir `hopmatch descriptors`), ou "
                f"essayer amplify.")
        label = note
    else:
        raise ValueError("contrast nécessite soit `note` (avec note_descriptors "
                         "peuplé), soit `descriptors` (sélection manuelle).")
    # descripteurs qui contrastent bien avec ceux de la note -- `target_descriptors`
    # (choisi à la main par l'utilisateur en GUI, voir docstring) REMPLACE le
    # calcul automatique s'il est fourni ; `unmapped` reste calculé sur `ndesc`
    # (les descripteurs de LA NOTE, pas la cible) dans les deux cas, c'est une
    # info sur la note saisie, indépendante de la façon dont la cible a été
    # obtenue ensuite.
    unmapped = sorted(d for d in ndesc if d not in reference.CONTRAST_AFFINITY)
    if target_descriptors is not None:
        target = _normalize_descriptors(target_descriptors)
    else:
        target = set()
        for d in ndesc:
            target.update(reference.CONTRAST_AFFINITY.get(d, []))
    ranked = []
    for h in hops:
        hd = hop_desc.get(h, set())
        hit = hd & target
        if not hit:
            continue
        hcomp = comp.get(h, {})
        if purposes_set is not None:
            resolved_purpose, _ = resolve_purpose(hops[h].get("purpose"), hcomp)
            if not _purpose_matches_filter(resolved_purpose, purposes_set):
                continue
        total_oil = (hcomp.get("total_oil") or {}).get("mid") or 0.0
        ranked.append({"variety": h, "name": hops[h]["name"],
                       "score": round(100 * len(hit) / max(len(target), 1), 1),
                       "contrast_via": sorted(hit), "sources": hops[h]["sources"],
                       "purpose": hops[h].get("purpose"),
                       "_rank": (-len(hit), -total_oil, h)})
    ranked.sort(key=lambda r: r["_rank"])
    for r in ranked:
        del r["_rank"]
    return {"mode": "contrast", "note": label, "affinity_target": sorted(target),
           "unmapped": unmapped, "total_matches": len(ranked), "ranked": ranked[:top]}


def _hop_pairing_frequencies(con) -> dict[tuple[str, str], float]:
    """{(variety_a, variety_b): fréquence} symétrique — BeerMaverick
    (`hop_pairings`, T25/T33 backlog). Mesuré : 36/203 houblons seulement ont
    une entrée (`paired_variety` réconcilié), la plupart des paires n'auront
    donc AUCUNE fréquence ici — `_pairing_grown_blends` doit s'en accommoder
    par repli, jamais par échec. Meilleure valeur connue si les deux sens
    existent (le graphique BeerMaverick d'un houblon n'est pas nécessairement
    symétrique avec celui de son partenaire)."""
    freq: dict[tuple[str, str], float] = {}
    rows = con.execute(
        "SELECT variety, paired_variety, frequency FROM hop_pairings "
        "WHERE paired_variety IS NOT NULL")
    for v, pv, f in rows:
        for a, b in ((v, pv), (pv, v)):
            if f > freq.get((a, b), -1):
                freq[(a, b)] = f
    return freq


_PAIRING_TOP_N = 10  # cf. `_pairing_grown_blends` — "top N" du pairing BeerMaverick


def _top_pairing_partners(freq: dict[tuple[str, str], float], variety: str, n: int) -> set[str]:
    """Les `n` partenaires BeerMaverick les plus fréquents de `variety` (pas
    n'importe quel partenaire ayant une fréquence > 0 — un vrai "top N"), cf.
    `_pairing_grown_blends`."""
    partners = sorted(
        ((b, f) for (a, b), f in freq.items() if a == variety), key=lambda x: -x[1])
    return {b for b, _ in partners[:n]}


_AROMATIC_ROLE = {"aromatic", "both"}
_BITTERING_ROLE = {"bittering", "both"}


def _grow_pick(pool: list[dict], partner_source: list[str], blend_varieties: list[str],
              target: set[str], by_variety: dict, freq: dict[tuple[str, str], float],
              pairing_top_n: int) -> tuple[dict, str]:
    """Choisit le prochain houblon à ajouter, en mélangeant pertinence ET
    pairing (jamais l'un puis l'autre en cascade, cf. `_pairing_grown_blends`) :
    parmi `pool` (déjà trié par pertinence), ne garde que les candidats
    figurant dans le top `pairing_top_n` des partenaires BeerMaverick d'AU
    MOINS UN houblon de `partner_source`, puis prend le plus pertinent de ce
    sous-ensemble (`via="pairing"`). `partner_source` peut être un
    sous-ensemble du blend complet (houblons aromatiques uniquement une fois
    la structure aromatique/amérisante établie — voir T-purpose) ; `covers`/
    `remaining_target` restent calculés sur `blend_varieties`, le blend
    complet, quel que soit `partner_source` : le taux de couverture ne doit
    jamais ignorer un houblon déjà choisi sous prétexte qu'il ne sert pas de
    source de pairing pour CETTE étape. Repli couverture gloutonne puis
    pertinence pure si aucun candidat du pool n'est dans ce top-N pairing."""
    partner_set: set[str] = set()
    for v in partner_source:
        partner_set |= _top_pairing_partners(freq, v, pairing_top_n)
    paired_candidates = [c for c in pool if c["variety"] in partner_set]
    if paired_candidates:
        return paired_candidates[0], "pairing"
    covered_so_far = (set().union(*(by_variety[v]["covers"] for v in blend_varieties))
                      if blend_varieties else set())
    remaining_target = target - covered_so_far
    gain_candidates = [c for c in pool if c["covers"] & remaining_target]
    if gain_candidates:
        return max(gain_candidates, key=lambda c: len(c["covers"] & remaining_target)), "coverage"
    return pool[0], "relevance"


def _pairing_grown_blends(con, candidates: list[dict], target: set[str], max_hops: int = 5,
                          base_variety: str | None = None, pairing_top_n: int = _PAIRING_TOP_N,
                          purpose_by_variety: dict[str, str | None] | None = None
                          ) -> list[dict]:
    """
    T33 backlog (décision utilisateur) : propose des blends de TAILLE
    CROISSANTE (1..max_hops), pas un seul blend "optimal" — pour laisser le
    brasseur choisir son compromis taille/couverture/authenticité plutôt que
    de lui imposer un seul résultat.

    `candidates` : liste déjà triée par pertinence décroissante, chaque entrée
    a au moins une clé "covers" (set[str], sous-ensemble de `target` que ce
    houblon couvre — le filtre de pertinence, càd ne garder que les houblons
    avec `covers` non vide, est déjà appliqué en amont par l'appelant).

    Taille 1 : `base_variety` si fourni (`via="chosen"`) — décision utilisateur
    (2026-08-19) : le score de `contrast`/`amplify` est souvent homogène (peu
    de descripteurs cibles -> plusieurs houblons à égalité de "meilleur
    candidat"), donc le classement seul ne désigne pas un choix évident ;
    l'utilisateur choisit lui-même le houblon de base en GUI/CLI plutôt que de
    se voir imposer `candidates[0]` arbitrairement parmi des ex-aequo. Repli
    sur `candidates[0]` (`via="top"`) si `base_variety` est omis ou absent des
    candidats (usage programmatique/CLI sans sélection).

    Sélection à chaque taille (hors structuration purpose ci-dessous) : voir
    `_grow_pick` (mélange pertinence+pairing, repli couverture puis
    pertinence pure).

    `purpose_by_variety` (T-purpose backlog, décision utilisateur 2026-08-19,
    "aromatic vs bittering hops") : {variety: "aromatic"|"bittering"|"both"|
    None}, depuis `hops.purpose` (voir CLAUDE.md, section BeerMaverick — SEULE
    source qui classe un houblon par usage). Quand fourni ET que le houblon de
    taille 1 a un rôle connu, la croissance devient STRUCTURÉE : taille 2
    cherche explicitement un houblon du rôle OPPOSÉ (via="complement") pour
    garantir au moins 1 aromatique + 1 amérisant dès la taille 2 (un houblon
    "both" à la taille 1 satisfait déjà les deux rôles, pas de complément
    forcé) ; à partir de là, la croissance se restreint aux houblons
    AROMATIQUES uniquement (purpose in {"aromatic","both"}), et le pairing
    BeerMaverick ne regarde que les partenaires des houblons AROMATIQUES déjà
    dans le blend — jamais de l'amérisant (demande explicite : "picking only
    aromatic hops that pairs well with the other aromatic hop, not the
    bittering"). S'arrête si plus aucun candidat aromatique n'est disponible,
    même avant `max_hops`. Repli SILENCIEUX sur la croissance générique
    (comportement T33/T42/T44, inchangé) dès que le rôle du houblon de base
    est inconnu (`purpose_by_variety` absent/vide, ou variété non couverte
    par BeerMaverick) OU qu'aucun candidat du rôle complémentaire n'existe —
    jamais d'erreur, jamais un blend plus petit que possible par manque de
    donnée `purpose`.

    Va TOUJOURS jusqu'à `max_hops` (ou épuisement des candidats) — ne s'arrête
    PAS dès couverture complète (décision utilisateur, 2026-08 : voir un blend
    à 5 même quand 1 seul houblon couvre déjà toute la cible reste une info
    utile — l'utilisateur compare lui-même la taille/couverture/authenticité,
    l'outil ne décide pas à sa place)."""
    if not candidates or not target:
        return []
    freq = _hop_pairing_frequencies(con)
    by_variety = {c["variety"]: c for c in candidates}
    pool = list(candidates)
    blend: list[tuple[str, str]] = []  # [(variety, via), ...]
    blends = []
    purpose_by_variety = purpose_by_variety or {}
    aromatic_members: set[str] = set()
    bittering_members: set[str] = set()

    def _assign_role(variety: str) -> None:
        p = purpose_by_variety.get(variety)
        if p in _AROMATIC_ROLE:
            aromatic_members.add(variety)
        if p in _BITTERING_ROLE:
            bittering_members.add(variety)

    for size in range(1, max_hops + 1):
        if not pool:
            break
        blend_varieties = [v for v, _ in blend]
        if size == 1:
            if base_variety is not None and base_variety in by_variety:
                chosen, via = by_variety[base_variety], "chosen"
            else:
                chosen, via = pool[0], "top"
            _assign_role(chosen["variety"])
        elif (aromatic_members or bittering_members) and not (aromatic_members and bittering_members):
            # rôle établi d'un seul côté (taille 1 aromatique OU amérisant,
            # jamais "both") -> chercher explicitement le rôle opposé.
            need_role = _BITTERING_ROLE if not bittering_members else _AROMATIC_ROLE
            complement_pool = [c for c in pool
                               if purpose_by_variety.get(c["variety"]) in need_role]
            if complement_pool:
                chosen, _ = _grow_pick(complement_pool, blend_varieties, blend_varieties,
                                       target, by_variety, freq, pairing_top_n)
                via = "complement"
                _assign_role(chosen["variety"])
            else:
                # aucun houblon du rôle complémentaire parmi les candidats :
                # repli honnête sur la croissance générique (pas de blend
                # plus petit que possible par manque de donnée purpose).
                chosen, via = _grow_pick(pool, blend_varieties, blend_varieties, target,
                                         by_variety, freq, pairing_top_n)
        elif aromatic_members and bittering_members:
            # structure établie des deux côtés -> ne recruter QUE des
            # houblons aromatiques, pairing scope = houblons AROMATIQUES du
            # blend uniquement (jamais l'amérisant, demande explicite).
            restricted_pool = [c for c in pool
                               if purpose_by_variety.get(c["variety"]) in _AROMATIC_ROLE]
            if not restricted_pool:
                break  # plus de houblon aromatique disponible -> on s'arrête ici
            chosen, via = _grow_pick(restricted_pool, sorted(aromatic_members),
                                     blend_varieties, target, by_variety, freq, pairing_top_n)
            _assign_role(chosen["variety"])
        else:
            # aucune donnée purpose exploitable (rôle de base inconnu) ->
            # comportement générique inchangé (T33/T42/T44).
            chosen, via = _grow_pick(pool, blend_varieties, blend_varieties, target,
                                     by_variety, freq, pairing_top_n)
        blend.append((chosen["variety"], via))
        pool = [c for c in pool if c["variety"] != chosen["variety"]]
        covered = set().union(*(by_variety[v]["covers"] for v, _ in blend))
        blends.append({
            "size": size,
            "hops": [{"variety": v, "name": by_variety[v]["name"], "via": via_,
                      "sources": by_variety[v]["sources"],
                      "purpose": purpose_by_variety.get(v),
                      "covers": sorted(by_variety[v]["covers"])}
                     for v, via_ in blend],
            "covered": sorted(target & covered),
            "residual": sorted(target - covered),
        })
    return blends


def contrast_blend(con, note: str | None = None, descriptors: list[str] | None = None,
                   target_descriptors: list[str] | None = None, purposes: list[str] | None = None,
                   max_hops: int = 5, top_candidates: int = 30, base_variety: str | None = None):
    """
    Propose des blends de taille croissante (1..max_hops) plutôt qu'un seul
    blend "optimal" — voir `_pairing_grown_blends` pour le mécanisme complet
    (houblon de base choisi par l'utilisateur via `base_variety`, additions
    suivantes mélangeant pertinence ET top-N pairing BeerMaverick, repli
    couverture explicite). `contrast` reste non-moléculaire par design (cf.
    ARCHITECTURE.md) : la cible et la pertinence des candidats viennent
    toujours de `CONTRAST_AFFINITY`/`hop_descriptors`, jamais des molécules.

    `target_descriptors` (2026-08-19, voir `contrast`) : propagé tel quel --
    le blend proposé doit viser la MÊME cible (potentiellement réduite à la
    main par l'utilisateur) que le tableau de résultats, jamais une cible
    différente calculée séparément.

    `purposes` (2026-08-19, T61, voir `contrast`) : propagé au POOL de
    candidats (filtré avant `_pairing_grown_blends`), pour que le blend soit
    composé des mêmes houblons que ceux affichés dans le tableau de
    résultats. N'affecte PAS la garantie structurelle aromatic+bittering à
    la taille 2 (`_pairing_grown_blends`, qui continue d'utiliser
    exclusivement le purpose RÉEL BeerMaverick, jamais ce filtre ni
    l'inférence) -- si le filtre exclut un rôle entier (ex. "aromatic"
    seul), le pool n'a simplement plus de candidat du rôle complémentaire,
    et le mécanisme retombe sur son repli générique déjà existant (documenté
    dans `_pairing_grown_blends`), pas une erreur.
    """
    r = contrast(con, note=note, descriptors=descriptors,
                target_descriptors=target_descriptors, purposes=purposes, top=top_candidates)
    target = set(r["affinity_target"])
    candidates = [dict(h, covers=set(h["contrast_via"])) for h in r["ranked"]]
    hops, _, _, _ = load(con)
    purpose_by_variety = {v: h.get("purpose") for v, h in hops.items()}
    blends = _pairing_grown_blends(con, candidates, target, max_hops=max_hops,
                                   base_variety=base_variety,
                                   purpose_by_variety=purpose_by_variety)
    return {"mode": "contrast_blend", "note": r["note"], "affinity_target": r["affinity_target"],
           "unmapped": r["unmapped"], "blends": blends}


def amplify_blend(con, note: str, w_mol: float = 0.5, w_desc: float = 0.5, use_oav=False,
                  max_hops: int = 5, top_candidates: int = 30, descriptors: list[str] | None = None,
                  base_variety: str | None = None):
    """
    Équivalent de `contrast_blend` pour `amplify` (T31/T32 backlog, décision
    utilisateur explicite) : propose des blends de taille croissante (1..max_hops),
    houblons choisis par fréquence RÉELLE de pairing BeerMaverick en priorité
    (voir `_pairing_grown_blends`).

    **PAS de reconstruction moléculaire (pas de NNLS)** — c'était `combine()`,
    retiré le 2026-08-12 pour une dégénérescence documentée en détail (voir
    CLAUDE.md, section « But ») : sur les notes à un seul composé « producible »
    (la majorité), n'importe quel houblon porteur atteignait un résidu
    artificiel de 0, une fausse confiance sans rapport avec la couverture
    réelle. La cible de couverture ici est le DESCRIPTEUR (comme
    `contrast_blend`), jamais la molécule : `covers` par houblon =
    `ndesc ∩ hop_descriptors[houblon]`. Le score moléculaire/descripteur
    d'`amplify` sert seulement à ORDONNER les candidats (pertinence), jamais à
    piloter la composition du blend.

    Nécessite des descripteurs pour la note (`descriptors=` ou
    `note_descriptors` peuplé, comme `amplify`) : sans descripteurs, il n'y a
    rien à couvrir par un blend — renvoie `blends: []` avec `has_descriptors:
    False` plutôt qu'une erreur, cohérent avec le repli honnête d'`amplify`.
    """
    r = amplify(con, note, w_mol=w_mol, w_desc=w_desc, use_oav=use_oav,
               top=top_candidates, descriptors=descriptors)
    if not r["has_descriptors"]:
        return {"mode": "amplify_blend", "note": note, "target_descriptors": [],
               "has_descriptors": False, "blends": []}
    hops, _, hop_desc, _ = load(con)
    ndesc = _normalize_descriptors(descriptors) if descriptors else get_note_descriptors(con, note)
    target = set(ndesc)
    candidates = []
    for h in r["ranked"]:
        covers = target & hop_desc.get(h["variety"], set())
        if covers:
            candidates.append(dict(h, covers=covers))
    purpose_by_variety = {v: h.get("purpose") for v, h in hops.items()}
    blends = _pairing_grown_blends(con, candidates, target, max_hops=max_hops,
                                   base_variety=base_variety,
                                   purpose_by_variety=purpose_by_variety)
    return {"mode": "amplify_blend", "note": note, "target_descriptors": sorted(target),
           "has_descriptors": True, "blends": blends}


# --------------------------------------------------------------------------- #
# DÉCOUVERTE — by_descriptor (pas un cas A/B : pas de note requise)
# --------------------------------------------------------------------------- #
# Public (pas de underscore) : réutilisé tel quel par `app.py` (tableaux de
# composition détaillée en Browse/`_hop_detail_expanders`) -- était dupliqué
# à l'identique dans les deux modules (trouvé en revue de code, 2026-08-20),
# à l'encontre du principe déjà suivi pour `CONTRAST_CORE_CATEGORIES`/
# `AROMA_WHEEL_DEFINITIONS` : une seule définition ici, jamais recopiée.
NON_AROMA_DISPLAY = {"total_oil", "alpha_acid", "beta_acid", "co_humulone"}


def by_descriptor(con, selected: list[str], wheel_descriptors: list[str] | None = None,
                  top: int = 10):
    """
    Houblons dont la roue d'arôme (`hop_descriptors`, BarthHaas/Yakima réelles)
    recoupe une sélection de descripteurs. Grounded sur les données houblon
    directement — ne dépend ni de CONTRAST_AFFINITY (prior curé) ni de FooDB.

    Tri à DEUX RÔLES SÉPARÉS (2026-08-19, revirement de méthodologie --
    décision utilisateur après un premier passage T33/T54 jugé imprécis en
    testant en direct "papaya" + roue [tropical, citrus, floral] : un
    houblon qui recoupait les 3 termes de la roue mais PAS "papaya" (le
    signal le plus précis demandé) ressortait quand même mélangé dans les
    résultats, avant les houblons "papaya" réels -- signalé explicitement
    comme moins précis que voulu, "the qualitative textual descriptor is
    not a priority over the wheel aroma descriptor selected"). `selected`
    (texte, vocabulaire complet à 104 termes -- ex. "papaya", plus précis
    que les 15 catégories de la roue) est désormais le SEUL filtre
    catégorique : un houblon DOIT recouper au moins un descripteur texte
    pour apparaître. `wheel_descriptors` (roue quantitative, ex. les pills
    GUI) ne sert plus qu'à NOTER (jamais filtrer) les houblons déjà
    retenus, par intensité moyenne mesurée -- jamais un critère de
    présence/absence.
    1. **Catégorique** (`selected`, PRIORITAIRE, inchangé dans son
       mécanisme) : nb de descripteurs TEXTE recoupés desc -- reste le
       filtre ET le tri principal.
    2. **Quantitatif** (`wheel_descriptors`, départage SEULEMENT à
       l'intérieur d'un même palier catégorique, ne filtre JAMAIS) :
       intensité moyenne (`hop_aroma_intensity`, T26 backlog, Yakima
       uniquement, 0-100 réel) sur l'intersection entre `wheel_descriptors`
       et ce que CE houblon a réellement en données quantitatives --
       jamais une moyenne comptant un descripteur manquant comme 0 (ce
       serait fabriquer une donnée). Houblons sans intensité exploitable
       classés après ceux qui en ont une, dans le MÊME palier catégorique
       -- honnêteté d'abord, même principe que les molécules orphelines.
    3. `total_oil` réconcilié desc (repli) puis `variety` asc
       (déterminisme total).

    **Repli** : si `selected` est VIDE (rien tapé dans le multiselect texte,
    seulement des pills roue cochées), `wheel_descriptors` sert AUSSI de
    filtre catégorique -- sinon rien ne filtrerait du tout. Dès que
    `selected` est non-vide, `wheel_descriptors` redevient purement une
    note, jamais un filtre, quel que soit son contenu.

    `intensity`/`quant_score`/`quant_descriptors` exposés dans chaque entrée
    retournée pour que la GUI affiche explicitement CE QUI a été utilisé
    (transparence -- jamais un réordonnancement silencieux).

    Retourne `{"ranked": [...], "total_matches": N}` (2026-08-20, revue de
    code -- avant ça, une liste nue tronquée à `top` sans aucun moyen de
    savoir combien de houblons recoupaient RÉELLEMENT la sélection avant
    troncature). Même besoin, même solution que `total_matches` sur
    `contrast` (T56 : Saaz invisible au plafond sans ce compteur) --
    `by_descriptor` départage déjà ses égalités de façon déterministe
    (`_rank`), donc ce n'est pas un bug de classement comme pour `contrast`,
    mais la GUI n'avait toujours aucun moyen d'afficher « showing N of M »
    plutôt que de tronquer en silence."""
    hops, comp, hop_desc, _ = load(con)
    selected = {reference.DESCRIPTOR_ALIASES.get(d, d) for d in selected}
    wheel = {reference.DESCRIPTOR_ALIASES.get(d, d) for d in (wheel_descriptors or [])}
    categorical = selected or wheel
    # T79 : passe par `resolve_aroma_intensity` (une seule source par
    # houblon, jamais un mélange Yakima/BarthHaas -- voir son commentaire)
    # -- l'ancienne requête brute ne filtrait pas par source, un houblon à
    # double source pouvait moyenner des intensités d'échelles incompatibles.
    intensity_by_variety = {v: resolve_aroma_intensity(by_source)
                            for v, by_source in load_aroma_intensity(con).items()}
    ranked = []
    for h in hops:
        hd = hop_desc.get(h, set())
        matched = categorical & hd
        if not matched:
            continue
        hcomp = comp.get(h, {})
        total_oil = (hcomp.get("total_oil") or {}).get("mid") or 0.0
        compounds = sorted(
            ({"compound": c, "mid": v["mid"], "unit": v["unit"], "sources": v["sources"]}
             for c, v in hcomp.items() if c not in NON_AROMA_DISPLAY and v["mid"] is not None),
            key=lambda r: -r["mid"])
        intensity, intensity_source = intensity_by_variety.get(h, ({}, None))
        quant_descriptors = sorted(d for d in wheel if d in intensity)
        quant_score = (sum(intensity[d] for d in quant_descriptors) / len(quant_descriptors)
                      if quant_descriptors else None)
        ranked.append({"variety": h, "name": hops[h]["name"],
                       "matched_descriptors": sorted(matched), "all_descriptors": sorted(hd),
                       "compounds": compounds, "sources": hops[h]["sources"],
                       "purpose": hops[h].get("purpose"), "intensity": intensity,
                       "intensity_source": intensity_source,
                       "quant_score": quant_score, "quant_descriptors": quant_descriptors,
                       "_rank": (-len(matched), 0 if quant_score is not None else 1,
                                -(quant_score or 0.0), -total_oil, h)})
    ranked.sort(key=lambda r: r["_rank"])
    for r in ranked:
        del r["_rank"]
    return {"ranked": ranked[:top], "total_matches": len(ranked)}


# --------------------------------------------------------------------------- #
# DÉCOUVERTE — similarité houblon<->houblon, calculée (Browse, T67/T68 backlog)
# --------------------------------------------------------------------------- #
def _coverage_penalized_cosine(raw_by_variety: dict[str, dict[str, float]],
                               variety: str) -> dict[str, dict]:
    """Cœur partagé de `similar_hops_by_composition`/`similar_hops_by_aroma_wheel`
    (T68, 2026-08-21, demande utilisateur : "we also could use the quantitative
    aroma wheel scores... implement this other layer") -- factorisé pour ne
    pas dupliquer deux fois la même méthode (cosinus normalisé-par-axe/pondéré-
    spécificité + pénalité de couverture, voir docstring de
    `similar_hops_by_composition` pour le détail complet de pourquoi la
    pénalité de couverture existe -- même raisonnement, quel que soit l'axe
    (composé chimique ou catégorie de roue d'arôme) : un houblon moins mesuré
    ne doit jamais dépasser un houblon à couverture complète juste parce que
    le cosinus pur ignore les dimensions manquantes.

    `raw_by_variety` : {variety: {axe: valeur brute}}, déjà filtré aux axes
    pertinents par l'appelant (composés aromatiques pour la composition,
    catégories de la roue d'arôme pour l'intensité) -- cette fonction ne sait
    rien du domaine, purement générique sur la structure {variety: {axe: v}}.

    Retourne {variety_candidate: {"similarity": 0..1, "coverage": 0..1,
    "shared": set[axe]}}, NON tronqué à `top` et NON multiplié par 100
    (fait par l'appelant, chacun avec son propre vocabulaire de sortie --
    `shared_compounds` vs `shared_descriptors`) -- `variety` lui-même exclu,
    candidats à similarité nulle/sans axe partagé exclus (honnêteté d'abord,
    pas de faux zéro)."""
    if variety not in raw_by_variety or not raw_by_variety[variety]:
        return {}
    axes = sorted({a for v in raw_by_variety.values() for a in v})
    max_val = {a: max((raw_by_variety[h].get(a, 0.0) for h in raw_by_variety), default=0.0)
              for a in axes}
    n = len(raw_by_variety)
    spec = {}
    for a in axes:
        n_with = sum(1 for h in raw_by_variety if raw_by_variety[h].get(a, 0.0) > 0)
        spec[a] = math.log(n / (1 + n_with)) + 1.0

    def vector(h: str) -> dict[str, float]:
        vec = {}
        for a in axes:
            v = raw_by_variety[h].get(a, 0.0)
            if v > 0 and max_val[a]:
                vec[a] = (v / max_val[a]) * spec[a]
        return vec

    target_vec = vector(variety)
    target_norm = math.sqrt(sum(v * v for v in target_vec.values()))
    if not target_vec or not target_norm:
        return {}

    out = {}
    for h in raw_by_variety:
        if h == variety:
            continue
        vec = vector(h)
        shared = target_vec.keys() & vec.keys()
        if not shared:
            continue
        dot = sum(target_vec[c] * vec[c] for c in shared)
        norm = math.sqrt(sum(v * v for v in vec.values()))
        cosine = dot / (target_norm * norm) if norm else 0.0
        coverage = len(shared) / len(target_vec)
        sim = cosine * coverage
        if sim <= 0:
            continue
        out[h] = {"similarity": sim, "coverage": coverage,
                 "shared": sorted(shared, key=lambda c: -(target_vec[c] * vec[c]))}
    return out


def similar_hops_by_composition(con, variety: str, top: int = 10) -> list[dict]:
    """Houblons les plus proches de `variety` par COMPOSITION MOLÉCULAIRE
    (`hop_composition`, déjà en base — aucune nouvelle source), demande
    utilisateur explicite (2026-08-21) pour une section "Similar hops" en bas
    de Browse. Volontairement PAS `hop_similar`/`hop_pairings`/`hop_substitutions`
    (T25, déjà affichées par `_hop_associations`) : ces trois-là sont
    éditoriales/recette (Yakima/BeerMaverick), celle-ci est calculée
    directement depuis la chimie mesurée — une relation distincte, jamais
    fusionnée avec les trois autres (voir `similar_hops` pour la combinaison
    de CETTE couche avec la couche roue d'arôme, T68).

    Réutilise la même méthode que la couche moléculaire d'`amplify`
    (`molecular_scores`) plutôt que d'en inventer une nouvelle : cosinus sur
    des vecteurs normalisés-par-composé (`amount / max sur tous les houblons`)
    puis pondérés par `specificity` (IDF-like — un composé quasi-ubiquitaire
    comme le myrcène pèse peu, un composé rare/signature pèse beaucoup), même
    principe que documenté en tête de ce module ("similarité normalisée-par-
    composé (TF-IDF), pas en cosinus pseudo-OAV"). Exclut
    `NON_AROMA_DISPLAY` (total_oil/alpha_acid/beta_acid/co_humulone) du
    vecteur : ce ne sont pas des molécules d'arôme.

    **Pénalité de couverture (corrige un vrai défaut, signalé en direct par
    l'utilisateur le jour même du premier passage T67 : Callista ressortait
    #1 pour Citra devant Mosaic, alors que Callista a des descripteurs
    berry/stone fruit très différents de Citra citrus/tropical, et que le
    comparatif visuel Compare Hops ne montrait rien de tel).** Root cause
    vérifiée sur données réelles : le cosinus pur est invariant d'échelle --
    Callista (BarthHaas seul, 8/10 composés de Citra, aucune donnée
    beta-pinène/géraniol) a des valeurs uniformément DILUÉES (~20-50% de
    celles de Citra sur les composés partagés, cohérent avec son alpha/huile
    totale plus faibles) mais PROPORTIONNELLEMENT alignées -> cosinus élevé
    (89.1%) simplement parce que la direction du vecteur, tronqué à ses 8
    dimensions, reste proche de celle de Citra. Mosaic, qui a pourtant la
    MÊME couverture complète que Citra (10/10 composés, aucune donnée
    manquante), scorait plus bas (88.2%) à cause d'un seul composé
    (`ketones`, poids de spécificité élevé car rare dans la base) où sa
    valeur diverge fortement -- un vrai désaccord directionnel sur UN axe
    pèse plus, dans un cosinus pur, qu'une incomplétude systématique sur
    DEUX axes entiers. C'est l'inverse de ce que la confiance dans la
    donnée devrait donner. Corrigé par `_coverage_penalized_cosine` (pénalité
    de rappel côté `variety`, voir sa docstring) : Mosaic (couverture 100%)
    repasse devant Callista (couverture 80%, pénalisé à 71.3%), vérifié en
    direct sur données réelles."""
    hops, comp, _, _ = load(con)
    raw = {v: {c: amount(v, c, comp) for c in cmap if c not in NON_AROMA_DISPLAY}
          for v, cmap in comp.items()}
    sims = _coverage_penalized_cosine(raw, variety)
    ranked = [{"variety": h, "name": hops[h]["name"], "similarity": round(100 * r["similarity"], 1),
              "coverage": round(100 * r["coverage"], 1), "shared_compounds": r["shared"][:5],
              "sources": hops[h]["sources"], "purpose": hops[h].get("purpose")}
             for h, r in sims.items()]
    ranked.sort(key=lambda r: (-r["similarity"], r["variety"]))
    return ranked[:top]


def similar_hops_by_aroma_wheel(con, variety: str, top: int = 10) -> list[dict]:
    """Houblons les plus proches de `variety` par ROUE D'ARÔME QUANTITATIVE
    (`hop_aroma_intensity`, T26 -- intensité RÉELLE 0-100 par catégorie,
    Yakima uniquement, voir `hop_aroma_intensity()`), T68 (2026-08-21, demande
    utilisateur explicite : "we also could use the quantitative aroma wheel
    scores right?"). Même méthode que `similar_hops_by_composition`
    (`_coverage_penalized_cosine`, cosinus normalisé-par-axe/pondéré-
    spécificité + pénalité de couverture) appliquée aux 15 catégories de la
    roue au lieu des composés de `hop_composition` -- deux couches
    INDÉPENDANTES sur des données différentes (chimie mesurée vs perception
    sensorielle Yakima), jamais fusionnées ici (voir `similar_hops` pour leur
    combinaison optionnelle, contrôlée par l'utilisateur).

    Couverture Yakima uniquement (94/151 variétés Yakima, T26) : un houblon
    BarthHaas seul, ou une variété Yakima non couverte, n'a AUCUNE entrée
    `hop_aroma_intensity` -> absent de `raw`, donc soit `variety` elle-même
    (liste vide, rien à comparer), soit simplement absent des candidats
    (jamais un score inventé)."""
    hops, _, _, _ = load(con)
    # T79 : voir le commentaire équivalent dans `by_descriptor` -- une seule
    # source par houblon, jamais un mélange.
    raw = {v: resolve_aroma_intensity(by_source)[0] for v, by_source in load_aroma_intensity(con).items()}
    sims = _coverage_penalized_cosine(raw, variety)
    ranked = [{"variety": h, "name": hops[h]["name"], "similarity": round(100 * r["similarity"], 1),
              "coverage": round(100 * r["coverage"], 1), "shared_descriptors": r["shared"][:5],
              "sources": hops[h]["sources"], "purpose": hops[h].get("purpose")}
             for h, r in sims.items() if h in hops]
    ranked.sort(key=lambda r: (-r["similarity"], r["variety"]))
    return ranked[:top]


_SIMILARITY_LAYERS = ("molecular", "aroma_wheel")


def similar_hops(con, variety: str, use_molecular: bool = True, use_aroma_wheel: bool = True,
                 top: int = 10) -> list[dict]:
    """Combine `similar_hops_by_composition`/`similar_hops_by_aroma_wheel`,
    chacune activable/désactivable indépendamment (T68, 2026-08-21, demande
    utilisateur explicite : "allow the user to toggle molecular and/or
    aroma_wheel layers... by default both layers would be included"). Point
    d'entrée utilisé par la GUI (`app._similar_hops_section`).

    Combinaison = MOYENNE des couches actives qui ont RÉELLEMENT une donnée
    pour ce candidat (pas une moyenne qui compte silencieusement une couche
    manquante comme 0 -- honnêteté d'abord, même principe que `quant_score`
    dans `by_descriptor`) : un houblon BarthHaas seul (aucune donnée
    `hop_aroma_intensity`) reste comparable via la seule couche moléculaire
    même si `use_aroma_wheel=True`, plutôt qu'exclu ou pénalisé pour une
    donnée qui n'existe simplement pas côté Yakima. `layers_used` (liste,
    triée) expose explicitement quelles couches ont contribué à CE houblon --
    jamais un score composite opaque.

    `use_molecular=use_aroma_wheel=False` -> liste vide (rien demandé). Un
    houblon sans AUCUNE donnée dans les couches actives -> absent (pas de
    score 0 fabriqué)."""
    if not use_molecular and not use_aroma_wheel:
        return []
    hops, comp, _, _ = load(con)
    per_layer: dict[str, dict[str, dict]] = {}
    if use_molecular:
        raw = {v: {c: amount(v, c, comp) for c in cmap if c not in NON_AROMA_DISPLAY}
              for v, cmap in comp.items()}
        per_layer["molecular"] = _coverage_penalized_cosine(raw, variety)
    if use_aroma_wheel:
        # T79 : voir le commentaire équivalent dans `by_descriptor` -- une
        # seule source par houblon, jamais un mélange.
        raw = {v: resolve_aroma_intensity(by_source)[0] for v, by_source in load_aroma_intensity(con).items()}
        per_layer["aroma_wheel"] = _coverage_penalized_cosine(raw, variety)

    candidates = set().union(*(sims.keys() for sims in per_layer.values())) if per_layer else set()
    ranked = []
    for h in candidates:
        if h not in hops:
            continue
        layer_scores = {layer: sims[h]["similarity"] for layer, sims in per_layer.items() if h in sims}
        if not layer_scores:
            continue
        combined = sum(layer_scores.values()) / len(layer_scores)
        entry = {"variety": h, "name": hops[h]["name"], "similarity": round(100 * combined, 1),
                 "layers_used": sorted(layer_scores),
                 "molecular_similarity": (round(100 * layer_scores["molecular"], 1)
                                          if "molecular" in layer_scores else None),
                 "aroma_wheel_similarity": (round(100 * layer_scores["aroma_wheel"], 1)
                                            if "aroma_wheel" in layer_scores else None),
                 "shared_compounds": per_layer.get("molecular", {}).get(h, {}).get("shared", [])[:5],
                 "shared_descriptors": per_layer.get("aroma_wheel", {}).get(h, {}).get("shared", [])[:5],
                 "sources": hops[h]["sources"], "purpose": hops[h].get("purpose")}
        ranked.append(entry)
    ranked.sort(key=lambda r: (-r["similarity"], r["variety"]))
    return ranked[:top]
