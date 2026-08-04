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

- [ ] **T4 — Aucune visualisation graphique**
  L'app est 100% tableaux. Ajouter un graphique radar (roue d'arôme) pour
  comparer visuellement les descripteurs de 1-3 houblons — candidat naturel
  pour `by-descriptor`/`amplify`. (Skills requis avant d'y toucher :
  `developing-with-streamlit`, `dataviz`.)

- [ ] **T5 — Pas de mode "parcourir la base"**
  Impossible d'explorer un houblon (composition + descripteurs + sources)
  sans passer par amplify/combine/by-descriptor. Ajouter un mode de
  recherche/consultation direct.

- [ ] **T6 — Pas de stats base en barre latérale**
  Aucune indication du nombre de houblons/notes/descripteurs chargés, ni de
  fraîcheur de la base — utile puisque la construction se fait uniquement
  en CLI, hors de la vue de l'utilisateur GUI.

- [ ] **T7 — `_notes`/`_descriptors` sans cache**
  Requêtées à chaque rerender Streamlit (500+ notes). `st.cache_data` réduirait
  la latence perçue sur une interaction typique.

- [ ] **T8 — top-N non ajustable sur amplify/contrast**
  `by-descriptor` a un slider "nombre de résultats" ; `amplify`/`contrast`
  sont figés à 8. Incohérent, à harmoniser.

## Sources de données additionnelles (recherche)

- [ ] **T9 — Hopsteiner (shop.hopsteiner.com), à évaluer plus avant**
  Vérifié en direct : HTML servi côté serveur (Magento), ~98 variétés en
  pellets, alpha/beta/co-humulone/huile totale + une liste courte de
  descripteurs (pas une prose comme BarthHaas actuellement). PAS de détail
  myrcène/humulène/caryophyllène par variété sur la page produit vérifiée
  (Cascade) — n'alimenterait donc PAS `hop_composition` au-delà de
  alpha/beta/total_oil (déjà couverts par 2 sources), seulement une 3e
  source de `hop_descriptors`. Valeur modeste vs effort d'intégration
  (nouveau slug-matching, tests, vérif anti-corruption comme Admiral/Yakima) :
  à faire seulement si le temps le permet après le reste du backlog.

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

- [ ] **T10 — `combine()` : parcimonie gloutonne sous-optimale**
  Résout le NNLS complet puis garde les `max_hops` meilleurs poids — pas une
  vraie recherche du meilleur sous-ensemble. Avec le gain de perf de T1, un
  essai sur quelques sous-ensembles candidats (au lieu d'un seul) devient
  abordable. Valeur moyenne, à ne considérer qu'en fin de backlog.
