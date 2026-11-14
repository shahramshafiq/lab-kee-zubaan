"""Turns an uploaded file of any kind into plain text lines that the report reader understands.

Supported: PDF (text, tables, and scanned pages through OCR), Word (.docx, with tables), Excel (.xlsx), CSV/TSV,
web pages (.html), RTF, plain text and markdown, and photos or scans (png, jpg, webp, bmp, tiff) through OCR.
OCR runs on this computer (rapidocr), so the picture is never sent to an outside service.
Tables always come out as '| cell | cell | cell |' lines, which is the one table layout the reader knows.
Several readings can be offered for one file (for example a PDF as plain text, then as laid-out text, then by OCR);
the caller keeps the first one in which test results are found.
"""
import csv
import html
import io
import logging
import re
import zipfile
from html.parser import HTMLParser
from typing import Iterator, List

log = logging.getLogger(__name__)

MAX_PAGES = 80            # long reports are fine, this only stops absurd files
MAX_OCR_IMAGES = 12       # scanned pages read by OCR (each takes a second or two)
MAX_UNZIPPED = 30_000_000  # protection against zip bombs in .docx and .xlsx
IMAGE_TYPES = {b"\x89PNG": "png", b"\xff\xd8\xff": "jpg", b"BM": "bmp", b"II*\x00": "tif", b"MM\x00*": "tif"}


class FileProblem(Exception):
    """The message is safe to show to the user."""


def kind_of(raw: bytes, filename: str) -> str:
    """pdf, docx, xlsx, image, html, rtf, csv, doc (old Word, not supported) or text."""
    name = (filename or "").lower()
    if raw[:5] == b"%PDF-":
        return "pdf"
    if raw[:4] == b"PK\x03\x04":
        if name.endswith(".xlsx") or name.endswith(".xlsm"):
            return "xlsx"
        if name.endswith(".docx") or name.endswith(".docm"):
            return "docx"
        try:
            names = zipfile.ZipFile(io.BytesIO(raw)).namelist()
        except Exception:
            return "text"
        return "docx" if "word/document.xml" in names else "xlsx" if "xl/workbook.xml" in names else "zip"
    if raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "doc"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image"
    for magic in IMAGE_TYPES:
        if raw.startswith(magic):
            return "image"
    head = raw[:600].lstrip().lower()
    if raw[:5] == b"{\\rtf":
        return "rtf"
    if name.endswith((".html", ".htm")) or head.startswith((b"<!doctype html", b"<html")):
        return "html"
    if name.endswith((".csv", ".tsv")):
        return "csv"
    return "text"


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16"):
        if encoding == "utf-16" and raw[:2] not in (b"\xff\xfe", b"\xfe\xff"):
            continue
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    try:
        text = raw.decode("cp1252")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    if text.count("\x00") > len(text) // 4:
        raise FileProblem("This file is not a readable report. Please upload a PDF, Word file, picture or text file.")
    return text


def row(cells: List[str]) -> str:
    cells = [re.sub(r"\s+", " ", c).strip() for c in cells]
    filled = [c for c in cells if c]
    if len(filled) == 1:
        return filled[0]                  # a plain line (for example a title or 'Age: 40')
    if len(filled) == 2:
        return f"{filled[0]}: {filled[1]}"  # 'Age | 40' is the same as 'Age: 40'
    return "| " + " | ".join(cells) + " |" if filled else ""


# ---------------------------------------------------------------- Word
def docx_to_text(raw: bytes) -> str:
    import xml.etree.ElementTree as ET
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                raise FileProblem("This Word file is too large to read.")
            root = ET.fromstring(z.read("word/document.xml"))
    except FileProblem:
        raise
    except Exception as exc:
        log.warning("Could not open the Word file: %s", type(exc).__name__)
        raise FileProblem("I could not open this Word file. Please save it as .docx or PDF and try again.")

    def para(p) -> str:
        out = []
        for node in p.iter():
            if node.tag == ns + "t" and node.text:
                out.append(node.text)
            elif node.tag in (ns + "tab",):
                out.append("  ")
            elif node.tag in (ns + "br", ns + "cr"):
                out.append("\n")
        return "".join(out)

    lines: List[str] = []
    body = root.find(ns + "body")
    for child in (body if body is not None else []):
        if child.tag == ns + "p":
            lines.append(para(child))
        elif child.tag == ns + "tbl":
            for tr in child.iter(ns + "tr"):
                cells = []
                for tc in tr.findall(ns + "tc"):
                    cells.append(" ".join(para(p) for p in tc.iter(ns + "p")).strip())
                lines.append(row(cells))
    return "\n".join(lines)


# ---------------------------------------------------------------- Excel, CSV
def xlsx_to_text(raw: bytes) -> str:
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:
        log.warning("Could not open the Excel file: %s", type(exc).__name__)
        raise FileProblem("I could not open this Excel file. Please save it as .xlsx or CSV and try again.")
    lines: List[str] = []
    for sheet in wb.worksheets[:10]:
        for values in sheet.iter_rows(values_only=True, max_row=3000):
            cells = ["" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)) for v in values]
            lines.append(row(cells))
    return "\n".join(lines)


def csv_to_text(raw: bytes) -> str:
    text = decode_text(raw)
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    lines = [row(cells) for cells in csv.reader(io.StringIO(text), dialect)]
    return "\n".join(l for l in lines if l)


# ---------------------------------------------------------------- web page, RTF
class _Html(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header", "footer", "pre"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: List[str] = []
        self.buf: List[str] = []
        self.cells: List[str] = []
        self.in_row = False
        self.skip = 0

    def _flush(self):
        text = "".join(self.buf).strip()
        if text:
            self.lines.append(text)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.skip += 1
        elif tag == "tr":
            self._flush(); self.in_row = True; self.cells = []
        elif tag in ("td", "th"):
            self.buf = []
        elif tag in self.BLOCK and not self.in_row:
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th"):
            self.cells.append("".join(self.buf)); self.buf = []
        elif tag == "tr":
            self.lines.append(row(self.cells)); self.in_row = False; self.cells = []
        elif tag in self.BLOCK and not self.in_row:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def html_to_text(raw: bytes) -> str:
    parser = _Html()
    parser.feed(decode_text(raw))
    parser._flush()
    return "\n".join(l for l in parser.lines if l)


def rtf_to_text(raw: bytes) -> str:
    text = raw.decode("latin-1")
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", "replace"), text)
    text = re.sub(r"\\(par|line|row)\b ?", "\n", text)
    text = re.sub(r"\\(tab|cell)\b ?", "  ", text)
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = re.sub(r"[{}]", "", text)
    return html.unescape(text)


# ---------------------------------------------------------------- OCR (pictures and scanned pages)
_ocr = None


def _engine():
    global _ocr
    if _ocr is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr = RapidOCR()
        except Exception as exc:
            log.warning("OCR is not available: %s", type(exc).__name__)
            raise FileProblem("Reading pictures is not available on this server. Please upload a PDF, Word or text file.")
    return _ocr


def ocr_lines(boxes) -> str:
    """Boxes of recognised text -> text lines. Boxes on the same height are one line (so a table row stays together)."""
    items = []
    for box, text, _score in boxes or []:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append({"x": min(xs), "top": min(ys), "mid": sum(ys) / 4, "h": max(ys) - min(ys), "text": str(text).strip()})
    items = [i for i in items if i["text"]]
    if not items:
        return ""
    items.sort(key=lambda i: i["mid"])
    rows, current = [], [items[0]]
    for it in items[1:]:
        ref = sum(c["mid"] for c in current) / len(current)
        if abs(it["mid"] - ref) <= max(6, 0.55 * max(c["h"] for c in current)):
            current.append(it)
        else:
            rows.append(current)
            current = [it]
    rows.append(current)
    out = []
    for r in rows:
        r.sort(key=lambda i: i["x"])
        out.append("| " + " | ".join(i["text"] for i in r) + " |" if len(r) >= 3 else "   ".join(i["text"] for i in r))
    return "\n".join(out)


def image_to_text(data: bytes) -> str:
    try:
        import numpy as np
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception as exc:
        log.warning("Could not open the picture: %s", type(exc).__name__)
        raise FileProblem("I could not open this picture. Please try a PNG or JPG, or upload the report as a PDF.")
    longest = max(img.size)
    if longest > 2400:  # big phone photos: smaller is faster and just as readable
        scale = 2400 / longest
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    elif longest < 900:  # tiny screenshots: bigger reads better
        scale = 1400 / longest
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    result, _elapsed = _engine()(np.array(img)[:, :, ::-1])
    text = ocr_lines(result)
    if not text:
        raise FileProblem("I could not read any text in this picture. Please try a clearer, straight-on photo.")
    return text


# ---------------------------------------------------------------- PDF
def _pdf_reader(raw: bytes):
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as exc:
        log.warning("Could not open PDF: %s", type(exc).__name__)
        raise FileProblem("I could not open this PDF. Please upload a different PDF, a picture or a text report.")
    if reader.is_encrypted:
        try:
            ok = reader.decrypt("")
        except Exception:
            ok = False
        if not ok:
            raise FileProblem("This PDF is password protected. Please upload an unlocked copy.")
    return reader


def pdf_readings(raw: bytes) -> Iterator[str]:
    reader = _pdf_reader(raw)
    pages = list(reader.pages)[:MAX_PAGES]
    plain = []
    try:
        for page in pages:
            plain.append(page.extract_text() or "")
    except Exception as exc:
        log.warning("Could not read PDF text: %s", type(exc).__name__)
    text = "\n".join(plain).strip()
    if text:
        yield text
        try:  # same text with the table columns kept apart
            laid = "\n".join((p.extract_text(extraction_mode="layout") or "") for p in pages).strip()
            if laid and laid != text:
                yield laid
        except Exception:
            log.info("Layout reading of the PDF skipped")
    # scanned pages (or a text layer that holds no results): read the pictures inside the pages
    found = []
    try:
        for page in pages:
            for image in page.images:
                found.append(image.data)
                if len(found) >= MAX_OCR_IMAGES:
                    break
            if len(found) >= MAX_OCR_IMAGES:
                break
    except Exception as exc:
        log.info("No pictures in the PDF pages: %s", type(exc).__name__)
    pieces = []
    for data in found:
        try:
            pieces.append(image_to_text(data))
        except FileProblem:
            continue
    if pieces:
        yield "\n".join(pieces)
    elif not text:
        raise FileProblem("This PDF has no text and no readable pictures. Please upload a clearer scan, a photo or a text report.")


# ---------------------------------------------------------------- the one entry point
def readings(raw: bytes, filename: str) -> Iterator[str]:
    """Yield one or more text readings of the file, best first."""
    kind = kind_of(raw, filename)
    if kind == "pdf":
        yield from pdf_readings(raw)
    elif kind == "docx":
        yield docx_to_text(raw)
    elif kind == "xlsx":
        yield xlsx_to_text(raw)
    elif kind == "csv":
        yield csv_to_text(raw)
        yield decode_text(raw)
    elif kind == "html":
        yield html_to_text(raw)
    elif kind == "rtf":
        yield rtf_to_text(raw)
    elif kind == "image":
        yield image_to_text(raw)
    elif kind == "doc":
        raise FileProblem("Old Word files (.doc) cannot be read. Please save it as .docx or PDF and upload again.")
    elif kind == "zip":
        raise FileProblem("This file type is not supported. Please upload a PDF, Word, Excel, picture or text file.")
    else:
        yield decode_text(raw)
