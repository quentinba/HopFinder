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
