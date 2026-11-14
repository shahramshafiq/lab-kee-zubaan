"""Web API. Thin routes only: all decisions are made in engine.py."""
import json
import logging
from decimal import Decimal
import mimetypes
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import chat, config, llm, observability, usage, voice
from app.engine import analyze
from app.explain import explain
from app.extract import Patient, parse_report
from app.knowledge import KnowledgeBase, load_kb
from app.logging_setup import setup_logging
from app.readfile import FileProblem, readings

setup_logging()
log = logging.getLogger("app")

mimetypes.add_type("application/javascript", ".js")  # some Windows setups say text/plain, which breaks module scripts
mimetypes.add_type("font/woff2", ".woff2")


class PageGZip(GZipMiddleware):
    """Compress the page files (the 3D scene is about 535 KB, 133 KB compressed) but never the API: compressing a
    streamed answer would hold sentences back and slow the voice."""

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


app = FastAPI(title="Lab Kee Zubaan", version="0.1")
app.middleware("http")(observability.middleware)
app.add_middleware(PageGZip, minimum_size=1024)
KB: KnowledgeBase = load_kb(config.DATA_DIR)
NAMES = chat.other_patient_names(config.DATA_DIR)
chat.ALIASES = KB.aliases  # so 'What does SGPT mean?' can be answered from the lab glossary
SESSIONS: Dict[str, Dict] = {}
MAX_SESSIONS = 500
MAX_CHARS = 200_000
MAX_UPLOAD = 12_000_000  # phone photos and long scanned reports are big


class AnalyzeRequest(BaseModel):
    report_text: Optional[str] = Field(None, max_length=MAX_CHARS)
    report_id: Optional[str] = Field(None, description="for example P004, one of the lab's own reports")
    age: Optional[int] = Field(None, ge=0, le=120)
    sex: Optional[str] = None
    language: str = "en"
    use_ai: bool = True


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=2000)
    language: str = "en"
    voice: bool = False  # True when the answer will be spoken: keep it very short


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=voice.MAX_TEXT)
    language: str = "en"


def _find_report(report_id: str) -> Path:
    for path in sorted(Path(config.DATA_DIR).glob("report_*.md")):
        if path.name.upper().startswith(f"REPORT_{report_id.upper()}"):
            return path
    raise HTTPException(404, f"No report with id {report_id}")


def _public(analysis: Dict) -> Dict:
    """What leaves the server. The name and record number stay inside (the chat uses them to refuse other patients)."""
    out = dict(analysis)
    out["patient"] = {k: v for k, v in analysis["patient"].items() if k not in ("name", "mrn")}
    return out


THANKS = {
    "en": ("Thank you. I used what you told me (marked as given by you, not from the report) and checked the results again."),
    "ur": ("شکریہ۔ میں نے آپ کی بتائی ہوئی معلومات استعمال کیں (ان پر نشان ہے کہ یہ آپ نے دی ہیں، رپورٹ میں نہیں تھیں) "
           "اور نتائج دوبارہ جانچ لیے۔"),
    "roman_urdu": ("Shukriya. Maine aap ki batayi hui maloomat istemal ki (nishan hai ke yeh aap ne di hain, report mein "
                   "nahin thin) aur nataij dobara jaanch liye."),
}


def _run(patient: Patient, language: str, use_ai: bool, background: Optional[BackgroundTasks] = None) -> Dict:
    result = explain(analyze(patient, KB), language=language, use_ai=use_ai)
    if background is not None:  # prepare the spoken summary now, so the Listen button plays at once
        voice_language = language if language in voice.VOICES else "en"
        background.add_task(voice.prewarm, result["explanation"]["voice"], voice_language)
    if len(SESSIONS) >= MAX_SESSIONS:
        SESSIONS.pop(next(iter(SESSIONS)))
    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = {"patient": patient, "analysis": result}
    result["session_id"] = session_id
    return _public(result)


def _apply_overrides(patient: Patient, age: Optional[int], sex: Optional[str]) -> None:
    """Age or sex given by the user (not by the report). The result says so."""
    if age is not None and patient.age is None:
        patient.age, patient.age_raw = age, f"{age} (given by the user)"
    if sex and patient.sex is None:
        s = sex.strip().lower()
        if s in ("male", "female"):
            patient.sex, patient.sex_raw = s, f"{s} (given by the user)"


class RangeRequest(BaseModel):
    session_id: str
    test: str = Field(..., min_length=1, max_length=80)
    low: float
    high: float
    language: str = "en"


@app.post("/api/user-range")
def user_range(req: RangeRequest):
    """The patient types the normal range printed on their own report for a test we have no range for.
    The result is then compared with it and labelled as coming from the patient, never as one of our lab files."""
    session = SESSIONS.get(req.session_id)
    if not session:
        raise HTTPException(404, "This conversation has expired. Please upload the report again.")
    if not (abs(req.low) < 1e9 and abs(req.high) < 1e9) or req.low >= req.high or req.low < 0:
        raise HTTPException(422, "Please type the range as two numbers, the lower one first (for example 15 and 150).")
    match = [f for f in session["analysis"]["results"] if f["test"] == req.test and f["can_provide_range"]]
    if not match:
        raise HTTPException(422, "This test does not need a range from you.")
    ranges = session.setdefault("user_ranges", {})
    ranges[match[0]["test_as_written"].strip().lower()] = (Decimal(str(req.low)), Decimal(str(req.high)))
    updated = explain(analyze(session["patient"], KB, user_ranges=ranges), language=req.language, use_ai=False)
    updated["session_id"] = req.session_id
    session["analysis"] = updated
    return _public(updated)


@app.get("/api/health")
def health():
    return {"ok": True, "ranges": len(KB.ranges), "urgent_rules": len(KB.urgent)}


@app.get("/api/metrics")
def metrics():
    """Simple counters: requests, errors, refusals, rate limits, AI fallbacks."""
    return dict(observability.METRICS)


@app.get("/api/demo-reports")
def demo_reports():
    """The lab's own sample reports, for trying the tool. Patient names are not listed."""
    out = []
    for path in sorted(Path(config.DATA_DIR).glob("report_*.md")):
        report_id = path.stem.split("_")[1]
        out.append({"id": report_id, "label": f"Sample report {report_id}"})
    return out


@app.post("/api/analyze")
def analyze_report(req: AnalyzeRequest, background: BackgroundTasks):
    if req.report_text:
        text, source = req.report_text, "pasted report"
    elif req.report_id:
        path = _find_report(req.report_id)
        text, source = path.read_text(encoding="utf-8"), path.name
    else:
        raise HTTPException(400, "Send report_text or report_id.")
    patient = parse_report(text, source)
    if not patient.results:
        raise HTTPException(422, "I could not find any test results in this report.")
    _apply_overrides(patient, req.age, req.sex)
    return _run(patient, req.language, req.use_ai, background)


class ExplainRequest(BaseModel):
    session_id: str
    language: str = "en"
    use_ai: bool = True  # False: only the instant rules text, in the chosen language (used when the language changes)


@app.post("/api/explain")
def explain_session(req: ExplainRequest):
    """The AI-written words for a report that was already analysed. The page shows the instant rules text first
    (analyze with use_ai=false) and swaps these in when they arrive."""
    session = SESSIONS.get(req.session_id)
    if not session:
        raise HTTPException(404, "This conversation has expired. Please upload the report again.")
    updated = explain(session["analysis"], language=req.language, use_ai=req.use_ai)
    updated["session_id"] = req.session_id
    session["analysis"] = updated
    return {"explanation": updated["explanation"]}


def _read_upload(raw: bytes, filename: str) -> Patient:
    """Try each reading of the file (plain text, laid-out text, OCR) and keep the first one with test results."""
    last_problem = None
    try:
        for text in readings(raw, filename):
            patient = parse_report(text, filename)
            if patient.results:
                return patient
    except FileProblem as exc:
        last_problem = exc
    except Exception as exc:  # a broken file must never become a server error
        log.warning("Could not read the upload: %s", type(exc).__name__)
        last_problem = FileProblem("I could not read this file. Please try a PDF, a picture, a Word file or a text file.")
    if last_problem:
        raise HTTPException(422, str(last_problem))
    raise HTTPException(422, "I could not find any test results in this file. If it is a photo, please make sure the "
                             "results table is sharp and fully in the picture.")


@app.post("/api/analyze-file")
async def analyze_file(background: BackgroundTasks, file: UploadFile = File(...), language: str = "en",
                       use_ai: bool = True):
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "File is too big (limit 12 MB).")
    if not raw:
        raise HTTPException(400, "The file is empty.")
    patient = await run_in_threadpool(_read_upload, raw, file.filename or "upload")
    return _run(patient, language, use_ai, background)


@app.post("/api/chat")
def chat_with_report(req: ChatRequest):
    session = SESSIONS.get(req.session_id)
    if not session:
        raise HTTPException(404, "This conversation has expired. Please upload the report again.")
    patient: Patient = session["patient"]
    # an answer to "please tell me your age or sex" updates the report and re-checks the results
    age, sex = chat.parse_demographics(req.message)
    needs = session["analysis"]["summary"]["needs"]
    if needs and ((age and "age" in needs) or (sex and "sex" in needs)):
        _apply_overrides(patient, age, sex)
        updated = explain(analyze(patient, KB, user_ranges=session.get('user_ranges')), language=req.language, use_ai=True)
        updated["session_id"] = req.session_id
        session["analysis"] = updated
        return {"answer": THANKS.get(req.language, THANKS["en"]), "refused": False, "source": "rules",
                "analysis": _public(updated)}
    return chat.answer(req.message, session["analysis"], NAMES, req.language, voice=req.voice)


@app.post("/api/chat-stream")
def chat_with_report_stream(req: ChatRequest):
    """Same as /api/chat, but the answer arrives sentence by sentence (one JSON object per line), so the page can
    start speaking the first sentence while the model is still writing the rest."""
    session = SESSIONS.get(req.session_id)
    if not session:
        raise HTTPException(404, "This conversation has expired. Please upload the report again.")
    patient: Patient = session["patient"]
    age, sex = chat.parse_demographics(req.message)
    needs = session["analysis"]["summary"]["needs"]

    def events():
        if needs and ((age and "age" in needs) or (sex and "sex" in needs)):
            _apply_overrides(patient, age, sex)
            updated = explain(analyze(patient, KB, user_ranges=session.get("user_ranges")), language=req.language,
                              use_ai=False)
            updated["session_id"] = req.session_id
            session["analysis"] = updated
            text = THANKS.get(req.language, THANKS["en"])
            yield {"type": "final", "answer": text, "spoken": text, "refused": False, "source": "rules",
                   "analysis": _public(updated)}
            return
        yield from chat.answer_stream(req.message, session["analysis"], NAMES, req.language, voice=req.voice)

    def lines():
        for event in events():
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


@app.post("/api/stt")
async def speech_to_text(audio: UploadFile = File(...), language: str = Form("en")):
    """A recording of the patient's question, returned as text."""
    raw = await audio.read()
    if not raw:
        raise HTTPException(400, "The recording is empty.")
    if len(raw) > voice.MAX_AUDIO_BYTES:
        raise HTTPException(413, "The recording is too long (limit 5 MB).")
    try:
        text = await run_in_threadpool(voice.transcribe, raw, audio.filename or "voice.webm", language)
    except voice.VoiceUnavailable as exc:
        raise HTTPException(503, str(exc))
    return {"text": text}


@app.post("/api/tts")
async def text_to_speech(req: SpeakRequest):
    """Spoken audio (mp3) for a text we wrote. If this fails the page uses the browser voice."""
    try:
        audio = await voice.synthesize(req.text, req.language)
    except voice.VoiceUnavailable as exc:
        raise HTTPException(503, str(exc))
    return Response(content=audio, media_type=voice.media_type(audio))


@app.get("/api/tts-stream")
async def text_to_speech_stream(text: str = Query(..., min_length=1, max_length=voice.MAX_TEXT), language: str = "en"):
    """Same audio, streamed: the browser starts playing at the first chunk. Used by the page."""
    stream = voice.synth_stream(text, language if language in voice.VOICES else "en")
    try:
        first = await stream.__anext__()  # fail now (503) instead of halfway through a response
    except voice.VoiceUnavailable as exc:
        raise HTTPException(503, str(exc))
    except StopAsyncIteration:
        raise HTTPException(503, "The voice service returned no sound.")

    async def chunks():
        yield first
        async for part in stream:
            yield part

    return StreamingResponse(chunks(), media_type=voice.media_type(first),
                             headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/warmup")
async def warm_up():
    """Called when the page opens: opens the AI connection and prepares a first voice, so the first real use is fast."""
    ai = await run_in_threadpool(llm.warm_up)
    try:
        await voice.synthesize("Ready.", "en")
        speech = True
    except voice.VoiceUnavailable:
        speech = False
    return {"ai": ai, "speech": speech}


@app.get("/api/usage")
def ai_usage():
    """What the AI services were used for: calls, tokens, estimated cost, calls left this hour."""
    return usage.snapshot()


STATIC = Path(__file__).resolve().parent.parent / "static"
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html")
