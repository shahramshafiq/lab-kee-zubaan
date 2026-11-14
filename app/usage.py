"""Counts what the AI services are used for: calls, tokens, time, estimated cost, and a simple hourly budget.

Free tiers have no price, so the default cost is 0. If you move to a paid plan, set the prices in .env
(LLM_PRICE_IN_PER_M and LLM_PRICE_OUT_PER_M, in dollars per million tokens) and the totals become real estimates.
"""
import logging
import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

log = logging.getLogger(__name__)

_lock = threading.Lock()
_totals: Dict[str, Dict[str, float]] = defaultdict(lambda: {"calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0,
                                                            "seconds": 0.0})
_recent: Deque[float] = deque()


def _prices():
    return float(os.getenv("LLM_PRICE_IN_PER_M", "0")), float(os.getenv("LLM_PRICE_OUT_PER_M", "0"))


def _tokens(data: dict):
    """Token counts from either answer shape (OpenAI style or Gemini style)."""
    u = data.get("usage") or {}
    if u:
        return int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
    u = data.get("usageMetadata") or {}
    return int(u.get("promptTokenCount", 0)), int(u.get("candidatesTokenCount", 0)) + int(u.get("thoughtsTokenCount", 0) or 0)


def record(label: str, data: dict, seconds: float) -> None:
    t_in, t_out = _tokens(data)
    with _lock:
        row = _totals[label]
        row["calls"] += 1
        row["tokens_in"] += t_in
        row["tokens_out"] += t_out
        row["seconds"] += seconds
        _recent.append(time.monotonic())
    log.info("AI call %s: %d in, %d out tokens, %.2fs", label, t_in, t_out, seconds)


def record_error(label: str) -> None:
    with _lock:
        _totals[label]["errors"] += 1


def calls_last_hour() -> int:
    cutoff = time.monotonic() - 3600
    with _lock:
        while _recent and _recent[0] < cutoff:
            _recent.popleft()
        return len(_recent)


def budget_left() -> int:
    """Calls left this hour. When it reaches 0 the app uses its rules text instead of calling the AI."""
    return int(os.getenv("LLM_MAX_CALLS_PER_HOUR", "1500")) - calls_last_hour()


def snapshot() -> dict:
    p_in, p_out = _prices()
    with _lock:
        models = {k: dict(v) for k, v in _totals.items()}
    total_in = sum(v["tokens_in"] for v in models.values())
    total_out = sum(v["tokens_out"] for v in models.values())
    for v in models.values():
        v["avg_seconds"] = round(v["seconds"] / v["calls"], 2) if v["calls"] else 0
        v["seconds"] = round(v["seconds"], 2)
    return {
        "models": models,
        "tokens_in": total_in,
        "tokens_out": total_out,
        "estimated_cost_usd": round(total_in / 1e6 * p_in + total_out / 1e6 * p_out, 4),
        "calls_last_hour": calls_last_hour(),
        "calls_left_this_hour": budget_left(),
    }
