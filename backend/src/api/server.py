"""FastAPI application (driving adapter).

Hosts:
- REST API router mounted at /api
- Three.js WebGL industrial digital twin at /
- Static file serving for PLY point clouds, textures, and scripts
- Automated database seeding on startup
- CORS middleware for multi-device desktop and mobile browsers
"""

from contextlib import asynccontextmanager
import logging
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ask_your_factory")

from api import container as container_module
from api.controllers.health_controller import health_check
from dto.common_dto import HealthResponse
from api.routes import router as api_router
from business.errors import NotFoundError
from infra.paths import FRONTEND_DIR

# Changes on every (re)start; the page reloads itself when it changes (development only).
BOOT_ID = uuid.uuid4().hex


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the container (database seed + scene pipeline) and the photoreal splat before serving."""
    container = container_module.get_container()
    try:
        # First run converts the raw scan (minutes, once); later runs find the cached file.
        logger.info("Photoreal scene ready: %s", container.scene.viewer_splat().name)
    except NotFoundError as error:
        logger.warning("Photoreal scene unavailable, viewer falls back to points: %s", error)
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


# Mount frontend assets
styles_dir = FRONTEND_DIR / "src" / "styles"
if styles_dir.exists():
    app.mount("/styles", StaticFiles(directory=str(styles_dir)), name="styles")

js_dir = FRONTEND_DIR / "src" / "js"
if js_dir.exists():
    app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")

public_dir = FRONTEND_DIR / "public"
if public_dir.exists():
    app.mount("/public", StaticFiles(directory=str(public_dir)), name="public")


@app.get("/", include_in_schema=False)
async def root_index():
    """Serve the interactive Three.js 3D digital twin dashboard."""
    index_path = FRONTEND_DIR / "index.html"
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


@app.get("/api/dev/version", include_in_schema=False)
async def dev_version():
    """Server boot id + newest frontend file time; the viewer polls this on localhost to auto-reload."""
    newest = max((p.stat().st_mtime for p in FRONTEND_DIR.rglob("*") if p.is_file()), default=0.0)
    return {"boot_id": BOOT_ID, "frontend_mtime": newest}


app.get("/health", tags=["System"], response_model=HealthResponse)(health_check)
app.get("/api/health", tags=["System"], response_model=HealthResponse)(health_check)


def start_server(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run("api.server:app", host=host, port=port, reload=True)


if __name__ == "__main__":
    start_server()
