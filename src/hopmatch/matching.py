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


def load(con: sqlite3.Connection):
    hops = {r["variety"]: dict(r) for r in con.execute("SELECT * FROM hops")}
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
                           "why": mol.get(h, (0, []))[1][:4], "sources": hops[h]["sources"]})
    ranked.sort(key=lambda r: -r["score"])
    _, orphan, cov = coverage(profile, comp)
    return {"mode": "amplify", "note": note, "coverage": cov, "orphan": orphan,
           "use_oav": use_oav, "has_descriptors": has_descriptors,
           "ranked": ranked[:top]}


# --------------------------------------------------------------------------- #
# CAS A — contrast (piloté par les affinités descripteurs, pas les molécules)
# --------------------------------------------------------------------------- #
def contrast(con, note: str | None = None, descriptors: list[str] | None = None, top=8):
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

    Retourne aussi `unmapped` : les descripteurs choisis qui n'ont AUCUNE
    entrée dans `reference.CONTRAST_AFFINITY` (couvre les 38 descripteurs
    réels de la base construite au moment de l'écriture, mais un futur crawl
    peut en révéler un nouveau) — signalés explicitement plutôt que de
    disparaître en silence dans une cible d'affinité vide, pour ne pas laisser
    croire à tort qu'aucun houblon ne contraste avec un descripteur donné.
    """
    hops, comp, hop_desc, _ = load(con)
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
    # descripteurs qui contrastent bien avec ceux de la note
    target = set()
    unmapped = sorted(d for d in ndesc if d not in reference.CONTRAST_AFFINITY)
    for d in ndesc:
        target.update(reference.CONTRAST_AFFINITY.get(d, []))
    ranked = []
    for h in hops:
        hd = hop_desc.get(h, set())
        hit = hd & target
        if hit:
            ranked.append({"variety": h, "name": hops[h]["name"],
                           "score": round(100 * len(hit) / max(len(target), 1), 1),
                           "contrast_via": sorted(hit), "sources": hops[h]["sources"]})
    ranked.sort(key=lambda r: -r["score"])
    return {"mode": "contrast", "note": label, "affinity_target": sorted(target),
           "unmapped": unmapped, "ranked": ranked[:top]}


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


def _pairing_grown_blends(con, candidates: list[dict], target: set[str], max_hops: int = 5
                          ) -> list[dict]:
    """
    T33 backlog (décision utilisateur) : propose des blends de TAILLE
    CROISSANTE (1..max_hops), pas un seul blend "optimal" — pour laisser le
    brasseur choisir son compromis taille/couverture/authenticité plutôt que
    de lui imposer un seul résultat.

    Le choix des houblons À CHAQUE TAILLE privilégie la fréquence RÉELLE
    d'association en recette (BeerMaverick, `hop_pairings`) — PAS la
    couverture ensembliste pure comme l'ancienne version de `contrast_blend` :
    demande explicite de l'utilisateur, la couverture reste calculée et
    rapportée mais ne pilote plus le choix des houblons en priorité.

    `candidates` : liste déjà triée par pertinence décroissante, chaque entrée
    a au moins une clé "covers" (set[str], sous-ensemble de `target` que ce
    houblon couvre — le filtre de pertinence, càd ne garder que les houblons
    avec `covers` non vide, est déjà appliqué en amont par l'appelant).

    Taille 1 : le houblon le plus pertinent tout court (`candidates[0]`) — la
    notion de "pairing" n'existe pas pour un seul houblon seul.
    Taille k>1 : le houblon dont la fréquence RÉELLE de pairing avec
    N'IMPORTE LEQUEL des houblons déjà dans le blend est la plus haute, parmi
    les candidats restants (`via="pairing"`). Repli EXPLICITE sur la
    couverture gloutonne classique (`via="coverage"` : houblon qui ajoute le
    plus de `target` encore non couvert) si aucune fréquence réelle n'existe
    depuis le blend courant — ne jamais renvoyer un blend plus petit que
    possible juste par manque de donnée BeerMaverick, mais toujours signaler
    la provenance de chaque houblon plutôt que de la cacher.

    Va TOUJOURS jusqu'à `max_hops` (ou épuisement des candidats) — ne s'arrête
    PAS dès couverture complète (décision utilisateur, 2026-08 : voir un blend
    à 5 même quand 1 seul houblon couvre déjà toute la cible reste une info
    utile — l'utilisateur compare lui-même la taille/couverture/authenticité,
    l'outil ne décide pas à sa place). Quand il ne reste ni fréquence réelle
    ni gain de couverture (cible déjà entièrement couverte, ou plus aucun
    candidat n'apporte quoi que ce soit de neuf), repli sur le houblon suivant
    par PERTINENCE globale (`via="relevance"`) plutôt que de s'arrêter — un
    houblon pertinent de plus reste une proposition valable, signalée comme
    telle (ni pairing réel, ni gain de couverture). S'arrête seulement quand
    le pool de candidats est épuisé."""
    if not candidates or not target:
        return []
    freq = _hop_pairing_frequencies(con)
    by_variety = {c["variety"]: c for c in candidates}
    pool = list(candidates)
    blend: list[tuple[str, str]] = []  # [(variety, via), ...]
    blends = []
    for size in range(1, max_hops + 1):
        if not pool:
            break
        if size == 1:
            chosen, via = pool[0], "top"
        else:
            best, best_freq = None, -1.0
            for cand in pool:
                for existing_v, _via in blend:
                    f = freq.get((existing_v, cand["variety"]))
                    if f is not None and f > best_freq:
                        best, best_freq = cand, f
            if best is not None:
                chosen, via = best, "pairing"
            else:
                covered_so_far = (set().union(*(by_variety[v]["covers"] for v, _ in blend))
                                  if blend else set())
                remaining_target = target - covered_so_far
                gain_candidates = [c for c in pool if c["covers"] & remaining_target]
                if gain_candidates:
                    chosen = max(gain_candidates,
                                key=lambda c: len(c["covers"] & remaining_target))
                    via = "coverage"
                else:
                    chosen, via = pool[0], "relevance"
        blend.append((chosen["variety"], via))
        pool = [c for c in pool if c["variety"] != chosen["variety"]]
        covered = set().union(*(by_variety[v]["covers"] for v, _ in blend))
        blends.append({
            "size": size,
            "hops": [{"variety": v, "name": by_variety[v]["name"], "via": via_,
                      "sources": by_variety[v]["sources"],
                      "covers": sorted(by_variety[v]["covers"])}
                     for v, via_ in blend],
            "covered": sorted(target & covered),
            "residual": sorted(target - covered),
        })
    return blends


def contrast_blend(con, note: str | None = None, descriptors: list[str] | None = None,
                   max_hops: int = 5, top_candidates: int = 30):
    """
    Propose des blends de taille croissante (1..max_hops) plutôt qu'un seul
    blend "optimal" — voir `_pairing_grown_blends` pour le mécanisme complet
    (fréquence RÉELLE de pairing BeerMaverick en priorité, repli couverture
    explicite). `contrast` reste non-moléculaire par design (cf.
    ARCHITECTURE.md) : la cible et la pertinence des candidats viennent
    toujours de `CONTRAST_AFFINITY`/`hop_descriptors`, jamais des molécules.
    """
    r = contrast(con, note=note, descriptors=descriptors, top=top_candidates)
    target = set(r["affinity_target"])
    candidates = [dict(h, covers=set(h["contrast_via"])) for h in r["ranked"]]
    blends = _pairing_grown_blends(con, candidates, target, max_hops=max_hops)
    return {"mode": "contrast_blend", "note": r["note"], "affinity_target": r["affinity_target"],
           "unmapped": r["unmapped"], "blends": blends}


def amplify_blend(con, note: str, w_mol: float = 0.5, w_desc: float = 0.5, use_oav=False,
                  max_hops: int = 5, top_candidates: int = 30, descriptors: list[str] | None = None):
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
    _, _, hop_desc, _ = load(con)
    ndesc = _normalize_descriptors(descriptors) if descriptors else get_note_descriptors(con, note)
    target = set(ndesc)
    candidates = []
    for h in r["ranked"]:
        covers = target & hop_desc.get(h["variety"], set())
        if covers:
            candidates.append(dict(h, covers=covers))
    blends = _pairing_grown_blends(con, candidates, target, max_hops=max_hops)
    return {"mode": "amplify_blend", "note": note, "target_descriptors": sorted(target),
           "has_descriptors": True, "blends": blends}


# --------------------------------------------------------------------------- #
# DÉCOUVERTE — by_descriptor (pas un cas A/B : pas de note requise)
# --------------------------------------------------------------------------- #
_NON_AROMA_DISPLAY = {"total_oil", "alpha_acid", "beta_acid"}


def by_descriptor(con, selected: list[str], top: int = 10):
    """
    Houblons dont la roue d'arôme (`hop_descriptors`, BarthHaas/Yakima réelles)
    recoupe une sélection de descripteurs. Grounded sur les données houblon
    directement — ne dépend ni de CONTRAST_AFFINITY (prior curé) ni de FooDB.
    Tri : (1) nb de descripteurs recoupés desc, (2) total_oil réconcilié desc
    (proxy d'intensité aromatique), (3) variety asc (déterminisme).
    """
    hops, comp, hop_desc, _ = load(con)
    selected = {reference.DESCRIPTOR_ALIASES.get(d, d) for d in selected}
    ranked = []
    for h in hops:
        hd = hop_desc.get(h, set())
        matched = selected & hd
        if not matched:
            continue
        hcomp = comp.get(h, {})
        total_oil = (hcomp.get("total_oil") or {}).get("mid") or 0.0
        compounds = sorted(
            ({"compound": c, "mid": v["mid"], "unit": v["unit"], "sources": v["sources"]}
             for c, v in hcomp.items() if c not in _NON_AROMA_DISPLAY and v["mid"] is not None),
            key=lambda r: -r["mid"])
        ranked.append({"variety": h, "name": hops[h]["name"],
                       "matched_descriptors": sorted(matched), "all_descriptors": sorted(hd),
                       "compounds": compounds, "sources": hops[h]["sources"],
                       "_rank": (-len(matched), -total_oil, h)})
    ranked.sort(key=lambda r: r["_rank"])
    for r in ranked:
        del r["_rank"]
    return ranked[:top]
