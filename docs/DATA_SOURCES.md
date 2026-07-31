# Sources de données (accessibilité & qualité vérifiées)

## Côté houblon (composition + descripteurs)

**BarthHaas** — https://www.barthhaas.com/hops-and-products/hop-varieties-overview
- Accès : HTML servi côté serveur (TYPO3), ~90 variétés énumérables, bloc « Analyses » label/valeur régulier. `requests` + BeautifulSoup suffit.
- Qualité : données producteur (« médiane des 4 dernières années »), propres. **Inclut les thiols (µg/kg)**, cétones, isobutyrate — ce que les autres n'ont pas.
- **Descripteurs d'arôme non fiables sur le site actuel** : vérifié en direct sur plusieurs
  variétés (admiral, tango, dolcita-hops, huell-classic, luna) que la section « Aroma Profile »
  a été remplacée par un paragraphe descriptif libre (« The flavour profile of Admiral... »),
  plus une liste courte séparée par virgules comme avant. `parsers.parse_descriptors` détecte ce
  cas (présence d'un point final) et renvoie `[]` plutôt que d'extraire un faux descripteur
  depuis du texte libre — vérifié : sans ce garde-fou, ~80% des variétés récupéraient un
  descripteur bruit (« typical aroma profile », un millésime de récolte comme « 2023 »...). La
  roue d'arôme est en fait rendue en `<canvas>` avec des valeurs numériques par axe
  (`data-values="3,6,4,..."`) mais les libellés d'axes sont injectés en JS, pas dans le HTML
  statique — piste non résolue. **Yakima reste la source fiable pour `hop_descriptors`.**
- Statut : `ingest.crawl_barthhaas` implémenté (composition fiable, descripteurs indisponibles).

**Yakima Chief** — https://www.yakimachief.com/variety/{slug}
- Accès : le site a un vrai rempart anti-bot devant le HTML (Vercel Security Checkpoint) —
  `requests` seul ne passe jamais, même avec un User-Agent de navigateur réel (vérifié ; un
  navigateur headless Playwright, lui, passe). Contournement retenu : leur front s'appuie sur
  **Algolia** (recherche instantanée) avec une clé API **publique en lecture seule**, exposée
  côté client (design normal pour ce type de clé Algolia « search-only ») — trouvée en
  inspectant les requêtes réseau via Playwright, puis interrogée en HTTP simple (pas besoin de
  navigateur en usage courant). Une requête ramène les ~152 variétés avec composition déjà
  structurée en JSON (`imported_fields.brewing_values`, low/ave/high) et roue d'arôme
  (`imported_fields.aromas`) — pas de parsing HTML/texte requis, contrairement à BarthHaas.
- Qualité : labo qualité YCH, conforme méthodes ASBC. Ajoute **β-pinène, sélinène**.
- **Piège de nommage** : les variétés déposées ont un slug `-brand` (`citra-brand`) qui ne
  fusionnerait jamais avec le slug BarthHaas (`citra`). Mais le catalogue a aussi de vrais
  doublons de SKU sans rapport (`perle` ET `perle-per03` coexistent) — `crawl_yakima` ne
  déprefixe `-brand` que hors collision avec un autre slug du même lot.
- Statut : `ingest.crawl_yakima` implémenté. Fragile par construction (clé/index Algolia non
  documentés publiquement, peuvent changer si YCH modifie son frontend).

**Beermaverick** — agrégé, sans API. Utile en recoupement. Non implémenté.

## Côté note (ingrédient → molécules)

**FooDB** — https://foodb.ca
- Accès : dump bulk téléchargeable (XML/CSV). Version figée au 2020-04-07. URL directe
  vérifiée : `foodb.ca/public/system/downloads/foodb_2020_4_7_csv.tar.gz`, HTTP 200 sans
  authentification, ~950 Mo. `ingest.download_foodb_dump` la télécharge et l'extrait
  automatiquement (idempotent, skip si `data/foodb_2020_04_07_csv/Food.csv` existe déjà) —
  `ingest_foodb` l'appelle si aucun dossier n'est fourni explicitement.
- Qualité : >28 000 composés / >1000 aliments ; concentrations **lacunaires** (14,4 % des
  liens compound↔aliment ont une concentration, mesuré sur l'ensemble du dump via
  `tools/audit_foodb.py`, pas juste un échantillon). Lié à PubChem/HMDB/ChEBI.
- **Piège vérifié sur ce dump précis** : `Compound.csv` a ses colonnes décalées à partir de
  `moldb_iupac` — la colonne `cas_number` contient des SMILES, le vrai CAS est sous
  `description` (0 % de forme CAS plausible dans `cas_number` vs 21,6 % dans `description`,
  sur 70 477 lignes). `ingest._resolve_cas_column` détecte la bonne colonne par format plutôt
  que par nom déclaré — défensif si un futur dump est propre.
- Licence : **non commerciale** (redistribution restreinte).
- Rôle : colonne vertébrale note→molécule (+ concentration là où dispo et où l'unité est une
  masse comparable — mg/100g, mg/kg ; les autres unités FooDB (IU, ppb, µM, kcal…) ne sont pas
  interconvertibles malgré `standard_content` qui prétend les normaliser).
- Statut : `ingest.ingest_foodb` implémenté. Jointure Flavornet↔FooDB par **CAS**. Les
  synonymes de nommage restants (nommage Flavornet/FooDB vs vocabulaire houblon) sont résolus
  en priorité par **CID PubChem** (`ingest.resolve_pubchem_cids` + `pubchem_cids`, identité
  chimique vérifiée), `reference.ALIASES` ne gardant que les agrégations sans CID propre
  (« thiols »). **Seule source de notes du pipeline** : `ingest_foodb` (`all_foods=True` par
  défaut) parcourt tout `Food.csv` (~1000 aliments sur le dump 2020-04-07) et crée une note par
  aliment, nom = celui de FooDB en minuscule — pas de traitement spécial pour un sous-ensemble
  de notes. Une amorce littérature de 7 notes (`reference.AROMA_NOTES`/`NOTE_DESCRIPTORS`/
  `NOTE_TO_FOODB` : yuzu, kumquat, basilic, rose, fruit-passion, mangue, pin-resine) a existé
  pendant le développement puis a été **retirée à la demande explicite de l'utilisateur** une
  fois ce pipeline suffisant — une seule source de vérité par note. Conséquence assumée :
  yuzu/rose/pin-resine n'avaient pas d'équivalent FooDB propre (yuzu absent, rose = faux ami
  "Rose hip", pin-resine pas un aliment) et ont donc disparu avec l'amorce — aucune ne revient
  tant qu'aucune source réelle ne les couvre. `notes` (paramètre optionnel, additif, vide par
  défaut) reste disponible pour donner un nom choisi à un aliment sans supprimer son nom
  auto-dérivé (bug corrigé en le construisant : "mangue" écrasait silencieusement "mango").
  **Filtre de distinctivité** : un aliment est écarté s'il n'a AUCUN composé à concentration
  mesurée (`foodb:conc`). Vérifié sur le dump réel : deux aliments sans rapport (capers/chervil)
  partagent 99,2% de leurs composés listés (5961/6011) — sans concentration, FooDB cite un
  gabarit générique plutôt qu'une composition mesurée pour cet aliment précis, et le poids
  retombe sur la table de seuils globale (identique entre aliments sans lien). Run réel : 345/847
  candidats avec ≥1 composé whitelisté écartés (992 aliments au total, 141 sans aucun composé
  whitelisté, ~510 notes distinctes conservées).
  **Généraliser les descripteurs a été testé et rejeté DEUX FOIS.** (1) Agréger les
  descripteurs Flavornet des molécules d'une note (pondéré par poids, puis par IDF, puis
  restreint aux seuls composés distinctifs) reproduit systématiquement la même
  dégénérescence que le problème ci-dessus sur la note médiane — convergence vers les
  mêmes mots génériques entre notes sans rapport, ou profil vide dès qu'on se limite aux
  composés vraiment food-specific (peu de notes en ont beaucoup). (2) Retesté sur les
  notes les PLUS riches en composés à concentration réelle (rosemary : 38, carrot : 45,
  red wine : 49...) — toujours dégénéré : carrot et wild carrot obtiennent un score
  "citrus" identique à 2 décimales près, rosemary/red wine/common oregano convergent tous
  vers citrus/spicy/floral malgré des profils olfactifs sans rapport. Cause identifiée :
  des composés génériques RÉELS et correctement mesurés (aldéhydes à chaîne moyenne —
  heptanal, nonanal, octanal...) apparaissent comme composés concentration dans énormément
  d'aliments chimiquement sans rapport et portent "citrus" comme descripteur Flavornet —
  le problème n'est plus la rareté du signal (filtré par le point 1) mais l'ubiquité
  chimique réelle de composés triviaux qui noient la signature propre à l'aliment. Aucun
  filtre de richesse ne peut compenser ça. `note_descriptors` reste donc VIDE par défaut
  pour toute note — `amplify`/`combine` fonctionnent en molécules-seules pour toutes les notes
  désormais. `contrast` est généralisé différemment : `matching.contrast(descriptors=)` laisse
  l'utilisateur décrire sa note à la main (vocabulaire réel `hop_descriptors`, comme
  `by_descriptor`) au lieu de dépendre de `note_descriptors` — couvre n'importe quelle note sans
  rien inventer. `matching.contrast_blend` en tire une combinaison parcimonieuse (couverture
  ensembliste, pas de NNLS) avec résidu rapporté.

**Flavornet** — http://www.flavornet.org
- Accès : une page HTML statique unique triée par indice de Kovats (`d_kovats_ov101.html`,
  pas de pagination), 738 lignes (CAS + nom + descripteurs), 734 CAS uniques après fusion des
  doublons de synonymes.
- Qualité : uniquement des composés **odeur-actifs** détectés en GC-olfactométrie + descripteur + CAS. Sert de whitelist « sensoriellement présent ». Figé (~2004).
- Statut : `ingest.ingest_flavornet` implémenté, écrit dans `flavornet_compounds` (distincte de
  `molecules`).

**FlavorDB2** — https://cosylab.iiitd.edu.in/flavordb2/
- Accès : pas d'API ni de dump bulk pour les seuils (l'unique JSON bulk du site est un graphe
  de co-occurrence ingrédient↔ingrédient, sans rapport). Fiche détail AJAX
  (`/molecules_details?id=<pubchem_cid>`) — **directement accessible par CID PubChem**, sans
  recherche par nom, une fois le CID connu (`pubchem_cids`, voir section Liant) ; recherche par
  nom (`/molecules?common_name=`) en repli sinon. La fiche contient le(s) CAS et un champ
  **texte libre** « Aroma threshold values » (ex. « 4 to 10 ppb », « Detection at 64 to 90 ppb »).
- **Piège vérifié** : ce champ texte libre contient parfois autre chose qu'un seuil — la fiche
  du myrcène y liste *« Aroma characteristics at 10%; terpy, herbaceous... »* (une composition
  dans un extrait, pas un seuil). `parsers.parse_flavordb2_threshold` ne fait confiance qu'à un
  nombre directement accolé à une unité reconnue (ppb/ppm/ppt) ; sinon `None`.
- Qualité : 25 595 molécules, **seuils aroma/goût par molécule** ; lien ingrédient→molécule en présence/absence (pas de concentration).
- Licence : **CC BY-NC-SA** (non commercial).
- Rôle : couche seuils (prior de puissance).
- Statut : `ingest.ingest_flavordb2` implémenté, **borné aux ~734 composés de la whitelist
  Flavornet** (pas les 25 595 molécules — hors de portée de ce dont hopmatch se sert, et
  inutilement lourd pour leur serveur). Run réel (avec `pubchem_cids` déjà résolu, repli par nom
  inclus, accès direct par CID) : **227 seuils trouvés sur 734** (727 via CID direct, 6 sans
  correspondance, 501 trouvés mais sans seuil publié). Écrit dans `flavordb2_thresholds`, jamais
  dans `molecules`/`reference.MOLECULES`.

**The Good Scents Company** — descripteurs parfumeur fins, **pas d'API, CGU restrictives**. Optionnel.

## Liant

**PubChem (PUG-REST)** — https://pubchem.ncbi.nlm.nih.gov
- Accès : `/compound/name/{cas}/cids/JSON` accepte un CAS comme synonyme et renvoie son CID.
  Vérifié : `140-67-0` (CAS estragole) → CID **8815**, identique au CID déjà connu de
  *methyl-chavicol* dans `reference.MOLECULES` — la fusion de synonymes est un fait chimique
  vérifié, pas une supposition de nommage.
- API publique robuste, domaine public. Limite d'usage : 5 requêtes/s conseillées.
- Statut : `ingest.resolve_pubchem_cids` implémenté, écrit `pubchem_cids(cas, cid)`, borné à la
  whitelist Flavornet (~734 composés, même périmètre que le reste du pipeline). Résolution par
  CAS d'abord, puis repli sur le nom du composé (`parsers.pubchem_name_fallbacks` : lettre
  grecque épelée, préfixe stéréochimique retiré — Flavornet ne fournit ni InChIKey ni SMILES,
  donc pas de variante au-delà de ces deux normalisations déterministes). Consommé par
  `ingest._canonical_compound` (fusion de synonymes par CID, priorité sur `reference.ALIASES`)
  et `ingest_flavordb2` (accès direct à la fiche par CID, sans recherche par nom).

## Rappel licences
Le **code** est MIT. **FooDB et FlavorDB2 sont non commerciales.** Un usage commercial de hopmatch imposerait de retirer/renégocier ces sources.
