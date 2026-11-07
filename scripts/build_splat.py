"""Rebuild the photoreal viewer splat (data/Equipment_Room.splat) from the raw scan.

The server also builds it automatically the first time the viewer asks for it. Run this to
pre-build it (or to rebuild after replacing the scan). Needs only numpy.

Usage (repository root, Git Bash):  backend/.venv/Scripts/python scripts/build_splat.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from infra.spatial.point_cloud import RAW_SPLAT_PATH  # noqa: E402
from infra.spatial.splat_export import build_viewer_splat  # noqa: E402

if __name__ == "__main__":
    if not RAW_SPLAT_PATH.exists():
        sys.exit("Raw splat not found: put 'Equipment Room.ply' in data/ or data/input/.")
    started = time.perf_counter()
    path = build_viewer_splat()
    print("wrote {} ({:.1f} MB) in {:.0f}s".format(path, path.stat().st_size / 1e6, time.perf_counter() - started))
