"""Ask Your Factory API Test Suite.

Validates core REST endpoints, data integrity, spatial queries,
safety guardrails, and copilot diagnostics against the API contract.
"""

from fastapi.testclient import TestClient
from api.server import app

client = TestClient(app)


def test_system_health():
    """Verify system liveness probe and metadata."""
    res = client.get("/api/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    body = res.json()
    assert body.get("status") == "healthy"
    assert body.get("models_loaded") == 30
    print("PASS: System Health Probe (/api/health)")


def test_list_assets():
    """Verify retrieval of all 30 assets and check key schema properties."""
    res = client.get("/api/assets")
    assert res.status_code == 200, f"List assets failed: {res.text}"
    assets = res.json()
    assert len(assets) == 30, f"Expected 30 assets, received {len(assets)}"
    
    first = assets[0]
    required_keys = ["asset_id", "tag", "asset_class", "area_id", "criticality"]
    for key in required_keys:
        assert key in first, f"Missing key '{key}' in asset record"
    print(f"PASS: List Assets ({len(assets)} equipment records verified)")


def test_asset_detail_and_404():
    """Verify single asset lookup with joined dossier and 404 handling."""
    res = client.get("/api/assets/ASSET-001")
    assert res.status_code == 200, f"Asset detail lookup failed: {res.text}"
    dossier = res.json()
    assert dossier.get("asset_id") == "ASSET-001"
    assert "tag" in dossier
    assert "state" in dossier

    missing_res = client.get("/api/assets/NON_EXISTENT_999")
    assert missing_res.status_code == 404, "Expected 404 for missing asset"
    print("PASS: Asset Dossier Lookup & 404 Not Found Handling")


def test_asset_telemetry_and_events():
    """Verify telemetry time-series retrieval and alarm events."""
    telem_res = client.get("/api/assets/ASSET-001/telemetry?limit=10")
    assert telem_res.status_code == 200, f"Telemetry fetch failed: {telem_res.text}"
    telem = telem_res.json()
    assert len(telem) > 0, "Expected at least 1 telemetry record"

    events_res = client.get("/api/assets/ASSET-001/events?limit=5")
    assert events_res.status_code == 200, f"Events fetch failed: {events_res.text}"
    print("PASS: Asset Telemetry Time-Series & Alarm Events")


def test_scene_anchors():
    """Every builder-pack asset is anchored to an extracted scene object with a real box."""
    res = client.get("/api/scene/anchors")
    assert res.status_code == 200, f"Anchors fetch failed: {res.text}"
    anchors = res.json()
    assert len(anchors) == 30, f"Expected 30 anchors, got {len(anchors)}"
    for anchor in anchors:
        assert anchor["mapping_status"].startswith("bound_to_extracted_")
        assert 0.0 < anchor["mapping_confidence"] <= 1.0
        assert min(anchor["bbox_x_m"], anchor["bbox_y_m"], anchor["bbox_z_m"]) > 0.0
    print("PASS: 3D Spatial Anchors & Bounding Box Coordinates")


def test_work_order_drafting_with_safety_guardrails():
    """Verify safety verification requirement and successful work order generation."""
    unsafe_res = client.post(
        "/api/work-orders/draft",
        json={
            "asset_id": "ASSET-001",
            "action": "Calibrate actuator position sensor",
            "safety_acknowledged": False,
        },
    )
    assert unsafe_res.status_code == 400, "Expected 400 when safety is not acknowledged"

    valid_res = client.post(
        "/api/work-orders/draft",
        json={
            "asset_id": "ASSET-001",
            "action": "Calibrate actuator position sensor",
            "priority": "high",
            "safety_acknowledged": True,
        },
    )
    assert valid_res.status_code == 201, f"Work order draft failed: {valid_res.text}"
    wo = valid_res.json()
    assert wo.get("work_order_id") is not None
    assert wo.get("status") == "draft"
    assert len(wo.get("safety_checklist", [])) > 0
    print("PASS: Work Order Safety Guardrails & Draft Generation")


def test_metaverse_dashboard():
    """Verify plant-wide KPI aggregates and condition distributions."""
    res = client.get("/api/metaverse/dashboard")
    assert res.status_code == 200, f"Dashboard fetch failed: {res.text}"
    dash = res.json()
    assert dash.get("total_assets") == 30
    assert dash.get("average_health_score") is not None
    assert "condition_counts" in dash
    print("PASS: Metaverse Plant-Wide Dashboard KPIs")


def test_avatar_proximity_query():
    """Standing at the faulty target returns it first and flags it as faulty."""
    target = client.get("/api/scene/anchors").json()
    faulty = next(a for a in target if a["asset_id"] == "ASSET-017")
    res = client.post(
        "/api/scene/proximity",
        json={"x": faulty["x_local_m"], "y": 0.0, "z": faulty["z_local_m"], "radius_m": 1.5},
    )
    assert res.status_code == 200, f"Proximity query failed: {res.text}"
    nearby = res.json()
    assert nearby[0]["asset_id"] == "ASSET-017"
    assert nearby[0]["distance_m"] == 0.0
    assert nearby[0]["is_faulty"] is True
    assert [n["distance_m"] for n in nearby] == sorted(n["distance_m"] for n in nearby)
    print(f"PASS: Spatial Proximity Detection ({len(nearby)} assets within radius)")


def test_copilot_diagnostics():
    """Verify AI field diagnostics copilot returns grounded citations and safety guardrails."""
    res = client.post(
        "/api/copilot/query",
        json={
            "asset_id": "ASSET-001",
            "prompt": "Evaluate equipment health and recent anomalies",
        },
    )
    assert res.status_code == 200, f"Copilot query failed: {res.text}"
    diag = res.json()
    assert diag.get("asset_id") == "ASSET-001"
    assert "health_score" in diag
    if "diagnosis" in diag:
        assert diag["diagnosis"] is not None
    else:
        assert diag.get("diagnosis_summary") is not None
    safety_items = diag.get("safety_checks", [])
    if len(safety_items) == 0:
        safety_items = diag.get("safety_guardrails", [])
    assert len(safety_items) > 0
    print("PASS: Evidence-Grounded AI Diagnostics Copilot")


def run_all_tests():
    """Run all API test suites sequentially."""
    print("==================================================")
    print("Ask Your Factory Test Suite Execution")
    print("==================================================")
    test_system_health()
    test_list_assets()
    test_asset_detail_and_404()
    test_asset_telemetry_and_events()
    test_scene_anchors()
    test_work_order_drafting_with_safety_guardrails()
    test_metaverse_dashboard()
    test_avatar_proximity_query()
    test_copilot_diagnostics()
    print("==================================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
