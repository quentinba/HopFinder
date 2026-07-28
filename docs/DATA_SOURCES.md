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
- Qualité : >28 000 composés / >1000 aliments ; concentrations **lacunaires** (peu de sources quantitatives — lancer `tools/audit_foodb.py` pour mesurer sur ton dump). Lié à PubChem/HMDB/ChEBI.
- Licence : **non commerciale** (redistribution restreinte).
- Rôle : colonne vertébrale note→molécule (+ concentration là où dispo).

**Flavornet** — http://www.flavornet.org
- Accès : HTML statique, ~738 composés. Figé (~2004).
- Qualité : uniquement des composés **odeur-actifs** détectés en GC-olfactométrie + descripteur + CAS. Sert de whitelist « sensoriellement présent ».

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
