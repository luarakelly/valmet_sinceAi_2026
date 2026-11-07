from typing import Any, Dict

from fastapi import Depends, File, Form, UploadFile

from api.container import Container, get_container
from api.controllers.errors import http_errors


async def analyze_viewport_view(
    file: UploadFile = File(...),
    classes: str = Form(default=""),
    confidence: float = Form(default=0.15, ge=0.01, le=0.95),
    app: Container = Depends(get_container),
) -> Dict[str, Any]:
    """Open-vocabulary YOLO-World detection on a viewport snapshot (2D, secondary to 3D extraction)."""
    image_bytes = await file.read()
    with http_errors():
        return app.vision.analyze(image_bytes, file.content_type or "", classes, confidence)
