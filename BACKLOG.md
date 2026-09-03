# Backlog — extension « styles de bière, recettes & procédé » (2026-08-27)

Issu d'une étude de deux outils existants demandée par l'utilisateur :

- **hop-finder russe** — <https://hop-finder.vercel.app/> (Next.js, données
  embarquées dans le payload RSC, 140 houblons / 175 arômes / 24 « styles »).
- **beer-analytics** — <https://www.beer-analytics.com/> +
  <https://github.com/scheb/beer-analytics> (Django, GPLv3, 1 153 452 recettes
  annoncées, aucune recette livrée dans le dépôt « for legal reasons »).

Le backlog historique (audit 2026-08-03, T1→T80, tout implémenté) reste dans
`docs/BACKLOG.md`. Ce fichier repart à **T81**. Convention identique : `[ ]` à
faire, `[x]` fait, un commit par ticket, `pytest` vert, un test par parseur/
solveur touché.

> **T90 n'est volontairement pas attribué** : dans ce projet « T90 » désigne déjà
> les pellets Type 90 (`parsers._BREWING_VALUE_PRIORITY`, README §Yakima).

---

## 0. Ce qui a été VÉRIFIÉ en direct (à ne pas re-investiguer)

Tout ce qui suit a été constaté sur la source réelle le 2026-08-27.

### BJCP — source directe, indépendante de beer-analytics ✅

**`beerjson/bjcp-json`** (<https://github.com/beerjson/bjcp-json>),
`styles/bjcp_styleguide-2021.json`, 525 Ko, format BeerJSON 2.01 :

- **110 styles**, chacun avec `style_id` (`21A`), `name`, `category`,
  `category_id`, `category_description`, `type`.
- **Vital statistics pour 93 styles**, en objets typés avec unité explicite :
  `original_gravity/final_gravity {minimum,maximum:{unit:"sg",value}}`,
  `alcohol_by_volume {unit:"%"}`, `international_bitterness_units {unit:"IBUs"}`,
  `color {unit:"SRM"}`.
- Les **17 sans vital stats** sont les catégories 28→34 (specialty, wood-aged,
  fruit, spice, smoke, alternative fermentables, historical) : c'est **normal**,
  elles héritent des stats du style de base. Ce n'est pas un trou de données.
- `tags` = les **tags officiels BJCP** (`"high-strength, pale-color,
  top-fermented, north-america, craft-style, ipa-family, bitter, hoppy"`) —
  c'est-à-dire exactement ce que beer-analytics éclate en colonnes
  `strength/color/fermentation/origin/era/flavor`. Rien à leur emprunter.
- **En PLUS de beer-analytics** : le texte descriptif complet
  (`overall_impression`, `aroma`, `appearance`, `flavor`, `mouthfeel`,
  `comments`, `history`, `ingredients`, `style_comparison`) et les
  `examples` commerciaux.
- Seule verrue relevée : les styles provisoires `X1`, `X2`, `X4` ont des clés
  espagnoles/portugaises qui ont fuité (`sabor`, `historia`, `impresion_general`,
  `impressao_geral`) — 3 styles sur 110, à normaliser au parsing.

**2021 est bien le millésime le plus récent pour la bière** (le 2025 ne concerne
que le cidre ; le mead reste en 2015). La page officielle « Downloads and
Resources » de bjcp.org **liste elle-même** des versions de données maintenues
par des tiers (XML de Phil Murray, XML de Matthew Smedberg, tableurs), avec la
réserve « have not been checked by the BJCP for accuracy ».

⇒ **beer-analytics n'est plus nécessaire pour les styles.** Ce qu'il garde
d'unique : la colonne `alt_names`/`alt_names_extra` (utile pour rattacher une
chaîne de style libre issue d'une recette à un id BJCP) et ses styles ajoutés
hors BJCP.

### beer-analytics — ce qui reste utile

| Fichier / endpoint | Contenu réel |
|---|---|
| `recipe_db/data/hops.csv` (48 Ko, 435 lignes) | `name;use;origin;substitutes;aromas;alt_names;alt_names_extra` — **dictionnaire d'alias de noms de houblons**, curé à la main, exactement ce qui manque pour réconcilier des noms de recettes |
| `recipe_db/data/styles.csv` (157 lignes) | BJCP 2021 + alt_names + styles maison ; **seuls les alt_names nous intéressent désormais** |
| `recipe_db/data/flavors.csv` | `name;category` (vocabulaire d'arôme → catégorie) |
| Endpoints JSON publics | par style : `abv/ibu/original-gravity/final-gravity/color-srm-histogram`, `popular-hops(-amount)`, `hop-pairings`, `trending-hops` ; par houblon : `usage-types`, `amount-used-per-use`, `typical-styles-*`, `alpha/beta-histogram`, `amount-percent-range`, `hop-pairings` |

- `robots.txt` : `Allow: /` sauf `/wa/`, `GPTBot` refusé nommément.
- Format = figure **Plotly** sérialisée (`layout.template` = 90 % du poids,
  seul `data[]` compte).
- Exemples réels : `/hops/dual-purpose/citra/charts/usage-types.json` →
  `x=[Mash, First Wort, Boil, Aroma, Dry Hop]`, `y=[439, 5317, 98935, 67838, 90059]`
  (fiche Citra : **154 571 recettes**) ; `amount-used-per-use.json` → une boîte à
  moustaches par type d'usage.
- `calculate_hop_pairings.py` : JOIN **strictement par paires**
  (`rh1.kind_id != rh2.kind_id`), seuil `HOP_MIN_RECIPES = 20`.
  **Aucun triplet ni quadruplet n'existe dans cet outil.**

### Corpus de recettes brutes — MMuM vérifié et exploitable ✅

`maischemalzundmehr.de` expose un **export JSON public par recette** :

```
GET https://www.maischemalzundmehr.de/export_json.php?id=<N>
```

Structure réelle (recette 2000, une IPA) :

- `Sorte` = style en texte libre allemand (`"India Pale Ale (sonstige)"`,
  `"Deutsches Pilsner"`, `"Amber Ale"`) ;
- `Stammwuerze`, `Bittere`, `Farbe`, `Alkohol` = OG(°P), IBU, EBC, ABV ;
- **`Hopfenkochen[]`** : `{Sorte, Menge (g), Alpha, Zeit (min), Typ}` où
  **`Typ` ∈ {`Standard`, `Whirlpool`, …}** ;
- **`Stopfhopfen[]`** : les additions de **dry hop**, séparées ;
- plus `Malze`, `Rasten`, `Hefe`, `Gaertemperatur`, `Endvergaerungsgrad`.

⇒ **Le schedule houblon complet est là, avec la séparation côté chaud / whirlpool
/ côté froid.** C'est exactement la donnée dont l'épique I (composeur de set) a
besoin empiriquement, et elle permet les triplets/quadruplets.

Taille : les ids observés vont au moins jusqu'à **2290** (id 2200 renvoie 57
octets = recette absente/supprimée, donc il y a des trous). Ordre de grandeur
≈ 2 000-2 300 recettes réelles — **modeste** : suffisant pour des triplets sur
les styles populaires (IPA, Pils, Weizen), insuffisant pour les styles de niche.
Corpus germanophone, donc biais net vers les styles allemands.

### Brewfather — corpus personnel uniquement ⚠

<https://docs.brewfather.app/api> : API v2, lecture **et** écriture, auth
`userid:apikey` en base64, **500 appels/heure**, réponses JSON en unités
métriques. Endpoints recettes/batches/inventaire.

**Portée : « your recipes »** — les recettes du compte, pas de bibliothèque
publique interrogeable. Un compte Pro ne change pas la portée.

⇒ Ce n'est **pas** une source de corpus pour les triplets, mais c'est une
excellente source pour un usage **personnel** (cf. T118) : comparer ses propres
recettes au style, voir ses propres combinaisons de houblons récurrentes.

### Publications & API Yakima Chief — explorée et TRANCHÉE

- *Survivable Compounds — A Brewer's Handbook*, YCH, 2022, 19 p. Mention page 2 :
  **« © 2022 by Yakima Chief Hops. All rights reserved. »** Le graphique des
  survivables est une **image** : aucune valeur par variété n'est extractible du
  PDF. Les **règles d'usage sont du texte, citables** → recopiées dans
  `CLAUDE.md` §« Règles procédé & survivables ».
- **API de lot testée sur 3 lots réels** (`23-WA346-027`, `P92-IUCIT3082`,
  `PC1-IUCIT1079`, trouvés via une URL de partage `tools.yakimachief.com/
  lookup?lots[]=…` indexée par les moteurs) :
  `GET tools.yakimachief.com/api/lot?lotNumber[]=<LOT>`.
  - ✅ **La réponse porte le nom de variété** (`variety`, `varietyCode`,
    `cultivar`, `cropYear`, forme produit CON02/PEL02/PEL06, ferme) →
    **aucun mapping lot↔houblon à construire**.
  - ✅ Bloc `survivables` à **22 champs**, bien au-delà des 8 publiés : ajoute
    `alphaPinene`, `betaPinene`, `myrcene`, `limonene`, les méthylesters C6→C10,
    `geranylAcetate`, `transCaryophyllene`, `humulene`, **`caryophylleneOxide`**,
    `transBetaFarnesene`.
  - ❌ **Pas énumérable** : aucun index, aucun endpoint de recherche par
    variété. Énumérer les numéros par force brute serait un scan de leur API —
    exclu. 3 lots trouvés, **tous Citra 2023** : impossible d'en faire un jeu de
    données.
  - ⚠ **Unité non déclarée.** Les ordres de grandeur suggèrent des ppm, mais
    alors le 3MH (0,7-1,5) serait 20 à 50× au-dessus de l'agrégat `thiols`
    BarthHaas (0-34 µg/kg). Hypothèse plausible non vérifiée : 3MH **total,
    précurseurs liés compris**. À élucider avant toute ingestion.
  - ⚠ **Mesures PAR LOT** : sur les 3 lots Citra 2023, le Cryo affiche ~2× les
    survivables du T90 — un lot n'est pas représentatif d'une variété.
- Le hop-finder russe déclare lui-même, dans son champ `dataType` :
  *« Values are reconstructed from the CY2023 poster chart geometry. »*
  ⇒ Ses chiffres sont des **pixels**, pas des mesures.

### État de NOTRE base (189 houblons)

`hop_composition` ne contient que **15 composés distincts** :
`total_oil` (249), `alpha_acid` (249), `beta_acid` (248), `myrcene` (246),
`humulene` (238), `caryophyllene` (227), `farnesene` (226), `linalool` (219),
`geraniol` (196), `co_humulone` (150, Yakima), `beta-pinene` (135, Yakima),
`ketones` (33, BarthHaas), `isobutyrate` (31, BarthHaas, `pct_oil`),
`thiols` (22, BarthHaas, `ug_kg`), `selinene` (2).

**`isobutyrate` et les thiols sont donc déjà en base**, mais **agrégés** :
pas de 3MH/4MMP/3MHA/3S4MP en espèces distinctes, et aucun des esters/cétones
nommés du modèle survivables (2-nonanone, méthyl géranate, isoamyl isobutyrate,
isobutyl isobutyrate). Exemples vérifiés en base, contrôlables dans la GUI
(Browse → tableau de composition) :

| Houblon | isobutyrate | thiols | ketones |
|---|---|---|---|
| **Luna** | 3,4 – 5,2 % d'huile | — | — |
| **Ariana** | 0,0 – 2,3 % d'huile | 0,0 – 10,7 µg/kg | 0,0 – 3,2 % |
| **Tango** | 0,5 – 0,6 % d'huile | 3,0 – 3,5 µg/kg | 0,0 – 0,6 % |
| **Aurora** | — | — | 0,0 – 1,2 % |

### Gisement gratuit déjà dans nos crawls, jamais exploité

API Algolia Yakima (déjà interrogée par `ingest.crawl_yakima`) :

- **`imported_fields.beer_types` : 144/153 variétés** — vocabulaire éditorial
  (`Lager` 65, `IPA` 56, `Pale Ale` 45, `Pilsner` 40, `Wheat` 23, `Stout` 22,
  `NEIPA` 5, `All Styles` 4…), 47 étiquettes distinctes, **pas BJCP**.
- `imported_fields.description` (153/153, 2 paragraphes éditoriaux),
  `cultivar` (Citra → `HBC 394`), `variety_id`, `experimental`, `organic`,
  `blend`, `photo`, `products_available`.

---

## 1. Décisions

- [x] **D1 — Source des styles : TRANCHÉE (indépendance obtenue).**
  On n'utilise **pas** `styles.csv` de beer-analytics pour les styles.
  Source = `beerjson/bjcp-json` (BJCP 2021), **téléchargé à l'ingestion**, jamais
  committé (même pattern que le dump FooDB). Attribution BJCP en GUI et dans
  `docs/DATA_SOURCES.md`. La question de licence GPLv3 disparaît par la même
  occasion ; il reste un emprunt ponctuel et assumé à `hops.csv`
  (alias de noms de houblons, T92) et aux endpoints agrégés (épique B).

- [x] **D2 — Survivables : TRANCHÉE (source de lot abandonnée).**
  L'exploration demandée par l'utilisateur a abouti : le mapping lot↔variété
  **fonctionne** (la réponse porte le nom de variété), mais les numéros de lot
  **ne sont pas énumérables** — 3 lots trouvés, tous Citra 2023. Un outil de
  recherche par lot n'a aucun intérêt pour l'utilisateur, et un jeu de données
  ne peut pas être constitué.
  ⇒ **On part sur l'indice dérivé de nos propres mesures** (linalol, géraniol,
  isobutyrate, thiols — déjà en base), clairement étiqueté comme dérivé.
  ⇒ La reconstruction pixel reste **exclue** (décision utilisateur : aucune
  donnée issue d'une image dans les données propres déjà intégrées).
  ⇒ Le client de lot survit en ticket **opportuniste** (T116), au cas où de
  vrais numéros deviendraient disponibles — ~30 lignes, aucun coût à garder.

- [x] **D3 — Corpus de recettes : TRANCHÉE (MMuM).**
  MMuM est exploitable, libre d'accès, avec le schedule complet (§0). Décision
  utilisateur : **on part là-dessus**, en acceptant les ~2 000-2 300 recettes
  germanophones, tout en notant que si scheb a agrégé 1,15 M de recettes, un
  volume supérieur est atteignable — d'où le message à lui envoyer (T89) qui
  demande un agrégat de co-occurrence n-aire.
  Le dataset Kaggle « Brewer's Friend » est à vérifier avant tout espoir : il
  est **au niveau recette** et pourrait ne pas porter le détail houblon.

- [x] **D4 — Taille de la base livrée : TRANCHÉE.**
  Contexte clarifié par l'utilisateur : les données sont poussées dans un dépôt
  privé séparé (`/Users/quentin/Documents/beer_project/hopfinder-db`, qui
  contient aujourd'hui `aromahops.db` seul), et `app._fetch_remote_db`
  télécharge **une seule URL** configurée dans `st.secrets`
  (`_DB_SOURCE_URL_SECRET`), uniquement si le fichier local est absent.
  ⇒ **Deux fichiers dans le même dépôt privé** :
  - `aromahops.db` — agrégats uniquement, la seule que l'app télécharge
    (l'URL du secret ne change pas) ;
  - `recipes.db` — corpus brut MMuM (+ Brewfather), versionné et sauvegardé
    dans le même dépôt, **jamais référencé par l'app**.
  Les commandes d'agrégation (T93, T126/T127) lisent `recipes.db` et écrivent
  leurs résultats dans `aromahops.db`. Aucun changement à `_fetch_remote_db`,
  aucun risque sur le temps de démarrage Streamlit Cloud.
  ⚠ Rappel permanent : **reboot Streamlit Cloud obligatoire après tout push de
  base** — le téléchargement ne se redéclenche que si le fichier local du
  conteneur est absent.

---

## 1bis. Contrat de ticket — à lire AVANT d'implémenter n'importe lequel

Ces règles valent pour **tous** les tickets et ne sont pas répétées dans chacun.
Elles sont écrites pour qu'aucune décision implicite ne reste à deviner.

**Périmètre et fichiers**
- Un ticket = **un commit**. Message de commit en français.
- Fichiers concernés uniquement : `src/hopmatch/{app,cli,ingest,matching,
  parsers,reference,schema}.py`, `tests/`, `docs/`, `data/mappings/`.
- Ne jamais modifier un fichier hors du périmètre annoncé par le ticket.

**Données — règles absolues du projet**
- **Ne jamais fabriquer une valeur de houblon.** Toute donnée passe par un
  parseur + une `source` tracée en base.
- **Ne jamais moyenner deux sources** qui mesurent selon des méthodologies
  différentes. Réconciliation à la LECTURE, jamais à l'écriture.
- Une mesure absente reste absente. **Jamais de 0 fabriqué**, jamais de repli
  silencieux sur une valeur codée en dur.
- Toute troncature de résultats doit être annoncée à l'utilisateur (pattern
  `total_matches`, déjà en place dans `matching.contrast`).

**Base de données**
- Le schéma vit dans `schema.py` (`SCHEMA` + `init_db`). Toute nouvelle table
  s'y ajoute, avec un commentaire expliquant sa source et ce qu'elle n'est pas.
- `init_db` fait `DROP TABLE IF EXISTS` sur chaque table : **ajouter le DROP
  correspondant** en même temps que le `CREATE`, sinon une reconstruction
  laisse une table stale.
- Clé primaire toujours explicite, incluant `source` quand la table est
  multi-sources.

**GUI (`app.py`)**
- **Tout texte utilisateur est en ANGLAIS.** Commentaires et docstrings en
  français, y compris dans `app.py`.
- Un saut de ligne dans `st.caption`/`help=`/tooltip s'écrit `"  \n"` (deux
  espaces avant le saut) — un `\n` seul est ignoré par le rendu Markdown.
- Une carte `app._panel()` par section logique. Jamais autour d'une seule
  ligne, jamais imbriquée.
- Tableaux via `st.dataframe` + `column_config`. **Jamais `st.columns` par
  ligne** (s'empile verticalement sous une largeur d'écran donnée).
- Couleurs de graphique : `_COMPARE_PALETTE` (5 premières entrées de
  `chartCategoricalColors`) est **réservée à l'identité des houblons** ;
  `_CATEGORY_CLASS_COLORS` puise dans les 5 dernières. Tout nouvel encodage
  couleur doit éviter ces deux jeux.
- **`app._RECENT_UPDATES` est mis à jour dans le MÊME commit** dès qu'un
  changement est visible par l'utilisateur final (nouvel outil, nouvelle
  section, comportement perceptible). Pas pour un refactor ou du CLI seul.

**Tests**
- `pytest -q` doit rester vert. Lancer avec `.venv/bin/python -m pytest -q`
  (le python système n'a pas les dépendances — voir la mémoire projet).
- **Tout parseur ou solveur touché reçoit un test.** Fixture locale sous
  `data/fixtures/` ou `tests/`, jamais un appel réseau dans un test.
- Nommer le test d'après le comportement garanti, pas d'après la fonction
  (exemple existant : `test_contrast_blend_mixes_relevance_and_pairing_not_
  pure_frequency`).

**Réseau (crawlers/ingestion)**
- `User-Agent` identifiable : `hopmatch/0.1 (research)`, comme les crawls
  existants.
- Une seule passe, délai entre requêtes, **réponses cachées sur disque** sous
  `data/cache/<source>/` pour ne jamais re-fetcher pendant le développement.
- `fetched_at` stocké par ligne quand la donnée peut changer dans le temps.
- Jamais d'énumération par force brute d'une API tierce.

**Definition of Done (tout ticket)**
1. Le comportement décrit est implémenté, sans élargir le périmètre.
2. `pytest -q` vert, nouveau(x) test(s) inclus.
3. Vérification **en conditions réelles** si le ticket touche la GUI :
   lancer l'app, regarder le rendu **dans les deux thèmes** (clair et sombre),
   console navigateur ouverte si un graphique Vega-Lite est modifié.
4. `_RECENT_UPDATES` à jour si visible par l'utilisateur.
5. Documentation mise à jour si une source de données est ajoutée
   (`docs/DATA_SOURCES.md`) ou si un prior est introduit (`README.md`).
6. La case du ticket passe à `[x]` dans ce fichier, avec une ligne de compte
   rendu si une décision a été prise en cours de route.

**En cas de doute**
- Si le ticket ne dit pas quoi faire dans un cas, **ne pas inventer** :
  s'arrêter et demander. Un choix implicite non documenté est une dette.
- Si une vérification contredit le ticket, **le ticket a tort** : le corriger
  et le dire, ne pas forcer l'implémentation.

---

## 2. Épique A — Styles BJCP (référence)

- [x] **T81 — Table `beer_styles` + commande `ingest-styles`**

  **Compte rendu (2026-08-27)** : implémenté tel quel, avec une correction au
  ticket trouvée en vérifiant les 3 styles à clés localisées un par un plutôt
  que de recopier sa liste : **`ejemplos_comerciales`** (espagnol, style X2)
  n'était pas dans la liste du ticket (qui ne mentionnait que la variante
  portugaise `exemplos_comerciais`, X4) — les deux mappent vers `examples`,
  ajoutées à `parsers._BJCP_LEAKED_LOCALE_KEYS`. Confirmé aussi que
  `marcacoes` (X4) porte l'équivalent de `tags`, pas de `comments`.
  Piège évité en cours de route : `ingest_beer_styles` créait initialement la
  table via `init_db` (qui DROP + recrée TOUTES les tables) quand
  `beer_styles` manquait — aurait vidé `hops`/`hop_composition`/etc. d'une
  base réelle déjà peuplée qui n'a jamais eu cette table. Corrigé par
  `schema.ensure_table` (crée UNE SEULE table manquante, sans toucher aux
  autres), réutilisable pour les prochains tickets qui ajoutent une table.
  Vérifié sur données réelles : `SELECT count(*) FROM beer_styles` → 110,
  `WHERE og_min IS NULL` → 17, `hops` intact (189, inchangé) après ingestion,
  `--year 2015` échoue explicitement avant tout appel réseau.
  **Addendum (T82, même jour)** : le style provisoire X2 porte
  `original_gravity`/`final_gravity` en `1055`/`1065`/`1008`/`1015` — unité
  `"sg"` correcte mais valeur décalée d'un facteur 1000 (bug de saisie côté
  `beerjson/bjcp-json` lui-même). Décision utilisateur : `_bjcp_vital_stat_
  bounds` normalise (÷1000) toute valeur `og`/`fg` strictement > 10 — seuil
  volontairement haut pour ne jamais toucher `abv`/`ibu`/`srm` (dépassent
  légitimement 10). Réingéré, vérifié : `og_max`/`fg_max` réels plafonnent
  maintenant à 1.13/1.04 sur toute la base (plus d'outlier à 1055).

  **Source** : `https://raw.githubusercontent.com/beerjson/bjcp-json/main/styles/bjcp_styleguide-2021.json`
  (525 Ko, BeerJSON 2.01). **Téléchargé à l'ingestion, jamais committé**
  (même pattern que `ingest.download_foodb_dump`). Cache disque sous
  `data/cache/bjcp/`.

  **Structure du JSON** : racine `{"beerjson": {"version": 2.01,
  "styles": [ … ]}}`, 110 entrées. Champs par style :
  `style_id` (`"21A"`), `name`, `category`, `category_id` (`"21"`),
  `category_description`, `type` (`"beer"`), `tags` (chaîne, virgules),
  `overall_impression`, `aroma`, `appearance`, `flavor`, `mouthfeel`,
  `comments`, `history`, `ingredients`, `style_comparison`, `examples`,
  et les vital stats sous forme d'objets typés :
  ```json
  "original_gravity": {"minimum": {"unit": "sg", "value": 1.056},
                       "maximum": {"unit": "sg", "value": 1.070}}
  ```
  idem `final_gravity`, `alcohol_by_volume` (`unit: "%"`),
  `international_bitterness_units` (`unit: "IBUs"`), `color` (`unit: "SRM"`).

  **Nouvelle table dans `schema.py`** (+ son `DROP TABLE IF EXISTS` dans
  `init_db`, sinon une reconstruction laisse une table stale) :
  ```sql
  CREATE TABLE beer_styles (
      style_id TEXT, guideline_year INTEGER, category_id TEXT, category TEXT,
      name TEXT, type TEXT, tags TEXT,
      og_min REAL, og_max REAL, fg_min REAL, fg_max REAL,
      abv_min REAL, abv_max REAL, ibu_min REAL, ibu_max REAL,
      srm_min REAL, srm_max REAL,
      overall_impression TEXT, aroma TEXT, appearance TEXT, flavor TEXT,
      mouthfeel TEXT, comments TEXT, history TEXT, ingredients TEXT,
      style_comparison TEXT, examples TEXT, category_description TEXT,
      source TEXT,
      PRIMARY KEY (style_id, guideline_year)
  );
  ```

  **Parseur** : `parsers.parse_beerjson_styles(payload: dict) -> list[dict]`.
  Trois pièges à traiter explicitement, chacun vérifié en direct le
  2026-08-27 :
  1. **17 styles n'ont AUCUNE vital stat** : `28A 28B 28C 29A 29B 29C 30A 30B
     30C 30D 31A 31B 32A 32B 34A 34B 34C` (specialty, wood-aged, fruit,
     spice, smoke, alternative fermentables, historical). **C'est normal** —
     ces styles héritent des stats du style de base choisi par le brasseur.
     Écrire `NULL`, **jamais 0**, et ne jamais les traiter comme un trou de
     données à combler.
  2. **Vérifier l'unité de chaque objet**, ne pas la supposer. Attendu :
     `sg` pour les densités, `%` pour l'ABV, `IBUs`, `SRM`. Si une unité
     inattendue apparaît (`plato`, `ebc`), **lever une erreur explicite**
     plutôt que d'écrire une valeur dans la mauvaise unité.
  3. **3 styles ont des clés espagnoles/portugaises qui ont fuité** :
     `X1`, `X2`, `X4` portent `sabor`, `historia`, `ingredientes`,
     `impresion_general`, `aspecto`, `sensacion_en_boca`, `comentarios`,
     `impressao_geral`, `aparencia`, `sensacao_de_boca`,
     `comparacoes_de_estilo`, `exemplos_comerciais`, `marcacoes`.
     Mapper ces clés vers leurs équivalents anglais via un dict de
     correspondance **explicite et commenté**, jamais par heuristique.

  **CLI** : nouvelle sous-commande `hopmatch ingest-styles`, option
  `--year {2021,2015}` (défaut 2021). Les deux millésimes coexistent dans la
  table via `guideline_year`, **jamais fusionnés** (même règle que
  Yakima/BarthHaas). Le fichier 2015 n'existe pas dans ce dépôt — si `--year
  2015` est demandé, échouer avec un message clair plutôt que de retomber
  silencieusement sur 2021.

  **Test** (`tests/test_ingest.py`) : fixture JSON réduite sous
  `tests/fixtures/bjcp_sample.json` contenant exactement 3 styles — un
  complet (21A), un sans vital stats (28A), un à clés espagnoles (X1) — et
  vérifier les trois comportements ci-dessus. **Aucun appel réseau.**

  **Vérification sur données réelles après implémentation** :
  `SELECT count(*) FROM beer_styles` → **110** ;
  `SELECT count(*) FROM beer_styles WHERE og_min IS NULL` → **17**.

- [x] **T82 — Mode GUI « Beer styles »**

  **Compte rendu (2026-08-27)** : implémenté avec plusieurs ajustements
  trouvés/demandés en vérification live, au-delà du texte initial du
  ticket :
  - **Cas non prévu par le ticket** : 4 styles provisoires partagent le
    MÊME `category_id` littéral `"X"` (Argentine/Brazilian/Italian/New
    Zealand Styles) — `app._category_sort_key` les groupe après toutes les
    catégories numériques, triés entre eux par nom (seul moyen de les
    distinguer).
  - **Bug de troncature trouvé en vérification live** : 5 `st.metric` côte
    à côte tronquaient les fourchettes ("2.8%…") — corrigé en passant à
    UNE LIGNE PAR CRITÈRE (`st.columns([2, 3])`, label+valeur | barre) sur
    retour utilisateur explicite ("explore the different elements into
    multiple lines").
  - **Ajout hors ticket, demande utilisateur explicite** : deux toggles
    d'unités INDÉPENDANTS en haut de page — Color (EBC/SRM) et Density
    (°Plato/SG) — un premier essai bundlé en un seul toggle Metric/Imperial
    a été refait en deux toggles séparés sur retour utilisateur ("Il peut
    arriver de vouloir utiliser EBC et Plato en meme temps"). EBC = SRM ×
    1,97 (facteur déjà établi dans ce projet, BACKLOG.md T91/MMuM — pas
    inventé pour ce ticket). SG→Plato : polynôme cubique standard ASBC
    (`app._sg_to_plato`), vérifié numériquement contre des points de
    référence connus (SG 1,050 → 12,4°P etc., voir compte rendu de session)
    avant d'être livré — provenance : connaissance générale du domaine
    brassicole, pas un fichier de ce dépôt, d'où la vérification
    supplémentaire demandée et faite. La couleur de la barre SRM reste
    TOUJOURS calculée sur la vraie valeur SRM en base, jamais reconvertie.
  - **Séparateur `—` remplacé par `-`** dans les noms affichés (catégorie/
    style/en-tête), et les tags/exemples (un `st.badge` par ligne à
    l'origine) regroupés via `_descriptor_chips`/`_source_chips` (un seul
    `st.markdown`, s'enroule naturellement) — deux retours utilisateur en
    vérification live.
  - **Bug upstream trouvé sur X2 pendant la construction de cette page**
    (`og_min`/`fg_min` = 1055/1008 au lieu de 1.055/1.008) : voir
    l'addendum sous T81 — corrigé dans le parseur, pas ici.
  - **Ajout supplémentaire, demande utilisateur explicite** : les bornes
    min/max écrites au-dessus de chaque extrémité de la barre de range
    (pas seulement dans `st.metric` à gauche). Bug trouvé en vérification
    live : les deux étiquettes grandissant chacune VERS L'INTÉRIEUR (min
    vers la droite, max vers la gauche) se chevauchaient sur toute
    fourchette étroite par rapport à son domaine (ABV 2.8–4.2 % sur un
    domaine 0–15 %, entre autres) — corrigé en les faisant grandir VERS
    L'EXTÉRIEUR à la place (`translateX(-100%)` sur la borne min,
    `translateX(0)` sur la max) : elles s'écartent alors toujours l'une de
    l'autre, quelle que soit l'étroitesse du segment, sans jamais se
    chevaucher.

  **Dépend de T81.** Nouvelle entrée dans `app.MODE_LABELS` :
  `"styles": "Beer styles"`.

  **Navigation** : deux `st.selectbox` en cascade — catégorie
  (`category_id` + `category`, triée par `category_id` **numérique**, pas
  lexicographique : sinon `10` passe avant `2`), puis style de cette
  catégorie (`style_id` + `name`).

  **Contenu, dans cet ordre, une carte `app._panel()` par bloc** :
  1. **En-tête** : `style_id` + `name`, `tags` rendus en `st.badge`
     (sage neutre — **pas** de terracotta, réservé à l'interaction).
  2. **Vital statistics** : 5 `st.metric` (ABV %, IBU, OG, FG, SRM) affichant
     la fourchette `min – max`, plus une **barre de range** par critère.
     Si la valeur est `NULL` (les 17 styles), afficher `—` et une
     `st.caption` expliquant que ce style hérite des stats du style de base,
     **jamais** une barre vide qui ferait croire à zéro.
  3. **Description** : `overall_impression` en texte courant, puis
     `aroma` / `appearance` / `flavor` / `mouthfeel` / `comments` /
     `history` / `ingredients` / `style_comparison` en `st.expander` repliés.
  4. **Commercial examples** : `examples` (chaîne à virgules) en badges.

  **Couleur SRM** : une échelle de couleur de bière réelle est légitime ici
  (c'est une mesure de couleur, pas un choix décoratif). Utiliser une rampe
  paille→ambre→brun→noir, indépendante de `_COMPARE_PALETTE`.

  ⚠ Texte utilisateur en **anglais**. ⚠ `_RECENT_UPDATES` même commit.

- [x] **T83 — Table `hop_beer_styles` (houblon → style, éditorial)**
  *Priorité utilisateur explicite : « super important ».*

  **Compte rendu (2026-08-27)** : implémenté avec une extension trouvée en
  vérification live (au-delà de la source Yakima explicitement spécée) —
  BeerMaverick porte AUSSI cette info, dans une section "Beer Styles using
  {Hop} Hops" (texte libre, noms en `<b>`), jamais exploitée avant :
  vérifiée stable sur 5 pages réelles (Citra, Mosaic, Simcoe, Centennial,
  Admiral y compris low-volume). `parsers.parse_beermaverick_styles`
  ajouté, écrit avec `source='beermaverick'` — jamais fusionné avec Yakima
  (`ingest._write_hop_beer_styles`, partagé entre les deux crawlers).
  BeerMaverick porte un vocabulaire BEAUCOUP plus large et moins propre que
  les 47 étiquettes Yakima (96 étiquettes non résolues après un premier
  crawl réel, pluriels incohérents type "Pale Ale"/"Pale Ales") —
  volontairement laissées `NULL` (jamais devinées), une passe de tri manuel
  supplémentaire pour ce vocabulaire est un suivi séparé, pas fait ici (le
  YAML T84 n'a couvert que les 47 étiquettes Yakima révisées avec
  l'utilisateur).
  **Bug d'encodage trouvé et corrigé en vérifiant sur données réelles** :
  BeerMaverick ne déclare pas de charset dans son en-tête HTTP
  (`Content-Type: text/html` nu) — `requests` retombait sur ISO-8859-1par
  défaut (RFC 2616) alors que le contenu réel est UTF-8, corrompant tout
  caractère non-ASCII ("Kölsch" → "KÃ¶lsch"). Corrigé par
  `resp.encoding = resp.apparent_encoding` avant `.text` dans
  `ingest_beermaverick`. Recrawlé, vérifié corrigé sur la base réelle.
  GUI : 4e bloc dans `_hop_associations` (Browse), groupé par source comme
  les descripteurs (`_descriptors_grouped_by_source`), réserve éditoriale
  systématique. Vérifié réel : 163 variétés distinctes couvertes (yakima
  143 + beermaverick 144, union), 454 lignes Yakima (71 résolues) + 573
  lignes BeerMaverick (76 résolues), `hops` intact (189) après les deux
  crawls (`ensure_table`, même pattern que T81/T84).

  **Source déjà crawlée, jamais exploitée** :
  `imported_fields.beer_types` de l'API Algolia Yakima, présent sur
  **144/153 variétés**, 47 étiquettes distinctes. Vocabulaire éditorial, pas
  BJCP : `Lager` ×65, `IPA` ×56, `Pale Ale` ×45, `Pilsner` ×40, `Wheat` ×23,
  `Stout` ×22, `American Pale Ale` ×17, `NEIPA` ×5, `All Styles` ×4, etc.

  **Table** (+ son `DROP` dans `init_db`) :
  ```sql
  CREATE TABLE hop_beer_styles (
      variety TEXT, style_label TEXT, style_id TEXT, source TEXT,
      PRIMARY KEY (variety, style_label, source)
  );
  ```
  `style_label` = l'étiquette brute telle quelle. `style_id` = l'id BJCP
  **seulement si la correspondance est certaine** (via T84), `NULL` sinon.
  ⚠ `All Styles`, `Ale`, `Amber`, `Imperial Ale` n'ont **pas** d'équivalent
  BJCP : ils restent `NULL` et sont affichés tels quels. Ne jamais rattacher
  au jugé.

  **Implémentation** : `parse_yakima_hit` retourne déjà le hit complet —
  ajouter l'extraction de `beer_types` et l'écriture dans `crawl_yakima`.
  Vérifier ensuite si BeerMaverick et BarthHaas portent la même information
  dans le HTML **déjà fetché** (c'est ainsi que la roue BarthHaas avait été
  trouvée en T79) ; si oui, les ingérer avec leur propre `source`.

  **GUI** : affiché dans `browse`, avec la réserve systématique
  « **suggestion éditoriale d'un producteur, pas une fréquence mesurée** » —
  exactement le traitement des pairings BeerMaverick. À ne pas confondre avec
  T86 (fréquence réelle en recettes), qui répondra à la même question avec
  des données mesurées.

  **Vérification réelle** : après `crawl-yakima`,
  `SELECT count(DISTINCT variety) FROM hop_beer_styles` ≈ **144**.

- [x] **T84 — Réconciliation `style_label` → `style_id` BJCP**

  **Compte rendu (2026-08-27)** : les 47 étiquettes réelles ont été
  récupérées en direct depuis l'API Algolia Yakima (144/153 houblons, exact
  match avec les chiffres du ticket) — 15 candidats proposés (9 haute
  confiance par correspondance exacte de nom BJCP, 6 confiance moyenne),
  **revus et confirmés par l'utilisateur avant écriture** (pas d'auto-génération
  silencieuse, conforme à la règle du ticket). Une correction trouvée à
  l'exemple du ticket lui-même : `"NEIPA": "21B"` (Specialty IPA) était
  l'exemple donné, mais les données BJCP 2021 réellement ingérées (T81)
  montrent que 21C est "Hazy IPA" — BJCP a renommé New England IPA en Hazy
  IPA sous 21C, 21B reste le catch-all générique "Specialty IPA". Utilisé
  `21C`, pas l'exemple du ticket. 32 étiquettes restent `null` (aucune
  correspondance BJCP défendable) — dont les 4 explicitement citées par
  T83 (`All Styles`, `Ale`, `Amber`, `Imperial Ale`).
  Usage #2 (chaînes de style allemandes, T91) pas encore ajouté au fichier
  — T91 (ingestion MMuM) n'a pas encore tourné, rien à réconcilier pour
  l'instant ; même fichier à compléter quand T91/T92 arriveront.
  Garde-fou testé contre la vraie table `beer_styles` (110 styles) :
  `test_beer_style_aliases_yaml_values_exist_in_real_bjcp_styles`.

  **Fichier** : `data/mappings/beer_style_aliases.yaml`, même forme que
  `barthhaas_aroma_wheel_categories.yaml`. Structure :
  ```yaml
  # label éditorial (Yakima/BeerMaverick/recette) -> style_id BJCP, ou null
  "American Pale Ale": "18B"
  "NEIPA": "21B"        # Specialty IPA: New England IPA
  "All Styles": null    # pas d'équivalent BJCP, volontairement non rattaché
  ```

  ⚠ **Trié à la main avec l'utilisateur, jamais dérivé automatiquement.**
  Précédent : les descripteurs auto-dérivés de FooDB ont été rejetés **deux
  fois** pour convergence vers des termes génériques. Un mapping de styles
  produit par fuzzy matching ferait la même erreur (« Wheat » →
  « American Wheat Beer » ? « Weissbier » ? les deux sont défendables).

  **Deux usages, un seul fichier** :
  1. les 47 étiquettes Yakima de T83 ;
  2. les chaînes de style libres des recettes (T91), en **allemand**
     (`"India Pale Ale (sonstige)"`, `"Deutsches Pilsner"`, `"Amber Ale"`).
  Amorce autorisée pour préparer le tri manuel : les colonnes `alt_names` /
  `alt_names_extra` de `recipe_db/data/styles.csv` (beer-analytics) — mais
  **chaque ligne est validée à la main** avant d'entrer dans le YAML.

  **Test** : garde-fou vérifiant que **toute valeur non-`null` du YAML existe
  réellement** dans `beer_styles.style_id` — même principe que
  `test_ingredient_descriptors_keys_and_terms_match_real_vocabulary`.

---

## 3. Épique B — Statistiques de recettes (beer-analytics)

- [x] **T85 — Client `ingest_beer_analytics` + distributions par style**

  **Compte rendu (2026-08-27/28)** : infrastructure et table livrées et
  testées (fixtures, aucun appel réseau requis par les tests) exactement
  comme spécifié — `ingest._beer_analytics_fetch`/`_beer_analytics_get`
  (cache disque `data/cache/beer_analytics/`, écriture atomique fichier
  temporaire + `os.replace`, comme `download_bjcp_styles`/T81), `parsers.
  discover_beer_analytics_charts`/`plotly_traces`/`parse_pandas_interval`
  (vérifiés en direct sur 5 charts réels : `x` = intervalles pandas, `y` =
  effectifs, `layout` ignoré, ~90% du poids confirmé — 8107 caractères de
  template contre quelques centaines de data). `style_recipe_stats` créée
  (+ `ensure_table`, + `DROP` dans `init_db`), CLI `ingest-beer-analytics`.

  ⚠ **Crawl complet interrompu une première fois, PAS un bug.** Premier
  essai (2026-08-27) : le site a brutalement ralenti après ~500 requêtes/
  1h30 (rythme initial ~13 requêtes/min tombé à ~0,1/min, connexion TCP
  `ESTABLISHED` mais quasi-immobile plusieurs dizaines de minutes) —
  comportement typique d'un rate-limiting informel côté serveur même à
  notre rythme poli d'1 req/s. Décision : **arrêter plutôt que forcer**
  (cohérent avec l'esprit de T89, « prévenir avant de lire régulièrement »
  — grinder à travers un ralentissement délibéré serait le contraire de
  « une seule passe, respectueuse »). 89/159 pages ingérées à ce stade
  (159 = un COMPTAGE ERRONÉ à l'époque, incluant les pages CATÉGORIE à un
  seul segment, ex. `/styles/standard-american-beer/`, jamais de vraies
  pages de style — corrigé le lendemain, voir plus bas).

  **Repris et terminé proprement le lendemain (2026-08-28), sur demande
  explicite de l'utilisateur** (« try again I want as much data as
  possible ») : le rythme normal était revenu (aucun ralentissement),
  **123/123 pages de style réellement ingérées, zéro erreur** — le cache
  disque a évité de re-fetcher les 89 déjà obtenues (rejouées en quelques
  secondes), seules les ~34 manquantes ont demandé un vrai fetch réseau.
  **6577 bins écrits au total** dans la base réelle (`aromahops.db`).
  123 est le VRAI total (pas 159, voir ci-dessus — corrigé dans le
  commentaire d'en-tête de `beer_style_aliases.yaml`).

  **Résolution `style_id`** (`data/mappings/beer_style_aliases.yaml`, T84,
  nouvel usage) : vocabulaire beer-analytics bien plus proche des noms
  BJCP littéraux que celui de Yakima (98/123 noms en correspondance EXACTE
  et NON ambiguë, contre les libellés larges/ambigus de Yakima qui restent
  `null`). **112/123 styles résolus au total** sur la base réelle finale.
  Découverte en cours de route : 7 variantes de « Specialty IPA »
  (Belgian/Black/Brown/Brut/Red/Rye/White IPA, 184 à 6179 recettes chacune
  sur le seul chart abv-histogram — volume réel non négligeable, vérifié
  en direct) que BJCP ne couvre que par un seul style_id générique (21B)
  sans vital stats propres à chaque variante. **Décision utilisateur
  (2026-08-27), après discussion** : ne PAS fabriquer de nouvelles lignes
  `beer_styles` pour ces variantes (aurait inventé un style_id/des vital
  stats BJCP qui n'existent pas officiellement) — mappées à `21B` dans le
  fichier d'alias (chaque variante garde sa propre ligne
  `style_recipe_stats`, clé `style_slug` pas `style_id`, donc jamais
  fondue avec les autres) ; rendre ces noms *cherchables individuellement*
  dans `browse` est le sujet du nouveau **T130** (recherche par alias),
  pas de ce ticket. 11 noms beer-analytics n'ont AUCUN équivalent dans nos
  110 styles BJCP 2021 ingérés (Kellerbier, Kentucky Common, Lichtenhainer,
  London Brown Ale, Piwo Grodziskie, Pre-Prohibition Lager/Porter,
  Roggenbier, Sahti, Specialty Wood-Aged Beer, Wood-Aged Beer — cette
  dernière paire découverte le 28, aucune catégorie "Wood Beer" présente
  dans notre jeu BJCP 2021 ingéré) — `null`, vérifié en direct contre les
  110 noms réels, pas une ambiguïté à trancher.

  **Aucun changement GUI** — ticket infrastructure pure, pas d'entrée dans
  `_RECENT_UPDATES` (règle CLAUDE.md : uniquement pour du changement
  visible par l'utilisateur final).

  --- Ticket original ci-dessous, conservé pour référence ---

  **Fondation de toute l'épique B.** Écrire d'abord l'infrastructure commune
  (T85), les tickets suivants la réutilisent.

  **Infrastructure commune** (`ingest.py`) :
  - `_beer_analytics_get(path: str) -> dict` : GET sur
    `https://www.beer-analytics.com<path>`, `User-Agent: hopmatch/0.1
    (research)`, **cache disque obligatoire** sous
    `data/cache/beer_analytics/<path aplati>.json`, délai de **1 s** entre
    deux requêtes réelles (aucun délai sur un hit de cache).
  - `_plotly_traces(payload: dict) -> list[dict]` : retourne `payload["data"]`
    **uniquement**. ⚠ `payload["layout"]["template"]` fait ~90 % du poids et
    ne contient aucune donnée — ne jamais le parser ni le stocker.

  **Découverte des URLs** : les chemins de charts sont dans le HTML de la page
  du style, en attribut `data-chart="…"`. Ne PAS les construire à la main : le
  segment de catégorie diffère du slug affiché (l'URL de page est
  `/styles/india-pale-ale/american-ipa/` mais les charts sont sous
  `/styles/ipa/american-ipa/charts/…`). Parser le HTML de la page, extraire
  les `data-chart`, suivre ceux dont on a besoin.

  **Table** (+ `DROP` dans `init_db`) :
  ```sql
  CREATE TABLE style_recipe_stats (
      style_id TEXT, style_slug TEXT, metric TEXT,
      bin_low REAL, bin_high REAL, count INTEGER,
      source TEXT, fetched_at TEXT,
      PRIMARY KEY (style_slug, metric, bin_low)
  );
  ```
  `metric ∈ {abv, ibu, og, fg, srm}`, depuis les 5 charts
  `abv-histogram`, `ibu-histogram`, `original-gravity-histogram`,
  `final-gravity-histogram`, `color-srm-histogram`.

  **Format des bins** : `trace["x"]` contient des chaînes d'intervalle
  pandas, `"(5.0, 5.3]"`. Parser `bin_low`/`bin_high` par expression
  régulière ; `trace["y"]` donne les effectifs. **Échouer bruyamment** si le
  format change, ne jamais deviner.

  ⚠ **Limite à afficher, jamais masquer** : ces histogrammes sont
  **pré-binnés** (10 classes) et les outliers ont déjà été retirés côté
  beer-analytics (`remove_outliers(…, 0.02)`). On ne peut donc PAS en dériver
  un vrai percentile. La GUI dit « distribution observée », **jamais
  « P5–P95 »**.

  `style_id` = notre id BJCP via T84, `NULL` si non résolu (leurs styles ne
  sont pas tous BJCP).

  **Test** : fixture JSON locale réduite (un seul trace, 3 bins), vérifier le
  parsing des intervalles et que `layout` est ignoré. Aucun appel réseau.

- [x] **T86 — `style_hop_usage` : quels houblons pour ce style**

  **Compte rendu (2026-08-28)** : vérifié en direct AVANT de trancher le
  point le plus incertain du ticket, comme demandé. Réponse à « à vérifier
  pendant l'implémentation » : **URLs distinctes, pas un filtrage client**.
  Reverse engineering du bundle JS `/static/app.js` (le HTML seul ne
  suffisait pas à trancher : les onglets "Used for" utilisent `data-bs-
  toggle="tab"`, un composant Bootstrap générique) — trouvé la classe
  `Chart` : `load(e={})` appelle `getRequest(this.chartUrl, e, ...)`, et le
  callback de navigation fait `chart.load({filter: i})` où `i` est la
  valeur de l'onglet cliqué (`aroma`/`bittering`/`dry-hop`, vide pour "Any").
  Confirmé par fetch réel : `popular-hops.json?filter=bittering` renvoie des
  valeurs RÉELLEMENT différentes de `popular-hops.json` seul (ex. Citra sur
  American IPA : dernière valeur 0,3311 en "any" vs 0,2120 en "bittering") —
  donc **capturé, comme demandé par le ticket** ("c'est la donnée la plus
  intéressante").

  ⚠ **Schéma étendu par rapport au ticket original** : `usage_type` ajouté à
  la clé primaire (`style_slug, hop_name, usage_type` au lieu de
  `style_slug, hop_name`) — le `CREATE TABLE` du ticket avait été rédigé
  AVANT cette vérification et n'avait nulle part où stocker la ventilation
  par usage qu'il demandait pourtant de capturer. `usage_type ∈ {any,
  bittering, aroma, dry-hop}`, "any" = onglet "Any" = aucun paramètre.

  ⚠ **Bug réel trouvé et corrigé en marge de ce ticket** :
  `ingest._beer_analytics_cache_filename` ne gérait pas les query strings —
  `"....json?filter=aroma"` ne se termine plus par `.json` littéralement,
  tombait dans le repli `.html` alors que le contenu est du JSON, ET aurait
  fait collision entre différents filtres du même chart s'il avait
  simplement tronqué la query string au lieu de la sanitiser en suffixe.
  Corrigé (voir `schema.py`/`ingest.py`), testé.

  **Crawl complet, en plusieurs passes** (2026-08-28) : le premier passage
  complet (123 styles × jusqu'à 8 requêtes) a essuyé ~291 échecs `NameResolutionError`
  groupés (panne DNS/réseau LOCALE transitoire — symptôme différent du
  ralentissement serveur de T85, jamais reproduit côté serveur : `curl`
  direct restait rapide pendant l'incident). Une reprise (cache-first, ne
  refetch que le manquant) a elle-même buté deux fois sur un blocage
  silencieux (aucune requête ne progressait pendant 15-20 min, CPU quasi
  nul — proche d'un hang réseau local plutôt qu'un vrai timeout, chaque
  tentative tuée puis relancée). **Troisième reprise complète sans
  incident** : **123/123 styles couverts, 112/123 style_id résolus (même
  taux que T85, cohérent), 3997 lignes, 3611/3997 (90%) houblons résolus
  vers une `variety`** — 28 noms de houblon distincts non résolus (variantes
  d'orthographe réelles type "Hallertauer Blanc"/"Mount Hood", houblons
  absents de notre catalogue à 203 variétés type Belma/Calypso/Strata, et
  une anomalie côté source : "Lambic" apparaît comme "houblon" sur un chart
  — un style de bière mal étiqueté chez beer-analytics, pas une erreur
  d'ici) — `variety` reste `NULL`, jamais deviné, `hop_name` brut toujours
  conservé.

  **Aucun changement GUI** — ticket infrastructure/données pures, pas
  d'entrée `_RECENT_UPDATES`.

- [x] **T87 — `style_hop_pairings` : paires réelles par style**

  **Compte rendu (2026-08-28)** : ticket direct, aucune ambiguïté à trancher
  cette fois (contrairement à T86) — vérifié en direct que la section « Hop
  Pairings » d'une page de style n'a PAS de `data-chart-navigation` (pas
  d'onglet any/aroma/bittering/dry-hop, contrairement à `popular-hops*.json`)
  : une seule URL par style suffit. Trace `box` par houblon partenaire,
  format identique à `popular-hops-amount.json` (T86) — réutilise
  directement `parsers.parse_box_trace`. Schéma implémenté TEL QUEL, sans
  déviation.

  `style_id`/`variety` résolus comme T85/T86. **123/123 styles couverts,
  112/123 style_id résolus (même taux que T85/T86, cohérent), 1182 lignes,
  1055/1182 (89%) houblons résolus vers une `variety`.**

  ⚠ **Crawl marqué par une instabilité réseau LOCALE récurrente** (déjà vue
  sur T86) : 3 tentatives se sont arrêtées net après quelques minutes
  (progression quasi nulle, CPU quasi nul — `curl` direct restait rapide à
  chaque fois pendant l'incident, donc pas un problème serveur). Chaque
  tentative tuée puis relancée (cache-first, ne refetch que le manquant) ;
  la 4e est passée sans aucun souci apparent. Deux tickets de suite touchés
  par le même symptôme — voir CLAUDE.md, probablement un problème propre à
  cette session/machine plutôt qu'à beer-analytics.com, à surveiller si ça
  continue sur les tickets suivants de l'épique B (T88/T89).

  ⚠ **PAIRES uniquement, respecté** : `calculate_hop_pairings` côté
  beer-analytics est un JOIN sur deux houblons distincts (seuil 20
  recettes) — aucun triplet dérivé ici, aucune tentative. La réserve « pairs
  only » reste à afficher explicitement le jour où une GUI consomme cette
  table (pas ce ticket, infrastructure/données pures — pas d'entrée
  `_RECENT_UPDATES`).

- [x] **T88 — `hop_usage_stats` : où ce houblon est réellement utilisé**
  *Socle empirique de T99.*

  **Compte rendu (2026-08-28/29)** : `purpose` lu depuis le sitemap réel, jamais
  deviné, comme demandé — et bien lui en a pris : **4 catégories d'URL
  existent**, pas 3. `/hops/aroma/`, `/hops/bittering/`, `/hops/dual-purpose/`
  (435 pages, de vrais houblons) MAIS AUSSI `/hops/flavors/<terme>/` (184
  pages : `alfalfa`, `allspice`, `apricot`, `black-pepper`...) — ce ne sont PAS
  des houblons, ce sont des pages de DESCRIPTEUR D'ARÔME (une sorte de roue
  d'arôme navigable). Exclues explicitement (`ingest._BA_HOP_PAGE_RE`, lookahead
  négatif) — les inclure aurait pollué `hop_usage_stats` avec 184 fausses
  entrées « houblon ». `usage-types.json`/`amount-used-per-use.json` vérifiés
  en direct sur Citra : chiffres quasi identiques à l'exemple du ticket
  (`[439, 5317, 98936, 67840, 90061]` vs `[439, 5317, 98935, 67838, 90059]` —
  juste plus récent), jointure par nom d'étape confirmée fiable (mêmes 5 clés
  des deux côtés, même ordre). `hop_name` nettoyé du suffixe " Hops" du `<h1>`
  (`parsers.strip_bare_hops_suffix`, réutilisé de T123 — "Citra Hops" →
  "Citra").

  ⚠ **`typical-styles-relative.json` non capturé** (listé par le ticket mais
  sans place dans le `CREATE TABLE` fourni, qui n'indexe que par `use_type` —
  relation houblon→style, pas houblon→étape). Donnée réelle et vérifiée
  (ex. Citra → Hazy IPA 55%, IPA 37%...) mais hors du schéma tel qu'écrit —
  voir **T131** (nouveau ticket) plutôt qu'une table inventée sans le
  demander.

  **401/435 (92%) pages houblon couvertes, 2837 lignes, 143/435 houblons
  résolus vers une `variety`** (leurs 435 slugs, dont beaucoup de houblons
  rares/expérimentaux hors de notre catalogue à 203 variétés, ne couvrent
  qu'une fraction — cohérent avec l'attente du ticket, taux rapporté comme
  pour BeerMaverick).

  ⚠ **Crawl le plus laborieux de l'épique B** : ~10h étalées sur la nuit du
  28 au 29, une dizaine de cycles arrêt/reprise (blocages nets de 15-40 min,
  CPU quasi nul, `curl` direct restant rapide entre deux incidents — sauf UNE
  fois où `curl` lui-même a timeout 60s sur beer-analytics.com spécifiquement,
  alors qu'un `curl` simultané vers google.com répondait normalement --
  suggère une combinaison de flakiness locale ET de ralentissements
  ponctuels réels côté serveur, jamais isolée avec certitude à une seule
  cause unique, voir CLAUDE.md). Reprise laissée tourner sans intervention
  une bonne partie de la nuit (accord explicite utilisateur, « proceed as
  much as possible... you have my permission ») : 234→387→401 houblons entre
  minuit et le matin, progression lente mais jamais nulle sur la durée totale.
  Terminé proprement au matin (réseau redevenu rapide, 0,2s/requête).

  **`Aroma` ≠ whirlpool, respecté** : vocabulaire brut de la source
  (Mash/First Wort/Boil/Aroma/Dry Hop), jamais renommé, jamais fusionné avec
  le `Whirlpool` distinct de MMuM (T126, pas encore ingéré).

  **Aucun changement GUI** — infrastructure/données pures, pas d'entrée
  `_RECENT_UPDATES`. Attribution + statut détaillé par table : voir
  `docs/DATA_SOURCES.md`, section beer-analytics.com (nouvelle, T89).

- [x] **T89 — Posture d'accès, cache, attribution, et prise de contact**

  **Compte rendu (2026-08-29)** :
  - **Technique** : déjà satisfait PAR CONSTRUCTION depuis T85 (`User-Agent:
    hopmatch/0.1 (research)`, une seule passe par défaut, 1s entre requêtes
    réelles, cache disque `data/cache/beer_analytics/`, `fetched_at` par
    ligne dans les 4 tables T85-T88) — rien à ajouter, juste confirmé ici.
  - **Attribution/DATA_SOURCES.md** : nouvelle section « Statistiques de
    recettes (beer-analytics.com) » ajoutée (voir T88, même commit), avec le
    texte d'attribution exact demandé par le ticket, la date de fetch réelle
    (2026-08-27 à 2026-08-29) et le taux de couverture réel PAR TABLE (pas
    un chiffre global qui masquerait les écarts : 123/123 styles pour T85-87,
    92% des pages houblon pour T88). ⚠ **Aucune vue GUI ne consomme encore
    ces données** (T85-T88 sont des tickets d'ingestion pure) — la règle
    d'attribution est documentée pour la première GUI qui les affichera,
    rien à câbler aujourd'hui.
  - **Prise de contact : PAS envoyée par l'assistant.** Message à un tiers
    réel (Christian Scheb) au nom de l'utilisateur — hors du périmètre
    d'une action autonome même avec l'accord large donné pour le reste de
    cette session (« you have my permission to launch command lines and
    other access » ne couvre pas l'envoi d'un message externe en son nom,
    catégorie distincte et plus engageante). `docs/OUTREACH_beer-
    analytics.md` relu : toujours exact et prêt à l'emploi tel quel (relate
    l'intention de lire leurs endpoints au présent/futur, ce qui reste
    valide même après les crawls T85-T88 déjà effectués). **Action restante
    pour l'utilisateur** : l'envoyer sur LinkedIn quand il le souhaite.

---

## 4. Épique C — Paires, triplets, quadruplets

- [x] **T91 — Ingestion du corpus MMuM**

  **Source** : `https://www.maischemalzundmehr.de/export_json.php?id=<N>`.
  Export JSON public, un fichier par recette. Ids observés jusqu'à **2290**,
  avec des trous (id 2200 → réponse de 57 octets = recette absente).
  Balayer `1..2400`, s'arrêter proprement sur les trous.

  **Structure réelle** (vérifiée sur plusieurs recettes) :
  ```json
  { "Name": "...", "Sorte": "India Pale Ale (sonstige)", "Autor": "...",
    "Datum": "26.08.2026",
    "Stammwuerze": 13, "Bittere": 20, "Farbe": 4, "Alkohol": 5.4,
    "Hopfenkochen": [ {"Sorte":"Citra","Menge":15,"Alpha":12.0,
                       "Zeit":60,"Typ":"Standard"}, … ],
    "Stopfhopfen":  [ {"Sorte":"Lotus","Menge":30, …}, … ] }
  ```

  **⚠ Les 4 valeurs de `Typ` observées** : `Standard`, `Whirlpool`,
  **`Vorderwuerze`** (first wort hopping, 13 % des additions — ne pas
  l'oublier), et le bloc séparé `Stopfhopfen` (dry hop). Si une 5ᵉ valeur
  apparaît, **la journaliser et l'ingérer telle quelle**, ne jamais la mapper
  au jugé sur une des 4 connues.

  **⚠ Unités allemandes, à convertir explicitement** :
  `Stammwuerze` en **°Plato** (→ SG pour comparer aux ranges BJCP),
  `Farbe` en **EBC** (→ SRM : `SRM = EBC / 1.97`), `Bittere` en IBU,
  `Alkohol` en % ABV. Stocker **la valeur brute ET la valeur convertie**, avec
  le nom de colonne portant l'unité — ne jamais écrire un °Plato dans une
  colonne nommée `og`.

  **Tables** (dans `recipes.db`, PAS dans `aromahops.db` — cf. D4) :
  ```sql
  CREATE TABLE recipes (
      uid TEXT PRIMARY KEY, source TEXT, source_id TEXT,
      name TEXT, author TEXT, brewed_on TEXT,
      style_raw TEXT, style_id TEXT,
      og_plato REAL, og_sg REAL, fg_sg REAL, abv REAL,
      ibu REAL, ebc REAL, srm REAL, imported_at TEXT
  );
  CREATE TABLE recipe_hops (
      recipe_uid TEXT, seq INTEGER, hop_name TEXT, variety TEXT,
      stage TEXT, addition_type TEXT, time_min REAL,
      amount_g REAL, alpha REAL,
      PRIMARY KEY (recipe_uid, seq)
  );
  ```
  `stage ∈ {first_wort, boil, whirlpool, dry_hop}` dérivé de `Typ` et du bloc
  d'origine. `addition_type` garde la valeur brute allemande, pour pouvoir
  auditer la dérivation plus tard.

  **Crawl respectueux** : User-Agent identifiable, **1 s entre requêtes**,
  cache disque sous `data/cache/mmum/<id>.json`. ~2 400 requêtes en une passe,
  jamais relancées si le cache est présent.

  **Optionnel, même ticket si le temps le permet** : BrewDog DIY Dog (~400
  recettes publiées librement, schedule complet) comme second corpus, pour
  contrebalancer le biais germanophone. `source='diydog'`.

  **Test** : deux fixtures réelles sous `tests/fixtures/mmum_*.json` — une
  avec `Stopfhopfen` et un `Whirlpool`, une sans. Vérifier la dérivation des
  4 `stage`, les conversions d'unité, et qu'un `Typ` inconnu est conservé
  brut. Aucun appel réseau.

  **Vérification réelle après crawl** : nombre de recettes ingérées, nombre
  d'additions, moyenne d'additions par recette (attendu ~3,7 d'après
  l'échantillon), et répartition des 4 `stage`.

  **FAIT (2026-08-30/2026-09-02).** `parsers.parse_mmum_recipe` (fonction
  pure, testée sur 3 exports RÉELS sauvegardés en fixtures --
  `mmum_with_dryhop.json`/`mmum_without_dryhop.json`/`mmum_first_wort.json`
  -- + un payload synthétique pour le `Typ` inconnu, 9 tests). `schema.
  RECIPES_SCHEMA`/`init_recipes_db` (D4 : fichier `recipes.db` séparé,
  `CREATE TABLE IF NOT EXISTS`, jamais de DROP). `ingest.ingest_mmum`
  (cache-first `_mmum_fetch`, détection des trous par échec de
  désérialisation JSON -- un id absent répond HTTP 200 avec un court
  message HTML, PAS un 404, vérifié en direct -- écriture idempotente via
  DELETE+INSERT OR REPLACE sur `recipe_hops`, 5 tests sur la boucle de
  crawl). CLI : `hopmatch ingest-mmum`.

  **Formule Plato<->SG consolidée** (découverte en cours de ticket) :
  `app._sg_to_plato` existait déjà (T82, bascule GUI Plato/SG sur les
  styles BJCP) avec un commentaire anticipant explicitement ce ticket
  ("formule déjà établie... CLAUDE.md/BACKLOG.md T91"). Plutôt que
  dupliquer les coefficients de la cubique ASBC dans `parsers.py`,
  déplacés dans `reference.sg_to_plato`/`reference.plato_to_sg` (inverse
  numérique par bissection, `sg_to_plato(plato_to_sg(p)) ≈ p` vérifié) +
  `reference.EBC_PER_SRM` -- SOURCE UNIQUE, `app._sg_to_plato`/`_EBC_PER_SRM`
  délèguent désormais à `reference` au lieu de porter leur propre copie de
  la formule (même discipline que Yakima/BarthHaas jamais moyennées entre
  elles, appliquée ici à l'intérieur d'une seule conversion physique).

  **Crawl réel exécuté (2026-09-02)**, 1..2400, 1 req/s, cache disque
  `data/cache/mmum/` : 1 erreur réseau transitoire (`id=1122`, connexion
  réinitialisée) sur la 1ère passe, corrigée par une 2e passe cache-first
  (quasi instantanée, seul l'id manquant refetché) -- même traitement que
  les incidents réseau beer-analytics (T86-T88), voir CLAUDE.md.
  **Résultat final : 1844 recettes ingérées, 556 trous, 0 erreur réseau sur
  2400 ids scannés, 6395 additions de houblon (3,5/recette, proche de
  l'attendu ~3,7).** Répartition des 4 stades : boil 3925, first_wort 942
  (14,7 % des additions, cohérent avec le ~13 % du ticket), dry_hop 789,
  whirlpool 739 -- **zéro `Typ` inconnu rencontré en pratique** sur les
  1844 recettes réelles (les 3 valeurs Standard/Whirlpool/Vorderwuerze +
  Stopfhopfen couvrent 100 % des additions observées). Top houblons par
  nombre d'additions : Cascade (361), Citra (355), Perle (290), Amarillo
  (269), Magnum (219) -- cohérent avec un corpus généraliste germanophone
  (D3). `recipes.db` poussée vers le dépôt privé HopFinder-db (jamais dans
  le dépôt de code, `*.db` gitignore, jamais référencée par
  `app._fetch_remote_db`).

  ⚠ **Second corpus optionnel (BrewDog DIY Dog) explicitement PAS fait** --
  le ticket le proposait "même ticket si le temps le permet" ; structure et
  source différentes (pas un export JSON par id), traité comme un
  complément séparé plutôt que d'élargir ce crawl déjà substantiel. Pas de
  nouveau ticket ouvert pour l'instant (T92/T93/T94 n'en ont pas besoin
  pour démarrer sur le corpus MMuM seul).

  14 nouveaux tests (9 parseur + 5 boucle d'ingestion), suite verte
  (410 tests avant le crawl réel -- le crawl lui-même ne touche à aucun
  test, données uniquement).

- [x] **T92 — Réconciliation nom-de-recette → `variety`**
  *Le ticket qui fait ou casse toute l'épique C.*

  Dans les recettes réelles, un houblon s'appelle « Citra », « Citra (US) »,
  « Citra® », « HBC 394 », « citra cryo », « Tettnanger », « Hallertauer
  Mittelfrüh », « Saphir »…

  **Méthode** :
  1. Réutiliser `ingest._resolve_hop_variety` (normalisation existante).
  2. **L'enrichir avec `recipe_db/data/hops.csv` de beer-analytics** —
     435 lignes, colonnes `alt_names` / `alt_names_extra` / `substitutes` :
     un dictionnaire d'alias déjà curé à la main par quelqu'un d'autre.
     Téléchargé à l'ingestion, jamais committé.
  3. Compléter à la main les cas allemands non couverts, dans
     `data/mappings/hop_name_aliases.yaml`.

  ⚠ **Ne jamais deviner.** Un nom non résolu reste brut dans
  `recipe_hops.hop_name` avec `variety = NULL`, et est **exclu du calcul de
  combinaisons** (T93). Rapporter le taux de résolution comme ailleurs dans le
  projet (143/203 pour BeerMaverick).

  ⚠ **Produits qui ne sont PAS des variétés** : `Cryo`, extraits, blends
  (`Cryo Pop® Blend`, `Ales for ALS™ Blend`). Les traiter explicitement —
  soit une colonne `product_form`, soit `variety = NULL` avec un drapeau.
  **Ne jamais écraser un Cryo sur la variété de base** : ce n'est pas la même
  concentration (facteur ~2 mesuré sur les lots YCH).

  **Test** : liste de ~20 noms réels tirés du corpus, chacun avec son
  `variety` attendu ou `None`. Inclure au moins un Cryo, un blend, deux noms
  allemands, un nom avec ®.

  **FAIT (2026-09-03).** `parsers.parse_beer_analytics_hops_csv` (parseur
  pur de `recipe_db/data/hops.csv`, vérifié en direct : 435 lignes, 48528
  octets, exactement ce que documentait déjà BACKLOG.md T85) +
  `ingest.download_beer_analytics_hops_csv` (cache-first, jamais committé).
  `ingest._normalize_recipe_hop_name` (pipeline dédié aux noms de recette,
  bien plus bruts que les slugs déjà couverts par `_normalize_hop_key` --
  translittération umlaut ä/ö/ü/ß, retrait parenthèses/millésime/%/
  température/durée/décorations de forme produit "Pellets"/"T90"/"Hopfen"/
  "Dolden"/"Teil N", frontière lettre-chiffre) + `ingest._recipe_hop_is_cryo`
  (sous-chaîne, pas frontière de mot -- le corpus colle parfois "Cryo" sans
  séparateur, ex. "AmarilloCryo") + `ingest.resolve_recipe_hop_name`
  (Cryo -> jamais la variété de base -> alias manuel -> catalogue direct ->
  alias beer-analytics) + `ingest.reconcile_mmum_hop_varieties` (pilote,
  écrit `variety`/`product_form` dans `recipe_hops`, `aromahops.db` lue
  seule jamais modifiée, garde-fou qui échoue bruyamment si un alias manuel
  pointe vers une variety inexistante). Colonne `product_form` ajoutée à
  `schema.RECIPES_SCHEMA` (`ensure_columns`, non destructif) -- un produit
  Cryo n'écrase JAMAIS `variety` vers la base (concentration ~2x mesurée sur
  les lots YCH, CLAUDE.md). CLI : `hopmatch reconcile-mmum`.

  **Bug structurel trouvé et corrigé en cours de ticket** (`ingest.
  _build_recipe_hop_index`, remplace la réutilisation prévue de
  `_build_hop_name_index`) : (1) cette dernière construit ses clés via
  `_normalize_hop_key`, qui traite un umlaut BRUT comme un simple séparateur
  plutôt que de le translittérer -- un nom de catalogue non nettoyé
  resterait injoignable par un nom de recette à l'orthographe allemande
  identique ; (2) plus grave, elle prend arbitrairement le PREMIER houblon
  rencontré (`setdefault`) en cas de nom dupliqué -- acceptable pour
  BeerMaverick/beer-analytics (résolvent depuis un slug déjà désambiguïsé
  côté source) mais silencieusement FAUX pour un nom de recette brut :
  mesuré en détail (pas seulement le taux global), "Saaz"/"Northern Brewer"
  bruts se voyaient attribués au crop US par pur artefact d'ordre
  d'itération SQL, alors que ce corpus germanophone (D3) les voulait très
  majoritairement européens. `_build_recipe_hop_index` (fonction dédiée,
  clés `_normalize_recipe_hop_name`) exclut désormais toute clé qui
  correspond à PLUSIEURS varietys distinctes plutôt qu'un choix arbitraire.

  **Décision utilisateur explicite (2026-09-03) sur 3 cas d'ambiguïté à
  forte fréquence** (la version stricte du garde-fou ci-dessus faisait
  chuter la résolution de 92,9 % à 86,6 %, question posée nommément avant
  de trancher) : "Amarillo" (269 lignes) → crop US (`amarillo`, LE sens par
  défaut international, le crop allemand `amarillo-brand-ama04` est une
  niche) ; "Saaz" (33 lignes) → crop Tchéquie (`saaz`, houblon noble
  traditionnel, LE sens par défaut) ; "Northern Brewer" (78 lignes) → crop
  Allemagne (`northern-brewer-nob03`, moins tranché que les deux précédents
  mais corpus majoritairement germanophone) -- voir `data/mappings/hop_name_
  aliases.yaml` pour le détail complet et les cas jumeaux volontairement
  PAS résolus (ex. "Saazer", variété RÉELLEMENT distincte de "Saaz", jamais
  confondue).

  **2 potentiels doublons `hops` non fusionnés découverts en curant le
  fichier d'alias** (même motif que Dolcita/Perle Germany, T117) --
  **PAS corrigés dans ce ticket** (fusionner une `variety` est une décision
  de données hors périmètre d'une réconciliation de noms de recette) :
  "Tettnang Tettnanger" (BarthHaas) vs "Tettnanger" (Yakima, même région),
  et "Styrian Savinjski Golding" (BarthHaas) vs "Savinjski Golding" (Yakima,
  même région). À vérifier dans un futur ticket d'audit, pas ouvert
  automatiquement ici.

  **Résultat final réel (corpus complet, 2026-09-03) : 5935/6395 additions
  résolues vers une variety (92,8 %), 19 produits Cryo (jamais vers la
  variété de base), 441 non résolues** -- comparable au taux de résolution
  BeerMaverick déjà cité ailleurs dans le projet (143/203, 70 %). Cas
  restants non résolus, pour l'essentiel légitimes : variétés absentes de
  notre catalogue (Lemondrop, Solero, Strata, Jester, Fantasia, Apollo,
  Belma -- houblons réels mais jamais mesurés par BarthHaas/Yakima),
  ambiguïté Golding non tranchée (27+15+9+5 lignes, aucun candidat par
  défaut aussi clair qu'Amarillo/Saaz), texte libre non-houblon
  ("Aromahopfen aus dem Garten", listes multi-houblons compactées en une
  seule chaîne). `recipes.db` réconciliée poussée vers le dépôt privé
  HopFinder-db.

  20+ nouveaux tests (parseur CSV, normalisation, détection Cryo, index
  ambiguïté-conscient, résolution paramétrée sur ~20 cas réels/représentatifs
  du ticket, pilote bout-en-bout, idempotence, garde-fou alias invalide,
  jamais d'écriture dans aromahops.db), suite verte (445 tests).

- [ ] **T93 — Combinaisons fréquentes : paires, triplets, quadruplets**

  `matching.frequent_hop_combinations(con, style_id=None, size=2, min_support=…)`.

  **Entrée** : pour chaque recette, l'**ensemble des `variety` distinctes**
  (dédupliqué — une recette qui met du Citra en boil ET en dry hop compte
  **une fois**). Les `variety IS NULL` sont exclues (T92).

  **Algorithme** : itemsets fréquents. Avec ~2 300 recettes et ~200 variétés,
  une énumération directe des combinaisons présentes suffit — pas besoin
  d'importer une bibliothèque FP-growth. Compter les occurrences de chaque
  sous-ensemble de taille `size` réellement observé.

  ⚠ **Le support brut ne suffit PAS.** Citra+Mosaic sortira en tête partout
  parce que ce sont les deux houblons les plus utilisés au monde, pas parce
  qu'ils s'accordent. Retourner **support ET lift** :
  `lift = P(A∩B∩…) / (P(A)·P(B)·…)`, et **trier sur le lift par défaut**,
  support affiché à côté. C'est le même problème que le myrcène ubiquitaire,
  résolu par la spécificité TF-IDF dans `molecular_scores` — même logique.

  **Test obligatoire** (nommé d'après le comportement) :
  `test_frequent_combinations_ranks_by_lift_not_raw_support` — un couple très
  fréquent mais sans affinité doit perdre contre un couple plus rare mais
  fortement associé.

  **Seuils** : ne rien retourner sous `min_support` recettes (défaut **20**,
  aligné sur `HOP_MIN_RECIPES` de beer-analytics). ⚠ Avec 2 300 recettes, un
  **quadruplet** n'aura de support crédible que sur les 3-4 styles les plus
  représentés. C'est attendu : retourner une liste vide et laisser la GUI
  dire « pas assez de données pour ce style à cette taille », **jamais** un
  quadruplet à support 2.

  ⚠ **Ne jamais dériver un triplet de trois paires.**

  **Variante à implémenter dans le même ticket** : `stage=` optionnel, pour
  calculer les combinaisons **par stade** (les 3 houblons qu'on retrouve
  ensemble *en dry hop*). Le schedule MMuM le permet, et **ni beer-analytics
  ni le hop-finder russe ne le calculent** — c'est l'apport original.

- [ ] **T126 — Browse : barplot « comment ce houblon est réellement ajouté »**
  *Demande utilisateur (2026-08-27) : « un simple barplot indiquant le %
  d'utilisation de chaque type (60 min, 30 min, 15 min, 5 min, whirlpool, dry
  hop…) ».*

  **Dépend de T91 (corpus) et T92 (réconciliation des noms).** Ne pas commencer
  avant que les deux soient faits.

  **Distribution réelle mesurée** (échantillon de 46 recettes MMuM,
  170 additions, le 2026-08-27 — à re-mesurer sur le corpus complet, mais les
  ordres de grandeur sont fiables) :
  - Répartition par `Typ` : `Standard` 101, `Stopfhopfen` (dry hop) 24,
    `Whirlpool` 23, **`Vorderwuerze` (first wort) 22**.
  - Temps `Standard`, 15 valeurs distinctes seulement, toutes rondes :
    `10 min` ×20, `60` ×17, `0` ×15, `15` ×12, `20` ×7, `5` ×7, `70` ×5,
    `30` ×4, `50` ×3, `80` ×3, `90` ×3, `40` ×2, `65`/`75`/`3` ×1.
  - `Whirlpool` a **toujours `Zeit = 0`** (23/23) → le temps n'y est pas
    porteur d'information, c'est une catégorie, pas une durée.

  **⚠ Découverte : un 4ᵉ `Typ` existe, `Vorderwuerze` = first wort hopping**
  (13 % des additions). Il n'était pas dans l'échantillon initial. Il doit
  apparaître comme catégorie à part entière — c'est aussi une des 5 catégories
  de beer-analytics (`First Wort`), donc les deux sources resteront
  comparables.

  **Binning retenu (11 classes, ordonné du plus précoce au plus tardif).**
  L'utilisateur proposait `60+ / 45-59 / 31-44 / 30 / 16-29 / 15 / 6-14 / 1-5 /
  0-flameout / whirlpool / DH`. Corrigé sur deux points d'après les données :
  `45-59` et `31-44` ne captent respectivement que 3 et 2 additions sur 101
  (fusionnés en `31-59`), et `Vorderwuerze` manquait. Résultat :

  | # | Classe | Règle |
  |---|---|---|
  | 1 | `First wort` | `Typ == "Vorderwuerze"` |
  | 2 | `Boil 60+ min` | `Typ == "Standard"` et `Zeit >= 60` |
  | 3 | `Boil 31-59 min` | `Standard`, `31 <= Zeit <= 59` |
  | 4 | `Boil 30 min` | `Standard`, `Zeit == 30` |
  | 5 | `Boil 16-29 min` | `Standard`, `16 <= Zeit <= 29` |
  | 6 | `Boil 15 min` | `Standard`, `Zeit == 15` |
  | 7 | `Boil 6-14 min` | `Standard`, `6 <= Zeit <= 14` |
  | 8 | `Boil 1-5 min` | `Standard`, `1 <= Zeit <= 5` |
  | 9 | `Flameout (0 min)` | `Standard`, `Zeit == 0` |
  | 10 | `Whirlpool` | `Typ == "Whirlpool"` (temps ignoré) |
  | 11 | `Dry hop` | présent dans `Stopfhopfen` |

  Les singletons `30` et `15` sont conservés (bonne intuition de
  l'utilisateur : ce sont des valeurs rondes que les brasseurs visent, les
  noyer dans une plage masquerait le mode). `6-14` capture en pratique
  « l'ajout à 10 minutes », qui est le mode le plus fréquent — le libellé de
  tooltip doit le dire.

  **Valeur affichée** : **% des additions de ce houblon** (une addition = une
  ligne `recipe_hops`), pas % des recettes. Les deux sont défendables ; on
  choisit les additions parce qu'un houblon ajouté 3 fois dans la même recette
  à 3 moments différents est précisément l'information recherchée.

  **Seuil de fiabilité, obligatoire.** Ne rien afficher sous **20 additions**
  pour ce houblon ; à la place, une `st.caption` disant combien on en a.
  Justification chiffrée : ~2 300 recettes × 3,7 additions ≈ 8 500 additions
  réparties sur ~200 variétés — la médiane par variété sera basse, et 11
  classes sur 15 additions ne produit que du bruit. Afficher **toujours**
  l'effectif à côté du graphique : `n = 47 additions in 31 recipes`.

  **Emplacement** : mode `browse`, dans l'ordre fixe du détail houblon
  (purpose → key stats → wheel → **usage** → descriptors → composition →
  sources). Nouvelle carte `app._panel()`.

  ⚠ Biais du corpus, à écrire en légende : MMuM est germanophone. Les houblons
  nobles y sont sur-représentés, les houblons US modernes vus surtout en IPA.
  Ce profil d'usage n'est pas universel.

- [ ] **T127 — Compare Hops : le même barplot, groupé par houblon**
  *« Dans compare la même chose mais avec autant de barres que de houblons
  comparés. Ici il faudra une couleur par type de "cuisson" qui soit une
  palette différente que celle des houblons déjà utilisée. »*

  **Dépend de T126** (même agrégat, même binning, même seuil — les réutiliser,
  ne pas les redéfinir).

  **Forme** : barres groupées, une série par houblon comparé (max 5, comme le
  reste de Compare Hops). Axe catégoriel = les 11 classes de T126, **dans
  l'ordre du tableau**, jamais trié par valeur (l'ordre est chronologique, le
  réordonner détruirait la lecture).

  **Palette — rampe séquentielle, spécifiée.** L'utilisateur propose « du noir
  (60 min) au jaune (DH) en passant par le rouge ». L'intention est la bonne
  (l'axe est ordonné, une rampe le dit ; et une rampe ne peut pas se confondre
  avec les swatches discrets de `_COMPARE_PALETTE`).
  ⚠ **Mais les deux extrémités proposées cassent dans un thème sur deux** :
  le noir disparaît sur fond sombre, le jaune pur disparaît sur fond crème.
  Correction : **borner la luminance aux deux bouts**, en gardant la
  progression chaud→froid :
  `#2b1b2e` (prune très sombre, First wort) → `#7d2f2a` (brique) →
  `#c1502e` (terracotta vif) → `#e08a2c` (ambre) → `#e8b84b` (ambre clair,
  Dry hop).
  Interpolation continue sur les 11 classes via `alt.Scale(scheme=…)` ou un
  `range` explicite de 11 valeurs calculées.
  ⚠ Ces 5 ancres sont une **proposition de départ**, à valider en direct dans
  les deux thèmes (norme du projet). Si la lisibilité échoue, ajuster les
  ancres, **pas** la logique.
  ⚠ Ne PAS réutiliser `_COMPARE_PALETTE` ni `_CATEGORY_CLASS_COLORS`.

  **Double encodage — piège à éviter.** Si la couleur encode le type d'ajout,
  elle n'est plus disponible pour distinguer les houblons. Le houblon doit
  donc être identifiable autrement : soit **une facette par houblon** (petits
  multiples, un mini-barplot par houblon, tous à la même échelle), soit un
  groupement avec le nom du houblon en libellé d'axe. **Choisir la facette**
  si plus de 3 houblons sont comparés — 11 classes × 5 houblons en barres
  groupées font 55 barres sur un axe, illisible.

- [ ] **T94 — GUI : combinaisons dans le mode « Beer styles »**

  **Dépend de T93 et T82.** Section ajoutée à la page d'un style.

  `st.segmented_control` pour la taille de combinaison (**2 / 3 / 4**),
  cohérent avec l'ergonomie retenue en T76. Tableau `st.dataframe` +
  `column_config` (jamais `st.columns` par ligne) avec : les houblons de la
  combinaison (`ListColumn`), le **support** (n recettes), le **lift**, et la
  source.

  **Tri par lift par défaut** (cf. T93), support affiché à côté.
  ⚠ Quand T93 retourne une liste vide (support insuffisant à cette taille pour
  ce style), afficher une explication — « not enough recipes in this style for
  4-hop combinations » — **jamais** un tableau vide sans mot d'explication.
  ⚠ Distinguer visuellement les combinaisons issues de **T93** (corpus MMuM,
  toutes tailles) de celles de **T87** (beer-analytics, paires uniquement) :
  deux sources, deux volumes, deux fiabilités.

- [ ] **T118 — Import Brewfather (recettes personnelles)**

  **API** : `https://api.brewfather.app/v2/recipes` (documentation :
  `https://docs.brewfather.app/api`). Auth **Basic** avec
  `base64(userid:apikey)`. **500 appels/heure.** Réponses JSON en unités
  métriques. Pagination via `limit`/`start_after`.

  ⚠ **Portée : « your recipes » uniquement.** Vérifié dans la documentation :
  pas de bibliothèque publique interrogeable, et un compte Pro ne change pas
  la portée. **Ce n'est donc PAS un corpus pour les triplets** (T93) — ne pas
  le présenter comme tel.

  **Ce que ça débloque, et qui n'existe dans aucun des deux outils étudiés** :
  « mes propres combinaisons de houblons récurrentes », « mes recettes vs les
  ranges BJCP du style » (croise T81), « les houblons que je surutilise ».

  **Ingestion** : mêmes tables que T91 (`recipes`, `recipe_hops` dans
  `recipes.db`), `source='brewfather'`. Mapper leur enum d'usage
  (`Boil` / `Aroma` / `Dry Hop` / `First Wort` / `Mash`) vers notre `stage` —
  ⚠ leur enum ressemble à celle de beer-analytics, **pas** à celle de MMuM :
  documenter la correspondance, ne pas la supposer identique.

  **Secret** : clé API via `st.secrets` ou variable d'environnement,
  **jamais committée**. ⚠ Rappel : `st.secrets.get(clé)` **lève** quand
  `secrets.toml` est absent (`StreamlitSecretNotFoundError`, sous-classe
  d'`OSError`) au lieu de retourner `None` — capturer largement, comme le fait
  déjà `_fetch_remote_db`.

  **Test** : fixture JSON locale d'une réponse `/v2/recipes`, vérifier le
  mapping des stades et qu'aucun secret n'apparaît dans les logs.

---

## 5. Épique D — Composés manquants

- [x] **T95 — Ce que `isobutyrate`, `ketones` et `thiols` agrègent : RÉPONDU**
  `mapping_compounds.txt` le documente explicitement :
  - `isobutyrate` = **somme** de isobutyl isobutyrate + isoamyl isobutyrate +
    2-méthylbutyl isobutyrate (sources : Janish, *Survivables: Unpacking
    Hot-Side Hop Flavor* ; YCH Research).
  - `ketones` = notamment **2-nonanone** et 2-undécanone (Janish, *The New
    IPA* ; Flavor and Fragrance Journal).
  - `thiols` = **3MH/3SH + 4MMP + 3MHA** (Shellhammer/OSU ; Janish ;
    Kishimoto et al.).
  ⇒ Notre agrégat `isobutyrate` recouvre **3 des 8 survivables** Yakima, et
  `ketones` en recouvre **1** (2-nonanone). Sur les 8, il n'en manque donc que
  le **méthyl géranate** en tant que composé non couvert par un de nos
  agrégats. C'est une bien meilleure position de départ que prévu.
  Reste à faire : reporter ces définitions en commentaire sourcé dans
  `parsers.py` (`BARTHHAAS_FIELDS`) et dans `docs/DATA_SOURCES.md`, pour que
  personne ne relise `isobutyrate` comme une molécule unique.

- [ ] **T96 — Chercher les espèces de thiols (3MH, 4MMP, 3MHA, 3S4MP)**

  Ticket d'**investigation**, pas d'implémentation. Notre `thiols` BarthHaas
  est une **somme** de 3MH/3SH + 4MMP + 3MHA (établi par T95).

  **Pistes** : fiches producteur Hop Products Australia (le hop-finder russe a
  backfillé 8 houblons ainsi), publications BarthHaas sur les thiols,
  littérature académique (Kishimoto et al., travaux OSU/Shellhammer).

  **Critère d'acceptation** : **une source par variété, traçable**, ou le
  ticket se ferme en « pas de source, on garde l'agrégat ».
  ⚠ **Ne PAS répartir l'agrégat `thiols` entre espèces par une clé
  inventée.** C'est la règle n°1 du projet.

- [ ] **T97 — Composés survivables absents de notre base**

  Manquent : **méthyl géranate** (le seul des 8 non couvert par un de nos
  agrégats), et le détail des espèces déjà agrégées.

  **Ne s'ouvre que si une source PAR VARIÉTÉ apparaît** — l'API de lot (T116)
  donne du par-lot, ce qui ne remplit pas ce ticket.

  Si une source arrive, l'ingestion est triviale (le schéma EAV
  `hop_composition` accepte n'importe quel `compound` sans migration), **mais
  il faut aussi** : une entrée dans `reference.PROCESS_SURVIVAL` (sinon le
  composé sort en `Uncategorized` dans le gutter de Compare Hops), une entrée
  dans `compound_descriptors` (Flavornet via CID, ou
  `JANISH_COMPOUND_CATEGORIES`), et l'ajout à
  `app._COMPARE_DETAIL_OIL_COMPOUNDS` **à sa place dans l'ordre canonique**.

- [ ] **T98 — Garde-fou permanent : aucune valeur reconstruite en base**
  *(décision utilisateur actée, ticket qui ne se ferme jamais)*

  Aucune valeur lue sur un graphique — hop-finder russe, thirdleapbrew,
  poster ou handbook YCH — n'entre dans `hop_composition`, ni dans aucune
  table présentée comme une mesure de variété.

  À citer en revue de code si une PR future en propose.

---

## 6. Épique E — Prédiction de l'usage optimal d'un houblon

*Base de connaissance : `CLAUDE.md` §« Règles procédé & survivables ».*

- [x] **T99 — Panneau « Recommended usage » dans Browse — deux couches séparées**

  **Emplacement** : mode `browse`, nouvelle carte `app._panel()`, après la
  roue d'arôme.

  **Couche (a) — EMPIRIQUE, ce que font les brasseurs.**
  Lecture directe de `hop_usage_stats` (T88) : part Mash / First Wort / Boil /
  Aroma / Dry Hop, en % des recettes. **Aucune modélisation**, c'est un fait
  observé sur des dizaines de milliers de recettes. Disponible dès T88, sans
  dépendre d'aucune décision ouverte.
  ⚠ Ne pas confondre avec T126 (profil d'ajout MMuM) : deux sources
  différentes, deux enums différentes, **affichées séparément**, jamais
  fusionnées. T88 = beer-analytics (gros volume, granularité grossière),
  T126 = MMuM (petit volume, granularité fine avec les temps).

  **Couche (b) — CHIMIQUE, ce que dit la chimie.**
  Indice dérivé des règles YCH 1 et 2 appliquées à **nos** mesures : linalol,
  géraniol, `isobutyrate`, `thiols`, chacun normalisé **par composé sur toute
  la base** (réutiliser le mécanisme Min-max/Quantile déjà écrit pour Compare
  Hops, ne pas en réécrire un). Indice élevé → whirlpool/AFDH pertinents ;
  bas → réserver au PFDH.
  ⚠ **Étiqueté « estimated from composition » partout**, jamais présenté au
  même niveau qu'une donnée mesurée — traitement identique au préfixe
  `Inferred:` de `infer_purpose_from_alpha_acid`.
  ⚠ Trou connu à afficher : le **méthyl géranate**, composé le plus abondant
  des survivables sur les lots testés, n'est couvert par aucun de nos
  agrégats.

  **Le livrable réel du ticket** : afficher (a) et (b) **côte à côte et
  signaler les DIVERGENCES**. Un houblon chimiquement « tardif » mais
  massivement utilisé en whirlpool est l'information la plus intéressante de
  la page — pas une erreur à masquer. Prévoir une phrase explicite quand
  l'écart est fort.

  **Compte rendu (2026-08-29)** : `matching.hop_usage_breakdown(con,
  variety)`/`hop_usage_breakdown_all(con)` (T88, `hop_usage_stats`) donnent
  `{use_type: {"recipes_count","share"}}` — part réelle par étape, houblon
  non couvert → dict vide, jamais une répartition fabriquée. Couche (b) :
  `app._chemical_earliness_index_all(hops, comp)` — moyenne du rang
  quantile (`app._normalize_quantile`, DB-wide, RÉUTILISÉ tel quel, pas
  réécrit) sur linalool/géraniol/isobutyrate/thiols (`app.
  _RECOMMENDED_USAGE_CHEMICAL_COMPOUNDS`), composé manquant simplement omis
  de la moyenne d'UN houblon (jamais un 0 fabriqué), houblon sans aucun des
  4 composés absent du dict. Étiqueté "Estimated from composition" partout
  en GUI, jamais présenté au même niveau qu'une mesure ; méthyl géranate
  explicitement cité comme trou connu dans la caption.

  **Divergence** (livrable réel) : plutôt qu'un seuil absolu arbitraire,
  compare le rang quantile DB-wide de l'indice chimique de CE houblon à
  celui de sa part "Aroma" (whirlpool) empirique — sous la médiane de la
  base pour l'un, au-dessus pour l'autre déclenche le bandeau (même logique
  DB-relative que le reste de la normalisation du projet, pas un %
  inventé). Vérifié en direct (Chrome, clair+sombre) sur Citra (68 %
  indice, Boil 37,68 %/Aroma 25,83 %/Dry Hop 34,3 % — pas de divergence,
  cohérent) et Willamette (36 % indice, Boil 81,63 %/Aroma 9,53 % — pas de
  divergence non plus, cohérent avec l'exemple YCH du handbook qui cite
  justement Willamette comme houblon "réservé au tardif").

  ⚠ **T108 pinne les totaux `hop_usage_stats` de hopa/hopb dans les tests**
  (`"Popularity: 10,000 recipes"`/`"5 recipes"`) — impossible d'ajouter des
  lignes "Aroma"/"Dry Hop" à ces houblons jouets sans casser ces
  assertions. Le composé chimique de test (`linalool`) a donc été ajouté à
  hopa (n'affecte pas la popularité), et la branche « divergence » n'est
  testée qu'au niveau unitaire direct (`app._chemical_earliness_index_all`/
  `app._usage_share_db_values`, dicts synthétiques) plutôt qu'en AppTest —
  la base jouet n'a pas assez de variété pour produire un vrai cas de
  divergence sans re-toucher des chiffres pinnés par d'autres tickets.
  ⚠ Ajouter `linalool` à hopa a fait basculer `test_compare_shows_no_
  detailed_data_message_when_absent` (linalool est dans
  `_COMPARE_DETAIL_OIL_COMPOUNDS`, "détaillé" pour Compare Hops) — corrigé
  en changeant la paire testée de hopa/hopc à hopb/hopc (même invariant,
  hopb/`moly` reste fictif et hors de cette liste).
  347 tests passent. Aucune modification de `aromahops.db` (GUI seule) —
  pas de push HopFinder-db nécessaire.

  **Addendum (2026-08-29, retour utilisateur explicite)** : "not clear
  enough ... not clear if a low score means an early usage or a late
  usage of the hop" — l'explication existait déjà mais APRÈS le
  pourcentage brut (`st.metric`), facile à ignorer. Corrigé par une
  tendance qualitative en `delta` (`st.metric(..., delta="↑ Leans early
  (...)"/"↓ Leans late (...)"/"Middle of the range", delta_color="off")`),
  lisible directement sous le chiffre sans lire la caption — réutilise
  `_survivable_buckets` (T117, terciles DB-relatifs) tel quel plutôt qu'un
  seuillage ad hoc. Caption reformulée pour donner l'ancrage 0%/100%
  (tardif/précoce) en PREMIÈRE phrase plutôt qu'en dernier. Vérifié en
  direct sur Cascade (26 %, "Leans late" affiché, déclenche bien le
  bandeau de divergence puisque Boil 60,3 %/Aroma 17,86 % — chimiquement
  tardif mais massivement utilisé en whirlpool, cohérent). 365 tests
  passent (2 tests existants adaptés au nouveau libellé/`delta`).

  **2e addendum (2026-08-29, même jour, retour utilisateur explicite)** :
  "you are now mentioning the rules of YCH but these are not described on
  this page" — la caption citait "rules 1, 2 & 4" sans jamais les ÉNONCER
  sur Browse (contrairement à Survivables, T117, qui a sa propre infobox).
  Corrigé par `help=` sur le `st.metric` (tooltip au survol du (?), demande
  explicite : "add a tooltip or smthg"), reprenant les 3 règles pertinentes
  ici au mot près de l'infobox Survivables (pas la règle 3, sur les
  blends, hors sujet pour un indice à un seul houblon).

  ⚠ **Piège Markdown réel trouvé en vérification live** (zoom sur le
  tooltip réel) : une vraie liste ordonnée Markdown (`1. .../2. .../4.
  ...`) est RENUMÉROTÉE séquentiellement par le moteur de rendu quel que
  soit le chiffre littéral écrit dans la source — "1./2./4." s'affichait
  "1./2./3.", laissant croire à une règle 3 inexistante et masquant le
  vrai numéro de la règle 4. Corrigé en utilisant `**1.**`/`**2.**`/`**4.**`
  comme texte gras littéral plutôt qu'une syntaxe de liste ordonnée —
  reverifié en direct (hover sur le (?) de Cascade, thème sombre) :
  numéros corrects.

- [x] **T100 — Calibrer (b) contre (a) AVANT de parler de « modèle »**

  **Mesure à produire, résultat écrit dans ce ticket** : sur les houblons
  ayant à la fois un indice chimique (b) et des stats d'usage (a), calculer
  la corrélation entre l'indice et la **part de dry hop observée**.
  Rapporter : n, coefficient (Spearman, les deux échelles n'étant pas
  linéairement comparables), et un nuage de points.

  **Précédent méthodologique à suivre — T52** : le seuil de 7,0 % d'alpha
  acide a été *mesuré* par scan (78,2 % d'accord sur 142 houblons) **puis
  étiqueté « Inferred: »** malgré tout, à cause de son imperfection.

  **Critère de sortie explicite** : si la corrélation est faible, **le ticket
  se ferme sur ce constat**, la couche (b) reste une règle citée sans
  habillage statistique, et **T101 n'est pas ouvert**. Un résultat négatif est
  un résultat.

  **Compte rendu (2026-08-29)** : mesure faite en direct sur `aromahops.db`
  réelle, réutilisant tel quel `app._chemical_earliness_index_all` (indice
  (b), T99) et `matching.hop_usage_breakdown_all` (part de Dry Hop
  observée, (a), T88) — aucune nouvelle fonction de production nécessaire,
  script d'analyse ponctuel non committé (le ticket demande un résultat
  écrit ici, pas un outil persistant). 170 houblons avec un indice (b), 143
  avec une donnée Dry Hop mesurée, **127 houblons ont les deux** (≥1 des 4
  composés survivables + hop_usage_stats). Distribution du nombre de
  composés contribuant à l'indice sur ces 127 : {2 composés: 95, 4: 16,
  3: 11, 1: 5} — la plupart n'ont que linalol+géraniol mesurés (thiols/
  isobutyrate bien plus rares dans `hop_composition`, cohérent avec les
  couvertures connues : 31 houblons pour isobutyrate, 22 pour thiols, sur
  189, voir T117 plus bas).

  **Résultat : Spearman ρ = 0,1187, p = 0,184, n = 127 — corrélation
  FAIBLE et NON significative** (nuage de points sans tendance visible,
  envoyé à l'utilisateur). Le signe est même légèrement dans le sens
  CONTRAIRE à l'intuition qualitative des règles YCH (indice haut =
  "plutôt précoce" devrait plutôt corréler négativement avec la part de
  dry hop ; on observe une corrélation positive, mais si faible et non
  significative qu'aucune lecture directionnelle ne peut en être tirée).

  ⇒ **Critère de sortie du ticket atteint : la couche (b) reste une règle
  CITÉE (règles YCH 1/2/4, sourcées handbook 2022), jamais habillée d'une
  validation statistique qu'elle n'a pas. T101 N'EST PAS OUVERT** — un
  modèle entraîné sur ce signal apprendrait essentiellement du bruit (et,
  comme le ticket T101 l'anticipait déjà, probablement le biais de
  popularité plutôt qu'un vrai signal chimique). Aucun changement de code
  production ; le libellé "Estimated from composition" de T99 reste
  approprié et n'a besoin d'aucun renforcement/affaiblissement suite à
  cette mesure.

- [ ] **T101 — Régression, SEULEMENT si T100 le justifie**

  **Fermé sans ouverture (2026-08-29) — voir le compte rendu de T100** : la
  corrélation mesurée (ρ=0,12, p=0,18, n=127) est trop faible pour
  justifier un modèle. Conservé ici tel quel comme trace du critère de
  sortie explicite du backlog, pas comme travail à faire.

  Cible : part de dry hop, ou score ordinal boil/whirlpool/dry hop.
  Variables : composition normalisée par composé.

  **Modèle lisible imposé** : régression logistique/ordinale ou arbre de
  décision peu profond. **Pas de boîte noire** — l'utilisateur doit pouvoir
  lire *pourquoi* Simcoe sort « dry hop ».

  **Métriques de validation croisée affichées en GUI**, pas seulement
  calculées. Un modèle dont on cache la performance n'a pas sa place ici.

  ⚠ **Biais de popularité à signaler explicitement** : les houblons modernes
  sont sur-représentés en dry hop parce qu'ils sont modernes, pas seulement à
  cause de leur chimie. Le modèle apprendra cette confusion.
  ⚠ **scikit-learn alourdit le déploiement Streamlit Cloud.** Vérifier
  `requirements.txt` et le temps de démarrage **avant** de s'engager ; une
  régression logistique se code en NumPy si c'est le seul besoin.

- [x] **T102 — Blend Explorer chimique (dans Compare Hops)**

  Empiler la composition en composés « survivables » de 2-3 houblons, avec
  **nos** données (linalol, géraniol, isobutyrate, thiols).

  **Ce que ça matérialise** : la **règle 3** du handbook YCH — « blender pour
  équilibrer, pas pour empiler ». Exemple donné par YCH et à reproduire :
  Loral (linalol) + Talus (géraniol) = dynamique ; Loral + Crystal (tous deux
  linalol) = plat, unidimensionnel.

  **Branché sur le mode Compare Hops existant**, pas de nouveau mode.
  Idée reprise du hop-finder russe, mais sans aucune de leurs données.

  **Compte rendu (2026-08-29)** : carte "Blend Explorer" ajoutée EN FIN de
  `app._compare`, affichée dès que ≥2 houblons sont sélectionnés (pas un
  plafond dur à 2-3 -- Compare Hops autorise déjà jusqu'à 5, restreindre
  davantage aurait été une contrainte UX artificielle sans raison technique
  forte). Réutilise `_survivable_compound_positions_all` (même socle
  factorisé que T99/T117) transposé : un bar PAR COMPOSÉ (pas par houblon
  comme T117), empilé PAR HOUBLON, mêmes couleurs `colors` déjà calculées
  pour les 2 autres graphiques de Compare Hops (cohérence visuelle
  garantie -- un houblon a la MÊME couleur sur les 3 graphiques).

  Vérifié en direct sur les VRAIS exemples cités par le ticket : Loral +
  Talus (réel, base réelle) reproduit exactement le récit YCH -- deux
  barres hautes (Linalool ~1.4 dominé par Loral, Géraniol ~1.7 dominé par
  Talus) = blend "dynamique", spread sur 2 axes. Loral + Crystal : les
  DEUX composés apparaissent chez les deux houblons (Crystal porte
  réellement du géraniol mesuré, pas seulement du linalol comme le
  suggérait l'exemple simplifié du handbook) -- pas un "plat" parfait,
  mais c'est la VRAIE donnée qui parle, pas un exemple fabriqué pour
  coller à la pédagogie YCH -- honnêteté d'abord, cohérent avec le reste
  du projet.

  Houblon sans AUCUN des 4 composés listé dans une caption dédiée ("No
  survivable-compound data for: ..."), jamais silencieusement traité comme
  0 dans l'empilement. 3 nouveaux tests AppTest (masqué à 1 seul houblon,
  rendu + houblon manquant signalé, message honnête si personne n'a de
  donnée). 360 tests passent.

  **Addendum (2026-08-29, retour utilisateur)** : infobox des 4 règles YCH
  (texte, sourcé handbook 2022) ajoutée sur la page Survivables (T117),
  juste après l'intro -- citées comme CONTEXTE de lecture du classement,
  jamais appliquées automatiquement au calcul (aucune des 4 n'est codée en
  dur dans l'indice, qui reste une simple normalisation par composé). La
  règle 3 renvoie explicitement vers ce Blend Explorer.

---

## 7. Épique F — Le croisement qui n'existe dans aucun des deux outils

- [x] **T103 — Outil « Style → houblons » (recettes × arômes)**
  *La fonctionnalité la plus originale du backlog : aucun des deux outils
  étudiés ne fait ce croisement.*

  **Dépend de T81 (styles), T86 (fréquence réelle) et T84 (réconciliation).**

  **Nouveau mode** `app.MODE_LABELS["style_hops"] = "Hops for a style"`.
  L'utilisateur choisit un style, l'outil affiche **deux classements côte à
  côte** :
  1. **Fréquence réelle** — `style_hop_usage` (T86), % de recettes de ce style
     utilisant ce houblon.
  2. **Pertinence aromatique** — `matching.by_descriptor` lancé sur les
     descripteurs typiques du style. ⚠ D'où viennent ces descripteurs ? Deux
     options, à trancher au moment du code : les extraire du texte BJCP
     (`aroma`/`flavor`/`ingredients` de T81, en cherchant les mots de notre
     vocabulaire de 138 descripteurs), ou les laisser l'utilisateur choisir en
     pré-remplissant à partir du texte BJCP. **Recommandation : la seconde**,
     pré-remplie et éditable — l'extraction automatique de descripteurs a déjà
     échoué deux fois dans ce projet (FooDB).

  **La colonne qui justifie l'outil** : « pertinent aromatiquement mais **rare
  dans ce style** » — les houblons bien classés en (2) et absents de (1).
  C'est le « pourquoi personne ne fait ça ? ». La mettre en avant, pas en
  annexe.

  **Compte rendu (2026-08-29)** : `matching.style_hop_frequency(con,
  style_id, usage_type)` (couche 1, `style_hop_usage`, T86, JOIN sur
  `hops` — les ~10% de `variety` non résolues côté T86 sont réelles mais
  non exploitables ici, exclues plutôt que fabriquées) et
  `matching.style_typical_descriptors(con, style_id)` (pré-remplissage,
  recherche MOT ENTIER du vocabulaire `hop_descriptors` dans le texte BJCP
  `aroma`/`flavor`/`ingredients` — recommandation du ticket retenue telle
  quelle : pré-remplissage éditable, PAS une extraction automatique
  imposée, aucun rapport avec les essais FooDB déjà rejetés — ici une
  simple présence littérale dans un texte curé humain, pas une
  co-occurrence statistique). Nouveau mode `app._style_hops`
  (`MODE_LABELS["style-hops"]` — tiret, pas underscore, pour rester
  cohérent avec TOUTES les autres clés de mode existantes, ex.
  "by-descriptor"). Sélecteur catégorie/style dupliqué de `_styles` (T82)
  plutôt que factorisé, pour ne pas toucher un mode stable déjà testé.

  Toggle `usage_type` (Any/Bittering/Aroma/Dry hop) ajouté sur la couche
  fréquence réelle (pas prévu explicitement par le ticket, mais
  `style_hop_usage` porte réellement cette ventilation depuis T86 et
  n'était affichée NULLE PART ailleurs dans la GUI avant ce ticket —
  masquer la ventilation aurait jeté une vraie donnée). La colonne
  pertinence aromatique EST INDÉPENDANTE du stade (elle ne dépend pas du
  procédé), vérifié en direct : bascule Any → Dry hop change bien la
  fréquence (Citra 35,3 % → 21,5 %, Galaxy apparaît) sans toucher au
  classement aromatique.

  Section "Aromatically relevant, rarely used in this style" calculée
  SEULEMENT si `style_hop_frequency` a au moins une ligne pour ce style/
  usage_type (sinon "absent" ne voudrait rien dire — aucune donnée
  beer-analytics du tout pour ce style, pas la confirmation que ces
  houblons y sont rares). Placée EN TÊTE (avant les deux classements côte
  à côte), conformément à "la mettre en avant, pas en annexe".

  Vérifié en direct (Chrome, 21A American IPA, thème sombre) : descripteurs
  pré-remplis réels (berry/caramel/citrus/floral/fruity/melon/pine/stone
  fruit/tropical, trouvés littéralement dans le texte BJCP) ; section
  "rarely used" affiche HBC 630/Idaho 7/Ekuanot/Talus/Falconer's Flight
  Blend/Zythos — des houblons bien classés aromatiquement mais jamais
  mesurés dans les vraies recettes American IPA de beer-analytics, alors
  que Citra/Cascade/Simcoe/Mosaic dominent à la fois la fréquence réelle
  ET le classement aromatique (cohérent, pas de bug).
  351 tests passent (+4 : 2 fonctions `matching.py` testées, mode complet
  testé en AppTest — cas positif avec section "rare & relevant" ET cas de
  repli silencieux sans descripteur typique). Aucune modification
  d'`aromahops.db` (GUI seule) — pas de push HopFinder-db nécessaire.

  **Addendum (2026-08-29, revue utilisateur)** : section "Aromatically
  relevant, rarely used in this style" déplacée SOUS les deux classements
  côte à côte (au lieu d'au-dessus) ; les deux classements passent dans
  leur propre `_panel()` (`_panel(cols[i])`, même mécanisme que les cartes
  de la page Home) pour partager le même fond opaque que la section "rare
  & relevant" -- les trois cartes ont désormais un traitement visuel
  identique, plutôt que deux blocs de texte nu à côté d'une carte encadrée.
  Vérifié en direct (Chrome, 21A American IPA, clair ET sombre).

- [ ] **T104 — Blends contraints par le style**

  `contrast_blend` / `amplify_blend` acceptent un `style_id` optionnel :
  - le pool de candidats est restreint aux houblons réellement utilisés dans
    ce style (`style_hop_usage`, support ≥ N recettes) ;
  - la croissance par pairing privilégie les paires **du style** (T87) plutôt
    que le pairing BeerMaverick global.

  ⚠ **Repli silencieux** sur le comportement actuel si le style est inconnu ou
  trop peu documenté — pattern identique à `purpose_by_variety` (T49), qui
  retombe sur la croissance générique quand le rôle est inconnu.
  ⚠ Ne pas casser la signature existante : `style_id=None` doit produire
  exactement le comportement d'aujourd'hui, vérifié par les tests existants
  qui doivent rester verts sans modification.

- [x] **T105 — Ranges officiels vs ranges observés, côte à côte**

  Dans le mode Beer styles (T82) : la fourchette **BJCP** (T81,
  prescriptive) et la distribution **réellement brassée** (T85, descriptive)
  sur le même axe, pour chacun des 5 critères.

  **Elles divergent, et cette divergence est l'information** — les IPA maison
  sont plus fortes que la lettre du guide.

  ⚠ **Jamais moyennées, jamais fusionnées** — même principe que Yakima vs
  BarthHaas pour les roues d'arôme. Deux encodages visuels distincts
  (la fourchette BJCP en bande, la distribution observée en histogramme
  derrière), légende explicite.
  ⚠ Rappeler que la distribution observée est **pré-binnée et écrêtée** par
  beer-analytics (cf. T85) — ce n'est pas un percentile.

  **Compte rendu (2026-08-29)** : `matching.style_observed_distribution(con,
  style_id)` lit `style_recipe_stats` (T85) et renvoie
  `{metric: [{"bin_low","bin_high","count"}, ...]}` triés par `bin_low` —
  dict vide (jamais un histogramme fabriqué) si le style n'est pas couvert
  côté beer-analytics. `_style_observed_vs_official_chart()` (Altair) rend
  deux couches superposées : `mark_rect` translucide terracotta pour la
  fourchette BJCP (band), `mark_bar` sage pour l'histogramme observé — jamais
  moyennées, jamais fusionnées en une seule courbe. Wiré dans
  `_vital_stat_row()` : repli silencieux sur l'ancienne `_range_bar_html()`
  quand `observed` est vide pour ce critère (style non couvert). Légende
  explicite affichée seulement si au moins un critère a des données
  observées, rappelant que l'histogramme est pré-binné/écrêté par
  beer-analytics, pas un percentile.

  ⚠ **Piège Vega-Lite trouvé en vérification live (screenshot zoomé, Chrome,
  thème sombre)** : `mark_bar` avec un encodage `x`/`x2` de largeur variable
  (bins) et seulement `y` (sans `y2`) ne redescend PAS à 0 automatiquement
  comme le ferait un bar chart classique `x:nominal` — chaque bin rendait un
  petit carré flottant à la hauteur de sa valeur au lieu d'une vraie barre.
  Corrigé par `y2=alt.Y2Datum(0)` explicite, même famille que le piège déjà
  documenté (`x2=alt.X2Datum(domain_min)` pour le barplot en échelle log de
  Compare Hops). Reverifié en direct après correction : ABV/IBU/OG/FG/SRM
  tous corrects, thème clair ET sombre, bascule EBC↔SRM aussi vérifiée
  (12–28 EBC ↔ 6.0–14.0 SRM sur 21A, conversion cohérente).
  342 tests passent (2 nouveaux : `test_style_observed_distribution_groups_
  bins_by_metric_sorted` dans `test_matching.py`,
  `test_styles_mode_shows_observed_distribution_legend_when_beer_analytics_
  covers_style` + `test_styles_mode_falls_back_silently_without_observed_
  data` dans `test_app.py` — ces derniers ne couvrent que le texte de la
  légende, pas le rendu réel du graphique, d'où le bug non détecté par les
  tests automatisés et trouvé seulement en vérification navigateur live).
  Aucune modification de `aromahops.db` (GUI seule) — pas de push
  HopFinder-db nécessaire.

---

## 8. Épique G — Petites reprises (rapides, indépendantes)

- [x] **T106 — Métadonnées d'identité du houblon**

  **Compte rendu (2026-08-27)** : vérification faite AVANT d'écrire quoi que
  ce soit, comme demandé par le ticket. Côté Yakima (Algolia), confirmé en
  direct sur les 153 hits réels : `imported_fields.cultivar`/`experimental`/
  `organic`/`blend` présents exactement comme décrit (booléens Python à
  convertir en 0/1, `cultivar` absent pour 4 variétés désignées seulement par
  un code HBC/YCH). Côté BeerMaverick, PAS de champ structuré : une section
  « Origin and Geneology of the {Hop} Hop » existe (parsée par
  `parsers.parse_beermaverick_origin`) mais en PROSE LIBRE, phrasée
  différemment à chaque houblon (vérifié sur 5 pages réelles : Citra
  « developed by X and released in Y », Simcoe « created by X, developed by
  Y, released through Z in Y » — 3 acteurs différents —, Amarillo sans année
  de sortie directement rattachée). Un parseur regex aurait deviné plus qu'il
  n'aurait extrait → **question posée à l'utilisateur**, qui a choisi la
  curation manuelle plutôt que le NULL partout ou le regex best-effort.

  **breeder/release_year/pedigree** : les 142 paragraphes BeerMaverick
  résolus ont été lus et transcrits à la main dans
  `data/mappings/hop_breeder_pedigree.yaml` (même esprit que `beer_style_
  aliases.yaml`/T79 — jamais dérivé automatiquement), clé = **nom de cultivar
  de base** (`ingest._cultivar_base_name`, suffixe de marque/licencié
  `" - NZ Hops"`/`" - MacHops"`/`" (Marque Déposée)"` retiré). Champ absent du
  texte source → omis, jamais deviné.

  ⚠ **Bug réel trouvé en vérifiant** : `hops` porte plusieurs lignes pour un
  même cultivar quand il est vendu sous des crops/licenciés différents (ex.
  `amarillo` US barthhaas+yakima vs `amarillo-brand-ama04` Germany yakima
  seul, même généalogie ; `motueka-brand-nz-hops` vs `motueka-brand-machops`,
  même cultivar sous deux marques NZ). `_resolve_hop_variety` ne réconcilie
  qu'UNE des deux lignes avec la page BeerMaverick source → sans correctif,
  l'autre ligne serait restée NULL par pur accident d'ordre de crawl.
  `ingest._write_hop_identity` applique donc le mapping par nom de cultivar
  de base à **toutes** les lignes `hops` partageant ce nom, pas seulement à
  la variété individuellement résolue — vérifié en direct : 152 variétés
  mises à jour (> 142 pages BeerMaverick, grâce à cette propagation).

  **Schéma** : `cultivar TEXT, breeder TEXT, release_year INTEGER,
  pedigree TEXT, is_experimental INTEGER, is_organic INTEGER,
  is_blend INTEGER` ajoutées à `hops` — CREATE TABLE canonique mis à jour
  dans `schema.py` (rebuild complet) **et** `schema.ensure_columns` (nouveau,
  même esprit que `ensure_table`/T81 mais pour des COLONNES : `ALTER TABLE
  ... ADD COLUMN` sur une base déjà peuplée, sans DROP). Le « ALTER
  impossible » du ticket visait `init_db` (qui recrée tout), pas une
  limite réelle de SQLite — ALTER ADD COLUMN fonctionne pleinement pour des
  colonnes simples sans contrainte. Booléens Yakima en 0/1 via
  `ingest._bool_to_sqlite`, jamais `0` par défaut sur une donnée absente.

  **GUI** (`app._render_hop_identity`, `browse`) : badges `Experimental`
  (orange)/`Organic` (sage)/`Blend` (gris) uniquement quand `1`, ligne de
  texte cultivar/breeder/année (`" · "` entre champs présents, ligne omise
  si les trois sont absents — pas de `—`), ligne pedigree séparée. Placé
  après purpose/region (exigence utilisateur antérieure et plus forte
  d'être EN PREMIER) mais avant `_render_key_stats`, conforme à la lettre
  du ticket. Vérifié en direct (Chrome, thèmes clair ET sombre) sur Admiral
  (cultivar+breeder+année+pedigree complets), Pekko (badge Organic +
  cultivar seul, pas de breeder), Zythos (badge Blend, breeder « Hopunion »)
  et Luna (aucune métadonnée → bloc entier silencieusement absent).

- [x] **T107 — Description éditoriale du houblon**

  **Compte rendu (2026-08-27)** : vérifié en direct sur le lot complet
  (153/153 variétés, exact comme annoncé) — le HTML est plus riche que
  "juste des `<p>`" : `<br>` sert AUSSI de séparateur de paragraphe à
  l'intérieur d'un même `<p>` (ex. Kohatu/Waimea/Wakatu séparent leur lien
  de fiche produit par `<br><br>`, pas par un `<p>` propre), `<em>` apparaît
  une fois (disclaimer de marque déposée, Dolcita) et `<a href=...>` pointe
  vers de vraies fiches produit PDF `yakimachief.com` (pas du spam tiers) sur
  8 variétés. `parsers.clean_yakima_description` traite `<p>`/`<br>` comme
  séparateurs de paragraphe ÉQUIVALENTS (jamais de texte recollé), convertit
  `<em>` en `*italique*` et `<a>` en lien markdown `[texte](url)` (jamais de
  HTML brut, conforme à la règle du ticket, mais un lien produit légitime de
  la même source déjà utilisée n'a pas de raison d'être perdu). Entités HTML
  (`&#039;`...) décodées. 150/152 variétés réellement peuplées sur la base
  réelle après un `crawl-yakima` (2 sans description exploitable -- jamais
  fabriqué).

  **Colonnes** : `hops.description TEXT` + `hops.description_source TEXT`
  (`schema.HOP_DESCRIPTION_COLUMNS`, migrées via `ensure_columns`, même
  mécanisme que T106).

  **GUI** (`app._render_hop_description`) : `_panel_expander` REPLIÉ dans
  `browse`, sous les métadonnées de T106 et avant les key stats. Attribution
  explicite « Producer description (Yakima Chief Hops) — marketing text from
  the hop's producer, not a neutral characterization. » Absent -> pas
  d'expander vide. Vérifié en direct (Chrome, dark theme) sur Citra (deux
  paragraphes propres) et Kohatu (lien produit cliquable rendu en markdown).

- [x] **T108 — Tri/filtre par popularité**

  **Compte rendu (2026-08-29)** : `matching.hop_popularity(con)` — SOMME de
  `recipes_count` sur les 5 `use_type` de `hop_usage_stats` (T88) par
  `variety`, un proxy de popularité relative (pas un compte de recettes
  UNIQUES : une recette utilisant un houblon en Boil ET en Dry Hop compte
  deux fois — acceptable pour un tri/filtre relatif, jamais présenté comme
  "nombre de recettes exact"). Une `variety` absente du dict = aucune ligne
  `hop_usage_stats` (non résolu côté beer-analytics) : jamais traité comme 0.

  **Addendum (2026-08-29, revue utilisateur)** : Popularity devient le
  DÉFAUT (au lieu de Name) sur `browse` — "so that the dropdown menu is
  more informative by default" (le sélecteur Hop affiche déjà le nombre de
  recettes dans son libellé une fois ce tri actif). `by-descriptor` GARDE
  Relevance par défaut (pas d'argument "dropdown" là — ce mode existe pour
  trier par pertinence aromatique, la popularité reste un ajout
  secondaire). Sur les DEUX modes, le slider "Minimum recipes" ne
  s'affiche plus QUE si le tri Popularity est actif — "otherwise it make
  no sense to display it" (sans effet en tri Name/Relevance, ni sur ce qui
  est montré ni sur l'ordre).

  **`browse`** : `st.segmented_control` "Sort by" (Name/Popularity) +
  `st.slider` "Minimum recipes" (0-200, défaut 0 = désactivé, jamais un
  filtre actif sans action explicite de l'utilisateur). Tri popularité :
  houblons AVEC donnée d'abord (part de
  recettes décroissante), houblons SANS donnée ensuite, triés par nom —
  groupe "no data" séparé et VISIBLE (`format_func` ajoute "(no popularity
  data)" au libellé quand ce tri est actif), jamais un 0 implicite mélangé
  au tri numérique. Le filtre ne masque QUE les houblons avec une popularité
  MESURÉE sous le seuil — jamais un houblon sans donnée.

  **`by-descriptor`** : mêmes contrôles, + un piège réel évité : le pool
  `ranked` retourné par `matching.by_descriptor` est déjà tronqué à `top`
  PAR PERTINENCE avant que je puisse le retrier par popularité — trier ce
  sous-ensemble déjà coupé n'aurait pas donné le vrai palmarès popularité
  parmi TOUT ce qui recoupe les descripteurs (vérifié en direct : "citrus"
  seul faisait ressortir des houblons blend NZ obscurs en tête du tri
  popularité, parce que le top-10 pertinence ne contenait pas les vrais
  houblons populaires). Corrigé : si le tri popularité est actif ET qu'il y
  a eu troncature, `matching.by_descriptor` est rappelé avec `top=
  total_matches` pour retrier sur l'ensemble réel avant de retronquer à
  `top`. Caption de transparence étendue pour mentionner le nombre masqué
  par le filtre popularité, même esprit que la transparence de troncature
  déjà en place (T56). Un caption "Popularity: N recipes (beer-analytics.com)"
  ajouté dans chaque expander de détail quand ce tri est actif (même
  emplacement que la transparence "Quantitative refinement" déjà existante).

  Vérifié en direct (Chrome, dark theme, base réelle) : tri popularité sur
  `browse` classe Cascade (298k recettes) en tête ; `by-descriptor` sur
  "citrus" (122 houblons recoupés) bascule correctement du top-10 pertinence
  (dominé par des blends NZ peu pertinents pour ce test) vers les vrais
  houblons populaires (Cascade/Citra/Amarillo/Centennial/Simcoe/Mosaic...)
  une fois le tri popularité activé — la correction de troncature ci-dessus
  fonctionne réellement, pas seulement en test.

- [ ] **T109 — Substitutions : une troisième source**

  `recipe_db/data/hops.csv` (beer-analytics, 435 lignes) porte une colonne
  `substitutes`. À côté de nos trois relations existantes : `hop_similar`
  (Yakima), `hop_substitutions` (BeerMaverick), et `similar_hops` (notre
  calcul chimique).

  ⚠ **Affichées séparément, jamais fusionnées** — règle établie en T25 et
  réaffirmée depuis. Un désaccord entre trois sources éditoriales et notre
  calcul chimique est en soi une information à montrer, pas un conflit à
  résoudre.

  **Bonus utile** : afficher les houblons sur lesquels les 3 sources
  éditoriales **convergent** — c'est un signal plus fort que chacune prise
  isolément.

- [ ] **T110 — `flavors.csv` comme vocabulaire de contrôle**

  `recipe_db/data/flavors.csv` (beer-analytics, `name;category`) est un
  mapping arôme → catégorie curé indépendamment du nôtre. À croiser avec nos
  138 descripteurs (`reference.DESCRIPTOR_ALIASES`, `CONTRAST_AFFINITY`) pour
  repérer trous et incohérences.

  ⚠ **Ne PAS importer en masse.** C'est un **audit**, livrant un rapport de
  différences à trier à la main — exactement comme le tri des 49 mots
  BarthHaas en T79 (15 retenus comme alias, le reste gardé distinct).
  ⚠ À faire **après** T112, pour ne pas empiler deux revues de vocabulaire.

- [x] **T123 — Suffixe « Hops » parasite dans le nom affiché (18 houblons)**

  **Compte rendu (2026-08-27)** : `parsers.strip_bare_hops_suffix` (nouvelle
  fonction, gardée par la présence de `" - "` n'importe où dans le nom plutôt
  que par le seul caractère précédant « Hops » — cette dernière lecture
  littérale du ticket ne distinguait pas "Luna Hops" de "Kohatu - NZ Hops"
  puisque le mot juste avant « Hops » dans les deux cas n'est pas un tiret ;
  la présence de `" - "` dans la chaîne entière, elle, sépare correctement
  les 7 cas à nettoyer des 11 à garder, vérifié sur les 18 cas réels).
  Câblée aux DEUX pipelines de nom (BarthHaas `crawl_barthhaas`, Yakima
  `parse_yakima_hit`), même endroit que `strip_trademark_symbols`, pour que
  la correction reste symétrique aux deux sources. `crawl-barthhaas` et
  `crawl-yakima` relancés sur la base réelle : `SELECT count(*) FROM hops
  WHERE name LIKE '% Hops'` → **11**, tous `- NZ Hops` ; les 7 anciens
  (Dolcita, Huell Classic, Luna, Ariana, Eclipse, El Dorado, Krush)
  vérifiés individuellement, noms corrects, fusion multi-source (El Dorado,
  Krush) intacte.

  **Symptôme** : 18 lignes de `hops` ont un nom d'affichage finissant par
  « Hops ». Trouvé le 2026-08-27 en listant des exemples d'isobutyrate.

  **Deux cas à NE PAS confondre** (requête de contrôle :
  `SELECT name, sources FROM hops WHERE name LIKE '% Hops';`) :
  1. **BarthHaas — à nettoyer (7)** : `Dolcita Hops`, `Huell Classic Hops`,
     `Luna Hops`, `Ariana Hops`, `Eclipse Hops`, `El Dorado Hops`,
     `Krush Hops`. « Hops » est l'habillage marketing de leur fiche, jamais
     une partie du nom de la variété.
  2. **Yakima `- NZ Hops` — à GARDER (11)** : `Kohatu - NZ Hops`,
     `Motueka - NZ Hops`, `Nectaron - NZ Hops`, `Nelson Sauvin - NZ Hops`,
     `NZ Southern Cross - NZ Hops`, etc. C'est le **fournisseur** (NZ Hops
     Ltd), un vrai qualificatif, explicitement conservé par T51.

  **Correctif** : nouvelle fonction dans `parsers.py`, sur le modèle exact de
  `_strip_yakima_brand_suffix`. Garde stricte : ne retirer « Hops » que s'il
  est en **suffixe nu précédé d'une simple espace**, et **jamais** si le
  caractère non-espace qui précède est un tiret. Concrètement :
  `"Luna Hops"` → `"Luna"` ; `"Kohatu - NZ Hops"` → inchangé.
  Appliquer au même endroit que le strip « Brand » existant, pour que la
  fusion multi-source (T51 : BarthHaas gagne sur conflit de nom) continue de
  fonctionner.

  **Garde-fou obligatoire** (précédent T40 : 6 vrais houblons finissaient par
  « r », d'où la correction ciblée) : vérifier par requête qu'aucune variété
  ne s'appelle légitimement « … Hops » au sens où « Hops » ferait partie du
  nom de cultivar. Les 7 ci-dessus sont tous des noms de variété connus
  (Dolcita, Huell Classic, Luna, Ariana, Eclipse, El Dorado, Krush) — aucun
  ne perd de sens en retirant le suffixe.

  **Test** : `tests/test_parsers.py`, un cas par branche — suffixe nu retiré,
  suffixe précédé d'un tiret conservé, nom sans suffixe inchangé.

  **Après correctif** : relancer `crawl-barthhaas` et `crawl-yakima` sur la
  base réelle, puis re-vérifier que
  `SELECT count(*) FROM hops WHERE name LIKE '% Hops'` retourne **11** (les
  `- NZ Hops` seuls) et non 0 ni 18.
  ⚠ Cosmétique sur le nom affiché uniquement — **ne jamais toucher aux clés
  `variety`**, qui sont référencées par 6 tables.

---

## 9. Épique H — Plomberie / dette

- [x] **T125 — Compare Hops : bracket « Oxygen containing » manquante quand
  `isobutyrate` est présent, + renommage du libellé de classe**

  **Compte rendu (2026-08-27)** : le bug de bracket manquante **ne se
  reproduit plus** — vérifié en direct sur la reproduction exacte du ticket
  (Ella, Galaxy, Huell Melon, Vic Secret), dans les deux thèmes, en mode
  absolu et % d'huile : les 5 brackets s'affichent, aucun `WARN Conflicting
  legend property` en console. Le `.resolve_scale(color="independent")` déjà
  présent sur le `hconcat` (ajouté dans le même commit 9c9c961 pour un
  symptôme voisin, "Thiols disparu") corrige apparemment aussi celui-ci en
  effet de bord. Aucun changement de code nécessaire pour cette partie —
  le ticket avait raison sur le diagnostic (rendu Vega-Lite, pas la logique
  Python) mais le correctif était déjà arrivé avant cette passe.
  Renommage appliqué (`_CATEGORY_CLASS_DISPLAY`). Vérification du cas court
  demandée par le ticket : le cas **2 lignes** (Simcoe/Mosaic ont en réalité
  des données isobutyrate/ketones ; testé à la place sur Admiral+Ahtanum,
  vraiment sans ces champs) déborde de ~3px sur 156px disponibles mais est
  **visuellement invisible** (zoom vérifié, aucun artefact). Un cas **pire,
  non anticipé par le ticket**, existe aussi : 10 houblons de la base n'ont
  qu'UN SEUL champ parmi linalool/géraniol/isobutyrate/ketones (ex. Boadicea,
  Bramling Cross, tous deux "linalool seul") — les comparer entre eux réduit
  le run "Oxygen containing" à 1 ligne, et le libellé déborde alors
  visiblement (reproduit et capturé). Signalé à l'utilisateur avec le
  compromis (`_CATEGORY_ROW_HEIGHT_FLOOR` est une hauteur de ligne globale à
  tout le barplot détaillé, l'augmenter pour couvrir ce cas gonflerait
  toutes les comparaisons, pas seulement celle-ci) : **décision utilisateur
  = ne pas toucher au floor**, ce cas est trop niche (ne se produit que si
  2 houblons comparés partagent exactement le même champ unique) pour
  justifier l'impact visuel global. `_CATEGORY_ROW_HEIGHT_FLOOR` reste à 78.

  **Symptôme** (utilisateur, 2026-08-27, usage réel) : dans le 2ᵉ barplot
  « Detailed composition », en comparant des houblons portant `isobutyrate`,
  la barre colorée (« bracket ») de la classe `Oxygen containing` ne s'affiche
  pas.

  **Reproduction** : comparer des houblons BarthHaas ayant `isobutyrate` —
  par exemple **Ella**, **Galaxy**, **Huell Melon**, **Vic Secret**.

  **Ce qui a DÉJÀ été éliminé** (reproduit hors Streamlit le 2026-08-27 —
  ne pas refaire cette investigation) : **la logique Python est correcte.**
  `reference.PROCESS_SURVIVAL` mappe bien `isobutyrate` et `ketones` sur
  (`Oxygen containing`, `Other (ketones, esters, aldehydes, epoxides)`), le
  `field_order` trié les rend contigus, et `app._contiguous_group_spans`
  produit bien les 5 spans attendus :
  ```
  field_order : myrcene | humulene caryophyllene farnesene | linalool geraniol
                | isobutyrate ketones | thiols
  spans       : (myrcene,myrcene) (humulene,farnesene) (linalool,geraniol)
                (isobutyrate,ketones) (thiols,thiols)
  ```
  ⇒ **Chercher au RENDU Vega-Lite, dans `app._compare_category_gutter`.**

  **Hypothèses à tester, dans cet ordre, EN DIRECT dans le navigateur avec la
  console ouverte** :
  1. **Conflit de résolution de légende/échelle dans le `alt.layer`** de
     `subclass_chart` (`bracket` + N couches `mark_text` + `subclass_
     boundaries` + `subclass_divider`). Précédent identique documenté dans
     `CLAUDE.md` : un conflit de propriété de légende émet
     `WARN Conflicting legend property` **et désactive silencieusement la
     couche** — invisible sans regarder la console. Le nombre de couches de
     texte varie avec le nombre de runs, ce qui expliquerait que le bug
     n'apparaisse qu'avec `isobutyrate`/`ketones` (2 runs de plus), absents
     des houblons utilisés pendant le développement.
     Test : ouvrir la console, comparer Ella+Galaxy, chercher tout `WARN`.
     Correctif probable : `.resolve_scale(color="independent")` sur le layer,
     ou poser `legend=None` de façon cohérente sur toutes les couches.
  2. **`alt.Y2("End:N", bandPosition=1)`** sur le `mark_rect` : vérifier que
     la bande de fin se résout quand le run est adjacent à la frontière entre
     le groupe primaire (ml/100g) et le groupe secondaire (µg/kg, thiols).

  **Ne PAS faire** : contourner en dessinant un rect par ligne. Le
  remplissage plein par catégorie a été explicitement retiré à la demande de
  l'utilisateur ; la bracket fine est le repère catégoriel voulu.

  **Renommage, même ticket** *(confirmé par l'utilisateur)*.
  Dans `app._CATEGORY_CLASS_DISPLAY`, remplacer
  `"Oxygen containing": "Oxygen cont."` par
  `"Oxygen containing": "Oxygen containing comp."`.
  L'utilisateur confirme qu'il y a la place. **Vérifier quand même le cas
  court** : le texte est pivoté à 90°, donc sa longueur consomme de la
  HAUTEUR, et le run `Oxygen containing` ne fait que **2 lignes** quand seuls
  linalol et géraniol sont présents (comparer 2 houblons Yakima sans
  isobutyrate ni ketones, ex. Simcoe + Mosaic). Si ça déborde à 2 lignes,
  augmenter `_CATEGORY_ROW_HEIGHT_FLOOR`, **pas** raccourcir le libellé.
  `"Sulfur compounds": "Sulfur comp."` et `Hydrocarbons` restent inchangés.

  **Definition of Done spécifique** : capture avant/après dans les DEUX
  thèmes, console sans `WARN` Vega-Lite, et les 5 brackets visibles sur une
  comparaison incluant Ella.

- [ ] **T111 — Séparer `recipes.db` de `aromahops.db`** *(D4 tranchée)*

  Les recettes brutes (T91, T118) vivent dans **`recipes.db`**, un fichier
  distinct. `aromahops.db` ne reçoit que les **agrégats** (T93, T126, T127).

  Les deux fichiers sont poussés dans le dépôt privé
  `hopfinder-db`, mais **seul `aromahops.db` est téléchargé par l'app** —
  `app._fetch_remote_db` lit une URL unique depuis `st.secrets`
  (`_DB_SOURCE_URL_SECRET`), qui ne change pas. Aucune modification de cette
  fonction n'est nécessaire.

  **Implémentation** : les commandes d'ingestion de recettes prennent un
  `--recipes-db` (défaut `recipes.db`) ; les commandes d'agrégation prennent
  les deux chemins, lisent la première et écrivent dans la seconde.

  **Vérification avant push** : taille finale d'`aromahops.db` et temps de
  démarrage de l'app. ⚠ Rappel : **reboot Streamlit Cloud obligatoire après
  tout push de base** (le téléchargement ne se redéclenche que si le fichier
  local du conteneur est absent).

- [ ] **T112 — `INGREDIENT_DESCRIPTORS` face au vocabulaire élargi**

  Dette du backlog précédent : les **506 entrées** de
  `reference.INGREDIENT_DESCRIPTORS` n'ont jamais été revues contre les **+34
  termes nets** ajoutés par T79 (BarthHaas). Le vocabulaire est passé de 104 à
  138 termes.

  **Travail** : pour chaque ingrédient, vérifier si un des 34 nouveaux termes
  serait plus juste que ceux actuellement assignés.
  ⚠ C'est un **jugement direct**, pas une dérivation programmatique — la
  dérivation automatique depuis FooDB a déjà échoué deux fois.
  ⚠ Le test existant
  `test_ingredient_descriptors_keys_and_terms_match_real_vocabulary` doit
  rester vert.
  **À faire avant T110.**

- [ ] **T113 — `docs/DATA_SOURCES.md` et `README.md`**

  Une section par nouvelle source (BJCP, beer-analytics, MMuM, YCH Tools,
  Brewfather) avec, pour chacune : licence, méthode d'accès, date de fetch,
  **taux de couverture réel mesuré**, et **ce que la source ne dit pas**.

  Mettre à jour la section « ce qui est un prior, pas une donnée » du README
  avec les deux nouveaux priors : l'indice de survivabilité (couche (b) de
  T99) et la matrice de rétention par stade (T119).

- [ ] **T114 — `app._RECENT_UPDATES`**

  Rappel de la règle `CLAUDE.md` : tout changement **visible par
  l'utilisateur final** met à jour cette liste **dans le même commit** —
  T82, T94, T99, T103, T117, T121, T126, T127 sont concernés.
  Liste statique curée à la main, en anglais. Jamais de lecture `git log` en
  direct (messages en français, et `.git` n'est pas garanti présent sur
  Streamlit Cloud).

---

## 10. Épique I — Tableau de couverture des composés par procédé

*Demande utilisateur (reformulée après échange du 2026-08-27) : « rajouter des
houblons ainsi que le procédé de houblonnage (dry hop, whirlpool…) et cocher les
cases des composés survivant au procédé. Ça permettrait au brasseur de voir
directement quels composés ne sont pas couverts par son blend. »*

**Revirement de conception acté** : ce n'est **PAS un optimiseur**, et la
couverture se raisonne **AU NIVEAU DU COMPOSÉ**, pas de la famille chimique.
Motif donné par l'utilisateur, et il est juste : « si on apporte le linalol mais
pas le géraniol dans la famille des alcools monoterpéniques, il faut le savoir »
— une agrégation par famille masque exactement l'information utile. Le
vocabulaire est donc celui du **2ᵉ barplot de Compare Hops**
(`app._COMPARE_DETAIL_OIL_COMPOUNDS` + `thiols`, 11 composés).

Conséquence heureuse : le risque de dégénérescence qui avait tué `combine()`
(NNLS) disparaît, puisqu'on ne résout plus rien — on **constate** une couverture
et on montre les trous. Le garde-fou T122 change donc de nature (voir plus bas).

⚠ **Le vrai piège de cette épique n'est pas algorithmique, il est
ÉPISTÉMIQUE** — mais **l'utilisateur l'a tranché le 2026-08-27, et sa position
devient la règle du projet pour cette épique** :

> « Sachant que je prends mes sources de peu de bases de données, je pars du
> principe que si la mesure est manquante, c'est soit que c'est un houblon sans
> cette molécule, soit qu'il y en a trop peu dedans pour le reporter. On peut
> donc mettre un message du genre "ton blend n'apporte **a priori** pas de
> thiols" plutôt que d'être catégorique. Ça résoudrait le problème par
> transparence. »

C'est une inférence **raisonnable et assumée** : BarthHaas et Yakima mesurent ce
qu'ils jugent digne d'être publié, donc une absence de ligne est un signal
faible mais réel, pas du pur bruit. **Deux états d'affichage suffisent donc** —
apporté / **a priori absent** — au lieu des trois que j'avais proposés.

Mais la transparence doit être RÉELLE, pas un simple adverbe :
- Le mot « a priori » partout dans le texte de l'outil, jamais « ne contient
  pas » ni « 0 ».
- Un **encart explicatif détaillé** dans l'app (T121) : pourquoi « a priori »,
  quelles sources mesurent quoi, et le **compte réel de couverture** par
  composé (`isobutyrate` 31/189, `ketones` 33/189, `thiols` 22/189,
  `selinene` 2/189, `beta-pinene` 135/189 — les autres > 190 lignes).
- Un houblon **jamais couvert par BarthHaas** (seule source de `isobutyrate`/
  `ketones`/`thiols`) doit être distingué d'un houblon couvert par BarthHaas
  mais sans la ligne : dans le premier cas, l'inférence de l'utilisateur ne
  s'applique pas du tout (personne n'a regardé), dans le second elle est
  solide. **C'est la seule nuance à conserver techniquement.**

- [x] **T115 — Prior « le côté chaud CRÉE de l'arôme » : SOURCÉ**
  Résolu par `mapping_compounds.txt` (fourni par l'utilisateur le 2026-08-26,
  relu le 2026-08-27). Extraits directement réutilisables :
  - **Humulène** : « sous sa forme pure hydrocarbonée, il s'évapore au boil /
    fermentation. Son arôme épicé "noble" caractéristique provient de ses
    **dérivés d'oxydation thermique (humulene epoxides I, II, III) formés au
    kettle/whirlpool** » — sources : The New IPA (Janish) ; JAFC.
  - **Caryophyllène** : « très volatil sous forme brute ; **s'oxyde au chaud en
    caryophyllene oxide** pour donner la persistance épicée » — sources :
    Janish ; ASBC.
  - **Myrcène** : « extrêmement volatil. Évaporation rapide au boil ; apport
    majeur en dry hopping à froid » — Janish ; OSU Hop Lab (Shellhammer).
  - **Linalol** : « soluble et très résistant à l'ébullition/fermentation
    ("survivable") » — Janish ; Journal of the Inst. of Brewing.
  - **Géraniol** : « convertie par la levure pendant la fermentation en
    β-citronellol » — Takoi et al. (2010, 2014) ; YCH Survivables Research.
  Fichier déplacé en `docs/mapping_compounds.txt` (2026-08-27).
  Reste à faire : **transcrire son contenu dans `reference.py`** avec la
  même rigueur que `PROCESS_SURVIVAL`/`JANISH_COMPOUND_CATEGORIES`
  (structure sourcée, une référence par entrée) — un `.txt` n'est pas une
  structure de données interrogeable par le code.
  ⚠ Toujours vrai : les produits d'oxydation **ne sont pas mesurés dans le
  houblon**. Un houblon riche en humulène est un **précurseur** de côté chaud,
  jamais une mesure de ce qu'on obtiendra. La GUI doit le dire (T121).

- [x] **T115b — Homonymie « 2-MIB » : CORRIGÉE dans le fichier de mapping**
  `docs/mapping_compounds.txt` (déplacé de la racine vers `docs/`) définissait
  « 2-MIB » comme le **2-méthylisobornéol** — alcool terpénique, terreux/moisi
  type géosmine, seuil 5-10 ng/L, décrit comme **un faux-goût venant de l'eau**
  (cyanobactéries). Ce n'est **pas** le « 2MIB » de Yakima Chief, qui est le
  **2-méthylbutyl isobutyrate**, un **ester** pomme verte/abricot, l'un des 8
  survivables (champ `twoMethylbutylIsobutyrate` de l'API YCH — confirmé sur 3
  lots réels : 109 à 268 selon le lot).
  Le fichier se contredisait d'ailleurs lui-même : son entrée « Isobutyrate »
  listait le 2-méthylbutyl isobutyrate parmi les esters du sous-groupe.
  **Corrigé en place** (2026-08-27) : l'entrée est scindée en deux, avec un
  bandeau `[!] ATTENTION HOMONYMIE` et le rattachement correct de chacune.
  Répercuté dans `CLAUDE.md` §« Côté chaud vs côté froid ».

- [ ] **T116 — Client de lookup de lot YCH (lots fournis par l'utilisateur)**

  **Endpoint** (vérifié en direct le 2026-08-27) :
  ```
  GET https://tools.yakimachief.com/api/lot?lotNumber[]=<LOT>[&lotNumber[]=<LOT2>…]
  Accept: application/json
  ```
  Réponse : `{"message":"success","data":{"lots":{<LOT>:{…}}, "errors":[…],
  "exceptions":[…]}}`. Un lot inconnu n'est **pas** une erreur HTTP : la
  réponse reste `200` et le lot apparaît dans `data.errors` avec
  `response.code == "0x7106"`. Traiter ce cas explicitement.

  **Champs à ingérer** (relevés sur 3 lots réels) : `lotNumber`, `variety`,
  `varietyCode`, `cultivar`, `cropYear`, `productName`, `productCode`
  (`CON02` balle / `PEL02` T90 / `PEL06` Cryo), `farms[].grownBy`,
  `brewingValues` (`uvAlpha`, `uvBeta`, `hsi`, `hplcAlpha`, `hplcBeta`,
  `hplcCohumulone`, `hplcColupulone`, `moisture`, `lcvAlpha75`),
  `oilComponents`, et `survivables` (22 champs, plusieurs souvent `null`).

  **Table dédiée** (+ son `DROP` dans `init_db`) :
  ```sql
  CREATE TABLE hop_lot_analysis (
      lot_number TEXT, compound TEXT, value REAL, unit TEXT,
      variety_name TEXT, variety TEXT, crop_year INTEGER,
      product_code TEXT, grown_by TEXT, source TEXT, fetched_at TEXT,
      PRIMARY KEY (lot_number, compound)
  );
  ```
  ⚠ **Jamais dans `hop_composition`.** Ce n'est pas une mesure de variété :
  sur les 3 lots Citra 2023 testés, le Cryo affiche ~2× les survivables du
  T90. `variety` (notre slug) résolu via `ingest._resolve_hop_variety` sur
  `variety_name`, `NULL` si non reconnu — jamais deviné.

  **Batching** : l'API accepte plusieurs `lotNumber[]` par requête (testé avec
  3). Grouper par lots de 20 maximum, délai entre requêtes, réponses cachées
  sous `data/cache/yakima_lots/`.

  **CLI** : `hopmatch lookup-lot <LOT> [<LOT>…]` et
  `hopmatch lookup-lot --file <chemin>` (un numéro par ligne).
  **On n'interroge que des numéros fournis. Aucune énumération, aucune
  génération de numéros.**

  ⚠ **BLOQUANT avant d'écrire quoi que ce soit en base** : l'unité n'est pas
  déclarée par l'API, et le 3MH y est 20 à 50× au-dessus de l'agrégat `thiols`
  BarthHaas (cf. §0). Tant que ces deux points ne sont pas élucidés — par la
  réponse à `docs/OUTREACH_yakima-chief.md`, ou par une source publiée —
  stocker `unit = NULL` et **ne jamais afficher ces valeurs à côté des
  nôtres**. Le client peut être écrit et testé sans que la GUI les montre.

  **Test** : fixture JSON locale (copier une réponse réelle dans
  `tests/fixtures/yakima_lot.json`), vérifier le parsing d'un lot valide, le
  traitement d'un `0x7106`, et l'absence d'écriture dans `hop_composition`.
  **Aucun appel réseau dans le test.**

- [ ] **T128 — Récolter des numéros de lot YCH publiés**

  Complément de T116 : le client ne sert à rien sans numéros. Ticket
  d'**investigation + collecte**, à faire une fois, résultat stocké dans un
  fichier versionné `data/mappings/yakima_lot_numbers.txt` (un numéro par
  ligne, avec en commentaire l'URL où il a été trouvé).

  **Sources à ratisser, dans cet ordre** :
  1. **URLs de partage indexées** : `tools.yakimachief.com/lookup?lots[]=…`.
     C'est ainsi que `23-WA346-027`, `P92-IUCIT3082` et `PC1-IUCIT1079` ont
     été trouvés. Chercher d'autres occurrences de ce motif d'URL.
  2. **Fiches produit et COA de revendeurs** qui affichent le numéro de lot
     (revendeurs US/EU de pellets YCH, Yakima Valley Hops et équivalents).
  3. **Forums et posts brassicoles** où des brasseurs citent leur numéro de
     lot en partageant une analyse.
  4. **Les cartons de l'utilisateur**, s'il achète du YCH.

  **Ce qui est explicitement exclu** : générer ou énumérer des numéros à
  partir du format observé (`<préfixe>-<IU><CODE_VARIÉTÉ><NNNN>`). On ne
  collecte que des numéros réellement publiés quelque part.

  **Critère d'arrêt** : si la récolte reste sous ~30 numéros couvrant moins de
  10 variétés, le ticket se ferme en « volume insuffisant », T116 reste
  dormant, et l'onglet Survivables (T117) tourne sur l'indice dérivé seul.
  État actuel de la récolte : **3 numéros, 1 variété (Citra 2023)**.

- [x] **T124 — Numéros de lot sans carton : EXPLORÉ, résultat mitigé**
  Question de l'utilisateur : « c'est pas possible qu'on ne trouve pas l'info
  sur le net (mapping lot ↔ hop name) ». **Exploré le 2026-08-27.**
  - ✅ **Le mapping n'a pas à être construit** : la réponse `/api/lot` porte
    `variety`, `varietyCode`, `cultivar`, `cropYear` et la forme produit.
    Chaque lot s'auto-étiquette.
  - ✅ Des numéros réels sont trouvables : `23-WA346-027`, `P92-IUCIT3082`,
    `PC1-IUCIT1079`, récupérés via une URL de partage
    `tools.yakimachief.com/lookup?lots[]=…` indexée par les moteurs, et
    testés avec succès contre l'API.
  - ❌ **Mais ils ne sont pas énumérables** : pas d'index, pas de recherche par
    variété, et énumérer par force brute serait un scan de leur API (exclu).
    Récolte totale : **3 lots, tous Citra 2023.**
  ⇒ **Conclusion : pas de jeu de données possible.** Décision utilisateur
  actée en D2 — on abandonne comme socle systématique et on part sur l'indice
  dérivé. Ticket clos, conservé pour ne pas refaire l'exploration.

- [x] **T117 — Onglet « Survivables » sur indice dérivé** *(D2 tranchée)*
  Repris de l'onglet SURVIVABLE du site russe, mais **sans aucune donnée
  reconstruite** : classement des houblons par un indice de survivabilité
  calculé sur **nos propres mesures** — linalol, géraniol, `isobutyrate`
  (= 3 des 8 survivables Yakima, cf. T95) et `thiols` (dont le 3MH) —
  normalisé par composé sur toute la base (mécanisme Min-max/Quantile déjà en
  place dans Compare Hops).
  Barres empilées par composé, tri par total, filtre haute/moyenne/basse.
  ⚠ **C'est un indice dérivé, pas une mesure de survivabilité** : les 4 règles
  YCH portent sur des concentrations absolues mesurées en labo, nous
  travaillons sur des % d'huile et un agrégat. Étiqueté comme tel partout,
  jamais présenté au même niveau qu'une donnée YCH (traitement du préfixe
  `Inferred:`).
  ⚠ **Couverture honnête** : `isobutyrate` n'existe que sur 31 houblons et
  `thiols` sur 22 (sur 189) — l'onglet n'affiche que les houblons réellement
  notables et **dit combien il en manque**, plutôt que de classer 189 houblons
  dont 158 sur une donnée absente.
  ⚠ Le **méthyl géranate**, pourtant le composé le plus abondant des
  survivables sur les 3 lots testés (346-689), n'est couvert par **aucun** de
  nos agrégats — l'indice a un trou connu, à afficher.

  **Compte rendu (2026-08-29)** : nouveau mode `app._survivables`
  (`MODE_LABELS["survivables"]`). Socle chimique FACTORISÉ avec T99 :
  `app._chemical_earliness_index_all` (T99, MOYENNE par composé) a été
  scindé pour extraire `app._survivable_compound_positions_all` (rang
  quantile PAR composé, `{variety: {compound: rang}}`), réutilisé tel
  quel par T99 (moyenne) et T117 (SOMME, barres empilées) -- même
  normalisation calculée une seule fois, jamais deux implémentations
  divergentes du même signal. Vérifié que le refactor ne change rien au
  calcul (`test_survivable_compound_positions_all_matches_chemical_index_
  inputs`, mêmes valeurs 0.75/1.0/0.25 que le test T99 existant).

  Paliers Haute/Moyenne/Basse : **terciles du total (somme) PARMI les
  houblons réellement couverts** (`app._survivable_buckets`), jamais un
  seuil absolu inventé — même logique DB-relative que la divergence de T99.
  Cas dégénéré (< 3 houblons couverts) : tout le monde "High" (un tercile
  n'a pas de sens en dessous de 3 valeurs). Couverture réelle vérifiée en
  direct sur `aromahops.db` : **170/189 houblons couverts** (au moins un
  des 4 composés), détail par composé Linalool 169/189, Géraniol 160/189,
  Isobutyrate 31/189, Thiols 22/189 — exactement les chiffres cités par le
  ticket, jamais un houblon sans aucune des 4 mesures affiché.

  ⚠ **Piège Vega-Lite réel trouvé en vérification live** (zoom sur le
  graphique réel, capture montrant des barres PLUS HAUTES que leurs
  voisines de GAUCHE malgré `sort=alt.SortField(field="total",
  order="descending")`) : `rows` porte PLUSIEURS lignes par houblon (une
  par composé mesuré), et Vega-Lite agrège le champ de tri par SOMME par
  défaut quand aucun `op` n'est précisé — `alt.SortField` de cette version
  d'Altair n'expose PAS de paramètre `op` (contrairement au schéma
  Vega-Lite brut, vérifié par `SchemaValidationError` en direct) — un
  houblon à 4 composés mesurés voyait donc son total sommé 4 fois contre 1x
  pour un houblon à 1 seul composé, inversant l'ordre. Corrigé en passant
  directement la liste PYTHON déjà triée comme domaine `sort` (`sort=
  hop_order`) plutôt qu'un champ à agréger côté Vega-Lite — aucune
  ambiguïté d'agrégation possible sur une liste explicite. Reverifié en
  direct (zoom) : strictement décroissant de Mosaic (3.0) au reste.

  Couleurs des 4 composés : 4 teintes de `_COMPARE_PALETTE` (denim/sauge/
  ochre/prune), EN ÉVITANT la terracotta (réservée à "interaction/
  cliquable" ailleurs dans la GUI). Largeur du graphique proportionnelle au
  nombre de houblons affichés (jusqu'à ~170), même logique "délibérément
  large/défilant" que le barplot détaillé de Compare Hops.
  356 tests passent (+5). Vérifié en direct (Chrome, clair, base réelle) :
  chart, filtre High/Medium/Low fonctionnel (rescale bien l'axe Y en
  excluant High). Aucune modification d'`aromahops.db` — pas de push
  HopFinder-db nécessaire.

  **Addendum (2026-08-29, retours utilisateur)** :
  - **Tous les noms de houblon sur l'axe X** : `alt.Axis(labelOverlap=
    False)` -- Vega-Lite éclaircissait silencieusement les libellés d'un
    axe nominal à ~170 catégories par défaut, masquant la plupart des noms
    malgré la rotation -45°. `chart_width` (déjà dimensionné pour ~170
    barres) laisse la place réelle nécessaire.
  - **Bug réel trouvé en signalant "Dolcita US"/"Perle Germany" mal
    ordonnés** : DEUX vraies paires de doublons cross-source non fusionnées
    dans `hops` (`dolcita-hops`/`dolcita`, `perle`/`perle-per03` — même nom
    ET même région, jamais attrapées par le garde-fou d'ingestion malgré
    une logique symétrique et correcte à la lecture, root cause exacte non
    élucidée). `ingest.merge_hop_varieties` (T60, 5 doublons fusionnés le
    2026-08-19) étendue aux 4 tables T85-T88 qui n'existaient pas à
    l'époque (`hop_usage_stats`, `hop_beer_styles`, `style_hop_usage`,
    `style_hop_pairings` -- auraient été silencieusement orphelines sinon),
    nouveau test `test_merge_hop_varieties_migrates_beer_analytics_tables`.
    Fusion appliquée à `aromahops.db` réelle (189 → 187 houblons), vérifiée
    lossless (comptages avant/après par table). **Push HopFinder-db
    nécessaire** (seule modification de données de ce batch T100/T117/
    T102/T129 -- voir CLAUDE.md "Doublons de houblons audités").
  - **Indicateur de purpose (aromatic/bittering)** : marqueur au-dessus de
    chaque colonne, résolu par `matching.resolve_purpose` (même résolution
    que `_purpose_badge` partout ailleurs). Design final après DEUX
    itérations en direct sur retour utilisateur :
    1. 1er essai : triangle unique, couleur = purpose (sauge/terracotta/
       gris, palette `_purpose_badge`, résolue par thème).
    2. **Retour** : "use a circle for aromatic and a triangle for
       bittering. Use grey for infered and black for known... merge (only
       for displaying) Both together with aromatic" -- refonte complète :
       **FORME** = aromatic (cercle) / bittering (triangle), **COULEUR** =
       confiance (connu vs inféré). "Both" (70/189 houblons réels -- existe
       bel et bien, contrairement au doute de l'utilisateur) FONDU dans
       "aromatic" pour CET AFFICHAGE seulement (raison donnée : un houblon
       dual-purpose est en pratique le plus souvent utilisé pour l'arôme,
       trop cher pour de l'amérisation pure, ex. Citra) -- `hops.purpose`
       brut inchangé en base, "Both" reste intact partout ailleurs (badges,
       tableaux). Houblon à purpose inconnu : AUCUNE ligne dans les données
       du marqueur (pas de transparent fabriqué comme le 1er essai).
    3. **2e retour, deux passes** : "black and grey" rendu comme encre
       `light-dark()` du texte principal (noir clair / blanc sombre) --
       correct par thème mais pas voulu ("I see white and grey... let's
       manage the theme variable... white for known and lightgrey for
       infered"). Blanc/gris clair fixes essayés, TOUJOURS insuffisant
       ("white and grey is not working... find two colors that contrast
       well with both beige and grey but that are not confusing with the
       barplot colors") -- design **FINAL** : brique `#a4383a` (connu) /
       sarcelle `#2f7a78` (inféré), les deux seules familles de teinte
       encore libres sur le cercle chromatique Organic (les 4 composés
       occupent déjà denim/sauge/ochre/prune), contour sombre fixe
       (`stroke`) pour la netteté des formes. `purpose_label` ajouté aussi
       au tooltip de chaque segment de barre (pas seulement le marqueur),
       pour rester visible même sans viser précisément le marqueur.
       Vérifié en direct (clair ET sombre) après chaque itération.
  362 tests passent au total après ces 3 addenda.

- [x] **T119 — Matrice composé × stade de procédé**

  `matching.compound_survival(compound: str, stage: str) -> dict | None`
  retournant `{"state": …, "source": …, "note": …}` ou `None` si le composé
  n'est pas dans la matrice.

  **`stage ∈ {"boil", "whirlpool", "afdh", "pfdh"}`**
  (afdh = active fermentation dry hop, pfdh = post fermentation dry hop).

  **`state ∈ {"kept", "partial", "lost", "precursor"}` — ordinal à 4 états,
  JAMAIS un pourcentage.** Nous n'avons aucun facteur de survie quantitatif ;
  en inventer un serait exactement ce que le projet s'interdit. Le 4ᵉ état
  (`precursor`) n'est pas cosmétique : c'est le cœur de la demande
  utilisateur sur l'oxydation des sesquiterpènes.

  **Périmètre** : les 11 composés de `app._COMPARE_DETAIL_OIL_COMPOUNDS` +
  `thiols`.

  **Sources à combiner** : `reference.PROCESS_SURVIVAL` (existant, qualitatif
  par classe, sourcé Janish), les 4 règles YCH (`CLAUDE.md` §Règles procédé),
  et les notes brassicoles de `docs/mapping_compounds.txt`.

  **Cas à trancher explicitement, chacun avec sa source dans le code** :
  | Composé | boil | whirlpool | afdh | pfdh | Justification |
  |---|---|---|---|---|---|
  | myrcène | `lost` | `partial` | `kept` | `kept` | « extrêmement volatil, évaporation rapide au boil ; apport majeur en dry hopping à froid » (Janish, OSU) |
  | humulène | `precursor` | `precursor` | `lost` | `kept` | s'évapore tel quel, mais génère les époxydes I/II/III au kettle/whirlpool (Janish, JAFC) |
  | caryophyllène | `precursor` | `precursor` | `lost` | `kept` | idem, → oxyde de caryophyllène (Janish, ASBC) |
  | linalol | `partial` | `kept` | `kept` | `kept` | « soluble et très résistant à l'ébullition/fermentation » (Janish, JIB) + règle YCH 1 |
  | géraniol | `partial` | `kept` | `kept` | `kept` | règle YCH 1 et 4 ; biotransformé en β-citronellol en AFDH (Takoi 2010/2014) |
  | isobutyrate | `partial` | `kept` | `kept` | `kept` | esters survivables, règle YCH 1 |
  | thiols | `partial` | `kept` | `kept` | `kept` | handbook YCH : « les composés solubles dans le moût — alcools monoterpéniques, 3MH — passent au fermenteur » |

  ⚠ **Ce tableau est une PROPOSITION de départ, à valider ligne par ligne
  contre les sources avant de l'écrire dans `reference.py`.** Les composés non
  listés (farnésène, β-pinène, sélinène, ketones) n'ont pas encore de position
  tranchée : les traiter ou les laisser hors matrice, mais **ne jamais deviner
  silencieusement**.

  ⚠ **Cette matrice porte sur la SURVIE au procédé** (question chimique), pas
  sur la présence dans le houblon (question de données). Les deux ne se
  combinent que dans T120, jamais avant.

  **Surcharge utilisateur** : les valeurs sont pré-remplies mais
  surchargeables en GUI (demande explicite : « on cocherait les cases »). Une
  surcharge est une opinion de brasseur, gardée en `st.session_state`,
  marquée comme telle à l'affichage, et **jamais écrite en base**.

  **Test** : vérifier que les 4 états sont les seuls produits, qu'un composé
  hors matrice retourne `None` (pas un état par défaut), et que chaque entrée
  porte une `source` non vide.

  **FAIT (2026-08-29).** `reference.PROCESS_STAGE_SURVIVAL` (44 entrées : 11
  composés × 4 stades, `{state, source, note}`) + `matching.compound_
  survival(compound, stage)`, lecture pure, aucune requête DB (même
  justification que `process_survival` existant : propriété de la molécule/
  du procédé, pas du houblon). 8 tests (états valides, périmètre complet,
  `None` sur composé/stade hors matrice, source/note non vides, sesquiterpènes
  precursor côté chaud puis kept côté froid, garde-fou structurel "jamais
  appelé par un chemin de score" identique à celui de `process_survival`).
  Correction vs. la proposition de départ du ticket : linalol passé de
  "partial" à "lost" au boil -- la source citée par le ticket lui-même
  (`PROCESS_SURVIVAL_EXPLANATIONS["boil-sensitive, survives whirlpool"]`)
  documente le MÊME ordre de perte pour myrcène et linalol ("essentially
  gone" à 60 min) ; myrcène étant "lost", linalol devait l'être aussi pour
  rester cohérent avec sa propre source. Composés non tranchés par la
  proposition de départ (beta-pinène, farnésène, sélinène, ketones)
  tranchés : beta-pinène reste sur "dry hop / late additions" (jamais
  "survives whirlpool", contrairement au myrcène -- aucune source ne
  documente sa survie au whirlpool) ; farnésène/sélinène suivent le
  comportement de classe humulène/caryophyllène (déjà groupés sous la même
  annotation `PROCESS_SURVIVAL`, pas de citation spécifique trouvée) ;
  ketones traité comme isobutyrate (2-nonanone = survivable YCH officiel,
  champ `twoNonanone`) mais avec la même réserve de confiance basse que
  `PROCESS_SURVIVAL["ketones"]` (agrégat BarthHaas mélangeant aussi le
  2-undécanone, non documenté). AFDH="lost" pour les sesquiterpènes bruts
  (humulène/caryophyllène/farnésène/sélinène) sourcé par le mécanisme de
  CO2-stripping des notes de séminaire BarthHaas de Christian Scheb (mémoire
  `barthhaas_hop_flavorist_seminar_notes`, reçues le jour même) -- première
  utilisation concrète de ces notes dans le code. Pas de câblage GUI (hors
  périmètre de ce ticket, voir T121) ni de surcharge utilisateur (dépend de
  cette matrice, également T121) -- `_RECENT_UPDATES` non touché (aucun
  changement visible utilisateur final pour l'instant).

  **Addendum (2026-08-30, relecture utilisateur en direct sur linalol).**
  Piège de lecture identifié : "early" est ambigu entre deux axes -- tôt
  DANS L'ÉBULLITION (défavorable au linalol, Janish) vs. tôt DANS LA
  CHRONOLOGIE relative à la fermentation (règle YCH 1 : "late kettle,
  whirlpool, AFDH" -- tous à exposition d'ébullition active faible/nulle).
  Pas de contradiction dans les DONNÉES (linalol reste `lost` au boil,
  `kept` au whirlpool -- "boil" est un cas hostile à part, pas le point de
  départ d'un continuum "plus tôt = pire"), mais la note "whirlpool" du
  linalol utilisait elle-même le mot "early" de façon ambiguë ("high
  survivables are usable early, including whirlpool") -- exactement le
  piège que l'utilisateur a repéré. Corrigé : notes boil/whirlpool du
  linalol réécrites pour distinguer explicitement les deux axes et se
  référencer l'une l'autre (pas de contradiction), + paragraphe d'avertissement
  général ajouté en tête de `reference.PROCESS_STAGE_SURVIVAL` pour que ce
  piège ne se reproduise pas sur un futur composé similaire (haut survivable
  mais mauvaise résistance au boil). Aucun `state` changé, uniquement la
  clarté des `note`. Suite verte (373 tests).

- [x] **T120 — Calcul de couverture d'un plan de houblonnage**

  `matching.hopping_plan_coverage(con, plan) -> list[dict]` où
  `plan = [(variety, stage), …]` (un même houblon peut apparaître à plusieurs
  stades).

  **Sortie, une entrée par composé** :
  ```python
  {"compound": "geraniol",
   "state": "delivered" | "presumed_absent",
   "delivered_by": [{"variety": …, "stage": …, "amount": …, "unit": …}],
   "survival": "kept",            # de T119, pour le stade concerné
   "measured_source_missing": bool}
  ```

  **Règle de combinaison** : un composé est `delivered` si **au moins un**
  couple (houblon, stade) du plan a (a) une valeur mesurée non nulle pour ce
  composé dans `hop_composition`, ET (b) un `state` de T119 valant `kept` ou
  `partial` à ce stade. Un `precursor` est rapporté séparément (il ne livre
  pas le composé, il en génère un autre).

  **Doctrine « a priori »** (décision utilisateur, cf. l'intro de l'épique) :
  l'absence de ligne en base est traitée comme « a priori absent », pas comme
  « inconnu ». **Une seule nuance conservée** : `measured_source_missing =
  True` quand **aucune** des sources qui mesurent ce composé n'a jamais
  couvert ce houblon (concrètement, `isobutyrate`/`ketones`/`thiols` ne
  viennent que de BarthHaas — un houblon absent du catalogue BarthHaas n'a pas
  été « mesuré à ~0 », il n'a pas été regardé). Dans ce cas l'inférence ne
  s'applique pas, et la GUI le dit différemment.

  **Aucun solveur, aucune optimisation.** On constate, on ne propose pas.

  **Test** : plan à 2 houblons dont un sans `isobutyrate`, vérifier
  `presumed_absent` ; plan avec un houblon hors BarthHaas, vérifier
  `measured_source_missing = True`.

  **FAIT (2026-08-30).** `matching.hopping_plan_coverage(con, plan)`,
  lecture pure sur `matching.load()` (déjà réconcilié multi-sources -- pas
  de nouvelle requête `hop_composition`). Une entrée par composé (11, ordre
  de `reference.PROCESS_STAGE_SURVIVAL`) : `state`
  (`delivered`/`presumed_absent`), `delivered_by`/`precursor_by` (listes de
  `{variety, stage, amount, unit}`), `survival` (meilleur état contributeur,
  `kept` > `partial` > `None`), `measured_source_missing`. `ValueError` sur
  un stade hors des 4 reconnus (pas dans le spec du ticket mais garde-fou
  raisonnable contre une faute de frappe silencieuse). `measured_source_
  missing` calculé au niveau du PLAN entier (pas houblon par houblon) : si
  au moins un houblon du plan a une couverture BarthHaas réelle (même sur un
  autre composé), l'absence d'isobutyrate/ketones/thiols pour ce plan reste
  une vraie inférence "a priori absent", pas un trou de données -- testé sur
  les fixtures réelles (saazer = BarthHaas sans isobutyrate propre → `False` ;
  simcoe = Yakima seul, aucune ligne BarthHaas → `True`). 8 tests (périmètre
  11 composés, stade invalide, delivered/kept, precursor ne livre jamais le
  composé lui-même, agrégation "meilleur des contributeurs", les deux cas du
  ticket, amount/unit vs `load()`). Suite verte (381 tests). Pas de câblage
  GUI (T121) ni de garde-fou de discrimination (T122, à faire avant T121).

- [x] **T121 — GUI : le tableau de couverture**

  **Nouveau mode** `app.MODE_LABELS["coverage"] = "Hopping plan"`.

  **Saisie** : `st.multiselect` de houblons, puis pour chacun un
  `st.segmented_control` de stade (Boil / Whirlpool / AFDH / PFDH). Un houblon
  peut être ajouté deux fois à deux stades.

  **Affichage** :
  1. **Grille composé × stade**, réutilisant le vocabulaire, l'ordre et les
     catégories chimiques du 2ᵉ barplot de Compare Hops
     (`_compare_category_gutter`) — les deux vues doivent se lire pareil.
  2. **Section « a priori non couvert », explicite et mise en avant** —
     c'est la demande centrale : « voir directement quels composés ne sont pas
     couverts par son blend ».
  3. **Encart explicatif** (`st.expander` replié, demande utilisateur
     explicite : « prévois un message plus détaillé pour ça ») expliquant en
     clair, sans jargon : pourquoi « a priori », quelles sources mesurent quoi,
     et le compte réel de couverture par composé —
     `isobutyrate` 31/189, `ketones` 33/189, `thiols` 22/189,
     `selinene` 2/189, `beta-pinene` 135/189, les autres > 190 lignes.

  **Vocabulaire imposé** : « **a priori** not delivered » / « presumed
  absent », **jamais** « does not contain » ni « 0 ». Les précurseurs
  s'affichent « generates spicy/woody aroma through oxidation », **pas**
  comme un composé livré tel quel.

  ⚠ `_RECENT_UPDATES` même commit.

  **FAIT (2026-08-30).** Nouveau mode `app._coverage` ("Explore — Hopping
  plan"). Saisie : `st.multiselect` de houblons (jusqu'à 6) puis, par
  houblon, un `st.segmented_control(selection_mode="multi")` de stades --
  un houblon ajouté à 2 stades donne bien 2 entrées de plan indépendantes,
  comme demandé, sans widget "plan builder" séparé. Grille : une COLONNE PAR
  ADDITION (houblon × stade, ex. "Citra · Whirlpool"), pas par houblon ni
  par stade seul -- lisible sans ambiguïté sur quelle addition livre quoi.
  Réutilise le vocabulaire/ordre/catégories chimiques du 2e barplot Compare
  Hops via les MÊMES fonctions (`_compound_category`, `_compound_display_
  label`, même source `reference.PROCESS_SURVIVAL`) -- **PAS** le même objet
  Vega-Lite `_compare_category_gutter` littéral (bâti sur mesure pour la
  géométrie d'un barplot horizontal, ne correspondrait à rien pour une
  grille) : `st.dataframe` à la place, convention déjà établie du projet.
  Distinction honnête au niveau CELLULE entre "a priori not delivered"
  (composé jamais mesuré chez ce houblon) et "Lost during this addition"
  (composé mesuré, mais `state` T119 = "lost" à CE stade précis) -- deux
  affirmations différentes, jamais confondues. Section "A priori not
  covered" : badges terracotta pour les composés vraiment absents (avec
  nuance "not enough data to say either way" si `measured_source_missing`),
  sous-section grise séparée pour les composés precursor-only (génèrent un
  arôme par oxydation sans être livrés). Encart explicatif : compte de
  couverture RÉEL calculé en direct sur la base (pas de nombre figé, contrairement
  au brouillon du ticket) + le résultat de T122 (3 composés peu informatifs,
  7 discriminants, sélinène à part). Vérifié en direct (Chrome, dark ET
  light) : grille/badges/expander corrects sur un plan Citra boil+whirlpool
  (linalol lost au boil / delivered au whirlpool, exactement T119 ; humulène/
  caryophyllène/farnésène en precursor aux deux stades ; sélinène a priori
  absent, citra n'en a aucune mesure). 10 nouveaux tests (5 unitaires sur
  `_coverage_cell_text`, 5 AppTest sur `_coverage`), suite verte (391 tests).

  **Addendum (2026-08-30, retour utilisateur en test réel : Citra +
  Mosaic, sélinène manquant).** « I have no idea how to add this compound.
  Is it possible to show examples of hops and the process of addition ».
  Panneau "Where would these come from?" ajouté dans la carte "A priori not
  covered" : pour CHAQUE composé non couvert (plain ET precursor-only),
  `app._coverage_delivering_stages` (lecture pure de `matching.compound_
  survival`, quels stades T119 livrent RÉELLEMENT ce composé -- jamais
  precursor/lost) + `app._coverage_source_suggestions` (houblons RÉELS avec
  ce composé mesuré, triés par quantité -- ceux déjà dans le plan signalés
  à part : "add it at PFDH too", pas une nouvelle variété à chercher).
  **Pas un solveur** (T120/T122 l'interdisent explicitement) : aucun
  houblon n'est ajouté automatiquement, aucun blend n'est proposé -- une
  simple lecture de données déjà chargées, symétrique à la question
  houblon->composés déjà posée par le reste de l'outil. Vérifié en direct
  (Chrome) sur le scénario RÉEL signalé : Citra (whirlpool) + Mosaic (afdh)
  -> "Selinene — delivered only from a PFDH addition; real examples with
  measured data: Topaz, Ella." 5 nouveaux tests (états delivering stages,
  déjà-dans-le-plan vs. exemples réels, repli honnête sans aucune donnée),
  suite verte (396 tests).

- [x] **T122 — Garde-fou : l'outil discrimine-t-il vraiment ?**
  *À faire AVANT d'écrire la GUI de T121.*

  **Le risque, chiffré** : 5 composés sur 11 sont présents chez presque tous
  les houblons — myrcène 246 lignes, humulène 238, caryophyllène 227,
  farnésène 226, linalol 219 (sur 189 houblons, plusieurs sources par
  houblon). Un plan quelconque « couvrira » donc toujours ceux-là et la grille
  paraîtra pleine quoi qu'on fasse. Ce sont **géraniol (196), isobutyrate
  (31), ketones (33), thiols (22)** qui discriminent réellement.

  **Mesure à produire** : sur ~20 plans réalistes (2 à 4 houblons, stades
  variés), compter **combien de composés changent d'état d'un plan à
  l'autre**. Écrire le résultat chiffré dans ce ticket.

  **Conséquence si la mesure confirme** : la GUI doit **mettre en avant les 4
  composés discriminants** et reléguer visuellement les 5 ubiquitaires (section
  repliée « always present »), sinon l'outil est joli et ne dit rien.

  **FAIT (2026-08-30) -- MESURE RÉALISÉE, HYPOTHÈSE DE DÉPART INFIRMÉE SUR
  LE DÉCOUPAGE EXACT (mais le risque global est réel, juste pas sur les
  composés attendus).** 20 plans réalistes (2-4 houblons courants -- Citra,
  Mosaic, Simcoe, Amarillo, Centennial, Cascade, Galaxy, Nelson Sauvin, El
  Dorado, Idaho 7, Sabro, Motueka, Enigma, Vic Secret, Azacca, Ekuanot,
  Talus, Loral, Comet, Willamette, Saaz, Chinook, Columbus, Wai-iti, Rakau,
  Riwaka, Pacifica -- stades variés boil/whirlpool/afdh/pfdh), passés dans
  `matching.hopping_plan_coverage` (script `t122_measure.py`, base réelle
  187 houblons). Résultat, état (`delivered`/`presumed_absent`) sur les 20
  plans :

  | Composé | États vus | Delivered/20 |
  |---|---|---|
  | myrcène | delivered seul | 20/20 |
  | linalol | delivered seul | 20/20 |
  | géraniol | delivered seul | 20/20 |
  | sélinène | presumed_absent seul | 0/20 |
  | beta-pinène | **les deux** | 17/20 |
  | humulène | **les deux** | 10/20 |
  | caryophyllène | **les deux** | 10/20 |
  | farnésène | **les deux** | 9/20 |
  | isobutyrate | **les deux** | 12/20 |
  | ketones | **les deux** | 13/20 |
  | thiols | **les deux** | 13/20 |

  **Ce que ça change vs. l'hypothèse de départ** : la couverture COMPOSITION
  seule (nombre de houblons ayant une valeur mesurée) prédisait 5 composés
  "toujours présents" (myrcène/humulène/caryophyllène/farnésène/linalol).
  En combinant avec la survie au procédé (T119), **seuls 3 composés sont
  réellement toujours "delivered" quel que soit le plan** : myrcène, linalol,
  géraniol -- parce qu'un plan réaliste a presque toujours AU MOINS un
  houblon à un stade whirlpool/afdh/pfdh, et ces 3 composés sont "kept" à
  ces 3 stades (myrcène "partial" au whirlpool suffit aussi à livrer).
  **Humulène/caryophyllène/farnésène ne discriminent PAS pour la raison
  attendue (rareté de mesure) mais pour une AUTRE raison, plus intéressante** :
  leur `state` T119 est "precursor" au boil ET au whirlpool, et "lost" en
  AFDH -- ils ne sont réellement "delivered" QU'à un stade PFDH. Un plan
  sans aucun houblon en PFDH ne les livre jamais, quelle que soit la
  composition. C'est donc le CROISEMENT composé×stade (T119), pas la seule
  rareté de mesure (T120's `comp`), qui pilote la discrimination pour ces
  3-là. Beta-pinène discrimine bien pour la raison attendue (135/187 houblons
  mesurés, ET son `state` T119 ne devient "kept" qu'en afdh/pfdh -- jamais
  au boil/whirlpool). Isobutyrate/ketones/thiols discriminent comme prévu
  (rareté BarthHaas). Sélinène ne discrimine jamais dans un plan réaliste
  (2/187 houblons -- Ella, Topaz -- absents de l'échantillon) : toujours
  `presumed_absent`, mais dans l'autre sens que les "toujours présents"
  (c'est un composé "toujours absent en pratique", pas "toujours livré").

  **Conséquence RÉVISÉE pour T121** (le risque de départ était réel, la
  liste ne l'était pas) : mettre en avant **7 composés discriminants**
  (beta-pinène, humulène, caryophyllène, farnésène, isobutyrate, ketones,
  thiols) ; reléguer en section repliée « always present » **3 composés**
  (myrcène, linalol, géraniol) ; traiter **sélinène** à part (« rarely
  measured — 2/187 hops », jamais dans la même section que les "always
  present", sens opposé). T121 doit lire ce tableau, pas la liste de départ
  du ticket ci-dessus (gardée telle quelle comme trace de l'hypothèse
  initiale, volontairement pas corrigée en place).

  C'est l'analyse qui manquait à `combine()` et qui a coûté son retrait.

- [ ] **T133 — Stade « Late boil » (5 min) distinct de « boil »**

  **Origine** : question utilisateur en direct (2026-08-30), en testant T121 :
  « I'm surprized we only have boil / whirlpool / afdh / pfdh. Why don't we
  have late boil for example? Should we rename whirlpool by "LateBoil(5min)/
  Whirlpool/HopStand"? ».

  **Décision de cadrage prise en direct (à ne pas revenir dessus sans
  raison neuve)** : NE PAS fusionner « late boil » dans « Whirlpool ».
  Chimiquement distincts — un ajout à 5 min de la fin d'ébullition reste
  sous ébullition ACTIVE (rolling boil), plus proche de « boil » que de
  « whirlpool » (post-ébullition, plus d'apport de chaleur actif). Ajouter
  un VRAI 5e stade plutôt qu'un renommage.

  **Pourquoi ce n'est pas cosmétique** : `reference.PROCESS_SURVIVAL_
  EXPLANATIONS["direct traces, contributes via oxidation"]` documente déjà
  qu'humulène/caryophyllène ont besoin d'une ébullition de PLUS de ~20
  minutes pour produire leurs dérivés d'oxydation (épicé/boisé) — un ajout
  à 5 min n'atteint jamais ce seuil. Le stade "boil" actuel de T119
  (`state="precursor"` pour humulène/caryophyllène/farnésène/sélinène)
  suppose implicitement une exposition PLEINE (60 min depuis le début),
  fausse pour un ajout tardif : à 5 min, ces composés devraient plutôt
  rester `kept` (forme brute, pas encore oxydée) qu'à `precursor`.

  **Ce qui est solidement sourcé pour la nouvelle colonne** :
  - Sesquiterpènes (humulène/caryophyllène/farnésène/sélinène) : `kept` à 5
    min (sous le seuil des ~20 min), pas `precursor` — direct depuis la
    source déjà citée ci-dessus.

  **Ce qui NE l'est PAS encore, à trancher AVANT d'écrire le code** :
  myrcène/linalol n'ont que 2 points de données chiffrés (Janish : ~50% de
  perte à 10 min, quasi totale à 60 min) — aucun chiffre à 5 min. Extrapoler
  un état ordinal (`kept`/`partial`) à partir de la FORME de la courbe (perte
  déjà significative à 10 min → probablement `partial`, pas `kept`, à 5 min)
  serait une INFÉRENCE, pas une lecture directe de la source — à valider
  explicitement avec l'utilisateur avant d'écrire quoi que ce soit
  (même règle que partout ailleurs dans ce projet : jamais deviner
  silencieusement). Géraniol/beta-pinène/isobutyrate/ketones/thiols non
  examinés du tout pour ce point — même travail de recoupement source par
  source que T119 à refaire pour ce seul stade.

  **Périmètre** (touche 4 tickets déjà livrés, pas juste une addition) :
  - `reference.PROCESS_STAGE_SURVIVAL` : nouvelle clé de stade
    (`"late_boil"` ou équivalent) sur les 11 composés — 11 nouvelles
    entrées sourcées, pas une extrapolation généralisée à toute la matrice.
  - `matching._PLAN_STAGES`/`compound_survival` : stade reconnu en plus des
    4 existants.
  - `app._COVERAGE_STAGE_LABELS` (T121) : libellé GUI ("Late boil" —
    PAS de fusion avec "Whirlpool", décision ci-dessus), colonne
    supplémentaire dans le `st.segmented_control` par houblon et dans la
    grille.
  - T122 (mesure de discrimination) : à REFAIRE sur les ~20 plans réalistes
    avec le stade en plus — pourrait changer la liste des composés
    "discriminants" vs. "toujours pareil" (le tableau actuel n'a que 4
    stades).

  **Test** : même garde-fou que T119
  (`test_compound_survival_covers_all_eleven_compounds_and_four_stages` →
  CINQ stades), + un cas qui vérifie explicitement qu'humulène/caryophyllène
  ne sont PLUS `precursor` à "late_boil" (c'est le point central du
  ticket).

## 10bis. Idée hors épique (trouvée en auditant un concurrent)

- [x] **T129 — Familles d'arôme comme filtre facetté (Browse / By-descriptor)**

  **Origine** : audit demandé par l'utilisateur (2026-08-27) du Каталог
  (Catalog) de hop-finder.vercel.app pour voir s'il apporte quelque chose
  d'absent de ce backlog. Conclusion de l'audit : presque tout recoupe déjà
  du décidé/planifié (leur tri « survivabilité » = les données pixel déjà
  rejetées en D2 ; leurs tags de style = T83/T84 ; leur « souvent utilisé
  avec » chiffré = `hop_pairings` BeerMaverick + T87 ; leur tri popularité =
  T108). **Seule chose distincte** : leur filtre latéral groupe les ~175
  mots d'arôme en **9 familles larges** (tropical, agrumes, baies, fruits à
  noyau, floral, herbacé, épicé, résineux/boisé, sucré/dessert), chacune
  avec un compteur, plutôt qu'une liste plate de mots à cocher un par un.
  Explicitement écarté de ce ticket, sur demande utilisateur : tout ce qui
  suppose un compte utilisateur côté hop-finder (favoris, stock personnel)
  — hors de portée d'un outil sans compte.

  **Ce que c'est, et ce que ce n'est PAS** : une taxonomie d'AFFICHAGE pour
  filtrer plus vite, rien côté données. **Pas** une nouvelle source externe
  à ingérer — le vocabulaire complet (138 termes réels, `hop_descriptors`)
  est déjà en base. Le seul travail est de définir la table de groupement
  {mot -> famille}.

  ⚠ **Ne PAS dériver les familles automatiquement.** Précédent direct dans
  ce projet : les descripteurs auto-dérivés de FooDB ont convergé vers des
  mots génériques et ont été rejetés **deux fois** (voir CLAUDE.md) ; le tri
  des 49 mots BarthHaas hors vocabulaire (T79) a été fait **à la main avec
  l'utilisateur**, jamais par heuristique. Même règle ici : proposer une
  répartition initiale des 138 termes réels de `hop_descriptors` en ~8-10
  familles (calquées librement sur l'idée du concurrent, PAS recopiées mot
  pour mot — leur liste est en russe et sur LEUR vocabulaire, pas le nôtre),
  puis la faire **valider/corriger par l'utilisateur** avant tout câblage
  GUI. Un mot qui ne rentre clairement dans aucune famille reste hors
  groupement plutôt que forcé quelque part au jugé.

  **Où l'utiliser** :
  1. `by-descriptor` — le sélecteur de pills est actuellement une liste
     plate des 138 termes (voir `app._by_descriptor`) ; un premier niveau
     par famille réduirait le bruit visuel avant de choisir les mots précis.
  2. `browse` — filtre facetté optionnel sur la liste de houblons (n'existe
     pas aujourd'hui : Browse n'a qu'un `st.selectbox` à un houblon, pas de
     liste filtrable — vérifier si ça vaut la peine d'ajouter une vue liste
     avant de faire ce filtre, sinon ce point ne s'applique qu'à
     `by-descriptor`).

  **Nouvelle constante** : `reference.DESCRIPTOR_FAMILIES` (dict
  `{descriptor: famille}`), sur le modèle de `DESCRIPTOR_ALIASES` — jamais
  un fichier YAML séparé pour ce qui reste une table de mapping courte et
  stable, cohérent avec le choix déjà fait pour les alias.

  **Test** : garde-fou vérifiant que toute clé de
  `reference.DESCRIPTOR_FAMILIES` existe réellement dans le vocabulaire
  `hop_descriptors` — même principe que
  `test_ingredient_descriptors_keys_and_terms_match_real_vocabulary`.

  **Compte rendu partiel (2026-08-29) — `reference.py` câblé, GUI PAS
  encore faite.** Répartition initiale (9 familles, ~8-10 cible) présentée
  à l'utilisateur, puis soumise à TROIS revues externes contradictoires
  demandées par l'utilisateur avant validation. Arbitrage explicite :
  - **Rejeté** l'axe chimique/provenance proposé par une revue (tag
    thiol/ester/Maillard + source hop/levure/malt/bois, similarité
    pondérée) — système différent et plus large qu'une taxonomie
    d'affichage, retombe sur les mêmes murs déjà rencontrés par ce projet
    (`combine()`/NNLS retiré pour dégénérescence sur données éparses ;
    dérivation FooDB rejetée deux fois) et une erreur de catégorie pour un
    vocabulaire houblon-only (`hop_descriptors` dit à quoi un HOUBLON
    ressemble par analogie, pas ce qui l'a produit).
  - **Accepté** les corrections de frontière convergentes (2-3/3 revues) :
    nouvelles familles Pome fruit, Melon, Vinous/wine, Alliaceous/sulfur,
    Dairy/creamy ; Herbal (26 mots, "dumping ground" unanime) scindée en
    Herbal + Green/vegetal ; fennel → Spicy ; woodruff → Sweet/dessert.
  - **Arbitrages gardés contre les revues**, signalés à l'utilisateur :
    banana/coconut restent Tropical, lemon balm/lemongrass/marmalade
    restent Citrus (ce sont ce que ces mots SENTENT pour un sélecteur GUI,
    pas leur botanique/chimie) ; pas de famille "dried/dark fruit" séparée
    (3 mots, jugé trop mince) ; Herbal pas subdivisée davantage
    (tea/mint/cooling).
  - **`fruity`/`sweet aromatic`** (37 et 12 houblons réels — vérifié, pas
    théorique) : question explicite de l'utilisateur après la 1ère revue
    de l'artefact ("dropping them or single category?"). Décision : ni
    l'un ni l'autre — nouvelle famille **Generic** (hyperonymes, pas des
    familles olfactives) plutôt que retirés, pour ne jamais devenir
    invisibles le jour où le sélecteur passe à deux niveaux.

  Revue faite via un artefact HTML dédié (16 cartes-familles, mots
  "contestés" marqués en pointillés, republié 2 fois pendant l'itération)
  plutôt qu'un mur de texte — validé par l'utilisateur ("go ahead and wire
  it in reference.py").

  **`reference.DESCRIPTOR_FAMILIES` écrit** : 138/138 clés (couverture
  complète vérifiée en direct sur `aromahops.db`, bien que le garde-fou
  n'exige que clés ⊆ vocabulaire, jamais l'inverse — un futur mot ingéré
  reste utilisable dans le sélecteur plat existant sans faire échouer le
  test). 16 familles au total (15 olfactives + Generic). 363 tests
  passent (+1, `test_descriptor_families_keys_match_real_vocabulary`).

  **Câblage GUI `by-descriptor` (2026-08-29, même jour)** : `st.pills`
  "Family" (16 options) juste au-dessus du multiselect "Descriptors" —
  NARROWING pur sur les `options` du multiselect, jamais un second filtre
  appliqué au résultat (aucune famille cochée = liste plate complète
  inchangée, comportement par défaut identique à avant). Piège réel évité
  AVANT vérification live (pas trouvé en bogue, anticipé en écrivant le
  code) : changer `options` d'un `st.multiselect` d'un rerun à l'autre
  fait planter Streamlit (`StreamlitAPIException`) si une valeur déjà
  choisie sort de la nouvelle liste — corrigé en passant `options =
  narrowed ∪ déjà_sélectionné` (lu depuis `st.session_state` AVANT de
  reconstruire le widget, clé fixe `by_descriptor_text_multiselect`), donc
  un mot déjà choisi reste toujours valide même en changeant de famille
  ensuite. Un mot du vocabulaire réel absent de `DESCRIPTOR_FAMILIES`
  (aucun cas aujourd'hui, mais le garde-fou ne l'exclut pas pour l'avenir)
  reste choisissable tant qu'aucune famille n'est cochée. Point Browse
  (liste filtrable) laissé de côté, comme prévu par le ticket : Browse n'a
  aujourd'hui qu'un `st.selectbox` à un houblon, pas de vue liste.

  2 nouveaux tests (narrowing par famille sur le vocabulaire jouet
  citrus/woody/floral/resinous ; garde-fou anti-crash sur changement de
  famille après sélection). 2 tests existants adaptés (`at.pills[0]`
  positionnel → `at.pills(key=...)`, un 2e widget pills s'étant intercalé
  avant celui de la roue d'arôme). 365 tests passent. Vérifié en direct
  (Chrome, base réelle) : 16 familles affichées, narrowing sur "Berry"
  confirmé (liste restreinte à berry/black currant/blackberry/blueberry/
  cranberry/gooseberry...).

- [ ] **T130 — Recherche de style BJCP par alias (Beer styles)**

  **Origine** : discussion T85 (2026-08-27). beer-analytics.com a des noms
  de style plus granulaires que BJCP 2021 sur certaines familles (ex. 7
  variantes de « Specialty IPA » : Belgian/Black/Brown/Brut/Red/Rye/White
  IPA — chacune avec un volume réel non négligeable, 184 à 6 179 recettes
  selon la variante, vérifié en direct sur les charts `abv-histogram`
  cache). BJCP ne définit qu'**un seul** style_id (21B) avec un seul jeu de
  vital stats officielles pour tout ce groupe — ajouter « Black IPA » comme
  une ligne à part dans `beer_styles` fabriquerait une entrée BJCP qui
  n'existe pas (le style_id serait inventé, et copier les vital stats de
  21B laisserait croire que BJCP les a définies spécifiquement pour Black
  IPA). **Refusé pour cette raison** (décision utilisateur explicite,
  2026-08-27) : `beer_styles` reste un reflet fidèle et exclusif du
  styleguide BJCP 2021 réel, jamais mélangé à une taxonomie tierce plus
  fine.

  **Ce que ce ticket fait à la place** : rendre ces noms plus fins
  **cherchables** dans l'outil `browse` (mode « Beer styles », T82) sans
  toucher `beer_styles`. Étendre `data/mappings/beer_style_aliases.yaml`
  (même fichier que T84/T85, nouvel usage) avec ces variantes -> `21B`
  (et toute variante similaire découverte ailleurs), puis faire en sorte
  que le sélecteur de style de `browse` accepte de RÉSOUDRE un nom tapé qui
  matche une clé du fichier d'alias vers l'entrée BJCP correspondante —
  taper « Black IPA » doit ouvrir la fiche « Specialty IPA (21B) »,
  honnêtement étiquetée comme telle (jamais une fiche « Black IPA »
  fabriquée). Les styles beer-analytics **sans aucun équivalent BJCP** dans
  nos 110 styles ingérés (ex. Kellerbier, Kentucky Common, Lichtenhainer,
  London Brown Ale, Piwo Grodziskie, Pre-Prohibition Lager/Porter,
  Roggenbier, Sahti — vérifiés absents en direct, pas une ambiguïté à
  trancher) restent `null` dans le fichier d'alias : rien à résoudre pour
  eux tant qu'un ticket séparé ne construit pas une vue qui ne dépend pas
  de `beer_styles`.

  **Dépend de T85** (le fichier d'alias doit porter les entrées beer-
  analytics, découvertes au fil de son ingestion).

  **Statut** : opportuniste, ne bloque rien et n'est bloqué par rien
  -- à faire quand une session GUI légère est utile entre deux tickets plus
  lourds.

- [ ] **T131 — `hop_typical_styles` : dans quels styles un houblon est-il utilisé**

  **Origine** : découvert en implémentant T88 (2026-08-28/29). Chaque page
  houblon beer-analytics.com porte un chart `typical-styles-relative.json`
  (et son pendant `typical-styles-absolute.json`) que le ticket T88 listait
  explicitement ("les styles typiques de ce houblon") mais dont le
  `CREATE TABLE hop_usage_stats` fourni ne prévoyait aucune colonne — cette
  table n'est indexée QUE par `use_type` (étape de procédé), alors que
  cette donnée est une relation houblon→STYLE, un axe complètement
  différent. Vérifié en direct sur Citra : trace `bar`, `x` = nom de style
  (`"Hazy IPA"`, `"IPA"`, `"White IPA"`, `"Double IPA"`, `"Specialty IPA"`...),
  `y` = part relative (0,55 pour Hazy IPA, la plus haute) — format identique
  à `usage-types.json`, même parseur `parsers.plotly_traces` réutilisable
  directement, aucun nouveau parseur nécessaire.

  **Ce que ça apporte** : c'est la relation INVERSE de `style_hop_usage`
  (T86, "pour ce style, quels houblons sont populaires") — ici "pour ce
  houblon, dans quels styles est-il populaire", empirique (recettes
  réelles), à ne jamais confondre avec `hop_beer_styles` (T83, éditorial —
  suggestion Yakima/BeerMaverick, pas une mesure de fréquence). Les trois
  restent des relations séparées, jamais fusionnées (même règle que les
  trois relations houblon↔houblon établie en T25/T109).

  **Table proposée** (à confirmer/ajuster en implémentant, comme tous les
  tickets de ce backlog) :
  ```sql
  CREATE TABLE hop_typical_styles (
      variety TEXT, hop_name TEXT, style_label TEXT, style_id TEXT,
      relative_share REAL, source TEXT, fetched_at TEXT,
      PRIMARY KEY (hop_name, style_label)
  );
  ```
  `style_label` = nom BRUT tel qu'écrit par beer-analytics (comme
  `hop_beer_styles.style_label`, T83) ; `style_id` résolu via le même
  `data/mappings/beer_style_aliases.yaml` (T84/T85, déjà enrichi côté
  beer-analytics par T85-T87 — bonne chance qu'une bonne partie résolve
  déjà sans travail de curation supplémentaire).

  **Dépend de T88** (réutilise les pages houblon déjà énumérées/cachées,
  même boucle de crawl possible pour ne pas refaire 435 fetches de page).

  **Statut** : opportuniste, comme T130 -- ne bloque rien, découvert en
  marge d'un autre ticket plutôt que planifié.

- [ ] **T132 — Revue de licence : CC-BY-SA 4.0 (beer-analytics.com)**

  **Origine** : réponse de Christian Scheb (mainteneur beer-analytics.com)
  à la prise de contact T89 (2026-08-29, voir mémoire `beer_analytics_
  contact_outcome`) -- crawl explicitement autorisé, mais "All content...
  is licensed under CC-BY-SA 4.0. So please have a look at the license
  terms regarding attribution and derivative works."

  **Ce qui manque aujourd'hui** : `docs/DATA_SOURCES.md` et la section
  « Licence » de CLAUDE.md ne mentionnent PAS cette licence pour
  beer-analytics — seule une attribution générique est documentée (T89).
  Contrairement aux sources déjà cataloguées (FooDB/FlavorDB2 = non
  commercial ; BeerMaverick = pas de licence de données publiée ;
  BarthHaas/Yakima = pas de CC connue), **CC-BY-SA a une clause ShareAlike
  réelle** : si `aromahops.db` compte comme une œuvre dérivée incorporant
  ces données (`style_recipe_stats`, `style_hop_usage`,
  `style_hop_pairings`, `hop_usage_stats`, T85-T88), ShareAlike pourrait
  exiger que CETTE PARTIE de la base soit elle-même redistribuée sous
  CC-BY-SA 4.0 — plus strict que le MIT du code, et potentiellement en
  tension avec le dépôt `HopFinder-db` actuellement privé/sans licence
  affichée.

  **Travail** :
  1. Lire le texte réel de CC-BY-SA 4.0 (pas juste "attribution requise") —
     en particulier ce que "derivative work" couvre pour une base de
     données dérivée d'agrégats statistiques (vs. republier leurs données
     brutes telles quelles).
  2. Trancher si `aromahops.db` (ou au moins les 4 tables T85-T88)
     constitue une œuvre dérivée au sens de la licence, et ce que ça
     implique pour `HopFinder-db` (dépôt privé aujourd'hui) et pour le
     déploiement Streamlit Cloud public.
  3. Mettre à jour `docs/DATA_SOURCES.md` (section beer-analytics.com) et
     CLAUDE.md (section Licence) avec la conclusion, quelle qu'elle soit —
     jamais laisser la question implicite.

  **Statut : explicitement reporté à la fin du projet, sur demande
  utilisateur** ("I need to review the license question at some point but
  I first want to finish the app") — ne bloque aucun autre ticket, mais ne
  doit pas être oublié avant tout élargissement de la diffusion (dépôt
  rendu public, usage commercial, etc.).

## 11. Ordre d'attaque recommandé

Tous les tickets sont désormais au niveau **spec d'implémentation** : DDL,
noms de fonctions, valeurs attendues, cas limites, tests, critères de
vérification. Lire d'abord **§1bis Contrat de ticket**, qui vaut pour tous et
n'est répété dans aucun.

**Lot 0 — correctifs, avant tout le reste.** Courts, indépendants, signalés
en usage réel. → **T125** (bracket « Oxygen containing » + renommage en
« Oxygen containing comp. »), **T123** (suffixe « Hops » parasite).

1. **Lot 1 — styles, aucune dépendance externe incertaine**
   T81 → T82 → T84 → T83, puis T106, T107.
   Livre en entier « choisir un style et voir ses ranges comme Brewfather »,
   plus l'association houblon→style qui dort déjà dans le crawl Yakima.
   ⚠ T84 avant T83 : la table de correspondance doit exister avant qu'on
   remplisse `hop_beer_styles.style_id`.

2. **Lot 2 — statistiques de recettes (beer-analytics)**
   **T85 d'abord** (infrastructure : client HTTP, cache, extraction Plotly —
   tout le reste la réutilise), puis **T88** (socle empirique de T99),
   puis T86, T87, T89.
   Ensuite les usages : T99, T108, T105, T103.

3. **Lot 3 — corpus brut MMuM**
   T91 → **T92** (la réconciliation des noms conditionne tout ce qui suit) →
   T93 → T94, puis **T126 → T127** (barplots de type d'ajout), puis T104.
   Seul chemin vers les triplets et quadruplets, et vers les combinaisons
   **par stade** que personne d'autre ne calcule.

4. **Lot 4 — procédé**
   T119 → T120 → **T122** (mesurer que l'outil discrimine) → T121 (GUI).
   T115 et T115b sont faits, plus rien ne bloque.
   ⚠ T122 **avant** T121, pas après : si la mesure montre que la grille est
   toujours pleine, la GUI change de forme.

**Transverses et opportunistes** — avancent quand une source apparaît, ne
bloquent rien : T96/T97 (espèces de thiols, méthyl géranate), T116/T128
(lots YCH, si des numéros deviennent disponibles), **T117** (onglet
Survivables sur indice dérivé — faisable dès maintenant, ne dépend de rien),
T118 (Brewfather), T100/T101 (régression, T101 conditionné par T100),
T102 (Blend Explorer), T109/T110/T112 (vocabulaire), T113/T114 (docs),
**T129** (familles d'arôme, GUI seule — faisable dès maintenant).

⚠ **T132** (revue de licence CC-BY-SA 4.0) n'est PAS opportuniste comme les
tickets ci-dessus — explicitement **reporté à la toute fin du projet** sur
demande utilisateur (2026-08-29), à ne reprendre qu'une fois le reste
terminé, jamais avant.

### Dépendances dures — à ne pas contourner

| Ticket | Dépend de | Pourquoi |
|---|---|---|
| T82, T105 | T81 | pas de page style sans table style |
| T83 | T84 | `style_id` ne se remplit pas sans la correspondance |
| T86, T87, T88 | T85 | client HTTP, cache et extraction Plotly communs |
| T92 | T91 | rien à réconcilier sans corpus |
| T93, T126, T127 | T92 | un nom non résolu fausse tout comptage |
| T94 | T93 + T82 | les combinaisons s'affichent dans la page style |
| T99 (a) | T88 | la couche empirique EST `hop_usage_stats` |
| T101 | T100 | pas de modèle sans calibration préalable |
| T103, T104 | T81 + T86 | croiser suppose les deux mondes |
| T121 | T119 + T120 + T122 | la GUI dépend de la mesure de discrimination |
| T127 | T126 | même agrégat, même binning, même seuil |
| T116 | T128 | un client sans numéros de lot ne sert à rien |

### Contacts à envoyer (indépendants du code)

- `docs/OUTREACH_beer-analytics.md` → l'auteur de beer-analytics. Prévenir
  avant de lire ses endpoints, et demander un agrégat de co-occurrence
  n-aire (seul chemin vers des triplets à grande échelle).
- `docs/OUTREACH_yakima-chief.md` → `Brewinghelp@yakimachief.com`. Demander
  les survivables **agrégés par variété**, et poser les deux questions
  techniques (unité, 3MH lié) qui débloqueraient T116.

**Décisions** : les 4 (D1–D4) sont tranchées. Aucune ne bloque le démarrage.
