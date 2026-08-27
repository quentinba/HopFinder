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

# molécule -> (descripteur odeur, seuil olfactif ppb | None -- RETIRÉ, voir
# ci-dessous, JAMAIS lu pour le scoring, PubChem CID | None)
#
# **Champ seuil (index 1) neutralisé à None partout (T75, 2026-08-21,
# décision utilisateur explicite -- "update the thresholds according to
# flavordb2... don't consider oav when we don't have any, put none... never
# to the old hardcoded literals").** Ces 14 valeurs étaient saisies à la
# main (littérature générale, sources non tracées au niveau du commit) et
# seedées une fois pour toutes dans la table `molecules` par `seed_
# reference`, jamais revues depuis -- `matching.molecular_scores` les lisait
# encore au moment de l'ajout de --oav. Root cause vérifiée en direct avant
# ce changement : pour 5 des 14, `flavordb2_thresholds` (734 composés,
# `ingest_flavordb2`, seuils RÉELLEMENT scrapés) porte une valeur DIFFÉRENTE
# de celle codée ici -- caryophyllène (64 ici vs 77.0 chez FlavorDB2),
# géraniol (4 vs 39.5, facteur 10 !), linalol (6 vs 7.0), beta-pinène (140
# vs 140.0, identique -- probablement la source originale de cette valeur
# précise), citronellol (8 vs 11.0) : le scoring utilisait donc un chiffre
# qui divergeait silencieusement de la propre donnée scrapée du projet, sans
# qu'aucun résultat affiché ne le signale. `--oav` résout désormais les
# seuils EN DIRECT depuis `flavordb2_thresholds` via CID->CAS (voir
# `matching.oav_thresholds`) -- ce champ ne sert donc plus qu'à documenter
# l'HISTORIQUE (gardé à None, pas supprimé, pour ne pas casser la forme du
# tuple utilisée ailleurs -- ex. `compound_descriptors` lit l'index 2/CID).
# Myrcène en particulier (voir docs/DATA_SOURCES.md pour le détail complet
# de la littérature bière/eau contradictoire) : AUCUNE valeur ponctuelle
# n'est défendable dans l'intervalle 30-1000 ppb rapporté en bière, donc
# None reste le seul choix honnête, pas seulement "en attendant FlavorDB2".
MOLECULES: dict[str, tuple[str, float | None, int | None]] = {
    "myrcene":        ("résineux, vert, géranium", None, 31253),
    "humulene":       ("boisé, houblon, épicé", None, 5281520),
    "caryophyllene":  ("boisé, poivré", None, 5281515),
    "farnesene":      ("floral, vert, boisé", None, 5281516),
    "geraniol":       ("rose, géranium, floral", None, 637566),
    "linalool":       ("floral, agrume", None, 6549),
    "beta-pinene":    ("pin, résineux", None, 14896),
    "selinene":       ("boisé, herbacé", None, 442393),
    "thiols":         ("passion, pamplemousse, cassis", None, None),
    "limonene":       ("agrume, orange", None, 22311),
    "terpinolene":    ("boisé, frais, agrume/pin", None, 11463),
    "citronellol":    ("rose, agrume", None, 8842),
    "geranial":       ("citron, citronnelle", None, 638011),
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

# Définitions des 15 catégories (+1, "menthol", ajoutée en T79 -- voir plus
# bas) de la roue d'arôme quantitative Yakima
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
    # 16e catégorie, AJOUTÉE (T79, 2026-08-22, demande utilisateur explicite
    # -- source BarthHaas, PAS le Hop Sensory Ballot Yakima comme les 15
    # ci-dessus, donc citée séparément) : leur roue d'arôme quantitative a
    # une catégorie "menthol" sans équivalent chez Yakima -- vérifié en
    # direct sur 97 variétés BarthHaas (data-rose-labels, 100% identique),
    # jamais force-fit sur une catégorie existante qui ne convient pas.
    # Mots réels observés sous cette catégorie sur le site (classe CSS
    # "menthol", `parsers.parse_barthhaas_tastes`) : Eucalyptus, Lemon
    # Balm, Menthol, Mint, Sage.
    "menthol": "Eucalyptus, lemon balm, menthol, mint, sage (BarthHaas category, "
              "no Yakima equivalent)",
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

# Annotation de survie au procédé par composé (T74, 2026-08-21, demande
# utilisateur explicite, spec complète fournie). Vérifié composé par composé
# contre `SELECT DISTINCT compound, source FROM hop_composition` (aromahops.db
# réel) le jour de l'ajout -- 11 composés d'huile essentielle présents
# (`matching.NON_AROMA_DISPLAY` exclut alpha_acid/beta_acid/co_humulone/
# total_oil, jamais annotés ici, voir plus bas), tous les 11 mappés avec
# certitude. α-pinène et β-citronellol (cités par la figure Janish
# ci-dessous) NE SONT PAS présents dans nos données réelles (ni BarthHaas ni
# Yakima ne les mesurent actuellement) -- pas d'entrée fabriquée pour un
# composé qui n'apparaîtrait jamais dans la GUI.
#
# ⚠️ DEUX NIVEAUX DE PROVENANCE DISTINCTS DANS LA MÊME STRUCTURE, à ne
# jamais confondre (y compris dans les commentaires qui suivent) :
#   - "class"/"subclass" (LA TAXONOMIE CHIMIQUE) : SOURCÉE, solide, PAS un
#     prior -- Scott Janish, The New IPA, figure "Chemical compositions of
#     the essential oils of hops" (voir docs/DATA_SOURCES.md pour le détail
#     complet de la citation).
#   - "annotation"/"confidence" (LA SURVIE AU PROCÉDÉ) : un PRIOR qualitatif
#     de brassage, au MÊME TITRE que CONTRAST_AFFINITY ci-dessus (voir aussi
#     README.md, section "Ce qui est un prior, pas une donnée") -- les taux
#     de transfert publiés dépendent de l'équipement/temps de contact/
#     température/levure ; les chiffrer ici serait exactement la précision-
#     déchet déjà refusée ailleurs dans ce projet (absence d'OAV réel,
#     retrait de combine() -- voir la section "But" de CLAUDE.md). D'où la
#     contrainte non négociable : AUCUNE valeur numérique nulle part dans
#     cette structure, jamais consommée par un score (TF-IDF/--oav/blends),
#     purement affichée -- voir `matching.process_survival` et son usage
#     GUI (app._process_survival_label).
#
# Note sesquiterpènes : leurs produits d'oxydation (humulénol, farnésol)
# changent de classe et passent en oxygénés -- d'où "contribue via
# oxydation" plutôt qu'un simple "survit"/"ne survit pas" binaire, pour ne
# pas suggérer que la molécule mesurée ARRIVE telle quelle dans le verre.
#
# Note soufrés : la figure Janish éclate cette classe en thiols, sulfures et
# thioesters (ces deux derniers indésirables) ; BarthHaas ne mesure QUE les
# thiols agrégés (voir schema.py, `hop_composition` compound="thiols").
# Sous-classe explicitement étiquetée "Thiols", jamais "Sulfur compounds"
# générique, pour ne pas suggérer une homogénéité que la source dément.
# Annotation reformulée (2026-08-21, signalé par l'utilisateur en direct :
# "there is a redundancy... 'late / dry hop'... but is still present") --
# "late / dry hop" (thiols) n'était qu'une PERMUTATION des mêmes mots que
# "dry hop / late additions" (monoterpènes) : deux entrées PROCESS_SURVIVAL
# distinctes avec des explications différentes (pas un bug de duplication),
# mais un libellé qui se LIT comme un doublon dans la légende. Reformulé en
# "extremely volatile — dry hop only" : même recommandation pratique, mais
# formulation distincte reflétant la raison chimique différente (volatilité
# extrême + quantités traces µg/kg, PAS la simple perte par évaporation des
# hydrocarbures monoterpéniques) -- ne se lit plus comme un réarrangement
# du même libellé.
#
# Cas particuliers, PAS des omissions -- les 11 composés RÉELLEMENT
# présents dans hop_composition sont TOUS mappés ci-dessous (vérifié,
# aucun composé réel n'est laissé sans décision) :
#   - "isobutyrate"/"ketones" classées "esters"/"ketones" par NOMENCLATURE
#     CHIMIQUE DIRECTE ("-ate" = ester, "ketones" = nom littéral de la
#     sous-classe -- pas une supposition sur un nom approchant) MAIS avec
#     confidence="low", car BarthHaas ne précise JAMAIS quelle(s)
#     molécule(s) précise(s) composent cette valeur agrégée (même réserve
#     déjà documentée pour le refus de deviner un CID PubChem sur un nom
#     flou -- voir ingest.py, section PubChem).
#   - "selinene" EST listé sous Sesquiterpènes dans le tableau du ticket
#     (avec humulène/caryophyllène/farnésène) -- mappé normalement,
#     confidence="high". (Ne pas confondre avec le tableau "Compound
#     Descriptions" d'un AUTRE extrait du même livre, utilisé pour T73
#     (`JANISH_COMPOUND_CATEGORIES` ci-dessus) : celui-là ne listait PAS
#     sélinène, mais ce n'est pas la source utilisée ici.)
# Composés `MOLECULES` cités par la figure mais absents de nos données
# réelles (α-pinène, β-citronellol) : voir le commentaire au-dessus de
# `PROCESS_SURVIVAL` -- pas d'entrée pour un composé qui ne s'afficherait
# jamais.
#
# `class`="Oxygen containing" (2026-08-27, corrigé sur signalement direct de
# l'utilisateur -- une session précédente avait paraphrasé le libellé de la
# figure Janish en "Oxygenated", pas le terme littéral de la source ("Oxygen
# Containing Compounds"). Puisque ce champ est documenté ci-dessus comme
# SOURCÉ (pas un prior), il doit reprendre le libellé exact du livre --
# corrigé sur les 4 entrées concernées (linalool/geraniol/ketones/
# isobutyrate).
PROCESS_SURVIVAL: dict[str, dict[str, str]] = {
    "myrcene":       {"class": "Hydrocarbons", "subclass": "Monoterpenes",
                      "annotation": "boil-sensitive, survives whirlpool", "confidence": "high"},
    "beta-pinene":   {"class": "Hydrocarbons", "subclass": "Monoterpenes",
                      "annotation": "dry hop / late additions", "confidence": "high"},
    "humulene":      {"class": "Hydrocarbons", "subclass": "Sesquiterpenes",
                      "annotation": "direct traces, contributes via oxidation", "confidence": "high"},
    "caryophyllene": {"class": "Hydrocarbons", "subclass": "Sesquiterpenes",
                      "annotation": "direct traces, contributes via oxidation", "confidence": "high"},
    "farnesene":     {"class": "Hydrocarbons", "subclass": "Sesquiterpenes",
                      "annotation": "direct traces, contributes via oxidation", "confidence": "high"},
    "selinene":      {"class": "Hydrocarbons", "subclass": "Sesquiterpenes",
                      "annotation": "direct traces, contributes via oxidation", "confidence": "high"},
    "linalool":      {"class": "Oxygen containing", "subclass": "Monoterpene alcohols",
                      "annotation": "boil-sensitive, survives whirlpool", "confidence": "high"},
    "geraniol":      {"class": "Oxygen containing", "subclass": "Monoterpene alcohols",
                      "annotation": "heat-resistant, persists through boiling", "confidence": "high"},
    "ketones":       {"class": "Oxygen containing",
                      "subclass": "Other (ketones, esters, aldehydes, epoxides)",
                      "annotation": "intermediate transfer", "confidence": "low"},
    "isobutyrate":   {"class": "Oxygen containing",
                      "subclass": "Other (ketones, esters, aldehydes, epoxides)",
                      "annotation": "intermediate transfer", "confidence": "low"},
    "thiols":        {"class": "Sulfur compounds", "subclass": "Thiols",
                      "annotation": "extremely volatile — dry hop only", "confidence": "medium"},
}

# Clarification en une phrase par annotation DISTINCTE de PROCESS_SURVIVAL
# (2026-08-21, demande utilisateur explicite, suite directe de T74 : "I'm
# not sure to understand the difference [between] 'direct traces,
# contribute via oxydation' [and] 'survive boiling'"). Les libellés courts
# de PROCESS_SURVIVAL restent volontairement bruts/factuels (déjà validés
# T74) -- cette table les COMPLÈTE pour la GUI (légende, pas une
# réécriture) plutôt que de les remplacer par un texte plus long qui
# encombrerait chaque ligne de tableau/tooltip. Prior qualitatif au même
# titre que PROCESS_SURVIVAL lui-même (voir son commentaire) -- explique le
# RAISONNEMENT chimique déjà résumé dans les notes du ticket T74, pas une
# nouvelle affirmation.
#
# **Correctif (2026-08-21, même jour, signalé par l'utilisateur en direct) :
# le premier jet de l'entrée "direct traces, contributes via oxidation"
# affirmait un déclencheur ("exposure to oxygen -- dry-hopping, packaging,
# aging") qui n'était PAS dans la donnée fournie -- une inférence perso à
# partir de connaissances générales de brassage, pas une donnée sourcée
# (exactement le type d'erreur que ce projet refuse ailleurs). Corrigé après
# clarification explicite de l'utilisateur : le déclencheur documenté (une
# étude d'extraction Saaz à temps d'ébullition variable, citée dans le livre)
# est une ÉBULLITION LONGUE (>20 min), PAS une oxydation au dry-hop/
# conditionnement/garde -- et cette étude précise ne couvre QUE humulène et
# caryophyllène, PAS farnésène/sélinène (regroupés sous la même annotation
# de CLASSE par la figure de taxonomie, une source différente et plus
# générale, sans que le déclencheur précis leur soit confirmé pour autant).
# "caryophyllene oxide"/"humulene epoxide" (noms de produits d'oxydation)
# retirés de la même façon -- jamais donnés par l'utilisateur, une
# supposition chimique plausible mais non vérifiée à ne pas afficher comme
# un fait. Seuls "humulénol"/"farnésol" restent, cités tels quels dans la
# spec originale du ticket T74.
PROCESS_SURVIVAL_EXPLANATIONS: dict[str, str] = {
    "dry hop / late additions":
        "Volatile, non-polar hydrocarbon — mostly stripped away by evaporation during a "
        "boil. Only additions with little or no boil exposure (dry hop, whirlpool, "
        "flame-out) keep it close to the measured amount. Grouped with myrcene by "
        "subclass (Monoterpenes) but without the same specifically-quantified boil-time "
        "figures — see 'boil-sensitive, survives whirlpool' below for those.",
    "direct traces, contributes via oxidation":
        "Heavier than the monoterpene hydrocarbons above, so a small amount can persist "
        "as a direct trace of the same molecule. For humulene and caryophyllene "
        "specifically, a Saaz extraction-timing study found that producing the "
        "spicy-noted oxidized compounds (e.g. humulene → humulenol) requires a LONG boil "
        "(over ~20 minutes) — not dry hop or late additions. Farnesene and selinene share "
        "this class-level annotation (sesquiterpene hydrocarbons that can oxidize into "
        "different, oxygenated compounds, e.g. farnesene → farnesol) but the boil-time "
        "specifics above are not established for them in this source.",
    "boil-sensitive, survives whirlpool":
        # Corrigé 2026-08-27 (signalé par l'utilisateur, discussion avec un autre outil
        # IA en lisant Scott Janish, The New IPA) : le libellé précédent pour LE LINALOL
        # SEUL ("survives boiling") était FAUX -- l'ancien raisonnement ("oxygéné donc peu
        # volatil donc résiste à l'ébullition") ne tient pas : Janish donne pour le
        # linalol le MÊME ordre de perte QUANTIFIÉ que le myrcène sous ébullition active
        # (~50% réduit à 10 min, quasi rien à 60 min, message utilisateur explicite : "This
        # sentence is true for myrcene and linalol in Scott Janish's book"). D'où le
        # partage de CETTE MÊME annotation entre myrcène et linalol (retour utilisateur
        # direct : "Why myrcene and linalol don't have the same tooltip? ... this is the
        # same behaviour right?" -- un premier jet les avait gardés séparés par erreur,
        # corrigé le même jour). Beta-pinène reste sur l'annotation générique "dry hop /
        # late additions" : même sous-classe chimique (Monoterpenes) que le myrcène, mais
        # pas la même donnée quantifiée spécifique -- jamais étendue à un composé sans
        # preuve. Ce qui rend le linalol (et par extension le myrcène) "survivable"
        # (recherche Yakima Chief, voir CLAUDE.md section "Règles procédé & survivables")
        # est plus étroit qu'une résistance générale à l'ébullition : ajouté au whirlpool/
        # knockout (après l'ébullition active, exposition moindre), une part significative
        # passe dans le fermenteur. NE PAS regrouper avec le géraniol (voir son annotation
        # séparée "heat-resistant, persists through boiling" ci-dessous) : même sous-classe
        # chimique que le linalol mais comportement de boil RÉELLEMENT différent, précisé
        # le même jour par l'utilisateur après une première correction qui les avait
        # encore confondus.
        "Scott Janish's The New IPA reports the same order of loss for myrcene and "
        "linalool under active boiling — roughly 50% reduced after 10 minutes, "
        "essentially gone after a full 60-minute boil (linalool isn't boil-resistant "
        "just because it's oxygenated). What makes them 'survivable' (Yakima Chief's "
        "research) is narrower than boil-resistance: added at whirlpool/knockout — past "
        "active boiling, lower heat exposure — a meaningful fraction carries through "
        "into the fermenter.",
    "heat-resistant, persists through boiling":
        # Ajouté 2026-08-27 (même correction round, relayé par l'utilisateur depuis Scott
        # Janish, The New IPA) : géraniol a un comportement de boil DIFFÉRENT du linalol
        # malgré la même sous-classe chimique ("Monoterpene alcohols") -- groupé par
        # Janish avec beta-eudesmol/humulène/humulene epoxide I/beta-farnésène/
        # caryophyllène (points d'ébullition plus hauts, décroissance progressive mais
        # encore présents à 60 min), PAS avec myrcène/linalol (perte quasi totale à 60
        # min). Mécanisme chimique différent de celui des sesquiterpènes ci-dessus
        # (persistance directe, pas une oxydation vers un nouveau composé) -- seule la
        # résistance thermique RELATIVE est comparable, jamais présentée comme le même
        # phénomène chimique.
        "Unlike linalool (same 'Monoterpene alcohols' subclass), geraniol has a higher "
        "boiling point and is more resistant to boiling wort — Scott Janish's The New "
        "IPA groups it with humulene/caryophyllene/farnesene in this respect: it "
        "decreases gradually over a full boil but is still present at 60 minutes, unlike "
        "myrcene/linalool which are essentially gone by then. Also the key "
        "biotransformation molecule: converted by yeast during active fermentation into "
        "β-citronellol.",
    "intermediate transfer":
        "BarthHaas doesn't specify which individual molecule(s) make up this aggregated "
        "measurement, so no volatility-based transfer behavior can be stated with "
        "confidence — hence the low confidence rating.",
    "extremely volatile — dry hop only":
        "Present in vanishingly small quantities (µg/kg) and far more volatile than the "
        "hydrocarbons above — boiling drives them off almost entirely, so even the "
        "moderate heat exposure that a late-boil addition tolerates is enough to lose "
        "most of it; aroma impact depends on avoiding prolonged heat exposure altogether.",
}

# Amorce ingrédient -> descripteurs de la roue d'arôme houblon (T76,
# 2026-08-22, demande utilisateur explicite -- "build a dictionary or
# mapping between each ingredient in fooddb and possible note descriptor
# mapping this... I want you to use IA for sure"). Sert à PRÉ-REMPLIR
# (jamais imposer) la couche descripteurs sur `amplify` quand l'utilisateur
# choisit un ingrédient -- toujours éditable dans la GUI, jamais écrit dans
# `note_descriptors` (délibérément vide, voir plus haut : aucune dérivation
# fiable FooDB->descripteurs n'a jamais été établie, cf. l'échec de
# `combine()`). Cette table est un mécanisme DIFFÉRENT : pas une dérivation
# automatique à partir des composés FooDB (déjà tentée, dégénérait -- voir
# `LOW_COVERAGE_WARNING_THRESHOLD` plus haut), mais un jugement direct
# "à quoi ressemble cet ingrédient, en langage d'arôme houblon" -- même
# statut de PRIOR heuristique que `CONTRAST_AFFINITY` ci-dessus (voir
# README, section "Ce qui est un prior, pas une donnée"), jamais une donnée
# vérifiée.
#
# Méthodologie (à respecter pour toute extension future) :
#   1. Auteur = jugement direct de l'assistant (Claude Sonnet 5, 2026-08-22),
#      PAS une dérivation programmatique depuis FooDB/Flavornet/FlavorDB2 --
#      c'est exactement le rapprochement que `note_descriptors` a renoncé à
#      automatiser. Jamais présenté comme une donnée mesurée.
#   2. Vocabulaire de sortie RESTREINT AUX 105 DESCRIPTEURS RÉELS de
#      `hop_descriptors` (vérifié par requête directe sur la base construite,
#      2026-08-22) -- jamais un terme inventé hors de ce vocabulaire, même
#      si un mot plus précis existerait ("coffee", par ex., n'a AUCUNE
#      entrée valable dans ce vocabulaire -- liste vide plutôt qu'un
#      rapprochement forcé sur "toffee"/"chocolate").
#   3. Liste vide `[]` = pas de correspondance arôme défendable trouvée dans
#      ce vocabulaire (ex. "beluga whale", "hot dog") -- PAS "pas encore
#      mappé". Un ingrédient absent du dict entièrement veut dire la même
#      chose (`.get(note, [])` côté `matching`/`app.py`) : les deux cas sont
#      délibérément équivalents, pas de distinction implicite entre eux.
#   4. 2-4 descripteurs maximum par ingrédient, jamais une liste large --
#      l'objectif est une suggestion éditable pertinente, pas une couverture
#      exhaustive du profil FooDB réel de l'ingrédient.
#
# Portée (2026-08-22, demande utilisateur explicite : "All 506 but make me
# review only the 44 curated") : couvre désormais les 506 notes FooDB
# réelles de la base, en DEUX passes datées la même journée. Passe 1 (revue
# manuelle utilisateur) : les 44 ingrédients de l'étude de couverture --oav
# (T76, additions RÉELLEMENT courantes en brassage -- fruits/agrumes/herbes/
# épices usuels en IPA/sour/stout), rédigés ET vérifiés terme à terme contre
# le vocabulaire réel. Passe 2 (même méthodologie, jugement direct, jamais
# une dérivation programmatique, sans revue individuelle systématique par
# l'utilisateur -- accepté explicitement) : les ~462 notes FooDB restantes,
# majoritairement sans rapport avec le houblon (poissons, viandes, plats
# préparés, produits laitiers...) -- honnêtement laissées à `[]` (361 notes
# sur 506, soit 71%) plutôt que de forcer un rapprochement, avec 145
# entrées non vides (fruits, baies, agrumes, herbes, épices, thés, vins/
# spiritueux, quelques légumes/champignons à caractère terreux). Validé par
# script avant publication : les 506 clés correspondent EXACTEMENT aux 506
# notes réelles de `aroma_notes` (aucune manquante, aucune mal orthographiée),
# et chaque terme de chaque valeur appartient au vocabulaire réel des 105
# descripteurs `hop_descriptors` -- voir tests/test_matching.py pour le
# test de non-régression correspondant.
INGREDIENT_DESCRIPTORS: dict[str, list[str]] = {
    'adobo'                                              : [],
    'alaska pollock'                                     : [],
    'alfalfa'                                            : ['hay', 'grassy'],
    'allium'                                             : ['onion', 'garlic'],
    'allspice'                                           : ['clove', 'spicy'],
    'almond'                                             : [],
    'american cranberry'                                 : ['redberry', 'berry', 'fruity'],
    'american lobster'                                   : [],
    'american pokeweed'                                  : [],
    'american shad'                                      : [],
    'anatidae'                                           : [],
    'anchovy'                                            : [],
    'anguilliformes'                                     : [],
    'anise'                                              : ['anise', 'licorice'],
    'apple'                                              : ['apple', 'fruity'],
    'apricot'                                            : ['apricot', 'stone fruit', 'fruity'],
    'arabica coffee'                                     : [],
    'arepa'                                              : [],
    'asparagus'                                          : ['grassy'],
    'atlantic halibut'                                   : [],
    'atlantic herring'                                   : [],
    'atlantic mackerel'                                  : [],
    'atlantic wolffish'                                  : [],
    'avocado'                                            : [],
    'babassu palm'                                       : [],
    'baby food'                                          : [],
    'bagel'                                              : [],
    'baked beans'                                        : [],
    'bamboo shoots'                                      : [],
    'banana'                                             : ['banana', 'tropical', 'fruity'],
    'barley'                                             : [],
    'bean'                                               : [],
    'bearded seal'                                       : [],
    'beefalo'                                            : [],
    'beer'                                               : [],
    'beluga whale'                                       : [],
    'bilberry'                                           : ['blueberry', 'berry', 'fruity'],
    'biscuit'                                            : [],
    'bitter gourd'                                       : [],
    'bivalvia (clam, mussel, oyster)'                    : [],
    'black cabbage'                                      : [],
    'black elderberry'                                   : ['elderberry', 'fruity', 'berry'],
    'black tea'                                          : ['tea'],
    'black walnut'                                       : [],
    'black-eyed pea'                                     : [],
    'blackcurrant'                                       : ['black currant', 'fruity', 'berry'],
    'blue crab'                                          : [],
    'borage'                                             : ['cucumber', 'herbal'],
    'brazil nut'                                         : [],
    'breakfast cereal'                                   : [],
    'breakfast sandwich'                                 : [],
    'broad bean'                                         : [],
    'broccoli'                                           : [],
    'brussel sprouts'                                    : [],
    'bulgur'                                             : [],
    'burdock'                                            : ['earthy'],
    'burrito'                                            : [],
    'butter'                                             : [],
    'butter substitute'                                  : [],
    'butterfat'                                          : [],
    'buttermilk'                                         : [],
    'butternut'                                          : [],
    'cabbage'                                            : [],
    'cake'                                               : [],
    'calabash'                                           : [],
    'candy bar'                                          : ['candy'],
    'canola'                                             : [],
    'capers'                                             : [],
    'caraway'                                            : ['anise', 'licorice'],
    'cardamom'                                           : ['spicy', 'herbal'],
    'carob'                                              : ['chocolate'],
    'carrot'                                             : [],
    'casein'                                             : [],
    'cashew nut'                                         : [],
    'cassava'                                            : [],
    'catfish'                                            : [],
    'catjang pea'                                        : [],
    'cattle (beef, veal)'                                : [],
    'cauliflower'                                        : [],
    'celeriac'                                           : [],
    'celery leaves'                                      : ['herbal'],
    'ceylon cinnamon'                                    : ['cinnamon', 'spicy'],
    'channel catfish'                                    : [],
    'cheese'                                             : [],
    'cherimoya'                                          : ['tropical', 'fruity'],
    'chestnut'                                           : [],
    'chicken'                                            : [],
    'chickpea'                                           : [],
    'chicory'                                            : [],
    'chili'                                              : ['spicy'],
    'chimichanga'                                        : [],
    'chinese cabbage'                                    : [],
    'chinese cinnamon'                                   : ['cinnamon', 'spicy'],
    'chinese mustard'                                    : [],
    'chinese water chestnut'                             : [],
    'chives'                                             : ['onion'],
    'chocolate'                                          : ['chocolate'],
    'chocolate mousse'                                   : ['chocolate'],
    'chocolate spread'                                   : ['chocolate'],
    'chum salmon'                                        : [],
    'cinnamon'                                           : ['cinnamon', 'spicy'],
    'clawed lobster'                                     : [],
    'cloves'                                             : ['clove', 'spicy'],
    'clupeinae (herring, sardine, sprat)'                : [],
    'cocktail'                                           : [],
    'cocoa bean'                                         : ['chocolate'],
    'cocoa butter'                                       : ['chocolate'],
    'cocoa powder'                                       : ['chocolate'],
    'coconut'                                            : ['coconut'],
    'coffee'                                             : [],
    'coffee mocha'                                       : ['chocolate'],
    'coffee substitute'                                  : [],
    'cold cut'                                           : [],
    'colorado pinyon'                                    : [],
    'columbidae (dove, pigeon)'                          : [],
    'common bean'                                        : [],
    'common buckwheat'                                   : [],
    'common cabbage'                                     : [],
    'common grape'                                       : ['grapes', 'fruity'],
    'common hazelnut'                                    : [],
    'common mushroom'                                    : ['earthy'],
    'common oregano'                                     : ['herbal'],
    'common pea'                                         : ['grassy'],
    'common sage'                                        : ['sage', 'herbal'],
    'common thyme'                                       : ['thyme', 'herbal'],
    'common walnut'                                      : [],
    'common wheat'                                       : [],
    'condensed milk'                                     : [],
    'cooking oil'                                        : [],
    'coriander'                                          : ['herbal', 'citrus'],
    'corn'                                               : [],
    'corn chip'                                          : [],
    'corn grits'                                         : [],
    'cornbread'                                          : [],
    'cornmint'                                           : ['mint', 'menthol'],
    'cottonseed'                                         : [],
    'cow milk, pasteurized, vitamin a + d added, 0% fat' : [],
    'cow milk, pasteurized, vitamin a + d added, 1% fat' : [],
    'cow milk, pasteurized, vitamin a + d added, 2% fat' : [],
    'cow milk, pasteurized, vitamin d added, 3.25% fat'  : [],
    'crab'                                               : [],
    'cracker'                                            : [],
    'cream'                                              : [],
    'cream substitute'                                   : [],
    'crisp bread'                                        : [],
    'cucumber'                                           : ['cucumber'],
    'cucurbita'                                          : [],
    'cumin'                                              : ['spicy', 'earthy'],
    'curry powder'                                       : ['curry', 'spicy'],
    'daikon radish'                                      : [],
    'date'                                               : ['dried fruit', 'fruity'],
    'deer'                                               : [],
    'dill'                                               : ['dill', 'herbal'],
    'dolphin fish'                                       : [],
    'domestic pig'                                       : [],
    'dried milk'                                         : [],
    'dripping'                                           : [],
    'dulce de leche'                                     : ['caramel'],
    'eastern oyster'                                     : [],
    'edible shell'                                       : [],
    'egg roll'                                           : [],
    'eggplant'                                           : [],
    'eggs'                                               : [],
    'elderberry'                                         : ['elderberry', 'fruity', 'berry'],
    'empanada'                                           : [],
    'enchilada'                                          : [],
    'endive'                                             : [],
    'european anchovy'                                   : [],
    'european plum'                                      : ['plum', 'fruity'],
    'evaporated milk'                                    : [],
    'evening primrose'                                   : ['floral'],
    'feijoa'                                             : ['tropical', 'fruity'],
    'fennel'                                             : ['fennel', 'herbal', 'licorice'],
    'fig'                                                : ['fig', 'dried fruit', 'fruity'],
    'fish oil'                                           : [],
    'flatfish'                                           : [],
    'flaxseed'                                           : [],
    'focaccia'                                           : [],
    'french plantain'                                    : ['banana', 'tropical', 'fruity'],
    'french toast'                                       : [],
    'frozen yogurt'                                      : [],
    'fruit-flavor drink'                                 : [],
    'frybread'                                           : [],
    'fudge'                                              : ['caramel', 'chocolate'],
    'gadus (common cod)'                                 : [],
    'garden cress'                                       : [],
    'garden onion'                                       : ['onion'],
    'garden rhubarb'                                     : [],
    'garden tomato'                                      : [],
    'garden tomato (var.)'                               : [],
    'garfish'                                            : [],
    'garlic'                                             : ['garlic'],
    'gelatin'                                            : [],
    'gin'                                                : ['citrus', 'floral'],
    'ginger'                                             : ['ginger', 'spicy'],
    'globe artichoke'                                    : [],
    'gooseberry'                                         : ['gooseberry', 'fruity', 'berry'],
    'gram bean'                                          : [],
    'grape'                                              : ['grapes', 'fruity'],
    'grape wine'                                         : ['wine', 'grapes', 'fruity'],
    'grapefruit'                                         : ['grapefruit', 'citrus', 'fruity'],
    'green bean'                                         : ['grassy'],
    'green bell pepper'                                  : ['grassy'],
    'green tea'                                          : ['green tea'],
    'green zucchini'                                     : [],
    'greenland halibut/turbot'                           : [],
    'guava'                                              : ['guava', 'tropical', 'fruity'],
    'haddock'                                            : [],
    'hamburger'                                          : [],
    'hazelnut'                                           : [],
    'heart of palm'                                      : [],
    'herbal tea'                                         : ['herbal', 'tea'],
    'hibiscus tea'                                       : ['hibiscus', 'tea'],
    'highbush blueberry'                                 : ['blueberry', 'fruity', 'berry'],
    'hippoglossus (common halibut)'                      : [],
    'horchata'                                           : [],
    'horseradish'                                        : [],
    'horseradish tree'                                   : [],
    'hot chocolate'                                      : ['chocolate'],
    'hot dog'                                            : [],
    'hushpuppy'                                          : [],
    'hyacinth bean'                                      : [],
    'hyssop'                                             : ['herbal'],
    'ice cream'                                          : [],
    'ice cream cone'                                     : [],
    'icing'                                              : [],
    'italian sweet red pepper'                           : [],
    'jackfruit'                                          : ['tropical', 'fruity'],
    'japanese pumpkin'                                   : [],
    'jerusalem artichoke'                                : [],
    'junket'                                             : [],
    'jute'                                               : [],
    'kale'                                               : [],
    'kefir'                                              : [],
    'ketchup'                                            : [],
    'kiwi'                                               : ['tropical', 'fruity'],
    'kohlrabi'                                           : [],
    'kumquat'                                            : ['citrus', 'orange', 'fruity'],
    'lard'                                               : [],
    'lasagna'                                            : [],
    'leavening agent'                                    : [],
    'leek'                                               : ['onion'],
    'lemon'                                              : ['lemon', 'citrus', 'fruity'],
    'lemon balm'                                         : ['lemon', 'herbal'],
    'lemon grass'                                        : ['lemongrass', 'citrus'],
    'lemon sole'                                         : [],
    'lentils'                                            : [],
    'lettuce'                                            : [],
    'lima bean'                                          : [],
    'lime'                                               : ['lime', 'citrus', 'fruity'],
    'lingonberry'                                        : ['berry', 'redberry', 'fruity'],
    'liquor'                                             : [],
    'loquat'                                             : ['stone fruit', 'fruity'],
    'lovage'                                             : ['herbal'],
    'lowbush blueberry'                                  : ['blueberry', 'fruity', 'berry'],
    'lumpsucker'                                         : [],
    'macadamia nut'                                      : [],
    'macaroni and cheese'                                : [],
    'madeira wine'                                       : ['wine'],
    'malus (crab apple)'                                 : ['apple', 'fruity'],
    'mamey sapote'                                       : ['tropical', 'fruity'],
    'mandarin orange (clementine, tangerine)'            : ['mandarin', 'tangerine', 'citrus', 'fruity'],
    'mango'                                              : ['mango', 'tropical', 'fruity'],
    'margarine'                                          : [],
    'margarine-like spread'                              : [],
    'marine mussel'                                      : [],
    'marzipan'                                           : [],
    'meat bouillon'                                      : [],
    'meatloaf'                                           : [],
    'milk (cow)'                                         : [],
    'milk (human)'                                       : [],
    'milk (other mammals)'                               : [],
    'milk substitute'                                    : [],
    'milkshake'                                          : [],
    'millet'                                             : [],
    'mixed nuts'                                         : [],
    'morchella (morel)'                                  : ['earthy'],
    'moth bean'                                          : [],
    'mountain hare'                                      : [],
    'mountain yam'                                       : [],
    'mung bean'                                          : [],
    'muskmelon'                                          : ['melon', 'honeydew', 'fruity'],
    'mustard'                                            : [],
    'nachos'                                             : [],
    'new zealand spinach'                                : [],
    'northern pike'                                      : [],
    'norway lobster'                                     : [],
    'nutmeg'                                             : ['nutmeg', 'spicy'],
    'nutritional drink'                                  : [],
    'oat'                                                : [],
    'oat bread'                                          : [],
    'ocean pout'                                         : [],
    'oil palm'                                           : [],
    'oil-seed camellia'                                  : [],
    'okra'                                               : [],
    'olive'                                              : [],
    'opium poppy'                                        : [],
    'orange bell pepper'                                 : [],
    'orange mint'                                        : ['mint', 'orange', 'citrus'],
    'other alcoholic beverage'                           : [],
    'other animal fat'                                   : [],
    'other beverage'                                     : [],
    'other bread'                                        : [],
    'other bread product'                                : [],
    'other candy'                                        : ['candy'],
    'other dish'                                         : [],
    'other fermented milk'                               : [],
    'other fish product'                                 : [],
    'other frozen dessert'                               : [],
    'other fruit product'                                : ['fruity'],
    'other pasta dish'                                   : [],
    'other sandwich'                                     : [],
    'other snack food'                                   : [],
    'other vegetable product'                            : [],
    'oyster mushroom'                                    : [],
    'pacific cod'                                        : [],
    'pacific jack mackerel'                              : [],
    'pacific ocean perch'                                : [],
    'pacific rockfish'                                   : [],
    'painted comber'                                     : [],
    'pak choy'                                           : [],
    'pan dulce'                                          : [],
    'pancake'                                            : [],
    'papaya'                                             : ['papaya', 'tropical', 'fruity'],
    'parsley'                                            : ['herbal'],
    'parsnip'                                            : [],
    'passion fruit'                                      : ['passion fruit', 'tropical', 'fruity'],
    'pasta'                                              : [],
    'pastry'                                             : [],
    'pate'                                               : [],
    'peach'                                              : ['peach', 'stone fruit', 'fruity'],
    'peanut'                                             : [],
    'pear'                                               : ['pear', 'fruity'],
    'pecan nut'                                          : [],
    'pectin'                                             : [],
    'pepper'                                             : ['pepper', 'spicy'],
    'pepper (c. frutescens)'                             : ['spicy'],
    'pepper (spice)'                                     : ['pepper', 'spicy'],
    'peppermint'                                         : ['mint', 'menthol', 'herbal'],
    'perciformes'                                        : [],
    'pie'                                                : [],
    'pie crust'                                          : [],
    'pigeon pea'                                         : [],
    'piki bread'                                         : [],
    'pine nut'                                           : [],
    'pineapple'                                          : ['pineapple', 'tropical', 'fruity'],
    'pink salmon'                                        : [],
    'pistachio'                                          : [],
    'pita bread'                                         : [],
    'pizza'                                              : [],
    'pleuronectidae (dab, halibut, plaice)'              : [],
    'pomegranate'                                        : ['dark fruit', 'fruity'],
    'popcorn'                                            : [],
    'poppy'                                              : [],
    'port wine'                                          : ['wine', 'dried fruit', 'fruity'],
    'pot marjoram'                                       : ['herbal'],
    'pot pie'                                            : [],
    'potato'                                             : [],
    'potato chip'                                        : [],
    'potato gratin'                                      : [],
    'processed cheese'                                   : [],
    'prunus (cherry, plum)'                              : ['cherry', 'plum', 'fruity'],
    'pudding'                                            : [],
    'pupusa'                                             : [],
    'purslane'                                           : [],
    'quail'                                              : [],
    'quesadilla'                                         : [],
    'quince'                                             : ['fruity', 'floral'],
    'rabbit'                                             : [],
    'radish'                                             : [],
    'rainbow smelt'                                      : [],
    'rainbow trout'                                      : [],
    'rape'                                               : [],
    'ravioli'                                            : [],
    'red beetroot'                                       : ['earthy'],
    'red bell pepper'                                    : [],
    'red king crab'                                      : [],
    'red tea'                                            : ['tea'],
    'red wine'                                           : ['wine'],
    'redcurrant'                                         : ['redcurrant', 'fruity', 'berry'],
    'relish'                                             : [],
    'remoulade'                                          : [],
    'rice'                                               : [],
    'rice bread'                                         : [],
    'robusta coffee'                                     : [],
    'rocket salad (ssp.)'                                : ['herbal'],
    'romaine lettuce'                                    : [],
    'rosemary'                                           : ['herbal', 'woody'],
    'rubus (blackberry, raspberry)'                      : ['blackberry', 'raspberry', 'fruity', 'berry'],
    'rum'                                                : ['molasses', 'dried fruit', 'fruity'],
    'rye'                                                : [],
    'rye bread'                                          : [],
    'sablefish'                                          : [],
    'sacred lotus'                                       : [],
    'safflower'                                          : [],
    'sake'                                               : [],
    'salad'                                              : [],
    'salad dressing'                                     : [],
    'salmonidae (salmon, trout)'                         : [],
    'sauce'                                              : [],
    'sausage'                                            : [],
    'savoy cabbage'                                      : [],
    'scallop'                                            : [],
    'scombridae (bonito, mackerel, tuna)'                : [],
    'scrapple'                                           : [],
    'sea-buckthornberry'                                 : ['berry', 'citrus', 'fruity'],
    'semolina'                                           : [],
    'sesame'                                             : [],
    'shea tree'                                          : [],
    'sheep (mutton, lamb)'                               : [],
    'sherry'                                             : ['wine'],
    'shiitake'                                           : ['earthy'],
    'shortening'                                         : [],
    'shrimp'                                             : [],
    'smelt'                                              : [],
    'snack bar'                                          : [],
    'sockeye salmon'                                     : [],
    'soft-necked garlic'                                 : ['garlic'],
    'sorghum'                                            : [],
    'soup'                                               : [],
    'sour cherry'                                        : ['cherry', 'fruity'],
    'sour cream'                                         : [],
    'soy bean'                                           : [],
    'soy sauce'                                          : [],
    'spearmint'                                          : ['mint', 'herbal'],
    'spinach'                                            : [],
    'spirit'                                             : [],
    'spotted seal'                                       : [],
    'spread'                                             : [],
    'star anise'                                         : ['anise', 'licorice', 'spicy'],
    'stew'                                               : [],
    'strawberry'                                         : ['strawberry', 'fruity', 'berry'],
    'strawberry guava'                                   : ['guava', 'strawberry', 'fruity', 'berry'],
    'striped mullet'                                     : [],
    'stuffing'                                           : [],
    'sturgeon'                                           : [],
    'summer savory'                                      : ['herbal'],
    'sunburst squash (pattypan squash)'                  : [],
    'sunflower'                                          : [],
    'swede'                                              : [],
    'sweet basil'                                        : ['herbal'],
    'sweet bay'                                          : ['herbal'],
    'sweet custard'                                      : ['vanilla'],
    'sweet marjoram'                                     : ['herbal'],
    'sweet orange'                                       : ['orange', 'citrus', 'fruity'],
    'sweet potato'                                       : [],
    'swordfish'                                          : [],
    'syrup'                                              : [],
    'taco'                                               : [],
    'taco shell'                                         : [],
    'tallow'                                             : [],
    'tamale'                                             : [],
    'tamarind'                                           : ['dried fruit', 'fruity'],
    'taro'                                               : [],
    'tarragon'                                           : ['herbal', 'licorice'],
    'tea'                                                : ['tea'],
    'thistle'                                            : [],
    'thunnus'                                            : [],
    'topping'                                            : [],
    'tortilla'                                           : [],
    'tortilla chip'                                      : [],
    'tostada'                                            : [],
    'tostada shell'                                      : [],
    'towel gourd'                                        : [],
    'trail mix'                                          : [],
    'triticale'                                          : [],
    'turkey'                                             : [],
    'turmeric'                                           : ['spicy', 'earthy'],
    'turnip'                                             : [],
    'ucuhuba'                                            : [],
    'unclassified food or beverage'                      : [],
    'vanilla'                                            : ['vanilla', 'sweet aromatic'],
    'vegetable juice'                                    : [],
    'vegetarian food'                                    : [],
    'vermouth'                                           : ['wine', 'herbal'],
    'vinegar'                                            : [],
    'vodka'                                              : [],
    'waffle'                                             : [],
    'walnut'                                             : [],
    'watermelon'                                         : ['watermelon', 'melon', 'fruity'],
    'wax gourd'                                          : [],
    'wheat'                                              : [],
    'wheat bread'                                        : [],
    'whey'                                               : [],
    'whisky'                                             : ['oak'],
    'white bread'                                        : [],
    'white cabbage'                                      : [],
    'white lupine'                                       : [],
    'white mustard'                                      : [],
    'white wine'                                         : ['white wine'],
    'whitefish'                                          : [],
    'wild carrot'                                        : [],
    'wild celery'                                        : [],
    'winged bean'                                        : [],
    'winter savory'                                      : ['herbal'],
    'winter squash'                                      : [],
    'yam'                                                : [],
    'yardlong bean'                                      : [],
    'yellow bell pepper'                                 : [],
    'yellow pond-lily'                                   : [],
    'yellow wax bean'                                    : [],
    'yellow zucchini'                                    : [],
    'yellowfin tuna'                                     : [],
    'ymer'                                               : [],
    'yogurt'                                             : [],
    'zwieback'                                           : [],
}

