from typing import Any, Dict, List, Optional, Protocol


class LanguageModel(Protocol):
    """Optional LLM that answers with JSON. Return None when unavailable or on error."""

    @property
    def name(self) -> str:
        ...

    @property
    def is_available(self) -> bool:
        ...

    def complete_json(self, prompt: str, images: Optional[List[bytes]] = None) -> Optional[Dict[str, Any]]:
        """images: optional JPEG bytes shown to the model with the prompt."""
        ...
