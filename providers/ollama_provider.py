"""
providers/ollama_provider.py
Ollama (Local LLM) implementation of the BaseProvider interface.
"""
import json
import requests
import logging
from typing import Dict, Any
from providers.base_provider import BaseProvider

logger = logging.getLogger("OllamaProvider")


class OllamaProvider(BaseProvider):
    """
    Local Ollama API client wrapper.
    """

    def test_connection(self) -> bool:
        url = self.base_url or "http://localhost:11434/api/tags"
        try:
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                return True
        except Exception as e:
            logger.warning(f"Ollama local connection test failed: {e}")
        return False

    def generate_briefing(self, structured_context: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = "http://localhost:11434/api/chat"
        if self.base_url:
            # If user provided base URL, ensure it maps to api/chat
            if not self.base_url.endswith("/api/chat") and not self.base_url.endswith("/api/chat/"):
                endpoint = self.base_url.rstrip("/") + "/api/chat"
            else:
                endpoint = self.base_url
                
        model_name = self.model or "llama3"
        
        system_instr = self._get_system_instructions()
        prompt = f"""
{system_instr}

Respond with a JSON object containing EXACTLY:
1. "executive_summary": A single paragraph decision overview of the current regime.
2. "key_opportunities": List of 2-3 opportunities (each starting with a color emoji, e.g. 🟢, and a bold title).
3. "key_risks": List of 2-3 risks (each starting with a color emoji, e.g. 🔴 or 🟡, and a bold title).
4. "timing_summary": Explanation of timing viability based on overlaps/liquidity.
5. "deployment_context": Details of tournament winner suitability or active barriers.

--- RAW QUANTITATIVE DIAGNOSTICS CONTEXT ---
{json.dumps(structured_context, default=str)}
--------------------------------------------
"""
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_instr},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {
                "temperature": self.temperature
            },
            "format": "json"
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=20)
            if response.status_code == 200:
                res_json = response.json()
                text = res_json["message"]["content"]
                return json.loads(text)
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise
