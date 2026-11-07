"""Test session setup: src/ on the path and a fresh, seeded SQLite database (never backend/database.db)."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='ask_your_factory_')}/test.db"
os.environ.setdefault("LLM_PROVIDER", "none")  # tests never call a real LLM
