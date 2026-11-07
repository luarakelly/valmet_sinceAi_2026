let scene, camera, renderer, controls;
let pointCloud = null;
let boundingFramesGroup = new THREE.Group();
let pathLineMesh = null;
let robotAvatar = null;
let assetsData = [];
let currentPath = [];
let navProgress = 0;
let pathLengths = [0];
let lastFrameTime = performance.now();
let isNavigating = false;
let navSpeed = 1.5;
let cameraMode = "orbit";
let currentSelectedAsset = "ASSET-017";
let pointSize = 0.070;
let renderMode = "splat";
let sidebarOpen = true;
let copilotOpen = true;
let proximityRadius = 0; // metres to a box edge; the server owns the value (scene summary)
let routeBriefings = [];
let nextBriefingIndex = 0;
let obstacleOverlay = null;

// Canonical scene frame from the backend: Y up, floor at y = 0, room centred on x = z = 0.
const ROBOT_GROUND_OFFSET = 0.15;
const OBSTACLE_OVERLAY_Y = 0.03;
const CELL_WALKABLE = 0;
const CELL_BLOCKED = 1;
const OBSTACLE_BLOCKED_RGBA = "rgba(239, 68, 68, 0.5)";
const OBSTACLE_TIGHT_RGBA = "rgba(245, 158, 11, 0.22)";
const MAX_NEARBY_ASSETS = 4;
const MAX_NEARBY_STRUCTURES = 2;
const ROBOT_SPEED_M_S = 0.8;
const ORBIT_VIEW = { position: [-5.5, 3.2, 4.5], target: [0, 0.8, 0] };
const TOP_VIEW = { position: [0, 9, 0.01], target: [0, 0, 0] };

const freeCam = {
  active: false,
  keys: new Set(),
  yaw: 0,
  pitch: 0,
  speed: 2.8,
  lastTime: 0,
};

function init3D() {
  const container = document.getElementById("canvas-container");
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x06090e);
  scene.fog = new THREE.FogExp2(0x06090e, 0.038);

  camera = new THREE.PerspectiveCamera(
    60,
    container.clientWidth / container.clientHeight,
    0.05,
    120,
  );
  camera.position.set(...ORBIT_VIEW.position);

  renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.target.set(...ORBIT_VIEW.target);

  const ambLight = new THREE.AmbientLight(0xffffff, 0.9);
  scene.add(ambLight);
  const dirLight = new THREE.DirectionalLight(0x00d2ff, 0.65);
  dirLight.position.set(5, 10, 5);
  scene.add(dirLight);

  const grid = new THREE.GridHelper(16, 16, 0x183040, 0x0b1722);
  grid.position.y = 0;
  grid.material.transparent = true;
  grid.material.opacity = 0.42;
  scene.add(grid);

  boundingFramesGroup.visible = true;
  scene.add(boundingFramesGroup);

  createRobotAvatar();
  loadBoilerRoomPLY();
  fetchAssetsAndFrames();

  window.addEventListener("resize", onWindowResize);
  setupFreeCamera();
  setupOmnibar();
  setupPanelCollapses();
  setupViewportRaycaster();
  // Collapse left and right panels by default for clean open viewport
  toggleLeftSidebar();
  toggleCopilotDrawer();

  animate();
}

function setupViewportRaycaster() {
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  let mouseDownTime = 0;
  let mouseDownPos = { x: 0, y: 0 };

  renderer.domElement.addEventListener("mousedown", (e) => {
    mouseDownTime = Date.now();
    mouseDownPos = { x: e.clientX, y: e.clientY };
  });

  renderer.domElement.addEventListener("mouseup", (e) => {
    const dt = Date.now() - mouseDownTime;
    const dx = Math.abs(e.clientX - mouseDownPos.x);
    const dy = Math.abs(e.clientY - mouseDownPos.y);
    if (dt > 300 || dx > 4 || dy > 4) return;

    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(
      boundingFramesGroup.children,
      true,
    );
    if (intersects.length > 0) {
      let topObj = intersects[0].object;
      while (
        topObj &&
        (!topObj.userData || !topObj.userData.id) &&
        topObj.parent
      ) {
        topObj = topObj.parent;
      }
      if (topObj && topObj.userData && topObj.userData.id) {
        const targetId = topObj.userData.id;
        selectAsset(targetId);
        showToast("Selected " + (topObj.userData.tag || targetId) + " in 3D");
      }
    }
  });
}

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

/**
 * Prepares the point cloud geometry with guaranteed bounding volumes and vertex colors.
 */
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

function cleanAndPreparePointGeometry(rawGeometry) {
  return preparePointGeometry(rawGeometry);
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

function applyRenderMode(mode) {
  renderMode = mode;
  let modeIndex = 0;
  if (mode === "studio") {
    modeIndex = 1;
  } else if (mode === "heat") {
    modeIndex = 2;
  }

  document
    .querySelectorAll(".render-mode-btn[data-render-mode]")
    .forEach(function (button) {
      let active = false;
      if (button.dataset.renderMode === mode) {
        active = true;
      }
      button.classList.toggle("active", active);
      if (active) {
        button.setAttribute("aria-pressed", "true");
      } else {
        button.setAttribute("aria-pressed", "false");
      }
    });

  if (pointCloud && pointCloud.material && pointCloud.material.uniforms) {
    if (pointCloud.material.uniforms.uMode) {
      pointCloud.material.uniforms.uMode.value = modeIndex;
    }
    if (pointCloud.material.uniforms.uPointSize) {
      if (mode === "splat") {
        pointCloud.material.uniforms.uPointSize.value = 0.088;
      } else {
        pointCloud.material.uniforms.uPointSize.value = 0.065;
      }
    }
    if (pointCloud.material.uniforms.uOpacity) {
      if (mode === "heat") {
        pointCloud.material.uniforms.uOpacity.value = 0.92;
      } else {
        pointCloud.material.uniforms.uOpacity.value = 0.98;
      }
    }
  }

  showToast("Render mode: " + mode.charAt(0).toUpperCase() + mode.slice(1));
}

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

// Surface mesh reconstructed from the Gaussian splat (see backend splat_mesh.py).
// Modes: 0 = scan colours, 1 = studio (height-tinted clay), 2 = heat (height ramp).
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

function loadBoilerRoomPLY() {
  showToast("Loading boiler room mesh...");
  const loader = new THREE.PLYLoader();
  loader.load(
    "/api/scene/boiler-room-mesh.ply",
    function (geometry) {
      if (pointCloud) {
        scene.remove(pointCloud);
      }
      geometry.computeVertexNormals();
      pointCloud = new THREE.Mesh(geometry, createMeshMaterial(geometry));
      scene.add(pointCloud);
      applyRenderMode(renderMode);
      const faces = geometry.index ? geometry.index.count / 3 : geometry.attributes.position.count / 3;
      const pointCountEl = document.getElementById("engine-point-count");
      if (pointCountEl) {
        pointCountEl.innerText = "Boiler room mesh · " + Math.round(faces / 1000) + "k triangles";
      }
    },
    undefined,
    function (err) {
      console.warn("Mesh unavailable, falling back to point cloud", err);
      loadBoilerRoomPointCloud();
    },
  );
}

function loadBoilerRoomPointCloud() {
  const loader = new THREE.PLYLoader();

  loader.load(
    "/api/scene/boiler-room.ply",
    function (rawGeometry) {
      if (pointCloud) {
        scene.remove(pointCloud);
      }

      const geometry = cleanAndPreparePointGeometry(rawGeometry, 0.12, 4);
      const material = createPointMaterial(geometry);

      pointCloud = new THREE.Points(geometry, material);
      scene.add(pointCloud);

      applyRenderMode(renderMode);

      const finalCount = geometry.attributes.position.count;
      const pointCountEl = document.getElementById("engine-point-count");
      if (pointCountEl) {
        pointCountEl.innerText = finalCount.toLocaleString() + " splats verified";
      }
      showToast("Boiler Room loaded (" + finalCount.toLocaleString() + " splats)");
    },
    undefined,
    function (err) {
      console.warn("Falling back to procedural cloud", err);
      generateProceduralPointcloud();
    }
  );
}

function generateProceduralPointcloud() {
  const pCount = 80000;
  const positions = new Float32Array(pCount * 3);
  const colors = new Float32Array(pCount * 3);
  for (let i = 0; i < pCount; i++) {
    const x = (Math.random() - 0.5) * 8.0;
    const y = (Math.random() - 0.5) * 3.0;
    const z = (Math.random() - 0.5) * 8.0 - 1.5;
    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;

    colors[i * 3] = 0.5 + Math.sin(x) * 0.2;
    colors[i * 3 + 1] = 0.5 + Math.cos(z) * 0.2;
    colors[i * 3 + 2] = 0.6;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geo.computeBoundingBox();
  const mat = createPointMaterial(geo);
  pointCloud = new THREE.Points(geo, mat);
  scene.add(pointCloud);
  applyRenderMode(renderMode);
}

async function fetchAssetsAndFrames() {
  try {
    const [assetsRes, framesRes, summaryRes] = await Promise.all([
      fetch("/api/assets"),
      fetch("/api/scene/frames"),
      fetch("/api/scene/summary"),
    ]);
    assetsData = await assetsRes.json();
    const frames = await framesRes.json();
    const summary = await summaryRes.json();
    currentSelectedAsset = summary.target_asset_id;
    proximityRadius = summary.proximity_radius_m;
    robotAvatar.position.set(summary.entry.x, ROBOT_GROUND_OFFSET, summary.entry.z);

    renderAssetList(assetsData);
    build3DBoundingBoxes(frames);
    const assetCountEl = document.getElementById("asset-count");
    if (assetCountEl) {
      assetCountEl.innerText =
        frames.length + " Objects · " + summary.mapped_asset_count + " Assets";
    }
    loadNavigationPath(currentSelectedAsset);
    loadObstacleOverlay();
  } catch (e) {
    console.error("Error fetching assets", e);
  }
}

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
  });
  const sprite = new THREE.Sprite(spriteMat);
  sprite.scale.set(0.9, 0.28, 1);
  return sprite;
}

function build3DBoundingBoxes(frames) {
  while (boundingFramesGroup.children.length > 0) {
    boundingFramesGroup.remove(boundingFramesGroup.children[0]);
  }

  frames.forEach((frame) => {
    const [w, h, d] = frame.size;
    const [x, y, z] = frame.pos;

    let colorHex = 0x10b981;
    let colorCss = "#10b981";
    if (frame.state === "watch") {
      colorHex = 0xf59e0b;
      colorCss = "#f59e0b";
    } else if (frame.state === "degraded") {
      colorHex = 0xf97316;
      colorCss = "#f97316";
    } else if (frame.state === "attention_required") {
      colorHex = 0xef4444;
      colorCss = "#ef4444";
    } else if (!frame.asset_id) {
      colorHex = 0x00d2ff;
      colorCss = "#00d2ff";
    }

    const isSelected = frame.id === currentSelectedAsset;
    let boxLineWidth = 1;
    let boxLineOpacity = 0.08;
    let boxFillOpacity = 0.0;
    let boxLabelOpacity = 0.0;
    if (isSelected) {
      boxLineWidth = 2;
      boxLineOpacity = 0.95;
      boxFillOpacity = 0.15;
      boxLabelOpacity = 1.0;
    }

    const boxGeo = new THREE.BoxGeometry(w, h, d);
    const edges = new THREE.EdgesGeometry(boxGeo);
    const lineMat = new THREE.LineBasicMaterial({
      color: colorHex,
      linewidth: boxLineWidth,
      transparent: true,
      opacity: boxLineOpacity,
    });
    const boxMesh = new THREE.LineSegments(edges, lineMat);
    boxMesh.position.set(x, y, z);

    const fillMat = new THREE.MeshBasicMaterial({
      color: colorHex,
      transparent: true,
      opacity: boxFillOpacity,
      depthWrite: false,
    });
    const fillMesh = new THREE.Mesh(boxGeo, fillMat);
    boxMesh.add(fillMesh);

    const labelSprite = createFloatingLabelSprite(
      frame.tag || frame.id,
      frame.state || frame.label.replace(/_/g, " "),
      colorCss,
    );
    labelSprite.position.set(0, h / 2 + 0.35, 0);
    labelSprite.material.opacity = boxLabelOpacity;
    boxMesh.add(labelSprite);

    boxMesh.userData = {
      id: frame.id,
      tag: frame.tag,
      state: frame.state,
      health: frame.health,
      label: frame.label,
      assetClass: frame.class,
      assetId: frame.asset_id,
      pos: [x, y, z],
      size: [w, h, d],
      lineMat: lineMat,
      fillMat: fillMat,
      labelSprite: labelSprite,
      baseColor: colorHex,
      isMapped: !!frame.asset_id,
      context: frame.context,
    };

    boundingFramesGroup.add(boxMesh);
  });
}

async function loadNavigationPath(targetId) {
  try {
    const res = await fetch(
      "/api/navigation/path?target_id=" + encodeURIComponent(targetId),
    );
    const data = await res.json();
    currentPath = data.waypoints;
    pathLengths = cumulativeLengths(currentPath);

    document.getElementById("hud-target-name").innerText =
      "Target: " + data.target_tag;
    document.getElementById("hud-dist").innerText = data.total_distance_m + "m";

    renderPathRibbon(currentPath);
    loadBriefings(targetId);
  } catch (err) {
    console.error("Path error", err);
  }
}

async function loadBriefings(targetId) {
  try {
    const res = await fetch(
      "/api/navigation/briefings?target_id=" + encodeURIComponent(targetId),
    );
    routeBriefings = await res.json();
    resetRouteLog();
  } catch (err) {
    console.error("Briefings error", err);
  }
}

function resetRouteLog() {
  nextBriefingIndex = 0;
  document.getElementById("route-log").replaceChildren();
  updateRouteLogCount();
}

function updateRouteLogCount() {
  document.getElementById("route-log-count").innerText =
    nextBriefingIndex + " / " + routeBriefings.length;
}

// Event-based: a briefing plays when the robot reaches the route progress of its closest approach.
function playDueBriefings() {
  while (
    nextBriefingIndex < routeBriefings.length &&
    routeBriefings[nextBriefingIndex].progress <= navProgress
  ) {
    appendRouteLogEntry(routeBriefings[nextBriefingIndex]);
    nextBriefingIndex++;
  }
  updateRouteLogCount();
}

function appendRouteLogEntry(briefing) {
  const item = document.createElement("li");
  item.className = "route-log-item route-log-" + briefing.state;

  const tag = document.createElement("b");
  tag.textContent = briefing.tag;
  const meta = document.createElement("span");
  meta.className = "route-log-meta";
  meta.textContent = briefing.health + "% · " + briefing.distance_m + " m";
  item.append(tag, meta);

  if (briefing.is_generated) {
    const badge = document.createElement("span");
    badge.className = "route-log-ai";
    badge.textContent = "AI";
    item.append(badge);
  }

  const text = document.createElement("p");
  text.textContent = briefing.text;
  item.append(text);

  item.onclick = function () {
    openCopilotForAsset(briefing.asset_id);
  };
  document.getElementById("route-log").prepend(item);
}

async function loadObstacleOverlay() {
  try {
    const res = await fetch("/api/navigation/grid");
    const grid = await res.json();
    const canvas = document.createElement("canvas");
    canvas.width = grid.cols;
    canvas.height = grid.rows;
    const ctx = canvas.getContext("2d");
    grid.cells.forEach(function (cellClass, index) {
      if (cellClass === CELL_WALKABLE) {
        return;
      }
      ctx.fillStyle = OBSTACLE_TIGHT_RGBA;
      if (cellClass === CELL_BLOCKED) {
        ctx.fillStyle = OBSTACLE_BLOCKED_RGBA;
      }
      ctx.fillRect(index % grid.cols, Math.floor(index / grid.cols), 1, 1);
    });

    const texture = new THREE.CanvasTexture(canvas);
    texture.magFilter = THREE.NearestFilter;
    texture.minFilter = THREE.NearestFilter;
    const width = grid.cols * grid.cell_m;
    const depth = grid.rows * grid.cell_m;
    obstacleOverlay = new THREE.Mesh(
      new THREE.PlaneGeometry(width, depth),
      new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false }),
    );
    obstacleOverlay.rotation.x = -Math.PI / 2; // canvas row j then lies at z = z_min + j * cell
    obstacleOverlay.position.set(grid.x_min + width / 2, OBSTACLE_OVERLAY_Y, grid.z_min + depth / 2);
    obstacleOverlay.visible = false;
    scene.add(obstacleOverlay);
  } catch (err) {
    console.error("Obstacle grid error", err);
  }
}

function setObstacleOverlay(isVisible) {
  if (obstacleOverlay) {
    obstacleOverlay.visible = isVisible;
  }
  const button = document.getElementById("btn-obstacles");
  button.classList.toggle("active", isVisible);
  button.setAttribute("aria-pressed", String(isVisible));
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

function renderAssetList(assets) {
  const listEl = document.getElementById("asset-list-container");
  listEl.innerHTML = "";

  assets.forEach(function (a) {
    const card = document.createElement("div");
    card.id = "asset-card-" + a.asset_id;

    let cardClass = "asset-card";
    if (a.asset_id === currentSelectedAsset) {
      cardClass = "asset-card active";
    }
    card.className = cardClass;
    if (a.asset_id === currentSelectedAsset) {
      card.style.background = "rgba(0, 210, 255, 0.16)";
      card.style.border = "1px solid #00d2ff";
    } else {
      card.style.background = "#0c1524";
      card.style.border = "1px solid rgba(255,255,255,0.12)";
    }
    card.style.borderRadius = "6px";
    card.style.marginBottom = "4px";

    let stateClass = "healthy";
    let health = 100;
    if (a.state) {
      stateClass = a.state.condition_state;
      health = a.state.health_score;
    }

    let dotClass = stateClass;
    if (stateClass === "attention_required") {
      dotClass = "attention";
    }

    let healthColor = "#10b981";
    if (health < 50) {
      healthColor = "#ef4444";
    } else if (health < 75) {
      healthColor = "#f59e0b";
    }

    let assetClassLabel = "EQUIPMENT";
    if (a.asset_class) {
      assetClassLabel = a.asset_class.replace(/_/g, " ");
    }

    const mainRow = document.createElement("div");
    mainRow.className = "asset-card-main";
    mainRow.style.cssText =
      "display:flex;align-items:center;justify-content:space-between;padding:10px 12px;cursor:pointer;user-select:none;min-height:38px;";
    mainRow.innerHTML =
      '<div style="display:flex;align-items:center;gap:8px;min-width:0;">' +
      '<span class="status-dot status-' +
      dotClass +
      '" style="width:9px;height:9px;border-radius:50%;flex-shrink:0;"></span>' +
      '<span style="font-weight:700;color:#ffffff;font-size:13px;letter-spacing:0.3px;">' +
      a.tag +
      "</span>" +
      '<span style="font-size:11px;color:#94a3b8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' +
      assetClassLabel +
      "</span>" +
      "</div>" +
      '<span style="font-family:var(--font-mono);font-weight:700;font-size:12px;color:' +
      healthColor +
      ';flex-shrink:0;margin-left:8px;">' +
      Math.round(health) +
      "%</span>";

    mainRow.onclick = function () {
      selectAsset(a.asset_id);
    };

    const actionsRow = document.createElement("div");
    actionsRow.className = "asset-actions";

    const focusBtn = document.createElement("button");
    focusBtn.className = "action-pill";
    focusBtn.innerHTML = "📍 Focus 3D";
    focusBtn.onclick = function (e) {
      e.stopPropagation();
      focusAssetIn3D(a.asset_id);
    };

    const navBtn = document.createElement("button");
    navBtn.className = "action-pill";
    navBtn.innerHTML = "🚀 Navigate";
    navBtn.onclick = function (e) {
      e.stopPropagation();
      startNavigationTo(a.asset_id);
    };

    const copilotBtn = document.createElement("button");
    copilotBtn.className = "action-pill";
    copilotBtn.innerHTML = "📋 Dossier";
    copilotBtn.onclick = function (e) {
      e.stopPropagation();
      openCopilotForAsset(a.asset_id);
    };

    actionsRow.appendChild(focusBtn);
    actionsRow.appendChild(navBtn);
    actionsRow.appendChild(copilotBtn);

    card.appendChild(mainRow);
    card.appendChild(actionsRow);
    listEl.appendChild(card);
  });
}

function focusAssetIn3D(assetId) {
  let targetPos = null;
  boundingFramesGroup.children.forEach(function (child) {
    if (child.userData && child.userData.id === assetId && child.userData.pos) {
      targetPos = child.userData.pos;
    }
  });

  if (targetPos) {
    if (cameraMode !== "orbit") {
      setCameraMode("orbit", document.getElementById("btn-cam-orbit"));
    }
    const [tx, ty, tz] = targetPos;
    controls.target.set(tx, ty + 0.4, tz);
    camera.position.set(tx + 2.2, ty + 1.6, tz + 2.5);
    controls.update();
    showToast("Camera routed to 3D equipment " + assetId);
  }
}

async function selectAsset(assetId) {
  currentSelectedAsset = assetId;

  document.querySelectorAll(".asset-card").forEach(function (el) {
    el.classList.remove("active");
  });
  const currentCard = document.getElementById("asset-card-" + assetId);
  if (currentCard) {
    currentCard.classList.add("active");
  }

  boundingFramesGroup.children.forEach(function (c) {
    if (c.userData && c.userData.lineMat) {
      const isSel = c.userData.id === assetId;
      if (isSel) {
        c.userData.lineMat.opacity = 1.0;
        if (c.userData.fillMat) {
          c.userData.fillMat.opacity = 0.2;
        }
        if (c.userData.labelSprite) {
          c.userData.labelSprite.material.opacity = 1.0;
        }
      } else {
        c.userData.lineMat.opacity = 0.08;
        if (c.userData.fillMat) {
          c.userData.fillMat.opacity = 0.0;
        }
        if (c.userData.labelSprite) {
          c.userData.labelSprite.material.opacity = 0.0;
        }
      }
    }
  });

  await loadNavigationPath(assetId);
  runCopilotDiagnosis(assetId);
}

function startNavigationTo(assetId) {
  selectAsset(assetId);
  focusAssetIn3D(assetId);
  if (!isNavigating) {
    toggleDroneNavigation();
  }
}

function openCopilotForAsset(assetId) {
  selectAsset(assetId);
  if (!copilotOpen) {
    toggleCopilotDrawer();
  }
}

async function runCopilotDiagnosis(assetId, question) {
  const body = { asset_id: assetId };
  if (question) {
    body.query = question;
  }
  try {
    const [assetRes, diagRes] = await Promise.all([
      fetch("/api/assets/" + encodeURIComponent(assetId)),
      fetch("/api/copilot/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    ]);
    const assetDossier = await assetRes.json();
    const diag = await diagRes.json();

    updateCopilotDrawer(assetDossier, diag);
  } catch (err) {
    console.error("Copilot error", err);
  }
}

function updateCopilotDrawer(dossier, diag) {
  document.getElementById("card-asset-tag").innerText =
    "ASSET: " + diag.tag + " (" + diag.asset_id + ")";
  document.getElementById("card-asset-class").innerText = diag.asset_class;

  let areaText = "Boiler Room";
  if (dossier.asset && dossier.asset.area_name) {
    areaText = dossier.asset.area_name;
  }
  document.getElementById("card-asset-area").innerText = areaText;

  const hBadge = document.getElementById("card-health-badge");
  hBadge.innerText =
    diag.health_score + "% " + diag.condition_state.toUpperCase();
  if (diag.health_score < 50) {
    hBadge.style.color = "var(--red)";
    hBadge.style.borderColor = "var(--red)";
  } else if (diag.health_score < 75) {
    hBadge.style.color = "var(--orange)";
    hBadge.style.borderColor = "var(--orange)";
  } else {
    hBadge.style.color = "var(--green)";
    hBadge.style.borderColor = "var(--green)";
  }

  document.getElementById("diag-conf").innerText =
    "Conf: " + diag.confidence_score;

  let findingIcon = "⚠️";
  let findingColor = "#fca5a5";
  let findingBg = "rgba(239, 68, 68, 0.12)";
  let findingBorder = "rgba(239, 68, 68, 0.35)";

  if (diag.condition_state === "healthy") {
    findingIcon = "✅";
    findingColor = "#6ee7b7";
    findingBg = "rgba(16, 185, 129, 0.12)";
    findingBorder = "rgba(16, 185, 129, 0.35)";
  } else if (diag.condition_state === "watch") {
    findingIcon = "🔍";
    findingColor = "#fde68a";
    findingBg = "rgba(245, 158, 11, 0.12)";
    findingBorder = "rgba(245, 158, 11, 0.35)";
  }

  const findingBox = document.getElementById("finding-box");
  findingBox.style.background = findingBg;
  findingBox.style.borderColor = findingBorder;
  document.getElementById("finding-icon").innerText = findingIcon;

  let findingTitle =
    diag.issue_code + " Signature (" + diag.health_score + "% Health)";
  if (diag.diagnosis_summary) {
    const sentences = diag.diagnosis_summary.split(".");
    for (let s of sentences) {
      const clean = s.trim();
      if (
        clean.length > 5 &&
        !clean.includes("/100") &&
        !clean.includes("evaluated as")
      ) {
        findingTitle = clean;
        break;
      }
    }
  }
  const findingEl = document.getElementById("primary-finding-text");
  findingEl.innerText = findingTitle;
  findingEl.style.color = findingColor;

  const rootCauseList = document.getElementById("root-cause-list");
  rootCauseList.innerHTML = "";

  let rootCauses = diag.multivariate_evidence.slice(0, 4);
  if (rootCauses.length === 0) {
    rootCauses = ["No telemetry drift, alarms or similar cases found for this asset."];
  }
  rootCauses.forEach(function (cause) {
    const li = document.createElement("li");
    li.className = "root-cause-item";
    const bullet = document.createElement("span");
    bullet.className = "root-cause-bullet";
    bullet.textContent = "•";
    const text = document.createElement("span");
    text.textContent = cause;
    li.append(bullet, text);
    rootCauseList.appendChild(li);
  });

  const actionList = document.getElementById("action-list");
  actionList.innerHTML = "";
  diag.recommended_actions.forEach(function (action) {
    const li = document.createElement("li");
    li.textContent = action;
    actionList.appendChild(li);
  });

  document.getElementById("copilot-model-badge").innerText = diag.grounded_mode;
  let answer = diag.diagnosis;
  if (diag.answer) {
    answer = diag.answer;
  }
  document.getElementById("copilot-answer").textContent = answer;

  const citBox = document.getElementById("evidence-citations-box");
  citBox.innerHTML = "";
  let chipSources = [];
  if (diag.citations && diag.citations.length > 0) {
    chipSources = diag.citations;
  } else if (diag.evidence_citations && diag.evidence_citations.length > 0) {
    chipSources = diag.evidence_citations.map(function (cid) {
      return {
        source_id: cid,
        description: "Telemetry / Document Citation",
      };
    });
  }

  chipSources.forEach(function (c) {
    const chip = document.createElement("button");
    chip.className = "evidence-chip";
    chip.innerText = "[" + c.source_id + "]";
    chip.title = c.description;
    chip.onclick = function () {
      showToast("Evidence: " + c.description);
    };
    citBox.appendChild(chip);
  });

  if (diag.safety_guardrails && diag.safety_guardrails.length > 0) {
    document.getElementById("safety-text").innerText =
      diag.safety_guardrails[0];
  }

  let telemRecords = [];
  if (dossier.recent_telemetry) {
    telemRecords = dossier.recent_telemetry;
  }
  drawTelemetryTrend(telemRecords);
}

function drawTelemetryTrend(records) {
  const canvas = document.getElementById("telem-canvas");
  const ctx = canvas.getContext("2d");
  canvas.width = canvas.clientWidth * window.devicePixelRatio;
  canvas.height = canvas.clientHeight * window.devicePixelRatio;

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!records || records.length < 2) {
    return;
  }

  const pts = records.map(function (r) {
    let val = 50.0;
    if (
      r.process_pressure_bar !== undefined &&
      r.process_pressure_bar !== null
    ) {
      val = r.process_pressure_bar;
    } else if (r.vibration_mm_s !== undefined && r.vibration_mm_s !== null) {
      val = r.vibration_mm_s;
    }
    return val;
  });
  const min = Math.min(...pts);
  const max = Math.max(...pts) + 0.001;

  ctx.strokeStyle = "#00d2ff";
  ctx.lineWidth = 2 * window.devicePixelRatio;
  ctx.beginPath();

  pts.forEach(function (val, idx) {
    const x = (idx / (pts.length - 1)) * canvas.width;
    const y =
      canvas.height -
      ((val - min) / (max - min)) * (canvas.height * 0.72) -
      canvas.height * 0.14;
    if (idx === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();
}

function setupOmnibar() {
  const input = document.getElementById("omnibar-input");
  const suggestionsBox = document.getElementById("omnibar-suggestions");
  const submitBtn = document.getElementById("omnibar-submit");

  function executeOmniQuery(query) {
    const q = query.trim().toLowerCase();
    if (q.length === 0) {
      return;
    }

    let matched = null;

    if (
      q.includes("degraded") ||
      q.includes("foul") ||
      q.includes("cavitation") ||
      q.includes("critical") ||
      q.includes("fail")
    ) {
      matched = assetsData.find(function (a) {
        if (a.state) {
          return (
            a.state.condition_state === "attention_required" ||
            a.state.condition_state === "degraded"
          );
        }
        return false;
      });
    } else if (q.includes("pump")) {
      matched = assetsData.find(function (a) {
        return a.asset_class === "PROCESS_PUMP";
      });
    } else if (q.includes("valve")) {
      matched = assetsData.find(function (a) {
        return a.asset_class === "CONTROL_VALVE";
      });
    } else if (q.includes("motor")) {
      matched = assetsData.find(function (a) {
        return a.asset_class === "ELECTRIC_MOTOR";
      });
    } else {
      matched = assetsData.find(function (a) {
        return (
          a.tag.toLowerCase().includes(q) ||
          a.asset_id.toLowerCase().includes(q)
        );
      });
    }

    if (!matched && assetsData.length > 0) {
      matched = assetsData[0];
    }

    if (matched) {
      suggestionsBox.style.display = "none";
      input.value =
        matched.tag + " (" + matched.asset_class.replace("_", " ") + ")";
      selectAsset(matched.asset_id);
      focusAssetIn3D(matched.asset_id);
      if (!copilotOpen) {
        toggleCopilotDrawer();
      }
      showToast(
        "Omnibar matched: " + matched.tag + " — Focus & Diagnosis activated",
      );
    } else {
      showToast("No equipment found matching query: " + query);
    }
  }

  input.oninput = function () {
    const q = input.value.trim().toLowerCase();
    if (q.length === 0) {
      suggestionsBox.style.display = "none";
      return;
    }

    const matches = assetsData
      .filter(function (a) {
        let matchedText =
          a.tag.toLowerCase() +
          " " +
          a.asset_class.toLowerCase() +
          " " +
          a.area_name.toLowerCase();
        if (a.state) {
          matchedText +=
            " " +
            a.state.condition_state.toLowerCase() +
            " " +
            a.state.issue_summary.toLowerCase();
        }
        return matchedText.includes(q);
      })
      .slice(0, 5);

    if (matches.length > 0) {
      suggestionsBox.innerHTML = "";
      matches.forEach(function (m) {
        const item = document.createElement("div");
        item.className = "omnibar-suggestion-item";

        let stClass = "healthy";
        let hScore = 100;
        if (m.state) {
          stClass = m.state.condition_state;
          hScore = m.state.health_score;
        }

        item.innerHTML =
          '<div style="display:flex; align-items:center;">' +
          '<span class="status-dot status-' +
          stClass +
          '"></span>' +
          '<b style="color:#fff; margin-right:6px;">' +
          m.tag +
          "</b>" +
          '<span style="color:var(--muted); font-size:11px;">' +
          m.asset_class.replace("_", " ") +
          " (" +
          m.area_name +
          ")</span>" +
          "</div>" +
          '<span style="font-family:var(--font-mono); font-size:11px; color:var(--accent);">' +
          hScore +
          "%</span>";

        item.onclick = function () {
          input.value = m.tag;
          suggestionsBox.style.display = "none";
          selectAsset(m.asset_id);
          focusAssetIn3D(m.asset_id);
          if (!copilotOpen) {
            toggleCopilotDrawer();
          }
        };
        suggestionsBox.appendChild(item);
      });
      suggestionsBox.style.display = "flex";
    } else {
      suggestionsBox.style.display = "none";
    }
  };

  input.onkeydown = function (e) {
    if (e.key === "Enter") {
      executeOmniQuery(input.value);
    }
  };

  submitBtn.onclick = function () {
    executeOmniQuery(input.value);
  };
}

function setupPanelCollapses() {
  const sidebar = document.getElementById("sidebar-metaverse");
  const leftToggle = document.getElementById("btn-toggle-left-sidebar");
  const copilot = document.getElementById("copilot-drawer");
  const rightToggle = document.getElementById("btn-toggle-copilot");

  leftToggle.onclick = toggleLeftSidebar;
  rightToggle.onclick = toggleCopilotDrawer;
}

function toggleLeftSidebar() {
  const sidebar = document.getElementById("sidebar-metaverse");
  const sidebarContainer = document.getElementById("left-sidebar-container");
  const leftToggle = document.getElementById("btn-toggle-left-sidebar");

  sidebarOpen = !sidebarOpen;
  if (sidebarOpen) {
    sidebarContainer.classList.remove("collapsed");
    sidebar.classList.remove("collapsed");
    leftToggle.innerText = "◀";
    leftToggle.style.right = "-24px";
    leftToggle.style.borderRadius = "0 6px 6px 0";
    leftToggle.style.borderLeft = "none";
    leftToggle.style.borderRight = "1px solid var(--border)";
  } else {
    sidebarContainer.classList.add("collapsed");
    sidebar.classList.add("collapsed");
    leftToggle.innerText = "▶";
    leftToggle.style.right = "-24px";
    leftToggle.style.borderRadius = "0 6px 6px 0";
  }
  setTimeout(onWindowResize, 310);
}

function toggleCopilotDrawer() {
  const copilot = document.getElementById("copilot-drawer");
  const copilotContainer = document.getElementById("right-copilot-container");
  const rightToggle = document.getElementById("btn-toggle-copilot");

  copilotOpen = !copilotOpen;
  if (copilotOpen) {
    copilotContainer.classList.remove("collapsed");
    copilot.classList.remove("collapsed");
    rightToggle.innerText = "▶";
    rightToggle.style.left = "-24px";
  } else {
    copilotContainer.classList.add("collapsed");
    copilot.classList.add("collapsed");
    rightToggle.innerText = "◀";
    rightToggle.style.left = "-24px";
  }
  setTimeout(onWindowResize, 310);
}

function toggleDroneNavigation() {
  if (navProgress >= 1.0) {
    navProgress = 0;
    resetRouteLog();
  }
  isNavigating = !isNavigating;

  const navBtnText = document.getElementById("nav-btn-text");
  const navBadge = document.getElementById("nav-badge");

  if (isNavigating) {
    navBtnText.innerHTML = "❚❚ Pause Drone";
    navBadge.innerText = "Active";
    navBadge.style.color = "var(--accent)";
  } else {
    navBtnText.innerHTML = "▶ Start Drone";
    navBadge.innerText = "Paused";
    navBadge.style.color = "var(--yellow)";
  }
}

function animate() {
  requestAnimationFrame(animate);

  const now = performance.now();
  const frameSeconds = Math.min((now - lastFrameTime) / 1000, 0.05);
  lastFrameTime = now;

  if (isNavigating && currentPath.length > 1) {
    const totalLength = pathLengths[pathLengths.length - 1];
    navProgress += (ROBOT_SPEED_M_S * navSpeed * frameSeconds) / totalLength;
    if (navProgress >= 1.0) {
      navProgress = 1.0;
      isNavigating = false;
      document.getElementById("nav-btn-text").innerHTML = "▶ Start Drone";
      document.getElementById("nav-badge").innerText = "Arrived";
      document.getElementById("nav-badge").style.color = "var(--green)";
      showToast("Arrived at " + currentSelectedAsset + " — running AI diagnosis");
      if (!copilotOpen) {
        toggleCopilotDrawer();
      }
      runCopilotDiagnosis(currentSelectedAsset);
    }

    const travelled = navProgress * totalLength;
    let segIdx = 0;
    while (segIdx < currentPath.length - 2 && pathLengths[segIdx + 1] < travelled) {
      segIdx++;
    }
    const segLength = pathLengths[segIdx + 1] - pathLengths[segIdx];
    let subT = 0;
    if (segLength > 0) {
      subT = (travelled - pathLengths[segIdx]) / segLength;
    }

    const p1 = currentPath[segIdx];
    const p2 = currentPath[segIdx + 1];

    const curX = p1.x + (p2.x - p1.x) * subT;
    const curZ = p1.z + (p2.z - p1.z) * subT;
    const heading = Math.atan2(p2.x - p1.x, p2.z - p1.z);

    robotAvatar.position.x = curX;
    robotAvatar.position.z = curZ;
    robotAvatar.rotation.y = heading;

    document.getElementById("hud-nav-fill").style.width =
      (navProgress * 100).toFixed(1) + "%";

    playDueBriefings();
    checkProximityEvents(curX, curZ);

    if (cameraMode === "drone") {
      camera.position.x = curX - Math.sin(heading) * 2.2;
      camera.position.z = curZ - Math.cos(heading) * 2.2;
      camera.position.y = 1.7;
      controls.target.set(curX, 0.5, curZ);
    }
  }

  updateFreeCamera();
  controls.update();
  renderer.render(scene, camera);
}

function boxEdgeDistance(rx, rz, pos, size) {
  const beyondX = Math.max(Math.abs(rx - pos[0]) - size[0] / 2, 0);
  const beyondZ = Math.max(Math.abs(rz - pos[2]) - size[2] / 2, 0);
  return Math.hypot(beyondX, beyondZ);
}

function checkProximityEvents(rx, rz) {
  const nearby = [];

  boundingFramesGroup.children.forEach(function (c) {
    if (c.userData && c.userData.pos) {
      const dist = boxEdgeDistance(rx, rz, c.userData.pos, c.userData.size);
      const isNear = dist <= proximityRadius;

      if (c.userData.lineMat && c.userData.fillMat && c.userData.labelSprite) {
        if (isNear) {
          c.userData.lineMat.opacity = 1.0;
          c.userData.fillMat.opacity = 0.22;
          c.userData.labelSprite.material.opacity = 1.0;
          c.userData.labelSprite.position.y =
            c.userData.size[1] / 2 + 0.42 + Math.sin(Date.now() * 0.005) * 0.04;
        } else {
          const isSel = c.userData.id === currentSelectedAsset;
          if (isSel) {
            c.userData.lineMat.opacity = 1.0;
            c.userData.fillMat.opacity = 0.2;
            c.userData.labelSprite.material.opacity = 1.0;
          } else {
            c.userData.lineMat.opacity = 0.08;
            c.userData.fillMat.opacity = 0.0;
            c.userData.labelSprite.material.opacity = 0.0;
          }
        }
      }

      if (isNear) {
        nearby.push({ data: c.userData, dist: dist });
      }
    }
  });

  renderNearbyAssets(nearby);
}

// Rebuilt only when the set of nearby frames changes, not every animation frame.
let nearbyKey = "";

function renderNearbyAssets(nearby) {
  const alertEl = document.getElementById("proximity-alert");
  const assets = nearby
    .filter(function (n) {
      return n.data.isMapped;
    })
    .sort(function (a, b) {
      return a.dist - b.dist;
    });
  const structures = nearby
    .filter(function (n) {
      return !n.data.isMapped;
    })
    .sort(function (a, b) {
      return a.dist - b.dist;
    })
    .slice(0, MAX_NEARBY_STRUCTURES);
  const key = assets
    .concat(structures)
    .map(function (n) {
      return n.data.id;
    })
    .join("|") + "#" + nearby.length;
  if (key === nearbyKey) {
    return;
  }
  nearbyKey = key;

  if (nearby.length === 0) {
    alertEl.style.display = "none";
    return;
  }
  alertEl.style.display = "flex";
  document.getElementById("nearby-count").innerText =
    assets.length + " assets · " + (nearby.length - assets.length) + " structures within " + proximityRadius + " m";

  const list = document.getElementById("nearby-list");
  list.innerHTML = "";
  assets.slice(0, MAX_NEARBY_ASSETS).forEach(function (n) {
    const li = document.createElement("li");
    li.className = "nearby-item";
    li.innerHTML =
      '<span class="status-dot status-' + statusDotClass(n.data.state) + '"></span>' +
      "<b>" + n.data.tag + "</b>" +
      "<span>" + n.data.assetClass + " · " + n.data.state + " · " + n.data.health + "%</span>" +
      "<span>" + n.dist.toFixed(1) + " m</span>";
    li.onclick = function () {
      openCopilotForAsset(n.data.id);
    };
    list.appendChild(li);
  });
  structures.forEach(function (n) {
    list.appendChild(structureListItem(n));
  });
}

function statusDotClass(state) {
  if (state === "attention_required") {
    return "attention";
  }
  return state;
}

function structureListItem(n) {
  const context = n.data.context;
  const li = document.createElement("li");
  li.className = "nearby-item";
  li.style.opacity = "0.7";
  const dot = document.createElement("span");
  dot.className = "status-dot status-" + statusDotClass(context.state);
  const label = document.createElement("span");
  label.style.gridColumn = "2 / 4";
  label.textContent = context.summary;
  const distance = document.createElement("span");
  distance.textContent = n.dist.toFixed(1) + " m";
  li.append(dot, label, distance);
  return li;
}
window.appCheckProximityEvents = checkProximityEvents;

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
  document.querySelectorAll(".view-toolbar button").forEach(function (button) {
    button.classList.remove("active");
    if (button.id === "btn-cam-free") {
      button.classList.add("active");
    }
  });
  renderer.domElement.requestPointerLock();
}

function exitFreeCamera() {
  freeCam.active = false;
  freeCam.keys.clear();
  controls.enabled = true;
  if (document.exitPointerLock) {
    document.exitPointerLock();
  }
  document.getElementById("freecam-hud").style.display = "none";
  document.getElementById("btn-cam-orbit").classList.add("active");
  cameraMode = "orbit";
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

function setCameraMode(mode, targetBtn) {
  if (freeCam.active) {
    exitFreeCamera();
  }
  cameraMode = mode;
  document.querySelectorAll(".view-toolbar button").forEach(function (b) {
    b.classList.remove("active");
  });
  targetBtn.classList.add("active");

  if (mode === "top") {
    camera.position.set(...TOP_VIEW.position);
    controls.target.set(...TOP_VIEW.target);
    setObstacleOverlay(true);
  } else if (mode === "orbit") {
    camera.position.set(...ORBIT_VIEW.position);
    controls.target.set(...ORBIT_VIEW.target);
  }
}

const btnSemanticExtract = document.getElementById("btn-semantic-extract");
if (btnSemanticExtract) {
  btnSemanticExtract.onclick = async function () {
    const origHtml = btnSemanticExtract.innerHTML;
    btnSemanticExtract.disabled = true;
    btnSemanticExtract.innerHTML = "<span>⏳ Segmenting Point Cloud...</span>";

    try {
      const res = await fetch("/api/scene/extract-assets", {
        method: "POST",
      });
      const data = await res.json();
      if (res.ok) {
        build3DBoundingBoxes(data.all_frames);
        document.getElementById("asset-count").innerText =
          data.extracted_count + " Objects · " + data.mapped_asset_count + " Assets";

        btnSemanticExtract.innerHTML = `<span>✔ ${data.extracted_count} objects in ${data.processing_seconds}s</span>`;
        setTimeout(() => {
          btnSemanticExtract.disabled = false;
          btnSemanticExtract.innerHTML = origHtml;
        }, 3000);
      } else {
        alert("Segmentation error: " + (data.detail || "Unknown error"));
        btnSemanticExtract.disabled = false;
        btnSemanticExtract.innerHTML = origHtml;
      }
    } catch (err) {
      console.error("Semantic extraction error", err);
      alert("Failed to run 3D semantic extraction: " + err.message);
      btnSemanticExtract.disabled = false;
      btnSemanticExtract.innerHTML = origHtml;
    }
  };
}

document.getElementById("btn-start-nav").onclick = toggleDroneNavigation;

document.getElementById("btn-reset-nav").onclick = function () {
  isNavigating = false;
  navProgress = 0;
  document.getElementById("nav-btn-text").innerHTML = "▶ Start Drone";
  document.getElementById("nav-badge").innerText = "Ready";
  document.getElementById("nav-badge").style.color = "var(--green)";
  document.getElementById("hud-nav-fill").style.width = "0%";
  resetRouteLog();
  if (currentPath.length > 0) {
    robotAvatar.position.set(currentPath[0].x, ROBOT_GROUND_OFFSET, currentPath[0].z);
  }
};

document.getElementById("speed-slider").oninput = function (e) {
  navSpeed = parseFloat(e.target.value);
  document.getElementById("speed-val").innerText = navSpeed.toFixed(1) + "x";
};

document.getElementById("btn-cam-drone").onclick = function (e) {
  setCameraMode("drone", e.currentTarget);
};
document.getElementById("btn-cam-orbit").onclick = function (e) {
  setCameraMode("orbit", e.currentTarget);
};
document.getElementById("btn-cam-top").onclick = function (e) {
  setCameraMode("top", e.currentTarget);
};
document.getElementById("btn-cam-free").onclick = enterFreeCamera;

document
  .querySelectorAll(".render-mode-btn[data-render-mode]")
  .forEach(function (button) {
    button.onclick = function () {
      applyRenderMode(button.dataset.renderMode);
    };
  });
document.getElementById("btn-vision-analyze").onclick = analyzeCurrentView;
document.getElementById("btn-obstacles").onclick = function () {
  setObstacleOverlay(!(obstacleOverlay && obstacleOverlay.visible));
};

function askCopilot() {
  const input = document.getElementById("copilot-question");
  const question = input.value.trim();
  if (!question) {
    return;
  }
  document.getElementById("copilot-answer").textContent = "Thinking…";
  runCopilotDiagnosis(currentSelectedAsset, question);
}
document.getElementById("btn-ask-copilot").onclick = askCopilot;
document.getElementById("copilot-question").onkeydown = function (e) {
  if (e.key === "Enter") {
    askCopilot();
  }
};

document.getElementById("btn-open-copilot").onclick = function () {
  if (!copilotOpen) {
    toggleCopilotDrawer();
  }
  runCopilotDiagnosis(currentSelectedAsset);
};

document.getElementById("btn-submit-wo").onclick = async function () {
  try {
    const res = await fetch("/api/work-orders/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ asset_id: currentSelectedAsset }),
    });
    const wo = await res.json();
    showToast("Maintenance Work Order " + wo.work_order_id + " generated!");
  } catch (err) {
    showToast("Error generating work order");
  }
};

document.getElementById("asset-search").oninput = function (e) {
  const q = e.target.value.toLowerCase();
  const filtered = assetsData.filter(function (a) {
    return (
      a.tag.toLowerCase().includes(q) ||
      a.asset_class.toLowerCase().includes(q) ||
      a.area_name.toLowerCase().includes(q)
    );
  });
  renderAssetList(filtered);
};

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
  if (!container || container.clientHeight === 0) {
    return;
  }
  camera.aspect = container.clientWidth / container.clientHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(container.clientWidth, container.clientHeight);

  if (
    pointCloud &&
    pointCloud.material &&
    pointCloud.material.uniforms &&
    pointCloud.material.uniforms.uScale
  ) {
    let fovHalfRad = THREE.MathUtils.degToRad(30.0);
    if (camera && camera.fov) {
      fovHalfRad = THREE.MathUtils.degToRad(camera.fov * 0.5);
    }
    pointCloud.material.uniforms.uScale.value =
      container.clientHeight / (2.0 * Math.tan(fovHalfRad));
  }
}

window.onload = function () {
  init3D();
  runCopilotDiagnosis("ASSET-017");
};
