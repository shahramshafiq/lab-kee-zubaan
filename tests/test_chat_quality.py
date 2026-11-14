"""Chat answers must be plain text, factually named, and never hand out a wrong full name."""
import json

import pytest
from fastapi.testclient import TestClient

from app import chat, config
from app.chat import plain_text
from app.engine import analyze
from app.explain import _facts, check_answer, check_text
from app.extract import parse_report
from app.knowledge import load_kb
from app.main import app

client = TestClient(app)
KB = load_kb(config.DATA_DIR)


def p009():
    return analyze(parse_report((config.DATA_DIR / "report_P009_Ian_Liver_High.md").read_text(encoding="utf-8")), KB)


def test_markdown_is_removed():
    raw = "**ALT - 85 U/L** (normal 7‑55):\n\n* higher than normal\n- a liver enzyme\n1. ask your doctor\n## Heading"
    out = plain_text(raw)
    assert "*" not in out and "#" not in out and "‑" not in out
    assert "higher than normal" in out and "ask your doctor" in out and out.count("\n\n") == 0


def test_dashes_become_plain():
    assert plain_text("7‑55 and 8–48") == "7-55 and 8-48"


def test_facts_include_the_full_names_from_the_glossary():
    names = {f["test"]: f["full_name"] for f in _facts(p009())}
    assert names == {"ALT": "Alanine Aminotransferase", "AST": "Aspartate Aminotransferase"}


@pytest.mark.parametrize("wrong", [
    "AST (alanine aminotransferase) is an enzyme",
    "ALT stands for aspartate aminotransferase",
    "alanine aminotransferase, also called AST",
])
def test_wrong_full_names_are_rejected(wrong):
    assert check_answer(wrong, p009()) == "wrong full name for ALT or AST"


@pytest.mark.parametrize("right", [
    "ALT (alanine aminotransferase) is an enzyme in the liver.",
    "AST is aspartate aminotransferase. ALT is alanine aminotransferase.",
])
def test_right_full_names_pass(right):
    assert check_answer(right, p009()) is None


def test_a_wrong_name_from_the_ai_is_replaced_by_the_safe_answer(monkeypatch):
    sid = client.post("/api/analyze", json={"report_id": "P009", "use_ai": False}).json()["session_id"]
    monkeypatch.setattr(chat.llm, "ask", lambda s, u, fast=False: "AST (alanine aminotransferase) is an enzyme.")
    r = client.post("/api/chat", json={"session_id": sid, "message": "what is AST?"}).json()
    assert "alanine" not in r["answer"].lower() and r["source"] == "rules"


def test_ai_markdown_never_reaches_the_page(monkeypatch):
    sid = client.post("/api/analyze", json={"report_id": "P009", "use_ai": False}).json()["session_id"]
    monkeypatch.setattr(chat.llm, "ask", lambda s, u, fast=False: "**AST** is an enzyme.\n\n- found in the liver\n- and muscles")
    r = client.post("/api/chat", json={"session_id": sid, "message": "what is AST?"}).json()
    assert "*" not in r["answer"] and "- " not in r["answer"] and "AST is an enzyme" in r["answer"]
