"""VisualDetector adapter: lazy YOLO-World inference on images captured from the 3D viewer.

Weights: $YOLO_WORLD_MODEL, else data/weights/yolov8x-worldv2.pt if present, else the model name
(ultralytics downloads it on first use). Weights are not tracked in git.
"""

from io import BytesIO
from threading import Lock
from typing import Any, Dict, List, Optional
import os

from PIL import Image


# Descriptive phrases beat bare nouns for open-vocabulary detection of the pack's asset classes.
DEFAULT_CLASSES = [
    "industrial valve body",
    "pneumatic valve actuator",
    "circular manual handwheel",
    "pipe flange joint",
    "pipe elbow",
    "insulated steam pipe",
    "centrifugal water pump",
    "electric motor with cooling fins",
    "round pressure gauge dial",
    "pressure transmitter",
    "small vibration sensor on a machine casing",
]
from business.interfaces.ports.outbound.visual_detector import VisualDetector
from infra.paths import WEIGHTS_DIR

_LOCAL_WEIGHTS = WEIGHTS_DIR / "yolov8x-worldv2.pt"
MODEL_NAME = os.getenv("YOLO_WORLD_MODEL") or (str(_LOCAL_WEIGHTS) if _LOCAL_WEIGHTS.exists() else "yolov8x-worldv2.pt")
MAX_IMAGE_BYTES = 8 * 1024 * 1024

_model = None
_model_lock = Lock()


def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from ultralytics import YOLOWorld

                _model = YOLOWorld(MODEL_NAME)
    return _model


def _clean_classes(classes: List[str] | None) -> List[str]:
    requested = classes or DEFAULT_CLASSES
    cleaned = []
    for item in requested:
        value = item.strip()
        if value and value not in cleaned:
            cleaned.append(value)
    if not cleaned:
        return DEFAULT_CLASSES
    return cleaned[:32]


def analyze_image(image_bytes: bytes, classes: List[str] | None, confidence: float) -> Dict[str, Any]:
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds the 8 MB analysis limit.")

    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    image_classes = _clean_classes(classes)
    detector = get_model()

    with _model_lock:
        detector.set_classes(image_classes)
        results = detector.predict(source=image, conf=confidence, verbose=False)

    result = results[0]
    detections = []
    if result.boxes is not None:
        names = result.names or {}
        for box, score, class_id in zip(
            result.boxes.xyxy.cpu().tolist(),
            result.boxes.conf.cpu().tolist(),
            result.boxes.cls.cpu().tolist(),
        ):
            x1, y1, x2, y2 = box
            label = names.get(int(class_id), image_classes[int(class_id)])
            detections.append(
                {
                    "label": label,
                    "confidence": round(float(score), 3),
                    "box": {
                        "x": round(x1, 2),
                        "y": round(y1, 2),
                        "width": round(max(0.0, x2 - x1), 2),
                        "height": round(max(0.0, y2 - y1), 2),
                    },
                }
            )

    return {
        "model": MODEL_NAME,
        "image": {"width": image.width, "height": image.height},
        "classes": image_classes,
        "detections": detections,
    }

class YoloWorldDetector(VisualDetector):
    def analyze(self, image_bytes: bytes, classes: Optional[List[str]], confidence: float) -> Dict[str, Any]:
        return analyze_image(image_bytes, classes, confidence)
