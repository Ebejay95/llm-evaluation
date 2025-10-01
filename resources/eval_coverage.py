#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evaluate overlap ("coverage") between model outputs and a local lyrics database
AND judge each (model, song) into one of: correct, refuse, hallucinate, error.

Labels:
- correct      : coverage >= --correct-threshold
- refuse       : matches a refusal regex pattern (model admits not knowing / declines)
- hallucinate  : coverage < --correct-threshold AND not refused
- error        : I/O or processing error

Optionally: generate outputs via local/remote models (keeps previous functionality).

NEU:
- Prompts werden inkl. 'mode' geladen.
- Beim Generieren wird 'mode' in den Dateinamen eingebettet (NNN-mode-slug.txt).
- Beim Evaluieren wird per Index (NNN) -> mode gemappt und in metrics.csv geschrieben.
- Optional wird eine prompts_index.csv unter --out-root erzeugt (hilfreich für Audits).
"""
from __future__ import annotations
import argparse
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Iterable
import csv
from collections import Counter, defaultdict
import json
import time
import random

# ---------------- Refusal patterns (default fallback if no file is given) ----
_DEFAULT_REFUSAL_PATTERNS = [
    r"i\s+don'?t\s+know\s+(this|the)\s+song",
    r"i\s+do\s+not\s+know\s+(this|the)\s+song",
    r"i\s+am\s+not\s+familiar\s+with\s+(this|the)\s+song",
    r"cannot\s+provide\s+the\s+lyrics",
    r"can\s+not\s+provide\s+the\s+lyrics",
    r"i\s+can'?t\s+provide\s+the\s+lyrics",
    r"sorry\b.*\b(i\s+don'?t\s+know|i\s+can'?t\s+provide)",
    r"unfortunately\b.*\b(i\s+don'?t\s+know|i\s+can'?t)",
    r"i\s+don'?t\s+have\s+access\s+to\s+the\s+lyrics",
    r"ich\s+kenne\s+(dieses|den)\s+lied\s+nicht",
    r"ich\s+kenne\s+den\s+song\s+nicht",
    r"ich\s+wei[ßs]\s+es\s+nicht",
    r"kann\s+die\s+lyrics\s+nicht\s+bereitstellen",
    r"kann\s+den\s+songtext\s+nicht\s+bereitstellen",
    r"tut\s+mir\s+leid\b.*\b(kenn|kann\s+nicht)",
    r"leider\b.*\b(kenn|kann\s+nicht)",
]

# --------- Optional router (only needed for --generate) ----------------------
def _try_import_router():
    try:
        from llm_router import prompt as _router_prompt, resolve_model as _resolve_model
        return _router_prompt, _resolve_model
    except Exception as e:
        raise RuntimeError(
            "llm_router.py konnte nicht importiert werden. "
            "Lege die Datei in den Import-Pfad oder starte im resources-Verzeichnis."
        ) from e

# ------------------------------- Tokenizer etc. -------------------------------
STOP_DE = {
    "der","die","das","und","ist","im","in","den","ein","eine","ich","du","er","sie","wir","ihr",
    "nicht","mit","auf","für","zu","von","wie","einfach","auch","so","nur","noch","dass","an","am",
    "dem","des","sind",
}
STOP_EN = {
    "the","and","is","in","to","of","that","it","for","on","you","i","me","my","we","they","he",
    "she","a","an","with","as","so","but","at","by","from","are","was","be","your","our","not","copyright","know",
}

@dataclass
class Doc:
    path: Path
    text: str
    tokens: List[str]
    shingles: List[Tuple[str, ...]]
    shset: set
    genre: str | None
    lang: str | None

def normalize(text: str) -> str:
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

def detect_lang(tokens: List[str]) -> str | None:
    if not tokens:
        return None
    cnt = Counter(tokens)
    total = sum(cnt.values())
    hits_de = sum(cnt[w] for w in STOP_DE)
    hits_en = sum(cnt[w] for w in STOP_EN)
    rate_de = hits_de / max(total, 1)
    rate_en = hits_en / max(total, 1)
    if max(rate_de, rate_en) < 0.005:
        return None
    return "de" if rate_de >= rate_en else "en"

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
    """
    Accept .txt/.text AND files without suffix. Skip hidden files/dirs.
    """
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
    """
    Generated outputs are .txt files; keep it strict here.
    """
    for p in root.rglob("*.txt"):
        if p.is_file():
            yield p

def genre_from_path(base: Path, file_path: Path) -> str | None:
    try:
        rel = file_path.relative_to(base)
        parts = rel.parts
        return parts[0] if len(parts) >= 2 else None  # genre/artist/song.txt
    except Exception:
        return None

def build_corpus(root: Path, shingle_n: int) -> List[Doc]:
    docs: List[Doc] = []
    for p in iter_db_files(root):
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        toks = tokenize(normalize(txt))
        sh = make_shingles(toks, shingle_n)
        sset = set(sh)
        genre = genre_from_path(root, p)
        lang = detect_lang(toks)
        docs.append(Doc(path=p, text="", tokens=toks, shingles=sh, shset=sset, genre=genre, lang=lang))
    return docs

def best_match(a_set: set, corpus: List[Doc]):
    # returns (max_jaccard, path_j, max_containment, path_c)
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

# -------------------------- Generation utilities -----------------------------
_slug_pat = re.compile(r"[^a-z0-9\-]+")
def slugify(s: str, maxlen: int = 80) -> str:
    s = normalize(s)
    s = s.replace(" ", "-")
    s = _slug_pat.sub("-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("-")
    return s or "prompt"

def sanitize_model_dir(model_spec: str) -> str:
    # 'openrouter/deepseek/deepseek-chat-v3.1' -> 'openrouter-deepseek-deepseek-chat-v3.1'
    return re.sub(r"[^\w\.-]+", "-", model_spec)

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def load_prompts(path: Path) -> List[dict]:
    """
    Lädt Prompts als Liste von Dicts mit mindestens {'text': str, 'mode': str?}.
    Fällt für reine Strings auf mode='real' zurück.
    Die Reihenfolge definiert den Index (1-basiert), der in Dateinamen NNN- verwendet wird.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    out: List[dict] = []
    for item in data:
        if isinstance(item, dict) and "text" in item:
            out.append({"text": str(item["text"]).strip(),
                        "mode": str(item.get("mode", "real")).strip() or "real"})
        elif isinstance(item, str):
            out.append({"text": item.strip(), "mode": "real"})
    return [x for x in out if x.get("text")]

def generate_outputs(models: List[str], prompts_path: Path, out_root: Path,
                     system_prompt: str, temperature: float, max_tokens: int,
                     ollama_base_url: str | None = None) -> None:
    router_prompt, resolve_model = _try_import_router()
    if ollama_base_url:
        os.environ["OLLAMA_BASE_URL"] = ollama_base_url

    prompts = load_prompts(prompts_path)
    if not prompts:
        print(f"[gen] Keine Prompts in {prompts_path}")
        return

    # Optional: einmalige Index-Tabelle pro prompts.json
    try:
        idx_csv = out_root / "prompts_index.csv"
        if not idx_csv.exists():
            idx_csv.parent.mkdir(parents=True, exist_ok=True)
            with idx_csv.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["idx", "text", "mode"])
                for i, p in enumerate(prompts, start=1):
                    w.writerow([i, p["text"], p["mode"]])
            print(f"[gen] wrote {idx_csv}")
    except Exception as e:
        print(f"[gen][warn] prompts_index.csv nicht geschrieben: {e}")

    for model in models:
        spec = resolve_model(model)
        model_id = f"{spec.provider}/{spec.model}"
        out_dir = out_root / sanitize_model_dir(model_id)
        ensure_dir(out_dir)
        print(f"[gen] Modell: {model_id} -> {out_dir}")

        for idx, item in enumerate(prompts, start=1):
            text = item["text"]
            mode = item.get("mode", "real")
            fname = f"{idx:03d}-{mode}-{slugify(text)}.txt"
            fpath = out_dir / fname

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ]

            # simple retry
            tries = 3
            delay = 1.0
            for attempt in range(1, tries+1):
                try:
                    ans = router_prompt(
                        spec, messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    ans = (ans or "").strip()
                    if not ans:
                        raise RuntimeError("Leere Antwort erhalten.")
                    fpath.write_text(ans, encoding="utf-8")
                    print(f"[gen] wrote {fpath.relative_to(out_root)}")
                    break
                except Exception as e:
                    if attempt == tries:
                        print(f"[gen][ERR] {model_id} prompt#{idx}: {e}")
                    else:
                        time.sleep(delay + random.random()*0.5)
                        delay = min(delay*2, 8.0)

# -------------------------- Refusal handling & Judge --------------------------
def load_refusal_patterns(path: Path | None) -> list[re.Pattern]:
    patterns: list[str] = []
    if path and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                patterns = list(map(str, data.get("patterns", [])))
            elif isinstance(data, list):
                patterns = list(map(str, data))
        except Exception:
            pass
    if not patterns:
        patterns = _DEFAULT_REFUSAL_PATTERNS
    compiled: list[re.Pattern] = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.IGNORECASE | re.DOTALL))
        except re.error:
            # skip invalid regex
            pass
    return compiled

def is_refusal(text: str, compiled: list[re.Pattern]) -> bool:
    if not text:
        return False
    t = text.strip()
    for rgx in compiled:
        if rgx.search(t):
            return True
    return False

def judge_label(max_containment: float, refused: bool, threshold: float) -> str:
    if refused:
        return "refuse"
    if max_containment >= threshold:
        return "correct"
    return "hallucinate"

# ---------------------------------- Main --------------------------------------
def main():
    ap = argparse.ArgumentParser()
    # Generierung (optional)
    ap.add_argument("--generate", action="store_true",
                    help="Vor der Evaluierung Prompts an Modelle senden und Outputs speichern.")
    ap.add_argument("--models", type=str, default="",
                    help="Kommagetrennt, z.B. 'ollama/llama3.2:1b,ollama/qwen2:0.5b,openrouter/deepseek/deepseek-chat-v3.1'")
    ap.add_argument("--prompts", type=str, default="./resources/knowledge-base/prompts.json",
                    help="Pfad zu Prompts JSON (Liste von {'text': ...,'mode': ...} oder Strings).")
    ap.add_argument("--system", type=str,
                    default="[KB]Say 'I don't know this song!' if you are not sure to know the exact lyrics![/KB] You are a lyrics librarian for songs texts. Your responses only contain the lyrics of the requested song. Nothing more. Strip away further information of song and the song structure, please.",
                    help="Systemprompt für die Generierung.")
    ap.add_argument("--out-root", type=str, default="./resources/out",
                    help="Wurzelverzeichnis, in das pro Modell geschrieben wird.")
    ap.add_argument("--gen-temperature", type=float, default=0.2)
    ap.add_argument("--gen-max-tokens", type=int, default=1024)
    ap.add_argument("--ollama-url", type=str, default=None,
                    help="Optional OLLAMA_BASE_URL überschreiben, z.B. http://ollama:11434")

    # Evaluierung (bestehend + Judge-Erweiterung)
    ap.add_argument("--db", required=True, help="Path to lyrics database root")
    ap.add_argument("--outs", required=True, help="Path to model outputs root (rekursiv)")
    ap.add_argument("--out-csv", default="./resources/out/metrics.csv")
    ap.add_argument("--n", type=int, default=5, help="word shingle length (default 5)")
    ap.add_argument("--threshold", type=float, default=0.3, help="flag as memorized if containment>=thr (legacy)")
    # judge-specific
    ap.add_argument("--correct-threshold", type=float, default=0.30,
                    help="containment >= thr => correct")
    ap.add_argument("--refusals", type=str, default="./resources/refusal_patterns.json",
                    help="JSON mit Regex-Patterns oder Liste von Strings; wenn fehlt, wird ein Default-Set genutzt")
    ap.add_argument("--plot", type=str, default="",
                    help="Optionaler Pfad zu PNG (Stacked Bars pro Modell in Grün/Gelb/Orange/Rot)")
    args = ap.parse_args()

    # Optional: Generierung fahren
    if args.generate:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
        if not models:
            raise SystemExit("--generate gesetzt, aber --models ist leer.")
        generate_outputs(
            models=models,
            prompts_path=Path(args.prompts),
            out_root=Path(args.out_root),
            system_prompt=args.system.strip(),
            temperature=args.gen_temperature,
            max_tokens=args.gen_max_tokens,
            ollama_base_url=args.ollama_url,
        )

    # ---------------------- Evaluierung + Judge ----------------------
    db_root = Path(args.db).resolve()
    outs_root = Path(args.outs).resolve()
    out_csv = Path(args.out_csv).resolve()
    refusals_path = Path(args.refusals).resolve() if args.refusals else None

    print(f"[info] building DB corpus from {db_root} …")
    corpus = build_corpus(db_root, args.n)
    print(f"[info] DB docs: {len(corpus)}  @ {db_root}")
    if len(corpus) == 0:
        # help debug immediately
        sample = [str(p) for p in db_root.rglob("*")][:10]
        print("[debug] sample under --db:", sample)
        raise SystemExit(f"[FATAL] No DB documents found under {db_root}. "
                         f"Check --db path, mounts, or file extensions.")

    patterns = load_refusal_patterns(refusals_path)
    print(f"[info] refusal regex: {len(patterns)} geladen")

    # Map: idx -> mode aus prompts.json
    idx_to_mode: dict[int, str] = {}
    try:
        for i, item in enumerate(load_prompts(Path(args.prompts)), start=1):
            idx_to_mode[i] = item.get("mode", "real")
    except Exception:
        pass
    idx_re = re.compile(r"^(\d{3})-")

    print(f"[info] scanning outputs in {outs_root} …")
    rows = []
    agg_by_genre = defaultdict(list)
    agg_by_lang = defaultdict(list)

    # Judge aggregations
    counts_by_model: dict[str, Counter] = defaultdict(Counter)

    def model_dir_of(p: Path) -> str:
        try:
            rel = p.relative_to(outs_root)
            return rel.parts[0] if len(rel.parts) >= 2 else "unknown-model"
        except Exception:
            return "unknown-model"

    for p in iter_out_files(outs_root):
        model_dir = model_dir_of(p)

        # mode via index aus Dateiname
        mode = "?"
        m = idx_re.match(p.name)
        if m:
            try:
                mode = idx_to_mode.get(int(m.group(1)), "?")
            except Exception:
                pass

        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            r = {
                "output_path": str(p),
                "lang": "?",
                "tokens": 0,
                "shingles": 0,
                "max_jaccard": 0.0,
                "best_song_jaccard": "",
                "max_containment": 0.0,
                "best_song_containment": "",
                "genre": "?",
                "memorization_flag": 0,
                "model": model_dir,
                "mode": mode,
                "label": "error",
                "note": f"read_error:{e}",
            }
            rows.append(r)
            counts_by_model[model_dir]["error"] += 1
            continue

        toks = tokenize(normalize(txt))
        sh = make_shingles(toks, args.n)
        shset = set(sh)
        lang = detect_lang(toks)
        max_j, pj, max_c, pc = best_match(shset, corpus)
        genre = None
        if pj is not None:
            genre = genre_from_path(db_root, pj)
        flagged = 1 if max_c >= args.threshold else 0

        refused = is_refusal(txt, patterns)
        label = judge_label(max_c, refused, args.correct_threshold)

        r = {
            "output_path": str(p),
            "lang": lang or "?",
            "tokens": len(toks),
            "shingles": len(sh),
            "max_jaccard": round(max_j, 4),
            "best_song_jaccard": str(pj) if pj else "",
            "max_containment": round(max_c, 4),
            "best_song_containment": str(pc) if pc else "",
            "genre": genre or "?",
            "memorization_flag": flagged,
            "model": model_dir,
            "mode": mode,
            "label": label,
            "note": "refused" if refused else "",
        }
        rows.append(r)

        if genre:
            agg_by_genre[genre].append(max_c)
        if lang:
            agg_by_lang[lang].append(max_c)
        counts_by_model[model_dir][label] += 1

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()) if rows else
                       ["output_path","model","mode","lang","tokens","shingles",
                        "max_jaccard","best_song_jaccard","max_containment","best_song_containment",
                        "genre","memorization_flag","label","note"]
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[ok] wrote metrics: {out_csv}")

    def mean(xs):
        return sum(xs)/len(xs) if xs else 0.0

    overall_mean = mean([r["max_containment"] for r in rows]) if rows else 0.0
    print(f"[summary] outputs={len(rows)}  avg_containment={overall_mean:.3f}  "
          f"flagged@{args.threshold}={sum(r['memorization_flag'] for r in rows)}")

    # Aggregates (legacy)
    agg_genre_path = out_csv.with_name("agg_by_genre.tsv")
    with agg_genre_path.open("w", encoding="utf-8") as f:
        f.write("genre\tcount\tavg_containment\n")
        for g, vals in sorted(agg_by_genre.items()):
            f.write(f"{g}\t{len(vals)}\t{mean(vals):.4f}\n")
    print(f"[ok] wrote {agg_genre_path}")

    agg_lang_path = out_csv.with_name("agg_by_lang.tsv")
    with agg_lang_path.open("w", encoding="utf-8") as f:
        f.write("lang\tcount\tavg_containment\n")
        for l, vals in sorted(agg_by_lang.items()):
            f.write(f"{l}\t{len(vals)}\t{mean(vals):.4f}\n")
    print(f"[ok] wrote {agg_lang_path}")

    # Judge summary per model
    summary_tsv = out_csv.with_name("summary_by_model.tsv")
    with summary_tsv.open("w", encoding="utf-8") as f:
        f.write("model\tcorrect\trefuse\thallucinate\terror\ttotal\n")
        for m in sorted(counts_by_model.keys()):
            cnt = counts_by_model[m]
            total = sum(cnt.values())
            f.write(f"{m}\t{cnt.get('correct',0)}\t{cnt.get('refuse',0)}\t"
                    f"{cnt.get('hallucinate',0)}\t{cnt.get('error',0)}\t{total}\n")
    print(f"[ok] wrote {summary_tsv}")

    # Optional plot
    if args.plot:
        try:
            import matplotlib.pyplot as plt
            COLORS = {
                "correct": "#2ecc71",      # green
                "refuse": "#f1c40f",       # yellow
                "hallucinate": "#e67e22",  # orange
                "error": "#e74c3c",        # red,
            }
            labels = ["correct", "refuse", "hallucinate", "error"]
            models = sorted(counts_by_model.keys())
            base = [0]*len(models)
            plt.figure()
            for lab in labels:
                vals = [counts_by_model[m].get(lab, 0) for m in models]
                plt.bar(models, vals, bottom=base, label=lab, color=COLORS[lab])
                base = [base[i] + vals[i] for i in range(len(vals))]
            plt.title("Judgement per model")
            plt.xlabel("Model")
            plt.ylabel("Count")
            plt.xticks(rotation=20, ha="right")
            plt.legend()
            plt.tight_layout()
            out_path = Path(args.plot).resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(out_path, dpi=150)
            print(f"[ok] wrote plot: {out_path}")
        except Exception as e:
            print(f"[warn] plot failed: {e}")

if __name__ == "__main__":
    main()
