"""Label the Equipment Room scan: captured views → Grounded-SAM 2 → 3D back-projection → DBSCAN → boxes.

Run after capturing views in the viewer (http://localhost:8000/?author → "Capture labeling views").
Needs a GPU (CPU works, slowly), `transformers`, `ultralytics` and `scikit-learn`.
Masks are cached next to each view, so re-running with other thresholds is fast.

Usage (repository root):  backend/.venv/Scripts/python scripts/label_scene.py [--device auto|cuda|cpu]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from infra.importers.workbook.dataset import get_dataset  # noqa: E402
from infra.labeling.pack_coverage import coverage_report  # noqa: E402
from infra.labeling.pipeline import ViewDetections, build_semantic_objects  # noqa: E402
from infra.labeling.segmenter import Detection  # noqa: E402
from infra.labeling.semantic_objects import write_semantic_objects  # noqa: E402
from infra.labeling.vocabulary import VOCABULARY  # noqa: E402
from infra.labeling.view_quality import view_problem  # noqa: E402
from infra.paths import LABELING_VIEWS_DIR, MODEL_OBJECTS_PATH  # noqa: E402
from infra.spatial.point_cloud import load_scene_cloud  # noqa: E402

EXIT_FAILURE = 1


def main() -> None:
    arguments = _parse()
    view_ids = _usable_views()
    if not view_ids:
        sys.exit("No views in {}. Capture them in the viewer first (?author).".format(LABELING_VIEWS_DIR))
    segmenter = _SegmenterOnDemand(arguments.device)
    views = [_view_detections(view_id, segmenter) for view_id in view_ids]
    cloud = load_scene_cloud()
    objects = build_semantic_objects(cloud.xyz, views)
    MODEL_OBJECTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_semantic_objects(MODEL_OBJECTS_PATH, objects)
    print("wrote {} model objects from {} views to {}; now run scripts/rebuild_labels.py".format(len(objects), len(views), MODEL_OBJECTS_PATH))
    print(json.dumps(coverage_report(get_dataset().get_assets(), objects), indent=1))


def _usable_views():
    """Captured views whose image is neither black nor smeared (camera inside a wall or pipe)."""
    usable = []
    for path in sorted(LABELING_VIEWS_DIR.glob("*.jpg")):
        problem = view_problem(_load_rgb(path))
        if problem:
            print("{}: skipped, {}".format(path.stem, problem))
        else:
            usable.append(path.stem)
    return usable


def _parse() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    return parser.parse_args()


class _SegmenterOnDemand:
    """Loads the heavy models only when a view has no cached masks."""

    def __init__(self, device: str) -> None:
        self._device = device
        self._segmenter = None

    def segment(self, image_rgb: np.ndarray):
        if self._segmenter is None:
            from infra.labeling.segmenter import GroundedSam2Segmenter

            self._segmenter = GroundedSam2Segmenter(self._device)
        return self._segmenter.segment(image_rgb)


def _view_detections(view_id: str, segmenter: _SegmenterOnDemand) -> ViewDetections:
    meta = json.loads((LABELING_VIEWS_DIR / "{}.json".format(view_id)).read_text())
    cache = LABELING_VIEWS_DIR / "{}.masks.npz".format(view_id)
    if cache.exists():
        detections = _load_cache(cache, meta["height"], meta["width"])
    else:
        detections = segmenter.segment(_load_rgb(LABELING_VIEWS_DIR / "{}.jpg".format(view_id)))
        _save_cache(cache, detections)
    print("{}: {} detections".format(view_id, len(detections)))
    return ViewDetections(meta["view_projection"], detections)


def _load_rgb(path: Path) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"))


def _save_cache(path: Path, detections) -> None:
    labels = np.array([d.term.label for d in detections])
    scores = np.array([d.score for d in detections])
    masks = np.array([d.mask for d in detections], dtype=bool)
    np.savez_compressed(path, labels=labels, scores=scores, packed=np.packbits(masks, axis=-1), width=masks.shape[-1] if len(masks) else 0)


def _load_cache(path: Path, height: int, width: int):
    terms = {term.label: term for term in VOCABULARY}
    stored = np.load(path)
    if len(stored["labels"]) == 0:
        return []
    masks = np.unpackbits(stored["packed"], axis=-1, count=int(stored["width"])).astype(bool)
    return [Detection(terms[str(label)], float(score), mask) for label, score, mask in zip(stored["labels"], stored["scores"], masks)]


if __name__ == "__main__":
    main()
