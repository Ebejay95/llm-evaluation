#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visualize judged results (metrics_judged.csv).

1) Stacked bars per model (correct/refuse/hallucinate/error)
2) Per-model song list as a colored graphic (one PNG per model):
   each song shown as a horizontal bar colored by its label.

Usage:
  python3 resources/visualize_judgement.py \
    --csv ./resources/out/metrics_judged.csv \
    --out-dir ./resources/out/vis \
    --save-stacked ./resources/out/vis/judgement_stacked.png
"""
from __future__ import annotations
import argparse
import csv
import os
from collections import Counter, defaultdict
from pathlib import Path
import matplotlib.pyplot as plt

# Color palette (hex)
COLORS = {
    "correct": "#2ecc71",      # green
    "refuse": "#f1c40f",       # yellow
    "hallucinate": "#e67e22",  # orange
    "error": "#e74c3c"         # red
}
LABELS = ["correct", "refuse", "hallucinate", "error"]

def read_rows(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows

def stacked_bar_by_model(rows, save_path: str | None = None):
    by_model = defaultdict(Counter)
    for r in rows:
        m = r.get("model", "unknown")
        label = r.get("label", "error")
        by_model[m][label] += 1

    models = sorted(by_model.keys())
    base = [0]*len(models)

    plt.figure(figsize=(max(6, 0.9*len(models)), 5))
    for lab in LABELS:
        vals = [by_model[m].get(lab, 0) for m in models]
        plt.bar(models, vals, bottom=base, label=lab, color=COLORS[lab])
        base = [base[i] + vals[i] for i in range(len(vals))]

    plt.title("Judgement per model")
    plt.xlabel("Model")
    plt.ylabel("Count")
    plt.xticks(rotation=20, ha="right")
    plt.legend()
    plt.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(save_path, dpi=150)
        print(f"[ok] saved stacked bar: {save_path}")
        plt.close()
    else:
        plt.show()

def _sanitize_filename(s: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in s)

def _song_id_from_row(r: dict) -> str:
    sid = (r.get("song_id") or "").strip()
    if sid:
        return sid
    # fallback: filename stem from output_path
    op = (r.get("output_path") or "").strip()
    if op:
        try:
            return Path(op).stem
        except Exception:
            pass
    return "(unknown)"

def draw_model_song_list(model: str, items: list[dict], out_dir: Path):
    """
    items: list of rows (dicts) for this model. Each must have song_id/label.
    Produces one PNG per model with a colored bar per song.
    """
    # sort by label group, then by song_id to keep it readable
    order_rank = {lab: i for i, lab in enumerate(LABELS)}
    items_sorted = sorted(
        items,
        key=lambda r: (order_rank.get(r.get("label","error"), 999), _song_id_from_row(r).lower())
    )

    n = len(items_sorted)
    if n == 0:
        return

    # dynamic height; ~0.35 per row plus padding
    height = max(3.0, 0.35 * n + 1.2)
    fig, ax = plt.subplots(figsize=(10, height))

    y_positions = list(range(n))[::-1]  # top to bottom
    for idx, r in enumerate(items_sorted):
        y = y_positions[idx]
        song = _song_id_from_row(r)
        lab = r.get("label", "error")
        color = COLORS.get(lab, "#999999")
        # Draw filled bar
        ax.barh(y=y, width=1.0, left=0.0, height=0.8, color=color, edgecolor="black", linewidth=0.2)
        # Text overlay (left aligned inside bar); keep it readable with a light bbox
        text = f"{song} — {lab}"
        ax.text(
            0.01, y, text,
            va="center", ha="left",
            fontsize=9,
            bbox=dict(facecolor="white", alpha=0.7, edgecolor="none", pad=1.5)
        )

    # Clean axes
    ax.set_xlim(0, 1)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_frame_on(False)
    ax.set_title(f"Songs & judgements — {model}", pad=10)

    # Build legend
    handles = [plt.Rectangle((0,0),1,1, color=COLORS[l]) for l in LABELS]
    ax.legend(handles, LABELS, loc="upper right", frameon=False, ncol=len(LABELS), bbox_to_anchor=(1, 1.08))

    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"model_songs_{_sanitize_filename(model)}.png"
    out_path = out_dir / fname
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[ok] saved per-model song list: {out_path}")

def per_model_song_lists(rows, out_dir: str):
    out_dir_p = Path(out_dir)
    by_model_rows = defaultdict(list)
    for r in rows:
        m = r.get("model", "unknown")
        by_model_rows[m].append(r)

    for model, items in sorted(by_model_rows.items()):
        draw_model_song_list(model, items, out_dir_p)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="./resources/out/metrics_judged.csv",
                    help="Path to metrics_judged.csv")
    ap.add_argument("--out-dir", default="./resources/out/vis",
                    help="Directory to write visualizations")
    args = ap.parse_args()

    rows = read_rows(args.csv)
    if not rows:
        print("No data.")
        return

    # 1) Stacked bars per model -> IMMER speichern
    stacked_out = str(Path(args.out_dir) / "judgement_stacked.png")
    stacked_bar_by_model(rows, save_path=stacked_out)

    # 2) Per-model song lists -> IMMER erzeugen
    per_model_song_lists(rows, args.out_dir)

if __name__ == "__main__":
    main()