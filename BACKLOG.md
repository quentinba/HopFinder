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

- [ ] **T85 — Client `ingest_beer_analytics` + distributions par style**

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

- [ ] **T86 — `style_hop_usage` : quels houblons pour ce style**

  **Dépend de T85** (réutiliser `_beer_analytics_get` / `_plotly_traces`).

  **Charts** : `popular-hops.json` (part de recettes dans le temps, une trace
  par houblon avec `x` = mois, `y` = `recipes_percent`) et
  `popular-hops-amount.json` (dosage).

  ⚠ `popular-hops.json` est une **série temporelle**, pas une valeur unique.
  Décision : stocker la **dernière valeur non nulle** de chaque trace comme
  part actuelle, ET la moyenne sur les 24 derniers mois. Ne pas écraser l'une
  par l'autre — ce sont deux questions différentes (« quoi maintenant » vs
  « quoi en général »).

  ```sql
  CREATE TABLE style_hop_usage (
      style_slug TEXT, style_id TEXT, hop_name TEXT, variety TEXT,
      recipes_pct_latest REAL, recipes_pct_avg24m REAL,
      amount_q1 REAL, amount_median REAL, amount_q3 REAL,
      source TEXT, fetched_at TEXT,
      PRIMARY KEY (style_slug, hop_name)
  );
  ```
  `variety` résolu via `ingest._resolve_hop_variety`, `NULL` si inconnu.

  **À vérifier pendant l'implémentation** : la page de style porte des
  attributs `data-filter` (`aroma`, `bittering`, `dry-hop`, `base`,
  `cara-crystal`…). Regarder s'ils correspondent à des **URLs de charts
  distinctes** ou à un filtrage côté client. Si ce sont des URLs, capturer la
  ventilation par type d'usage — c'est la donnée la plus intéressante de ce
  ticket. Si c'est du client, le noter et passer.

- [ ] **T87 — `style_hop_pairings` : paires réelles par style**

  **Chart** : `/styles/<cat>/<style>/charts/hop-pairings.json`. Une trace de
  type `box` par houblon partenaire, avec `name` (le houblon), `q1`,
  `median`, `q3`, `lowerfence`, `upperfence`, `mean` — la distribution de la
  **part de charge houblon** (`amount_percent`) de ce partenaire.

  ```sql
  CREATE TABLE style_hop_pairings (
      style_slug TEXT, style_id TEXT, hop_name TEXT, variety TEXT,
      share_q1 REAL, share_median REAL, share_q3 REAL, share_mean REAL,
      source TEXT, fetched_at TEXT,
      PRIMARY KEY (style_slug, hop_name)
  );
  ```

  ⚠ **Ce sont des PAIRES, et seulement des paires.** `calculate_hop_pairings`
  côté beer-analytics est un JOIN `rh1.kind_id != rh2.kind_id`, seuil
  `HOP_MIN_RECIPES = 20`. Les triplets viennent de T93 et de nulle part
  ailleurs. **Ne jamais dériver un triplet de trois paires** — ce serait une
  invention. La GUI doit dire « pairs » explicitement.

- [ ] **T88 — `hop_usage_stats` : où ce houblon est réellement utilisé**
  *Socle empirique de T99. À faire EN PREMIER dans l'épique B.*

  **Charts par houblon** (URL : `/hops/<purpose>/<slug>/charts/…`, où
  `<purpose>` vaut `aroma`/`bittering`/`dual-purpose` — le récupérer depuis la
  page du houblon, ne pas le deviner) :
  - `usage-types.json` → une trace `bar`, `x = ["Mash","First Wort","Boil",
    "Aroma","Dry Hop"]`, `y` = nombre de recettes. Exemple réel Citra :
    `[439, 5317, 98935, 67838, 90059]` sur 154 571 recettes.
  - `amount-used-per-use.json` → une boîte par type d'usage
    (`q1`/`median`/`q3`).
  - `typical-styles-relative.json` → les styles typiques de ce houblon.

  ```sql
  CREATE TABLE hop_usage_stats (
      variety TEXT, hop_name TEXT, use_type TEXT, recipes_count INTEGER,
      amount_q1 REAL, amount_median REAL, amount_q3 REAL,
      source TEXT, fetched_at TEXT,
      PRIMARY KEY (variety, use_type, source)
  );
  ```

  ⚠ **`Aroma` chez beer-analytics ≠ whirlpool.** Leur enum vient des formats
  de recette importés ; `Aroma` couvre les additions tardives de fin
  d'ébullition/flameout. Ne pas le renommer « Whirlpool » dans la GUI, et ne
  pas le confondre avec le `Whirlpool` de MMuM (T126), qui est un champ
  distinct d'une autre source. **Les deux vues coexistent sans être
  fusionnées.**

  **Couverture attendue** : leurs slugs de houblons ne couvrent pas nos 189
  variétés. Rapporter le taux de résolution comme ailleurs (143/203 pour
  BeerMaverick), et laisser `NULL` plutôt que de forcer une correspondance.

- [ ] **T89 — Posture d'accès, cache, attribution, et prise de contact**

  **Technique** (déjà décrit en T85, rappelé ici comme critère de recette) :
  User-Agent identifiable, une seule passe, 1 s entre requêtes, cache disque,
  `fetched_at` par ligne.

  **Attribution GUI, obligatoire** partout où une de ces données apparaît :
  « Recipe statistics: beer-analytics.com — aggregated from public homebrew
  recipes ». Section dédiée dans `docs/DATA_SOURCES.md` avec la date de fetch
  et le taux de couverture réel.

  **Prise de contact** : envoyer le message rédigé dans
  `docs/OUTREACH_beer-analytics.md`. Deux buts — prévenir avant de lire
  régulièrement leurs endpoints, et demander un **agrégat de co-occurrence
  n-aire** (le seul chemin vers des triplets à grande échelle, cf. D3).
  Proposer une contribution en retour (nos variétés BarthHaas/Yakima récentes
  normalisées, pour leur `hops.csv`).

---

## 4. Épique C — Paires, triplets, quadruplets

- [ ] **T91 — Ingestion du corpus MMuM**

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

- [ ] **T92 — Réconciliation nom-de-recette → `variety`**
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

- [ ] **T99 — Panneau « Recommended usage » dans Browse — deux couches séparées**

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

- [ ] **T100 — Calibrer (b) contre (a) AVANT de parler de « modèle »**

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

- [ ] **T101 — Régression, SEULEMENT si T100 le justifie**

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

- [ ] **T102 — Blend Explorer chimique (dans Compare Hops)**

  Empiler la composition en composés « survivables » de 2-3 houblons, avec
  **nos** données (linalol, géraniol, isobutyrate, thiols).

  **Ce que ça matérialise** : la **règle 3** du handbook YCH — « blender pour
  équilibrer, pas pour empiler ». Exemple donné par YCH et à reproduire :
  Loral (linalol) + Talus (géraniol) = dynamique ; Loral + Crystal (tous deux
  linalol) = plat, unidimensionnel.

  **Branché sur le mode Compare Hops existant**, pas de nouveau mode.
  Idée reprise du hop-finder russe, mais sans aucune de leurs données.

---

## 7. Épique F — Le croisement qui n'existe dans aucun des deux outils

- [ ] **T103 — Outil « Style → houblons » (recettes × arômes)**
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

- [ ] **T105 — Ranges officiels vs ranges observés, côte à côte**

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

---

## 8. Épique G — Petites reprises (rapides, indépendantes)

- [ ] **T106 — Métadonnées d'identité du houblon**

  **Tout est déjà dans des payloads que nous fetchons et jetons.**
  Champs Algolia Yakima disponibles sur 153/153 variétés :
  `imported_fields.cultivar` (Citra → `"HBC 394"`), `variety_id`,
  `experimental` (bool), `organic` (bool), `blend` (bool), `country_code`.
  Côté BeerMaverick (HTML déjà fetché par `ingest_beermaverick`) : parentage,
  année de sortie, sélectionneur — **à vérifier dans le HTML avant de
  promettre**, le ticket ne dit pas qu'ils y sont, il dit d'aller regarder.

  **Colonnes à ajouter à `hops`** (`ALTER` impossible : `init_db` recrée
  tout — modifier le `CREATE TABLE hops` dans `schema.py`) :
  `cultivar TEXT, breeder TEXT, release_year INTEGER, pedigree TEXT,
  is_experimental INTEGER, is_organic INTEGER, is_blend INTEGER`.
  Booléens SQLite en `0`/`1`, `NULL` si l'information n'existe pas —
  **jamais `0` par défaut**, qui affirmerait « ce n'est pas expérimental »
  alors que personne ne l'a dit.

  **GUI** : dans `browse`, juste sous le nom du houblon, avant les key stats.
  Badges pour `experimental`/`organic`/`blend` (uniquement quand `1`),
  ligne de texte pour cultivar/breeder/année/pedigree. Champs absents :
  ne rien afficher, pas de `—`.

- [ ] **T107 — Description éditoriale du houblon**

  **Source** : `imported_fields.description` (Algolia Yakima), présent sur
  **153/153 variétés**, ~2 paragraphes de HTML (`<p>…</p><p>…</p>`).

  **Colonne** : `hops.description TEXT` + `hops.description_source TEXT`.

  ⚠ **Nettoyer le HTML** avant stockage : le champ contient de vraies balises.
  Extraire le texte (les `<p>` deviennent des sauts de paragraphe), ne jamais
  injecter le HTML brut dans la GUI.

  **GUI** : `st.expander` replié dans `browse`, sous les métadonnées de T106.
  ⚠ **Attribution explicite obligatoire** : « Producer description (Yakima
  Chief Hops) » — c'est du **texte marketing d'un vendeur**, jamais présenté
  comme une caractérisation neutre. Même esprit que la réserve affichée sur
  les pairings BeerMaverick.

- [ ] **T108 — Tri/filtre par popularité**

  **Dépend de T88** (`hop_usage_stats.recipes_count`).

  Ajouter un tri « Popularity » dans `browse` et `by-descriptor`, et un filtre
  « exclure les houblons quasi jamais utilisés » (seuil ajustable, défaut
  suggéré : moins de 50 recettes).
  ⚠ Un houblon **sans** donnée de popularité (non résolu côté beer-analytics)
  n'est pas « impopulaire » : le placer dans un groupe « no data », jamais en
  bas d'un tri numérique avec un 0 implicite.

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

- [ ] **T117 — Onglet « Survivables » sur indice dérivé** *(D2 tranchée)*
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

- [ ] **T119 — Matrice composé × stade de procédé**

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

- [ ] **T120 — Calcul de couverture d'un plan de houblonnage**

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

- [ ] **T121 — GUI : le tableau de couverture**

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

- [ ] **T122 — Garde-fou : l'outil discrimine-t-il vraiment ?**
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

  C'est l'analyse qui manquait à `combine()` et qui a coûté son retrait.

## 10bis. Idée hors épique (trouvée en auditant un concurrent)

- [ ] **T129 — Familles d'arôme comme filtre facetté (Browse / By-descriptor)**

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

  **Statut** : opportuniste, ne bloque rien et n'est bloqué par rien
  -- à faire quand une session GUI légère est utile entre deux tickets plus
  lourds.

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
