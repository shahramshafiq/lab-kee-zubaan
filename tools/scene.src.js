// The 3D background: a slow DNA helix, rising light particles and pulsing "sound rings".
// It is built into static/scene.js by tools/build_scene.ps1 (only the parts of three.js used here are kept, so the
// file stays small for phones). Colours: sapphire, ocean and jade on a deep navy page.
import {
  AdditiveBlending, BufferAttribute, BufferGeometry, CanvasTexture, Color, DoubleSide, Group, InstancedMesh,
  LineBasicMaterial, LineSegments, Matrix4, Mesh, MeshBasicMaterial, PerspectiveCamera, Points, PointsMaterial,
  Quaternion, RingGeometry, Scene, SphereGeometry, Vector3, WebGLRenderer,
} from "three";

const OCEAN = new Color(0x00d3fb);
const JADE = new Color(0x83fd80);
const WHITE = new Color(0xffffff);
const WARM = new Color(0xff5a7a);  // used for urgent results

export function createScene(canvas, options = {}) {
  const low = !!options.low;
  const reduced = !!options.reduced;
  let renderer;
  try {
    renderer = new WebGLRenderer({ canvas, alpha: true, antialias: !low, powerPreference: "default" });
  } catch (err) {
    return null;  // no WebGL: the page still looks good with its gradient
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, low ? 1.25 : 1.75));
  renderer.setClearColor(0x000000, 0);

  const scene = new Scene();
  const camera = new PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.set(0, 0, 14);

  // ---------- a soft round light sprite ----------
  function lightSprite() {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const g = c.getContext("2d");
    const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, "rgba(255,255,255,1)");
    grd.addColorStop(0.35, "rgba(255,255,255,0.5)");
    grd.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = grd;
    g.fillRect(0, 0, 64, 64);
    return new CanvasTexture(c);
  }
  const sprite = lightSprite();

  // ---------- rising particles ----------
  const COUNT = low ? 60 : 150;
  const pos = new Float32Array(COUNT * 3);
  const col = new Float32Array(COUNT * 3);
  const speed = new Float32Array(COUNT);
  const sway = new Float32Array(COUNT);
  const tmp = new Color();
  for (let i = 0; i < COUNT; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 34;
    pos[i * 3 + 1] = (Math.random() - 0.5) * 22;
    pos[i * 3 + 2] = (Math.random() - 0.5) * 14 - 2;
    speed[i] = 0.12 + Math.random() * 0.4;
    sway[i] = Math.random() * Math.PI * 2;
    tmp.copy(Math.random() < 0.55 ? OCEAN : Math.random() < 0.6 ? JADE : WHITE);
    col.set([tmp.r, tmp.g, tmp.b], i * 3);
  }
  const pGeo = new BufferGeometry();
  pGeo.setAttribute("position", new BufferAttribute(pos, 3));
  pGeo.setAttribute("color", new BufferAttribute(col, 3));
  const pMat = new PointsMaterial({ size: low ? 0.22 : 0.17, map: sprite, vertexColors: true, transparent: true,
    opacity: 0.6, depthWrite: false, blending: AdditiveBlending });
  const points = new Points(pGeo, pMat);
  scene.add(points);

  // ---------- sound rings ----------
  const ringGroup = new Group();
  const rings = [];
  const RING_COUNT = 4;
  for (let i = 0; i < RING_COUNT; i++) {
    const mat = new MeshBasicMaterial({ color: i % 2 ? OCEAN.clone() : JADE.clone(), transparent: true, opacity: 0.2,
      side: DoubleSide, blending: AdditiveBlending, depthWrite: false });
    const ring = new Mesh(new RingGeometry(1.5, 1.55, 128), mat);
    rings.push(ring);
    ringGroup.add(ring);
  }
  scene.add(ringGroup);

  // ---------- DNA helix ----------
  const helix = new Group();
  const STEPS = low ? 26 : 40;
  const RADIUS = 1.5;
  const sphereGeo = new SphereGeometry(0.13, 10, 10);
  const sphereMat = new MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9 });
  const beads = new InstancedMesh(sphereGeo, sphereMat, STEPS * 2);
  const m = new Matrix4();
  const q = new Quaternion();
  const one = new Vector3(1, 1, 1);
  const rungs = [];
  for (let i = 0; i < STEPS; i++) {
    const y = (i - STEPS / 2) * 0.3;
    const a = i * 0.42;
    const p1 = new Vector3(Math.cos(a) * RADIUS, y, Math.sin(a) * RADIUS);
    const p2 = new Vector3(Math.cos(a + Math.PI) * RADIUS, y, Math.sin(a + Math.PI) * RADIUS);
    beads.setMatrixAt(i * 2, m.compose(p1, q, one));
    beads.setMatrixAt(i * 2 + 1, m.compose(p2, q, one));
    beads.setColorAt(i * 2, i % 3 === 0 ? JADE : OCEAN);
    beads.setColorAt(i * 2 + 1, i % 3 === 0 ? OCEAN : WHITE);
    if (i % 2 === 0) rungs.push(p1.x, p1.y, p1.z, p2.x, p2.y, p2.z);
  }
  beads.instanceMatrix.needsUpdate = true;
  if (beads.instanceColor) beads.instanceColor.needsUpdate = true;
  helix.add(beads);
  const rungGeo = new BufferGeometry();
  rungGeo.setAttribute("position", new BufferAttribute(new Float32Array(rungs), 3));
  const rungMat = new LineBasicMaterial({ color: 0x00d3fb, transparent: true, opacity: 0.35, blending: AdditiveBlending });
  helix.add(new LineSegments(rungGeo, rungMat));
  helix.rotation.z = 0.32;
  scene.add(helix);

  // ---------- state ----------
  let mode = "intro";
  let energy = 0;          // 0 calm .. 1 loud (voice, bursts)
  let burstLevel = 0;      // a short burst that fades by itself
  let holdLevel = 0;       // a level that stays (for example while the voice is speaking)
  let warm = 0;            // 0 normal colours .. 1 warm (urgent)
  let warmTarget = 0;
  let running = false;
  let last = 0;
  let t = 0;
  const pointer = { x: 0, y: 0 };
  const view = { scale: 1.2, x: 0, y: 0, z: 0, alpha: 1, ringAlpha: 1 };  // current, eased towards the mode's target
  let target = { scale: 1.2, x: 0, y: 0, z: 0, alpha: 1, ringAlpha: 1 };

  function targetFor(name) {
    const wide = canvas.clientWidth > 820;
    if (name === "intro") return { scale: 1.25, x: 0, y: 0, z: 0, alpha: 1, ringAlpha: 1 };
    return { scale: wide ? 0.62 : 0.5, x: wide ? 7.2 : 0, y: wide ? 0 : 5, z: -3, alpha: wide ? 0.36 : 0.2, ringAlpha: 0.5 };
  }
  target = targetFor(mode);

  function resize() {
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    target = targetFor(mode);
  }

  function frame(now) {
    if (!running) return;
    requestAnimationFrame(frame);
    if (document.hidden) { last = now; return; }
    const dt = Math.min((now - last) / 1000, 0.05);
    if (now - last < (low ? 28 : 14)) return;  // about 35 to 60 frames a second, saves battery on phones
    last = now;
    t += dt;
    burstLevel *= Math.pow(0.35, dt);  // bursts fade by themselves
    energy += (Math.max(burstLevel, holdLevel) - energy) * Math.min(1, dt * 5);
    warm += (warmTarget - warm) * Math.min(1, dt * 3);
    const ease = Math.min(1, dt * 1.6);
    for (const k of ["scale", "x", "y", "z", "alpha", "ringAlpha"]) view[k] += (target[k] - view[k]) * ease;

    // particles drift upward and sway
    const arr = pGeo.attributes.position.array;
    const lift = 1 + energy * 2.2;
    for (let i = 0; i < COUNT; i++) {
      arr[i * 3 + 1] += speed[i] * dt * lift;
      arr[i * 3] += Math.sin(t * 0.6 + sway[i]) * dt * 0.25;
      if (arr[i * 3 + 1] > 11) arr[i * 3 + 1] = -11;
    }
    pGeo.attributes.position.needsUpdate = true;
    pMat.opacity = 0.4 + energy * 0.4;

    // sound rings breathe slowly, and ripple outwards when there is sound
    const rate = 0.16 + energy * 0.7;
    rings.forEach((ring, i) => {
      const phase = (t * rate + i / RING_COUNT) % 1;
      const s = 0.7 + phase * (2.6 + energy * 2.2);
      ring.scale.set(s, s, 1);
      ring.material.opacity = (1 - phase) * (0.18 + energy * 0.4) * view.ringAlpha;
      ring.material.color.copy(i % 2 ? OCEAN : JADE).lerp(WARM, warm);
    });
    ringGroup.position.set(view.x * 0.6, view.y * 0.6, view.z);

    // helix turns, a little faster with sound
    helix.rotation.y += dt * (0.3 + energy * 0.9);
    helix.scale.setScalar(view.scale);
    helix.position.set(view.x, view.y, view.z);
    sphereMat.opacity = 0.9 * view.alpha;
    rungMat.opacity = 0.35 * view.alpha;
    rungMat.color.set(0x00d3fb).lerp(WARM, warm);

    // gentle parallax from the pointer or the tilt of the phone
    camera.position.x += (pointer.x * 1.2 - camera.position.x) * Math.min(1, dt * 2);
    camera.position.y += (pointer.y * 0.8 - camera.position.y) * Math.min(1, dt * 2);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  }

  window.addEventListener("pointermove", (e) => {
    pointer.x = (e.clientX / window.innerWidth - 0.5) * 2;
    pointer.y = -(e.clientY / window.innerHeight - 0.5) * 2;
  }, { passive: true });
  window.addEventListener("resize", resize);
  resize();

  return {
    start() {
      if (reduced) { renderer.render(scene, camera); return; }  // one still frame, no motion
      if (running) return;
      running = true;
      last = performance.now();
      requestAnimationFrame(frame);
    },
    stop() { running = false; },
    setMode(name) { mode = name; target = targetFor(name); },
    hold(v) { holdLevel = v; },
    setWarm(on) { warmTarget = on ? 1 : 0; },
    burst(v = 1) { burstLevel = Math.max(burstLevel, v); },
  };
}
