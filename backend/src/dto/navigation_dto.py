"""Navigation contracts."""

from typing import List, Optional

from pydantic import BaseModel, Field


class NavigationRouteRequest(BaseModel):
    """Request pathfinding from avatar start position to an asset."""
    start: List[float] = Field(description="Current avatar 3D position [x, y, z]")
    target_asset_id: str = Field(description="Destination asset ID or tag")


class NavigationRouteResponse(BaseModel):
    """Obstacle-free collision-avoiding trajectory waypoints."""
    target_asset_id: str
    target_tag: str
    total_distance_m: float
    waypoints: List[List[float]] = Field(description="Ordered list of [x, y, z] navigation waypoints")


class Waypoint(BaseModel):
    x: float
    y: float = 0.0
    z: float


class NavigationPathResponse(BaseModel):
    """Collision-checked route from the entry (or a given start) to a standing spot beside the target."""

    target_id: str
    target_tag: Optional[str] = None
    target_pos: List[float]
    waypoints: List[Waypoint]
    total_distance_m: float
    estimated_walk_seconds: float
    collision_free: bool
    min_clearance_m: float
    robot_radius_m: float
    algorithm: str



class WalkableGridResponse(BaseModel):
    """Occupancy grid. Cell (i, j) covers x = x_min + i·cell, z = z_min + j·cell; layers are
    base64 bytes in row-major (i, j) order, index = i·nz + j, 1 = true."""

    x_min: float
    z_min: float
    cell: float
    nx: int
    nz: int
    reachable: str = Field(description="1 where the robot centre may stand (inflated by its radius)")
    blocked: str = Field(description="1 on obstacle cells (walls, equipment)")
