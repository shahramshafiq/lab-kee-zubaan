"""Every kind of upload, and the awkward report lines from the team's edge-case pack."""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEAD = "* **Recorded Age**: 40\n* **Biological Sex**: Male\n"


def up(raw: bytes, name: str, language: str = "en"):
    return client.post("/api/analyze-file", files={"file": (name, raw)}, params={"language": language, "use_ai": "false"})


def analyse(text: str):
    r = client.post("/api/analyze", json={"report_text": text, "use_ai": False})
    assert r.status_code == 200, r.text
    return r.json()


def statuses(data):
    return [(f["test"], f["status"]) for f in data["results"]]


# ---------- formats ----------
def make_docx(paragraphs, table_rows=()):
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    if table_rows:
        rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in r) + "</w:tr>"
                       for r in table_rows)
        body += f"<w:tbl>{rows}</w:tbl>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<w:document {ns}><w:body>{body}</w:body></w:document>')
        z.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


def test_word_file_with_a_table():
    raw = make_docx(["Age: 40", "Sex: Male"], [["Test", "Result", "Unit"], ["Hemoglobin", "15", "g/dL"], ["ALT", "30", "U/L"]])
    r = up(raw, "report.docx")
    assert r.status_code == 200
    assert dict(statuses(r.json())) == {"Hemoglobin": "normal", "ALT": "normal"}


def test_csv_with_other_column_order():
    raw = b"Test,Method,Result,Unit,Range\nHemoglobin,Auto,15,g/dL,13.8-17.2\nALT,UV,30,U/L,7-55\n"
    r = up(HEAD.encode() + b"\n" + raw, "r.csv")
    assert r.status_code == 200
    assert dict(statuses(r.json())) == {"Hemoglobin": "normal", "ALT": "normal"}


def test_html_table():
    html = ("<html><body><p>Age: 40</p><p>Sex: Male</p><table><tr><th>Test</th><th>Result</th><th>Unit</th></tr>"
            "<tr><td>Hemoglobin</td><td>15</td><td>g/dL</td></tr></table></body></html>").encode()
    r = up(html, "r.html")
    assert r.status_code == 200 and statuses(r.json()) == [("Hemoglobin", "normal")]


def test_xlsx():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in (["Age", 40], ["Sex", "Male"], ["Test", "Result", "Unit"], ["Hemoglobin", 15, "g/dL"]):
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    r = up(buf.getvalue(), "r.xlsx")
    assert r.status_code == 200 and statuses(r.json()) == [("Hemoglobin", "normal")]


def test_utf16_and_bom_and_crlf_text():
    text = (HEAD + "Hemoglobin: 15 g/dL\n").replace("\n", "\r\n")
    assert up(b"\xef\xbb\xbf" + text.encode(), "a.txt").status_code == 200
    assert up(text.encode("utf-16"), "a.txt").status_code == 200


def test_old_word_and_unknown_zip_get_plain_messages():
    assert up(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 50, "a.doc").status_code == 422
    assert up(b"PK\x03\x04" + b"0" * 50, "a.zip").status_code == 422


def test_picture_of_a_report_is_read_by_ocr():
    PIL = pytest.importorskip("PIL.Image")
    pytest.importorskip("rapidocr_onnxruntime")
    from PIL import ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except OSError:
        pytest.skip("no font to draw the test picture")
    img = PIL.new("RGB", (900, 360), "white")
    d = ImageDraw.Draw(img)
    for i, line in enumerate(["Age: 40", "Sex: Male", "Hemoglobin   15   g/dL", "ALT   30   U/L"]):
        d.text((30, 20 + i * 70), line, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    r = up(buf.getvalue(), "photo.png")
    assert r.status_code == 200, r.text
    assert dict(statuses(r.json())).get("Hemoglobin") == "normal"


# ---------- awkward lines (the team's pack) ----------
def test_thousands_comma_still_triggers_the_danger_limit():
    d = analyse(HEAD + "ALT: 1,200 U/L\nPlatelet Count: 45,000 cells/mcL")
    assert dict(statuses(d)) == {"ALT": "urgent", "Platelet Count": "urgent"}
    assert d["urgent_warning"]


def test_decimal_comma_is_flagged_not_guessed():
    d = analyse(HEAD + "Hemoglobin: 1,2 g/dL")
    assert statuses(d) == [("Hemoglobin", "cannot_classify")]
    assert "comma" in d["results"][0]["reason"]


@pytest.mark.parametrize("value", ["Pending", "N/A", "Hemolyzed sample - result unavailable", "-4.1 g/dL"])
def test_unreadable_values_are_listed_as_cannot_classify(value):
    d = analyse(HEAD + f"Hemoglobin: {value}")
    assert statuses(d) == [("Hemoglobin", "cannot_classify")]


def test_blank_result_line_is_listed():
    d = analyse(HEAD + "Hemoglobin: 15 g/dL\nPlatelet Count:\n")
    assert ("Platelet Count", "cannot_classify") in statuses(d)


def test_scientific_notation_and_per_cumm():
    d = analyse(HEAD + "WBC: 7.5E3 /uL\nWhite Blood Cell Count: 7500 /cumm")
    assert [s for _, s in statuses(d)] == ["normal"]  # the same value twice, shown once


def test_specimen_details_are_never_results():
    text = ("## SECTION II: SPECIMEN DETAILS\n* Fasting duration: 12 hours\n* Tube count: 3\n"
            "## SECTION III: ANALYTICAL RESULTS\n")
    r = client.post("/api/analyze", json={"report_text": HEAD + text, "use_ai": False})
    assert r.status_code == 422


def test_names_in_other_word_order_match_the_lab_sheet():
    d = analyse(HEAD + "Glucose (Fasting): 95 mg/dL\nCholesterol, Total: 180 mg/dL")
    assert ("Fasting Blood Sugar", "normal") in statuses(d) and ("Cholesterol", "normal") in statuses(d)
    assert statuses(analyse(HEAD + "Fasting Blood Sugar (FBS): 90 mg/dL")) == [("Fasting Blood Sugar", "normal")]
    # a different cholesterol is NOT total cholesterol
    d = analyse(HEAD + "Cholesterol (HDL): 55 mg/dL")
    assert statuses(d) == [("Cholesterol (HDL)", "cannot_classify")]


def test_same_test_with_two_values_is_a_conflict():
    d = analyse(HEAD + "Hemoglobin: 11.5 g/dL\nHb: 12.9 g/dL")
    assert [s for _, s in statuses(d)] == ["cannot_classify", "cannot_classify"]
    assert "more than once" in d["results"][0]["reason"]


def test_trace_in_urine_is_not_guessed():
    d = analyse(HEAD + "Urine Protein: Trace")
    assert statuses(d) == [("Urine Protein", "cannot_classify")]


def test_name_and_record_number_do_not_leave_the_server():
    d = analyse("* **Patient Full Name**: Test Person\n* **Medical Record Number (MRN)**: CLD-X-0001\n" + HEAD + "Hemoglobin: 15 g/dL")
    assert "name" not in d["patient"] and "mrn" not in d["patient"]
    assert "Test Person" not in str(d) and "CLD-X-0001" not in str(d)


# ---------- the patient can give the range printed on their own report ----------
def test_user_range_for_a_test_without_a_range():
    d = analyse(HEAD + "Ferritin: 20 ng/mL")
    assert d["results"][0]["can_provide_range"] and d["results"][0]["next_step"]
    sid = d["session_id"]
    r = client.post("/api/user-range", json={"session_id": sid, "test": "Ferritin", "low": 15, "high": 150})
    assert r.status_code == 200
    f = r.json()["results"][0]
    assert f["status"] == "normal" and f["user_range"] and "typed" in f["range_used"]["source"]
    bad = client.post("/api/user-range", json={"session_id": sid, "test": "Ferritin", "low": 150, "high": 15})
    assert bad.status_code == 422


# ---------- chat ----------
def chat(sid, message, language="en"):
    return client.post("/api/chat", json={"session_id": sid, "message": message, "language": language}).json()


def test_other_people_questions_are_refused_in_the_users_language():
    sid = analyse(HEAD + "Hemoglobin: 15 g/dL")["session_id"]
    for q in ("My husband's report is on the same system, compare us", "Who in the lab has high sugar?"):
        assert chat(sid, q)["refused"] is True
    ur = chat(sid, "Who in the lab has high sugar?", "ur")["answer"]
    assert "مریض" in ur and "I can only" not in ur
    ru = chat(sid, "Do I have diabetes?", "roman_urdu")["answer"]
    assert "doctor" in ru and "I cannot" not in ru


def test_alias_question_is_answered_from_the_glossary():
    sid = analyse(HEAD + "Hemoglobin: 15 g/dL")["session_id"]
    a = chat(sid, "What does SGPT mean?")
    assert "ALT" in a["answer"] and a["source"] == "rules"


# ---------- more cases from the second round of testing ----------
@pytest.mark.parametrize("line", [
    "Hemoglobin (Hb): 6.5 g/dL", "Platelet Count (PLT): 45000 cells/mcL", "ALT (SGPT): 1200 U/L",
    "Fasting Blood Sugar (FBS): 350 mg/dL",
    "Hemoglobin: 6.5 g/dL (L)", "Hemoglobin: 6.5 g/dL [13.8-17.2]", "Hemoglobin: 6.5 g/dL CRITICAL",
    "Hemoglobin: 6.5 g/dL 13.8 - 17.2 L", "| Hemoglobin | 6.5 | g/dL | 13.8-17.2 | CRITICAL |",
    "Platelets: <10 cells/mcL", "ALT: >1000 U/L",
])
def test_danger_is_found_whatever_the_line_looks_like(line):
    d = analyse(HEAD + line)
    assert d["results"][0]["status"] == "urgent" and d["urgent_warning"], line


def test_flags_in_the_report_are_never_trusted():
    d = analyse(HEAD + "Hemoglobin: 15 g/dL (H)\nALT: 30 U/L CRITICAL")
    assert [f["status"] for f in d["results"]] == ["normal", "normal"]


def test_wrong_direction_comparator_is_not_called_urgent():
    d = analyse(HEAD + "Hemoglobin: >5 g/dL")  # could be anything above 5
    assert d["results"][0]["status"] == "cannot_classify"


@pytest.mark.parametrize("age", ["18 months", "3 weeks", "10 days", "2 years"])
def test_a_baby_is_never_given_the_adult_range(age):
    d = analyse(f"* **Recorded Age**: {age}\n* **Biological Sex**: Male\nHemoglobin: 15 g/dL")
    assert d["results"][0]["status"] == "cannot_classify"


def test_ocr_text_without_spaces_is_split():
    from app.readfile import _respace
    assert _respace("Hemoglobin15g/dL") == "Hemoglobin 15 g/dL"
    assert _respace("Platelets<10cells/mcL") == "Platelets <10 cells/mcL"
    assert _respace("Vitamin B12 350 pg/mL") == "Vitamin B12 350 pg/mL"
