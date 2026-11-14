"use strict";
// All text that comes from the server or the AI is added with textContent, never as HTML.

const $ = (id) => document.getElementById(id);
const STATUS = {
  normal: "Normal", low: "Low", high: "High", urgent: "URGENT",
  cannot_classify: "Cannot be classified", needs_demographics: "Need more information",
};
const BROWSER_VOICE = { en: "en-IN", ur: "ur-PK", roman_urdu: "en-IN" };

const state = { tab: "sample", sessionId: null, file: null, lastText: "", speaking: false, recorder: null };

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
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

const language = () => $("language").value;
const isRtl = () => language() === "ur";

function setStatus(message, isError) {
  const node = $("status");
  node.textContent = message || "";
  node.className = "status" + (isError ? " error" : "");
}

// ---------- tabs and samples ----------
document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    state.tab = button.dataset.tab;
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === button));
    ["sample", "upload", "paste"].forEach((name) => $("pane-" + name).classList.toggle("hidden", name !== state.tab));
  });
});

async function loadSamples() {
  try {
    const items = await (await api("/api/demo-reports")).json();
    const select = $("sample-select");
    items.forEach((item) => select.appendChild(new Option(item.label, item.id)));
  } catch (err) {
    setStatus(err.message, true);
  }
}

$("file-input").addEventListener("change", (event) => { state.file = event.target.files[0] || null; });

// ---------- analyze ----------
async function runAnalyze() {
  const lang = language();
  setStatus("Reading your report...");
  $("go").disabled = true;
  try {
    let response;
    if (state.tab === "sample") {
      response = await api("/api/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_id: $("sample-select").value, language: lang }),
      });
    } else if (state.tab === "paste") {
      const text = $("paste-text").value.trim();
      if (!text) throw new Error("Please paste the report text first.");
      response = await api("/api/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_text: text, language: lang }),
      });
    } else {
      if (!state.file) throw new Error("Please choose a report file first.");
      const form = new FormData();
      form.append("file", state.file);
      response = await api(`/api/analyze-file?language=${encodeURIComponent(lang)}`, { method: "POST", body: form });
    }
    const data = await response.json();
    state.sessionId = data.session_id;
    $("log").replaceChildren();
    render(data);
    setStatus("");
    $("results").classList.remove("hidden");
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    $("go").disabled = false;
  }
}
$("go").addEventListener("click", runAnalyze);
$("language").addEventListener("change", () => { if (state.sessionId) runAnalyze(); });

// ---------- render ----------
function render(data) {
  const rtl = isRtl();
  const ex = data.explanation;

  const urgent = $("urgent");
  urgent.textContent = data.urgent_warning || "";
  urgent.classList.toggle("hidden", !data.urgent_warning);

  state.lastText = ex.voice || ex.summary;
  const voice = $("voice-text");
  voice.textContent = state.lastText;
  voice.classList.toggle("rtl", rtl);

  const needs = data.summary.needs || [];
  $("needs").classList.toggle("hidden", needs.length === 0);
  $("need-age").parentElement.classList.toggle("hidden", !needs.includes("age"));
  $("need-sex").parentElement.classList.toggle("hidden", !needs.includes("sex"));

  const summary = $("summary");
  summary.textContent = ex.summary;
  summary.classList.toggle("rtl", rtl);

  const cards = $("cards");
  cards.replaceChildren();
  data.results.forEach((r) => {
    const card = el("article", "result " + r.status);
    const head = el("header");
    head.appendChild(el("h3", "", r.test));
    head.appendChild(el("span", "chip " + r.status, STATUS[r.status] || r.status));
    card.appendChild(head);

    const shown = r.value_as_written + (r.unit_as_written ? " " + r.unit_as_written : "");
    card.appendChild(el("p", "value", "Your result: " + shown));
    if (r.conversion) card.appendChild(el("p", "note", "Unit conversion: " + r.conversion));
    if (r.range_used) {
      const rg = r.range_used;
      const range = rg.qualitative ? rg.qualitative : `${rg.low} to ${rg.high} ${rg.unit}`;
      card.appendChild(el("p", "note", "Normal for this patient: " + range));
    }
    const text = ex.tests[r.test];
    if (text) card.appendChild(el("p", rtl ? "rtl" : "", text));
    if (r.reason) {
      const details = el("details");
      details.appendChild(el("summary", "", "How we decided"));
      details.appendChild(el("p", "", r.reason));
      card.appendChild(details);
    }
    cards.appendChild(card);
  });

  const questions = $("questions");
  questions.replaceChildren();
  questions.classList.toggle("rtl", rtl);
  ex.questions.forEach((q) => questions.appendChild(el("li", "", q)));

  $("disclaimer").textContent = data.disclaimer;
}

// ---------- speech out ----------
const player = $("player");

function stopSpeaking() {
  player.pause();
  window.speechSynthesis && window.speechSynthesis.cancel();
  state.speaking = false;
  $("play").textContent = "► Listen";
}

async function speak(text) {
  stopSpeaking();
  state.speaking = true;
  $("play").textContent = "■ Stop";
  try {
    const response = await api("/api/tts", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, language: language() }),
    });
    player.src = URL.createObjectURL(await response.blob());
    player.onended = stopSpeaking;
    await player.play();
  } catch (err) {
    // the voice service is down or the browser blocked sound: use the browser's own voice
    if (window.speechSynthesis) {
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = BROWSER_VOICE[language()] || "en-IN";
      utter.rate = 0.9;
      utter.onend = stopSpeaking;
      window.speechSynthesis.speak(utter);
    } else {
      stopSpeaking();
    }
  }
}
$("play").addEventListener("click", () => (state.speaking ? stopSpeaking() : speak(state.lastText)));

// ---------- chat ----------
function addMessage(who, text, refused) {
  const bubble = el("div", "msg " + who + (refused ? " refused" : ""), text);
  if (isRtl()) bubble.classList.add("rtl");
  $("log").appendChild(bubble);
  $("log").scrollTop = $("log").scrollHeight;
}

async function sendChat(message, spoken) {
  if (!message.trim() || !state.sessionId) return;
  addMessage("me", message);
  $("chat-input").value = "";
  $("send").disabled = true;
  try {
    const response = await api("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, message, language: language(), voice: spoken }),
    });
    const data = await response.json();
    if (data.analysis) render(data.analysis);
    addMessage("bot", data.answer, data.refused);
    if ($("speak-answers").checked && !data.refused) speak(data.answer);
  } catch (err) {
    addMessage("bot", err.message);
  } finally {
    $("send").disabled = false;
  }
}
$("send").addEventListener("click", () => sendChat($("chat-input").value, false));
$("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat($("chat-input").value, false); });

$("need-go").addEventListener("click", () => {
  const age = $("need-age").value.trim();
  const sex = $("need-sex").value;
  if (!age && !sex) return;
  const parts = ["I am"];
  if (age) parts.push(`${age} years old`);
  if (sex) parts.push(sex);
  sendChat(parts.join(" "), false);
});

// ---------- speech in (push to talk) ----------
async function toggleRecording() {
  const note = $("mic-note");
  if (state.recorder) { state.recorder.stop(); return; }
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    note.textContent = "This browser cannot record. Please type your question.";
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
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
    note.textContent = "Listening done. Understanding...";
    try {
      const form = new FormData();
      form.append("audio", new Blob(chunks, { type: recorder.mimeType || "audio/webm" }), "voice.webm");
      form.append("language", language());
      const text = (await (await api("/api/stt", { method: "POST", body: form })).json()).text;
      note.textContent = "";
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

loadSamples();
