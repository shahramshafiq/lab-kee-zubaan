"""Things an attacker or a curious judge might try against the API and the page."""
import os
import re
from pathlib import Path

os.environ["PROVIDER_ORDER"] = "none"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
STATIC = Path(__file__).resolve().parent.parent / "static"


def new_session(report_id="P004"):
    return client.post("/api/analyze", json={"report_id": report_id, "use_ai": False}).json()["session_id"]


@pytest.mark.parametrize("report_id", ["../README", "..\\README", "P004/../../x", "%2e%2e/x", "", " ", "P" * 5000,
                                       "P004'; DROP TABLE x;--", "<script>alert(1)</script>", "*", "report_", None])
def test_report_id_cannot_escape_the_lab_folder(report_id):
    body = {"report_id": report_id, "use_ai": False} if report_id is not None else {"use_ai": False}
    r = client.post("/api/analyze", json=body)
    assert r.status_code in (400, 404, 422), (report_id, r.status_code)


def test_sessions_are_separate_and_unguessable():
    a, b = new_session("P004"), new_session("P013")
    assert a != b and len(a) >= 32
    ra = client.post("/api/chat", json={"session_id": a, "message": "what is my result"}).json()
    rb = client.post("/api/chat", json={"session_id": b, "message": "what is my result"}).json()
    assert ra["answer"] != rb["answer"]
    assert client.post("/api/chat", json={"session_id": a[:-1] + "0", "message": "hi"}).status_code in (200, 404)
    assert client.post("/api/chat", json={"session_id": "../../etc/passwd", "message": "hi"}).status_code == 404


def test_error_responses_do_not_leak_stack_traces_or_paths():
    for r in (client.post("/api/analyze", content=b"{broken"), client.post("/api/chat", json={}),
              client.get("/api/nothing"), client.post("/api/analyze", json={"report_id": "P999"})):
        text = r.text
        assert "Traceback" not in text and "C:\\" not in text and "/app/" not in text


def test_security_headers_present():
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "no-referrer" in r.headers["referrer-policy"]
    assert "microphone=(self)" in r.headers["permissions-policy"]


def test_huge_request_body_is_refused_early():
    r = client.post("/api/analyze", content=b"x" * 7_000_000, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_the_page_never_inserts_model_text_as_html():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "document.write" not in js and "eval(" not in js


def test_the_page_loads_no_outside_scripts():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert not re.search(r'<script[^>]+src=["\']https?://', html)


def test_script_in_a_name_comes_back_as_plain_data():
    text = "* **Patient Full Name**: <script>alert(1)</script>\n* **Recorded Age**: 40\n* **Biological Sex**: Male\nHemoglobin: 15 g/dL"
    r = client.post("/api/analyze", json={"report_text": text, "use_ai": False})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")


def test_prompt_never_contains_name_or_record_number(monkeypatch):
    """The model only sees age, sex and results. Check the exact text that would be sent."""
    seen = []
    from app import explain as ex

    def spy(system, user):
        seen.append(system + "\n" + user)
        raise ex.llm.LLMUnavailable("test")

    ex._CACHE.clear()
    text = ("* **Patient Full Name**: Zaynab Qureshi\n* **Medical Record Number (MRN)**: CLD-X77-1234\n"
            "* **Recorded Age**: 40\n* **Biological Sex**: Female\nHemoglobin: 15 g/dL")
    from app.engine import analyze
    from app.extract import parse_report
    from app.main import KB

    ex.explain(analyze(parse_report(text), KB), asker=spy)
    blob = " ".join(seen)
    assert seen and "Zaynab" not in blob and "Qureshi" not in blob and "CLD-X77" not in blob


def test_chat_message_length_and_type_limits():
    sid = new_session()
    assert client.post("/api/chat", json={"session_id": sid, "message": "x" * 2001}).status_code == 422
    assert client.post("/api/chat", json={"session_id": sid, "message": ""}).status_code == 422
    assert client.post("/api/chat", json={"session_id": sid, "message": 123}).status_code == 422
    assert client.post("/api/chat", json={"session_id": sid}).status_code == 422


def test_methods_not_allowed():
    assert client.get("/api/analyze").status_code == 405
    assert client.delete("/api/chat").status_code == 405
