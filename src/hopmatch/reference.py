"""
Données de référence — la couche "note → molécules / descripteurs".

⚠️ AMORCE : ces tables sont saisies à la main depuis la littérature. C'est
exactement la moitié que le projet vise à remplacer par des sources réelles
(FooDB pour la composition, Flavornet pour les composés odeur-actifs, FlavorDB2
pour les seuils). Voir ingest.py (scaffolds foodb/flavornet) et docs/DATA_SOURCES.md.

Tant que ces sources ne sont pas branchées, l'app tourne sur cette amorce — utile
pour la démo et les tests, insuffisante pour un usage sérieux.
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

# molécule côté note -> composé mesuré côté houblon (thiols agrégés, synonymes
# FooDB/Flavornet à normaliser vers le vocabulaire houblon existant, etc.)
ALIASES: dict[str, str] = {
    "3-mercaptohexanol": "thiols", "4mmp": "thiols",
    "estragole": "methyl-chavicol",  # même composé (CAS 140-67-0), nom Flavornet/FooDB
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
