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
   houblon) + molécules **orphelines** + (roadmap) biotransformation par souche.

## Base : EAV multi-sources
`hop_composition(variety, compound, vmin, vmax, unit, source, confidence, notes)`
avec clé (variety, compound, source) → deux sources coexistent pour une variété.
Réconciliation à la lecture : moyenne des milieux de fourchette, provenance tracée.
Unités mixtes (% d'huile vs µg/kg pour les thiols) gérées via la normalisation
par composé (les unités s'annulent au sein d'un composé).

`flavornet_compounds(cas, compound, descriptors)` : whitelist odeur-active, distincte
de `molecules` (couche de matching, avec seuils). Sert uniquement à filtrer FooDB à
l'ingestion (`ingest_foodb`), jointure par CAS (pas encore par PubChem CID/InChIKey —
voir docs/DATA_SOURCES.md). `ingest_foodb` écrit aussi dans `molecules` en `INSERT OR
IGNORE` (odeur/descripteur uniquement), sans jamais y écrire de seuil.

`flavordb2_thresholds(cas, compound, threshold_ppb)` : même principe que
`flavornet_compounds` — table brute dédiée, bornée aux ~734 composés de la whitelist
Flavornet (pas les 25 595 molécules de FlavorDB2 : périmètre = ce dont hopmatch peut
se servir). `ingest_foodb` lit **cette table directement** pour le palier « seuil
connu », **jamais** `molecules`/`reference.MOLECULES` (14 seuils manuels, amorce
littérature) — décision explicite : ne jamais mélanger un seuil sourcé et un seuil
deviné dans une même décision de poids automatisée. `reference.MOLECULES` reste
utilisé ailleurs (option `--oav`, indépendante de ce pipeline).

**Normalisation des noms de composés à l'ingestion FooDB** (`ingest._canonical_compound`).
Deux pièges d'honnêteté sinon : (1) synonymes explicites (`reference.ALIASES`, ex.
estragole/methyl-chavicol, même CAS) → sans ça, double comptage dans le profil d'une
note ; (2) préfixe grec (β-caryophyllene vs caryophyllene, vocabulaire houblon sans
préfixe) → sinon fausse orpheline alors que le houblon fournit la molécule sous son
autre nom. On ne renomme que vers une forme déjà connue du vocabulaire houblon.

## Validation/réparation
`schema.validate_and_repair` détecte l'inversion myrcène/caryophyllène (fréquente
dans les scrapes tiers), les négatifs, les sommes incohérentes. Inoffensif sur
BarthHaas/Yakima (propres) ; utile si tu ingères un dataset brut.

## Les trois modes
- `amplify` = w_mol·(molécules) + w_desc·(descripteurs). Cas A, prolonger.
- `contrast` = affinités descripteurs (carte curée). Cas A, contraster. **Non
  moléculaire** : le contraste ne se dérive pas des composés partagés.
- `combine` = NNLS `A·w ≈ t` (A = composés×houblons normalisés, t = poids note),
  parcimonie (≤ max_hops), + **résidu irréductible** = orphelines. Cas B.
- `by_descriptor` = recoupement `hop_descriptors ∩ sélection`, sans note requise.
  Orthogonal aux cas A/B : grounded sur les roues d'arôme réelles (pas
  `CONTRAST_AFFINITY`), ne dépend ni de FooDB ni de `crawl_yakima`. Tri par nb de
  descripteurs recoupés puis `total_oil` réconcilié (proxy d'intensité) puis variety.
  Descripteurs normalisés à l'ingestion via `reference.DESCRIPTOR_ALIASES`.

## Ce qui est volontairement absent
Pas d'OAV quantitatif (pas de concentration fiable), pas de cosinus pseudo-OAV,
pas de modèle de dose chiffré. Ces éléments reviendront si/quand FooDB fournit des
concentrations exploitables (cf. audit).
