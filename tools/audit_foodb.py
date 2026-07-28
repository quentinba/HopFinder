#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_foodb.py — quantifie la lacunarité des concentrations dans un dump FooDB CSV.

À lancer sur TON dossier :
    python audit_foodb.py /Users/quentin/Downloads/foodb_2020_04_07_csv

Répond à : quelle fraction des liens aliment↔composé porte réellement une
concentration ? (vs simple présence). Défensif sur les noms de colonnes, car
le schéma FooDB varie un peu selon les versions.
"""
import os
import sys
import glob
import pandas as pd

CONC_CANDIDATES = ["orig_content", "standard_content", "orig_max", "standard_max",
                   "orig_min", "content"]


def find_csv(folder, *names):
    """Trouve un CSV par nom (insensible casse), sinon None."""
    for name in names:
        hits = glob.glob(os.path.join(folder, f"{name}.csv")) + \
               glob.glob(os.path.join(folder, f"{name.capitalize()}.csv"))
        if hits:
            return hits[0]
    return None


def main(folder):
    content_path = find_csv(folder, "content")
    if not content_path:
        print("Content.csv introuvable. Fichiers présents :")
        for f in sorted(glob.glob(os.path.join(folder, "*.csv"))):
            print("  ", os.path.basename(f))
        return

    print(f"Lecture de {os.path.basename(content_path)} ...")
    # lecture par morceaux : Content.csv peut faire plusieurs centaines de Mo
    cols = pd.read_csv(content_path, nrows=0).columns.tolist()
    print("Colonnes détectées :", cols)

    conc_col = next((c for c in CONC_CANDIDATES if c in cols), None)
    src_col = "source_type" if "source_type" in cols else None
    print(f"Colonne concentration utilisée : {conc_col!r} | source_type : {bool(src_col)}\n")

    usecols = [c for c in {conc_col, src_col, "food_id", "source_id"} if c]
    total = 0
    with_conc = 0
    compound_rows = 0
    compound_with_conc = 0
    foods = set()
    compounds = set()

    for chunk in pd.read_csv(content_path, usecols=usecols, chunksize=200_000,
                             low_memory=False):
        total += len(chunk)
        has = chunk[conc_col].notna() if conc_col else pd.Series(False, index=chunk.index)
        with_conc += int(has.sum())
        if "food_id" in chunk:
            foods.update(chunk["food_id"].dropna().unique())
        if "source_id" in chunk:
            compounds.update(chunk["source_id"].dropna().unique())
        if src_col:
            iscmp = chunk[src_col].astype(str).str.lower().eq("compound")
            compound_rows += int(iscmp.sum())
            compound_with_conc += int((iscmp & has).sum())

    print("=== RÉSULTAT ===")
    print(f"Lignes Content totales        : {total:,}")
    print(f"  avec une concentration      : {with_conc:,} ({100*with_conc/max(total,1):.1f}%)")
    if src_col:
        print(f"Lignes 'Compound' (vs Nutrient): {compound_rows:,}")
        print(f"  dont avec concentration     : {compound_with_conc:,} "
              f"({100*compound_with_conc/max(compound_rows,1):.1f}%)")
    print(f"Aliments distincts            : {len(foods):,}")
    print(f"Composés distincts (source_id): {len(compounds):,}")
    print("\nLecture : un faible % 'avec concentration' confirme que la majorité")
    print("des liens FooDB sont de la présence sans quantité — donc pas d'OAV possible.")

    # Bonus : zoom sur un aliment si Food.csv dispo
    food_path = find_csv(folder, "food")
    if food_path and "food_id" in usecols:
        try:
            fdf = pd.read_csv(food_path, usecols=lambda c: c in ("id", "name"))
            for target in ("yuzu", "basil", "lime", "mango"):
                match = fdf[fdf["name"].astype(str).str.contains(target, case=False, na=False)]
                if not match.empty:
                    fid = match.iloc[0]["id"]
                    sub = pd.read_csv(content_path, usecols=usecols)
                    s = sub[sub["food_id"] == fid]
                    n = len(s); nc = int(s[conc_col].notna().sum()) if conc_col else 0
                    print(f"  [{match.iloc[0]['name']}] {n} composés listés, "
                          f"{nc} avec concentration ({100*nc/max(n,1):.0f}%)")
        except Exception as e:  # noqa
            print("  (zoom aliment ignoré :", e, ")")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python audit_foodb.py <dossier_foodb_csv>")
        sys.exit(1)
    main(sys.argv[1])
