"""Path briefings, box-edge proximity and context for structures without an Excel row."""

from app.metaverse.briefings import build_briefings, find_encounters
from app.metaverse.copilot import FieldServiceCopilot
from app.metaverse.dataset import get_dataset
from app.metaverse.navigation import PROXIMITY_RADIUS_M, box_edge_distance_m
from app.metaverse.scene_processor import get_scene


def _offline_copilot() -> FieldServiceCopilot:
    copilot = FieldServiceCopilot()
    copilot.api_key = None
    return copilot


def test_box_edge_distance_is_zero_inside_and_measured_to_the_edge_outside():
    center, size = [0.0, 0.5, 0.0], [2.0, 1.0, 1.0]
    assert box_edge_distance_m(0.5, 0.2, center, size) == 0.0
    assert box_edge_distance_m(2.0, 0.0, center, size) == 1.0
    assert round(box_edge_distance_m(2.0, 1.5, center, size), 3) == round((1.0**2 + 1.0**2) ** 0.5, 3)


def test_nearby_is_measured_to_the_box_edge():
    scene = get_scene()
    frame = scene.frames[0]
    x, _, z = frame["pos"]
    hits = scene.nearby(x, z)
    assert frame["id"] in {hit["id"] for hit in hits}
    assert all(hit["distance_m"] <= PROXIMITY_RADIUS_M for hit in hits)


def test_encounters_follow_the_route_in_walking_order():
    scene = get_scene()
    route = scene.get_navigation_path()
    encounters = find_encounters(scene.frames, route["waypoints"])
    assert encounters
    progress = [e["progress"] for e in encounters]
    assert progress == sorted(progress)
    assert all(0.0 <= p <= 1.0 for p in progress)
    assert all(e["distance_m"] <= PROXIMITY_RADIUS_M for e in encounters)


def test_every_briefing_has_text_and_the_target_is_among_them():
    scene = get_scene()
    route = scene.get_navigation_path()
    briefings = build_briefings(scene.frames, route["waypoints"], get_dataset().get_assets(), _offline_copilot())
    assert briefings
    assert all(b["text"] and b["tag"] in b["text"] for b in briefings)
    assert not any(b["is_generated"] for b in briefings)
    assert any(b["is_target"] for b in briefings)


def test_structures_without_an_excel_row_carry_the_nearest_assets_context():
    frames = get_scene().frames
    unmapped = [f for f in frames if not f["asset_id"]]
    assert unmapped
    assert all(f["context"] and f["context"]["tag"] in f["context"]["summary"] for f in unmapped)
    assert all(f["context"] is None for f in frames if f["asset_id"])


def test_obstacle_grid_matches_its_declared_size():
    grid = get_scene().get_obstacle_grid()
    assert len(grid["cells"]) == grid["cols"] * grid["rows"]
    assert set(grid["cells"]) <= {0, 1, 2}
