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
`ALIASES` (résolution de composés, indépendante des notes),
`DESCRIPTOR_ALIASES`/`CONTRAST_AFFINITY` (vocabulaire descripteur,
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

# Option --biotransform (redirection géraniol->citronellol / linalol->
# alpha-terpinéol via une table BIOTRANSFORMATIONS) IMPLÉMENTÉE PUIS RETIRÉE
# le 2026-08-12 (décision utilisateur). La science derrière restait solide
# (King & Dickinson 2003, FEMS Yeast Research, deux souches convergentes ;
# corroboré par Michel et al. 2019) — le problème était l'INTÉGRATION, pas la
# source : `hop_compound(m, biotransform=True)` redirige la molécule demandée
# vers son précurseur SANS vérifier si ce précurseur est déjà, séparément,
# une entrée du même profil de note. Sur les 29 notes réelles qui demandent
# du citronellol, LES 29 demandent aussi du géraniol (chevauchement total,
# vérifié) : la même mesure de géraniol d'un houblon comptait donc deux fois
# dans le score (une fois comme "géraniol", une fois redirigée comme
# "citronellol"), gonflant le classement de façon non réfléchie plutôt que
# reflétant une vraie contribution supplémentaire. Vérifié en direct : change
# le rang #1 sur plusieurs notes réelles (ex. "coriander" : Sabro/Ekuanot
# s'inversent). Corriger le double comptage aurait ajouté de la complexité
# à une hypothèse déjà étroite (une seule souche « standard », non vérifiable
# par hopmatch) pour un bénéfice marginal — cohérent avec le retrait de
# `combine()` le même jour pour des raisons similaires (voir matching.py).
# Ne pas réintroduire sans corriger le double comptage à la racine (ex.
# exclure de la redirection toute molécule dont le précurseur est déjà,
# indépendamment, demandé par la même note).

# Normalisation des variantes de descripteurs entre sources (pluriel, formulation).
# Amorce curée ; appliquée à l'ingestion (ingest._ingest_variety), pas dans
# parsers.parse_descriptors qui reste un parseur brut sans connaissance métier.
# À enrichir au fil des variétés réellement ingérées (crawl_barthhaas/crawl_yakima).
DESCRIPTOR_ALIASES: dict[str, str] = {
    "citrus fruit": "citrus", "citrus fruits": "citrus",
    "stonefruit": "stone fruit", "stone fruits": "stone fruit",
    "berries": "berry", "tropical fruit": "tropical", "tropical fruits": "tropical",
    "woody/resinous": "woody", "spice": "spicy", "spices": "spicy",
    # -- BeerMaverick (ingest_beermaverick, tags #hashtag par page) : vrais
    # renommages du MÊME concept, pas des sous-familles (celles-ci vont dans
    # CONTRAST_AFFINITY ci-dessous, en gardant le terme précis visible plutôt
    # que de l'écraser) --
    "resin": "resinous", "cannabis": "dank", "black tea": "tea",
    "slightly spicy": "spicy",
    # -- Yakima Chief (aroma_values/sensory_values, roue d'arôme T26) : un des
    # 15 axes fixes de leur taxonomie Contentstack est mal étiqueté "Pomme"
    # (français) au lieu de "Apple", MÊME sous le filtre de requête Algolia
    # publish_details.locale:"en-us" -- vérifié en direct (2026-08-19,
    # signalé par l'utilisateur) : ce n'est PAS un mélange de locale côté
    # hopmatch (une seule requête, un seul filtre en-us, déjà appliqué), mais
    # une erreur de saisie dans LEUR CMS -- l'entrée taxonomique porte le même
    # uid Contentstack (cs95db0a8ac5cfd199) sur toutes les variétés qui
    # l'utilisent, donc une coquille unique et cohérente, pas un champ
    # aléatoirement traduit. Les 14 autres axes sont bien en anglais (vérifié
    # sur l'ensemble des 153 variétés du catalogue).
    "pomme": "apple",
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
    "tangerine":   ["resinous", "woody", "herbal"],
    "mandarin":    ["resinous", "woody", "herbal"],
    "marmalade":   ["resinous", "woody", "herbal"],
    # -- sous-familles fruit à noyau -> mêmes cibles que "stone fruit" --
    "apricot":     ["spicy", "woody"],
    "peach":       ["spicy", "woody"],
    "pear":        ["spicy", "woody"],
    "apple":       ["spicy", "woody"],
    "cherry":      ["spicy", "woody"],
    "plum":        ["spicy", "woody"],
    # -- sous-familles tropical/fruité -> mêmes cibles que "tropical" --
    "pineapple":    ["resinous", "dank", "spicy"],
    "passion fruit": ["resinous", "dank", "spicy"],
    "melon":        ["resinous", "dank", "spicy"],
    "coconut":      ["resinous", "dank", "spicy"],
    "bubblegum":    ["resinous", "dank", "spicy"],
    "fruity":       ["resinous", "dank", "spicy"],
    "watermelon":   ["resinous", "dank", "spicy"],
    "honeydew":     ["resinous", "dank", "spicy"],
    "lychee":       ["resinous", "dank", "spicy"],
    "mango":        ["resinous", "dank", "spicy"],
    "guava":        ["resinous", "dank", "spicy"],
    "banana":       ["resinous", "dank", "spicy"],
    "nectar":       ["resinous", "dank", "spicy"],
    "papaya":       ["resinous", "dank", "spicy"],
    # -- registre baie/fruit sombre -> plus proche du dank/terreux que du tropical --
    "berry":        ["earthy", "dank", "woody"],
    "black currant": ["earthy", "woody", "spicy"],
    "dried fruit":  ["woody", "spicy", "earthy"],
    "raspberry":    ["earthy", "dank", "woody"],
    "blackberry":   ["earthy", "dank", "woody"],
    "strawberry":   ["earthy", "dank", "woody"],
    "blueberry":    ["earthy", "dank", "woody"],
    "redcurrant":   ["earthy", "dank", "woody"],
    "redberry":     ["earthy", "dank", "woody"],
    "loganberry":   ["earthy", "dank", "woody"],
    "elderberry":   ["earthy", "dank", "woody"],
    "gooseberry":   ["earthy", "dank", "woody"],
    "dark fruit":   ["earthy", "dank", "woody"],
    "fig":          ["woody", "spicy", "earthy"],  # -> mêmes cibles que "dried fruit"
    # -- sous-familles florales -> mêmes cibles que "floral" --
    "rose":            ["earthy", "woody", "spicy"],
    "sweet aromatic":  ["earthy", "woody", "spicy"],
    "white wine":      ["earthy", "woody", "spicy"],
    "jasmine":         ["earthy", "woody", "spicy"],
    "lilac":           ["earthy", "woody", "spicy"],
    "magnolia":        ["earthy", "woody", "spicy"],
    "hibiscus":        ["earthy", "woody", "spicy"],
    "geranium":        ["earthy", "woody", "spicy"],
    "chamomile":       ["earthy", "woody", "spicy"],
    "potpourri":       ["earthy", "woody", "spicy"],
    "blossom":         ["earthy", "woody", "spicy"],
    "lavender":        ["earthy", "woody", "spicy"],
    "grapes":          ["earthy", "woody", "spicy"],  # -> mêmes cibles que "white wine"
    "sauvignon blanc": ["earthy", "woody", "spicy"],  # -> mêmes cibles que "white wine"
    "wine":            ["earthy", "woody", "spicy"],  # -> mêmes cibles que "white wine"
    "vanilla":         ["earthy", "woody", "spicy"],  # -> mêmes cibles que "sweet aromatic"
    "caramel":         ["earthy", "woody", "spicy"],  # -> mêmes cibles que "sweet aromatic"
    "honey":           ["earthy", "woody", "spicy"],  # -> mêmes cibles que "sweet aromatic"
    "toffee":          ["earthy", "woody", "spicy"],  # -> mêmes cibles que "sweet aromatic"
    "molasses":        ["earthy", "woody", "spicy"],  # -> mêmes cibles que "sweet aromatic"
    "chocolate":       ["earthy", "woody", "spicy"],  # -> mêmes cibles que "sweet aromatic"
    "candy":           ["earthy", "woody", "spicy"],  # -> mêmes cibles que "sweet aromatic"
    "candied fruit":   ["earthy", "woody", "spicy"],  # -> mêmes cibles que "sweet aromatic"
    # -- sous-familles herbacées -> mêmes cibles que "herbal" --
    "grassy":   ["citrus", "floral"],
    "hay":      ["citrus", "floral"],
    "mint":     ["citrus", "floral"],
    "tea":      ["citrus", "floral"],
    "green tea": ["citrus", "floral"],
    "sage":      ["citrus", "floral"],
    "thyme":     ["citrus", "floral"],
    "dill":      ["citrus", "floral"],
    "fennel":    ["citrus", "floral"],
    "eucalyptus": ["citrus", "floral"],
    "menthol":   ["citrus", "floral"],
    "cucumber":  ["citrus", "floral"],
    # -- sous-familles boisées/résineuses --
    "cedar":    ["citrus", "tropical", "floral"],   # -> mêmes cibles que "woody"
    "pine":     ["citrus", "tropical"],             # -> mêmes cibles que "resinous"
    "tobacco":  ["citrus", "tropical", "floral"],   # -> mêmes cibles que "woody"
    "leather":  ["citrus", "tropical", "floral"],   # -> mêmes cibles que "woody"
    "oak":      ["citrus", "tropical", "floral"],   # -> mêmes cibles que "woody"
    "incense":  ["citrus", "tropical"],             # -> mêmes cibles que "resinous"
    # -- épicé --
    "black pepper": ["tropical", "floral", "stone fruit"],  # -> mêmes cibles que "spicy"
    "curry":        ["tropical", "floral", "stone fruit"],
    "ginger":       ["tropical", "floral", "stone fruit"],
    "cinnamon":     ["tropical", "floral", "stone fruit"],
    "clove":        ["tropical", "floral", "stone fruit"],
    "nutmeg":       ["tropical", "floral", "stone fruit"],
    "pepper":       ["tropical", "floral", "stone fruit"],
    "anise":        ["tropical", "floral", "stone fruit"],
    "licorice":     ["tropical", "floral", "stone fruit"],
    # -- terreux (registre allium/savoureux, proche des houblons dits "earthy") --
    "onion":  ["floral"],
    "garlic": ["floral"],
}
