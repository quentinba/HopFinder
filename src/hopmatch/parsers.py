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


def parse_region(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, l in enumerate(lines[:-1]):
        if l.upper().startswith("CULTIVATION AREA"):
            return lines[i + 1]
    for i, l in enumerate(lines[:-1]):
        if "BREWING VALUES" in l.upper() and not any(c.isdigit() for c in lines[i + 1]):
            return lines[i + 1]
    return ""
