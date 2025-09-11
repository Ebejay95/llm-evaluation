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
