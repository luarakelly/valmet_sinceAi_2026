"""Filesystem locations shared by infrastructure adapters.

backend/src/infra/paths.py -> parents[3] is the repository root.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
DATA_DIR = Path(os.getenv("ASK_YOUR_FACTORY_DATA_DIR", str(REPO_ROOT / "data")))
FRONTEND_DIR = REPO_ROOT / "frontend"
WEIGHTS_DIR = DATA_DIR / "weights"
