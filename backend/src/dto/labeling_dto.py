"""Labeling capture contract: one rendered view and the camera matrix that produced it."""

from typing import List

from pydantic import BaseModel, Field

MATRIX_VALUES = 16
MAX_IMAGE_SIDE = 4096


class ViewUpload(BaseModel):
    view_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    image_base64: str = Field(min_length=1)
    view_projection: List[float] = Field(min_length=MATRIX_VALUES, max_length=MATRIX_VALUES)
    width: int = Field(gt=0, le=MAX_IMAGE_SIDE)
    height: int = Field(gt=0, le=MAX_IMAGE_SIDE)
