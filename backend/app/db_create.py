from pathlib import Path
import sys
import os
from sqlmodel import SQLModel, create_engine

# Ensure we're on the right working dir, sir
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent))

# Import models so they are registered with SQLModel.metadata
from app import models  


def main():
    # Where's the db? Where's waldo??
    default_db = BASE_DIR.parent / "database.db"
    db_url = os.getenv("DATABASE_URL") or f"sqlite:///{default_db}"

    if db_url.startswith("sqlite:///"):
        db_file = Path(db_url.replace("sqlite:///", ""))
        if not db_file.exists():
            print(f"Database file will be created at {db_file}")
        else:
            # ensure tables exits
            print(f"Database file exists at {db_file}; ensuring tables exist")

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    print(f"Created database and tables at {db_url}")


if __name__ == "__main__":
    main()
