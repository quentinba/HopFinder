"""
Données de référence — propriétés MOLÉCULE et vocabulaire DESCRIPTEUR, pas de
notes pré-remplies : toutes les notes viennent du pipeline (`ingest_foodb`,
`all_foods=True` par défaut — voir docs/DATA_SOURCES.md). Une amorce
littérature de 7 notes (yuzu, basilic...) a existé ici avant que le pipeline
FooDB ne soit branché ; retirée une fois ce pipeline suffisant, pour ne garder
qu'une seule source de vérité par note plutôt que deux qui se recouvrent
partiellement (choix explicite de l'utilisateur — les 3 notes sans équivalent
FooDB, yuzu/rose/pin-resine, disparaissent avec : aucune ne reviendra tant
qu'aucune source réelle ne les couvre).

Reste : `MOLECULES` (propriétés par molécule, indépendantes de toute note),
`ALIASES`/`BIOTRANSFORMATIONS` (résolution de composés, indépendantes des
notes), `DESCRIPTOR_ALIASES`/`CONTRAST_AFFINITY` (vocabulaire descripteur,
indépendant des notes — `CONTRAST_AFFINITY` est déjà keyed par descripteur,
pas par note, donc `contrast` reste utilisable pour N'IMPORTE QUELLE note via
une sélection manuelle de descripteurs, `matching.contrast(descriptors=[...])`
— voir ce module).
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

# Biotransformation levure (option --biotransform, `amplify`) :
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
# depuis un corpus de recettes → co-occurrence) — prior heuristique explicitement
# signalé comme tel (voir README, section "Ce qui est un prior, pas une donnée"),
# jamais traité comme une donnée houblon vérifiée.
#
# Deux groupes de clés :
#   1. Les 10 catégories "cœur" (citrus...earthy) : servent À LA FOIS de clé ET de
#      valeur possible — un maillage fermé entre elles, le noyau original.
#   2. Les descripteurs plus étroits du vocabulaire réel `hop_descriptors`
#      (vérifié sur la base construite : 38 descripteurs distincts au total,
#      seuls 10 couverts avant cet ajout — un utilisateur choisissant "grapefruit"
#      ou "pine" en `contrast --descriptors` obtenait une cible vide sans
#      explication). Chacun est rattaché aux catégories cœur les plus proches par
#      logique d'accord classique (fruit vif/agrume ↔ registre boisé-résineux-
#      terreux ; floral ↔ épicé-terreux ; herbacé ↔ fruité-floral), PAS à d'autres
#      descripteurs étroits entre eux — ça garderait la cible de contraste sur des
#      catégories assez larges pour recouper la roue d'arôme réelle d'un houblon
#      (les tags étroits comme "grapefruit" sont rares sur un houblon donné, les
#      catégories cœur beaucoup plus fréquentes). `matching.contrast` signale
#      explicitement un descripteur choisi sans entrée ici (voir `unmapped`).
CONTRAST_AFFINITY: dict[str, list[str]] = {
    # -- catégories cœur (maillage fermé) --
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
    # -- sous-familles agrume -> mêmes cibles que "citrus" --
    "grapefruit":  ["resinous", "woody", "herbal"],
    "lemon":       ["resinous", "woody", "herbal"],
    "lime":        ["resinous", "woody", "herbal"],
    "orange":      ["resinous", "woody", "herbal"],
    "lemongrass":  ["resinous", "woody", "herbal"],
    # -- sous-familles fruit à noyau -> mêmes cibles que "stone fruit" --
    "apricot":     ["spicy", "woody"],
    "peach":       ["spicy", "woody"],
    "pear":        ["spicy", "woody"],
    # -- sous-familles tropical/fruité -> mêmes cibles que "tropical" --
    "pineapple":    ["resinous", "dank", "spicy"],
    "passion fruit": ["resinous", "dank", "spicy"],
    "melon":        ["resinous", "dank", "spicy"],
    "coconut":      ["resinous", "dank", "spicy"],
    "bubblegum":    ["resinous", "dank", "spicy"],
    "fruity":       ["resinous", "dank", "spicy"],
    # -- registre baie/fruit sombre -> plus proche du dank/terreux que du tropical --
    "berry":        ["earthy", "dank", "woody"],
    "black currant": ["earthy", "woody", "spicy"],
    "dried fruit":  ["woody", "spicy", "earthy"],
    # -- sous-familles florales -> mêmes cibles que "floral" --
    "rose":            ["earthy", "woody", "spicy"],
    "sweet aromatic":  ["earthy", "woody", "spicy"],
    "white wine":      ["earthy", "woody", "spicy"],
    # -- sous-familles herbacées -> mêmes cibles que "herbal" --
    "grassy":   ["citrus", "floral"],
    "hay":      ["citrus", "floral"],
    "mint":     ["citrus", "floral"],
    "tea":      ["citrus", "floral"],
    "green tea": ["citrus", "floral"],
    # -- sous-familles boisées/résineuses --
    "cedar":    ["citrus", "tropical", "floral"],   # -> mêmes cibles que "woody"
    "pine":     ["citrus", "tropical"],             # -> mêmes cibles que "resinous"
    # -- épicé --
    "black pepper": ["tropical", "floral", "stone fruit"],  # -> mêmes cibles que "spicy"
}
