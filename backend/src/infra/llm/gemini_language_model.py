"""LanguageModel adapter for Google Gemini (google-genai). Optional: None on any failure."""

import json
import logging
import os
from typing import Any

from business.interfaces.ports.outbound.language_model import LanguageModel

logger = logging.getLogger("ask_your_factory.llm.gemini")

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
REQUEST_TIMEOUT_MS = 30_000  # never hold a request thread for longer


class GeminiLanguageModel(LanguageModel):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        self._model = model or os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        self._client = None
        self.last_error: str | None = None  # why the last call returned None, for diagnostics

    @property
    def name(self) -> str:
        return self._model

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete_json(self, prompt: str, images: list[bytes] | None = None) -> dict[str, Any] | None:
        if not self.is_available:
            return None

        try:
            if self._client is None:
                from google import genai

                from google.genai import types

                self._client = genai.Client(api_key=self._api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))

            contents: Any = prompt
            if images:
                from google.genai import types

                contents = [types.Part.from_bytes(data=image, mime_type="image/jpeg") for image in images] + [prompt]

            response = self._client.models.generate_content(
                model=self._model,
                contents=contents,
                config={"response_mime_type": "application/json"},
            )
            self.last_error = None
            return json.loads(response.text)
        except Exception as error:
            self.last_error = "{}: {}".format(type(error).__name__, str(error)[:900])
            logger.warning("Gemini call failed (%s): %s", self._model, self.last_error)
            return None