"""Small shared contracts reused across endpoints."""

from pydantic import BaseModel


class ImageSize(BaseModel):
    width: int
    height: int


class PixelBox(BaseModel):
    """Axis-aligned box in image pixels (top-left origin)."""

    x: float
    y: float
    width: float
    height: float


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    models_loaded: int
