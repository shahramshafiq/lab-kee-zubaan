// Starts the 3D background, runs the doors-opening welcome, and lets the 3D scene react to what the page does
// (voice, new results, urgent results). All of it is decoration: if anything here fails, the page works without it.
import { createScene } from "/static/scene.js";

const root = document.documentElement;
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const small = window.innerWidth < 700 || (navigator.hardwareConcurrency || 4) <= 4;

let scene = null;
try {
  scene = createScene(document.getElementById("scene"), { low: small, reduced });
} catch (err) {
  scene = null;
}
if (scene) scene.start();

function enterApp() {
  if (!root.classList.contains("intro-on") || root.classList.contains("intro-open")) return;
  root.classList.add("intro-open");
  if (scene) { scene.burst(1); scene.setMode("ambient"); }
  window.setTimeout(() => {
    root.classList.remove("intro-on", "intro-open");
    root.classList.add("intro-done");
    const intro = document.getElementById("intro");
    if (intro) intro.hidden = true;
    const main = document.getElementById("main");
    if (main) main.focus({ preventScroll: true });
  }, 1700);
}

if (root.classList.contains("intro-on")) {
  const button = document.getElementById("enter");
  if (button) { button.addEventListener("click", enterApp); button.focus({ preventScroll: true }); }
  window.setTimeout(enterApp, 4200);  // opens by itself, so nobody is stuck at the door
} else if (scene) {
  scene.setMode("ambient");
}

// the page tells the scene what is happening
document.addEventListener("lz:voice", (e) => {
  if (!scene) return;
  scene.hold(e.detail === "on" ? 0.85 : e.detail === "busy" ? 0.3 : 0);
});
document.addEventListener("lz:listening", (e) => { if (scene) scene.hold(e.detail ? 0.55 : 0); });
document.addEventListener("lz:results", (e) => {
  if (!scene) return;
  scene.burst(1);
  scene.setWarm(!!(e.detail && e.detail.urgent));
});
document.addEventListener("lz:reset", () => { if (scene) { scene.setWarm(false); scene.hold(0); } });

// theme dots: switch without reloading, and tell the scene to take the new colours
const themeColors = { ivory: "#fbf8f1", ink: "#121212", night: "#050f26" };
function setTheme(name) {
  root.setAttribute("data-theme", name);
  try { localStorage.setItem("lz-theme", name); } catch (err) { /* private mode: the choice just is not remembered */ }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", themeColors[name] || "#fbf8f1");
  document.dispatchEvent(new CustomEvent("lz:theme", { detail: name }));
  document.querySelectorAll("[data-set-theme]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.setTheme === name)));
}
document.querySelectorAll("[data-set-theme]").forEach((b) => b.addEventListener("click", () => setTheme(b.dataset.setTheme)));
setTheme(root.getAttribute("data-theme") || "ivory");

window.lz = { scene };
