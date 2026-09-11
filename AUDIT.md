# AUDIT — HopFinder (hopmatch)

Audit en lecture seule, 2026-09-10. Aucun fichier de code modifié.

> ⚠ **Trois prémisses du brief d'audit sont fausses** — vérifié avant de commencer,
> parce qu'elles orientaient une partie des questions vers du code qui n'existe pas :
> 1. **« moteur de blending basé sur NNLS »** — il n'y a **aucune NNLS** dans ce projet.
>    `combine()` (NNLS) a été implémenté puis **retiré le 2026-08-12** pour dégénérescence
>    mesurée (`matching.py:13-21`, `docs/ARCHITECTURE.md:122`). Aucune dépendance scipy.
>    Les blends actuels (`contrast_blend`/`amplify_blend`) sont un mélange
>    pertinence + fréquence de pairing réelle BeerMaverick, sans solveur. Les questions du
>    brief sur « conditionnement du système NNLS », « solution dégénérée », « coefficients
>    normalisés en proportions », « résidu élevé » sont donc sans objet.
> 2. **« déployée sur Render »** — le déploiement est **Streamlit Community Cloud**
>    (`requirements.txt`, `app._fetch_remote_db:710`). Aucun fichier Render.
> 3. **« SQLite multi-sources (BarthHaas, Yakima Chief, FooDB, PubChem) »** — il y a en
>    réalité **10+ sources** (voir cartographie). Cet écart n'est pas anodin : c'est
>    précisément une source non listée (hops-comptoir) qui cause le bug bloquant n°1.

---

## 1. Cartographie

**Arborescence et modules** (24 800 lignes, dont 9 900 de tests) :

| Module | Lignes | Rôle | Dépend de |
|---|---|---|---|
| `app.py` | 6 911 | GUI Streamlit, 10 modes | `matching`, `schema` |
| `ingest.py` | 3 480 | Crawlers + ingestion, 1 fonction par source | `parsers`, `schema`, `reference` |
| `matching.py` | 2 062 | **Moteur** : scoring, blends, similarité | `reference` |
| `reference.py` | 1 811 | Priors curés (affinités contraste, survie procédé, descripteurs ingrédient) | — |
| `parsers.py` | 1 398 | Parseurs HTML/JSON purs, sans I/O | — |
| `schema.py` | 624 | DDL SQLite + `validate_and_repair` | — |
| `cli.py` | 417 | Points d'entrée `hopmatch <cmd>` | tous |

Découpage propre et respecté : `app.py` n'importe **jamais** `reference`/`ingest`/`parsers`
(ré-exports explicites via `matching`, ex. `matching.AROMA_WHEEL_DEFINITIONS:1115`), et
`parsers.py` ne fait aucune I/O. Le moteur est utilisable sans la GUI (le CLI le prouve).

**Points d'entrée** : `hopmatch = hopmatch.cli:main` (build/crawl/ingest/amplify/contrast/
by-descriptor) ; `streamlit run src/hopmatch/app.py` pour la GUI.

**Base** : SQLite EAV multi-sources, **21 tables**, 7 Mo, aucun index explicite (uniquement
les auto-index de clé primaire — sans conséquence à cette taille). `aromahops.db` (produit)
et `recipes.db` (corpus MMuM brut) sont **deux fichiers séparés** qui ne communiquent qu'en
lecture. Peuplement réel constaté : 192 houblons, 2 510 lignes de composition, 506 notes,
138 descripteurs, 6 577 bins de stats de style.

Sources réellement présentes en base — `hop_composition.source` :
`barthhaas`, `yakima`, `hops-comptoir`, `hopsteiner-thiol-2024` ;
`hop_descriptors.source` : + `beermaverick`. Plus, dans d'autres tables : FooDB, Flavornet,
FlavorDB2, PubChem, beer-analytics.com, BJCP, MMuM.

**Chemin d'une requête** (Amplify) :
`main():6750` → `_db_path():682` → `_fetch_remote_db():710` (Cloud) → `_connection():753`
(nouvelle connexion **par rerun** — choix correct et documenté, sqlite3 n'est pas
thread-safe entre reruns Streamlit) → `_amplify(con)` → `matching.amplify():1047` →
`load():80` (réconciliation multi-sources) + `get_note():259` → `molecular_scores():918` +
`descriptor_overlap():966` → tri → `_render_hop_rows():1360` (`st.dataframe` +
`column_config`).

**Tests** : 604 tests, 5 fichiers, tous verts. Ils testent réellement (pas du smoke) :
parseurs sur fixtures HTML figées, invariants d'ingestion, déterminisme du tri, et
non-régression de plusieurs bugs historiques nommés. **Faille structurelle** : les fixtures
(`data/fixtures/`) ne contiennent que **barthhaas** et **yakima** — la diversité de sources
de la vraie base n'est pas représentée, donc aucun test de `matching` ne peut voir un
conflit d'unités inter-sources (cf. bug B1).

**Déploiement** : Streamlit Community Cloud, `requirements.txt` = `-e .[ui]` ; base
construite en local puis téléchargée au démarrage depuis un dépôt GitHub privé via
`st.secrets`. Dépendances **non épinglées** (bornes basses seulement : `streamlit>=1.50`).

---

## 2. Synthèse — les 5 points les plus importants

1. **[BLOQUANT] Le classement moléculaire d'`amplify` est faux depuis l'ajout de la source
   française.** `matching.amount():242` renvoie la valeur brute pour toute unité ≠ `pct_oil`.
   Les 5 variétés hops-comptoir publient linalol/géraniol/farnésène en **mg/100 g** (≈ 1 000×
   l'échelle ml/100 g des autres). Mesuré : **232/258 notes (90 %) ont un houblon français en
   #1**, et **240/258 (93 %) changent de #1** si on retire ces valeurs. Ce n'est pas un
   problème des seuls houblons français : la normalisation par composé écrase **tous les
   autres houblons à ~0**.
2. **[BLOQUANT] La documentation décrivait l'invariant que ce bug viole**, et personne ne l'a
   vu : `README.md:543` dit « quantité = (% d'huile / 100) × huile totale (ou **valeur brute
   pour les thiols en µg/kg**) ». C'était vrai tant que les thiols étaient la seule unité
   étrangère. T134 en a ajouté une seconde sans revisiter ni la doc, ni `amount()`.
3. **[IMPORTANT] `amplify` n'a aucun départage d'égalité**, contrairement à `contrast` et
   `by_descriptor` qui en ont un explicite et documenté. En mode « Descriptors » (le défaut
   GUI), les scores ne prennent que 3-4 valeurs distinctes : sur `strawberry`, **11 houblons
   ex æquo à 66,7** dont on n'en affiche que 8, choisis par l'ordre des lignes SQLite.
4. **[IMPORTANT] Le « Score » affiché n'est pas interprétable et n'est pas comparable d'une
   requête à l'autre** : c'est un rang relatif renormalisé par le meilleur houblon de *cette*
   requête (`mmax`, `matching.py:1082`). Rendu en `ProgressColumn` 0-100 (`app.py:1401`) sans
   `help=` ni note — le premier houblon fait toujours 100.
5. **[IMPORTANT] La popover « Database » ment par omission** (`app.py:6847`) : elle nomme 7
   sources et en oublie 4 réellement utilisées (hops-comptoir, Hopsteiner, beer-analytics,
   MMuM). Sur un projet dont le principe affiché n°1 est « toujours rapporter la provenance »,
   c'est le seul écran qui prétend lister les sources et il est incomplet.

Le reste du projet est d'un niveau inhabituellement élevé : séparation des couches stricte,
604 tests réels, refus systématique de fabriquer une donnée manquante, et une traçabilité des
décisions (CLAUDE.md + docstrings) meilleure que la moyenne des projets de cette taille.

---

## 3. Bugs

### B1 — [BLOQUANT] Mélange d'unités dans `amount()` : le scoring moléculaire est faux

> ✅ **CORRIGÉ le 2026-09-10** (lots 2 puis 1, option (a) du §7 validée : exclusion +
> mention à l'écran). `matching.SCORING_ABSOLUTE_UNITS` + `unit_excluded_measurements`,
> chip « N hop(s) not scorable here » en Amplify. Vérifié sur la base réelle :
> **0/258 notes** ont encore un houblon `mg_100g` en #1 (était 232/258), et
> `strawberry` redonne Talus 100 / Cryo Pop 96,6 / Nectaron 94,2 au lieu de
> Barbe Rouge 100 / Elixir 60 / reste à 0,2. 4 tests de non-régression ajoutés,
> 608 tests verts. Le diagnostic ci-dessous est conservé tel qu'écrit en phase 1.

**Fichier** : `src/hopmatch/matching.py:242-249`, exploité par `molecular_scores():938,953`.

```python
def amount(variety, molecule, comp) -> float:
    rec = comp.get(variety, {}).get(hop_compound(molecule))
    if not rec or rec["mid"] is None: return 0.0
    if rec["unit"] == "pct_oil":
        oil = comp.get(variety, {}).get("total_oil")
        return (rec["mid"] / 100.0) * ((oil["mid"] if oil else 1.0) or 1.0)
    return rec["mid"]        # <-- toute autre unité passe BRUTE
```

`return rec["mid"]` était correct tant que la seule autre unité était `ug_kg` (thiols, jamais
dans le même axe que les composés d'huile). T134 (2026-09-08) a introduit `mg_100g` pour
linalol/farnésène/géraniol sur 5 variétés — **les mêmes noms de composés** que ceux mesurés
en `pct_oil` par BarthHaas/Yakima.

**Reproduction** (base réelle, `aromahops.db`) :

```
elixir       farnesene  mid=175.000 unit=mg_100g  -> amount() = 175.0
citra        farnesene  mid=  0.425 unit=pct_oil  -> amount() =   0.007225
barbe-rouge  geraniol   mid= 12.500 unit=mg_100g  -> amount() =  12.5
talus        geraniol   mid=  1.800 unit=pct_oil  -> amount() =   0.031   (le vrai max)
```

`molecular_scores` normalise ensuite par `max_amt[m]` = max sur **tous** les houblons
(`matching.py:938`), puis `s = w * (a / max_amt[m]) * spec[m]` (`:956`). Le maximum du
géraniol passe de 0,031 à 12,5 : la contribution géraniol de **tous les autres houblons**
tombe à ~0,25 % de sa valeur réelle. L'axe entier est annihilé.

**Effet mesuré sur les 258 notes ayant un classement moléculaire :**

| Mesure | Résultat |
|---|---|
| Notes dont le #1 est un houblon français `mg_100g` | **232 / 258 (90 %)** |
| Notes dont le #1 change si on exclut `mg_100g` | **240 / 258 (93 %)** |

Exemples : `strawberry` → Barbe Rouge au lieu de Talus ; `anise` → Barbe Rouge au lieu de
Bravo ; `apple` → Barbe Rouge au lieu de Cryo Pop.

**Visible à l'écran** — Amplify → « strawberry » → « Molecular only » :
Barbe Rouge **100,0**, Elixir **60,0**, puis Brewers Gold / Centennial / Krush / Cryo Pop /
Ekuanot / HBC 638 tous à **0,2** — toute la base écrasée par deux houblons, « via geraniol ».

**Gravité** : bloquante et silencieuse. Elle touche le cœur scientifique de l'outil, sur le
mode principal, sans aucun signal d'erreur. Elle est active en production depuis le
2026-09-08.

**Correctif proposé** : même forme que celui déjà appliqué côté affichage le 2026-09-09
(`app._COMPARE_DETAIL_ABSOLUTE_UNITS:3478`) — liste blanche explicite des unités reconnues,
et **exclusion** (retour `0.0`) de toute unité inconnue de cet axe, plutôt qu'un passage
brut. Aucune conversion mg/100 g → % d'huile ne doit être tentée : elle exigerait une densité
d'huile de houblon qui n'est sourcée nulle part dans ce projet.

⚠ Un simple `return 0.0` fait **disparaître** ces mesures du scoring. C'est le comportement
honnête (on ne sait pas les comparer), mais il faut le dire à l'écran — sinon on remplace un
faux résultat par un silence, ce que le projet s'interdit ailleurs. **Décision à trancher, cf.
§7.**

**Test qui échoue et démontre le bug** :

```python
def test_amount_never_mixes_a_foreign_unit_into_the_pct_oil_axis():
    comp = {
        "fr":  {"geraniol": {"mid": 12.5, "unit": "mg_100g"},
                "total_oil": {"mid": 2.0, "unit": "ml_100g"}},
        "usa": {"geraniol": {"mid": 1.8,  "unit": "pct_oil"},
                "total_oil": {"mid": 1.7, "unit": "ml_100g"}},
    }
    # "usa" est le houblon le plus riche en géraniol réellement comparable :
    # il doit porter le maximum de l'axe, pas être écrasé par une autre unité.
    assert matching.amount("usa", "geraniol", comp) >= matching.amount("fr", "geraniol", comp)
```

### B2 — [IMPORTANT] Même racine, propagée à `similar_hops` et à l'indice Survivables

> ✅ **CORRIGÉ le 2026-09-10**, par le même correctif que B1 (`similar_hops_by_composition`
> passe par `amount()`).

**Fichier** : `matching.py:1859` et `:1930` (`similar_hops_by_composition`, via `amount()`).

Effet mesuré sur `similar_hops_by_composition("citra")` : similarités faussées de 1 à 2 points
et interversion réelle du classement (Sabro 20,6 / Comet absent → Comet 21,1 devant Sabro
21,0 après correction). Moins spectaculaire qu'en B1 parce que le cosinus est dominé par les
autres composés, mais c'est la même racine et le même correctif la traite.

L'onglet Survivables et l'indice de précocité (`app._survivable_compound_positions_all`)
étaient touchés par le même mécanisme ; ils passent désormais par
`app._compare_detail_value`, **corrigé le 2026-09-09**. Ce correctif-là est donc déjà en
place — c'est `matching.amount()` qui ne l'a jamais reçu.

### B3 — [IMPORTANT] `amplify` : égalités départagées par l'ordre des lignes SQLite

> ✅ **CORRIGÉ le 2026-09-10** (lot 3). `amplify` utilise désormais le même tuple `_rank`
> que `contrast`/`by_descriptor` : score BRUT desc (jamais l'arrondi d'affichage, pour ne
> pas réordonner deux scores réellement différents), puis huile totale desc, puis `variety`
> asc. Les 11 ex æquo de `strawberry` sont maintenant ordonnés et reproductibles. 2 tests.

**Fichier** : `matching.py:1094` — `ranked.sort(key=lambda r: -r["score"])`, sans clé
secondaire. Le tri Python est stable → l'ordre retombe sur celui de `hops`, c'est-à-dire
`SELECT * FROM hops` **sans `ORDER BY`** (`matching.py:81`), donc l'ordre d'insertion du
crawl.

**Reproduction** : Amplify, ingrédient `strawberry`, mode « Descriptors » (le défaut GUI).
Distribution réelle des scores : `{66.7: 11 houblons, 33.3: 46 houblons}`. On affiche
**8 des 11** ex æquo ; les 3 exclus le sont sans critère. Un re-crawl dans un ordre différent
changerait le top-8 affiché sans qu'aucune donnée n'ait changé.

C'est aussi une **incohérence interne** : `contrast` (`matching.py:1738`) et `by_descriptor`
(`:1736`) ont tous deux un tuple `_rank` explicite et documenté (score, puis huile totale
desc, puis `variety` asc). `amplify` est le seul des trois à ne pas en avoir.

**Correctif** : même tuple `_rank` que ses deux jumelles.

### B4 — [MINEUR] `amount()` fabrique une huile totale par défaut

> ✅ **CORRIGÉ le 2026-09-11** (lot 5). `matching._total_oil` remplace le repli à `1.0` :
> huile totale absente, `mid` nul ou **0.0** → le composé ne participe pas (0.0) au lieu
> d'être noté sur une hypothèse. **Mesuré avant correction : 0 houblon sur 191** déclenchait
> ce repli — c'était donc un piège LATENT, pas un chiffre faux, exactement le profil qu'avait
> §B1 avant l'arrivée de hops-comptoir. Le classement réel est inchangé, vérifié.
> Le cas est rapporté par `unscorable_measurements` (ex-`unit_excluded_measurements`,
> élargie aux deux causes d'exclusion) et remonte dans le chip existant — pas de nouveau
> chemin de perte silencieuse.

**Fichier** : `matching.py:248` — `((oil["mid"] if oil else 1.0) or 1.0)`.

Si `total_oil` est inconnu, la quantité est calculée **comme si** le houblon contenait
1,0 ml/100 g. C'est une valeur inventée, en contradiction directe avec la règle affichée du
projet (« jamais une valeur fabriquée », appliquée partout ailleurs — cf.
`app._compare_detail_value` qui renvoie `None` dans exactement ce cas). Effet : un houblon
sans huile totale mesurée voit ses composés surestimés ou sous-estimés d'un facteur égal à sa
vraie huile totale (0,5 à 3,0 → jusqu'à 3×).

**Correctif** : retourner `0.0` (le composé ne participe pas) et compter ce houblon dans la
couverture rapportée, plutôt que de le noter sur une hypothèse.

### B5 — [MINEUR] `_db_path()` lève sur un `--db` en fin d'arguments

> ✅ **CORRIGÉ le 2026-09-11** (lot 5) : repli sur le chemin par défaut, l'argument sans
> valeur est ignoré comme il l'est déjà quand il est absent.

**Fichier** : `app.py:682-685` — `sys.argv[sys.argv.index("--db") + 1]`. `streamlit run
app.py -- --db` (option sans valeur) lève `IndexError` avant tout rendu, donc page blanche
plutôt que message. Coût du correctif : 2 lignes.

### Ce que j'ai cherché et **pas** trouvé (rien à corriger)

- **Remise à l'échelle BarthHaas 0-8 → 0-100** (`matching.py:547`) : je m'attendais à un biais
  systématique entre les deux roues. Vérifié sur les 2 569 valeurs réelles : après remise à
  l'échelle, Yakima moyenne **39,3** / BarthHaas **38,3**. L'hypothèse de linéarité est
  empiriquement solide. 61 houblons sont notés via BarthHaas, 94 via Yakima — ça comptait.
- **`st.cache_data`/`cache_resource` sur objets mutables ou connexions** : traité correctement
  et pour les bonnes raisons (`app.py:753-758`, `769-794`) — connexion **non** cachée,
  paramètre `_con` non haché, clé de cache = chemin + mtime de la base.
- **Mélange de sources dans une même roue d'arôme** : déjà trouvé et corrigé en T79
  (`resolve_aroma_intensity`), avec repli sur source dégénérée géré.
- **`except` trop larges** : les ~25 occurrences sont toutes dans les boucles de crawl
  d'`ingest.py`, chacune avec un `print` du motif — resilience de crawl délibérée, pas une
  exception avalée.
- **Chemins en dur, secrets commités** : aucun. `.gitignore` couvre `*.db`, `data/cache/`,
  et le journal de tickets contenant des citations utilisateur.
- **Division par zéro / comparaisons de flottants** : les dénominateurs sont gardés
  (`or 1.0`, `default=0.0`, `if hi == lo`) partout où je les ai suivis.

---

## 4. Cohérence du code et des fonctionnalités

**Ce qui est bon** (dit brièvement, comme demandé) : nommage homogène, docstrings denses et
datées, séparation `parsers` (pur) / `ingest` (I/O) / `matching` (calcul) / `app` (rendu)
respectée sans fuite, moteur utilisable hors GUI.

**C1 — Trois fonctions de classement, trois politiques de tri différentes.** `amplify` sans
départage (B3), `contrast` et `by_descriptor` avec un `_rank` explicite. Même famille de
sortie, même écran, règles divergentes.

**C2 — Deux implémentations de la conversion d'unité, désormais désynchronisées.**
`matching.amount():242` (scoring) et `app._compare_detail_value():3481` (affichage) font le
même travail. La seconde a été corrigée le 2026-09-09, la première non — c'est exactement le
risque de divergence subtile que le brief vise. **Un seul helper devrait porter cette règle**,
importé par les deux (par ex. `matching.compound_quantity(rec, total_oil, allowed_units)`).

**C3 — `hops.purpose` : « Inferred: » exposé jusque dans les tableaux de résultats.** Le
projet interdit explicitement d'utiliser `infer_purpose_from_alpha_acid` pour structurer les
blends (78,2 % d'accord seulement), mais l'affiche dans la colonne « Purpose » d'Amplify
(visible à l'écran : « Inferred: Bit… », tronqué). Le libellé est correct sur le fond ; il est
tronqué en pratique par la largeur de colonne, ce qui affiche « Inferred: Bit » — pire qu'une
absence.

**C4 — Terminologie flottante côté utilisateur.** « Ingredient » (label du champ), « note »
(vocabulaire du code et de la base, `aroma_notes`), « addition » (texte des taglines),
« aroma note » (README) désignent tous la même chose. Idem « descriptor » / « flavor » /
« aroma descriptor » / « wheel category ». Le brief demandait de vérifier ce point
précisément : c'est réel, mais bénin tant qu'un glossaire manque plutôt que des libellés
contradictoires.

**C5 — Dépendances non épinglées.** `pyproject.toml` ne pose que des bornes basses. Sur
Streamlit Cloud, l'app est reconstruite à chaque redéploiement : une montée majeure de
Streamlit ou d'Altair peut casser la prod sans qu'aucun commit n'ait eu lieu. Le projet
s'appuie déjà sur des comportements pointus de l'API (`light-dark()`, `column_config`,
`st.segmented_control`, `theme=None` sur des specs Vega-Lite précises) — c'est-à-dire
exactement le genre de code qui casse sur une montée de version.

**C6 — Entrée morte assumée.** `schema.DROP_COMPOUNDS = {"polyphenols"}:504` est documentée
comme « dead entry, inoffensif ». Correct, mais autant la supprimer.

---

## 5. Ergonomie et graphisme

Point de vue adopté : brasseur amateur, première visite, objectif « composer un blend ».

**Ce qui est bon** : l'identité visuelle (système Organic) est cohérente, lisible en clair et
en sombre, et la palette de graphiques est explicitement pensée pour le daltonisme (les deux
premières couleurs catégorielles survivent à toutes les formes). Les explications au point
d'usage existent déjà (« How does this work? » sur chaque page, « How does the molecular score
work? » à côté du contrôle, note de référence sur la couverture 4-12 %) — le brief supposait
qu'elles manquaient, c'est faux.

**E1 — [change l'usage, effort faible] L'ingrédient par défaut est « adobo ».** C'est la
première note par ordre alphabétique. Un brasseur qui arrive voit une marinade philippine,
**sans descripteurs pré-remplis**, donc l'app s'ouvre dans son état le plus faible avec le
message « No auto-suggested descriptors for adobo yet ». Proposer un défaut représentatif
(mangue, fruit de la passion, yuzu) change la première impression pour ~5 lignes.

**E2 — [change l'usage, effort faible] Le « Score » n'a aucune échelle de référence.**
`ProgressColumn` 0-100 (`app.py:1401`) sans `help=`. Le premier houblon fait **toujours** 100 :
c'est un rang relatif, pas une qualité d'accord. Deux requêtes différentes ne sont pas
comparables. Un `help=` sur la colonne, plus une note d'une ligne sous le tableau, suffisent.

**E3 — [change l'usage, effort moyen] Le mode par défaut produit des ex æquo massifs.** En
« Descriptors », le score est une fraction de recouvrement sur 2-4 descripteurs : il ne peut
prendre que 3-5 valeurs. Sur `strawberry` : 11 houblons à 66,7 puis 46 à 33,3 (cf. B3). Le
tableau donne une impression de classement là où il n'y a que deux paliers. Afficher le palier
(« 2 descripteurs sur 3 ») serait plus honnête qu'un score à une décimale.

**E4 — [polish, effort faible] Les tableaux débordent horizontalement.** Sur un écran de
1568 px, la colonne « Composition sources » est déjà coupée dans Amplify, et « Compo… » dans
les tableaux de blend. `column_config` gère les types mais aucune largeur n'est contrainte.

**E5 — [change l'usage, effort moyen] 10 modes dans une liste radio plate.** Le regroupement
existe mais seulement sous forme de préfixe textuel (« HopFinder — » / « Explore — »,
`app.py:6826`), choix documenté et assumé faute d'un widget Streamlit adapté. Le résultat
reste 10 items visuellement identiques ; c'est le premier écran, et rien n'indique par où
commencer.

**E6 — [polish] Mobile.** `st.dataframe` multi-colonnes + radar 500×500 px fixes : l'usage en
brasserie ou en magasin, cité par le brief, n'est pas réaliste aujourd'hui. Le projet a déjà
abandonné `st.columns`-par-ligne pour cette raison ; la logique n'a pas été poussée jusqu'aux
tableaux.

**États** : chargement, vide, erreur base absente, première visite — tous traités et
informatifs (`app.py:6780-6786` pour le cas base absente, message actionnable).

---

## 6. Documentation et justification des calculs

### 6.1 État des lieux, fonctionnalité par fonctionnalité

| Écran | Explication en app | Doc dépôt | Formules | Écart doc/code |
|---|---|---|---|---|
| Amplify | ✅ 2 expanders + note de couverture | ✅ README:558-575 | partielles, en prose | ⚠ **D1** (invariant d'unité faux) |
| Contrast | ✅ expander, dit « heuristique, non sourcée » | ✅ README | non | — |
| From descriptors | ✅ expander | ✅ | non | ⚠ biais de couverture non dit (D4) |
| Browse | ✅ | ✅ | s/o | — |
| Compare hops | ✅ + captions par graphique | partielle | non | — |
| Beer styles | ✅ « éditorial BJCP, pas une mesure » | ✅ DATA_SOURCES | s/o | — |
| Hops for a style | ✅ | ✅ | non | — |
| Survivables | ✅ « estimation dérivée, pas une mesure labo » | ✅ CLAUDE.md | non | — |
| Hopping plan | ✅ | ✅ | s/o | — |
| **Score affiché** | ❌ **aucune** | ❌ | ❌ | **E2** |

Le niveau de transparence est déjà supérieur à la moyenne : chaque écran dit ce qu'il n'est
pas (« pas une mesure de labo », « estimation dérivée », « heuristique culinaire »). Ce qui
manque n'est pas l'honnêteté, c'est **l'interprétabilité du chiffre affiché**.

### 6.2 Écarts constatés entre documentation et code

- **D1 — [grave] `README.md:543`** : « Quantité d'une molécule = (% d'huile / 100) × huile
  totale **(ou valeur brute pour les thiols en µg/kg)** ». La parenthèse énonce un invariant —
  « les thiols sont la seule unité étrangère » — qui est **faux depuis T134**. La doc décrit
  donc précisément la règle que le code viole (B1). C'est le symptôme exact que le brief
  cherchait : un changement d'implémentation jamais répercuté.
- **D2 — `README.md:262, 524, 649, 691`** : dénominateur « 203 houblons » (4 occurrences).
  Réel : **192**. Les fractions dérivées sont donc fausses (« 143/203 », « 36/203 »).
- **D3 — `README.md:235`** : vocabulaire de descripteurs « 104 termes ». Réel : **138**
  (CLAUDE.md le sait, le tableau du README n'a pas suivi).
- **D4 — non documenté** : `by_descriptor` classe par **nombre absolu** de descripteurs
  recoupés (`matching.py:1736`). Or les houblons couverts par BeerMaverick portent 9,0
  descripteurs en moyenne contre 4,7 pour les autres. Mesuré : sur une sélection de
  3 descripteurs, **9 des 10 premiers résultats** sont des houblons couverts par BeerMaverick.
  Le classement reflète donc en partie la couverture documentaire, pas seulement l'arôme.
  C'est le même piège que celui déjà identifié et corrigé pour le cosinus
  (`_coverage_penalized_cosine`), jamais appliqué ici.
- **D5 — `app.py:6847`** : la popover « Database » liste 7 sources, il en manque 4
  (hops-comptoir, Hopsteiner, beer-analytics, MMuM). C'est le seul écran qui prétend faire
  l'inventaire.
- **D6 — le brief lui-même** : NNLS / Render / 4 sources (cf. encadré d'ouverture). Si ce
  brief a été rédigé à partir d'une doc, cette doc est périmée ; s'il l'a été de mémoire, la
  doc n'est pas assez saillante pour corriger le souvenir.

### 6.3 Plan de rédaction proposé

`docs/methodologie.md` n'existe pas ; son contenu existe à ~80 %, dispersé entre
`README.md` (989 lignes, quickstart **et** plongée méthodologique), `docs/DATA_SOURCES.md`
(522) et `docs/ARCHITECTURE.md` (138). Je ne propose pas de tout réécrire, mais :

1. **Extraire** la partie méthodologique du README vers `docs/methodologie.md` (le README
   redevient un aperçu + installation). Aucun contenu neuf à ce stade.
2. **Ajouter ce qui manque réellement** : les formules en notation mathématique **avec
   unités** (aujourd'hui en prose), la règle d'unité explicite (quelles unités entrent dans
   quel axe, laquelle est exclue et pourquoi), et **un exemple chiffré de bout en bout**
   suivable à la main — le brief le demande et c'est le meilleur garde-fou contre une
   récidive de B1 : un exemple numérique figé aurait cassé au moment de T134.
3. **Dans l'app** : `help=` sur la colonne Score (E2), popover Database complétée (D5).
4. **Corriger** D2/D3 (chiffres périmés) — 10 minutes.

---

## 7. À confirmer — hypothèses non vérifiées et questions ouvertes

1. ~~**Que faire des mesures `mg_100g` une fois B1 corrigé ?**~~ **Tranché le 2026-09-10 :
   option (a)** — exclues du scoring, avec mention explicite à l'écran (chip nommant les
   houblons et composés écartés). Les options (b) conversion par densité d'huile sourcée
   et (c) demander à Comptoir Agricole la base de leurs pourcentages restent ouvertes si
   on veut un jour réintégrer ces mesures plutôt que les écarter.
2. **`hop_lot_analysis` n'existe pas dans `aromahops.db`** alors que le schéma et le client
   T116 sont écrits. Attendu (aucun lot ingéré, `ensure_table` la créera) ou oubli ?
3. **Impact de B1 sur les blends** : `amplify_blend` part du classement `amplify`. Je n'ai
   pas mesuré la propagation aux blends, seulement au classement simple.
4. **Le biais D4 est-il un défaut ?** Un houblon mieux documenté *mérite* peut-être de mieux
   ressortir. Je le signale comme non documenté, pas comme certainement à corriger.
5. **Reproductibilité au-delà de l'ordre SQL** : je n'ai trouvé aucune graine aléatoire ni
   `set`/`dict` non ordonné influençant un classement, hors B3. Je n'ai pas testé un rebuild
   complet de la base pour le confirmer de bout en bout.
6. Je n'ai pas audité en profondeur `ingest.py` (3 480 lignes, 11 sources) ni `reference.py`
   (1 811 lignes de priors curés). L'audit a priorisé le moteur, la GUI et les données
   réellement servies.

---

## 8. Plan d'action proposé (valeur / effort)

| # | Lot | Change quoi | Fichiers | Risque de régression |
|---|---|---|---|---|
| ~~**1**~~ | ~~**Corriger B1 + B2**~~ ✅ **fait le 2026-09-10** | Le classement moléculaire est redevenu juste : 0/258 notes avec un houblon `mg_100g` en #1 (était 232/258) | `matching.py` (`SCORING_ABSOLUTE_UNITS`, `amount`, `unit_excluded_measurements`, `amplify`), `app.py` (chip + réexport de la constante, C2 traité au passage) | Effectué : 608 tests verts, vérifié en direct dans l'app. |
| ~~**2**~~ | ~~**Tests multi-sources**~~ ✅ **fait le 2026-09-10** | Le bug B1 est désormais détectable par les tests | `tests/test_matching.py` (4 tests, `comp` à unités mélangées construit à la main plutôt que via les fixtures barthhaas/yakima) | Nul. Les 4 tests ont d'abord été vérifiés ROUGES sur le code buggé. |
| ~~**3**~~ | ~~**B3 : départage déterministe d'`amplify`**~~ ✅ **fait le 2026-09-10** | Top-N stable et reproductible ; même tri que ses deux jumelles | `matching.py` (`amplify`), `tests/test_matching.py` (2 tests) | Effectué : l'ordre affiché à égalité change, c'était le but. |
| ~~**4**~~ | ~~**D2/D3/D5 + `help=` sur Score** (E2)~~ ✅ **fait le 2026-09-10** | Provenance complète (4 sources manquantes ajoutées), chiffres du README à jour, score enfin interprétable | `README.md`, `app.py` (`_render_hop_rows` accepte un `help=` par colonne, popover Database), `tests/test_app.py` | Nul. Similar hops laissé tel quel : sa légende sous le tableau explique déjà la métrique. |
| ~~**5**~~ | ~~**B4 + B5**~~ ✅ **fait le 2026-09-11** | Plus aucune valeur inventée dans le moteur ; plus de page blanche sur `--db` sans valeur | `matching.py` (`_total_oil`, `amount`, `unscorable_measurements`), `app.py` (`_db_path`, chip), tests | Nul en pratique : 0 houblon concerné sur la base actuelle, classement vérifié identique. |
| ~~**6**~~ | ~~**E1 + E4**~~ ✅ **fait les 2026-09-10/11** | Browse et Amplify s'ouvrent sur un champ vide ; colonnes étroites bornées, les listes de droite ne sont plus poussées hors écran | `app.py`, tests | Nul. |
| ~~**7**~~ | ~~**C2 : unifier les deux conversions d'unité**~~ ✅ **fait le 2026-09-11** | `matching.compound_quantity` porte seule la règle ; `unscorable_measurements` n'énumère plus les causes, elle interroge le helper | `matching.py`, `app.py` | Faible. Tests verts. |
| ~~**8**~~ | ~~**`docs/methodologie.md` + exemple chiffré**~~ ✅ **fait le 2026-09-11** | Formules avec unités, règle d'unité en §0, exemple Amplify/strawberry retombant exactement sur le 100,0 / 96,6 affiché, §6 « ce que l'outil ne prétend pas faire » | `docs/methodologie.md` (neuf), `README.md` (liens + écart D1 corrigé) | Nul. **Écart au plan** : la prose méthodologique du README n'a PAS été déplacée (casserait les ancres pour un gain nul) ; les deux docs sont croisés par des liens. |
| ~~**9**~~ | ~~**C5 : épingler les dépendances**~~ ✅ **fait le 2026-09-11** | Plafond sur la majeure suivante pour les 8 dépendances (pas d'`==`, qui bloquerait les correctifs de sécurité) | `pyproject.toml` | Faible, résolution vérifiée. |
| **10** | **E3 ✅ + E6 ✅ faits le 2026-09-11** — E5 **laissé tel quel (décision utilisateur)** | E3 : chip « Top N all tied at X » quand les houblons affichés sont simplement ex æquo (le cas normal en mode Descriptors). E6 : tous les graphiques avaient une largeur en pixels FIXES -- mesuré, 2 des 5 de Compare Hops débordaient déjà leur conteneur à 1512 px, et sur un téléphone il aurait fallu faire défiler l'intérieur du cadre. Réglé par 2 lignes de CSS (`max-width:100%; height:auto`) exploitant le `viewBox` que Vega-Lite émet déjà : réduction proportionnelle quand c'est étroit, AUCUN changement quand c'est large -- donc sans toucher à `_COMPARE_RADAR_SIZE`/`_COMPARE_CHART_WIDTH`, dont CLAUDE.md interdit de reproposer une valeur sans retour explicite. Tooltips vérifiés intacts (moteur SVG = hit-testing DOM natif, corrigé de la mise à l'échelle par le navigateur). E5 : laissé en l'état sur décision utilisateur (2026-09-11). | `app.py` | E3/E6 : nul, vérifiés en direct. |

**Ordre recommandé** : 2 → 1 → 3 → 4 → 5 → 7 → 6 → 8 → 9 → 10.
Le lot 2 avant le lot 1 : sans fixture multi-sources, on corrige le moteur à l'aveugle.

---

*Fin de la phase 1. Aucune modification de code n'a été faite. J'attends ta validation, et
en particulier ta décision sur la question 1 du §7, avant d'attaquer le lot 1.*
