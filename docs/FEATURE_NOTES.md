# Notes de fonctionnalités (backlog)

Idées capturées en conception, à implémenter (probablement via Claude Code).

## Découverte par descripteurs  *(demandé par l'utilisateur)*

**Statut : implémenté** (`matching.by_descriptor`, CLI `hopmatch by-descriptor` /
`hopmatch descriptors`, tests dans `tests/test_matching.py`). Le reste de cette
section documente les décisions de spec prises à l'implémentation.

**But UX.** Présenter à l'utilisateur une liste curée de descripteurs de goût
(le vocabulaire d'arôme). Il en sélectionne un ou plusieurs → l'app liste les
houblons correspondants, chacun avec **ses descripteurs d'arôme ET ses molécules**.

**Pourquoi c'est solide (et différent du mode contraste).** Le vocabulaire et les
correspondances viennent des roues d'arôme réelles (`hop_descriptors`, données
BarthHaas/Yakima), PAS du prior `CONTRAST_AFFINITY` que j'ai inventé. Donc cette
feature est **grounded** et n'a besoin ni de la carte d'affinités ni de FooDB. Elle
est implémentable dès maintenant sur la base existante.

**Comportement.**
1. Vocabulaire proposé = `SELECT DISTINCT descriptor FROM hop_descriptors ORDER BY 1`
   (la liste réelle des descripteurs présents dans la base).
2. L'utilisateur choisit 1..n descripteurs.
3. Résultat = houblons dont `hop_descriptors` recoupe la sélection, classés par :
   1) nombre de descripteurs recoupés (desc), 2) `total_oil` réconcilié (desc, valeur
   `hop_composition` moyenne des sources — proxy d'intensité aromatique en l'absence
   d'autre signal de pertinence), 3) `variety` (asc, pour un ordre déterministe en cas
   d'égalité totale).
4. Pour chaque houblon affiché : ses descripteurs + ses composés (`hop_composition`,
   valeur réconciliée + sources, triés par valeur réconciliée décroissante), pour
   donner « arômes ET molécules ».

**Interface proposée.**
- CLI : `hopmatch by-descriptor citrus,tropical`
  et `hopmatch descriptors` pour lister le vocabulaire disponible.
- Fonction : `matching.by_descriptor(con, selected: list[str], top=10)` renvoyant
  `[{variety, name, matched_descriptors, all_descriptors, compounds, sources}]` où
  `compounds = [{compound, mid, unit, sources}]` (même forme que `matching.load()`,
  pas de nouvelle convention de sortie).
- Nouveau mode, plus SIMPLE que amplify/contrast/combine (pas de note requise).

**Normalisation des descripteurs (prérequis, pas juste une note d'intention).**
Vérifié sur les fixtures actuelles : `parse_descriptors` minuscule déjà tout, aucune
variante pluriel/espacement en conflit sur les 4 houblons de fixture. Le risque reste
réel dès qu'on élargit (crawl_barthhaas déjà réel sur ~90 variétés, crawl_yakima à
venir) : « stone fruit » vs « stonefruit », « citrus » vs « citrus fruit », etc.
Décision : ajouter `reference.DESCRIPTOR_ALIASES` (dict variante -> forme canonique,
amorce curée à enrichir au fil des ingestions réelles) et l'appliquer dans
`ingest._ingest_variety` juste avant l'écriture dans `hop_descriptors` (pas dans
`parsers.parse_descriptors`, qui reste un parseur brut sans connaissance métier).

**Notes.**
- Idéal pour une future UI (cases à cocher sur le vocabulaire).
- Ne dépend pas des scaffolds (FooDB, Yakima crawl) : bon premier ticket Claude Code.
