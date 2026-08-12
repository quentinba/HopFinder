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
- **Option `--biotransform` : portée étroite et sourcée, généralisée par espèce de levure
  (pas par souche commerciale individuelle).** `reference.BIOTRANSFORMATIONS`
  ne contient que géraniol→citronellol et linalol→alpha-terpinéol — les deux seules voies
  avec preuve indépendante convergente entre souche ale ET lager (King & Dickinson 2003 ;
  corroboré par Michel et al. 2019 pour l'absence d'effet souche sur un thiol proche).
  Jamais de drapeau par souche commerciale individuelle : aucune source ne compare des
  souches commerciales entre elles, seulement des codes de collection académique.

## Réalité des données (vérifiée)
- **BarthHaas** : source houblon primaire. HTML servi, parsable, inclut les THIOLS.
  Crawler implémenté (`ingest.crawl_barthhaas`).
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
  donnée comme `reference.ALIASES`/`BIOTRANSFORMATIONS`. Ne pas retenter sans nouvelle piste.
- **Licence** : le CODE est MIT ; FooDB et FlavorDB2 sont NON COMMERCIALES. Un usage
  commercial imposerait de retirer/renégocier ces sources.

## Caveat validation
`schema.validate_and_repair` corrige l'inversion myrcène/caryophyllène des datasets
scrappés sales. Sur BarthHaas/Yakima (propres) elle ne se déclenche pas — c'est un
filet de sécurité, pas une valeur active.

## Prochaines tâches (ordre d'utilité)
Fait : `ingest.ingest_flavornet`, `ingest.ingest_foodb` (généralisé à `all_foods=True` par défaut
+ filtre de distinctivité + `download_foodb_dump` automatique — seule source de notes du
pipeline, amorce littérature retirée), `by-descriptor`, `ingest.crawl_yakima`,
`ingest.ingest_flavordb2`, `ingest.resolve_pubchem_cids` (jointure structurale CAS->CID + repli
sur le nom, voir `docs/FEATURE_NOTES.md` pour le détail de spec de by-descriptor), option
`--biotransform` (`amplify`, portée étroite — voir décision ci-dessus), GUI Streamlit
(`src/hopmatch/app.py`), `contrast`/`contrast_blend` généralisés par sélection manuelle de
descripteurs (`matching.contrast(descriptors=[...])`, sans dépendre de `note_descriptors`),
GUI : mode `browse` (T5), heatmap de comparaison des descripteurs en `by-descriptor` (T4).
`combine()` (NNLS) implémenté, amélioré (T10), puis RETIRÉ (2026-08-12) — voir la section
« But » en haut de ce fichier pour le détail de la décision.
Reste :
1. Jointure FooDB/hop_composition au-delà des ~734 composés Flavornet si le vocabulaire
   s'élargit beaucoup (crawl Yakima déjà réel, plus d'aliments FooDB).
2. Extension de `reference.BIOTRANSFORMATIONS` SI une étude comparant des souches
   commerciales entre elles (pas des codes de collection académique TUM/CBS/NCYC) sur
   ces mêmes composés devient disponible. Pas de drapeau par souche individuelle en
   attendant — voir le raisonnement dans README.md#option---biotransform.
3. `parsers.parse_descriptors` (BarthHaas) renvoie désormais `[]` pour la plupart des variétés :
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
