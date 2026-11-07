"""Start the server:  python backend/src/main.py   (or ./run.sh / run.bat)."""

import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.server:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "1") == "1",
        reload_dirs=[str(SRC_DIR)],
        app_dir=str(SRC_DIR),
    )
