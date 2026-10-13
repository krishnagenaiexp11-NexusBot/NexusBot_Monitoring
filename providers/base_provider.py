"""
providers/base_provider.py
Abstract base class defining the contract for AI narrative briefing providers in NexusBot V3.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseProvider(ABC):
    """
    Interface for modular AI providers.
    Ensures consistent inputs/outputs and dynamic configuration capability.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "")
        self.base_url = config.get("base_url", "")
        self.temperature = float(config.get("temperature", 0.2))
        self.max_tokens = int(config.get("max_tokens", 1000))

    @abstractmethod
    def test_connection(self) -> bool:
        """
        Validates connection/authentication to the AI provider.
        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def generate_briefing(self, structured_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes quantitative diagnostics context and returns structured insights briefing.
        """
        pass

    def _get_system_instructions(self) -> str:
        return (
            "You are NexusBot's Execution Analyst Assistant. Only interpret supplied engine outputs. "
            "Do not fabricate indicators, signals, or generic market predictions. Ground every sentence in actual fields "
            "from the provided raw JSON context. Explicitly mention specific values. State which of the 19 modular engines "
            "inside the intelligence pipeline returned WARNING, FAIL, or BLOCKED status. Do not invent details. "
            "Respond ONLY with a JSON object matching the requested schema. No markdown formatting codeblocks."
        )
