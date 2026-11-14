"""PDF upload: a real text PDF works, scans and broken files get a clear message, never a crash."""
import os

os.environ["PROVIDER_ORDER"] = "none"

from fastapi.testclient import TestClient  # noqa: E402
from fpdf import FPDF  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def make_pdf(lines):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    for line in lines:
        pdf.cell(text=line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def upload(raw, name="report.pdf", mime="application/pdf"):
    return client.post("/api/analyze-file?use_ai=false", files={"file": (name, raw, mime)})


def test_text_pdf_is_read():
    raw = make_pdf(["CityLab Report", "Patient Name: Test Person", "Age: 42", "Sex: Female",
                    "Hemoglobin 6.5 g/dL 12.1 - 15.1 Low",
                    "Platelet Count: 120000 cells/mcL"])
    r = upload(raw)
    assert r.status_code == 200, r.text
    data = r.json()
    status = {f["test"]: f["status"] for f in data["results"]}
    assert status == {"Hemoglobin": "urgent", "Platelet Count": "low"}


def test_pdf_table_style_rows_with_range_and_flag_columns():
    raw = make_pdf(["Age: 30", "Sex: Male", "ALT 85 U/L 7 - 55 HIGH", "AST 40 U/L 8 - 48 Normal"])
    r = upload(raw)
    assert r.status_code == 200
    assert {f["test"]: f["status"] for f in r.json()["results"]} == {"ALT": "high", "AST": "normal"}


def test_pdf_without_text_is_explained_as_a_scan():
    pdf = FPDF()
    pdf.add_page()  # an empty page looks like a scan: no text layer
    r = upload(bytes(pdf.output()))
    assert r.status_code == 422 and "scan" in r.json()["detail"].lower()


def test_pdf_with_no_results_is_rejected_politely():
    r = upload(make_pdf(["Hello world", "Nothing here"]))
    assert r.status_code == 422


def test_broken_pdf_is_rejected_not_crashed():
    assert upload(b"%PDF-1.4 this is not really a pdf").status_code == 422


def test_empty_upload():
    assert upload(b"", "a.txt", "text/plain").status_code == 400


def test_binary_garbage_is_unsupported():
    assert upload(b"\xff\xfe\x00\x01\x02garbage", "a.bin", "application/octet-stream").status_code == 422


def test_oversize_upload_is_refused():
    assert upload(b"%PDF-" + b"0" * 12_100_000).status_code == 413


def test_text_upload_still_works():
    raw = b"* **Recorded Age**: 40\n* **Biological Sex**: Male\n- Hemoglobin: 15 g/dL\n"
    r = upload(raw, "r.md", "text/markdown")
    assert r.status_code == 200 and r.json()["results"][0]["status"] == "normal"
