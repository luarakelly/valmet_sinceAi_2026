"""2D open-vocabulary segmentation: GroundingDINO finds boxes for the prompt list, SAM 2 cuts masks.

Heavy and GPU-bound: imported lazily and only by scripts/label_scene.py, never by the FastAPI process.
"""

from dataclasses import dataclass
import logging
from typing import List, Sequence

import numpy as np

from infra.labeling.vocabulary import Term, prompt_text, term_for_phrase

logger = logging.getLogger("ask_your_factory.segmenter")

DINO_MODEL_ID = "IDEA-Research/grounding-dino-base"
SAM_WEIGHTS = "sam2.1_b.pt"
BOX_THRESHOLD = 0.30
TEXT_THRESHOLD = 0.25
MAX_MASK_FRACTION = 0.35  # a mask this large is the wall or the floor, not an object
MIN_MASK_PIXELS = 100


@dataclass(frozen=True)
class Detection:
    term: Term
    score: float
    mask: np.ndarray  # H×W bool


def keep_detections(
    phrases: Sequence[str], scores: Sequence[float], masks: Sequence[np.ndarray]
) -> List[Detection]:
    """Drop unknown phrases, room-sized masks and specks; the rest become Detections."""
    kept: List[Detection] = []
    for phrase, score, mask in zip(phrases, scores, masks):
        term = term_for_phrase(phrase)
        is_object_sized = MIN_MASK_PIXELS <= mask.sum() <= MAX_MASK_FRACTION * mask.size
        if term is not None and is_object_sized:
            kept.append(Detection(term, float(score), mask.astype(bool)))
    return kept


class GroundedSam2Segmenter:
    def __init__(self, device: str = "auto") -> None:
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
        from ultralytics import SAM

        self._torch = torch
        self._device = device
        if device == "auto":
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading GroundingDINO and SAM 2 on %s", self._device)
        self._processor = AutoProcessor.from_pretrained(DINO_MODEL_ID)
        self._dino = AutoModelForZeroShotObjectDetection.from_pretrained(DINO_MODEL_ID).to(self._device).eval()
        self._sam = SAM(SAM_WEIGHTS)

    def segment(self, image_rgb: np.ndarray) -> List[Detection]:
        boxes, scores, phrases = self._detect(image_rgb)
        if len(boxes) == 0:
            return []
        masks = self._cut_masks(image_rgb, boxes)
        return keep_detections(phrases, scores, masks)

    def _detect(self, image_rgb: np.ndarray):
        from PIL import Image

        height, width = image_rgb.shape[:2]
        inputs = self._processor(images=Image.fromarray(image_rgb), text=prompt_text(), return_tensors="pt").to(self._device)
        with self._torch.no_grad():
            outputs = self._dino(**inputs)
        result = self._processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=BOX_THRESHOLD, text_threshold=TEXT_THRESHOLD, target_sizes=[(height, width)]
        )[0]
        phrases = result.get("text_labels", result["labels"])
        return result["boxes"].cpu().numpy(), result["scores"].cpu().numpy(), list(phrases)

    def _cut_masks(self, image_rgb: np.ndarray, boxes: np.ndarray) -> List[np.ndarray]:
        outcome = self._sam(image_rgb[:, :, ::-1].copy(), bboxes=boxes.tolist(), verbose=False)[0]
        return [mask.cpu().numpy() > 0.5 for mask in outcome.masks.data]
