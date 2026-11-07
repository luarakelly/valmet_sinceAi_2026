# File structure

```text
valmet_sinceAi_2026/
├── backend/
│   ├── src/
│   │   ├── main.py                         # python backend/src/main.py → uvicorn api.server:app
│   │   ├── api/                            # driving adapter (HTTP)
│   │   │   ├── server.py                   # FastAPI app, startup, static frontend at /
│   │   │   ├── container.py                # composition root
│   │   │   ├── routes.py                   # all /api endpoints → controllers
│   │   │   └── controllers/                # asset, scene, navigation, copilot, work_order,
│   │   │                                   # dashboard, maintenance, vision, verification,
│   │   │                                   # health, errors
│   │   ├── dto/                            # API contracts (Pydantic)
│   │   │   ├── asset_dto.py  scene_dto.py  navigation_dto.py  copilot_dto.py
│   │   │   └── work_order_dto.py  dashboard_dto.py  maintenance_dto.py
│   │   │       vision_dto.py  common_dto.py
│   │   ├── business/
│   │   │   ├── errors.py
│   │   │   ├── models/records.py           # record types exchanged across ports
│   │   │   ├── interfaces/ports/outbound/  # asset_repository, scene_engine, language_model,
│   │   │   │                               # visual_detector, verification_store (inbound/ empty)
│   │   │   └── services/                   # asset, scene, navigation, copilot (+ drift),
│   │   │                                   # work_order, dashboard, maintenance, vision, verification
│   │   └── infra/
│   │       ├── paths.py                    # repo / data / frontend locations
│   │       ├── db/sqlmodel/                # tables.py, database.py (engine + seed), repositories/
│   │       ├── importers/workbook/dataset.py
│   │       ├── spatial/                    # point_cloud, segmentation, navigation,
│   │       │                               # asset_mapping, splat_mesh, splat_export,
│   │       │                               # verification_store, scene_pipeline
│   │       ├── llm/                        # gemini, claude, build_language_model()
│   │       └── vision/yolo_world_detector.py
│   ├── tests/
│   │   ├── unit/business/                  # services with in-memory fakes
│   │   ├── unit/infra/spatial/             # extraction density, canonical frame, routes,
│   │   │                                   # asset mapping, splat export
│   │   └── integration/api/                # HTTP contract + end-to-end acceptance
│   ├── conftest.py   requirements.txt
├── frontend/                               # index.html, src/js/bootstrap.js (Three.js + Spark),
│                                           # src/js/app.js, src/styles/app.css
├── data/                                   # viewer PLY, mesh, .splat (tracked), workbook, cache,
│   │                                       # object_verification.json (camera verdicts);
│   ├── input/                              #   raw 355 MB splat (ignored)
│   └── weights/                            #   YOLO weights (ignored, auto-download)
├── scripts/                                # build_splat.py, build_mesh.py, seed_database.py
├── docs/
├── initialize.sh/.bat   run.sh/.bat
└── README.md
```
