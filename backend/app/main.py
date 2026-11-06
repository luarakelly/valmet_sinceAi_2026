"""Ask Your Factory Application Entrypoint.

FastAPI server hosting:
- REST API router mounted at /api
- Three.js WebGL industrial digital twin at /
- Static file serving for PLY point clouds, textures, and scripts
- Automated database seeding on startup
- CORS middleware for multi-device desktop and mobile browsers
"""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Dict, Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ask_your_factory")

from app.database import init_db, get_session
from app.routes import router as api_router

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent
STATIC_DIR = APP_DIR / "three_d" / "static"
DATA_DIR = PROJECT_ROOT / "data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler initializing database schema and seeding data."""
    logger.info("Initializing Ask Your Factory database schema...")
    try:
        init_db(populate=True)
        logger.info("Database initialized and verified.")
    except Exception as exc:
        logger.error(f"Error during init_db: {exc}", exc_info=True)

    yield

    logger.info("Shutting down Ask Your Factory backend.")


app = FastAPI(
    title="Ask Your Factory API",
    description=(
        "REST API supporting 3D semantic asset framing, multivariate telemetry time-series, "
        "A* collision-free navigation, and Gemini evidence-grounded diagnostics for the "
        "Ask Your Factory industrial digital twin."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")

try:
    from app.navigation import router as nav_router
    app.include_router(nav_router, prefix="/api")
except ImportError:
    pass

try:
    from app.copilot import router as copilot_router
    app.include_router(copilot_router, prefix="/api")
except ImportError:
    pass

try:
    from app.metaverse.routes import router as metaverse_router
    app.include_router(metaverse_router, prefix="/api")
except ImportError:
    pass


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def root_index():
    """Serve the interactive Three.js 3D digital twin dashboard."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        index_path = APP_DIR / "three_d" / "static" / "index.html"

    if index_path.exists():
        return FileResponse(str(index_path))

    return HTMLResponse(
        """<!DOCTYPE html>
<html>
<head><title>Ask Your Factory</title></head>
<body style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 2rem;">
    <h1>Ask Your Factory</h1>
  <p>API Server is operational. Interactive documentation is available at <a href="/docs" style="color: #38bdf8;">/docs</a>.</p>
  <ul>
    <li><a href="/api/assets" style="color: #38bdf8;">/api/assets</a></li>
    <li><a href="/api/scene/anchors" style="color: #38bdf8;">/api/scene/anchors</a></li>
    <li><a href="/api/metaverse/dashboard" style="color: #38bdf8;">/api/metaverse/dashboard</a></li>
  </ul>
</body>
</html>"""
    )


@app.get("/model/pointcloud.ply", include_in_schema=False)
@app.get("/api/scene/boiler-room.ply", include_in_schema=False)
async def get_pointcloud_ply():
    """Serve the boiler room point cloud file to Three.js PLYLoader."""
    candidates = [
        DATA_DIR / "Industrial_Boiler_Room_standard.ply",
        PROJECT_ROOT / "Industrial_Boiler_Room_standard.ply",
        STATIC_DIR / "Industrial_Boiler_Room_standard.ply",
        DATA_DIR / "Industrial Boiler Room.ply",
        PROJECT_ROOT / "Industrial Boiler Room.ply",
    ]
    for p in candidates:
        if p.exists():
            return FileResponse(str(p), media_type="application/octet-stream", filename=p.name)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Boiler room PLY model not found on server.",
    )


@app.get("/health", tags=["System"])
@app.get("/api/health", tags=["System"])
async def health_check() -> Dict[str, Any]:
    """Liveness probe confirming API service readiness."""
    return {
        "status": "healthy",
        "service": "ask-your-factory",
        "version": "1.0.0",
        "models_loaded": 30,
    }


def start_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run("app.main:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    start_server()
