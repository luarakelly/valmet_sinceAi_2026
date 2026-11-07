"""The photoreal export keeps splats in the same canonical frame as the point cloud."""

import numpy as np

from infra.spatial import point_cloud as pc
from infra.spatial import splat_export as se


def _matrix(q):
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def test_rotation_matches_position_flip():
    rng = np.random.default_rng(0)
    q = rng.normal(size=(8, 4))
    q /= np.linalg.norm(q, axis=1)[:, None]
    flip = np.diag([1.0, -1.0, -1.0])
    for raw, out in zip(q, se.rotate_180_about_x(q)):
        assert np.allclose(flip @ _matrix(raw), _matrix(out))


def test_export_uses_canonical_frame(tmp_path):
    rng = np.random.default_rng(1)
    n = 5000
    names = ["x", "y", "z", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3",
             "f_dc_0", "f_dc_1", "f_dc_2", "opacity"]
    data = np.zeros(n, dtype=[(k, "<f4") for k in names])
    xyz = rng.uniform([-4, -3, -2], [4, 0.2, 2], size=(n, 3))
    xyz[: n // 3, 1] = 0.2  # dense floor layer (raw frame is Y-down)
    for i, k in enumerate("xyz"):
        data[k] = xyz[:, i]
    for k in ("scale_0", "scale_1", "scale_2"):
        data[k] = np.log(0.02)
    data["rot_0"] = 1.0
    data["opacity"] = 3.0
    raw = tmp_path / "raw.ply"
    header = "ply\nformat binary_little_endian 1.0\nelement vertex {}\n".format(n)
    header += "".join("property float {}\n".format(k) for k in names) + "end_header\n"
    with open(raw, "wb") as handle:
        handle.write(header.encode("ascii"))
        data.tofile(handle)

    out = se.build_viewer_splat(raw, tmp_path / "scene.splat")
    records = np.fromfile(out, dtype=se.SPLAT_DTYPE)
    assert out.stat().st_size == 32 * len(records)

    columns = pc._read_ply(raw)
    confident, _ = pc._confident_splats(columns)
    expected, inside = pc.canonical_transform(confident)(xyz.astype(np.float64))
    assert np.allclose(np.sort(expected[inside][:, 0]), np.sort(records["position"][:, 0]), atol=1e-4)
    assert abs(np.percentile(records["position"][:, 1], 5)) < 0.05  # floor at y = 0
