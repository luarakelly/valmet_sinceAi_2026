"""AI Scan contract: YOLO-World detections on a viewport snapshot."""

from typing import List

from pydantic import BaseModel

from dto.common_dto import ImageSize, PixelBox


class VisionDetection(BaseModel):
    label: str
    confidence: float
    box: PixelBox


class VisionAnalysisResponse(BaseModel):
    model: str
    image: ImageSize
    classes: List[str]
    detections: List[VisionDetection]
