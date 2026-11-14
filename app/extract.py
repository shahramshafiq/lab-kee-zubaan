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
TIME_UNITS = {"hours", "hour", "hrs", "hr", "h", "minutes", "minute", "mins", "min", "seconds", "sec", "days", "day",
              "weeks", "months", "years", "yrs", "yr"}  # a duration is never a lab result
NO_RESULT = re.compile(r"^(pending|awaited|in progress|n/?a|na|nr|none|not (?:available|done|reported|performed|tested)|"
                       r"unavailable|-+|—)$|hem[o]?lyz|haemolys|hemolys|insufficient|clotted|lipemic|result unavailable|"
                       r"sample (?:rejected|not)|cancel|invalid|\berror\b", re.I)
VALUE_RE = re.compile(r"^(?P<cmp>[<>]=?)?\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>.*)$")
# 'Hemoglobin 13.5 g/dL' or 'Hemoglobin 13.5 g/dL 12.1 - 15.1 Normal' (PDF tables). A unit is required here.
PLAIN_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ()%/.\-]{1,40}?)\s+(?P<value>[<>]?=?\s*\d+(?:\.\d+)?)\s*"
    r"(?P<unit>[A-Za-z%/^*µμ][A-Za-z%/^*0-9µμ.]*)(?:\s+.*)?$")
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
    value_text: str = ""      # what was written, when it could not be read
    alt_value: Optional[Decimal] = None  # '1,200' read as 1200, used ONLY to check the danger limits
    alt_unit: str = ""
    missing_reason: str = ""  # set when the report names the test but gives no usable result (Pending, N/A, -4.1, 1,2 ...)


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


def _odd_reason(text: str) -> str:
    """Why a value could not be read, in words for the patient. '' when it is simply not a result."""
    t = (text or "").strip()
    if not t:
        return "the report names this test but no result is written next to it"
    if NO_RESULT.search(t.strip(". ")):
        return f"the report gives no result for this test ('{t[:40]}')"
    if re.match(r"^[-−–]\s*\d", t):
        return "the value is written as a negative number, which is not possible for a lab result, so it cannot be trusted"
    if COMMA_NUMBER.match(t):
        return (f"the number is written with a comma ('{t[:20]}'), so it could mean a decimal or a thousand "
                "(1,2 or 1,200). Please check the report")
    return ""


FLAG_WORDS = r"(?:HH|LL|H|L|HIGH|LOW|CRITICAL|CRIT|ABNORMAL|NORMAL|URGENT|PANIC|ALERT|FLAG|REF|REFERENCE|RANGE|NORMAL RANGE)"


def _clean_unit(unit: str) -> str:
    """'g/dL (L)', 'g/dL [13.8-17.2]', 'g/dL  CRITICAL', 'mg/dL 70 - 99 H' -> just the unit. The lab's own flags are
    never trusted or used: the status always comes from the lab files."""
    u = re.sub(r"[\(\[\{][^\)\]\}]*[\)\]\}]?", " ", unit or "")           # brackets and what is inside
    u = re.split(r"\s+\d+(?:\.\d+)?\s*[-–]\s*\d|\s+[<>]=?\s*\d", u)[0]   # a reference range after the unit
    u = re.sub(r"[↑↓*!]+", " ", u)
    u = re.sub(r"\s+(?:" + FLAG_WORDS + r")\b.*$", "", u.strip(), flags=re.I)  # a flag word after the unit
    return re.sub(r"\s+", " ", u).strip()


COMMA_NUMBER = re.compile(r"^[<>]?=?\s*\d{1,3},\d")
SCI_RE = re.compile(r"^(?P<cmp>[<>]=?)?\s*(?P<num>\d+(?:\.\d+)?)\s*[eE](?P<exp>[+-]?\d{1,2})\s*(?P<unit>.*)$")


def _parse_value(text: str):
    """Return (value, unit, qualitative, comparator) or None when the text is not a result value."""
    text = text.strip()
    if COMMA_NUMBER.match(text):
        return None  # 1,2 or 1,200 could be a decimal or a thousand: never guess
    sci = SCI_RE.match(text)
    if sci:  # 7.5E3 is 7500
        return (Decimal(sci.group("num")).scaleb(int(sci.group("exp"))), _clean_unit(sci.group("unit")), None,
                sci.group("cmp") or "")
    m = VALUE_RE.match(text)
    if m:
        return Decimal(m.group("num")), _clean_unit(m.group("unit")), None, m.group("cmp") or ""
    if text.lower().strip(". ") in QUALITATIVE:
        return None, "", text.strip(". "), ""
    return None


HEADER_WORDS = {"test", "test name", "analyte", "investigation", "parameter", "result", "results", "value", "unit",
                "units", "reference", "reference range", "range", "normal range", "flag", "status", "method", "remarks"}
UNIT_CELL = re.compile(r"^[A-Za-zµμ%/][A-Za-z0-9%/^*µμ.\-]{0,14}$")
RANGE_CELL = re.compile(r"^[<>]?=?\s*\d+(?:\.\d+)?\s*[-–]\s*\d")


def _is_header_row(cells) -> bool:
    words = [c.lower().strip(" :") for c in cells if c.strip()]
    return len(words) >= 2 and sum(w in HEADER_WORDS for w in words) >= 2


def _table_value(cells):
    """The value of a table row. The result is normally the second cell; some tables put a method or code there first."""
    first = _parse_value(cells[1] + (" " + cells[2] if len(cells) > 2 else ""))
    if first and (first[0] is not None or first[2]):
        return first
    for i in range(1, len(cells)):
        cell = cells[i].strip()
        if not cell or RANGE_CELL.match(cell):
            continue
        parsed = _parse_value(cell)
        if parsed and (parsed[0] is not None or parsed[2]):
            if parsed[0] is not None and not parsed[1] and i + 1 < len(cells) and UNIT_CELL.match(cells[i + 1].strip())                     and cells[i + 1].strip().lower() not in HEADER_WORDS | QUALITATIVE:
                return parsed[0], cells[i + 1].strip(), None, parsed[3]
            return parsed
    return first


def _parse_age(raw: str) -> Optional[int]:
    """Age in whole years. '18 months' is 1, '3 weeks' is 0 (never read as 18 or 3 years)."""
    m = re.search(r"\d+", raw)
    if not m:
        return None
    n = int(m.group())
    low = raw.lower()
    if re.search(r"year|yr|\by\b", low):
        return n
    if re.search(r"month|mth|\bmos?\b", low):
        return n // 12
    if re.search(r"week|wk", low):
        return n // 52
    if re.search(r"\bdays?\b", low):
        return n // 365
    return n


def _parse_sex(raw: str) -> Optional[str]:
    r = raw.strip().lower().strip(".")
    if r in ("m", "male", "man"):
        return "male"
    if r in ("f", "female", "woman"):
        return "female"
    return None


AGE_ANY = re.compile(r"(?:^|[^A-Za-z])(?:patient[ ]+)?age(?:[ ]*[(]years[)])?[ ]*[:=-][ ]*(\d{1,3}[ ]*(?:years?|yrs?|yr|months?|mths?|mos?|weeks?|wks?|days?|y)?)(?![A-Za-z])", re.I)
SEX_ANY = re.compile(r"(?:^|[^A-Za-z])(?:biological[ ]+)?(?:sex|gender)[ ]*[:=-][ ]*(male|female|m|f)(?![A-Za-z])", re.I)
AGE_SEX_ANY = re.compile(r"age[ ]*[/&][ ]*(?:sex|gender)[ ]*[:=-][ ]*(\d{1,3})[ ]*(?:years?|yrs?|y)?[ ]*[/,][ ]*(male|female|m|f)(?![A-Za-z])", re.I)


def _demographics_anywhere(text: str, p: "Patient") -> None:
    """Age and sex written inside a longer line ('Patient name: A. Khan   Age: 42 years   Sex: Female'), as PDFs and photos
    often give them. Only used when the line-by-line reading did not find them."""
    body = text
    for line in text.splitlines():
        if APPENDIX.match(line):
            body = text[:text.index(line)]
            break
    if p.age is None:
        m = AGE_SEX_ANY.search(body)
        if m:
            p.age_raw, p.age = m.group(1), int(m.group(1))
            p.sex_raw, p.sex = m.group(2), _parse_sex(m.group(2))
        else:
            m = AGE_ANY.search(body)
            if m:
                p.age_raw, p.age = m.group(1).strip()[:40], _parse_age(m.group(1))
    if p.sex is None:
        m = SEX_ANY.search(body)
        if m:
            p.sex_raw, p.sex = m.group(1), _parse_sex(m.group(1))


def parse_report(text: str, source: str = "report") -> Patient:
    p = Patient(source=source)
    pending_name = None

    in_meta = [False]  # inside the specimen or patient details part of the report: nothing there is a result

    def add(name: str, parsed, number: int, raw_line: str, text=None) -> None:
        if in_meta[0] or len(p.results) >= MAX_RESULTS:
            return
        if parsed:
            if parsed[1].lower().strip(". ") in TIME_UNITS:
                return
            p.results.append(RawResult(clean_test_name(name), parsed[0], parsed[1], parsed[2], parsed[3], number,
                                       raw_line))
        elif text is not None and not META_WORDS.search(name):
            reason = _odd_reason(text)
            if reason:
                th = re.match(r"^(\d{1,3}),(\d{3})(?!\d)\s*(.*)$", (text or "").strip())
                p.results.append(RawResult(clean_test_name(name), None, "", None, "", number, raw_line,
                                           (text or "").strip()[:30], Decimal(th.group(1) + th.group(2)) if th else None,
                                           th.group(3).strip() if th else "", reason))

    for number, raw_line in enumerate(text.splitlines(), start=1):
        if APPENDIX.match(raw_line):
            break  # everything after this is filler
        s = _clean(raw_line)
        if s.startswith("#"):
            heading = s.lower()
            if re.search(r"specimen|demographic|encounter|patient details|collection", heading):
                in_meta[0] = True
            elif re.search(r"result|analytical|finding|investigation", heading):
                in_meta[0] = False
            continue
        if not s:
            continue

        # markdown table row: | name | value | unit |
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells) or len(cells) < 2:
                continue
            if _is_header_row(cells):
                continue
            add(cells[0], _table_value(cells), number, raw_line, " ".join(cells[1:3]))
            continue

        # arrow form: name -> value
        if "->" in s:
            name, _, rest = s.partition("->")
            if name.strip():
                add(name.strip(), _parse_value(rest), number, raw_line, rest)
            continue

        m = re.match(r"^(.{1,60}?)\s*[:=]\s*(.+)$", s)
        if not m:
            blank = re.match(r"^([A-Za-z][^:=|]{1,38}?)\s*:\s*$", s)  # 'Platelet Count:' with nothing after it
            if blank and len(blank.group(1).split()) <= 4 and not META_WORDS.search(blank.group(1))                     and blank.group(1).strip().lower() not in NAME_KEYS | AGE_KEYS | SEX_KEYS | MRN_KEYS:
                add(blank.group(1), None, number, raw_line, "")
                continue
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
        elif k.replace(" ", "") in ("age/sex", "sex/age", "age&sex", "age,sex", "age/gender", "gender/age"):
            m_age = re.search(r"\d{1,3}", value)
            m_sex = re.search(r"\b(male|female|m|f)\b", value, re.I)
            if m_age:
                p.age_raw, p.age = value[:40], int(m_age.group())
            if m_sex:
                p.sex_raw, p.sex = value[:40], _parse_sex(m_sex.group(1))
        elif k in SEX_KEYS:
            p.sex_raw, p.sex = value[:40], _parse_sex(value)
        elif k in MRN_KEYS:
            p.mrn = value[:60]
        elif k in TEST_NAME_KEYS:
            pending_name = value
        elif k in TEST_VALUE_KEYS and pending_name:
            add(pending_name, _parse_value(value), number, raw_line, value)
            pending_name = None
        elif not META_WORDS.search(key):
            add(key, _parse_value(value), number, raw_line, value)
    _demographics_anywhere(text, p)
    log.info("Parsed %s: %d results, age=%s sex=%s", source, len(p.results), p.age, p.sex)
    return p
