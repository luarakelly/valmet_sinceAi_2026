"""AI Scan: open-vocabulary 2D detection on a viewport snapshot (secondary to 3D extraction)."""

from typing import Any, Dict, List

from business.errors import PayloadTooLargeError, ServiceUnavailableError, UnsupportedMediaTypeError
from business.interfaces.ports.outbound import VisualDetector


class VisionService:
    def __init__(self, detector: VisualDetector):
        self._detector = detector

    def analyze(self, image_bytes: bytes, content_type: str, classes: str, confidence: float) -> Dict[str, Any]:
        if not content_type or not content_type.startswith("image/"):
            raise UnsupportedMediaTypeError("Image upload required.")
        requested: List[str] = [c.strip() for c in classes.split(",") if c.strip()]
        try:
            return self._detector.analyze(image_bytes, requested, confidence)
        except ValueError as error:
            raise PayloadTooLargeError(str(error)) from error
        except Exception as error:
            raise ServiceUnavailableError("YOLO-World analysis unavailable: {}".format(error)) from error
