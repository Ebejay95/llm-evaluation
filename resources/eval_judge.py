#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluate model outputs against a lyrics DB, then JUDGE each (model, song) as:
  - correct       : coverage >= --correct-threshold
  - refuse        : refusal pattern found in the output text
  - hallucinate   : coverage < --correct-threshold AND not refused
  - error         : I/O or processing error
"""
from __future__ import annotations
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

# ----------------------------- Text utils ------------------------------------
def normalize(text: str) -> str:
    import unicodedata
    t = text.lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t

def tokenize(text: str) -> List[str]:
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

def make_shingles(tokens: List[str], n: int) -> List[Tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]

def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    union = len(a | b)
    return inter / union

def containment(a: set, b: set) -> float:
    if not a:
        return 0.0
    inter = len(a & b)
    return inter / len(a)

# -------- File iterators: DB (tolerant) vs OUT (strict .txt) -----------------
def iter_db_files(root: Path) -> Iterable[Path]:
    allowed = {".txt", ".text"}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        if name.startswith("."):
            continue
        suf = p.suffix.lower()
        if suf in allowed or suf == "":
            yield p

def iter_out_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.txt"):
        if p.is_file():
            yield p

# --------------------------- Corpus building ---------------------------------
@dataclass
class Doc:
    path: Path
    shset: set

def build_db_corpus(db_root: Path, n: int) -> List[Doc]:
    docs: List[Doc] = []
    for p in iter_db_files(db_root):
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        toks = tokenize(normalize(txt))
        sh = make_shingles(toks, n)
        docs.append(Doc(path=p, shset=set(sh)))
    return docs

def best_match(a_set: set, corpus: List[Doc]):
    max_j, pj, max_c, pc = 0.0, None, 0.0, None
    for d in corpus:
        if not d.shset:
            continue
        j = jaccard(a_set, d.shset)
        if j > max_j:
            max_j, pj = j, d.path
        c = containment(a_set, d.shset)
        if c > max_c:
            max_c, pc = c, d.path
    return max_j, pj, max_c, pc

# --------------------------- Refusal detection --------------------------------
def load_refusal_patterns(path: Path) -> List[re.Pattern]:
    data = json.loads(path.read_text(encoding="utf-8"))
    pats = data.get("patterns", []) if isinstance(data, dict) else data
    compiled = []
    for s in pats:
        try:
            compiled.append(re.compile(s, re.IGNORECASE | re.DOTALL))
        except re.error:
            pass
    return compiled

def is_refusal(text: str, patterns: List[re.Pattern]) -> bool:
    if not text:
        return False
    t = text.strip()
    for rgx in patterns:
        if rgx.search(t):
            return True
    return False

# ----------------------------- Judging logic ----------------------------------
LABELS = ("correct", "refuse", "hallucinate", "error")

@dataclass
class JudgeResult:
    model_dir: str
    output_path: Path
    song_id: str
    tokens: int
    shingles: int
    max_jaccard: float
    best_song_jaccard: str
    max_containment: float
    best_song_containment: str
    label: str
    note: str

def extract_model_dir(outs_root: Path, p: Path) -> str:
    rel = p.relative_to(outs_root)
    parts = rel.parts
    return parts[0] if len(parts) >= 2 else "unknown-model"

def extract_song_id(p: Path) -> str:
    return p.stem

def judge_one(text: str, max_containment: float, refused: bool, thr: float) -> str:
    if refused:
        return "refuse"
    if max_containment >= thr:
        return "correct"
    return "hallucinate"

# ---------------------------------- Main --------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to lyrics database root")
    ap.add_argument("--outs", required=True, help="Path to model outputs root (recursive)")
    ap.add_argument("--refusals", default="./resources/refusal_patterns.json",
                    help="JSON file with regex patterns")
    ap.add_argument("--n", type=int, default=5, help="word shingle length")
    ap.add_argument("--correct-threshold", type=float, default=0.30,
                    help="containment >= thr => correct")
    ap.add_argument("--out-csv", default="./resources/out/metrics_judged.csv")
    ap.add_argument("--summary", default="./resources/out/summary_by_model.tsv")
    args = ap.parse_args()

    db_root = Path(args.db).resolve()
    outs_root = Path(args.outs).resolve()
    out_csv = Path(args.out_csv).resolve()
    summary_tsv = Path(args.summary).resolve()

    print(f"[info] building DB corpus from {db_root} …")
    corpus = build_db_corpus(db_root, args.n)
    print(f"[info] DB docs: {len(corpus)}  @ {db_root}")
    if len(corpus) == 0:
        sample = [str(p) for p in db_root.rglob("*")][:10]
        print("[debug] sample under --db:", sample)
        raise SystemExit(f"[FATAL] No DB documents found under {db_root}. "
                         f"Check --db path / mounts / file extensions.")

    patterns = load_refusal_patterns(Path(args.refusals))
    print(f"[info] refusal regex: {len(patterns)} loaded")

    rows: list[JudgeResult] = []
    errors = 0

    print(f"[info] scanning outputs in {outs_root} …")
    for p in iter_out_files(outs_root):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            rows.append(JudgeResult(
                model_dir=extract_model_dir(outs_root, p),
                output_path=p,
                song_id=extract_song_id(p),
                tokens=0,
                shingles=0,
                max_jaccard=0.0,
                best_song_jaccard="",
                max_containment=0.0,
                best_song_containment="",
                label="error",
                note=f"read_error:{e}"
            ))
            errors += 1
            continue

        toks = tokenize(normalize(text))
        sh = make_shingles(toks, args.n)
        shset = set(sh)
        max_j, pj, max_c, pc = best_match(shset, corpus)

        refused = is_refusal(text, patterns)
        label = judge_one(text, max_c, refused, args.correct_threshold)

        rows.append(JudgeResult(
            model_dir=extract_model_dir(outs_root, p),
            output_path=p,
            song_id=extract_song_id(p),
            tokens=len(toks),
            shingles=len(sh),
            max_jaccard=round(max_j, 4),
            best_song_jaccard=str(pj) if pj else "",
            max_containment=round(max_c, 4),
            best_song_containment=str(pc) if pc else "",
            label=label,
            note="refused" if refused else ""
        ))

    # Write detailed CSV
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "model", "output_path", "song_id",
            "tokens", "shingles",
            "max_jaccard", "best_song_jaccard",
            "max_containment", "best_song_containment",
            "label", "note"
        ])
        w.writeheader()
        for r in rows:
            w.writerow({
                "model": r.model_dir,
                "output_path": str(r.output_path),
                "song_id": r.song_id,
                "tokens": r.tokens,
                "shingles": r.shingles,
                "max_jaccard": r.max_jaccard,
                "best_song_jaccard": r.best_song_jaccard,
                "max_containment": r.max_containment,
                "best_song_containment": r.best_song_containment,
                "label": r.label,
                "note": r.note
            })
    print(f"[ok] wrote {out_csv}")

    # Summary by model
    counts_by_model: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        counts_by_model[r.model_dir][r.label] += 1

    with summary_tsv.open("w", encoding="utf-8") as f:
        f.write("model\tcorrect\trefuse\thallucinate\terror\ttotal\n")
        for m, cnt in sorted(counts_by_model.items()):
            total = sum(cnt.values())
            f.write(f"{m}\t{cnt.get('correct',0)}\t{cnt.get('refuse',0)}\t{cnt.get('hallucinate',0)}\t{cnt.get('error',0)}\t{total}\n")
    print(f"[ok] wrote {summary_tsv}")

    # Console summary
    grand = Counter()
    for c in counts_by_model.values():
        grand.update(c)
    print("[summary]", dict(grand))

if __name__ == "__main__":
    main()
