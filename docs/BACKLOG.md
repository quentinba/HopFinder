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

- **Investigué, PAS retenu — BeerMaverick** (beermaverick.com). Endpoint JS
  interne trouvé (`/api/js/?hop=<id>`) mais explicitement documenté par eux
  comme "internal use" (pas d'accès public officiel) ; de plus, c'est un
  agrégateur (compile depuis la littérature producteur, pas une mesure labo
  indépendante) — sous le niveau de confiance de BarthHaas/Yakima. Cohérent
  avec la mention déjà présente dans README ("agrégé, sans API... non
  implémenté"). Pas de scraping tant que ces deux réserves ne sont pas levées.

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
