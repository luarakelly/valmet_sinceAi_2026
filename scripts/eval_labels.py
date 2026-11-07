"""Score the automatic labels against the operator's boxes (data/asset_placements.json, status confirmed).

Compares data/semantic_objects.json with the plain geometric extraction on recall at 3D IoU >= 0.25.
Draw 20+ ground-truth boxes in the viewer (?author) before running this.

Usage (repository root):  backend/.venv/Scripts/python scripts/eval_labels.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from infra.importers.workbook.dataset import get_dataset  # noqa: E402
from infra.labeling.evaluation import LabeledBox, score_boxes  # noqa: E402
from infra.labeling.instances import OrientedBox  # noqa: E402
from infra.labeling.semantic_objects import read_semantic_objects  # noqa: E402
from infra.paths import PLACEMENTS_PATH, SEMANTIC_OBJECTS_PATH  # noqa: E402
from infra.spatial.point_cloud import load_scene_cloud  # noqa: E402
from infra.spatial.segmentation import detect_room, extract_objects  # noqa: E402


def main() -> None:
    truth = _ground_truth()
    if not truth:
        sys.exit("No confirmed placements in {}. Box some assets in the viewer first.".format(PLACEMENTS_PATH))
    semantic = [LabeledBox(o.asset_class, OrientedBox(o.center, o.size, o.yaw)) for o in read_semantic_objects(SEMANTIC_OBJECTS_PATH)]
    cloud = load_scene_cloud()
    geometric = [LabeledBox(None, OrientedBox(o.center, o.size, 0.0)) for o in extract_objects(cloud, detect_room(cloud))]
    print(json.dumps({"ground_truth": len(truth), "semantic": score_boxes(truth, semantic), "geometric_baseline": score_boxes(truth, geometric)}, indent=1))


def _ground_truth():
    classes = {asset["asset_id"]: asset["asset_class"] for asset in get_dataset().get_assets()}
    records = json.loads(PLACEMENTS_PATH.read_text()) if PLACEMENTS_PATH.exists() else {}
    return [
        LabeledBox(classes.get(asset_id), OrientedBox(tuple(r["center"]), tuple(r["size"]), 0.0))
        for asset_id, r in records.items()
        if r.get("status") == "confirmed"
    ]


if __name__ == "__main__":
    main()
