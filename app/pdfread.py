"""Text from a PDF report. Scanned (image only) PDFs have no text, we say so instead of guessing."""
import io
import logging

log = logging.getLogger(__name__)

MAX_PAGES = 20


class PdfProblem(Exception):
    """The message is safe to show to the user."""


def pdf_to_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
    except Exception as exc:
        log.warning("Could not open PDF: %s", type(exc).__name__)
        raise PdfProblem("I could not open this PDF. Please upload a text or markdown report, or a different PDF.")
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                raise PdfProblem("This PDF is password protected. Please upload an unlocked copy.")
        except PdfProblem:
            raise
        except Exception:
            raise PdfProblem("This PDF is password protected. Please upload an unlocked copy.")
    parts = []
    try:
        for page in list(reader.pages)[:MAX_PAGES]:
            parts.append(page.extract_text() or "")
    except Exception as exc:
        log.warning("Could not read PDF text: %s", type(exc).__name__)
        raise PdfProblem("I could not read the text in this PDF.")
    text = "\n".join(parts).strip()
    if not text:
        raise PdfProblem("This PDF looks like a scan or a photo, so there is no text to read. "
                         "Please upload a text report for now (scanned reports need OCR, which is not added yet).")
    return text
