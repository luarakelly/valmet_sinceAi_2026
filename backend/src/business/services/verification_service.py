"""Camera verification: a vision-language model looks at a render of one scene object and says what it is.

The workbook has no real positions (Scene_Anchors are placeholders), so what an object *is* must come
from evidence in the scan. This stores that evidence; asset binding uses it (infra/spatial/asset_mapping).
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from business.errors import InvalidRequestError, NotFoundError, ServiceUnavailableError
from business.interfaces.ports.outbound import LanguageModel, VerificationStore
from business.services.scene_service import SceneService

MAX_IMAGE_BYTES = 4 * 1024 * 1024

# What the model may answer → builder-pack asset class (None = visible but not a pack asset class).
CATEGORY_TO_ASSET_CLASS: Dict[str, Optional[str]] = {
    "pump": "PROCESS_PUMP",
    "electric_motor": "ELECTRIC_MOTOR",
    "control_valve": "CONTROL_VALVE",
    "pressure_transmitter": "PRESSURE_TRANSMITTER",
    "vibration_sensor": "VIBRATION_SENSOR",
    "pipe": None,
    "structure": None,
    "unknown": None,
}

PROMPT = """You are inspecting ONE object in a render of a Gaussian-splat 3D scan of an industrial boiler room.
The image is cropped around a single detected object, outlined by a thin cyan rectangle at the centre. The
render is soft and may contain artefacts. Decide what the object inside the cyan rectangle is.

Categories (answer with exactly one key):
- pump: a process pump with a casing/volute, usually on a base plate near floor level
- electric_motor: a cylindrical or boxy motor with a fan cover or cooling fins, usually coupled to a pump
- control_valve: a valve body with an actuator, diaphragm head or handwheel, installed in a pipe
- pressure_transmitter: a small instrument or pressure gauge on a pipe or impulse line
- vibration_sensor: a very small sensor stud mounted on a machine casing
- pipe: plain pipe, elbow, flange, hose, insulation or cable tray
- structure: wall, floor, cabinet, tank, rack, ladder, steel frame or anything else
- unknown: you cannot tell

Be conservative: if the centre object is not clearly one of the equipment categories, answer pipe,
structure or unknown. Respond with JSON only:
{"category": "<key>", "confidence": <0..1>, "visible_features": "<one short phrase>"}"""


class VerificationService:
    def __init__(self, scene: SceneService, llm: Optional[LanguageModel], store: VerificationStore):
        self._scene = scene
        self._llm = llm
        self._store = store

    def all(self) -> Dict[str, Dict[str, Any]]:
        return self._store.all()

    def verify(self, object_id: str, image: bytes, content_type: str) -> Dict[str, Any]:
        frame = self._scene.find_frame(object_id)
        if frame is None:
            raise NotFoundError("No scene object matches '{}'.".format(object_id))
        if not content_type or not content_type.startswith("image/"):
            raise InvalidRequestError("Image upload required.")
        if len(image) > MAX_IMAGE_BYTES:
            raise InvalidRequestError("Image exceeds the 4 MB limit.")
        if self._llm is None:
            raise ServiceUnavailableError("Camera verification needs an LLM key (GEMINI_API_KEY).")

        answer = self._llm.complete_json(PROMPT, images=[image])
        if not isinstance(answer, dict) or answer.get("category") not in CATEGORY_TO_ASSET_CLASS:
            reason = getattr(self._llm, "last_error", None) or "unexpected answer"
            raise ServiceUnavailableError("The model returned no usable classification ({}).".format(reason))

        try:
            confidence = max(0.0, min(1.0, float(answer.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        record = {
            "category": answer["category"],
            "asset_class": CATEGORY_TO_ASSET_CLASS[answer["category"]],
            "confidence": round(confidence, 2),
            "visible_features": str(answer.get("visible_features", ""))[:160],
            "model": self._llm.name,
            "center": [round(float(v), 2) for v in frame["pos"]],
            "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self._store.save(frame["scene_id"], record)
        return {"object_id": frame["scene_id"], **record}

    def reset(self) -> None:
        self._store.clear()
