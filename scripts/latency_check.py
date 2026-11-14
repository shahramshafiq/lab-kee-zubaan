"""Measures how fast each step of the voice loop is on THIS machine and network.

    python scripts/latency_check.py

Steps: AI answer (normal and quick model), speech to text, text to speech (first audio byte and full file),
and a cached spoken summary. Times are in seconds. Run it a few times: the first call is always the slowest.
"""
import asyncio
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TTS_CACHE_DIR", str(Path(__file__).resolve().parent.parent / ".tts_cache"))

from app import config, llm, voice  # noqa: E402,F401  (config loads the .env file)

SYSTEM = "Answer in one short sentence."
USER = "In simple words, what does hemoglobin measure?"
TEXT = "Your hemoglobin is very low. Please see a doctor today. Only a doctor can diagnose."


def timed(label, fn, repeat=3):
    times = []
    for _ in range(repeat):
        t = time.perf_counter()
        try:
            fn()
            times.append(time.perf_counter() - t)
        except Exception as exc:
            print(f"{label:<34} FAILED ({type(exc).__name__})")
            return
    print(f"{label:<34} first {times[0]:.2f}s | typical {statistics.median(times):.2f}s | best {min(times):.2f}s")


async def tts_first_byte(text, language):
    t = time.perf_counter()
    stream = voice.synth_stream(text, language)
    first = await stream.__anext__()
    first_byte = time.perf_counter() - t
    size = len(first)
    async for part in stream:
        size += len(part)
    return first_byte, time.perf_counter() - t, size


def main():
    llm.warm_up()
    timed("AI answer, normal model", lambda: llm.ask(SYSTEM, USER))
    timed("AI answer, quick model (voice)", lambda: llm.ask(SYSTEM, USER, fast=True))

    # unique text each time so the disk cache does not hide the real speed
    for language in ("en", "ur"):
        results = []
        for i in range(3):
            text = TEXT + (" " * (i + 1)) + str(time.time())[-4:] if language == "en" else "آپ کا ہیموگلوبن بہت کم ہے۔ " + str(i)
            results.append(asyncio.run(tts_first_byte(text, language)))
        fb = [r[0] for r in results]
        full = [r[1] for r in results]
        print(f"{'text to speech ' + language:<34} first audio {fb[0]:.2f}s | typical {statistics.median(fb):.2f}s ; "
              f"complete {statistics.median(full):.2f}s")

    asyncio.run(voice.synthesize(TEXT, "en"))  # make sure it is cached
    t = time.perf_counter()
    asyncio.run(tts_first_byte(TEXT, "en"))
    print(f"{'spoken summary from cache':<34} {time.perf_counter() - t:.3f}s")

    # speech to text with a short clip made by our own text to speech
    clip = asyncio.run(voice.synthesize("What does my hemoglobin result mean?", "en"))
    timed("speech to text (3 s clip)", lambda: voice.transcribe(clip, "clip.mp3", "en"))


if __name__ == "__main__":
    main()
