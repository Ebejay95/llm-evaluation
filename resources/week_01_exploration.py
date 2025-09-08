import sys
from pathlib import Path

# utils importierbar machen
THIS_DIR = Path(__file__).resolve().parent
UTILS_DIR = THIS_DIR / "utils"
sys.path.insert(0, str(UTILS_DIR))

from app_context import load_company
from scenario_recommender import recommend_scenarios, followup_questions

def run(company_id: str):
    company = load_company(company_id)
    recs = recommend_scenarios(company, top_k=3)

    print(f"\n=== Company: {company['name']} ({company['industry']}) ===")
    for i, r in enumerate(recs, 1):
        print(f"\n[{i}] {r['scenario_name']}")
        print(f"   Score: {r['score']:.2f} | EAL_before: {r['eal_before']:.2f} €")
        print(f"   Warum: {r['explain_fit']}")
        print(f"   Controls: {', '.join(r['suggested_controls'])}")
        print(f"   Frameworks: {', '.join(r['framework_refs'])}")
        print("   Folgefragen:")
        for q in followup_questions(company, r['scenario_name']):
            print(f"    - {q}")

if __name__ == "__main__":
    # CLI: python resources/week_01_exploration.py c-001 c-002
    ids = sys.argv[1:] or ["c-001", "c-002"]
    for cid in ids:
        run(cid)
