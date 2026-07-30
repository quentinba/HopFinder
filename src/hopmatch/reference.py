"""
Données de référence — la couche "note → molécules / descripteurs".

⚠️ AMORCE : ces tables (MOLECULES, AROMA_NOTES, NOTE_DESCRIPTORS) sont saisies
à la main depuis la littérature, pour 7 notes. FooDB (composition), Flavornet
(composés odeur-actifs) et FlavorDB2 (seuils) sont branchés (voir ingest.py) et
ENRICHISSENT cette amorce sans l'effacer (`ingest_foodb`, `all_foods=True` par
défaut, généralise même au-delà de ces 7 notes à ~500 notes auto-dérivées de
FooDB — voir docs/DATA_SOURCES.md). L'amorce reste la seule source pour
`note_descriptors`/`CONTRAST_AFFINITY` (mode `contrast` par note) : dériver ça
depuis FooDB a été tenté et rejeté (données trop génériques). `contrast` reste
utilisable au-delà des 7 notes via une sélection manuelle de descripteurs
(`matching.contrast(descriptors=[...])`), pas via cette amorce.
"""

# molécule -> (descripteur odeur, seuil olfactif ppb | None, PubChem CID | None)
# Le seuil est un PRIOR de puissance, pas une mesure d'OAV (pas de concentration).
MOLECULES: dict[str, tuple[str, float | None, int | None]] = {
    "myrcene":        ("résineux, vert, géranium", 13, 31253),
    "humulene":       ("boisé, houblon, épicé", 120, 5281520),
    "caryophyllene":  ("boisé, poivré", 64, 5281515),
    "farnesene":      ("floral, vert, boisé", 60, 5281516),
    "geraniol":       ("rose, géranium, floral", 4, 637566),
    "linalool":       ("floral, agrume", 6, 6549),
    "beta-pinene":    ("pin, résineux", 140, 14896),
    "selinene":       ("boisé, herbacé", None, 442393),
    "thiols":         ("passion, pamplemousse, cassis", 0.06, None),
    "limonene":       ("agrume, orange", 34, 22311),
    "terpinolene":    ("boisé, frais, agrume/pin", 200, 11463),
    "citronellol":    ("rose, agrume", 8, 8842),
    "geranial":       ("citron, citronnelle", 32, 638011),
    "methyl-chavicol": ("anis, estragon, basilic", None, 8815),
}

# molécule côté note -> composé mesuré côté houblon. Réservé aux AGRÉGATIONS
# (plusieurs molécules mesurées ensemble côté houblon sous un même composé,
# ex. les thiols) : ce n'est pas un fait d'identité chimique résoluble par CID
# PubChem (le composé cible n'a pas de CID propre), donc ça reste manuel.
# Les synonymes de nommage purs (estragole/methyl-chavicol, même CAS) sont
# désormais résolus structuralement via ingest._canonical_compound + le CID
# PubChem (ingest.resolve_pubchem_cids) — ne pas les remettre ici.
ALIASES: dict[str, str] = {
    "3-mercaptohexanol": "thiols", "4mmp": "thiols",
}

# Biotransformation levure (option --biotransform, cas A `amplify`/cas B `combine`) :
# molécule demandée par la note -> composé précurseur mesuré côté houblon, que la
# fermentation peut convertir. Actif seulement si l'utilisateur l'active — ça
# affirme une fermentation standard, ce que hopmatch ne peut pas vérifier.
#
# Portée volontairement étroite aux deux voies avec preuve indépendante
# convergente sur souche ale ET lager (King & Dickinson 2003, FEMS Yeast
# Research — courbes cinétiques réelles sur S. cerevisiae NCYC 1681 et
# S. bayanus NCYC 1324, deux espèces différentes, résultats concordants) :
#   - géraniol -> citronellol : produit principal, quantifié dans les deux
#     souches (~1,4-1,5 µg/mL de pic depuis 10 µg/mL de géraniol ajouté).
#     Corroboré par Michel et al. 2019 (BrewingScience) : aucun effet souche
#     détecté sur un thiol proche mécaniquement, sur ~98 souches de brasserie.
#   - linalol -> alpha-terpinéol : produit principal du linalol, également
#     quantifié dans les deux souches (~0,4-0,45 µg/mL après 15 jours).
#
# Délibérément PAS étendu : (1) aux esters (acétate de géranyle/citronellyle) —
# King & Dickinson montrent que SEULE la souche lager les produit, pas l'ale :
# preuve divergente entre souches, donc hors de la portée "généralisable" de
# cette option ; (2) aux thiols (précurseurs non mesurés côté houblon, rien à
# rediriger) ; (3) aux terpènes majoritaires du houblon — myrcène, humulène,
# caryophyllène, les pinènes sont explicitement montrés NON biotransformés
# (aucun produit détecté, juste perdus par évaporation/adsorption) ; (4) au
# nérol comme cible ou source — jamais mesuré côté houblon (aucune fiche
# BarthHaas/Yakima ne le rapporte), une redirection vers lui serait inerte.
# Non validé pour Kveik/Brettanomyces/fermentation mixte : aucune étude
# trouvée ne teste ces cas, donc aucune affirmation n'est faite (ni "pareil",
# ni "différent") — l'option suppose une souche standard.
BIOTRANSFORMATIONS: dict[str, str] = {
    "citronellol": "geraniol",
    "alpha-terpineol": "linalool",
}

# note -> {molécule: poids de contribution au caractère (0-1)}
AROMA_NOTES: dict[str, dict[str, float]] = {
    "yuzu":          {"limonene": 1.0, "linalool": 0.7, "myrcene": 0.4, "terpinolene": 0.3, "beta-pinene": 0.3, "geraniol": 0.2},
    "kumquat":       {"limonene": 1.0, "myrcene": 0.6, "beta-pinene": 0.4, "caryophyllene": 0.3, "linalool": 0.2},
    "basilic":       {"linalool": 1.0, "methyl-chavicol": 0.9, "caryophyllene": 0.4},
    "rose":          {"geraniol": 1.0, "citronellol": 0.9, "linalool": 0.3},
    "fruit-passion": {"thiols": 1.0, "myrcene": 0.3},
    "mangue":        {"myrcene": 1.0, "terpinolene": 0.6, "caryophyllene": 0.3},
    "pin-resine":    {"beta-pinene": 1.0, "myrcene": 0.5, "humulene": 0.3},
}

# note -> descripteurs sensoriels (pour la couche descripteurs, primaire)
NOTE_DESCRIPTORS: dict[str, list[str]] = {
    "yuzu":          ["citrus", "floral"],
    "kumquat":       ["citrus"],
    "basilic":       ["herbal", "spicy"],
    "rose":          ["floral"],
    "fruit-passion": ["tropical"],
    "mangue":        ["tropical", "stone fruit"],
    "pin-resine":    ["woody", "resinous"],
}

# note -> nom d'aliment FooDB (Food.name) à ingérer via ingest_foodb.
# Uniquement les correspondances propres et sans ambiguïté (vérifié sur le dump 2020-04-07) :
#   - yuzu : absent de FooDB (aucune entrée), reste sur l'amorce littérature.
#   - rose : FooDB n'a que "Rose hip" (le fruit de l'églantier, note plus acidulée que
#     florale) — mapper "rose" dessus serait un faux ami, on s'abstient.
#   - pin-resine : pas un aliment (note résineuse pure), aucun candidat FooDB pertinent.
NOTE_TO_FOODB: dict[str, str] = {
    "kumquat":       "Kumquat",
    "basilic":       "Sweet basil",
    "fruit-passion": "Passion fruit",
    "mangue":        "Mango",
}

# Normalisation des variantes de descripteurs entre sources (pluriel, formulation).
# Amorce curée ; appliquée à l'ingestion (ingest._ingest_variety), pas dans
# parsers.parse_descriptors qui reste un parseur brut sans connaissance métier.
# À enrichir au fil des variétés réellement ingérées (crawl_barthhaas/crawl_yakima).
DESCRIPTOR_ALIASES: dict[str, str] = {
    "citrus fruit": "citrus", "citrus fruits": "citrus",
    "stonefruit": "stone fruit", "stone fruits": "stone fruit",
    "berries": "berry", "tropical fruit": "tropical", "tropical fruits": "tropical",
    "woody/resinous": "woody", "spice": "spicy", "spices": "spicy",
}

# Carte d'affinités descripteurs pour le MODE CONTRASTE (cas A).
# Le contraste ne se dérive pas des molécules partagées : ce sont des paires de
# descripteurs connues pour bien s'accorder. Amorce curée, à enrichir (idéalement
# depuis un corpus de recettes → co-occurrence).
CONTRAST_AFFINITY: dict[str, list[str]] = {
    "citrus":      ["resinous", "woody", "herbal"],
    "tropical":    ["resinous", "dank", "spicy"],
    "floral":      ["earthy", "woody", "spicy"],
    "stone fruit": ["spicy", "woody"],
    "herbal":      ["citrus", "floral"],
    "woody":       ["citrus", "tropical", "floral"],
    "resinous":    ["citrus", "tropical"],
    "spicy":       ["tropical", "floral", "stone fruit"],
    "dank":        ["tropical", "citrus"],
    "earthy":      ["floral"],
}
