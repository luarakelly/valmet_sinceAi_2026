"""Cross-check of the workbook's asset list against what the labeler found in the scan."""

from collections import Counter
from typing import Any, Dict, List

from infra.labeling.semantic_objects import SemanticObject


def coverage_report(assets: List[Dict[str, Any]], objects: List[SemanticObject]) -> Dict[str, Any]:
    """Per asset class: how many the workbook lists vs how many the scan shows; plus everything else found."""
    expected = Counter(asset["asset_class"] for asset in assets)
    found = Counter(obj.asset_class for obj in objects if obj.asset_class)
    classes = {
        asset_class: {"in_workbook": count, "found_in_scan": found.get(asset_class, 0), "missing": max(0, count - found.get(asset_class, 0))}
        for asset_class, count in sorted(expected.items())
    }
    extras = Counter(obj.label for obj in objects if not obj.asset_class)
    unlisted = {asset_class: count for asset_class, count in found.items() if asset_class not in expected}
    return {"classes": classes, "other_objects": dict(sorted(extras.items())), "unlisted_asset_classes": unlisted}
