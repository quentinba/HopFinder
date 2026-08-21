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

# Catégories aromatiques par composé, croisées à la main contre le tableau
# "Compound Descriptions" de Scott Janish, The New IPA (p.22 -- image fournie
# par l'utilisateur, 2026-08-21, T73 : "double check that the description of
# molecules is completed by this figure... if some smell or taste is missing
# from the infobox of each compound, add them"). Source DISTINCTE de
# Flavornet (livre de brassage, pas une mesure GC-O) -- jamais fusionnée
# silencieusement : `matching.compound_descriptors` l'ajoute à part, citée
# ("Janish, The New IPA"), uniquement quand la catégorie n'est pas DÉJÀ
# représentée par un mot Flavornet existant (même racine -- ex. Flavornet
# "wood" == "Woody" du livre, pas de doublon ajouté).
#
# Vérifié composé par composé contre le tableau du livre, restreint aux
# composés RÉELLEMENT mesurés dans `hop_composition` actuellement (les
# molécules `MOLECULES` sans CID ou jamais présentes dans les données
# houblon réelles, ex. limonene/terpinolene/citronellol/geranial/methyl-
# chavicol, n'ont pas d'entrée ici -- ajouter une catégorie qui ne
# s'affichera jamais serait une entrée morte) :
#   - geraniol -> Floral (le livre liste "geraniol" littéralement)
#   - linalool -> Citrus (idem, "linalool" littéral)
#   - myrcene -> Herbal (idem, "myrcene" littéral)
#   - humulene, beta-pinene, farnesene -> Woody (le livre liste "humulene",
#     "β-pinene", "farnesene" littéralement sous Woody)
#   - caryophyllene -> Woody ET Spicy (le livre liste "β-caryophyllene" dans
#     LES DEUX catégories -- déjà entièrement couvert par Flavornet "wood,
#     spice" dans notre base, aucun ajout visible n'en résulte, mais gardé
#     ici comme fait de référence exact, pas une supposition)
#   - thiols -> Berry & Currant (le livre liste "4-mercapto-4-methylpentan-
#     2-one", soit 4MMP -- déjà agrégé sous "thiols" par `ALIASES` ci-dessus,
#     donc l'association s'applique de plein droit à notre composé agrégé ;
#     seul cas où Flavornet ne résout RIEN pour ce composé -- voir
#     `compound_descriptors` -- donc le premier et unique descripteur visible)
# Explicitement PAS ajoutés faute de correspondance vérifiable dans le
# tableau du livre : "isobutyrate"/"ketones" (composés agrégés BarthHaas,
# aucune entrée nominative dans le livre -- leur assigner "raspberry ketone"
# / Berry & Currant serait une supposition non vérifiable sur QUELLE cétone
# précise BarthHaas mesure réellement, même principe que le refus déjà
# documenté de deviner un CID PubChem) ; "selinene" (absent du tableau du
# livre, aucune des 12 catégories ne le cite).
JANISH_COMPOUND_CATEGORIES: dict[str, list[str]] = {
    "geraniol": ["floral"],
    "linalool": ["citrus"],
    "myrcene": ["herbal"],
    "humulene": ["woody"],
    "beta-pinene": ["woody"],
    "farnesene": ["woody"],
    "caryophyllene": ["woody", "spicy"],
    "thiols": ["berry & currant"],
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
    # 15 axes fixes de leur taxonomie Contentstack est étiqueté "Pomme" au
    # lieu de "Apple" -- pris pour une coquille de saisie française (2026-08-19,
    # signalé par l'utilisateur, "Pomme" détecté comme seul terme non-anglais
    # de la roue). **Correction (2026-08-19, en creusant AROMA_WHEEL_DEFINITIONS
    # ci-dessous) : PAS une coquille.** Le "Hop Sensory Ballot" officiel de
    # Yakima Chief (`Hop_Sensory_Ballot_V2.pdf`, révisé juin 2021, télécharge
    # depuis leur propre site) utilise LITTÉRALEMENT "POMME" comme intitulé de
    # catégorie officiel (à côté de DRIED FRUIT, BERRY, STONE FRUIT...) --
    # terme professionnel standard en dégustation (vin/cidre/bière) pour la
    # famille "fruits à pépins" (pomme/poire), pas du français mal placé. Alias
    # conservé tel quel : "apple" reste plus clair pour un public GUI non
    # spécialiste que "pomme", mais ce n'est plus documenté comme la
    # correction d'un bug source -- juste un choix d'affichage.
    "pomme": "apple",
}

# Définitions des 15 catégories de la roue d'arôme quantitative Yakima
# (`hop_aroma_intensity`, T26) -- demande utilisateur explicite (2026-08-19) :
# "grassy, herbal and vegetal mean the same thing... can you help me
# understand them". Vérifié : elles ne sont PAS synonymes (corrélation
# grassy/vegetal mesurée sur les données réelles : Pearson r=0.16 sur 81
# houblons à vegetal>0, écart moyen 13.8 points -- Saaz par exemple a
# grassy=75/vegetal=8, à l'opposé l'un de l'autre). Sourcé au mot près sur le
# "Hop Sensory Ballot" officiel Yakima Chief (`Hop_Sensory_Ballot_V2.pdf`,
# révisé juin 2021, colonne "Specific Aromas" par catégorie -- télécharge
# depuis leur propre site, archive Wayback Machine du 2024-06-27 utilisée
# faute d'URL directe encore valide après leur migration de site) : la
# distinction est claire une fois les exemples posés -- grassy = herbe
# fraîchement coupée/foin (végétal SEC), herbal = thé/menthe/romarin (herbe
# AROMATIQUE culinaire), vegetal = chou/céleri/poivron/plant de tomate
# (légume, souvent proche d'un défaut en brassage) -- trois notions
# olfactives réellement distinctes, pas une seule "goût d'herbe fraîche"
# comme perçu au premier abord. Clés = exactement le vocabulaire
# `hop_aroma_intensity` (15 termes, voir `matching._intensity_vocabulary`) ;
# "apple" correspond à leur catégorie "Pomme" (voir alias ci-dessus).
AROMA_WHEEL_DEFINITIONS: dict[str, str] = {
    "dried fruit": "Date, dried apricot, dried fig, raisin",
    "berry": "Black currant, blueberry, grape, raspberry, strawberry",
    "stone fruit": "Apricot, cherry, peach, plum",
    "apple": "Apple, pear (Yakima's “Pomme” category)",
    "melon": "Cantaloupe, cucumber, honeydew, watermelon",
    "tropical": "Banana, coconut, guava, lychee, mango, passion fruit, pineapple",
    "citrus": "Grapefruit, lemon, lemongrass, lime, orange",
    "floral": "Cherry blossom, geranium, jasmine, rose, soapy",
    "herbal": "Black tea, dill, green tea, mint, rosemary, thyme "
             "— aromatic culinary herbs/tea",
    "vegetal": "Cabbage, celery, green pepper, tomato plant "
              "— savory vegetable notes, often a caution flag in brewing",
    "grassy": "Green grass, hay — freshly cut grass, not aromatic herbs",
    "earthy": "Barnyard, compost, geosmin, leather, mushroom, soil",
    "woody": "Cedar, pine, resinous, sawdust, tea tree, tobacco",
    "spicy": "Anise, black pepper, cinnamon, clove, ginger",
    "sweet aromatic": "Bubblegum, caramel, chocolate, creamy, honey, vanilla",
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
