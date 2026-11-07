"""Scene contracts: proximity queries."""


from pydantic import BaseModel
from dto.asset_dto import SceneAnchorRead


class ProximityQueryRequest(BaseModel):
    """Query nearby assets relative to avatar position."""
    x: float
    y: float
    z: float
    radius_m: float = 3.0


class ProximityAssetResponse(BaseModel):
    """Asset within avatar interaction radius with fault status."""
    asset_id: str
    tag: str
    distance_m: float
    health_score: float
    condition_state: str
    issue_code: str
    is_faulty: bool
    anchor: SceneAnchorRead
