"""Rebuild the viewer mesh (data/Equipment_Room_mesh.ply) from the raw splat.

Needs the raw scan at data/Equipment Room.ply or data/input/Equipment Room.ply
and the mesh extras from backend/requirements.txt (scikit-image, trimesh, fast-simplification).

Usage (repository root, Git Bash):  backend/.venv/Scripts/python scripts/build_mesh.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from infra.spatial.point_cloud import RAW_SPLAT_PATH, build_scene_mesh  # noqa: E402

if __name__ == "__main__":
    if not RAW_SPLAT_PATH.exists():
        sys.exit("Raw splat not found: put 'Equipment Room.ply' in data/ or data/input/.")
    started = time.perf_counter()
    path = build_scene_mesh(force=True)
    print("wrote {} in {:.0f}s".format(path, time.perf_counter() - started))
