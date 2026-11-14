"""Turns a lab report (text) into a patient record and a list of raw results.

Reports are noisy: the real data is a few lines, followed by pages of legal filler. We cut the filler
and read the result lines with tolerant patterns, because the same report can show results as a table,
bullets, 'Test: X / Result: Y', 'name -> value', 'name = value' or just 'Hemoglobin 13.5 g/dL'.
Test names are cleaned because they can end up in a prompt (a report must not be able to give orders).
"""
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from app.guard import clean_test_name

log = logging.getLogger(__name__)

APPENDIX = re.compile(r"^#+\s*APPENDIX", re.I)
# keys that describe the patient or the paper, never a test result
META_WORDS = re.compile(
    r"\b(id|number|mrn|date|time|phone|doctor|physician|specimen|sample|barcode|accession|page|address|"
    r"issued|issuance|facility|laboratory|lab|report|section|appendix|version)\b", re.I)
NAME_KEYS = {"patient full name", "patient name", "name", "full name"}
AGE_KEYS = {"recorded age", "age", "patient age", "age (years)", "age in years"}
SEX_KEYS = {"biological sex", "sex", "gender", "sex at birth", "patient sex"}
MRN_KEYS = {"medical record number (mrn)", "medical record number", "mrn"}
TEST_NAME_KEYS = {"test", "test conducted", "test name", "analyte", "investigation"}
TEST_VALUE_KEYS = {"result", "results", "value recorded", "value", "observed value"}
QUALITATIVE = {"negative", "positive", "trace", "nil", "absent", "present", "not detected", "detected", "normal"}
VALUE_RE = re.compile(r"^(?P<cmp>[<>]=?)?\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>.*)$")
PLAIN_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ()%/.\-]{1,40}?)\s+(?P<value>[<>]?=?\s*\d+(?:\.\d+)?)\s*"
    r"(?P<unit>[A-Za-z%/^*0-9µμ.]+)?$")
MAX_RESULTS = 200


@dataclass
class RawResult:
    name: str
    value: Optional[Decimal]
    unit: str
    qualitative: Optional[str]
    comparator: str
    line: int
    raw: str


@dataclass
class Patient:
    name: str = ""
    age: Optional[int] = None
    age_raw: str = ""
    sex: Optional[str] = None
    sex_raw: str = ""
    mrn: str = ""
    results: List[RawResult] = field(default_factory=list)
    source: str = ""


def _clean(line: str) -> str:
    s = re.sub(r"\*\*", "", line).strip()
    return re.sub(r"^[*\-•]\s+", "", s).strip()


def _parse_value(text: str):
    """Return (value, unit, qualitative, comparator) or None when the text is not a result value."""
    text = text.strip()
    m = VALUE_RE.match(text)
    if m:
        return Decimal(m.group("num")), m.group("unit").strip(), None, m.group("cmp") or ""
    if text.lower().strip(". ") in QUALITATIVE:
        return None, "", text.strip(". "), ""
    return None


def _parse_age(raw: str) -> Optional[int]:
    m = re.search(r"\d+", raw)
    return int(m.group()) if m else None


def _parse_sex(raw: str) -> Optional[str]:
    r = raw.strip().lower().strip(".")
    if r in ("m", "male", "man"):
        return "male"
    if r in ("f", "female", "woman"):
        return "female"
    return None


def parse_report(text: str, source: str = "report") -> Patient:
    p = Patient(source=source)
    pending_name = None

    def add(name: str, parsed, number: int, raw_line: str) -> None:
        if parsed and len(p.results) < MAX_RESULTS:
            p.results.append(RawResult(clean_test_name(name), parsed[0], parsed[1], parsed[2], parsed[3], number,
                                       raw_line))

    for number, raw_line in enumerate(text.splitlines(), start=1):
        if APPENDIX.match(raw_line):
            break  # everything after this is filler
        s = _clean(raw_line)
        if not s or s.startswith("#"):
            continue

        # markdown table row: | name | value | unit |
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells) or len(cells) < 2:
                continue
            if cells[0].lower() in ("test", "test name", "analyte") and cells[1].lower() in ("result", "value", "results"):
                continue
            add(cells[0], _parse_value(cells[1] + (" " + cells[2] if len(cells) > 2 else "")), number, raw_line)
            continue

        # arrow form: name -> value
        if "->" in s:
            name, _, rest = s.partition("->")
            if name.strip():
                add(name.strip(), _parse_value(rest), number, raw_line)
            continue

        m = re.match(r"^(.{1,60}?)\s*[:=]\s*(.+)$", s)
        if not m:
            plain = PLAIN_RE.match(s)  # 'Hemoglobin 13.5 g/dL'
            if plain and not META_WORDS.search(plain.group("name")):
                add(plain.group("name"),
                    _parse_value(plain.group("value").replace("=", "") + " " + (plain.group("unit") or "")),
                    number, raw_line)
            continue
        key, value = m.group(1).strip(), m.group(2).strip()
        k = key.lower()
        if k in NAME_KEYS:
            p.name = value[:80]
        elif k in AGE_KEYS:
            p.age_raw, p.age = value[:40], _parse_age(value)
        elif k in SEX_KEYS:
            p.sex_raw, p.sex = value[:40], _parse_sex(value)
        elif k in MRN_KEYS:
            p.mrn = value[:60]
        elif k in TEST_NAME_KEYS:
            pending_name = value
        elif k in TEST_VALUE_KEYS and pending_name:
            add(pending_name, _parse_value(value), number, raw_line)
            pending_name = None
        elif not META_WORDS.search(key):
            add(key, _parse_value(value), number, raw_line)
    log.info("Parsed %s: %d results, age=%s sex=%s", source, len(p.results), p.age, p.sex)
    return p
