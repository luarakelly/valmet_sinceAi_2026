"""Go/no-go check: does GroundingDINO + SAM 2 see equipment in our renders? Writes overlay PNGs.

Put a few viewer screenshots (JPG/PNG) in data/labeling/spike/ and run:
  backend/.venv/Scripts/python scripts/spike_grounded_sam.py [--device auto|cuda|cpu]
GO when most images show at least one correct, tight detection.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from infra.paths import DATA_DIR  # noqa: E402

SPIKE_DIR = DATA_DIR / "labeling" / "spike"
OVERLAY_ALPHA = 0.45


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    arguments = parser.parse_args()
    images = sorted(p for p in SPIKE_DIR.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png") and not p.stem.endswith("_overlay"))
    if not images:
        sys.exit("Put screenshots in {}".format(SPIKE_DIR))
    from PIL import Image

    from infra.labeling.segmenter import GroundedSam2Segmenter

    segmenter = GroundedSam2Segmenter(arguments.device)
    for path in images:
        rgb = np.asarray(Image.open(path).convert("RGB"))
        detections = segmenter.segment(rgb)
        overlay = rgb.copy().astype(float)
        for detection in detections:
            colour = np.random.default_rng(abs(hash(detection.term.label)) % 2**32).integers(60, 255, 3)
            overlay[detection.mask] = (1 - OVERLAY_ALPHA) * overlay[detection.mask] + OVERLAY_ALPHA * colour
        Image.fromarray(overlay.astype(np.uint8)).save(SPIKE_DIR / "{}_overlay.png".format(path.stem))
        print("{}: {}".format(path.name, ", ".join("{} {:.2f}".format(d.term.label, d.score) for d in detections) or "nothing"))


if __name__ == "__main__":
    main()
