"""Unified execution pipeline for 3D topology optimization."""

import math
import time
from pathlib import Path

from app.three_d.config import (
    ACTIVE_SOLID_THRESHOLD,
    CM_PER_M,
    DEFAULT_ENABLE_GYROID,
    DEFAULT_ENABLE_OVERHANG,
    DEFAULT_LOAD_DIRECTION,
    DEFAULT_LOAD_MAGNITUDE,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MIN_SAFETY_FACTOR,
    DEFAULT_PRESERVE_MARGIN,
    DEFAULT_PRINT_FLOW_MM3_S,
    DEFAULT_RESOLUTION,
    DEFAULT_SURFACE_ISOVALUE,
    DEFAULT_UNCONSTRAINED_FOS,
    DEFAULT_VOLUME_FRACTION,
    DEFAULT_VOXEL_PITCH_MM,
    DELAMINATION_RISK_HIGH,
    DELAMINATION_RISK_LOW,
    DELAMINATION_RISK_MODERATE,
    FILAMENT_DIAMETER_MM,
    G_PER_KG,
    MATERIALS,
    MM_PER_CM,
    MM_PER_M,
    MM3_PER_CM3,
    PERCENTAGE_FACTOR,
    SAFETY_FACTOR_CRITICAL_THRESHOLD,
    SAFETY_FACTOR_TARGET_THRESHOLD,
    SECONDS_PER_HOUR,
    SUPPORT_MODE_CANTILEVER,
)
from app.three_d.fea import (
    calculate_stress_tensors,
    evaluate_anisotropic_safety,
    evaluate_structural_safety,
    identify_preserved_regions,
)
from app.three_d.geometry import (
    apply_gyroid_infill,
    apply_stress_colormap,
    build_preservation_masks,
    create_default_beam,
    export_mesh,
    load_mesh,
    reconstruct_surface,
    voxelize_mesh,
)
from app.three_d.optimizer import run_simp_optimization


def _estimate_print_times(original_vol_cm3, optimized_vol_cm3, flow_rate):
    original_hours = round((original_vol_cm3 * MM3_PER_CM3) / (flow_rate * SECONDS_PER_HOUR), 2)
    optimized_hours = round((optimized_vol_cm3 * MM3_PER_CM3) / (flow_rate * SECONDS_PER_HOUR), 2)
    saved_hours = round(original_hours - optimized_hours, 2)
    return original_hours, optimized_hours, saved_hours


def _calculate_volume_and_mass_savings(active_voxels, pitch, target_volume, density_g_cm3):
    original_vol_cm3 = (active_voxels * (pitch**3)) / MM3_PER_CM3
    optimized_vol_cm3 = original_vol_cm3 * target_volume
    saved_vol_cm3 = original_vol_cm3 - optimized_vol_cm3

    original_mass = round(original_vol_cm3 * density_g_cm3, 1)
    optimized_mass = round(optimized_vol_cm3 * density_g_cm3, 1)
    mass_saved = round(saved_vol_cm3 * density_g_cm3, 1)

    filament_radius_cm = (FILAMENT_DIAMETER_MM / MM_PER_CM) / 2.0
    filament_area_cm2 = math.pi * (filament_radius_cm**2)
    filament_saved_m = round((saved_vol_cm3 / filament_area_cm2) / CM_PER_M, 1)

    return original_vol_cm3, optimized_vol_cm3, original_mass, optimized_mass, mass_saved, filament_saved_m


def calculate_savings_metrics(
    active_voxels, pitch, target_volume, material_properties, flow_rate=DEFAULT_PRINT_FLOW_MM3_S
):
    density = material_properties["density_g_cm3"]
    orig_vol, opt_vol, orig_mass, opt_mass, mass_saved, fil_saved = _calculate_volume_and_mass_savings(
        active_voxels, pitch, target_volume, density
    )
    cost_saved = round((mass_saved / G_PER_KG) * material_properties["cost_eur_kg"], 2)
    reduction = round((1.0 - target_volume) * PERCENTAGE_FACTOR, 1)
    orig_time_h, opt_time_h, saved_time_h = _estimate_print_times(orig_vol, opt_vol, flow_rate)

    return {
        "original_volume_cm3": round(orig_vol, 1),
        "optimized_volume_cm3": round(opt_vol, 1),
        "original_mass_g": orig_mass,
        "optimized_mass_g": opt_mass,
        "mass_saved_g": mass_saved,
        "filament_saved_m": fil_saved,
        "cost_saved_eur": cost_saved,
        "reduction_pct": reduction,
        "original_time_hours": orig_time_h,
        "optimized_time_hours": opt_time_h,
        "print_time_saved_hours": saved_time_h,
    }


def resolve_material(material_name, custom_material=None):
    if custom_material is not None:
        base_material = MATERIALS["PLA"].copy()
        base_material.update(custom_material)
        return base_material
    if material_name in MATERIALS:
        return MATERIALS[material_name]
    return MATERIALS["PLA"]


def _prepare_target_mesh(input_path):
    if bool(input_path):
        return load_mesh(input_path)
    return create_default_beam()


def _evaluate_pipeline_safety(displacement, edof, density_grid, mat_props, pitch=DEFAULT_VOXEL_PITCH_MM):
    if displacement is None:
        return 0.0, DEFAULT_UNCONSTRAINED_FOS, 0.0, DEFAULT_UNCONSTRAINED_FOS
    grid_spacing_m = pitch / MM_PER_M
    stress_scale = 1.0 / (grid_spacing_m * grid_spacing_m)
    vm_unit, sz_unit = calculate_stress_tensors(displacement, edof, 1.0, mat_props["nu"])
    active_solid = density_grid > ACTIVE_SOLID_THRESHOLD
    yield_strength = mat_props["yield_strength_mpa"]
    max_stress, fos = evaluate_structural_safety(vm_unit * stress_scale, active_solid, yield_strength)
    max_sz, fos_z = evaluate_anisotropic_safety(sz_unit * stress_scale, active_solid, yield_strength)
    return max_stress, fos, max_sz, fos_z


def _determine_delamination_risk(anisotropic_fos_z):
    if anisotropic_fos_z < SAFETY_FACTOR_CRITICAL_THRESHOLD:
        return DELAMINATION_RISK_HIGH
    if anisotropic_fos_z < SAFETY_FACTOR_TARGET_THRESHOLD:
        return DELAMINATION_RISK_MODERATE
    return DELAMINATION_RISK_LOW


def _build_safety_dict(displacement, edof, density_grid, mat_props, pitch, preserve_margin, enable_overhang):
    max_stress, fos, max_sz, fos_z = _evaluate_pipeline_safety(
        displacement, edof, density_grid, mat_props, pitch
    )
    delamination_risk = _determine_delamination_risk(fos_z)

    is_safe = False
    if fos >= DEFAULT_MIN_SAFETY_FACTOR:
        if fos_z >= DEFAULT_MIN_SAFETY_FACTOR:
            is_safe = True

    return {
        "max_stress_mpa": max_stress,
        "factor_of_safety": fos,
        "max_tensile_z_mpa": max_sz,
        "anisotropic_fos_z": fos_z,
        "delamination_risk": delamination_risk,
        "yield_strength_mpa": mat_props["yield_strength_mpa"],
        "is_safe": is_safe,
        "preserve_margin": preserve_margin,
        "enable_overhang": enable_overhang,
    }


def _summarize_results(solid_mask, elapsed_seconds, savings, safety):
    result = {
        "grid_shape": list(solid_mask.shape),
        "active_voxels": int(solid_mask.sum()),
        "total_voxels": int(solid_mask.size),
        "elapsed_seconds": elapsed_seconds,
    }
    result.update(savings)
    result.update(safety)
    return result


def _export_optimized_geometry(
    grid, origin, pitch, path, displacement, edof, poisson_ratio, shape, enable_gyroid, target_volume=DEFAULT_VOLUME_FRACTION, keep_in=None, keep_out=None
):
    export_grid = grid.copy()
    if keep_out is not None:
        export_grid[keep_out] = 0.0
    if keep_in is not None:
        export_grid[keep_in] = 1.0
    if enable_gyroid:
        export_grid = apply_gyroid_infill(export_grid, pitch)
    adaptive_isovalue = min(DEFAULT_SURFACE_ISOVALUE, max(0.12, target_volume * 0.75))
    mesh = reconstruct_surface(export_grid, origin, pitch, isovalue=adaptive_isovalue)
    if displacement is not None:
        vm_unit, _ = calculate_stress_tensors(displacement, edof, 1.0, poisson_ratio)
        mesh = apply_stress_colormap(mesh, vm_unit, origin, pitch, shape)
    export_mesh(mesh, path)
    if path.lower().endswith(".stl"):
        ply_path = str(Path(path).with_suffix(".ply"))
        export_mesh(mesh, ply_path)


def _prepare_optimization_domain(input_path, resolution, preserve_margin, support_mode, preserved_zones):
    mesh = _prepare_target_mesh(input_path)
    solid_mask, origin, pitch = voxelize_mesh(mesh, resolution)
    base_preserved = identify_preserved_regions(solid_mask, preserve_margin, support_mode)
    keep_in, keep_out = build_preservation_masks(preserved_zones, origin, pitch, solid_mask.shape, base_preserved)
    return solid_mask, origin, pitch, keep_in, keep_out


def _build_iteration_wrapper(callback, origin, pitch):
    if callback is None:
        return None
    def _invoker(iter_num, compliance, change, densities=None):
        try:
            callback(iter_num, compliance, change, densities, origin, pitch)
        except TypeError:
            try:
                callback(iter_num, compliance, change, densities)
            except TypeError:
                callback(iter_num, compliance, change)
    return _invoker


def run_optimization_pipeline(
    output_path, input_path=None, material_name="PLA", target_volume=DEFAULT_VOLUME_FRACTION,
    resolution=DEFAULT_RESOLUTION, max_iterations=DEFAULT_MAX_ITERATIONS,
    load_magnitude=DEFAULT_LOAD_MAGNITUDE, load_direction=DEFAULT_LOAD_DIRECTION,
    preserve_margin=DEFAULT_PRESERVE_MARGIN, enable_overhang=DEFAULT_ENABLE_OVERHANG,
    iteration_callback=None, load_cases=None, support_mode=SUPPORT_MODE_CANTILEVER,
    enable_gyroid=DEFAULT_ENABLE_GYROID, custom_material=None, preserved_zones=None,
):
    mat_props = resolve_material(material_name, custom_material)
    solid_mask, origin, pitch, keep_in, keep_out = _prepare_optimization_domain(
        input_path, resolution, preserve_margin, support_mode, preserved_zones
    )
    cb = _build_iteration_wrapper(iteration_callback, origin, pitch)
    start_timestamp = time.time()
    density_grid, last_displacement, edof = run_simp_optimization(
        solid_mask, target_volume, 1.0, mat_props["nu"],
        max_iterations, load_magnitude, load_direction,
        keep_in, enable_overhang, True, cb,
        load_cases, support_mode, keep_out,
    )
    elapsed_seconds = round(time.time() - start_timestamp, 2)
    _export_optimized_geometry(
        density_grid, origin, pitch, output_path, last_displacement, edof,
        mat_props["nu"], solid_mask.shape, enable_gyroid, target_volume, keep_in, keep_out,
    )

    savings = calculate_savings_metrics(int(solid_mask.sum()), pitch, target_volume, mat_props)
    safety = _build_safety_dict(last_displacement, edof, density_grid, mat_props, pitch, preserve_margin, enable_overhang)
    summary = _summarize_results(solid_mask, elapsed_seconds, savings, safety)
    summary["support_mode"] = support_mode
    summary["enable_gyroid"] = enable_gyroid
    summary["preserved_zones"] = preserved_zones
    return summary
