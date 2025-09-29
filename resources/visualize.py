#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal visualization for lyrics coverage metrics.
Run after you generated ./resources/out/metrics.csv

python3 resources/visualize.py --csv ./resources/out/metrics.csv
"""
from __future__ import annotations
import argparse
import csv
from collections import defaultdict
import matplotlib.pyplot as plt

def read_rows(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            row["max_containment"] = float(row.get("max_containment", 0.0))
            rows.append(row)
    return rows

def plot_hist(rows):
    vals = [r["max_containment"] for r in rows]
    plt.figure()
    plt.hist(vals, bins=20)
    plt.title("Distribution of max containment")
    plt.xlabel("Containment (A∩B)/|A|")
    plt.ylabel("#outputs")
    plt.tight_layout()
    plt.show()

def plot_by(rows, key, title):
    groups = defaultdict(list)
    for r in rows:
        groups[r.get(key, "?")].append(r["max_containment"])
    xs = sorted(groups.keys())
    data = [groups[x] for x in xs]
    plt.figure()
    plt.boxplot(data, labels=xs, showfliers=False)
    plt.title(title)
    plt.ylabel("Containment")
    plt.tight_layout()
    plt.show()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="./resources/out/metrics.csv")
    args = ap.parse_args()
    rows = read_rows(args.csv)
    if not rows:
        print("No data.")
        return
    plot_hist(rows)
    plot_by(rows, "genre", "Containment by genre")
    plot_by(rows, "lang", "Containment by language")

if __name__ == "__main__":
    main()
