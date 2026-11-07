from fastapi.testclient import TestClient

from api.server import app


client = TestClient(app)


def test_industrial_metaverse_acceptance_flow():
    page = client.get("/")
    assert page.status_code == 200
    assert "canvas-container" in page.text
    assert "checkProximityEvents" in page.text
    assert "btn-cam-free" in page.text

    ply = client.get("/api/scene/boiler-room.ply")
    assert ply.status_code == 200
    assert ply.content.startswith(b"ply")

    frames_response = client.get("/api/scene/frames")
    assert frames_response.status_code == 200
    frames = frames_response.json()
    asset_frames = [frame for frame in frames if frame.get("asset_id")]
    assert len(asset_frames) >= 20
    assert all(frame.get("scene_id") for frame in asset_frames)
    assert all(frame.get("mapped_asset") for frame in asset_frames)
    assert all(len(frame.get("size", [])) == 3 for frame in asset_frames)

    assets = client.get("/api/assets").json()
    faulty = next(
        asset
        for asset in assets
        if (asset.get("state") or {}).get("condition_state")
        in {"attention_required", "degraded", "watch"}
    )
    asset_id = faulty["asset_id"]

    route = client.get("/api/navigation/path", params={"target_id": asset_id})
    assert route.status_code == 200
    route_data = route.json()
    assert route_data["target_id"] == asset_id
    assert len(route_data["waypoints"]) >= 2
    assert route_data["collision_free"] is True
    assert route_data["min_clearance_m"] >= route_data["robot_radius_m"] - 0.04

    diagnosis = client.post(
        "/api/copilot/query",
        json={"asset_id": asset_id, "query": "What should I inspect first?"},
    )
    assert diagnosis.status_code == 200
    diagnosis_data = diagnosis.json()
    assert diagnosis_data["asset_id"] == asset_id
    assert diagnosis_data["evidence_citations"]
    assert diagnosis_data["recommended_actions"]
    assert diagnosis_data["safety_checks"]
