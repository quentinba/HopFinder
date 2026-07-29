# CLAUDE.md — contexte projet hopmatch

Ce fichier donne à Claude Code le contexte et les décisions issues de la conception
de hopmatch. Lis-le avant d'agir. (Détails : `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md`.)

## But
Outil brasseur : **note olfactive → molécules → houblons**. Deux cas d'usage aux
scorings DIFFÉRENTS :
- **Cas A** — accorder un houblon à un ajout (yuzu, basilic…). Modes `amplify`
  (prolonger) et `contrast` (contraster). L'ajout est dans la bière, donc le houblon
  n'a pas à le reproduire : le « plafond de couverture » ne pénalise pas.
- **Cas B** — reproduire un goût sans ajout, via une **combinaison** de houblons
  (`combine`, NNLS). Ici la valeur est de dire ce qui est **irréductible**.

## Décisions de conception (ne pas revenir dessus sans raison)
- **Descripteurs = couche primaire** (roues d'arôme BarthHaas/Yakima). Robuste, sans
  concentration. Les molécules sont la couche secondaire.
- **Pas d'OAV quantitatif.** On n'a pas de concentration fiable (voir FooDB ci-dessous).
  Le seuil olfactif est un **prior de puissance** (option `--oav`), pas un OAV réel.
  Ne pas réintroduire de cosinus pseudo-OAV : ce serait de la précision-déchet.
- **Le contraste n'est PAS moléculaire.** Il se dérive d'une carte d'affinités
  descripteurs (`reference.CONTRAST_AFFINITY`), pas des composés partagés.
- **Matching moléculaire = similarité normalisée-par-composé (TF-IDF)**, pour que les
  molécules-signature pilotent, pas le myrcène ubiquitaire.
- **Honnêteté d'abord** : toujours rapporter la couverture et les molécules orphelines.
- **Base EAV multi-sources** : `hop_composition` clé (variety, compound, source) ;
  réconciliation à la LECTURE (moyenne des milieux, provenance tracée), pas à l'écriture.

## Réalité des données (vérifiée)
- **BarthHaas** : source houblon primaire. HTML servi, parsable, inclut les THIOLS.
  Crawler implémenté (`ingest.crawl_barthhaas`).
- **Yakima Chief** : secondaire. Front SPA → extraction DOM (ou Playwright). Ajoute
  β-pinène, sélinène. `ingest.crawl_yakima` = SCAFFOLD.
- **FooDB** : source note→molécule. Dump bulk local, figé 2020-04-07, licence NON
  COMMERCIALE. `ingest.ingest_foodb` IMPLÉMENTÉ. Vérifié sur le dump réel :
  - lacunaire : 14,4 % des liens compound↔aliment ont une concentration (mesuré sur
    l'ENSEMBLE du dump via `tools/audit_foodb.py`, pas un échantillon) ; un aliment
    liste ~6000+ composés (longue traîne de bruit).
  - **piège dataset** : `Compound.csv` a ses colonnes décalées à partir de `moldb_iupac` —
    `cas_number` contient des SMILES, le vrai CAS est sous `description` (0 % de forme
    CAS plausible dans `cas_number` vs 21,6 % dans `description`, sur 70 477 lignes).
    `ingest._resolve_cas_column` détecte la bonne colonne par FORMAT, pas par nom déclaré.
    Une fois ce bug contourné, l'estragole (marqueur du basilic) EST bien présent dans
    FooDB — l'absence constatée initialement était un artefact de ce bug, pas un vrai trou.
  - synonymes entre sources (estragole/methyl-chavicol même CAS 140-67-0 ;
    β-caryophyllène/caryophyllène) → sans normalisation : double comptage note-side et
    FAUSSE ORPHELINE côté houblon. Résolu par `ingest._canonical_compound`
    (`reference.ALIASES` + dépréfixage grec), PAS encore par jointure PubChem CID —
    ALIASES est une amorce manuelle, à remplacer si le vocabulaire s'élargit beaucoup.
  - le tri par concentration est dominé par du bruit NUTRITIONNEL (eau, cendres, minéraux) :
    FooDB mêle nutrition et arôme → FILTRER via whitelist odeur-active (Flavornet) AVANT.
  - seules unités « masse comparable » retenues comme concentration fiable (mg/100g,
    mg/kg) : `standard_content` prétend normaliser mais recopie IU/ppb/µM tels quels
    (vérifié) — les traiter comme des mg serait de la précision-déchet.
  Poids : concentration (mg/100g-équivalent) → sinon prior de seuil (1/seuil, depuis
  `molecules`) → sinon présence pure. 3 paliers disjoints, jamais mélangés entre eux.
  FUSIONNE avec l'amorce littérature (molécule par molécule), ne l'efface pas.
  `reference.NOTE_TO_FOODB` : 4/7 notes-amorce seulement (kumquat, basilic, fruit-passion,
  mangue) — yuzu absent de FooDB, rose = faux ami ("Rose hip"), pin-résine pas un aliment.
  Voir `tools/{audit_foodb,foodb_impact_check}.py`.
- **Flavornet** : 738 composés odeur-actifs (GC-O) + descripteurs, 734 CAS uniques
  (page HTML statique unique `d_kovats_ov101.html`, pas de pagination). Sert de whitelist
  « sensoriellement présent » (table `flavornet_compounds`, distincte de `molecules`).
  `ingest.ingest_flavornet` IMPLÉMENTÉ.
- **FlavorDB2** : seuils par molécule. Pas d'API (JSON par fiche ; endpoint v1 = 500).
  Licence CC BY-NC-SA (non commercial).
- **PubChem (PUG-REST)** : domaine public. Clé InChIKey/CID pour joindre les 3 mondes.
- **Licence** : le CODE est MIT ; FooDB et FlavorDB2 sont NON COMMERCIALES. Un usage
  commercial imposerait de retirer/renégocier ces sources.

## Caveat validation
`schema.validate_and_repair` corrige l'inversion myrcène/caryophyllène des datasets
scrappés sales. Sur BarthHaas/Yakima (propres) elle ne se déclenche pas — c'est un
filet de sécurité, pas une valeur active.

## Prochaines tâches (ordre d'utilité)
Fait : `ingest.ingest_flavornet`, `ingest.ingest_foodb`, `by-descriptor` (voir
`docs/FEATURE_NOTES.md` pour le détail de spec de ce dernier). Reste :
1. `ingest.crawl_yakima` — itérer contre un site SPA vivant.
2. Couche seuils (FlavorDB2) + drapeau biotransformation par souche
   (géraniol→citronellol, précurseurs→thiols) — touche plusieurs modules. Enrichirait
   aussi les poids `foodb:thr` de `ingest_foodb`, limités aux seuils déjà connus.
3. Jointure PubChem CID/InChIKey — remplacerait la table d'alias manuelle
   (`reference.ALIASES`) par une résolution structurale des synonymes, plus robuste
   à l'échelle que l'amorce actuelle.

## Conventions
- Commentaires/docstrings en français (cohérent avec l'existant).
- Ne jamais fabriquer de données houblon en dur : passer par un parseur + source tracée.
- `pytest` doit rester vert. Ajouter un test quand on touche un solveur ou un parseur.
- Commandes : `pip install -e ".[dev]"` ; `pytest -q` ; `hopmatch build` puis
  `hopmatch amplify|contrast|combine <note>` ou `hopmatch by-descriptor <descripteurs>`.
