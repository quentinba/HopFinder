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


def hop_aroma_intensity(con, variety: str) -> dict[str, float]:
    """Roue d'arôme QUANTITATIVE d'un houblon (T26 backlog), {descriptor:
    intensité 0-100} — Yakima uniquement (`hop_aroma_intensity`, distinct de
    `hop_descriptors` qui est binaire présence/absence). Vide pour un houblon
    sans cette donnée (BarthHaas seul, ou variété non couverte) : pas de
    repli inventé."""
    return {r["descriptor"]: r["intensity"] for r in con.execute(
        "SELECT descriptor, intensity FROM hop_aroma_intensity WHERE variety=?", (variety,))}


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


def _normalize_descriptors(descriptors: list[str]) -> set[str]:
    """Vocabulaire réel `hop_descriptors` (comme `by_descriptor`), pas inventé —
    même normalisation utilisée par `amplify`/`contrast` pour une sélection
    manuelle de descripteurs."""
    return {reference.DESCRIPTOR_ALIASES.get(d.strip().lower(), d.strip().lower())
           for d in descriptors if d.strip()}


# --------------------------------------------------------------------------- #
# Couches de score
# --------------------------------------------------------------------------- #
def molecular_scores(note_profile, comp, use_oav=False, mols=None):
    """Similarité moléculaire normalisée-par-composé (TF-IDF). -> {variety: (score, contribs)}.

    `use_oav` : multiplie la contribution d'une molécule par un PRIOR DE PUISSANCE
    (REFERENCE_THRESHOLD_PPB / seuil olfactif) quand son seuil est connu — seulement
    pour les ~14 molécules curées dans `reference.MOLECULES` (myrcène, humulène,
    caryophyllène, géraniol, linalol, thiols...), les composés d'huile de houblon
    les plus courants. Ce n'est PAS un OAV réel (aucune concentration mesurée) :
    juste une réponse à « molécule X et Y ont la même quantité normalisée, mais X a
    un seuil olfactif 10x plus bas — laquelle pèse le plus dans l'odeur perçue ? ».
    Vérifié sur la base réelle : change le classement complet sur ~18% des notes et
    le houblon #1 sur ~15% (échantillon de 40 notes) — un effet réel, pas un bruit.
    """
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
            if use_oav and mols:
                thr = mols.get(hop_compound(m), {}).get("threshold_ppb")
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
    """
    hops, comp, hop_desc, mols = load(con)
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

    mol = molecular_scores(profile, comp, use_oav=use_oav, mols=mols)
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
    return {"mode": "amplify", "note": note, "coverage": cov, "orphan": orphan,
           "use_oav": use_oav, "has_descriptors": has_descriptors,
           "ranked": ranked[:top]}


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
    intensity_by_variety: dict[str, dict[str, float]] = {}
    for r in con.execute("SELECT variety, descriptor, intensity FROM hop_aroma_intensity"):
        intensity_by_variety.setdefault(r["variety"], {})[r["descriptor"]] = r["intensity"]
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
        intensity = intensity_by_variety.get(h, {})
        quant_descriptors = sorted(d for d in wheel if d in intensity)
        quant_score = (sum(intensity[d] for d in quant_descriptors) / len(quant_descriptors)
                      if quant_descriptors else None)
        ranked.append({"variety": h, "name": hops[h]["name"],
                       "matched_descriptors": sorted(matched), "all_descriptors": sorted(hd),
                       "compounds": compounds, "sources": hops[h]["sources"],
                       "purpose": hops[h].get("purpose"), "intensity": intensity,
                       "quant_score": quant_score, "quant_descriptors": quant_descriptors,
                       "_rank": (-len(matched), 0 if quant_score is not None else 1,
                                -(quant_score or 0.0), -total_oil, h)})
    ranked.sort(key=lambda r: r["_rank"])
    for r in ranked:
        del r["_rank"]
    return {"ranked": ranked[:top], "total_matches": len(ranked)}
