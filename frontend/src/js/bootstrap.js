// Loads Three.js r180 (ES modules) + Spark (Gaussian splat renderer), exposes them as the
// globals app.js expects (THREE, THREE.OrbitControls, THREE.PLYLoader, window.Spark), then
// starts app.js. If Spark fails to load, the app still runs with the point-cloud view.
import * as THREE_NS from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";

window.THREE = Object.assign({}, THREE_NS, { OrbitControls: OrbitControls, PLYLoader: PLYLoader });

try {
  window.Spark = await import("@sparkjsdev/spark");
} catch (error) {
  console.warn("Spark splat renderer unavailable; falling back to points", error);
  window.Spark = null;
}

const app = document.createElement("script");
app.src = "/js/app.js";
document.body.appendChild(app);

// Team authoring panel: only when the page is opened with ?author.
if (new URLSearchParams(window.location.search).has("author")) {
  app.onload = function () {
    const authoring = document.createElement("script");
    authoring.src = "/js/authoring.js";
    document.body.appendChild(authoring);
  };
}
