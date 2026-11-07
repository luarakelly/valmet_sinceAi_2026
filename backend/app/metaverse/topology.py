"""Process flow topology and connected equipment nervous system.

Reconstructs the industrial process flow circuits linking pumps, motors,
valves, and transmitters within the 3D boiler room. Maps physical fluid
lines and models fault propagation across connected equipment.
"""

from dataclasses import asdict, dataclass
import math
from typing import Any, Dict, List, Optional, Tuple

FLOW_HEALTH_THRESHOLD = 70
DEFAULT_ELEVATION_OFFSET_M = 0.25

HEX_COLOR_HEALTHY = "#00d2ff"
HEX_COLOR_WARNING = "#f59e0b"
HEX_COLOR_CRITICAL = "#ef4444"


@dataclass(frozen=True)
class ProcessNode:
    """One equipment node within a process circuit."""

    asset_id: str
    tag: str
    asset_class: str
    role_in_loop: str
    health: int
    state: str
    issue_code: str
    pos: Tuple[float, float, float]
    is_fault_origin: bool
    is_impacted: bool


@dataclass(frozen=True)
class ProcessFlowLoop:
    """A functional process circuit connecting multiple industrial assets."""

    loop_id: str
    name: str
    area_name: str
    process_context: str
    has_fault: bool
    status: str
    fault_summary: str
    flow_rate_pct: float
    nodes: List[ProcessNode]
    path_3d: List[Tuple[float, float, float]]
    line_color: str


LOOP_DEFINITIONS = (
    {
        "loop_id": "LOOP-UTILITY",
        "name": "Utility Steam & Feedwater Circulation Loop",
        "area_name": "Utility Island",
        "process_context": "utilities",
        "sequence": (
            ("ASSET-020", "Driver Motor"),
            ("ASSET-017", "Primary Feed Pump"),
            ("ASSET-026", "Discharge Pressure Transmitter"),
            ("ASSET-009", "Pressure Regulating Valve"),
            ("ASSET-006", "Header Isolation Valve"),
            ("ASSET-001", "Terminal Delivery Valve"),
        ),
        "fault_origin_id": "ASSET-017",
        "fault_summary": "P-005 fouling drops feed flow -8.7%, destabilizing PT-002 pressure and inducing CV-009 position deviation",
    },
    {
        "loop_id": "LOOP-CHEM-PREP",
        "name": "Chemical Dosing & Injection Loop",
        "area_name": "Chemical Preparation",
        "process_context": "wet_process",
        "sequence": (
            ("ASSET-021", "Driver Motor"),
            ("ASSET-016", "Metering Feed Pump"),
            ("ASSET-014", "Dosing Injection Pump"),
            ("ASSET-027", "Line Pressure Transmitter"),
            ("ASSET-003", "Dosing Control Valve"),
            ("ASSET-011", "Injection Control Valve"),
            ("ASSET-028", "Skid Vibration Sensor 1"),
            ("ASSET-029", "Skid Vibration Sensor 2"),
            ("ASSET-030", "Skid Vibration Sensor 3"),
        ),
        "fault_origin_id": "ASSET-014",
        "fault_summary": "P-002 cavitation instability creates mechanical shock detected at VS-002 with CV-003 position drift",
    },
    {
        "loop_id": "LOOP-STOCK-PREP",
        "name": "Pulp Stock Refining & Feed Loop",
        "area_name": "Stock Preparation",
        "process_context": "wet_process",
        "sequence": (
            ("ASSET-024", "Refiner Drive Motor"),
            ("ASSET-022", "Auxiliary Pump Motor"),
            ("ASSET-015", "Stock Transfer Pump"),
            ("ASSET-002", "Consistency Control Valve"),
            ("ASSET-007", "Stock Proportioning Valve"),
            ("ASSET-012", "Refiner Bypass Valve"),
        ),
        "fault_origin_id": "ASSET-024",
        "fault_summary": "M-006 sustained overheating and M-004 current imbalance threaten unannounced stock feed starvation",
    },
    {
        "loop_id": "LOOP-MACHINE-HALL",
        "name": "Paper Machine Steam & Condensate Loop",
        "area_name": "Machine Hall",
        "process_context": "continuous_process",
        "sequence": (
            ("ASSET-019", "Main Drive Motor"),
            ("ASSET-023", "Condensate Motor"),
            ("ASSET-018", "Condensate Return Pump"),
            ("ASSET-004", "Main Steam Header Valve"),
            ("ASSET-008", "Dryer Section Control Valve"),
            ("ASSET-010", "Condensate Return Valve"),
            ("ASSET-005", "Exhaust Bypass Valve"),
        ),
        "fault_origin_id": "ASSET-023",
        "fault_summary": "M-005 current imbalance combined with M-001 coupling misalignment threatens dryer thermal stability",
    },
    {
        "loop_id": "LOOP-WATER-TREAT",
        "name": "Effluent Clarification & Water Treatment Loop",
        "area_name": "Water Treatment",
        "process_context": "utilities",
        "sequence": (
            ("ASSET-013", "Effluent Circulation Pump"),
            ("ASSET-025", "Header Pressure Transmitter"),
        ),
        "fault_origin_id": "ASSET-013",
        "fault_summary": "P-001 rotating-equipment misalignment induces mechanical vibration into PT-001 header",
    },
)


def _find_frame(frames: List[Dict[str, Any]], asset_id: str) -> Optional[Dict[str, Any]]:
    for frame in frames:
        if frame.get("asset_id") == asset_id:
            return frame
    return None


def _build_smooth_path(points: List[Tuple[float, float, float]]) -> List[Tuple[float, float, float]]:
    """Builds an elevated 3D pipe routing path connecting sequence nodes."""
    if len(points) < 2:
        return points

    path: List[Tuple[float, float, float]] = []
    for idx in range(len(points) - 1):
        p1 = points[idx]
        p2 = points[idx + 1]
        mid_y = max(p1[1], p2[1]) + DEFAULT_ELEVATION_OFFSET_M

        path.append(p1)
        # Add elevated pipe elbows to simulate real overhead piping runs
        path.append((p1[0], mid_y, p1[2]))
        path.append((p2[0], mid_y, p2[2]))

    path.append(points[-1])
    return path


def build_process_topology(frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Constructs the complete process topology with 3D routes and node metadata."""
    loops_result: List[Dict[str, Any]] = []

    for loop_def in LOOP_DEFINITIONS:
        nodes: List[ProcessNode] = []
        raw_positions: List[Tuple[float, float, float]] = []
        has_critical_fault = False
        lowest_health = 100

        fault_origin_id = loop_def["fault_origin_id"]

        for asset_id, role in loop_def["sequence"]:
            frame = _find_frame(frames, asset_id)
            if frame is None:
                continue

            health = int(frame.get("health", 100))
            state = str(frame.get("state", "healthy"))
            issue_code = str(frame.get("issue_code", "NORMAL"))
            pos = tuple(frame.get("pos", (0.0, 0.0, 0.0)))

            if health < lowest_health:
                lowest_health = health

            is_origin = False
            if asset_id == fault_origin_id:
                is_origin = True

            is_impacted = False
            if health < FLOW_HEALTH_THRESHOLD:
                has_critical_fault = True
                is_impacted = True

            node = ProcessNode(
                asset_id=asset_id,
                tag=str(frame.get("tag", asset_id)),
                asset_class=str(frame.get("class", "EQUIPMENT")),
                role_in_loop=role,
                health=health,
                state=state,
                issue_code=issue_code,
                pos=pos,
                is_fault_origin=is_origin,
                is_impacted=is_impacted,
            )
            nodes.append(node)
            raw_positions.append(pos)

        if not nodes:
            continue

        loop_status = "NORMAL"
        line_color = HEX_COLOR_HEALTHY
        flow_rate = 98.4

        if has_critical_fault:
            loop_status = "DEGRADED"
            line_color = HEX_COLOR_WARNING
            flow_rate = 82.1
            if lowest_health < 50:
                loop_status = "CRITICAL_FLOW_STARVATION"
                line_color = HEX_COLOR_CRITICAL
                flow_rate = 68.3

        path_3d = _build_smooth_path(raw_positions)

        loop_obj = ProcessFlowLoop(
            loop_id=loop_def["loop_id"],
            name=loop_def["name"],
            area_name=loop_def["area_name"],
            process_context=loop_def["process_context"],
            has_fault=has_critical_fault,
            status=loop_status,
            fault_summary=loop_def["fault_summary"],
            flow_rate_pct=flow_rate,
            nodes=nodes,
            path_3d=path_3d,
            line_color=line_color,
        )
        loops_result.append(asdict(loop_obj))

    return loops_result


def get_asset_flow_context(asset_id: str, frames: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Returns the process loop context and upstream/downstream neighbors for an asset."""
    all_loops = build_process_topology(frames)

    for loop in all_loops:
        node_ids = [n["asset_id"] for n in loop["nodes"]]
        if asset_id not in node_ids:
            continue

        idx = node_ids.index(asset_id)
        current_node = loop["nodes"][idx]

        upstream_node = None
        if idx > 0:
            upstream_node = loop["nodes"][idx - 1]

        downstream_node = None
        if idx < len(loop["nodes"]) - 1:
            downstream_node = loop["nodes"][idx + 1]

        # Calculate isolation point for Lockout/Tagout (LOTO)
        isolation_valve = None
        for n in loop["nodes"]:
            if "VALVE" in n["asset_class"]:
                isolation_valve = n
                break

        electrical_breaker = None
        for n in loop["nodes"]:
            if "MOTOR" in n["asset_class"]:
                electrical_breaker = n
                break

        isolation_text = "Adhere to standard plant permit-to-work and lockout procedures."
        if isolation_valve is not None and electrical_breaker is not None:
            valve_tag = isolation_valve["tag"]
            motor_tag = electrical_breaker["tag"]
            isolation_text = (
                f"Close and tag manual valve {valve_tag} if mechanical servicing. "
                f"Lock out breaker switch on {motor_tag} before motor casing disassembly."
            )

        return {
            "loop_id": loop["loop_id"],
            "loop_name": loop["name"],
            "area_name": loop["area_name"],
            "process_context": loop["process_context"],
            "loop_status": loop["status"],
            "flow_rate_pct": loop["flow_rate_pct"],
            "line_color": loop["line_color"],
            "fault_summary": loop["fault_summary"],
            "current_node": current_node,
            "upstream_node": upstream_node,
            "downstream_node": downstream_node,
            "sequence_position": f"{idx + 1} of {len(loop['nodes'])}",
            "safety_loto": {
                "mechanical_isolation": isolation_valve,
                "electrical_isolation": electrical_breaker,
                "isolation_instructions": isolation_text,
            },
        }

    return None
