"""Random and brute-force checks: the engine must never crash, and must agree with a plain re-implementation."""
import json
import random
from decimal import Decimal

import pytest

from app import config
from app.engine import analyze
from app.extract import parse_report
from app.knowledge import load_kb

KB = load_kb(config.DATA_DIR)

TOKENS = [
    "Hemoglobin", "Hb", "ALT", "SGPT", "SGOT", "FBS", "TSH", "Protein", "pH Level", "Platelet Count", "WBC",
    "Cholesterol", "AST", "Ferritin", "Creatinine", ":", "->", "|", "=", "g/dL", "mg/dL", "mmol/L", "U/L", "10^9/L",
    "cells/mcL", "13.5", "0", "-1", "1e5", "99999999999999999999", "0.0000001", "NaN", "inf", "<5", ">100",
    "Negative", "1+", "\x00", "‮", "\U0001F600", "Age", "Sex", "Male", "Female", "M", "F", "42", "7", "300",
    "[DATA CORRUPTED]", "\n", "\n", "\t", "**", "#", "### APPENDIX 1", "Test", "Result", "Value Recorded", "---", "|---|",
    "التحليل", "ہیموگلوبن", "Biological Sex", "Recorded Age",
]


@pytest.mark.parametrize("seed", range(400))
def test_random_text_never_crashes_and_stays_serialisable(seed):
    rnd = random.Random(seed)
    text = "".join(rnd.choice(TOKENS) + rnd.choice([" ", " ", "", "\n", ": "]) for _ in range(rnd.randint(1, 60)))
    for strict in (True, False):
        result = analyze(parse_report(text), KB, strict=strict)
        json.dumps(result)  # must be plain data
        for f in result["results"]:
            assert f["status"] in ("normal", "low", "high", "urgent", "cannot_classify", "needs_demographics")
        assert 3 <= len(result["questions_for_doctor"]) <= 5


def expected_status(rule, value):
    """A plain version of the rule: exactly on a limit is normal."""
    if rule.qualitative is not None:
        return None
    if value < rule.low:
        return "low"
    if value > rule.high:
        return "high"
    return "normal"


def urgent_hit(test, value):
    for u in KB.urgent:
        if u.test == test:
            if (u.trigger == "less" and value <= u.threshold) or (u.trigger == "greater" and value >= u.threshold):
                return True
    return False


def test_engine_agrees_with_a_plain_reimplementation_on_every_limit():
    checked = 0
    for rule in KB.ranges:
        if rule.qualitative is not None:
            continue
        sexes = ["male", "female"] if rule.sex == "all" else [rule.sex]
        for sex in sexes:
            for age in (rule.age_min, (rule.age_min + rule.age_max) // 2, rule.age_max):
                for delta in (Decimal("-0.01"), Decimal("0"), Decimal("0.01")):
                    for limit in (rule.low, rule.high):
                        value = limit + delta
                        text = (f"* **Recorded Age**: {age}\n* **Biological Sex**: {sex}\n"
                                f"{rule.test}: {value} {rule.unit}\n")
                        f = analyze(parse_report(text), KB, strict=True)["results"][0]
                        want = "urgent" if urgent_hit(rule.test, value) else expected_status(rule, value)
                        assert f["status"] == want, (rule.test, sex, age, str(value), f["status"], want)
                        checked += 1
    assert checked > 150


def test_ages_outside_every_range_are_never_guessed():
    for age in (0, 1, 17, 101, 150):
        text = f"* **Recorded Age**: {age}\n* **Biological Sex**: Male\nHemoglobin: 15 g/dL\n"
        assert analyze(parse_report(text), KB, strict=True)["results"][0]["status"] == "cannot_classify"


def test_same_report_in_every_layout_gives_the_same_statuses():
    layouts = [
        "- Hemoglobin: 15 g/dL\n- ALT: 85 U/L\n",
        "* **Hemoglobin**: 15 g/dL\n* **ALT**: 85 U/L\n",
        "| Test | Result | Unit |\n| :--- | :--- | :--- |\n| Hemoglobin | 15 | g/dL |\n| ALT | 85 | U/L |\n",
        "Hemoglobin -> 15 g/dL\nALT -> 85 U/L\n",
        "Test: Hemoglobin\nResult: 15 g/dL\nTest: ALT\nResult: 85 U/L\n",
        "Hemoglobin 15 g/dL\nALT 85 U/L\n",
    ]
    head = "* **Recorded Age**: 40\n* **Biological Sex**: Male\n"
    seen = {tuple((f["test"], f["status"]) for f in analyze(parse_report(head + body), KB)["results"])
            for body in layouts}
    assert seen == {(("Hemoglobin", "normal"), ("ALT", "high"))}
