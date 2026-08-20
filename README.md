# HopFinder

*Nom d'affichage du projet (GUI, GitHub) ; le paquet Python et la commande CLI restent
`hopmatch` (décision utilisateur 2026-08-19 — renommage d'affichage seulement, pas de
renommage mécanique du paquet/CLI/`pyproject.toml`).*

**Note olfactive → molécules → houblons.** Un outil pour brasseur qui répond à une
question concrète : *quel houblon accorder à un ajout* (yuzu, basilic…) — en le
prolongeant, en le contrastant, ou en explorant/comparant directement le catalogue.

> État : `pytest` vert (200 tests). Toutes les sources tournent contre les sites externes :
> `crawl_barthhaas`, `crawl_yakima`, `ingest_flavornet`, `ingest_foodb`, `ingest_flavordb2`,
> `resolve_pubchem_cids`, `ingest_beermaverick` — voir [Feuille de route](#feuille-de-route).

---

## Aperçu

HopFinder relie deux mondes : l'**arôme** — une note comme yuzu, basilic ou mangue, un
ensemble de molécules volatiles et un vocabulaire de descripteurs — et le **houblon** —
son profil d'huile essentielle et sa propre roue d'arôme. Cinq outils, disponibles en GUI
(Streamlit) et pour la plupart en CLI :

| Outil | Question à laquelle il répond |
|---|---|
| **Amplify** | Cet ajout est déjà dans ma bière — quel houblon *prolonge* son caractère ? |
| **Contrast** | Quel houblon *contraste* bien avec cet ajout (accord complémentaire, pas similaire) ? |
| **Compare Hops** | Comment se comparent 2 à 5 houblons précis, côte à côte (roue d'arôme, acides, composition détaillée) ? |
| **By-descriptor** | Quels houblons portent tel(s) descripteur(s) (agrume, tropical, dank…), sans note de départ ? |
| **Browse** | Que sait-on d'un houblon précis — composition, purpose (aromatique/amérisant), associations, roue d'arôme ? |

`Amplify`/`Contrast` proposent aussi des **blends** (1 à 5 houblons), en priorisant les
associations réellement utilisées ensemble en recette plutôt qu'une couverture purement
théorique. Chaque résultat, partout dans l'outil, rapporte sa **couverture** et ce qu'il ne
peut pas faire (molécules orphelines, données manquantes) — jamais un score affiché sans
son contexte de fiabilité.

Les données viennent de sources réelles tracées à la source (BarthHaas, Yakima Chief,
BeerMaverick, FooDB, Flavornet, FlavorDB2, PubChem) — jamais d'une base inventée à la
main. Le détail de chacune, et le raisonnement derrière chaque choix de conception, est
dans la [partie méthodologie](#méthodologie--sources-de-données) plus bas.

**Pour essayer tout de suite** : [Installation & usage](#installation--usage) juste en
dessous suffit à construire une base et lancer l'outil. Le reste de ce document est une
**plongée méthodologique** — comment chaque donnée est obtenue, pourquoi chaque choix de
conception a été fait, quelles limites sont connues — utile pour comprendre ce que les
résultats veulent vraiment dire, pas nécessaire pour simplement essayer l'outil.

---

## Installation & usage

### Installation

```bash
git clone <ton-repo> hopmatch && cd hopmatch
python3 --version           # nécessite 3.10+ — voir la note ci-dessous sinon
python3 -m venv .venv
source .venv/bin/activate
pip install -e .            # cœur (numpy, scipy)
pip install -e ".[crawl]"   # + requests, beautifulsoup4 (crawl BarthHaas/Yakima)
pip install -e ".[foodb]"   # + pandas (audit/ingest FooDB)
pip install -e ".[ui]"      # + streamlit (GUI navigateur)
pip install -e ".[dev]"     # + pytest
```

> Si `python3 --version` affiche moins que 3.10 (fréquent : le `python3` système
> macOS/Linux est souvent plus ancien), installer une version récente séparément
> (`brew install python@3.12` sur macOS, ou pyenv) et créer le venv avec ce binaire
> précis, ex. `/opt/homebrew/opt/python@3.12/bin/python3.12 -m venv .venv`.

Une fois le venv activé (`source .venv/bin/activate`), `hopmatch`, `streamlit` et
`pytest` sont directement sur le `PATH`. Dans un nouveau terminal où il n'est pas
activé, préfixer les commandes par `.venv/bin/` (`.venv/bin/hopmatch`,
`.venv/bin/streamlit run ...`).

### Construire une base

`hopmatch build` construit **seulement la démo** — 3 fiches BarthHaas + 3 fiches
Yakima figées dans `data/fixtures/`, avec citra/mosaic communs aux deux sources :
**4 houblons, 0 note**. `build` ne peuple plus aucune note (il n'y a pas d'amorce
littérature dans ce projet) : `amplify`/`contrast` ont besoin d'`ingest-foodb`
en plus pour avoir des notes à interroger — `by-descriptor`/`browse`/`Compare Hops`
fonctionnent dès `build`.

```bash
hopmatch build                    # démo : 4 houblons
```

Pour une base réelle, lancer les crawls/ingestions réseau — chacun écrit dans la
même base (`aromahops.db` par défaut, pas besoin d'appeler `build` avant : ils
l'initialisent si elle n'existe pas) et fusionne les variétés déjà présentes :

```bash
hopmatch crawl-barthhaas          # ~90 variétés BarthHaas
hopmatch crawl-yakima             # ~152 variétés Yakima Chief (via Algolia) + hop_similar
hopmatch ingest-flavornet         # whitelist odeur-active (~734 composés) — avant les deux suivants
hopmatch resolve-pubchem-cids     # jointure structurale CAS->CID — avant les deux suivants
hopmatch ingest-flavordb2         # seuils olfactifs, bornés à cette whitelist
hopmatch ingest-foodb              # télécharge+extrait le dump FooDB si absent, puis ingère
hopmatch ingest-beermaverick      # pairings/substitutions houblon<->houblon (agrégateur)
```

L'ordre ci-dessus est celui des dépendances réelles entre commandes (`ingest-flavornet`
avant `resolve-pubchem-cids` avant `ingest-flavordb2`/`ingest-foodb`) ; les deux crawls
houblon (`crawl-barthhaas`/`crawl-yakima`) sont indépendants et dans n'importe quel ordre.

`ingest-foodb` n'exige plus de télécharger le dump FooDB à la main : sans argument, il
télécharge et extrait automatiquement `foodb_2020_04_07_csv.tar.gz` (~950 Mo, licence
CC BY-NC-SA non commerciale — voir [Licences](#licences)) dans `data/foodb_2020_04_07_csv/`
s'il n'y est pas déjà (idempotent : ne retélécharge rien au run suivant). `hopmatch
ingest-foodb <dossier>` reste possible pour pointer vers un dump déjà téléchargé
ailleurs. Il ingère par défaut tout `Food.csv` (~1000 aliments, ~510 notes distinctes
après le filtre de distinctivité — voir [FooDB](#côté-ingrédient--molécule)).

### CLI

```bash
hopmatch list                     # notes et houblons disponibles

hopmatch amplify mango                    # prolonger
hopmatch amplify "sweet basil" --oav      # + prior de puissance olfactive
hopmatch amplify mango --descriptors citrus,tropical  # + couche descripteurs (sélection manuelle)
hopmatch amplify-blend mango --descriptors citrus,tropical --max-hops 5  # blends 1-5, priorité pairing réel
hopmatch contrast --descriptors citrus,herbal        # contraster (sélection manuelle)
hopmatch contrast-blend --descriptors citrus,herbal --max-hops 5   # blends 1-5, priorité pairing réel

hopmatch descriptors              # vocabulaire de descripteurs disponible
hopmatch by-descriptor citrus,tropical   # découverte, sans note requise

pytest -q                         # 200 tests (nécessite l'extra [dev])
```

`Compare Hops` (comparer 2 à 5 houblons côte à côte) et `Browse` (consulter un houblon en
détail) n'ont pas d'équivalent CLI — GUI uniquement.

### GUI navigateur

Lecture seule contre une base déjà construite (voir [Construire une base](#construire-une-base)
ci-dessus) :

```bash
streamlit run src/hopmatch/app.py
```

La page d'accueil résume les 5 outils avec un bouton "Open" par outil pour y accéder
directement. Chaque mode (Amplify/Contrast/By-descriptor/Browse/Compare Hops) et ses
options propres (`--oav`, taille de blend, nombre de résultats…) vivent dans la barre
latérale, qui affiche aussi le nombre de houblons/notes/descripteurs chargés et la date
de dernière modification de la base, ainsi qu'un lien vers ce dépôt GitHub. Pour pointer
vers une autre base : `streamlit run src/hopmatch/app.py -- --db chemin.db`.

Le détail de ce que chaque mode affiche (roue d'arôme quantitative, associations
houblon↔houblon, composition détaillée…) et pourquoi il est construit ainsi est décrit
dans [Interface graphique : détails d'implémentation](#interface-graphique--détails-dimplémentation),
plus bas dans la partie méthodologie.

---

# Méthodologie & sources de données

Cette partie explique *comment* HopFinder obtient et traite chaque donnée, et *pourquoi*
chaque choix de conception a été fait — utile pour juger la fiabilité d'un résultat, pas
nécessaire pour simplement utiliser l'outil (voir [Installation & usage](#installation--usage)
ci-dessus).

**Sommaire**
1. [Le principe de conception : les données sont le goulot](#le-principe-de-conception--les-données-sont-le-goulot)
2. [Les bases de données : pourquoi et comment chacune](#les-bases-de-données--pourquoi-et-comment-chacune)
3. [Les modes, en détail](#les-modes-en-détail)
4. [Interface graphique : détails d'implémentation](#interface-graphique--détails-dimplémentation)
5. [Architecture technique](#architecture-technique)
6. [Ce qui est un prior, pas une donnée](#ce-qui-est-un-prior-pas-une-donnée)
7. [Structure du projet](#structure-du-projet)
8. [Feuille de route](#feuille-de-route)
9. [Licences](#licences)

## Le principe de conception : les données sont le goulot

Le vrai facteur perceptuel serait l'**OAV** (Odor Activity Value = concentration ÷ seuil de
détection), et un moteur de matching plus sophistiqué (cosinus pondéré par OAV) serait
tentant. HopFinder y renonce pour une raison empirique : **aucune concentration fiable** n'est
disponible côté ingrédient — la seule source quantitative (FooDB) est lacunaire (14,4 % des
liens compound↔aliment portent une concentration). Un cosinus-OAV sur des données de présence
produirait de la *précision-déchet* : une élégance mathématique posée sur du vide.

HopFinder fait donc trois choix assumés :

1. **Descripteurs = couche primaire.** Le brasseur pense en « agrume / tropical / dank ».
   Les roues d'arôme (BarthHaas, Yakima) sont des données réelles, robustes, sans besoin de
   concentration. C'est la fondation.
2. **Molécules = couche secondaire**, en similarité *normalisée par composé* (voir
   [méthode](#méthode-de-score-moléculaire-tf-idf)), pas en OAV. Le seuil olfactif sert de
   **prior de puissance** (option `--oav`), pas de mesure.
3. **Honnêteté explicite.** Chaque résultat rapporte la *couverture* et les *molécules
   orphelines* — ce que le houblon ne peut pas faire. C'est souvent l'info la plus utile.

> Une quatrième approche — reproduire un goût *sans* ajout, en recomposant le profil par
> combinaison de houblons (NNLS) — a été tentée puis retirée : mesurée sur les 506 notes
> réelles de la base, aucune ne dépassait 20 % de couverture (max observé 12 %, médiane
> 1,3 %). La chimie de l'huile de houblon ne recoupe simplement pas la plupart des arômes
> alimentaires, et sur les notes à un seul composé « producible » (la majorité), le calcul
> dégénère en un système à une seule équation où n'importe quel houblon porteur atteint un
> résidu artificiel de 0 — une fausse confiance sans rapport avec la couverture réelle.
> Décision utilisateur du 2026-08-12, voir l'historique git pour le détail.

---

## Les bases de données : pourquoi et comment chacune

Le pipeline joint trois mondes — l'**ingrédient** (l'ajout), la **molécule**, le **houblon** —
et chacun a ses sources. Pour chaque base : *pourquoi* elle sert, *comment* HopFinder y accède,
et *ce qu'elle vaut*.

### Vue d'ensemble

| Base | Monde | Rôle | Accès | Qualité / limite | Licence |
|---|---|---|---|---|---|
| **BarthHaas** | houblon | composition (dont thiols) | HTML servi | propre, producteur ; pas de descripteurs fiables | données producteur |
| **Yakima Chief** | houblon | β-pinène, sélinène, roue d'arôme (catégorique et quantitative), variétés similaires, purpose | API Algolia (checkpoint devant le HTML) | propre, labo ASBC | données producteur |
| **BeerMaverick** | houblon↔houblon + descripteurs | pairings/substitutions, roue d'arôme (104 termes), purpose | HTML statique | agrégateur, pas une mesure de labo | non publiée |
| **FooDB** | ingrédient→molécule | composition + concentration | dump bulk | lacunaire, bruitée, figée 2020 | **non commerciale** |
| **Flavornet** | molécule | whitelist odeur-active | HTML statique | curée mais petite/ancienne | académique |
| **FlavorDB2** | molécule | seuils olfactifs | scrape HTML (fiche par CID) | seuils utiles, texte libre, présence seule | **CC BY-NC-SA** |
| **PubChem** | molécule | identité chimique (jointure) | API PUG-REST | robuste | domaine public |

### Côté houblon

**BarthHaas** — *source primaire de composition.*
- **Pourquoi.** Producteur majeur qui publie, variété par variété, la composition d'huile
  essentielle sur une médiane de plusieurs récoltes — données propres et représentatives.
  Seule source grand public à donner les **thiols** (3-MH, 4-MMP… en µg/kg), déterminants
  pour les profils tropicaux/agrumes.
- **Comment.** Site servi côté serveur (TYPO3, pas de JS bloquant). La page d'index liste
  ~90 variétés énumérables ; chaque fiche a un bloc « Analyses » au format label/valeur
  régulier, parsé avec `requests` + BeautifulSoup (`ingest.crawl_barthhaas`). Champs :
  myrcène, humulène, caryophyllène, farnésène, linalol, géraniol, cétones, isobutyrate,
  thiols, huile totale, acides alpha/bêta.
- **Limite.** Pas de β-pinène ni de sélinène (que Yakima donne). D'où la fusion.
- **Descripteurs d'arôme non fiables sur ce site.** Vérifié en direct sur plusieurs variétés
  (admiral, tango, dolcita-hops...) : la section « Aroma Profile » n'est plus une liste courte
  séparée par virgules mais un paragraphe descriptif libre. `parsers.parse_descriptors` détecte
  ce cas (présence d'un point final) et renvoie une liste vide plutôt que d'extraire un faux
  descripteur — sans ce garde-fou, la quasi-totalité des variétés récupéraient un descripteur
  bruit (« typical aroma profile », un millésime de récolte comme « 2023 »). BarthHaas reste la
  source de composition ; les descripteurs viennent de Yakima et BeerMaverick (voir plus bas —
  BeerMaverick s'est révélé le vocabulaire le plus riche des deux, signalé en direct par
  l'utilisateur : "dank" n'était tagué que sur 1/203 houblons côté Yakima).
- **Symboles commerciaux (®/™/©) et slugs déposés.** Le générateur de slug de BarthHaas
  translittère ® en "r"/™ en "tm" collé sans séparateur ("Citra®" → `citrar`), ce qui créait
  de faux doublons avec Yakima (`ingest._fix_barthhaas_trademark_slug`, ne déclenche que sur
  un motif exact vérifié pour ne jamais tronquer un vrai nom finissant en "r" comme Saazer).
  Les symboles eux-mêmes sont aussi retirés du nom AFFICHÉ (`parsers.strip_trademark_symbols`,
  appliqué à l'ingestion, pas juste à l'affichage) pour permettre une fusion cross-source fiable
  même quand un symbole diffère entre BarthHaas et Yakima.

**Yakima Chief (YCH)** — *source secondaire, complémentaire.*
- **Pourquoi.** Complète BarthHaas avec le **β-pinène** et le **sélinène**, et fournit deux
  roues d'arôme exploitables pour la couche descripteurs : une liste éditoriale courte
  (`aromas`) et une roue **quantitative** à 15 catégories fixes, 0-100 réelle
  (`aroma_values`/`sensory_values` — voir [Compare Hops et Browse](#interface-graphique--détails-dimplémentation)
  pour son usage GUI). Données issues de leur labo qualité, conformes aux méthodes ASBC.
- **Comment.** Le site place un rempart anti-bot devant le HTML (Vercel Security Checkpoint) :
  une requête HTTP simple ne l'atteint pas, même avec un User-Agent de navigateur. Leur front
  s'appuie sur **Algolia** (recherche instantanée) avec une clé API **publique en lecture
  seule** exposée côté client — design normal pour ce type de clé Algolia « search-only »,
  visible dans le JS de n'importe quel navigateur qui visite le site. `ingest.crawl_yakima`
  interroge cet index Algolia directement en HTTP simple : une requête ramène les ~152
  variétés, chacune avec sa composition **déjà structurée en JSON** (pas de texte à parser,
  contrairement à BarthHaas) et sa roue d'arôme. Fragile par construction : clé et index ne
  sont pas documentés publiquement, et peuvent changer si YCH modifie son frontend.
- **Piège de nommage.** Les variétés déposées ont un slug `-brand` (`citra-brand`,
  `mosaic-brand`…) qui ne fusionnerait jamais avec le slug BarthHaas (`citra`, `mosaic`). Le
  catalogue YCH a aussi de vrais doublons de SKU sans rapport avec les marques (`perle` ET
  `perle-per03` coexistent, `saaz` ET `saaz-saz01`…). `crawl_yakima` déprefixe `-brand`
  uniquement lorsque ça ne rentre pas en collision avec un autre slug du même lot — sinon le
  slug reste tel quel, pour ne jamais fusionner silencieusement deux fiches distinctes. Le mot
  "Brand" présent dans le nom affiché de 50/153 variétés (artefact marketing Yakima, jamais côté
  BarthHaas) est retiré à l'ingestion (`parsers._strip_yakima_brand_suffix`), de même que les
  symboles ®/™/© (voir BarthHaas ci-dessus).
- **Limite.** Pas de thiols. Complémentarité exacte avec BarthHaas.
- **Forme produit.** Chaque variété expose plusieurs analyses selon la forme commerciale
  (`brewing_values[].code`) : pellets T90 (`PEL02`), feuille en balle/entière (`CON02`/`CON04`),
  et des produits dérivés très différents (Cryo Hops® concentré en lupuline, extrait CO2,
  huiles d'essai). `ingest.crawl_yakima` prend **PEL02 en priorité** — la forme réellement
  utilisée en brasserie — avec repli sur les formes feuille (quasi toujours identiques,
  vérifié : seulement 9/148 variétés diffèrent réellement entre les deux) plutôt que sur un
  produit dérivé à composition différente. Chaque niveau de repli est filtré par un contrôle
  de plausibilité (acide alpha ≤30%, aucune variété commerciale connue ne dépasse ~25%) —
  découvert en vérifiant que la variété `admiral` avait une entrée corrompue côté YCH lui-même
  (voir `docs/DATA_SOURCES.md`).
- **Deux crops distincts vs vrais doublons.** Un même nom de variété peut apparaître deux fois
  pour deux raisons différentes, distinguées via `imported_fields.country_code`/`variety_code` :
  soit un VRAI doublon (même variété, même région, juste un slug différent entre BarthHaas et
  Yakima — ex. Challenger, Fuggle — fusionnés à l'ingestion via `ingest.merge_hop_varieties`),
  soit deux CROPS réellement distincts du même cultivar cultivés dans des pays différents (ex.
  Amarillo®, Perle, Saaz, Northern Brewer) — jamais fusionnés (perdrait la distinction de
  terroir réelle), mais désambiguïsés par région dans le nom affiché dès qu'une collision existe
  (`matching._disambiguate_hop_names`, ex. "Northern Brewer (United States)"/"Northern Brewer
  (Germany)"), appliqué une seule fois à la source (`matching.load()`) pour tout le reste de
  l'outil.

> **Fusion.** Une variété peut recevoir des mesures des deux sources ; HopFinder les stocke
> toutes (schéma EAV) et les *réconcilie à la lecture* (moyenne des milieux de fourchette,
> provenance tracée). Citra combine ainsi le β-pinène de Yakima **et** les thiols de BarthHaas.

### Côté ingrédient → molécule

**FooDB** — *colonne vertébrale de la composition des aliments.*
- **Pourquoi.** Base de composition alimentaire la plus complète (28 000+ composés, 1000+
  aliments), reliée à PubChem/HMDB/ChEBI, et seule à porter des **concentrations** —
  l'équivalent, côté ingrédient, du « % d'huile » côté houblon.
- **Comment.** Dump bulk téléchargeable (CSV/XML), version figée au 2020-04-07. Lecture de
  `Content.csv` (liens aliment↔composé), jointe à `Compound.csv`.
- **Limites importantes :**
  - **Lacunaire.** 14,4 % des liens compound↔aliment portent une concentration (mesuré sur
    l'ensemble du dump via `tools/audit_foodb.py`, pas un échantillon isolé).
  - **Trop large.** Un aliment liste 6000+ composés (longue traîne de traces agrégées). Brut,
    c'est du bruit, pas un profil.
  - **`Compound.csv` a ses colonnes décalées sur ce dump (2020-04-07) :** la colonne
    `cas_number` contient des SMILES, le vrai CAS est sous `description` (0 % de forme CAS
    plausible dans `cas_number` contre 21,6 % dans `description`, sur 70 477 lignes).
    `ingest._resolve_cas_column` détecte la bonne colonne par taux de correspondance au
    format CAS plutôt que par le nom de colonne — défensif si un futur dump est propre.
  - **Synonymes entre sources.** Un même composé peut porter des noms différents côté
    Flavornet/FooDB et côté houblon (estragole/methyl-chavicol, même CAS 140-67-0 ;
    β-caryophyllène vs caryophyllène). Sans normalisation, la molécule apparaît deux fois
    dans le profil d'une note (double comptage) et devient une **fausse orpheline** côté
    houblon (qui la fournit pourtant, sous son autre nom). `ingest._canonical_compound`
    résout ça par priorité : identité de CID PubChem (`pubchem_cids`), puis
    `reference.ALIASES` (réduit aux agrégations sans CID propre, ex. « thiols »), puis
    dépréfixage grec (β-/α-/...) en dernier recours.
  - **Bruit nutritionnel.** Trier par concentration remonte l'eau, les cendres, les
    minéraux — FooDB mêle nutrition et arôme.
  - **Licence non commerciale.**
- **Rôle, compte tenu de ces limites.** FooDB ne s'ingère pas brut. `ingest.ingest_foodb`
  applique : (1) **filtrage** de chaque aliment via la whitelist odeur-active Flavornet
  (jointure par CAS, pas par nom), (2) concentration là où elle existe *et où l'unité est
  comparable* (familles mg/100g et mg/kg uniquement — les autres unités FooDB, IU/ppb/µM/kcal,
  ne sont pas des masses et ne sont pas convertibles fiablement malgré la colonne
  `standard_content` qui prétend les normaliser), (3) sinon prior de seuil (1/seuil, depuis
  `flavordb2_thresholds`), (4) sinon présence pure — 3 paliers disjoints, jamais mélangés
  entre eux pour éviter une fausse précision.
- **Seule source de notes du pipeline.** `ingest_foodb` (`all_foods=True` par défaut)
  parcourt tout `Food.csv` (~1000 aliments sur le dump 2020-04-07) et crée une note par
  aliment, nom = celui de FooDB en minuscule — pas de traitement spécial pour un
  sous-ensemble de notes. Une amorce littérature de 7 notes (yuzu, kumquat, basilic, rose,
  fruit-passion, mangue, pin-resine) a existé pendant le développement, puis a été
  **retirée à la demande explicite de l'utilisateur** une fois ce pipeline suffisant — une
  seule source de vérité par note plutôt que deux qui se recouvrent partiellement.
  Conséquence assumée : yuzu, rose et pin-resine n'avaient pas d'équivalent FooDB propre
  (yuzu absent du dump, rose n'a que "Rose hip" — un faux ami plus acidulé que floral —,
  pin-resine n'est pas un aliment) et ont donc disparu avec l'amorce ; aucune ne revient
  tant qu'aucune source réelle ne les couvre. Un paramètre `notes` optionnel et **additif**
  reste disponible pour donner un nom choisi à un aliment sans effacer son nom auto-dérivé
  (les deux coexistent : ex. si on choisit de nommer "Mango" en "mangue", la note "mango"
  reste quand même présente en plus).
- **Filtre de distinctivité.** Un aliment sans AUCUN composé à concentration mesurée est
  écarté. Pourquoi : vérifié sur le dump réel que deux aliments sans rapport (capers/chervil)
  partagent 99,2% de leurs composés listés (5961/6011) — sans concentration, FooDB cite un
  gabarit générique plutôt qu'une composition mesurée pour cet aliment précis, et le poids
  retombe sur la table de seuils globale, identique entre aliments sans lien. Sur un run réel :
  345 des 847 candidats avec ≥1 composé whitelisté écartés (992 aliments au total, 141 sans
  aucun composé whitelisté, **~510 notes distinctes conservées**).
- **Généraliser les descripteurs a été essayé et abandonné.** Agréger les descripteurs
  Flavornet des molécules d'une note (pondéré, puis pondéré par IDF, puis restreint aux seuls
  composés distinctifs) reproduit systématiquement la même dégénérescence : soit les notes
  convergent vers les mêmes mots génériques, soit le profil devient vide dès qu'on se limite
  aux composés vraiment food-specific. `note_descriptors` reste donc VIDE par défaut pour
  toute note — `amplify` fonctionne en scoring molécules-seules pour toutes les
  notes désormais ; `contrast` (voir plus bas) est généralisé autrement, par sélection
  manuelle de descripteurs plutôt que par auto-dérivation.
  (Outils : `tools/audit_foodb.py`, `tools/foodb_impact_check.py`.)

**Flavornet** — *le filtre « odeur-active ».*
- **Pourquoi.** Ce qui manque à FooDB : une liste de composés **détectés au-dessus de leur
  seuil dans de vrais produits** par GC-olfactométrie. Elle réduit la liste de 6000 composés
  d'un aliment à la poignée qui compte vraiment.
- **Comment.** Une page HTML statique unique, triée par indice de Kovats
  (`d_kovats_ov101.html`, pas de pagination) : 738 lignes (CAS + nom + descripteurs), 734 CAS
  uniques une fois les doublons de synonymes fusionnés à la clé. `ingest.ingest_flavornet`
  écrit ça dans la table `flavornet_compounds`, distincte de `molecules` (couche de matching
  note→molécule avec seuils).
- **Limite.** Petite et ancienne (~2004). Whitelist, pas source de composition.

**FlavorDB2** — *la couche seuils.*
- **Pourquoi.** Fournit les **seuils olfactifs par molécule**, indispensables comme *prior de
  puissance* (une molécule à seuil très bas compte plus, même en petite quantité).
- **Comment.** Pas d'API ni de dump bulk pour les seuils (l'unique JSON bulk du site est un
  graphe de co-occurrence ingrédient↔ingrédient, sans rapport). Fiche détail AJAX
  (`/molecules_details?id=<pubchem_cid>`) — accessible directement par CID une fois résolu via
  `pubchem_cids`, avec repli sur la recherche par nom sinon. La fiche contient le(s) CAS et un
  champ **texte libre** « Aroma threshold values » (ex. « 4 to 10 ppb », « Detection at 64 to
  90 ppb ») — ce champ contient parfois autre chose qu'un seuil : la fiche du myrcène y liste
  *« Aroma characteristics at 10%; terpy, herbaceous... »*, une composition dans un extrait
  aromatique, pas un seuil de détection. `parsers.parse_flavordb2_threshold` ne fait confiance
  qu'à un nombre **directement accolé à une unité reconnue** (ppb/ppm/ppt) ; un pourcentage ou
  un texte sans unité renvoie `None`, jamais une valeur devinée.
- **Limite cruciale.** Le lien ingrédient→molécule est en **présence/absence** : aucune
  concentration *dans l'ingrédient*. Le seuil reste donc un prior, pas un OAV. Licence
  CC BY-NC-SA. `ingest.ingest_flavordb2` se borne aux ~734 composés de la whitelist Flavornet
  (pas les 25 595 molécules du site — hors du périmètre utile à HopFinder, et inutilement lourd
  pour leur serveur), et écrit dans `flavordb2_thresholds`, jamais dans
  `molecules`/`reference.MOLECULES`.

### Flavornet + FlavorDB2 : deux questions différentes sur la même molécule

Les deux sources parlent de la **molécule elle-même**, jamais d'un aliment précis
(contrairement à FooDB) — mais elles répondent chacune à une question différente :

| Source | Question | Réponse type |
|---|---|---|
| Flavornet | Cette molécule sent-elle quelque chose, tout court ? | binaire + descriptif : « linalol : oui, floral/agrume » |
| FlavorDB2 | À partir de quelle quantité devient-elle perceptible ? | quantitatif : « linalol : perceptible dès 6 ppb » |

Flavornet sert à **filtrer** (garder les composés FooDB qui sentent quelque chose, jeter le
reste). FlavorDB2 sert à **pondérer** ce qui reste (une molécule à seuil très bas, comme les
thiols à ~0,06 ppb, compte plus fort qu'une molécule à seuil élevé, même sans connaître sa
concentration exacte dans l'aliment). Deux tables séparées, jamais fusionnées à l'ingestion :
`flavornet_compounds(cas, compound, descriptors)` et
`flavordb2_thresholds(cas, compound, threshold_ppb)` — copies fidèles de leur source, sans
nettoyage. `ingest_foodb` les lit directement, jamais via `molecules`.

**Règle explicite : aucun repli sur une liste codée en dur.** `reference.MOLECULES` contient
14 molécules avec seuil saisies à la main depuis la littérature, encore utilisées par
l'option `--oav` (indépendante du pipeline d'ingestion) et par la résolution CID de
`_canonical_compound`. Le pipeline d'ingestion (FooDB/Flavornet/FlavorDB2) ne s'appuie
**jamais** dessus comme repli silencieux : si
`flavordb2_thresholds` ne connaît pas une molécule, elle reste sans seuil (palier
« présence »), point. Mélanger un seuil sourcé (FlavorDB2) et un seuil deviné/manuel dans le
même calcul serait exactement le genre de précision-déchet que le projet évite ailleurs (pas
d'OAV, pas de cosinus pseudo-OAV) — et rendrait impossible de savoir, en regardant un
résultat, si un poids vient d'une vraie source ou d'une estimation maison.

### Le liant

**PubChem (PUG-REST)** — *le CID comme identité chimique de référence.*
- **Pourquoi.** Les trois mondes n'utilisent pas toujours les mêmes noms (estragole = methyl
  chavicol = 4-allylanisole…). PubChem fournit l'identité chimique canonique (**CID**) qui
  permet de reconnaître deux noms comme la même molécule sans dépendre des synonymes —
  au-delà de ce qu'une table d'alias manuelle peut couvrir.
- **Comment.** `ingest.resolve_pubchem_cids` résout le CID de chaque composé de la whitelist
  Flavornet via l'endpoint PUG-REST `/compound/name/{cas}/cids/JSON` (qui accepte un CAS comme
  synonyme), stocké dans `pubchem_cids(cas, cid)`. Le CAS de l'estragole (140-67-0) résout au
  CID 8815, identique au CID déjà connu de *methyl-chavicol* dans `reference.MOLECULES` — la
  fusion de synonymes devient un fait chimique, pas une supposition de nommage.
- **Repli sur le nom quand le CAS seul ne suffit pas.** Flavornet ne fournit ni InChIKey ni
  SMILES — seule variante disponible en plus du CAS : le nom du composé lui-même
  (`parsers.pubchem_name_fallbacks`), avec deux normalisations déterministes vérifiées sur les
  échecs d'un run réel : lettre grecque épelée (`δ-cadinol` ne résout qu'en `delta-cadinol`,
  PubChem n'indexant pas le symbole grec comme synonyme) et préfixe stéréochimique retiré
  (`(r)-linden ether` ne résout qu'en `linden ether`). Pas de recherche floue au-delà de ces
  deux règles : mieux vaut un composé sans CID que le mauvais CID.
- **Deux usages concrets.**
  1. `ingest._canonical_compound` fusionne un synonyme Flavornet/FooDB avec le vocabulaire
     houblon par identité de CID en priorité ; la table d'alias manuelle (`reference.ALIASES`)
     ne garde que les *agrégations* sans CID propre (« thiols » regroupe plusieurs molécules
     mesurées ensemble côté houblon — pas un synonyme de nommage, un CID ne peut pas trancher
     ça). Le dépréfixage grec (β-caryophyllène → caryophyllène) reste un filet pour les CAS
     non résolus.
  2. `ingest_flavordb2` va directement à `/molecules_details?id=<cid>` (l'endpoint natif de
     FlavorDB2) quand le CID est connu, au lieu de chercher par nom exact.
- **Limite assumée.** Résolution par CAS uniquement (pas encore InChIKey), et bornée aux ~734
  composés de la whitelist Flavornet — cohérent avec le reste du pipeline. Respecte la limite
  d'usage PubChem (5 requêtes/s).

### BeerMaverick et le purpose (aromatique / amérisant)

**BeerMaverick** — *agrégateur d'usage réel, houblon↔houblon.*
- **Pourquoi.** BarthHaas/Yakima ne donnent aucune association houblon↔houblon ni de
  classement par usage. BeerMaverick, un agrégateur qui analyse des recettes publiées et des
  choix éditoriaux de brasseurs expérimentés (**pas** une mesure de labo — affiché avec cette
  réserve partout où c'est montré), comble ce manque : associations fréquentes en recette
  (`hop_pairings`), substitutions suggérées (`hop_substitutions`), un vocabulaire de
  descripteurs bien plus riche et sélectif que Yakima seul (104 termes au total une fois
  fusionné, ex. "dank" correctement présent sur 6 houblons contre 1 seul côté Yakima), et le
  **purpose** (aromatic/bittering/both — la seule des sources à classer un houblon par usage).
- **Comment.** HTML statique servi normalement par chaque page `beermaverick.com/hop/{slug}/`
  (`robots.txt` ouvert, sitemap public). Réconciliation par nom normalisé
  (`ingest._resolve_hop_variety`, tolère ®/™/« Brand »/« NZ Hops »...) : 143/203 variétés du
  catalogue ont une page BeerMaverick correspondante.
- **Purpose inféré en repli.** Pour les variétés sans purpose BeerMaverick réel, l'acide alpha
  moyen sert de repli (`matching.infer_purpose_from_alpha_acid`) : seuil de 7,0% **mesuré**
  (scan de seuils sur les 142 houblons ayant à la fois un purpose réel et un acide alpha connu,
  78% d'accord avec BeerMaverick) — toujours préfixé "Inferred:" dans la GUI, jamais confondu
  avec une donnée mesurée, et jamais utilisé pour structurer les blends (voir plus bas).

---

## Les modes, en détail

### Méthode de score moléculaire (TF-IDF)

Brique commune à plusieurs modes. Le piège naïf : sommer les molécules partagées. Problème —
le **myrcène est présent à ~50 % dans presque tous les houblons**, donc il écrase le classement
et ne fait remonter que « les houblons les plus huileux ». La solution (analogue TF-IDF) :

1. **Quantité** d'une molécule dans un houblon = `(% d'huile / 100) × huile totale`
   (ou valeur brute pour les thiols en µg/kg).
2. **Normalisation par composé** (term frequency) : chaque molécule est ramenée à [0,1] par son
   maximum à travers les houblons. Ainsi « le plus riche en linalol » pèse autant que « le plus
   riche en myrcène ».
3. **Spécificité** (inverse document frequency) : une molécule présente partout (myrcène) est
   peu discriminante et pèse moins ; une molécule rare (thiols, géraniol) caractérise fortement.
4. **Poids de la note** : chaque molécule est pondérée par sa contribution au caractère de l'ajout.
5. Optionnel `--oav` : × prior de seuil (1/seuil). Approximatif, désactivé par défaut en CLI
   (activé par défaut en GUI, un effet réel mesuré, voir plus bas).

Score moléculaire = somme de ces contributions, normalisée 0-100.

### `amplify` : prolonger un ajout

**Contexte.** L'ajout (le yuzu) est *physiquement dans la bière* — c'est lui qui apporte le
limonène et le citral. Le houblon n'a donc pas à les fabriquer : le « plafond de couverture »
(le fait que le houblon manque de certaines molécules) **ne pénalise pas** ici. L'objectif est
un houblon qui *prolonge* le caractère.

**Méthode.**
1. Récupérer le profil moléculaire de la note (`aroma_notes` : molécule→poids) et ses
   descripteurs (`note_descriptors` — vide par défaut pour toute note, voir juste en dessous).
2. **Couche moléculaire** : score TF-IDF ci-dessus, sur les molécules que le houblon possède
   réellement. Normalisé 0-1.
3. **Couche descripteurs** : recoupement entre les descripteurs de la note et la roue d'arôme du
   houblon (fraction des descripteurs de la note présents dans le houblon).
4. **Score final** = `w_mol × score_moléculaire + w_desc × score_descripteurs` (0,5 / 0,5 par
   défaut) — sauf si la note n'a aucun descripteur (`note_descriptors` vide, le cas par défaut
   pour toute note) : `w_mol=1` automatiquement plutôt que de plafonner silencieusement le
   score à `w_mol × 100` par défaut.
5. **Sortie** : houblons classés, avec les molécules qui contribuent le plus, la couverture, et
   les molécules orphelines (dans la note mais absentes du houblon — ici purement informatives).

**Activer la couche descripteurs.** `note_descriptors` étant vide par défaut, `amplify` accepte
aussi `descriptors=[...]` (comme `contrast`) : `hopmatch amplify mango --descriptors citrus,tropical`
sélectionne à la main les descripteurs de la note sur le vocabulaire réel `hop_descriptors`,
éphémère (ne persiste rien) — le seul moyen d'activer cette couche puisqu'aucune source ne
fournit ça automatiquement (voir « pourquoi la sélection manuelle » sous `contrast`).

`hopmatch amplify mango` → houblons classés par recoupement molécules/descripteurs avec le
profil FooDB de "mango" (myrcène, terpinolène...).

**Avertissement couverture moléculaire faible.** Signalé en direct par l'utilisateur (test de
"strawberry") : sans descripteurs, la couche moléculaire seule dégénère exactement comme
`combine()` (voir l'encadré plus haut) — 163/506 notes réelles n'ont QUE le géraniol comme
molécule productible, et le score se réduit alors à un simple tri par quantité brute de
géraniol, sans rapport avec la note. Mesuré : Talus® et Ekuanot® (les 2 houblons
les plus riches en géraniol de la base) raflent #1 sur 44 % de toutes les notes classées quand
aucun descripteur n'est fourni. La couche descripteurs corrige ça concrètement quand elle est
alimentée (vérifié : Talus tombe de #1 à #6 sur "strawberry" avec `--descriptors fruity,berry`)
— `amplify` affiche donc désormais un avertissement (`ATTENTION` en CLI, `st.warning` en GUI)
dès que la couverture moléculaire passe sous 20 % (`matching.LOW_COVERAGE_WARNING_THRESHOLD`),
pour encourager explicitement l'ajout du plus de descripteurs possible.

**`--oav` en pratique.** Effet réel mesuré, pas négligeable : change le classement complet sur
~18% des notes et le houblon #1 sur ~15% (échantillon de 40 notes). Activé par défaut en GUI
(décision utilisateur), reste optionnel en CLI (`--oav`).

**Proposer un blend.** `matching.amplify_blend` (CLI : `hopmatch amplify-blend`) — équivalent de
`contrast_blend` ci-dessous pour `amplify`, même mécanisme partagé (`_pairing_grown_blends`,
priorité à la fréquence réelle de pairing BeerMaverick). La cible du blend est le
**descripteur** propre de la note (comme `contrast_blend`), jamais une reconstruction
moléculaire — **pas de NNLS ici non plus** : ce serait recréer `combine()`, déjà retiré (voir
l'encadré plus haut). Le score moléculaire d'`amplify` sert seulement à classer les candidats,
jamais à piloter la composition du blend. Nécessite des descripteurs pour la note (sinon rien
à couvrir — `has_descriptors: False`, blend vide, pas d'erreur).

### `contrast` : accorder par contraste

**Contexte.** Le contraste **ne se dérive pas d'une similarité moléculaire** — chercher des
molécules partagées, c'est l'amplification. Le contraste, ce sont des profils *différents mais
harmonieux* (un houblon dank/noble sous un ajout agrume vif) : ça ne se calcule pas à partir des
composés communs.

**Méthode.**
1. Récupérer les descripteurs de la note — **choisis à la main par l'utilisateur**
   (`--descriptors`, vocabulaire réel `hop_descriptors`, comme `by-descriptor`), ou, si
   `note_descriptors` a été peuplé pour une note précise (voir « Pourquoi la sélection
   manuelle » ci-dessous), via cette note.
2. Pour chacun, chercher ses descripteurs **complémentaires** dans la carte d'affinités
   (`reference.CONTRAST_AFFINITY` : ex. agrume ↔ résineux/boisé/herbacé) — cette cible
   PROPOSÉE reste modifiable : la GUI la pré-coche mais laisse l'utilisateur décocher/ajouter
   librement (utile quand la cible auto-calculée est trop large — ex. ne garder que "spicy"
   pour retrouver un houblon noble comme Saaz, noyé sous des houblons dank/resinous plus
   nombreux).
3. Cible = union des descripteurs complémentaires (retenus).
4. Classer les houblons selon le nombre de descripteurs-cibles que leur roue d'arôme recoupe,
   avec un filtre optionnel par **purpose** (aromatique/amérisant, pré-coché sur les deux).

`hopmatch contrast --descriptors citrus,floral` → cible earthy/herbal/resinous/woody/spicy →
les houblons noble/herbacés ressortent.

**Vocabulaire de descripteurs élargi (38 → 104 termes).** Signalé en direct par l'utilisateur :
`contrast --descriptors tropical` ciblait "dank" (via `CONTRAST_AFFINITY`) mais quasiment aucun
houblon ne le couvrait. Vérifié en direct sur l'API Algolia Yakima : "Dank" n'y est tagué que
sur 1/203 houblons de toute la base (CTZ), alors même que Chinook/Columbus (classiquement
"dank" chez les brasseurs) n'ont pas ce tag chez Yakima — leur champ `aromas` est une liste
courte éditoriale, pas exhaustive. BeerMaverick expose un vocabulaire bien plus riche et
correctement sélectif (bloc `#pine #dank #cannabis...` par page, 131 tags distincts sur 142
pages) : Chinook/Columbus y sont bien tagués "dank", Mosaic/Simcoe non — cohérent avec l'usage
réel. `ingest.ingest_beermaverick` écrit désormais ces tags dans `hop_descriptors`
(source='beermaverick', filtrés/normalisés — voir `ingest._normalize_beermaverick_tag`) :
vocabulaire réel passé de 38 à 104 descripteurs, "dank" couvert par 6 houblons au lieu d'1,
`contrast --descriptors tropical` renvoie maintenant Chinook à 100% (dank+resinous+spicy).

**Pourquoi la sélection manuelle (`--descriptors`) est le chemin normal, pas un `note`
curé.** `contrast` par `note` exige que `note_descriptors` soit déjà peuplé pour cette
note-là — vide par défaut pour toutes les notes, puisqu'il n'y a plus d'amorce littérature
dans ce projet (retirée à la demande explicite de l'utilisateur, voir la section FooDB
plus haut). Dériver automatiquement des descripteurs depuis FooDB a aussi été tenté
(agrégation pondérée, puis pondérée par IDF, puis restreinte aux composés à concentration
réelle) et rejeté : ça reproduit la même dégénérescence documentée dans la section FooDB
plus haut, pas un vrai signal par note. `matching.contrast(descriptors=[...])` est donc le
chemin normal : l'utilisateur décrit lui-même sa note avec le vocabulaire réel de la roue
d'arôme — fonctionne pour n'importe quelle note sans rien inventer côté données, et sans
note requise du tout.

**Tri déterministe et transparence sur la troncature.** Sur une cible de 3-4 descripteurs, le
score (`100 × recoupés / cible`) ne prend que 3-4 valeurs possibles : des égalités massives
entre houblons sont la norme, pas l'exception (signalé en direct : Saaz invisible même au
plafond maximum de résultats sur "tropical"/"mango"). Résolu par un tri secondaire déterministe
(`total_oil` réconcilié desc, puis `variety` asc) et par un champ `total_matches` qui permet à
la GUI/CLI d'annoncer explicitement « showing N of M » plutôt que de tronquer en silence — même
traitement appliqué à `by-descriptor` (voir plus bas).

**Proposer un blend.** `matching.contrast_blend` (CLI : `hopmatch contrast-blend`) propose
**plusieurs tailles de blend (1 à 5)**, pas un seul blend "optimal" — l'utilisateur a jugé
l'ancienne version (couverture ensembliste gloutonne pure) peu utile : rien ne garantissait que
les houblons combinés soient réellement utilisés ensemble. Le houblon de taille 1 est choisi
**par l'utilisateur** (la GUI propose un sélecteur) plutôt qu'imposé — le score étant souvent
homogène (plusieurs houblons ex-aequo "meilleur candidat"), le classement seul ne désigne pas
un choix évident. À partir de là, si le purpose du houblon de base est connu, la taille 2
garantit explicitement un houblon du rôle opposé (au moins 1 aromatique + 1 amérisant), puis la
croissance se restreint aux houblons aromatiques ; à chaque taille >1, le houblon choisi
mélange **pertinence ET fréquence RÉELLE de pairing** (BeerMaverick, `hop_pairings`, restreint
au top-10 des partenaires d'un houblon déjà dans le blend) — jamais l'un puis l'autre en
cascade. Repli explicite sur la pertinence/couverture pure quand aucune fréquence réelle
n'existe (36/203 houblons seulement ont une donnée BeerMaverick, mesuré) — jamais un blend plus
petit que possible par manque de données, mais chaque houblon signale sa provenance (`via`).
Ne s'arrête pas dès couverture complète (voir un blend à 5 reste utile même quand 1 houblon
couvre déjà toute la cible). Toujours pas de NNLS (le contraste reste non-moléculaire par
design). Mécanisme partagé (`matching._pairing_grown_blends`) avec `amplify_blend` ci-dessus.

> ⚠️ La carte d'affinités est un **prior heuristique**, pas une donnée sourcée (voir
> [Ce qui est un prior, pas une donnée](#ce-qui-est-un-prior-pas-une-donnée)). À ancrer sur un
> corpus de recettes ou une référence d'accords (*The Flavor Bible*).

### Option `--biotransform` — implémentée puis retirée

L'option existait pour rediriger une molécule demandée par la note vers son composé
précurseur mesuré côté houblon (géraniol → citronellol, linalol → alpha-terpinéol),
sur l'hypothèse d'une fermentation levure standard. La science sourcée derrière
restait solide (King & Dickinson 2003, corroborée par Michel et al. 2019), mais
**l'intégration avait un vrai bug de double comptage**, retiré le 2026-08-12
(décision utilisateur, vérifié en direct) : `hop_compound(m, biotransform=True)`
redirigeait la molécule demandée vers son précurseur sans vérifier si ce précurseur
était déjà, séparément, une entrée du même profil de note. Sur les **29 notes
réelles** qui demandent du citronellol, **les 29** demandent aussi du géraniol
(chevauchement total, vérifié) — la même mesure de géraniol d'un houblon comptait
donc deux fois dans le score (une fois comme « géraniol », une fois redirigée comme
« citronellol »), gonflant le classement sans réelle justification (vérifié : change
le houblon n°1 sur plusieurs notes réelles, ex. "coriander"). Corriger le double
comptage à la racine aurait ajouté de la complexité à une hypothèse déjà étroite
(une seule souche « standard », non vérifiable par HopFinder) pour un bénéfice
marginal — voir `reference.py` pour le détail complet et le raisonnement pour ne
pas la réintroduire sans corriger le double comptage.

### Découverte — `by-descriptor` : explorer par vocabulaire

Un mode à part, orthogonal à `amplify`/`contrast` : pas de note requise. L'utilisateur choisit un ou
plusieurs descripteurs dans le vocabulaire réel de la base (`hopmatch descriptors`) → l'app
liste les houblons qui les portent, avec leurs descripteurs **et** leurs molécules.

**Grounded**, contrairement à `contrast` : le vocabulaire et les correspondances viennent des
roues d'arôme réelles (`hop_descriptors`, BarthHaas/Yakima/BeerMaverick), pas de
`CONTRAST_AFFINITY` (le prior heuristique). Ne dépend ni de FooDB ni de `crawl_yakima`.

**Méthode, à deux paliers.** (1) **Catégorique**, prioritaire : nombre de descripteurs texte
recoupés (desc) — le filtre ET le tri principal ; un houblon doit recouper au moins un
descripteur choisi pour apparaître. (2) **Quantitatif**, départage seulement à l'intérieur d'un
même palier catégorique : intensité moyenne mesurée (`hop_aroma_intensity`, Yakima uniquement,
0-100 réel, voir la roue d'arôme quantitative plus bas) sur les descripteurs de la roue choisis
en plus — jamais un critère de présence/absence, jamais une moyenne comptant un descripteur
manquant comme 0. (3) `total_oil` réconcilié desc puis `variety` asc en dernier recours
(déterminisme total, même tri secondaire que `contrast`). En GUI, la roue quantitative (15
catégories fixes) est proposée comme des pills à cocher séparément du texte libre : si aucun
descripteur texte n'est choisi, elle sert aussi de filtre (repli), sinon elle ne fait plus que
noter les résultats déjà filtrés par le texte.

Les variantes de descripteurs entre sources (« stone fruit » vs « stonefruit », pluriels…) sont
normalisées à l'ingestion via `reference.DESCRIPTOR_ALIASES`, appliqué dans
`ingest._ingest_variety` — pas dans le parseur brut.

`hopmatch by-descriptor citrus,tropical` → Simcoe, Citra, Mosaic (Saazer, sans aucun des deux,
n'apparaît pas).

**GUI uniquement** : dès que ≥2 houblons recoupent la sélection, une heatmap houblon ×
descripteur compare visuellement leurs profils complets — pas seulement les descripteurs
recherchés —, scindée en deux grilles (descripteurs de la roue quantitative, shadés par
intensité mesurée ; autres descripteurs, catégoriques uniquement, jamais de nuance possible).
Radar écarté volontairement pour CE cas précis (voir `docs/BACKLOG.md#T4`) : les descripteurs
d'un houblon forment ici un ensemble binaire, pas une quantité — un radar déformerait par
l'aire sans gain de lisibilité (à distinguer du radar utilisé pour la roue d'arôme
*quantitative*, où l'aire a un sens — voir plus bas).

---

## Interface graphique : détails d'implémentation

Cette section documente les choix propres à la GUI Streamlit (`app.py`) qui n'ont pas
d'équivalent CLI — utile pour comprendre ce qu'affiche chaque mode et pourquoi, pas nécessaire
pour simplement s'en servir (voir [GUI navigateur](#gui-navigateur) pour le lancement).

**Page d'accueil.** Résume les 5 outils (carte avec icône/tagline/description) avec un bouton
"Open" par outil pour y accéder directement — bascule le mode via une clé de relais
(`st.session_state["_next_mode"]`, consommée en tout début de `main()` avant l'instanciation du
widget radio ; Streamlit interdit de modifier `session_state["mode"]` une fois ce widget déjà
créé dans le même run).

**`browse` — consulter un houblon.** Sans équivalent CLI. Recherche par nom/variété, puis pour
le houblon choisi : purpose (aromatique/amérisant/les deux, ou "Inferred: ..." en repli, voir
BeerMaverick plus haut) affiché en information principale ; alpha/beta acides, co-humulone
(Yakima uniquement), huile totale en `st.metric` ; descripteurs ; composition détaillée triée
par valeur ; et, pour les variétés couvertes par la roue quantitative Yakima (94/151, voir
`docs/DATA_SOURCES.md`), un radar/spider chart sur 15 axes fixes — intensité 0-100 réelle,
**pas** une simple présence/absence (contrairement à la heatmap de `by-descriptor` ci-dessus,
ce radar-ci porte une vraie quantité par axe, d'où le choix justifié d'un radar plutôt qu'une
grille). Chaque label d'axe affiche sa définition au survol (tooltip Vega-Lite natif), sourcée
sur le "Hop Sensory Ballot" officiel de Yakima Chief — utile car trois catégories voisines
(grassy/herbal/vegetal) sont facilement perçues comme synonymes alors qu'elles désignent des
notes réellement différentes (herbe fraîche coupée / thé-menthe-romarin / légume, ce dernier
étant plutôt un signal de prudence en brassage). `browse` affiche enfin trois associations
houblon↔houblon, chacune étiquetée avec sa propre source — trois questions différentes, jamais
présentées comme interchangeables : **Variétés similaires** (Yakima, curé par YCH) ;
**Associations fréquentes en recette** et **Substitutions suggérées** (BeerMaverick — un
agrégateur, pas une mesure de labo).

**`compare` — comparer 2 à 5 houblons côte à côte.** Sans équivalent CLI, inspiré de l'outil de
comparaison de beermaverick.com (fonctionnalité de référence, pas le design). Une couleur fixe
et cohérente par houblon sur les trois graphiques : le même radar d'arôme quantitatif que
`browse` mais superposé pour plusieurs houblons à la fois (surlignage au survol d'un houblon —
trait plus épais et opacité pleine — pour le distinguer quand plusieurs polygones se
chevauchent ; note technique : Vega-Lite ne permet pas de passer un tracé visuellement devant
les autres de façon réactive, le contraste fort en tient lieu) ; un barplot à double axe pour
alpha/beta acides + co-humulone (converti en % absolu du houblon, pas en % des acides alpha) et
huile totale ; puis un second barplot à double axe pour la composition détaillée (% d'huile
d'un côté, thiols en µg/kg de l'autre — deux unités incompatibles sur le même graphique sinon).

**`amplify`/`contrast`/`by-descriptor`.** Chaque ligne de résultat a un expander de détail
directement sur place (composition, descripteurs, roue d'arôme si disponible) plutôt qu'un
bouton de navigation vers `browse` — une version précédente perdait le contexte de la page en
cours en y renvoyant. La taille de blend proposée est toujours fixée à 5 (pas de curseur) ; les
tailles de blend sont chacune affichées dans leur propre encadré visuel pour rester lisibles
côte à côte.

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
négatifs, les sommes aberrantes. **Dormant sur BarthHaas/Yakima** (propres) — un filet de
sécurité pour l'ingestion de sources sales, pas une valeur active.

**Table `flavornet_compounds`** (`cas` clé primaire, `compound`, `descriptors`). Distincte de
`molecules` : une whitelist « sensoriellement présent » utilisée pour filtrer FooDB à
l'ingestion, pas une couche de matching note→houblon. `ingest_foodb` écrit aussi dans
`molecules` (`INSERT OR IGNORE`) pour les composés qu'elle découvre, sans écraser les seuils
déjà connus des 14 entrées curées de `reference.MOLECULES`.

**Table `pubchem_cids`** (`cas`, `cid`). Résolution structurale CAS→CID, bornée à la whitelist
Flavornet. Consommée par `ingest._canonical_compound` (fusion de synonymes par identité de CID)
et `ingest_flavordb2` (accès direct à la fiche par CID).

**Table `hop_aroma_intensity`** (`variety`, `descriptor`, `intensity`, `source`). Roue d'arôme
QUANTITATIVE (0-100 réel), Yakima uniquement — distincte de `hop_descriptors` (présence/absence,
toutes sources). Alimentée par `crawl_yakima` depuis `imported_fields.sensory_values`/
`aroma_values`, consommée par `matching.by_descriptor` (tri quantitatif) et les radars GUI
(`browse`/`compare`).

---

## Ce qui est un prior, pas une donnée

Une partie du contenu de `reference.py` n'est **pas sourcée** — une synthèse de connaissances
générales, à traiter comme un prior, pas une mesure :

- **`CONTRAST_AFFINITY`** (carte d'affinités) : prior de sagesse culinaire, aucune source. À
  ancrer sur un corpus de recettes ou une référence d'accords.
- Les listes de composés d'impact : connaissance générale, à confirmer via Flavornet/littérature.

À l'inverse, tout ce qui vient d'un **parseur avec source tracée** (composition houblon) est de
la donnée. Règle du projet : ne jamais figer en dur des valeurs de composition — passer par un
parseur et une provenance.

---

## Structure du projet

```
src/hopmatch/
  reference.py   propriétés molécule (MOLECULES) + alias/normalisation + carte d'affinités
                 (⚠️ CONTRAST_AFFINITY = prior, à ancrer) + définitions de la roue d'arôme —
                 pas de note pré-remplie, voir le module pour l'historique de l'amorce
                 littérature retirée
  parsers.py     parseurs label/valeur BarthHaas & Yakima, descripteurs, unités FooDB
  schema.py      schéma SQLite EAV (+ flavornet_compounds, flavordb2_thresholds, pubchem_cids) +
                 validation/réparation
  ingest.py      build fixtures / crawl BarthHaas / crawl Yakima (Algolia) / ingest_flavornet /
                 resolve_pubchem_cids / ingest_flavordb2 / ingest_foodb / ingest_beermaverick
  matching.py    load+réconciliation ; amplify / contrast / by_descriptor + blends
  cli.py         CLI
  app.py         GUI Streamlit (lecture seule, importe matching/schema directement)
data/fixtures/   pages réelles (démo) : barthhaas/{citra,mosaic,saazer}, yakima/{citra,mosaic,simcoe}
tools/           audit_foodb.py, foodb_impact_check.py
tests/           parsers, ingest, validation, réconciliation, modes
docs/            ARCHITECTURE.md, DATA_SOURCES.md, FEATURE_NOTES.md, BACKLOG.md
CLAUDE.md        contexte projet pour Claude Code
```

---

## Feuille de route

Fait : `ingest.ingest_flavornet`, `ingest.ingest_foodb` (seule source de notes du pipeline,
`all_foods=True` par défaut + filtre de distinctivité + `download_foodb_dump` automatique —
amorce littérature de 7 notes retirée à la demande explicite de l'utilisateur une fois ce
pipeline suffisant), `by-descriptor`, `ingest.crawl_yakima` (via Algolia), `ingest.ingest_flavordb2`,
`ingest.resolve_pubchem_cids` (jointure structurale CAS→CID, avec repli sur le nom du composé —
cf. `parsers.pubchem_name_fallbacks` — quand le CAS seul ne résout rien ; remplace la table
d'alias manuelle pour les synonymes purs et la recherche par nom exact de `ingest_flavordb2`),
GUI Streamlit (`src/hopmatch/app.py`, lecture seule), `contrast`/`contrast_blend`
généralisés par sélection manuelle de descripteurs, libellés de mode conviviaux
(`app.MODE_LABELS`), roue d'arôme quantitative par houblon en `browse`/`compare` (radar/spider
chart, Yakima uniquement, tooltip par catégorie), associations houblon<->houblon en `browse`
(`hop_similar` Yakima + `hop_pairings`/`hop_substitutions` BeerMaverick,
`ingest.ingest_beermaverick`), purpose (aromatique/amérisant, réel ou inféré), avertissement de
couverture moléculaire faible sur `amplify`, vocabulaire de descripteurs élargi de 38 à 104
termes via les tags BeerMaverick, `contrast_blend` refondu + `amplify_blend` ajouté (plusieurs
tailles de blend 1-5, priorité à la fréquence réelle de pairing BeerMaverick, houblon de base
choisi par l'utilisateur), outil **Compare Hops** (comparaison directe de 2 à 5 houblons),
nettoyage des noms de houblon (®/™/©, suffixe "Brand", désambiguïsation régionale des vrais
doublons de crop). Détail complet de chaque étape dans `docs/BACKLOG.md`/`CLAUDE.md`.

**Résidu PubChem accepté, pas une piste ouverte.** 6/734 CAS restent sans CID (0,8%) après CAS
+ repli par nom : recherché aussi par CAS comme identifiant d'enregistrement PubChem (endpoint
`xref/RegistryID`, distinct de la recherche par nom) — sans succès. Vérifié individuellement
pour deux cas : `methylethylpyrazine` désigne plusieurs isomères réels distincts (2-éthyl-3/5/
6-méthylpyrazine…) sans indication de lequel dans le nom Flavornet ; `dehydrocarveol`
(synonyme `p-menthatrien-2-ol` confirmé par des fournisseurs chimiques externes) ne répond sur
aucune des variantes de nom essayées — probablement absent de PubChem, pas juste mal nommé.
Coder un CID à la main pour ces cas ne serait pas une donnée vérifiée comme les autres entrées
manuelles du projet (`reference.ALIASES`) : ce serait une supposition sans confirmation
possible. Laissé non résolu.

**`combine()` (mode `combine`, NNLS) implémenté puis retiré.** Livré, testé, amélioré
(`docs/BACKLOG.md#T10`), puis retiré le 2026-08-12 après mesure sur les 506 notes réelles :
0 % ne dépassaient 20 % de couverture, et sur les notes à un seul composé « producible »
(la majorité) le calcul dégénérait en un résidu artificiel de 0 — confiance affichée sans
rapport avec la couverture réelle. Décision utilisateur, pas un bug de méthode : la chimie de
l'huile de houblon ne recoupe simplement pas la plupart des arômes alimentaires. Voir
l'historique git pour le détail (`matching.py`, `cli.py`, `app.py`, tests).

**`--biotransform` implémenté puis retiré.** Livré, puis retiré le 2026-08-12 (même jour que
`combine()`, décision utilisateur) : bug de double comptage confirmé sur les 29 notes réelles
demandant du citronellol (les 29 demandent aussi du géraniol, donc la même mesure comptait
deux fois) — voir la [section dédiée](#option---biotransform--implémentée-puis-retirée) pour
le détail complet.

Reste :

1. Jointure au-delà des ~734 composés Flavornet si le vocabulaire s'élargit beaucoup (crawl
   Yakima déjà réel, plus d'aliments FooDB).

---

## Licences

**Code : MIT** (voir `LICENSE`). **Les données ne le sont pas** : FooDB et FlavorDB2 sont **non
commerciales**, TGSC restrictive. Tant que HopFinder reste personnel ou open-source non lucratif,
c'est bon ; une distribution commerciale imposerait de retirer ou renégocier ces sources. Détail
par source dans `docs/DATA_SOURCES.md`.
