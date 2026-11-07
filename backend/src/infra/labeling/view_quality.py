"""Cheap image checks (numpy only): a view that is black or smeared must not feed the labeler."""

import numpy as np

MIN_MEAN_BRIGHTNESS = 25.0  # 0-255; camera inside a wall renders near-black
MIN_DETAIL = 4.0  # mean absolute neighbour difference; smeared splat close-ups fall below it


def view_problem(image_rgb: np.ndarray) -> str:
    """'' when the view is usable, otherwise the reason it is not."""
    gray = image_rgb.astype(np.float32).mean(axis=2)
    if gray.mean() < MIN_MEAN_BRIGHTNESS:
        return "too dark"
    detail = (np.abs(np.diff(gray, axis=0)).mean() + np.abs(np.diff(gray, axis=1)).mean()) / 2.0
    if detail < MIN_DETAIL:
        return "too blurry"
    return ""
