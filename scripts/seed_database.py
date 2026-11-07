"""(Re)seed the SQLite database from the builder pack.

Usage (repository root, Git Bash):  backend/.venv/Scripts/python scripts/seed_database.py [--force]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from infra.db.sqlmodel.database import init_db, populate_db_if_empty  # noqa: E402

if __name__ == "__main__":
    init_db(populate=True)
    if "--force" in sys.argv:
        print(populate_db_if_empty(force=True))
    print("Database ready.")
