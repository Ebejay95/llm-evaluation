# llm_router.py
# Unified routing for Ollama (local) and OpenRouter (hosted) chat completions.
# - Provider selection by model string:
#     * "ollama/<model>"   -> Ollama (explicit)
#     * "openrouter/<id>"  -> OpenRouter (explicit)
#     * "<model>"          -> defaults to Ollama for backward compatibility
# - Single entrypoint: prompt(model, messages, **opts) -> str
#
# ENV:
#   OPENROUTER_API_KEY   (required for openrouter/*)
#   OPENROUTER_BASE_URL  (optional, default: https://openrouter.ai/api/v1)
#   OPENROUTER_REFERER   (optional, helpful per docs)
#   OPENROUTER_TITLE     (optional, helpful per docs)
#   OLLAMA_BASE_URL      (optional, default: http://localhost:11434)
#
# Usage example:
#   from llm_router import prompt, resolve_model, parse_models_arg
#   text = prompt("openrouter/gpt-4o-mini", [{"role":"user","content":"Hi!"}])
#   text2 = prompt("llama3.2:1b", [{"role":"user","content":"Hi!"}])  # defaults to Ollama
#
from __future__ import annotations

import os
import time
import json
import typing as t
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class ModelSpec:
    provider: str   # "ollama" | "openrouter"
    model: str      # provider-native model id


def _trim(s: str) -> str:
    return s.strip() if isinstance(s, str) else s


def resolve_model(spec: str, *, default_provider: str = "ollama") -> ModelSpec:
    """
    Resolve a model string into (provider, model).

    Accepted forms:
      - "openrouter/<model_id>"  -> provider=openrouter, model=<model_id>
      - "ollama/<model_id>"      -> provider=ollama,     model=<model_id>
      - "<legacy_ollama_id>"     -> provider=ollama (default), model=<legacy_ollama_id>
    """
    s = _trim(spec)
    if not s:
        raise ValueError("Empty model spec")

    if s.startswith("openrouter/"):
        return ModelSpec("openrouter", s.split("/", 1)[1])
    if s.startswith("ollama/"):
        return ModelSpec("ollama", s.split("/", 1)[1])

    # Backward compatibility: bare ids are treated as Ollama models
    return ModelSpec(default_provider, s)


def parse_models_arg(arg: str) -> list[ModelSpec]:
    """
    Turn CLI arg like 'llama3.2:1b,qwen2:0.5b,openrouter/gpt-4o-mini'
    into a list of ModelSpec.
    """
    if not arg:
        return []
    parts = [p for p in (x.strip() for x in arg.split(",")) if p]
    return [resolve_model(p) for p in parts]


# ---------- Provider Clients ----------

class LLMClient:
    def __init__(self, spec: ModelSpec):
        self.spec = spec

    def chat(
        self,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs,
    ) -> str:
        raise NotImplementedError


class OllamaClient(LLMClient):
    """
    Minimal Ollama chat client (non-stream) compatible with:
    POST {OLLAMA_BASE_URL}/api/chat
    body: {"model": "...", "messages": [...], "stream": false, ...}
    """
    def __init__(self, spec: ModelSpec):
        super().__init__(spec)
        self.base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")

    def chat(self, messages: list[dict], temperature=None, max_tokens=None, **kwargs) -> str:
        url = f"{self.base}/api/chat"
        payload = {
            "model": self.spec.model,
            "messages": messages,
            "stream": False,
        }
        # Ollama optionally accepts "options": {"temperature": ...}
        if temperature is not None or max_tokens is not None:
            payload["options"] = {}
            if temperature is not None:
                payload["options"]["temperature"] = float(temperature)
            if max_tokens is not None:
                payload["options"]["num_predict"] = int(max_tokens)

        # Merge any raw extra options, if provided
        extras = kwargs.get("ollama_options")
        if isinstance(extras, dict):
            payload.setdefault("options", {}).update(extras)

        r = requests.post(url, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        # Typical response: {"message":{"role":"assistant","content":"..."}, ...}
        msg = (data or {}).get("message") or {}
        content = msg.get("content")
        if not content:
            # Some Ollama builds structure tokens under "messages" (rare), fallback
            content = (data or {}).get("response") or ""
        return content


class OpenRouterClient(LLMClient):
    """
    Minimal OpenRouter chat client (non-stream) per:
    POST {OPENROUTER_BASE_URL}/chat/completions
    headers:
      Authorization: Bearer <OPENROUTER_API_KEY>
      HTTP-Referer: <optional>
      X-Title: <optional>
    body:
      {"model": "<id>", "messages": [...], "temperature": ..., "max_tokens": ...}
    """
    def __init__(self, spec: ModelSpec):
        super().__init__(spec)
        self.base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is missing (required for openrouter/* models).")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # Optional but recommended
        if os.environ.get("OPENROUTER_REFERER"):
            self.headers["HTTP-Referer"] = os.environ["OPENROUTER_REFERER"]
        if os.environ.get("OPENROUTER_TITLE"):
            self.headers["X-Title"] = os.environ["OPENROUTER_TITLE"]

    def chat(self, messages: list[dict], temperature=None, max_tokens=None, **kwargs) -> str:
        url = f"{self.base}/chat/completions"
        payload = {
            "model": self.spec.model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        # Allow raw OpenRouter extras (e.g., route preferences)
        extras = kwargs.get("openrouter_options")
        if isinstance(extras, dict):
            payload.update(extras)

        # Simple retry on 429/5xx
        backoff = 1.0
        for attempt in range(5):
            r = requests.post(url, headers=self.headers, data=json.dumps(payload), timeout=120)
            if r.status_code in (429, 500, 502, 503, 504):
                if attempt == 4:
                    r.raise_for_status()
                time.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
                continue
            r.raise_for_status()
            break

        data = r.json()
        # Typical response: {"choices":[{"message":{"role":"assistant","content":"..."}}], ...}
        choices = (data or {}).get("choices") or []
        if not choices:
            return ""
        content = ((choices[0] or {}).get("message") or {}).get("content") or ""
        return content


# ---------- Routing & single entrypoint ----------

def get_client(model: str | ModelSpec) -> LLMClient:
    spec = model if isinstance(model, ModelSpec) else resolve_model(model)
    if spec.provider == "ollama":
        return OllamaClient(spec)
    if spec.provider == "openrouter":
        return OpenRouterClient(spec)
    raise ValueError(f"Unknown provider: {spec.provider}")


def prompt(
    model: str | ModelSpec,
    messages: list[dict],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs,
) -> str:
    """
    Unified completion call for both providers.

    Args:
      model: "openrouter/<id>", "ollama/<id>", or bare "<ollama_id>"
      messages: list of {"role": "system"|"user"|"assistant", "content": str}
      temperature, max_tokens: forwarded to the provider
      kwargs:
        - openrouter_options: dict (only for OpenRouter)
        - ollama_options: dict (only for Ollama)

    Returns:
      assistant text (str)
    """
    client = get_client(model)
    return client.chat(messages, temperature=temperature, max_tokens=max_tokens, **kwargs)
