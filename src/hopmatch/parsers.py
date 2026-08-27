"""
Parseurs label/valeur pour les fiches houblon (BarthHaas, Yakima Chief).

Les deux sources exposent leurs analyses sous forme « label ligne N, valeur ligne
N+1 » une fois le DOM aplati en texte. On factorise le parseur ; seules les tables
de labels et quelques quirks diffèrent.

  BarthHaas → thiols (µg/kg), cétones, isobutyrate
  Yakima    → β-pinène, sélinène
"""
from __future__ import annotations
import re

# label normalisé -> (compound, unit)
BARTHHAAS_LABELS = {
    "MYRCENE": ("myrcene", "pct_oil"), "HUMULENE": ("humulene", "pct_oil"),
    "CARYOPHYLLENE": ("caryophyllene", "pct_oil"),
    "FARNESEN": ("farnesene", "pct_oil"), "FARNESENE": ("farnesene", "pct_oil"),
    "LINALOOL": ("linalool", "pct_oil"), "GERANIOL": ("geraniol", "pct_oil"),
    "KETONE": ("ketones", "pct_oil"), "ISOBUTYRATE": ("isobutyrate", "pct_oil"),
    "THIOLS": ("thiols", "ug_kg"), "TOTAL OIL": ("total_oil", "ml_100g"),
    "ALPHA-ACIDS": ("alpha_acid", "pct"), "BETA-ACIDS": ("beta_acid", "pct"),
}
YAKIMA_LABELS = {
    "B-PINENE": ("beta-pinene", "pct_oil"), "MYRCENE": ("myrcene", "pct_oil"),
    "LINALOOL": ("linalool", "pct_oil"), "CARYOPHYLLENE": ("caryophyllene", "pct_oil"),
    "FARNESENE": ("farnesene", "pct_oil"), "HUMULENE": ("humulene", "pct_oil"),
    "GERANIOL": ("geraniol", "pct_oil"),
    "SILINENE": ("selinene", "pct_oil"), "SELINENE": ("selinene", "pct_oil"),
    "TOTAL OIL": ("total_oil", "ml_100g"),
    "ALPHA ACIDS": ("alpha_acid", "pct"), "BETA ACIDS": ("beta_acid", "pct"),
}

LABELS_BY_SOURCE = {"barthhaas": BARTHHAAS_LABELS, "yakima": YAKIMA_LABELS}

# clé de champ JSON (API Algolia YCH, brewing_values[i]) -> (compound, unit).
# Distinct de YAKIMA_LABELS (texte des fixtures) : la source API a ses propres
# clés (ex. 'b_pinene', 'silinene') déjà structurées en {low, ave, high}.
YAKIMA_API_FIELDS = {
    "b_pinene": ("beta-pinene", "pct_oil"), "myrcene": ("myrcene", "pct_oil"),
    "linalool": ("linalool", "pct_oil"), "caryophyllene": ("caryophyllene", "pct_oil"),
    "farnesene": ("farnesene", "pct_oil"), "humulene": ("humulene", "pct_oil"),
    "geraniol": ("geraniol", "pct_oil"), "silinene": ("selinene", "pct_oil"),
    "oil": ("total_oil", "ml_100g"), "alpha": ("alpha_acid", "pct"), "beta": ("beta_acid", "pct"),
    # co-humulone (% des acides alpha, convention brassicole standard) --
    # demande utilisateur (2026-08-19). Yakima UNIQUEMENT : champ `co_h` vu en
    # direct sur l'API Algolia réelle (ex. Citra : 20-24%, cohérent avec les
    # valeurs publiques connues), absent du HTML BarthHaas (vérifié en direct,
    # aucune ligne "CO-HUMULONE" sur leurs fiches).
    "co_h": ("co_humulone", "pct"),
}


def parse_range(s: str) -> tuple[float | None, float | None]:
    """'50 - 70%' -> (50, 70) ; 'up to 2.8 ml/100 g' -> (0, 2.8) ; '1.0 - 3.0' -> (1, 3)."""
    clean = re.sub(r"ml\s*/\s*100\s*g", "", s, flags=re.I)
    clean = re.sub(r"µg\s*/\s*kg", "", clean, flags=re.I)
    nums = re.findall(r"\d+\.?\d*", clean.replace(",", "."))
    if not nums:
        return (None, None)
    vals = [float(n) for n in nums]
    if len(vals) == 1:
        return (0.0, vals[0]) if "up to" in s.lower() else (vals[0], vals[0])
    return (vals[0], vals[1])


def _norm(line: str, label_map: dict) -> str | None:
    up = line.strip().upper().rstrip("*")
    up = re.sub(r"\(.*?\)", "", up)
    up = re.sub(r"ML\s*/\s*100\s*G", "", up)
    up = re.sub(r"µG\s*/\s*KG", "", up, flags=re.I)
    up = up.replace("%", "").strip()
    return up if up in label_map else None


def parse_composition(text: str, label_map: dict) -> dict[str, tuple]:
    """Renvoie {compound: (vmin, vmax, unit)}."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out = {}
    for i, line in enumerate(lines[:-1]):
        key = _norm(line, label_map)
        if key is None:
            continue
        compound, unit = label_map[key]
        vmin, vmax = parse_range(lines[i + 1])
        if vmax is not None:
            out[compound] = (vmin, vmax, unit)
    return out


_BARE_YEAR_RE = re.compile(r"^\d{4}$")


def parse_descriptors(text: str) -> list[str]:
    """
    Extrait la roue d'arôme : la ligne suivant 'AROMA PROFILE'.

    Sur le site BarthHaas réel (vérifié en direct sur plusieurs variétés,
    ex. 'admiral', 'tango'), 1 ou 2 lignes de bruit s'intercalent parfois avant
    le vrai contenu — un sous-titre 'Typical Aroma Profile' et/ou une année
    brute ('2023', millésime de récolte) — on les saute. Le contenu réel qui
    suit n'est PLUS une liste courte séparée par virgules comme dans les
    fixtures historiques, mais un paragraphe descriptif complet (ex. « The
    flavour profile of Admiral... contribute to the overall impression. »).
    Miner ce texte libre pour en extraire de faux descripteurs serait de la
    précision-déchet (CLAUDE.md) ; un paragraphe se repère par un point final,
    absent d'une vraie liste de descripteurs courts — dans ce cas, aucun
    descripteur n'est retourné plutôt qu'un mot inventé.

    **Ne retourne donc quasi jamais rien sur le site réel actuel (T79,
    2026-08-22, confirmé en direct sur les 97 variétés du catalogue) --
    mais ça ne veut PAS dire que BarthHaas n'a pas de descripteurs
    utilisables.** Il en a, ailleurs sur la même page : voir
    `parse_barthhaas_tastes` (liste `<li>` structurée en tête de page,
    ex. "Lemon", "Cranberry" -- jamais du texte libre miné, un vrai
    descripteur par élément) et `parse_barthhaas_aroma_wheel` (roue
    quantitative embarquée en attributs `data-*`). Cette fonction-ci
    (paragraphe "AROMA PROFILE") reste inutile sur le site actuel, gardée
    telle quelle par honnêteté sur ce qu'elle fait vraiment.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, l in enumerate(lines[:-1]):
        if l.upper().startswith("AROMA PROFILE"):
            j = i + 1
            while j < len(lines) and (
                    "AROMA PROFILE" in lines[j].upper() or _BARE_YEAR_RE.match(lines[j])):
                j += 1
            if j >= len(lines) or "." in lines[j]:
                return []
            return [d.strip().lower() for d in re.split(r"[,;]", lines[j]) if d.strip()]
    return []


def parse_barthhaas_tastes(html: str) -> list[tuple[str, str]]:
    """Extrait la liste `<ul class="section-card-text__tastes">` en tête de
    chaque page BarthHaas (T79, 2026-08-22, demande utilisateur explicite,
    après capture d'écran montrant "Lemon, Cranberry, Cream, Pepper, Mate
    Tea" sur la page Admiral -- jamais trouvée avant car hors du texte
    "AROMA PROFILE" que `parse_descriptors` regarde). Vérifié en direct sur
    les 97 variétés du catalogue (2026-08-22) : présente à 100%, toujours
    3 à 5 éléments `<li>`, JAMAIS du texte libre à miner -- un vrai mot
    descripteur par élément, structurellement fiable (contrairement au
    paragraphe "AROMA PROFILE").

    Chaque `<li>` porte une classe CSS allemande qui identifie SANS
    AMBIGUÏTÉ l'une des 12 catégories de la roue BarthHaas (vérifié sur les
    97 variétés : exactement 12 classes distinctes, correspondance 1:1
    avec les 12 libellés `data-rose-labels`, voir `parse_barthhaas_aroma_
    wheel`) -- ex. "zitrus"->citrus, "sahnekaramell"->cream caramel,
    "grun"->grassy-hay. Renvoyée TELLE QUELLE (classe brute, mot en
    minuscule) : cette fonction reste une extraction FIDÈLE à la source,
    jamais une décision de mapping vers le vocabulaire `hop_descriptors`
    existant (alias/nouveaux termes) -- cette décision (revue par
    l'utilisateur) vit ailleurs (reference.py/ingest.py), pas ici.

    Renvoie [] si la page n'a pas cette liste (jamais vu sur les 97
    variétés réelles, mais une page pourrait changer de structure)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    ul = soup.find("ul", class_="section-card-text__tastes")
    if not ul:
        return []
    out = []
    for li in ul.find_all("li"):
        classes = li.get("class") or []
        cls = classes[0] if classes else ""
        text = li.get_text(strip=True).lower()
        if text:
            out.append((cls, text))
    return out


def parse_barthhaas_aroma_wheel(html: str) -> dict[str, float] | None:
    """Extrait la roue d'arôme QUANTITATIVE BarthHaas ("rose chart") : 12
    catégories fixes (`data-rose-labels`, IDENTIQUE mot pour mot sur les 97
    variétés vérifiées, 2026-08-22) + une valeur numérique par catégorie
    (`data-values` sur un `<canvas>`) -- rendue en `<canvas>` côté client
    (Chart.js ou similaire) mais les valeurs sont DÉJÀ dans le HTML statique
    servi par le serveur, aucune exécution JS nécessaire pour les lire.

    Échelle 0-8 environ (vérifiée sur les 97 variétés : min 0.0, max 8.0,
    moyenne ~3.1) -- DIFFÉRENTE de l'échelle 0-100 de Yakima
    (`hop_aroma_intensity`, moyenne ~39). Ne JAMAIS mélanger les deux
    échelles sans normalisation explicite (voir la discussion utilisateur
    sur le risque d'une moyenne brute des deux sources -- non retenue).

    Renvoie le PREMIER jeu de valeurs rencontré dans le HTML (repéré en
    direct : c'est celui du petit graphique "hero" en tête de page, dont
    les valeurs sont TOUJOURS identiques à celles du bloc "Typical Aroma
    Profile" plus bas sur la page -- vérifié sur plusieurs variétés).
    N'extrait PAS les variantes par millésime (ex. "Aroma Profile 2024"/
    "2023", présentes sur 20/97 variétés vérifiées) -- une variété réelle
    de donnée historique intéressante, mais hors du périmètre de cette
    première passe (portée volontairement limitée, étape par étape --
    voir CLAUDE.md pour la discussion complète).

    Renvoie None si la page n'a pas cette donnée (jamais vu sur les 97
    variétés réelles, mais une page pourrait changer de structure), ou si
    labels/values ne correspondent pas en nombre (jamais observé, mais pas
    de zip silencieux sur des listes de tailles différentes)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    labels_el = soup.find(attrs={"data-rose-labels": True})
    if not labels_el:
        return None
    labels = [l.strip() for l in labels_el["data-rose-labels"].split(",")]
    canvas = soup.find("canvas", attrs={"data-values": True})
    if not canvas:
        return None
    values = [float(v) for v in canvas["data-values"].split(",")]
    if len(labels) != len(values):
        return None
    return dict(zip(labels, values))


def parse_flavornet(html: str) -> list[tuple[str, str, list[str]]]:
    """
    Parse la table Flavornet triée par indice de Kovats (d_kovats_ov101.html) :
    une ligne par composé odeur-actif, avec CAS (dans le lien vers sa fiche),
    nom et descripteurs séparés par virgule. Renvoie [(cas, compound, descriptors)].
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        link = tr.find("td", class_="ch")
        sm = tr.find("td", class_="sm")
        if link is None or sm is None:
            continue
        a = link.find("a", href=True)
        if a is None:
            continue
        m = re.search(r"info/([^/]+)\.html", a["href"])
        if not m:
            continue
        cas = m.group(1)
        compound = a.get_text(strip=True).lower()
        descriptors = [d.strip() for d in sm.get_text(strip=True).split(",") if d.strip()]
        out.append((cas, compound, descriptors))
    return out


def mass_mg_per_100g(value: float | None, unit: str | None) -> float | None:
    """
    Convertit une concentration FooDB (Content.orig_content/orig_unit) en mg/100g
    UNIQUEMENT si l'unité est une masse/masse comparable (mg/100g, mg/kg...).
    Renvoie None pour les unités non comparables (IU, ppb, µM, kcal, RE, NE, α-TE...)
    plutôt que de les traiter comme des mg — 'standard_content' de FooDB prétend
    normaliser mais recopie en fait ces unités telles quelles (vérifié sur le dump).
    """
    if value is None or unit is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    u = str(unit).strip().lower()
    if re.match(r"^mg\s*/\s*100\s*g", u):
        return value
    if re.match(r"^mg\s*/\s*kg", u):
        return value * 0.1
    return None


def parse_region(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, l in enumerate(lines[:-1]):
        if l.upper().startswith("CULTIVATION AREA"):
            return lines[i + 1]
    for i, l in enumerate(lines[:-1]):
        if "BREWING VALUES" in l.upper() and not any(c.isdigit() for c in lines[i + 1]):
            return lines[i + 1]
    return ""


_THRESHOLD_UNIT_RE = re.compile(r"(ppb|ppt|ppm)\b", re.I)
_THRESHOLD_UNIT_TO_PPB = {"ppb": 1.0, "ppt": 0.001, "ppm": 1000.0}


def parse_flavordb2_threshold(text: str) -> float | None:
    """
    Texte libre FlavorDB2 (« 4 to 10 ppb », « Detection at 64 to 90 ppb », mais
    aussi des pièges type « Aroma characteristics at 10%; terpy, herbaceous... »
    pour le myrcène — une composition, pas un seuil). On ne fait confiance qu'à
    un nombre directement associé à une unité RECONNUE (ppb/ppm/ppt) : jamais un
    pourcentage, jamais un nombre sans unité. Prend la première plage/valeur
    trouvée dans le texte (milieu si plage), convertie en ppb. Renvoie None si
    aucune unité reconnue n'apparaît — mieux vaut aucun seuil qu'un seuil deviné.
    """
    m = _THRESHOLD_UNIT_RE.search(text)
    if not m:
        return None
    prefix = text[:m.start()]
    nums = re.findall(r"\d+\.?\d*", prefix.split(";")[-1])
    if not nums:
        return None
    vals = [float(n) for n in nums[-2:]]
    mid = sum(vals) / len(vals)
    return mid * _THRESHOLD_UNIT_TO_PPB[m.group(1).lower()]


def parse_flavordb2_search(html: str) -> list[tuple[str, int]]:
    """Résultats de /flavordb2/molecules?common_name=... -> [(nom, pubchem_cid)]."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out = []
    table = soup.find("table", id="molecules")
    if table is None:
        return out
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        name = tds[0].get_text(strip=True)
        a = tds[1].find("a")
        cid_text = a.get_text(strip=True) if a else ""
        if name and cid_text.isdigit():
            out.append((name, int(cid_text)))
    return out


def parse_flavordb2_detail(html: str) -> tuple[list[str], float | None]:
    """Fiche /flavordb2/molecules_details?id=... -> (liste CAS, seuil ppb | None)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    cas_list: list[str] = []
    for th in soup.find_all("th"):
        if th.get_text(strip=True) == "CAS:":
            td = th.find_next_sibling("td")
            if td:
                cas_list = [c.strip() for c in td.get_text(strip=True).split(",") if c.strip()]
            break
    threshold = None
    for strong in soup.find_all("strong"):
        if strong.get_text(strip=True) == "Aroma threshold values:":
            li = strong.find_parent("li")
            if li:
                text = li.get_text(" ", strip=True).replace("Aroma threshold values:", "", 1).strip()
                threshold = parse_flavordb2_threshold(text)
            break
    return cas_list, threshold


_MAX_PLAUSIBLE_ALPHA_ACID = 30.0  # aucune variété commerciale connue ne dépasse ~24-25%

# Priorité de forme produit dans brewing_values[].code, vérifiée en direct sur
# l'index Algolia YCH (152 variétés réelles) :
#   - PEL02 (Type 90 Hop Pellets) : présent sur 148/152 variétés — LA forme
#     commerciale standard utilisée en brasserie, celle qu'on veut par défaut.
#   - CON02/CON04 (Leaf Hops, Baled / Whole Leaf, Packed) : quasi toujours
#     identiques à PEL02 (myrcène/alpha/huile égaux sur tous les cas vérifiés
#     sauf 9/148, où ça diffère réellement) — repli raisonnable si PEL02 manque.
#   - ARO01 ('HopAroma') : présent sur SEULEMENT 1/152 variétés (Admiral) — et
#     c'est précisément l'entrée trouvée corrompue (voir _is_plausible_brewing_entry).
#     Repli de dernier rang parmi les codes "de confiance", pas le choix par défaut.
# Explicitement PAS dans cette liste (donc jamais choisis sauf si c'est
# vraiment tout ce qui existe pour une variété) : PEL06 (Cryo Hops®, lupuline
# concentrée), PEL07 (American Noble Hops®), EXT01 (extrait CO2), ARO17/19/24/25
# (produits "Boost"/huile pure d'essai) — des produits dérivés à composition
# fondamentally différente (alpha jusqu'à 64%, huile jusqu'à 99%+ pour un
# extrait pur), pas "le même houblon dans un autre emballage".
_BREWING_VALUE_PRIORITY = ["PEL02", "CON02", "CON04", "ARO01"]


def _is_plausible_brewing_entry(b: dict) -> bool:
    """
    Écarte une entrée `brewing_values` dont l'acide alpha est chimiquement
    impossible — vérifié en direct sur Admiral (YCH, index Algolia) : l'entrée
    ARO01 ('HopAroma') annonce alpha 54-62%, tandis que les trois entrées
    produit (CON02/CON04/PEL02, mutuellement cohérentes à 13-16%) s'accordent
    avec BarthHaas (indépendant, 1,0-1,7 ml/100g d'huile — contre 5-9 pour
    ARO01). Erreur de saisie sur le site YCH lui-même pour cette variété, pas
    un bug de notre côté ; sans ce garde-fou, `amount()` multiplie CHAQUE
    composé par un total_oil gonflé (ARO01 : 5-9 contre ~1-2 ailleurs), faisant
    remonter la variété en tête de presque tous les classements moléculaires.
    """
    alpha = (b.get("alpha") or {}).get("high")
    return alpha is None or alpha <= _MAX_PLAUSIBLE_ALPHA_ACID


def _select_brewing_entry(brewing: list[dict]) -> dict:
    """Choisit l'entrée `brewing_values` selon `_BREWING_VALUE_PRIORITY`
    (première présente ET plausible), puis à défaut la première entrée
    plausible qui reste (y compris un produit dérivé, en dernier recours),
    puis la toute première quand même (mieux vaut une variété suspecte que
    silencieusement absente)."""
    if not brewing:
        return {}
    by_code = {b.get("code"): b for b in brewing}
    for code in _BREWING_VALUE_PRIORITY:
        b = by_code.get(code)
        if b and _is_plausible_brewing_entry(b):
            return b
    return next((b for b in brewing if _is_plausible_brewing_entry(b)), brewing[0])


def _select_sensory_items(imp: dict, bv_code: str | None) -> list[dict]:
    """Choisit la liste d'items `{aroma, aroma_intensity}` correspondant à LA
    MÊME forme produit que la composition retenue (`bv_code`, ex. "PEL02") —
    cohérence entre composition et intensité d'arôme, même logique que
    `_select_brewing_entry`. `imported_fields.sensory_values` est une liste de
    {code, sensory_value_items}, un sous-ensemble des codes `brewing_values`
    (vérifié en direct sur Mosaic : CON04/PEL02/PEL06 seulement, sur les 10
    formes de brewing_values). Repli sur `imported_fields.aroma_values`
    (niveau variété, sans code produit associé — vérifié identique à l'entrée
    PEL02 de sensory_values sur les échantillons observés, mais pas garanti
    partout) si aucune entrée sensory_values ne correspond au code choisi."""
    for entry in imp.get("sensory_values") or []:
        if entry.get("code") == bv_code:
            return entry.get("sensory_value_items") or []
    return imp.get("aroma_values") or []


_TRADEMARK_SYMBOL_RE = re.compile(r"[®™©]")


def strip_trademark_symbols(name: str | None) -> str | None:
    """Retire ®/™/© du nom affiché (T59, demande utilisateur explicite,
    2026-08-19 : "I see some ® or ™ in the name of some results of hop.
    Could you remove this... to avoid having them and allow proper merging
    of multiple sources?"). Appliqué à la SOURCE (ici + `crawl_barthhaas`),
    pas seulement à l'affichage GUI -- même principe que
    `_strip_yakima_brand_suffix` (T51) : une seule correction en amont plutôt
    qu'un correctif répété partout où un nom est affiché. `_normalize_hop_key`
    (réconciliation BeerMaverick) retirait déjà ces symboles pour la clé de
    MATCHING interne, mais `hops.name` lui-même (et la comparaison brute de
    `ingest._find_variety_by_name_region`, T53) les gardait -- un houblon dont
    le symbole différerait entre BarthHaas et Yakima (présent d'un côté,
    absent ou différent de l'autre) pouvait donc échapper à la fusion
    cross-source. Simple suppression des 3 caractères, espaces multiples
    résultants recollapsés (même post-traitement que `_strip_yakima_brand_
    suffix`) -- ni "Brand"/"NZ Hops"/qualificatifs réels ne sont touchés,
    seuls les 3 symboles eux-mêmes."""
    if not name:
        return name
    cleaned = _TRADEMARK_SYMBOL_RE.sub("", name)
    return re.sub(r"\s+", " ", cleaned).strip()


_YAKIMA_BRAND_SUFFIX_RE = re.compile(r"\(Brand\)|Brand", re.I)


def _strip_yakima_brand_suffix(display_name: str | None) -> str | None:
    """Retire le mot "Brand" (ou "(Brand)") du `display_name` Yakima — un
    artefact de LEUR convention d'affichage marketing (variétés déposées),
    PAS une partie du nom réel du houblon : signalé par l'utilisateur (2026-
    08-19), "Mosaic® Brand" côté Yakima quand BarthHaas affiche juste
    "Mosaic®" pour la même variété (vérifié en direct sur leur page réelle,
    <h1>, aucun "Brand"). Confirmé sur l'API Algolia réelle : 50/153
    variétés ont "Brand" dans `display_name`, toujours comme un mot à part
    (jamais une sous-chaîne d'un autre mot), sous 3 formes vues en direct :
    "X® Brand", "X™ (Brand)" (Galaxy, un seul cas), et "X® Brand - NZ Hops"/
    "X™ Brand - MacHops" (variantes régionales, où "- NZ Hops"/"- MacHops"
    est un vrai qualificatif à GARDER, seul "Brand" est retiré) ; un cas a
    aussi un qualificatif avant "Brand" ("Nectaron® Organic Brand - NZ
    Hops" -> "Organic" gardé). Ne retire QUE le mot "Brand" lui-même, jamais
    ce qui l'entoure -- espaces multiples résultants recollapsés."""
    if not display_name:
        return display_name
    cleaned = _YAKIMA_BRAND_SUFFIX_RE.sub("", display_name)
    return re.sub(r"\s+", " ", cleaned).strip()


_BARE_HOPS_SUFFIX_RE = re.compile(r"\s+Hops$")


def strip_bare_hops_suffix(name: str | None) -> str | None:
    """Retire un suffixe « Hops » NU (précédé d'une simple espace) du nom
    affiché — T123 (2026-08-27), trouvé en listant des exemples
    d'isobutyrate : 7 fiches BarthHaas ("Luna Hops", "Dolcita Hops"...)
    portent « Hops » comme habillage marketing de leur page, jamais une
    partie du nom de variété.

    Garde stricte, sur le modèle de `_strip_yakima_brand_suffix` : ne JAMAIS
    retirer « Hops » si le nom contient un qualificatif à tiret ("<nom> -
    <région> Hops", ex. "Kohatu - NZ Hops", 11 cas Yakima réels, fournisseur
    NZ Hops Ltd explicitement conservé par T51) -- détecté par la présence
    de " - " (tiret entouré d'espaces) N'IMPORTE OÙ dans le nom, jamais par
    le seul caractère précédant "Hops" (insuffisant : dans "Kohatu - NZ
    Hops", le mot juste avant "Hops" est "NZ", pas un tiret). Un tiret SANS
    espaces autour (ex. "Wai-iti - NZ Hops", cultivar réel) n'est pas cette
    séquence -- seul le vrai séparateur qualificatif déclenche la garde,
    vérifié sur les 11 cas réels. Repli explicite vers "ne rien retirer" en
    cas de doute (aucun tiret détecté mais forme non prévue) plutôt que de
    deviner."""
    if not name or not _BARE_HOPS_SUFFIX_RE.search(name):
        return name
    if " - " in name:
        return name
    cleaned = _BARE_HOPS_SUFFIX_RE.sub("", name)
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_yakima_hit(hit: dict) -> tuple[str, str, str, dict, list[str], dict[str, float]]:
    """
    Extrait (variety, name, region, comp, descriptors, aroma_intensity) d'un
    hit Algolia YCH (index contentstack--name-asc, _content_type='variety').
    Renvoie comp au même format que parse_composition ({compound: (vmin, vmax,
    unit)}).

    La composition vient de imported_fields.brewing_values, forme produit
    choisie par `_select_brewing_entry` (Type 90 Pellets en priorité — voir
    `_BREWING_VALUE_PRIORITY` — pas un produit dérivé type Cryo/CO2/extrait).

    aroma_intensity (T26 backlog, roue d'arôme quantitative) vient de
    imported_fields.sensory_values/aroma_values — {aroma: intensité 0-100},
    une donnée RÉELLE distincte de `descriptors` (qui ne garde qu'un sous-
    ensemble des arômes les plus forts, sans valeur : vérifié sur Mosaic,
    `aromas` liste 4 termes quand `aroma_values` en couvre 15). Simplement non
    exploitée jusqu'ici (contrairement à BarthHaas, dont la roue d'arôme EST
    verrouillée dans un `<canvas>` sans libellé d'axe récupérable côté HTML
    statique — voir docs/DATA_SOURCES.md — Yakima n'a jamais eu ce problème,
    la donnée était juste là dans la même réponse Algolia déjà utilisée pour
    la composition, pas besoin de parsing canvas).
    """
    imp = hit.get("imported_fields") or {}
    variety = (hit.get("url") or "").rsplit("/", 1)[-1]
    name = (strip_trademark_symbols(strip_bare_hops_suffix(_strip_yakima_brand_suffix(
        imp.get("display_name")))) or variety)
    region = imp.get("country_name") or ""
    descriptors = [d.strip().lower() for d in (imp.get("aromas") or []) if d and d.strip()]

    brewing = imp.get("brewing_values") or []
    bv = _select_brewing_entry(brewing)
    comp: dict = {}
    for field, (compound, unit) in YAKIMA_API_FIELDS.items():
        rng = bv.get(field) or {}
        lo, hi = rng.get("low"), rng.get("high")
        if lo is not None and hi is not None:
            comp[compound] = (float(lo), float(hi), unit)

    aroma_intensity = {
        item["aroma"].strip().lower(): float(item["aroma_intensity"])
        for item in _select_sensory_items(imp, bv.get("code"))
        if item.get("aroma") and item.get("aroma_intensity") is not None
    }
    return variety, name, region, comp, descriptors, aroma_intensity


_GREEK_TO_LATIN = {"α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta"}
_STEREO_PREFIX_RE = re.compile(r"^\(\s*[±rs+\-]+\s*\)[-\s]*", re.I)


def pubchem_name_fallbacks(name: str) -> list[str]:
    """
    Variantes de nom à tenter auprès de PubChem quand le nom Flavornet brut ne
    résout rien (endpoint /compound/name/.../cids/JSON). Vérifié sur les CAS
    non résolus d'un run réel : 'δ-cadinol' ne résout qu'en 'delta-cadinol'
    (PubChem n'indexe pas le symbole grec comme synonyme), '(r)-linden ether'
    seulement en 'linden ether' (le descripteur stéréochimique n'est pas un
    synonyme reconnu). Renvoie des variantes déterministes seulement — pas de
    recherche floue, qui risquerait de faire correspondre le mauvais composé
    (mieux vaut rester non résolu que deviner).
    """
    variants = [name]
    greek = "".join(_GREEK_TO_LATIN.get(c, c) for c in name)
    if greek != name:
        variants.append(greek)
    for base in (name, greek):
        stripped = _STEREO_PREFIX_RE.sub("", base).strip()
        if stripped and stripped != base:
            variants.append(stripped)
    seen: set[str] = set()
    out = []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


# --------------------------------------------------------------------------- #
# BeerMaverick (T25 backlog) — pairing/substitution, PAS une mesure de labo
# --------------------------------------------------------------------------- #
_BM_PAIRINGS_RE = re.compile(
    r"getElementById\('commonChart'\).*?labels:\s*\[(.*?)\].*?data:\s*\[(.*?)\]", re.S)
_BM_SUBSTITUTIONS_RE = re.compile(r"Hop Substitutions.*?<ul>(.*?)</ul>", re.S)
_BM_HOP_LINK_RE = re.compile(r'<a href="/hop/([a-z0-9-]+)/"[^>]*>\s*([^<]+?)\s*</a>')
_BM_PURPOSE_RE = re.compile(r"<th>Purpose:</th>\s*<td>(.*?)</td>", re.S)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")


def parse_beermaverick_purpose(html: str) -> str | None:
    """
    Extrait la ligne « Purpose: Aroma|Bittering|Dual » du tableau
    « Analyses/Basics » d'une page beermaverick.com/hop/{slug}/ — la SEULE
    source trouvée qui classe explicitement un houblon par usage (aromatique/
    amérisant/double-usage) : ni BarthHaas ni Yakima n'exposent ce champ
    (vérifié en direct sur leurs pages/API respectives, voir CLAUDE.md). Texte
    brut ("Aroma"/"Bittering"/"Dual"), normalisé à l'ingestion
    (`ingest._normalize_beermaverick_purpose`) — ce module reste un parseur
    brut sans connaissance métier, comme les autres `parse_beermaverick_*`.
    Absent sur certaines pages (page stub/faible volume, comme les
    substitutions/pairings) -> None, jamais de valeur inventée."""
    m = _BM_PURPOSE_RE.search(html)
    if not m:
        return None
    text = _STRIP_TAGS_RE.sub("", m.group(1)).strip()
    return text or None


def parse_beermaverick_pairings(html: str) -> list[tuple[str, float]]:
    """
    Extrait la section « Hop Pairings » d'une page beermaverick.com/hop/{slug}/ :
    un graphique Chart.js embarqué DIRECTEMENT dans le HTML statique servi
    (pas besoin de leur endpoint interne /api/js/?hop=<id>, documenté par eux
    comme "internal use" et donc écarté — voir docs/BACKLOG.md). Fréquence
    relative (PAS un pourcentage, PAS une mesure de labo : "nous avons analysé
    des centaines des bières les plus populaires" — un agrégat éditorial,
    affiché avec cette réserve en GUI). Section absente sur les variétés à
    faible volume de recettes (ex. Admiral, vérifié en direct) -> []."""
    m = _BM_PAIRINGS_RE.search(html)
    if not m:
        return []
    labels = [l.strip() for l in re.findall(r"'([^']*)'", m.group(1))]
    values = [float(x) for x in re.findall(r"[\d.]+", m.group(2))]
    return list(zip(labels, values))


def parse_beermaverick_substitutions(html: str) -> list[tuple[str, str]]:
    """
    Extrait la section « Hop Substitutions » (choix éditorial de brasseurs
    expérimentés, PAS une mesure) — liste `<li><a href="/hop/{slug}/">Nom</a>`
    dans le HTML statique. Renvoie (slug_beermaverick, nom_affiché) : le slug
    permet une réconciliation directe vers notre propre `variety` (voir
    ingest._resolve_hop_variety), plus fiable qu'un matching sur le nom
    affiché seul."""
    m = _BM_SUBSTITUTIONS_RE.search(html)
    if not m:
        return []
    return _BM_HOP_LINK_RE.findall(m.group(1))


_BM_TAGS_RE = re.compile(r"<b>Tags:</b>.*?</p>", re.S)
_BM_TAG_LINK_RE = re.compile(r"/hops/tag/([a-z_]+)/")


def parse_beermaverick_tags(html: str) -> list[str]:
    """
    Extrait le bloc « Tags: #pine #resin #dank... » d'une page
    beermaverick.com/hop/{slug}/ — un vocabulaire de descripteurs RÉEL et bien
    plus riche que la liste courte `aromas` de Yakima (vérifié en direct sur
    Chinook/Columbus : Yakima ne tague AUCUN des deux "dank" alors que
    BeerMaverick le fait pour les deux, correctement — voir CLAUDE.md pour le
    détail complet de cette investigation). Renvoie les slugs bruts avec
    underscore (`black_pepper`), pas encore normalisés : la conversion
    underscore->espace + résolution alias/sous-famille (`reference.
    DESCRIPTOR_ALIASES`/`CONTRAST_AFFINITY`) et le filtrage des tags non-arôme
    (`ingest._BEERMAVERICK_TAG_DROPLIST` : "mild", "clean", "hoppy"...) se font
    à l'ingestion, pas ici (ce module reste un parseur brut sans connaissance
    métier, comme `parse_descriptors`)."""
    m = _BM_TAGS_RE.search(html)
    if not m:
        return []
    return _BM_TAG_LINK_RE.findall(m.group(0))


# T81 (2026-08-27) : 3 styles provisoires (X1, X2, X4) du JSON BJCP 2021 ont
# des clés espagnoles/portugaises qui ont fuité à la place de leurs
# équivalents anglais (vérifié en direct sur les 3 styles réels). Mapping
# EXPLICITE, jamais deviné par heuristique -- une clé absente de ce dict est
# ignorée (jamais fusionnée au jugé). "comentarios" (espagnol ET portugais,
# même orthographe) couvre X1 ET X4. "marcacoes" (portugais, X4) porte en
# réalité l'équivalent de `tags` (vérifié : contenu "estilo-craft, fruta,
# ácida, cerveja-specialty", même forme que les `tags` anglais d'un autre
# style, et `tags` est bien `None` sur X4) -- pas un doublon de "comments"
# comme son orthographe pourrait le laisser penser.
# ⚠ "ejemplos_comerciales" (espagnol, X2) N'ÉTAIT PAS listée dans le ticket
# T81 (qui ne mentionne que la variante portugaise "exemplos_comerciais",
# X4) -- trouvée en vérifiant les 3 styles un par un plutôt que de recopier
# la liste du ticket telle quelle. Les deux mappent vers `examples`.
_BJCP_LEAKED_LOCALE_KEYS = {
    # Espagnol (X1, X2)
    "sabor": "flavor",
    "historia": "history",
    "ingredientes": "ingredients",
    "impresion_general": "overall_impression",
    "aspecto": "appearance",
    "sensacion_en_boca": "mouthfeel",
    "comentarios": "comments",
    "ejemplos_comerciales": "examples",
    # Portugais (X4)
    "impressao_geral": "overall_impression",
    "aparencia": "appearance",
    "sensacao_de_boca": "mouthfeel",
    "comparacoes_de_estilo": "style_comparison",
    "exemplos_comerciais": "examples",
    "marcacoes": "tags",
}

# unité attendue par champ de "vital statistics" BeerJSON -- vérifiée sur les
# 110 styles réels (2026-08-27) : jamais d'autre unité observée, mais on ne
# suppose rien à l'exécution (voir `_bjcp_vital_stat_bounds`).
_BJCP_VITAL_STAT_UNITS = {
    "original_gravity": "sg", "final_gravity": "sg",
    "alcohol_by_volume": "%", "international_bitterness_units": "IBUs",
    "color": "SRM",
}


def _bjcp_vital_stat_bounds(style: dict, field: str) -> tuple[float | None, float | None]:
    """(min, max) d'une vital stat BeerJSON (`style[field]` = {"minimum":
    {"unit","value"}, "maximum": {...}}), ou (None, None) si le style n'a pas
    cette vital stat (17/110 styles réels, spécialités héritant du style de
    base -- normal, jamais un trou de données à combler par 0). Lève une
    erreur explicite si l'unité observée diffère de `_BJCP_VITAL_STAT_UNITS`
    (ex. un jour "plato"/"ebc") plutôt que d'écrire une valeur dans la
    mauvaise unité en silence."""
    obj = style.get(field)
    if not obj:
        return None, None
    expected_unit = _BJCP_VITAL_STAT_UNITS[field]
    bounds = []
    for bound in ("minimum", "maximum"):
        b = obj.get(bound)
        if not b:
            bounds.append(None)
            continue
        unit = b.get("unit")
        if unit != expected_unit:
            raise ValueError(
                f"BJCP {style.get('style_id')!r} : unité inattendue pour "
                f"{field!r}.{bound} ({unit!r}, attendu {expected_unit!r}) -- "
                f"format BeerJSON changé ? à vérifier avant d'ingérer.")
        bounds.append(b.get("value"))
    return tuple(bounds)


def parse_beerjson_styles(payload: dict) -> list[dict]:
    """Extrait les styles d'un payload BeerJSON 2.01 (`bjcp-json`,
    `payload["beerjson"]["styles"]`) en une liste de dicts prêts à insérer
    dans `beer_styles` (sans `guideline_year`, ajouté par l'appelant selon le
    fichier téléchargé -- ce parseur ne sait pas quel millésime il lit).

    Trois pièges traités explicitement (voir BACKLOG.md T81, vérifiés en
    direct le 2026-08-27) :
    1. 17/110 styles sans AUCUNE vital stat -- `_bjcp_vital_stat_bounds`
       renvoie (None, None), jamais 0.
    2. Unité de chaque vital stat vérifiée, jamais supposée -- voir
       `_bjcp_vital_stat_bounds`.
    3. 3 styles provisoires (X1, X2, X4) aux clés espagnoles/portugaises --
       voir `_BJCP_LEAKED_LOCALE_KEYS`, résolu AVANT insertion, jamais par
       heuristique."""
    out = []
    for s in payload["beerjson"]["styles"]:
        row = {
            "style_id": s.get("style_id"), "category_id": s.get("category_id"),
            "category": s.get("category"), "name": s.get("name"), "type": s.get("type"),
            "tags": s.get("tags"),
            "overall_impression": s.get("overall_impression"), "aroma": s.get("aroma"),
            "appearance": s.get("appearance"), "flavor": s.get("flavor"),
            "mouthfeel": s.get("mouthfeel"), "comments": s.get("comments"),
            "history": s.get("history"), "ingredients": s.get("ingredients"),
            "style_comparison": s.get("style_comparison"), "examples": s.get("examples"),
            "category_description": s.get("category_description"),
            "source": "bjcp-json",
        }
        # clés localisées qui ont fuité (X1/X2/X4) : ne comblent QUE les
        # champs anglais absents, ne remplacent jamais une valeur déjà là.
        for leaked_key, target_field in _BJCP_LEAKED_LOCALE_KEYS.items():
            if row.get(target_field) is None and s.get(leaked_key) is not None:
                row[target_field] = s[leaked_key]
        og_min, og_max = _bjcp_vital_stat_bounds(s, "original_gravity")
        fg_min, fg_max = _bjcp_vital_stat_bounds(s, "final_gravity")
        abv_min, abv_max = _bjcp_vital_stat_bounds(s, "alcohol_by_volume")
        ibu_min, ibu_max = _bjcp_vital_stat_bounds(s, "international_bitterness_units")
        srm_min, srm_max = _bjcp_vital_stat_bounds(s, "color")
        row.update(og_min=og_min, og_max=og_max, fg_min=fg_min, fg_max=fg_max,
                  abv_min=abv_min, abv_max=abv_max, ibu_min=ibu_min, ibu_max=ibu_max,
                  srm_min=srm_min, srm_max=srm_max)
        out.append(row)
    return out
