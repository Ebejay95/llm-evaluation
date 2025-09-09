# resources/utils/baseline_checks.py

import json
from pathlib import Path

# Farben (fallback ohne colorama)
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except Exception:
    class _NoColor:
        def __getattr__(self, _): return ""
    Fore = Style = _NoColor()

# KB / Recommender
from utils.app_context import load_company, load_scenarios, load_controls
from utils.scenario_recommender import recommend_scenarios, followup_questions

# Optional: Pfad zu den Probes (wird aktuell nicht von runner.py genutzt)
THIS_DIR = Path(__file__).resolve().parent.parent
PROBES = THIS_DIR / "data" / "probes_w1.json"

# ----------------------------------------------------------------------
# Baseline / Probes
# ----------------------------------------------------------------------
def load_probes():
    return json.loads(PROBES.read_text(encoding="utf-8"))

def normalize_names(names):
    return set(n.strip().lower() for n in names)

def _set_metrics(expected, got):
    exp = set(n.strip().lower() for n in expected)
    got = set(n.strip().lower() for n in got)
    inter = exp & got
    union = exp | got
    overlap = len(inter)
    precision = overlap / max(len(got), 1)
    recall = overlap / max(len(exp), 1)
    f1 = 0.0 if (precision + recall) == 0 else 2 * precision * recall / (precision + recall)
    jaccard = overlap / max(len(union), 1)
    return {"overlap": overlap, "precision": precision, "recall": recall, "f1": f1, "jaccard": jaccard}

def run_one(company_id: str):
    company = load_company(company_id)
    recs = recommend_scenarios(company, top_k=3)
    top_names = [r["scenario_name"] for r in recs]
    ctrls = {c for r in recs for c in r["suggested_controls"]}
    return top_names, ctrls, recs, company

def run_baseline(argcids, probes, strict: bool = False):
    scenarios_kb = {s["name"] for s in load_scenarios()}
    controls_kb  = {c["name"] for c in load_controls().values()}

    total, passed = 0, 0
    for pr in probes:
        cid = pr["company_id"]
        if cid in argcids:
            expected = pr["expected_top_scenarios"]
            got_scenarios, got_ctrls, _, _ = run_one(cid)

            m = _set_metrics(expected, got_scenarios)
            top1_ok = (got_scenarios and expected and got_scenarios[0].strip().lower() == expected[0].strip().lower())

            checks = []
            checks.append(("Top3 nur aus KB", set(got_scenarios).issubset(scenarios_kb)))
            checks.append(("Controls nur aus KB", set(got_ctrls).issubset(controls_kb)))

            if strict:
                equal_sets = (normalize_names(got_scenarios) == normalize_names(expected))
                checks.append(("Top3 decken Erwartung ab (mengenbasiert)", equal_sets))
            else:
                checks.append((f"Top3 Overlap ≥2 & Jaccard≥0.5 (F1={m['f1']:.2f})", (m["overlap"] >= 2 and m["jaccard"] >= 0.5)))
                checks.append(("Top1 match (Head-Agreement)", top1_ok))

            total += len(checks)
            local_pass = sum(1 for _, ok in checks if ok)
            passed += local_pass

            header = f"[{cid}] Checks {local_pass}/{len(checks)}"
            color = Fore.CYAN if local_pass == len(checks) else Fore.YELLOW
            print(f"\n{Style.BRIGHT}{color}{header}{Style.RESET_ALL}")

            for name, ok in checks:
                mark = f"{Fore.GREEN}OK{Style.RESET_ALL}" if ok else f"{Fore.RED}FAIL{Style.RESET_ALL}"
                print(f" - {name}: {mark}")

            # Transparenz
            print(f" {Fore.WHITE}Got   :{Style.RESET_ALL} {got_scenarios}")
            print(f" {Fore.WHITE}Expect:{Style.RESET_ALL} {expected}")
            print(f" {Fore.WHITE}Metrics:{Style.RESET_ALL} overlap={m['overlap']} precision={m['precision']:.2f} recall={m['recall']:.2f} F1={m['f1']:.2f} Jaccard={m['jaccard']:.2f}")

    summary = f"=== SUMMARY: {passed}/{total} checks passed ==="
    sum_color = Fore.GREEN if passed == total and total > 0 else (Fore.YELLOW if passed > 0 else Fore.RED)
    print(f"\n{Style.BRIGHT}{sum_color}{summary}{Style.RESET_ALL}")

def render_baseline_output(company_id: str):
    _, _, recs, company = run_one(company_id)
    return {
        "company_id": company_id,
        "company_name": company["name"],
        "scenarios": [
            {
                "name": r["scenario_name"],
                "score": r["score"],
                "why": r["explain_fit"],
                "controls": r["suggested_controls"],
                "framework_refs": r["framework_refs"],
                "eal_before": r["eal_before"],
            } for r in recs
        ],
        "followups": followup_questions(company, recs[0]["scenario_name"]) if recs else []
    }
