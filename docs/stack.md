# Technology Stack

## Architecture Overview

```text
Browser (Three.js r128 + OrbitControls + PLYLoader)
       │  REST (/api)
       ▼
FastAPI (Python 3.11+, Uvicorn, SQLModel / SQLite WAL)
       │
       ├─► Scene pipeline (NumPy + SciPy, ≈0.5 s at startup)
       │     raw 3DGS splat → canonical cloud → 144 framed objects → 30 bound assets → occupancy grid
       ├─► Navigation: inflated occupancy grid, A* + line-of-sight smoothing, measured clearance
       ├─► Copilot: telemetry drift (t-score), alarms, similar cases, docs, data-quality penalties;
       │     optional Gemini narrative accepted only when every cited ID exists
       └─► Vision: YOLO-World open-vocabulary detection on viewport snapshots
```

## Scene pipeline (`backend/src/infra/spatial/`)

| Module | Responsibility |
|---|---|
| `point_cloud.py` | Reads `Equipment Room.ply`, drops low-opacity / oversized splats, rotates COLMAP Y-down to Y-up, puts the floor at y = 0 and centres the room. Exports `Equipment_Room_standard.ply` for the viewer (tracked, so a clone works without the 395 MB raw scan). |
| `segmentation.py` | Removes walls, floor and ceiling; voxelises equipment and pipe-rack layers separately; splits 26-connected components at thin links (erosion seeds) or the sparsest plane; labels each box from geometry and colour (pipe runs, floor machines, valves, instruments, fire-safety equipment …). |
| `navigation.py` | 2D obstacle map between ankle and robot height, Euclidean-distance inflation by the robot radius, largest connected free region, A* with no corner cutting, string-pulling, and per-route `min_clearance_m` / `collision_free` measured on the final segments. |
| `asset_mapping.py` | Binds the 30 builder-pack assets to compatible, reachable objects (pumps → floor machines, sensors → instruments …) with a `mapping_confidence`; the lowest-health asset becomes the inspection target at the far end of the walk. |
| `scene_pipeline.py` | `SceneEngine` adapter: runs the above once per process, serves frames, anchors, proximity and routes. |
| `business/services/copilot_service.py` | Evidence engine + optional Gemini/Claude layer (citation-verified). |
| `infra/importers/workbook/dataset.py` | Loads the builder pack (JSON cache or Excel). |

## Configuration (`.env`)

- `GEMINI_API_KEY` (optional): enables the LLM narrative; without it the deterministic evidence engine answers.
- `GEMINI_MODEL` (optional, default `gemini-2.5-flash`).
- `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` (optional): Claude instead of Gemini.
- `LLM_PROVIDER` (optional): `gemini`, `claude` or `none`.
- `YOLO_WORLD_MODEL` (optional): weights path; default `data/weights/yolov8s-worldv2.pt` or auto-download.
- `DATABASE_URL` (optional, default `backend/database.db`).

## Quick Start

1. Initialize environment: `./initialize.sh` (or `initialize.bat`)
2. Launch server: `./run.sh` (or `run.bat`)
3. Open browser: `http://localhost:8000/`
4. Tests: `cd backend && .venv/Scripts/python -m pytest` (Linux/macOS: `.venv/bin/python`)
