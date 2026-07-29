# Sources de données (accessibilité & qualité vérifiées)

## Côté houblon (composition + descripteurs)

**BarthHaas** — https://www.barthhaas.com/hops-and-products/hop-varieties-overview
- Accès : HTML servi côté serveur (TYPO3), ~90 variétés énumérables, bloc « Analyses » label/valeur régulier. `requests` + BeautifulSoup suffit.
- Qualité : données producteur (« médiane des 4 dernières années »), propres. **Inclut les thiols (µg/kg)**, cétones, isobutyrate — ce que les autres n'ont pas.
- Statut : `ingest.crawl_barthhaas` implémenté.

**Yakima Chief** — https://www.yakimachief.com/variety/{slug}
- Accès : valeurs rendues dans le HTML mais front type SPA → extraction DOM (ou playwright si `requests` ne renvoie qu'un shell).
- Qualité : labo qualité YCH, conforme méthodes ASBC. Ajoute **β-pinène, sélinène**.
- Statut : `ingest.crawl_yakima` = scaffold.

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
- Accès : pas d'API ; données JSON par fiche (à scraper ; l'ancien endpoint v1 renvoie une 500).
- Qualité : 25 595 molécules, **seuils aroma/goût par molécule** ; lien ingrédient→molécule en présence/absence (pas de concentration).
- Licence : **CC BY-NC-SA** (non commercial).
- Rôle : couche seuils (prior de puissance).

**The Good Scents Company** — descripteurs parfumeur fins, **pas d'API, CGU restrictives**. Optionnel.

## Liant

**PubChem (PUG-REST)** — https://pubchem.ncbi.nlm.nih.gov
- API publique robuste, domaine public. Clé InChIKey/CID pour joindre ingrédient ↔ molécule ↔ houblon.

## Rappel licences
Le **code** est MIT. **FooDB et FlavorDB2 sont non commerciales.** Un usage commercial de hopmatch imposerait de retirer/renégocier ces sources.
