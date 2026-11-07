import math

import numpy as np

from infra.labeling.camera_rig import EYE_HEIGHT_M, YAWS_PER_STATION, plan_views
from infra.labeling.vocabulary import VOCABULARY, prompt_text, term_for_phrase
from infra.spatial.navigation import CELL, OccupancyGrid


def open_room_grid() -> OccupancyGrid:
    reachable = np.zeros((125, 100), dtype=bool)
    reachable[5:120, 5:95] = True
    return OccupancyGrid(x_min=0.0, z_min=0.0, clearance=reachable.astype(float), reachable=reachable)


def test_views_stand_on_reachable_floor_at_eye_height():
    grid = open_room_grid()
    views = plan_views(grid, count=40)
    assert 20 <= len(views) <= 50
    for view in views:
        assert grid.is_reachable(view.eye[0], view.eye[2])
        assert view.eye[1] == EYE_HEIGHT_M


def test_views_look_outward_in_several_directions():
    views = plan_views(open_room_grid(), count=40)
    yaws = {round(math.degrees(math.atan2(v.target[0] - v.eye[0], v.target[2] - v.eye[2]))) % 360 for v in views}
    assert len(yaws) >= YAWS_PER_STATION


def test_plan_is_deterministic_and_ids_unique():
    first = plan_views(open_room_grid())
    assert first == plan_views(open_room_grid())
    assert len({v.view_id for v in first}) == len(first)


def test_no_reachable_cells_gives_no_views():
    grid = OccupancyGrid(0.0, 0.0, np.zeros((4, 4)), np.zeros((4, 4), dtype=bool))
    assert plan_views(grid) == []


def test_vocabulary_covers_every_pack_asset_class_and_spec_prompts():
    classes = {term.asset_class for term in VOCABULARY}
    assert {"CONTROL_VALVE", "PROCESS_PUMP", "ELECTRIC_MOTOR", "PRESSURE_TRANSMITTER", "VIBRATION_SENSOR"} <= classes
    prompts = prompt_text().removesuffix(" .").split(" . ")
    for needed in ("crate", "pipe", "valve", "fire extinguisher", "pallet", "hazard sign"):
        assert needed in prompts
    assert prompt_text().endswith(" .")


def test_phrase_maps_back_to_term_even_for_fragments():
    assert term_for_phrase("Electric motor").label == "ELECTRIC_MOTOR"
    assert term_for_phrase("extinguisher").label == "FIRE_EXTINGUISHER"
    assert term_for_phrase("banana") is None
