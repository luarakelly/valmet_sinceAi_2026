"""Test session setup: every run uses a fresh, seeded SQLite database (never backend/database.db)."""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='ask_your_factory_')}/test.db"

from app.database import init_db  # noqa: E402  (must import after DATABASE_URL is set)

init_db(populate=True)
