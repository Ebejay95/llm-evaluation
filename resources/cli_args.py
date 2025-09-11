import argparse

def parse_args():
    ap = argparse.ArgumentParser(prog="llm_runner")
    ap.add_argument("--provider", type=str, default="ollama", choices=["ollama"], help="LLM Provider")
    ap.add_argument("--model", type=str, default=None, help="z.B. 'mistral:7b', 'llama3.2:1b'")
    ap.add_argument("--ollama-url", type=str, default=None, help="z.B. http://ollama:11434")

    # EINZIG NEUER ARG: Single-Chat direkt ans Modell
    ap.add_argument("-chat", "--chat", type=str, default=None,
                    help="Einzelne Eingabe direkt ans Modell schicken")

    return ap.parse_args()

def provider_args_from(args):
    return {
        "provider_name": args.provider,
        "model": args.model,
        "ollama_url": args.ollama_url,
    }
