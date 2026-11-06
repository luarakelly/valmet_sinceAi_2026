from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile
import numpy as np
import trimesh
from skimage import measure

from app.three_d.config import (
    COLORMAP_BAND_HALF,
    COLORMAP_BAND_QUARTER,
    COLORMAP_BAND_THREE_QUARTERS,
    COLORMAP_MAX_COLOR_VALUE,
    COLORMAP_TINT_WEIGHT,
    DEFAULT_BEAM_EXTENTS,
    DEFAULT_CYLINDER_RADIUS_MM,
    DEFAULT_EPSILON,
    DEFAULT_GYROID_CELL_SIZE_MM,
    DEFAULT_SMOOTH_ITERATIONS,
    DEFAULT_SPHERE_RADIUS_MM,
    DEFAULT_SURFACE_ISOVALUE,
    GYROID_CLIP_AMPLITUDE,
    GYROID_DENSITY_LOWER_THRESHOLD,
    GYROID_DENSITY_UPPER_THRESHOLD,
    GYROID_MIN_RELATIVE_DENSITY,
    GYROID_SCALE_FACTOR,
    PADDING_WIDTH_MARCHING_CUBES,
    VOXEL_CENTER_OFFSET,
    ZONE_SHAPE_BOX,
    ZONE_SHAPE_CYLINDER,
    ZONE_SHAPE_SPHERE,
    ZONE_TYPE_KEEP_IN,
    ZONE_TYPE_KEEP_OUT,
)


def create_default_beam():
    return trimesh.creation.box(extents=DEFAULT_BEAM_EXTENTS)


def repair_mesh(mesh):
    trimesh.repair.fix_normals(mesh)
    trimesh.repair.fix_inversion(mesh)
    trimesh.repair.fill_holes(mesh)
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    return mesh


def _parse_3mf_fallback(tree):
    vertices = []
    faces = []
    for elem in tree.iter():
        tag_name = elem.tag.split("}")[-1]
        if tag_name == "vertex":
            vertices.append([float(elem.attrib["x"]), float(elem.attrib["y"]), float(elem.attrib["z"])])
        elif tag_name == "triangle":
            faces.append([int(elem.attrib["v1"]), int(elem.attrib["v2"]), int(elem.attrib["v3"])])
    return vertices, faces


def _parse_3mf_mesh_element(elem, vertex_offset):
    mesh_vertices = []
    mesh_faces = []
    for child in elem:
        child_tag = child.tag.split("}")[-1]
        if child_tag == "vertices":
            for v in child:
                mesh_vertices.append([float(v.attrib["x"]), float(v.attrib["y"]), float(v.attrib["z"])])
        elif child_tag == "triangles":
            for t in child:
                mesh_faces.append([
                    int(t.attrib["v1"]) + vertex_offset,
                    int(t.attrib["v2"]) + vertex_offset,
                    int(t.attrib["v3"]) + vertex_offset,
                ])
    return mesh_vertices, mesh_faces


def _parse_3mf_elements(tree):
    vertices = []
    faces = []
    for elem in tree.iter():
        tag_name = elem.tag.split("}")[-1]
        if tag_name == "mesh":
            mesh_v, mesh_f = _parse_3mf_mesh_element(elem, len(vertices))
            vertices.extend(mesh_v)
            faces.extend(mesh_f)

    if not vertices:
        vertices, faces = _parse_3mf_fallback(tree)

    return np.array(vertices), np.array(faces)


def _load_3mf(filepath):
    with zipfile.ZipFile(filepath, "r") as archive:
        model_names = [name for name in archive.namelist() if name.lower().endswith(".model")]
        if not model_names:
            raise ValueError(f"Invalid 3MF file: {filepath}")
        tree = ET.fromstring(archive.read(model_names[0]))

    vertices, faces = _parse_3mf_elements(tree)
    return trimesh.Trimesh(vertices=vertices, faces=faces)


def _load_cad_brep(filepath):
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(filepath))
        gmsh.model.mesh.generate(2)
        _node_tags, coords, _ = gmsh.model.mesh.getNodes()
        nodes = coords.reshape((-1, 3))
        elem_types, _tags, elem_node_tags = gmsh.model.mesh.getElements(2)
        tri_idx = np.where(np.array(elem_types) == 2)[0]
        if len(tri_idx) == 0:
            raise ValueError(f"No surface mesh could be generated from CAD file: {filepath}")
        faces = (elem_node_tags[tri_idx[0]] - 1).reshape((-1, 3))
        return trimesh.Trimesh(vertices=nodes, faces=faces)
    finally:
        gmsh.finalize()


def load_mesh(filepath):
    extension = Path(filepath).suffix.lower()
    if extension == ".3mf":
        mesh = _load_3mf(filepath)
    elif extension in (".step", ".stp", ".iges", ".igs"):
        mesh = _load_cad_brep(filepath)
    else:
        mesh = trimesh.load(filepath, force="mesh")
        if isinstance(mesh, trimesh.Scene):
            mesh = mesh.to_geometry()

    if mesh.is_empty:
        raise ValueError(f"File '{filepath}' contains no valid 3D geometry.")

    return repair_mesh(mesh)


def apply_gyroid_infill(density_grid, pitch, cell_size_mm=DEFAULT_GYROID_CELL_SIZE_MM):
    nx, ny, nz = density_grid.shape
    coords = [np.arange(nx) * pitch, np.arange(ny) * pitch, np.arange(nz) * pitch]
    grid_x, grid_y, grid_z = np.meshgrid(coords[0], coords[1], coords[2], indexing="ij")
    wave_number = (2.0 * np.pi) / max(pitch, cell_size_mm)
    gyroid_field = (
        np.sin(wave_number * grid_x) * np.cos(wave_number * grid_y)
        + np.sin(wave_number * grid_y) * np.cos(wave_number * grid_z)
        + np.sin(wave_number * grid_z) * np.cos(wave_number * grid_x)
    )
    gyroid_sheet = 1.0 - np.clip(np.abs(gyroid_field) / GYROID_CLIP_AMPLITUDE, 0.0, 1.0)
    infilled_densities = density_grid.copy()
    lattice_mask = (
        (density_grid > GYROID_DENSITY_LOWER_THRESHOLD) & (density_grid < GYROID_DENSITY_UPPER_THRESHOLD)
    )
    infilled_densities[lattice_mask] = np.maximum(
        GYROID_MIN_RELATIVE_DENSITY,
        gyroid_sheet[lattice_mask] * density_grid[lattice_mask] * GYROID_SCALE_FACTOR,
    )
    return infilled_densities


def _scalar_to_turbo_rgb(val):
    norm_val = float(np.clip(val, 0.0, 1.0))
    alpha = COLORMAP_MAX_COLOR_VALUE
    if norm_val < COLORMAP_BAND_QUARTER:
        fraction = norm_val / COLORMAP_BAND_QUARTER
        return 0, int(COLORMAP_MAX_COLOR_VALUE * fraction), COLORMAP_MAX_COLOR_VALUE, alpha
    if norm_val < COLORMAP_BAND_HALF:
        fraction = (norm_val - COLORMAP_BAND_QUARTER) / COLORMAP_BAND_QUARTER
        return 0, COLORMAP_MAX_COLOR_VALUE, int(COLORMAP_MAX_COLOR_VALUE * (1.0 - fraction)), alpha
    if norm_val < COLORMAP_BAND_THREE_QUARTERS:
        fraction = (norm_val - COLORMAP_BAND_HALF) / COLORMAP_BAND_QUARTER
        return int(COLORMAP_MAX_COLOR_VALUE * fraction), COLORMAP_MAX_COLOR_VALUE, 0, alpha
    fraction = (norm_val - COLORMAP_BAND_THREE_QUARTERS) / COLORMAP_BAND_QUARTER
    green_component = int(COLORMAP_MAX_COLOR_VALUE * (1.0 - fraction * COLORMAP_TINT_WEIGHT))
    return COLORMAP_MAX_COLOR_VALUE, green_component, 0, alpha


def apply_stress_colormap(mesh, vm_stresses, origin, pitch, grid_shape, max_stress=None):
    if len(mesh.vertices) == 0 or len(vm_stresses) == 0:
        return mesh
    stress_3d = vm_stresses.reshape(grid_shape)
    peak_stress = max_stress
    if peak_stress is None or peak_stress <= 0.0:
        peak_stress = float(np.max(stress_3d)) + DEFAULT_EPSILON

    nx, ny, nz = grid_shape
    vertex_colors = np.zeros((len(mesh.vertices), 4), dtype=np.uint8)
    for idx, vertex in enumerate(mesh.vertices):
        ix = int(np.clip(round((vertex[0] - origin[0]) / pitch), 0, nx - 1))
        iy = int(np.clip(round((vertex[1] - origin[1]) / pitch), 0, ny - 1))
        iz = int(np.clip(round((vertex[2] - origin[2]) / pitch), 0, nz - 1))
        norm_val = stress_3d[ix, iy, iz] / peak_stress
        vertex_colors[idx] = _scalar_to_turbo_rgb(norm_val)

    mesh.visual.vertex_colors = vertex_colors
    return mesh


def voxelize_mesh(mesh, resolution):
    bounds = mesh.bounds
    if bounds is None:
        raise ValueError("Cannot calculate bounding box for the provided mesh.")

    extents = bounds[1] - bounds[0]
    max_dimension = np.max(extents)
    pitch = max_dimension / float(resolution)

    voxel_grid = mesh.voxelized(pitch=pitch)
    voxel_grid = voxel_grid.fill()
    solid_matrix = voxel_grid.matrix

    origin = bounds[0]
    return solid_matrix, origin, pitch


def _extract_marching_cubes(padded_grid, isovalue):
    max_density = float(np.max(padded_grid))
    candidate_levels = [isovalue, 0.25, 0.15, 0.05]
    for level in candidate_levels:
        if level >= max_density:
            continue
        try:
            v, f, _normals, _values = measure.marching_cubes(padded_grid, level=level)
            if len(v) > 0 and len(f) > 0:
                return v, f
        except (ValueError, RuntimeError):
            continue
    return None, None


def reconstruct_surface(
    density_grid, origin, pitch, isovalue=DEFAULT_SURFACE_ISOVALUE, smooth_iterations=DEFAULT_SMOOTH_ITERATIONS,
):
    padded = np.pad(density_grid, pad_width=PADDING_WIDTH_MARCHING_CUBES, mode="constant", constant_values=0.0)
    vertices, faces = _extract_marching_cubes(padded, isovalue)
    if vertices is None or faces is None or len(vertices) == 0:
        return trimesh.Trimesh()

    vertices = (vertices - 1.0) * pitch + origin
    surface = trimesh.Trimesh(vertices=vertices, faces=faces)
    if surface.volume < 0.0:
        surface.faces = np.fliplr(surface.faces)
    trimesh.repair.fix_normals(surface)
    trimesh.repair.fix_inversion(surface)
    if smooth_iterations > 0 and len(surface.faces) > 0:
        trimesh.smoothing.filter_taubin(surface, iterations=smooth_iterations)
        trimesh.repair.fix_normals(surface)
    return surface


def _build_3dmodel_xml(vertices, faces):
    vertex_elements = [
        f'<vertex x="{v[0]:.4f}" y="{v[1]:.4f}" z="{v[2]:.4f}"/>' for v in vertices
    ]
    triangle_elements = [
        f'<triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>' for f in faces
    ]

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
        '  <metadata name="Designer">OptiShape 3D</metadata>\n'
        '  <metadata name="Application">OptiShape Generative Topology Optimizer</metadata>\n'
        '  <metadata name="Title">Optimized Generative Part</metadata>\n'
        '  <metadata name="RecommendedNozzleDiameter">0.4</metadata>\n'
        '  <metadata name="RecommendedLayerHeight">0.2</metadata>\n'
        '  <resources><object id="1" type="model"><mesh>\n'
        '    <vertices>\n' + '\n'.join(vertex_elements) + '\n    </vertices>\n'
        '    <triangles>\n' + '\n'.join(triangle_elements) + '\n    </triangles>\n'
        '  </mesh></object></resources>\n'
        '  <build><item objectid="1"/></build>\n'
        '</model>'
    )


def _write_3mf_archive(mesh, output_path):
    types_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        '</Types>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>'
    )
    model_xml = _build_3dmodel_xml(mesh.vertices, mesh.faces)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types_xml)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("3D/3dmodel.model", model_xml)


def export_mesh(mesh, output_path):
    if output_path.lower().endswith(".3mf"):
        _write_3mf_archive(mesh, output_path)
    else:
        mesh.export(output_path)


def _rasterize_cylinder(center, radius, height, axis, origin, pitch, grid_shape):
    nx, ny, nz = grid_shape
    xs = origin[0] + (np.arange(nx) + VOXEL_CENTER_OFFSET) * pitch - center[0]
    ys = origin[1] + (np.arange(ny) + VOXEL_CENTER_OFFSET) * pitch - center[1]
    zs = origin[2] + (np.arange(nz) + VOXEL_CENTER_OFFSET) * pitch - center[2]
    radius_sq = radius * radius

    if axis == "x":
        cross_section = ys[:, None] ** 2 + zs[None, :] ** 2 <= radius_sq
        mask = np.repeat(cross_section[None, :, :], nx, axis=0)
        if height is not None and height > 0:
            mask = mask & (np.abs(xs)[:, None, None] <= height / 2.0)
    elif axis == "y":
        cross_section = xs[:, None] ** 2 + zs[None, :] ** 2 <= radius_sq
        mask = np.repeat(cross_section[:, None, :], ny, axis=1)
        if height is not None and height > 0:
            mask = mask & (np.abs(ys)[None, :, None] <= height / 2.0)
    else:
        cross_section = xs[:, None] ** 2 + ys[None, :] ** 2 <= radius_sq
        mask = np.repeat(cross_section[:, :, None], nz, axis=2)
        if height is not None and height > 0:
            mask = mask & (np.abs(zs)[None, None, :] <= height / 2.0)
    return mask


def _rasterize_box(min_pt, max_pt, origin, pitch, grid_shape):
    nx, ny, nz = grid_shape
    xs = origin[0] + (np.arange(nx) + VOXEL_CENTER_OFFSET) * pitch
    ys = origin[1] + (np.arange(ny) + VOXEL_CENTER_OFFSET) * pitch
    zs = origin[2] + (np.arange(nz) + VOXEL_CENTER_OFFSET) * pitch
    mask_x = (xs >= min_pt[0]) & (xs <= max_pt[0])
    mask_y = (ys >= min_pt[1]) & (ys <= max_pt[1])
    mask_z = (zs >= min_pt[2]) & (zs <= max_pt[2])
    return mask_x[:, None, None] & mask_y[None, :, None] & mask_z[None, None, :]


def _rasterize_sphere(center, radius, origin, pitch, grid_shape):
    nx, ny, nz = grid_shape
    xs = origin[0] + (np.arange(nx) + VOXEL_CENTER_OFFSET) * pitch - center[0]
    ys = origin[1] + (np.arange(ny) + VOXEL_CENTER_OFFSET) * pitch - center[1]
    zs = origin[2] + (np.arange(nz) + VOXEL_CENTER_OFFSET) * pitch - center[2]
    distance_sq = xs[:, None, None] ** 2 + ys[None, :, None] ** 2 + zs[None, None, :] ** 2
    return distance_sq <= (radius * radius)


def rasterize_geometric_zone(zone_def, origin, pitch, grid_shape):
    shape_type = zone_def.get("shape", ZONE_SHAPE_CYLINDER).lower()
    if shape_type == ZONE_SHAPE_BOX:
        min_pt = zone_def.get("min_pt", [0.0, 0.0, 0.0])
        max_pt = zone_def.get("max_pt", [0.0, 0.0, 0.0])
        return _rasterize_box(min_pt, max_pt, origin, pitch, grid_shape)
    if shape_type == ZONE_SHAPE_SPHERE:
        center = zone_def.get("center", [0.0, 0.0, 0.0])
        radius = float(zone_def.get("radius", DEFAULT_SPHERE_RADIUS_MM))
        return _rasterize_sphere(center, radius, origin, pitch, grid_shape)

    center = zone_def.get("center", [0.0, 0.0, 0.0])
    radius = float(zone_def.get("radius", DEFAULT_CYLINDER_RADIUS_MM))
    height = zone_def.get("height", None)
    if height is not None:
        height = float(height)
    axis = zone_def.get("axis", "z").lower()
    return _rasterize_cylinder(center, radius, height, axis, origin, pitch, grid_shape)


def build_preservation_masks(zones, origin, pitch, grid_shape, base_preserved=None):
    keep_in = np.zeros(grid_shape, dtype=bool)
    keep_out = np.zeros(grid_shape, dtype=bool)
    if base_preserved is not None:
        keep_in = keep_in | base_preserved

    if not zones:
        return keep_in, keep_out

    for zone in zones:
        zone_mask = rasterize_geometric_zone(zone, origin, pitch, grid_shape)
        zone_type = zone.get("type", ZONE_TYPE_KEEP_IN).lower()
        if zone_type == ZONE_TYPE_KEEP_OUT:
            keep_out = keep_out | zone_mask
        else:
            keep_in = keep_in | zone_mask

    keep_in = keep_in & (~keep_out)
    return keep_in, keep_out
