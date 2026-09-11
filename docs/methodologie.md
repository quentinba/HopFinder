# Méthodologie — d'où vient chaque chiffre affiché

Ce document est la référence **rigoureuse** : les formules exactes, avec leurs unités,
ce que chaque chiffre veut dire, et ce que l'outil ne prétend pas faire. Il doit permettre
de **reproduire un résultat à la main** sans lire le code.

- Pour *essayer* l'outil : [README — Installation & usage](../README.md#installation--usage).
- Pour le *pourquoi* de chaque choix de conception et l'historique des décisions :
  [README — partie méthodologie](../README.md#méthodologie--sources-de-données) et
  `CLAUDE.md`.
- Pour le détail de chaque source (licence, mode d'obtention, pièges) :
  [docs/DATA_SOURCES.md](DATA_SOURCES.md).

Écrit le 2026-09-11 (AUDIT.md §6.3). Chiffres vérifiés sur la base du même jour :
192 houblons, 506 notes, 138 descripteurs.

---

## 0 bis. Un même objet, plusieurs noms (AUDIT.md §C4)

Trois mots désignent **exactement la même chose** selon l'endroit où on les lit. C'est
historique, assumé, et il vaut mieux le savoir que le deviner :

| Mot | Où | Pourquoi |
|---|---|---|
| **note** | code, base (`aroma_notes`), CLI (`hopmatch amplify <note>`) | nom d'origine, gardé partout en interne |
| **Ingredient** | libellé du champ en GUI | « note » ne parlait pas au brasseur — renommage **d'affichage seulement** (T76), jamais propagé au code ni à la base |
| **addition** | prose de la GUI (« Extend an addition ») | c'est ce que le mot décrit : ce qu'on met réellement dans la recette |

De même, **descripteur** (le mot d'arôme, ex. « dank ») et **catégorie de roue** (les 15
axes qui peuvent porter une intensité mesurée) ne sont pas synonymes : toute catégorie de
roue est un descripteur, l'inverse est faux — c'est ce qui sépare les deux heatmaps de
« From descriptors » (§4).

---

## 0. La règle d'unité (à lire en premier)

C'est le point qui a produit le bug le plus coûteux du projet (AUDIT.md §B1), et la seule
chose à comprendre avant toutes les formules : **une mesure de composé n'entre dans un
calcul que si on sait la ramener à une échelle commune.**

`hop_composition.unit` prend aujourd'hui 5 valeurs réelles :

| Unité | Signification | Traitement |
|---|---|---|
| `pct_oil` | % de l'**huile** totale | converti : `q = mid × huile_totale / 100` → ml/100 g |
| `ug_kg` | µg/kg de **houblon** (thiols) | déjà absolu, pris tel quel |
| `mg_100g` | mg/100 g de **houblon** (hops-comptoir) | **exclu** de tout calcul |
| `pct` | % du houblon (acides alpha/bêta, co-/colupulone) | hors axe aromatique (affichage seul) |
| `ml_100g` | ml/100 g (`total_oil` lui-même) | sert de dénominateur, jamais scoré |

Une seule fonction porte cette règle : **`matching.compound_quantity`**.

```
                    ⎧ mid × huile_totale / 100     si unit = pct_oil et huile_totale connue
quantité(mesure) =  ⎨ mid                          si unit ∈ {ug_kg}
                    ⎩ indéfinie                    sinon
```

« Indéfinie » signifie : la mesure **existe** mais n'est pas plaçable sur cet axe. Deux cas :

1. **unité incomparable** — `mg_100g` est une masse par 100 g de *houblon*, `pct_oil` une
   fraction de l'*huile*. Passer de l'une à l'autre exigerait une densité d'huile de houblon
   qu'aucune source de ce projet ne fournit. Aucune conversion n'est tentée.
2. **huile totale inconnue** — un % d'huile n'est convertible que si l'on sait combien
   d'huile le houblon porte. Aucune valeur par défaut n'est substituée.

Dans les deux cas la mesure est **écartée du calcul et nommée à l'écran**
(`matching.unscorable_measurements` → chip « N hop(s) not scorable here » dans Amplify).
Elle reste visible telle quelle, avec son unité, dans les tableaux de composition de Browse.

> **Pourquoi c'est capital.** Le score normalise chaque molécule par son maximum **sur toute
> la base**. Une seule valeur dans une unité ~1 000× plus grande devient donc ce maximum et
> écrase la contribution de *tous* les autres houblons — pas seulement celle du houblon
> fautif. Mesuré avant correction : 232/258 notes avaient un houblon `mg_100g` en tête, et
> 93 % changeaient de premier une fois l'unité écartée.

---

## 1. Réconciliation multi-sources (`matching.load`)

Avant tout calcul, chaque mesure est réduite à un point unique.

**Milieu d'intervalle.** Les sources publient des fourchettes ; on garde le milieu :

```
mid = (vmin + vmax) / 2        (ou l'unique borne connue si une seule est renseignée)
```

**Conflit entre sources.** `hop_composition` a pour clé `(variety, compound, source)` :
plusieurs sources coexistent pour le même couple. À la **lecture**, leurs `mid` sont
**moyennés** :

```
mid_réconcilié = moyenne( mid_s  pour chaque source s mesurant ce (variété, composé) )
```

La provenance reste tracée (`sources`) et affichée. Jamais de réconciliation à l'écriture :
la base garde toutes les mesures d'origine.

> ⚠ **Limite connue, non corrigée.** Cette moyenne ne vérifie pas que les unités
> concordent. Elle n'est sûre aujourd'hui que parce que l'ingestion garantit en amont qu'une
> variété donnée ne reçoit pas deux unités différentes pour le même composé. C'est une
> garantie d'ingestion, pas une garantie de lecture.

**Roue d'arôme : jamais de moyenne.** Yakima (0–100) et BarthHaas (0–8) mesurent selon des
méthodologies distinctes. Une seule source est retenue **par houblon**, entière ; BarthHaas
est remise à l'échelle :

```
intensité_0_100 = min(100, valeur_barthhaas × 100 / 8)
```

Vérifié sur les 2 569 valeurs réelles : après remise à l'échelle, moyenne Yakima 39,3 vs
BarthHaas 38,3 — l'hypothèse de linéarité tient empiriquement.

---

## 2. Amplify — « quel houblon prolonge cet ajout ? »

**Ce que ça fait, en termes de brasseur.** L'ajout (fraise, yuzu, basilic) est *déjà dans la
bière* : il apporte lui-même ses molécules. On cherche un houblon qui **prolonge** son
caractère, pas un qui le reproduise.

**Entrées.** `aroma_notes` (FooDB, dump figé 2020-04-07) : molécule → poids, pour l'ingrédient
choisi. `hop_composition` (BarthHaas/Yakima/hops-comptoir/Hopsteiner). `hop_descriptors`
(BarthHaas/Yakima/BeerMaverick). Les descripteurs de l'ingrédient sont pré-remplis depuis
`reference.INGREDIENT_DESCRIPTORS` — **un jugement direct, pas une dérivation de données**,
librement éditable.

### 2.1 Couche moléculaire (TF-IDF)

Pour un houblon `h` et une molécule `m` de poids `w(m)` dans la note :

```
quantité :        a(h,m)   = compound_quantity(mesure, huile_totale)        [§0]
normalisation :   tf(h,m)  = a(h,m) / max over h' of a(h',m)                ∈ [0,1]
spécificité :     idf(m)   = ln( N / (1 + N_m) ) + 1
score :           S_mol(h) = Σ over m of  w(m) × tf(h,m) × idf(m)
```

- `N` = nombre de houblons ayant une composition (191), `N_m` = nombre en portant `m`.
- `idf` fait qu'une molécule quasi ubiquitaire (myrcène, 190/191) pèse peu, une molécule rare
  beaucoup. Sans lui, le classement se réduirait à « les houblons les plus huileux ».
- Molécule dont `a = 0` : ignorée (ne contribue pas), jamais comptée comme un 0 pénalisant.

**Option `--oav`** (activée par défaut en GUI) : multiplie chaque contribution par un *prior
de puissance olfactive*, `30 / seuil_ppb(m)`, quand un seuil FlavorDB2 réel existe pour `m` —
sinon multiplicateur neutre `1`, jamais un seuil deviné. Ce n'est **pas** un OAV réel : il n'y
a aucune concentration mesurée en bière, seulement une pondération « à quantité normalisée
égale, la molécule au seuil le plus bas pèse davantage ».

### 2.2 Couche descripteurs

Simple **rappel** sur les descripteurs choisis pour l'ingrédient :

```
S_desc(h) = |D_note ∩ D_hop| / |D_note|        ∈ [0,1]
```

### 2.3 Score final affiché

```
score(h) = 100 × ( w_mol × S_mol(h)/max(S_mol) + w_desc × S_desc(h) )
```

`(w_mol, w_desc)` vaut `(0, 1)` en mode *Descriptors*, `(1, 0)` en *Molecular only*,
`(0.5, 0.5)` en *Both*. Si l'ingrédient n'a aucun descripteur, bascule automatique en
`(1, 0)` plutôt que de plafonner silencieusement le score à 50.

**Égalités** départagées par : huile totale décroissante, puis nom croissant. Nécessaire :
`S_desc` sur 3 descripteurs ne prend que 4 valeurs, les ex æquo sont la norme.

### 2.4 Exemple chiffré, vérifiable à la main

Ingrédient **strawberry**, mode *Molecular only*, base du 2026-09-11.

1. Le profil FooDB compte 65 molécules ; **une seule est productible** par un houblon :
   le géraniol, de poids `w = 0,332`. Couverture = 0,332 / Σw = **1,8 %**.
2. Quantités (§0) :
   - Talus : `1,8 % × 1,725 ml/100g / 100` = **0,031050**
   - Cryo Pop : `1,0 % × 3,0 / 100` = **0,030000**
   - maximum sur les 191 houblons = **0,031050** (Talus)
3. Spécificité : 160 houblons sur 191 portent du géraniol →
   `ln(191 / 161) + 1 = 0,170869 + 1` = **1,170869**
4. Scores moléculaires :
   - Talus : `0,332 × (0,031050/0,031050) × 1,170869` = **0,388729**
   - Cryo Pop : `0,332 × (0,030000/0,031050) × 1,170869` = **0,375583**
5. Normalisation par le meilleur (`mmax = 0,388729`) :
   - Talus : `0,388729 / 0,388729` = 1,0000 → **100,0**
   - Cryo Pop : `0,375583 / 0,388729` = 0,9662 → **96,6**

C'est exactement ce que l'écran affiche. On voit aussi la limite : avec **une seule molécule
productible**, ce classement ne fait que trier les houblons par quantité de géraniol — d'où
le chip « Single-molecule ranking » affiché dans ce cas précis.

### 2.5 Comment lire le score

- **C'est un rang relatif, pas une qualité d'accord.** Le meilleur houblon d'une requête vaut
  toujours 100, quelle que soit la pertinence réelle.
- **Il n'est pas comparable d'une requête à l'autre.** Un « 96,6 » sur strawberry et un
  « 96,6 » sur mangue ne disent rien l'un de l'autre. Seuls l'ordre et les écarts *à
  l'intérieur* d'un même tableau ont un sens.
- La couverture moléculaire (4–12 % typiques) mesure la part de l'ingrédient que la chimie
  du houblon recoupe. **Un chiffre bas est normal**, pas un défaut de données.

---

## 3. Contrast — « quel houblon contraste bien ? »

Cherche un profil **complémentaire**, pas similaire.

```
cible :   T = ⋃ CONTRAST_AFFINITY[d]  pour d dans les descripteurs de la note
score :   score(h) = 100 × |D_hop ∩ T| / |T|
```

**Ici le score est absolu** — une fraction de la cible réellement couverte — donc, contrairement
à Amplify, **comparable d'une requête à l'autre**. Égalités départagées comme Amplify.

`reference.CONTRAST_AFFINITY` est une **heuristique d'accord culinaire curée à la main**, pas
une donnée sourcée, et le contraste n'est **jamais** moléculaire.

---

## 4. From descriptors

```
1. filtre   : |D_sélection ∩ D_hop| ≥ 1        (descripteurs TEXTE uniquement)
2. tri n°1  : |D_sélection ∩ D_hop| décroissant
3. tri n°2  : intensité moyenne sur les catégories de roue cochées
4. tri n°3  : huile totale décroissante, puis nom
```

Les pills de roue d'arôme **notent** sans jamais filtrer — sauf si aucun descripteur texte
n'est saisi, auquel cas elles servent aussi de filtre (sinon rien ne filtrerait).

Les deux heatmaps sont séparées **par vocabulaire**, pas par disponibilité : la première
contient les catégories qui *peuvent* porter une mesure de roue quelque part dans la base, la
seconde celles qui ne le peuvent jamais. Une case noire de la première = « ce houblon porte
cette catégorie comme étiquette, mais son intensité n'a pas été mesurée *pour lui* ».

> ⚠ **Biais connu, non corrigé** (AUDIT.md §D4) : le tri n°1 compte un **nombre absolu** de
> descripteurs recoupés. Or les houblons couverts par BeerMaverick en portent 9,0 en moyenne
> contre 4,7 pour les autres. Sur une sélection de 3 descripteurs, 9 des 10 premiers résultats
> sont des houblons couverts par BeerMaverick. Le classement reflète donc en partie la
> richesse documentaire, pas seulement l'arôme.

---

## 5. Similar hops (Browse)

Cosinus normalisé-par-axe, pondéré spécificité, **puis pénalisé par la couverture** :

```
vecteur :     v_h[a] = (valeur_h[a] / max_h' valeur_h'[a]) × idf(a)
cosinus :     cos    = (v_cible · v_h) / (‖v_cible‖ × ‖v_h‖)
couverture :  cov    = |axes partagés| / |axes de la cible|
similarité :  sim    = cos × cov
```

La pénalité corrige un défaut réel : le cosinus étant invariant d'échelle, un houblon
**partiellement mesuré** mais proportionnellement aligné obtenait un meilleur score qu'un
houblon complètement mesuré (Callista 89,1 % devant Mosaic 88,2 % sur Citra, alors que
Callista n'a que 8 des 10 composés). `cov` est asymétrique, calculée sur les axes de la cible.

Deux couches indépendantes (composition chimique, roue d'arôme) ; quand les deux sont
actives, moyenne des couches ayant **réellement** une donnée pour ce candidat — jamais un 0
fabriqué pour une couche absente.

---

## 6. Ce que l'outil ne prétend pas faire

- **Pas de reconstruction d'un goût par combinaison de houblons.** Tentée (NNLS), mesurée,
  **retirée** : sur les 506 notes réelles aucune ne dépassait 20 % de couverture, et sur les
  notes à un seul composé productible le solveur renvoyait un résidu artificiel de 0 pour
  n'importe quel houblon porteur. Les blends actuels s'appuient sur les associations
  réellement observées en recette, pas sur un solveur.
- **Pas de prédiction de ce que vous sentirez dans le verre.** Tout est mesuré sur le
  *houblon*, pas sur la bière. Rien ne modélise le rendement d'extraction, l'isomérisation, la
  biotransformation par la levure, ni les pertes au procédé.
- **Pas de variabilité récolte à récolte.** Une variété = une fourchette publiée. Deux lots
  réels de la même variété peuvent différer d'un facteur 2 (mesuré sur des lots Cryo vs T90).
- **Pas de mesure de laboratoire pour les relations houblon↔houblon.** Pairings,
  substitutions et statistiques de style viennent d'agrégateurs de recettes publiées
  (BeerMaverick, beer-analytics.com, MMuM) : ce sont des usages observés, pas des mesures.
- **Pas de vocabulaire d'arôme objectif.** Les descripteurs viennent de roues éditoriales et
  de tags de brasseurs. « dank » ou « juicy » n'ont pas de définition analytique.
- **Pas de données fraîches.** FooDB est figée au 2020-04-07. Les crawls producteurs datent de
  leur dernier passage (voir la popover « Database » dans l'app).
- **Licences.** Code MIT ; FooDB et FlavorDB2 sont **non commerciales** (CC BY-NC-SA) ;
  BeerMaverick et hops-comptoir ne publient aucune licence de données — attribution
  systématique, lecture seule, esprit non commercial.
