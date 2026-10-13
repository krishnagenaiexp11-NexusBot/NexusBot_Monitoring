"""
providers/openrouter_provider.py
OpenRouter implementation of the BaseProvider interface.
"""
import json
import logging
from typing import Dict, Any
import requests
from providers.openai_provider import OpenAIProvider

logger = logging.getLogger("OpenRouterProvider")


class OpenRouterProvider(OpenAIProvider):
    """
    OpenRouter API client wrapper (uses OpenAI compatibility layer).
    """

    def test_connection(self) -> bool:
        if not self.base_url:
            self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        if not self.model:
            self.model = "anthropic/claude-3.5-sonnet:beta"
        if not self.api_key:
            return False
        return True

    def generate_briefing(self, structured_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.base_url:
            self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        if not self.model:
            self.model = "anthropic/claude-3.5-sonnet:beta"
        if not self.api_key:
            raise ValueError("OpenRouter API key is missing.")

        system_instr = self._get_system_instructions()
        prompt = f"""
{system_instr}

Return only a JSON object with exactly these keys:
- "executive_summary": one paragraph explaining the deterministic market decision.
- "key_opportunities": array of 2-3 concise opportunity strings.
- "key_risks": array of 2-3 concise risk strings.
- "timing_summary": timing viability from the supplied readiness/session fields.
- "deployment_context": why the selected strategy won and why others were penalized.

Do not add markdown fences or prose outside the JSON object.

--- RAW QUANTITATIVE DIAGNOSTICS CONTEXT ---
{json.dumps(structured_context, default=str)}
--------------------------------------------
"""

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "http://localhost:8502",
            "X-Title": "NexusBot V3",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instr},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        response = requests.post(self.base_url, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            raise Exception(f"OpenRouter HTTP {response.status_code}: {response.text}")

        res_json = response.json()
        choices = res_json.get("choices") or []
        if not choices:
            raise Exception(f"OpenRouter returned no choices: {res_json}")

        message = choices[0].get("message") or {}
        text = message.get("content") or choices[0].get("text") or ""
        if not text:
            raise Exception(f"OpenRouter returned empty content: {res_json}")

        meta = {
            "provider": "OpenRouter",
            "model": self.model,
            "prompt": prompt,
            "raw_response": text,
            "usage": res_json.get("usage", {}),
            "finish_reason": choices[0].get("finish_reason"),
            "id": res_json.get("id"),
        }

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                parsed["_ai_meta"] = meta
            return parsed
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(text[start:end + 1])
                    if isinstance(parsed, dict):
                        parsed["_ai_meta"] = meta
                    return parsed
                except json.JSONDecodeError:
                    pass
            logger.warning("OpenRouter returned non-JSON content; wrapping as executive summary.")
            return {
                "executive_summary": text.strip(),
                "key_opportunities": [],
                "key_risks": [],
                "timing_summary": "",
                "deployment_context": "",
                "_ai_meta": meta,
            }
