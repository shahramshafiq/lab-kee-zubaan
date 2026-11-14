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
from app.speakable import to_speech

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


# Optional very fast English voice on Groq (about 0.3 s). It needs the account owner to accept the model's terms in the
# Groq console once. Until then (or if it ever fails) we silently use the Edge voice.
GROQ_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
GROQ_TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "hannah")
_groq_tts_working = True


def _use_groq(language: str) -> bool:
    wanted = os.getenv("TTS_ENGLISH_PROVIDER", "edge").lower() == "groq"
    return wanted and _groq_tts_working and language in ("en", "roman_urdu") and bool(os.getenv("GROQ_API_KEY"))


def _groq_tts(text: str) -> bytes:
    """Blocking call. Returns wav audio, or b'' when this voice cannot be used (and stops trying)."""
    global _groq_tts_working
    base = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    try:
        r = llm.client().post(f"{base}/audio/speech", headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                              json={"model": GROQ_TTS_MODEL, "input": text[:1000], "voice": GROQ_TTS_VOICE,
                                    "response_format": "wav"}, timeout=15)
    except Exception:
        log.warning("Groq voice did not answer, using the Edge voice")
        return b""
    if r.status_code == 200 and r.content:
        return r.content
    if r.status_code < 500 and r.status_code != 429:
        _groq_tts_working = False  # for example: terms not accepted yet. Do not try again this run.
    log.warning("Groq voice unavailable (status %d), using the Edge voice", r.status_code)
    return b""


def media_type(audio: bytes) -> str:
    return "audio/wav" if audio[:4] == b"RIFF" else "audio/mpeg"


def _cache_file(text: str, language: str) -> Path:
    engine = "groq" if _use_groq(language) else VOICES.get(language, VOICES["en"])
    key = hashlib.sha1(f"{engine}|{TTS_RATE}|{text}".encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{key}.audio"


async def synth_stream(text: str, language: str) -> AsyncIterator[bytes]:
    """Yield audio bytes as they are produced (wav from Groq in one piece, mp3 from Edge in chunks).
    Finished audio is cached for next time."""
    import edge_tts  # imported here so the app still starts if the package is missing

    text = to_speech(text, language)  # '12,000 g/dL' is said as words, not as digits
    cached = _cache_file(text, language)
    if cached.exists():
        yield cached.read_bytes()
        return
    if _use_groq(language):
        fast = await asyncio.to_thread(_groq_tts, text)
        if fast:
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cached.write_bytes(fast)
            except OSError:
                log.warning("Could not write the voice cache")
            yield fast
            return
        cached = _cache_file(text, language)  # the engine may have changed after a failure
        if cached.exists():
            yield cached.read_bytes()
            return
    voice = VOICES.get(language, VOICES["en"])
    chunks = []
    try:
        async for data in _edge_hedged(text, voice):
            chunks.append(data)
            yield data
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


# The Edge voice service is usually quick (1 to 1.5 s to the first sound) but now and then one request is slow (3 to 7 s)
# or returns nothing. So a second identical request is started when the first is slow or fails, and whichever sounds
# first is used. This is what keeps the Urdu voice from feeling slow.
HEDGE_AFTER = float(os.getenv("TTS_HEDGE_AFTER", "1.8"))
EDGE_DEADLINE = float(os.getenv("TTS_DEADLINE", "25"))


async def _edge_attempt(text: str, voice: str, tag: int, out: "asyncio.Queue") -> None:
    import edge_tts

    try:
        async for part in edge_tts.Communicate(text, voice, rate=TTS_RATE).stream():
            if part["type"] == "audio":
                await out.put((tag, part["data"]))
        await out.put((tag, None))  # finished
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await out.put((tag, exc))


async def _edge_hedged(text: str, voice: str) -> AsyncIterator[bytes]:
    out: asyncio.Queue = asyncio.Queue()
    tasks = {0: asyncio.create_task(_edge_attempt(text, voice, 0, out))}
    winner = None
    failed = set()
    deadline = asyncio.get_running_loop().time() + EDGE_DEADLINE
    try:
        while True:
            left = deadline - asyncio.get_running_loop().time()
            if left <= 0:
                raise TimeoutError("voice deadline")
            wait = left if (winner is not None or 1 in tasks) else min(left, HEDGE_AFTER)
            try:
                tag, item = await asyncio.wait_for(out.get(), wait)
            except asyncio.TimeoutError:
                if winner is None and 1 not in tasks and asyncio.get_running_loop().time() < deadline:
                    log.info("Voice is slow, starting a second request")
                    tasks[1] = asyncio.create_task(_edge_attempt(text, voice, 1, out))
                    continue
                raise TimeoutError("voice deadline")
            if winner is not None and tag != winner:
                continue  # the other request, no longer needed
            if isinstance(item, Exception):
                failed.add(tag)
                if winner == tag:
                    raise item  # failed half way through: the caller keeps what it already has
                if 1 not in tasks:  # first request failed outright: try again at once
                    tasks[1] = asyncio.create_task(_edge_attempt(text, voice, 1, out))
                elif len(failed) == 2:
                    raise item
                continue
            if item is None:
                return
            if winner is None:
                winner = tag
                for other, task in tasks.items():
                    if other != tag:
                        task.cancel()
            yield item
    finally:
        for task in tasks.values():
            task.cancel()


async def synthesize(text: str, language: str) -> bytes:
    audio = b"".join([c async for c in synth_stream(text, language)])
    if not audio:
        raise VoiceUnavailable("The voice service returned no sound.")
    return audio


def prewarm(text: str, language: str) -> None:
    """Prepare the audio in the background (blocking call, run it from a background task or thread)."""
    if os.getenv("TTS_PREWARM", "false").lower() not in ("1", "true", "yes"):  # the page primes its own audio
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
