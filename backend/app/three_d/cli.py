"""Command-line interface for the topology optimizer."""

import argparse
import json
from pathlib import Path
import sys

from app.three_d.config import (
    DEFAULT_ENABLE_GYROID,
    DEFAULT_ENABLE_OVERHANG,
    DEFAULT_LOAD_DIRECTION,
    DEFAULT_LOAD_MAGNITUDE,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_PRESERVE_MARGIN,
    DEFAULT_RESOLUTION,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    DEFAULT_VOLUME_FRACTION,
    MATERIALS,
    PERCENTAGE_FACTOR,
    SUPPORT_MODE_CANTILEVER,
    VALID_LOAD_DIRECTIONS,
    VALID_SUPPORT_MODES,
)
from app.three_d.pipeline import run_optimization_pipeline


def normalize_cli_args(raw_args):
    normalized = []
    skip_next = False
    for i in range(len(raw_args)):
        if skip_next:
            skip_next = False
            continue
        arg = raw_args[i]
        if arg in ["--direction", "-d"] and i + 1 < len(raw_args):
            normalized.append(f"--direction={raw_args[i + 1]}")
            skip_next = True
            continue
        normalized.append(arg)
    return normalized


def _add_mesh_arguments(parser):
    parser.add_argument(
        "--input", "-i", type=str, default="",
        help="Input 3D model (.stl, .3mf, .obj, .ply, .glb, .off, .step, .stp)"
    )
    parser.add_argument(
        "--output", "-o", type=str, default="optimized.stl",
        help="Output file (.stl, .3mf, .obj, .ply, .glb, .off)"
    )
    parser.add_argument(
        "--material", "-m", type=str, default="PLA", choices=list(MATERIALS.keys()), help="Material preset"
    )
    parser.add_argument(
        "--volume", "-v", type=float, default=DEFAULT_VOLUME_FRACTION, help="Target volume fraction"
    )


def _add_simulation_arguments(parser):
    parser.add_argument(
        "--resolution", "-r", type=int, default=DEFAULT_RESOLUTION, help="Voxel grid resolution"
    )
    parser.add_argument(
        "--iterations", type=int, default=DEFAULT_MAX_ITERATIONS, help="Maximum iterations"
    )
    parser.add_argument(
        "--direction", "-d", type=str, default=DEFAULT_LOAD_DIRECTION, choices=VALID_LOAD_DIRECTIONS, help="Force direction"
    )
    parser.add_argument(
        "--load", type=float, default=DEFAULT_LOAD_MAGNITUDE, help="Applied load magnitude in N"
    )
    parser.add_argument(
        "--support-mode", "--support", dest="support_mode", type=str,
        default=SUPPORT_MODE_CANTILEVER, choices=VALID_SUPPORT_MODES,
        help="Boundary support conditions"
    )


def _add_manufacturing_arguments(parser):
    parser.add_argument(
        "--preserve-margin", "-p", type=int, default=DEFAULT_PRESERVE_MARGIN, help="Voxel margin for non-design mounting zones"
    )
    parser.add_argument(
        "--overhang", action="store_true", default=DEFAULT_ENABLE_OVERHANG, help="Enable 45° self-supporting AM overhang filter"
    )
    parser.add_argument(
        "--gyroid", action="store_true", default=DEFAULT_ENABLE_GYROID, help="Synthesize TPMS gyroid infill"
    )
    parser.add_argument(
        "--preserved-zones", type=str, default="", help="JSON string or file path for keep-in/keep-out zones"
    )


def _add_server_arguments(parser):
    parser.add_argument(
        "--gui", action="store_true", help="Launch the web-based 3D graphical user interface"
    )
    parser.add_argument(
        "--host", type=str, default=DEFAULT_SERVER_HOST, help="Host address to bind GUI"
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_SERVER_PORT, help="Port number to bind GUI"
    )


def parse_arguments(args=None):
    if args is None:
        args = sys.argv[1:]
    args = normalize_cli_args(args)

    parser = argparse.ArgumentParser(
        description="OptiShape: 3D Stress & Topology Optimization for .stl and .obj models"
    )
    _add_mesh_arguments(parser)
    _add_simulation_arguments(parser)
    _add_manufacturing_arguments(parser)
    _add_server_arguments(parser)
    return parser.parse_args(args)


def log_iteration(iteration, compliance, change):
    print(
        f"Iter {iteration + 1:2d} | Compliance: {compliance:10.4f} | Max Density Change: {change:6.4f}"
    )


def _print_pipeline_summary(result, output_path):
    active = result["active_voxels"]
    total = result["total_voxels"]
    mass_saved = result["mass_saved_g"]
    cost_saved = result["cost_saved_eur"]
    filament_saved = result["filament_saved_m"]
    reduction = result["reduction_pct"]
    max_stress = result["max_stress_mpa"]
    fos = result["factor_of_safety"]

    if result["is_safe"]:
        safety_label = "SAFE (PASS)"
    else:
        safety_label = "YIELD RISK (WARNING)"

    print(f"Grid Size: {result['grid_shape']} ({active}/{total} active voxels)")
    print(f"Material Savings: -{reduction}% mass ({mass_saved}g / {filament_saved}m filament / €{cost_saved:.2f})")
    print(f"Structural Integrity: Max Stress = {max_stress} MPa | Factor of Safety = {fos} ({safety_label})")
    print(f"Optimization completed in {result['elapsed_seconds']:.2f} seconds.")
    print(f"Saved result to {output_path}")
    print("Done! Model is ready for 3D printing or CAD verification.")


def _parse_cli_preserved_zones(zones_arg):
    if not zones_arg:
        return None
    zones_path = Path(zones_arg)
    if zones_path.exists():
        return json.loads(zones_path.read_text(encoding="utf-8"))
    return json.loads(zones_arg)


def execute_pipeline(args):
    dir_val = getattr(args, "direction", DEFAULT_LOAD_DIRECTION)
    load_val = getattr(args, "load", DEFAULT_LOAD_MAGNITUDE)
    margin = getattr(args, "preserve_margin", DEFAULT_PRESERVE_MARGIN)
    overhang = getattr(args, "overhang", DEFAULT_ENABLE_OVERHANG)
    mode = getattr(args, "support_mode", SUPPORT_MODE_CANTILEVER)
    gyroid = getattr(args, "gyroid", DEFAULT_ENABLE_GYROID)
    preserved_zones = _parse_cli_preserved_zones(getattr(args, "preserved_zones", ""))

    target_vol_pct = args.volume * PERCENTAGE_FACTOR
    print("--- OptiShape 3D Topology Optimizer ---")
    print(f"Material: {args.material} | Target Volume: {target_vol_pct:.1f}%")
    print(f"Load: {load_val}N {dir_val} | Support: {mode} | Gyroid: {gyroid}")

    if bool(args.input):
        print(f"Loading input mesh: {args.input}")
    else:
        print("No input provided. Generating sample cantilever beam...")

    result = run_optimization_pipeline(
        output_path=args.output, input_path=args.input,
        material_name=args.material, target_volume=args.volume,
        resolution=args.resolution, max_iterations=args.iterations,
        load_magnitude=load_val, load_direction=dir_val,
        preserve_margin=margin, enable_overhang=overhang,
        iteration_callback=log_iteration, support_mode=mode,
        enable_gyroid=gyroid, preserved_zones=preserved_zones,
    )
    _print_pipeline_summary(result, args.output)


def run():
    args = parse_arguments()
    if args.gui:
        from app.three_d.server import start_server

        start_server(host=args.host, port=args.port)
        return

    try:
        execute_pipeline(args)
    except (FileNotFoundError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)
