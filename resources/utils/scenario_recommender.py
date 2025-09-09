from typing import List, Dict, Any, Tuple
from utils.app_context import load_scenarios, load_controls

def score_scenario(company: Dict[str, Any], scn: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
    revenue = float(company.get("revenue_eur", 0.0))
    p = float(scn["annual_frequency"])
    impact_pct = float(scn["impact_pct_revenue"])
    eal_before = p * (revenue * impact_pct)

    boost = 1.0

    if company.get("industry") in scn.get("industries", []):
        boost += 0.25


    if company.get("employees", 0) >= 100 and "email" in scn.get("tags", []):
        boost += 0.15

    applicability = 1.0

    score = eal_before * boost * applicability
    return score, {"eal_before": eal_before, "boost": boost, "applicability": applicability}

def recommend_scenarios(company: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
    scenarios = load_scenarios()
    ctrls = load_controls()
    ranked = []
    for scn in scenarios:
        s, parts = score_scenario(company, scn)
        ranked.append((s, parts, scn))
    ranked.sort(key=lambda x: x[0], reverse=True)

    results = []
    for s, parts, scn in ranked[:top_k]:
        scn_controls = [ctrls[cid]["name"] for cid in scn.get("control_ids", []) if cid in ctrls]
        results.append({
            "scenario_id": scn["id"],
            "scenario_name": scn["name"],
            "score": round(s, 2),
            "eal_before": round(parts["eal_before"], 2),
            "explain_fit": _explain_fit(company, scn, parts),
            "suggested_controls": scn_controls,
            "framework_refs": scn.get("framework_refs", [])
        })
    return results

def _explain_fit(company: Dict[str, Any], scn: Dict[str, Any], parts: Dict[str, float]) -> str:
    reasons = []
    if company.get("industry") in scn.get("industries", []):
        reasons.append("Branche passt")
    if company.get("employees", 0) >= 100 and "email" in scn.get("tags", []):
        reasons.append("E-Mail-Risiko skaliert")
    base = f"EAL_before ≈ p×Umsatz×Impact = {parts['eal_before']:.0f} €"
    return ", ".join(reasons) + ("; " if reasons else "") + base

def followup_questions(company: Dict[str, Any], scenario_name: str) -> List[str]:
    q = [
        f"Welche geschäftskritischen Prozesse wären von '{scenario_name}' betroffen (IT/OT getrennt)?",
        "Gibt es Evidenz (≤90 Tage) zu MFA, EDR, Backups, Segmentierung?",
        "Wie hoch ist grob die Abdeckung (Coverage) der relevanten Controls?",
        "Wann war der letzte Restore-/IR-Test? Gibt es Protokolle?",
        "Gibt es Drittparteien/Vendoren mit hohem Zugriff (Supply Chain)?"
    ]
    return q
