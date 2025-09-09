# resources/utils/llm_checks.py
import re
from utils.app_context import load_scenarios, load_controls
from utils.baseline_checks import _set_metrics

_SCENARIOS_KB = None
_CONTROLS_KB = None

def _kb_sets():
    global _SCENARIOS_KB, _CONTROLS_KB
    if _SCENARIOS_KB is None or _CONTROLS_KB is None:
        _SCENARIOS_KB = {s["name"] for s in load_scenarios()}
        _CONTROLS_KB  = {c["name"] for c in load_controls().values()}
    return _SCENARIOS_KB, _CONTROLS_KB

def _extract_list_items(md: str):
    return re.findall(r"^(?:\s*[-*]\s+|\s*\d+\.\s+)(.+)$", md, re.MULTILINE)

def _first_k_scenarios_from_text(md: str, k: int = 3):
    scn_kb, _ = _kb_sets()
    found_order = []
    for line in _extract_list_items(md):
        name = line.strip()
        if name in scn_kb and name not in found_order:
            found_order.append(name)
        else:
            import re as _re
            base = _re.split(r"[\(\-–:]", name, maxsplit=1)[0].strip()
            for kb_name in scn_kb:
                if base and kb_name.lower().startswith(base.lower()) and kb_name not in found_order:
                    found_order.append(kb_name)
                    break
        if len(found_order) >= k:
            break
    return found_order

def _controls_only_from_kb(md: str) -> bool:
    _, ctrl_kb = _kb_sets()
    mentioned = set()
    import re as _re
    for kb in ctrl_kb:
        if _re.search(_re.escape(kb), md, _re.IGNORECASE):
            mentioned.add(kb)
    off_hits = _re.findall(r"\bctl-[a-z0-9\-]+\b", md, _re.IGNORECASE)
    if off_hits:
        return len(mentioned) > 0
    return True

def _mentions_eal_reasoning(md: str) -> bool:
    import re as _re
    return bool(_re.search(r"(EAL|p\s*[×x*]\s*Umsatz\s*[×x*]\s*Impact|p\s*×|Umsatz\s*×)", md, _re.IGNORECASE))

def check_llm_answer(md: str, expected_top3: list) -> dict:
    scn_kb, _ = _kb_sets()
    extracted_top = _first_k_scenarios_from_text(md, 3)
    only_kb_scenarios = all(name in scn_kb for name in extracted_top) and len(extracted_top) == 3
    controls_ok = _controls_only_from_kb(md)
    eal_ok = _mentions_eal_reasoning(md)

    m = _set_metrics(expected_top3, extracted_top)
    top1_ok = (extracted_top and expected_top3 and extracted_top[0].strip().lower() == expected_top3[0].strip().lower())

    return {
        "parsed_top3": extracted_top,
        "only_kb_scenarios": only_kb_scenarios,
        "controls_within_kb": controls_ok,
        "mentions_eal_reasoning": eal_ok,
        "overlap": m["overlap"],
        "precision": m["precision"],
        "recall": m["recall"],
        "f1": m["f1"],
        "jaccard": m["jaccard"],
        "top1_match": top1_ok,
        "all_checks_passed": all([only_kb_scenarios, controls_ok, eal_ok, (m["overlap"] >= 2 and m["jaccard"] >= 0.5)])
    }
