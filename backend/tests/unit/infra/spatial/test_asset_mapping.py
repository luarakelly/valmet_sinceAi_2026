"""Asset binding: camera evidence beats shape guesses, and nothing is forced onto the wrong object."""

from infra.spatial.asset_mapping import ASSUMED, CAMERA_VERIFIED, PROPOSED, Binding, Verified, attach_components, bind_assets
from infra.spatial.segmentation import SceneObject


def obj(number: int, label: str, x: float = 0.0) -> SceneObject:
    return SceneObject(
        object_id="OBJ-{:03d}".format(number), label=label, center=(x, 0.5, 0.0),
        size=(0.5, 0.5, 0.5), point_count=100, color=(0.5, 0.5, 0.5),
    )


def asset(asset_id: str, asset_class: str, health: int = 90) -> dict:
    return {"asset_id": asset_id, "tag": asset_id, "asset_class": asset_class, "state": {"health_score": health}}


def near(objects):
    ids = {o.object_id: 0.0 for o in objects}
    return ids, dict(ids)


def test_nothing_verified_keeps_the_shape_guess_but_labels_it_proposed():
    objects = [obj(1, "FLOOR_MOUNTED_MACHINE"), obj(2, "VALVE_ASSEMBLY", 3.0)]
    reach, walk = near(objects)
    bindings = bind_assets(objects, [asset("A1", "PROCESS_PUMP", 40)], "A1", reach, walk)
    assert bindings["OBJ-001"].status == PROPOSED


def test_a_verified_object_beats_a_better_looking_unverified_one():
    objects = [obj(1, "FLOOR_MOUNTED_MACHINE"), obj(2, "OVERHEAD_PIPE_RUN", 3.0)]
    reach, walk = near(objects)
    verified = {"OBJ-002": Verified("pump", "PROCESS_PUMP", 0.9, "casing on a base plate")}
    bindings = bind_assets(objects, [asset("A1", "PROCESS_PUMP", 40)], "A1", reach, walk, verified)
    assert set(bindings) == {"OBJ-002"}
    assert bindings["OBJ-002"].status == CAMERA_VERIFIED
    assert bindings["OBJ-002"].confidence == 0.9


def test_an_object_the_camera_says_is_a_pipe_is_never_given_to_a_pump():
    objects = [obj(1, "FLOOR_MOUNTED_MACHINE")]
    reach, walk = near(objects)
    verified = {"OBJ-001": Verified("pipe", None, 0.9, "curved pipe")}
    bindings = bind_assets(objects, [asset("A1", "PROCESS_PUMP", 95), asset("A2", "PROCESS_PUMP", 40)], "A2", reach, walk, verified)
    assert [b.status for b in bindings.values()] == [ASSUMED]  # only the inspection target is forced somewhere
    assert list(bindings.values())[0].asset["asset_id"] == "A2"


def test_assets_without_a_matching_object_stay_unlocated():
    objects = [obj(1, "VALVE_ASSEMBLY"), obj(2, "VALVE_ASSEMBLY", 3.0)]
    reach, walk = near(objects)
    verified = {
        "OBJ-001": Verified("control_valve", "CONTROL_VALVE", 0.8, "valve with actuator"),
        "OBJ-002": Verified("control_valve", "CONTROL_VALVE", 0.7, "valve with handwheel"),
    }
    assets = [asset("T", "CONTROL_VALVE", 30), asset("M1", "ELECTRIC_MOTOR"), asset("M2", "ELECTRIC_MOTOR")]
    bindings = bind_assets(objects, assets, "T", reach, walk, verified)
    assert {b.asset["asset_id"] for b in bindings.values()} == {"T"}


def test_unverified_objects_are_only_weak_guesses_once_camera_evidence_exists():
    objects = [obj(1, "FLOOR_MOUNTED_MACHINE"), obj(2, "VALVE_ASSEMBLY", 3.0)]
    reach, walk = near(objects)
    verified = {"OBJ-002": Verified("pipe", None, 0.9, "pipe")}
    bindings = bind_assets(objects, [asset("A1", "PROCESS_PUMP", 40)], "A1", reach, walk, verified)
    assert bindings["OBJ-001"].status == PROPOSED
    assert bindings["OBJ-001"].confidence <= 0.45


def test_every_unbound_object_joins_the_nearest_bound_assets_system():
    pump, valve = asset("ASSET-001", "PROCESS_PUMP"), asset("ASSET-002", "CONTROL_VALVE")
    objects = [obj(1, "FLOOR_MOUNTED_MACHINE", 0.0), obj(2, "VALVE_ASSEMBLY", 5.0), obj(3, "PIPE", 1.0), obj(4, "PIPE", 4.5)]
    bindings = {"OBJ-001": Binding(asset=pump, confidence=0.8), "OBJ-002": Binding(asset=valve, confidence=0.8)}

    links = attach_components(objects, bindings)

    assert set(links) == {"OBJ-003", "OBJ-004"}
    assert links["OBJ-003"].asset["asset_id"] == "ASSET-001"
    assert links["OBJ-004"].asset["asset_id"] == "ASSET-002"
    assert links["OBJ-004"].distance_m == 0.5


def test_no_bound_assets_means_no_components():
    assert attach_components([obj(1, "PIPE")], {}) == {}
