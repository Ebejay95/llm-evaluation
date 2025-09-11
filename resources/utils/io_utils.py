--- a/resources/utils/llm_provider.py
+++ b/resources/utils/llm_provider.py
@@ -1,21 +1,47 @@
 from typing import Optional
 import os
 
 class LLMProvider:
     def generate(self, system: str, user: str) -> str:
         raise NotImplementedError
 
 class OllamaProvider(LLMProvider):
     def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
-        from ollama import Client as _OllamaClient
+        from ollama import Client as _OllamaClient
         self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:1b")
         self.host  = host or os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_HOST") or "http://ollama:11434"
         self._client = _OllamaClient(host=self.host)
+        # Async-Client wird lazy initialisiert (s.u.)
+        self._aclient = None
 
     def generate(self, system: str, user: str) -> str:
         prompt = f"System:\n{system}\n\nUser:\n{user}"
         resp = self._client.generate(model=self.model, prompt=prompt)
         return resp.get("response", "")
+
+    async def agenerate(self, system: str, user: str) -> str:
+        """
+        Asynchrone Variante. Nutzt ollama.AsyncClient, falls vorhanden.
+        Fallback: führt die synchrone generate()-Methode in einem Thread aus.
+        """
+        try:
+            from ollama import AsyncClient as _AsyncOllamaClient
+        except Exception:
+            # Fallback: Sync in Thread, damit Aufrufer trotzdem parallelisieren kann
+            import asyncio
+            loop = asyncio.get_running_loop()
+            return await loop.run_in_executor(None, lambda: self.generate(system, user))
+
+        if self._aclient is None:
+            self._aclient = _AsyncOllamaClient(host=self.host)
+
+        prompt = f"System:\n{system}\n\nUser:\n{user}"
+        resp = await self._aclient.generate(model=self.model, prompt=prompt)
+        return resp.get("response", "")
