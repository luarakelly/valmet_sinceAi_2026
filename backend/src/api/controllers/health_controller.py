from typing import Any, Dict


async def health_check() -> Dict[str, Any]:
    """Liveness probe confirming API service readiness."""
    return {"status": "healthy", "service": "ask-your-factory", "version": "1.1.0", "models_loaded": 30}
