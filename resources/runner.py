import json
from pathlib import Path
from typing import Dict, List

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except Exception:
    class _NoColor:
        def __getattr__(self, _): return ""
    Fore = Style = _NoColor()

from utils.app_context import load_company, load_scenarios, load_controls
from utils.baseline_checks import run_baseline, render_baseline_output
from utils.llm_provider import OllamaProvider
from utils.llm_checks import check_llm_answer
from week_01_exploration import (
    build_system_prompt,
    llm_security_check,
    build_user_prompt_client_chat,
)

def _make_provider(provider_args):
    name = (provider_args or {}).get("provider_name", "ollama")
    if name == "ollama":
        return OllamaProvider(
            model=(provider_args or {}).get("model"),
            host=(provider_args or {}).get("ollama_url"),
        )
    raise RuntimeError(f"Unbekannter/ungerüsteter Provider: {name}. Unterstützt: 'ollama'.")

# ---- Baseline ----
def run_baseline_mode(company_ids: List[str], probes_path: Path, strict: bool = False):
    with probes_path.open("r", encoding="utf-8") as f:
        probes = json.load(f)
    run_baseline(company_ids, probes, strict=strict)

def render_baseline_json(company_ids: List[str]):
    return [render_baseline_output(cid) for cid in company_ids]

# ---- LLM + Checks ----
def run_llm_with_checks(company_ids: List[str], probes_by_id: Dict[str, dict], provider_args):
    provider = _make_provider(provider_args)
    scenarios = load_scenarios()
    controls  = load_controls()
    out = []

    for cid in company_ids:
        company = load_company(cid)
        system = build_system_prompt()
        user   = llm_security_check(company, scenarios, controls)

        banner = f"=== LLM for {cid} ({company['name']}) ==="
        print(f"\n{Style.BRIGHT}{Fore.MAGENTA}{banner}{Style.RESET_ALL}")
        try:
            raw = provider.generate(system, user).strip()
            print(f"{Fore.WHITE}{raw}{Style.RESET_ALL}")

            expected = probes_by_id.get(cid, {}).get("expected_top_scenarios", [])
            checks = check_llm_answer(raw, expected)
            print(f"\n{Style.BRIGHT}{Fore.CYAN}LLM CHECKS:{Style.RESET_ALL} {json.dumps(checks, ensure_ascii=False)}")

            out.append({
                "company_id": cid,
                "company_name": company["name"],
                "raw_markdown": raw,
                "checks": checks
            })
        except Exception as e:
            print(f"{Fore.RED}ERROR: {e}{Style.RESET_ALL}")
            out.append({
                "company_id": cid,
                "company_name": company["name"],
                "error": str(e)
            })
    return out

# ---- Client Chat ----
def run_client_chat_mode(company_id: str, user_question: str, provider_args):
    if not company_id or not isinstance(company_id, str):
        raise ValueError("Ungültige Company-ID.")
    user_question = (user_question or "").strip()
    if not user_question:
        raise ValueError("Die freie Frage darf nicht leer sein.")
    if len(user_question) > 4000:
        raise ValueError("Die freie Frage ist zu lang (>4000 Zeichen). Bitte kürzen.")

    provider = _make_provider(provider_args)
    company = load_company(company_id)
    scenarios = load_scenarios()
    controls = load_controls()

    system = build_system_prompt()
    user = build_user_prompt_client_chat(company, scenarios, controls, user_question)

    banner = f"=== CLIENT CHAT for {company_id} ({company['name']}) ==="
    print(f"\n{Style.BRIGHT}{Fore.MAGENTA}{banner}{Style.RESET_ALL}")
    raw = provider.generate(system, user).strip()
    print(f"{Fore.WHITE}{raw}{Style.RESET_ALL}")
    return {
        "company_id": company_id,
        "company_name": company["name"],
        "question": user_question,
        "raw_markdown": raw
    }