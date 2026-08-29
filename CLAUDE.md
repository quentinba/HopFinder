# CLAUDE.md — contexte projet hopmatch

Ce fichier donne à Claude Code le contexte et les décisions issues de la conception
de hopmatch. Lis-le avant d'agir. (Détails : `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md`.)

Ce fichier a été condensé le 2026-08-26 (il approchait 220 Ko) : l'historique
détaillé tour par tour (vérifications en direct, deltas de nombre de tests,
valeurs intermédiaires remplacées par un correctif suivant) a été retiré. Seules
les décisions définitives, l'état actuel des données/fonctionnalités, et les
pièges techniques encore pertinents pour éviter de refaire une investigation
déjà close sont gardés. `git log` fait foi pour l'historique complet.

## But
Outil brasseur (nom d'affichage GUI : **HopFinder** — le paquet Python/CLI reste
`hopmatch`) : **note olfactive → molécules → houblons**. Accorder un houblon à un
ajout (yuzu, basilic…). Modes `amplify` (prolonger) et `contrast` (contraster).
L'ajout est dans la bière, donc le houblon n'a pas à le reproduire : le « plafond de
couverture » ne pénalise pas.

## Décisions définitives (ne pas revenir dessus sans raison neuve)

- **`combine()` (NNLS, reproduire un goût par combinaison de houblons) implémenté
  puis RETIRÉ (2026-08-12).** Sur les 506 notes réelles : 0 % ne dépassaient 20 %
  de couverture. Sur les notes à un seul composé productible (majorité), NNLS
  dégénère en un système à une équation où n'importe quel houblon porteur atteint
  un résidu artificiel de 0 (ex. "strawberry"/"passion fruit" retournaient tous
  deux "100% Talus, résidu 0.0" via le géraniol, seul composé commun). Pas un bug
  de méthode — aucun algorithme ne change le recoupement chimique réel. Ne pas
  réintroduire sans une source qui couvre bien plus de composés aromatiques par
  aliment.
- **`amplify()` a le même problème de fond mais n'a PAS été retiré** — un
  avertissement s'affiche à la place (`matching.LOW_COVERAGE_WARNING_THRESHOLD`
  historique, recalibré côté GUI en T76, voir plus bas). Sans descripteurs,
  163/506 notes n'ont QUE le géraniol comme molécule productible → le score se
  réduit à un simple tri par quantité brute de géraniol (Talus/Ekuanot raflent
  #1 sur 44 % des notes concernées). La couche descripteurs
  (`matching.descriptor_overlap`) corrige concrètement le classement quand
  fournie (vérifié : Talus tombe de #1 à #6 sur "strawberry" + descripteurs).
- **`--biotransform` implémenté puis RETIRÉ (2026-08-12).** Science sourcée
  solide (géraniol→citronellol, King & Dickinson 2003 / Michel et al. 2019) mais
  bug de double comptage : les 29 notes demandant du citronellol demandent aussi
  toutes du géraniol, donc la même mesure comptait deux fois. Ne pas réintroduire
  sans corriger le double comptage à la racine.
- **Descripteurs = couche primaire** (roues d'arôme). Robuste, sans concentration.
  Les molécules sont la couche secondaire, optionnelle en GUI Amplify (T76).
- **Pas de seuil OAV codé en dur.** Résolu en direct depuis FlavorDB2 (T75, voir
  section OAV plus bas) — jamais de repli sur un ancien littéral.
- **Le contraste n'est PAS moléculaire.** Dérivé d'une carte d'affinités
  descripteurs (`reference.CONTRAST_AFFINITY`), pas des composés partagés.
- **Matching moléculaire = similarité normalisée-par-composé (TF-IDF)**, pour que
  les molécules-signature pilotent, pas le myrcène ubiquitaire.
- **Honnêteté d'abord** : toujours rapporter la couverture, les molécules
  orphelines, et la provenance (source de donnée) de chaque affirmation affichée.
- **Base EAV multi-sources** : `hop_composition` clé (variety, compound, source) ;
  réconciliation à la LECTURE (moyenne des milieux, provenance tracée), jamais à
  l'écriture. Sources différentes JAMAIS moyennées entre elles quand elles mesurent
  selon des méthodologies distinctes (ex. roue d'arôme Yakima 0-100 vs BarthHaas
  0-8 — voir section BarthHaas).
- **Descripteurs auto-dérivés de FooDB testés et rejetés deux fois** (agrégation
  Flavornet pondérée IDF, puis restreinte aux notes les plus riches en données) :
  converge systématiquement vers les mêmes mots génériques (citrus/spicy/floral)
  à cause d'aldéhydes à chaîne moyenne ubiquitaires. Ne pas retenter sans changer
  de vocabulaire source. `note_descriptors` reste vide par défaut pour toute note ;
  `contrast(descriptors=[...])` fonctionne par sélection manuelle, pas par
  dérivation automatique.
- **`INGREDIENT_DESCRIPTORS` (T76, amorce ingrédient→descripteurs GUI) est un
  jugement direct de l'assistant, PAS une dérivation programmatique FooDB** —
  cette approche avait déjà dégénéré (point précédent). 506 entrées, vocabulaire
  restreint aux 138 descripteurs réels de `hop_descriptors`, garde-fou testé
  (`test_ingredient_descriptors_keys_and_terms_match_real_vocabulary`).
- **`hops.breeder`/`release_year`/`pedigree` (T106) : curation manuelle
  (`data/mappings/hop_breeder_pedigree.yaml`), PAS un parseur regex** — la
  section « Origin and Geneology » de BeerMaverick est de la prose libre,
  phrasée différemment à chaque houblon (vérifié sur 5 pages réelles : jusqu'à
  3 acteurs distincts type "created by X, developed by Y, released through
  Z"), un regex aurait deviné plus qu'il n'aurait extrait. Clé = nom de
  cultivar de base (`ingest._cultivar_base_name`), appliquée à TOUTES les
  lignes `hops` du même cultivar (`ingest._write_hop_identity`) — plusieurs
  crops/licenciés distincts (ex. Amarillo US/Germany, Motueka NZ Hops/
  MacHops) partagent la même généalogie mais sont des lignes `hops` séparées.
- **`contrast_blend`/`amplify_blend` : plusieurs tailles (1-5), houblon de base
  choisi par l'utilisateur, mélange pertinence/pairing réel BeerMaverick — jamais
  une pure couverture gloutonne, jamais une cascade top→pairing→couverture.**
  Historique de méthodologie (T33 → 3 revirements successifs, tous validés par
  l'utilisateur) : couverture pure jugée peu utile (rien ne garantit un usage
  réel conjoint) → priorité à la fréquence de pairing BeerMaverick → ne s'arrête
  plus à couverture complète (`via="relevance"` quand plus rien à couvrir) →
  houblon de base = choix explicite (`via="chosen"`), additions suivantes =
  MÉLANGE pertinence+pairing (filtre les candidats déjà triés par pertinence au
  top-10 pairing d'un houblon du blend, jamais la fréquence brute seule — testé
  par `test_contrast_blend_mixes_relevance_and_pairing_not_pure_frequency`).
  Structuré par `purpose` (T-purpose) : taille 2 garantit un houblon du rôle
  complémentaire (aromatic/bittering) si le houblon de base a un rôle connu et
  unilatéral ; au-delà, ne recrute que des aromatiques. Repli silencieux sur le
  comportement générique si le purpose est inconnu.
- **`similar_hops` (T67/T68, Browse) : cosinus normalisé-par-axe pondéré
  spécificité + PÉNALITÉ DE COUVERTURE.** Un houblon moins mesuré ne doit jamais
  dépasser un houblon à couverture complète sur la même cible — bug réel trouvé
  en direct (Callista, BarthHaas seul avec 8/10 composés dilués mais alignés,
  dépassait Mosaic à couverture 10/10 par pur effet d'invariance d'échelle du
  cosinus). Corrigé par `_coverage_penalized_cosine` (facteur =
  `len(shared)/len(target_vec)`, asymétrique). Deux couches combinables
  (composition moléculaire + roue d'arôme quantitative), moyenne des couches
  ayant réellement une donnée pour le candidat (jamais 0 fabriqué pour une
  couche manquante).
- **Amplify GUI : descripteurs = couche principale, moléculaire = case optionnelle
  décochée par défaut (T76).** L'auto-trigger moléculaire "si couverture
  suffisante" a été explicitement écarté après étude empirique sur 44 ingrédients
  réellement courants en brassage : couverture molécule médiane 4,2 %, max 12,4 %
  — aucun seuil "suffisant" défendable ne laisserait la couche allumée pour un
  usage réel. `rank_mode` = `st.segmented_control` à 3 états (Descriptors / Both /
  Molecular only), remplace un empilement de cases à cocher dépendantes jugé peu
  ergonomique.
- **`hops.purpose` (aromatic/bittering/both, source BeerMaverick) jamais déduit
  par défaut** — `infer_purpose_from_alpha_acid` (seuil 7,0 % alpha acide, 78,2 %
  d'accord avec BeerMaverick sur 142 houblons) existe mais est explicitement
  préfixé "Inferred:" en GUI et JAMAIS utilisé pour structurer les blends (pour ne
  pas contaminer la garantie aromatic+bittering avec une estimation imparfaite).

## Réalité des données (état actuel, vérifié)

### BarthHaas — source primaire
HTML servi, parsable, inclut les thiols. `ingest.crawl_barthhaas`.
- **Bug de slug marque déposée** (®→"r", ™→"tm" collés sans séparateur, ex.
  "Citra®"→`citrar`) corrigé par `ingest._fix_barthhaas_trademark_slug` (ne
  déclenche que si le slug == normalize(h1) + suffixe exact — vérifié qu'aucun
  houblon finissant légitimement par "r" n'est touché).
- **Descripteurs qualitatifs + roue quantitative BarthHaas (T79)** :
  `<ul class="section-card-text__tastes">` (3-5 mots courts) et
  `data-rose-labels`/`data-values` (roue 0-8, 12 axes, HTML statique, pas de JS
  requis) — trouvés en réexaminant le HTML déjà fetché après un signalement
  utilisateur. Mapping 12 catégories BarthHaas → vocabulaire `hop_aroma_intensity`
  dans `data/mappings/barthhaas_aroma_wheel_categories.yaml` (+1 catégorie neuve,
  "menthol", sans équivalent Yakima). 49 mots qualitatifs hors vocabulaire
  existant triés avec l'utilisateur (15 retenus comme alias dans
  `data/mappings/barthhaas_descriptor_aliases.yaml`, le reste gardé distinct —
  ex. "apple blossom"/"camomile blossom" jamais fusionnés à leur terme de base,
  un qualificatif floral change la note).
  **`parsers.parse_descriptors` n'est PLUS appelé par `crawl_barthhaas`** (retiré
  après un faux descripteur "analyses" — artefact de barre d'onglets aplatie par
  `get_text`, pas un vrai mot d'arôme) ; la fonction reste utilisée par
  `build_from_fixtures` (fixtures contrôlées, pas de risque).
- **Roues de millésime** ("Aroma Profile 2023/2024", 20/97 houblons) délibérément
  PAS extraites — seule la roue "Typical" est parsée.
- **Yakima et BarthHaas ne sont JAMAIS moyennés** (méthodologies différentes,
  échelles différentes). Résolution par houblon (`matching.resolve_aroma_
  intensity`, défaut Yakima sauf dégénéré/absent → BarthHaas) pilote le SCORE
  (déterministe). L'AFFICHAGE (Browse, expanders, Compare) a un
  `st.segmented_control` Yakima↔BarthHaas explicite (`matching.select_aroma_
  intensity`, jamais de repli caché) + avertissement nommant les houblons absents
  de la source choisie (`_aroma_wheel_missing_warning`). Le vocabulaire d'axes
  affiché est restreint aux catégories que la/les source(s) résolue(s) peuvent
  réellement porter (`matching.aroma_wheel_vocabulary(sources=...)`) — sauf en
  comparaison multi-houblons où l'UNION des sources réellement utilisées est
  gardée (décision utilisateur explicite : ne jamais masquer une vraie mesure
  d'un houblon à cause de la limite de source d'un autre houblon affiché à côté).

### Yakima Chief — secondaire
Ajoute β-pinène, sélinène. Contournement anti-bot : API Algolia publique du site
(voir mémoire `yakima_chief_algolia_bypass`).
- Slugs `-brand` déprefixés pour fusionner avec BarthHaas, suffixe "Brand" retiré
  du nom affiché (`parsers._strip_yakima_brand_suffix` + fusion multi-source
  faisant gagner BarthHaas sur conflit de nom).
- Forme produit : `parsers._BREWING_VALUE_PRIORITY` préfère PEL02 (Type 90
  Pellets, forme standard brassicole), repli CON02/CON04 puis ARO01 — ARO01 était
  utilisé par défaut avant correction alors qu'il n'existe que sur 1/152 variétés
  et est corrompu (alpha 54-62 %, chimiquement impossible).
- Roue d'arôme quantitative Yakima : `aroma_values`/`sensory_values` (0-100
  réel), 15 catégories, écrite dans `hop_aroma_intensity` — jamais dans
  `hop_descriptors`.
- Alias `"pomme"→"apple"` (coquille FR du CMS Yakima, uid Contentstack unique et
  cohérent, pas un vrai mélange de locale).
- `hops.purpose`, `co_h` (co-humulone), `alpha_acid`/`beta_acid` : voir sections
  dédiées.

### FooDB — seule source de notes
Dump bulk figé 2020-04-07, licence NON COMMERCIALE. `ingest.download_foodb_dump`
télécharge automatiquement si absent.
- Lacunaire (14,4 % des liens compound↔aliment ont une concentration).
- **Piège colonne CAS** : `Compound.csv` a ses colonnes décalées, le vrai CAS est
  sous `description`, pas `cas_number` (qui contient des SMILES) —
  `ingest._resolve_cas_column` détecte par FORMAT, pas par nom déclaré.
- Synonymes résolus par CID PubChem en priorité (`ingest._canonical_compound`).
- Whitelist odeur-active Flavornet appliquée AVANT tri (sinon domination par du
  bruit nutritionnel).
- Poids : concentration mg/100g-équiv → sinon prior de seuil (FlavorDB2
  UNIQUEMENT, jamais `reference.MOLECULES`) → sinon présence pure.
- `ingest_foodb(all_foods=True)` parcourt tout `Food.csv` (~1000 aliments),
  filtre de distinctivité (écarte un aliment sans aucun composé à concentration
  mesurée — sinon FooDB retombe sur un gabarit générique partagé entre aliments
  sans rapport). ~510 notes distinctes. L'amorce littérature de 7 notes a été
  retirée (une seule source de vérité par note).

### Flavornet / FlavorDB2 / PubChem
- **Flavornet** : 738 composés odeur-actifs (GC-O) + descripteurs, whitelist
  `flavornet_compounds`.
- **FlavorDB2** : seuils par molécule, texte libre avec pièges (myrcène liste
  "10%" de composition, pas un seuil — `parsers.parse_flavordb2_threshold`
  n'accepte qu'un nombre + unité ppb/ppm/ppt reconnue). Résolu directement par
  CID PubChem. 227/734 seuils trouvés. Licence CC BY-NC-SA.
- **PubChem** : `resolve_pubchem_cids`, résout CAS→CID pour la whitelist
  Flavornet, repli sur nom (lettre grecque épelée, préfixe stéréochimique
  retiré). 6/734 CAS résiduels sans CID (vérifiés individuellement — pas un
  problème de terme de recherche, molécules probablement absentes de PubChem).
- **`--oav` (T75)** : `matching.oav_thresholds` résout CHAQUE seuil en direct via
  la chaîne CID→CAS→`flavordb2_thresholds` — `reference.MOLECULES[...][1]`
  (ancien seuil codé en dur) mis à `None` partout, jamais de repli sur un
  littéral. 5 des 14 molécules avaient un seuil codé en dur divergent du vrai
  seuil FlavorDB2 (géraniol : 4 ppb codé en dur vs 39,5 réel, facteur ~10).
  `matching.oav_coverage` + `OAV_LOW_COVERAGE_WARNING_THRESHOLD = 0.80` (dérivé
  empiriquement : médiane 100 %, moyenne 91 % sur les 258 notes à molécules
  productibles).

### BeerMaverick
Associations houblon↔houblon (pairings, substitutions) absentes de
BarthHaas/Yakima — agrégateur de recettes publiées, PAS une mesure de labo,
réserve affichée systématiquement en GUI. HTML statique, `robots.txt` ouvert.
`ingest.ingest_beermaverick`. Réconciliation par nom normalisé
(`ingest._resolve_hop_variety`), 143/203 variétés couvertes.
- **Descripteurs réels** (`hop_descriptors`, source='beermaverick') : tags
  `#pine #dank #cannabis...`, bien plus riches et sélectifs que les `aromas`
  éditoriaux courts de Yakima (ex. "dank" : 1/203 houblons chez Yakima seul vs 6
  après BeerMaverick). Vocabulaire `hop_descriptors` élargi 38→104→138 termes
  (104 après BeerMaverick, +34 nets après T79/BarthHaas).
- **`hops.purpose`** (Aroma/Bittering/Dual → aromatic/bittering/both) : seule
  BeerMaverick le renseigne, jamais déduit par défaut d'un proxy.
- `hop_similar` (Yakima, `similar_varieties`) est une TROISIÈME relation
  houblon↔houblon, distincte des deux BeerMaverick — les trois affichées
  séparément, jamais fusionnées.

### beer-analytics.com — statistiques de recettes (épique B, T85+)
Agrégateur de recettes homebrew publiées, PAS du BJCP ni une mesure de labo.
`ingest.ingest_beer_analytics` → `style_recipe_stats` (distributions ABV/IBU/
OG/FG/SRM par style, pré-binnées, outliers déjà retirés côté source — jamais
un percentile dérivable, GUI future : « observed distribution », jamais
« P5–P95 »). URLs de charts (`data-chart="…"` dans le HTML de page, JAMAIS
construites à la main — le segment de catégorie diverge du slug de page
affiché, ex. page `/styles/india-pale-ale/american-ipa/` mais charts sous
`/styles/ipa/american-ipa/charts/…`).
- **Cache disque `data/cache/beer_analytics/` réellement obligatoire, pas
  cosmétique** : lors du premier essai (2026-08-27) le site a ralenti
  brutalement (~13 req/min → ~0,1 req/min) après ~500 requêtes/1h30 même à
  notre rythme poli d'1 req/s — rate-limiting informel probable. Crawl arrêté
  délibérément plutôt que forcé (89/159 -- 159 était un COMPTAGE ERRONÉ,
  incluant les pages catégorie à un seul segment ; le vrai total est 123).
  Repris le lendemain sur demande explicite de l'utilisateur (« I want as
  much data as possible ») : rythme redevenu normal, **123/123 pages
  terminées proprement, zéro erreur** — le cache a évité de re-fetcher les
  89 déjà obtenues. État actuel : crawl complet, 6577 bins, 112/123 style_id
  résolus. Si un futur re-crawl (nouvelles données, pas juste une reprise)
  montre à nouveau un ralentissement soutenu, même précaution : arrêter
  plutôt que forcer, et considérer la prise de contact prévue (T89,
  `docs/OUTREACH_beer-analytics.md`) avant de retenter.
- **`style_id` (résolution BJCP) jamais fabriqué en ajoutant une ligne
  `beer_styles`.** beer-analytics a une granularité de style PARFOIS plus
  fine que BJCP (ex. 7 variantes de « Specialty IPA » — Black/White/Red IPA
  etc., chacune avec un volume réel de centaines à milliers de recettes) que
  BJCP ne couvre que par UN SEUL style_id générique (21B) sans vital stats
  propres à chaque variante. Ajouter « Black IPA » comme ligne `beer_styles`
  distincte inventerait un style_id/des vital stats BJCP qui n'existent pas
  officiellement — refusé (décision utilisateur, 2026-08-27). Ces variantes
  sont mappées à 21B dans `data/mappings/beer_style_aliases.yaml` (chacune
  garde sa propre ligne `style_recipe_stats` par `style_slug`, jamais fondue
  avec les autres) ; les rendre cherchables individuellement dans `browse`
  est le sujet de T130 (recherche par alias), pas de l'ingestion elle-même.
- **Onglets "Used for" (Any/Bittering/Aroma/Dry-Hop, T86) : de vraies
  requêtes `?filter=<valeur>` sur la même URL de chart, PAS un filtrage
  client** malgré `data-bs-toggle="tab"` (Bootstrap générique, ne suffit
  pas à trancher par le HTML seul) — confirmé par reverse engineering du
  bundle `/static/app.js` (`Chart.load({filter: i})` -> `getRequest(this.
  chartUrl, {filter: i}, ...)`) ET par fetch réel (payloads réellement
  différents). `style_hop_usage.usage_type` fait partie de la clé primaire
  pour cette raison (le `CREATE TABLE` du ticket T86 original n'avait nulle
  part où stocker cette ventilation, rédigé avant la vérification).
  `_beer_analytics_cache_filename` doit gérer les query strings (sanitisées
  en suffixe de nom de fichier, jamais tronquées -- sinon collision entre
  deux filtres du même chart, bug réel trouvé et corrigé).
- **Échecs réseau RÉCURRENTS pendant un crawl (T86/T87/T88, 2026-08-28/29) :
  cause probablement MIXTE, pas isolée avec certitude à une seule source.**
  Sur T86 : ~291 `NameResolutionError` groupés puis deux blocages
  silencieux (15-20 min, CPU quasi nul), passé à la 3e tentative. Sur T87 :
  3 tentatives bloquées net, passé à la 4e. Sur T88 (le pire des trois,
  ~10h étalées sur une nuit, une dizaine de cycles arrêt/reprise) : PENDANT
  un de ces incidents, un `curl` DIRECT vers beer-analytics.com a lui-même
  timeout 60s, alors qu'un `curl` simultané vers google.com répondait
  normalement en 0,2s -- ce point unique change la lecture : les incidents
  précédents (où `curl` restait rapide pendant le blocage Python) pointaient
  vers une cause locale, mais celui-ci pointe vers le serveur beer-
  analytics.com lui-même. **Conclusion révisée : combinaison probable de
  flakiness locale ET de ralentissements ponctuels réels côté serveur,
  jamais isolée avec certitude à une seule cause unique** -- ne plus
  affirmer "jamais un problème serveur" comme la version précédente de
  cette note le faisait. Réponse qui a marché à chaque fois, quelle que
  soit la cause exacte : tuer le process bloqué et relancer tel quel
  (cache-first, ne refetch que le manquant, jamais de perte de progression)
  -- si la reprise progresse lentement mais JAMAIS à zéro, la laisser tourner
  plutôt que de tuer prématurément (T88 a fini par passer à 92% en laissant
  tourner une reprise pendant plusieurs heures sans re-tuer). Si un futur
  crawl (T89+ ou un re-crawl) touche encore ce symptôme, même traitement :
  tuer + relancer si zéro progression, laisser tourner si lente mais non
  nulle, pas la peine de diagnostiquer plus loin avant d'essayer.

### Licence
Code MIT. FooDB/FlavorDB2 non commerciales. BeerMaverick sans licence de données
publiée — attribution systématique, lecture seule, esprit non-commercial.

## Fonctionnalités clés (état actuel)

- **Doublons de houblons audités** : 5 vrais doublons cross-source fusionnés
  (`ingest.merge_hop_varieties`) ; 4 crops réellement distincts par région
  (Amarillo, Perle, Saaz, Northern Brewer) désambiguïsés par affichage "Nom
  (Région)" dès collision (`matching._disambiguate_hop_names`, appliqué partout,
  pas seulement Browse).
- **Symboles ®/™/© retirés du nom affiché** (`parsers.strip_trademark_symbols`).
- **`by_descriptor`** : tri catégorique (recoupement `hop_descriptors`) PUIS
  quantitatif (intensité moyenne roue d'arôme). Pills roue = notation seule sauf
  repli si aucun descripteur texte choisi. `total_matches` exposé (troncature
  jamais silencieuse).
- **`contrast`** : cible d'affinité modifiable par l'utilisateur
  (`contrast_affinity_target`, pills pré-cochées/librement éditables) ; tri
  secondaire déterministe (score puis huile totale desc puis variété asc) ;
  filtre par `purpose`.
- **`compound_descriptors`** ("Smells like") : résolution CID→CAS→Flavornet,
  complétée par `reference.JANISH_COMPOUND_CATEGORIES` (Scott Janish, *The New
  IPA*, tableau "Compound Descriptions" p.22 — croisement manuel, jamais une
  supposition de CID) — comble notamment les thiols (aucune résolution Flavornet
  possible). Affiché dans tous les tableaux de composition (Browse, expanders,
  Compare Hops tooltip).
- **`process_survival`** : annotation qualitative de survie au procédé par classe
  de composé (`reference.PROCESS_SURVIVAL`, sourcé Janish pour la classification,
  prior qualitatif pour l'annotation/confidence — jamais de valeur numérique,
  vérifié programmatiquement). Colonne "Process" partout où "Smells like"
  apparaît. Légende `_process_survival_legend` en expander replié.
- **`descriptor_sources`** (T77) : provenance PAR DESCRIPTEUR séparée de la
  provenance de COMPOSITION — un houblon peut avoir sa composition sourcée
  BarthHaas mais ses descripteurs matchés sourcés BeerMaverick uniquement (bug
  de confusion réel signalé par l'utilisateur : "Sources: barthhaas" juxtaposé à
  des descripteurs 100 % BeerMaverick). Colonnes séparées "Descriptor sources" /
  "Composition sources" partout (Amplify, Contrast, blends, By-descriptor,
  Browse, expanders). Regroupé par source en GUI (`_descriptors_grouped_by_
  source`, une ligne en gras par source plutôt qu'une annotation par mot).
- **Compare Hops** : jusqu'à 5 houblons, radar roue d'arôme superposé + 2
  barplots (Principal info : alpha/beta/co-humulone/oil ; Detailed composition :
  composés d'huile, bascule absolu/relatif ml-100g↔%, menu **Normalization**
  None/Log/Min-max/Quantile calculée par composé sur toute la base). Tooltips
  "Smells like"/"Process" par composé (couche rect invisible sous les barres,
  pas de tooltip natif sur label d'axe Vega-Lite).
- **Déploiement Streamlit Community Cloud** : base construite en local, hébergée
  dans un dépôt GitHub privé séparé, téléchargée par l'app au démarrage si
  absente (`app._fetch_remote_db`, `@st.cache_resource`). **Reboot Streamlit
  Cloud requis après tout push de base** (le téléchargement ne se redéclenche
  que si le fichier local du conteneur est absent).

## Refonte esthétique GUI — système "Organic" (Claude Design)

Palette crème/terracotta/sauge, Caprasimo+Figtree (`.streamlit/config.toml`).
Contrainte respectée : jamais touché `matching`/`ingest`/`parsers`/`reference`/
`schema`/`cli`. GUI 100 % anglais (voir Conventions).

- **`light-dark()` CSS + propriété calculée `color-scheme` sur `.stApp`** : seul
  mécanisme qui suit le sélecteur Light/Dark/System de Streamlit de façon
  INSTANTANÉE sans rerun Python (Streamlit n'expose aucune variable CSS de
  thème ; `st.context.theme.type` est en retard d'1-2 reruns réels). Fond
  d'écran (`_BACKGROUND_STYLE_TEMPLATE`), logo (`.hf-logo-mark`/`.hf-logo-word`)
  et palette de graphiques en dépendent tous.
- **`st.container(border=True)`/`st.expander` n'ont pas de fond opaque natif**
  (vérifié par `getComputedStyle`) → `app._panel()`/`_panel_expander()` (clé
  `panel_{n}`, hook CSS `st-key-panel_*`) injecte le fond crème/sombre. UNE carte
  par section logique (jamais autour d'une ligne, jamais imbriquée).
  Ordre fixe du détail houblon : purpose → key stats → wheel → descriptors →
  composition → sources.
- **Tables via `column_config`** (`ProgressColumn`, `NumberColumn(percent)`,
  `ListColumn`) — `st.columns`-par-ligne abandonné car il s'empile
  verticalement sous une largeur d'écran donnée (cassait sur mobile).
- **Chips** : `st.badge`/directive Markdown `:color-badge[...]` — sage="fine",
  terracotta="read this", jamais de rouge. `purpose="both"` en gris neutre (le
  violet du thème était visuellement indissociable du sage). Préfixe
  `Inferred:` rendu en italique (substitut au "outlined" demandé, `st.badge`
  n'a pas de hook CSS par instance).
- **Palette de graphiques** (`_COMPARE_PALETTE`) : denim/terracotta/sauge/
  ochre/prune répartis sur le cercle chromatique (PAS des nuances de la même
  teinte — un 1er essai s'était effondré en nuances de rouille). Couleur
  assignée par position TRIÉE de la sélection (stable). Heatmap en rampe SAUGE
  mono-teinte (jamais terracotta, réservé à "interaction"/cliquable).
- **Radar d'arôme** : remplissage via `mark_line(interpolate="linear-closed",
  filled=True)` — **`mark_area` ne fonctionne PAS pour un polygone fermé sur
  x/y arbitraires** (remplit vers le bord du graphique le plus proche, pas
  entre points consécutifs ; piège Vega-Lite, pas un bug de code). Légende
  Compare : `color` PARTAGÉ par les 3 couches (fill/line/points) — un canal
  `fill` séparé du canal `color` sur le même champ fait FUSIONNER les légendes
  avec un conflit `disable` qui désactive tout (`WARN Conflicting legend
  property`, invisible sans vérifier la console). 500×500px, traits/points fins
  (`strokeWidth` 1.5, `size` 30/55) — historique de 4 tailles essayées (480→
  340→400→500), ne pas re-proposer une autre valeur sans nouveau retour
  explicite. Légende horizontale en bas (2 colonnes, `symbolOpacity=1` sinon
  hérite l'opacité du fill). Abréviation région dans la légende SEULEMENT
  (`_abbreviate_region_suffix`, table fermée sur 13 régions réelles) — jamais
  dans le tooltip/tableaux.
- **Barplot "Detailed composition" en échelle log** : `mark_bar` est
  structurellement incompatible avec une échelle log en Vega-Lite (`x2`
  implicite = littéral `0`, `log(0)` indéfini, casse la géométrie quel que soit
  le domaine déclaré — limitation Vega-Lite réelle, confirmée par reproduction
  isolée hors Streamlit). Corrigé par `x2=alt.X2Datum(domain_min)` (domaine
  min réel × 0.9 comme constante littérale, pas une référence de champ).
- **Normalisation** (`app._compare`, menu à 4 options) : None (brut, défaut),
  Log (ci-dessus), Min-max/Quantile calculées PAR COMPOSÉ sur `comp` ENTIER
  (toute la base, pas juste la sélection) — domaine [0,1] figé (sinon "0 =
  minimum de la base" devient faux si la sélection ne couvre pas les extrêmes),
  valeur brute conservée à côté pour le tooltip (sinon deux composés
  d'amplitudes très différentes affichent la même position normalisée sans
  contexte). Ordre des composés trié sur la valeur BRUTE toujours (pas la
  valeur normalisée) — sinon l'ordre change à chaque changement de menu.
- **`theme="streamlit"` (Altair) respecte les couleurs EXPLICITES** d'un
  `alt.Scale(domain=..., range=[...])` — seules les couleurs implicites/par
  défaut sont écrasées. Donc aucun `_chart_theme()` séparé n'a été nécessaire ;
  gridlines/police/fond suivent déjà le thème Organic nativement.
- **`st.secrets.get(clé)` LÈVE** (pas de `secrets.toml`) au lieu de renvoyer
  `None` comme un dict standard — capturé largement dans `_fetch_remote_db`.
- **Logo** : lockup "1d Stacked" (marque au-dessus du mot-symbole), construit
  en HTML/CSS `mask-image` (PAS `st.image`, un masque CSS ne peut pas
  s'appliquer à un widget image natif) à partir de `assets/mini_logo_square.png`
  recoloré terracotta par thème. `st.logo` écarté (plafond de taille intégré à
  32px). Favicon = variant "1b" (disque sage + marque crème, ~84 % du canevas,
  généré une fois par script ponctuel PIL) — la marque nue perd sa silhouette
  sous ~24px.

## Règles procédé & « survivables » (mémoire durable pour le modèle prédictif)

Base de connaissance pour le futur modèle « quel houblon à quel moment du
procédé » (backlog T99-T101, épique E). **Ces règles sont un PRIOR SOURCÉ, pas
une mesure** : elles viennent d'une publication industrielle citable, elles sont
appliquées à NOS mesures, et elles doivent être étiquetées comme telles en GUI
(même traitement que le préfixe `Inferred:` de `infer_purpose_from_alpha_acid`).

### Les 8 composés « survivables » Yakima Chief

Composés bière-solubles qui traversent le côté chaud et la fermentation active
(analyse GC-QTOF + GC-SCD). Noms de champs EXACTS de l'API YCH Tools
(`/api/lot`, voir plus bas) — à réutiliser tels quels si on ingère un jour :

| Champ API | Composé | Classe | Odeur (source : handbook YCH 2022) |
|---|---|---|---|
| `isobutylIsobutyrate` | isobutyl isobutyrate | ester | fruité |
| `twoMethylbutylIsobutyrate` | 2-méthylbutyl isobutyrate (« 2MIB ») | ester | pomme verte, abricot |
| `isoamylIsobutyrate` | isoamyl isobutyrate | ester | fruité |
| `methylGeranate` | méthyl géranate | ester terpénique | — |
| `twoNonanone` | 2-nonanone | cétone | fruité, floral, herbacé |
| `linalool` | linalol | alcool monoterpénique | fruité/floral (« Froot Loops »), booster de fruité |
| `geraniol` | géraniol | alcool monoterpénique | géranium, agrume |
| `threeMercaptohexanol` | 3-mercaptohexanol (3MH) | thiol | pamplemousse, groseille à maquereau |

Historique de version du modèle (à ne pas confondre) : **7 composés** dans le
webinar 2020 (« Sulfur: The Next Aroma Frontier »), le marqueur 2019 « butanoic
acid, 3-methylbutyl ester » ayant été retiré ; **8 composés** dans la version
moderne (ajout de l'isobutyl isobutyrate).

### Les 4 règles d'usage (handbook YCH 2022, texte, citable)

1. **Hauts survivables → utilisables TÔT.** Late kettle, whirlpool, dry hop en
   fermentation active (AFDH). Exemple donné : Ekuanot® > Palisade® pour un
   whirlpool à fort impact.
2. **Bas survivables → réserver au TARDIF.** Dry hop post-fermentation (PFDH).
   Exemple donné : Willamette.
3. **Blender pour ÉQUILIBRER les concentrations, pas pour les empiler.**
   Exemple donné : Loral® (linalol) + Talus® (géraniol) = dynamique ;
   Loral® + Crystal (tous deux linalol) = plat, unidimensionnel.
4. **Charger le moût tôt en survivables favorise la BIOTRANSFORMATION.**
   Fortes concentrations d'alcools monoterpéniques + thiols en whirlpool/AFDH
   = conditions du métabolisme levurien des composés houblon.

Précisions du même document, utiles au modèle :
- Le géraniol est partiellement biotransformé en **β-citronellol** par certaines
  levures (amplifie le profil agrume/floral). Le β-citronellol n'est **pas**
  dans le houblon, il apparaît en bière.
- Le nérol (isomère du géraniol) n'est **pas détectable** par l'analyse YCH.
- Une addition **late kettle** perd beaucoup de volatils, mais les composés
  solubles dans le moût (**alcools monoterpéniques, 3MH**) passent au fermenteur.
- Ordre de grandeur des seuils : myrcène ~20 ppb vs **4MMP ~0,05 ppb**
  (deux ordres de grandeur d'écart — les soufrés pèsent malgré des
  concentrations minuscules).
- L'**isomérisation** des acides alpha se produit au-dessus de 79 °C / 175 °F,
  **whirlpool compris** (pas seulement à l'ébullition).

⚠ **Ne PAS recréer le bug de `--biotransform`** (retiré le 2026-08-12) : la
règle 4 et la conversion géraniol→citronellol sont un phénomène PROCÉDÉ, à
n'appliquer qu'au moment du procédé. La version retirée comptait deux fois la
même mesure (les 29 notes demandant du citronellol demandaient toutes aussi du
géraniol). Toute réutilisation ici doit rester au niveau « stade de procédé »,
jamais rentrer dans le scoring note→molécule.

### Côté chaud vs côté froid (SOURCÉ — `docs/mapping_compounds.txt`)

Distinction que le modèle procédé doit porter. Sourcée depuis
`mapping_compounds.txt` (fourni par l'utilisateur, relu et corrigé le
2026-08-27) — Janish *The New IPA*, JAFC, ASBC, OSU Hop Lab (Shellhammer),
Takoi et al. :

- **Le côté chaud CRÉE de l'arôme** : oxydation des sesquiterpènes
  (humulène, caryophyllène) en époxydes/humulénol/oxyde de caryophyllène →
  caractère noble, épicé, boisé. Ces produits ne sont **pas mesurés dans le
  houblon** (ils se forment dans la chaudière) : un houblon riche en humulène/
  caryophyllène est donc un *précurseur* de côté chaud, jamais une mesure
  directe de ce qu'on obtiendra.
- **Le côté froid PRÉSERVE** : thiols, esters, monoterpènes très volatils
  (myrcène) sont perdus à l'ébullition → dry hop.
- **Cas mixte** : linalol et géraniol survivent au whirlpool (règle 1) ET
  bénéficient de l'AFDH (règle 4). Ils ne sont donc PAS « côté froid seulement »,
  contrairement à l'intuition. C'est le point qui rend le modèle non trivial.

`reference.PROCESS_SURVIVAL` (annotation qualitative par classe de composé,
classification sourcée Janish) est la structure existante à étendre — jamais une
valeur numérique inventée, cf. la vérification programmatique déjà en place.

⚠ **Homonymie « 2-MIB », piège corrigé le 2026-08-27.** Le sigle désigne DEUX
molécules sans rapport : le **2-méthylbutyl isobutyrate** (ESTER, pomme verte/
abricot, l'un des 8 survivables Yakima, champ `twoMethylbutylIsobutyrate`) et le
**2-méthylisobornéol** (alcool terpénique, terreux/moisi type géosmine, seuil
5-10 ng/L, **faux-goût venant de l'EAU** — cyanobactéries — pas du houblon).
L'un est à maximiser, l'autre à éviter. `mapping_compounds.txt` les confondait ;
l'entrée a été scindée et annotée.

⚠ **Ce que les agrégats BarthHaas contiennent** (même source) :
`isobutyrate` = isobutyl isobutyrate + isoamyl isobutyrate + 2-méthylbutyl
isobutyrate ; `ketones` = 2-nonanone + 2-undécanone notamment ;
`thiols` = 3MH/3SH + 4MMP + 3MHA. Donc `isobutyrate` recouvre **3 des 8**
survivables Yakima et `ketones` **1** — ne jamais relire ces champs comme des
molécules uniques.

### API de lot Yakima Chief — explorée et TRANCHÉE (2026-08-27)

Les valeurs de survivables par variété n'existent publiquement que sous forme
d'IMAGE (poster/handbook YCH, `© all rights reserved`) — d'où les
reconstructions au pixel du hop-finder russe et de thirdleapbrew. **Mais** YCH
Tools expose une API JSON publique donnant les mesures OFFICIELLES du labo :

```
GET https://tools.yakimachief.com/api/lot?lotNumber[]=<LOT>[&lotNumber[]=<LOT2>]
```

**Exploré et vérifié en direct** sur 3 lots réels (`23-WA346-027`,
`P92-IUCIT3082`, `PC1-IUCIT1079`, trouvés via une URL de partage
`tools.yakimachief.com/lookup?lots[]=…` indexée par les moteurs de recherche) :

- **La réponse contient le nom de variété** (`variety`, `varietyCode`,
  `cultivar`) — donc **aucun mapping lot↔houblon n'est à construire**, chaque
  lot s'auto-étiquette. Plus `cropYear`, `productName`/`productCode`
  (CON02 balle / PEL02 T90 / PEL06 Cryo), `farms[].grownBy`.
- `brewingValues` : `uvAlpha`, `uvBeta`, `hsi`, `hplcAlpha/Beta/Cohumulone/
  Colupulone`, `moisture`, `lcvAlpha75`.
- `oilComponents` : mêmes % d'huile que ce qu'on a déjà.
- **`survivables` : 22 champs**, bien au-delà des 8 du modèle publié —
  les 8 (`isobutylIsobutyrate`, `twoMethylbutylIsobutyrate`,
  `isoamylIsobutyrate`, `methylGeranate`, `twoNonanone`, `linalool`,
  `geraniol`, `threeMercaptohexanol`) **plus** `alphaPinene`, `betaPinene`,
  `myrcene`, `limonene`, `methylHexanoate`, `methylHeptanoate`,
  `methylOctanoate`, `methylNonanoate`, `methylDecanoate`, `geranylAcetate`,
  `transCaryophyllene`, `humulene`, **`caryophylleneOxide`**,
  `transBetaFarnesene` (plusieurs souvent `null`).

⚠ **Unité NON déclarée par l'API.** Les ordres de grandeur suggèrent des ppm
(myrcène ~9 263 sur un T90 à 2,6 % d'huile ≈ cohérent avec des mg/kg), mais
alors le 3MH à 0,7-1,5 serait ~700-1500 µg/kg, **20 à 50× au-dessus** de
l'agrégat `thiols` BarthHaas (0-34 µg/kg). Hypothèse plausible non vérifiée :
YCH mesurerait le 3MH **total, précurseurs liés compris** (conjugués cystéine/
glutathion), bien plus abondants que le thiol libre. À élucider avant toute
ingestion — ne jamais poser ces valeurs à côté des nôtres sans l'avoir tranché.

⚠ **Ce sont des mesures PAR LOT, pas par variété** : sur les 3 lots Citra 2023
ci-dessus, le Cryo (PEL06) affiche ~2× les survivables du T90 (PEL02) — normal
(concentré de lupuline), mais cela interdit de traiter un lot comme
représentatif d'une variété.

**Décision (utilisateur, 2026-08-27) : source ABANDONNÉE comme socle
systématique.** Les numéros de lot ne sont pas énumérables (pas d'index, et
énumérer par force brute serait un scan de leur API — exclu). 3 lots trouvés,
tous Citra 2023 : impossible d'en faire un jeu de données. L'onglet Survivables
tourne donc sur l'**indice dérivé de nos propres mesures** (linalol, géraniol,
isobutyrate, thiols — déjà en base). Le client de lot reste un ticket
opportuniste au cas où de vrais numéros deviendraient disponibles.

⇒ **Aucune valeur lue sur un graphique n'entre nulle part.** Si un jour des
chiffres entrent, c'est par cette API, avec de vrais numéros de lot, dans une
table séparée (`hop_lot_analysis`) qui n'est PAS une mesure de variété.

## Conventions
- Commentaires/docstrings en français (cohérent avec l'existant).
- **Exception : le texte UTILISATEUR de la GUI (`app.py`) est en ANGLAIS**
  (labels, captions, warnings, badges). `cli.py` (sorties `print`) et tous les
  commentaires/docstrings, y compris dans `app.py`, restent en français.
- Retours à la ligne dans `st.caption`/`help=`/tooltips : un `\n` seul est
  ignoré par le rendu Markdown Streamlit — utiliser `"  \n"` (deux espaces avant
  le saut) pour un vrai saut de ligne visuel.
- Ne jamais fabriquer de données houblon en dur : passer par un parseur + source
  tracée.
- `pytest` doit rester vert. Ajouter un test quand on touche un solveur ou un
  parseur.
- Commandes : `pip install -e ".[dev]"` ; `pytest -q` ; `hopmatch build` (démo, 4
  houblons, 0 note) puis `hopmatch ingest-flavornet` puis `hopmatch ingest-foodb`
  (télécharge le dump si besoin) avant `hopmatch amplify|contrast <note>` ;
  `hopmatch by-descriptor <descripteurs>` fonctionne dès `build`.
- **`app._RECENT_UPDATES`** (liste "Recent updates" en bas de la page d'accueil,
  liste STATIQUE curée à la main — jamais de lecture `git log` en direct côté
  GUI, messages de commit en français incompatibles avec le texte GUI anglais,
  et `.git` n'est pas garanti présent sur Streamlit Cloud) **doit être mise à
  jour dans le MÊME COMMIT que tout changement GUI visible** par l'utilisateur
  final (nouvel outil, nouvelle section, comportement perceptible — pas les
  changements internes purs : refactor, tests, CLI seul).

## Reste (backlog)
1. Jointure FooDB/hop_composition au-delà des ~734 composés Flavornet si le
   vocabulaire s'élargit beaucoup.
2. Roues de millésime BarthHaas (2023/2024, 20/97 houblons) jamais extraites —
   pourrait affiner une comparaison temporelle si un besoin réel se présente.
3. `INGREDIENT_DESCRIPTORS` pas encore revue contre le vocabulaire élargi par
   T79 (+34 termes nets) — mentionné par l'utilisateur, pas encore repris.
