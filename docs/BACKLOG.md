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
