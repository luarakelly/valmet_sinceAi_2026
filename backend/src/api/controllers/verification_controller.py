from typing import Any, Dict

from fastapi import Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from api.container import Container, get_container
from api.controllers.errors import http_errors


async def verify_object(
    id: str,
    file: UploadFile = File(...),
    app: Container = Depends(get_container),
) -> Dict[str, Any]:
    """A render of one scene object → what a vision-language model says it is (stored as evidence)."""
    image = await file.read()
    with http_errors():
        # The model call blocks for seconds: keep it off the event loop so the server stays responsive.
        return await run_in_threadpool(app.verification.verify, id, image, file.content_type or "")


def list_verification(app: Container = Depends(get_container)) -> Dict[str, Dict[str, Any]]:
    """Stored camera verifications keyed by scene object id."""
    return app.verification.all()


def reset_verification(app: Container = Depends(get_container)) -> Dict[str, str]:
    app.verification.reset()
    return {"status": "cleared"}
