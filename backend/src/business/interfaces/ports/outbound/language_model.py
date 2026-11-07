from typing import Any, Dict, Optional, Protocol


class LanguageModel(Protocol):
    """Optional LLM that answers with JSON. Return None when unavailable or on error."""

    @property
    def name(self) -> str:
        ...

    @property
    def is_available(self) -> bool:
        ...

    def complete_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        ...
