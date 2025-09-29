#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

# === Farben ============================================================
try:
    from colorama import init as _colorama_init, Fore, Style
    _colorama_init(autoreset=True)
except Exception:
    class _NoColor:
        def __getattr__(self, _): return ""
    Fore = Style = _NoColor()

THEME = {
    "prompt": Fore.CYAN,      
    "user": Fore.CYAN,        
    "assistant": Fore.GREEN,  
    "info": Fore.YELLOW,      
    "error": Fore.RED,        
    "reset": Style.RESET_ALL,
}

def cprint(text: str, color: str = ""):
    print(f"{color}{text}{THEME['reset']}")

# ======================================================================

try:
    from llm_router import prompt, resolve_model  # dein Router: Ollama + OpenRouter
except ImportError:
    print("Fehlt: llm_router.py muss im Import-Pfad liegen.", file=sys.stderr)
    sys.exit(1)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Minimal Chat (Ollama/OpenRouter) mit optionalem Kontext")
    ap.add_argument("--model", type=str, default="ollama/llama3.2:1b",
                    help="Model-Spec: 'ollama/<id>' | 'openrouter/<id>' | '<ollama_id>'")
    ap.add_argument("--ollama-url", type=str, default=None,
                    help="z.B. http://localhost:11434 (überschreibt OLLAMA_BASE_URL)")
    ap.add_argument("--system", type=str, default="You are a lyrics librarian for songs texts. anwer only the lyrics as text. nothing more. strip away thurder. information of song and song structure",
                    help="Systemprompt")
    ap.add_argument("--stateless", action="store_true",
                    help="Jede Eingabe als neuer Chat (kein Verlauf).")
    ap.add_argument("--save", type=str, default=None,
                    help="Optional: Transcript automatisch als JSONL mitloggen (Pfad).")
    return ap.parse_args()


def save_jsonl(path: str, obj: Dict[str, Any]) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception as e:
        cprint(f"[warn] Konnte nicht schreiben: {e}", THEME["error"])


def as_model_string(ms) -> str:
    prov = getattr(ms, "provider", None)
    mid = getattr(ms, "model", None)
    if prov and mid:
        return f"{prov}/{mid}"
    return str(ms)


def main():
    args = parse_args()

    # argparse erzeugt kein Attribut mit Bindestrich; kompatibel halten:
    if not hasattr(args, "ollama_url") and hasattr(args, "ollama-url"):
        setattr(args, "ollama_url", getattr(args, "ollama-url"))

    if args.ollama_url:
        os.environ["OLLAMA_BASE_URL"] = args.ollama_url

    try:
        model_spec = resolve_model(args.model)  # akzeptiert auch bare IDs
    except Exception as e:
        cprint(f"Ungültiges --model: {e}", THEME["error"])
        sys.exit(1)

    system_prompt = args.system.strip()
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]

    cprint(f"Model: {as_model_string(model_spec)}  |  stateless={args.stateless}", THEME["info"])
    cprint("Befehle: /new, /sys <text>, /model <spec>, /save <pfad.jsonl>, /exit", THEME["info"])
    if args.save:
        cprint(f"[log] JSONL: {args.save}", THEME["info"])

    while True:
        try:
            # farbiger Prompt
            user_in = input(f"{THEME['prompt']}> {THEME['reset']}").strip()
        except (EOFError, KeyboardInterrupt):
            cprint("\nBye.", THEME["info"])
            break

        if not user_in:
            continue

        # Slash-Commands
        if user_in.startswith("/"):
            parts = user_in.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd == "/exit":
                cprint("Bye.", THEME["info"])
                break

            elif cmd == "/new":
                messages = [{"role": "system", "content": system_prompt}]
                cprint("[ok] Verlauf geleert.", THEME["info"])
                continue

            elif cmd == "/sys":
                if arg:
                    system_prompt = arg
                    messages = [m for m in messages if m.get("role") != "system"] + [{"role": "system", "content": system_prompt}]
                    cprint("[ok] Systemprompt gesetzt.", THEME["info"])
                cprint(f"[sys] {system_prompt}", THEME["info"])
                continue

            elif cmd == "/model":
                if not arg:
                    cprint(f"[info] aktuell: {as_model_string(model_spec)}", THEME["info"])
                else:
                    try:
                        model_spec = resolve_model(arg)
                        cprint(f"[ok] Modell gewechselt zu: {as_model_string(model_spec)}", THEME["info"])
                    except Exception as e:
                        cprint(f"[err] Ungültiges Modell: {e}", THEME["error"])
                continue

            elif cmd == "/save":
                if arg:
                    args.save = arg
                    cprint(f"[ok] Log-Pfad: {args.save}", THEME["info"])
                else:
                    cprint(f"[info] Log-Pfad: {args.save or '(aus)'}", THEME["info"])
                continue

            else:
                cprint("[info] Unbekannter Befehl. Verfügbar: /new, /sys, /model, /save, /exit", THEME["info"])
                continue

        # Optional: User-Frage echoen (farbig), falls gewünscht:
        # cprint(user_in, THEME["user"])

        # Anfrage senden
        if args.stateless:
            msgs = [{"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_in}]
        else:
            messages.append({"role": "user", "content": user_in})
            msgs = messages

        try:
            answer = prompt(model_spec, msgs, temperature=0.2, max_tokens=1024)
        except Exception as e:
            cprint(f"[err] Request fehlgeschlagen: {e}", THEME["error"])
            if not args.stateless and messages and messages[-1].get("role") == "user":
                messages.pop()
            continue

        if not args.stateless:
            messages.append({"role": "assistant", "content": answer})

        # Antwort farbig ausgeben
        cprint(answer, THEME["assistant"])

        if args.save:
            save_jsonl(args.save, {
                "ts": datetime.utcnow().isoformat(),
                "model": as_model_string(model_spec),
                "stateless": args.stateless,
                "system": system_prompt,
                "user": user_in,
                "assistant": answer,
            })


if __name__ == "__main__":
    main()
