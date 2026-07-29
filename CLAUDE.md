# CLAUDE.md — contexte projet hopmatch

Ce fichier donne à Claude Code le contexte et les décisions issues de la conception
de hopmatch. Lis-le avant d'agir. (Détails : `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md`.)

## But
Outil brasseur : **note olfactive → molécules → houblons**. Deux cas d'usage aux
scorings DIFFÉRENTS :
- **Cas A** — accorder un houblon à un ajout (yuzu, basilic…). Modes `amplify`
  (prolonger) et `contrast` (contraster). L'ajout est dans la bière, donc le houblon
  n'a pas à le reproduire : le « plafond de couverture » ne pénalise pas.
- **Cas B** — reproduire un goût sans ajout, via une **combinaison** de houblons
  (`combine`, NNLS). Ici la valeur est de dire ce qui est **irréductible**.

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
  `ingest.crawl_yakima` IMPLÉMENTÉ. Fragile (clé/index Algolia non documentés).
- **FooDB** : source note→molécule. Dump bulk local, figé 2020-04-07, licence NON
  COMMERCIALE. `ingest.ingest_foodb` IMPLÉMENTÉ. Vérifié sur le dump réel :
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
  FUSIONNE avec l'amorce littérature (molécule par molécule), ne l'efface pas.
  `reference.NOTE_TO_FOODB` : 4/7 notes-amorce seulement (kumquat, basilic, fruit-passion,
  mangue) — yuzu absent de FooDB, rose = faux ami ("Rose hip"), pin-résine pas un aliment.
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
Fait : `ingest.ingest_flavornet`, `ingest.ingest_foodb`, `by-descriptor`, `ingest.crawl_yakima`,
`ingest.ingest_flavordb2`, `ingest.resolve_pubchem_cids` (jointure structurale CAS->CID + repli
sur le nom, voir `docs/FEATURE_NOTES.md` pour le détail de spec de by-descriptor), option
`--biotransform` (`amplify`/`combine`, portée étroite — voir décision ci-dessus), GUI Streamlit
(`src/hopmatch/app.py`). Reste :
1. Jointure FooDB/hop_composition au-delà des ~734 composés Flavornet si le vocabulaire
   s'élargit beaucoup (crawl Yakima déjà réel, plus d'aliments FooDB).
2. Extension de `reference.BIOTRANSFORMATIONS` SI une étude comparant des souches
   commerciales entre elles (pas des codes de collection académique TUM/CBS/NCYC) sur
   ces mêmes composés devient disponible. Pas de drapeau par souche individuelle en
   attendant — voir le raisonnement dans README.md#option---biotransform.

## Conventions
- Commentaires/docstrings en français (cohérent avec l'existant).
- Ne jamais fabriquer de données houblon en dur : passer par un parseur + source tracée.
- `pytest` doit rester vert. Ajouter un test quand on touche un solveur ou un parseur.
- Commandes : `pip install -e ".[dev]"` ; `pytest -q` ; `hopmatch build` puis
  `hopmatch amplify|contrast|combine <note>` ou `hopmatch by-descriptor <descripteurs>`.
