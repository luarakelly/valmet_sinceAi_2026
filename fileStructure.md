# Project Structure & Architecture

```text
valmet_sinceAi_2026/
├── backend/                               # Python FastAPI backend service
│   ├── app/
│   │   ├── main.py                        # FastAPI entry point, lifecycle, routing & static mounts
│   │   ├── routes.py                      # Core CRUD endpoints (assets, telemetry, work orders, health)
│   │   ├── models.py                      # SQLModel relational schema (Asset, Telemetry, WorkOrder, etc.)
│   │   ├── schemas.py                     # Pydantic request/response validation schemas
│   │   ├── crud.py                        # Database access & query routines
│   │   ├── database.py                    # Engine configuration, session generators & initial data seed
│   │   ├── db.py                          # Database session helper re-exports
│   │   ├── db_create.py                   # Schema creation & bootstrap CLI utility
│   │   ├── gemini.py                      # Google Gemini client wrapper
│   │   ├── system_prompt.txt              # Diagnostic prompt instructions for AI Field Copilot
│   │   └── metaverse/                     # Digital Twin spatial & AI reasoning package
│   │       ├── routes.py                  # Digital twin endpoints (/api/scene/*, /api/navigation/*)
│   │       ├── dataset.py                 # Valmet Builder Pack Excel reader & parser
│   │       ├── scene_processor.py         # 3D spatial voxel density & A* navigation solver
│   │       ├── vision.py                  # Open-vocabulary YOLO-World visual detector
│   │       └── copilot.py                 # Multi-modal telemetry & diagnostic copilot logic
│   ├── database.db                        # SQLite local runtime database
│   ├── requirements.txt                   # Backend Python package specifications
│   ├── test_routes.py                     # API unit tests
│   └── test_acceptance.py                # End-to-end integration acceptance tests
│
├── frontend/                              # Frontend single-page application
│   ├── index.html                         # Primary HTML5 shell & viewport layout
│   ├── public/                            # Static public assets served at /public
│   └── src/
│       ├── js/
│       │   └── app.js                     # Three.js 3D viewport, point cloud splatting, HUD & UI logic
│       └── styles/
│           └── app.css                    # Industrial dark theme design system & UI stylesheets
│
├── data/                                  # Spatial models, challenge documents & data packs
│   ├── Industrial Boiler Room.ply         # Raw 3D Gaussian Splat scan (~355 MB)
│   ├── Industrial_Boiler_Room_standard.ply# Cleaned binary PLY point cloud for Three.js
│   ├── metaverse_cache.json               # Precomputed spatial scene cache
│   ├── valmet_builder_pack.xlsx           # Industrial asset, telemetry & drawing metadata
│   └── Valmet_x_SinceAI_2026_Challenge_Brief_FINAL_updated (1).docx # Challenge specification
│
├── initialize.sh / initialize.bat         # Bootstrap virtual environment & dependencies (uv/pip)
├── run.sh / run.bat                       # Launch local server with hot reloading
├── stack.md                               # Architectural stack & technology breakdown
└── fileStructure.md                       # Comprehensive directory map
```

## Module Boundaries & Runtime Path

1. **Backend Service (`backend/`)**:
   - `backend/app/main.py` launches the FastAPI application, mounts static frontend assets (`/js`, `/styles`, `/public`), and includes API routers under `/api`.
   - `backend/app/metaverse/` encapsulates all 3D spatial computing, point-cloud parsing, pathfinding, and vision processing away from standard CRUD routes.

2. **Frontend Application (`frontend/`)**:
   - Cleanly partitioned into markup (`index.html`), scripts (`src/js/`), and stylesheets (`src/styles/`).
   - Single point of entry for client-side logic in `app.js`, eliminating dual-maintenance or inline script drift.

3. **Data & Artifacts (`data/`)**:
   - Houses heavy binary datasets (point clouds, excel datasets, and raw models) separated from application code.
