"""Draw data/semantic_objects.json over the captured views (data/labeling/preview/<view>.jpg) to check boxes by eye.

Usage (repository root):  backend/.venv/Scripts/python scripts/preview_labels.py [view_id ...]
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from infra.labeling.semantic_objects import read_semantic_objects  # noqa: E402
from infra.paths import LABELING_VIEWS_DIR, SEMANTIC_OBJECTS_PATH  # noqa: E402

EDGES = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
NEAR_PLANE = 0.05
LINE_WIDTH = 3
PALETTE = [(255, 60, 60), (255, 160, 0), (80, 200, 255), (255, 255, 255), (150, 255, 150), (200, 120, 255), (255, 230, 80), (255, 0, 255)]


def main() -> None:
    objects = read_semantic_objects(SEMANTIC_OBJECTS_PATH)
    if not objects:
        sys.exit("No semantic objects in {}".format(SEMANTIC_OBJECTS_PATH))
    wanted = sys.argv[1:] or sorted(p.stem for p in LABELING_VIEWS_DIR.glob("*.jpg"))
    out_dir = LABELING_VIEWS_DIR.parent / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    labels = sorted({o.label for o in objects})
    for view_id in wanted:
        image_path = LABELING_VIEWS_DIR / "{}.jpg".format(view_id)
        meta_path = LABELING_VIEWS_DIR / "{}.json".format(view_id)
        if not image_path.exists() or not meta_path.exists():
            print("skip {}: view not found".format(view_id))
            continue
        _draw(image_path, json.loads(meta_path.read_text())["view_projection"], objects, labels).save(out_dir / "{}.jpg".format(view_id), quality=88)
    print("wrote previews to {}".format(out_dir))


def _draw(image_path, view_projection, objects, labels):
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    matrix = np.array(view_projection).reshape(4, 4).T
    draw = ImageDraw.Draw(image)
    for obj in objects:
        clip = np.c_[_corners(obj), np.ones(8)] @ matrix.T
        if (clip[:, 3] <= NEAR_PLANE).any():
            continue
        ndc = clip[:, :3] / clip[:, 3:4]
        points = [((a * 0.5 + 0.5) * width, (0.5 - b * 0.5) * height) for a, b, _ in ndc]
        colour = PALETTE[labels.index(obj.label) % len(PALETTE)]
        for i, j in EDGES:
            draw.line([points[i], points[j]], fill=colour, width=LINE_WIDTH)
        draw.text((min(x for x, _ in points) + 3, min(y for _, y in points) + 3), obj.label, fill=colour)
    return image


def _corners(obj) -> np.ndarray:
    cx, cy, cz = obj.center
    sx, sy, sz = obj.size
    c, s = math.cos(obj.yaw), math.sin(obj.yaw)
    corners = []
    for dx in (-1, 1):
        for dy in (-1, 1):
            for dz in (-1, 1):
                lx, lz = dx * sx / 2, dz * sz / 2
                corners.append((cx + lx * c - lz * s, cy + dy * sy / 2, cz + lx * s + lz * c))
    return np.array(corners)


if __name__ == "__main__":
    main()
