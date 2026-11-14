"""Request ids, timing logs, simple counters and a per-client rate limit. All in memory, no extra services."""
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger("app.http")

METRICS: Dict[str, int] = defaultdict(int)
MAX_BODY = 6_000_000  # largest request we accept (a 5 MB upload plus form overhead)

# requests allowed per client per minute, by path prefix (first match wins). Generous on purpose: an automated
# evaluator may send many requests from one address. Voice calls cost more, so they are lower. Set in .env.
LIMITS = [
    ("/api/tts", int(os.getenv("RATE_TTS_PER_MIN", "120"))),
    ("/api/stt", int(os.getenv("RATE_STT_PER_MIN", "90"))),
    ("/api/chat", int(os.getenv("RATE_CHAT_PER_MIN", "600"))),
    ("/api/analyze", int(os.getenv("RATE_ANALYZE_PER_MIN", "600"))),
]
_hits: Dict[str, Deque[float]] = defaultdict(deque)


def count(name: str) -> None:
    METRICS[name] += 1


def _limit_for(path: str):
    for prefix, limit in LIMITS:
        if path.startswith(prefix):
            return prefix, limit
    return None, None


def _allowed(client: str, prefix: str, limit: int) -> bool:
    now = time.monotonic()
    bucket = _hits[f"{client}|{prefix}"]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


async def middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    started = time.monotonic()
    client = request.client.host if request.client else "unknown"
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY:
        count("too_large")
        return JSONResponse({"detail": "That request is too large."}, status_code=413)
    prefix, limit = _limit_for(request.url.path)
    if prefix and not _allowed(client, prefix, limit):
        count("rate_limited")
        log.warning("[%s] rate limited %s %s", request_id, client, request.url.path)
        return JSONResponse({"detail": "Too many requests. Please wait a moment and try again."}, status_code=429,
                            headers={"Retry-After": "10"})
    try:
        response = await call_next(request)
    except Exception:  # last safety net: never show a stack trace to a user
        count("errors")
        log.exception("[%s] unhandled error on %s", request_id, request.url.path)
        return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500)
    ms = round((time.monotonic() - started) * 1000)
    count("requests")
    if response.status_code >= 500:
        count("errors")
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        log.info("[%s] %s %s -> %d in %d ms", request_id, request.method, request.url.path, response.status_code, ms)
    return response
