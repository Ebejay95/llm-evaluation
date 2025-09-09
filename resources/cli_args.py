import argparse

def parse_args():
    ap = argparse.ArgumentParser(prog="week_01_exploration")
    ap.add_argument("--ids", nargs="+", default=["c-001"], help="Company IDs")
    ap.add_argument("--as-json", action="store_true", help="Baseline als JSON ausgeben")
    ap.add_argument("--with-llm", action="store_true", help="LLM + Checks ausführen")
    ap.add_argument("--save", type=str, default="", help="Optionaler JSON-Log-Pfad")
    ap.add_argument("--strict", action="store_true", help="Strenger Mengenvergleich für Baseline")

    ap.add_argument("--client-chat", type=str, default="", metavar="COMPANY_ID", help="Freie Frage im Firmenkontext")
    ap.add_argument("--ask", type=str, default="", help="Freie Nutzerfrage für --client-chat")

    ap.add_argument("--provider", type=str, default="ollama", choices=["ollama", "cmd"], help="LLM Provider")
    ap.add_argument("--model", type=str, default=None, help="z.B. 'mistral:7b', 'llama3.2:1b'")
    ap.add_argument("--ollama-url", type=str, default=None, help="z.B. http://ollama:11434")
    ap.add_argument("--llm-cmd", type=str, default=None, help="nur für provider=cmd")
    return ap.parse_args()

def provider_args_from(args):
    return {
        "provider_name": args.provider,
        "model": args.model,
        "ollama_url": args.ollama_url,
        "llm_cmd": args.llm_cmd,
    }