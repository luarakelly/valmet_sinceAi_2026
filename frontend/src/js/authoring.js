// Team authoring mode (open the app with ?author): box each asset in the viewer once.
// YOLO-World proposes 2D boxes (or draw one); the backend lifts the box to a 3D box on the scan
// surface; saving binds the asset to it with certainty. Reads app.js globals; loaded by bootstrap.js.
(function () {
  const DETECT_CONFIDENCE = 0.12;
  const MIN_DRAG_PX = 8;
  const POLL_MS = 400;
  const SAVED_COLOR = 0x34d399;
  const PREVIEW_COLOR = 0xfbbf24;

  const state = {
    capture: null, // {viewProjection, detections}
    imageBox: null, // [x0, y0, x1, y1] fractions of the view
    lifted: null, // {center, size, point_count}
    placements: {},
    previewHelper: null,
    savedHelpers: [],
    isInitialised: false,
  };

  const panel = buildPanel();
  const overlay = buildOverlay();
  setInterval(tick, POLL_MS);

  function buildPanel() {
    const root = document.createElement("div");
    root.className = "author-panel";
    root.innerHTML =
      '<div class="author-title">Place assets</div>' +
      '<p class="author-hint">Fly close to an asset (Shift+F), then Detect. Click a yellow box, or drag your own.</p>' +
      '<button id="author-detect">Detect in this view</button>' +
      '<button id="author-reframe" hidden>Move camera</button>' +
      '<div class="author-status" id="author-status">No view captured.</div>' +
      '<select id="author-asset"></select>' +
      '<button id="author-save" disabled>Save placement</button>' +
      '<div class="author-title">Saved</div>' +
      '<div id="author-saved"></div>';
    document.body.appendChild(root);
    root.querySelector("#author-detect").onclick = detect;
    root.querySelector("#author-reframe").onclick = dropCapture;
    root.querySelector("#author-save").onclick = savePlacement;
    return root;
  }

  function buildOverlay() {
    const layer = document.createElement("div");
    layer.className = "author-overlay";
    layer.addEventListener("pointerdown", startDrag);
    document.querySelector(".viewport").appendChild(layer);
    return layer;
  }

  function isViewerReady() {
    return Boolean(scene && camera && renderer && assetsData.length > 0);
  }

  // app.js builds the scene and loads the assets asynchronously: start once both exist.
  function tick() {
    if (!isViewerReady()) {
      return;
    }
    if (!state.isInitialised) {
      state.isInitialised = true;
      fillAssetOptions();
      loadPlacements();
    }
    dropCaptureWhenCameraMoved();
  }

  function setStatus(text) {
    panel.querySelector("#author-status").innerText = text;
  }

  // ------------------------------------------------------------ capture + detect

  function currentViewProjection() {
    camera.updateMatrixWorld();
    return new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse).elements.slice();
  }

  async function captureSceneImage() {
    // Only the scan itself: robot, path, grid and helper boxes would confuse the detector.
    const hidden = scene.children.filter(function (child) {
      return child !== sceneModel && child !== sparkRenderer && child.visible;
    });
    hidden.forEach(function (child) { child.visible = false; });
    renderer.render(scene, camera);
    const blob = await new Promise(function (resolve) { renderer.domElement.toBlob(resolve, "image/jpeg", 0.9); });
    hidden.forEach(function (child) { child.visible = true; });
    return blob;
  }

  async function detect() {
    const button = panel.querySelector("#author-detect");
    button.disabled = true;
    setStatus("Detecting…");
    try {
      const viewProjection = currentViewProjection();
      const form = new FormData();
      form.append("file", await captureSceneImage(), "view.jpg");
      form.append("confidence", String(DETECT_CONFIDENCE));
      const result = await fetchJson("/api/vision/analyze", { method: "POST", body: form });
      state.capture = { viewProjection: viewProjection, detections: result.detections, image: result.image };
      showCapture();
      setStatus(result.detections.length + " proposals. Click one, or drag your own box.");
    } catch (error) {
      setStatus("Detect failed: " + error.message);
    } finally {
      button.disabled = false;
    }
  }

  function showCapture() {
    overlay.innerHTML = "";
    overlay.classList.add("active");
    panel.querySelector("#author-reframe").hidden = false;
    const image = state.capture.image;
    state.capture.detections.forEach(function (detection) {
      const box = detection.box;
      const fractions = [
        box.x / image.width,
        box.y / image.height,
        (box.x + box.width) / image.width,
        (box.y + box.height) / image.height,
      ];
      const element = drawBox(fractions, "author-proposal");
      element.innerHTML = '<span class="author-box-label">' + escapeHtml(detection.label) + " " + Math.round(detection.confidence * 100) + "%</span>";
      element.addEventListener("pointerdown", function (event) { event.stopPropagation(); });
      element.addEventListener("click", function () { chooseBox(fractions); });
    });
  }

  function drawBox(fractions, className) {
    const element = document.createElement("div");
    element.className = className;
    element.style.left = fractions[0] * 100 + "%";
    element.style.top = fractions[1] * 100 + "%";
    element.style.width = (fractions[2] - fractions[0]) * 100 + "%";
    element.style.height = (fractions[3] - fractions[1]) * 100 + "%";
    overlay.appendChild(element);
    return element;
  }

  function dropCapture() {
    state.capture = null;
    state.imageBox = null;
    overlay.innerHTML = "";
    overlay.classList.remove("active");
    panel.querySelector("#author-reframe").hidden = true;
    setPreview(null);
    setLifted(null);
    setStatus("No view captured.");
  }

  function dropCaptureWhenCameraMoved() {
    if (!state.capture) {
      return;
    }
    const now = currentViewProjection();
    const moved = now.some(function (value, index) { return Math.abs(value - state.capture.viewProjection[index]) > 1e-6; });
    if (moved) {
      dropCapture();
    }
  }

  // ------------------------------------------------------------ draw your own box

  function startDrag(event) {
    if (!state.capture) {
      return;
    }
    const rect = overlay.getBoundingClientRect();
    const start = { x: event.clientX, y: event.clientY };
    const rubber = drawBox([0, 0, 0, 0], "author-drawn");

    function fractionsAt(x, y) {
      return [(x - rect.left) / rect.width, (y - rect.top) / rect.height];
    }

    function onMove(moveEvent) {
      const a = fractionsAt(start.x, start.y);
      const b = fractionsAt(moveEvent.clientX, moveEvent.clientY);
      rubber.style.left = Math.min(a[0], b[0]) * 100 + "%";
      rubber.style.top = Math.min(a[1], b[1]) * 100 + "%";
      rubber.style.width = Math.abs(b[0] - a[0]) * 100 + "%";
      rubber.style.height = Math.abs(b[1] - a[1]) * 100 + "%";
    }

    function onUp(upEvent) {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      rubber.remove();
      const dragged = Math.hypot(upEvent.clientX - start.x, upEvent.clientY - start.y) >= MIN_DRAG_PX;
      if (!dragged) {
        return;
      }
      const a = fractionsAt(start.x, start.y);
      const b = fractionsAt(upEvent.clientX, upEvent.clientY);
      chooseBox([Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])].map(clamp01));
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function clamp01(value) {
    return Math.min(1, Math.max(0, value));
  }

  // ------------------------------------------------------------ lift + preview

  async function chooseBox(imageBox) {
    state.imageBox = imageBox;
    overlay.querySelectorAll(".author-chosen").forEach(function (element) { element.remove(); });
    drawBox(imageBox, "author-chosen");
    setStatus("Fitting a 3D box…");
    try {
      const lifted = await fetchJson("/api/scene/lift-box", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ view_projection: state.capture.viewProjection, image_box: imageBox }),
      });
      setLifted(lifted);
      setPreview(lifted);
      setStatus("Box " + lifted.size.map(function (v) { return v.toFixed(2); }).join(" × ") + " m from " + lifted.point_count + " points. Pick the asset and save.");
    } catch (error) {
      setLifted(null);
      setPreview(null);
      setStatus(error.message);
    }
  }

  function setLifted(lifted) {
    state.lifted = lifted;
    panel.querySelector("#author-save").disabled = !lifted;
  }

  function boxHelper(center, size, color) {
    const min = new THREE.Vector3(center[0] - size[0] / 2, center[1] - size[1] / 2, center[2] - size[2] / 2);
    const max = new THREE.Vector3(center[0] + size[0] / 2, center[1] + size[1] / 2, center[2] + size[2] / 2);
    const helper = new THREE.Box3Helper(new THREE.Box3(min, max), color);
    helper.material.depthTest = false;
    helper.renderOrder = 999;
    scene.add(helper);
    return helper;
  }

  function setPreview(lifted) {
    if (state.previewHelper) {
      scene.remove(state.previewHelper);
      state.previewHelper = null;
    }
    if (lifted) {
      state.previewHelper = boxHelper(lifted.center, lifted.size, PREVIEW_COLOR);
    }
  }

  // ------------------------------------------------------------ assets + saved placements

  function fillAssetOptions() {
    const select = panel.querySelector("#author-asset");
    select.innerHTML = "";
    assetsData.forEach(function (asset) {
      const option = document.createElement("option");
      option.value = asset.asset_id;
      option.innerText = asset.tag + " · " + prettyClass(asset.asset_class) + (state.placements[asset.asset_id] ? " ✓" : "");
      select.appendChild(option);
    });
  }

  async function loadPlacements() {
    try {
      state.placements = await fetchJson("/api/scene/placements");
    } catch (error) {
      setStatus("Could not load placements: " + error.message);
      return;
    }
    fillAssetOptions();
    renderSaved();
  }

  function renderSaved() {
    state.savedHelpers.forEach(function (helper) { scene.remove(helper); });
    state.savedHelpers = Object.values(state.placements).map(function (record) {
      return boxHelper(record.center, record.size, SAVED_COLOR);
    });
    const list = panel.querySelector("#author-saved");
    list.innerHTML = "";
    Object.keys(state.placements).sort().forEach(function (assetId) {
      const row = document.createElement("div");
      row.className = "author-saved-row";
      const asset = assetsData.find(function (a) { return a.asset_id === assetId; });
      row.innerHTML = "<span>" + escapeHtml(asset ? asset.tag : assetId) + '</span><button title="Remove">×</button>';
      row.querySelector("button").onclick = function () { removePlacement(assetId); };
      list.appendChild(row);
    });
  }

  async function savePlacement() {
    const assetId = panel.querySelector("#author-asset").value;
    setStatus("Saving…");
    try {
      await fetchJson("/api/scene/placements/" + encodeURIComponent(assetId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ center: state.lifted.center, size: state.lifted.size }),
      });
      window.location.reload();
    } catch (error) {
      setStatus("Save failed: " + error.message);
    }
  }

  async function removePlacement(assetId) {
    try {
      await fetchJson("/api/scene/placements/" + encodeURIComponent(assetId), { method: "DELETE" });
      window.location.reload();
    } catch (error) {
      setStatus("Remove failed: " + error.message);
    }
  }
})();
