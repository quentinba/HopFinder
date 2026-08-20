# Backlog — audit du 2026-08-03

Issu d'un audit autonome (méthodologie, code, GUI, sources de données
additionnelles). Chaque ticket implémenté est testé (pytest + vérification
CLI/GUI réelle) et committé séparément. État tenu à jour au fil de
l'implémentation ([ ] à faire, [x] fait — voir le commit associé).

## Performance / correction

- [x] **T1 — `specificity()` recalculée inutilement en O(n_hops²)** (commit à suivre)
  `molecular_scores()` appelle `specificity(m, comp, biotransform)` à
  l'intérieur de la boucle `for h in comp: for m in note_profile:`, alors que
  cette valeur ne dépend QUE de `m`/`comp`/`biotransform`, jamais de `h`.
  Mesuré : `amplify()` ~1s sur la base réelle (203 houblons). Corrigible en
  cache par molécule (même principe que `max_amt`, déjà mis en cache juste
  au-dessus dans le code) — gain attendu proche de 20-50x, comportement
  identique (résultats inchangés, juste moins recalculés).

- [x] **T2 — `CONTRAST_AFFINITY` ne couvre que 10/~39 descripteurs réels**
  Le vocabulaire réel de `hop_descriptors` sur la base construite (Yakima)
  a ~39 termes distincts ; `CONTRAST_AFFINITY` n'en couvre que 10. Un
  utilisateur qui choisit "grapefruit", "pine", "mint", "lemon", "rose"...
  dans `contrast --descriptors` obtient une cible d'affinité vide sans
  explication. Étendre la couverture (reste un prior heuristique, déjà
  documenté comme tel dans README — pas une extension de données houblon
  fabriquées) + avertir explicitement quand un descripteur choisi n'a pas
  d'entrée dans la carte, plutôt que de le laisser disparaître en silence.

- [x] **T3 — Pas de test automatisé pour cli.py/app.py**
  `test_cli.py`/`test_app.py` n'existent pas : le câblage argparse→matching
  et la logique du dispatch ne sont vérifiés que manuellement. Ajouter des
  tests de fumée sur une base jouet (même pattern que `test_combine.py`).

## GUI

- [x] **T4 — Aucune visualisation graphique**
  L'app est 100% tableaux. Ajouté dans `by-descriptor` : une heatmap
  houblon x descripteur (présence/absence) comparant les candidats retournés
  (jusqu'à 12, triés par pertinence). **Radar écarté volontairement** au
  profit d'une heatmap, sur la base du skill `dataviz` : les descripteurs
  d'un houblon sont un ensemble binaire (pas une quantité), un radar
  déformerait par l'aire pour un gain de lisibilité nul, alors que la table
  du skill recommande explicitement « grille -> heatmap, une teinte » pour
  ce type de données — c'est exactement la forme des données ici. Une teinte
  (bleu = présent, gris clair = absent), légende toujours affichée, tooltip
  par cellule (houblon/descripteur/présence). Bug réel trouvé et corrigé en
  testant en direct dans le navigateur (pas juste `pytest`) : largeur de
  graphique par défaut trop étroite -> Vega-Lite masquait un libellé de
  houblon sur deux (10 houblons, seuls 5 nom affichés) ; corrigé avec une
  largeur au pas (`alt.Step`, comme la hauteur déjà utilisée pour les
  lignes) + `labelOverlap=False` + `labelLimit=200` (les plus longs noms,
  ex. "Nectaron® Brand - NZ Hops", étaient tronqués avec l'ellipse par
  défaut).

- [x] **T5 — Pas de mode "parcourir la base"**
  Impossible d'explorer un houblon (composition + descripteurs + sources)
  sans passer par amplify/combine/by-descriptor. Ajouter un mode de
  recherche/consultation direct.

- [x] **T6 — Pas de stats base en barre latérale**
  Aucune indication du nombre de houblons/notes/descripteurs chargés, ni de
  fraîcheur de la base — utile puisque la construction se fait uniquement
  en CLI, hors de la vue de l'utilisateur GUI.

- [x] **T7 — `_notes`/`_descriptors` sans cache**
  Requêtées à chaque rerender Streamlit (500+ notes). `st.cache_data` réduirait
  la latence perçue sur une interaction typique.

- [x] **T8 — top-N non ajustable sur amplify/contrast**
  `by-descriptor` a un slider "nombre de résultats" ; `amplify`/`contrast`
  sont figés à 8. Incohérent, à harmoniser.

- [x] **T24 — Libellés de mode peu conviviaux**
  `amplify`/`contrast`/`by-descriptor`/`browse` affichés tels quels dans la
  barre latérale. Renommés en `HopFinder - Amplify`/`HopFinder - Contrast`/
  `HopFinder from Descriptors`/`Browse hop informations` (`app.MODE_LABELS`,
  `format_func` sur le radio) — purement cosmétique, les clés internes/CLI ne
  changent pas.

- [x] **T26 — Roue d'arôme graphique par houblon en `browse`**
  Demandée « comme BeerMaverick/Yakima ». Première version en `hop_descriptors`
  (présence/absence, camembert à rayon fixe) jugée à raison non informative en
  retour utilisateur — **contrairement à T4** (radar écarté pour la
  COMPARAISON multi-houblon, où il déformerait par l'aire), ici il n'y a
  qu'UN polygone à la fois, l'objection T4 ne s'applique pas. En creusant le
  retour, découverte d'une vraie donnée quantitative jamais exploitée côté
  Yakima (`imported_fields.aroma_values`/`sensory_values`, intensité 0-100 —
  voir la section Yakima Chief de CLAUDE.md et `docs/DATA_SOURCES.md`) :
  nouvelle table `hop_aroma_intensity`, nouveau champ retourné par
  `parse_yakima_hit`, rendu en radar/spider chart (polygone sur 15 axes fixes,
  coordonnées calculées en Python — un premier essai en `mark_arc` Vega-Lite
  theta+radius ne balayait qu'un demi-cercle par défaut, bug non résolu,
  abandonné). 94/151 variétés Yakima couvertes ; BarthHaas n'a pas cette
  donnée, rien affiché pour les variétés non couvertes.

- [x] **T25 — Associations houblon<->houblon en `browse`**
  Demandé : reproduire les « Hop Pairings » BeerMaverick. Trois relations
  distinctes implémentées, chacune affichée avec sa propre source (demande
  explicite de l'utilisateur — jamais présentées comme interchangeables) :
  **Variétés similaires** (Yakima, `imported_fields.similar_varieties`, curé
  par YCH, table `hop_similar`) ; **Associations fréquentes en recette**
  (BeerMaverick, fréquence relative dans des recettes publiées, table
  `hop_pairings`) ; **Substitutions suggérées** (BeerMaverick, choix éditorial
  de brasseurs, table `hop_substitutions`). BeerMaverick avait d'abord été
  écarté (réserve d'accès sur leur endpoint interne) puis réexaminé et retenu
  après avoir trouvé que la même donnée est déjà dans le HTML statique de
  chaque page produit — voir l'entrée « Sources de données additionnelles »
  ci-dessous pour l'historique complet, et `docs/DATA_SOURCES.md` pour le
  détail d'implémentation. Réconciliation par nom normalisé
  (`ingest._resolve_hop_variety`) : 143/203 de nos variétés ont une page
  BeerMaverick correspondante.

  **Addendum — vocabulaire de descripteurs élargi de 38 à 104 termes.**
  Signalé par l'utilisateur : `contrast --descriptors tropical` ciblait "dank"
  mais quasiment aucun houblon ne le couvrait, et Mosaic (censé l'avoir selon
  l'utilisateur) ne l'avait pas non plus. Vérifié en direct : Yakima ne tague
  "Dank" que sur 1/203 houblons (CTZ) — `imported_fields.aromas` est une liste
  courte éditoriale, pas exhaustive. BeerMaverick expose un vrai bloc de tags
  par page (`<b>Tags:</b> #pine #dank...`), 131 tags distincts sur 142 pages,
  correctement sélectif (Chinook/Columbus tagués "dank", Mosaic/Simcoe non —
  cohérent avec l'usage réel). Ingéré dans `hop_descriptors`
  (source='beermaverick'), filtré (`ingest._BEERMAVERICK_TAG_DROPLIST`) puis
  normalisé (`ingest._normalize_beermaverick_tag` + nouvelles entrées
  `reference.CONTRAST_AFFINITY`/`DESCRIPTOR_ALIASES`). Résultat : "dank" passe
  de 1 à 6 houblons couverts ; `contrast --descriptors tropical` renvoie
  maintenant Chinook à 100%.

- [x] **T33 — `contrast_blend` refondu + `amplify_blend` ajouté**
  L'utilisateur a jugé l'ancien `contrast_blend` (couverture ensembliste
  gloutonne, un seul blend "optimal") peu utile — rien ne garantissait que
  les houblons combinés soient réellement utilisés ensemble. Nouvelle
  méthodologie explicitement demandée : proposer PLUSIEURS tailles de blend
  (1 à 5), et à chaque taille >1, choisir le houblon par fréquence RÉELLE de
  pairing BeerMaverick (`hop_pairings`) avec un houblon déjà dans le blend —
  la couverture reste calculée/rapportée mais ne pilote plus le choix.
  Repli explicite sur la couverture gloutonne classique quand aucune
  fréquence réelle n'existe (36/203 houblons seulement ont une donnée
  `hop_pairings`, mesuré) — jamais un blend plus petit que possible par
  manque de données, mais provenance signalée par houblon (`via`:
  "top"/"pairing"/"coverage"). Mécanisme partagé
  (`matching._pairing_grown_blends`) avec le nouveau `amplify_blend` (cible =
  descripteurs de la note, **pas de NNLS** — décision explicite pour ne pas
  recréer `combine()`, déjà retiré pour la dégénérescence documentée en
  T10/« But »). Vérifié en direct sur une cible large (10 catégories cœur) :
  Amarillo (meilleur candidat) puis Simcoe/Citra/Mosaic/Chinook, 4 houblons
  sur 5 ajoutés via une fréquence de pairing BeerMaverick réelle.

- [x] **T34 — Libellé "Hopfinder from Descriptors"**
  Coquille de casse (F minuscule). Renommé "HopFinder from Descriptors"
  (`app.MODE_LABELS`), cohérent avec "HopFinder - Amplify"/"- Contrast" (T24).

- [x] **T35 — Libellé "Browse hop composition"**
  Renommé "Browse hop informations" (`app.MODE_LABELS`) — la page affiche
  aussi les associations houblon<->houblon (T25) et la roue d'arôme (T26),
  pas seulement la composition.

- [x] **T36 — `--oav` actif par défaut en GUI**
  La case `--oav (prior de puissance olfactive)` démarrait décochée
  (`value=False`). Effet réel mesuré et documenté (T23, ~1 note sur 6 change
  de classement) — passée à `value=True` par défaut, désactivable pour
  comparer sans.

- [x] **T37 — Curseur "Nombre de résultats" mal placé en Amplify**
  Dans la sidebar, loin du multiselect de descripteurs qu'il affecte.
  Déplacé dans le corps de la page Amplify, juste après le multiselect
  (`st.slider` au lieu de `st.sidebar.slider`) — Contrast garde le sien en
  sidebar (non demandé pour ce mode).

- [x] **T38 — Curseur de taille de blend 1-5**
  Retiré (`amplify`/`contrast` appellent désormais `amplify_blend`/
  `contrast_blend` avec `max_hops=5` fixe) — pas d'utilité à proposer moins
  de 5 tailles, cf. T33/T41 : le mécanisme grossit maintenant toujours
  jusqu'à `max_hops`.

- [x] **T39 — Navigation directe résultat → Browse**
  Bouton (icône `open_in_new`) sur chaque ligne de résultat en `amplify`,
  `contrast` et `by-descriptor`, ouvrant `browse` pré-sélectionné sur ce
  houblon. `st.dataframe` ne supporte pas de bouton par ligne : rendu manuel
  via `st.columns` (`app._render_hop_table`/`_browse_button`). Changer
  `st.session_state["mode"]` directement lève
  `StreamlitAPIException` (widget déjà instancié) — relais par une clé
  différente (`_next_mode`/`_next_browse_hop`) consommée en tête de `main()`
  avant l'instanciation du radio/selectbox concerné ; recherche `browse`
  réinitialisée au passage (sinon un filtre resté d'une visite précédente
  pourrait exclure le houblon ciblé et faire planter le `st.selectbox`).

- [x] **T40 — Houblons avec un "r" résiduel ("Citrar", "Mosaicr"...)**
  Root cause investiguée en direct plutôt que patchée en surface (exigence
  explicite de l'utilisateur — un vrai houblon peut légitimement finir par
  "r") : BarthHaas translittère ® en "r" et ™ en "tm", collés sans séparateur
  dans son propre générateur de slug. `ingest._fix_barthhaas_trademark_slug`
  ne déclenche que si le slug égale exactement `normalize(h1) + "r"/"tm"` (+
  suffixe optionnel) — vérifié sur 6 vrais houblons finissant par "r"
  (Saazer, Glacier, Endeavour, Challenger, Cluster, Pioneer) qu'aucun n'est
  touché. 10 houblons concernés (Citra, Mosaic, Ekuanot, Loral, Sabro,
  Summit, Azacca, Talus, Bru-1, Amarillo) fusionnent maintenant correctement
  avec leur entrée Yakima au lieu d'exister en double, chacune amputée d'une
  partie des données (thiols côté BarthHaas, β-pinène/sélinène côté Yakima).
  203 → 193 houblons en base après réingestion réelle. Voir CLAUDE.md
  (section BarthHaas) pour le détail complet de l'investigation.

- [x] **T41 — Roue d'arôme (T26) trop petite, illisible en thème sombre**
  Rayon agrandi (130 → 170), police des labels augmentée (14px). Couleurs
  explicites par thème (`st.context.theme.type` — seule information de
  thème exposée par Streamlit, pas de couleur exacte lisible) : les marques
  Altair `mark_text`/`mark_rule` n'héritent PAS automatiquement du thème
  Streamlit contrairement aux axes/légendes natifs — vérifié en lisant le
  rendu réel en thème sombre (labels noirs sur fond sombre, illisibles)
  avant correction.

- [x] **T42 — Blend `contrast` toujours de taille 1**
  Signalé par l'utilisateur. PAS un bug : conséquence attendue du early-exit
  ajouté en T33 (`if not (target - covered): break`), devenu très fréquent
  une fois le vocabulaire de descripteurs élargi à 104 termes (T25 addendum)
  — un seul houblon populaire couvre souvent à lui seul les 2-3 descripteurs
  cibles de `CONTRAST_AFFINITY`. Revirement de méthodologie tranché par
  l'utilisateur : early-exit retiré, `_pairing_grown_blends` grossit
  maintenant toujours jusqu'à `max_hops` (ou épuisement du pool). Nouveau
  statut `via="relevance"` quand ni pairing ni gain de couverture n'existe
  plus — étiqueté "rien de neuf à couvrir" pour ne jamais laisser croire à
  une couverture supplémentaire inexistante.

- [x] **T43 — Roue d'arôme toujours illisible en thème sombre après T41**
  Le premier passage (palette choisie via `st.context.theme.type`) ne
  suffisait pas, signalé par l'utilisateur après vérification en direct.
  Cause réelle : `st.altair_chart` applique par défaut `theme="streamlit"`,
  qui réécrit la config Vega-Lite globale et écrase les couleurs de mark
  explicites (`mark_text`/`mark_rule` sans encodage de couleur) — pas un
  mauvais choix de couleur, un thème global qui gagne dessus. Corrigé par
  `theme=None` sur cet appel `st.altair_chart` (`app._browse`), laissant
  Vega-Lite utiliser la palette choisie à la main plutôt que celle de
  Streamlit.

- [x] **T44 — Blend `contrast`/`amplify` : houblon de base + mélange
  pertinence/pairing plutôt qu'une cascade**
  Deux problèmes signalés ensemble par l'utilisateur après T33/T42 : (1) le
  score de `contrast` est souvent homogène (plusieurs houblons ex-aequo
  "meilleur candidat"), donc imposer `candidates[0]` comme houblon de base
  masque un choix arbitraire ; (2) le mécanisme de pairing choisissait le
  houblon de plus haute fréquence de pairing n'importe où dans le pool
  restant, PAS un mélange pertinence+pairing comme demandé à l'origine —
  en pratique une cascade (pairing jusqu'à épuisement, puis couverture).
  Corrigé : `matching._pairing_grown_blends` accepte `base_variety` (choisi
  par l'utilisateur en GUI via `app._select_base_hop`, affiché juste
  au-dessus du blend pour amplify ET contrast — repli sur `candidates[0]`
  si omis) ; les additions suivantes filtrent d'abord les candidats restants
  (déjà triés par pertinence) à ceux présents dans le TOP 10
  (`_PAIRING_TOP_N`) des partenaires BeerMaverick d'un houblon déjà dans le
  blend, puis prennent le PLUS PERTINENT de ce sous-ensemble — jamais celui
  de plus haute fréquence brute. Vérifié par test : un candidat de fréquence
  99 mais moins pertinent perd contre un candidat de fréquence 10 mais plus
  pertinent, dès lors que les deux sont dans le top-10 pairing du houblon de
  base.

- [x] **T45 — Bouton "ouvrir dans Browse" retiré, remplacé par des
  expanders sur place**
  Signalé par l'utilisateur : cliquer le bouton ajouté en T39 faisait perdre
  la page amplify/contrast en cours (résultats + blend), sans moyen d'y
  revenir. Retiré entièrement (`_render_hop_table`/`_browse_button`
  supprimés, tableaux revenus à `st.dataframe`) et remplacé par
  `app._hop_detail_expanders` : un expander de détail par houblon
  (descripteurs, composition, sources) directement SOUS le tableau de
  résultats, sans navigation — même esprit que la liste d'expanders déjà
  présente sous la heatmap de `by-descriptor` (suggéré explicitement par
  l'utilisateur en exemple).

- [x] **T46 — Roue d'arôme : axe "Pomme" en français**
  Signalé par l'utilisateur : français et anglais mélangés dans la roue
  d'arôme. Investigué en direct sur l'API Algolia YCH (153 variétés) : PAS un
  mélange de locale côté hopmatch (`crawl_yakima` filtre déjà strictement
  `publish_details.locale:"en-us"`) — 14 des 15 axes sont bien en anglais,
  seul "Pomme" est mal étiqueté DANS le CMS Yakima lui-même, sous la MÊME
  locale, avec le MÊME uid Contentstack réutilisé identiquement sur ~281
  variétés (coquille de saisie source unique et cohérente, pas un champ
  traduit au hasard). Corrigé par un alias ciblé
  (`reference.DESCRIPTOR_ALIASES["pomme"] = "apple"`), déjà appliqué par le
  mécanisme d'ingestion existant. 94 lignes stales supprimées puis
  `crawl-yakima` relancé.

- [x] **T47 — GUI traduite en anglais**
  Demande utilisateur explicite ; scope confirmé par question de
  clarification (le texte utilisateur de `app.py` uniquement — labels,
  captions, warnings, badges ; `cli.py` et tous les commentaires/docstrings,
  y compris dans `app.py`, restent en français comme le reste du projet).
  Réécriture complète de `app.py` : tous les libellés/messages ; champs Vega
  utilisés comme libellés de tooltip (`_aroma_wheel`, `_descriptor_heatmap`)
  également renommés en anglais, visibles au survol. Voir CLAUDE.md,
  section Conventions, pour l'exception documentée durablement.

- [x] **T48 — Aromatic/bittering/dual purpose**
  Demande utilisateur : "I completely forgot something in this app: it's the
  concept of aromatic vs bittering hops." Recherché sur BarthHaas ET Yakima :
  aucun des deux n'expose ce classement (vérifié en direct). BeerMaverick
  seul l'a (`<tr><th>Purpose:</th><td>Aroma|Bittering|Dual</td></tr>`, même
  tableau HTML déjà exploité pour pairings/tags) — vérifié sur 9 houblons
  connus, cohérent avec l'usage réel. Écrit dans `hops.purpose` (nouvelle
  colonne, "aromatic"/"bittering"/"both"/NULL). Affiché en info PRINCIPALE
  en `browse` (juste sous le nom du houblon) et en colonne colorée
  (`st.badge`, couleurs sémantiques Streamlit — seul rendu par cellule
  adapté aux deux thèmes) dans les résultats amplify/contrast. Run réel
  (143 variétés couvertes) : 52 aromatic, 20 bittering, 70 both, 52 sans
  donnée. Voir la section BeerMaverick de CLAUDE.md pour le détail complet.

- [x] **T49 — Blends structurés aromatic + bittering**
  Suite de T48, demande utilisateur explicite : "propose blends with at
  least 1 aromatic and 1 bittering as a first proposal (n=2) and then
  propose blends picking only aromatic hops that pairs well with the other
  aromatic hop (not the bittering)". `matching._pairing_grown_blends` accepte
  `purpose_by_variety` : si le rôle du houblon de base (taille 1) est connu
  et unilatéral, la taille 2 cherche explicitement le rôle opposé
  (`via="complement"`) ; à partir de là, la croissance se restreint aux
  houblons aromatiques et le pairing BeerMaverick ne regarde que les
  partenaires aromatiques du blend, jamais l'amérisant. S'arrête dès
  épuisement du pool aromatique, même avant `max_hops`. Repli silencieux sur
  la croissance générique (T33/T42/T44) si le rôle de base est inconnu ou
  qu'aucun candidat complémentaire n'existe. Vérifié en direct sur données
  réelles (`contrast-blend --descriptors citrus,floral`) : Celeia
  (aromatic) + Millennium (bittering, complément) à la taille 2, puis
  seulement des houblons aromatiques/both aux tailles 3-5.

- [x] **T50 — Image de fond**
  Demande utilisateur : gravure houblon fournie (`assets/background.png`)
  comme fond de l'app. PNG (~3,1 Mo) reconverti en JPEG qualité 82 à
  l'ingestion GUI (`app._background_data_uri`, ~360 Ko), inliné en base64
  via CSS (`st.markdown(..., unsafe_allow_html=True)`) — pas de serveur de
  fichiers statiques à configurer. Voile semi-transparent couleur du thème
  (même mécanisme que `_aroma_wheel`, `st.context.theme.type`) pour rester
  lisible en clair et en sombre ; cible `stAppViewContainer` seulement, pas
  la sidebar. Vérifié en direct dans les deux thèmes.

  **Addendum 1 (2026-08-19, deux problèmes signalés par l'utilisateur juste
  après) :** (1) l'image (fond crème, trait noir) ne convenait qu'au thème
  clair. Corrigé par un négatif couleur (`PIL.ImageOps.invert`) via
  `st.context.theme.type`. (2) le fond restait bloqué sur la tranche du haut
  même en défilant. Tentative : retirer `background-attachment: fixed` +
  `center top` au profit de `right top` sans `fixed`.

  **Addendum 2 (même jour, l'utilisateur signale que les DEUX ne sont
  toujours pas corrigés) — root cause réinvestiguée en direct sur le DOM/CSS
  réel, pas supposée :** (1) le sélecteur de thème Streamlit (menu "⋮") est
  un état 100% CÔTÉ CLIENT (aucun attribut/style lié au thème sur `<html>`/
  `<body>`, vérifié) qui ne déclenche PAS de rerun Python immédiat —
  `st.context.theme.type` reste bloqué sur l'ancienne valeur tant qu'aucune
  VRAIE interaction widget n'a eu lieu (confirmé : deux reruns réels après
  avoir choisi "Light" ne suffisaient pas, il en a fallu un troisième).
  `st.context.theme.type` abandonné pour ce composant : les deux variantes
  (normale + négatif) sont désormais TOUTES LES DEUX embarquées dans le CSS,
  sélectionnées par `@media (prefers-color-scheme: dark)` — évalué par le
  navigateur, instantané, sans aller-retour Python. Limite assumée : ne suit
  que la préférence OS ("System", le réglage par défaut), pas un override
  manuel Light/Dark qui contredirait l'OS (cas minoritaire, toujours corrigé
  après une vraie interaction). (2) `[data-testid="stAppViewContainer"]`
  n'est PAS l'élément qui défile réellement — mise en page à défilement
  imbriqué, c'est `[data-testid="stMain"]` qui a `overflow-y: auto` et un
  `scrollHeight` > `clientHeight` (vérifié via `getComputedStyle`/
  `scrollHeight` en direct) ; `stAppViewContainer` fait toujours exactement
  la hauteur du viewport, donc `cover` dessus ne voyait jamais plus qu'un
  viewport de l'image, `fixed` ou pas. Corrigé en ciblant `stMain` avec
  `background-attachment: local` (pas le défaut `scroll`, qui fixe le fond
  par rapport à la BOÎTE de l'élément, pas à son contenu défilant) : `local`
  fait défiler le fond avec le contenu réel, sur toute la hauteur défilable.
  `background-position: right top` conservé. Vérifié en direct : le fond
  change bien de portion en défilant, dans les deux thèmes.

  **Addendum 3 (même jour, l'utilisateur signale que le thème ne change
  toujours pas l'image : "changing theme doesn't change the image used")**
  — la médiaquery CSS de l'addendum 2 suit la préférence OS, PAS le
  sélecteur Light/Dark/System du menu Streamlit lui-même : aucune des deux
  méthodes tentées (`st.context.theme.type`, `prefers-color-scheme`) ne
  suit ce sélecteur de façon fiable et instantanée. Trouvé en direct
  (`getComputedStyle`) : `.stApp` a une propriété CSS `color-scheme`
  calculée qui, elle, se met à jour INSTANTANÉMENT au clic sur Light/Dark/
  System (vérifié : "dark"→"light" sans aucun rerun Python) — pilotée par
  une classe Emotion générée dynamiquement, mais la propriété CSS calculée
  qui en résulte est stable et lisible. Problème : `color-scheme` n'est
  utilisable qu'en valeur `<color>` (`light-dark()`), pas pour choisir entre
  deux `background-image`/`url()` entières — aucune solution CSS pure ne
  permet ce choix. Basculé sur `st.iframe` (PAS `st.markdown` : un
  `<script>` injecté via `st.markdown(unsafe_allow_html=True)` NE
  S'EXÉCUTE JAMAIS, vérifié en direct avec un test minimal) avec une chaîne
  HTML brute — documenté comme exécutant du JS avec accès same-origin à la
  page parente. Le script lit `color-scheme` sur `.stApp` via
  `window.parent.document`, applique le fond directement en JS, et observe
  les changements de `class` sur `.stApp` (`MutationObserver`) pour réagir
  à chaque bascule de thème sans dépendre d'un rerun Python ; écoute aussi
  `matchMedia(...).addEventListener` pour le cas "System" + OS qui change
  en cours de session. Vérifié en direct : bascule Light/Dark/System dans
  le menu Streamlit change l'image immédiatement, dans les deux sens.

  **Addendum 4 (même jour, l'utilisateur signale que le niveau de zoom
  change à chaque interaction)** — cause : `background-attachment: local`
  sur `stMain` (addendum 2) fait recalculer `background-size: cover` contre
  le `scrollHeight` RÉEL de `stMain`, qui change à chaque page/résultat
  affiché — l'image "respire" visiblement d'une interaction à l'autre.
  Corrigé en repassant `background-attachment: fixed` (ancré au VIEWPORT,
  constant hors redimensionnement de fenêtre) sur `stAppViewContainer` —
  PAS `stMain` : `fixed` sur un élément qui défile lui-même a un rendu
  cross-browser incohérent, `stAppViewContainer` (qui ne défile jamais
  lui-même, voir addendum 2) est la cible correcte pour un fond réellement
  figé. Utilise aussi `assets/background_zoomed.png` (fournie par
  l'utilisateur) au lieu de `background.png` — un crop déjà recadré,
  affiché tel quel (`background-position: center center`, plus de recadrage
  `right top` côté CSS). Vérifié en direct : le fond ne bouge plus du tout
  en défilant, dans les deux thèmes.

- [x] **T51 — Suffixe "Brand" dans le nom affiché ("Mosaic Brand")**
  Signalé par l'utilisateur : "Mosaic Brand" en GUI côté Yakima alors que
  BarthHaas affiche "Mosaic" pour la même variété. Root cause à deux
  niveaux, vérifiée en direct : (1) `imported_fields.display_name` Yakima
  porte littéralement "Brand" pour 50/153 variétés — un artefact de leur
  convention d'affichage marketing, jamais présent côté BarthHaas pour la
  même variété. Corrigé par `parsers._strip_yakima_brand_suffix` (retire
  uniquement le mot "Brand"/"(Brand)", garde ®/™ et les vrais qualificatifs
  comme "- NZ Hops"/"Organic"). (2) `_ingest_variety` n'écrivait `name` qu'à
  la création, jamais sur fusion multi-sources — un houblon ingéré par
  Yakima PUIS BarthHaas gardait pour toujours le nom (avec "Brand") du
  premier crawl. Corrigé : BarthHaas (source primaire) l'emporte toujours
  sur conflit ; une réingestion de la même source peut aussi rafraîchir le
  nom. Réingestion réelle (`crawl-barthhaas` + `crawl-yakima`) : 43 → 0
  houblons avec "Brand" dans le nom affiché.

- [x] **T52 — Alpha/beta acides, co-humulone, huile totale en avant + purpose
  inféré depuis l'acide alpha (demande utilisateur, 2026-08-19)**
  Signalé : "il manque un élément principal : les infos les plus importantes
  de yakima : i) ALPHA ACIDS % and it's fraction of cohumulone ii) BETA ACIDS
  % et iii) TOTAL OIL ml/100g" — puis "the AA% mean... can be used to infer
  the aromatic/bittering status", "instead of unknown for the purpose, use
  infered:aromatic and infered:bittering", "make this column a bit more wide".

  **Bug racine découvert en creusant** : `alpha_acid`/`beta_acid` étaient
  dans `schema.DROP_COMPOUNDS` ("non aromatiques") — jamais stockées en base
  du tout (pas juste filtrées à l'affichage), vérifié via
  `SELECT DISTINCT compound FROM hop_composition` ne retournant aucune ligne
  `alpha_acid`/`beta_acid`. Retirées de ce filtre (`polyphenols` seul y
  reste, entrée morte jamais produite par aucun parseur).

  **Co-humulone** (fraction des acides alpha) : nouveau, Yakima UNIQUEMENT
  (`co_h` côté API Algolia — Citra 20-24%, cohérent avec les valeurs
  publiques connues) — vérifié en direct qu'il est absent du HTML BarthHaas
  (aucune ligne "CO-HUMULONE" sur leurs fiches). `parsers.YAKIMA_API_FIELDS`
  mappe `co_h` -> `co_humulone`. Réingestion réelle (`crawl-barthhaas` +
  `crawl-yakima`) : 249 lignes alpha_acid, 248 beta_acid, 150 co_humulone
  (Yakima seul), 249 total_oil dans `hop_composition`.

  **Purpose inféré** (`matching.infer_purpose_from_alpha_acid`/
  `resolve_purpose`) : seuil `ALPHA_ACID_BITTERING_THRESHOLD_PCT = 7.0`
  **mesuré**, pas deviné — scan de seuils (0 à 25%, pas 0,25) sur les 142
  houblons ayant À LA FOIS un `purpose` BeerMaverick réel et un acide alpha
  connu, cherchant le seuil maximisant l'accord aromatic vs bittering+both :
  7,0% est le meilleur séparateur trouvé, 78,2% d'accord (79 vrais positifs,
  32 vrais négatifs, 20 faux positifs, 11 faux négatifs) — imparfait
  (chevauchement réel : des houblons "aromatic" mesurés montent jusqu'à
  17,5% d'alpha, des "bittering" descendent à 5%), d'où le préfixe
  "Inferred: " systématique en GUI, jamais présenté au même niveau qu'une
  donnée BeerMaverick réelle. **Portée strictement limitée à l'affichage** :
  `resolve_purpose` ne touche jamais `_pairing_grown_blends`/
  `purpose_by_variety` (structure des blends aromatic+bittering, T-purpose),
  qui continue d'utiliser EXCLUSIVEMENT le purpose BeerMaverick réel — une
  estimation à 78% ne doit jamais contaminer une garantie de structure
  fondée sur de la donnée réelle. Le vrai purpose l'emporte toujours quand
  il existe ; repli sur l'inférence seulement s'il est `None` et que
  l'acide alpha est connu ; sinon `None` (jamais de "Unknown" fabriqué).

  **GUI** (`app._render_key_stats`, `app._row_with_purpose`) : 4
  `st.metric` (Alpha/Beta/Co-humulone/Total oil, "—" si absent, jamais une
  valeur inventée) ajoutés en tête de Browse ET des expanders de détail
  d'Amplify/Contrast/By-descriptor (même contenu partout, demande
  utilisateur explicite "ainsi que dans les détails des houblons proposés
  pour les autres outils"). Unité/qualificatif déplacé dans le LABEL du
  metric ("Total oil (ml/100g)", "Co-humulone (% of AA)") plutôt que dans
  la valeur : "1.4 ml/100g" tronquait en "1.4 ml/1…" dans la largeur de
  colonne fixe de `st.metric` (constaté en direct au navigateur). Colonne
  Purpose des tableaux de résultats (`_render_hop_rows`) élargie de 3 à 5
  (sur une grille `st.columns` totalisant 16 parts) : "Inferred: Bittering"
  tronquait encore en "Inferred: Bitt…" à 3, plein texte lisible à 5
  (vérifié en direct au navigateur, capture avant/après). `_NON_AROMA_DISPLAY`
  (deux définitions, `app.py` et `matching.py`) étendu avec `co_humulone`
  pour ne pas le dupliquer dans le tableau de composition générique
  maintenant qu'il est réellement stocké et affiché via `_render_key_stats`.

  Effet de bord noté en vérifiant (hors scope de ce ticket, pas corrigé) :
  la base contient un doublon "Amarillo®" (`amarillo`, fusion
  BarthHaas+Yakima, purpose=None -> inféré) et `amarillo-brand-ama04`
  (Yakima seul, purpose BeerMaverick réel="aromatic") — même nom affiché,
  variety keys différentes non fusionnées, indiscernables dans le
  sélecteur Browse. Pas un artefact de ce ticket (préexistant), à investiguer
  séparément si signalé par l'utilisateur.

- [x] **T53 — Renommage d'affichage "HopFinder", copie de la page d'accueil
  clarifiée, roue d'arôme ajoutée à `by-descriptor`, doublons de houblons
  audités et corrigés (demande utilisateur, 2026-08-19)**

  **Renommage d'affichage.** Demande : "Make the name of the App HopFinder
  instead of hopmatch (everywhere on Github and the GUI)". Clarifié par
  question explicite à l'utilisateur : affichage seulement (GUI
  `st.set_page_config`/`st.title`, titre + prose conversationnelle de
  README.md), le paquet Python, la commande CLI (`hopmatch build`/...) et
  `pyproject.toml` restent `hopmatch` — pas de renommage mécanique du code.
  Les mentions LITTÉRALES de commandes CLI dans README.md (blocs de code,
  ex. `hopmatch amplify mango`) restent inchangées : ce sont de vraies
  commandes, pas du texte de marque.

  **Copie de la page d'accueil (`app._TOOL_SUMMARIES`).** 4 demandes
  explicites : (1) Amplify : retiré "rather than reproducing it" (redondant
  avec "extends") ; (2) expliqué TF-IDF en une phrase (pondère chaque
  molécule partagée par sa spécificité entre houblons, pour qu'une molécule
  rare comme un thiol compte plus qu'une molécule ubiquitaire comme le
  myrcène) ; (3) précisé que la couche descripteurs (aroma-wheel overlap)
  ne s'active QUE si l'utilisateur ajoute manuellement des descripteurs
  correspondant à son ajout ; (4) Contrast : précisé qu'un dictionnaire
  codé en dur (`reference.CONTRAST_AFFINITY`) associe chaque descripteur à
  ses contrastes complémentaires — un prior heuristique de pairing
  culinaire, pas une donnée sourcée, jamais moléculaire (cohérent avec la
  mise en garde déjà présente dans README.md#ce-qui-est-un-prior-pas-une-donnée).
  (5) Retiré le préfixe "No note required: " de la carte `by-descriptor`
  (déjà clair par le nom de l'outil).

  **Roue d'arôme ajoutée à `by-descriptor`.** Signalé : "The aroma wheel is
  missing from the from descriptor tool". L'expander de détail par houblon
  de `_by_descriptor` (badge purpose + stats clés + descripteurs + tableau
  de composition, ajoutés en T52) n'avait jamais la roue d'arôme
  quantitative contrairement à `_browse`/`_hop_detail_expanders`
  (Amplify/Contrast) — même bloc `st.altair_chart(_aroma_wheel(...),
  theme=None)` désormais ajouté aux trois, contenu réellement identique
  partout où un houblon est détaillé.

  **Doublons de houblons audités (demande : "There is two Amarillo entry,
  check why and fix it for this hop and other if it exists").** Audit
  complet de `hops` par `name` strictement identique : **7 paires** trouvées,
  de DEUX natures différentes, distinguées en vérifiant en direct sur l'API
  Algolia Yakima (`imported_fields.country_code`/`cultivar`/`variety_code`) :

  1. **5 VRAIS doublons** (Challenger, Fuggle, Hallertauer Tradition,
     Hersbrucker Spät, Target) : même variété, MÊME région, juste un slug
     différent entre BarthHaas (ex. `wye-challenger`, préfixe historique du
     Wye College) et Yakima (`challenger`) — jamais fusionnés faute de
     mécanisme de réconciliation cross-source au-delà du slug exact/
     dépréfixage marque (contrairement à `_resolve_hop_variety` pour
     BeerMaverick). Root cause confirmée : `name` strictement identique
     entre les deux sources dans les 5 cas (pas de souci d'accents/
     translittération à gérer), seule la `region` différait de libellé sans
     changer de pays (BarthHaas "Great Britain" vs Yakima "United Kingdom").
     **Corrigé à la racine** : `ingest._find_variety_by_name_region`
     (nouveau, alias GB/UK volontairement restreint à ce cas vérifié) tente
     une résolution par nom+région AVANT de créer une nouvelle ligne, dans
     `crawl_barthhaas` ET `crawl_yakima` (symétrique, indépendant de l'ordre
     des deux crawls) — seulement en repli quand la clé slug directe
     n'existe pas déjà, pour ne jamais dévier d'une correspondance certaine.
     `crawl_yakima` restructuré en deux passes pour que `hop_similar`
     référence toujours la clé FINALE (post-fusion), jamais une clé
     pré-fusion jamais écrite dans `hops` (bug identifié en écrivant le
     correctif, jamais laissé passer). Les 5 paires DÉJÀ en base (créées
     avant ce correctif) réparées via `ingest.merge_hop_varieties(con, keep,
     drop)` (nouveau, réutilisable) : déplace composition/descripteurs/roue
     d'arôme/associations houblon<->houblon (dans les deux sens) vers la
     clé survivante, fusionne `sources` (union) et `purpose`
     (`COALESCE(keep, drop)` — un seul des deux avait une valeur réelle dans
     les 5 cas, jamais de conflit à trancher), supprime la ligne fusionnée.
     Appliqué en direct sur la base réelle : 194 → 189 houblons, 0 référence
     morte vérifiée après coup (hop_similar/hop_pairings/hop_substitutions/
     hop_composition/hop_descriptors, tous varieties existent bien dans
     `hops`).
  2. **4 crops RÉELLEMENT distincts** (Amarillo®, Perle, Saaz, Northern
     Brewer) : même nom affiché ET même cultivar (ex. Amarillo VGXP01) mais
     cultivés dans des pays DIFFÉRENTS (Amarillo US vs Allemagne, Perle
     US vs Allemagne, Saaz US vs Tchéquie, Northern Brewer US vs Allemagne)
     — vérifié en direct sur `imported_fields.country_code` pour chaque
     paire, jamais un artefact de données. `_find_variety_by_name_region`
     ne les fusionne PAS grâce à la correspondance stricte sur la région
     (garantie explicite, testée). **Fusionner ces 4 paires aurait été une
     RÉGRESSION** (perte d'une vraie distinction de terroir) : la correction
     est donc côté AFFICHAGE — `app._disambiguated_hop_labels` (nouveau)
     ajoute `(région)` au libellé UNIQUEMENT en cas de collision de nom
     réelle dans le sélecteur `browse` (ex. "Amarillo® (United States)" /
     "Amarillo® (Germany)"), jamais sur un nom déjà unique.

- [x] **T54 — `by-descriptor` : tri à deux couches (catégorique + quantitatif
  roue d'arôme), sélection rapide par pills, heatmap shadée par intensité
  (demande utilisateur, 2026-08-19)**

  Demande explicite : "Currently in the from descriptor tool... we are
  relying on descriptors... that is categorical, however we could rely on
  the small amount of wheel aroma descriptor as quantitative value...
  propose a 2 layer results ordering the hops that have the textual
  descriptor but inside this selection, propose a ordered result... based
  on the aroma wheel descriptors" — confirmé après une recommandation
  explicite (tradeoffs : couverture 94/151 variétés Yakima uniquement,
  vocabulaire 15 termes vs 104 pour `hop_descriptors`) — puis "propose a
  section here user can click on the boxes corresponding to aroma wheel
  flavors (since there is not much it will be more visible)".

  **`matching.by_descriptor` — tri à deux couches.** Couche 1 (inchangée,
  PRIORITAIRE) : nb de descripteurs `hop_descriptors` recoupés desc — reste
  le filtre/tri principal, jamais remplacé. Couche 2 (NOUVELLE, départage
  À L'INTÉRIEUR de chaque palier catégorique) : intensité moyenne
  (`hop_aroma_intensity`, T26, Yakima uniquement, 0-100 réel) sur
  l'INTERSECTION entre les descripteurs sélectionnés et ceux que CE houblon
  a réellement en données quantitatives — jamais une moyenne comptant les
  descripteurs manquants comme 0 (fabriquerait une donnée). Les houblons
  sans intensité exploitable pour la sélection (pas de couverture Yakima,
  ou descripteurs hors des 15 catégories de la roue) passent APRÈS ceux qui
  en ont une dans le MÊME palier catégorique — jamais mélangés à un score
  de 0 inventé, même principe que les molécules orphelines. Repli inchangé
  sur `total_oil` puis `variety` en dernier recours. Chaque entrée retournée
  expose désormais `quant_score`/`quant_descriptors`/`intensity` (transparence
  — la GUI affiche explicitement ce qui a été moyenné, jamais un
  réordonnancement silencieux).

  **GUI — sélection rapide par `st.pills`.** Nouveau widget "Aroma wheel
  flavors" (`st.pills`, `selection_mode="multi"`) au-dessus du multiselect
  général à 104 termes, listant les 15 catégories à donnée quantitative —
  "small number of options that fit on one line" (skill Streamlit),
  nettement plus visible/cliquable que de les chercher dans le multiselect.
  Union simple avec la sélection générale (pas de mécanisme séparé) : un
  descripteur choisi via les pills a exactement le même effet catégorique
  qu'un choix dans le multiselect — la différence est uniquement que les 15
  termes de la roue ont AUSSI des données quantitatives exploitables pour le
  tri secondaire.

  **GUI — transparence par houblon.** Caption explicite dans chaque
  expander de détail : "Quantitative refinement: X/100 avg. intensity on
  [descripteurs] (Yakima)" quand une donnée existe, ou une explication
  honnête de son absence (BarthHaas seul / variété non couverte) quand le
  houblon matche catégoriquement un descripteur de la roue sans avoir de
  donnée quantitative pour lui — jamais silencieux sur ce qui pilote
  l'ordre.

  **GUI — heatmap shadée par intensité.** `_descriptor_heatmap` passait
  d'une teinte binaire (présent/absent) à 7 états : `absent` (fond neutre,
  inchangé) / `no data` (gris neutre, présent côté `hop_descriptors` mais
  sans intensité mesurée pour ce houblon précis — jamais confondu avec une
  vraie valeur basse) / 5 paliers de bleu croissant (0-20 à 80-100,
  discrétisé plutôt qu'un dégradé continu Vega, pour rester lisible sur une
  petite cellule de grille). Réutilise `h["intensity"]` déjà chargé par
  `matching.by_descriptor` pour le tri — aucune requête supplémentaire.
  Vérifié en direct : sur une base réelle, les descripteurs hors des 15
  catégories de la roue (ex. "pine"/"grapefruit", vocabulaire BeerMaverick)
  s'affichent bien en gris "no data" sur toute la ligne plutôt qu'en bleu
  inventé.

  **Addendum (même jour, retour utilisateur immédiat après usage réel) —
  revirement de méthodologie : le filtre catégorique et le score
  quantitatif étaient UNIONNÉS dans un seul ensemble `selected`, donc un
  houblon ne recoupant QUE des termes de la roue (ex. tropical/citrus/
  floral) pouvait ressortir mélangé PARMI des houblons recoupant un
  descripteur texte plus précis (ex. "papaya") choisi explicitement par
  l'utilisateur.** Signalé en direct : "the qualitative textual descriptor
  is not a priority over the wheel aroma descriptor selected... I think we
  should separate the textual descriptor above, pre-select all hops having
  this descriptor and then score the hops that match this based on the
  average score of the wheel descriptor inputed". `matching.by_descriptor`
  restructuré avec un DEUXIÈME paramètre `wheel_descriptors` (optionnel,
  distinct du premier `selected`) : `selected` (texte, multiselect à 104
  termes) est désormais le SEUL filtre catégorique dès qu'il est non-vide —
  un houblon DOIT recouper au moins un descripteur texte pour apparaître ;
  `wheel_descriptors` (pills) ne filtre plus RIEN, il sert uniquement à
  NOTER (moyenne d'intensité) les houblons déjà retenus par le texte.
  Repli explicite conservé : si AUCUN descripteur texte n'est choisi
  (seulement des pills roue cochées), `wheel_descriptors` sert alors AUSSI
  de filtre catégorique — sinon rien ne filtrerait du tout. GUI : la
  caption de la section pills reformulée ("scores the results above by
  measured intensity; does not filter them, except as a fallback when no
  text descriptor is chosen") pour rendre ce rôle explicite. Vérifié en
  direct sur données réelles : descripteur texte "papaya" + pills
  [tropical, citrus, floral] → exactement les 4 houblons portant
  réellement "papaya" (Idaho 7®, Ekuanot®, Azacca™, Mosaic®), chacun noté
  par son intensité moyenne sur les 3 axes de la roue (ex. Idaho 7® :
  81/100) — plus aucun houblon "roue seule" mélangé dans les résultats.

  **Second addendum (même jour) — heatmap scindée en deux sections +
  couleur "présent" corrigée.** Retour utilisateur immédiat après usage
  réel : "could you however separate descriptors from quantitative aroma
  wheel values in two section in the heatmap? Also replace the grey for
  the presence of the descriptor by a black color because it look like
  NaNs". `_descriptor_heatmap` (renommé en interne, factorisé via
  `_heatmap_chart`) construit désormais DEUX grilles distinctes à partir du
  même `ranked`/`shown` : une pour les descripteurs du vocabulaire roue à
  15 catégories (`intensity_vocab`, nouveau paramètre), une pour tous les
  autres (BarthHaas/Yakima/BeerMaverick, ex. "pine"/"grapefruit" —
  structurellement JAMAIS de donnée quantitative, quel que soit le
  houblon) — mélanger les deux laissait croire qu'un descripteur
  catégorique-only était juste un houblon hors couverture Yakima plutôt
  qu'une impossibilité de principe. Chaque section ne s'affiche que si
  elle contient au moins un descripteur (`None` sinon). Palier "présent
  sans donnée quantitative" recoloré de gris (`#b0aca5`) à noir plein
  (`#000000`) — le gris se lisait comme un NaN/valeur manquante, pas comme
  "présent" ; même palette/légende réutilisée dans les deux sections pour
  rester cohérente. Vérifié en direct : sur une sélection réelle, la
  section "Aroma wheel descriptors" montre citrus/tropical/floral/etc. en
  dégradé de bleu, la section "Other descriptors" (fruity/pine/grapefruit/
  mandarin...) entièrement en noir plein ou fond neutre, jamais de bleu
  (cohérent : ces descripteurs n'ont structurellement aucune intensité
  mesurée possible).

- [x] **T56 — `contrast` : houblon attendu introuvable même au plafond de
  résultats (demande utilisateur, 2026-08-19)**

  Signalé : "If I put mango as descriptor or Tropical, I should have spicy as
  complementary note. Hence I should find the Saaz hop amongst results, why
  it's not the case even if I increase the number of results?"

  **Investigation.** `reference.CONTRAST_AFFINITY["tropical"]` (et `["mango"]`)
  = `["resinous", "dank", "spicy"]` — la cible d'affinité INCLUT bien "spicy".
  Requête directe sur la base réelle : Saaz recoupe bien "spicy"
  (`contrast_via: ["spicy"]`, score 33.3 = 1 descripteur recoupé sur 3) — donc
  `matching.contrast` identifiait déjà correctement Saaz comme un match
  valide. Le problème n'était PAS la logique de matching, mais le CLASSEMENT :
  sur "tropical", 91 houblons recoupent la cible sur la base réelle, dont 84
  à égalité au score minimal (33.3, un seul des 3 descripteurs recoupé) — le
  score n'a que 3-4 valeurs discrètes possibles (`100 * |recoupés| /
  |cible|`), donc des égalités massives sont la norme, pas l'exception. Sans
  second critère de tri, l'ordre à l'intérieur d'une égalité dépendait de
  l'itération SQL de `hops` (aucun `ORDER BY`, donc ni alphabétique ni
  pertinent) — Saaz tombait à la position ~74 par pur hasard d'ordonnancement,
  hors de portée du plafond GUI (30, avant ce correctif).

  **Corrigé.** `matching.contrast` trie désormais à trois niveaux : (1) score
  (nb de descripteurs cible recoupés, inchangé, PRIORITAIRE), (2) `total_oil`
  réconcilié desc (même proxy d'intensité aromatique qu'`by_descriptor`, pas
  une valeur inventée), (3) `variety` asc (déterminisme total en cas
  d'égalité complète). Ceci rend le classement REPRODUCTIBLE et EXPLICABLE
  au lieu d'arbitraire, mais ne garantit PAS qu'un houblon donné dans une
  égalité massive de score apparaisse dans les `top` premiers — c'est un
  vrai classement par pertinence relative (score d'abord), pas une garantie
  d'exhaustivité. D'où un second correctif, complémentaire :
  `matching.contrast` retourne désormais aussi `total_matches` (nombre TOTAL
  de houblons recoupant la cible AVANT troncature à `top`) ; la GUI
  (`app._contrast`) affiche une légende explicite ("Showing 8 of 91 hops
  overlapping this target — raise 'Number of results'...") dès que
  `total_matches > len(ranked)`, plutôt que de laisser la troncature
  silencieuse — honnêteté d'abord, même principe que la couverture
  moléculaire faible ou les molécules orphelines ailleurs dans le projet.
  Plafond du curseur "Number of results" relevé de 30 à 100 (la cible
  n'ayant souvent que 3-4 descripteurs, un plafond bas ne suffit pas à sortir
  un match "un seul recoupement" d'une égalité de plusieurs dizaines de
  houblons sur une base réelle).

  **Effet de bord sur les tests existants.** Le nouveau tri secondaire par
  `total_oil` a inversé l'ordre relatif de `mosaic`/`simcoe` (ex-aequo à
  score 20.0 sur "citrus,floral" dans les fixtures : simcoe 1.75 >
  citra 1.7 > mosaic 1.625 ml/100g) — un test de `contrast_blend`
  (`test_contrast_blend_mixes_relevance_and_pairing_not_pure_frequency`)
  dépendait de cet ordre implicite pour démontrer que la pertinence l'emporte
  sur la fréquence BeerMaverick brute ; mis à jour pour utiliser le NOUVEL
  ordre de pertinence (simcoe > citra > mosaic) sans changer l'intention du
  test (toujours : le plus pertinent gagne, malgré une fréquence de pairing
  plus basse).

  Vérifié en direct sur données réelles : "tropical" → 91 houblons au total,
  Saaz visible dès que le curseur "Number of results" est relevé (position
  ~74 sur 91, dans le nouveau tri déterministe par total_oil).

- [x] **T57 — `contrast` : cible d'affinité modifiable par l'utilisateur
  (demande utilisateur, 2026-08-19, suite directe de T56)**

  Signalé : "I think we should orient the complementary aroma by
  pre-selecting them but let the user chose which one he want to keep. In
  the saaz example, user could only want to find spicy as complementary
  note, we should make possible to untick dank and woody(sic, resinous),
  rather than imposing the mapping. So please make a menu below the
  Descriptor of note to contrast where we will pre-tick proposed contrast
  note but let the user modify them to obtain another result."

  **Contexte.** T56 (même jour) avait déjà résolu la DÉCOUVRABILITÉ de Saaz
  (tri déterministe + plafond de résultats relevé + transparence de
  troncature), mais la cible d'affinité elle-même restait entièrement
  imposée par `reference.CONTRAST_AFFINITY` — pour "tropical", toujours les
  3 descripteurs dank+resinous+spicy, sans moyen de restreindre à un seul.
  Ce ticket donne à l'utilisateur le contrôle direct sur CETTE cible.

  **`matching.py`.** Nouveau `contrast_affinity_target(descriptors) ->
  (target, unmapped)` : factorise le calcul auto (déjà présent dans
  `contrast()`) hors de la fonction, pour que la GUI puisse l'appeler AVANT
  de lancer la recherche et afficher la proposition. `contrast()` et
  `contrast_blend()` gagnent un paramètre `target_descriptors: list[str] |
  None = None` : quand fourni, REMPLACE entièrement le calcul automatique
  (`unmapped` reste calculé sur les descripteurs de la NOTE, indépendamment
  de la cible retenue ensuite — c'est une info sur la note, pas sur la
  cible). `None` (par défaut) = comportement inchangé, rétrocompatible pour
  le CLI et tout appel direct qui ignore ce raffinement. Nouvelle constante
  `CONTRAST_CORE_CATEGORIES` (calculée depuis `CONTRAST_AFFINITY.values()`,
  jamais d'autres valeurs possibles dans la carte — maillage fermé à 10
  catégories) exposée pour que `app.py` n'ait pas besoin d'importer
  `reference` directement (respect de la frontière architecturale existante
  : app.py n'importe que `matching`/`schema`).

  **GUI (`app._contrast`).** Nouvelle section `st.pills` (sélection
  multiple) sous "Descriptors of the note to contrast", listant les 10
  catégories cœur, pré-cochées avec la proposition automatique
  (`contrast_affinity_target`) mais librement modifiables — untick pour
  exclure une catégorie proposée, coche pour en ajouter une non proposée.
  `key` du widget dérivée des descripteurs de note actuellement sélectionnés
  (`contrast_target_pills_{tuple(sorted(selected))}`) : Streamlit ne
  réinitialise un widget à son `default` que si sa `key` change, donc
  changer les descripteurs de note RECALCULE la proposition (nouvelle
  pré-sélection fraîche), tandis qu'une modification manuelle de
  l'utilisateur survit aux reruns tant que les descripteurs de note ne
  changent pas eux-mêmes. La sélection résultante (`target_selected`) est
  propagée à la fois à `matching.contrast` (tableau de résultats) ET
  `matching.contrast_blend` (proposition de blend) — les deux visent
  toujours exactement la même cible, jamais recalculée séparément.

  **Vérifié en direct sur données réelles.** "tropical" propose
  dank/resinous/spicy (91 houblons recoupés au total, score max 100 pour
  qui recoupe les 3). Décocher dank+resinous (ne garder que "spicy")
  ramène la cible à 78 houblons recoupés — mais TOUS à score 100 désormais
  (un seul terme cible possible à recouper), au lieu d'un mélange dilué
  33.3/66.7/100 sur la cible à 3 termes. Saaz devient alors trouvable en
  relevant simplement le curseur "Number of results" (T56, plafond 100) —
  plus besoin de deviner sa position dans une égalité massive à 3 termes,
  et le choix de cible reflète directement l'intention réelle de
  l'utilisateur plutôt qu'une carte d'affinités imposée.

- [x] **T58 — Nouvel outil GUI "Compare Hops" (demande utilisateur, 2026-08-19)**

  Inspiré de https://beermaverick.com/hops/hop-comparison-tool/ (mentionné par
  l'utilisateur comme référence de fonctionnalité, PAS de design à copier
  telle quelle). Cinquième mode GUI (aux côtés d'amplify/contrast/
  by-descriptor/browse).

  **Sélection.** Multiselect jusqu'à 5 houblons (`st.multiselect(...,
  max_selections=5)`). Chaque houblon sélectionné reçoit une couleur fixe et
  cohérente sur TOUS les graphiques de la page (même couleur sur le radar
  et les deux barplots) — palette CATÉGORIELLE, pas divergente : "Spectral"
  (suggéré par l'utilisateur) est une palette ColorBrewer DIVERGENTE (pensée
  pour un gradient autour d'un centre neutre), pas adaptée à 5 houblons sans
  ordre naturel entre eux. Recommandation : `alt.Scale(scheme="tableau10")`
  (intégré à Vega-Lite/Altair, pas de dépendance supplémentaire), 5 premières
  teintes — moderne, distinctif, conçu pour du nominal/catégoriel. À
  confirmer/ajuster visuellement à l'implémentation (vérifier lisibilité
  dans les deux thèmes clair/sombre, même contrainte que le reste de la GUI).

  **Radar/spider chart (roue d'arôme).** Superposition de jusqu'à 5 polygones
  (un par houblon sélectionné, couleur cohérente avec le reste de la page) sur
  les mêmes 15 axes que `_aroma_wheel` (`hop_aroma_intensity`, T26, Yakima
  uniquement, 0-100 réel). **Ne contredit PAS la décision T4 (radar écarté
  pour `by-descriptor`)** : T4 comparait des descripteurs BINAIRES
  (présence/absence, où l'aire déforme sans apporter d'info) — ici les axes
  sont des intensités QUANTITATIVES réelles sur un vocabulaire fixe, exactement
  le cas d'usage pour lequel un radar overlay est justifié (et ce que fait
  BeerMaverick lui-même sur cette page). Honnêteté d'abord : un houblon
  sélectionné sans couverture Yakima (pas de `hop_aroma_intensity`) doit être
  signalé explicitement (pas de polygone silencieusement absent, ni de valeurs
  à 0 fabriquées) — légende ou caption dédiée.

  **Barplot 1 — infos principales.** %AA, %BA, co-humulone, huile totale
  (ml/100g) — les 4 champs déjà mis en avant par `_render_key_stats`
  (`alpha_acid`, `beta_acid`, `co_humulone`, `total_oil`). **Piège d'unités
  signalé explicitement par l'utilisateur** : `co_humulone` est stocké en
  "% des acides alpha" (`pct`, mais une fraction DE `alpha_acid`, pas une
  fraction du houblon total) — pas directement comparable en barres à côté de
  %AA/%BA (qui SONT des fractions du houblon total) ni de `total_oil` (ml/100g,
  unité physique différente). Conversion nécessaire AVANT affichage :
  `co_humulone_abs_pct = alpha_acid_pct * (co_humulone_pct_of_AA / 100)` — ainsi
  %AA/%BA/co-humulone-absolu partagent une seule échelle "%", `total_oil`
  (ml/100g) reste sur un second axe. Implémentation Altair : chart en couches
  (`alt.layer(...).resolve_scale(y="independent")`), pas un simple
  `mark_bar` — Vega-Lite ne fait pas de double axe nativement sur une seule
  couche.

  **Barplot 2 — infos détaillées.** Tous les autres composés de
  `hop_composition` (hors les 4 "principaux" ci-dessus, cf.
  `app._NON_AROMA_DISPLAY`) : myrcene, humulene, caryophyllene, farnesene,
  linalool, geraniol, beta-pinene, selinene, thiols, isobutyrate, ketones.
  **Piège d'unités supplémentaire découvert en vérifiant la base réelle
  (l'utilisateur n'avait signalé le problème que pour le barplot 1)** :
  `thiols` est stocké en `ug_kg` (µg/kg), TOUS les autres composés de cette
  liste sont en `pct_oil` (% de l'huile totale) — mélanger thiols dans le
  même axe que les autres écraserait visuellement sa barre (ordres de
  grandeur incompatibles, ex. thiols ~0.06 µg/kg vs myrcène ~40% d'huile).
  Même traitement à prévoir : soit un second axe dédié pour `thiols`
  (comme le barplot 1), soit l'exclure de ce barplot et l'afficher à part
  (à trancher à l'implémentation — vérifier d'abord combien des 5 houblons
  sélectionnés ont réellement une mesure de thiols avant de décider si ça
  vaut la complexité d'un second axe ici aussi).

  **Reste à trancher à l'implémentation (pas bloquant pour le ticket)** :
  emplacement exact dans le layout (page dédiée vs section), tri des barres
  (alphabétique vs par valeur), affichage des houblons sans donnée pour un
  compound donné (barre à 0 vs absente vs "no data" — cohérent avec le
  traitement déjà établi ailleurs dans la GUI, jamais une valeur inventée).

  **Implémenté et vérifié en direct (2026-08-19).** Nouveau mode `app._compare`
  (5e outil, carte dédiée en page d'accueil), `st.multiselect(...,
  max_selections=5)`. Palette `_COMPARE_PALETTE` = 5 premières teintes
  tableau10 (`#4c78a8, #f58518, #e45756, #72b7b2, #54a24b`), un dict
  `{nom affiché -> couleur}` construit UNE fois et réutilisé tel quel dans
  les 3 graphiques (`alt.Scale(domain=..., range=...)` explicite partout,
  pas de dépendance à l'ordre implicite d'un domaine partagé). Radar
  (`_aroma_wheel_compare`, généralisation multi-houblons de `_aroma_wheel` —
  grille/spokes/labels calculés une fois, un polygone par houblon avec
  `color`+`detail` sur `Hop`) : houblons sans `hop_aroma_intensity` exclus
  du polygone et listés explicitement dans une caption "No quantitative
  aroma wheel data for: ..." (jamais une valeur à 0 fabriquée). Barplot 1
  (`_compare_principal_values` + `_compare_dual_axis_barplot`) : co-humulone
  converti en % absolu (`alpha_acid_pct * co_humulone_pct_of_AA / 100`),
  `alt.layer(...).resolve_scale(y="independent")` avec un `scale.domain`
  EXPLICITE et identique sur `x` dans les deux couches (indispensable :
  chaque couche ne reçoit qu'un SOUS-ENSEMBLE des 4 champs, sans domaine
  explicite partagé les groupes de barres se désalignent entre couches).
  Barplot 2 (mêmes helpers, réutilisés) : liste fixe de 10 composés `pct_oil`
  + `thiols` (`ug_kg`) sur son propre axe secondaire, exactement le second
  piège d'unité anticipé dans ce ticket — confirmé en direct que sans ce
  traitement la barre thiols (~0.06) aurait été invisible à côté du myrcène
  (~40%). Composés absents de TOUS les houblons sélectionnés exclus du
  domaine `x` (pas de colonne vide). Vérifié en direct dans le navigateur
  (Citra/Mosaic/Simcoe) : radar superposé avec légende, barplot 1 à double
  axe (% à gauche, ml/100g à droite), barplot 2 à double axe (% d'huile à
  gauche, µg/kg thiols à droite) — tout rendu correctement, couleurs
  cohérentes hop-par-hop sur les 3 graphiques. Choix de layout tranchés :
  page dédiée (pas une section d'un autre mode) ; barres dans l'ordre fixe
  de la liste (pas de tri par valeur, cohérent avec le radar qui a lui
  aussi un ordre d'axe fixe) ; donnée absente = barre/axe omis, jamais 0.

  **Addendum — lisibilité des labels d'axe X (signalé par l'utilisateur le
  même jour, immédiatement après vérification de T58).** Deux problèmes :
  (1) barplot 1, le label "Co-humulone (% of hop)" tronqué en "Co-humulone
  (% …" ; (2) barplot 2, un label sur deux invisible à l'angle par défaut
  (-20°), chevauchement masqué silencieusement par `labelOverlap` de
  Vega-Lite plutôt que rendu qui se recouvre.
  Pour (1), suggestion utilisateur d'insérer un `\n` avant "(%..." dans le
  libellé — **insuffisant seul, vérifié en direct** : le JSON de la spec
  Vega-Lite contient bien le vrai caractère de saut de ligne (confirmé via
  `chart.to_dict()`), mais l'axe restait tronqué sur une seule ligne. Cause
  réelle : le mark texte d'axe de Vega-Lite ne coupe PAS automatiquement sur
  un `\n` littéral dans une chaîne — il faut lui fournir un TABLEAU de
  lignes. Corrigé en ajoutant `axis.labelExpr: "split(datum.label, '\\n')"`
  (convertit la chaîne en tableau au moment du rendu) + `axis.labelLineHeight`
  (espacement entre les lignes) + `axis.labelLimit=200` (pour ne plus jamais
  tronquer avant même d'atteindre le saut de ligne) dans
  `app._compare_dual_axis_barplot`. Pour (2), angle porté à -45° (`label_angle`
  nouveau paramètre de `_compare_dual_axis_barplot`, passé explicitement
  `label_angle=-45` au barplot 2 seulement — le barplot 1 garde -20°, ses
  4 libellés courts n'en ont pas besoin) ; `labelAlign="right"` +
  `labelBaseline="middle"` déjà présents (ajoutés lors de l'implémentation
  initiale, cf. docstring de la fonction) assurent l'alignement du label
  pivoté avec son tick, indépendamment de l'angle choisi. Vérifié en direct
  dans le navigateur (Citra/Mosaic/Simcoe) : "Co-humulone (% of hop)"
  s'affiche désormais sur deux lignes complètes sous son tick ; les 5
  labels du barplot 2 (myrcene, caryophyllene, linalool, beta-pinene,
  ketones) sont tous visibles et correctement alignés à -45°. Suite pytest
  (197 tests) verte après ce correctif, aucune régression.

  **Second addendum — le premier correctif jugé insuffisant par l'utilisateur
  ("No you didn't fix the issue, I think it's worse"), 4 points corrigés le
  même jour.** (1) **Radar trop petit / "narrow"** : le radar utilisait
  `width="content"` avec une largeur Vega-Lite FIGÉE à 480px, tandis que les
  deux barplots utilisaient `width="stretch"` (remplissage du conteneur,
  potentiellement bien plus large) -- trois graphiques, trois stratégies de
  largeur incohérentes entre elles. Corrigé en unifiant sur une largeur
  numérique EXPLICITE et PARTAGÉE (`app._COMPARE_CHART_WIDTH = 700`),
  appliquée identiquement aux 3 `properties(width=...)` (radar carré
  700×700, les deux barplots 700×320) et rendue partout avec
  `width="content"` (jamais "stretch", qui écraserait cette largeur
  explicite). Nécessaire pour le radar : son domaine x/y est QUANTITATIF et
  géométriquement carré (coordonnées calculées à la main, voir
  `_aroma_wheel_compare`) -- un simple passage à `width="stretch"` sans
  ajuster la hauteur en proportion aurait déformé les polygones (cercle →
  ellipse), d'où le choix d'une largeur fixe partagée plutôt qu'un
  redimensionnement responsive. (2) **Angle différent entre les deux
  barplots** : le premier correctif avait laissé le barplot 1 à -20° (par
  défaut) et seulement forcé -45° sur le barplot 2 via un paramètre
  `label_angle` -- incohérent d'un graphique à l'autre. Le paramètre est
  retiré, remplacé par une constante unique `_COMPARE_LABEL_ANGLE = -45`
  appliquée aux deux. (3) **"FORCE THE DISPLAY OF ALL LABELS"** : cause
  racine non traitée par le premier correctif -- Vega-Lite masque par
  défaut un label qu'il calcule comme chevauchant son voisin
  (`labelOverlap`, valeur implicite non désactivée jusqu'ici). Ajouté
  `axis.labelOverlap=False` (force l'affichage de TOUS les labels, quitte à
  un léger chevauchement visuel à forte densité de catégories -- préférable
  à un label silencieusement absent, même principe d'honnêteté que le reste
  de la GUI). (4) **"Total oil (ml/100g)" sur 2 lignes, comme Co-humulone"**
  (retour utilisateur explicite) : `_compare_principal_values` renvoie
  désormais `"Total oil\n(ml/100g)"` (même mécanisme `labelExpr: split()`
  que Co-humulone, aucun code supplémentaire nécessaire). Vérifié en direct
  dans le navigateur (Citra/Mosaic/Simcoe) : radar large occupant toute la
  largeur du conteneur, alignée pixel-perfect avec les deux barplots en
  dessous ; barplot 1 -- "Co-humulone (% of hop)" ET "Total oil (ml/100g)"
  sur deux lignes complètes, angle -45° ; barplot 2 -- les 10 labels
  (myrcene, humulene, caryophyllene, farnesene, linalool, geraniol,
  beta-pinene, isobutyrate, ketones, thiols) TOUS visibles au même angle
  -45°, alignés avec leurs ticks. Suite pytest (197 tests) verte, aucune
  régression.

  **Troisième addendum — surlignage au survol du radar (demande utilisateur,
  2026-08-19).** "Would it be possible ... to highlight the line when the
  user mouseover one of the line?" `_aroma_wheel_compare` gagne un
  `alt.selection_point(fields=["Hop"], on="mouseover", nearest=True)`
  (`hover`), attaché à `points` (cibles d'accroche -- cercles pleins, plus
  faciles à survoler précisément qu'un simple trait) et référencé en
  CONDITION dans `polygon_line`, layer SŒUR de la même composition `layer`
  -- pattern standard Vega-Lite (un paramètre de sélection déclaré sur une
  couche reste visible aux couches sœurs). Premier essai : opacité 0.15
  pour les houblons non survolés -- **jugé pire par l'utilisateur** ("all
  the non mouseover lines are not visible... not hide the other") : corrigé
  en remontant à 0.55 (clairement visible, mais visuellement en retrait par
  rapport au houblon survolé à opacité pleine + trait 2.5x plus épais [2→5]
  + points 2.2x plus gros [50→110]). **Limite documentée et assumée** (pas
  de contournement tenté) : passer le trait survolé visuellement AU-DESSUS
  des autres (vrai z-index) n'est PAS possible en Vega-Lite déclaratif --
  un `mark_line` multi-séries (`detail="Hop:N"`) compile en UN SEUL mark
  Vega dont l'ordre d'empilement des sous-tracés est figé à la compilation
  par l'ordre du domaine `color` ; il n'existe pas de canal d'encodage
  Vega-Lite pour un z-index RÉACTIF au survol (le canal `order` ne contrôle
  que l'ordre des points LE LONG d'un même tracé, pas l'empilement entre
  tracés -- un vrai z-index dynamique demanderait de redescendre en Vega
  bas niveau, hors de portée d'Altair). Compensé par le contraste fort
  (opacité + épaisseur) plutôt qu'un vrai passage au premier plan --
  suffisant en pratique avec ≤5 houblons aux couleurs bien distinctes.
  `clear="mouseout"` ajouté pour réinitialiser l'état par défaut en
  quittant le radar. Vérifié en direct dans le navigateur (Citra/Mosaic) :
  survol d'un point -- le houblon le plus proche (`nearest=True`) passe en
  trait épais/opacité pleine, l'autre reste net à 0.55 (plus jamais quasi
  invisible) ; tooltip inchangé (Hop/Descriptor/Intensity). Suite pytest
  (197 tests) verte, aucune régression.

- [x] **T59 — Retirer ®/™ du DÉBUT des noms de houblon (demande utilisateur,
  2026-08-19)**

  Signalé : "I see some ® or ™ in the name of some results of hop. Could
  you remove this from the name at the beginning to avoid having them and
  allow proper merging of multiple sources?"

  **À vérifier avant d'implémenter (pas encore fait à l'écriture de ce
  ticket)** : les cas déjà connus/corrigés dans ce projet (`_fix_barthhaas_
  trademark_slug`, `_strip_yakima_brand_suffix`) concernent des ® /™ COLLÉS
  À LA FIN d'un mot ou dans un slug d'URL (ex. "Citra®" → slug `citrar`,
  "Mosaic® Brand" → nom affiché) — jamais un symbole EN DÉBUT de nom
  affiché. Avant de coder quoi que ce soit : lister les houblons réels de
  la base dont `name` commence par `®`/`™` (`SELECT variety, name FROM hops
  WHERE name LIKE '®%' OR name LIKE '™%'`) pour confirmer le motif exact et
  la ou les source(s) concernée(s) (BarthHaas ? Yakima ? les deux ?) — même
  méthodologie que pour tous les autres correctifs de nommage de ce projet
  (jamais corriger sur la seule base d'une supposition, voir T51/T53 pour
  les précédents). Le lien avec "allow proper merging of multiple sources"
  suggère que le symbole en tête empêche la clé de réconciliation
  (`ingest._normalize_hop_key`/`_find_variety_by_name_region`) de matcher
  deux entrées qui devraient fusionner — à confirmer en reproduisant un cas
  concret avant de corriger.

  **Vérifié en direct puis implémenté (2026-08-19).** Aucun houblon réel
  n'avait le symbole EN TOUTE PREMIÈRE position (`SELECT ... WHERE name LIKE
  '®%'` : 0 résultat) — "at the beginning" relu comme "dès le départ /
  systématiquement", pas "en position 0" : 62 houblons réels portent ®/™
  ailleurs dans le nom (ex. "Citra®", "El Dorado® Hops"), cohérent avec le
  reste du message ("remove this... to avoid having them"). Nouveau
  `parsers.strip_trademark_symbols` (retire `[®™©]`, recollapse les espaces
  — même mécanisme que `_strip_yakima_brand_suffix`, T51), appliqué à LA
  SOURCE : `parsers.parse_yakima_hit` (après le retrait de "Brand") et
  `ingest.crawl_barthhaas` (sur `h1_title`) — jamais seulement à
  l'affichage GUI. Confirmé que `_normalize_hop_key` (réconciliation
  BeerMaverick) retirait déjà ces symboles pour SA clé interne, mais
  `hops.name` et la comparaison brute de `_find_variety_by_name_region`
  (T53) les gardaient — un houblon dont le symbole différerait entre
  BarthHaas et Yakima pouvait donc échapper à la fusion cross-source, exactement
  le risque signalé par l'utilisateur. Réingestion réelle (`crawl-barthhaas`
  + `crawl-yakima`) : 0/189 houblons avec ®/™/© restant, aucune régression
  de comptage (194→189 déjà stable depuis T53, aucun houblon perdu ni
  dupliqué par ce correctif). Vérifié qu'aucune NOUVELLE collision de nom
  n'a été introduite par la suppression du symbole au-delà des 4 paires déjà
  connues et gérées par T60 (Amarillo/Perle/Saaz/Northern Brewer).

- [x] **T60 — Doublon "Northern Brewer" dans `contrast` : dédoublonnage par
  couverture d'info plutôt que par région (demande utilisateur, 2026-08-19)**

  Signalé : "I see Northern Brewer twice in the result of contrast:mango, it
  has different values and one purpose is bittering while the other is
  infered:bittering. please investigate this issue and remove duplicates. I
  guess if both are actually in yakima we should select the one with the
  higher coverage of information (here the purpose is missing in one of
  them)."

  **Investigation faite (2026-08-19, en direct sur la base réelle).**
  Confirmé : `northern-brewer` (région "United States", `sources='yakima'`,
  `purpose='bittering'` RÉEL BeerMaverick, 8 descripteurs dont 3
  BeerMaverick, 11 lignes de composition) et `northern-brewer-nob03`
  (région "Germany", `sources='yakima'` aussi, `purpose=None` → affiché
  "Inferred: Bittering", 4 descripteurs Yakima seulement, 11 lignes de
  composition) — mêmes valeurs de composition très proches mais PAS
  identiques (alpha_acid 7-10% vs 6-10%, co_humulone 30-34% vs 27-32%...).
  Root cause identique à Amarillo/Perle/Saaz déjà documentée en T53/T54 :
  Yakima catalogue CE cultivar sous deux `variety_code` distincts
  (`NOB01`/`NOB03`) cultivés dans deux pays différents (vérifié en direct
  sur l'API Algolia à l'époque de T53) — PAS un artefact de crawl, un choix
  déclaré de la source elle-même. BeerMaverick (purpose + descripteurs
  enrichis) ne s'est réconcilié qu'avec UNE seule des deux entrées
  (`northern-brewer`), laissant l'autre avec une couverture d'info
  nettement plus pauvre — c'est CE déséquilibre que l'utilisateur observe
  concrètement ("higher coverage of information").

  **Tension avec la décision T53/T54 à trancher avant d'implémenter.** T53
  avait explicitement choisi de NE PAS fusionner Amarillo/Perle/Saaz/
  Northern Brewer (contrairement à Challenger/Fuggle/Hallertauer Tradition/
  Hersbrucker Spät/Target, de VRAIS doublons de slug pour la MÊME région) :
  fusionner aurait perdu une vraie distinction de terroir confirmée par la
  source elle-même. L'utilisateur propose maintenant un critère différent
  ("si les deux sont dans yakima, garder celui avec la meilleure couverture
  d'info") qui REVIENT à fusionner ces paires quand elles partagent une
  source unique — à confirmer explicitement avec l'utilisateur avant
  implémentation, car ça inverse une décision déjà prise et documentée : la
  région (donc potentiellement la composition réelle) diffère, fusionner
  perd cette info même si l'un des deux est mieux enrichi côté
  BeerMaverick/descripteurs.

  **Complication vérifiée en direct, à ne pas ignorer si le critère
  "couverture d'info" est retenu** : il n'est PAS uniformément cohérent sur
  les 4 paires connues. Saaz et Perle : un côté domine clairement sur tous
  les axes (composition + descripteurs + purpose). **Amarillo est un cas
  CONFLICTUEL** : `amarillo` (US, multi-source barthhaas+yakima) a PLUS de
  lignes de composition (20 vs 11, grâce à la fusion barthhaas) mais MOINS
  de descripteurs (5 vs 16) et pas de purpose réel, alors que
  `amarillo-brand-ama04` (Allemagne, yakima seul) a un purpose réel ET 16
  descripteurs mais moins de composition — un simple "score de complétude"
  devra définir explicitement quel(s) axe(s) comptent (composition ?
  descripteurs ? purpose ? une pondération des trois ?) plutôt que supposer
  qu'un côté domine toujours l'autre.

  **Si retenu (après confirmation utilisateur)**, mécanisme envisageable :
  réutiliser `ingest.merge_hop_varieties` (déjà écrit pour T53, generic
  "fusionner deux variety keys") avec un critère de sélection du survivant
  basé sur une fonction de score de couverture (nb de sources, nb de
  descripteurs, présence d'un purpose réel, nb de compounds) plutôt que sur
  "BarthHaas toujours primaire" (règle actuelle, qui ne s'applique pas ici
  puisque les deux côtés sont `yakima` seul).

  **Décision utilisateur (2026-08-19, tranche la tension ci-dessus) :**
  "you either need to remove duplicate or modify the name base on the
  provenance. I suggest to drop it if it's not easy to retrieve the origin
  (terroir)." La provenance (région) est FACILE à retrouver -- déjà dans
  `hops.region`, vérifiée en direct via l'API Algolia (ci-dessus, T53/T54) --
  donc modification du nom retenue, PAS suppression : ces paires restent
  deux crops réels distincts, jamais fusionnées.

  **Implémenté.** Nouveau `matching._disambiguate_hop_names(hops)` (privé),
  appliqué UNE FOIS à l'intérieur de `load()` -- la seule source de `hops`
  pour TOUT le reste (amplify/contrast/by_descriptor/blends/CLI/GUI) : "Foo"
  x2 avec régions différentes devient "Foo (Region A)"/"Foo (Region B)" EN
  PLACE, sans code de désambiguïsation répété ailleurs. Pas de suffixe
  fabriqué si la région manque d'un côté (filet de sécurité testé). Ancien
  `app._disambiguated_hop_labels` (T53, ne couvrait QUE le sélecteur Browse)
  retiré -- redondant, `_browse` utilise directement `hops[v]["name"]`
  désormais. Vérifié en direct sur données réelles : `contrast --descriptors
  mango` affiche bien "Northern Brewer (United States)" et "Northern Brewer
  (Germany)" comme deux lignes distinctes et lisibles (au lieu de deux
  "Northern Brewer" indiscernables), même chose pour "Amarillo (Germany)"
  dans la même liste de résultats -- aucun changement de comportement pour
  la structure des blends (toujours basée sur le purpose RÉEL, jamais
  affecté par ce renommage d'affichage).

- [x] **T61 — `contrast` : filtre par purpose (aromatic/bittering), pré-coché
  sur les deux (demande utilisateur, 2026-08-19)**

  Signalé : "In the contrast tool, we should add another menu for purpose,
  it would be pre-selecting both bittering and aromatic but we should let
  user add a filter on this purpose."

  Même esprit que T57 (menu de cible d'affinité pré-coché mais modifiable) :
  nouveau `st.pills`/`st.multiselect` sous (ou à côté de) la section cible
  d'affinité de `app._contrast`, options = les valeurs de purpose EFFECTIF
  affichées ailleurs dans la GUI (`matching.resolve_purpose` : "aromatic",
  "bittering", "both" — voir aussi si "both" doit compter comme
  aromatic+bittering simultanément ou comme une 3e case à part, à décider à
  l'implémentation), pré-coché sur `["aromatic", "bittering"]` (donc "both"
  inclus par défaut puisqu'il satisfait les deux, à confirmer). Filtre les
  lignes de `r["ranked"]` (résultat de `matching.contrast`) après résolution
  du purpose (réel ou inféré, `_row_with_purpose`/`matching.resolve_purpose`
  — déjà utilisé pour l'affichage) avant rendu du tableau — ATTENTION :
  `total_matches`/la troncature `top` sont calculés AVANT ce filtre côté
  `matching.contrast` (qui ne connaît pas le purpose désiré par l'utilisateur
  pour le tri) ; un filtrage purement côté GUI après coup fausserait le
  message de troncature (T56) et pourrait masquer des résultats qui
  auraient dû apparaître avant le plafond `top` -- probablement nécessaire
  de faire remonter ce filtre dans `matching.contrast` lui-même (nouveau
  paramètre, même pattern que `target_descriptors` en T57) plutôt que de
  filtrer après coup côté GUI, pour que `total_matches`/le tri/la
  troncature restent cohérents avec ce que l'utilisateur voit réellement.

  **Implémenté et vérifié en direct (2026-08-19), exactement comme
  anticipé.** `matching.contrast`/`contrast_blend` gagnent un paramètre
  `purposes: list[str] | None = None` -- `None` (défaut) = comportement
  inchangé, rétrocompatible CLI. Le filtre est appliqué DANS la boucle de
  construction de `ranked` (avant le calcul de `total_matches` et la
  troncature à `top`), en résolvant le purpose EFFECTIF de chaque houblon
  via `resolve_purpose` (réel BeerMaverick, ou inféré depuis l'acide alpha)
  — exactement ce que la GUI affiche déjà par ligne. Nouveau
  `_purpose_matches_filter` : un houblon "both" satisfait le filtre dès
  qu'AU MOINS un des deux rôles est demandé (jamais une 3e case séparée) ;
  un purpose totalement inconnu (ni réel ni inférable) est exclu dès qu'un
  filtre est actif. GUI (`app._contrast`) : `st.pills` sous la section
  cible d'affinité (T57), pré-cochée sur `["aromatic", "bittering"]`,
  propagée à la fois au tableau de résultats ET au blend proposé (même
  cible, même filtre partout). Vérifié en direct sur données réelles :
  "mango" → 91 matches (les deux purposes) ; décocher "bittering" → 74
  matches, chaque ligne restante affichant "Aromatic" ou "Aromatic +
  Bittering", plus aucune ligne "Bittering" seule.

- [x] **T62 — Définitions des 15 catégories de la roue d'arôme, tooltip au
  survol de chaque label (demande utilisateur, 2026-08-19)**

  Point de départ : signalement que "grassy", "herbal" et "vegetal"
  semblaient redondants dans le radar Compare Hops ("in my mind grassy,
  herbal and vegetal mean the same thing: it's the taste of fresh herb").
  Investigation en plusieurs passes AVANT tout changement de code
  (`hop_aroma_intensity` reste 100% Yakima, confirmé deux fois par requête
  SQL directe -- aucune fusion BarthHaas en jeu) :
  - Corrélation `vegetal`/`grassy` mesurée sur les 81 houblons réels à
    `vegetal>0` : Pearson r=0.16 (faible), écart absolu moyen 13.8 points,
    seulement 30% des houblons à moins de 5 points d'écart -- Saaz est le
    contre-exemple le plus net (grassy=75, vegetal=8, écart de 67 points).
    Conclusion à ce stade : PAS une redondance systématique malgré quelques
    houblons où ça se ressemble (Mosaic, Citra).
  - Site public actuel de Yakima Chief (yakimachief.com, vérifié en direct
    sur `/variety/saaz-saz01`) : AUCUN radar/roue d'arôme affiché
    publiquement, seulement une courte liste de badges ("Aroma Profile" --
    5-6 termes, ex. Saaz : Spicy/Earthy/Floral/Grassy/Woody), qui correspond
    exactement à `hop_descriptors` (source=yakima, 38 termes) -- jamais
    "vegetal" dedans. Donc "vegetal" vient d'un champ Yakima plus profond
    (`aroma_values`/`sensory_values`, T26) jamais rendu publiquement par
    Yakima elle-même -- pas une invention hopmatch, mais une donnée Yakima
    peu visible ailleurs.
  - **Source qui a tranché la question** : le "Hop Sensory Ballot" officiel
    de Yakima Chief (`Hop_Sensory_Ballot_V2.pdf`, révisé juin 2021 --
    l'URL directe sur yakimachief.com est cassée depuis leur migration de
    site, récupéré via Wayback Machine, capture du 2024-06-27). Ce document
    liste NOMMÉMENT les 15 catégories de `hop_aroma_intensity` (+ 2 de plus,
    "Onion/Garlic" et "Dank", absentes de notre vocabulaire à 15) avec leurs
    "Specific Aromas" par catégorie -- confirme que grassy/herbal/vegetal
    sont TROIS notions réellement distinctes dans le vocabulaire officiel
    Yakima, pas une redondance perçue à tort : **Grassy** = green
    grass/hay (herbe fraîchement coupée, végétal SEC) ; **Herbal** = black
    tea/dill/green tea/mint/rosemary/thyme (herbe AROMATIQUE culinaire) ;
    **Vegetal** = cabbage/celery/green pepper/tomato plant (légume, souvent
    un signal de prudence en brassage). Confirme aussi, en creusant : la
    catégorie "Pomme" (notre alias → "apple") N'EST PAS une coquille
    française du CMS Yakima comme documenté précédemment (`CLAUDE.md`,
    `reference.DESCRIPTOR_ALIASES`) -- c'est le terme professionnel
    standard de dégustation pour "fruits à pépins" (pomme/poire), utilisé
    tel quel dans LEUR PROPRE document officiel en anglais. Commentaire
    corrigé dans `reference.py` en conséquence (l'alias d'affichage
    "apple" lui-même n'a pas changé, toujours plus clair pour un public
    GUI non spécialiste).

  **Implémenté.** `reference.AROMA_WHEEL_DEFINITIONS` (nouveau) : dict des
  15 catégories → définition sourcée sur le ballot officiel, ré-exporté via
  `matching.AROMA_WHEEL_DEFINITIONS` (même pattern que
  `CONTRAST_CORE_CATEGORIES` -- `app.py` n'importe jamais `reference`
  directement). Demande utilisateur explicite pour l'affichage : "(?) close
  to each label name, displaying the description of this specific note when
  mouseovering it" (option retenue, plutôt qu'un unique (?) global) --
  implémenté nativement en Vega-Lite plutôt qu'une icône (?) positionnée à
  la main sur 15 positions radiales : le mark `text` des labels d'axe
  (`_aroma_wheel`/`_aroma_wheel_compare`) gagne un champ `Definition` sur
  ses données + `tooltip=["Descriptor:N", "Definition:N"]` sur son
  encodage -- Vega-Lite affiche déjà nativement une infobulle au survol de
  n'importe quel mark ayant un canal `tooltip`, donc survoler UN SEUL label
  affiche SA définition précise, sans DOM/JS custom. Fonctionne aussi sur
  un axe à intensité 0 (testé sur Saaz US, apple/vegetal à 0) puisque le
  mark texte reste présent même quand le polygone n'atteint pas cet axe.
  Caption de découvrabilité ajoutée sous CHAQUE rendu de roue (4 emplacements
  -- `_browse`, `_hop_detail_expanders` [partagé Amplify+Contrast],
  `by-descriptor`, `_compare`) : "Hover a label for its definition (Yakima
  Chief Hop Sensory Ballot)." -- sans ça, une infobulle pure au survol
  n'est pas découvrable. Vérifié en direct : survol de "vegetal" sur Saaz
  (CZ et US) affiche bien "Cabbage, celery, green pepper, tomato plant —
  savory vegetable notes, often a caution flag in brewing", et de même pour
  chacun des 15 labels sur Browse/Compare Hops. Suite pytest (197 tests)
  verte, aucune régression.

- [x] **T63 — Revue de code complète post-T52/T62, 6 défauts corrigés
  (demande utilisateur, 2026-08-20)**

  "Do a massive review of the codebase to find any redundancies, errors or
  inconsistencies after all these changes." Relecture méthodique des ~7400
  lignes (`app.py`/`matching.py`/`reference.py`/`ingest.py`/`parsers.py`/
  `schema.py`/`cli.py`/tests), croisée avec `pyflakes` pour la détection
  mécanique de code mort. 6 défauts vérifiés (pas de spéculation, chacun
  confirmé sur le code réel/git blame/DB en direct) :

  1. **`_NON_AROMA_DISPLAY` dupliqué à l'identique dans `app.py` ET
     `matching.py`** (même set, même usage dans 3 comprehensions) --
     contraire au principe déjà suivi cette session pour
     `CONTRAST_CORE_CATEGORIES`/`AROMA_WHEEL_DEFINITIONS` (une seule
     définition, ré-exportée). Corrigé : renommé `matching.NON_AROMA_DISPLAY`
     (public, sans underscore, cohérent avec les deux autres ré-exports),
     copie `app.py` supprimée, 3 usages + 2 commentaires repointés vers
     `matching.NON_AROMA_DISPLAY`.
  2. **`ingest.py` : `n_curated` calculé mais jamais lu** dans
     `ingest_foodb` (confirmé pré-existant, juillet 2026 -- un print qui le
     consommait a été retiré sans retirer l'assignation). Ligne morte
     supprimée.
  3. **`tests/test_matching.py` : assertion manquante** dans
     `test_pairing_top_n_excludes_low_ranked_partners` -- `second` calculé
     depuis le premier appel `contrast_blend` (comportement par défaut,
     `pairing_top_n=10`) mais jamais vérifié ; seule la variante manuelle
     (`pairing_top_n=0`) était testée. Le chemin par défaut n'avait donc
     aucune couverture malgré les apparences. Assertions ajoutées
     (`second["variety"] == "mosaic"`, `second["via"] == "pairing"`),
     vérifiées vertes.
  4. **`app._browse` : `hcomp = comp.get(selected, {})` calculé deux fois**
     (lignes ~897 et ~934) sans rien entre les deux qui puisse le faire
     changer. Deuxième calcul, mort, supprimé.
  5. **`reference.AROMA_WHEEL_DEFINITIONS` (T62, sans aucun test)** : rien
     ne vérifiait la chaîne de ré-export `reference` -> `matching`, ni que
     ses 15 clés restent synchronisées avec le vocabulaire réel de
     `hop_aroma_intensity` (actuellement synchronisées, vérifié en direct
     sur la base, mais sans garde-fou pour un futur re-crawl Yakima qui
     renommerait/ajouterait une catégorie -- le tooltip se viderait alors en
     silence, `matching.AROMA_WHEEL_DEFINITIONS.get(d, "")`). Deux tests
     ajoutés : identité de ré-export (`is`), et couverture exacte des 15
     catégories documentées.
  6. **`matching.by_descriptor` sans équivalent de `total_matches`**,
     contrairement à `contrast` (T56, qui l'a ajouté précisément pour ce
     problème : Saaz invisible au plafond `top` sans compteur explicite).
     `by_descriptor` départage déjà ses égalités de façon déterministe (pas
     le même bug racine que T56), mais la GUI n'avait aucun moyen d'afficher
     « showing N of M » plutôt que de tronquer en silence. Corrigé --
     **changement de contrat le plus large de cette revue** : `by_descriptor`
     retourne désormais `{"ranked": [...], "total_matches": N}` au lieu
     d'une liste nue (même forme que `contrast`/`amplify`). Répercuté sur
     TOUS les appelants : `cli._print_by_descriptor` (+ message de
     troncature en CLI), `app._by_descriptor` (+ caption de transparence,
     même libellé que `contrast`), et les 12 sites d'appel direct dans
     `tests/test_matching.py` (`["ranked"]` ajouté partout, + 1 nouveau test
     `test_by_descriptor_total_matches_counts_before_truncation`).

  Vérifié en direct : `pyflakes` sur tout `src/`+`tests/` ne relève plus
  rien (2 warnings avant, dont un seul pré-existant à cette session) ;
  navigateur réel -- `by-descriptor` sur "citrus" affiche "Showing 10 of
  122 hops overlapping these descriptors — raise..." ; CLI (`hopmatch
  by-descriptor citrus --top 3`) affiche le même compte (122) en français.
  Suite pytest : 197 -> 200 tests (3 nouveaux : total_matches, 2x
  AROMA_WHEEL_DEFINITIONS), tous verts, aucune régression.

- [x] **T64 — Déploiement Streamlit Community Cloud : bootstrap de la base
  distante, dépendances de déploiement, contact licence dans l'app
  (2026-08-20, demande utilisateur)**

  Point de départ : l'utilisateur veut déployer sur Streamlit Community
  Cloud (gratuit), sans que l'app re-télécharge/reconstruise la base à
  chaque réveil, tout en réduisant l'exposition légale liée aux données
  non-commerciales (FooDB/FlavorDB2, CC BY-NC-SA). Signalé au passage que
  "these DB are build by the app on the fly" -- **vérifié FAUX** :
  `app.py` est en lecture seule contre une base déjà construite (aucun
  chemin de code ne construit/télécharge quoi que ce soit avant ce
  ticket) ; sur un conteneur Community Cloud frais (système de fichiers
  éphémère, reconstruit à chaque réveil après veille), l'app échouait
  simplement avec "Database not found".

  **Vérifié avant tout changement** : `git ls-files | grep -Ei
  '\.(db|sqlite3?|json|csv|tsv|parquet)$'` renvoie déjà vide -- aucun
  fichier de données n'est commité dans le dépôt public (`.gitignore`
  exclut déjà `*.db`, `data/foodb_*/`, `data/*.csv`), donc rien à corriger
  de ce côté.

  **Mécanisme retenu** (voir aussi la réponse détaillée donnée à
  l'utilisateur dans la conversation) : construire la base UNE FOIS en
  local (pipeline CLI existant, inchangé), l'héberger à part dans un dépôt
  GitHub PRIVÉ (pas le dépôt de code, public), et faire télécharger CE
  seul fichier par l'app à son démarrage si absent -- jamais de
  re-scraping BarthHaas/Yakima/BeerMaverick ni de re-téléchargement du
  dump FooDB (~950 Mo) depuis le conteneur déployé (trop lent pour un
  réveil utilisateur, et un scraping systématique répété depuis une IP
  cloud partagée risquerait un blocage/rate-limit côté sources).

  **Implémenté (`app.py`)** : `_fetch_remote_db(db_path)`, décoré
  `@st.cache_resource` (pas juste le test `os.path.exists` de l'appelant :
  plusieurs sessions utilisateur peuvent atteindre `main()` en parallèle
  sur un conteneur fraîchement réveillé, le cache partagé garantit un seul
  téléchargement réel). Lit `DB_DOWNLOAD_URL`/`DB_DOWNLOAD_TOKEN` depuis
  `st.secrets` (jamais commités, configurés dans le tableau de bord
  Streamlit Cloud), interroge l'API Contents de GitHub (`Authorization:
  Bearer <token>`, `Accept: application/vnd.github.v3.raw` -- fonctionne
  sur un dépôt privé, contrairement à `raw.githubusercontent.com`).
  **Piège découvert en testant en direct** : `st.secrets.get(clé)` NE SE
  COMPORTE PAS comme un dict -- sans AUCUN `secrets.toml` du tout (cas du
  développement local), il **lève** `StreamlitSecretNotFoundError`
  (sous-classe d'`OSError`) plutôt que de renvoyer `None` ; capturé
  largement (`except Exception`) pour que l'absence de configuration
  distante reste un simple "rien à faire ici", jamais une exception qui
  casserait le rendu de la page. Câblé dans `main()` : tentative de
  téléchargement seulement si le fichier est absent, message d'erreur
  existant conservé en dernier repli (mentionne désormais aussi les deux
  clés de secrets attendues).

  **Dépendances de déploiement corrigées au passage** (nécessaires pour
  que le déploiement fonctionne du tout, pas juste pour ce mécanisme) :
  `pyproject.toml` `dependencies = []` (base) signifie qu'un simple `pip
  install .` n'installe RIEN, pas même streamlit -- ajout d'un
  `requirements.txt` à la racine (`-e .[ui]`, détecté automatiquement par
  Streamlit Cloud) qui réutilise l'extra `[ui]` existant plutôt que de
  dupliquer des bornes de version. `pillow` (utilisé directement par
  `app.py` via `from PIL import Image` pour l'image de fond) manquait de
  l'extra `[ui]` -- fonctionnait en local uniquement parce que `streamlit`
  le tire lui-même en dépendance transitive (vérifié via `pip show
  streamlit`), corrigé en le déclarant explicitement plutôt que de
  compter sur cet effet de bord. Commentaire d'installation du README
  ("cœur (numpy, scipy)") était stale -- aucun import numpy/scipy nulle
  part dans `src/` (scipy servait à l'ancien `combine()`/NNLS, retiré le
  2026-08-12) -- corrigé.

  **Contact licence visible dans l'app elle-même**, pas seulement dans
  `README.md`/`LICENSE` (déploiement public sur des données en partie
  non-commerciales — la personne concernée par un signalement regarde
  l'app déployée, pas nécessairement le dépôt GitHub associé) : caption
  sous le lien GitHub de la sidebar, "Code MIT · data licenses ·
  quentin4313@gmail.com" (les deux derniers en lien cliquable).

  **Ce qui reste à faire côté utilisateur** (hors de portée de l'outil --
  création de compte/dépôt/jeton) : créer le dépôt GitHub privé pour la
  base, y pousser `aromahops.db`, générer un jeton d'accès personnel
  fine-grained en lecture seule sur ce seul dépôt, déployer le dépôt de
  code (public) sur Streamlit Community Cloud, et configurer
  `DB_DOWNLOAD_URL`/`DB_DOWNLOAD_TOKEN` dans les secrets de l'app
  déployée. Voir le message à l'utilisateur pour les étapes détaillées.

  Vérifié en direct : (1) chemin d'échec -- base absente + secrets
  configurés vers une URL invalide -- affiche l'erreur réseau proprement
  puis retombe sur le message "Database not found" existant, aucune
  exception non gérée ; (2) chemin normal (base déjà présente en local)
  inchangé, vérifié sur la vraie base (189 houblons) ; (3) lien
  GitHub + caption licence visibles en tête de sidebar. 4 tests unitaires
  ajoutés pour `_fetch_remote_db` (déjà présent, secrets absents, secrets
  partiels, téléchargement réussi avec un `urlopen` simulé). Suite pytest
  200 -> 204, tous verts.

## Sources de données additionnelles (recherche)

- **Investigué à nouveau, PAS retenu — Hopsteiner (shop.hopsteiner.com)**.
  Re-vérifié en direct : le site a changé depuis la première investigation
  (audit du 2026-08-03, qui décrivait un Magento à slugs lisibles) — ce n'est
  plus le cas aujourd'hui (`/hop-varieties/cascade/` → 404). Nouvelle
  plateforme e-commerce à ID produit opaques (`/all-products/shop/hop-pellets/
  12475204.html`). Le contenu utile est toujours là sur une fiche produit —
  alpha/beta/co-humulone/huile totale, ET une vraie liste courte de
  descripteurs par tags (`aroma/citrus`, `aroma/floral`... pas une prose) —
  mais **la page catégorie ne liste que 18 produits en HTML statique** (pas
  de sitemap.xml, pas de pagination visible, aucune trace d'API de recherche
  publique type Algolia/Klevu/Searchspring dans le HTML) contre les ~98
  variétés attendues : la majorité du catalogue est très probablement
  chargée en JS après coup (pagination/scroll infini côté client), ce qui
  demanderait un navigateur headless plutôt qu'un simple crawl HTTP — un
  cran de fragilité au-dessus de BarthHaas (HTML statique) et même de Yakima
  (API JSON publique). Toujours AUCUN détail myrcène/humulène/caryophyllène
  par variété (vérifié sur la fiche produit récupérée), donc toujours
  seulement une 3e source de `hop_descriptors`, jamais de `hop_composition`
  au-delà de ce que 2 sources couvrent déjà. Effort en hausse, valeur
  inchangée (modeste) : décision inchangée, mais pour une raison plus forte
  qu'avant — ne pas reconsidérer sans un changement structurel du site
  (sitemap, API publique retrouvée) ou un besoin réel de 3e corroboration
  des descripteurs.

- **Investigué, initialement PAS retenu, puis RÉEXAMINÉ ET RETENU (T25, 2026-08,
  décision utilisateur) — BeerMaverick** (beermaverick.com). Verdict initial :
  endpoint JS interne trouvé (`/api/js/?hop=<id>`) mais explicitement documenté
  par eux comme "internal use" (pas d'accès public officiel) ; de plus, c'est un
  agrégateur (compile depuis la littérature producteur, pas une mesure labo
  indépendante) — sous le niveau de confiance de BarthHaas/Yakima. Pas de
  scraping tant que ces deux réserves n'étaient pas levées.
  **Réserve d'accès levée à la revérification** : la donnée qui motivait cette
  investigation (pairings + substitutions) est en fait DÉJÀ dans le HTML statique
  servi normalement par chaque page `beermaverick.com/hop/{slug}/` — pas besoin
  de l'endpoint interne du tout, `robots.txt` autorise tout, sitemap public.
  **Réserve de qualité maintenue mais pas bloquante** : toujours un agrégateur,
  pas une mesure de labo — affiché en GUI avec cette réserve systématiquement,
  jamais mélangé aux couches de score. Voir `docs/DATA_SOURCES.md` pour le
  détail complet de l'implémentation retenue (`ingest.ingest_beermaverick`).

- **Investigué, PAS retenu — John I. Haas "Hops Companion"**
  (johnihaas.com, PDF). Contient de vraies tables de composition par
  variété, mais c'est un PDF statique (extraction de tableau fragile, pas
  re-crawlable facilement, difficile à vérifier automatiquement comme les
  sources HTML/JSON actuelles). Piste à garder pour un futur effort dédié,
  pas dans ce backlog.

- **Investigué, PAS retenu — MotlerHops.fr**. Revendeur français, pas un
  producteur/labo. Vérifié sur une fiche produit réelle (Citra) : alpha acid
  seul comme donnée chiffrée, descripteurs en PROSE marketing (même piège
  que BarthHaas actuel), pas de détail myrcène/humulène/etc. Aucune valeur
  ajoutée vs les sources déjà intégrées.

## Méthodologie (optionnel, si temps disponible)

- [x] **T10 — `combine()` : parcimonie gloutonne sous-optimale**
  L'ancienne méthode (NNLS complet, garder les `max_hops` plus gros poids,
  re-résoudre dessus) n'est pas une recherche du meilleur sous-ensemble — juste
  une heuristique. Ajout d'une seconde heuristique, une **sélection gloutonne
  avant** (matching pursuit : à chaque étape, ajouter le houblon qui réduit le
  plus le résidu sur le sous-ensemble déjà choisi, jusqu'à `max_hops`), et
  `combine()` garde désormais celle des deux qui minimise le résidu réel —
  jamais un remplacement pur et simple (aucune des deux heuristiques n'est
  optimale ni dominante ; mesuré sur un échantillon de 80 notes réelles :
  la seule gloutonne fait mieux dans ~20 % des cas mais MOINS bien dans
  quelques cas). Coût mesuré sur la base réelle (203 houblons) : jusqu'à
  ~280ms pour `max_hops=6` sur la note la plus défavorable — acceptable pour
  un usage interactif CLI/GUI. Non-régression : `tests/test_combine.py`
  contient un cas adversarial construit par recherche aléatoire où l'ancienne
  heuristique seule choisirait un sous-ensemble strictement pire (résidu 0.71
  vs 0.51) que la nouvelle décision "meilleur des deux".

  **Addendum 2026-08-12 — `combine()` retiré entièrement (décision utilisateur).**
  Cette amélioration restait correcte, mais mesurée sur les 506 notes réelles :
  0 % ne dépassaient 20 % de couverture (max 12 %, médiane 1,3 %) — la chimie de
  l'huile de houblon ne recoupe simplement pas la plupart des arômes alimentaires.
  Pire, sur les notes à un seul composé « producible » (la majorité), NNLS dégénère
  en système à une seule équation : n'importe quel houblon porteur atteint un
  résidu artificiel de 0, une fausse confiance sans rapport avec la couverture
  réelle (observé en direct : "strawberry" et "passion fruit" retournaient tous
  deux "100% Talus, résidu 0.0", géraniol étant le seul composé commun aux deux
  notes sur toute la base). `tests/test_combine.py` supprimé avec la fonction —
  voir CLAUDE.md et l'historique git pour le détail complet.
