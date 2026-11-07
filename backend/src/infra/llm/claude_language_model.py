"""LanguageModel adapter for the Claude Messages API (stdlib HTTP). Optional: None on any failure.

Env: ANTHROPIC_API_KEY, ANTHROPIC_MODEL (default claude-sonnet-5-5), ANTHROPIC_VERSION (default 2023-06-01).
"""

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from business.interfaces.ports.outbound.language_model import LanguageModel

logger = logging.getLogger("ask_your_factory.llm.claude")
API_URL = "https://api.anthropic.com/v1/messages"


class ClaudeLanguageModel(LanguageModel):
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, timeout_s: float = 30.0):
        self._api_key = api_key if api_key is not None else os.getenv("ANTHROPIC_API_KEY", "")
        self._model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        self._version = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
        self._timeout = timeout_s

    @property
    def name(self) -> str:
        return self._model

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def complete_json(self, prompt: str, images: Optional[List[bytes]] = None) -> Optional[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(image).decode("ascii")}}
            for image in (images or [])
        ]
        blocks.append({"type": "text", "text": prompt + "\nRespond with the JSON object only."})
        body = json.dumps({
            "model": self._model,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": blocks}],
        }).encode("utf-8")
        request = urllib.request.Request(API_URL, data=body, method="POST", headers={
            "content-type": "application/json", "x-api-key": self._api_key, "anthropic-version": self._version,
        })
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = "".join(block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text")
            match = re.search(r"\{.*\}", text, re.S)
            return json.loads(match.group(0)) if match else None
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            logger.warning("Claude unavailable: %s", exc)
            return None
