# CLAUDE.md — contexte projet hopmatch

Ce fichier donne à Claude Code le contexte et les décisions issues de la conception
de hopmatch. Lis-le avant d'agir. (Détails : `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md`.)

## But
Outil brasseur : **note olfactive → molécules → houblons**. Accorder un houblon à un
ajout (yuzu, basilic…). Modes `amplify` (prolonger) et `contrast` (contraster).
L'ajout est dans la bière, donc le houblon n'a pas à le reproduire : le « plafond de
couverture » ne pénalise pas.

**`combine()` (NNLS, reproduire un goût sans ajout par combinaison de houblons)
implémenté puis RETIRÉ (décision utilisateur, 2026-08-12).** Mesuré sur les 506 notes
réelles de la base : 0 % ne dépassaient 20 % de couverture (max observé 12 %, médiane
1,3 %) — la chimie de l'huile de houblon ne recoupe simplement pas la plupart des
arômes alimentaires. Pire : sur les notes à un seul composé « producible » (la
majorité), NNLS dégénère en un système à une seule équation où n'importe quel houblon
porteur atteint un résidu artificiel de 0 — une fausse confiance sans rapport avec la
couverture réelle (ex. observé en direct : "strawberry" et "passion fruit" retournaient
tous deux "100% Talus, résidu 0.0", simplement parce que le géraniol était le SEUL
composé commun aux deux notes sur toute la base). Pas un bug de méthode (l'amélioration
T10 du backlog — garder le meilleur de deux heuristiques de sous-ensemble — restait
correcte) : un problème de fond, aucun algorithme ne change le recoupement chimique
réel. Ne pas réintroduire sans un changement de fond côté données (une source qui
couvre bien plus de composés aromatiques par aliment).

**Le même problème de fond touche aussi `amplify()` (avertissement ajouté, PAS
retiré — décision utilisateur, 2026-08).** Signalé en direct par l'utilisateur en
testant "strawberry" : la couche moléculaire seule, sans descripteurs, se dégrade
exactement comme `combine()` — 163/506 notes réelles n'ont QUE le géraniol comme
molécule productible, et le score se réduit alors à `amount(ce houblon, géraniol) /
amount(houblon le plus riche en géraniol de toute la base)` : un simple tri par
quantité brute d'UNE molécule, sans rapport avec la note en question. Mesuré : sans
descripteurs, Talus® Brand (le houblon avec le plus de géraniol, 0.036) et Ekuanot®
Brand (0.0315) raflent #1 sur 44 % des 258 notes ayant un classement moléculaire non
vide (166+55/506). Contrairement à `combine()`, PAS retiré : la couche descripteurs
(`matching.descriptor_overlap`, indépendante de la concentration moléculaire) corrige
concrètement le classement quand l'utilisateur en fournit — vérifié sur "strawberry" +
["fruity","berry"] : Talus tombe de #1 à #6. La couverture ne dépassant jamais 12 % sur
toute la base (voir ci-dessus), un avertissement (`matching.LOW_COVERAGE_WARNING_THRESHOLD
= 0.20`) s'affiche désormais en CLI (`ATTENTION`) et GUI (`st.warning`) dès que
`coverage < 20%`, encourageant explicitement l'ajout de descripteurs — voir
`cli._print_amplify`/`app._amplify`. Ce seuil flagge la quasi-totalité des notes
réelles : reflet honnête des données, pas un seuil mal choisi.

**`contrast_blend` refondu + `amplify_blend` ajouté (T33 backlog, décision utilisateur,
2026-08) — priorité à la fréquence RÉELLE d'usage, pas à la couverture pure.**
L'utilisateur a jugé l'ancien `contrast_blend` (couverture ensembliste gloutonne pure,
un seul blend "optimal") peu utile — rien ne garantissait que les houblons combinés
soient réellement utilisés ensemble en pratique. Nouvelle méthodologie explicitement
demandée : proposer PLUSIEURS tailles de blend (1 à 5, pas un seul "meilleur"),
et à chaque taille >1, choisir le houblon par fréquence RÉELLE de pairing
BeerMaverick (`hop_pairings`) avec un houblon déjà dans le blend — la couverture
reste calculée/rapportée mais ne pilote plus le choix en priorité. Repli EXPLICITE
sur la couverture gloutonne classique (`via="coverage"`) quand aucune fréquence
réelle n'existe depuis le blend courant (36/203 houblons seulement ont une donnée
`hop_pairings`, mesuré) — jamais un blend plus petit que possible juste par manque
de données, mais toujours la provenance signalée (`via`: "top"|"pairing"|"coverage").
Mécanisme partagé (`matching._pairing_grown_blends`) entre `contrast_blend` (cible =
`CONTRAST_AFFINITY`, inchangé) et le nouveau `amplify_blend` (cible = descripteurs
propres de la note, **PAS de reconstruction moléculaire/NNLS** — ce serait recréer
`combine()`, déjà retiré pour la dégénérescence documentée ci-dessus ; le score
moléculaire d'`amplify` sert seulement à classer les candidats, jamais à piloter la
composition du blend). Vérifié en direct sur données réelles : sur une cible large
(les 10 catégories cœur), le mécanisme choisit Amarillo (meilleur candidat) puis
Simcoe/Citra/Mosaic/Chinook, les 4 par pairing réel BeerMaverick — 4 additions sur 5
via une fréquence de recette vérifiée, pas une heuristique de couverture.

**`_pairing_grown_blends` ne s'arrête plus à la couverture complète (2026-08-18, décision
utilisateur — revirement de méthodologie explicite).** Signalé par l'utilisateur : en
`contrast`, le blend proposé restait bloqué à taille 1. Investigation en direct : ce
n'était PAS un bug mais le comportement voulu du T33 (`if not (target - covered): break`)
qui devenait très fréquent une fois le vocabulaire de descripteurs élargi à 104 termes
(voir BeerMaverick ci-dessus) — un seul houblon populaire couvre souvent à lui seul les
2-3 descripteurs cibles de `CONTRAST_AFFINITY`, donc plus aucune taille >1 n'était
générée. L'utilisateur a tranché : voir un blend à 5 houblons reste une info utile même
quand 1 seul houblon couvre déjà toute la cible (piste éventuelle de substitution/
diversité), donc le early-exit est retiré — le mécanisme grossit maintenant TOUJOURS
jusqu'à `max_hops` (ou épuisement du pool de candidats). Nouveau statut `via="relevance"`
(distinct de `"coverage"`) quand aucun gain de couverture n'est plus possible ET qu'aucun
pairing BeerMaverick ne s'applique depuis le blend courant : ajoute alors le houblon
suivant par pertinence de classement pur, explicitement étiqueté "rien de neuf à
couvrir" en CLI/GUI pour ne jamais laisser croire à une couverture supplémentaire
inexistante — honnêteté d'abord, même principe que les molécules orphelines.

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
- **Option `--biotransform` implémentée puis RETIRÉE (2026-08-12, décision
  utilisateur).** La science sourcée restait solide (géraniol→citronellol,
  linalol→alpha-terpinéol, preuve indépendante convergente ale/lager — King &
  Dickinson 2003, corroboré par Michel et al. 2019) mais l'intégration avait un
  vrai bug : `hop_compound(m, biotransform=True)` redirigeait la molécule
  demandée vers son précurseur SANS vérifier si ce précurseur était déjà,
  séparément, une entrée du même profil de note. Sur les 29 notes réelles
  demandant du citronellol, LES 29 demandent aussi du géraniol : la même mesure
  de géraniol comptait donc deux fois dans le score. Voir `reference.py` pour
  le détail complet. Ne pas réintroduire sans corriger le double comptage à la
  racine.

## Réalité des données (vérifiée)
- **BarthHaas** : source houblon primaire. HTML servi, parsable, inclut les THIOLS.
  Crawler implémenté (`ingest.crawl_barthhaas`).
  **Bug de slug marque déposée corrigé (2026-08-18, signalé par l'utilisateur : "Citrar"/
  "Mosaicr" en `browse`).** Root cause vérifiée en direct (crawl complet des 97 pages
  BarthHaas, comparaison slug brut vs vrai `<h1>` via `ingest._normalize_hop_key`) : le
  générateur de slug de BarthHaas translittère ® en un simple "r" et ™ en "tm", collé
  SANS séparateur au mot précédent ("Citra®" → `citrar`, "Azacca™" → `azaccatm`) — un
  défaut du site source, pas un bug de parsing hopmatch au sens classique, mais hopmatch
  utilisait ce slug comme clé d'identité et le prenait donc pour une vraie variété.
  9 houblons touchés (+ `amarillor-vgxp01-cv`, cas étendu avec code cultivar SKU en plus
  de la marque). Corrigé chirurgicalement par `ingest._fix_barthhaas_trademark_slug(slug,
  h1_title)` : ne déclenche QUE si le slug est exactement `normalize(h1) + "r"/"tm"` (ou
  ce préfixe + un tiret) — vérifié sur les vrais houblons finissant légitimement par "r"
  (Saazer, Glacier, Endeavour, Challenger, Cluster, Pioneer...) qu'aucun n'est touché,
  conformément à l'exigence explicite de l'utilisateur de ne PAS tronquer bêtement un "r"
  final. Conséquence : ces 10 houblons fusionnent désormais correctement avec leur entrée
  Yakima (`barthhaas,yakima` au lieu de deux lignes séparées, chacune privée d'une partie
  des données — Yakima manque les thiols, BarthHaas manque β-pinène/sélinène) ; 203 → 193
  houblons en base après réingestion réelle. BeerMaverick non affecté (vérifié : même
  décompte de pairings/substitutions/descripteurs avant/après, car il résout déjà par les
  clés Yakima propres qui existaient indépendamment).
- **Yakima Chief** : secondaire. Ajoute β-pinène, sélinène. Vrai rempart anti-bot devant
  le HTML (Vercel Security Checkpoint) — `requests` seul ne passe jamais (vérifié, même
  avec UA de navigateur). Contournement : leur front s'appuie sur Algolia avec une clé
  API PUBLIQUE en lecture seule exposée côté client (design normal pour ce type de clé) —
  interrogée en HTTP simple, sans navigateur. Une requête ramène les ~152 variétés en
  JSON déjà structuré (composition + roue d'arôme), pas de parsing HTML. Piège nommage :
  slugs `-brand` (`citra-brand`) à déprefixer pour fusionner avec BarthHaas (`citra`),
  SAUF collision avec un vrai doublon de SKU déjà existant (`perle`/`perle-per03`).
  **Choix de forme produit corrigé (vérifié en direct, signalé par l'utilisateur)** :
  `parse_yakima_hit` préférait `brewing_values[code=ARO01]` ('HopAroma', supposée
  « l'analyse brute de la variété »). Faux sur le catalogue réel : ARO01 n'existe que
  sur 1/152 variétés (`admiral`) et CETTE entrée est corrompue côté YCH lui-même —
  alpha 54-62% (chimiquement impossible, >25% inconnu commercialement), oil 5-9 ml/100g,
  contre alpha 13-16% / oil 1-1,7 pour ses 3 entrées produit (CON02/CON04/PEL02,
  mutuellement cohérentes), confirmé par BarthHaas indépendamment. Sans ARO01 sur les
  151 autres variétés, le code retombait sur `brewing[0]` = **CON02 (Leaf Hops, Baled)
  dans 145/152 cas** — pas la forme utilisée en brasserie. `parsers._BREWING_VALUE_PRIORITY`
  préfère maintenant explicitement PEL02 (Type 90 Pellets, présent sur 148/152, LA forme
  standard en brasserie — demandé par l'utilisateur), repli CON02/CON04 puis ARO01,
  filtré par `_is_plausible_brewing_entry` (alpha ≤30%) à chaque niveau. Exclut par défaut
  les produits dérivés (PEL06 Cryo Hops, PEL07 Noble Hops, EXT01 extrait CO2, ARO17/19/24/25
  Boost/huile d'essai — composition fondamentalement différente, alpha jusqu'à 64%, huile
  jusqu'à 99%+) sauf si c'est vraiment tout ce qui existe pour une variété. Réingestion
  réelle : 18/152 variétés changent de valeurs (CON02→PEL02 différaient réellement, pas
  juste une histoire de source `admiral`).
  **Roue d'arôme QUANTITATIVE (T26 backlog)** : la même réponse Algolia contient aussi
  `imported_fields.aroma_values` (niveau variété) et `imported_fields.sensory_values` (par
  forme produit, mêmes codes que `brewing_values`), chacun `{aroma, aroma_intensity}` —
  intensité RÉELLE 0-100, jamais parsée jusqu'ici (découvert en creusant un retour
  utilisateur : une première roue basée sur `hop_descriptors`/`aromas`, binaire
  présence/absence, jugée à raison non informative — `aromas` ne garde qu'un
  sous-ensemble des arômes les plus forts sans valeur, ex. Mosaic : 4 termes dans
  `aromas` contre 15 dans `aroma_values`). `parse_yakima_hit` choisit l'entrée
  `sensory_values` de LA MÊME forme produit que la composition retenue, repli sur
  `aroma_values` (variété) sinon. Écrit dans `hop_aroma_intensity` (table dédiée, jamais
  dans `hop_descriptors`). 94/151 variétés Yakima couvertes, vocabulaire fixe à 15
  catégories, 12-15/15 par houblon couvert. Cas dégénéré géré : `admiral` a une entrée
  présente mais entièrement à 0 (cohérent avec sa corruption déjà documentée plus haut) —
  `app._browse` vérifie `any(valeur > 0)`, pas juste la présence du dict. GUI `browse` :
  rendu en radar/spider chart (polygone sur 15 axes fixes, coordonnées calculées en
  Python), PAS un camembert à rayon variable — une première version en `mark_arc`
  (theta+radius Vega-Lite) ne balayait qu'un demi-cercle par défaut, bug non résolu,
  abandonné pour l'approche polygone. Voir `docs/DATA_SOURCES.md` pour le détail complet.
  `ingest.crawl_yakima` IMPLÉMENTÉ. Fragile (clé/index Algolia non documentés).
- **FooDB** : source note→molécule. Dump bulk, figé 2020-04-07, licence NON COMMERCIALE.
  `ingest.download_foodb_dump` télécharge+extrait automatiquement le tar.gz
  (`foodb.ca/public/system/downloads/...`, 200 sans authentification, vérifié) si absent
  localement — plus besoin de le récupérer à la main ; idempotent (skip si déjà présent).
  `ingest.ingest_foodb` IMPLÉMENTÉ, l'appelle si `foodb_csv_dir` omis. Vérifié sur le dump réel :
  - lacunaire : 14,4 % des liens compound↔aliment ont une concentration (mesuré sur
    l'ENSEMBLE du dump via `tools/audit_foodb.py`, pas un échantillon) ; un aliment
    liste ~6000+ composés (longue traîne de bruit).
  - **piège dataset** : `Compound.csv` a ses colonnes décalées à partir de `moldb_iupac` —
    `cas_number` contient des SMILES, le vrai CAS est sous `description` (0 % de forme
    CAS plausible dans `cas_number` vs 21,6 % dans `description`, sur 70 477 lignes).
    `ingest._resolve_cas_column` détecte la bonne colonne par FORMAT, pas par nom déclaré.
    Une fois ce bug contourné, l'estragole (marqueur du basilic) EST bien présent dans
    FooDB — l'absence constatée initialement était un artefact de ce bug, pas un vrai trou.
  - synonymes entre sources (estragole/methyl-chavicol même CAS 140-67-0 ;
    β-caryophyllène/caryophyllène) → sans normalisation : double comptage note-side et
    FAUSSE ORPHELINE côté houblon. Résolu par `ingest._canonical_compound`, PRIORITÉ au
    CID PubChem (`pubchem_cids`, identité chimique vérifiée : 140-67-0 → CID 8815,
    identique à methyl-chavicol), repli sur `reference.ALIASES` (réduit aux agrégations
    sans CID propre comme "thiols") puis dépréfixage grec si le CID n'est pas résolu.
  - le tri par concentration est dominé par du bruit NUTRITIONNEL (eau, cendres, minéraux) :
    FooDB mêle nutrition et arôme → FILTRER via whitelist odeur-active (Flavornet) AVANT.
  - seules unités « masse comparable » retenues comme concentration fiable (mg/100g,
    mg/kg) : `standard_content` prétend normaliser mais recopie IU/ppb/µM tels quels
    (vérifié) — les traiter comme des mg serait de la précision-déchet.
  Poids : concentration (mg/100g-équivalent) → sinon prior de seuil (1/seuil, depuis
  `flavordb2_thresholds` UNIQUEMENT — JAMAIS `molecules`/`reference.MOLECULES`, décision
  explicite pour ne jamais mélanger un seuil sourcé et un seuil deviné) → sinon présence
  pure. 3 paliers disjoints, jamais mélangés entre eux.
  **Seule source de notes du pipeline** : `ingest_foodb` (`all_foods=True` par défaut)
  parcourt TOUT `Food.csv` (~1000 aliments sur le dump 2020-04-07) et crée une note par
  aliment (nom en minuscule) — pipeline non supervisé, rien dans le filtrage/pondération
  n'est spécifique à une note en particulier. Une amorce littérature de 7 notes
  (yuzu, kumquat, basilic, rose, fruit-passion, mangue, pin-resine, dans
  `reference.AROMA_NOTES`/`NOTE_DESCRIPTORS`/`NOTE_TO_FOODB`) a existé pendant le
  développement puis a été **retirée à la demande explicite de l'utilisateur** une fois ce
  pipeline suffisant — une seule source de vérité par note plutôt que deux qui se
  recouvrent. Conséquence assumée : yuzu/rose/pin-resine n'ont pas d'équivalent FooDB
  (yuzu absent, rose = faux ami "Rose hip", pin-resine n'est pas un aliment) et ont donc
  disparu du pipeline — aucune ne reviendra tant qu'aucune source réelle ne les couvre.
  `notes` (paramètre optionnel, additif, vide par défaut) reste disponible pour qui veut
  quand même donner un nom choisi à un aliment — `food_entries` est une LISTE de
  (food_id, note, is_curated), pas un dict par food_id : un aliment peut porter plusieurs
  noms sans que l'un écrase l'autre (bug corrigé en le construisant : "mangue" curée
  écrasait silencieusement "mango" auto-dérivée).
  **Filtre de distinctivité** (n'épargne que les entrées de `notes`, si fournies) : un
  aliment est écarté s'il n'a AUCUN composé à concentration mesurée — vérifié sur le dump
  réel que deux aliments sans rapport (capers/chervil) partagent 99,2% de leurs composés
  listés (5961/6011) : sans concentration, FooDB cite un gabarit générique, pas une
  composition mesurée pour cet aliment précis, et retombe sur la table de seuils GLOBALE
  (poids identiques entre aliments sans lien). 345/847 candidats avec ≥1 composé
  whitelisté écartés sur le dump réel (992 aliments au total, 141 sans aucun composé
  whitelisté, ~510 notes distinctes conservées).
  **Descripteurs auto-dérivés testés et rejetés, DEUX FOIS, pour deux raisons
  différentes** : (1) agréger les descripteurs Flavornet des molécules d'une note (même
  pondérés par IDF, même restreints aux composés distinctifs post-filtre) reproduit la
  même dégénérescence sur la note MÉDIANE — converge vers les mêmes mots génériques entre
  notes sans rapport, ou devient vide dès qu'on restreint aux seuls composés à
  concentration réelle (peu de notes en ont beaucoup). (2) Reproduit vérifié même sur les
  notes les PLUS riches en composés concentration (rosemary 38, carrot 45, red wine 49...) :
  toutes convergent quand même vers citrus/spicy/floral (carrot et wild carrot obtiennent
  un score "citrus" identique à 2 décimales près). Cause identifiée : des composés
  génériques RÉELS et correctement mesurés (aldéhydes à chaîne moyenne — heptanal,
  nonanal, octanal...) apparaissent comme composés concentration dans énormément
  d'aliments chimiquement sans rapport, et portent "citrus" comme descripteur Flavornet ;
  aucun filtre sur la RICHESSE des données ne peut compenser ça, le problème n'est plus
  la rareté du signal mais l'ubiquité chimique réelle de certains composés triviaux qui
  noient la signature propre à l'aliment. Définitivement PAS viable, ne pas retenter sans
  changer de vocabulaire source (pas Flavornet) ; voir `matching.contrast`.
  `note_descriptors` est donc VIDE par défaut pour toute note — `amplify`
  fonctionne en molécules-seules pour toutes les notes désormais (plus de traitement
  spécial pour un sous-ensemble curé). **`contrast` généralisé par sélection manuelle** :
  `matching.contrast(con, descriptors=[...])` laisse l'utilisateur décrire sa note à la
  main (vocabulaire réel `hop_descriptors`, comme `by_descriptor`) au lieu d'exiger
  `note_descriptors` — fonctionne pour N'IMPORTE QUELLE note sans rien inventer côté
  données ; `contrast(note=...)` reste disponible mais lève `ValueError` tant que
  `note_descriptors` n'est pas peuplé pour cette note (jamais par défaut désormais).
  `matching.contrast_blend` propose en plus une combinaison parcimonieuse (couverture
  ensembliste gloutonne sur `hop_descriptors`, PAS de NNLS — contrast reste
  non-moléculaire) avec résidu rapporté.
  Voir `tools/{audit_foodb,foodb_impact_check}.py`.
- **Flavornet** : 738 composés odeur-actifs (GC-O) + descripteurs, 734 CAS uniques
  (page HTML statique unique `d_kovats_ov101.html`, pas de pagination). Sert de whitelist
  « sensoriellement présent » (table `flavornet_compounds`, distincte de `molecules`).
  `ingest.ingest_flavornet` IMPLÉMENTÉ.
- **FlavorDB2** : seuils par molécule. Pas d'API/dump bulk pour les seuils ; fiche détail AJAX
  (`/molecules_details?id=<pubchem_cid>`) — accessible DIRECTEMENT par CID une fois résolu via
  `pubchem_cids` (repli sur recherche par nom sinon), champ seuil en TEXTE LIBRE avec de vrais
  pièges (le myrcène y liste "10%" de composition, PAS un seuil —
  `parsers.parse_flavordb2_threshold` n'accepte qu'un nombre accolé à une unité reconnue
  ppb/ppm/ppt). 25 595 molécules au total, mais `ingest.ingest_flavordb2` IMPLÉMENTÉ se
  borne aux ~734 de la whitelist Flavornet (pas tout crawler : hors sujet + lourd pour leur
  serveur). Run réel (avec CID déjà résolus, repli par nom inclus) : 227/734 seuils trouvés
  (727 accès directs par CID, 6 sans correspondance — contre 86 trouvés / 488 sans
  correspondance avant le CID). Écrit dans `flavordb2_thresholds` (jamais dans `molecules`).
  Licence CC BY-NC-SA (non commercial).
- **PubChem (PUG-REST)** : `ingest.resolve_pubchem_cids` IMPLÉMENTÉ, `/compound/name/{cas}/cids/JSON`
  (accepte un CAS comme synonyme), écrit `pubchem_cids(cas, cid)`, borné à la whitelist
  Flavornet. Repli sur le nom du composé quand le CAS seul échoue
  (`parsers.pubchem_name_fallbacks` : lettre grecque épelée, préfixe stéréochimique retiré —
  Flavornet ne donne ni InChIKey ni SMILES, rien d'autre à essayer ; pas de recherche floue
  au-delà). C'est le "liant" structural qui remplace la table d'alias manuelle et la recherche
  par nom exact — voir `_canonical_compound` et `ingest_flavordb2` ci-dessus. Domaine public,
  limite 5 req/s. RÉSIDU ACCEPTÉ : 6/734 CAS restent sans CID (aussi testé via
  `xref/RegistryID`, pas juste `name` — sans succès). Vérifié individuellement que ce n'est PAS
  un problème de terme de recherche à corriger : `methylethylpyrazine` désigne plusieurs
  isomères réels distincts (aucun moyen de savoir lequel), `dehydrocarveol` (synonyme
  `p-menthatrien-2-ol` confirmé ailleurs) ne répond sur aucune variante essayée — probablement
  absent de PubChem. Coder un CID à la main ici serait une supposition non vérifiable, pas une
  donnée comme `reference.ALIASES`. Ne pas retenter sans nouvelle piste.
- **BeerMaverick** (T25 backlog) : associations houblon<->houblon, absentes de BarthHaas/
  Yakima. « Hop Pairings » (fréquence relative d'association dans des recettes publiées,
  analysées par eux) et « Hop Substitutions » (choix éditorial de brasseurs expérimentés).
  **Réexaminé et RETENU (2026-08, décision utilisateur)** — une investigation précédente
  avait écarté BeerMaverick à cause de leur endpoint interne `/api/js/?hop=<id>`,
  explicitement documenté "internal use" (voir `docs/BACKLOG.md` pour l'historique complet
  de cette réserve). Revérifié en direct : LA MÊME donnée (pairings ET substitutions) est
  en fait déjà dans le HTML statique servi normalement par chaque page
  `beermaverick.com/hop/{slug}/` — exactement comme BarthHaas, aucun besoin de cet endpoint
  interne. `robots.txt` : `Disallow:` vide (vérifié), sitemap public (`beerm-sitemap.xml`,
  318 pages houblon). AGRÉGATEUR (analyse de recettes publiées), PAS une mesure de labo
  indépendante comme BarthHaas/Yakima — GUI affiche systématiquement cette réserve avec la
  donnée, jamais mélangé aux couches de score (`matching`). Réconciliation par nom normalisé
  (`ingest._resolve_hop_variety`, tolère ®/™/"Brand"/"NZ Hops"...) : 143/203 de nos variétés
  ont une page BeerMaverick correspondante (mesuré sur le sitemap complet) ; les pages sans
  équivalent local sont simplement ignorées, aucun houblon fabriqué. `ingest.ingest_beermaverick`
  IMPLÉMENTÉ. Écrit `hop_pairings`/`hop_substitutions` (tables dédiées).
  **Écrit aussi de vrais descripteurs dans `hop_descriptors` (source='beermaverick'), découvert
  en creusant un retour utilisateur** : `contrast(descriptors=["tropical"])` ciblait "dank"
  (via `CONTRAST_AFFINITY`) mais quasiment AUCUN houblon ne le couvrait — vérifié en direct sur
  l'API Algolia : Yakima ne tague "Dank" QUE sur 1/203 houblons (CTZ) dans toute la base, alors
  même que Chinook/Columbus (classiquement "dank" chez les brasseurs) n'ont pas ce tag chez
  Yakima. Cause : `imported_fields.aromas` (Yakima) est une liste COURTE éditoriale, pas
  exhaustive (déjà documenté pour T26). BeerMaverick expose un bloc `<b>Tags:</b> #pine #dank
  #cannabis...` par page, un vocabulaire RÉEL bien plus riche (131 tags distincts sur 142 pages
  crawlées) et correctement sélectif — Chinook/Columbus taggés "dank", Mosaic/Simcoe non
  (cohérent avec l'usage brassicole réel, vérifié en direct). Run réel : vocabulaire
  `hop_descriptors` passé de 38 à **104 descripteurs distincts**, "dank" désormais sur 6
  houblons (CTZ, Amarillo, Chinook, Columbus, Galaxy, Summit) au lieu d'1 seul ; `contrast`
  sur "tropical" renvoie maintenant Chinook à 100% (dank+resinous+spicy) au lieu d'aucun
  houblon crédible. Filtrage (`ingest._BEERMAVERICK_TAG_DROPLIST`, ~25 tags de qualité
  générique non-olfactifs comme "mild"/"clean"/"hoppy") puis normalisation
  (`ingest._normalize_beermaverick_tag`) : vrais renommages du même concept vers
  `reference.DESCRIPTOR_ALIASES` (ex. "resin"→"resinous", "cannabis"→"dank" — quasi-synonyme
  en terminologie houblon) ; sous-familles réelles (raspberry, jasmine, curry...) gardées comme
  entrées DISTINCTES dans `reference.CONTRAST_AFFINITY` (même valeur-cible que leur catégorie
  cœur), jamais écrasées vers un terme générique — même principe que "grapefruit"/"lemon" déjà
  présents. Les 104 descripteurs réels sont TOUS couverts par `CONTRAST_AFFINITY` (vérifié,
  zéro non-mappé).
  **En complément, côté Yakima** : `imported_fields.similar_varieties` (curé par YCH
  lui-même, référencé par uid Contentstack, résolu directement dans `crawl_yakima` contre le
  lot complet) donne une TROISIÈME relation — similarité/substitut selon Yakima, distincte des
  deux relations BeerMaverick. Écrit `hop_similar`. Les trois tables/sources sont affichées
  séparément en GUI (`app._hop_associations`), jamais fusionnées : ce sont trois questions
  différentes ("quoi de similaire ?" x2 sources vs "quoi d'utilisé ensemble ?").
- **Licence** : le CODE est MIT ; FooDB et FlavorDB2 sont NON COMMERCIALES. BeerMaverick n'a
  pas de licence de données explicite publiée — contenu affiché avec attribution de source
  systématique (GUI), en lecture seule, esprit non-commercial comme le reste du projet. Un
  usage commercial imposerait de retirer/renégocier ces sources.

## Caveat validation
`schema.validate_and_repair` corrige l'inversion myrcène/caryophyllène des datasets
scrappés sales. Sur BarthHaas/Yakima (propres) elle ne se déclenche pas — c'est un
filet de sécurité, pas une valeur active.

## Prochaines tâches (ordre d'utilité)
Fait : `ingest.ingest_flavornet`, `ingest.ingest_foodb` (généralisé à `all_foods=True` par défaut
+ filtre de distinctivité + `download_foodb_dump` automatique — seule source de notes du
pipeline, amorce littérature retirée), `by-descriptor`, `ingest.crawl_yakima`,
`ingest.ingest_flavordb2`, `ingest.resolve_pubchem_cids` (jointure structurale CAS->CID + repli
sur le nom, voir `docs/FEATURE_NOTES.md` pour le détail de spec de by-descriptor), GUI Streamlit
(`src/hopmatch/app.py`), `contrast`/`contrast_blend` généralisés par sélection manuelle de
descripteurs (`matching.contrast(descriptors=[...])`, sans dépendre de `note_descriptors`),
GUI : mode `browse` (T5), heatmap de comparaison des descripteurs en `by-descriptor` (T4),
roue d'arôme quantitative par houblon en `browse` (T26, radar/spider chart — voir la
section Yakima Chief ci-dessus), libellés de mode conviviaux (T24, `app.MODE_LABELS`,
purement cosmétique côté GUI, les clés internes/CLI ne changent pas), associations
houblon<->houblon en `browse` (T25 : `hop_similar` Yakima + `hop_pairings`/
`hop_substitutions` BeerMaverick, réexaminé et retenu — voir la section BeerMaverick
ci-dessus). `ingest.ingest_beermaverick` IMPLÉMENTÉ.
`combine()` (NNLS) implémenté, amélioré (T10), puis RETIRÉ (2026-08-12) — voir la section
« But » en haut de ce fichier pour le détail de la décision. Option `--biotransform`
implémentée puis RETIRÉE le même jour (bug de double comptage, voir la section
« Décisions de conception » ci-dessus). `--oav` réexaminé (T23) : conservé, effet réel
mesuré (~1 note sur 6 change de classement), documentation CLI/GUI enrichie plutôt que
retiré. Vocabulaire de descripteurs élargi de 38 à 104 termes via les tags BeerMaverick
(voir la section BeerMaverick ci-dessus — corrige la couverture "dank" quasi inexistante
côté Yakima seul). `contrast_blend` refondu + `amplify_blend` ajouté (T33, priorité à la
fréquence réelle de pairing BeerMaverick plutôt qu'à la couverture pure, plusieurs
tailles de blend 1-5 proposées — voir la section dédiée ci-dessus).
Batch GUI/data du 2026-08-18 (9 changements demandés par l'utilisateur) : libellés
"HopFinder from Descriptors"/"Browse hop informations" ; `--oav` actif par défaut en GUI ;
curseur "Nombre de résultats" déplacé dans la page Amplify (repli sidebar conservé pour
Contrast) ; curseur de taille de blend retiré, toujours 5 (`amplify_blend`/
`contrast_blend` appelés avec `max_hops=5` fixe) ; bouton "ouvrir dans Browse" sur chaque
ligne de résultat (`amplify`, `contrast`, `by-descriptor` — relais `session_state`
`_next_mode`/`_next_browse_hop` consommé en tête de `main()`) ; correction du bug de slug
marque déposée BarthHaas (voir la section BarthHaas ci-dessus, fusion Citra/Mosaic/etc.
avec Yakima) ; roue d'arôme agrandie (rayon 130→170) et adaptative au thème clair/sombre
(`st.context.theme.type`, seule info de thème exposée par Streamlit — palette choisie à la
main, pas de lecture de couleur exacte possible) ; `_pairing_grown_blends` ne s'arrête
plus à la couverture complète (voir section dédiée ci-dessus, corrige le blend `contrast`
bloqué à taille 1).
Reste :
1. Jointure FooDB/hop_composition au-delà des ~734 composés Flavornet si le vocabulaire
   s'élargit beaucoup (crawl Yakima déjà réel, plus d'aliments FooDB).
2. `parsers.parse_descriptors` (BarthHaas) renvoie désormais `[]` pour la plupart des variétés :
   le site réel a remplacé sa liste courte de descripteurs par un paragraphe descriptif (vérifié
   en direct sur plusieurs variétés, ex. 'admiral', 'tango' — voir le commentaire de la fonction).
   Piste non explorée : les pages exposent une roue d'arôme en `<canvas>` avec des valeurs
   numériques par axe (`data-values="3,6,4,..."`) — les libellés d'axes ne sont pas dans le HTML
   statique (rendu JS), pas retrouvés. Si retrouvés, remplacerait avantageusement l'ancien format
   texte par des poids QUANTITATIFS par descripteur. Yakima (`imported_fields.aromas`) reste la
   source fiable de `hop_descriptors` en attendant.

## Conventions
- Commentaires/docstrings en français (cohérent avec l'existant).
- Ne jamais fabriquer de données houblon en dur : passer par un parseur + source tracée.
- `pytest` doit rester vert. Ajouter un test quand on touche un solveur ou un parseur.
- Commandes : `pip install -e ".[dev]"` ; `pytest -q` ; `hopmatch build` (démo, 4 houblons,
  0 note — `build` ne seed plus de note, seul `ingest-foodb` en crée) puis `hopmatch
  ingest-flavornet` puis `hopmatch ingest-foodb` (télécharge le dump si besoin) avant de
  pouvoir utiliser `hopmatch amplify|contrast <note>` ; `hopmatch by-descriptor
  <descripteurs>` ne dépend d'aucune note et fonctionne dès `build`.
