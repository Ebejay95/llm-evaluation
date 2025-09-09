from typing import Optional
import os

class LLMProvider:
    def generate(self, system: str, user: str) -> str:
        raise NotImplementedError

class OllamaProvider(LLMProvider):
    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        from ollama import Client as _OllamaClient
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:1b")
        self.host  = host or os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_HOST") or "http://ollama:11434"
        self._client = _OllamaClient(host=self.host)

    def generate(self, system: str, user: str) -> str:
        prompt = f"System:\n{system}\n\nUser:\n{user}"
        resp = self._client.generate(model=self.model, prompt=prompt)
        return resp.get("response", "")
