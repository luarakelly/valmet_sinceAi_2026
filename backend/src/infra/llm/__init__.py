"""LLM adapters. `build_language_model()` picks one from the environment (or none)."""

import os
from typing import Optional

from business.interfaces.ports.outbound.language_model import LanguageModel

from .claude_language_model import ClaudeLanguageModel
from .gemini_language_model import GeminiLanguageModel


def build_language_model() -> Optional[LanguageModel]:
    """LLM_PROVIDER=gemini|claude|none; default: Gemini if GEMINI_API_KEY, else Claude if ANTHROPIC_API_KEY."""
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider == "none":
        return None
    if provider == "claude" or (not provider and not os.getenv("GEMINI_API_KEY") and os.getenv("ANTHROPIC_API_KEY")):
        model = ClaudeLanguageModel()
    else:
        model = GeminiLanguageModel()
    return model if model.is_available else None


__all__ = ["ClaudeLanguageModel", "GeminiLanguageModel", "build_language_model"]
