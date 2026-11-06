"""Web server and REST API for OptiShape 3D topology optimization."""

import json
import tempfile
import time
import uuid
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from app.three_d.config import (
    DEFAULT_ENABLE_GYROID,
    DEFAULT_ENABLE_OVERHANG,
    DEFAULT_LOAD_DIRECTION,
    DEFAULT_LOAD_MAGNITUDE,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_PRESERVE_MARGIN,
    DEFAULT_RESOLUTION,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DEFAULT_VOLUME_FRACTION,
    FORMAT_MEDIA_TYPES,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    MATERIALS,
    MAX_UPLOAD_SIZE_BYTES,
    PERCENTAGE_FACTOR,
    SUPPORT_MODE_CANTILEVER,
    SUPPORTED_INPUT_EXTENSIONS,
    VALID_EXPORT_FORMATS,
    VALID_LOAD_DIRECTIONS,
    VALID_SUPPORT_MODES,
)
from app.three_d.geometry import create_default_beam, export_mesh, load_mesh, reconstruct_surface
from app.three_d.pipeline import run_optimization_pipeline
from app.three_d.report import generate_html_report, generate_markdown_report


class JobStore:
    """Encapsulates in-memory job state and workspace directories without globals."""

    def __init__(self):
        self._jobs = {}
        self._temp_base = Path(tempfile.gettempdir()) / "optishape_jobs"

    def get_job_dir(self, job_id):
        job_dir = self._temp_base / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def register(self, job_id, material, volume, iterations):
        self._jobs[job_id] = {
            "id": job_id,
            "status": JOB_STATUS_RUNNING,
            "progress": 0,
            "iteration": 0,
            "max_iterations": iterations,
            "compliance": 0.0,
            "change": 0.0,
            "material": material,
            "volume": volume,
            "start_time": time.time(),
            "elapsed": 0.0,
            "error": None,
        }

    def get(self, job_id):
        return self._jobs.get(job_id)

    def update(self, job_id, **kwargs):
        job = self._jobs.get(job_id)
        if job is not None:
            job.update(kwargs)


def _handle_job_iteration(
    job_store, job_id, iterations, iter_num, compliance, change, densities=None, origin=None, pitch=None
):
    progress_pct = int(((iter_num + 1) / iterations) * PERCENTAGE_FACTOR)
    job_store.update(
        job_id,
        iteration=iter_num + 1,
        compliance=float(compliance),
        change=float(change),
        progress=progress_pct,
    )
    if densities is not None and origin is not None and pitch is not None:
        try:
            job_dir = job_store.get_job_dir(job_id)
            live_path = str(job_dir / "live.stl")
            live_mesh = reconstruct_surface(densities, origin, pitch, isovalue=0.25, smooth_iterations=1)
            if len(live_mesh.faces) > 0:
                export_mesh(live_mesh, live_path)
                job_store.update(job_id, has_live_mesh=True, live_iter=iter_num + 1)
        except (ValueError, RuntimeError, OSError):
            pass


def _prepare_job_input_mesh(job_store, job_id, input_path):
    job_dir = job_store.get_job_dir(job_id)
    if not input_path:
        input_path = str(job_dir / "input.stl")
        export_mesh(create_default_beam(), input_path)
    else:
        stl_path = job_dir / "input.stl"
        if not stl_path.exists():
            export_mesh(load_mesh(input_path), str(stl_path))
    return input_path


def _record_job_completion(job_store, job_id, result):
    job_store.update(
        job_id,
        status=JOB_STATUS_COMPLETED,
        progress=100,
        elapsed=result["elapsed_seconds"],
        metrics=result,
    )


def _parse_optional_json(json_str):
    if not json_str:
        return None
    try:
        return json.loads(json_str)
    except (ValueError, TypeError):
        return None


def _execute_optimization_job(
    job_store, job_id, input_path, material_name, target_volume, resolution,
    iterations, load_magnitude=DEFAULT_LOAD_MAGNITUDE,
    load_direction=DEFAULT_LOAD_DIRECTION, preserve_margin=DEFAULT_PRESERVE_MARGIN,
    enable_overhang=DEFAULT_ENABLE_OVERHANG, load_cases=None,
    support_mode=SUPPORT_MODE_CANTILEVER, enable_gyroid=DEFAULT_ENABLE_GYROID,
    custom_material=None, preserved_zones=None,
):
    output_stl = str(job_store.get_job_dir(job_id) / "optimized.stl")
    output_3mf = str(job_store.get_job_dir(job_id) / "optimized.3mf")
    input_path = _prepare_job_input_mesh(job_store, job_id, input_path)

    def on_iteration(iter_num, compliance, change, densities=None, origin=None, pitch=None):
        _handle_job_iteration(
            job_store, job_id, iterations, iter_num, compliance, change, densities, origin, pitch
        )

    try:
        optimization_result = run_optimization_pipeline(
            output_stl, input_path, material_name, target_volume,
            resolution, iterations, load_magnitude, load_direction,
            preserve_margin, enable_overhang, on_iteration,
            load_cases, support_mode, enable_gyroid, custom_material,
            preserved_zones,
        )
        export_mesh(load_mesh(output_stl), output_3mf)
        report_html = generate_html_report(optimization_result, job_id, material_name)
        (job_store.get_job_dir(job_id) / "report.html").write_text(report_html, encoding="utf-8")
        _record_job_completion(job_store, job_id, optimization_result)
    except (ValueError, RuntimeError, KeyError, OSError) as err:
        job_store.update(job_id, status=JOB_STATUS_FAILED, error=str(err))


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


app = FastAPI(title="OptiShape 3D API", version="0.1.0")
app.state.job_store = JobStore()
app.state.static_dir = Path(__file__).parent / "static"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/materials")
def api_get_materials():
    return {
        "materials": MATERIALS,
        "directions": VALID_LOAD_DIRECTIONS,
        "support_modes": list(VALID_SUPPORT_MODES),
        "supported_inputs": SUPPORTED_INPUT_EXTENSIONS,
        "supported_exports": VALID_EXPORT_FORMATS,
        "defaults": {
            "volume": DEFAULT_VOLUME_FRACTION,
            "resolution": DEFAULT_RESOLUTION,
            "iterations": DEFAULT_MAX_ITERATIONS,
            "load": DEFAULT_LOAD_MAGNITUDE,
            "direction": DEFAULT_LOAD_DIRECTION,
            "preserve_margin": DEFAULT_PRESERVE_MARGIN,
            "enable_overhang": DEFAULT_ENABLE_OVERHANG,
            "enable_gyroid": DEFAULT_ENABLE_GYROID,
            "support_mode": SUPPORT_MODE_CANTILEVER,
        },
    }


async def _save_uploaded_mesh(file, job_dir):
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file exceeds 50MB")
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in SUPPORTED_INPUT_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported format '{file_ext}'")
    input_target = job_dir / f"input{file_ext}"
    input_target.write_bytes(file_bytes)
    return str(input_target)


def _dispatch_job(background_tasks, job_store, job_id, input_path, job_params):
    job_store.register(job_id, job_params["material"], job_params["volume"], job_params["iterations"])
    background_tasks.add_task(
        _execute_optimization_job,
        job_store,
        job_id,
        input_path,
        job_params["material"],
        job_params["volume"],
        job_params["resolution"],
        job_params["iterations"],
        job_params["load"],
        job_params["direction"],
        job_params["preserve_margin"],
        job_params["enable_overhang"],
        job_params["load_cases"],
        job_params["support_mode"],
        job_params["enable_gyroid"],
        job_params["custom_material"],
        job_params["preserved_zones"],
    )


def _validate_job_params(material, custom_mat, direction, support_mode, volume=None, load=None):
    if material not in MATERIALS and custom_mat is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid material")
    if direction not in VALID_LOAD_DIRECTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid load direction")
    if support_mode not in VALID_SUPPORT_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid support mode")
    if volume is not None and (volume <= 0.0 or volume >= 1.0):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Volume fraction must be between 0.0 and 1.0")
    if load is not None and load <= 0.0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Applied load must be positive")


def _package_job_params(
    material, volume, resolution, iterations, load, direction,
    preserve_margin, enable_overhang, support_mode, enable_gyroid,
    load_cases, custom_material, preserved_zones,
):
    return {
        "material": material,
        "volume": volume,
        "resolution": resolution,
        "iterations": iterations,
        "load": load,
        "direction": direction,
        "preserve_margin": preserve_margin,
        "enable_overhang": enable_overhang,
        "support_mode": support_mode,
        "enable_gyroid": enable_gyroid,
        "load_cases": load_cases,
        "custom_material": custom_material,
        "preserved_zones": preserved_zones,
    }


@app.post("/api/jobs")
async def api_create_job(
    background_tasks: BackgroundTasks,
    job_store: Annotated[JobStore, Depends(get_job_store)],
    file: Annotated[UploadFile | None, File()] = None,
    material: Annotated[str, Form()] = "PLA",
    volume: Annotated[float, Form()] = DEFAULT_VOLUME_FRACTION,
    resolution: Annotated[int, Form()] = DEFAULT_RESOLUTION,
    iterations: Annotated[int, Form()] = DEFAULT_MAX_ITERATIONS,
    load: Annotated[float, Form()] = DEFAULT_LOAD_MAGNITUDE,
    direction: Annotated[str, Form()] = DEFAULT_LOAD_DIRECTION,
    preserve_margin: Annotated[int, Form()] = DEFAULT_PRESERVE_MARGIN,
    enable_overhang: Annotated[bool, Form()] = DEFAULT_ENABLE_OVERHANG,
    support_mode: Annotated[str, Form()] = SUPPORT_MODE_CANTILEVER,
    enable_gyroid: Annotated[bool, Form()] = DEFAULT_ENABLE_GYROID,
    load_cases_json: Annotated[str | None, Form()] = None,
    custom_material_json: Annotated[str | None, Form()] = None,
    preserved_zones_json: Annotated[str | None, Form()] = None,
):
    custom_mat = _parse_optional_json(custom_material_json)
    _validate_job_params(material, custom_mat, direction, support_mode, volume, load)
    job_id = str(uuid.uuid4())
    in_path = None
    if file:
        in_path = await _save_uploaded_mesh(file, job_store.get_job_dir(job_id))
    cases = _parse_optional_json(load_cases_json)
    zones = _parse_optional_json(preserved_zones_json)
    job_params = _package_job_params(
        material, volume, resolution, iterations, load,
        direction, preserve_margin, enable_overhang, support_mode,
        enable_gyroid, cases, custom_mat, zones,
    )
    _dispatch_job(background_tasks, job_store, job_id, in_path, job_params)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/report")
def api_get_job_report(
    job_id: str,
    format: str = "html",
    job_store: Annotated[JobStore, Depends(get_job_store)] = None,
):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    metrics = job.get("metrics")
    if not metrics:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not ready")
    mat_name = job.get("material", "PLA")
    if format.lower() == "md":
        content = generate_markdown_report(metrics, job_id, mat_name)
        return Response(content=content, media_type="text/markdown")
    content = generate_html_report(metrics, job_id, mat_name)
    return HTMLResponse(content=content)


@app.get("/api/jobs/{job_id}")
def api_get_job(job_id: str, job_store: Annotated[JobStore, Depends(get_job_store)]):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@app.get("/api/jobs/{job_id}/live")
def api_get_job_live(job_id: str, job_store: Annotated[JobStore, Depends(get_job_store)]):
    job_dir = job_store.get_job_dir(job_id)
    live_path = job_dir / "live.stl"
    if not live_path.exists():
        output_path = job_dir / "optimized.stl"
        if output_path.exists():
            live_path = output_path
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Live mesh not ready")
    return FileResponse(
        path=live_path,
        media_type="model/stl",
        filename=f"live_{job_id[:8]}.stl",
    )


@app.get("/api/jobs/{job_id}/output")
def api_get_job_output(job_id: str, job_store: Annotated[JobStore, Depends(get_job_store)]):
    output_path = job_store.get_job_dir(job_id) / "optimized.stl"
    if not output_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optimized mesh not ready")
    return FileResponse(
        path=output_path,
        media_type="model/stl",
        filename=f"optimized_{job_id[:8]}.stl",
    )


@app.get("/api/jobs/{job_id}/3mf")
def api_get_job_3mf(job_id: str, job_store: Annotated[JobStore, Depends(get_job_store)]):
    output_path = job_store.get_job_dir(job_id) / "optimized.3mf"
    if not output_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="3MF mesh not ready")
    return FileResponse(
        path=output_path,
        media_type="model/3mf",
        filename=f"optimized_{job_id[:8]}.3mf",
    )


@app.get("/api/jobs/{job_id}/export/{format_ext}")
def api_get_job_export(job_id: str, format_ext: str, job_store: Annotated[JobStore, Depends(get_job_store)]):
    fmt = format_ext.lower().lstrip(".")
    if fmt not in VALID_EXPORT_FORMATS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported export format '{fmt}'")
    job_dir = job_store.get_job_dir(job_id)
    target_path = job_dir / f"optimized.{fmt}"
    if not target_path.exists():
        src_path = job_dir / "optimized.ply"
        if not src_path.exists():
            src_path = job_dir / "optimized.stl"
        if not src_path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Optimized mesh not ready")
        export_mesh(load_mesh(str(src_path)), str(target_path))
    return FileResponse(
        path=target_path,
        media_type=FORMAT_MEDIA_TYPES.get(fmt, "application/octet-stream"),
        filename=f"optimized_{job_id[:8]}.{fmt}",
    )


@app.post("/api/preview")
async def api_preview_mesh(file: Annotated[UploadFile, File()]):
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in SUPPORTED_INPUT_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported format '{file_ext}'")
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file exceeds 50MB")

    temp_path = Path(tempfile.gettempdir()) / f"prev_{uuid.uuid4()}{file_ext}"
    try:
        temp_path.write_bytes(file_bytes)
        mesh = load_mesh(str(temp_path))
        stl_bytes = mesh.export(file_type="stl")
        return Response(content=stl_bytes, media_type="model/stl")
    finally:
        if temp_path.exists():
            temp_path.unlink()


@app.get("/api/jobs/{job_id}/input")
def api_get_job_input(
    job_id: str,
    format: str = "stl",
    job_store: Annotated[JobStore, Depends(get_job_store)] = None,
):
    job_dir = job_store.get_job_dir(job_id)
    stl_path = job_dir / "input.stl"
    if format == "stl" and stl_path.exists():
        return FileResponse(path=stl_path, media_type="model/stl", filename=f"input_{job_id[:8]}.stl")
    input_files = list(job_dir.glob("input.*"))
    if not input_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Input mesh not found")
    src = input_files[0]
    fmt = src.suffix.lower().lstrip(".")
    media_type = FORMAT_MEDIA_TYPES.get(fmt, "application/octet-stream")
    return FileResponse(path=src, media_type=media_type, filename=src.name)


@app.get("/", response_class=HTMLResponse)
def api_index():
    index_file = app.state.static_dir / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>OptiShape UI not found</h1>", status_code=status.HTTP_404_NOT_FOUND)
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


def start_server(host=DEFAULT_SERVER_HOST, port=DEFAULT_SERVER_PORT):
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
