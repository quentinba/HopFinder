# hopmatch

**Note olfactive → molécules → houblons.** Un outil pour brasseur qui répond à deux
questions concrètes : *quel houblon accorder à un ajout* (yuzu, basilic…), et *peut-on
reproduire un goût avec du houblon seul* ?

> État : squelette fonctionnel, testé (`pytest` vert, 18 tests) sur des données réelles
> de démonstration (3 variétés BarthHaas + 3 Yakima). `ingest_flavornet`, `ingest_foodb`
> et `by-descriptor` tournent réellement contre les sources externes. Il reste
> `crawl_yakima` (scaffold) et la couche seuils FlavorDB2 — voir [Feuille de route](#feuille-de-route).

---

## Table des matières
1. [L'idée en une page](#lidée-en-une-page)
2. [Le principe de conception : les données sont le goulot](#le-principe-de-conception--les-données-sont-le-goulot)
3. [Les bases de données : pourquoi et comment chacune](#les-bases-de-données--pourquoi-et-comment-chacune)
4. [Les deux cas d'usage, en détail](#les-deux-cas-dusage-en-détail)
5. [Architecture technique](#architecture-technique)
6. [Ce qui est mon prior et pas une donnée](#ce-qui-est-mon-prior-et-pas-une-donnée)
7. [Installation & usage](#installation--usage)
8. [Structure du projet](#structure-du-projet)
9. [Feuille de route](#feuille-de-route)
10. [Licences](#licences)

---

## L'idée en une page

Un arôme (yuzu, basilic, mangue) est un ensemble de **molécules volatiles**. Un houblon,
lui, a un **profil d'huile essentielle** (myrcène, linalol, géraniol, thiols…) et une
**roue d'arôme** (descripteurs : agrume, tropical, résineux…). hopmatch relie les deux :

- **Cas A — accorder.** Tu mets un ajout dans ta bière et tu cherches le houblon qui va
  bien avec. Deux modes : *amplifier* (prolonger le caractère de l'ajout) ou *contraster*.
- **Cas B — reproduire.** Tu veux le goût sans l'ajout : hopmatch cherche une **combinaison**
  de houblons qui recompose le profil, et te dit **ce qui restera hors de portée**.

Ces deux cas n'ont **pas le même scoring**, et c'est le point de conception central
(détaillé plus bas).

---

## Le principe de conception : les données sont le goulot

Tentation naturelle : construire un moteur de matching sophistiqué (OAV, cosinus pondéré).
On y a renoncé, pour une raison empirique. Le vrai facteur perceptuel serait l'**OAV**
(Odor Activity Value = concentration ÷ seuil de détection). Or **on n'a pas de
concentrations fiables** : la seule source quantitative (FooDB) est lacunaire (vérifié :
~7 % des composés d'un aliment ont une concentration). Un cosinus-OAV sur des données de
présence produirait donc de la *précision-déchet* : une élégance mathématique posée sur du
vide.

hopmatch fait donc trois choix assumés :

1. **Descripteurs = couche primaire.** Le brasseur pense en « agrume / tropical / dank ».
   Les roues d'arôme (BarthHaas, Yakima) sont des données réelles, robustes, sans besoin de
   concentration. C'est la fondation.
2. **Molécules = couche secondaire**, en similarité *normalisée par composé* (voir
   [méthode](#méthode-de-score-moléculaire-tf-idf)), pas en OAV. Le seuil olfactif sert de
   **prior de puissance** (option `--oav`), pas de mesure.
3. **Honnêteté explicite.** On rapporte toujours la *couverture* et les *molécules
   orphelines* — ce que le houblon ne peut pas faire. C'est souvent l'info la plus utile.

---

## Les bases de données : pourquoi et comment chacune

Le pipeline joint trois mondes — l'**ingrédient** (l'ajout), la **molécule**, le **houblon** —
et chacun a ses sources. Voici, pour chaque base, *pourquoi* on l'utilise, *comment* on y
accède, et *ce qu'elle vaut*.

### Vue d'ensemble

| Base | Monde | Rôle | Accès | Qualité / limite | Licence |
|---|---|---|---|---|---|
| **BarthHaas** | houblon | composition (dont thiols) | HTML servi | propre, producteur | données producteur |
| **Yakima Chief** | houblon | β-pinène, sélinène, roue d'arôme | HTML (SPA) | propre, labo ASBC | données producteur |
| **FooDB** | ingrédient→molécule | composition + concentration | dump bulk | lacunaire, bruitée, figée 2020 | **non commerciale** |
| **Flavornet** | molécule | whitelist odeur-active | HTML statique | curée mais petite/ancienne | académique |
| **FlavorDB2** | molécule | seuils olfactifs | scrape JSON | seuils utiles, présence seule | **CC BY-NC-SA** |
| **PubChem** | molécule | identité chimique (jointure) | API PUG-REST | robuste | domaine public |

### Côté houblon

**BarthHaas** — *source primaire de composition.*
- **Pourquoi.** C'est un producteur majeur qui publie, variété par variété, la composition
  d'huile essentielle sur une médiane de plusieurs récoltes — donc des données propres et
  représentatives. Surtout, c'est la seule source grand public qui donne les **thiols**
  (3-MH, 4-MMP… en µg/kg), déterminants pour les profils tropicaux/agrumes.
- **Comment.** Le site est servi côté serveur (TYPO3, pas de JS bloquant). La page d'index
  liste ~90 variétés énumérables ; chaque fiche a un bloc « Analyses » au format label/valeur
  régulier. On le parse avec `requests` + BeautifulSoup (voir `ingest.crawl_barthhaas`, déjà
  implémenté). Champs : myrcène, humulène, caryophyllène, farnésène, linalol, géraniol,
  cétones, isobutyrate, thiols, huile totale, acides alpha/bêta.
- **Limite.** Pas de β-pinène ni de sélinène (que Yakima donne). D'où la fusion.

**Yakima Chief (YCH)** — *source secondaire, complémentaire.*
- **Pourquoi.** Complète BarthHaas avec le **β-pinène** et le **sélinène**, et fournit une
  **roue d'arôme** (descripteurs sensoriels) exploitable directement pour la couche
  descripteurs. Données issues de leur labo qualité, conformes aux méthodes ASBC.
- **Comment.** Pages `/variety/{slug}`. Les valeurs sont *présentes* dans le HTML rendu, mais
  le front est de type SPA → il faut une extraction DOM ciblée (ou Playwright si un simple
  `requests` ne renvoie qu'un shell JS). C'est le scaffold `ingest.crawl_yakima`.
- **Limite.** Pas de thiols. Complémentarité exacte avec BarthHaas.

> **Fusion.** Une variété reçoit des mesures des deux sources ; hopmatch les stocke toutes
> (schéma EAV) et les *réconcilie à la lecture* (moyenne des milieux de fourchette, provenance
> tracée). Citra finit ainsi avec le β-pinène de Yakima **et** les thiols de BarthHaas.

### Côté ingrédient → molécule

**FooDB** — *colonne vertébrale de la composition des aliments.*
- **Pourquoi.** C'est la base de composition alimentaire la plus complète (28 000+ composés,
  1000+ aliments), reliée à PubChem/HMDB/ChEBI, et surtout la seule qui porte des
  **concentrations** — l'équivalent, côté ingrédient, du « % d'huile » côté houblon. C'est ce
  qui rendrait le pipeline symétrique.
- **Comment.** Dump bulk téléchargeable (CSV/XML), version figée au 2020-04-07. On lit
  `Content.csv` (liens aliment↔composé), joint à `Compound.csv`.
- **Limites — vérifiées sur le dump réel, importantes :**
  - **Lacunaire.** ~14-16 % des liens ont une concentration (confirmé sur l'ensemble du
    dump via `tools/audit_foodb.py`, pas juste un aliment isolé).
  - **Trop large.** Un aliment liste 6000+ composés (longue traîne de traces agrégées). Brut,
    c'est du bruit, pas un profil.
  - **`Compound.csv` a un bug de colonnes décalées sur ce dump (2020-04-07) :** la colonne
    `cas_number` contient en fait des SMILES, le vrai CAS est sous `description` (vérifié :
    0 % de forme CAS plausible dans `cas_number` contre 21,6 % dans `description`, sur 70 477
    lignes). `ingest._resolve_cas_column` détecte la bonne colonne par taux de correspondance
    au format CAS plutôt que de faire confiance au nom de colonne — défensif si un futur dump
    est propre.
  - **Synonymes entre sources.** Un même composé peut porter des noms différents côté
    Flavornet/FooDB et côté houblon (estragole/methyl-chavicol, même CAS 140-67-0 ;
    β-caryophyllène vs caryophyllène). Sans normalisation, la molécule apparaît deux fois
    dans le profil d'une note (double comptage) et devient une **fausse orpheline** côté
    houblon (qui la fournit pourtant, sous son autre nom). `ingest._canonical_compound`
    résout ça via `reference.ALIASES` + un dépréfixage grec (β-/α-/...), en ne renommant que
    vers une forme déjà connue du vocabulaire houblon.
  - **Bruit nutritionnel.** Trier par concentration remonte l'eau, les cendres, les minéraux —
    FooDB mêle nutrition et arôme.
  - **Licence non commerciale.**
- **Rôle réel, à cause de ces limites.** FooDB ne s'ingère pas brut. La recette implémentée
  (`ingest.ingest_foodb`) : (1) **filtrer** chaque aliment via la whitelist odeur-active
  Flavornet (jointure par CAS, pas par nom), (2) prendre la concentration là où elle existe
  *et où l'unité est comparable* (familles mg/100g et mg/kg uniquement — les autres unités
  FooDB, IU/ppb/µM/kcal, ne sont pas des masses et ne sont pas convertibles fiablement malgré
  la colonne `standard_content` qui prétend les normaliser), (3) sinon prior de seuil
  (1/seuil, depuis `molecules`), (4) sinon présence pure — 3 paliers disjoints, jamais mélangés
  entre eux pour éviter une fausse précision. **Fusionne** avec l'amorce littérature existante
  molécule par molécule (ne l'efface pas : FooDB peut manquer des composés-signature qu'elle
  connaît). Seuls 4 des 7 aliments-notes de l'amorce ont une correspondance FooDB propre et
  sans ambiguïté (`reference.NOTE_TO_FOODB`) : kumquat, basilic (Sweet basil), fruit-passion
  (Passion fruit), mangue (Mango). Yuzu est absent de FooDB ; rose n'a que "Rose hip" (faux
  ami, plus acidulé que floral) ; pin-résine n'est pas un aliment. Ces trois restent sur
  l'amorce littérature.
  (Outils : `tools/audit_foodb.py`, `tools/foodb_impact_check.py`.)

**Flavornet** — *le filtre « odeur-active ».*
- **Pourquoi.** C'est précisément ce qui manque à FooDB : une liste de composés **détectés
  au-dessus de leur seuil dans de vrais produits** par GC-olfactométrie. Elle transforme la
  liste de 6000 composés d'un aliment en la poignée qui compte vraiment.
- **Comment.** Une page HTML statique unique, triée par indice de Kovats
  (`d_kovats_ov101.html`, pas de pagination) : 738 lignes (CAS + nom + descripteurs),
  734 CAS uniques une fois les doublons de synonymes fusionnés à la clé. `ingest.ingest_flavornet`
  (implémenté) écrit ça dans la table `flavornet_compounds`, distincte de `molecules`
  (qui reste la couche de matching note→molécule avec seuils).
- **Limite.** Petite et ancienne (~2004). Whitelist, pas source de composition.

**FlavorDB2** — *la couche seuils.*
- **Pourquoi.** Fournit les **seuils olfactifs par molécule**, indispensables comme *prior de
  puissance* (une molécule à seuil très bas compte plus, même en petite quantité).
- **Comment.** Pas d'API ; données en JSON par fiche molécule (à scraper — l'ancien endpoint
  v1 renvoie une 500). 25 595 molécules.
- **Limite cruciale.** Le lien ingrédient→molécule est en **présence/absence** : aucune
  concentration *dans l'ingrédient*. Donc on ne peut pas déduire « le linalol est au-dessus de
  son seuil dans le basilic » — le seuil reste un prior, pas un OAV. Licence CC BY-NC-SA.

### Le liant

**PubChem (PUG-REST)** — *la clé de jointure, pas encore branchée.*
- **Pourquoi.** Les trois mondes n'utilisent pas toujours les mêmes noms (estragole = methyl
  chavicol = 4-allylanisole…). PubChem fournit l'identité chimique canonique (**CID**,
  **InChIKey**) qui permettrait de joindre ingrédient ↔ molécule ↔ houblon sans se faire
  piéger par les synonymes, au-delà de ce qu'un CAS ou une table d'alias manuelle couvrent.
- **État actuel.** La jointure Flavornet↔FooDB implémentée passe par le **CAS** (présent des
  deux côtés), pas par PubChem. Les synonymes restants (nommage différent entre Flavornet/FooDB
  et le vocabulaire houblon — estragole/methyl-chavicol, β-caryophyllène/caryophyllène) sont
  résolus par une petite table d'alias curée (`reference.ALIASES`) + un dépréfixage grec, pas
  par une jointure structurale via PubChem. Ça marche pour le nombre limité de synonymes
  rencontrés jusqu'ici, mais ne passera pas à l'échelle si le vocabulaire s'élargit beaucoup
  (crawl Yakima, plus d'aliments FooDB) — PubChem reste la vraie solution générique, non
  implémentée.
- **Comment (si branché).** API PUG-REST publique, domaine public, robuste.

---

## Les deux cas d'usage, en détail

### Méthode de score moléculaire (TF-IDF)

Brique commune à plusieurs modes. Le piège naïf : sommer les molécules partagées. Problème —
le **myrcène est présent à ~50 % dans presque tous les houblons**, donc il écrase le classement
et on ne fait que remonter « les houblons les plus huileux ». La solution (analogue TF-IDF) :

1. **Quantité** d'une molécule dans un houblon = `(% d'huile / 100) × huile totale`
   (ou valeur brute pour les thiols en µg/kg).
2. **Normalisation par composé** (term frequency) : chaque molécule est ramenée à [0,1] par son
   maximum à travers les houblons. Ainsi « le plus riche en linalol » pèse autant que « le plus
   riche en myrcène ».
3. **Spécificité** (inverse document frequency) : une molécule présente partout (myrcène) est
   peu discriminante et pèse moins ; une molécule rare (thiols, géraniol) caractérise fortement.
4. **Poids de la note** : chaque molécule est pondérée par sa contribution au caractère de l'ajout.
5. Optionnel `--oav` : × prior de seuil (1/seuil). Approximatif, désactivé par défaut.

Score moléculaire = somme de ces contributions, normalisée 0-100.

### Cas A — `amplify` : prolonger un ajout

**Contexte.** L'ajout (le yuzu) est *physiquement dans la bière* — c'est lui qui apporte le
limonène et le citral. Le houblon n'a donc pas à les fabriquer : le « plafond de couverture »
(le fait que le houblon manque de certaines molécules) **ne pénalise pas** ici. On cherche un
houblon qui *prolonge* le caractère.

**Méthode.**
1. Récupérer le profil moléculaire de la note (`aroma_notes` : molécule→poids) et ses
   descripteurs (`note_descriptors`).
2. **Couche moléculaire** : score TF-IDF ci-dessus, sur les molécules que le houblon possède
   réellement. Normalisé 0-1.
3. **Couche descripteurs** : recoupement entre les descripteurs de la note et la roue d'arôme du
   houblon (fraction des descripteurs de la note présents dans le houblon).
4. **Score final** = `w_mol × score_moléculaire + w_desc × score_descripteurs` (0,5 / 0,5 par
   défaut).
5. **Sortie** : houblons classés, avec les molécules qui contribuent le plus, la couverture, et
   les molécules orphelines (dans la note mais absentes du houblon — ici purement informatives).

`hopmatch amplify yuzu` → Citra, Mosaic, Simcoe en tête (linalol + β-pinène + géraniol).

### Cas A — `contrast` : accorder par contraste

**Contexte.** Le contraste **ne se dérive pas d'une similarité moléculaire** — chercher des
molécules partagées, c'est l'amplification. Le contraste, ce sont des profils *différents mais
harmonieux* (un houblon dank/noble sous un ajout agrume vif). Ça ne se calcule pas à partir des
composés communs.

**Méthode.**
1. Récupérer les descripteurs de la note.
2. Pour chacun, chercher ses descripteurs **complémentaires** dans la carte d'affinités
   (`reference.CONTRAST_AFFINITY` : ex. agrume ↔ résineux/boisé/herbacé).
3. Cible = union des descripteurs complémentaires.
4. Classer les houblons selon le nombre de descripteurs-cibles que leur roue d'arôme recoupe.

`hopmatch contrast yuzu` → cible earthy/herbal/resinous/woody → Saazer (noble, herbacé) ressort.

> ⚠️ La carte d'affinités est un **prior heuristique**, pas une donnée sourcée (voir
> [section dédiée](#ce-qui-est-mon-prior-et-pas-une-donnée)). À ancrer sur un corpus de recettes
> ou une référence d'accords (*The Flavor Bible*).

### Cas B — `combine` : reproduire avec une combinaison de houblons

**Contexte.** Ici le houblon doit tout fournir seul : le plafond de couverture **mord pleinement**.
Un seul houblon suffit rarement, mais un **blend** peut s'approcher. La vraie valeur n'est pas
juste « voici le blend » — c'est **« voici le plus proche ET voici ce qui manquera quoi qu'il
arrive »**.

**Méthode (moindres carrés non négatifs, NNLS).**
1. **Molécules couvrables** = molécules de la note qu'au moins un houblon porte.
2. **Matrice A** (molécules couvrables × houblons), chaque case = quantité normalisée par molécule
   (mêmes unités comparables entre lignes).
3. **Cible t** = poids de la note pour ces molécules (normalisés).
4. **Résoudre** `A · w ≈ t` avec `w ≥ 0` (NNLS) → poids non négatifs par houblon.
5. **Parcimonie** : garder les `max_hops` meilleurs (un brasseur ne blende pas 8 variétés) et
   re-résoudre sur ce sous-ensemble.
6. **Sortie** : proportions du blend (normalisées à 100 %), **résidu** (distance à la cible =
   à quel point on approche), et **molécules irréductibles** = orphelines qu'aucune combinaison
   ne peut fournir (limonène, terpinolène…) — la quantification honnête du plafond de couverture.

`hopmatch combine mangue` → blend + « irréductible : terpinolène ».

### Découverte — `by-descriptor` : explorer par vocabulaire

Un troisième mode, orthogonal aux cas A/B : pas de note requise. L'utilisateur choisit un ou
plusieurs descripteurs dans le vocabulaire réel de la base (`hopmatch descriptors`) → l'app
liste les houblons qui les portent, avec leurs descripteurs **et** leurs molécules.

**Grounded**, contrairement à `contrast` : le vocabulaire et les correspondances viennent des
roues d'arôme réelles (`hop_descriptors`, BarthHaas/Yakima), pas de `CONTRAST_AFFINITY` (le
prior heuristique). Ne dépend ni de FooDB ni de `crawl_yakima`.

**Méthode.** Recoupement `hop_descriptors ∩ sélection`. Tri : (1) nombre de descripteurs
recoupés (desc), (2) `total_oil` réconcilié (desc, proxy d'intensité en l'absence d'autre
signal), (3) `variety` (asc, déterminisme en cas d'égalité totale). Les variantes de
descripteurs entre sources (« stone fruit » vs « stonefruit », pluriels…) sont normalisées à
l'ingestion via `reference.DESCRIPTOR_ALIASES`, appliqué dans `ingest._ingest_variety` — pas
dans le parseur brut.

`hopmatch by-descriptor citrus,tropical` → Simcoe, Citra, Mosaic (Saazer, sans aucun des deux,
n'apparaît pas).

---

## Architecture technique

**Base SQLite EAV multi-sources.** `hop_composition(variety, compound, vmin, vmax, unit, source,
confidence, notes)` avec clé `(variety, compound, source)` : deux sources coexistent pour une
variété. La réconciliation se fait **à la lecture** (moyenne des milieux de fourchette), jamais
à l'écriture — rien n'est écrasé, tout est traçable. Les unités mixtes (% d'huile vs µg/kg pour
les thiols) sont gérées par la normalisation par composé (les unités s'annulent au sein d'un
composé).

**Validation / réparation** (`schema.validate_and_repair`). Détecte l'inversion
myrcène/caryophyllène fréquente dans les datasets tiers scrappés (le caryophyllène dépasse
rarement ~15 % : au-delà de 25 %, c'est presque sûrement une valeur de myrcène mal rangée), les
négatifs, les sommes aberrantes. **Dormant sur BarthHaas/Yakima** (propres) — c'est un filet de
sécurité pour l'ingestion de sources sales, pas une valeur active.

**Table `flavornet_compounds`** (`cas` clé primaire, `compound`, `descriptors`). Distincte de
`molecules` : c'est une whitelist « sensoriellement présent » utilisée pour filtrer FooDB à
l'ingestion, pas une couche de matching note→houblon. `ingest_foodb` écrit aussi dans
`molecules` (`INSERT OR IGNORE`) pour les composés qu'elle découvre sans écraser les seuils déjà
connus des 14 entrées curées de `reference.MOLECULES`.

---

## Ce qui est mon prior et pas une donnée

Transparence importante. Une partie du contenu de `reference.py` n'est **pas sourcée** — c'est
ma synthèse de connaissances générales, à traiter comme une amorce à remplacer :

- **`AROMA_NOTES`** (note → molécules + poids) : mes estimations. À remplacer par FooDB filtré.
- **`CONTRAST_AFFINITY`** (carte d'affinités) : mon prior de sagesse culinaire, aucune source. À
  ancrer sur un corpus de recettes ou une référence d'accords.
- Les listes de composés d'impact : connaissance générale, à confirmer via Flavornet/littérature.

À l'inverse, tout ce qui vient d'un **parseur avec source tracée** (composition houblon) est de
la donnée. Règle du projet : ne jamais figer en dur des valeurs de composition — passer par un
parseur et une provenance.

---

## Installation & usage

```bash
git clone <ton-repo> hopmatch && cd hopmatch
pip install -e .            # cœur (numpy, scipy)
pip install -e ".[crawl]"   # + requests, beautifulsoup4 (crawl BarthHaas)
pip install -e ".[foodb]"   # + pandas (audit/ingest FooDB)
pip install -e ".[dev]"     # + pytest
```

```bash
hopmatch build                    # construit aromahops.db depuis data/fixtures
hopmatch list                     # notes et houblons disponibles

hopmatch amplify yuzu             # cas A — prolonger
hopmatch amplify basilic --oav    # + prior de seuil
hopmatch contrast yuzu            # cas A — contraster
hopmatch combine mangue           # cas B — recomposer
hopmatch combine fruit-passion --max-hops 2

hopmatch descriptors              # vocabulaire de descripteurs disponible
hopmatch by-descriptor citrus,tropical   # découverte, sans note requise

hopmatch crawl-barthhaas          # base complète BarthHaas (~90 variétés, réseau)
hopmatch ingest-flavornet         # whitelist odeur-active (~734 composés, réseau)
hopmatch ingest-foodb <dossier_dump_foodb_csv>   # note→molécule filtré (local, gros fichiers)

pytest -q                         # 18 tests
```

---

## Structure du projet

```
src/hopmatch/
  reference.py   amorce note→molécule/descripteur + alias/normalisation + carte d'affinités
                 (⚠️ AROMA_NOTES/CONTRAST_AFFINITY = prior, à remplacer/ancrer)
  parsers.py     parseurs label/valeur BarthHaas & Yakima, descripteurs, unités FooDB
  schema.py      schéma SQLite EAV (+ flavornet_compounds) + validation/réparation
  ingest.py      build fixtures / crawl BarthHaas / ingest_flavornet / ingest_foodb (réel) ;
                 crawl_yakima (scaffold)
  matching.py    load+réconciliation ; amplify / contrast / combine(NNLS) / by_descriptor
  cli.py         CLI
data/fixtures/   pages réelles (démo) : barthhaas/{citra,mosaic,saazer}, yakima/{citra,mosaic,simcoe}
tools/           audit_foodb.py, foodb_impact_check.py
tests/           parsers, validation, réconciliation, modes, non-régression NNLS
docs/            ARCHITECTURE.md, DATA_SOURCES.md, FEATURE_NOTES.md
CLAUDE.md        contexte projet pour Claude Code
```

---

## Feuille de route

Fait : `ingest.ingest_flavornet`, `ingest.ingest_foodb` (jointure par CAS + alias, pas encore
PubChem CID), `by-descriptor`. Reste :

1. **`ingest.crawl_yakima`** — extraction DOM contre le SPA (ou Playwright).
2. **Couche seuils** (FlavorDB2) + **drapeau biotransformation** par souche (géraniol→citronellol,
   précurseurs→thiols — central pour une NEIPA Kveik). Enrichirait aussi les poids `foodb:thr` de
   `ingest_foodb`, aujourd'hui limités aux seuils déjà connus de `reference.MOLECULES`.
3. **Jointure PubChem CID/InChIKey** — remplacerait la table d'alias manuelle
   (`reference.ALIASES`) par une résolution structurale, plus robuste à l'échelle.

---

## Licences

**Code : MIT** (voir `LICENSE`). **Les données ne le sont pas** : FooDB et FlavorDB2 sont **non
commerciales**, TGSC restrictive. Tant que hopmatch reste personnel ou open-source non lucratif,
c'est bon ; une distribution commerciale imposerait de retirer ou renégocier ces sources. Détail
par source dans `docs/DATA_SOURCES.md`.