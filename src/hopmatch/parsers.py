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
