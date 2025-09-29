# resources/utils/llm_provider.py
from typing import Optional
import os
from ollama import Client as _OllamaClient

class LLMProvider:
    def generate(self, system: str, user: str, **opts) -> str:
        raise NotImplementedError

class OllamaProvider(LLMProvider):
    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:1b")
        self.host  = host or os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_HOST") or "http://ollama:11434"
        self._client = _OllamaClient(host=self.host)

    def generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        top_p: float | None = None,
        top_k: int | None = None,
        seed: int | None = None,
        force_json: bool = False,  # NEU
    ) -> str:
        prompt = f"System:\n{system}\n\nUser:\n{user}"
        options = {}
        if temperature is not None: options["temperature"] = float(temperature)
        if top_p is not None:      options["top_p"] = float(top_p)
        if top_k is not None:      options["top_k"] = int(top_k)
        if seed is not None:       options["seed"] = int(seed)

        resp = self._client.generate(
            model=self.model,
            prompt=prompt,
            options=options or None,
            format="json" if force_json else None,  # NEU
        )
        out = resp.get("response", "").strip()

        # Hilfreich: falls das Modell dennoch Text um das JSON packt → JSON-Teil ausschneiden
        if force_json and "{" in out and "}" in out:
            try:
                start = out.find("{")
                end = out.rfind("}")
                if start != -1 and end != -1:
                    out = out[start:end+1]
            except Exception:
                pass
        return out

    def spawn(self) -> "OllamaProvider":
        return OllamaProvider(model=self.model, host=self.host)
