#!/usr/bin/env python3
"""
Hängt `prompt_author`, `prompt_album`, `prompt_title` an ./out/metrics.csv an,
indem die Prompts aus /knowledge-base/prompts.json per Slug gemappt werden.

Wichtig:
- Kein ID-Mapping. Stattdessen: aus "Author, Album, Title" einen Slug bilden,
  der exakt dem Teil nach "<id>-<mode>-" und vor ".txt" entspricht, z.B.
  "Alan Walker, Projects In The Jungle, Takin' My Life"
  -> "alan-walker-projects-in-the-jungle-takin-my-life".
- metrics.csv hat Header; neue Spalten werden angehängt.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import unicodedata
from typing import Dict, Tuple, Optional

# .../<id>-<mode>-<slug>.txt  -> wir wollen <slug>
PATH_PATTERN = re.compile(r"/(\d+)-([a-z_]+)-([^.]+)\.txt$")

def slugify(text: str) -> str:
    if text is None:
        return ""
    # Unicode-Normalisierung + Entfernen von Diakritika
    nfkd = unicodedata.normalize("NFKD", text)
    no_diacritics = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    s = []
    for ch in no_diacritics.lower():
        s.append(ch if ch.isalnum() else "-")
    out = "".join(s)
    out = re.sub(r"-+", "-", out).strip("-")
    return out

def parse_prompt_text(text: str) -> Tuple[str, str, str]:
    parts = [p.strip() for p in (text or "").split(",")]
    if len(parts) != 3:
        parts = (parts + [""] * 3)[:3]
    return parts[0], parts[1], parts[2]

def build_prompt_slug_map(prompts_path: str) -> Dict[str, Tuple[str, str, str]]:
    with open(prompts_path, "r", encoding="utf-8") as f:
        prompts = json.load(f)
    if not isinstance(prompts, list):
        raise ValueError("prompts.json muss ein Array sein")

    slug_map: Dict[str, Tuple[str, str, str]] = {}
    for item in prompts:
        if not isinstance(item, dict):
            continue
        author, album, title = parse_prompt_text(item.get("text", ""))
        slug = slugify(f"{author} {album} {title}")
        slug_map[slug] = (author, album, title)
    return slug_map

def slug_from_output_path(output_path: str) -> Optional[str]:
    m = PATH_PATTERN.search(output_path or "")
    return m.group(3) if m else None

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", default="./out/metrics.csv")
    ap.add_argument("--prompts", default="/knowledge-base/prompts.json")
    ap.add_argument("--out", default="./out/metrics_with_prompts.csv")
    args = ap.parse_args()

    slug_map = build_prompt_slug_map(args.prompts)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    with open(args.metrics, "r", encoding="utf-8") as fin, \
         open(args.out, "w", encoding="utf-8", newline="") as fout:
        reader = csv.reader(fin)
        writer = csv.writer(fout)

        first = True
        for row in reader:
            if first:
                first = False
                writer.writerow(row + ["prompt_author", "prompt_album", "prompt_title"])
                continue

            output_path = row[0] if row else ""
            file_slug = slug_from_output_path(output_path) or ""
            author = album = title = ""

            if file_slug:
                # 1) exakter Treffer
                triple = slug_map.get(file_slug)
                if not triple:
                    # 2) streng normalisieren und versuchen
                    triple = slug_map.get(slugify(file_slug))
                if not triple:
                    # 3) letzte Rettung: Teilstring-Match
                    for s, t in slug_map.items():
                        if s in file_slug or file_slug in s:
                            triple = t
                            break
                if triple:
                    author, album, title = triple

            writer.writerow(row + [author, album, title])

    print(f"Geschrieben: {args.out}")

if __name__ == "__main__":
    main()
