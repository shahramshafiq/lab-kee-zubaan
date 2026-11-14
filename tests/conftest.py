"""Runs before every test file: tests never call a real AI or speech service."""
import os

os.environ["PROVIDER_ORDER"] = "none"
os.environ["TTS_PREWARM"] = "false"
os.environ["LLM_MAX_CALLS_PER_HOUR"] = "100000"
