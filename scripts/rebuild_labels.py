"""Regenerate data/semantic_objects.json from the hand-drawn view annotations (and model output, if any).

Safe to run any time: inputs are validated, bad boxes and views are skipped with a reason, the old result is
backed up, the new one is written atomically, and an empty result never replaces a good file.
Run again after changing the scan, the cameras (re-capture) or data/view_annotations.json.

Usage (repository root):  backend/.venv/Scripts/python scripts/rebuild_labels.py
"""

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from infra.importers.workbook.dataset import get_dataset  # noqa: E402
from infra.labeling.pack_coverage import coverage_report  # noqa: E402
from infra.labeling.rebuild import rebuild_objects  # noqa: E402
from infra.labeling.semantic_objects import read_semantic_objects, write_json_atomically, write_semantic_objects  # noqa: E402
from infra.paths import (  # noqa: E402
    LABELING_VIEWS_DIR,
    MODEL_OBJECTS_PATH,
    SEMANTIC_OBJECTS_PATH,
    SEMANTIC_REPORT_PATH,
    VIEW_ANNOTATIONS_PATH,
)
from infra.spatial.point_cloud import load_scene_cloud  # noqa: E402
from infra.spatial.segmentation import detect_room  # noqa: E402

MATRIX_VALUES = 16


def main() -> None:
    if not VIEW_ANNOTATIONS_PATH.exists():
        sys.exit("Missing {}. Draw boxes first (see README: Automatic semantic labels).".format(VIEW_ANNOTATIONS_PATH))
    projections, problems = _view_projections()
    cloud = load_scene_cloud()
    result = rebuild_objects(cloud.xyz, detect_room(cloud), projections, VIEW_ANNOTATIONS_PATH, read_semantic_objects(MODEL_OBJECTS_PATH))
    issues = problems + result.issues
    if not result.objects:
        _print_issues(issues)
        sys.exit("No valid objects produced; {} left untouched.".format(SEMANTIC_OBJECTS_PATH.name))
    if SEMANTIC_OBJECTS_PATH.exists():
        shutil.copyfile(SEMANTIC_OBJECTS_PATH, SEMANTIC_OBJECTS_PATH.with_suffix(".json.bak"))
    write_semantic_objects(SEMANTIC_OBJECTS_PATH, result.objects)
    report = {
        "objects": len(result.objects),
        "by_label": dict(sorted(Counter(o.label for o in result.objects).items())),
        "issues": issues,
        "workbook_coverage": coverage_report(get_dataset().get_assets(), result.objects),
    }
    write_json_atomically(SEMANTIC_REPORT_PATH, report)
    print("wrote {} objects to {}; {} issues (see {})".format(len(result.objects), SEMANTIC_OBJECTS_PATH.name, len(issues), SEMANTIC_REPORT_PATH.name))
    print(json.dumps({"by_label": report["by_label"], "workbook_coverage": report["workbook_coverage"]["classes"]}, indent=1))


def _view_projections():
    """view_id → camera matrix from the captured sidecar files; unreadable ones are reported and skipped."""
    projections, problems = {}, []
    for meta_path in sorted(LABELING_VIEWS_DIR.glob("*.json")):
        try:
            matrix = json.loads(meta_path.read_text())["view_projection"]
            if len(matrix) != MATRIX_VALUES:
                raise ValueError("expected {} numbers".format(MATRIX_VALUES))
            projections[meta_path.stem] = [float(v) for v in matrix]
        except (OSError, ValueError, KeyError, TypeError) as error:
            problems.append("view {} skipped: unreadable camera ({})".format(meta_path.stem, error))
    if not projections:
        problems.append("no captured views in {}".format(LABELING_VIEWS_DIR))
    return projections, problems


def _print_issues(issues) -> None:
    for issue in issues[:20]:
        print(" -", issue)


if __name__ == "__main__":
    main()
