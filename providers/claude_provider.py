"""
providers/claude_provider.py
Claude (Anthropic) implementation of the BaseProvider interface.
"""
import json
import requests
import logging
from typing import Dict, Any
from providers.base_provider import BaseProvider

logger = logging.getLogger("ClaudeProvider")


class ClaudeProvider(BaseProvider):
    """
    Anthropic Claude API client wrapper.
    """

    def test_connection(self) -> bool:
        if not self.api_key:
            return False
        
        url = self.base_url or "https://api.anthropic.com/v1/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        model_name = self.model or "claude-3-5-sonnet-20241022"
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            if response.status_code == 200 or response.status_code == 201:
                return True
        except Exception as e:
            logger.warning(f"Claude connection test failed: {e}")
        return False

    def generate_briefing(self, structured_context: Dict[str, Any]) -> Dict[str, Any]:
        url = self.base_url or "https://api.anthropic.com/v1/messages"
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"
        }
        model_name = self.model or "claude-3-5-sonnet-20241022"
        
        system_instr = self._get_system_instructions()
        prompt = f"""
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
            "system": system_instr,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code in (200, 201):
                res_json = response.json()
                text = res_json["content"][0]["text"]
                # Clean up any surrounding markdown
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                return json.loads(text.strip())
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Claude generation failed: {e}")
            raise
