"""Golden tests: every visible report is checked against the answer we expect from the lab's own rules."""
from pathlib import Path

import pytest

from app import config
from app.engine import analyze
from app.extract import parse_report
from app.knowledge import load_kb

DATA = config.DATA_DIR


@pytest.fixture(scope="module")
def kb():
    return load_kb(DATA)


def run(kb, filename):
    path = DATA / filename
    patient = parse_report(path.read_text(encoding="utf-8"), filename)
    return analyze(patient, kb, strict=True)


def statuses(result):
    return {f["test"]: f["status"] for f in result["results"]}


def test_knowledge_loaded(kb):
    assert len(kb.ranges) >= 11
    assert len(kb.urgent) == 4
    assert kb.canonical("SGPT") == "ALT" and kb.canonical("sgot") == "AST" and kb.canonical("FBS") == "Fasting Blood Sugar"


def test_p001_normal(kb):
    r = run(kb, "report_P001_Alice_Smith_CBC.md")
    assert statuses(r) == {"Hemoglobin": "normal", "White Blood Cell Count": "normal"}


def test_p002_alias_and_exact_limit_is_normal(kb):
    r = run(kb, "report_P002_Bob_Jones_Liver.md")
    assert r["patient"]["sex"] == "female"  # the name sounds male, the report says female: do not guess
    assert statuses(r) == {"ALT": "normal"}  # 45 is exactly the female upper limit


def test_p003_missing_age_and_sex_asks(kb):
    r = run(kb, "report_P003_Charlie_Brown_Sugar_NoDemo.md")
    f = r["results"][0]
    assert f["status"] == "needs_demographics" and set(f["ask"]) == {"age", "sex"}


def test_p004_urgent_hemoglobin_and_low_platelets(kb):
    r = run(kb, "report_P004_Diana_Prince_Hem_Urgent.md")
    assert statuses(r) == {"Hemoglobin": "urgent", "Platelet Count": "low"}
    assert "see a doctor today" in r["urgent_warning"].lower()


def test_p005_unit_conversion_shown(kb):
    r = run(kb, "report_P005_Ethan_Hunt_Sugar_UnitConv.md")
    f = r["results"][0]
    assert f["status"] == "high" and f["value_standard"] == 108 and "6 mmol/L x 18 = 108 mg/dL" in f["conversion"]


def test_p006_unknown_test_not_guessed(kb):
    r = run(kb, "report_P006_Fiona_UnknownTest.md")
    f = r["results"][0]
    assert f["status"] == "cannot_classify" and "cannot be classified from the files" in f["reason"]


def test_p007_thyroid_normal(kb):
    assert statuses(run(kb, "report_P007_George_Thyroid.md")) == {"TSH": "normal"}


def test_p008_urine(kb):
    assert statuses(run(kb, "report_P008_Haley_Urine.md")) == {"Urine pH": "normal", "Urine Protein": "normal"}


def test_p009_liver_high(kb):
    assert statuses(run(kb, "report_P009_Ian_Liver_High.md")) == {"ALT": "high", "AST": "high"}


def test_p010_cholesterol_exact_limit_is_normal(kb):
    assert statuses(run(kb, "report_P010_Julia_Cholesterol.md")) == {"Cholesterol": "normal"}


def test_p011_cbc(kb):
    assert statuses(run(kb, "report_P011_Kevin_CBC.md")) == {"White Blood Cell Count": "high", "Platelet Count": "low"}


def test_p012_missing_sex_asks_and_does_not_classify(kb):
    r = run(kb, "report_P012_Laura_AST_MissingSex.md")
    f = r["results"][0]
    assert f["status"] == "needs_demographics" and f["ask"] == ["sex"]


def test_p013_urgent_sugar(kb):
    r = run(kb, "report_P013_Michael_Sugar_Urgent.md")
    assert statuses(r) == {"Fasting Blood Sugar": "urgent"} and r["summary"]["urgent"]


def test_p014_aliases_multiple(kb):
    assert statuses(run(kb, "report_P014_Nancy_Multiple.md")) == {"Fasting Blood Sugar": "normal", "AST": "normal"}


def test_doctor_questions_between_3_and_5(kb):
    for path in sorted(DATA.glob("report_*.md")):
        r = run(kb, path.name)
        assert 3 <= len(r["questions_for_doctor"]) <= 5, path.name


def test_deterministic(kb):
    a = run(kb, "report_P009_Ian_Liver_High.md")
    b = run(kb, "report_P009_Ian_Liver_High.md")
    assert a == b
