"""
providers/openai_provider.py
OpenAI implementation of the BaseProvider interface.
"""
import json
import requests
import logging
from typing import Dict, Any
from providers.base_provider import BaseProvider

logger = logging.getLogger("OpenAIProvider")


class OpenAIProvider(BaseProvider):
    """
    OpenAI Chat Completion API client wrapper.
    """

    def test_connection(self) -> bool:
        if not self.api_key:
            return False
        
        url = self.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        model_name = self.model or "gpt-4o-mini"
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            if response.status_code == 200:
                return True
        except Exception as e:
            logger.warning(f"OpenAI connection test failed: {e}")
        return False

    def generate_briefing(self, structured_context: Dict[str, Any]) -> Dict[str, Any]:
        url = self.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        model_name = self.model or "gpt-4o-mini"
        
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
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"}
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                res_json = response.json()
                text = res_json["choices"][0]["message"]["content"]
                return json.loads(text)
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"OpenAI generation failed: {e}")
            raise
