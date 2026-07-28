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
  COMMERCIALE. Vérifié sur le dump réel (2026) :
  - lacunaire : ~14-16 % des liens ont une concentration ; un aliment liste ~6000+
    composés (longue traîne de bruit). Basilic : 6628 composés, 7 % avec concentration.
  - MAIS les composés d'impact PRÉSENTS ont bien leur concentration (basilic : linalol
    437, eugénol 5,15, cinéole 45,55 mg/100g) → OAV partiel possible là où c'est couvert.
  - TROU de couverture : l'estragole (marqueur majeur du basilic) est absent SOUS CE NOM.
    → ne jamais matcher par nom : joindre par **PubChem CID / InChIKey** (estragole=CID 8815).
    C'est le rôle de PubChem dans l'archi.
  - le tri par concentration est dominé par du bruit NUTRITIONNEL (eau, cendres, minéraux) :
    FooDB mêle nutrition et arôme → FILTRER via whitelist odeur-active AVANT, jamais classer
    par concentration brute.
  DONC `ingest_foodb` : filtrer (Flavornet/FlavorDB2) → concentration où présente →
  cross-référencer une 2e source pour rattraper les trous → sinon présence + prior de seuil.
  Joindre par CID, pas par nom. SCAFFOLD. Voir `tools/{audit_foodb,foodb_impact_check}.py`.
- **Flavornet** : ~738 composés odeur-actifs (GC-O) + descripteurs. HTML statique.
  Sert de whitelist « sensoriellement présent ». `ingest.ingest_flavornet` = SCAFFOLD.
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
1. `ingest.ingest_foodb` — le plus utile. Lancer d'abord `tools/audit_foodb.py`, puis
   ingérer FILTRÉ (voir docstring). Nécessite le dump FooDB local.
2. `ingest.crawl_yakima` — itérer contre un site SPA vivant.
3. Couche seuils (FlavorDB2) + drapeau biotransformation par souche
   (géraniol→citronellol, précurseurs→thiols) — touche plusieurs modules.
4. **Découverte par descripteurs** (`by-descriptor`) — demandé par l'utilisateur.
   Détail : `docs/FEATURE_NOTES.md`. Grounded (roues d'arôme réelles), simple,
   implémentable dès maintenant sur la base existante.

## Conventions
- Commentaires/docstrings en français (cohérent avec l'existant).
- Ne jamais fabriquer de données houblon en dur : passer par un parseur + source tracée.
- `pytest` doit rester vert. Ajouter un test quand on touche un solveur ou un parseur.
- Commandes : `pip install -e ".[dev]"` ; `pytest -q` ; `hopmatch build` puis
  `hopmatch amplify|contrast|combine <note>`.
