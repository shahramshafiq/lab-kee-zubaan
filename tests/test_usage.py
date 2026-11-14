"""Usage counting and the hourly budget that switches the AI off before it can run away."""
import pytest

from app import llm, usage


@pytest.fixture(autouse=True)
def clean():
    usage._totals.clear()
    usage._recent.clear()
    yield
    usage._totals.clear()
    usage._recent.clear()


def test_tokens_counted_for_both_answer_shapes():
    usage.record("groq:m", {"usage": {"prompt_tokens": 100, "completion_tokens": 40}}, 0.5)
    usage.record("gemini:m", {"usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 3}}, 1.0)
    snap = usage.snapshot()
    assert snap["tokens_in"] == 110 and snap["tokens_out"] == 48
    assert snap["models"]["groq:m"]["calls"] == 1 and snap["models"]["gemini:m"]["avg_seconds"] == 1.0


def test_cost_estimate_uses_prices_from_the_environment(monkeypatch):
    monkeypatch.setenv("LLM_PRICE_IN_PER_M", "1.0")
    monkeypatch.setenv("LLM_PRICE_OUT_PER_M", "2.0")
    usage.record("x", {"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 500_000}}, 1)
    assert usage.snapshot()["estimated_cost_usd"] == 2.0


def test_errors_are_counted():
    usage.record_error("x")
    assert usage.snapshot()["models"]["x"]["errors"] == 1


def test_budget_stops_the_ai_and_the_app_falls_back(monkeypatch):
    monkeypatch.setenv("LLM_MAX_CALLS_PER_HOUR", "2")
    usage.record("x", {}, 0.1)
    usage.record("x", {}, 0.1)
    assert usage.budget_left() == 0
    with pytest.raises(llm.LLMUnavailable):
        llm.ask("s", "u")
