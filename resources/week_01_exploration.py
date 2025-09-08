import json, sys, argparse, os, shlex, subprocess, textwrap, re
from pathlib import Path

# Farbige Ausgabe (plattformtauglich)
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
except Exception:  # Fallback, falls colorama nicht verfügbar ist
    class _NoColor:
        def __getattr__(self, _): return ""
    Fore = Style = _NoColor()

# Utils importierbar machen
THIS_DIR = Path(__file__).resolve().parent
UTILS_DIR = THIS_DIR / "utils"
sys.path.insert(0, str(UTILS_DIR))

from app_context import load_company, load_scenarios, load_controls
from scenario_recommender import recommend_scenarios, followup_questions

PROBES = THIS_DIR / "data" / "probes_w1.json"

# ----------------------------------------------------------------------
# Lokale LLM Provider (ohne API Keys)
# ----------------------------------------------------------------------
class LLMProvider:
    def generate(self, system: str, user: str) -> str:
        raise NotImplementedError

class OllamaProvider(LLMProvider):
    """Nur Ollama-CLI über subprocess; Prompt via STDIN (kein -p Flag)."""
    def __init__(self, model: str = None):
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1")

    def generate(self, system: str, user: str) -> str:
        prompt = f"System:\n{system}\n\nUser:\n{user}"
        cmd = ["ollama", "run", self.model]
        out = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        if out.returncode != 0:
            raise RuntimeError(f"ollama CLI error: {out.stderr.strip()}")
        return out.stdout

class CmdProvider(LLMProvider):
    """
    Generischer Provider für lokale CLIs.
    Erfordert Umgebungsvariable LLM_CMD, z.B.:
      export LLM_CMD='llamafile --model my.gguf --prompt "{SYSTEM}\n\n{USER}"'
    """
    def __init__(self):
        self.cmd_template = os.getenv("LLM_CMD", "").strip()
        if not self.cmd_template:
            raise RuntimeError("LLM_CMD nicht gesetzt. Beispiel: export LLM_CMD='llamafile ... \"{SYSTEM}\\n\\n{USER}\"'")

    def generate(self, system: str, user: str) -> str:
        cmd_str = self.cmd_template.replace("{SYSTEM}", escape_for_shell(system)).replace("{USER}", escape_for_shell(user))
        cmd = shlex.split(cmd_str)
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if out.returncode != 0:
            raise RuntimeError(f"LLM_CMD error: {out.stderr.strip()}")
        return out.stdout

def escape_for_shell(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s

def get_provider():
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "ollama":
        return OllamaProvider()
    if provider == "cmd":
        return CmdProvider()
    return None

# ----------------------------------------------------------------------
# Prompts
# ----------------------------------------------------------------------
def build_system_prompt():
    return (
        "Du bist ein Security Risk Advisor. Antworte ausschließlich auf Basis der gelieferten JSONs. "
        "Erfinde keine neuen Szenarien/Controls/Framework-Refs. "
        "Wenn Information fehlt, fordere gezielt Evidenz an. "
        "Antworte präzise, in sauberem Markdown und mit kurzen, nachvollziehbaren Begründungen."
    )

def build_user_prompt(company, scenarios, controls):
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
    1) Empfiehl Top-3 Szenarien für die Firma.
    2) Für jedes Szenario: kurze Begründung, Controls (nur aus CONTROLS_JSON), Framework-Refs (nur aus SCENARIOS_JSON/CONTROLS_JSON).
    3) Gib 3–5 präzise Folgefragen aus.
    Antworte in sauberem Markdown.
    """).strip()

def build_user_prompt_client_chat(company, scenarios, controls, user_question: str):
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
    - Liste 2–4 sinnvolle Folgefragen (Evidenz, Coverage, OT-Zonen, je nach Firma).
    Ausgabeformat: Markdown mit klaren Abschnitten (Erklärung, Relevanz für die Firma, Empfohlene Controls, Framework-Refs, Folgefragen).
    """).strip()

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

            # Always show metrics für Transparenz
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

# ----------------------------------------------------------------------
# Einfache LLM-Checks (inline, keine Extra-Datei)
# ----------------------------------------------------------------------
_SCENARIOS_KB = None
_CONTROLS_KB = None

def _kb_sets():
    global _SCENARIOS_KB, _CONTROLS_KB
    if _SCENARIOS_KB is None or _CONTROLS_KB is None:
        _SCENARIOS_KB = {s["name"] for s in load_scenarios()}
        _CONTROLS_KB  = {c["name"] for c in load_controls().values()}
    return _SCENARIOS_KB, _CONTROLS_KB

def _extract_list_items(md: str):
    # fängt Bullet- oder nummerierte Listenzeilen
    return re.findall(r"^(?:\s*[-*]\s+|\s*\d+\.\s+)(.+)$", md, re.MULTILINE)

def _first_k_scenarios_from_text(md: str, k: int = 3):
    scn_kb, _ = _kb_sets()
    found_order = []
    for line in _extract_list_items(md):
        name = line.strip()
        # Exakte Übereinstimmung gegen KB bevorzugen
        if name in scn_kb and name not in found_order:
            found_order.append(name)
        else:
            # Locker: Teil vor Klammern/Trenner
            base = re.split(r"[\(\-–:]", name, maxsplit=1)[0].strip()
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
    for kb in ctrl_kb:
        if re.search(re.escape(kb), md, re.IGNORECASE):
            mentioned.add(kb)
    off_hits = re.findall(r"\bctl-[a-z0-9\-]+\b", md, re.IGNORECASE)
    if off_hits:
        # Wenn nur unbekannte IDs erscheinen und keine bekannten Namen, werten wir als False.
        return len(mentioned) > 0
    return True

def _mentions_eal_reasoning(md: str) -> bool:
    # Hinweise auf p×Umsatz×Impact, EAL_before, etc.
    return bool(re.search(r"(EAL|p\s*[×x*]\s*Umsatz\s*[×x*]\s*Impact|p\s*×|Umsatz\s*×)", md, re.IGNORECASE))

def check_llm_answer(md: str, expected_top3: list) -> dict:
    scn_kb, _ = _kb_sets()
    extracted_top = _first_k_scenarios_from_text(md, 3)
    only_kb_scenarios = all(name in scn_kb for name in extracted_top) and len(extracted_top) == 3
    controls_ok = _controls_only_from_kb(md)
    eal_ok = _mentions_eal_reasoning(md)

    # Gradiert
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

# ----------------------------------------------------------------------
# LLM-Smoketest + integrierte Checks
# ----------------------------------------------------------------------
def run_llm_smoketest_with_checks(company_ids, probes_by_id):
    provider = get_provider()
    if not provider:
        msg = "LLM_PROVIDER nicht (korrekt) gesetzt. Smoketest übersprungen. (Nutze 'ollama' oder 'cmd')"
        print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}")
        return []

    scenarios = load_scenarios()
    controls  = load_controls()
    out = []

    for cid in company_ids:
        company = load_company(cid)
        system = build_system_prompt()
        user   = build_user_prompt(company, scenarios, controls)

        banner = f"=== LLM SMOKETEST for {cid} ({company['name']}) ==="
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

# ----------------------------------------------------------------------
# Client-Chat (freier Prompt im Firmenkontext)
# ----------------------------------------------------------------------
def run_client_chat(company_id: str, user_question: str):
    # Args Validation
    if not company_id or not isinstance(company_id, str):
        raise ValueError("Ungültige Company-ID.")
    user_question = (user_question or "").strip()
    if not user_question:
        raise ValueError("Die freie Frage (--ask) darf nicht leer sein.")
    if len(user_question) > 4000:
        raise ValueError("Die freie Frage ist zu lang (>4000 Zeichen). Bitte kürzen.")

    provider = get_provider()
    if not provider:
        raise RuntimeError("LLM_PROVIDER nicht (korrekt) gesetzt. Setze z. B. LLM_PROVIDER=ollama.")

    company = load_company(company_id)  # wirf Fehler, falls unbekannt
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

# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", default=["c-001"], help="Company IDs")
    ap.add_argument("--as-json", action="store_true", help="Strukturierte JSON-Ausgabe der Baseline")
    ap.add_argument("--with-llm", action="store_true", help="LLM-SmokeTest mit integrierten Checks ausführen")
    ap.add_argument("--save", type=str, default="", help="Optionaler Pfad für JSON-Log (Baseline/LLM/Client-Chat)")
    ap.add_argument("--strict", action="store_true", help="Strikter Mengen-Gleichheitscheck statt gradiertem Matching")
    # Neuer Modus:
    ap.add_argument("--client-chat", type=str, default="", metavar="COMPANY_ID", help="Freier Prompt im Kontext einer Firma")
    ap.add_argument("--ask", type=str, default="", help="Freie Frage für --client-chat (in Anführungszeichen)")

    args = ap.parse_args()

    # Validierungslogik für Modi-Kombinationen
    client_chat_mode = bool(args.client_chat)
    if client_chat_mode and not args.ask:
        print(f"{Fore.RED}Für --client-chat ist --ask \"<Frage>\" erforderlich.{Style.RESET_ALL}")
        sys.exit(2)

    if not PROBES.exists() and not client_chat_mode:
        print(f"{Fore.RED}Missing probes file: {PROBES}{Style.RESET_ALL}")
        sys.exit(1)

    log_payload = {"baseline": None, "llm_runs": None, "client_chat": None}

    if client_chat_mode:
        try:
            cc = run_client_chat(args.client_chat, args.ask)
            log_payload["client_chat"] = cc
        except Exception as e:
            print(f"{Fore.RED}CLIENT-CHAT ERROR: {e}{Style.RESET_ALL}")
            sys.exit(3)
        # Client-Chat kann allein stehen; die restlichen Modi sind optional.
    else:
        probes = load_probes()
        probes_by_id = {p["company_id"]: p for p in probes}

        if args.as_json:
            baseline_out = [render_baseline_output(cid) for cid in args.ids]
            print(json.dumps(baseline_out, ensure_ascii=False, indent=2))
            log_payload["baseline"] = baseline_out
        else:
            run_baseline(args.ids, probes, strict=args.strict)

        if args.with_llm:
            llm_log = run_llm_smoketest_with_checks(args.ids, probes_by_id)
            log_payload["llm_runs"] = llm_log

    if args.save and (args.as_json or args.with_llm or client_chat_mode):
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(log_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{Fore.GREEN}Saved run to {args.save}{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
