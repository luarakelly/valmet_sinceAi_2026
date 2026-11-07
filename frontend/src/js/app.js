// Ask Your Factory — guided boiler-room digital twin.
// Flow: 1) scene + faulty target  2) robot walks, nearby frames light up  3) AI diagnosis on arrival.
// Scene frame from the backend: Y up, floor at y = 0, room centred on x = z = 0.

let scene, camera, renderer, controls;
let sceneModel = null; // THREE.Points (scan) or THREE.Mesh (surface)
let pointCloud = null; // alias kept for the shaders/resize helpers
let viewKind = "points"; // "points" | "mesh"
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
const FOLLOW_DISTANCE = 4.5;
const FOLLOW_HEIGHT = 3.2;
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

  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance", preserveDrawingBuffer: true });
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

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

  scene.add(new THREE.AmbientLight(0xffffff, 0.9));
  const dirLight = new THREE.DirectionalLight(0xbfe9ff, 0.6);
  dirLight.position.set(5, 10, 5);
  scene.add(dirLight);

  const grid = new THREE.GridHelper(20, 40, 0x183040, 0x0b1722);
  grid.material.transparent = true;
  grid.material.opacity = 0.35;
  scene.add(grid);

  scene.add(boundingFramesGroup);
  createRobotAvatar();

  window.addEventListener("resize", onWindowResize);
  setupFreeCamera();
  setupViewportPicking();
  setupOmnibar();
  setupPanels();
  setupToolbar();
  setupHelp();

  loadSceneModel("points");
  fetchSceneData();
  animate();
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

  const ringGeo = new THREE.RingGeometry(2.3, 2.38, 48);
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
      }
    `,
    side: THREE.DoubleSide,
  });
}

function loadSceneModel(kind) {
  viewKind = kind;
  document.querySelectorAll(".render-mode-btn[data-view]").forEach(function (b) {
    b.classList.toggle("active", b.dataset.view === kind);
  });
  const loader = new THREE.PLYLoader();
  const url = kind === "mesh" ? "/api/scene/boiler-room-mesh.ply" : "/api/scene/boiler-room.ply";
  showToast(kind === "mesh" ? "Loading surface mesh…" : "Loading scan points…");
  loader.load(
    url,
    function (geometry) {
      if (sceneModel) {
        scene.remove(sceneModel);
        sceneModel.geometry.dispose();
      }
      if (kind === "mesh") {
        geometry.computeVertexNormals();
        sceneModel = new THREE.Mesh(geometry, createMeshMaterial(geometry));
      } else {
        preparePointGeometry(geometry);
        sceneModel = new THREE.Points(geometry, createPointMaterial(geometry));
      }
      pointCloud = sceneModel;
      scene.add(sceneModel);
      applyRenderMode(renderMode);
      const count = kind === "mesh"
        ? Math.round((geometry.index ? geometry.index.count : geometry.attributes.position.count) / 3)
        : geometry.attributes.position.count;
      showToast((kind === "mesh" ? "Mesh: " : "Scan: ") + count.toLocaleString() + (kind === "mesh" ? " triangles" : " points"));
    },
    undefined,
    function (err) {
      console.warn("Could not load " + url, err);
      if (kind === "mesh") {
        showToast("Mesh not available — showing scan points");
        loadSceneModel("points");
      } else {
        showToast("Scan could not be loaded — is the backend running?");
      }
    },
  );
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
    if (cameraMode === "orbit" || cameraMode === "top") {
      setCameraMode("follow");
    }
    hideHelp();
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

function renderNearby(near) {
  const box = document.getElementById("proximity-alert");
  const assets = near.filter(function (n) { return n.frame.asset_id; }).sort(function (a, b) { return a.dist - b.dist; });
  if (near.length === 0) {
    box.style.display = "none";
    return;
  }
  box.style.display = "flex";
  document.getElementById("nearby-count").innerText =
    assets.length + " assets · " + (near.length - assets.length) + " structures within " + PROXIMITY_RADIUS + " m";
  const list = document.getElementById("nearby-list");
  list.innerHTML = "";
  assets.slice(0, 6).forEach(function (n) {
    const f = n.frame;
    const li = document.createElement("li");
    li.className = "nearby-item";
    li.innerHTML =
      '<span class="status-dot status-' + dotClass(f.state) + '"></span>' +
      "<b>" + escapeHtml(f.tag) + "</b>" +
      "<span>" + escapeHtml(prettyClass(f.class)) + " · " + escapeHtml(f.state || "") + " · " + Math.round(f.health || 0) + "%</span>" +
      "<span>" + n.dist.toFixed(1) + " m</span>";
    li.onclick = function () {
      showSelection(f.id);
    };
    list.appendChild(li);
  });
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
  setText("card-asset-class", "Extracted 3D object (no builder-pack asset)");
  setText("card-asset-area", frame.point_count + " points");
  const badge = document.getElementById("card-health-badge");
  badge.innerText = "STRUCTURE";
  badge.style.color = STATE_CSS.structure;
  badge.style.borderColor = STATE_CSS.structure;
  setText(
    "card-mapping-note",
    "Size " + frame.size.map(function (s) { return s.toFixed(2); }).join(" × ") +
      " m · centre (" + frame.pos.map(function (s) { return s.toFixed(2); }).join(", ") + ")",
  );
  document.getElementById("telem-block").style.display = "none";
  document.getElementById("diag-block").style.display = "none";
}

async function runCopilotDiagnosis(assetId, question) {
  const body = { asset_id: assetId };
  if (question) {
    body.query = question;
  }
  document.getElementById("diag-block").style.display = "";
  document.getElementById("telem-block").style.display = "";
  if (question) {
    setText("copilot-answer", "Thinking…");
  }
  try {
    const [dossier, diag] = await Promise.all([
      fetchJson("/api/assets/" + encodeURIComponent(assetId)),
      fetchJson("/api/copilot/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    ]);
    if (selectedId !== assetId && !question) {
      return; // a newer selection is already being shown
    }
    updateCopilotDrawer(dossier, diag, question);
  } catch (err) {
    console.error("Copilot error", err);
    setText("copilot-answer", "");
    showToast("Copilot: " + err.message);
  }
}

function updateCopilotDrawer(dossier, diag, question) {
  const state = dossier.current_state || dossier.state || {};
  const tag = diag.tag || dossier.tag || dossier.asset_id;
  const health = diag.health_score != null ? diag.health_score : state.health_score;
  const condition = diag.condition_state || state.condition_state || "unknown";

  setText("card-asset-tag", tag + " · " + (diag.asset_id || dossier.asset_id));
  setText("card-asset-class", prettyClass(diag.asset_class || dossier.asset_class));
  setText("card-asset-area", dossier.area_name || "Boiler room");

  const frame = framesById.get(dossier.asset_id);
  if (frame && frame.asset_id) {
    setText(
      "card-mapping-note",
      "Synthetic mapping → 3D object " + frame.scene_id + " (" + prettyClass(frame.label) + "), confidence " +
        (frame.mapping_confidence != null ? frame.mapping_confidence : "—") + (frame.id === routeTargetId ? " · inspection target" : ""),
    );
  } else {
    setText("card-mapping-note", "Not placed in the 3D scene.");
  }

  const badge = document.getElementById("card-health-badge");
  badge.innerText = Math.round(health || 0) + "% " + condition.replace(/_/g, " ").toUpperCase();
  const css = STATE_CSS[condition] || STATE_CSS.healthy;
  badge.style.color = css;
  badge.style.borderColor = css;

  const confidence = diag.confidence_score != null ? diag.confidence_score : diag.model_confidence;
  setText("diag-conf", "Confidence " + (confidence != null ? Number(confidence).toFixed(2) : "—"));

  const findingBox = document.getElementById("finding-box");
  const icon = condition === "healthy" ? "✅" : condition === "watch" ? "🔍" : "⚠️";
  findingBox.style.borderColor = css;
  findingBox.style.background = css + "1f";
  setText("finding-icon", icon);
  setText("primary-finding-text", diag.diagnosis_summary || diag.diagnosis || (diag.issue_code || "") + " signature");

  fillList("root-cause-list", (diag.multivariate_evidence || []).slice(0, 5), "No telemetry drift, alarms or similar cases found.", true);
  fillList("action-list", diag.recommended_actions || [], "Continue routine monitoring.", false);

  const citBox = document.getElementById("evidence-citations-box");
  citBox.innerHTML = "";
  (diag.citations || []).forEach(function (c) {
    const chip = document.createElement("button");
    chip.className = "evidence-chip";
    chip.innerText = c.source_id;
    chip.title = c.description || "";
    chip.onclick = function () {
      showToast(c.source_id + ": " + (c.description || ""));
    };
    citBox.appendChild(chip);
  });

  if (diag.safety_guardrails && diag.safety_guardrails.length > 0) {
    setText("safety-text", diag.safety_guardrails[0]);
  }
  setText("copilot-model-badge", diag.grounded_mode || "evidence engine");
  setText("copilot-answer", question ? diag.answer || diag.diagnosis || "" : diag.answer || "");
  drawTelemetryTrend(dossier.recent_telemetry || []);
}

function fillList(id, items, emptyText, bullets) {
  const el = document.getElementById(id);
  el.innerHTML = "";
  const rows = items.length ? items : [emptyText];
  rows.forEach(function (item) {
    const li = document.createElement("li");
    if (bullets) {
      li.className = "root-cause-item";
      li.innerHTML = '<span class="root-cause-bullet">•</span>';
      const span = document.createElement("span");
      span.textContent = item;
      li.appendChild(span);
    } else {
      li.textContent = item;
    }
    el.appendChild(li);
  });
}

function drawTelemetryTrend(records) {
  const canvas = document.getElementById("telem-canvas");
  const ctx = canvas.getContext("2d");
  canvas.width = canvas.clientWidth * window.devicePixelRatio;
  canvas.height = canvas.clientHeight * window.devicePixelRatio;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const channels = [
    ["process_flow_pct", "flow %"],
    ["vibration_mm_s", "vibration mm/s"],
    ["bearing_temp_c", "bearing °C"],
    ["process_pressure_bar", "pressure bar"],
    ["position_actual_pct", "position %"],
  ];
  let key = null;
  let label = "Recent telemetry";
  for (const [k, l] of channels) {
    if (records.some(function (r) { return r[k] !== undefined && r[k] !== null; })) {
      key = k;
      label = "Recent " + l;
      break;
    }
  }
  setText("telem-label", label);
  if (!key || records.length < 2) {
    return;
  }
  const pts = records.map(function (r) { return r[key]; }).filter(function (v) { return v !== null && v !== undefined; });
  const min = Math.min(...pts);
  const max = Math.max(...pts) + 1e-6;
  ctx.strokeStyle = "#00d2ff";
  ctx.lineWidth = 2 * window.devicePixelRatio;
  ctx.beginPath();
  pts.forEach(function (val, idx) {
    const x = (idx / (pts.length - 1)) * canvas.width;
    const y = canvas.height - ((val - min) / (max - min)) * (canvas.height * 0.72) - canvas.height * 0.14;
    if (idx === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
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

  function group(title, items, open) {
    if (items.length === 0) return;
    const details = document.createElement("details");
    details.className = "asset-group";
    details.open = open;
    const summary = document.createElement("summary");
    summary.innerText = title + " (" + items.length + ")";
    details.appendChild(summary);
    items.forEach(function (a) {
      details.appendChild(assetCard(a));
    });
    list.appendChild(details);
  }
  group("Needs attention", attention, true);
  group("Healthy", healthy, false);
}

function assetCard(a) {
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
    '<span class="asset-class">' + escapeHtml(prettyClass(a.asset_class)) + (isTarget ? " · target" : "") + "</span>" +
    '<span class="asset-health" style="color:' + (STATE_CSS[state] || STATE_CSS.healthy) + '">' + Math.round(health) + "%</span>" +
    "</div>" +
    '<div class="asset-actions">' +
    '<button class="action-pill" data-act="focus">📍 Show in 3D</button>' +
    '<button class="action-pill" data-act="route">🚶 Route here</button>' +
    "</div>";
  card.querySelector(".asset-card-main").onclick = function () {
    selectAndFocus(a.asset_id);
  };
  card.querySelector('[data-act="focus"]').onclick = function (e) {
    e.stopPropagation();
    selectAndFocus(a.asset_id);
  };
  card.querySelector('[data-act="route"]').onclick = async function (e) {
    e.stopPropagation();
    if (await loadRoute(a.asset_id)) {
      showToast("New inspection target: " + a.tag + " — press Start inspection");
      renderAssetList(filteredAssets());
      showSelection(a.asset_id);
    }
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
  } else if (mode === "follow") {
    const p = robotAvatar.position;
    const dir = new THREE.Vector3().subVectors(camera.position, controls.target).setY(0);
    if (dir.lengthSq() < 0.01) dir.set(1, 0, 1);
    dir.normalize().multiplyScalar(FOLLOW_DISTANCE);
    tweenCamera(new THREE.Vector3(p.x + dir.x, FOLLOW_HEIGHT, p.z + dir.z), new THREE.Vector3(p.x, 0.6, p.z));
  }
  lastRobotPos = robotAvatar.position.clone();
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

  // Follow mode: move camera and pivot with the robot, keep the user's zoom/rotation.
  if (cameraMode === "follow" && lastRobotPos && !camTween) {
    const delta = new THREE.Vector3().subVectors(robotAvatar.position, lastRobotPos);
    camera.position.add(delta);
    controls.target.add(delta);
  }
  lastRobotPos = robotAvatar.position.clone();

  updateCameraTween();
  updateFreeCamera();
  if (!freeCam.active) {
    clampTarget();
    controls.update();
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
    const lower = q.toLowerCase();
    const asset = findAsset(q);
    if (/(need|needs|require).*(attention|maintenance)|degraded|priorit|faulty|worst|critical/.test(lower) && !asset) {
      document.getElementById("asset-search").value = "";
      renderAssetList(assetsData);
      if (!sidebarOpen) toggleLeftSidebar();
      const worst = assetsData.filter(function (a) { return assetState(a) !== "healthy"; })
        .sort(function (a, b) { return a.state.health_score - b.state.health_score; });
      showToast(worst.length + " assets need attention — worst: " + worst.slice(0, 3).map(function (a) { return a.tag; }).join(", "));
      if (worst[0]) selectAndFocus(worst[0].asset_id);
      return;
    }
    if (asset && /(where|show|find|locate|highlight)/.test(lower)) {
      selectAndFocus(asset.asset_id);
      return;
    }
    if (asset && /(route|reach|go to|navigate|walk|path)/.test(lower)) {
      loadRoute(asset.asset_id).then(function (ok) {
        if (ok) {
          showSelection(asset.asset_id);
          showToast("Route to " + asset.tag + " ready — press Start inspection");
        }
      });
      return;
    }
    // Everything else goes to the AI copilot about the named (or selected) asset.
    const target = asset ? asset.asset_id : selectedId && framesById.get(selectedId) && framesById.get(selectedId).asset_id ? selectedId : routeTargetId;
    if (!copilotOpen) toggleCopilotDrawer();
    selectedId = target;
    refreshFrameStyles();
    document.getElementById("copilot-question").value = q;
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
  document.getElementById("btn-cam-orbit").onclick = function () { setCameraMode("orbit"); };
  document.getElementById("btn-cam-follow").onclick = function () { setCameraMode("follow"); };
  document.getElementById("btn-cam-top").onclick = function () { setCameraMode("top"); };
  document.getElementById("btn-cam-reset").onclick = resetView;
  document.querySelectorAll(".render-mode-btn[data-view]").forEach(function (b) {
    b.onclick = function () {
      if (b.dataset.view !== viewKind) loadSceneModel(b.dataset.view);
    };
  });
  document.getElementById("btn-heat").onclick = function () {
    applyRenderMode(renderMode === "heat" ? "splat" : "heat");
  };
  document.getElementById("btn-all-frames").onclick = function (e) {
    showAllFrames = !showAllFrames;
    e.currentTarget.classList.toggle("active", showAllFrames);
    refreshFrameStyles();
    showToast(showAllFrames ? "Showing all " + framesData.length + " extracted frames" : "Showing target, selection and nearby frames");
  };

  const more = document.getElementById("more-dropdown");
  document.getElementById("btn-more").onclick = function (e) {
    e.stopPropagation();
    more.classList.toggle("open");
  };
  document.addEventListener("click", function () {
    more.classList.remove("open");
  });
  document.getElementById("btn-cam-free").onclick = enterFreeCamera;
  document.getElementById("btn-vision-analyze").onclick = analyzeCurrentView;
  document.getElementById("btn-semantic-extract").onclick = rerunExtraction;

  document.getElementById("btn-ask-copilot").onclick = askCopilot;
  document.getElementById("copilot-question").onkeydown = function (e) {
    if (e.key === "Enter") askCopilot();
  };
  document.getElementById("btn-submit-wo").onclick = draftWorkOrder;
  document.getElementById("asset-search").oninput = function () {
    renderAssetList(filteredAssets());
  };
}

function askCopilot() {
  const question = document.getElementById("copilot-question").value.trim();
  if (!question) return;
  const frame = framesById.get(selectedId);
  const target = frame && !frame.asset_id ? routeTargetId : selectedId || routeTargetId;
  runCopilotDiagnosis(target, question);
}

async function draftWorkOrder() {
  const frame = framesById.get(selectedId);
  const target = frame && !frame.asset_id ? routeTargetId : selectedId || routeTargetId;
  try {
    const wo = await fetchJson("/api/work-orders/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_id: target }),
    });
    showToast("Draft " + (wo.work_order_id || "") + " created for review (not submitted)");
  } catch (err) {
    showToast("Work order: " + err.message);
  }
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
  let seen = false;
  try {
    seen = localStorage.getItem("ayf-help-seen") === "1";
  } catch (e) {
    seen = false;
  }
  if (!seen) document.getElementById("help-card").classList.add("open");
}

function hideHelp() {
  document.getElementById("help-card").classList.remove("open");
  try {
    localStorage.setItem("ayf-help-seen", "1");
  } catch (e) {
    /* storage unavailable */
  }
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
  }, 3500);
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

window.onload = init3D;
