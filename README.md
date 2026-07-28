# hopmatch

**Note olfactive → molécules → houblons.** Un outil pour brasseur : trouver les houblons qui s'accordent avec un ajout (yuzu, basilic…), ou tenter de reproduire un profil aromatique avec du houblon seul.

> État : squelette fonctionnel testé sur données réelles de démonstration (3 variétés BarthHaas + 3 Yakima). Les crawlers pleine échelle et la source « note » (FooDB) sont des scaffolds documentés — voir [Passer à Claude Code](#passer-à-claude-code).

## Les deux cas d'usage (ils n'ont pas le même scoring)

- **Cas A — accorder un houblon à un ajout.** L'ajout est dans la bière ; le houblon n'a pas à le reproduire. Deux modes :
  - `amplify` : houblons qui **prolongent** le caractère de l'ajout (molécules partagées + descripteurs).
  - `contrast` : houblons qui **contrastent** bien, via une carte d'affinités descripteurs (le contraste ne se dérive pas des molécules partagées).
- **Cas B — reproduire un goût sans ajout.** `combine` cherche une **combinaison** de houblons (NNLS) qui recompose le profil, et rapporte le **résidu irréductible** : les molécules d'impact qu'aucun houblon ne peut fournir. C'est la réponse honnête au « à quel point peut-on s'approcher ».

## Installation

```bash
git clone <ton-repo> hopmatch && cd hopmatch
pip install -e .            # cœur (numpy, scipy)
pip install -e ".[crawl]"   # + requests, beautifulsoup4 (crawl BarthHaas)
pip install -e ".[foodb]"   # + pandas (audit/ingest FooDB)
pip install -e ".[dev]"     # + pytest
```

## Démarrage

```bash
hopmatch build                       # construit aromahops.db depuis data/fixtures
hopmatch list

# Cas A
hopmatch amplify yuzu                 # houblons qui prolongent le yuzu
hopmatch amplify basilic --oav        # avec prior de seuil (approx.)
hopmatch contrast yuzu                # houblons qui contrastent

# Cas B
hopmatch combine mangue               # combinaison recomposant la mangue
hopmatch combine fruit-passion --max-hops 2

# Base complète BarthHaas (~90 variétés, réseau) :
hopmatch crawl-barthhaas
```

Exemple de sortie (`combine mangue`) :

```
[COMBINE] mangue — couverture 68% | résidu 0.305
  100.0%  Citra
  irréductible (aucun houblon ne fournit) : terpinolene
```

## Architecture (résumé)

Trois couches, détaillées dans [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) :

1. **Descripteurs** (primaire) — roues d'arôme BarthHaas/Yakima. Robuste, sans concentration.
2. **Molécules** (secondaire) — similarité normalisée-par-composé (TF-IDF), sur les composés que le houblon possède réellement. Le seuil olfactif est un **prior de puissance**, pas un OAV (on n'a pas de concentration fiable).
3. **Honnêteté** — rapport de couverture + molécules orphelines + (à venir) drapeau biotransformation.

Base SQLite **EAV multi-sources** : une variété reçoit des mesures de plusieurs sources (BarthHaas *et* Yakima), réconciliées à la lecture (moyenne des milieux de fourchette, provenance tracée). Une couche de **validation/réparation** corrige les datasets sales (inversion myrcène/caryophyllène).

## Sources de données & licences

Détail et qualité vérifiée dans [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md). En bref :

| Source | Rôle | Accès | Licence |
|---|---|---|---|
| BarthHaas | houblon (dont thiols) | HTML servi, parsable | données producteur |
| Yakima Chief | houblon (β-pinène, sélinène) | HTML (SPA) | données producteur |
| FooDB | note → molécules (+conc.) | dump bulk | **non commercial** |
| Flavornet | composés odeur-actifs | HTML statique | académique |
| FlavorDB2 | seuils par molécule | scrape JSON | **CC BY-NC-SA** |
| PubChem | identifiants (jointure) | API PUG-REST | domaine public |

⚠️ **Le code est sous MIT, pas les données.** FooDB et FlavorDB2 sont **non commerciales**. Tant que hopmatch reste perso/open-source non lucratif, c'est bon ; une distribution commerciale imposerait de revoir ces sources.

## Structure

```
src/hopmatch/
  reference.py   amorce note→molécule/descripteur + carte d'affinités (⚠️ à remplacer par FooDB)
  parsers.py     parseurs label/valeur BarthHaas & Yakima
  schema.py      schéma SQLite EAV + validation/réparation
  ingest.py      build fixtures / crawl BarthHaas (réel) ; foodb/yakima/flavornet (scaffolds)
  matching.py    load+réconciliation ; amplify / contrast / combine(NNLS)
  cli.py         CLI
data/fixtures/   pages réelles (démo) : barthhaas/{citra,mosaic,saazer}, yakima/{citra,mosaic,simcoe}
tools/audit_foodb.py   quantifie la lacunarité des concentrations FooDB
tests/           parsers, validation, réconciliation, modes
```

## Feuille de route

- [ ] Crawler Yakima (scaffold `ingest.crawl_yakima`)
- [ ] Ingest FooDB → remplace l'amorce note→molécule (`ingest.ingest_foodb`)
- [ ] Ingest Flavornet → whitelist odeur-active (`ingest.ingest_flavornet`)
- [ ] Couche seuils depuis FlavorDB2 (prior de puissance par molécule)
- [ ] Enrichir la carte d'affinités contraste (idéalement co-occurrence recettes)
- [ ] Drapeau biotransformation par souche (géraniol→citronellol, précurseurs→thiols)

## Passer à Claude Code

Ce dépôt est volontairement structuré pour que les prochaines tâches soient déléguées à **Claude Code** dans ton environnement — parce qu'elles nécessitent ce que ce squelette n'a pas : ton réseau, tes gros fichiers locaux, et des itérations contre des sites vivants. Concrètement, ouvre Claude Code sur le repo et attaque, dans l'ordre :

1. **`ingest.ingest_foodb`** — le plus utile. Nécessite ton dump FooDB local (~1 Go, hors de portée d'un sandbox). Lance d'abord `python tools/audit_foodb.py <dossier>` pour mesurer la lacunarité réelle, puis code l'ingestion aliment→composé + jointure seuils/Flavornet par PubChem CID. Tâche typée « données locales volumineuses » → Claude Code.
2. **`ingest.crawl_yakima`** — nécessite des allers-retours contre un site SPA vivant (tester `requests` vs playhwright, ajuster les sélecteurs DOM). Itératif contre le réseau → Claude Code.
3. **Couche seuils + biotransformation** — enrichissements qui touchent plusieurs modules et gagnent à être développés en contexte repo complet.

Règle simple : tout ce qui demande **ton réseau, tes fichiers, ou plusieurs itérations sur du code réparti** est un bon candidat Claude Code. Ce qui est conceptuel ou ponctuel, on peut le faire ici.

## Licence

Code : MIT (voir [`LICENSE`](LICENSE)). Données : voir chaque source ci-dessus.
