"""Labeling capture run: which cameras to render, and where the rendered views are kept."""

import base64
import binascii
from typing import Any, Dict, List

from business.errors import InvalidRequestError
from business.interfaces.ports.outbound import SceneEngine, ViewStore


class LabelingService:
    def __init__(self, scene: SceneEngine, views: ViewStore):
        self._scene = scene
        self._views = views

    def plan(self) -> Dict[str, Any]:
        return {"views": self._scene.labeling_views(), "captured": self._views.view_ids()}

    def save_view(self, view_id: str, image_base64: str, view_projection: List[float], width: int, height: int) -> Dict[str, Any]:
        try:
            jpeg = base64.b64decode(image_base64, validate=True)
        except (binascii.Error, ValueError):
            raise InvalidRequestError("image_base64 is not valid base64.")
        self._views.save(view_id, jpeg, {"view_id": view_id, "view_projection": view_projection, "width": width, "height": height})
        return {"view_id": view_id, "captured_count": len(self._views.view_ids())}
