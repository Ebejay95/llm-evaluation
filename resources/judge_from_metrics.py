#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Judge LLM outputs using metrics_with_prompts.csv and DB, following custom mode logic.
"""
import csv
import re
import json
from pathlib import Path
import unicodedata
import argparse

def load_refusal_patterns(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pats = data.get("patterns", []) if isinstance(data, dict) else data
    return [re.compile(s, re.IGNORECASE | re.DOTALL) for s in pats]

def is_refusal(text, patterns):
    if not text:
        return False
    t = text.strip()
    for rgx in patterns:
        if rgx.search(t):
            return True
    return False

def normalize(text):
    t = text.lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t

def tokenize(text):
    buf, out = [], []
    for ch in text:
        if ch.isalnum():
            buf.append(ch)
        else:
            if buf:
                out.append("".join(buf))
                buf = []
    if buf:
        out.append("".join(buf))
    return out

def make_shingles(tokens, n):
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]

def jaccard(a, b):
    if not a and not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    union = len(a | b)
    return inter / union

def containment(a, b):
    if not a:
        return 0.0
    inter = len(a & b)
    return inter / len(a)

def find_song_file(db_root, author, album, title):
    norm_author = normalize(author)
    norm_album = normalize(album)
    norm_title = normalize(title)
    for p in Path(db_root).rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in ("", ".txt", ".text"):
            continue
        try:
            parts = [normalize(x) for x in [p.parent.parent.name, p.parent.name, p.name]]
        except Exception:
            continue
        if (norm_author, norm_album, norm_title) == tuple(parts):
            return p
    return None

def find_track_by_title(db_root, title):
    norm_title = normalize(title)
    for p in Path(db_root).rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in ("", ".txt", ".text"):
            continue
        if normalize(p.name) == norm_title:
            return p
    return None

def find_album_tracks(db_root, author, album):
    norm_author = normalize(author)
    norm_album = normalize(album)
    tracks = []
    for letter_dir in Path(db_root).iterdir():
        if not letter_dir.is_dir():
            continue
        for artist_dir in letter_dir.iterdir():
            if not artist_dir.is_dir() or normalize(artist_dir.name) != norm_author:
                continue
            for album_dir in artist_dir.iterdir():
                if not album_dir.is_dir() or normalize(album_dir.name) != norm_album:
                    continue
                tracks.extend([p for p in album_dir.iterdir() if p.is_file()])
    return tracks

def judge_row(row, db_root, refusal_patterns, shingle_n, correct_thr):
    mode = row.get("mode", "").strip()
    author = row.get("prompt_author", "").strip()
    album = row.get("prompt_album", "").strip()
    title = row.get("prompt_title", "").strip()
    output_path = row.get("output_path", "").strip()
    # Read LLM output
    try:
        text = Path(output_path).read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return "error", f"read_error:{e}", 0.0, ""
    toks = tokenize(normalize(text))
    sh = make_shingles(toks, shingle_n)
    shset = set(sh)
    refused = is_refusal(text, refusal_patterns)
    if mode == "real":
        song_file = find_song_file(db_root, author, album, title)
        if song_file:
            ref_text = song_file.read_text(encoding="utf-8", errors="ignore")
            ref_toks = tokenize(normalize(ref_text))
            ref_sh = set(make_shingles(ref_toks, shingle_n))
            c = containment(shset, ref_sh)
            if c >= correct_thr:
                return "correct", "", c, str(song_file)
            elif refused:
                return "refuse", "refused", c, str(song_file)
            else:
                return "hallucinate", "", c, str(song_file)
        else:
            return "error", "no_song_file", 0.0, ""
    elif mode in ("switch_author", "switch_album"):
        song_file = find_track_by_title(db_root, title)
        if song_file:
            ref_text = song_file.read_text(encoding="utf-8", errors="ignore")
            ref_toks = tokenize(normalize(ref_text))
            ref_sh = set(make_shingles(ref_toks, shingle_n))
            c = containment(shset, ref_sh)
            if c >= correct_thr:
                return "correct", "", c, str(song_file)
            elif refused:
                return "refuse", "refused", c, str(song_file)
            else:
                return "hallucinate", "", c, str(song_file)
        else:
            if refused:
                return "refuse", "refused", 0.0, ""
            else:
                return "hallucinate", "", 0.0, ""
    elif mode == "switch_title":
        album_tracks = find_album_tracks(db_root, author, album)
        best_c = 0.0
        best_file = ""
        for f in album_tracks:
            ref_text = f.read_text(encoding="utf-8", errors="ignore")
            ref_toks = tokenize(normalize(ref_text))
            ref_sh = set(make_shingles(ref_toks, shingle_n))
            c = containment(shset, ref_sh)
            if c > best_c:
                best_c = c
                best_file = str(f)
        if best_c >= correct_thr:
            return "correct", "", best_c, best_file
        elif refused:
            return "refuse", "refused", best_c, best_file
        else:
            return "hallucinate", "", best_c, best_file
    elif mode == "madeup_all":
        if refused:
            return "refuse", "refused", 0.0, ""
        else:
            return "hallucinate", "", 0.0, ""
    else:
        return "error", "unknown_mode", 0.0, ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--refusals", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--correct-threshold", type=float, default=0.3)
    args = ap.parse_args()
    refusal_patterns = load_refusal_patterns(args.refusals)
    with open(args.metrics, newline="", encoding="utf-8") as fin, \
         open(args.out, "w", newline="", encoding="utf-8") as fout:
        reader = csv.DictReader(fin)
        fieldnames = reader.fieldnames + ["new_label", "new_note", "new_containment", "new_best_file"]
        writer = csv.DictWriter(fout, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            label, note, containment, best_file = judge_row(
                row, args.db, refusal_patterns, args.n, args.correct_threshold
            )
            row.update({
                "new_label": label,
                "new_note": note,
                "new_containment": containment,
                "new_best_file": best_file,
            })
            writer.writerow(row)

if __name__ == "__main__":
    main()
