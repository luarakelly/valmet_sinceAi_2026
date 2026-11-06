"""Finite element analysis for 3D hexahedral voxel grids."""

import numpy as np
from scipy.sparse.linalg import spsolve

from app.three_d.config import (
    DEFAULT_EPSILON,
    DEFAULT_LOAD_DIRECTION,
    DEFAULT_LOAD_MAGNITUDE,
    DEFAULT_PRESERVE_MARGIN,
    DEFAULT_UNCONSTRAINED_FOS,
    DEFAULT_Z_ANISOTROPIC_FACTOR,
    DOF_AXIS_MAP,
    DOFS_PER_HEX8,
    DOFS_PER_NODE,
    GAUSS_WEIGHT_FACTOR,
    NUM_NODES_PER_HEX8,
    PA_PER_MPA,
    STRESS_TENSOR_COMPONENTS,
    SUPPORT_MODE_CANTILEVER,
    SUPPORT_MODE_CLAMPED_ENDS,
    SUPPORT_MODE_SIMPLY_SUPPORTED,
)

HEX8_REFERENCE_NODES = np.array(
    [
        [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
        [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
    ],
    dtype=float,
)


def _build_constitutive_matrix(youngs_modulus, poisson_ratio):
    factor = youngs_modulus / ((1.0 + poisson_ratio) * (1.0 - 2.0 * poisson_ratio))
    shear_modulus = (1.0 - 2.0 * poisson_ratio) / 2.0
    matrix_c = np.zeros((STRESS_TENSOR_COMPONENTS, STRESS_TENSOR_COMPONENTS))
    matrix_c[0:3, 0:3] = poisson_ratio
    np.fill_diagonal(matrix_c[0:3, 0:3], 1.0 - poisson_ratio)
    np.fill_diagonal(matrix_c[3:6, 3:6], shear_modulus)
    return matrix_c * factor


def _build_b_matrix(xi, eta, zeta, reference_nodes):
    shape_derivs_natural = np.zeros((NUM_NODES_PER_HEX8, DOFS_PER_NODE))
    shape_derivs_natural[:, 0] = 0.125 * reference_nodes[:, 0] * (1.0 + eta * reference_nodes[:, 1]) * (1.0 + zeta * reference_nodes[:, 2])
    shape_derivs_natural[:, 1] = 0.125 * reference_nodes[:, 1] * (1.0 + xi * reference_nodes[:, 0]) * (1.0 + zeta * reference_nodes[:, 2])
    shape_derivs_natural[:, 2] = 0.125 * reference_nodes[:, 2] * (1.0 + xi * reference_nodes[:, 0]) * (1.0 + eta * reference_nodes[:, 1])
    shape_derivs_physical = shape_derivs_natural * 2.0

    strain_displacement_b = np.zeros((STRESS_TENSOR_COMPONENTS, DOFS_PER_HEX8))
    for node_idx in range(NUM_NODES_PER_HEX8):
        col = node_idx * DOFS_PER_NODE
        dx, dy, dz = shape_derivs_physical[node_idx]
        strain_displacement_b[0, col] = dx
        strain_displacement_b[1, col + 1] = dy
        strain_displacement_b[2, col + 2] = dz
        strain_displacement_b[3, col + 1] = dx
        strain_displacement_b[3, col] = dy
        strain_displacement_b[4, col + 2] = dy
        strain_displacement_b[4, col + 1] = dz
        strain_displacement_b[5, col + 2] = dx
        strain_displacement_b[5, col] = dz
    return strain_displacement_b


def calculate_hex8_stiffness(youngs_modulus=1.0, poisson_ratio=0.3, E=None, nu=None):
    if E is not None:
        youngs_modulus = E
    if nu is not None:
        poisson_ratio = nu

    matrix_c = _build_constitutive_matrix(youngs_modulus, poisson_ratio)
    gauss_coord = 1.0 / np.sqrt(3.0)
    element_stiffness = np.zeros((DOFS_PER_HEX8, DOFS_PER_HEX8))

    for xi in [-gauss_coord, gauss_coord]:
        for eta in [-gauss_coord, gauss_coord]:
            for zeta in [-gauss_coord, gauss_coord]:
                matrix_b = _build_b_matrix(xi, eta, zeta, HEX8_REFERENCE_NODES)
                element_stiffness += matrix_b.T @ matrix_c @ matrix_b * GAUSS_WEIGHT_FACTOR
    return element_stiffness


def build_edof_matrix(nelx, nely, nelz):
    nodes_y = nely + 1
    nodes_z = nelz + 1
    num_elements = nelx * nely * nelz
    edof = np.zeros((num_elements, DOFS_PER_HEX8), dtype=int)

    grid_x, grid_y, grid_z = np.meshgrid(
        np.arange(nelx), np.arange(nely), np.arange(nelz), indexing="ij"
    )

    stride_x = nodes_y * nodes_z
    stride_y = nodes_z
    n0 = grid_x * stride_x + grid_y * stride_y + grid_z
    n1 = (grid_x + 1) * stride_x + grid_y * stride_y + grid_z
    n2 = (grid_x + 1) * stride_x + (grid_y + 1) * stride_y + grid_z
    n3 = grid_x * stride_x + (grid_y + 1) * stride_y + grid_z
    n4 = grid_x * stride_x + grid_y * stride_y + (grid_z + 1)
    n5 = (grid_x + 1) * stride_x + grid_y * stride_y + (grid_z + 1)
    n6 = (grid_x + 1) * stride_x + (grid_y + 1) * stride_y + (grid_z + 1)
    n7 = grid_x * stride_x + (grid_y + 1) * stride_y + (grid_z + 1)

    elem_nodes = np.stack([n0, n1, n2, n3, n4, n5, n6, n7], axis=-1).reshape(-1, NUM_NODES_PER_HEX8)
    for node_idx in range(NUM_NODES_PER_HEX8):
        base_dof = DOFS_PER_NODE * elem_nodes[:, node_idx]
        edof[:, node_idx * DOFS_PER_NODE] = base_dof
        edof[:, node_idx * DOFS_PER_NODE + 1] = base_dof + 1
        edof[:, node_idx * DOFS_PER_NODE + 2] = base_dof + 2
    return edof


def detect_primary_axis(solid_mask):
    solid_indices = np.argwhere(solid_mask)
    if len(solid_indices) == 0:
        return 0
    spans = [int(np.ptp(solid_indices[:, i])) for i in range(3)]
    return int(np.argmax(spans))


def _extract_layer_nodes(axis, layer_idx, voxels, nodes_y, nodes_z):
    stride_x = nodes_y * nodes_z
    stride_y = nodes_z
    nodes = set()
    for item in voxels:
        vx = item[0]
        vy = item[1]
        vz = item[2]
        if axis == 0:
            for dy in (0, 1):
                for dz in (0, 1):
                    nodes.add(layer_idx * stride_x + (vy + dy) * stride_y + (vz + dz))
        elif axis == 1:
            for dx in (0, 1):
                for dz in (0, 1):
                    nodes.add((vx + dx) * stride_x + layer_idx * stride_y + (vz + dz))
        else:
            for dx in (0, 1):
                for dy in (0, 1):
                    nodes.add((vx + dx) * stride_x + (vy + dy) * stride_y + layer_idx)
    return nodes


def _build_fixed_dofs(axis, min_coord, max_coord, solid_indices, nodes_y, nodes_z, support_mode=SUPPORT_MODE_CANTILEVER):
    min_voxels = solid_indices[solid_indices[:, axis] == min_coord]
    fixed_nodes = _extract_layer_nodes(axis, min_coord, min_voxels, nodes_y, nodes_z)
    fixed_dofs = []
    for node in fixed_nodes:
        fixed_dofs.extend([DOFS_PER_NODE * node, DOFS_PER_NODE * node + 1, DOFS_PER_NODE * node + 2])

    if support_mode in (SUPPORT_MODE_SIMPLY_SUPPORTED, SUPPORT_MODE_CLAMPED_ENDS):
        max_voxels = solid_indices[solid_indices[:, axis] == max_coord]
        max_nodes = _extract_layer_nodes(axis, max_coord + 1, max_voxels, nodes_y, nodes_z)
        for node in max_nodes:
            fixed_dofs.extend([DOFS_PER_NODE * node + 1, DOFS_PER_NODE * node + 2])
            if support_mode == SUPPORT_MODE_CLAMPED_ENDS:
                fixed_dofs.append(DOFS_PER_NODE * node)

    return np.array(sorted(set(fixed_dofs)), dtype=int)


def _parse_force_components(magnitude, direction):
    if isinstance(direction, (list, tuple, np.ndarray)) and len(direction) == DOFS_PER_NODE:
        return [float(direction[0]), float(direction[1]), float(direction[2])]
    axis_char = str(direction)[-1].upper()
    dof_offset = DOF_AXIS_MAP.get(axis_char, 2)
    signed_magnitude = -abs(magnitude)
    if str(direction).startswith("+"):
        signed_magnitude = abs(magnitude)
    components = [0.0, 0.0, 0.0]
    components[dof_offset] = signed_magnitude
    return components


def _build_force_vector(axis, load_coord, solid_indices, nodes_y, nodes_z, total_dofs, magnitude, direction):
    axis_layers = np.unique(solid_indices[:, axis])
    if load_coord not in axis_layers:
        load_coord = int(axis_layers[np.argmin(np.abs(axis_layers - load_coord))])
    voxels = solid_indices[solid_indices[:, axis] == load_coord]
    load_nodes = _extract_layer_nodes(axis, load_coord + 1, voxels, nodes_y, nodes_z)
    components = _parse_force_components(magnitude, direction)
    force_vector = np.zeros(total_dofs)
    node_count = len(load_nodes)
    if node_count == 0:
        outer_coord = int(axis_layers[-1])
        load_nodes = _extract_layer_nodes(axis, outer_coord + 1, solid_indices, nodes_y, nodes_z)
        node_count = max(1, len(load_nodes))

    for node in load_nodes:
        force_vector[DOFS_PER_NODE * node] += components[0] / node_count
        force_vector[DOFS_PER_NODE * node + 1] += components[1] / node_count
        force_vector[DOFS_PER_NODE * node + 2] += components[2] / node_count
    return force_vector


def setup_multi_boundary_conditions(solid_mask, load_cases=None, support_mode=SUPPORT_MODE_CANTILEVER):
    nelx, nely, nelz = solid_mask.shape
    nodes_y = nely + 1
    nodes_z = nelz + 1
    total_dofs = DOFS_PER_NODE * (nelx + 1) * nodes_y * nodes_z
    solid_indices = np.argwhere(solid_mask)
    axis = detect_primary_axis(solid_mask)
    min_coord = int(np.min(solid_indices[:, axis]))
    max_coord = int(np.max(solid_indices[:, axis]))

    fixed_dofs = _build_fixed_dofs(axis, min_coord, max_coord, solid_indices, nodes_y, nodes_z, support_mode)
    free_dofs = np.setdiff1d(np.arange(total_dofs), fixed_dofs)

    axis_layers = np.unique(solid_indices[:, axis])
    load_coord = max_coord
    if support_mode in (SUPPORT_MODE_SIMPLY_SUPPORTED, SUPPORT_MODE_CLAMPED_ENDS):
        mid_target = int((min_coord + max_coord) // 2)
        load_coord = int(axis_layers[np.argmin(np.abs(axis_layers - mid_target))])

    cases = load_cases
    if not cases:
        cases = [{"magnitude": DEFAULT_LOAD_MAGNITUDE, "direction": DEFAULT_LOAD_DIRECTION, "weight": 1.0}]

    force_vectors = []
    case_weights = []
    for case in cases:
        mag = case.get("magnitude", DEFAULT_LOAD_MAGNITUDE)
        dir_val = case.get("direction", DEFAULT_LOAD_DIRECTION)
        weight = case.get("weight", 1.0)
        f_vec = _build_force_vector(axis, load_coord, solid_indices, nodes_y, nodes_z, total_dofs, mag, dir_val)
        if np.sum(np.abs(f_vec[free_dofs])) == 0.0:
            f_vec = _build_force_vector(axis, max_coord, solid_indices, nodes_y, nodes_z, total_dofs, mag, dir_val)
        force_vectors.append(f_vec)
        case_weights.append(weight)
    return fixed_dofs, free_dofs, force_vectors, case_weights


def setup_boundary_conditions(
    solid_mask,
    load_magnitude=DEFAULT_LOAD_MAGNITUDE,
    load_direction=DEFAULT_LOAD_DIRECTION,
    support_mode=SUPPORT_MODE_CANTILEVER,
):
    single_case = [{"magnitude": load_magnitude, "direction": load_direction, "weight": 1.0}]
    fixed_dofs, free_dofs, force_vectors, _ = setup_multi_boundary_conditions(
        solid_mask, single_case, support_mode
    )
    return fixed_dofs, free_dofs, force_vectors[0]


def _mark_axis_range(target, axis, start, end):
    slices = [slice(None), slice(None), slice(None)]
    slices[axis] = slice(start, end)
    target[tuple(slices)] = True


def identify_preserved_regions(solid_mask, margin=DEFAULT_PRESERVE_MARGIN, support_mode=SUPPORT_MODE_CANTILEVER):
    preserved = np.zeros(solid_mask.shape, dtype=bool)
    if margin <= 0 or not np.any(solid_mask):
        return preserved

    solid_indices = np.argwhere(solid_mask)
    axis = detect_primary_axis(solid_mask)
    min_c = int(np.min(solid_indices[:, axis]))
    max_c = int(np.max(solid_indices[:, axis]))

    _mark_axis_range(preserved, axis, min_c, min_c + margin)
    _mark_axis_range(preserved, axis, max_c - margin + 1, max_c + 1)

    if support_mode in (SUPPORT_MODE_SIMPLY_SUPPORTED, SUPPORT_MODE_CLAMPED_ENDS):
        mid_c = int((min_c + max_c) // 2)
        half_m = max(1, margin // 2)
        start_c = max(0, mid_c - half_m)
        end_c = min(solid_mask.shape[axis], mid_c + half_m + 1)
        _mark_axis_range(preserved, axis, start_c, end_c)

    return preserved & solid_mask


def solve_fea(stiffness_matrix, force_vector, free_dofs, total_dofs):
    reduced_stiffness = stiffness_matrix[free_dofs, :][:, free_dofs]
    reduced_force = force_vector[free_dofs]

    free_displacements = spsolve(reduced_stiffness, reduced_force)

    displacement_vector = np.zeros(total_dofs)
    displacement_vector[free_dofs] = free_displacements
    return displacement_vector


def calculate_stress_tensors(displacement_vector, edof_matrix, youngs_modulus, poisson_ratio):
    matrix_c = _build_constitutive_matrix(youngs_modulus, poisson_ratio)
    matrix_b_center = _build_b_matrix(0.0, 0.0, 0.0, HEX8_REFERENCE_NODES)

    element_displacements = displacement_vector[edof_matrix]
    strains = element_displacements @ matrix_b_center.T
    stresses = strains @ matrix_c.T

    sigma_xx, sigma_yy, sigma_zz = stresses[:, 0], stresses[:, 1], stresses[:, 2]
    tau_xy, tau_yz, tau_zx = stresses[:, 3], stresses[:, 4], stresses[:, 5]

    normal_diff_sq = (sigma_xx - sigma_yy)**2 + (sigma_yy - sigma_zz)**2 + (sigma_zz - sigma_xx)**2
    shear_stress_sq = 6.0 * (tau_xy**2 + tau_yz**2 + tau_zx**2)
    von_mises_pa = np.sqrt(0.5 * (normal_diff_sq + shear_stress_sq))
    return von_mises_pa / PA_PER_MPA, sigma_zz / PA_PER_MPA


def calculate_von_mises_stresses(displacement_vector, edof_matrix, youngs_modulus, poisson_ratio):
    von_mises_mpa, _ = calculate_stress_tensors(displacement_vector, edof_matrix, youngs_modulus, poisson_ratio)
    return von_mises_mpa


def evaluate_structural_safety(vm_stresses_mpa, active_mask, yield_strength_mpa):
    active_stresses = vm_stresses_mpa[active_mask.flatten()]
    if len(active_stresses) == 0:
        return 0.0, DEFAULT_UNCONSTRAINED_FOS

    max_stress = float(np.max(active_stresses))
    factor_of_safety = yield_strength_mpa / (max_stress + DEFAULT_EPSILON)
    return round(max_stress, 2), round(factor_of_safety, 2)


def evaluate_anisotropic_safety(
    sigma_z_mpa, active_mask, yield_strength_mpa, z_factor=DEFAULT_Z_ANISOTROPIC_FACTOR
):
    active_sigma_z = sigma_z_mpa[active_mask.flatten()]
    if len(active_sigma_z) == 0:
        return 0.0, DEFAULT_UNCONSTRAINED_FOS

    max_tensile_z = float(np.max(np.maximum(0.0, active_sigma_z)))
    z_axis_yield = yield_strength_mpa * z_factor
    fos_z = z_axis_yield / (max_tensile_z + DEFAULT_EPSILON)
    return round(max_tensile_z, 2), round(fos_z, 2)
