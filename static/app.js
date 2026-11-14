"use strict";
// All text that comes from the server or the AI is added with textContent, never as HTML.

const $ = (id) => document.getElementById(id);
const STATUS = {
  en: { normal: "Normal", low: "Low", high: "High", urgent: "URGENT", cannot_classify: "Cannot be classified", needs_demographics: "Need more information" },
  ur: { normal: "نارمل", low: "کم", high: "زیادہ", urgent: "فوری توجہ", cannot_classify: "جانچ ممکن نہیں", needs_demographics: "مزید معلومات درکار" },
};
const DEVICE_LANG = { en: ["en-IN", "en-GB", "en-US", "en"], roman_urdu: ["en-IN", "en-GB", "en-US", "en"], ur: ["ur-PK", "ur-IN", "ur"] };

const state = {
  lang: "en", input: "upload", file: null, sessionId: null, analysis: null, voiceText: "",
  testNodes: {}, run: 0, recorder: null, mode: "idle",
};

// ---------- helpers ----------
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function store(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode */ } }
function recall(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; } }
const isUrdu = () => state.lang === "ur";

function markUrdu(node) {  // proper Nastaliq, right to left, only for Urdu script text
  if (isUrdu()) { node.classList.add("rtl"); node.setAttribute("lang", "ur"); }
  return node;
}

async function api(path, options) {
  let response;
  try {
    response = await fetch(path, options);
  } catch (err) {
    throw new Error("Cannot reach the server. Please check your connection.");
  }
  if (!response.ok) {
    let detail = `Something went wrong (${response.status}).`;
    try { const body = await response.json(); if (body.detail) detail = String(body.detail); } catch (e) { /* keep default */ }
    throw new Error(detail);
  }
  return response;
}

function setStatus(message, isError, busy) {
  const node = $("status");
  node.replaceChildren();
  if (busy) node.appendChild(el("span", "spin"));
  node.appendChild(document.createTextNode(message || ""));
  node.className = "status" + (isError ? " error" : "");
}

// ---------- language (set once at the top, it decides the words and the voice) ----------
function setLanguage(lang, rerun) {
  state.lang = lang;
  store("lz-lang", lang);
  document.documentElement.lang = lang === "ur" ? "ur" : "en";
  document.querySelectorAll(".seg-btn").forEach((b) => {
    const on = b.dataset.lang === lang;
    b.classList.toggle("on", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
  if (rerun && state.sessionId) switchLanguage();
}

// Same report, new language: the instant text in that language first, then the AI words.
async function switchLanguage() {
  const run = ++state.run;
  const lang = state.lang;
  try {
    const quick = await (await api("/api/explain", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, language: lang, use_ai: false }),
    })).json();
    if (run !== state.run) return;
    state.analysis.explanation = quick.explanation;
    render(state.analysis);
    explainInBackground(run, lang);
  } catch (err) {
    addMessage("bot", err.message);
  }
}
document.querySelectorAll(".seg-btn").forEach((b) => b.addEventListener("click", () => setLanguage(b.dataset.lang, true)));

// ---------- start screen ----------
function chooseFile(file) {
  state.file = file || null;
  state.input = "upload";
  $("file-name").textContent = file ? "Selected: " + file.name : "";
}
$("file-input").addEventListener("change", (e) => chooseFile(e.target.files[0]));
const drop = $("drop");
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) chooseFile(e.dataTransfer.files[0]); });

$("show-paste").addEventListener("click", () => {
  state.input = "paste";
  $("paste-box").classList.remove("hidden"); $("sample-box").classList.add("hidden");
  $("paste-text").focus();
});
$("show-sample").addEventListener("click", () => {
  state.input = "sample";
  $("sample-box").classList.remove("hidden"); $("paste-box").classList.add("hidden");
});

async function loadSamples() {
  try {
    const items = await (await api("/api/demo-reports")).json();
    items.forEach((item) => $("sample-select").appendChild(new Option(item.label, item.id)));
  } catch (err) { /* the other ways still work */ }
}

// ---------- the flow: results appear at once (rules), the AI words are swapped in when ready ----------
async function analyzeThenExplain() {
  const run = ++state.run;
  const lang = state.lang;
  setStatus("Reading your report...", false, true);
  $("go").disabled = true;
  try {
    let response;
    if (state.input === "sample") {
      response = await api("/api/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_id: $("sample-select").value, language: lang, use_ai: false }),
      });
    } else if (state.input === "paste") {
      const text = $("paste-text").value.trim();
      if (!text) throw new Error("Please paste the text of your report first.");
      response = await api("/api/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_text: text, language: lang, use_ai: false }),
      });
    } else {
      if (!state.file) throw new Error("Please choose or drop a report file first.");
      const form = new FormData();
      form.append("file", state.file);
      response = await api(`/api/analyze-file?language=${encodeURIComponent(lang)}&use_ai=false`, { method: "POST", body: form });
    }
    if (run !== state.run) return;
    const data = await response.json();
    state.sessionId = data.session_id;
    $("log").replaceChildren();
    render(data);
    showResults();
    setStatus("");
    explainInBackground(run, lang);
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    $("go").disabled = false;
  }
}

async function explainInBackground(run, lang) {
  try {
    const body = await (await api("/api/explain", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, language: lang }),
    })).json();
    if (run !== state.run || lang !== state.lang) return;  // the user moved on
    state.analysis.explanation = body.explanation;
    updateTexts(body.explanation);
  } catch (err) { /* the instant text stays, nothing is lost */ }
}

function showResults() {
  $("start").classList.add("hidden");
  $("results").classList.remove("hidden");
  window.scrollTo({ top: 0, behavior: "smooth" });
  $("h-results").focus({ preventScroll: true });
}
$("again").addEventListener("click", () => {
  stopSpeaking();
  state.sessionId = null; state.analysis = null; state.run += 1;
  $("results").classList.add("hidden");
  $("start").classList.remove("hidden");
  window.scrollTo({ top: 0 });
});
$("go").addEventListener("click", () => { state.sessionId = null; analyzeThenExplain(); });

// ---------- render ----------
function render(data) {
  state.analysis = data;
  const ex = data.explanation;
  const urdu = isUrdu();

  const urgent = $("urgent");
  urgent.textContent = data.urgent_warning || "";
  urgent.classList.toggle("hidden", !data.urgent_warning);

  state.voiceText = ex.voice || ex.summary;
  const voice = $("voice-text");
  voice.textContent = state.voiceText;
  voice.classList.toggle("rtl", urdu);
  prime(state.voiceText);

  const needs = data.summary.needs || [];
  $("needs").classList.toggle("hidden", needs.length === 0);
  $("need-age").parentElement.classList.toggle("hidden", !needs.includes("age"));
  $("need-sex").parentElement.classList.toggle("hidden", !needs.includes("sex"));

  const cards = $("cards");
  cards.replaceChildren();
  state.testNodes = {};
  data.results.forEach((r) => {
    const card = el("article", "result " + r.status);
    const head = el("header");
    const name = (ex.test_names && ex.test_names[r.test]) || r.test;
    head.appendChild(markUrdu(el("h3", "", name)));
    head.appendChild(markUrdu(el("span", "chip " + r.status, (STATUS[urdu ? "ur" : "en"])[r.status] || r.status)));
    card.appendChild(head);

    const shown = r.value_as_written + (r.unit_as_written ? " " + r.unit_as_written : "");
    const value = el("p", "value", shown);
    if (r.range_used) {
      const rg = r.range_used;
      const range = rg.qualitative ? rg.qualitative : `${rg.low} to ${rg.high} ${rg.unit}`;
      value.appendChild(el("small", "", "   normal for you: " + range));
    }
    card.appendChild(value);

    const text = el("p", "plain");
    state.testNodes[r.test] = text;
    card.appendChild(text);

    if (r.reason || r.conversion) {
      const details = el("details");
      details.appendChild(el("summary", "", "How we decided"));
      if (r.conversion) details.appendChild(el("p", "", "Unit conversion: " + r.conversion));
      if (r.reason) details.appendChild(el("p", "", r.reason));
      card.appendChild(details);
    }
    cards.appendChild(card);
  });
  updateTexts(ex);
  $("disclaimer").textContent = data.disclaimer;
}

function updateTexts(ex) {
  const urdu = isUrdu();
  Object.keys(state.testNodes).forEach((test) => {
    const node = state.testNodes[test];
    node.textContent = ex.tests[test] || "";
    node.classList.toggle("rtl", urdu);
  });
  const list = $("questions");
  list.replaceChildren();
  list.classList.toggle("rtl", urdu);
  ex.questions.forEach((q) => list.appendChild(el("li", "", q)));
}

$("need-go").addEventListener("click", () => {
  const age = $("need-age").value.trim();
  const sex = $("need-sex").value;
  if (!age && !sex) return;
  const parts = ["I am"];
  if (age) parts.push(`${age} years old`);
  if (sex) parts.push(sex);
  sendChat(parts.join(" "), false);
});

// ---------- share and print ----------
$("share").addEventListener("click", () => {
  if (!state.analysis) return;
  const ex = state.analysis.explanation;
  const lines = [ex.summary, "", "Questions for my doctor:"].concat(ex.questions.map((q) => "- " + q));
  lines.push("", "Explained by Lab Kee Zubaan. This is not a diagnosis.");
  window.open("https://wa.me/?text=" + encodeURIComponent(lines.join("\n")), "_blank", "noopener");
});
$("print").addEventListener("click", () => window.print());

// ---------- voice out ----------
// Summary: the audio is requested as soon as the results appear, so Listen starts at once.
// Chat answers: the device's own voice starts in milliseconds when it has the language, otherwise the server voice.
const player = $("player");
let deviceVoices = [];
function loadVoices() { if (window.speechSynthesis) deviceVoices = window.speechSynthesis.getVoices(); }
if (window.speechSynthesis) { loadVoices(); window.speechSynthesis.addEventListener("voiceschanged", loadVoices); }

function deviceVoice(lang) {
  for (const code of DEVICE_LANG[lang] || DEVICE_LANG.en) {
    const found = deviceVoices.filter((v) => v.lang.toLowerCase().replace("_", "-").startsWith(code.toLowerCase()));
    if (found.length) return found.find((v) => /natural|online/i.test(v.name)) || found[0];
  }
  return null;  // never fall back to a voice of another language: it would read Urdu letters as nonsense
}

function setMode(mode) {
  state.mode = mode;
  const button = $("play");
  button.classList.toggle("busy", mode === "busy");
  button.classList.toggle("on", mode === "on");
  $("play-label").textContent = mode === "on" ? "Stop" : mode === "busy" ? "Preparing" : "Listen";
}

function audioUrl(text) { return `/api/tts-stream?language=${encodeURIComponent(state.lang)}&text=${encodeURIComponent(text)}`; }

function prime(text) {
  state.primed = audioUrl(text);
  player.preload = "auto";
  player.src = state.primed;
  player.load();
}

function stopSpeaking() {
  player.pause();
  window.speechSynthesis && window.speechSynthesis.cancel();
  setMode("idle");
}

function speakOnDevice(text, voice) {
  const utter = new SpeechSynthesisUtterance(text);
  utter.voice = voice; utter.lang = voice.lang; utter.rate = 0.95;
  utter.onstart = () => setMode("on");
  utter.onend = () => setMode("idle");
  utter.onerror = () => setMode("idle");
  window.speechSynthesis.speak(utter);
}

function clip(text) {  // the voice service takes up to 1500 characters: cut at a sentence end
  if (text.length <= 1400) return text;
  const cut = text.slice(0, 1400);
  const end = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("۔"), cut.lastIndexOf("? "));
  return end > 200 ? cut.slice(0, end + 1) : cut;
}

function voiceFailed(text) {
  // server voice did not play: use the device voice if it has this language, else tell the user, never stay silent
  const voice = window.speechSynthesis ? deviceVoice(state.lang) : null;
  if (voice) { speakOnDevice(text, voice); return; }
  setMode("idle");
  $("mic-note").textContent = "I could not play the voice just now. The answer is shown above.";
}

function speakFromServer(text) {
  text = clip(text);
  const url = audioUrl(text);
  setMode("busy");
  if (!player.src.endsWith(url)) player.src = url;
  player.currentTime = 0;
  player.onplaying = () => setMode("on");
  player.onended = () => setMode("idle");
  player.onerror = () => voiceFailed(text);
  player.play().catch(() => voiceFailed(text));
}

// Phones (iPhone Safari especially) only allow sound that was started by a tap. The first tap on the page plays a
// silent clip on our audio element, after which the spoken replies are allowed.
const SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAIlYAAESsAAACABAAZGF0YQAAAAA=";
let unlocked = false;
function unlockAudio() {
  if (unlocked) return;
  unlocked = true;
  try {
    player.muted = true;
    player.src = SILENT;
    const p = player.play();
    const done = () => { player.pause(); player.muted = false; state.primed = ""; };
    if (p && p.then) p.then(done, done); else done();
    if (window.speechSynthesis) window.speechSynthesis.speak(new SpeechSynthesisUtterance(""));
  } catch (e) { player.muted = false; }
}
document.addEventListener("pointerdown", unlockAudio, { once: true });

player.addEventListener("waiting", () => { if (state.mode !== "idle") setMode("busy"); });

$("play").addEventListener("click", () => {
  if (state.mode !== "idle") { stopSpeaking(); return; }
  speakFromServer(state.voiceText);
});
window.addEventListener("pagehide", stopSpeaking);

function speakAnswer(spoken) {
  stopSpeaking();
  const voice = window.speechSynthesis ? deviceVoice(state.lang) : null;
  if (voice) speakOnDevice(clip(spoken), voice); else speakFromServer(spoken);
}

// ---------- chat ----------
function addMessage(who, text, refused) {
  const bubble = el("div", "msg " + who + (refused ? " refused" : ""), text);
  markUrdu(bubble);
  $("log").appendChild(bubble);
  $("log").scrollTop = $("log").scrollHeight;
}

async function sendChat(message, byVoice) {
  if (!message.trim() || !state.sessionId) return;
  addMessage("me", message);
  $("chat-input").value = "";
  $("send").disabled = true;
  try {
    const response = await api("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, message, language: state.lang, voice: byVoice }),
    });
    const data = await response.json();
    if (data.analysis) { render(data.analysis); explainInBackground(state.run, state.lang); }
    addMessage("bot", data.answer, data.refused);
    if (byVoice) speakAnswer(data.spoken || data.answer);  // asked by voice: answered by voice
  } catch (err) {
    addMessage("bot", err.message);
  } finally {
    $("send").disabled = false;
  }
}
$("send").addEventListener("click", () => sendChat($("chat-input").value, false));
$("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat($("chat-input").value, false); });

// ---------- voice in: press the microphone, ask, press again ----------
async function toggleRecording() {
  const note = $("mic-note");
  if (state.recorder) { state.recorder.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    note.textContent = "This browser cannot record. Please type your question.";
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch (err) {
    note.textContent = "The microphone is blocked. Allow it in the browser, or type your question.";
    return;
  }
  stopSpeaking();
  const chunks = [];
  const recorder = new MediaRecorder(stream);
  state.recorder = recorder;
  recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
  recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    state.recorder = null;
    $("mic").classList.remove("rec");
    note.textContent = "Understanding...";
    try {
      const mime = recorder.mimeType || "audio/webm";
      const ext = mime.includes("mp4") || mime.includes("aac") ? "m4a" : mime.includes("ogg") ? "ogg" : mime.includes("wav") ? "wav" : "webm";
      const form = new FormData();
      form.append("audio", new Blob(chunks, { type: mime }), "voice." + ext);  // the file name tells the speech service the format
      form.append("language", state.lang);
      const text = (await (await api("/api/stt", { method: "POST", body: form })).json()).text;
      note.textContent = "Press the microphone, ask your question, press it again.";
      if (!text) { note.textContent = "I did not hear anything. Please try again."; return; }
      await sendChat(text, true);
    } catch (err) {
      note.textContent = err.message;
    }
  };
  recorder.start();
  $("mic").classList.add("rec");
  note.textContent = "Listening... press the microphone again when you are done.";
}
$("mic").addEventListener("click", toggleRecording);

// ---------- start up ----------
setLanguage(recall("lz-lang", "en"), false);
loadSamples();
fetch("/api/warmup").catch(() => { /* only a speed-up, never required */ });
