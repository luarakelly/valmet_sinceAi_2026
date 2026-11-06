# Project Structure & Architecture

```text
valmet_sinceAi_2026/
├── backend/                               # Python FastAPI backend service
│   ├── app/
│   │   ├── main.py                        # FastAPI entry point, lifecycle, routing & static mounts
│   │   ├── routes.py                      # REST API router mounted at /api
│   │   ├── models.py                      # SQLModel relational schema (AssetMaster, Telemetry, WorkOrder, etc.)
│   │   ├── schemas.py                     # Pydantic request/response validation schemas
│   │   ├── crud.py                        # Database access & query routines
│   │   ├── database.py                    # Engine configuration, session generators & initial data seed
│   │   └── metaverse/                     # Digital Twin spatial & AI reasoning package
│   │       ├── dataset.py                 # Builder pack loader (JSON cache or Excel)
│   │       ├── point_cloud.py             # Raw splat → canonical Y-up cloud + viewer PLY export
│   │       ├── segmentation.py            # Voxel segmentation, splitting & geometric labelling
│   │       ├── navigation.py              # Occupancy grid, A*, measured clearance
│   │       ├── asset_mapping.py           # Builder-pack assets → extracted objects (+confidence)
│   │       ├── scene_processor.py         # Orchestrates the scene pipeline, serves frames/routes
│   │       ├── vision.py                  # Open-vocabulary YOLO-World visual detector
│   │       └── copilot.py                 # Evidence engine + citation-verified Gemini layer
│   ├── database.db                        # SQLite local runtime database
│   ├── requirements.txt                   # Backend Python package specifications
│   ├── conftest.py                        # Tests run on a fresh temporary database
│   ├── test_routes.py                     # API contract tests
│   ├── test_scene.py                      # Extraction density, canonical frame, navigation guarantees
│   ├── test_copilot.py                    # Drift detection, citation grounding, confidence
│   └── test_acceptance.py                 # End-to-end demo flow
│
├── frontend/                              # Frontend single-page application
│   ├── index.html                         # Primary HTML5 shell & viewport layout
│   ├── public/                            # Static public assets served at /public
│   └── src/
│       ├── js/
│       │   └── app.js                     # Three.js 3D viewport, Gaussian splat shader, HUD & UI logic
│       └── styles/
│           └── app.css                    # Industrial dark theme design system & UI stylesheets
│
├── data/                                  # Spatial models, challenge documents & data packs
│   ├── Industrial Boiler Room.ply         # Raw 3D Gaussian Splat scan (~339 MB)
│   ├── Industrial_Boiler_Room_standard.ply# Canonical (Y-up, floor 0) viewer cloud, generated from the raw splat
│   ├── metaverse_cache.json               # Precomputed industrial data cache
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
   - `backend/app/main.py`: Launches FastAPI, mounts static frontend assets (`/js`, `/styles`, `/public`), and seeds database on startup.
   - `backend/app/routes.py`: API contract endpoints plus scene, navigation and copilot routes under `/api`.
   - `backend/app/metaverse/`: Scene pipeline (144 framed objects, 30 bound assets), obstacle-aware A* with measured clearance, and evidence-grounded AI copilot.

2. **Frontend Application (`frontend/`)**:
   - Modularized into `index.html`, `src/js/app.js`, and `src/styles/app.css`.
   - Three.js WebGL viewport with smooth Gaussian splat shader blending, dynamic bounding box frames, inspection robot avatar, and interactive omnibar.

3. **Data & Artifacts (`data/`)**:
   - Cleanly separated from application source code.
