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


def parse_descriptors(text: str) -> list[str]:
    """Extrait la roue d'arôme : la ligne suivant 'AROMA PROFILE'."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, l in enumerate(lines[:-1]):
        if l.upper().startswith("AROMA PROFILE"):
            return [d.strip().lower() for d in re.split(r"[,;]", lines[i + 1]) if d.strip()]
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


def parse_yakima_hit(hit: dict) -> tuple[str, str, str, dict, list[str]]:
    """
    Extrait (variety, name, region, comp, descriptors) d'un hit Algolia YCH
    (index contentstack--name-asc, _content_type='variety'). Renvoie comp au
    même format que parse_composition ({compound: (vmin, vmax, unit)}).

    La composition vient de imported_fields.brewing_values[code='ARO01']
    ('HopAroma', l'analyse brute de la variété) — pas d'une forme produit
    (pellets/leaf/baled), qui ne diffère qu'en présentation, pas en variété ;
    à défaut, la première entrée disponible.
    """
    imp = hit.get("imported_fields") or {}
    variety = (hit.get("url") or "").rsplit("/", 1)[-1]
    name = imp.get("display_name") or variety
    region = imp.get("country_name") or ""
    descriptors = [d.strip().lower() for d in (imp.get("aromas") or []) if d and d.strip()]

    brewing = imp.get("brewing_values") or []
    bv = next((b for b in brewing if b.get("code") == "ARO01"), brewing[0] if brewing else {})
    comp: dict = {}
    for field, (compound, unit) in YAKIMA_API_FIELDS.items():
        rng = bv.get(field) or {}
        lo, hi = rng.get("low"), rng.get("high")
        if lo is not None and hi is not None:
            comp[compound] = (float(lo), float(hi), unit)
    return variety, name, region, comp, descriptors
