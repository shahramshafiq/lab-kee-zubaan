"""The only place that talks to an AI service.

Providers are tried in the order of PROVIDER_ORDER, models in each provider's list are tried in order.
Timeouts, HTTP 429 and 5xx errors are retried with a short backoff. Errors never include keys or URLs.
"""
import json
import logging
import os
import random
import re
import time
from typing import Callable, List, Optional

import httpx

log = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """Raised when no provider could answer. The message is safe to show to a user."""


def _env_list(name: str, default: str) -> List[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


def _settings():
    return {
        "order": _env_list("PROVIDER_ORDER", "groq,gemini"),
        "timeout": float(os.getenv("REQUEST_TIMEOUT_SECONDS", "25")),
        "retries": int(os.getenv("MAX_RETRIES", "2")),
        # one question never waits longer than this in total, then the rules text is used
        "deadline": time.monotonic() + float(os.getenv("LLM_DEADLINE_SECONDS", "22")),
    }


def _post(url: str, headers: dict, body: dict, timeout: float, retries: int, deadline: float) -> Optional[dict]:
    """POST with retries. Returns parsed JSON, or None when this model should be skipped."""
    for attempt in range(retries + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            log.warning("AI deadline reached, giving up on this question")
            return None
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=min(timeout, remaining))
        except (httpx.TimeoutException, httpx.TransportError):
            log.warning("AI call timed out or failed to connect (attempt %d)", attempt + 1)
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429 or r.status_code >= 500:
                log.warning("AI service busy, status %d (attempt %d)", r.status_code, attempt + 1)
                wait = r.headers.get("retry-after")
                if wait and wait.replace(".", "", 1).isdigit() and float(wait) <= 10:
                    time.sleep(float(wait))
            else:
                log.warning("AI service refused the request, status %d", r.status_code)
                return None  # a 4xx will not get better by retrying
        time.sleep(min(2 ** attempt, 4) + random.random() * 0.3)
    return None


def _openai_compatible(prefix: str, system: str, user: str, cfg: dict) -> Optional[str]:
    key = os.getenv(f"{prefix}_API_KEY", "")
    if not key:
        return None
    base = os.getenv(f"{prefix}_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    for model in _env_list(f"{prefix}_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b"):
        data = _post(
            f"{base}/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {"model": model, "temperature": 0.2,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            cfg["timeout"], cfg["retries"], cfg["deadline"],
        )
        if data:
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                log.warning("Unexpected answer shape from %s", prefix)
    return None


def _gemini(system: str, user: str, cfg: dict) -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    base = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    for model in _env_list("GEMINI_MODELS", "gemini-3.1-flash-lite,gemini-3-flash-preview"):
        data = _post(
            f"{base}/models/{model}:generateContent",
            {"x-goog-api-key": key},
            {"systemInstruction": {"parts": [{"text": system}]},
             "contents": [{"role": "user", "parts": [{"text": user}]}],
             "generationConfig": {"temperature": 0.2}},
            cfg["timeout"], cfg["retries"], cfg["deadline"],
        )
        if data:
            try:
                return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
            except (KeyError, IndexError, TypeError):
                log.warning("Unexpected answer shape from gemini")
    return None


def ask(system: str, user: str) -> str:
    """Return the model's text. Raises LLMUnavailable if every provider failed."""
    cfg = _settings()
    for name in cfg["order"]:
        text = None
        if name == "groq":
            text = _openai_compatible("GROQ", system, user, cfg)
        elif name == "gemini":
            text = _gemini(system, user, cfg)
        elif name == "openrouter":
            text = _openai_compatible("OPENROUTER", system, user, cfg)
        if text:
            return text
    raise LLMUnavailable("The AI writer is not available right now.")


def extract_json(text: str) -> Optional[dict]:
    """Models sometimes wrap JSON in prose or code fences. Take the first {...} block."""
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def ask_json(system: str, user: str, validate: Callable[[dict], bool], asker: Callable = ask) -> dict:
    """Ask for JSON. If the answer is not valid JSON or fails validate(), ask once more, then give up."""
    for attempt in range(2):
        text = asker(system, user if attempt == 0 else user + "\n\nReturn ONLY the JSON object, nothing else.")
        data = extract_json(text)
        if data is not None and validate(data):
            return data
        log.warning("AI answer was not usable JSON (attempt %d)", attempt + 1)
    raise LLMUnavailable("The AI writer gave an answer we could not use.")
