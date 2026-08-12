# Architecture

## Principe : les données sont le goulot, pas l'algorithme
Un scoring sophistiqué (cosinus pseudo-OAV) sur des données ingrédient en
présence/absence et des profils houblon en fourchettes produit de la précision-
déchet. hopmatch privilégie donc des couches robustes et honnêtes.

## Trois couches
1. **Descripteurs (primaire).** Recoupement entre les descripteurs de la note et
   la roue d'arôme du houblon (BarthHaas/Yakima). Sans concentration, robuste,
   contourne le plafond de couverture. C'est ce que le brasseur « pense ».
2. **Molécules (secondaire).** Similarité normalisée-par-composé (TF-IDF) : chaque
   composé est ramené à [0,1] à travers les houblons puis pondéré par sa rareté,
   pour que les molécules-signature pilotent, pas le myrcène ubiquitaire. Le seuil
   olfactif est un **prior de puissance** (option `--oav`), pas un OAV réel.
3. **Honnêteté.** Couverture (fraction du caractère réellement portable par le
   houblon) + molécules **orphelines** + biotransformation levure optionnelle
   (`--biotransform`, portée étroite — voir plus bas).

## Base : EAV multi-sources
`hop_composition(variety, compound, vmin, vmax, unit, source, confidence, notes)`
avec clé (variety, compound, source) → deux sources coexistent pour une variété.
Réconciliation à la lecture : moyenne des milieux de fourchette, provenance tracée.
Unités mixtes (% d'huile vs µg/kg pour les thiols) gérées via la normalisation
par composé (les unités s'annulent au sein d'un composé).

`flavornet_compounds(cas, compound, descriptors)` : whitelist odeur-active, distincte
de `molecules` (couche de matching, avec seuils). Sert uniquement à filtrer FooDB à
l'ingestion (`ingest_foodb`), jointure par CAS. `ingest_foodb` écrit aussi dans
`molecules` en `INSERT OR IGNORE` (odeur/descripteur uniquement), sans jamais y
écrire de seuil.

`pubchem_cids(cas, cid)` : résolution structurale CAS→CID PubChem
(`ingest.resolve_pubchem_cids`), bornée à la whitelist Flavornet. Le "liant" entre
les 3 mondes — voir docs/DATA_SOURCES.md pour le détail. Deux consommateurs :
`ingest._canonical_compound` (fusion de synonymes par identité de CID, priorité sur
la table d'alias manuelle) et `ingest_flavordb2` (accès direct à la fiche FlavorDB2
par CID, sans recherche par nom).

`flavordb2_thresholds(cas, compound, threshold_ppb)` : même principe que
`flavornet_compounds` — table brute dédiée, bornée aux ~734 composés de la whitelist
Flavornet (pas les 25 595 molécules de FlavorDB2 : périmètre = ce dont hopmatch peut
se servir). `ingest_foodb` lit **cette table directement** pour le palier « seuil
connu », **jamais** `molecules`/`reference.MOLECULES` (14 seuils manuels, amorce
littérature) — décision explicite : ne jamais mélanger un seuil sourcé et un seuil
deviné dans une même décision de poids automatisée. `reference.MOLECULES` reste
utilisé ailleurs (option `--oav`, indépendante de ce pipeline).

**Normalisation des noms de composés à l'ingestion FooDB** (`ingest._canonical_compound`).
Deux pièges d'honnêteté sinon : synonymes de nommage (estragole/methyl-chavicol,
β-caryophyllène/caryophyllène) → sans normalisation, double comptage dans le profil
d'une note OU fausse orpheline alors que le houblon fournit la molécule sous un autre
nom. Résolution en cascade : (1) **identité de CID PubChem** (`pubchem_cids`, priorité —
fait chimique vérifié, pas une supposition de nommage) ; (2) `reference.ALIASES`, réduit
aux agrégations sans CID propre (« thiols » regroupe plusieurs molécules mesurées
ensemble côté houblon — pas un synonyme de nommage) ; (3) dépréfixage grec, filet pour
les CAS non résolus par PubChem. On ne renomme que vers une forme déjà connue du
vocabulaire houblon.

## Validation/réparation
`schema.validate_and_repair` détecte l'inversion myrcène/caryophyllène (fréquente
dans les scrapes tiers), les négatifs, les sommes incohérentes. Inoffensif sur
BarthHaas/Yakima (propres) ; utile si tu ingères un dataset brut.

## Les modes
- `amplify` = w_mol·(molécules) + w_desc·(descripteurs). Prolonger l'ajout.
- `contrast` = affinités descripteurs (carte curée). Contraster. **Non
  moléculaire** : le contraste ne se dérive pas des composés partagés. Par
  `note`, exige `note_descriptors` peuplé pour cette note — vide par défaut
  pour toutes les notes (pas d'amorce littérature dans ce projet, retirée à la
  demande explicite de l'utilisateur ; dériver des descripteurs depuis FooDB a
  aussi été tenté et rejeté, données trop génériques, voir
  docs/DATA_SOURCES.md) — `ValueError` explicite dans ce cas. Le chemin normal
  est `descriptors=[...]` : sélection manuelle par l'utilisateur sur le
  vocabulaire réel `hop_descriptors` (même principe que `by_descriptor`),
  fonctionne pour n'importe quelle note sans curation. `contrast_blend` propose
  une combinaison parcimonieuse (couverture ensembliste gloutonne, pas de NNLS)
  avec résidu non couvert rapporté.
- `by_descriptor` = recoupement `hop_descriptors ∩ sélection`, sans note requise.
  Orthogonal à `amplify`/`contrast` : grounded sur les roues d'arôme réelles (pas
  `CONTRAST_AFFINITY`), ne dépend ni de FooDB ni de `crawl_yakima`. Tri par nb de
  descripteurs recoupés puis `total_oil` réconcilié (proxy d'intensité) puis variety.
  Descripteurs normalisés à l'ingestion via `reference.DESCRIPTOR_ALIASES`.

`--biotransform` (`amplify`) : `matching.hop_compound(m, biotransform=True)`
redirige une molécule vers son précurseur mesuré côté houblon via
`reference.BIOTRANSFORMATIONS` — géraniol→citronellol et linalol→alpha-terpinéol
uniquement (deux voies avec preuve indépendante convergente ale/lager, King &
Dickinson 2003 ; corroboré par Michel et al. 2019 sur l'absence d'effet souche). Un
seul point d'implémentation (`hop_compound`) traverse `amount`, `specificity`,
`coverage`, donc `molecular_scores`/`amplify`. Pas de sélection de souche : aucune
source ne compare des souches commerciales entre elles, seulement des codes de
collection académique — voir README.md#option---biotransform pour le détail du
raisonnement.

## `combine()` (NNLS) — implémenté puis retiré
Un mode `combine` a existé : `A·w ≈ t` (A = composés×houblons normalisés, t = poids
note) résolu par NNLS, parcimonie (≤ max_hops) via deux heuristiques combinées
(garder le meilleur des deux résidus), **résidu irréductible** = orphelines. Retiré
le 2026-08-12 (décision utilisateur) après mesure sur les 506 notes réelles : 0 %
ne dépassaient 20 % de couverture (max observé 12 %, médiane 1,3 %). Sur les notes à
un seul composé « producible » (la majorité), NNLS dégénère en un système à une
seule équation : n'importe quel houblon porteur du composé atteint un résidu
artificiel de 0, une fausse confiance sans rapport avec la couverture réelle — pas
un bug d'implémentation, la chimie de l'huile de houblon ne recoupe simplement pas
la plupart des arômes alimentaires. Voir CLAUDE.md pour le détail complet et
l'historique git pour le code retiré.

## Ce qui est volontairement absent
Pas d'OAV quantitatif (pas de concentration fiable), pas de cosinus pseudo-OAV,
pas de modèle de dose chiffré. Ces éléments reviendront si/quand FooDB fournit des
concentrations exploitables (cf. audit).
