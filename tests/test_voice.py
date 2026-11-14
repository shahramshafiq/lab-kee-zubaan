"""Voice logic that can be checked without a real speech service."""
import asyncio

import pytest

from app import voice


def test_media_type_by_content():
    assert voice.media_type(b"RIFF....WAVE") == "audio/wav"
    assert voice.media_type(b"\xff\xfb\x90\x00") == "audio/mpeg"


def test_groq_voice_is_off_by_default(monkeypatch):
    monkeypatch.delenv("TTS_ENGLISH_PROVIDER", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    assert voice._use_groq("en") is False


def test_groq_voice_used_for_english_only_when_asked(monkeypatch):
    monkeypatch.setenv("TTS_ENGLISH_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(voice, "_groq_tts_working", True)
    assert voice._use_groq("en") and voice._use_groq("roman_urdu") and not voice._use_groq("ur")


def test_fast_voice_is_used_and_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("TTS_ENGLISH_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(voice, "_groq_tts_working", True)
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    calls = []
    monkeypatch.setattr(voice, "_groq_tts", lambda text: calls.append(text) or b"RIFF0000WAVEdata")
    first = asyncio.run(voice.synthesize("hello there", "en"))
    second = asyncio.run(voice.synthesize("hello there", "en"))
    assert first == second == b"RIFF0000WAVEdata" and len(calls) == 1  # second answer came from the cache


def test_cache_key_differs_between_engines(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(voice, "_groq_tts_working", True)
    monkeypatch.delenv("TTS_ENGLISH_PROVIDER", raising=False)
    edge_key = voice._cache_file("same text", "en")
    monkeypatch.setenv("TTS_ENGLISH_PROVIDER", "groq")
    assert voice._cache_file("same text", "en") != edge_key


def test_groq_failure_turns_itself_off_and_edge_is_used(monkeypatch, tmp_path):
    class Boom:
        status_code = 400
        content = b""

    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setattr(voice, "_groq_tts_working", True)
    monkeypatch.setattr(voice.llm.client(), "post", lambda *a, **k: Boom())
    assert voice._groq_tts("hi") == b""
    assert voice._groq_tts_working is False
    monkeypatch.setattr(voice, "_groq_tts_working", True)  # leave the module clean for other tests
