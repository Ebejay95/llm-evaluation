# resources/utils/baseline_checks.py
from typing import List, Dict, Any

def _set_metrics(expected_top3: List[str], extracted_top3: List[str]) -> Dict[str, float]:
    exp = [e.strip().lower() for e in (expected_top3 or [])]
    got = [g.strip().lower() for g in (extracted_top3 or [])]
    exp_set, got_set = set(exp), set(got)

    overlap = len(exp_set & got_set)
    precision = overlap / max(len(got_set), 1)
    recall = overlap / max(len(exp_set), 1)
    f1 = (2 * precision * recall) / max((precision + recall), 1e-9)
    jaccard = overlap / max(len(exp_set | got_set), 1)
    return {
        "overlap": float(overlap),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "jaccard": float(jaccard),
    }

def run_baseline(company_ids, probes, strict: bool = False):
    # Platzhalter: hier könntest du später echte Baseline-Bewertungen laufen lassen
    for cid in company_ids:
        _ = probes  # ungenutzt im Stub
        print(f"[baseline] processed {cid} (strict={strict})")

def render_baseline_output(company_id: str) -> Dict[str, Any]:
    # Platzhalter-Ausgabe, damit runner.py funktioniert
    return {"company_id": company_id, "status": "ok"}
