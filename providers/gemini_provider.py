"""
providers/gemini_provider.py
Google Gemini implementation of the BaseProvider interface.
"""
import json
import requests
import logging
from typing import Dict, Any
from providers.base_provider import BaseProvider

logger = logging.getLogger("GeminiProvider")


class GeminiProvider(BaseProvider):
    """
    Google Gemini REST API client wrapper.
    """

    def test_connection(self) -> bool:
        if not self.api_key:
            return False
        
        # Fast connection test by executing a minimal token query
        model_name = self.model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": "say OK"}]}],
            "generationConfig": {"maxOutputTokens": 5}
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            if response.status_code == 200:
                return True
        except Exception as e:
            logger.warning(f"Gemini connection test failed: {e}")
        return False

    def generate_briefing(self, structured_context: Dict[str, Any]) -> Dict[str, Any]:
        model_name = self.model or "gemini-1.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        
        system_instr = self._get_system_instructions()
        prompt = f"""
System Instructions: {system_instr}

--- RAW QUANTITATIVE DIAGNOSTICS CONTEXT ---
{json.dumps(structured_context, indent=2, default=str)}
--------------------------------------------

Respond with a JSON object containing EXACTLY:
1. "executive_summary": A single paragraph decision overview of the current regime.
2. "key_opportunities": List of 2-3opportunities (each starting with a color emoji, e.g. 🟢, and a bold title).
3. "key_risks": List of 2-3 risks (each starting with a color emoji, e.g. 🔴 or 🟡, and a bold title).
4. "timing_summary": Explanation of timing viability based on overlaps/liquidity.
5. "deployment_context": Details of tournament winner suitability or active barriers.
"""
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "executive_summary": {"type": "STRING"},
                        "key_opportunities": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "key_risks": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "timing_summary": {"type": "STRING"},
                        "deployment_context": {"type": "STRING"}
                    },
                    "required": ["executive_summary", "key_opportunities", "key_risks", "timing_summary", "deployment_context"]
                }
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                res_json = response.json()
                text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text)
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            raise
