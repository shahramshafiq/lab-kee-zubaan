"""The AI writer is checked, never trusted. These tests use a fake model so they run offline."""
import json

import pytest

from app import config, llm
from app.engine import analyze
from app.explain import check_text, deidentify, explain
from app.extract import parse_report
from app.knowledge import load_kb

DATA = config.DATA_DIR


@pytest.fixture(scope="module")
def p004():
    kb = load_kb(DATA)
    text = (DATA / "report_P004_Diana_Prince_Hem_Urgent.md").read_text(encoding="utf-8")
    return analyze(parse_report(text), kb, strict=True)


def good_answer():
    return json.dumps({
        "summary": "Your hemoglobin is very low at 6.5 g/dL. Please see a doctor today. Only a doctor can diagnose.",
        "tests": {"Hemoglobin": "Hemoglobin carries oxygen. 6.5 g/dL is below the safe limit.",
                  "Platelet Count": "Platelets help blood clot. 120000 is a bit low."},
        "questions": ["What should I do today?", "Do I need more tests?", "Why is it low?"],
    })


def test_good_text_is_used(p004):
    out = explain(p004, asker=lambda s, u: good_answer())
    assert out["explanation"]["source"] == "ai"


def test_invented_number_is_rejected(p004):
    bad = json.loads(good_answer())
    bad["summary"] = "Your hemoglobin is 9.9 g/dL. Please see a doctor today."
    assert check_text(bad, p004) is not None
    out = explain(p004, asker=lambda s, u: json.dumps(bad))
    assert out["explanation"]["source"] == "rules"


def test_number_written_another_way_is_fine(p004):
    ok = json.loads(good_answer())
    ok["tests"]["Platelet Count"] = "Platelets are low: 120,000 (about 120 thousand), the normal start is 150,000."
    assert check_text(ok, p004) is None


def test_diagnosis_is_rejected(p004):
    bad = json.loads(good_answer())
    bad["tests"]["Hemoglobin"] = "You have anemia."
    assert check_text(bad, p004) == "sounds like a diagnosis"


def test_harmless_you_have_is_allowed_but_disease_claims_are_not(p004):
    ok = json.loads(good_answer())
    ok["summary"] = "You have a low platelet count at 120000. Low hemoglobin can mean anemia. See a doctor today."
    assert check_text(ok, p004) is None  # naming a possible cause in general is fine
    for bad_text in ("You may have anemia.", "Aap ko diabetes hai.", "He is suffering from jaundice.",
                     "آپ کو یرقان ہے"):
        bad = json.loads(good_answer())
        bad["tests"]["Hemoglobin"] = bad_text
        assert check_text(bad, p004) == "sounds like a diagnosis", bad_text


def test_missing_urgent_warning_is_rejected(p004):
    bad = json.loads(good_answer())
    bad["summary"] = "Everything looks fine."
    assert check_text(bad, p004) == "urgent result without a doctor warning"


def test_ai_down_falls_back_to_rules(p004):
    def broken(system, user):
        raise llm.LLMUnavailable("down")

    out = explain(p004, asker=broken)
    assert out["explanation"]["source"] == "rules" and "see a doctor today" in out["explanation"]["summary"].lower()


def test_garbage_json_falls_back(p004):
    out = explain(p004, asker=lambda s, u: "sorry I cannot help")
    assert out["explanation"]["source"] == "rules"


def test_name_and_mrn_never_reach_the_model(p004):
    safe = deidentify(p004)
    blob = json.dumps(safe)
    assert "Diana" not in blob and "CLD-P004" not in blob
