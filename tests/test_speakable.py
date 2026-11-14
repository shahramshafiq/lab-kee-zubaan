"""Numbers and units are spoken as words (this was a user complaint: '12,000' must not sound like digits)."""
import pytest

from app.speakable import to_speech, urdu_number


@pytest.mark.parametrize("written,spoken", [
    ("12,000", "twelve thousand"), ("14000", "fourteen thousand"), ("85", "eighty-five"),
    ("6.5", "six point five"), ("150000", "one hundred and fifty thousand"), ("0", "zero"),
])
def test_english_numbers(written, spoken):
    assert to_speech(written) == spoken


def test_english_units_and_names():
    assert to_speech("WBC 12,000 cells/mcL") == "W B C twelve thousand cells per microliter"
    assert to_speech("ALT is 85 U/L.") == "A L T is eighty-five units per liter."
    assert to_speech("5.2 mmol/L") == "five point two millimoles per liter"
    assert to_speech("108 mg/dL") == "one hundred and eight milligrams per deciliter"
    assert to_speech("13.8 g/dL") == "thirteen point eight grams per deciliter"


def test_ranges_are_said_with_to():
    assert to_speech("normal 7 - 55 U/L") == "normal seven to fifty-five units per liter"
    assert to_speech("4500-11000") == "four thousand, five hundred to eleven thousand"


def test_no_digits_or_slashes_left_in_a_spoken_report_sentence():
    text = "Hemoglobin 6.5 g/dL, platelets 120,000 cells/mcL, sugar 6.0 mmol/L, TSH 2.5 mIU/L."
    spoken = to_speech(text)
    assert not any(c.isdigit() for c in spoken) and "/" not in spoken


@pytest.mark.parametrize("n,words", [
    (0, "صفر"), (14, "چودہ"), (45, "پینتالیس"), (85, "پچاسی"), (99, "ننانوے"), (100, "ایک سو"),
    (101, "ایک سو ایک"), (12000, "بارہ ہزار"), (14000, "چودہ ہزار"), (150000, "ایک لاکھ پچاس ہزار"),
    (2500000, "پچیس لاکھ"),
])
def test_urdu_numbers(n, words):
    assert urdu_number(n) == words


def test_urdu_sentence():
    out = to_speech("سفید خلیات 14000 cells/mcL، ALT 85 U/L اور 6.5 g/dL", "ur")
    assert "چودہ ہزار" in out and "اے ایل ٹی" in out and "پچاسی" in out and "چھ اعشاریہ پانچ" in out
    assert not any(c.isdigit() for c in out)


def test_roman_urdu_uses_the_english_rules():
    assert to_speech("ALT 85 U/L hai", "roman_urdu") == "A L T eighty-five units per liter hai"


def test_huge_and_odd_numbers_do_not_crash():
    assert to_speech("99999999999999999999") == "99999999999999999999"
    assert to_speech("1.2.3 and -5 and 3e5") != ""
    assert to_speech("") == ""


def test_chat_reply_carries_a_spoken_version():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    sid = client.post("/api/analyze", json={"report_id": "P011", "use_ai": False}).json()["session_id"]
    r = client.post("/api/chat", json={"session_id": sid, "message": "is my white blood cell count normal?"}).json()
    assert "spoken" in r and not any(c.isdigit() for c in r["spoken"])
