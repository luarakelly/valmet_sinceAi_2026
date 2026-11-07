"""Placement contract: lift a 2D box drawn in the viewer into a 3D box, and store it for an asset."""

from typing import List, Literal

from pydantic import BaseModel, Field, model_validator

MATRIX_VALUES = 16
BOX_COORDINATES = 4
VECTOR_SIZE = 3


class LiftBoxRequest(BaseModel):
    view_projection: List[float] = Field(min_length=MATRIX_VALUES, max_length=MATRIX_VALUES)
    image_box: List[float] = Field(min_length=BOX_COORDINATES, max_length=BOX_COORDINATES)

    @model_validator(mode="after")
    def box_is_inside_image(self) -> "LiftBoxRequest":
        x0, y0, x1, y1 = self.image_box
        is_inside_image = 0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0
        if not is_inside_image:
            raise ValueError("image_box must be [x0, y0, x1, y1] fractions with x0 < x1 and y0 < y1")
        return self


class PlacementBox(BaseModel):
    center: List[float] = Field(min_length=VECTOR_SIZE, max_length=VECTOR_SIZE)
    size: List[float] = Field(min_length=VECTOR_SIZE, max_length=VECTOR_SIZE)
    status: Literal["proposed", "confirmed"] = "confirmed"


class LiftBoxResponse(PlacementBox):
    point_count: int
