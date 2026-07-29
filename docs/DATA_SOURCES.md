# Sources de données (accessibilité & qualité vérifiées)

## Côté houblon (composition + descripteurs)

**BarthHaas** — https://www.barthhaas.com/hops-and-products/hop-varieties-overview
- Accès : HTML servi côté serveur (TYPO3), ~90 variétés énumérables, bloc « Analyses » label/valeur régulier. `requests` + BeautifulSoup suffit.
- Qualité : données producteur (« médiane des 4 dernières années »), propres. **Inclut les thiols (µg/kg)**, cétones, isobutyrate — ce que les autres n'ont pas.
- Statut : `ingest.crawl_barthhaas` implémenté.

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
- Accès : dump bulk téléchargeable (XML/CSV). Version figée au 2020-04-07.
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
- Statut : `ingest.ingest_foodb` implémenté. Jointure Flavornet↔FooDB par **CAS** (pas encore
  PubChem CID/InChIKey — les synonymes hors CAS passent par `reference.ALIASES`, amorce
  manuelle). `reference.NOTE_TO_FOODB` ne couvre que 4/7 notes-amorce (kumquat, basilic,
  fruit-passion, mangue) : yuzu absent de FooDB, rose n'a que "Rose hip" (faux ami), pin-résine
  n'est pas un aliment.

**Flavornet** — http://www.flavornet.org
- Accès : une page HTML statique unique triée par indice de Kovats (`d_kovats_ov101.html`,
  pas de pagination), 738 lignes (CAS + nom + descripteurs), 734 CAS uniques après fusion des
  doublons de synonymes.
- Qualité : uniquement des composés **odeur-actifs** détectés en GC-olfactométrie + descripteur + CAS. Sert de whitelist « sensoriellement présent ». Figé (~2004).
- Statut : `ingest.ingest_flavornet` implémenté, écrit dans `flavornet_compounds` (distincte de
  `molecules`).

**FlavorDB2** — https://cosylab.iiitd.edu.in/flavordb2/
- Accès : pas d'API ni de dump bulk pour les seuils (l'unique JSON bulk du site est un graphe
  de co-occurrence ingrédient↔ingrédient, sans rapport). Recherche par nom
  (`/molecules?common_name=`) puis fiche détail AJAX (`/molecules_details?id=<pubchem_cid>`),
  qui contient le(s) CAS et un champ **texte libre** « Aroma threshold values » (ex. « 4 to 10
  ppb », « Detection at 64 to 90 ppb »).
- **Piège vérifié** : ce champ texte libre contient parfois autre chose qu'un seuil — la fiche
  du myrcène y liste *« Aroma characteristics at 10%; terpy, herbaceous... »* (une composition
  dans un extrait, pas un seuil). `parsers.parse_flavordb2_threshold` ne fait confiance qu'à un
  nombre directement accolé à une unité reconnue (ppb/ppm/ppt) ; sinon `None`.
- Qualité : 25 595 molécules, **seuils aroma/goût par molécule** ; lien ingrédient→molécule en présence/absence (pas de concentration).
- Licence : **CC BY-NC-SA** (non commercial).
- Rôle : couche seuils (prior de puissance).
- Statut : `ingest.ingest_flavordb2` implémenté, **borné aux ~734 composés de la whitelist
  Flavornet** (pas les 25 595 molécules — hors de portée de ce dont hopmatch se sert, et
  inutilement lourd pour leur serveur). Run réel : 86 seuils trouvés sur 734 (488 sans
  correspondance de nom exacte, 160 trouvés mais sans seuil publié). Écrit dans
  `flavordb2_thresholds`, jamais dans `molecules`/`reference.MOLECULES`.

**The Good Scents Company** — descripteurs parfumeur fins, **pas d'API, CGU restrictives**. Optionnel.

## Liant

**PubChem (PUG-REST)** — https://pubchem.ncbi.nlm.nih.gov
- API publique robuste, domaine public. Clé InChIKey/CID pour joindre ingrédient ↔ molécule ↔ houblon.

## Rappel licences
Le **code** est MIT. **FooDB et FlavorDB2 sont non commerciales.** Un usage commercial de hopmatch imposerait de retirer/renégocier ces sources.
