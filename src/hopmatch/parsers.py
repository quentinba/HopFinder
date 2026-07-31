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
    descripteur n'est retourné plutôt qu'un mot inventé. Yakima
    (imported_fields.aromas, JSON structuré) reste la source fiable pour
    hop_descriptors sur les variétés qu'il couvre.
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


def parse_yakima_hit(hit: dict) -> tuple[str, str, str, dict, list[str]]:
    """
    Extrait (variety, name, region, comp, descriptors) d'un hit Algolia YCH
    (index contentstack--name-asc, _content_type='variety'). Renvoie comp au
    même format que parse_composition ({compound: (vmin, vmax, unit)}).

    La composition vient de imported_fields.brewing_values, forme produit
    choisie par `_select_brewing_entry` (Type 90 Pellets en priorité — voir
    `_BREWING_VALUE_PRIORITY` — pas un produit dérivé type Cryo/CO2/extrait).
    """
    imp = hit.get("imported_fields") or {}
    variety = (hit.get("url") or "").rsplit("/", 1)[-1]
    name = imp.get("display_name") or variety
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
    return variety, name, region, comp, descriptors


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
