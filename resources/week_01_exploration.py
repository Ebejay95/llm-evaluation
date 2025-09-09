# resources/week_01_exploration.py
import json, sys
from pathlib import Path

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except Exception:
    class _NoColor:
        def __getattr__(self, _): return ""
    Fore = Style = _NoColor()

# === Prompt-Builder bleiben hier ===
import textwrap
from typing import Any, Dict, List

def build_system_prompt() -> str:
    return (
        "Du bist ein Security Risk Advisor. Antworte ausschließlich auf Basis der gelieferten JSONs. "
        "Erfinde keine neuen Szenarien/Controls/Framework-Refs. "
        "Wenn Information fehlt, fordere gezielt Evidenz an. "
        "Antworte präzise, in reinem JSON ohne Erläuterung oder sauberem Markdownund mit kurzen, nachvollziehbaren Begründungen."
    )

def llm_security_check(company: Dict[str, Any], scenarios: List[Dict[str, Any]], controls: Dict[str, Dict[str, Any]]) -> str:
    company_json = json.dumps(company, ensure_ascii=False)
    scenarios_json = json.dumps(scenarios, ensure_ascii=False)
    controls_json = json.dumps(list(controls.values()), ensure_ascii=False)
    return textwrap.dedent(f"""
    COMPANY_JSON:
    {company_json}

    SCENARIOS_JSON:
    {scenarios_json}

    CONTROLS_JSON:
    {controls_json}

    AUFGABE:
    1) Liefere nur die rohe JSON ohne markdown, wie es eine API tun würde. Nutze die zur Verfügung stehenden Datasets.
    2) Das JSON enthaellt 1 attribut "recommended_scenarios" mit einem array von scenario ids, die auf das Unternehmen passen.
    3) Das JSON enthaellt ein Attribut "frameworks" in dem die jeweils passende Vorgaben zu einem scenario anhand seiner id gepsiehcert werden. Diese werden, wenn mehrere gelten mit einem | getrennt.
    4) Das JSON enthaellt eine Bewertung "score" des Unternehmens in Schulnoten von A, B, C, D, E, F (A unkritisch bis F ultrakritisch)
    5) Dann kannst du einen einfachen Begruendungstext ohne innere Quotes und Gleiederung mit maximal 100 Woertern erstellen in einem JSON Attribut "analysis"
    """).strip()

def build_user_prompt_client_chat(company: Dict[str, Any], scenarios: List[Dict[str, Any]], controls: Dict[str, Dict[str, Any]], user_question: str) -> str:
    company_json = json.dumps(company, ensure_ascii=False)
    scenarios_json = json.dumps(scenarios, ensure_ascii=False)
    controls_json = json.dumps(list(controls.values()), ensure_ascii=False)
    return textwrap.dedent(f"""
    COMPANY_JSON:
    {company_json}

    SCENARIOS_JSON:
    {scenarios_json}

    CONTROLS_JSON:
    {controls_json}

    USER_QUESTION:
    {user_question}

    AUFGABE:
    Beantworte die USER_QUESTION faktentreu und ausschließlich auf Basis der obigen JSONs.
    - Wenn es um Begriffe (z. B. DDoS) geht, erkläre kurz und laienverständlich.
    - Wenn Maßnahmen/Empfehlungen genannt werden, nutze NUR Controls aus CONTROLS_JSON und nenne passende Framework-Refs aus SCENARIOS_JSON/CONTROLS_JSON.
    - Wenn die Frage Szenario-spezifisch ist, referenziere die zugehörigen Szenarienamen aus SCENARIOS_JSON.
    - Liste 2-4 sinnvolle Folgefragen (Evidenz, Coverage, OT-Zonen, je nach Firma).
    Ausgabeformat: Markdown mit klaren Abschnitten (Erklärung, Relevanz für die Firma, Empfohlene Controls, Framework-Refs, Folgefragen).
    """).strip()

# === Verschlanktes main(): delegiert nur noch ===
def main():
    from cli_args import parse_args, provider_args_from
    from runner import (
        run_baseline_mode,
        render_baseline_json,
        run_llm_with_checks,
        run_client_chat_mode,
    )

    args = parse_args()
    provider_args = provider_args_from(args)

    THIS_DIR = Path(__file__).resolve().parent
    PROBES = THIS_DIR / "data" / "probes_w1.json"

    if args.client_chat:
        if not args.ask.strip():
            print(f"{Fore.RED}Für --client-chat ist --ask \"<Frage>\" erforderlich.{Style.RESET_ALL}")
            sys.exit(2)
        cc = run_client_chat_mode(args.client_chat, args.ask, provider_args)
        log_payload = {"baseline": None, "llm_runs": None, "client_chat": cc}
    else:
        if not PROBES.exists():
            print(f"{Fore.RED}Missing probes file: {PROBES}{Style.RESET_ALL}")
            sys.exit(1)

        log_payload = {"baseline": None, "llm_runs": None, "client_chat": None}

        if args.as_json:
            baseline_out = render_baseline_json(args.ids)
            print(json.dumps(baseline_out, ensure_ascii=False, indent=2))
            log_payload["baseline"] = baseline_out
        else:
            run_baseline_mode(args.ids, PROBES, strict=args.strict)

        if args.with_llm:
            probes = json.loads(PROBES.read_text(encoding="utf-8"))
            probes_by_id = {p["company_id"]: p for p in probes}
            llm_log = run_llm_with_checks(args.ids, probes_by_id, provider_args)
            log_payload["llm_runs"] = llm_log

    if args.save and (args.as_json or args.with_llm or args.client_chat):
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(log_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{Fore.GREEN}Saved run to {out}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
