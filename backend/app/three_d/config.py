"""Configuration parameters and domain presets for stress calculation."""

# Material presets with Young's Modulus (Pa), Poisson's ratio, density (g/cm^3),
# cost (€/kg), and yield strength (MPa)
MATERIALS = {
    "PLA": {
        "E": 3.5e9,
        "nu": 0.36,
        "density_g_cm3": 1.24,
        "cost_eur_kg": 20.0,
        "yield_strength_mpa": 50.0,
    },
    "PETG": {
        "E": 2.1e9,
        "nu": 0.38,
        "density_g_cm3": 1.27,
        "cost_eur_kg": 22.0,
        "yield_strength_mpa": 45.0,
    },
    "TPU": {
        "E": 0.1e9,
        "nu": 0.45,
        "density_g_cm3": 1.21,
        "cost_eur_kg": 32.0,
        "yield_strength_mpa": 25.0,
    },
    "ALUMINUM": {
        "E": 69.0e9,
        "nu": 0.33,
        "density_g_cm3": 2.70,
        "cost_eur_kg": 45.0,
        "yield_strength_mpa": 276.0,
    },
    "STEEL": {
        "E": 200.0e9,
        "nu": 0.30,
        "density_g_cm3": 7.85,
        "cost_eur_kg": 15.0,
        "yield_strength_mpa": 350.0,
    },
}

# Unit conversions and physical scaling
PA_PER_MPA = 1_000_000.0
MM3_PER_CM3 = 1_000.0
SECONDS_PER_HOUR = 3_600.0
MM_PER_CM = 10.0
CM_PER_M = 100.0
G_PER_KG = 1_000.0
MM_PER_M = 1_000.0
PERCENTAGE_FACTOR = 100.0

# 3D Hexahedral finite element dimensions
NUM_NODES_PER_HEX8 = 8
DOFS_PER_NODE = 3
DOFS_PER_HEX8 = 24
STRESS_TENSOR_COMPONENTS = 6
GAUSS_WEIGHT_FACTOR = 0.125
DEFAULT_UNCONSTRAINED_FOS = 999.0

# Load and kinematic degrees of freedom
FILAMENT_DIAMETER_MM = 1.75
DEFAULT_LOAD_DIRECTION = "-Y"
VALID_LOAD_DIRECTIONS = ["-Y", "+Y", "-Z", "+Z", "+X", "-X"]
DOF_AXIS_MAP = {"X": 0, "Y": 1, "Z": 2}

# SIMP solver parameters
DEFAULT_PENALTY = 3.0
DEFAULT_MIN_STIFFNESS = 1e-4
DEFAULT_MIN_DENSITY = 0.001
DEFAULT_FILTER_RADIUS = 1.5
DEFAULT_MOVE_LIMIT = 0.2
DEFAULT_MAX_ITERATIONS = 30
DEFAULT_VOLUME_FRACTION = 0.4
DEFAULT_CONVERGENCE_TOL = 0.01

# Additive manufacturing and non-design constraints
DEFAULT_PRESERVE_MARGIN = 1
DEFAULT_ENABLE_OVERHANG = False
DEFAULT_MIN_SAFETY_FACTOR = 1.5
DEFAULT_PRINT_FLOW_MM3_S = 15.0
DEFAULT_Z_ANISOTROPIC_FACTOR = 0.60
SUPPORT_MODE_CANTILEVER = "cantilever"
SUPPORT_MODE_SIMPLY_SUPPORTED = "simply_supported"
SUPPORT_MODE_CLAMPED_ENDS = "clamped_both_ends"
VALID_SUPPORT_MODES = ["cantilever", "simply_supported", "clamped_both_ends"]
DEFAULT_GYROID_CELL_SIZE_MM = 10.0
DEFAULT_ENABLE_GYROID = False

# Delamination risk categories
DELAMINATION_RISK_LOW = "low"
DELAMINATION_RISK_MODERATE = "moderate"
DELAMINATION_RISK_HIGH = "high"
SAFETY_FACTOR_CRITICAL_THRESHOLD = 1.0
SAFETY_FACTOR_TARGET_THRESHOLD = 1.5

# Non-design preserved functional zones
ZONE_TYPE_KEEP_IN = "keep_in"
ZONE_TYPE_KEEP_OUT = "keep_out"
ZONE_SHAPE_CYLINDER = "cylinder"
ZONE_SHAPE_BOX = "box"
ZONE_SHAPE_SPHERE = "sphere"
SUPPORTED_INPUT_EXTENSIONS = [
    ".stl", ".3mf", ".obj", ".ply", ".glb", ".gltf", ".off", ".step", ".stp", ".iges", ".igs"
]
VALID_EXPORT_FORMATS = ["stl", "3mf", "obj", "ply", "glb", "off"]
FORMAT_MEDIA_TYPES = {
    "stl": "model/stl",
    "3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
    "obj": "model/obj",
    "ply": "model/ply",
    "glb": "model/gltf-binary",
    "off": "text/plain",
}

# Bisection optimization limits
DEFAULT_BISECTION_TOL = 1e-3
DEFAULT_BISECTION_UPPER = 1e9
DEFAULT_EPSILON = 1e-9

# Physics and mesh parameters
DEFAULT_BEAM_EXTENTS = (60.0, 20.0, 20.0)
DEFAULT_LOAD_MAGNITUDE = 100.0
DEFAULT_RESOLUTION = 30
DEFAULT_SURFACE_ISOVALUE = 0.4
DEFAULT_SMOOTH_ITERATIONS = 5
DEFAULT_VOXEL_PITCH_MM = 4.0
ACTIVE_SOLID_THRESHOLD = 0.5
DEFAULT_CYLINDER_RADIUS_MM = 5.0
DEFAULT_SPHERE_RADIUS_MM = 5.0

# Gyroid infill synthesis parameters
GYROID_CLIP_AMPLITUDE = 1.1
GYROID_DENSITY_LOWER_THRESHOLD = 0.2
GYROID_DENSITY_UPPER_THRESHOLD = 0.8
GYROID_MIN_RELATIVE_DENSITY = 0.2
GYROID_SCALE_FACTOR = 1.5
VOXEL_CENTER_OFFSET = 0.5

# Colormap rendering parameters
COLORMAP_BAND_QUARTER = 0.25
COLORMAP_BAND_HALF = 0.50
COLORMAP_BAND_THREE_QUARTERS = 0.75
COLORMAP_MAX_COLOR_VALUE = 255
COLORMAP_TINT_WEIGHT = 0.70
PADDING_WIDTH_MARCHING_CUBES = 1

# Reporting defaults
DEFAULT_REPORT_JOB_ID = "Job-001"
DEFAULT_REPORT_MATERIAL = "PLA"

# Web server parameters
DEFAULT_SERVER_HOST = "0.0.0.0"
DEFAULT_SERVER_PORT = 8000
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"
MAX_UPLOAD_SIZE_BYTES = 52_428_800
