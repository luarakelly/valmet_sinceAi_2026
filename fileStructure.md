# File Structure

```text
.
├── README.md                         # Project overview
├── stack.md                          # Architecture and technology map
├── .env.example                      # Local Gemini/database configuration template
├── .gitignore                        # Secrets, environments, caches, and build output
├── initialize.sh / initialize.bat    # Create uv environment and install backend dependencies
├── run.sh / run.bat                  # Start FastAPI with Uvicorn
├── data/
│   ├── valmet_builder_pack.xlsx      # Source industrial metadata
│   ├── Valmet_SinceAI_2026_Synthetic_Industrial_Metaverse_Builder_Pack (1) (2) (1).xlsx
│   ├── Valmet_x_SinceAI_2026_Challenge_Brief_FINAL_updated (1).docx
│   └── metaverse_cache.json          # Cached industrial data
├── backend/
│   ├── requirements.txt              # Python dependencies, including Gemini
│   ├── test_routes.py                # API and data-integrity tests
│   ├── test_acceptance.py             # End-to-end API acceptance test
│   └── app/
│       ├── main.py                   # FastAPI application entry point
│       ├── routes.py                  # Primary REST endpoints
│       ├── metaverse/                 # Scene, copilot, and data-pack routes
│       ├── gemini.py                 # Gemini client wrapper
│       ├── system_prompt.txt         # AI behavior instructions
│       ├── database.py / db.py        # Database setup and sessions
│       ├── db_create.py               # Database creation utility
│       ├── models.py / schemas.py    # SQLModel and API data contracts
│       ├── crud.py                   # Database operations
│       ├── geometry_utils/            # Mesh analysis and reports
│       ├── three_d/                   # 3D geometry, FEA, optimization, and server
│       │   └── static/                # Active Three.js viewer
│       └── __init__.py                # 3D package marker
```

The active runtime path is: `run.*` -> `backend/app/main.py` -> FastAPI routes -> Gemini, SQLite, and 3D modules. The root route serves the Three.js viewer from `backend/app/three_d/static/index.html`.
