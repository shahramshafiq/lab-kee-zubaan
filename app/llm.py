"""The only place that talks to an AI service.

Providers are tried in the order of PROVIDER_ORDER, models in each provider's list are tried in order.
Timeouts, HTTP 429 and 5xx errors are retried with a short backoff. Errors never include keys or URLs.
One shared connection pool is kept alive, so a call does not pay for a new TLS handshake every time.
Every call is counted in usage.py, and an hourly call budget turns the AI off before it can run away.
"""
import json
import logging
import os
import random
import re
import time
from typing import Callable, List, Optional

import httpx

from app import usage

log = logging.getLogger(__name__)

_client: Optional[httpx.Client] = None


class LLMUnavailable(Exception):
    """Raised when no provider could answer. The message is safe to show to a user."""


def client() -> httpx.Client:
    """One connection pool for the whole app (keep-alive), created on first use."""
    global _client
    if _client is None:
        _client = httpx.Client(limits=httpx.Limits(max_connections=20, max_keepalive_connections=10,
                                                   keepalive_expiry=120))
    return _client


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


def _post(url: str, headers: dict, body: dict, timeout: float, retries: int, deadline: float,
          label: str) -> Optional[dict]:
    """POST with retries. Returns parsed JSON, or None when this model should be skipped."""
    for attempt in range(retries + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            log.warning("AI deadline reached, giving up on this question")
            return None
        started = time.monotonic()
        try:
            r = client().post(url, headers=headers, json=body, timeout=min(timeout, remaining))
        except (httpx.TimeoutException, httpx.TransportError):
            log.warning("AI call %s timed out or failed to connect (attempt %d)", label, attempt + 1)
            usage.record_error(label)
        else:
            if r.status_code == 200:
                data = r.json()
                usage.record(label, data, time.monotonic() - started)
                return data
            usage.record_error(label)
            if r.status_code == 429 or r.status_code >= 500:
                log.warning("AI service busy (%s), status %d (attempt %d)", label, r.status_code, attempt + 1)
                wait = r.headers.get("retry-after")
                if wait and wait.replace(".", "", 1).isdigit() and float(wait) <= 10:
                    time.sleep(float(wait))
            else:
                log.warning("AI service refused the request (%s), status %d", label, r.status_code)
                return None  # a 4xx will not get better by retrying
        time.sleep(min(2 ** attempt, 4) * 0.5 + random.random() * 0.2)
    return None


def _models(prefix: str, fast: bool, default: str, default_fast: str) -> List[str]:
    if fast:
        return _env_list(f"{prefix}_MODELS_FAST", default_fast)
    return _env_list(f"{prefix}_MODELS", default)


def _openai_compatible(prefix: str, system: str, user: str, cfg: dict, fast: bool) -> Optional[str]:
    key = os.getenv(f"{prefix}_API_KEY", "")
    if not key:
        return None
    base = os.getenv(f"{prefix}_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    for model in _models(prefix, fast, "openai/gpt-oss-120b,openai/gpt-oss-20b", "openai/gpt-oss-20b,openai/gpt-oss-120b"):
        data = _post(
            f"{base}/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {"model": model, "temperature": 0.2,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            cfg["timeout"], cfg["retries"], cfg["deadline"], f"{prefix.lower()}:{model}",
        )
        if data:
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                log.warning("Unexpected answer shape from %s", prefix)
    return None


def _gemini(system: str, user: str, cfg: dict, fast: bool) -> Optional[str]:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return None
    base = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    for model in _models("GEMINI", fast, "gemini-3.1-flash-lite,gemini-3-flash-preview",
                         "gemini-3.1-flash-lite,gemini-3-flash-preview"):
        data = _post(
            f"{base}/models/{model}:generateContent",
            {"x-goog-api-key": key},
            {"systemInstruction": {"parts": [{"text": system}]},
             "contents": [{"role": "user", "parts": [{"text": user}]}],
             "generationConfig": {"temperature": 0.2}},
            cfg["timeout"], cfg["retries"], cfg["deadline"], f"gemini:{model}",
        )
        if data:
            try:
                return "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
            except (KeyError, IndexError, TypeError):
                log.warning("Unexpected answer shape from gemini")
    return None


def ask(system: str, user: str, fast: bool = False) -> str:
    """Return the model's text. fast=True tries the quicker model first (used for spoken answers).
    Raises LLMUnavailable if every provider failed or the hourly budget is used up."""
    if usage.budget_left() <= 0:
        log.warning("Hourly AI call budget used up, using rules text")
        raise LLMUnavailable("The AI writer is resting for now.")
    cfg = _settings()
    for name in cfg["order"]:
        text = None
        if name == "groq":
            text = _openai_compatible("GROQ", system, user, cfg, fast)
        elif name == "gemini":
            text = _gemini(system, user, cfg, fast)
        elif name == "openrouter":
            text = _openai_compatible("OPENROUTER", system, user, cfg, fast)
        if text:
            return text
    raise LLMUnavailable("The AI writer is not available right now.")


def warm_up() -> bool:
    """Open the connection to the first provider ahead of time, so the first real question is not slower."""
    for name in _env_list("PROVIDER_ORDER", "groq,gemini"):
        if name == "groq" and os.getenv("GROQ_API_KEY"):
            base = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
            try:
                client().get(f"{base}/models", headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"},
                             timeout=8)
                return True
            except httpx.HTTPError:
                return False
    return False


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
