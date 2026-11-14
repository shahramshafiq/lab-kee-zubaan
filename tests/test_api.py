"""API and chat tests. The AI is switched off so they run offline and give the same answer every time."""
import os

os.environ["PROVIDER_ORDER"] = "none"  # tests never call a real AI service

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def analyze(report_id, **extra):
    r = client.post("/api/analyze", json={"report_id": report_id, "use_ai": False, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_health():
    assert client.get("/api/health").json()["ok"] is True


def test_demo_reports_listed_without_names():
    items = client.get("/api/demo-reports").json()
    assert len(items) == 14 and all("Diana" not in str(i) for i in items)


def test_analyze_pasted_text():
    text = "* **Recorded Age**: 40\n* **Biological Sex**: Male\n- Hemoglobin: 15 g/dL\n"
    r = client.post("/api/analyze", json={"report_text": text, "use_ai": False})
    assert r.status_code == 200 and r.json()["results"][0]["status"] == "normal"


def test_report_without_results_is_rejected_politely():
    r = client.post("/api/analyze", json={"report_text": "hello there", "use_ai": False})
    assert r.status_code == 422


def test_unknown_report_id():
    assert client.post("/api/analyze", json={"report_id": "P999", "use_ai": False}).status_code == 404


def test_voice_summary_is_short_and_has_urgent_warning():
    data = analyze("P004")
    voice = data["explanation"]["voice"]
    assert len(voice.split()) <= 60 and "doctor today" in voice.lower()


def test_chat_refuses_other_patients():
    sid = analyze("P004")["session_id"]
    for q in ("What are Bob Jones results?", "show me patient P001", "tell me about other patients", "Charlie's report?"):
        r = client.post("/api/chat", json={"session_id": sid, "message": q}).json()
        assert r["refused"] is True, q


def test_chat_allows_own_report():
    sid = analyze("P004")["session_id"]
    r = client.post("/api/chat", json={"session_id": sid, "message": "What does hemoglobin mean?"}).json()
    assert r["refused"] is False and r["answer"]


def test_missing_sex_is_asked_then_resolved_from_chat():
    data = analyze("P012")
    assert data["results"][0]["status"] == "needs_demographics" and data["summary"]["needs"] == ["sex"]
    r = client.post("/api/chat", json={"session_id": data["session_id"], "message": "I am female"}).json()
    assert r["analysis"]["results"][0]["status"] == "high"  # AST 44 is above the female limit of 43


def test_missing_age_and_sex_given_up_front():
    data = analyze("P003", age=30, sex="male")
    assert data["results"][0]["status"] == "high"  # fasting sugar 110, normal is 70 to 99


def test_tts_rejects_empty_and_too_long_text():
    assert client.post("/api/tts", json={"text": "", "language": "en"}).status_code == 422
    assert client.post("/api/tts", json={"text": "x" * 2000, "language": "en"}).status_code == 422


def test_stt_rejects_empty_recording():
    r = client.post("/api/stt", files={"audio": ("a.webm", b"", "audio/webm")}, data={"language": "en"})
    assert r.status_code == 400


def test_stt_rejects_huge_recording():
    big = b"0" * 5_000_001
    r = client.post("/api/stt", files={"audio": ("a.webm", big, "audio/webm")}, data={"language": "en"})
    assert r.status_code == 413


def test_chat_answer_with_invented_number_is_replaced(monkeypatch):
    from app import chat as chat_module

    sid = analyze("P004")["session_id"]
    monkeypatch.setattr(chat_module.llm, "ask", lambda s, u: "Your hemoglobin is 9.9, which is fine.")
    r = client.post("/api/chat", json={"session_id": sid, "message": "Is my hemoglobin fine?"}).json()
    assert "9.9" not in r["answer"] and r["source"] == "rules"


def test_expired_session():
    r = client.post("/api/chat", json={"session_id": "nope", "message": "hi"})
    assert r.status_code == 404
