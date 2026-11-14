"""Speech in and speech out. The same checked text is what gets spoken, the voice never adds anything.

Speech to text: Groq Whisper (free tier). Text to speech: Microsoft Edge neural voices through edge-tts.
Speed: audio is streamed, so playback starts at the first chunk; the spoken summary is prepared in the
background right after a report is analysed (so Listen is instant); finished audio is cached on disk;
and the HTTP connection is kept warm. If either service is down the page falls back to the browser's voice.
"""
import asyncio
import hashlib
import logging
import os
from pathlib import Path
from typing import AsyncIterator

from app import llm

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


def _cache_file(text: str, language: str) -> Path:
    voice = VOICES.get(language, VOICES["en"])
    key = hashlib.sha1(f"{voice}|{TTS_RATE}|{text}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.mp3"


async def synth_stream(text: str, language: str) -> AsyncIterator[bytes]:
    """Yield mp3 bytes as they are produced. Finished audio is cached for next time."""
    import edge_tts  # imported here so the app still starts if the package is missing

    cached = _cache_file(text, language)
    if cached.exists():
        yield cached.read_bytes()
        return
    voice = VOICES.get(language, VOICES["en"])
    chunks = []
    try:
        async with asyncio.timeout(25):
            async for part in edge_tts.Communicate(text, voice, rate=TTS_RATE).stream():
                if part["type"] == "audio":
                    chunks.append(part["data"])
                    yield part["data"]
    except Exception as exc:  # network, service change, timeout
        log.warning("Text to speech failed: %s", type(exc).__name__)
        if not chunks:
            raise VoiceUnavailable("The voice service is not available right now.") from exc
        return  # some audio was already sent, stop cleanly
    if chunks:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(b"".join(chunks))
        except OSError:
            log.warning("Could not write the voice cache")


async def synthesize(text: str, language: str) -> bytes:
    audio = b"".join([c async for c in synth_stream(text, language)])
    if not audio:
        raise VoiceUnavailable("The voice service returned no sound.")
    return audio


def prewarm(text: str, language: str) -> None:
    """Prepare the audio in the background (blocking call, run it from a background task or thread)."""
    if os.getenv("TTS_PREWARM", "true").lower() not in ("1", "true", "yes"):
        return
    try:
        asyncio.run(synthesize(text, language))
    except Exception:
        log.info("Voice prewarm skipped")


def transcribe(audio: bytes, filename: str, language: str) -> str:
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise VoiceUnavailable("Speech recognition is not set up.")
    base = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    for attempt in range(2):
        try:
            r = llm.client().post(
                f"{base}/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                data={"model": STT_MODEL, "language": STT_LANG.get(language, "en"), "response_format": "json",
                      "temperature": "0"},
                files={"file": (filename or "voice.webm", audio, "application/octet-stream")},
                timeout=30,
            )
        except Exception:
            log.warning("Speech recognition timed out (attempt %d)", attempt + 1)
            continue
        if r.status_code == 200:
            return (r.json().get("text") or "").strip()
        log.warning("Speech recognition refused, status %d", r.status_code)
        if r.status_code != 429 and r.status_code < 500:
            break
    raise VoiceUnavailable("I could not understand the recording. Please try again or type your question.")
