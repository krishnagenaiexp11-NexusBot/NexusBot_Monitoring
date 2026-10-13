"""
providers/lmstudio_provider.py
LM Studio (Local OpenAI compatibility) implementation of the BaseProvider interface.
"""
from typing import Dict, Any
from providers.openai_provider import OpenAIProvider


class LMStudioProvider(OpenAIProvider):
    """
    LM Studio local API wrapper (uses OpenAI compatibility layer).
    """

    def test_connection(self) -> bool:
        if not self.base_url:
            self.base_url = "http://localhost:1234/v1/chat/completions"
        # LM Studio usually ignores the API key but it must be populated to pass OpenAI validation
        if not self.api_key:
            self.api_key = "lm-studio-local"
        return super().test_connection()

    def generate_briefing(self, structured_context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.base_url:
            self.base_url = "http://localhost:1234/v1/chat/completions"
        if not self.api_key:
            self.api_key = "lm-studio-local"
        return super().generate_briefing(structured_context)
