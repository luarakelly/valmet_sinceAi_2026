# Stack

## Runtime

```text
Browser (FastAPI-served Three.js viewer) -> FastAPI -> SQLite
                                             |
                                             -> Gemini API
                                             |
                                             -> 3D / geometry tools
```

- **Active UI:** Three.js, HTML, and browser JavaScript served from `backend/app/three_d/static/index.html`.
- **Backend:** FastAPI served by Uvicorn. The entry point is `backend/app/main.py`; routes are in `backend/app/routes.py`.
- **Database:** SQLModel + SQLAlchemy over SQLite. Configuration is in `backend/app/db.py`.
- **AI:** Google Gemini via `google-genai`. The wrapper is `backend/app/gemini.py`; its instructions are in `backend/app/system_prompt.txt`.
- **Geometry:** NumPy, SciPy, Trimesh, and scikit-image support `backend/app/three_d/` and `backend/app/geometry_utils/`.
- **Data:** `data/` contains the source workbooks, challenge brief, and cached industrial data. A PLY scene asset is optional; the backend searches `data/` for it and reports a 404 when it is unavailable.

## Run

1. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`.
2. Run `initialize.sh` or `initialize.bat` once.
3. Run `run.sh` or `run.bat` to start the API.

The active AI path is **Gemini only**. The root scripts start the FastAPI/Uvicorn backend and serve the browser viewer.
