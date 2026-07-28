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

## Ce qui est volontairement absent
Pas d'OAV quantitatif (pas de concentration fiable), pas de cosinus pseudo-OAV,
pas de modèle de dose chiffré. Ces éléments reviendront si/quand FooDB fournit des
concentrations exploitables (cf. audit).
