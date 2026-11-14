"""Urdu rules text, the instant-then-AI flow, and the quick-model-first explanation."""
import json
import re

import pytest
from fastapi.testclient import TestClient

from app import config, explain as ex
from app.engine import analyze
from app.explain import check_text, explain, rules_explanation
from app.extract import parse_report
from app.knowledge import load_kb
from app.main import app

client = TestClient(app)
KB = load_kb(config.DATA_DIR)
URDU = re.compile(r"[؀-ۿ]")


def analysis(filename):
    return analyze(parse_report((config.DATA_DIR / filename).read_text(encoding="utf-8")), KB, strict=True)


@pytest.fixture(autouse=True)
def fresh():
    ex._CACHE.clear()
    yield


@pytest.mark.parametrize("path", sorted(config.DATA_DIR.glob("report_*.md")), ids=lambda p: p.name[7:11])
def test_every_report_has_complete_urdu_text_without_the_ai(path):
    a = analysis(path.name)
    e = rules_explanation(a, "ur")
    assert e["language"] == "ur" and e["source"] == "rules"
    assert URDU.search(e["summary"]) and URDU.search(e["voice"])
    assert 3 <= len(e["questions"]) <= 5 and all(URDU.search(q) for q in e["questions"])
    for f in a["results"]:
        if f["test"] in ("Hemoglobin", "White Blood Cell Count", "Platelet Count", "Fasting Blood Sugar", "ALT", "AST",
                         "Cholesterol", "TSH", "Urine pH", "Urine Protein"):
            assert URDU.search(e["tests"][f["test"]]), f["test"]


def test_urdu_voice_is_short_and_warns_when_urgent():
    e = rules_explanation(analysis("report_P004_Diana_Prince_Hem_Urgent.md"), "ur")
    assert len(e["voice"].split()) <= 60 and "آج ہی ڈاکٹر" in e["voice"]


def test_urdu_text_never_names_a_disease_for_the_patient():
    for path in config.DATA_DIR.glob("report_*.md"):
        e = rules_explanation(analysis(path.name), "ur")
        blob = e["summary"] + e["voice"] + " ".join(e["tests"].values()) + " ".join(e["questions"])
        for word in ("ذیابیطس", "یرقان", "کینسر", "ہیپاٹائٹس", "خون کی کمی ہے"):
            assert word not in blob, (path.name, word)


def test_missing_sex_is_asked_in_urdu():
    e = rules_explanation(analysis("report_P012_Laura_AST_MissingSex.md"), "ur")
    assert "جنس" in e["voice"]


def test_spoken_summary_is_always_the_rules_text_even_with_ai(monkeypatch):
    a = analysis("report_P004_Diana_Prince_Hem_Urgent.md")
    good = json.dumps({"summary": "Your hemoglobin is 6.5, very low. See a doctor today.",
                       "tests": {"Hemoglobin": "It carries oxygen.", "Platelet Count": "Helps clotting."},
                       "questions": ["What should I do today?", "Do I need tests?", "Why is it low?"],
                       "voice": "this AI voice text must be ignored"})
    out = explain(a, "en", asker=lambda s, u: good)
    assert out["explanation"]["source"] == "ai"
    assert out["explanation"]["voice"] == rules_explanation(a, "en")["voice"]


def test_quick_model_first_then_the_stronger_one(monkeypatch):
    a = analysis("report_P004_Diana_Prince_Hem_Urgent.md")
    calls = []

    def fake_ask(system, user, fast=False):
        calls.append(fast)
        bad = {"summary": "Hemoglobin is 9.9. See a doctor today.", "tests": {}, "questions": ["a?", "b?", "c?"]}
        good = {"summary": "Hemoglobin is 6.5, very low. See a doctor today.", "tests": {"Hemoglobin": "Carries oxygen."},
                "questions": ["What should I do today?", "Do I need tests?", "Why is it low?"]}
        return json.dumps(bad if fast else good)

    monkeypatch.setattr(ex.llm, "ask", fake_ask)
    out = explain(a, "en")
    assert calls == [True, False] and out["explanation"]["source"] == "ai"  # quick model rejected, strong one accepted


def test_explain_endpoint_swaps_in_ai_words(monkeypatch):
    first = client.post("/api/analyze", json={"report_id": "P009", "use_ai": False, "language": "en"}).json()
    assert first["explanation"]["source"] == "rules"
    good = json.dumps({"summary": "ALT is 85 and AST is 60, both above normal. Only a doctor can diagnose.",
                       "tests": {"ALT": "A liver helper protein.", "AST": "A liver and muscle helper protein."},
                       "questions": ["Why is it high?", "Do I repeat the test?", "What should I avoid?"]})
    monkeypatch.setattr(ex.llm, "ask", lambda s, u, fast=False: good)
    r = client.post("/api/explain", json={"session_id": first["session_id"], "language": "en"})
    assert r.status_code == 200 and r.json()["explanation"]["source"] == "ai"
    again = client.post("/api/chat", json={"session_id": first["session_id"], "message": "what is ALT?"})
    assert again.status_code == 200


def test_explain_endpoint_survives_an_ai_outage(monkeypatch):
    first = client.post("/api/analyze", json={"report_id": "P004", "use_ai": False}).json()

    def down(system, user, fast=False):
        raise ex.llm.LLMUnavailable("down")

    monkeypatch.setattr(ex.llm, "ask", down)
    r = client.post("/api/explain", json={"session_id": first["session_id"], "language": "ur"})
    assert r.status_code == 200 and r.json()["explanation"]["source"] == "rules"
    assert r.json()["explanation"]["language"] == "ur"


def test_explain_endpoint_unknown_session():
    assert client.post("/api/explain", json={"session_id": "nope", "language": "en"}).status_code == 404


def test_analyze_in_urdu_without_ai_is_instant_and_urdu():
    r = client.post("/api/analyze", json={"report_id": "P013", "use_ai": False, "language": "ur"}).json()
    assert URDU.search(r["explanation"]["voice"]) and r["results"][0]["status"] == "urgent"
