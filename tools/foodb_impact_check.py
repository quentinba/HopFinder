#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
foodb_impact_check.py — la lacune FooDB te gêne-t-elle LÀ OÙ ÇA COMPTE ?

Hypothèse à tester : la faible couverture globale en concentration (6-9 % par
aliment) vient d'une longue traîne de composés listés par agrégation, mais les
composés d'IMPACT (ceux qui font l'arôme) ont peut-être tous une valeur.

Ce script, pour un aliment :
  1. affiche combien de composés ont une concentration ;
  2. vérifie tes composés d'impact nommés : présents ? concentration ? valeur ;
  3. liste les composés QUI ONT une concentration (pour juger à l'œil s'ils sont
     bien les composés importants, ou du bruit).

Usage :
    python foodb_impact_check.py /Users/quentin/Downloads/foodb_2020_04_07_csv \\
        --food "sweet basil" \\
        --impact linalool,estragole,methyl-chavicol,eugenol,1,8-cineole
"""
import argparse
import glob
import os
import re
import sys
import pandas as pd

CONC = "orig_content"          # colonne concentration (cf. audit)
STD = "standard_content"


def find_csv(folder, *names):
    for name in names:
        for cand in (name, name.capitalize(), name.upper()):
            hit = glob.glob(os.path.join(folder, f"{cand}.csv"))
            if hit:
                return hit[0]
    return None


def norm(s):
    """normalise un nom de composé pour comparaison lâche."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--food", required=True, help="sous-chaîne du nom d'aliment")
    ap.add_argument("--impact", default="", help="composés d'impact, séparés par virgule")
    a = ap.parse_args()

    food_path = find_csv(a.folder, "food")
    cmp_path = find_csv(a.folder, "compound")
    content_path = find_csv(a.folder, "content")
    if not (food_path and content_path):
        print("Food.csv / Content.csv introuvables.")
        sys.exit(1)

    # 1) résoudre le food_id
    foods = pd.read_csv(food_path, usecols=lambda c: c in ("id", "name", "name_scientific"))
    match = foods[foods["name"].astype(str).str.contains(a.food, case=False, na=False)]
    if match.empty:
        print(f"Aucun aliment ne matche {a.food!r}.")
        sys.exit(1)
    fid = int(match.iloc[0]["id"])
    print(f"Aliment : {match.iloc[0]['name']} (food_id={fid})\n")

    # 2) noms des composés : Content.source_id -> Compound.name (+ fallback orig_source_name)
    cmp_names = {}
    if cmp_path:
        cdf = pd.read_csv(cmp_path, usecols=lambda c: c in ("id", "name"))
        cmp_names = dict(zip(cdf["id"], cdf["name"]))

    # 3) lire les lignes Content de cet aliment (chunked, filtrées)
    usecols = ["source_id", "source_type", "food_id", CONC, STD,
               "orig_unit", "orig_source_name"]
    rows = []
    for chunk in pd.read_csv(content_path, usecols=lambda c: c in usecols,
                             chunksize=300_000, low_memory=False):
        sub = chunk[(chunk["food_id"] == fid) &
                    (chunk["source_type"].astype(str).str.lower() == "compound")]
        if len(sub):
            rows.append(sub)
    if not rows:
        print("Aucun composé pour cet aliment.")
        sys.exit(0)
    df = pd.concat(rows, ignore_index=True)
    df["cname"] = df["source_id"].map(cmp_names).fillna(df.get("orig_source_name"))
    df["has_conc"] = df[CONC].notna() | df[STD].notna()

    n = len(df)
    nc = int(df["has_conc"].sum())
    print(f"Composés listés : {n} | avec concentration : {nc} ({100*nc/max(n,1):.0f}%)\n")

    # 4) tes composés d'impact
    impacts = [x.strip() for x in a.impact.split(",") if x.strip()]
    if impacts:
        print("=== COMPOSÉS D'IMPACT ===")
        namecol = df["cname"].astype(str).map(norm)
        for imp in impacts:
            key = norm(imp)
            hit = df[namecol.str.contains(re.escape(key), na=False)] if key else df.iloc[0:0]
            if hit.empty:
                print(f"  {imp:<20} ABSENT de la liste FooDB de cet aliment")
                continue
            # meilleure ligne = celle qui a une concentration si possible
            best = hit.sort_values("has_conc", ascending=False).iloc[0]
            if best["has_conc"]:
                val = best[CONC] if pd.notna(best[CONC]) else best[STD]
                unit = best.get("orig_unit", "")
                print(f"  {imp:<20} présent, CONCENTRATION = {val} {unit}")
            else:
                print(f"  {imp:<20} présent mais SANS concentration (présence seule)")
        print()

    # 5) que sont les composés qui ONT une concentration ? (juger le signal/bruit)
    withc = df[df["has_conc"]].copy()
    print(f"=== TOP composés AVEC concentration (max {min(25, len(withc))}) ===")
    withc = withc.sort_values(CONC, ascending=False, na_position="last")
    for _, r in withc.head(25).iterrows():
        print(f"  {str(r['cname'])[:34]:<34} {r[CONC]} {r.get('orig_unit','')}")
    print("\nLecture : si tes composés d'impact ont une concentration et que la liste")
    print("ci-dessus contient les molécules 'qui comptent', la lacune globale ne te")
    print("gêne pas — tu peux t'appuyer sur la concentration là où c'est utile.")


if __name__ == "__main__":
    main()
