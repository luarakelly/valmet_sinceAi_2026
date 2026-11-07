// Ask Your Factory — guided boiler-room digital twin.
// Flow: 1) scene + faulty target  2) robot walks, nearby frames light up  3) AI diagnosis on arrival.
// Scene frame from the backend: Y up, floor at y = 0, room centred on x = z = 0.
// Loaded by bootstrap.js after THREE (r180, with OrbitControls/PLYLoader) and Spark are on window.

let scene, camera, renderer, controls;
let sceneModel = null; // SplatMesh (photoreal), THREE.Points (scan) or THREE.Mesh (surface)
let pointCloud = null; // alias kept for the shaders/resize helpers
let viewKind = "splat"; // "splat" (photoreal Gaussian splat) | "points" | "mesh"
let sparkRenderer = null;
let gridHelper = null;
let loadToken = 0; // ignores late loads after the user switched view
let renderMode = "splat"; // "splat" | "heat"
const boundingFramesGroup = new THREE.Group();
let pathLineMesh = null;
let robotAvatar = null;

let assetsData = [];
let framesData = [];
const framesById = new Map(); // frame id (asset id when mapped, else OBJ-xxx) -> frame
let sceneSummary = null;
let roomBounds = { x: [-5, 5], z: [-3, 3], ceiling: 3 };

let routeTargetId = null; // the inspection target (does NOT change when you just select something)
let selectedId = null; // what the copilot panel shows
let nearbyIds = new Set();
let nearLabelIds = new Set(); // the few nearest assets that get a label (keeps the view readable)
let nearbyAssets = []; // [{assetId, dist}] nearest first, shown in the left list
const groupOpen = { near: true, attention: true, healthy: false, detected: false }; // remembers what the user expanded
let showAllFrames = false;

let currentPath = [];
let pathLengths = [0];
let navProgress = 0;
let isNavigating = false;
let navSpeed = 1.5;
let lastFrameTime = performance.now();
let cameraMode = "orbit"; // "orbit" | "follow" | "top" | "free"
let lastRobotPos = null;
let camTween = null;
let sidebarOpen = true;
let copilotOpen = true;

const ROBOT_GROUND_OFFSET = 0.15;
const PROXIMITY_RADIUS = 1.5;
const MAX_NEAR_LABELS = 4;
// Labels keep a fixed on-screen size (not world size), so they never fill the screen up close.
const LABEL_SCREEN_HEIGHT = 0.045; // fraction of the view height
// Follow camera: eye height behind the robot, on the path it already walked (always free space).
// The splat was captured at standing height, so this is where it looks sharp.
const FOLLOW_BACK = 1.8;
const FOLLOW_EYE = 1.6;
const FOLLOW_LOOK_AHEAD = 2.5;
const DEBUG = new URLSearchParams(window.location.search).has("debug");
const LABEL_PRIORITY = { target: 4, selected: 3, fault: 2, near: 1 };
const ROBOT_SPEED_M_S = 0.8;
const ORBIT_VIEW = { position: [-5.5, 3.6, 5.0], target: [0, 0.8, 0] };
const TOP_VIEW = { position: [0, 10, 0.01], target: [0, 0, 0] };
const STATE_COLORS = {
  attention_required: 0xef4444,
  degraded: 0xf97316,
  watch: 0xf59e0b,
  healthy: 0x10b981,
  structure: 0x5eead4,
};
const STATE_CSS = {
  attention_required: "#ef4444",
  degraded: "#f97316",
  watch: "#f59e0b",
  healthy: "#10b981",
  structure: "#5eead4",
};

const freeCam = { active: false, keys: new Set(), yaw: 0, pitch: 0, speed: 2.8, lastTime: 0 };

// ---------------------------------------------------------------- setup

function init3D() {
  const container = document.getElementById("canvas-container");
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x070b12);

  camera = new THREE.PerspectiveCamera(55, container.clientWidth / container.clientHeight, 0.03, 200);
  camera.position.set(...ORBIT_VIEW.position);

  // antialias off: recommended by Spark (no benefit for splats, large cost).
  renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance", preserveDrawingBuffer: true });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.NoToneMapping; // keep the scan's real colours
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  if (window.Spark) {
    sparkRenderer = new window.Spark.SparkRenderer({ renderer: renderer });
  }

  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.rotateSpeed = 0.6;
  controls.zoomSpeed = 0.9;
  controls.panSpeed = 0.8;
  controls.screenSpacePanning = true;
  controls.minDistance = 0.4;
  controls.maxDistance = 18;
  controls.maxPolarAngle = Math.PI * 0.495; // never go below the floor
  controls.target.set(...ORBIT_VIEW.target);

  // r155+ uses physically based light units: these values match the old r128 look.
  scene.add(new THREE.AmbientLight(0xffffff, 1.4));
  const dirLight = new THREE.DirectionalLight(0xbfe9ff, 1.8);
  dirLight.position.set(5, 10, 5);
  scene.add(dirLight);

  gridHelper = new THREE.GridHelper(20, 40, 0x183040, 0x0b1722);
  gridHelper.material.transparent = true;
  gridHelper.material.opacity = 0.35;
  scene.add(gridHelper);
  if (sparkRenderer) scene.add(sparkRenderer);

  scene.add(boundingFramesGroup);
  createRobotAvatar();

  window.addEventListener("resize", onWindowResize);
  setupFreeCamera();
  setupViewportPicking();
  setupOmnibar();
  setupPanels();
  setupToolbar();
  setupHelp();

  document.body.classList.toggle("debug", DEBUG);
  loadSceneModel(sparkRenderer ? "splat" : "points");
  fetchSceneData();
  animate();
  startDevAutoReload();
}

// Development only: reload the page when the server restarts or a frontend file changes.
function startDevAutoReload() {
  if (!/^(localhost|127\.0\.0\.1)$/.test(window.location.hostname)) return;
  let known = null;
  setInterval(async function () {
    try {
      const res = await fetch("/api/dev/version", { cache: "no-store" });
      if (!res.ok) return;
      const v = await res.json();
      const key = v.boot_id + ":" + v.frontend_mtime;
      if (known && key !== known) window.location.reload();
      known = key;
    } catch (e) {
      /* server restarting: try again on the next tick */
    }
  }, 2000);
}

// ---------------------------------------------------------------- scene geometry

function createRobotAvatar() {
  robotAvatar = new THREE.Group();

  const bodyGeo = new THREE.BoxGeometry(0.5, 0.22, 0.6);
  const bodyMat = new THREE.MeshStandardMaterial({
    color: 0x1e293b,
    metalness: 0.8,
    roughness: 0.3,
  });
  const body = new THREE.Mesh(bodyGeo, bodyMat);
  robotAvatar.add(body);

  const wheelGeo = new THREE.CylinderGeometry(0.09, 0.09, 0.08, 16);
  wheelGeo.rotateZ(Math.PI / 2);
  const wheelMat = new THREE.MeshStandardMaterial({
    color: 0x0f172a,
    roughness: 0.8,
  });
  const wheelFL = new THREE.Mesh(wheelGeo, wheelMat);
  wheelFL.position.set(-0.28, -0.06, -0.2);
  const wheelFR = new THREE.Mesh(wheelGeo, wheelMat);
  wheelFR.position.set(0.28, -0.06, -0.2);
  const wheelRL = new THREE.Mesh(wheelGeo, wheelMat);
  wheelRL.position.set(-0.28, -0.06, 0.2);
  const wheelRR = new THREE.Mesh(wheelGeo, wheelMat);
  wheelRR.position.set(0.28, -0.06, 0.2);
  robotAvatar.add(wheelFL);
  robotAvatar.add(wheelFR);
  robotAvatar.add(wheelRL);
  robotAvatar.add(wheelRR);

  const mastGeo = new THREE.CylinderGeometry(0.04, 0.04, 0.28, 12);
  const mastMat = new THREE.MeshStandardMaterial({ color: 0x475569 });
  const mast = new THREE.Mesh(mastGeo, mastMat);
  mast.position.set(0, 0.22, -0.1);
  robotAvatar.add(mast);

  const headGeo = new THREE.BoxGeometry(0.22, 0.12, 0.16);
  const headMat = new THREE.MeshStandardMaterial({
    color: 0x00d2ff,
    emissive: 0x00d2ff,
    emissiveIntensity: 0.45,
  });
  const head = new THREE.Mesh(headGeo, headMat);
  head.position.set(0, 0.38, -0.1);
  robotAvatar.add(head);

  const visorGeo = new THREE.BoxGeometry(0.18, 0.05, 0.02);
  const visorMat = new THREE.MeshBasicMaterial({ color: 0x070c14 });
  const visor = new THREE.Mesh(visorGeo, visorMat);
  visor.position.set(0, 0.39, -0.19);
  robotAvatar.add(visor);

  const light = new THREE.SpotLight(0x00d2ff, 2.8, 7, Math.PI / 4, 0.5);
  light.position.set(0, 0.38, -0.2);
  light.target.position.set(0, -0.5, -3.0);
  robotAvatar.add(light);
  robotAvatar.add(light.target);

  const ringGeo = new THREE.RingGeometry(0.34, 0.42, 40); // small marker under the robot
  ringGeo.rotateX(-Math.PI / 2);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0x00d2ff,
    transparent: true,
    opacity: 0.35,
    side: THREE.DoubleSide,
  });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.position.y = -0.1;
  robotAvatar.add(ring);

  robotAvatar.position.set(0, ROBOT_GROUND_OFFSET, 0);
  scene.add(robotAvatar);
}

function preparePointGeometry(geometry) {
  if (!geometry.hasAttribute("color")) {
    const count = geometry.attributes.position.count;
    const colors = new Float32Array(count * 3);
    for (let i = 0; i < colors.length; i += 3) {
      colors[i] = 0.45;
      colors[i + 1] = 0.78;
      colors[i + 2] = 0.92;
    }
    geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  }
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  return geometry;
}

function createPointMaterial(geometry) {
  if (!geometry.hasAttribute("color")) {
    const color = new Float32Array(geometry.attributes.position.count * 3);
    for (let i = 0; i < color.length; i += 3) {
      color[i] = 0.45;
      color[i + 1] = 0.78;
      color[i + 2] = 0.92;
    }
    geometry.setAttribute("color", new THREE.BufferAttribute(color, 3));
  }

  geometry.computeBoundingBox();
  const bounds = geometry.boundingBox;

  let minY = -1.0;
  let maxY = 1.0;
  if (bounds) {
    minY = bounds.min.y;
    maxY = bounds.max.y;
  }

  let modeVal = 0;
  if (renderMode === "studio") {
    modeVal = 1;
  } else if (renderMode === "heat") {
    modeVal = 2;
  }

  const container = document.getElementById("canvas-container");
  let viewportHeight = 800.0;
  if (container && container.clientHeight > 0) {
    viewportHeight = container.clientHeight;
  }

  let fovHalfRad = THREE.MathUtils.degToRad(30.0);
  if (camera && camera.fov) {
    fovHalfRad = THREE.MathUtils.degToRad(camera.fov * 0.5);
  }
  const projScale = viewportHeight / (2.0 * Math.tan(fovHalfRad));

  let currentPointSize = 0.088;
  if (renderMode === "studio") {
    currentPointSize = 0.065;
  } else if (renderMode === "heat") {
    currentPointSize = 0.065;
  }

  return new THREE.ShaderMaterial({
    uniforms: {
      uPointSize: { value: currentPointSize },
      uScale: { value: projScale },
      uOpacity: { value: 0.98 },
      uMode: { value: modeVal },
      uMinY: { value: minY },
      uMaxY: { value: maxY },
    },
    vertexShader: `
      attribute vec3 color;
      uniform float uPointSize;
      uniform float uScale;
      uniform float uMinY;
      uniform float uMaxY;
      varying vec3 vColor;
      varying float vHeight;

      void main() {
        vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
        float heightRange = max(uMaxY - uMinY, 0.001);
        vHeight = clamp((position.y - uMinY) / heightRange, 0.0, 1.0);
        vColor = color;

        // Perspective splat footprint scaling with distance attenuation
        float depth = max(-viewPosition.z, 0.1);
        gl_PointSize = clamp(uPointSize * (uScale / depth), 3.0, 128.0);
        gl_Position = projectionMatrix * viewPosition;
      }
    `,
    fragmentShader: `
      uniform float uOpacity;
      uniform int uMode;
      varying vec3 vColor;
      varying float vHeight;

      vec3 heatColor(float value) {
        vec3 cool = vec3(0.04, 0.45, 0.95);
        vec3 mid = vec3(0.12, 0.92, 0.55);
        vec3 warm = vec3(0.98, 0.72, 0.08);
        vec3 hot = vec3(0.95, 0.18, 0.06);

        if (value < 0.33) {
          return mix(cool, mid, value / 0.33);
        } else if (value < 0.66) {
          return mix(mid, warm, (value - 0.33) / 0.33);
        } else {
          return mix(warm, hot, (value - 0.66) / 0.34);
        }
      }

      void main() {
        // Continuous soft Gaussian splat profile with ellipsoidal / circular falloff
        vec2 uv = gl_PointCoord * 2.0 - 1.0;
        float r2 = dot(uv, uv);
        if (r2 > 1.0) {
          discard;
        }

        // True Gaussian radial attenuation: exp(-2.0 * r^2)
        float gaussian = exp(-2.0 * r2);
        float edgeCut = 1.0 - smoothstep(0.70, 1.0, r2);
        float splatAlpha = gaussian * edgeCut * uOpacity;
        if (splatAlpha < 0.02) {
          discard;
        }

        // Pseudo-3D spherical normal impostor
        float z = sqrt(max(0.0, 1.0 - r2));
        vec3 normal = normalize(vec3(uv.x * 0.6, -uv.y * 0.6, z * 1.5));
        vec3 lightDir = normalize(vec3(0.35, 0.75, 0.55));
        float diff = max(dot(normal, lightDir), 0.0);
        float shade = 0.85 + 0.15 * diff;

        vec3 outputColor = vColor;
        if (uMode == 0) {
          // Photorealistic Splat mode: full fidelity, gamma adjustment & 3D curvature
          outputColor = pow(vColor, vec3(0.92)) * shade;
          outputColor += vec3(0.025) * exp(-4.0 * r2);
        } else if (uMode == 1) {
          // Studio Engineering mode: digital twin cyber-cyan height gradient
          vec3 cyberGradient = mix(vec3(0.03, 0.22, 0.38), vec3(0.00, 0.88, 0.98), vHeight);
          outputColor = mix(outputColor, cyberGradient, 0.65) * shade;
          outputColor += vec3(0.04, 0.10, 0.15) * exp(-4.0 * r2);
        } else if (uMode == 2) {
          // Heatmap thermal inspection mode
          outputColor = heatColor(vHeight) * shade;
        }

        gl_FragColor = vec4(outputColor, splatAlpha);
        #include <colorspace_fragment>
      }
    `,
    transparent: true,
    depthWrite: false,
    depthTest: true,
    blending: THREE.NormalBlending,
  });
}

function createMeshMaterial(geometry) {
  geometry.computeBoundingBox();
  const bounds = geometry.boundingBox;
  let modeVal = 0;
  if (renderMode === "studio") {
    modeVal = 1;
  } else if (renderMode === "heat") {
    modeVal = 2;
  }
  return new THREE.ShaderMaterial({
    uniforms: {
      uMode: { value: modeVal },
      uOpacity: { value: 1.0 },
      uMinY: { value: bounds.min.y },
      uMaxY: { value: bounds.max.y },
    },
    vertexShader: `
      attribute vec3 color;
      uniform float uMinY;
      uniform float uMaxY;
      varying vec3 vColor;
      varying vec3 vNormal;
      varying float vHeight;
      void main() {
        vColor = color;
        vNormal = normalize(mat3(modelMatrix) * normal);
        vHeight = clamp((position.y - uMinY) / max(uMaxY - uMinY, 0.001), 0.0, 1.0);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: `
      uniform int uMode;
      uniform float uOpacity;
      varying vec3 vColor;
      varying vec3 vNormal;
      varying float vHeight;
      vec3 heatColor(float v) {
        vec3 a = vec3(0.04, 0.45, 0.95), b = vec3(0.12, 0.92, 0.55), c = vec3(0.98, 0.72, 0.08), d = vec3(0.95, 0.18, 0.06);
        if (v < 0.33) return mix(a, b, v / 0.33);
        if (v < 0.66) return mix(b, c, (v - 0.33) / 0.33);
        return mix(c, d, (v - 0.66) / 0.34);
      }
      void main() {
        vec3 n = normalize(vNormal);
        if (!gl_FrontFacing) n = -n;
        vec3 key = normalize(vec3(0.35, 0.85, 0.45));
        vec3 fill = normalize(vec3(-0.6, 0.3, -0.5));
        float light = 0.42 + 0.48 * max(dot(n, key), 0.0) + 0.18 * max(dot(n, fill), 0.0) + 0.08 * n.y;
        vec3 base = vColor;
        if (uMode == 1) {
          base = mix(vec3(0.70, 0.74, 0.78), vec3(0.55, 0.80, 0.92), vHeight * 0.6);
        } else if (uMode == 2) {
          base = heatColor(vHeight);
        }
        gl_FragColor = vec4(base * light, uOpacity);
        #include <colorspace_fragment>
      }
    `,
    side: THREE.DoubleSide,
  });
}

function removeSceneModel() {
  if (!sceneModel) return;
  scene.remove(sceneModel);
  if (window.Spark && sceneModel instanceof window.Spark.SplatMesh) {
    sceneModel.dispose();
  } else if (sceneModel.geometry) {
    sceneModel.geometry.dispose();
  }
  sceneModel = null;
  pointCloud = null;
}

function markViewButtons(kind) {
  document.querySelectorAll(".render-mode-btn[data-view]").forEach(function (b) {
    b.classList.toggle("active", b.dataset.view === kind);
  });
  setText("view-name", { splat: "Photoreal", points: "Points", mesh: "Mesh" }[kind] || kind);
}

function setLoading(fraction, text) {
  const screen = document.getElementById("loading-screen");
  if (fraction === null) {
    screen.classList.add("done");
    return;
  }
  screen.classList.remove("done");
  document.getElementById("loading-fill").style.width = Math.round(fraction * 100) + "%";
  if (text) setText("loading-text", text);
}

// fetch() with download progress (the splat is ~13 MB).
async function fetchBytes(url, onProgress) {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.status + " " + res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* not JSON */ }
    throw new Error(detail);
  }
  const total = Number(res.headers.get("Content-Length")) || 0;
  if (!res.body || !total) return res.arrayBuffer();
  const reader = res.body.getReader();
  const out = new Uint8Array(total);
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    out.set(value, received);
    received += value.length;
    onProgress(received / total);
  }
  return out.buffer;
}

function loadSceneModel(kind) {
  if (kind === "splat" && !sparkRenderer) {
    showToast("Photoreal view unavailable (splat renderer did not load) — showing scan points");
    kind = "points";
  }
  viewKind = kind;
  markViewButtons(kind);
  const token = ++loadToken;
  if (kind === "splat") {
    loadSplatModel(token);
    return;
  }
  const loader = new THREE.PLYLoader();
  const url = kind === "mesh" ? "/api/scene/boiler-room-mesh.ply" : "/api/scene/boiler-room.ply";
  showToast(kind === "mesh" ? "Loading surface mesh…" : "Loading scan points…");
  loader.load(
    url,
    function (geometry) {
      if (token !== loadToken) return;
      removeSceneModel();
      if (kind === "mesh") {
        geometry.computeVertexNormals();
        sceneModel = new THREE.Mesh(geometry, createMeshMaterial(geometry));
      } else {
        preparePointGeometry(geometry);
        sceneModel = new THREE.Points(geometry, createPointMaterial(geometry));
      }
      pointCloud = sceneModel;
      scene.add(sceneModel);
      gridHelper.visible = true;
      applyRenderMode(renderMode);
      setLoading(null);
      const count = kind === "mesh"
        ? Math.round((geometry.index ? geometry.index.count : geometry.attributes.position.count) / 3)
        : geometry.attributes.position.count;
      showToast((kind === "mesh" ? "Mesh: " : "Scan: ") + count.toLocaleString() + (kind === "mesh" ? " triangles" : " points"));
    },
    undefined,
    function (err) {
      console.warn("Could not load " + url, err);
      if (token !== loadToken) return;
      if (kind === "mesh") {
        showToast("Mesh not available — showing scan points");
        loadSceneModel("points");
      } else {
        showToast("Scan could not be loaded — is the backend running?");
      }
    },
  );
}

// Photoreal: the real Gaussian splat (already in the scene frame), rendered by Spark.
// The first request can take ~10–30 s while the server converts the raw scan once.
// Photoreal: the real Gaussian splat (already in the scene frame), rendered by Spark.
// The server prepares the file at startup, so this is a plain ~13 MB download.
async function loadSplatModel(token) {
  setLoading(0.02, "Loading the photoreal scan…");
  try {
    const bytes = await fetchBytes("/api/scene/boiler-room.splat", function (f) {
      setLoading(0.05 + f * 0.85, "Loading the photoreal scan… " + Math.round(f * 100) + "%");
    });
    if (token !== loadToken) return;
    setLoading(0.95, "Preparing the 3D view…");
    const splat = new window.Spark.SplatMesh({ fileBytes: bytes, fileType: "splat", fileName: "boiler-room.splat" });
    await splat.initialized;
    if (token !== loadToken) {
      splat.dispose();
      return;
    }
    removeSceneModel();
    sceneModel = splat;
    scene.add(splat);
    gridHelper.visible = false; // the real floor is in the splat
    if (renderMode === "heat") applyRenderMode("splat");
    setLoading(null);
  } catch (err) {
    console.warn("Photoreal scene unavailable", err);
    if (token !== loadToken) return;
    showToast("Photoreal scene unavailable (" + err.message + ") — showing scan points");
    setLoading(0.5, "Loading the point cloud instead…");
    loadSceneModel("points");
  }
}

function applyRenderMode(mode) {
  renderMode = mode;
  document.getElementById("btn-heat").classList.toggle("active", mode === "heat");
  if (sceneModel && sceneModel.material && sceneModel.material.uniforms && sceneModel.material.uniforms.uMode) {
    sceneModel.material.uniforms.uMode.value = mode === "heat" ? 2 : 0;
  }
}

// ---------------------------------------------------------------- data

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  let body = null;
  try {
    body = await res.json();
  } catch (e) {
    body = null;
  }
  if (!res.ok) {
    const detail = body && body.detail ? body.detail : res.status + " " + res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

async function fetchSceneData() {
  try {
    const [assets, frames, summary] = await Promise.all([
      fetchJson("/api/assets"),
      fetchJson("/api/scene/frames"),
      fetchJson("/api/scene/summary"),
    ]);
    assetsData = assets;
    framesData = frames;
    sceneSummary = summary;
    if (summary.room) {
      roomBounds = summary.room;
    }
    framesById.clear();
    frames.forEach(function (f) {
      framesById.set(f.id, f);
    });

    routeTargetId = summary.target_asset_id;
    selectedId = routeTargetId;
    robotAvatar.position.set(summary.entry.x, ROBOT_GROUND_OFFSET, summary.entry.z);
    lastRobotPos = robotAvatar.position.clone();

    document.getElementById("asset-count").innerText =
      frames.length + " frames · " + (summary.mapped_asset_count || 0) + " assets";

    buildFrames(frames);
    renderAssetList(assetsData);
    await loadRoute(routeTargetId);
    showSelection(routeTargetId);
    setStep(1);
  } catch (e) {
    console.error("Scene data error", e);
    showToast("Could not load the scene data: " + e.message);
  }
}

// ---------------------------------------------------------------- 3D frames

function createFloatingLabelSprite(tag, stateText, colorHex) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 72;
  const ctx = canvas.getContext("2d");

  ctx.fillStyle = "rgba(10, 18, 30, 0.88)";
  ctx.strokeStyle = colorHex;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.roundRect(4, 4, 248, 64, 12);
  ctx.fill();
  ctx.stroke();

  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 26px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(tag, 128, 34);

  ctx.fillStyle = colorHex;
  ctx.font = "bold 18px monospace";
  ctx.fillText(stateText.toUpperCase(), 128, 58);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const spriteMat = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    opacity: 0.0,
    depthTest: false,
    sizeAttenuation: false,
  });
  const sprite = new THREE.Sprite(spriteMat);
  sprite.scale.set(LABEL_SCREEN_HEIGHT * (256 / 72), LABEL_SCREEN_HEIGHT, 1);
  sprite.renderOrder = 10;
  return sprite;
}

function frameState(frame) {
  return frame.asset_id ? frame.state || "healthy" : "structure";
}

function buildFrames(frames) {
  while (boundingFramesGroup.children.length > 0) {
    const child = boundingFramesGroup.children[0];
    boundingFramesGroup.remove(child);
  }
  frames.forEach(function (frame) {
    const [w, h, d] = frame.size;
    const [x, y, z] = frame.pos;
    const state = frameState(frame);
    const colorHex = STATE_COLORS[state] || STATE_COLORS.structure;

    const boxGeo = new THREE.BoxGeometry(w, h, d);
    const lineMat = new THREE.LineBasicMaterial({ color: colorHex, transparent: true, opacity: 0, depthTest: true });
    const box = new THREE.LineSegments(new THREE.EdgesGeometry(boxGeo), lineMat);
    box.position.set(x, y, z);

    const fillMat = new THREE.MeshBasicMaterial({ color: colorHex, transparent: true, opacity: 0, depthWrite: false });
    const fill = new THREE.Mesh(boxGeo, fillMat);
    box.add(fill);

    let label = null;
    if (frame.asset_id) {
      label = createFloatingLabelSprite(frame.tag || frame.id, (frame.state || "").replace(/_/g, " "), STATE_CSS[state]);
      label.position.set(0, h / 2 + 0.12, 0);
      label.material.opacity = 0;
      box.add(label);
    }

    box.userData = { id: frame.id, frame: frame, lineMat: lineMat, fillMat: fillMat, label: label, shown: false };
    boundingFramesGroup.add(box);
  });
  refreshFrameStyles();
}

// Which frames are drawn, and how strongly:
//   target / selected: full + label;  nearest few assets: full + label;
//   other nearby assets: outline only;  other mapped assets: faint;
//   unmapped structure: hidden unless "All frames" is on.
function refreshFrameStyles() {
  boundingFramesGroup.children.forEach(function (box) {
    const u = box.userData;
    const f = u.frame;
    const isTarget = f.id === routeTargetId;
    const isSelected = f.id === selectedId;
    const isNear = nearbyIds.has(f.id);
    let line = 0;
    let fill = 0;
    let label = 0;
    if (isTarget || isSelected) {
      line = 1;
      fill = isTarget ? 0.16 : 0.1;
      label = 1;
    } else if (isNear && f.asset_id) {
      line = 0.9;
      fill = nearLabelIds.has(f.id) ? 0.06 : 0;
      label = nearLabelIds.has(f.id) ? 1 : 0;
    } else if (isNear && showAllFrames) {
      line = 0.5;
    } else if (f.asset_id) {
      line = showAllFrames ? 0.55 : 0.28;
    } else if (showAllFrames) {
      line = 0.35;
    }
    u.lineMat.opacity = line;
    u.fillMat.opacity = fill;
    if (u.label) {
      u.label.material.opacity = label;
    }
    u.shown = line > 0;
    box.visible = u.shown;
    u.priority = isTarget ? LABEL_PRIORITY.target
      : isSelected ? LABEL_PRIORITY.selected
      : f.asset_id && frameState(f) !== "healthy" ? LABEL_PRIORITY.fault
      : LABEL_PRIORITY.near;
  });
}

// Hide a label when it would overlap a more important one on screen.
const _labelPos = new THREE.Vector3();
let lastDeclutter = 0;
function declutterLabels() {
  const w = renderer.domElement.clientWidth;
  const h = renderer.domElement.clientHeight;
  const labelH = (LABEL_SCREEN_HEIGHT * h) / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)));
  const labelW = labelH * (256 / 72);
  const candidates = [];
  boundingFramesGroup.children.forEach(function (box) {
    const u = box.userData;
    if (!u.label) return;
    u.label.visible = false;
    if (!box.visible || u.label.material.opacity <= 0) return;
    u.label.getWorldPosition(_labelPos);
    const dist = _labelPos.distanceTo(camera.position);
    _labelPos.project(camera);
    if (_labelPos.z > 1 || Math.abs(_labelPos.x) > 1.1 || Math.abs(_labelPos.y) > 1.1) return;
    candidates.push({ u: u, x: (_labelPos.x + 1) * 0.5 * w, y: (1 - _labelPos.y) * 0.5 * h, dist: dist });
  });
  candidates.sort(function (a, b) { return b.u.priority - a.u.priority || a.dist - b.dist; });
  const placed = [];
  candidates.forEach(function (c) {
    const hit = placed.some(function (p) { return Math.abs(p.x - c.x) < labelW && Math.abs(p.y - c.y) < labelH; });
    if (!hit) {
      c.u.label.visible = true;
      placed.push(c);
    }
  });
}

// ---------------------------------------------------------------- route & robot

async function loadRoute(targetId) {
  try {
    const data = await fetchJson("/api/navigation/path?target_id=" + encodeURIComponent(targetId));
    currentPath = data.waypoints;
    pathLengths = cumulativeLengths(currentPath);
    routeTargetId = data.target_id || targetId;
    document.getElementById("hud-target-name").innerText = "Target: " + (data.target_tag || targetId);
    document.getElementById("hud-dist").innerText = data.total_distance_m + " m";
    renderPathRibbon(currentPath);
    resetRobot();
    refreshFrameStyles();
    renderTargetCard();
    return true;
  } catch (err) {
    showToast("No collision-free route: " + err.message);
    return false;
  }
}

function cumulativeLengths(waypoints) {
  const lengths = [0];
  for (let i = 1; i < waypoints.length; i++) {
    const dx = waypoints[i].x - waypoints[i - 1].x;
    const dz = waypoints[i].z - waypoints[i - 1].z;
    lengths.push(lengths[i - 1] + Math.hypot(dx, dz));
  }
  return lengths;
}

function renderPathRibbon(waypoints) {
  if (pathLineMesh) {
    scene.remove(pathLineMesh);
  }

  const points = waypoints.map(function (p) {
    return new THREE.Vector3(p.x, p.y + 0.02, p.z);
  });
  const curve = new THREE.CatmullRomCurve3(points);
  const tubeGeo = new THREE.TubeGeometry(curve, 64, 0.035, 8, false);
  const tubeMat = new THREE.MeshBasicMaterial({
    color: 0x00d2ff,
    transparent: true,
    opacity: 0.75,
  });
  pathLineMesh = new THREE.Mesh(tubeGeo, tubeMat);
  scene.add(pathLineMesh);
}

function resetRobot() {
  isNavigating = false;
  navProgress = 0;
  document.getElementById("nav-btn-text").innerHTML = "▶ Start inspection";
  document.getElementById("hud-nav-fill").style.width = "0%";
  if (currentPath.length > 0) {
    robotAvatar.position.set(currentPath[0].x, ROBOT_GROUND_OFFSET, currentPath[0].z);
    if (currentPath.length > 1) {
      robotAvatar.rotation.y = Math.atan2(currentPath[1].x - currentPath[0].x, currentPath[1].z - currentPath[0].z);
    }
  }
  lastRobotPos = robotAvatar.position.clone();
  nearbyIds = new Set();
  nearLabelIds = new Set();
  renderNearby([]);
  refreshFrameStyles();
  setStep(1);
}

function toggleNavigation() {
  if (currentPath.length < 2) {
    showToast("No route loaded yet");
    return;
  }
  if (navProgress >= 1.0) {
    resetRobot();
  }
  isNavigating = !isNavigating;
  document.getElementById("nav-btn-text").innerHTML = isNavigating ? "❚❚ Pause" : "▶ Resume";
  if (isNavigating) {
    setStep(2);
    groupOpen.near = true;
    if (!sidebarOpen) toggleLeftSidebar();
    if (cameraMode === "orbit" || cameraMode === "top") {
      setCameraMode("follow");
    }
    hideHelp();
  }
}

async function goTo(assetId) {
  if (await loadRoute(assetId)) {
    renderAssetList(filteredAssets());
    showSelection(assetId);
    toggleNavigation();
  }
}

function onArrival() {
  isNavigating = false;
  document.getElementById("nav-btn-text").innerHTML = "↻ Run again";
  setStep(3);
  const frame = framesById.get(routeTargetId);
  showToast("Arrived at " + (frame ? frame.tag : routeTargetId) + " — AI diagnosis");
  if (!copilotOpen) {
    toggleCopilotDrawer();
  }
  showSelection(routeTargetId);
  if (frame) {
    if (cameraMode === "follow") setCameraMode("orbit");
    focusOn(frame.pos, frame.size);
  }
}

// ---------------------------------------------------------------- proximity

function distanceToFootprint(rx, rz, frame) {
  const [x, , z] = frame.pos;
  const [w, , d] = frame.size;
  const dx = Math.max(Math.abs(rx - x) - w / 2, 0);
  const dz = Math.max(Math.abs(rz - z) - d / 2, 0);
  return Math.hypot(dx, dz);
}

function checkProximityEvents(rx, rz) {
  const near = [];
  framesData.forEach(function (f) {
    const dist = distanceToFootprint(rx, rz, f);
    if (dist <= PROXIMITY_RADIUS) {
      near.push({ frame: f, dist: dist });
    }
  });
  const ids = new Set(near.map(function (n) { return n.frame.id; }));
  let changed = ids.size !== nearbyIds.size;
  if (!changed) {
    ids.forEach(function (id) {
      if (!nearbyIds.has(id)) changed = true;
    });
  }
  if (changed) {
    nearbyIds = ids;
    nearLabelIds = new Set(
      near.filter(function (n) { return n.frame.asset_id; })
        .sort(function (a, b) { return a.dist - b.dist; })
        .slice(0, MAX_NEAR_LABELS)
        .map(function (n) { return n.frame.id; }),
    );
    refreshFrameStyles();
    renderNearby(near);
  }
}
window.appCheckProximityEvents = checkProximityEvents;

// Nearby assets live in the left Equipment list as the "Near the robot" group (no floating panel).
function renderNearby(near) {
  nearbyAssets = near
    .filter(function (n) { return n.frame.asset_id; })
    .sort(function (a, b) { return a.dist - b.dist; })
    .map(function (n) { return { assetId: n.frame.asset_id, dist: n.dist }; });
  renderAssetList(filteredAssets());
}

// ---------------------------------------------------------------- selection & copilot panel

function showSelection(id) {
  selectedId = id;
  refreshFrameStyles();
  document.querySelectorAll(".asset-card").forEach(function (el) {
    el.classList.toggle("active", el.dataset.id === id);
  });
  const frame = framesById.get(id);
  if (frame && !frame.asset_id) {
    renderStructureCard(frame);
    return;
  }
  runCopilotDiagnosis(id);
}

function renderStructureCard(frame) {
  setText("card-asset-tag", frame.id + " · " + prettyClass(frame.label));
  setText("card-asset-meta", "Detected 3D object · not linked to a builder-pack asset");
  setText("card-mapping-note", frame.point_count + " points · " + frame.size.map(function (s) { return s.toFixed(2); }).join(" × ") + " m");
  const badge = document.getElementById("card-health-badge");
  badge.innerText = "STRUCTURE";
  badge.style.color = STATE_CSS.structure;
  badge.style.borderColor = STATE_CSS.structure;
  document.getElementById("diag-block").style.display = "none";
}

async function runCopilotDiagnosis(assetId, question) {
  const body = { asset_id: assetId };
  if (question) body.query = question;
  document.getElementById("diag-block").style.display = "";
  const thinking = question ? addMessage("ai", "Thinking…") : null;
  try {
    const [dossier, diag] = await Promise.all([
      fetchJson("/api/assets/" + encodeURIComponent(assetId)),
      fetchJson("/api/copilot/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    ]);
    if (thinking) thinking.remove();
    if (selectedId === assetId || question) updateCopilotDrawer(dossier, diag);
    if (question) {
      const ids = (diag.citations || []).filter(function (c) { return c.source_type !== "data_quality"; })
        .map(function (c) { return c.source_id; }).slice(0, 6);
      addMessage("ai", diag.answer || diag.diagnosis_summary || diag.diagnosis || "No answer.", ids);
    }
  } catch (err) {
    console.error("Copilot error", err);
    if (thinking) thinking.remove();
    if (question) addMessage("ai", "Sorry, that failed: " + err.message);
    else showToast("Copilot: " + err.message);
  }
}

// Conversation thread in the right column; every answer stays here (never only in a toast).
function addMessage(role, text, chips) {
  const thread = document.getElementById("cp-thread");
  const msg = document.createElement("div");
  msg.className = "msg msg-" + role;
  msg.textContent = text;
  if (chips && chips.length) {
    const row = document.createElement("div");
    row.className = "msg-chips";
    chips.forEach(function (id) {
      const chip = document.createElement("span");
      chip.className = "evidence-chip";
      chip.textContent = id;
      row.appendChild(chip);
    });
    msg.appendChild(row);
  }
  thread.appendChild(msg);
  while (thread.children.length > 30) thread.removeChild(thread.firstChild);
  thread.scrollTop = thread.scrollHeight;
  if (!copilotOpen) toggleCopilotDrawer();
  return msg;
}

function updateCopilotDrawer(dossier, diag) {
  const state = dossier.current_state || dossier.state || {};
  const tag = diag.tag || dossier.tag || dossier.asset_id;
  const health = diag.health_score != null ? diag.health_score : state.health_score;
  const condition = diag.condition_state || state.condition_state || "unknown";
  const css = STATE_CSS[condition] || STATE_CSS.healthy;

  setText("card-asset-tag", tag);
  setText("card-asset-meta", prettyClass(diag.asset_class || dossier.asset_class) + " · " + (dossier.area_name || "Boiler room"));
  const frame = framesById.get(dossier.asset_id);
  setText("card-mapping-note", frame && frame.asset_id
    ? "Synthetic mapping → 3D object " + frame.scene_id + " · confidence " + (frame.mapping_confidence != null ? frame.mapping_confidence : "—") +
      (frame.id === routeTargetId ? " · inspection target" : "")
    : "Not placed in the 3D scene.");
  const badge = document.getElementById("card-health-badge");
  badge.innerText = Math.round(health || 0) + "% " + condition.replace(/_/g, " ").toUpperCase();
  badge.style.color = css;
  badge.style.borderColor = css;

  // Observation / hypothesis / next safe check, built from the grounded result.
  const citations = diag.citations || [];
  const evidence = citations.filter(function (c) { return ["telemetry", "event", "service_case", "work_order"].indexOf(c.source_type) >= 0; });
  const docs = citations.filter(function (c) { return c.source_type === "doc"; });
  const dq = citations.filter(function (c) { return c.source_type === "data_quality"; });
  const healthy = condition === "healthy";
  setText("dx-observation", "Health " + Math.round(health || 0) + "/100 · " + condition.replace(/_/g, " ") +
    " · " + evidence.length + " piece" + (evidence.length === 1 ? "" : "s") + " of evidence");
  const hypo = /Hypothesis:\s*([^.]*)/.exec(diag.diagnosis || "");
  setText("dx-hypothesis", healthy ? "No significant deviation — routine monitoring" : hypo ? hypo[1] : prettyClass(diag.issue_code));
  const actions = diag.recommended_actions || [];
  setText("dx-next", actions[1] || actions[0] || "Continue routine monitoring.");
  const confidence = diag.confidence_score != null ? diag.confidence_score : diag.model_confidence;
  setText("dx-conf", confidence != null ? Number(confidence).toFixed(2) : "—");
  const fill = document.getElementById("dx-conf-fill");
  fill.style.width = Math.round((confidence || 0) * 100) + "%";
  fill.style.background = css;
  setText("dx-conf-note", dq.length ? "Lowered by " + dq.length + " data-quality issue" + (dq.length === 1 ? "" : "s") + " and the synthetic 3D mapping." : "");
  document.getElementById("diag-block").style.borderColor = css;

  // "Why?" — one row per evidence item: ID + short text. Documents last.
  const list = document.getElementById("dx-why-list");
  list.innerHTML = "";
  evidence.concat(docs).forEach(function (c) {
    const li = document.createElement("li");
    const id = document.createElement("span");
    id.className = "evidence-chip";
    id.textContent = c.source_id;
    const text = document.createElement("span");
    const d = (c.description || "").replace(/\s*\[[^\]]*\]\s*$/, "");
    text.textContent = d.length > 140 ? d.slice(0, 137) + "…" : d;
    text.title = c.description || "";
    li.appendChild(id);
    li.appendChild(text);
    list.appendChild(li);
  });
  setText("dx-why-title", "Why? " + evidence.length + " evidence · " + docs.length + " document" + (docs.length === 1 ? "" : "s"));

  const llm = diag.grounded_mode && diag.grounded_mode !== "deterministic-evidence-engine";
  setText("copilot-model-badge", llm ? "Grounded answer · " + diag.grounded_mode + " (citations verified)" : "Grounded answer · evidence engine (no LLM)");
}





// ---------------------------------------------------------------- equipment list

function assetState(a) {
  return (a.state && a.state.condition_state) || "healthy";
}

function renderAssetList(assets) {
  const list = document.getElementById("asset-list-container");
  list.innerHTML = "";
  const attention = assets.filter(function (a) { return assetState(a) !== "healthy"; })
    .sort(function (a, b) { return (a.state ? a.state.health_score : 100) - (b.state ? b.state.health_score : 100); });
  const healthy = assets.filter(function (a) { return assetState(a) === "healthy"; });
  const byId = new Map(assets.map(function (a) { return [a.asset_id, a]; }));
  const near = nearbyAssets
    .filter(function (n) { return byId.has(n.assetId); })
    .map(function (n) { return { asset: byId.get(n.assetId), dist: n.dist }; });

  function group(key, title, items, card, extraClass) {
    if (items.length === 0) return;
    const details = document.createElement("details");
    details.className = "asset-group" + (extraClass ? " " + extraClass : "");
    details.open = groupOpen[key];
    details.ontoggle = function () { groupOpen[key] = details.open; };
    const summary = document.createElement("summary");
    summary.innerText = title + " (" + items.length + ")";
    details.appendChild(summary);
    items.forEach(function (item) {
      details.appendChild(card(item));
    });
    list.appendChild(details);
  }
  group("near", "Near the robot · " + PROXIMITY_RADIUS + " m", near, function (n) {
    return assetCard(n.asset, n.dist.toFixed(1) + " m");
  }, "near-group");
  group("attention", "Needs attention", attention, assetCard, "attention-group");
  group("healthy", "Healthy", healthy, assetCard, "healthy-group");
  renderDetectedGroup(list);
  renderTargetCard();
}

// "Detected objects": the extraction result (challenge criterion 1) in one place.
function renderDetectedGroup(list) {
  if (!framesData.length) return;
  const mapped = framesData.filter(function (f) { return f.asset_id; }).length;
  const counts = {};
  framesData.filter(function (f) { return !f.asset_id; }).forEach(function (f) {
    const k = prettyClass(f.label);
    counts[k] = (counts[k] || 0) + 1;
  });
  const details = document.createElement("details");
  details.className = "asset-group detected-group";
  details.open = groupOpen.detected;
  details.ontoggle = function () { groupOpen.detected = details.open; };
  const summary = document.createElement("summary");
  summary.innerText = "Detected objects (" + framesData.length + ")";
  details.appendChild(summary);
  const body = document.createElement("div");
  body.className = "detected-body";
  const rows = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a]; })
    .map(function (k) { return "<li><span>" + escapeHtml(k) + "</span><b>" + counts[k] + "</b></li>"; }).join("");
  body.innerHTML =
    '<div class="detected-line"><b>' + mapped + "</b> mapped to builder-pack assets (synthetic mapping)</div>" +
    '<div class="detected-line"><b>' + (framesData.length - mapped) + "</b> other structures, by shape:</div>" +
    '<ul class="detected-counts">' + rows + "</ul>";
  const btn = document.createElement("button");
  btn.className = "action-pill" + (showAllFrames ? " active" : "");
  btn.textContent = showAllFrames ? "Hide extra frames in 3D" : "Show all " + framesData.length + " in 3D";
  btn.onclick = function () {
    showAllFrames = !showAllFrames;
    refreshFrameStyles();
    renderAssetList(filteredAssets());
  };
  body.appendChild(btn);
  details.appendChild(body);
  list.appendChild(details);
}

// Pinned inspection target at the top of the left column.
function renderTargetCard() {
  const el = document.getElementById("target-card");
  const a = assetsData.find(function (x) { return x.asset_id === routeTargetId; });
  if (!a) {
    el.innerHTML = "";
    return;
  }
  const state = assetState(a);
  const dist = currentPath.length > 1 ? pathLengths[pathLengths.length - 1].toFixed(1) + " m" : "";
  el.innerHTML =
    '<div class="target-label">Inspection target</div>' +
    '<div class="target-row"><span class="status-dot status-' + dotClass(state) + '"></span><b>' + escapeHtml(a.tag) + "</b>" +
    "<span>" + escapeHtml(prettyClass(a.asset_class)) + "</span>" +
    '<span class="asset-health" style="color:' + (STATE_CSS[state] || STATE_CSS.healthy) + '">' + Math.round(a.state ? a.state.health_score : 100) + "%</span></div>" +
    '<div class="target-row"><span class="muted">Route ' + dist + '</span><button class="btn" id="btn-target-go">Go ▶</button></div>';
  el.querySelector(".target-row").onclick = function () { selectAndFocus(a.asset_id); };
  document.getElementById("btn-target-go").onclick = function (e) {
    e.stopPropagation();
    goTo(a.asset_id);
  };
}

function assetCard(a, distanceText) {
  const state = assetState(a);
  const health = a.state ? a.state.health_score : 100;
  const card = document.createElement("div");
  card.className = "asset-card" + (a.asset_id === selectedId ? " active" : "");
  card.dataset.id = a.asset_id;
  const isTarget = a.asset_id === routeTargetId;
  card.innerHTML =
    '<div class="asset-card-main">' +
    '<span class="status-dot status-' + dotClass(state) + '"></span>' +
    "<b>" + escapeHtml(a.tag) + "</b>" +
    '<span class="asset-class">' + escapeHtml(prettyClass(a.asset_class)) + (isTarget ? " · target" : "") +
    (typeof distanceText === "string" ? " · " + escapeHtml(distanceText) : "") + "</span>" +
    '<span class="asset-health" style="color:' + (STATE_CSS[state] || STATE_CSS.healthy) + '">' + Math.round(health) + "%</span>" +
    "</div>" +
    '<div class="asset-actions">' +
    '<button class="action-pill" data-act="route">🚶 Route here</button>' +
    "</div>";
  card.querySelector(".asset-card-main").onclick = function () {
    selectAndFocus(a.asset_id);
  };
  card.querySelector('[data-act="route"]').onclick = function (e) {
    e.stopPropagation();
    goTo(a.asset_id);
  };
  return card;
}

function selectAndFocus(id) {
  showSelection(id);
  const frame = framesById.get(id);
  if (frame) {
    if (cameraMode !== "orbit") setCameraMode("orbit");
    focusOn(frame.pos, frame.size);
  } else {
    showToast("This asset has no 3D frame");
  }
}

function filteredAssets() {
  const q = document.getElementById("asset-search").value.trim().toLowerCase();
  if (!q) return assetsData;
  return assetsData.filter(function (a) {
    return (a.tag + " " + a.asset_class + " " + (a.area_name || "") + " " + assetState(a)).toLowerCase().includes(q);
  });
}

// ---------------------------------------------------------------- camera

function setCameraMode(mode) {
  if (freeCam.active && mode !== "free") {
    exitFreeCamera();
  }
  cameraMode = mode;
  ["orbit", "follow", "top"].forEach(function (m) {
    document.getElementById("btn-cam-" + m).classList.toggle("active", m === mode);
  });
  if (mode === "top") {
    tweenCamera(new THREE.Vector3(...TOP_VIEW.position), new THREE.Vector3(...TOP_VIEW.target));
  }
  controls.enableRotate = mode !== "follow";
  controls.enablePan = mode !== "follow";
  lastRobotPos = robotAvatar.position.clone();
}

// Point on the current route at a given distance from its start (clamped).
function pointOnPath(distance) {
  if (currentPath.length < 2) return null;
  const total = pathLengths[pathLengths.length - 1];
  const d = THREE.MathUtils.clamp(distance, 0, total);
  let seg = 0;
  while (seg < currentPath.length - 2 && pathLengths[seg + 1] < d) seg++;
  const len = pathLengths[seg + 1] - pathLengths[seg];
  const t = len > 0 ? (d - pathLengths[seg]) / len : 0;
  const a = currentPath[seg];
  const b = currentPath[seg + 1];
  return new THREE.Vector3(a.x + (b.x - a.x) * t, 0, a.z + (b.z - a.z) * t);
}

// Eye-height camera behind the robot, smoothly following.
function updateFollowCamera(dt) {
  const r = robotAvatar.position;
  const heading = new THREE.Vector3(Math.sin(robotAvatar.rotation.y), 0, Math.cos(robotAvatar.rotation.y));
  let behind = null;
  if (currentPath.length > 1) {
    const travelled = navProgress * pathLengths[pathLengths.length - 1];
    if (travelled > FOLLOW_BACK * 0.5) behind = pointOnPath(travelled - FOLLOW_BACK);
  }
  if (!behind) behind = new THREE.Vector3(r.x, 0, r.z).addScaledVector(heading, -FOLLOW_BACK);
  const wantPos = new THREE.Vector3(behind.x, FOLLOW_EYE, behind.z);
  const wantTarget = new THREE.Vector3(r.x, 0.9, r.z).addScaledVector(heading, FOLLOW_LOOK_AHEAD);
  const k = 1 - Math.exp(-dt * 3.5);
  camera.position.lerp(wantPos, k);
  controls.target.lerp(wantTarget, k);
}

function resetView() {
  setCameraMode("orbit");
  tweenCamera(new THREE.Vector3(...ORBIT_VIEW.position), new THREE.Vector3(...ORBIT_VIEW.target));
}

function focusOn(pos, size) {
  const target = new THREE.Vector3(pos[0], pos[1], pos[2]);
  const extent = Math.max(size ? Math.max(size[0], size[1], size[2]) : 0.5, 0.4);
  const distance = THREE.MathUtils.clamp(extent * 3.5, 2.2, 6);
  const dir = new THREE.Vector3().subVectors(camera.position, controls.target);
  if (dir.lengthSq() < 0.01) dir.set(1, 0.8, 1);
  dir.normalize();
  dir.y = Math.max(dir.y, 0.35);
  dir.normalize();
  tweenCamera(target.clone().add(dir.multiplyScalar(distance)), target);
}

function tweenCamera(toPosition, toTarget, ms) {
  camTween = {
    fromPos: camera.position.clone(),
    fromTarget: controls.target.clone(),
    toPos: toPosition,
    toTarget: toTarget,
    start: performance.now(),
    duration: ms || 650,
  };
}

function updateCameraTween() {
  if (!camTween) return;
  const t = Math.min((performance.now() - camTween.start) / camTween.duration, 1);
  const k = t * t * (3 - 2 * t);
  camera.position.lerpVectors(camTween.fromPos, camTween.toPos, k);
  controls.target.lerpVectors(camTween.fromTarget, camTween.toTarget, k);
  if (t >= 1) camTween = null;
}

// Keep the orbit pivot inside the room so zoom always heads somewhere meaningful.
function clampTarget() {
  const margin = 1.5;
  const t = controls.target;
  t.x = THREE.MathUtils.clamp(t.x, roomBounds.x[0] - margin, roomBounds.x[1] + margin);
  t.z = THREE.MathUtils.clamp(t.z, roomBounds.z[0] - margin, roomBounds.z[1] + margin);
  t.y = THREE.MathUtils.clamp(t.y, 0, (roomBounds.ceiling || 3) + 0.5);
}

function setupViewportPicking() {
  const raycaster = new THREE.Raycaster();
  raycaster.params.Points.threshold = 0.05;
  const mouse = new THREE.Vector2();
  let down = null;

  function pick(e) {
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
  }

  function frameHit() {
    const shown = boundingFramesGroup.children.filter(function (b) { return b.userData.shown; });
    const hits = raycaster.intersectObjects(shown, true);
    for (const hit of hits) {
      let obj = hit.object;
      while (obj && !(obj.userData && obj.userData.frame) && obj.parent) obj = obj.parent;
      if (obj && obj.userData && obj.userData.frame) return { frame: obj.userData.frame, point: hit.point };
    }
    return null;
  }

  renderer.domElement.addEventListener("pointerdown", function (e) {
    down = { x: e.clientX, y: e.clientY, t: Date.now() };
  });
  renderer.domElement.addEventListener("pointerup", function (e) {
    if (!down || freeCam.active) return;
    const moved = Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y);
    if (moved > 5 || Date.now() - down.t > 350) return;
    pick(e);
    const hit = frameHit();
    if (hit) {
      showSelection(hit.frame.id);
      if (!copilotOpen) toggleCopilotDrawer();
    }
  });
  renderer.domElement.addEventListener("dblclick", function (e) {
    if (freeCam.active) return;
    pick(e);
    const hit = frameHit();
    if (hit) {
      focusOn(hit.frame.pos, hit.frame.size);
      return;
    }
    if (sceneModel) {
      const hits = raycaster.intersectObject(sceneModel, false);
      if (hits.length > 0) {
        focusOn([hits[0].point.x, hits[0].point.y, hits[0].point.z], [0.6, 0.6, 0.6]);
      }
    }
  });
}

function setupFreeCamera() {
  const canvas = renderer.domElement;
  canvas.addEventListener("click", function () {
    if (freeCam.active && document.pointerLockElement !== canvas) {
      canvas.requestPointerLock();
    }
  });

  document.addEventListener("pointerlockchange", function () {
    if (freeCam.active) {
      if (document.pointerLockElement === canvas) {
        document.getElementById("freecam-hud").textContent =
          "FREE CAM  WASD + mouse  Shift+F to exit";
      } else {
        document.getElementById("freecam-hud").textContent =
          "FREE CAM  click viewport to capture mouse  Shift+F to exit";
      }
    }
  });

  document.addEventListener("mousemove", function (event) {
    if (!freeCam.active || document.pointerLockElement !== canvas) {
      return;
    }
    freeCam.yaw -= event.movementX * 0.0022;
    freeCam.pitch = THREE.MathUtils.clamp(
      freeCam.pitch - event.movementY * 0.0022,
      -Math.PI / 2 + 0.05,
      Math.PI / 2 - 0.05,
    );
    camera.rotation.set(freeCam.pitch, freeCam.yaw, 0, "YXZ");
  });

  window.addEventListener("keydown", function (event) {
    if (event.shiftKey && event.key.toLowerCase() === "f") {
      event.preventDefault();
      if (freeCam.active) {
        exitFreeCamera();
      } else {
        enterFreeCamera();
      }
      return;
    }
    if (freeCam.active) {
      freeCam.keys.add(event.key.toLowerCase());
    }
  });

  window.addEventListener("keyup", function (event) {
    freeCam.keys.delete(event.key.toLowerCase());
  });
}

function enterFreeCamera() {
  freeCam.active = true;
  cameraMode = "free";
  controls.enabled = false;
  const euler = new THREE.Euler().setFromQuaternion(camera.quaternion, "YXZ");
  freeCam.yaw = euler.y;
  freeCam.pitch = euler.x;
  camera.rotation.set(freeCam.pitch, freeCam.yaw, 0, "YXZ");
  document.getElementById("freecam-hud").style.display = "block";
  ["orbit", "follow", "top"].forEach(function (m) {
    document.getElementById("btn-cam-" + m).classList.remove("active");
  });
  renderer.domElement.requestPointerLock();
}

function exitFreeCamera() {
  freeCam.active = false;
  freeCam.keys.clear();
  if (document.exitPointerLock) document.exitPointerLock();
  document.getElementById("freecam-hud").style.display = "none";
  // Re-anchor the orbit pivot in front of where the free camera looks.
  const forward = new THREE.Vector3();
  camera.getWorldDirection(forward);
  controls.target.copy(camera.position).add(forward.multiplyScalar(2.5));
  controls.enabled = true;
  cameraMode = "orbit";
  document.getElementById("btn-cam-orbit").classList.add("active");
}

function updateFreeCamera() {
  if (!freeCam.active) {
    return;
  }
  const now = performance.now();
  let lastTime = now;
  if (freeCam.lastTime) {
    lastTime = freeCam.lastTime;
  }
  const delta = Math.min((now - lastTime) / 1000, 0.05);
  freeCam.lastTime = now;

  const direction = new THREE.Vector3();
  camera.getWorldDirection(direction);
  direction.y = 0;
  direction.normalize();
  const right = new THREE.Vector3()
    .crossVectors(direction, camera.up)
    .normalize();
  const movement = new THREE.Vector3();

  if (freeCam.keys.has("w")) movement.add(direction);
  if (freeCam.keys.has("s")) movement.sub(direction);
  if (freeCam.keys.has("d")) movement.add(right);
  if (freeCam.keys.has("a")) movement.sub(right);
  if (freeCam.keys.has(" ")) movement.y += 1;
  if (freeCam.keys.has("control")) movement.y -= 1;

  if (movement.lengthSq() > 0) {
    movement.normalize().multiplyScalar(freeCam.speed * delta);
    camera.position.add(movement);
  }
}

// ---------------------------------------------------------------- animation loop

function animate() {
  requestAnimationFrame(animate);
  const now = performance.now();
  const dt = Math.min((now - lastFrameTime) / 1000, 0.05);
  lastFrameTime = now;

  if (isNavigating && currentPath.length > 1) {
    const total = pathLengths[pathLengths.length - 1];
    navProgress = Math.min(1, navProgress + (ROBOT_SPEED_M_S * navSpeed * dt) / Math.max(total, 1e-6));
    const travelled = navProgress * total;
    let seg = 0;
    while (seg < currentPath.length - 2 && pathLengths[seg + 1] < travelled) seg++;
    const segLength = pathLengths[seg + 1] - pathLengths[seg];
    const t = segLength > 0 ? (travelled - pathLengths[seg]) / segLength : 0;
    const p1 = currentPath[seg];
    const p2 = currentPath[seg + 1];
    robotAvatar.position.x = p1.x + (p2.x - p1.x) * t;
    robotAvatar.position.z = p1.z + (p2.z - p1.z) * t;
    robotAvatar.rotation.y = Math.atan2(p2.x - p1.x, p2.z - p1.z);
    document.getElementById("hud-nav-fill").style.width = (navProgress * 100).toFixed(1) + "%";
    checkProximityEvents(robotAvatar.position.x, robotAvatar.position.z);
    if (navProgress >= 1) onArrival();
  }

  if (cameraMode === "follow" && !camTween) updateFollowCamera(dt);
  lastRobotPos = robotAvatar.position.clone();

  updateCameraTween();
  updateFreeCamera();
  if (!freeCam.active) {
    clampTarget();
    controls.update();
  }
  if (now - lastDeclutter > 120) {
    declutterLabels();
    lastDeclutter = now;
  }
  renderer.render(scene, camera);
}

// ---------------------------------------------------------------- omnibar (natural language)

function setupOmnibar() {
  const input = document.getElementById("omnibar-input");
  const box = document.getElementById("omnibar-suggestions");

  function findAsset(text) {
    const q = text.toLowerCase().replace(/[^a-z0-9]/g, "");
    return assetsData.find(function (a) {
      const tag = a.tag.toLowerCase().replace(/[^a-z0-9]/g, "");
      const id = a.asset_id.toLowerCase().replace(/[^a-z0-9]/g, "");
      return q.includes(tag) || q.includes(id);
    });
  }

  function run(text) {
    const q = text.trim();
    if (!q) return;
    box.style.display = "none";
    input.value = "";
    addMessage("user", q);
    const lower = q.toLowerCase();
    const asset = findAsset(q);
    if (/(need|needs|require).*(attention|maintenance)|degraded|priorit|faulty|worst|critical/.test(lower) && !asset) {
      document.getElementById("asset-search").value = "";
      renderAssetList(assetsData);
      if (!sidebarOpen) toggleLeftSidebar();
      const worst = assetsData.filter(function (a) { return assetState(a) !== "healthy"; })
        .sort(function (a, b) { return a.state.health_score - b.state.health_score; });
      addMessage("ai", worst.length + " assets need attention. Worst first: " + worst.slice(0, 5).map(function (a) {
        return a.tag + " (" + Math.round(a.state.health_score) + "%)";
      }).join(", ") + ". They are listed on the left under Needs attention.");
      if (worst[0]) selectAndFocus(worst[0].asset_id);
      return;
    }
    if (asset && /(where|show|find|locate|highlight)/.test(lower)) {
      selectAndFocus(asset.asset_id);
      addMessage("ai", asset.tag + " (" + prettyClass(asset.asset_class) + ") is in " + (asset.area_name || "the boiler room") +
        " — the camera is now on it. Synthetic mapping to a detected 3D object.");
      return;
    }
    if (asset && /(route|reach|go to|navigate|walk|path)/.test(lower)) {
      loadRoute(asset.asset_id).then(function (ok) {
        if (ok) {
          showSelection(asset.asset_id);
          renderAssetList(filteredAssets());
          addMessage("ai", "Route to " + asset.tag + ": " + pathLengths[pathLengths.length - 1].toFixed(1) +
            " m, collision-free. The robot is walking there.");
          toggleNavigation();
        }
      });
      return;
    }
    // Everything else goes to the AI copilot about the named (or selected) asset.
    const target = asset ? asset.asset_id : selectedId && framesById.get(selectedId) && framesById.get(selectedId).asset_id ? selectedId : routeTargetId;
    if (!copilotOpen) toggleCopilotDrawer();
    selectedId = target;
    refreshFrameStyles();
    runCopilotDiagnosis(target, q);
  }

  input.oninput = function () {
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) {
      box.style.display = "none";
      return;
    }
    const matches = assetsData.filter(function (a) {
      return (a.tag + " " + a.asset_class + " " + (a.area_name || "")).toLowerCase().includes(q);
    }).slice(0, 5);
    box.innerHTML = "";
    matches.forEach(function (m) {
      const item = document.createElement("div");
      item.className = "omnibar-suggestion-item";
      item.innerHTML = '<span><span class="status-dot status-' + dotClass(assetState(m)) + '"></span><b>' +
        escapeHtml(m.tag) + "</b> " + escapeHtml(prettyClass(m.asset_class)) + "</span><span>" +
        Math.round(m.state ? m.state.health_score : 100) + "%</span>";
      item.onclick = function () {
        input.value = "";
        box.style.display = "none";
        selectAndFocus(m.asset_id);
      };
      box.appendChild(item);
    });
    box.style.display = matches.length ? "flex" : "none";
  };
  input.onkeydown = function (e) {
    if (e.key === "Enter") run(input.value);
  };
  document.getElementById("omnibar-submit").onclick = function () {
    run(input.value);
  };
}

// ---------------------------------------------------------------- panels, toolbar, help

function setupPanels() {
  document.getElementById("btn-toggle-left-sidebar").onclick = toggleLeftSidebar;
  document.getElementById("btn-toggle-copilot").onclick = toggleCopilotDrawer;
}

function toggleLeftSidebar() {
  sidebarOpen = !sidebarOpen;
  document.getElementById("left-sidebar-container").classList.toggle("collapsed", !sidebarOpen);
  document.getElementById("sidebar-metaverse").classList.toggle("collapsed", !sidebarOpen);
  document.getElementById("btn-toggle-left-sidebar").innerText = sidebarOpen ? "◀" : "▶";
  setTimeout(onWindowResize, 310);
}

function toggleCopilotDrawer() {
  copilotOpen = !copilotOpen;
  document.getElementById("right-copilot-container").classList.toggle("collapsed", !copilotOpen);
  document.getElementById("copilot-drawer").classList.toggle("collapsed", !copilotOpen);
  document.getElementById("btn-toggle-copilot").innerText = copilotOpen ? "▶" : "◀";
  setTimeout(onWindowResize, 310);
}

function setupToolbar() {
  document.getElementById("btn-start-nav").onclick = toggleNavigation;
  document.getElementById("btn-reset-nav").onclick = resetRobot;
  document.getElementById("speed-slider").oninput = function (e) {
    navSpeed = parseFloat(e.target.value);
    setText("speed-val", navSpeed.toFixed(1) + "x");
  };
  document.getElementById("btn-cam-orbit").onclick = resetView;
  document.getElementById("btn-cam-follow").onclick = function () { setCameraMode("follow"); };
  document.getElementById("btn-cam-top").onclick = function () { setCameraMode("top"); };
  document.querySelectorAll(".render-mode-btn[data-view]").forEach(function (b) {
    b.onclick = function () {
      closeMenus();
      if (renderMode === "heat") applyRenderMode("splat");
      if (b.dataset.view !== viewKind) loadSceneModel(b.dataset.view);
    };
  });
  document.getElementById("btn-heat").onclick = function () {
    closeMenus();
    if (viewKind === "splat") {
      renderMode = "heat"; // height colouring needs the point view
      loadSceneModel("points");
      return;
    }
    applyRenderMode(renderMode === "heat" ? "splat" : "heat");
  };

  function menu(buttonId, dropdownId) {
    const dd = document.getElementById(dropdownId);
    document.getElementById(buttonId).onclick = function (e) {
      e.stopPropagation();
      const open = !dd.classList.contains("open");
      closeMenus();
      dd.classList.toggle("open", open);
    };
  }
  menu("btn-view-menu", "view-dropdown");
  menu("btn-more", "more-dropdown");
  document.addEventListener("click", closeMenus);
  document.getElementById("btn-cam-free").onclick = enterFreeCamera;
  document.getElementById("btn-vision-analyze").onclick = analyzeCurrentView;
  document.getElementById("btn-semantic-extract").onclick = rerunExtraction;
  document.getElementById("asset-search").oninput = function () {
    renderAssetList(filteredAssets());
  };
}

function closeMenus() {
  document.querySelectorAll(".more-dropdown.open").forEach(function (d) { d.classList.remove("open"); });
}

async function rerunExtraction() {
  showToast("Re-running 3D extraction…");
  try {
    const data = await fetchJson("/api/scene/extract-assets", { method: "POST" });
    framesData = data.all_frames || framesData;
    framesById.clear();
    framesData.forEach(function (f) { framesById.set(f.id, f); });
    buildFrames(framesData);
    showToast(data.extracted_count + " objects in " + data.processing_seconds + " s");
  } catch (err) {
    showToast("Extraction failed: " + err.message);
  }
}

function setupHelp() {
  document.getElementById("btn-help").onclick = function () {
    document.getElementById("help-card").classList.add("open");
  };
  document.getElementById("btn-help-close").onclick = hideHelp;
}

function hideHelp() {
  document.getElementById("help-card").classList.remove("open");
}

function setStep(n) {
  document.querySelectorAll("#steps .step").forEach(function (li) {
    const s = Number(li.dataset.step);
    li.classList.toggle("active", s === n);
    li.classList.toggle("done", s < n);
  });
}

// ---------------------------------------------------------------- YOLO (secondary)

function renderVisionDetections(result) {
  const overlay = document.getElementById("vision-overlay");
  overlay.innerHTML = "";
  const imageWidth = result.image.width;
  const imageHeight = result.image.height;
  result.detections.forEach(function (detection) {
    const box = document.createElement("div");
    box.className = "vision-detection";
    box.style.left = (detection.box.x / imageWidth) * 100 + "%";
    box.style.top = (detection.box.y / imageHeight) * 100 + "%";
    box.style.width = (detection.box.width / imageWidth) * 100 + "%";
    box.style.height = (detection.box.height / imageHeight) * 100 + "%";

    const label = document.createElement("span");
    label.className = "vision-detection-label";
    label.innerText =
      detection.label + " " + Math.round(detection.confidence * 100) + "%";
    box.appendChild(label);
    overlay.appendChild(box);
  });
}

async function analyzeCurrentView() {
  const button = document.getElementById("btn-vision-analyze");
  const canvas = renderer.domElement;
  button.disabled = true;
  button.innerText = "Scanning...";
  try {
    const blob = await new Promise(function (resolve) {
      canvas.toBlob(resolve, "image/jpeg", 0.82);
    });
    if (!blob) {
      throw new Error("Could not capture the 3D view.");
    }
    const form = new FormData();
    form.append("file", blob, "ask-your-factory-view.jpg");
    form.append(
      "classes",
      "person, worker, safety helmet, pump, valve, pipe, tank, boiler, motor, industrial machine, pressure gauge, ladder, fire extinguisher",
    );
    const response = await fetch("/api/vision/analyze", {
      method: "POST",
      body: form,
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "YOLO-World analysis failed.");
    }
    renderVisionDetections(result);
    showToast("YOLO-World found " + result.detections.length + " object(s)");
  } catch (error) {
    console.error("YOLO-World analysis error", error);
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerText = "AI Scan";
  }
}

// ---------------------------------------------------------------- helpers

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = text == null ? "" : String(text);
}

function prettyClass(value) {
  return (value || "—").toString().replace(/_/g, " ").toLowerCase();
}

function dotClass(state) {
  if (state === "attention_required") return "attention";
  return state || "healthy";
}

function escapeHtml(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

function showToast(msg) {
  const t = document.getElementById("toast");
  t.innerText = msg;
  t.classList.add("show");
  setTimeout(function () {
    t.classList.remove("show");
  }, 2500);
}

function onWindowResize() {
  const container = document.getElementById("canvas-container");
  if (!container || container.clientHeight === 0) return;
  camera.aspect = container.clientWidth / container.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(container.clientWidth, container.clientHeight);
  if (sceneModel && sceneModel.material && sceneModel.material.uniforms && sceneModel.material.uniforms.uScale) {
    sceneModel.material.uniforms.uScale.value = container.clientHeight / (2.0 * Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)));
  }
}

// app.js is injected by bootstrap.js, possibly after the load event already fired.
if (document.readyState === "complete") {
  init3D();
} else {
  window.addEventListener("load", init3D);
}
