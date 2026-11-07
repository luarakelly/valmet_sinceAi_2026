"""LanguageModel adapter for Google Gemini (google-genai). Optional: None on any failure."""

import json
import logging
import os
from typing import Any, Dict, Optional

from business.interfaces.ports.outbound.language_model import LanguageModel

logger = logging.getLogger("ask_your_factory.llm.gemini")
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class GeminiLanguageModel(LanguageModel):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self._api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self._model = model or os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        self._client = None

    @property
    def name(self) -> str:
        return self._model

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        try:
            if self._client is None:
                from google import genai

                self._client = genai.Client(api_key=self._api_key)
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.2},
            )
            return json.loads(response.text)
        except Exception as exc:  # network, quota, bad JSON, missing package
            logger.warning("Gemini unavailable: %s", exc)
            return None
