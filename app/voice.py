"""Speech in and speech out. The same checked text is what gets spoken, the voice never adds anything.

Speech to text: Groq Whisper (free tier). Text to speech: Microsoft Edge neural voices through edge-tts.
If either is down the web page falls back to the browser's own speech, so voice never blocks the report.
"""
import asyncio
import hashlib
import logging
import os
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

VOICES = {
    "en": os.getenv("TTS_VOICE_EN", "en-IN-NeerjaNeural"),
    "ur": os.getenv("TTS_VOICE_UR", "ur-PK-UzmaNeural"),
    "roman_urdu": os.getenv("TTS_VOICE_ROMAN_URDU", "en-IN-NeerjaNeural"),
}
TTS_RATE = os.getenv("TTS_RATE", "-8%")  # a little slower, easier for older listeners
CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", ".tts_cache"))
MAX_TEXT = 1500
MAX_AUDIO_BYTES = 5_000_000
STT_MODEL = os.getenv("STT_MODEL", "whisper-large-v3-turbo")
# Roman Urdu speakers talk Urdu, so Whisper is told 'ur'
STT_LANG = {"en": "en", "ur": "ur", "roman_urdu": "ur"}


class VoiceUnavailable(Exception):
    """Safe to show: the speech service did not answer. The page then uses the browser voice."""


async def synthesize(text: str, language: str) -> bytes:
    import edge_tts  # imported here so the app still starts if the package is missing

    voice = VOICES.get(language, VOICES["en"])
    key = hashlib.sha1(f"{voice}|{TTS_RATE}|{text}".encode("utf-8")).hexdigest()
    cached = CACHE_DIR / f"{key}.mp3"
    if cached.exists():
        return cached.read_bytes()

    async def run() -> bytes:
        chunks = []
        async for part in edge_tts.Communicate(text, voice, rate=TTS_RATE).stream():
            if part["type"] == "audio":
                chunks.append(part["data"])
        return b"".join(chunks)

    try:
        audio = await asyncio.wait_for(run(), timeout=25)
    except Exception as exc:  # network, service change, timeout
        log.warning("Text to speech failed: %s", type(exc).__name__)
        raise VoiceUnavailable("The voice service is not available right now.") from exc
    if not audio:
        raise VoiceUnavailable("The voice service returned no sound.")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(audio)
    except OSError:
        log.warning("Could not write the voice cache")
    return audio


def transcribe(audio: bytes, filename: str, language: str) -> str:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise VoiceUnavailable("Speech recognition is not set up.")
    base = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    for attempt in range(2):
        try:
            r = httpx.post(
                f"{base}/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                data={"model": STT_MODEL, "language": STT_LANG.get(language, "en"), "response_format": "json",
                      "temperature": "0"},
                files={"file": (filename or "voice.webm", audio, "application/octet-stream")},
                timeout=30,
            )
        except (httpx.TimeoutException, httpx.TransportError):
            log.warning("Speech recognition timed out (attempt %d)", attempt + 1)
            continue
        if r.status_code == 200:
            return (r.json().get("text") or "").strip()
        log.warning("Speech recognition refused, status %d", r.status_code)
        if r.status_code != 429 and r.status_code < 500:
            break
    raise VoiceUnavailable("I could not understand the recording. Please try again or type your question.")
