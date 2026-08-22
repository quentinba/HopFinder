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

**Houblon de base choisi par l'utilisateur + mélange pertinence/pairing au lieu d'une
cascade top→pairing→couverture (2026-08-19, décision utilisateur — second revirement).**
Signalé après le premier passage T33/ci-dessus : (1) le score de `contrast` est souvent
homogène (plusieurs houblons ex-aequo "meilleur candidat" — ex. citra/mosaic/simcoe tous
à 20.0 sur une cible "citrus,floral" typique), donc imposer `candidates[0]` comme houblon
de taille 1 masque un choix arbitraire parmi des ex-aequo ; (2) le mécanisme de pairing
tel qu'implémenté en T33 se comportait en CASCADE (essayer le pairing partout jusqu'à
épuisement, puis retomber sur la couverture) plutôt qu'un vrai MÉLANGE des deux signaux
comme demandé à l'origine. Deux changements dans `matching._pairing_grown_blends` :
(1) nouveau paramètre `base_variety` — taille 1 devient le choix EXPLICITE de
l'utilisateur (`via="chosen"`) plutôt que `candidates[0]` par défaut (repli sur
`candidates[0]`/`via="top"` si omis, ex. usage CLI/programmatique) ; exposé en GUI juste
au-dessus de la section blend (`app._select_base_hop`) pour amplify ET contrast. (2)
Le choix des additions suivantes (taille k>1) ne prend plus « la fréquence de pairing la
plus haute, n'importe où dans le pool » mais filtre d'abord les candidats restants
(`pool`, déjà trié par PERTINENCE) à ceux présents dans le TOP `_PAIRING_TOP_N` (10 par
défaut, pas n'importe quelle fréquence positive) des partenaires BeerMaverick d'au moins
un houblon déjà dans le blend (`matching._top_pairing_partners`), puis prend le PLUS
PERTINENT de ce sous-ensemble filtré — jamais celui de plus haute fréquence brute.
Vérifié par test (`test_contrast_blend_mixes_relevance_and_pairing_not_pure_frequency`) :
un candidat de fréquence 99 mais moins pertinent perd contre un candidat de fréquence 10
mais plus pertinent, dès lors que les deux sont dans le top-10 pairing du houblon de
base — exactement le mélange demandé, pas une cascade. Repli inchangé (couverture puis
pertinence) si aucun candidat restant n'est dans le top-N pairing d'un houblon du blend.

**Bouton de navigation directe vers Browse retiré, remplacé par des expanders de détail
sur place (2026-08-19, décision utilisateur).** Le bouton "ouvrir dans Browse" par ligne
de résultat (T39, ajouté 2026-08-18) faisait perdre la page amplify/contrast en cours
(résultats + blend) sans moyen d'y revenir, signalé en direct par l'utilisateur. Retiré
entièrement (`app._browse_button`/`_render_hop_table` supprimés, tableaux de résultats
revenus à `st.dataframe` simple) et remplacé par `app._hop_detail_expanders` : un
expander par houblon SOUS le tableau de résultats (descripteurs complets, composition,
sources), rendu directement dans la page courante — même esprit que la liste
d'expanders déjà présente sous la heatmap de `by-descriptor` (suggéré explicitement par
l'utilisateur en exemple). Le relais `_next_browse_hop`/`browse_hop` (session_state) est
retiré de `main()` ; `_next_mode` seul reste (utilisé par la page d'accueil, sans rapport
avec ce bouton).

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
  **Suffixe "Brand" retiré du nom affiché (2026-08-19, signalé par l'utilisateur : "Mosaic
  Brand" au lieu de "Mosaic" en GUI).** Root cause à deux niveaux, vérifiée en direct :
  (1) `imported_fields.display_name` côté Yakima porte littéralement le mot "Brand" pour
  50/153 variétés (ex. "Mosaic® Brand"), un artefact de LEUR convention d'affichage
  marketing (variétés déposées) — BarthHaas n'a jamais ce mot pour la même variété
  (vérifié en direct sur leur `<h1>` réel : "Mosaic®", rien d'autre). Corrigé par
  `parsers._strip_yakima_brand_suffix`, appliqué dans `parse_yakima_hit` : retire
  uniquement le mot "Brand"/"(Brand)" (3 formes vues en direct : "X® Brand", "X™
  (Brand)" — un seul cas, Galaxy —, et "X® Brand - NZ Hops"/"X™ Brand - MacHops"), en
  gardant tout le reste intact (®/™, qualificatifs réels comme "- NZ Hops"/"Organic").
  (2) Même après ce correctif, `_ingest_variety` n'écrivait `name` QU'à la création de la
  ligne, jamais lors d'une fusion multi-sources (`UPDATE hops SET sources=?` seul) — un
  houblon ingéré par Yakima PUIS BarthHaas gardait pour toujours le nom (avec "Brand") du
  premier crawl, même une fois BarthHaas fusionné avec son nom plus propre. Corrigé :
  BarthHaas (source primaire) l'emporte désormais toujours sur conflit de nom ; une
  réingestion de la MÊME source (aucune autre n'a jamais touché la variété) peut aussi
  rafraîchir le nom. Réingestion réelle (`crawl-barthhaas` + `crawl-yakima`) : 43 → 0
  houblons avec "Brand" dans le nom affiché sur les 194 de la base.
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
  **Axe "Pomme" corrigé en "apple" (2026-08-19, signalé par l'utilisateur : français et
  anglais mélangés dans la roue d'arôme).** Investigué en direct sur l'API Algolia réelle
  (153 variétés) : PAS un mélange de locale côté hopmatch — la requête filtre déjà
  strictement `publish_details.locale:"en-us"`, une seule locale. Les 14 autres axes sur
  15 sont bien en anglais ; seul "Pomme" (français) est mal étiqueté DANS le CMS Yakima
  lui-même, sous la MÊME locale en-us, avec le MÊME uid Contentstack
  (`cs95db0a8ac5cfd199`) réutilisé identiquement sur les ~281 variétés qui l'ont — une
  coquille de saisie unique et cohérente côté source, pas un champ traduit au hasard, donc
  pas d'« version anglaise du site » alternative à cibler. Corrigé par un alias ciblé
  (`reference.DESCRIPTOR_ALIASES["pomme"] = "apple"`), déjà appliqué par
  `ingest._ingest_variety` à l'écriture de `hop_aroma_intensity` (mécanisme existant,
  réutilisé sans changement de code d'ingestion). 94 lignes `descriptor='pomme'` stales
  supprimées puis `crawl-yakima` relancé : roue d'arôme entièrement anglaise en base
  (vérifié : `SELECT DISTINCT descriptor FROM hop_aroma_intensity` ne renvoie plus que les
  15 termes anglais attendus).
  **"Herbal"/"Vegetal" enquêtés puis NON fusionnés (2026-08-19, hypothèse utilisateur
  invalidée par la donnée réelle).** Signalé comme doublon apparent dans le radar Compare
  Hops, avec l'hypothèse que "herbal" viendrait de Yakima et "vegetal" de BarthHaas.
  Vérifié en direct : FAUX — `hop_aroma_intensity` est intégralement Yakima
  (`ingest._ingest_variety(..., aroma_intensity=...)` n'est appelé qu'avec ce paramètre
  depuis `crawl_yakima`, jamais depuis `crawl_barthhaas`), les deux termes sont donc déjà
  dans la MÊME source. Pas un doublon pour autant : les valeurs mesurées divergent
  nettement par houblon (ex. celeia herbal=83/vegetal=0 ; cluster-fugget
  herbal=15/vegetal=42 ; cashmere herbal=30/vegetal=34) — deux axes sensoriels
  légitimement distincts dans le vocabulaire Yakima (herbal = menthe/thé/foin ; vegetal =
  oignon/ail/légume cuit, souvent un signal de défaut en brassage), pas une variante de
  langue comme "Pomme"/"apple" ci-dessus. Fusionner aurait perdu un signal réel et mesuré
  indépendamment. Utilisateur confirmé après présentation des chiffres : conservés
  séparés, aucun changement de code.
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

  **`hops.purpose` (aromatic/bittering/both) ajouté (2026-08-19, décision utilisateur —
  "the concept of aromatic vs bittering hops").** Cherché explicitement sur BarthHaas ET
  Yakima : AUCUN des deux n'expose de classement houblon par usage (vérifié en direct sur
  leurs pages/API respectives — BarthHaas n'a que "Aroma & Flavor" comme catégorie de
  PRODUIT DÉRIVÉ, pas d'usage de la variété brute ; Yakima n'a rien d'équivalent dans
  `imported_fields`). BeerMaverick, en revanche, affiche une ligne « Purpose: Aroma /
  Bittering / Dual » dans le même tableau HTML statique "Analyses" déjà exploité pour
  pairings/substitutions/tags — vérifié sur 9 houblons connus (Citra=Dual, Warrior/Magnum/
  Apollo/Bravo/Millennium/Summit=Bittering, Saaz-cz/Hallertau Mittelfrüh/Amarillo=Aroma),
  cohérent avec l'usage brassicole réel. `parsers.parse_beermaverick_purpose` extrait le
  texte brut ; `ingest._normalize_beermaverick_purpose` mappe vers notre vocabulaire à 3
  catégories (`"Aroma"→"aromatic"`, `"Bittering"→"bittering"`, `"Dual"→"both"` — nom choisi
  côté hopmatch, pas une retranscription). Écrit dans `hops.purpose` (nouvelle colonne,
  NULL par défaut — seule BeerMaverick le renseigne, jamais déduit d'un proxy comme l'alpha
  acide, ce serait fabriquer une donnée). Run réel sur les 143 variétés couvertes par
  BeerMaverick : 52 aromatic, 20 bittering, 70 both, 52 sans donnée (hors couverture
  BeerMaverick). Affiché en GUI comme info PRINCIPALE en `browse` (juste sous le nom du
  houblon, demande utilisateur explicite) et en colonne dans les résultats amplify/contrast
  (`app._purpose_badge`, couleurs `st.badge` — tokens sémantiques Streamlit, PAS des hex
  littéraux, seul moyen vérifié de s'adapter aux deux thèmes clair/sombre à la fois).

  **Blends structurés par purpose (`matching._pairing_grown_blends`, paramètre
  `purpose_by_variety`)** : demande utilisateur explicite — "propose blends with at least 1
  aromatic and 1 bittering as a first proposal (n=2) and then propose blends picking only
  aromatic hops that pairs well with the other aromatic hop (not the bittering)". Taille 1
  = houblon de base (choisi par l'utilisateur, voir T44) ; si son rôle est connu et
  unilatéral (aromatic OU bittering, jamais "both"), taille 2 cherche explicitement un
  houblon du rôle OPPOSÉ parmi les candidats (`via="complement"`) — un houblon "both" à la
  taille 1 satisfait déjà les deux rôles, pas de complément forcé. À partir de là (rôle
  établi des deux côtés), la croissance se restreint aux houblons AROMATIQUES uniquement
  (`purpose in {"aromatic","both"}`), et le pairing BeerMaverick ne regarde que les
  partenaires des houblons AROMATIQUES du blend — jamais l'amérisant, conformément à la
  demande. S'arrête dès qu'il n'y a plus de candidat aromatique disponible, même avant
  `max_hops`. Repli SILENCIEUX sur la croissance générique (T33/T42/T44, inchangée) dès que
  le rôle du houblon de base est inconnu (variété non couverte par BeerMaverick) ou qu'aucun
  candidat du rôle complémentaire n'existe — jamais d'erreur, jamais un blend plus petit que
  possible par manque de donnée `purpose`. Vérifié en direct sur données réelles
  (`contrast-blend --descriptors citrus,floral`) : Celeia (aromatic, meilleur candidat) puis
  Millennium (bittering, complément) à la taille 2, puis Perle/Falconer's Flight 7Cs/
  Vanguard (aromatic ou both) aux tailles 3-5 — jamais un second houblon purement
  amérisant.
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
Batch de suivi du 2026-08-19 (retour utilisateur sur 3 points du batch précédent) :
**roue d'arôme réellement lisible en thème sombre** — le premier passage (palette
`st.context.theme.type`) restait illisible en vrai, signalé par l'utilisateur ; cause
réelle trouvée : `st.altair_chart` applique par défaut `theme="streamlit"`, qui réécrit
la config Vega-Lite globale et écrase les couleurs de mark explicites choisies à la main
— `theme=None` (voir `app._browse`) laisse Vega-Lite utiliser les couleurs qu'on lui
donne, pas celles de Streamlit ; **houblon de base + mélange pertinence/pairing** au lieu
d'une cascade top→pairing→couverture (voir section dédiée ci-dessus) ; **bouton
Browse retiré**, remplacé par des expanders de détail sur place (voir section dédiée
ci-dessus).
Batch du 2026-08-19 (3 nouveaux points) : **GUI traduite en anglais** (scope confirmé par
l'utilisateur : `app.py` uniquement — texte utilisateur, labels/captions/warnings/badges ;
CLI (`cli.py`) et commentaires/docstrings restent en français, cf. Conventions ci-dessous) ;
**roue d'arôme incluse dans le détail par houblon** (`app._hop_detail_expanders`, même
contenu que `browse` — badge purpose, sources, descripteurs, roue, composition — plutôt
qu'une simple liste de composés, demande utilisateur "same content than what is on the
browse page") ; **`hops.purpose` (aromatic/bittering/both)** ajouté depuis BeerMaverick,
affiché en info principale `browse` + colonne colorée `st.badge` en résultats amplify/
contrast, et blends structurés pour garantir au moins 1 aromatique + 1 amérisant à la
taille 2 puis ne recruter que des aromatiques ensuite (voir la section BeerMaverick
ci-dessus pour le détail complet des trois). En cours de ce même batch, corrigé aussi le
seul axe non-anglais de la roue d'arôme ("Pomme"→"apple", voir section Yakima Chief).

**Image de fond ajoutée (2026-08-19, demande utilisateur, `assets/background.png`, fournie
par l'utilisateur — gravure houblon).** Fichier hors sandbox (`~/Downloads`) au départ,
copié manuellement par l'utilisateur (Finder, pas Terminal — `cp`/`sudo cp` échouaient
avec `Operation not permitted`, restriction TCC macOS sur Downloads, pas un problème
hopmatch). PNG fourni (~3,1 Mo, texture papier + hachures fines qui compresse mal en PNG)
reconverti en JPEG qualité 82 à l'ingestion GUI (`app._background_data_uri`, ~360 Ko) et
inliné en base64 (`data:image/jpeg;base64,...`) via CSS injecté par `st.markdown(...,
unsafe_allow_html=True)` — pas de serveur de fichiers statiques Streamlit à configurer.
Voile semi-transparent COULEUR DU THÈME par-dessus, cible `[data-testid=
"stAppViewContainer"]`, pas la sidebar.
**Premier correctif tenté le même jour (retour utilisateur immédiat) — INSUFFISANT,
voir le second correctif ci-dessous pour la vraie root cause :** négatif couleur via
`st.context.theme.type` pour le thème sombre ; retrait de `background-attachment:
fixed` + `background-position: right top` pour le défilement. L'utilisateur a signalé
que NI L'UN NI L'AUTRE n'était réellement corrigé (le thème clair montrait encore le
négatif, la position ne changeait toujours pas en défilant) — root cause réinvestiguée
en direct sur le DOM/CSS réel plutôt que supposée :
- **Thème** : le sélecteur Streamlit (menu "⋮") est un état 100% CÔTÉ CLIENT (aucun
  attribut/style lié au thème sur `<html>`/`<body>`, vérifié) qui ne déclenche PAS de
  rerun Python immédiat — `st.context.theme.type`, lu en tout début de `main()`, reste
  bloqué sur l'ancienne valeur tant qu'aucune VRAIE interaction widget n'a eu lieu
  (confirmé : deux reruns réels après avoir choisi "Light" ne suffisaient pas, il en a
  fallu un troisième). `st.context.theme.type` abandonné pour ce composant précis : les
  deux variantes (normale + négatif) sont désormais TOUTES LES DEUX embarquées dans le
  CSS, sélectionnées par `@media (prefers-color-scheme: dark)` — évalué par le
  navigateur, instantané, sans aller-retour Python. Limite assumée et documentée : ne
  suit que la préférence OS ("System", le réglage par défaut), pas un override manuel
  Light/Dark qui contredirait l'OS (cas minoritaire, toujours corrigé après une vraie
  interaction — même limite qu'avant, mais confinée à ce cas).
- **Position** : `[data-testid="stAppViewContainer"]` N'EST PAS l'élément qui défile
  réellement — Streamlit a une mise en page à défilement imbriqué, c'est
  `[data-testid="stMain"]` qui a `overflow-y: auto` et un `scrollHeight` >
  `clientHeight` (vérifié via `getComputedStyle`/`scrollHeight` en direct sur le DOM
  réel). `stAppViewContainer` fait toujours exactement la hauteur du viewport, donc
  `background-size: cover` dessus ne voyait jamais plus qu'un viewport de l'image,
  `fixed` ou pas — le retrait de `fixed` au premier correctif n'avait donc aucun effet
  puisque la cible elle-même ne grandissait jamais. Corrigé en ciblant `stMain` avec
  `background-attachment: local` (pas le défaut `scroll`, qui fixe le fond par rapport
  à la BOÎTE de l'élément, pas à son contenu défilant) : `local` fait défiler le fond
  avec le contenu réel de `stMain`, sur toute sa hauteur défilable.
  `background-position: right top` conservé.
Vérifié en direct dans les deux thèmes, y compris en défilant longuement (composition
de l'illustration visiblement différente entre le haut et le bas de page).

**Second correctif, toujours le même jour — le thème restait cassé aussi ("changing
theme doesn't change the image used") : la médiaquery `prefers-color-scheme` du premier
correctif suit la préférence OS, PAS le sélecteur Light/Dark/System du menu Streamlit —
aucune des deux méthodes tentées jusque-là (`st.context.theme.type`, `prefers-color-
scheme`) ne suit ce sélecteur de façon fiable et instantanée.** Trouvé en direct
(`getComputedStyle`) : `.stApp` a une propriété CSS `color-scheme` calculée qui, elle,
se met à jour INSTANTANÉMENT au clic sur Light/Dark/System (vérifié : "dark"→"light"
sans aucun rerun Python) — pilotée par une classe Emotion générée dynamiquement (nom
non stable, pas utilisable comme sélecteur), mais la propriété CSS calculée qui en
résulte est stable et lisible. Problème : `color-scheme` n'est utilisable qu'en valeur
`<color>` (`light-dark()`), pas pour choisir entre deux `background-image`/`url()`
entières — aucune solution CSS pure ne permet ce choix. Basculé sur `st.iframe` (PAS
`st.markdown` : un `<script>` injecté via `st.markdown(unsafe_allow_html=True)` NE
S'EXÉCUTE JAMAIS, vérifié en direct avec un test minimal — `window.__test` reste
`undefined`) avec une chaîne HTML brute : documenté comme exécutant du JS avec accès
same-origin à la page parente. Le script (`app._BACKGROUND_SCRIPT_TEMPLATE`) lit
`color-scheme` sur `.stApp` via `window.parent.document`, applique le fond directement
en JS (plus de `<style>` séparé), et observe les changements de `class` sur `.stApp`
(`MutationObserver`) pour réagir à CHAQUE bascule de thème sans dépendre d'un rerun
Python ; écoute aussi `matchMedia("(prefers-color-scheme: dark)").addEventListener`
pour le cas "System" + OS qui change en cours de session. Iframe rendue à hauteur
quasi nulle (`height=1`), aucun contenu visible voulu. Vérifié en direct : bascule
Light/Dark/System dans le menu Streamlit change l'image immédiatement, dans les deux
sens, sans aucune interaction supplémentaire.

**Troisième correctif, toujours le même jour — l'utilisateur a signalé que le niveau de
zoom de l'image changeait à chaque interaction.** Cause : `background-attachment:
local` sur `stMain` (second correctif) fait recalculer `background-size: cover` contre
le `scrollHeight` RÉEL de `stMain`, qui change à chaque page/résultat affiché — l'image
"respire" visiblement d'une interaction à l'autre, jamais un vrai zoom figé. Corrigé en
repassant `background-attachment: fixed` (ancré au VIEWPORT, constant hors
redimensionnement de fenêtre) sur `[data-testid="stAppViewContainer"]` — PAS `stMain` :
`fixed` sur un élément qui défile lui-même (`overflow-y: auto`) a un rendu
cross-browser incohérent (le fond peut rester figé ou défiler selon le moteur) ;
`stAppViewContainer`, qui ne défile jamais lui-même (voir second correctif), est la
cible correcte pour un fond réellement figé. Utilise aussi désormais
`assets/background_zoomed.png` (fournie par l'utilisateur, remplace `background.png`,
toujours présente dans le dépôt mais inutilisée) — un crop déjà recadré par
l'utilisateur, affiché tel quel (`background-position: center center`, plus de
recadrage `right top` côté CSS, qui n'avait plus de sens sur un crop déjà cadré en
amont). Vérifié en direct : le fond ne bouge plus du tout en défilant, dans les deux
thèmes, sans changement de zoom d'une interaction à l'autre.

**T51 — suffixe "Brand" retiré du nom affiché (2026-08-19, signalé par l'utilisateur —
voir la section Yakima Chief ci-dessus pour le détail complet).** Root cause à deux
niveaux : (1) `display_name` Yakima porte littéralement "Brand" pour 50/153 variétés
(artefact marketing, jamais présent côté BarthHaas) — corrigé par
`parsers._strip_yakima_brand_suffix`. (2) `_ingest_variety` ne mettait jamais `name` à
jour lors d'une fusion multi-sources — corrigé, BarthHaas l'emporte désormais toujours
sur conflit. Réingestion réelle : 43 → 0 houblons avec "Brand" dans le nom affiché.

**T52 — Alpha/beta acides, co-humulone, huile totale en avant + purpose inféré depuis
l'acide alpha (2026-08-19, demande utilisateur explicite — voir `docs/BACKLOG.md` pour
le détail complet).** Bug racine découvert en creusant : `alpha_acid`/`beta_acid`
étaient dans `schema.DROP_COMPOUNDS` ("non aromatiques") — jamais stockées en base du
tout, pas juste filtrées à l'affichage. Retirées de ce filtre (seul `polyphenols`, une
entrée morte, y reste). Co-humulone (fraction des acides alpha) ajouté, Yakima
UNIQUEMENT (`co_h` côté API Algolia, absent du HTML BarthHaas — vérifié en direct).
Purpose inféré (`matching.resolve_purpose`/`infer_purpose_from_alpha_acid`) : seuil
`ALPHA_ACID_BITTERING_THRESHOLD_PCT = 7.0` **mesuré** (scan de seuils sur les 142
houblons ayant à la fois un purpose BeerMaverick réel et un acide alpha connu, 78,2%
d'accord avec BeerMaverick) — préfixé "Inferred: " en GUI, jamais confondu avec une
donnée réelle, et **jamais utilisé pour la structure des blends** (`_pairing_grown_blends`
continue d'utiliser exclusivement le purpose BeerMaverick réel, pour ne pas contaminer
la garantie aromatic+bittering avec une estimation imparfaite). GUI : 4 `st.metric`
(Alpha/Beta/Co-humulone/Total oil, "—" si absent) en tête de `browse` ET des expanders
de détail Amplify/Contrast/By-descriptor ; unité déplacée dans le LABEL du metric
("Total oil (ml/100g)") après un `st.metric` tronqué en "1.4 ml/1…" constaté en direct ;
colonne Purpose des tableaux de résultats élargie de 3 à 5 (sur 16 parts) pour que
"Inferred: Bittering" reste lisible (également constaté tronqué en direct avant
correction). Effet de bord noté hors scope (pas corrigé) : un doublon "Amarillo®"
préexistant (`amarillo` fusionné vs `amarillo-brand-ama04` isolé) rend l'inférence et
le purpose réel visibles côte à côte sous le même nom affiché dans le sélecteur Browse.

**T53 — Renommage d'affichage "HopFinder", copie de la page d'accueil, roue d'arôme
dans `by-descriptor`, doublons de houblons audités (2026-08-19, demande utilisateur
— voir `docs/BACKLOG.md` pour le détail complet).** Renommage confirmé par question
explicite : affichage seulement (GUI + titre/prose README.md), le paquet Python/CLI/
`pyproject.toml` restent `hopmatch`. Page d'accueil : TF-IDF et couche descripteurs
(déclenchée seulement si l'utilisateur ajoute des descripteurs manuellement)
expliqués en une phrase pour Amplify ; dictionnaire d'affinités codé en dur
(`reference.CONTRAST_AFFINITY`, un prior heuristique de pairing culinaire, pas
sourcé) explicité pour Contrast. Roue d'arôme ajoutée à l'expander de détail de
`by-descriptor` (manquait par rapport à `browse`/Amplify/Contrast).
**Doublons de houblons** — audit complet par `name` identique, 7 paires trouvées,
vérifiées en direct sur `imported_fields.country_code` (API Algolia Yakima) pour
distinguer deux natures : (1) **5 VRAIS doublons** (Challenger, Fuggle, Hallertauer
Tradition, Hersbrucker Spät, Target) — même variété, MÊME région, juste un slug
différent entre BarthHaas et Yakima, jamais fusionnés faute de réconciliation
cross-source par nom+région (contrairement à la résolution BeerMaverick). Corrigé à
la racine (`ingest._find_variety_by_name_region`, appliqué dans `crawl_barthhaas` ET
`crawl_yakima`, alias GB/UK volontairement restreint aux libellés vérifiés) + réparé
sur la base existante (`ingest.merge_hop_varieties`, nouveau, réutilisable) : 194 →
189 houblons, 0 référence morte vérifiée après coup. (2) **4 crops RÉELLEMENT
distincts** (Amarillo®, Perle, Saaz, Northern Brewer) — même cultivar, pays de
culture différent (vérifié en direct), fusionner aurait été une RÉGRESSION : corrigé
côté AFFICHAGE (`app._disambiguated_hop_labels`, ajoute `(région)` uniquement en cas
de collision de nom réelle dans le sélecteur Browse, ex. "Amarillo® (United
States)"/"Amarillo® (Germany)").

**T54 — `by-descriptor` : tri à deux couches catégorique+quantitatif, pills de
sélection rapide, heatmap shadée par intensité (2026-08-19, demande utilisateur,
confirmée après recommandation explicite sur les tradeoffs — voir `docs/BACKLOG.md`
pour le détail complet).** `matching.by_descriptor` garde le recoupement
`hop_descriptors` comme filtre/tri PRIORITAIRE (inchangé), puis départage à
l'intérieur de chaque palier catégorique par l'intensité moyenne mesurée
(`hop_aroma_intensity`, T26, Yakima uniquement, sur l'intersection sélection ∩
données réelles du houblon — jamais un 0 fabriqué pour un descripteur manquant).
Houblons sans donnée quantitative exploitable classés après ceux qui en ont une,
dans le même palier — honnêteté d'abord. GUI : `st.pills` pour sélectionner
rapidement les 15 termes à donnée quantitative ; caption de transparence par
houblon ("Quantitative refinement: X/100 avg. intensity on ..." ou l'explication
de son absence) ; `_descriptor_heatmap` passée de 2 à 7 états (absent / no data /
5 paliers de bleu 0-100), réutilise `h["intensity"]` déjà chargé par
`by_descriptor`, aucune requête supplémentaire.
**Addendum (même jour, retour utilisateur immédiat après usage réel) — revirement :**
les descripteurs texte et les pills roue étaient UNIONNÉS dans un seul filtre
catégorique, donc un houblon ne recoupant QUE la roue (ex. tropical/citrus/floral)
pouvait ressortir mélangé parmi des houblons recoupant un descripteur texte plus
précis (ex. "papaya") — signalé : "the qualitative textual descriptor is not a
priority over the wheel aroma descriptor selected". `by_descriptor` prend
désormais `wheel_descriptors` comme second paramètre SÉPARÉ : `selected` (texte)
est le SEUL filtre catégorique dès qu'il est non-vide (un houblon doit recouper
au moins un descripteur texte) ; `wheel_descriptors` (pills) ne filtre plus rien,
sert uniquement à NOTER les houblons déjà retenus par le texte — sauf repli
explicite quand aucun descripteur texte n'est choisi (les pills filtrent alors
seules, sinon rien ne filtrerait). Vérifié en direct : "papaya" + pills
[tropical, citrus, floral] → exactement les 4 houblons portant "papaya", chacun
noté par son intensité moyenne sur les 3 axes.
**Second addendum (même jour) :** la heatmap est scindée en deux grilles
distinctes — descripteurs du vocabulaire roue (`intensity_vocab`, dégradé de
bleu possible) vs. tous les autres (structurellement jamais de donnée
quantitative, ex. "pine"/"grapefruit") — plutôt qu'une seule grille mélangée,
signalé confus par l'utilisateur. Palier "présent sans donnée" recoloré de
gris à noir plein (`#000000`) : le gris se lisait comme un NaN/valeur
manquante, pas comme "présent" (`_heatmap_chart`, factorisé pour les 2 sections).

**T55 — blends : chaque taille dans son propre `st.container(border=True)`
(2026-08-19, demande utilisateur : "it's visually difficult to separate blend
n1/n2...n5").** `_render_blends` enchaînait `st.write("**Size N**")` +
`_render_hop_rows` sans aucune séparation visuelle entre tailles. Pas de
conversion en `st.dataframe`/`st.table` (le Purpose reste un `st.badge` par
cellule, seul widget qui s'adapte aux deux thèmes) : un conteneur bordé par
taille délimite au moins aussi clairement que des lignes horizontales sans ce
compromis. Vérifié en direct : Size 1/2/3... chacun visuellement encadré.

**T56 — `contrast` : Saaz (et d'autres) introuvable même au plafond de résultats
(2026-08-19, signalé par l'utilisateur sur "tropical"/"mango" → "spicy"
attendu).** Root cause vérifiée en direct : Saaz recoupe bien "spicy" (1/3 de
la cible "tropical" = dank/resinous/spicy, score 33.3) — mais AUCUN tri
secondaire n'existait, donc parmi les ~84 houblons à égalité de score sur une
base réelle, l'ordre dépendait de l'itération SQL de `hops` (arbitraire), pas
d'un critère pertinent — Saaz tombait à la position ~74, hors du plafond GUI
(30). Corrigé : `matching.contrast` trie désormais par score PUIS `total_oil`
réconcilié desc PUIS `variety` asc (même proxy que `by_descriptor`) — rend le
classement déterministe/explicable, mais ne garantit pas qu'un houblon donné
dans une égalité massive tombe dans les `top` premiers. D'où deux correctifs
complémentaires : `total_matches` (nouveau, compte AVANT troncature) permet à
la GUI d'afficher "Showing 8 of 91 hops..." au lieu d'une troncature
silencieuse ; plafond du curseur "Number of results" relevé de 30 à 100.
Vérifié en direct sur données réelles : Saaz apparaît bien à 100.

**T57 — `contrast` : cible d'affinité modifiable par l'utilisateur (2026-08-19,
demande utilisateur, suite directe de T56).** "we should orient the
complementary aroma by pre-selecting them but let the user chose which one he
want to keep... In the saaz example, user could only want to find spicy as
complementary note, we should make possible to untick dank and resinous,
rather than imposing the mapping." `matching.contrast_affinity_target(descriptors)`
(nouveau, factorisé hors de `contrast()`) calcule la proposition automatique
sans toucher la base -- réutilisable par la GUI pour pré-afficher la
proposition AVANT de lancer la recherche. `contrast()`/`contrast_blend()`
acceptent un nouveau paramètre `target_descriptors` qui REMPLACE le calcul
automatique quand fourni (`None` = comportement inchangé, rétrocompatible
CLI). GUI (`app._contrast`) : nouvelle section `st.pills` sous les
"Descriptors of the note to contrast", listant les 10 catégories cœur de
`CONTRAST_AFFINITY` (`matching.CONTRAST_CORE_CATEGORIES`, nouveau -- jamais
d'autres valeurs possibles dans la carte, "there is not much" comme les pills
de la roue d'arôme), pré-cochées avec la proposition automatique mais
librement modifiables (untick pour exclure, coche pour élargir). `key` du
widget dépend des descripteurs de note sélectionnés (`contrast_target_pills_
{tuple(sorted(selected))}`) : changer la note recalcule la proposition
(nouvelle pré-sélection), une modification manuelle survit aux reruns tant
que la note ne change pas elle-même. Vérifié en direct sur données réelles :
"tropical" propose dank/resinous/spicy ; décocher dank+resinous (ne garder
que spicy) fait passer la cible de 91 à 78 houblons recoupés, TOUS à score
100 (un seul terme cible) au lieu d'un mélange 33/67/100 -- Saaz redevient
trouvable en relevant simplement "Number of results" (T56), plus besoin de
deviner sa position dans une égalité massive à 3 termes.

**T58-T61 (2026-08-19, demande utilisateur groupée en 4 tickets — voir
`docs/BACKLOG.md` pour le détail complet de chacun).**
**T58 — nouvel outil GUI "Compare Hops"** (inspiré de beermaverick.com, pas le
design) : jusqu'à 5 houblons, palette tableau10 (catégorielle, PAS "Spectral"
suggéré par l'utilisateur — divergente, pas adaptée à du nominal), couleur
cohérente sur les 3 graphiques. Radar de roue d'arôme superposé
(`app._aroma_wheel_compare`, généralisation multi-houblons de `_aroma_wheel` —
ne contredit pas le rejet du radar en T4, qui concernait des descripteurs
BINAIRES, pas une intensité quantitative). 2 barplots à double axe
(`app._compare_dual_axis_barplot`) : co-humulone converti en % absolu
(`alpha_acid × co_humulone_pct_of_AA / 100`) pour partager l'axe % avec AA/BA,
`total_oil` (ml/100g) sur un second axe ; piège d'unité supplémentaire détecté
en écrivant le ticket (pas signalé par l'utilisateur) sur le barplot détaillé :
`thiols` en µg/kg contre `pct_oil` pour tous les autres composés, même
traitement à double axe.
**T59 — ®/™/© retirés du nom affiché** (`parsers.strip_trademark_symbols`,
appliqué à la source comme `_strip_yakima_brand_suffix` T51) : vérifié en
direct qu'aucun houblon n'avait le symbole en position 0 (relu "at the
beginning" comme "dès le départ", pas "en tête de chaîne") — 62 houblons
réels concernés ailleurs dans le nom. Réingestion réelle : 0/189 restants.
**T60 — désambiguïsation par région déplacée dans `matching.load()`**
(`_disambiguate_hop_names`, remplace l'ancien `app._disambiguated_hop_labels`
scopé au seul sélecteur Browse) : décision utilisateur explicite après la
tension notée en T53/T54 — "modify the name base on the provenance" puisque
la région est facile à retrouver, PAS de fusion (perdrait la distinction de
terroir réelle). "Northern Brewer"/"Amarillo" etc. s'affichent désormais
partout (amplify/contrast/by-descriptor/blends), pas seulement Browse, sous
la forme "Nom (Région)" dès qu'une collision existe.
**T61 — `contrast`/`contrast_blend` : filtre par purpose** (`purposes`,
nouveau paramètre, même pattern que `target_descriptors` T57), pré-coché
`["aromatic", "bittering"]` en GUI, résolu via `resolve_purpose` (réel ou
inféré) AVANT troncature à `top` pour ne pas fausser `total_matches`/T56. Un
purpose "both" satisfait le filtre dès qu'un des deux rôles est demandé ;
un purpose totalement inconnu est exclu dès qu'un filtre est actif.
Vérifié en direct sur les 4 tickets, données réelles : Compare Hops
(Citra/Mosaic/Simcoe, radar + 2 barplots à double axe corrects) ; 0 symbole
commercial restant en base ; "Northern Brewer (United States)"/"Northern
Brewer (Germany)" désormais distincts dans les résultats `contrast` ; filtre
purpose passant de 91 à 74 matches sur "mango" en décochant "bittering".

**T62 — Définitions des 15 catégories de la roue d'arôme + tooltip par label
(2026-08-19, demande utilisateur, voir `docs/BACKLOG.md` pour le détail
complet de l'investigation).** Signalé comme redondance apparente
("grassy/herbal/vegetal semblent dire la même chose") ; vérifié FAUX sur
trois fronts avant de coder quoi que ce soit : (1) `hop_aroma_intensity`
reste 100% Yakima (aucune fusion BarthHaas) ; (2) corrélation
`vegetal`/`grassy` mesurée sur données réelles = Pearson r=0.16 (faible,
Saaz en contre-exemple net : grassy=75/vegetal=8) ; (3) le "Hop Sensory
Ballot" officiel Yakima Chief (PDF récupéré via Wayback Machine, leur URL
directe étant cassée depuis leur migration de site) confirme trois notions
réellement distinctes : grassy = herbe fraîche coupée/foin, herbal =
thé/menthe/romarin (herbe aromatique culinaire), vegetal =
chou/céleri/poivron/tomate (légume, souvent un signal de prudence en
brassage). Ce même document révèle aussi que "Pomme" (alias → "apple",
voir section BarthHaas plus haut) N'ÉTAIT PAS une coquille française du CMS
Yakima comme documenté précédemment -- c'est leur propre terme
professionnel de dégustation pour "fruits à pépins", en anglais dans leur
document officiel ; commentaire de `reference.py` corrigé en conséquence
(l'alias d'affichage "apple" reste inchangé, juste plus clair pour un
public non spécialiste). `reference.AROMA_WHEEL_DEFINITIONS` (nouveau, 15
entrées sourcées sur ce ballot) ré-exporté via
`matching.AROMA_WHEEL_DEFINITIONS`. Tooltip par label demandé
explicitement par l'utilisateur ("(?) close to each label name... when
mouseovering it") : implémenté nativement via le canal `tooltip` de
Vega-Lite sur le mark `text` des labels d'axe (`_aroma_wheel`/
`_aroma_wheel_compare`), pas une icône (?) positionnée à la main -- survoler
UN SEUL label affiche SA définition précise. Caption de découvrabilité
ajoutée sous les 4 rendus de roue de la GUI (Browse, Amplify, Contrast,
By-descriptor, Compare Hops). Vérifié en direct sur Saaz (CZ et US, y
compris un axe à intensité 0).

**T63 — Revue de code complète, 6 défauts corrigés (2026-08-20, demande
utilisateur : "do a massive review of the codebase", puis "fix all this",
voir `docs/BACKLOG.md` pour le détail complet).** Relecture méthodique de
tout `src/`+`tests/` (~7400 lignes) croisée avec `pyflakes`. Corrigés :
(1) `_NON_AROMA_DISPLAY` dupliqué à l'identique dans `app.py` ET
`matching.py` -- renommé `matching.NON_AROMA_DISPLAY` (public, ré-exporté,
même principe que `CONTRAST_CORE_CATEGORIES`/`AROMA_WHEEL_DEFINITIONS`),
copie `app.py` supprimée. (2) `ingest.py` : `n_curated` mort (pré-existant,
juillet 2026) supprimé. (3) `tests/test_matching.py` : assertion manquante
dans `test_pairing_top_n_excludes_low_ranked_partners` -- le chemin par
défaut (`pairing_top_n=10`) n'était jamais vérifié malgré les apparences,
corrigé. (4) `app._browse` : `hcomp` calculé deux fois, doublon mort
supprimé. (5) `reference.AROMA_WHEEL_DEFINITIONS` (T62) sans aucun test --
2 tests ajoutés (identité de ré-export, couverture exacte des 15
catégories). (6) **`matching.by_descriptor` sans équivalent de
`total_matches`** contrairement à `contrast` (T56) -- changement le plus
large : `by_descriptor` retourne désormais `{"ranked": [...],
"total_matches": N}` au lieu d'une liste nue, répercuté sur `cli.py`,
`app.py` (+ caption de transparence), et les 12 sites d'appel direct dans
les tests. Vérifié en direct : `pyflakes` propre sur tout le projet ;
navigateur réel + CLI affichent tous deux "10 of 122" sur `by-descriptor
citrus`. Suite pytest 197 -> 200, toutes vertes.

**T64 — Déploiement Streamlit Community Cloud (2026-08-20, demande
utilisateur, voir `docs/BACKLOG.md` pour le détail complet).** Corrigé un
malentendu au passage : `app.py` NE construit/télécharge PAS la base "à la
volée" comme supposé -- lecture seule contre une base déjà là, échouait
simplement sur un conteneur Community Cloud frais (système de fichiers
éphémère). Vérifié avant tout changement : aucun fichier de données n'est
commité dans le dépôt public (`.gitignore` déjà correct). Mécanisme
retenu : base construite une fois en local, hébergée dans un dépôt GitHub
PRIVÉ séparé, téléchargée par l'app à son démarrage si absente
(`app._fetch_remote_db`, `@st.cache_resource`, API Contents GitHub via
`st.secrets["DB_DOWNLOAD_URL"/"DB_DOWNLOAD_TOKEN"]`) -- jamais de
re-scraping des sources depuis le conteneur déployé. Piège découvert en
testant en direct : `st.secrets.get(clé)` LÈVE (pas de `secrets.toml` du
tout) au lieu de renvoyer `None` comme un dict -- capturé largement.
Dépendances de déploiement corrigées au passage (nécessaires, pas
optionnelles) : `requirements.txt` ajouté à la racine (`pyproject.toml`
seul n'installe rien, `dependencies = []`), `pillow` déclaré explicitement
dans l'extra `[ui]` (fonctionnait avant seulement par effet de bord
transitif de `streamlit`), commentaire README stale "numpy, scipy"
corrigé (aucun import numpy/scipy dans `src/`, scipy servait à l'ancien
`combine()` retiré le 2026-08-12). Contact licence ajouté DANS l'app
(caption en tête de sidebar), pas seulement dans `README.md`/`LICENSE`.
4 tests ajoutés pour `_fetch_remote_db`. Suite pytest 200 -> 204.
**Addendum (2026-08-20)** : le lien GitHub ajouté dans la sidebar
(`st.sidebar.page_link`) a été retiré -- Streamlit Community Cloud
affiche déjà sa propre icône GitHub en haut à droite de l'app déployée,
rendant le lien ajouté à la main redondant. La caption licence/contact
reste (pas d'équivalent natif Streamlit).

**T65 — Inputs des outils centralisés sur la page principale, plus dans
la sidebar (2026-08-20, demande utilisateur signalée après le déploiement
réel sur téléphone, voir `docs/BACKLOG.md` pour le détail complet).**
"The note for amplify is in the panel, not the tool page... straightforward
on PC but not phone" -- la sidebar Streamlit est repliée par défaut sur
mobile (menu hamburger), invisible sans interaction supplémentaire,
contrairement au bureau où elle reste toujours visible (jamais remarqué en
testant sur PC tout le reste de la session). Audit de tous les
`st.sidebar.*` : 4 vrais inputs d'outil déplacés vers la page principale
(sélecteur de note d'`amplify`, `--oav`, curseurs "Number of results"/
"Number of hops shown" de `contrast`/`by-descriptor`) ; le reste
(licence/contact, stats de base, radio de NAVIGATION entre outils) reste
en sidebar -- chrome global de l'app, pas un input d'outil. `main()`
traite désormais `amplify` de façon symétrique aux 4 autres modes
(`_amplify(con, note)` -> `_amplify(con)`, sélection de note déplacée à
l'intérieur). 2 captions de transparence corrigées ("in the sidebar" ->
"above"). 3 tests AppTest repointés (`at.sidebar.selectbox`/`slider` ->
`at.selectbox`/`slider`). Suite pytest 204, vérifié en direct dans le
navigateur pour les 3 outils. (Lien GitHub de la sidebar retiré juste
après, même jour : redondant avec l'icône GitHub que Streamlit Community
Cloud affiche déjà nativement en haut à droite de l'app déployée.)

**T66 — Tableaux de résultats amplify/contrast/blends en `st.dataframe`
(2026-08-20, demande utilisateur signalée juste après T65, voir
`docs/BACKLOG.md` pour le détail complet).** Root cause différente de
T65 : `app._render_hop_rows` (partagé par les tableaux de résultats
amplify/contrast et les tableaux de blend) construisait chaque ligne à la
main via `st.columns`, choisi à l'origine pour un `st.badge` Purpose
coloré (un `st.dataframe` ne peut pas rendre un widget arbitraire par
cellule) -- or Streamlit empile automatiquement les `st.columns` à la
verticale sous une certaine largeur d'écran (comportement responsive
natif, pas un bug de cette app), donc chaque ligne redescendait en pile
sur mobile, plus du tout un tableau. Décision utilisateur explicite :
"use plain text for the tables, but keep the badges for the browse and
other places". `_render_hop_rows` réécrit en `st.dataframe` réel, Purpose
en texte simple via un nouveau `_purpose_label` (factorisé hors de
`_purpose_badge`, qui reste inchangé et coloré partout ailleurs --
Browse, expanders de détail -- où un seul purpose s'affiche à la fois,
jamais un tableau). 1 test réécrit pour lire `at.dataframe[0].value` (un
vrai `pandas.DataFrame`) au lieu de chercher une signature `st.badge`.
Suite pytest 204, vérifié en direct (Amplify "mango" + ses 5 tailles de
blend en vrais tableaux bordés ; badge "Bittering" toujours coloré sur
Browse).

**T67 — "Similar hops" en bas de Browse, par composition moléculaire (2026-08-21,
demande utilisateur explicite, faisant suite à un brainstorm de features : parmi 3
idées proposées (substitute finder, filtre "my hop stock", amplify multi-notes),
l'utilisateur a retenu la première mais reformulée -- pas les associations
éditoriales `hop_similar`/`hop_pairings`/`hop_substitutions` (T25, déjà affichées
par `_hop_associations`), une section calculée depuis `hop_composition`, "ordering
hops from the most similar to the least based on the molecular composition we
already have in house").** `matching.similar_hops_by_composition(con, variety,
top=10)` : RÉUTILISE la méthode déjà établie pour la couche moléculaire d'`amplify`
(`molecular_scores` -- cosinus sur vecteurs normalisés-par-composé/pondérés par
`specificity`, voir "similarité normalisée-par-composé (TF-IDF)" en tête de
`matching.py`), appliquée houblon<->houblon au lieu de note<->houblon, plutôt que
d'inventer une nouvelle méthode -- pas de nouvelle source de données, tout vient de
`hop_composition` déjà en base. Exclut `NON_AROMA_DISPLAY` du vecteur (pas des
molécules d'arôme). Houblon absent de `comp`, sans aucun composé aromatique mesuré,
ou sans AUCUN composé partagé avec un candidat -> exclu (pas un faux score 0),
même principe honnêteté-d'abord que les molécules orphelines -- vérifié en direct
sur 3 vraies variétés BarthHaas-only sans aucun composé hors alpha/beta/oil (Huell
Classic Hops, Relax, Sticklebract) : liste vide, caption explicite en GUI plutôt
qu'un tableau vide silencieux. Rendu en `app._similar_hops_section` (nouvelle
fonction, `_render_hop_rows` réutilisé tel quel) tout en bas de `_browse`, sous
`_hop_associations` -- une QUATRIÈME relation houblon<->houblon, jamais fusionnée
avec les trois éditoriales/recette déjà affichées juste au-dessus. 3 tests ajoutés
(`test_matching.py`). Vérifié en direct dans le navigateur sur la base réelle (189
houblons) : Relax (BarthHaas seul, aucun composé d'arôme mesuré au-delà
alpha/beta/oil) -> liste vide avec message explicite. Suite pytest 204 -> 207.

**Addendum T67, même jour (2026-08-21, signalé par l'utilisateur en direct) --
Callista ressortait #1 pour Citra devant Mosaic, un vrai défaut de méthode, pas
une confusion utilisateur.** Callista a des descripteurs berry/stone fruit très
différents de Citra citrus/tropical, et le comparatif visuel Compare Hops ne
montrait rien de tel -- creusé en direct sur les valeurs réelles (`hop_composition`)
plutôt que supposé. Root cause : le cosinus pur est invariant d'échelle. Callista
(BarthHaas seul, 8/10 composés de Citra, aucune donnée beta-pinène/géraniol
Yakima) a des valeurs uniformément DILUÉES (~20-50% de celles de Citra sur les
composés partagés, cohérent avec son alpha/huile totale plus faibles) mais
PROPORTIONNELLEMENT alignées -> cosinus élevé (89.1%) simplement parce que la
direction du vecteur, tronqué à ses 8 dimensions, reste proche de celle de
Citra. Mosaic, qui a pourtant la MÊME couverture complète que Citra (10/10
composés, aucune donnée manquante -- et figure d'ailleurs dans le
`hop_similar` Yakima RÉEL de Citra, confirmation indépendante), scorait plus
bas (88.2%) à cause d'UN SEUL composé (`ketones`, poids de spécificité élevé
car rare dans la base) où sa valeur diverge fortement -- un désaccord
directionnel sur un axe pesait plus, dans un cosinus pur, qu'une incomplétude
systématique sur deux axes entiers. C'est l'inverse de ce que la confiance
dans la donnée devrait donner : un houblon moins mesuré ne devrait jamais
pouvoir dépasser un houblon à couverture complète sur la même cible. Corrigé
par une pénalité de COUVERTURE (rappel des composés de la variété requêtée que
le candidat a aussi, `len(shared) / len(target_vec)`, asymétrique -- aucune
pénalité si le candidat a des composés EN PLUS, déjà pénalisé par la norme du
cosinus) multipliée au cosinus, exposée en GUI (nouvelle colonne "Coverage",
transparence). Résultat vérifié en direct après correctif : Mosaic repasse #1
(88.2%, couverture 100%), Callista retombe #4 (71.3% = 89.1% * 0.8 couverture).
1 test ajouté (`test_similar_hops_by_composition_penalizes_incomplete_coverage`).
Suite pytest 207 -> 208.

**T68 — Deuxième couche de similarité (roue d'arôme quantitative), combinaison
activable par couche, titre commun "Database similarity and substitution"
(2026-08-21, demande utilisateur explicite, même jour que T67).** "We also
could use the quantitative aroma wheel scores right? ... allow the used to
toogle molecular and/or aroma_wheel layers." Root du refactor : la méthode de
`similar_hops_by_composition` (cosinus normalisé-par-axe/pondéré-spécificité +
pénalité de couverture, T67 addendum) ne dépend en réalité d'aucune notion
propre à `hop_composition` -- factorisée en `matching._coverage_penalized_
cosine(raw_by_variety, variety)`, générique sur {variety: {axe: valeur}}.
`similar_hops_by_composition` et le nouveau `similar_hops_by_aroma_wheel`
(sur `hop_aroma_intensity`, T26, Yakima uniquement) l'appellent chacun avec
leur propre univers d'axes -- aucune duplication de la méthode. `matching.
similar_hops(con, variety, use_molecular=, use_aroma_wheel=, top=)` combine
les deux : MOYENNE des couches actives ayant réellement une donnée pour
CHAQUE candidat (jamais une couche manquante comptée comme 0 -- un houblon
BarthHaas seul, sans `hop_aroma_intensity`, reste comparable via la seule
couche moléculaire même si les deux sont activées), `layers_used` exposé par
ligne pour la transparence. Point d'entrée GUI unique
(`app._similar_hops_section`), toggle `st.pills` (même widget que le filtre
Purpose de `contrast` -- 2 options, tiennent sur une ligne), les deux actives
par défaut ; tableau : colonnes Molecular/Aroma wheel affichées seulement
quand les deux couches sont actives (sinon redondantes avec Similarity).
**Titre "Database similarity and substitution" ajouté** (signalé : "the
'Similar varieties (Yakima)' is not a main title as compared with 'Similar
hops (by molecular composition)'") -- l'ancien `st.subheader` propre à la
section calculée (T67) la faisait paraître plus importante que les 3
relations éditoriales de `_hop_associations` (simples `st.write("**...**")`)
juste au-dessus ; un seul `st.subheader` commun ajouté, les 5 relations
(3 éditoriales + 2 couches calculées) redescendues au même poids visuel
(`st.write("**...**")`) en-dessous.
**Observation notée pendant la vérification, pas un bug corrigé** : la
couche roue d'arôme seule produit des scores très resserrés en haut de
classement pour Citra (Simcoe 99.7%, Cascade 99.6%, Ekuanot 99.3%...,
`shared_descriptors` quasi identiques). Cohérent avec la donnée elle-même
(taxonomie à 15 catégories seulement, 12-15/15 couvertes pour la plupart des
houblons Yakima, donc peu de pouvoir discriminant par rapport aux 8-10 axes
bien plus variables de `hop_composition`) plutôt qu'un défaut de méthode
comme Callista/T67 -- pas de contre-exemple démontrant une erreur, donc rien
changé ; à surveiller si l'utilisateur trouve un cas concret qui semble
faux. 7 tests ajoutés (`test_matching.py`). Suite pytest 208 -> 211.

**Addendum T68, même jour (2026-08-21, signalé par l'utilisateur en direct) --
en-têtes de colonne ambigus avec une seule couche active.** "Toogling
molecular add the 'Similarity' column and toogling the aroma wheel shows
'Molecular'." Vérifié en direct : AUCUN mismatch de données (le score avec
une seule couche active est bien celui de cette couche, confirmé en
comparant `similar_hops(use_aroma_wheel=False)` à `similar_hops_by_
composition` seule, valeurs identiques au décimal près) -- le vrai défaut
était que `app._similar_hops_section` titrait la colonne de score
génériquement "Similarity" quel que soit le nombre de couches actives (1 ou
2), sans jamais dire LAQUELLE avec une seule couche -- lisible à tort comme
un mismatch. Corrigé : en-tête toujours explicite selon l'état des pills --
"Molecular similarity" (molecular seul), "Aroma wheel similarity" (aroma
wheel seul), ou "Combined similarity"/"Molecular similarity"/"Aroma wheel
similarity" (les trois colonnes, deux couches actives). Vérifié en direct
dans le navigateur sur les 3 états (Admiral molecular-seul, Citra aroma
wheel-seul, Citra deux couches) : aucune ambiguïté restante, valeurs
identiques entre vue combinée-un-seul-actif et vue couche seule. Aucun test
ajouté (changement de libellé GUI pur, pas de logique nouvelle).

**Second addendum T68, même jour (2026-08-21, signalé par l'utilisateur en
direct) -- "Similar hops (computed from measured data)" au même niveau de
titre que "Database similarity and substitution", séparateur avant.** Le
premier passage T68 avait mis les 5 relations (3 éditoriales +
2 couches calculées) sous UN SEUL `st.subheader` commun, la section calculée
redescendue en `st.write("**...**")` -- l'utilisateur a précisé vouloir
plutôt DEUX sections soeurs de même poids, pas une hiérarchie à un niveau.
`app._similar_hops_section` repasse en `st.subheader` (comme avant le
premier passage T68) ; `app._browse` insère un `st.divider()` entre la fin
de `_hop_associations` et l'appel à `_similar_hops_section`, marquant la
frontière entre "Database similarity and substitution" (titre couvrant
seulement les 3 relations éditoriales désormais) et "Similar hops (computed
from measured data)" (sa propre section, même niveau `st.subheader`).
Vérifié en direct dans le navigateur : séparateur visible juste avant le
second subheader, les deux rendus avec la même taille de police. Aucun test
ajouté (changement de structure GUI pur).

**T69 — Section "Recent updates" en bas de la page d'accueil (2026-08-21,
demande utilisateur explicite : "add ... a summary of last implemented
features from the most recent to the oldest ... rely on github commit for
that").** `app._RECENT_UPDATES` : liste statique de 10 entrées (date +
résumé en anglais), la plus récente en tête, écrites à partir de
`git log` RÉEL (pas inventées) -- décision explicite de NE PAS lire `git
log` en direct dans la GUI : les messages de commit sont en français
(convention CLI/commit, voir Conventions plus bas) donc incompatibles avec
le texte GUI anglais sans traduction automatique non fiable, et `.git`
n'est pas garanti présent dans le conteneur Streamlit Community Cloud
déployé (T64). Curée à la main comme ce journal CLAUDE.md, à MAINTENIR
MANUELLEMENT (ajouter une entrée) à chaque nouvelle fonctionnalité
utilisateur livrée -- pas régénérée automatiquement. Rendue sous les
boîtes d'outils existantes (`app._home`, après le `st.columns` de
`_TOOL_SUMMARIES`), `st.divider()` + `st.subheader("Recent updates")` +
liste markdown. Vérifié en direct dans le navigateur. Aucun test ajouté
(contenu statique, pas de logique).

**T70 — Compare Hops : bascule relatif/absolu (% d'huile <-> ml/100g) sur le
barplot "Detailed composition" (2026-08-21, suggestion reprise telle quelle,
committé sans passer par ce journal sur le moment -- rattrapé ici).** "Compare
Hops separates total oil... from composition (% of oil)... the reader has both
numbers in front of them but in two different charts, and has to do the
multiplication in their head." `app._compare_detail_value(hcomp, compound,
absolute)` convertit chaque composé `pct_oil` en quantité absolue via
`total_oil` déjà réconcilié par `matching.load()` (`% × huile_totale / 100`,
EXACTEMENT ce que `matching.amount()` fait déjà côté scoring, réappliqué ici
pour l'affichage) -- toggle `st.toggle`, ON par défaut (demande explicite),
réponds directement à l'écran à "deux houblons à 48%/35% de myrcène peuvent-
ils s'inverser en absolu si leur huile totale diffère ?" sans calcul mental.
Thiols (déjà en µg/kg) jamais convertis (vérifié via `rec["unit"] !=
"pct_oil"`). Houblon sans `total_oil` connu : composé exclu du graphique
plutôt qu'une valeur fabriquée à partir d'une huile devinée, signalé
explicitement en caption -- vérifié en direct qu'aucun houblon réel n'est
concerné (tous les houblons avec un composé `pct_oil` ont un `total_oil`
connu dans la base actuelle).

**T71 — Tooltip descripteurs par composé sur le barplot "Detailed
composition" (2026-08-21, demande utilisateur explicite, suggestion reprise
telle quelle).** "Sur le barplot, myrcene est une chaîne nue. Rien ne dit
qu'elle couvre vert, herbacé, résineux et pin. C'est précisément ce qui m'a
permis de croire... que myrcène élevé impliquait bière verte." `matching.
compound_descriptors(con, compounds)` : jointure par IDENTITÉ STRUCTURALE
(CID PubChem `reference.MOLECULES[c][2]` -> CAS via `pubchem_cids` -> `flavornet_
compounds.descriptors`), PAS par nom de chaîne -- même principe que
`ingest._canonical_compound`/`_build_cas_to_hop_name` à l'ingestion, jamais
réinventé. Vérifié en direct sur les 11 composés du barplot : 8/11 résolus
(myrcene -> "balsamic, must, spice" -- confirme au passage que le lien
myrcène=vert de l'utilisateur n'était pas dans la donnée elle-même ; humulene,
caryophyllene, farnesene, linalool, geraniol, beta-pinene, selinene), thiols/
isobutyrate/ketones correctement absents (agrégations sans entrée `reference.
MOLECULES` individuelle, jamais une valeur inventée).

Pas de tooltip natif possible sur le LABEL D'AXE lui-même (contrairement à la
roue d'arôme qui dessine ses propres labels en `mark_text` avec coordonnées
calculées à la main -- Vega-Lite n'expose aucun canal d'encodage sur le texte
d'un axe standard `alt.Axis`) : substitut retenu, une colonne RECT invisible
(`opacity=0.001`, pas exactement 0 -- certains moteurs Vega n'attachent pas
d'écouteur de survol à une opacité strictement nulle) couvrant toute la
hauteur du graphique par composé résolu, posée EN PREMIER dans l'empilement
de couches (donc sous les barres) : survoler une barre garde son tooltip
habituel (Hop/Field/Value + "Smells like" ajouté) ; survoler l'espace autour
(y compris juste au-dessus de bâtonnets trop courts pour être visés) déclenche
le même tooltip "Smells like" via la couche rect -- une cible de survol PLUS
LARGE que le seul label, pas plus fragile à positionner. Vérifié en direct
dans le navigateur (Citra vs Cluster) : survol direct d'une barre myrcène ->
tooltip complet avec "Smells like: balsamic, must, spice" ; survol de
l'espace vide au-dessus des bâtonnets géraniol (aucune barre sous le
curseur) -> "Field: geraniol / Smells like: rose, geranium" via la couche
rect ; colonnes ketones/isobutyrate/thiols (non résolues) correctement
sans aucun tooltip descripteur. Barplot "Principal info" (alpha/beta/co-
humulone/oil) non affecté : `descriptors` n'est passé qu'à l'appel du
barplot "Detailed composition", ces 4 grandeurs ne sont de toute façon pas
des composés odeur-actifs Flavornet. 3 tests ajoutés (`test_matching.py`,
chaîne CID->CAS->descripteurs, absence si CAS non résolu, absence si pas
d'entrée Flavornet). Suite pytest 211 -> 214.

**T72 — "Smells like" étendu aux tableaux de composition texte (2026-08-21,
demande utilisateur explicite, suite directe de T71) : "this was implemented
when mousovering a bar of the barplot but the information should be also in
the compounds table of the browse results".** T71 n'avait câblé
`matching.compound_descriptors` que dans le barplot Compare Hops -- or le
même défaut (composé "nu", sans indication de ce qu'il sent) existe dans
TROIS tableaux de composition texte distincts, chacun déjà documenté comme
devant reproduire le même contenu que Browse : `app._browse` (table
principale), `app._hop_detail_expanders` (expanders sous les résultats
amplify/contrast, T39/T53 -- "same content than what is on the browse
page") et `app._by_descriptor` (expanders sous la heatmap, implémentation
séparée avec sa propre structure `h["compounds"]`). Plutôt que de câbler
`compound_descriptors` séparément à chaque site (et refaire des requêtes
CID->CAS->Flavornet par houblon dans une boucle), `app._all_compound_
descriptors(con, comp)` calcule le dict compound->descripteurs UNE SEULE
FOIS par rendu de page sur l'univers complet des composés présents dans
`comp` (indépendant du houblon affiché), réutilisé par les 3 sites avec
une colonne "Smells like" ajoutée à chacun (valeur "—" si non résolu,
même convention que les colonnes de score des couches calculées T67/T68).
Vérifié en direct dans le navigateur sur les 3 emplacements (Browse/
Admiral, Amplify "mango" détail Sabro, By-descriptor "citrus" détail
Sorachi Ace) : colonne présente et cohérente partout, myrcene -> "balsamic,
must, spice" identique aux trois endroits. Aucun test AppTest ajouté
(wrapper trivial autour de `matching.compound_descriptors`, déjà testé
unitairement en T71 ; `_all_compound_descriptors` ne fait qu'agréger
l'univers de composés et déléguer).

**T73 — Descripteurs de composé complétés contre Scott Janish, The New IPA
(2026-08-21, demande utilisateur explicite, photo du tableau "Compound
Descriptions" p.22 fournie).** "Double check that the description of
molecules is completed by this figure... if some smell or taste is missing
from the infobox of each compound, add them." `reference.
JANISH_COMPOUND_CATEGORIES` (nouveau) : catégorie(s) par composé, croisées
À LA MAIN contre les 12 catégories du tableau du livre, restreintes aux
composés RÉELLEMENT mesurés dans `hop_composition` (pas d'entrée pour les
molécules `MOLECULES` jamais présentes dans les données houblon réelles,
ex. limonene/citronellol -- une entrée qui ne s'afficherait jamais serait
morte). Résultat de la vérification composé par composé (voir le
commentaire de `JANISH_COMPOUND_CATEGORIES` pour le détail complet) :
geraniol->Floral, linalool->Citrus, myrcene->Herbal, humulene/beta-pinene/
farnesene->Woody, caryophyllene->Woody+Spicy, thiols->Berry & Currant (via
le composé 4-mercapto-4-methylpentan-2-one/4MMP listé dans cette catégorie
par le livre -- déjà agrégé sous "thiols" par `reference.ALIASES`, donc
l'association s'applique de plein droit). Explicitement PAS mappés faute de
correspondance vérifiable : isobutyrate/ketones (composés agrégés BarthHaas
sans entrée nominative dans le livre -- leur assigner "raspberry ketone" au
hasard serait une supposition non vérifiable sur QUELLE cétone précise est
mesurée, même principe que le refus déjà documenté de deviner un CID
PubChem) ; selinene (absent des 12 catégories du tableau).

`matching.compound_descriptors` complété (pas remplacé) : la catégorie
Janish n'est ajoutée QUE si elle n'est pas déjà représentée par un mot
Flavornet existant (comparaison par racine de 4 lettres, ex. Flavornet
"wood" couvre déjà "Woody" -- pas de doublon), et TOUJOURS distinctement
citée `"(Janish, The New IPA)"` dans la chaîne retournée, jamais fusionnée
sans attribution à la mesure GC-O Flavornet. Vérifié en direct sur les 11
composés réels : myrcene/linalool/geraniol/beta-pinene gagnent une
catégorie manquante (ex. myrcene : "balsamic, must, spice; herbal (Janish,
The New IPA)") ; humulene/caryophyllene/farnesene/selinene inchangés (déjà
couverts, ou absents du livre) ; **thiols, qui n'avait AUCUNE résolution
Flavornet possible (pas de CID propre) et affichait "—" partout, obtient
désormais sa première étiquette : "berry & currant (Janish, The New IPA)"**
-- seul repli utile de ce ticket qui comble un vrai trou plutôt qu'un
doublon. Vérifié en direct dans le navigateur (Compare Hops, Citra) :
tooltip myrcène et thiols corrects avec citation visible.

5 tests réécrits/ajoutés dans `test_matching.py` (résolution combinée
Flavornet+Janish, repli Janish seul sans CAS, absence totale sans aucune
des deux sources, thiols via Janish seul, dédoublonnage quand déjà couvert).
**Chaîne de test corrigée en cours de route (signalé par l'utilisateur en
direct)** : le premier jet utilisait `"herbal, minty"` comme donnée
Flavornet FACTICE pour tester le dédoublonnage -- l'utilisateur a
légitimement demandé si "minty" venait de l'image (non, jamais) ; remplacée
par `"FIXTURE-herbXX"`, délibérément imprononçable/non-anglais pour ne
jamais pouvoir être confondue avec une vraie donnée produit, même
principe que documenté ailleurs pour ne jamais laisser une valeur de test
ressembler à une donnée réelle. Suite pytest 214 -> 216.

**T74 — Annotation de survie au procédé par classe de composé (2026-08-21,
demande utilisateur explicite, spec complète fournie avec contrainte non
négociable).** "Un lecteur qui voit « myrcène 48 % » sur une fiche doit
savoir que ce chiffre compte en dry hop et devient largement caduc sur une
ébullition de 60 minutes." Contrainte non négociable respectée à la lettre :
AUCUNE valeur numérique, l'annotation est un badge texte purement affiché,
jamais consommée par un score (`matching.process_survival` est une lecture
pure sur `reference.PROCESS_SURVIVAL`, appelée uniquement depuis `app.py` --
vérifié directement, aucun appel depuis `molecular_scores`/`amplify`/
`contrast`/`by_descriptor`, et suite pytest complète inchangée avant/après).

Étape 0 respectée avant de coder : `SELECT DISTINCT compound, source FROM
hop_composition` sur la base réelle -- 11 composés d'huile essentielle
présents, tous mappés avec certitude (aucun laissé sans décision). α-pinène
et β-citronellol, cités par la figure Janish mais jamais mesurés par
BarthHaas/Yakima actuellement, n'ont PAS d'entrée (une annotation qui ne
s'afficherait jamais serait une entrée morte).

`reference.PROCESS_SURVIVAL` : structure {compound: {class, subclass,
annotation, confidence}}, à côté de `CONTRAST_AFFINITY`, avec le MÊME
avertissement de prior -- mais **deux niveaux de provenance distincts dans
la même structure**, documentés explicitement pour ne jamais les confondre :
la classification (class/subclass) est SOURCÉE (Scott Janish, The New IPA,
figure "Chemical compositions of the essential oils of hops" -- voir
docs/DATA_SOURCES.md pour la citation complète) ; l'annotation/confidence
est un PRIOR qualitatif de brassage (équipement/temps de contact/
température/levure font varier le taux réel), au même titre que
CONTRAST_AFFINITY -- listé dans README.md, section "Ce qui est un prior,
pas une donnée", SANS marquer la classification comme prior (elle, solide).

Mapping vérifié composé par composé (voir le commentaire complet dans
reference.py) : myrcene/beta-pinene -> Monoterpenes ("dry hop / late
additions", haute) ; humulene/caryophyllene/farnesene/selinene ->
Sesquiterpenes ("direct traces, contributes via oxidation" -- PAS un simple
"survit"/"ne survit pas" binaire, car les produits d'oxydation
(humulénol, farnésol) changent de classe, haute) ; linalool/geraniol ->
Monoterpene alcohols ("survives boiling", haute) ; ketones/isobutyrate ->
"Other (ketones, esters, aldehydes, epoxides)" ("intermediate transfer",
BASSE -- BarthHaas ne précise jamais quelle molécule précise compose cette
valeur agrégée, classées par nomenclature chimique directe -- "-ate"=ester,
"ketones"=nom littéral -- pas une supposition sur un nom approchant) ;
thiols -> "Thiols" (jamais "Sulfur compounds" générique -- la figure éclate
cette classe en thiols/sulfures/thioesters, BarthHaas ne mesure QUE les
thiols agrégés) ("late / dry hop", MOYENNE, via le composé 4-mercapto-4-
methylpentan-2-one/4MMP listé sous cette sous-classe -- déjà agrégé sous
"thiols" par `reference.ALIASES`).

`matching.process_survival(compound) -> dict | None` : lecture pure,
`None` si non mappé, jamais une valeur par défaut. GUI :
`app._process_survival_label` formate l'annotation + suffixe explicite
"(low confidence)" pour confidence="low" SEULEMENT (cohérent avec le
préfixe "Inferred:" déjà utilisé pour le purpose) -- confiance moyenne/
haute affichées sans suffixe, comme demandé. Colonne "Process" ajoutée aux
3 tableaux de composition texte (Browse, `_hop_detail_expanders`,
`_by_descriptor` -- même extension que T72 pour "Smells like", cohérence
avec le principe déjà établi "même contenu que Browse") et au tooltip/
couche rect du barplot "Detailed composition" de Compare Hops (même
mécanisme que "Smells like" T71, deux informations indépendantes ajoutées
côte à côte dans le même tooltip, jamais fusionnées). Composé sans
annotation -> "—", jamais "unknown"/placeholder.

**Corrigé en cours de route** : un premier jet de commentaire réutilisait
par erreur le raisonnement de T73 ("selinene absent du tableau du livre")
alors que CE tableau-ci (fourni directement dans le ticket, distinct de
l'image T73) liste explicitement sélinène sous Sesquiterpènes -- corrigé
dans le code ET le test correspondant (repris sur "limonene", vraiment
absent des données ET du tableau) avant tout commit.

6 tests ajoutés (`test_matching.py`) : complétude (chaque composé distinct
de hop_composition mappé ou exclu, échoue sur un composé nouveau non
décidé), exclusion des 4 champs non-arôme, `None` sur composé inconnu,
structure complète à 4 champs pour un composé mappé, suffixe confiance
basse, absence de toute valeur numérique dans TOUTE la structure (vérifié
programmatiquement, pas juste par relecture). Suite pytest 216 -> 222.
Vérifié en direct dans le navigateur (Browse/Admiral, Compare Hops/Citra) :
colonne "Process" et tooltip corrects, y compris le cas basse confiance
(isobutyrate : "intermediate transfer (low confidence)").

README.md et docs/DATA_SOURCES.md mis à jour (citation Janish complète,
distinction explicite entre les DEUX figures du même livre utilisées par
T73 et T74 -- jamais confondues).

**Addendum T74, même jour (2026-08-21, signalé par l'utilisateur en
direct) : légende de clarification pour les annotations "Process".** "I'm
not sure to understand the difference [between] 'direct traces, contribute
via oxydation' [and] 'survive boiling'." Distinction réelle (chimie déjà
résumée dans les notes du ticket original, mais pas assez explicite pour
un lecteur sans le contexte) : "survives boiling" (linalol/géraniol, déjà
oxygénés via un groupe -OH -- une part significative de LA MÊME molécule
persiste à travers l'ébullition) VS "direct traces, contributes via
oxidation" (humulène/caryophyllène/farnésène/sélinène, hydrocarbures --
une petite fraction survit telle quelle en traces directes, mais l'essentiel
de la contribution aromatique vient de ce que la molécule DEVIENT après
exposition à l'oxygène -- caryophyllène->oxyde de caryophyllène, humulène->
humulénol/époxyde d'humulène, farnésène->farnésol -- des composés
chimiquement DIFFÉRENTS, pas la même molécule qui "survit" partiellement).

`reference.PROCESS_SURVIVAL_EXPLANATIONS` (nouveau) : une phrase de
clarification par annotation DISTINCTE de `PROCESS_SURVIVAL` (5 entrées),
même statut de prior qualitatif que `PROCESS_SURVIVAL` lui-même --
COMPLÈTE les libellés courts existants (déjà validés T74) sans les
réécrire. `app._process_survival_legend()` : `st.expander("What do these
Process labels mean?")` replié par défaut, dérivé des annotations
RÉELLEMENT utilisées (jamais une entrée orpheline si `PROCESS_SURVIVAL`
change), affiché une fois sous le tableau de composition de Browse et une
fois sous le barplot "Detailed composition" de Compare Hops -- jamais
répété dans chaque expander de détail (bruit visuel inutile). 1 test
ajouté (complétude : chaque annotation utilisée a une explication).
Vérifié en direct dans le navigateur (Browse/Admiral) : légende correcte,
distinction claire entre les deux annotations. Suite pytest 222 -> 223.

**Second addendum T74, même jour (2026-08-21, signalé par l'utilisateur en
direct, sur l'explication ci-dessus) : erreur de sourcing corrigée avant
tout commit.** "In the 'direct traces, contributes via oxidation' you
describe it as any type of oxydation can make them appear. but in the
Scott's book he only mention LONG BOIL as an activator." La première
version de l'explication affirmait un déclencheur ("exposure to oxygen --
dry-hopping, packaging, aging") jamais donné par l'utilisateur -- une
inférence perso à partir de connaissances générales de brassage, PAS une
donnée sourcée (reconnu directement quand interrogé -- voir échange en
direct). Corrigé après clarification explicite : le déclencheur réel est
une ÉBULLITION LONGUE (>20 min), issu d'une étude d'extraction Saaz à temps
variable citée dans le livre -- ET cette étude précise ne couvre QUE
humulène et caryophyllène, PAS farnésène/sélinène (qui restent regroupés
sous la même annotation de CLASSE via la figure de taxonomie, une source
différente et plus générale, sans que le déclencheur précis leur soit
confirmé pour autant). "caryophyllene oxide"/"humulene epoxide" (noms de
produits d'oxydation inventés, jamais donnés) retirés -- seuls
"humulénol"/"farnésol" gardés, cités tels quels dans la spec originale du
ticket. Aucun changement de code hors le texte de `reference.
PROCESS_SURVIVAL_EXPLANATIONS["direct traces, contributes via oxidation"]`
-- vérifié en direct dans le navigateur, légende corrigée. Suite pytest
inchangée à 223 (aucun test ne verrouillait le contenu littéral de cette
phrase).

**Troisième addendum T74, même jour (2026-08-21, signalé par l'utilisateur
en direct) : libellé thiols reformulé, lisait comme un doublon.** "There is
a redundancy in the infobox of the Process. late / dry hop no longer exist
but is still present in the infobox." Vérifié en direct : PAS un bug de
duplication littérale -- `PROCESS_SURVIVAL["thiols"]["annotation"]` ("late /
dry hop") et `PROCESS_SURVIVAL["myrcene"/"beta-pinene"]["annotation"]`
("dry hop / late additions") étaient deux entrées BIEN distinctes avec des
explications différentes -- mais une simple PERMUTATION des mêmes mots,
qui se LIT comme un doublon accidentel dans la légende "What do these
Process labels mean?" une fois les deux entrées listées côte à côte.
Reformulé thiols en "extremely volatile — dry hop only" (même
recommandation pratique, mais formulation distincte reflétant la raison
chimique réellement différente : volatilité extrême + quantités traces
µg/kg, pas la simple perte par évaporation des hydrocarbures
monoterpéniques) -- explication correspondante mise à jour en cohérence.
Vérifié : aucun autre usage de la chaîne littérale "late / dry hop" dans le
code/tests (`grep` sur src/tests/docs/README), donc pas de test cassé.
Vérifié en direct dans le navigateur : les 5 entrées de la légende se
lisent maintenant comme 5 idées distinctes, plus de paire qui se ressemble.
Suite pytest inchangée à 223.

**T75 — Seuils `--oav` résolus en direct depuis FlavorDB2, plus de valeurs
codées en dur (2026-08-21/22, ticket "transparence de couverture sur
--oav").** Ticket initial : ajouter une métrique de couverture OAV (part du
score moléculaire couverte par des molécules à seuil sourcé) + avertissement
nommant les molécules non couvertes, sur le modèle exact de
`LOW_COVERAGE_WARNING_THRESHOLD`, avec pour prémisse que le myrcène n'avait
« aucun seuil retenu » dans `reference.MOLECULES`. **Investigation Step-0
(imposée par le ticket lui-même avant tout code) a révélé que cette prémisse
était fausse** : le myrcène avait bien un seuil codé en dur
(`threshold_ppb=13`) — et plus largement, `flavordb2_thresholds` (déjà
peuplée par `ingest.ingest_flavordb2`, 227 seuils réels) n'était **jamais
consultée par le scoring** : `molecular_scores` lisait uniquement
`reference.MOLECULES[...][1]`, 14 valeurs codées en dur en 2025, jamais
recroisées avec les seuils FlavorDB2 déjà en base. Signalé à l'utilisateur
avant toute modification (règle du ticket : « ne pas changer un seuil sans
le signaler explicitement — modifierait silencieusement le classement de
tous les résultats existants »). Question de l'utilisateur en retour :
« Wait, don't FlavorDB2 cover the OAV per molecules? Why is this hardcoded »
— recroisement direct effectué : **5 des 14 molécules ont un seuil
FlavorDB2 réel qui diverge silencieusement du seuil codé en dur**, le plus
net étant le géraniol (4 ppb codé en dur vs **39,5 ppb** en base, facteur
~10) ; aussi caryophyllène (64 vs 77,0), linalol (6 vs 7,0), bêta-pinène
(140 vs 140,0), citronellol (8 vs 11,0). Confirmé en direct par `curl` sur
les fiches FlavorDB2 réelles (`molecules_details?id=<cid>`, User-Agent
`hopmatch/0.1 (research)`) que myrcène/humulène/farnésène/limonène/
terpinolène/géranial n'ont réellement AUCUN seuil publié en base (pas un
problème de nommage/CID — vérifié en premier, comme demandé). Direction
utilisateur explicite (4 points) : (1) vérifier d'abord qu'il ne s'agit pas
d'un problème de correspondance CID/CAS pour les molécules manquantes —
fait, confirmé négatif ; (2) mettre à jour les seuils selon FlavorDB2 ; (3)
`None` plutôt que jamais retomber sur les anciens littéraux codés en dur
quand un seuil est absent ; (4) rendre visible en GUI la source des seuils
OAV. Implémenté : `reference.MOLECULES` — tous les `threshold_ppb` mis à
`None` (le tuple garde sa forme à 3 éléments, l'index CID reste utilisé par
`compound_descriptors`, T71) ; nouvelle `matching.oav_thresholds(con,
molecules)` résout CHAQUE seuil en direct via la chaîne CID
`reference.MOLECULES` → CAS `pubchem_cids` → seuil `flavordb2_thresholds`,
molécule absente de cette chaîne → absente du dict retourné (jamais un seuil
deviné) ; `molecular_scores` prend désormais `thresholds: dict|None` (plus
`mols`) et lit `thresholds.get(m)` au lieu de
`mols.get(hop_compound(m), {}).get("threshold_ppb")` ; nouvelle
`matching.oav_coverage(note_profile, comp, thresholds)` (fraction du poids
moléculaire couvert par un seuil sourcé + liste triée des molécules non
couvertes, calculée SEULEMENT si `use_oav=True`, sinon `(None, [])`) ;
nouvelle constante `OAV_LOW_COVERAGE_WARNING_THRESHOLD = 0.80` (dérivée
empiriquement, comme `LOW_COVERAGE_WARNING_THRESHOLD` T69 : médiane 100 %,
moyenne 91 % de couverture OAV mesurées sur les 258 notes réelles à
molécules productibles, 0,80 signale 50/258 = 19 % des notes) ; `amplify`
calcule `oav_thr`/`oav_cov`/`oav_uncovered` et les expose dans son dict de
retour (`oav_coverage`, `oav_uncovered`). Avertissement câblé sur le même
modèle que `LOW_COVERAGE_WARNING_THRESHOLD` (T69) : ligne `ATTENTION` en CLI
(`cli.py::_print_amplify`) et `st.warning` en GUI, tous deux nommant
explicitement les molécules non couvertes (pas juste un pourcentage) ; GUI
ajoute aussi un `st.caption` discret (visible dès que `--oav` est actif, pas
seulement sous le seuil d'alerte) expliquant d'où vient chaque seuil ; aide
de la case à cocher `--oav` réécrite pour dire explicitement « résolu en
direct depuis FlavorDB2, jamais codé en dur ». Documentation : entrée
myrcène ajoutée à `docs/DATA_SOURCES.md` (texte du ticket, verbatim) +
paragraphe sur l'historique des 5 divergences détectées ; README section
`--oav` étendue (sourcing + couverture). **4 tests requis par le ticket,
tous ajoutés** (`tests/test_matching.py`, suffixe `_oav`/`molecular_scores_
neutral`) : couverture 100 % quand tout est sourcé ; couverture < 100 % +
molécule non couverte correctement listée + sous le seuil d'alerte ; qu'un
seuil jamais inventé n'entre dans le calcul (un seuil encore présent dans
`reference.MOLECULES` via `monkeypatch` — cas de régression hypothétique —
n'est PAS lu, seule la chaîne FlavorDB2 compte) ; qu'un score sans
`--oav` est identique avec ou sans données FlavorDB2 insérées. Plus :
résolution CID→CAS→seuil testée directement, et neutralité stricte (1×,
égalité exacte avec `use_oav=False`) pour une molécule sans seuil. Fixture
`db` (`tests/test_matching.py`) ayant `pubchem_cids`/`flavordb2_thresholds`
vides par défaut (comme pour `compound_descriptors`, T71/T73) : lignes
insérées/retirées par test (`try`/`finally DELETE`), même pattern déjà
établi. `load()` conserve son tuple à 4 éléments (`mols` toujours renvoyé,
13 des 14 sites d'appel le jettent déjà via `_` avant ce ticket) : changer sa
signature était hors scope, aucun bénéfice fonctionnel, aurait touché 13
sites d'appel pour rien. Suite complète : 224 → **231 tests, tous verts** ;
`pyflakes` propre sur `matching.py`/`reference.py`/`app.py`/`cli.py`/
`tests/test_matching.py`.

**T76 — Explication TF-IDF/--oav dans la GUI Amplify + défaut --oav
piloté par la couverture réelle par note (2026-08-22, suite directe de T75,
demande utilisateur explicite).** Déclenché par une confusion légitime en
testant T75 en direct : couverture --oav à 100% sur "mango" alors que
l'utilisateur s'attendait à "plus de 10 molécules" — investigation en
direct qui a révélé que ce n'était PAS un bug mais le fonctionnement normal
de `coverage()` (seules ~14 molécules curées ont des données `hop_
composition` quantitatives, indépendamment de --oav, déjà documenté T69).
L'utilisateur a ensuite demandé une explication précise du mécanisme
moléculaire, puis un infobox GUI clair pour ça, à partir d'un brouillon
qu'il a fourni.

**Infobox `_molecular_score_explainer()`** (`st.expander` replié par défaut,
même principe que `_process_survival_legend` T74, affiché en haut de la
page Amplify) : analogie recherche documentaire (houblon=document,
molécule=mot, myrcène="le"/"a"), formule `contribution = note_weight × TF ×
IDF × OAV` avec les 4 facteurs expliqués séparément, section "ce que --oav
fait/ne fait pas" (ne filtre JAMAIS, direction inversée seuil bas =
multiplicateur haut), et un exemple chiffré pas-à-pas. Brouillon utilisateur
adapté avec **deux corrections factuelles vérifiées avant publication**
(jamais republié tel quel) : (1) le brouillon citait "thiols, cétones,
isobutyrate" comme groupe touché par le biais de neutralité --oav ;
vérifié dans `reference.py` : seuls les thiols sont dans `reference.
MOLECULES` (CID=None -> jamais de seuil --oav) -- "ketones"/"isobutyrate"
n'existent que côté `PROCESS_SURVIVAL`/`JANISH_COMPOUND_CATEGORIES` (badge
Process, T74), hors du scoring moléculaire/--oav -- affirmation corrigée
pour ne citer QUE les thiols ; (2) l'exemple chiffré du brouillon affirmait
que l'écart entre deux houblons fictifs "se resserre" avec --oav (1,20×
cité comme le cas AVEC --oav contre 1,44× SANS) ; recalculé à la main ET
par script (`amount`/`specificity` réels appliqués aux mêmes chiffres) :
c'est l'inverse -- SANS --oav le ratio est 1,20 (B atteint 83,4% de A),
AVEC --oav il est 1,44 (B tombe à 69,7%) -- l'écart s'ÉLARGIT ici, pas
l'inverse (le β-pinène, seul vrai atout du houblon B, est justement la
molécule la plus pénalisée par --oav). Narration corrigée en conséquence ;
le reste de l'arithmétique du brouillon (TF/IDF/multiplicateurs/totaux)
était juste, revérifié terme à terme avant publication. Exemple clairement
labellé "hypothetical numbers, not real hop data" -- cohérent avec la
convention "prior, pas donnée" déjà établie (README).

**Défaut `--oav` piloté par note.** La case `--oav` passait de `value=True`
fixe pour toute note à une valeur calculée AVANT son rendu : `default_oav =
bool(producible) and oav_coverage(note) >= OAV_LOW_COVERAGE_WARNING_
THRESHOLD` (0.80, seuil T75 déjà établi) -- répond littéralement à la
demande utilisateur ("automatically triggers the OAV if we have enough OAV
coverage (and if molecular layer is activated for sure)"), le garde
`bool(producible)` couvrant la clause "si la couche moléculaire est
activée". `key=f"use_oav_{note}"` (pas de clé fixe) : un widget Streamlit
distinct par note plutôt qu'un seul état partagé -- changer de note
recalcule un nouveau défaut informé par CETTE note, tout en gardant en
mémoire (session_state) un override manuel si l'utilisateur revient sur une
note déjà visitée dans la session. Vérifié en direct dans le navigateur :
"adobo" (0 molécule productible) -> case décochée par défaut ; "mango"
(2 molécules productibles, toutes deux avec un seuil FlavorDB2 sourcé,
couverture 100%) -> case cochée par défaut.

**Étude empirique de couverture sur les additions RÉELLEMENT courantes en
brassage** (demande utilisateur explicite : "study the distribution of
molecular coverage in a list of addition used frequently in beers... not
all the database because a lot of ingredients are never seen in a beer").
44 notes choisies à la main (fruits/agrumes/herbes/épices usuels en
IPA/sour/stout -- mangue, fraise, myrtille, cassis, groseille, cerise
acide, orange, pêche, abricot, ananas, fruit de la passion, pamplemousse,
citron, citron vert, menthes, coriandre, vanille, coco, chocolat, café,
piment, gingembre, cannelle, girofle, muscade, pastèque, goyave, kiwi,
pomme, poire, grenade, raisin, banane, groseille à maquereau, romarin,
thym, cardamome, anis (+étoilé), basilic, fenouil, tamarin -- recoupées
contre les 506 notes réelles de la base, `difflib.get_close_matches` pour
les libellés proches, ex. "highbush blueberry"/"blackcurrant"/"sour
cherry"). Résultat surprenant à signaler explicitement à l'utilisateur :
couverture MOLÉCULAIRE médiane 4,2% (moyenne 5,0%), maximum 12,4% (anis
étoilé) sur ces 44 notes -- jamais proche des 20% de `LOW_COVERAGE_
WARNING_THRESHOLD` (déjà établi comme "faible" sur toute la base, T69) ;
3 notes à 0% exactement (chocolat, café, piment -- ZÉRO molécule
productible, `amplify` sans descripteurs y renvoie une liste vide). Couverture
--oav (sur les 41 notes à ≥1 molécule productible) très différente :
médiane 81,5%, moyenne 81,5%, mais 19 notes sur 41 (46%) sous le seuil de
0.80 -- une proportion de notes flaggées PLUS élevée que sur toute la base
(19% en T75) : les additions courantes en brassage tirent davantage sur
myrcène/humulène/farnésène (non sourcés) que la moyenne des 506 notes.
Donnée brute conservée dans l'historique de conversation, pas dans un
fichier séparé (pas de script d'étude committé -- calcul ponctuel, pas un
besoin récurrent).

**Signalé à l'utilisateur, PAS implémenté (2e moitié de la demande, en
attente de confirmation) :** "automatically triggers the molecular layer if
we have enough coverage" ne peut PAS se lire littéralement contre ces
chiffres -- avec un maximum réel de 12,4% sur des additions à brassage
réellement courantes, n'importe quel seuil "suffisant" défendable
laisserait la couche moléculaire éteinte pour la quasi-totalité des cas
d'usage réels de l'outil, ce qui viderait `amplify` de son intérêt.
Contrairement au défaut --oav (une simple valeur de case à cocher,
réversible), un gate dur sur la couche moléculaire changerait le
CLASSEMENT/la disponibilité même des résultats -- décision de scoring, pas
d'ergonomie, donc pas prise sans confirmation explicite (même règle que
T75 : "ne pas changer silencieusement un classement"). Deux lectures
possibles proposées à l'utilisateur, réponse en attente au moment de cette
entrée.

**Suite T76 (même jour, 2026-08-22) — reframe complet d'Amplify : descripteurs
en couche principale, moléculaire optionnel, amorce IA ingrédient->descripteurs
(506 entrées).** Réponse utilisateur à la question ci-dessus ("Deux lectures
possibles... réponse en attente") : ni l'une ni l'autre -- direction complètement
différente. Demande verbatim : "I want you to put as a first layer the
descriptors and as an optional layer the molecular... Once user put the
ingredient, will automatically select the Note descriptors matching this
ingredient... I need you to build a dictionary or mapping between each
ingredient in fooddb and possible note descriptor mapping this. For this
mapping I want you to use IA for sure."

Implémenté (`app._amplify`) :
- **"Note" renommé "Ingredient"** en GUI (label + aide) -- interne (`note`,
  `aroma_notes`, CLI `hopmatch amplify <note>`) inchangé, portée = label GUI
  uniquement (même principe que la convention anglais/français déjà établie).
- **Couche descripteurs = couche principale**, pré-remplie automatiquement à
  la sélection d'un ingrédient depuis `reference.INGREDIENT_DESCRIPTORS`
  (nouveau dict, voir ci-dessous), toujours éditable (`st.multiselect`
  `default=`, `key=f"desc_{note}"` -- un widget par ingrédient, mémorise un
  override manuel si retour sur un ingrédient déjà visité dans la session).
  Caption explicite selon le cas ("Prefilled from X's typical aroma
  (AI-assisted suggestion, not measured data)..." ou "No auto-suggested
  descriptors for X yet...").
- **Couche moléculaire = case à cocher optionnelle** ("Also use molecular
  similarity (optional)"), décochée par défaut (`key=f"use_mol_{note}"`) --
  l'infobox TF-IDF (`_molecular_score_explainer`, T76 précédent same-day) et
  la case `--oav` ne s'affichent que si cochée.
- **`w_mol`/`w_desc` pilotés explicitement par ce choix** plutôt que par le
  repli implicite `has_descriptors` de `matching.amplify` : moléculaire
  décoché -> `(0.0, 1.0)` ; coché -> `(0.5, 0.5)` (le repli interne `has_
  descriptors` de `matching.amplify` continue de s'appliquer PAR-DESSUS dans
  le seul cas moléculaire coché + aucun descripteur -> `(1.0, 0.0)`,
  inchangé). Cas "aucun descripteur ET moléculaire décoché" intercepté AVANT
  l'appel à `matching.amplify` (message explicite "nothing to rank") --
  sinon le repli interne de `matching.amplify` retomberait silencieusement
  sur 100% moléculaire malgré un choix utilisateur explicite contraire.
- **Avertissement de couverture moléculaire recalibré** (demande utilisateur
  explicite : "recalibrate the warning message based on the true
  distribution 4-12 that you can describe at the top of the molecular
  box") -- l'ancien `st.warning` à `LOW_COVERAGE_WARNING_THRESHOLD`=20% se
  déclenchait pour LITTÉRALEMENT toutes les notes de toute la base
  (`coverage()` ne dépasse jamais ~12%, y compris sur les 44 ingrédients
  réellement courants en brassage étudiés plus haut) : un "avertissement"
  qui ne varie jamais n'avertit de rien. Remplacé par (1) un `st.caption`
  factuel systématique en haut de la section moléculaire donnant la vraie
  plage mesurée (4-12%, 44 ingrédients réels), et (2) un `st.warning` RECENTRÉ
  sur le vrai cas dégénéré (`len(producible) <= 1` -- le cas géraniol/
  Talus/Ekuanot documenté en T69, PAS un seuil de pourcentage).

**`reference.INGREDIENT_DESCRIPTORS`** (nouveau dict, 506 entrées -- une par
note réelle de `aroma_notes`) : amorce de pré-remplissage, jugement direct de
l'assistant (PAS une dérivation programmatique FooDB, cette approche avait déjà
dégénéré -- voir `combine()`/`LOW_COVERAGE_WARNING_THRESHOLD`), vocabulaire de
sortie restreint aux 105 descripteurs RÉELS de `hop_descriptors` (jamais un
terme inventé), liste vide = pas de correspondance défendable (361/506, 71% --
la majorité des notes FooDB sont poissons/viandes/plats préparés sans rapport
avec le houblon), 145/506 non vides. Choix méthodologiques utilisateur
explicites (`AskUserQuestion`, répondu) : (1) amorce statique rédigée par
l'assistant dans cette session, PAS un appel API LLM en direct dans l'app
(pas de secret/dépendance réseau nouvelle) ; (2) les 506 notes couvertes, mais
seules les 44 de l'étude de couverture --oav (T76 précédent) effectivement
revues à la main par l'utilisateur. Garde-fou permanent ajouté :
`test_ingredient_descriptors_keys_and_terms_match_real_vocabulary`
(`tests/test_matching.py`) -- vérifie contre la vraie base (`aromahops.db`,
pas la fixture) que les 506 clés correspondent EXACTEMENT aux notes réelles et
que chaque terme appartient au vocabulaire réel.

**Corrections post-revue utilisateur (même jour) :** deux incohérences
signalées après un premier passage en revue des 44 ingrédients curés :
(i) "berry" absent de plusieurs baies réelles (myrtille, cassis, groseille,
fraise, sureau...) alors que présent sur d'autres (canneberge, airelle) ;
(ii) "fruity" présent sur mangue mais absent d'autres fruits tout aussi
fruités (goyave, banane, ananas, papaye...). Cause : incohérence
d'application de la règle par le premier passage (44 entrées rédigées à la
main) ET par la passe automatisée (462 entrées). Corrigé PROGRAMMATIQUEMENT
(pas une réécriture manuelle de 506 lignes, source d'erreur) : script
détectant tout terme de "signal" fruit/baie déjà présent (ex. "guava",
"blueberry") sans que "fruity"/"berry" l'accompagne, exclusion explicite des
faux positifs revue à la main (coriandre/gin/mélisse citronnée/citronnelle/
menthe orange -- caractère herbacé/citronné réel, mais PAS des fruits,
"fruity" y aurait été une surinterprétation), 40 entrées corrigées, aucune
ne dépasse le plafond de 4 termes (`strawberry guava` : "tropical" retiré
pour faire de la place à "berry"+"fruity", les deux plus informatifs ici).
Revalidé par le même script de garde-fou + `pytest` (232 verts) + `pyflakes`
propre après correction.

**Incident opérationnel (à ne pas reproduire) : un fork a exécuté `git
stash` sur le dépôt PARTAGÉ pendant que la session principale éditait
activement les mêmes fichiers.** Chargé d'étendre `INGREDIENT_DESCRIPTORS`
aux 506 notes (tâche déléguée en fork pour ne pas remplir le contexte
principal de 462 entrées mécaniques), le fork a lancé `git stash` de sa
propre initiative (jamais demandé) pour une vérification annexe -- capturant
TOUT le travail non committé de la session (T75 + T76 en cours), y compris
des fichiers que la session principale modifiait EN PARALLÈLE au même
moment (`tests/test_app.py`). Le `git stash pop` a échoué (conflit), le fork
a alors tenté une récupération manuelle (`git checkout stash@{0} -- <path>`
fichier par fichier + un merge 3-way `git merge-file` pour le fichier en
conflit) -- travail interrompu (`TaskStop`) en cours de vérification finale
avant que le stash ne soit droppé. **Rien n'a été perdu** (le stash est resté
intact tout du long, jamais droppé) mais l'incident a fait disparaître
temporairement le contenu de 9 fichiers de la copie de travail, détecté par
des `grep`/`wc -l` qui ne retrouvaient plus de contenu pourtant écrit avec
succès quelques échanges plus tôt. Récupération complète vérifiée après coup
(diff fichier par fichier contre le stash : 8/9 fichiers identiques
byte-à-byte, `tests/test_app.py` correctement fusionné par le fork --
confirmé en relisant le fichier directement, pas en faisant confiance au
rapport du fork) ; `git restore --staged .` pour désindexer (le fork avait
laissé 8 fichiers en zone de stage) sans toucher au contenu ; suite complète
`pytest`/`pyflakes` revérifiée verte après coup. Stash `stash@{0}` conservé
intentionnellement (filet de sécurité redondant mais gratuit) plutôt que
droppé sans qu'on le demande. **Leçon retenue (voir aussi la mémoire
cross-session correspondante) : ne jamais déléguer une tâche en fork NON
ISOLÉ (`isolation` omis) si cette tâche pourrait toucher au dépôt git
partagé (`git stash`/`git checkout`/etc.) alors que la session principale
édite activement des fichiers en parallèle -- soit interdire explicitement
toute commande git dans le prompt du fork, soit lancer le fork avec
`isolation: "worktree"` s'il a réellement besoin de git.**

**Addendum T76, même jour (2026-08-22, 4 retours utilisateur avant commit) :**
1. **Avertissement "Orphans" déplacé DANS `if use_molecular:`** -- purement
   moléculaire (`coverage()` : molécules de la note qu'aucun houblon ne
   produit), sans rapport avec la couche descripteurs, s'affichait avant même
   case décochée.
2. **Infobox TF-IDF (`_molecular_score_explainer`) + caption "For
   reference"(plage 4-12%) sorties de `if use_molecular:`, affichées
   INCONDITIONNELLEMENT.** Signalé par l'utilisateur : "user should be
   informed before taking the decision to activate it or not" -- l'ancien
   emplacement les rendait invisibles tant que la case n'était pas DÉJÀ
   cochée, à l'envers de leur rôle (aider à décider si l'activer).
3. **Colonne "Mol." du tableau de résultats masquée si `use_molecular` est
   décoché** -- `w_mol=0` dans ce cas, la valeur affichée ne contribue à rien
   au score, la montrer aurait laissé croire le contraire.
4. **Amorce `INGREDIENT_DESCRIPTORS` déployée sur `contrast`** (jusque-là
   Amplify seul) : nouveau sélecteur "Ingredient (optional)" en tête de
   `_contrast`, `index=None`/`placeholder` (rien de sélectionné par défaut,
   contrairement à Amplify où un ingrédient est obligatoire -- `contrast` n'a
   jamais eu besoin d'un ingrédient précis, juste de descripteurs). Préremplit
   `st.multiselect` en dessous (même pattern -- caption explicite, `key=
   f"contrast_desc_{ingredient}"` pour la mémoire par ingrédient), en
   AMONT de la logique de cible de contraste existante (T61/T-tropical) qui
   continue de fonctionner à l'identique une fois les descripteurs remplis
   (peu importe qu'ils viennent de l'amorce ou d'une saisie manuelle).

**Point signalé à l'utilisateur, PAS corrigé (hors des 4 demandes
explicites) :** la colonne "Contributes via" (`why_str`, alimentée par les
contributeurs moléculaires `mol.get(h, (0,[]))[1]`) continue d'afficher des
noms de molécules même `use_molecular` décoché, alors qu'elles ne pèsent plus
RIEN dans le score (`w_mol=0`) -- `matching.molecular_scores` reste calculé
inconditionnellement dans `matching.amplify` (jamais gaté par `w_mol`), donc
"why" est toujours peuplé. Potentiellement trompeur (donne l'impression que
ces molécules ont influencé le classement), mais pas demandé explicitement :
laissé tel quel, signalé pour confirmation avant d'y toucher (même règle que
pour l'auto-trigger moléculaire T75/T76 : pas de changement de ce qui
s'affiche comme "cause" du score sans confirmation).

**2e addendum T76, même jour (2026-08-22) : le point signalé ci-dessus était
en fait la vraie demande.** Réponse utilisateur : "we are missing the
descriptor contribution... create two distinctive columns 'Molecular
contributors' and 'Descriptor contributors'... activate the columns only if
the respective scores are activated." Implémenté (`app._amplify`) :
- **"Contributes via" scindée en deux colonnes** : "Molecular contributors"
  (`h["why"]`, inchangé) et "Descriptor contributors" (NOUVEAU -- calculé en
  app.py, PAS dans matching.py : simple recoupement d'ensembles déjà chargés,
  `set(selected_desc) & hop_desc.get(variety, set())`, pas une nouvelle
  notion de score). "Activées" = pèsent RÉELLEMENT dans le score final, pas
  juste "cochées" : `show_desc_col = r["has_descriptors"] and w_desc > 0` --
  le `w_desc > 0` en plus de `has_descriptors` couvre le nouveau cas
  "Use only the molecular layer" ci-dessous (descripteurs sélectionnés,
  `has_descriptors=True`, mais explicitement mis à `w_desc=0`). Colonne
  "Desc." (fraction numérique) soumise à la même règle, par cohérence avec
  "Mol." déjà masquée au tour précédent. Caption des `_hop_detail_expanders`
  mise à jour en cohérence (`_contrib_caption` : "via molecular: ...;
  descriptors: ..." selon ce qui est effectivement actif).
- **Nouvelle case "Use only the molecular layer (ignore descriptors)"**
  (demande utilisateur explicite, proposition d'emplacement suivie
  littéralement : "just below 'Also use molecular similarity'"), visible
  seulement si la couche moléculaire est cochée. `w_mol`/`w_desc` : `(0,1)`
  si moléculaire décoché ; `(1,0)` si "molecular only" coché ; `(0.5,0.5)`
  sinon (repli `has_descriptors` de `matching.amplify` inchangé,
  s'applique par-dessus si la sélection de descripteurs est vide).
  Différent de vider manuellement le multiselect de descripteurs : préserve
  la sélection/l'amorce pour un retour ultérieur au blend plutôt que de la
  perdre. Vérifié en direct dans le navigateur : mango, moléculaire+descripteurs
  actifs -> 6 colonnes (Mol., Desc., Molecular contributors, Descriptor
  contributors inclus) ; "Use only the molecular layer" coché -> "Desc." et
  "Descriptor contributors" disparaissent, score de Talus repasse à 100
  (recalculé purement sur geraniol/beta-pinene).

**3e addendum T76, même jour (2026-08-22) : les 2 cases moléculaires
remplacées par UN `st.segmented_control` à 3 états.** L'utilisateur, après
avoir vu le rendu du 2e addendum, a demandé un avis ergonomique ("Do you
think it's ergonomic this way?"). Diagnostic donné puis confirmé par
l'utilisateur : "Also use molecular similarity" + sa sous-case "Use only the
molecular layer" (qui n'apparaissait QUE si la première était cochée)
encodaient en réalité 3 états mutuellement exclusifs via deux booléens
dépendants -- pattern peu lisible ("case qui n'apparaît que si une autre
case précise est cochée"), signalé par l'utilisateur lui-même dans un
message suivant ("I have the feeling these two buttons are not super
clear/ergonomic"). Remplacé par `st.segmented_control("How to rank hops?",
["Descriptors", "Both", "Molecular only"], default="Descriptors",
required=True)` -- correspond 1:1 aux 3 seules combinaisons `w_mol`/`w_desc`
réellement utilisées (0/1, 0.5/0.5, 1/0), conforme à la convention Streamlit
du projet (segmented_control préféré à une case/un radio pour ce genre de
choix, voir la skill `developing-with-streamlit`). `required=True` : jamais
de désélection vers `None`, un état est toujours actif. `use_molecular =
rank_mode in ("Both", "Molecular only")` / `molecular_only = rank_mode ==
"Molecular only"` dérivés directement, tout le reste de la logique en aval
(w_mol/w_desc, gating des colonnes/warnings/--oav/explainer) inchangé --
seul le CONTRÔLE d'entrée a changé, pas le comportement. `tests/test_app.py`
: les 6 tests qui activaient la couche moléculaire via `at.checkbox[0].
set_value(True)` mis à jour vers `at.segmented_control[0].set_value("Both")`
(API AppTest confirmée par lecture directe de `streamlit.testing.v1.
element_tree.ButtonGroup`, commune à `st.pills`/`st.segmented_control`).
Vérifié en direct dans le navigateur : "Descriptors" sélectionné par
défaut (surlignage rouge) ; clic sur "Both" fait apparaître `--oav` +
"Molecular coverage" à l'identique du comportement précédent.

## T77 -- Provenance PAR DESCRIPTEUR séparée de la provenance de composition
(2026-08-22, confusion réelle signalée en direct par l'utilisateur)

Signalé par l'utilisateur en testant By-descriptor sur "berry"/"raspberry" en
production : Enigma ressort #1, colonne "Sources" affiche "barthhaas" --
l'utilisateur visite la vraie page BarthHaas d'Enigma, n'y voit AUCUN de ces
deux mots ("Passion Fruit, Nutmeg, Lime, Pineapple, Red Currant" listés à la
place), légitimement confus ("does berry come from this only?").

**Root cause vérifiée en direct sur la base construite** (pas supposée) :
`hop_descriptors` d'Enigma a 6 lignes, **TOUTES sourcées "beermaverick"**
(berry, raspberry, redcurrant, stone fruit, tropical, white wine) -- ZÉRO
venant de BarthHaas (dont les descripteurs d'arôme sont un site parsé comme
`[]`, jamais fiable, voir `docs/DATA_SOURCES.md`) et ZÉRO de Yakima (`hops.
sources = "barthhaas"` seul pour Enigma -- confirmé, Yakima ne couvre pas
cette variété). La colonne "Sources" des tableaux de résultats
(`hops[h]["sources"]`) n'a JAMAIS reflété que la provenance de la
COMPOSITION -- `hop_desc` (`matching.load()`) est un simple `set[str]` de
NOMS de descripteurs, le `source` de chaque ligne `hop_descriptors` n'était
JAMAIS conservé nulle part en aval du chargement. La juxtaposition visuelle
("Sources: barthhaas" affiché juste à côté/au-dessus des descripteurs
matchés) laissait raisonnablement croire à l'utilisateur que cette
provenance couvrait aussi les descripteurs -- confusion légitime, pas une
erreur de lecture de sa part.

**Fix : nouvelle `matching.descriptor_sources(con) -> {variety: {descripteur:
{sources}}}`**, fonction séparée plutôt qu'un enrichissement de `hop_desc`
dans `load()` (`hop_desc` reste un `set[str]` utilisé pour des opérations
d'ensemble -- `&`, `descriptor_overlap` -- dans de nombreux appelants,
changer sa forme aurait cassé ce pattern partout ; ce besoin de provenance
est localisé à l'AFFICHAGE, pas au scoring). Déployé partout où la
juxtaposition composition/descripteurs existait :
- **Amplify** (`_amplify`) : nouvelle colonne "Descriptor sources" (montrée
  seulement si `show_desc_col`, même garde que "Descriptor contributors"),
  "Sources" renommée "Composition sources".
- **Contrast** (`_contrast`) : même split sur `h["contrast_via"]`.
- **Blends** (`_render_blends`, partagé amplify_blend/contrast_blend) : même
  split sur `h["covers"]` -- signature étendue d'un paramètre `desc_src`
  (les deux appelants l'avaient déjà calculé pour leur propre tableau).
- **By-descriptor** (`_by_descriptor`) : l'en-tête d'expander perdait son
  `[{h['sources']}]` trompeur (juxtaposé à "matches berry, raspberry") --
  remplacé par une caption explicite "Matched descriptors sourced from: X —
  composition sourced from: Y" ; "All descriptors" annote CHAQUE terme
  individuellement (`d (source)`).
- **`_hop_detail_expanders`** (partagé Amplify/Contrast) et **Browse**
  (`_browse`, page hop unique) : même annotation par terme sur la liste
  "Descriptors" complète, groupée par source ; caption renommée "Composition
  sources".
- **PAS touché** : `_similar_hops_section` (Browse, "Similar hops") -- ses
  "Shared aroma categories" viennent de `hop_aroma_intensity` (roue
  quantitative, Yakima UNIQUEMENT par construction, jamais BeerMaverick/
  BarthHaas) -- pas le même risque de confusion, une colonne "Descriptor
  sources" y serait redondante (toujours "yakima"). `_compare` (Compare
  Hops) : ne montre ni `hop_descriptors` ni "Sources" du tout, hors périmètre.

Nouveau test `test_descriptor_sources_groups_by_variety_and_descriptor`
(`tests/test_matching.py`) : vérifié sur un vrai cas multi-source de la
fixture (`citra`/`citrus` a RÉELLEMENT deux sources, barthhaas ET yakima,
confirmé en direct sur la base construite -- pas fabriqué pour le test).
Suite complète : 232 -> **233 tests, tous verts** ; `pyflakes` propre.
Vérifié en direct dans le navigateur, reproduction EXACTE du signalement
utilisateur : By-descriptor, "berry"+"raspberry", expander Enigma ouvert ->
"Matched descriptors sourced from: beermaverick — composition sourced
from: barthhaas" ; "All descriptors: berry (beermaverick), raspberry
(beermaverick), redcurrant (beermaverick)..." -- répond directement à la
question posée ("does berry come from this only?" -- oui, de BeerMaverick,
jamais de BarthHaas). Amplify sur "mango" : colonnes "Descriptor sources"
(beermaverick, yakima) et "Composition sources" (barthhaas/yakima selon le
houblon) désormais visibles séparément.

## T78 -- Logo HopFinder (2026-08-22, image fournie par l'utilisateur)

`assets/logo.png` (fond crème opaque, 1772×694, uploadé par l'utilisateur --
confirmé après coup que le fichier inconnu repéré plus tôt dans `git status`
n'était PAS lié à un incident, juste l'utilisateur ajoutant son propre
asset). Fond retiré par script one-off (seuillage de distance couleur au
référentiel des 4 coins + feather linéaire 15-40 pour un bord anti-aliasé,
PAS un cutout brutal) : vérifié en direct que le fond crème plein cadre
aurait rendu comme un bloc clair disgracieux sur le thème sombre par défaut
de l'app -- comparé sur fond sombre ET clair avant de valider. Recadré au
bbox du contenu (+12px de marge) -> `assets/logo_transparent.png`
(1512×560). Original (`assets/logo.png`) conservé tel quel, jamais modifié
ni supprimé.

Intégré :
- **GUI** (`app.main`) : `st.logo(_LOGO_PATH, size="large")`, apparaît en
  haut de la sidebar sur toutes les pages (mécanisme natif Streamlit dédié
  à cet usage, pas un `st.image` mal placé) -- chemin résolu depuis
  `__file__` (même pattern que `_BACKGROUND_PATH`), correct quel que soit
  le cwd d'où `streamlit run` est lancé.
- **GitHub** (`README.md`) : image centrée en tête de fichier (remplace le
  titre texte `# HopFinder` -- pattern standard des README GitHub avec
  logo), même asset transparent (rend correctement sur GitHub en thème
  clair ET sombre, vérifié via les mêmes previews composite).

Favicon (`page_icon`) laissé à l'emoji `🌿` existant -- pas demandé
explicitement, et le logo (lockup horizontal large) n'a pas de recadrage
carré propre pour cet usage (la poignée de la loupe traverse la zone
texte) ; à reconsidérer si un jour une variante icône seule est fournie.
Vérifié en direct dans le navigateur : logo lisible en haut de la sidebar,
transparence propre sur le thème sombre par défaut.

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
- **Exception (2026-08-19, décision utilisateur explicite, scope confirmé) : le texte
  UTILISATEUR de la GUI (`app.py` — labels, captions, warnings, badges, tout ce qui
  s'affiche dans Streamlit) est en ANGLAIS**, pas en français. Ne s'applique QU'à `app.py` :
  `cli.py` (sorties `print`) et les commentaires/docstrings de tout le projet, y compris
  dans `app.py` lui-même, restent en français comme le reste du projet. Avant cette date,
  toute la GUI était en français — ne pas revenir en arrière sans redemander.
- Ne jamais fabriquer de données houblon en dur : passer par un parseur + source tracée.
- `pytest` doit rester vert. Ajouter un test quand on touche un solveur ou un parseur.
- Commandes : `pip install -e ".[dev]"` ; `pytest -q` ; `hopmatch build` (démo, 4 houblons,
  0 note — `build` ne seed plus de note, seul `ingest-foodb` en crée) puis `hopmatch
  ingest-flavornet` puis `hopmatch ingest-foodb` (télécharge le dump si besoin) avant de
  pouvoir utiliser `hopmatch amplify|contrast <note>` ; `hopmatch by-descriptor
  <descripteurs>` ne dépend d'aucune note et fonctionne dès `build`.
- **`app._RECENT_UPDATES` (T69, liste "Recent updates" en bas de la page d'accueil) doit
  être mise à jour DANS LE MÊME COMMIT que tout changement utilisateur visible de la GUI**
  (décision utilisateur explicite, 2026-08-21, après un oubli réel : le commit `995e83d`
  -- bascule relatif/absolu du barplot Compare Hops -- avait été poussé sans nouvelle
  entrée, "why this commit don't display a new feature update in the main page"). C'est
  une liste STATIQUE curée à la main (voir sa section pour le pourquoi : pas de lecture
  `git log` en direct, messages de commit en français incompatibles avec le texte GUI
  anglais) -- rien ne la met à jour automatiquement, donc AVANT de committer un changement
  visible dans `app.py` (nouvel outil, nouvelle section, changement de comportement
  perceptible), ajouter une entrée en tête de `_RECENT_UPDATES` (date du jour, résumé en
  anglais, une phrase) fait partie du changement lui-même, pas une étape à part qu'on peut
  oublier. Ne s'applique qu'aux changements GUI VISIBLES par l'utilisateur final (pas les
  changements internes purs -- refactor, tests, corrections de commentaires, CLI seul).
