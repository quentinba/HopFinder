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
PROCESS_SURVIVAL: dict[str, dict[str, str]] = {
    "myrcene":       {"class": "Hydrocarbons", "subclass": "Monoterpenes",
                      "annotation": "dry hop / late additions", "confidence": "high"},
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
    "linalool":      {"class": "Oxygenated", "subclass": "Monoterpene alcohols",
                      "annotation": "survives boiling", "confidence": "high"},
    "geraniol":      {"class": "Oxygenated", "subclass": "Monoterpene alcohols",
                      "annotation": "survives boiling", "confidence": "high"},
    "ketones":       {"class": "Oxygenated",
                      "subclass": "Other (ketones, esters, aldehydes, epoxides)",
                      "annotation": "intermediate transfer", "confidence": "low"},
    "isobutyrate":   {"class": "Oxygenated",
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
        "Volatile, non-polar hydrocarbons — mostly stripped away by evaporation during a "
        "boil. Only additions with little or no boil exposure (dry hop, whirlpool, "
        "flame-out) keep them close to the measured amount.",
    "direct traces, contributes via oxidation":
        "Heavier than the monoterpene hydrocarbons above, so a small amount can persist "
        "as a direct trace of the same molecule. For humulene and caryophyllene "
        "specifically, a Saaz extraction-timing study found that producing the "
        "spicy-noted oxidized compounds (e.g. humulene → humulenol) requires a LONG boil "
        "(over ~20 minutes) — not dry hop or late additions. Farnesene and selinene share "
        "this class-level annotation (sesquiterpene hydrocarbons that can oxidize into "
        "different, oxygenated compounds, e.g. farnesene → farnesol) but the boil-time "
        "specifics above are not established for them in this source.",
    "survives boiling":
        "Already oxygenated (an -OH group makes these far less volatile and more "
        "water-soluble than any hydrocarbon above) — a meaningful share persists as the "
        "same molecule through a boil, not just in late/dry-hop additions.",
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
