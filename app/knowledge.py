"""Reads the lab's reference files into plain data. Every rule remembers its file and line."""
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

APPENDIX = re.compile(r"^#+\s*APPENDIX", re.I)

# Extra spellings that the glossary does not list. Kept small on purpose.
EXTRA_ALIASES = {
    "hgb": "Hemoglobin",
    "haemoglobin": "Hemoglobin",
    "platelets": "Platelet Count",
    "wbc count": "White Blood Cell Count",
    "total cholesterol": "Cholesterol",
    "fasting glucose": "Fasting Blood Sugar",
    "fasting blood glucose": "Fasting Blood Sugar",
    "fbg": "Fasting Blood Sugar",
    "thyroid stimulating hormone": "TSH",
    "ph level": "Urine pH",
    "urine ph": "Urine pH",
    "ph": "Urine pH",
    "protein": "Urine Protein",
    "urine protein": "Urine Protein",
    "urinary protein": "Urine Protein",
}


@dataclass
class RangeRule:
    test: str
    sex: str  # male, female or all
    age_min: int
    age_max: int
    low: Optional[Decimal]
    high: Optional[Decimal]
    unit: str
    qualitative: Optional[str]  # for example "Negative"
    source: str  # file name and line


@dataclass
class UrgentRule:
    test: str
    trigger: str  # "less" or "greater"
    threshold: Decimal
    unit: str
    source: str


@dataclass
class KnowledgeBase:
    ranges: List[RangeRule] = field(default_factory=list)
    urgent: List[UrgentRule] = field(default_factory=list)
    aliases: Dict[str, str] = field(default_factory=dict)
    safety_rules: List[str] = field(default_factory=list)

    def canonical(self, raw_name: str) -> Optional[str]:
        key = re.sub(r"\s+", " ", raw_name.strip().lower())
        if key in self.aliases:
            return self.aliases[key]
        return None


def _lines(path: Path):
    """Yield (line number, text) up to the first appendix heading (the rest is legal filler)."""
    for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if APPENDIX.match(text):
            break
        yield number, text


def _dec(text: str) -> Decimal:
    return Decimal(text.strip())


def _add_alias(kb: KnowledgeBase, alias: str, canonical: str) -> None:
    kb.aliases[re.sub(r"\s+", " ", alias.strip().lower())] = canonical


def _parse_glossary(kb: KnowledgeBase, path: Path) -> None:
    for number, text in _lines(path):
        m = re.search(r"\*\*(.+?)\*\*\s+is the exact equivalent of\s+\*\*(.+?)\*\*", text)
        if not m:
            m = re.search(r"\*\*(.+?)\*\*\s+maps to\s+\*\*(.+?)\*\*", text)
        if m:
            _add_alias(kb, m.group(1), m.group(2).strip())
            _add_alias(kb, m.group(2), m.group(2).strip())


def _canonical_from_header(header: str):
    """'Hemoglobin (Hb)' -> ('Hemoglobin', 'Hb')."""
    m = re.match(r"(.+?)\s*\((.+?)\)\s*$", header.strip())
    return (m.group(1).strip(), m.group(2).strip()) if m else (header.strip(), None)


def _parse_hematology(kb: KnowledgeBase, path: Path) -> None:
    current = None
    for number, text in _lines(path):
        head = re.match(r"^\*\s+\*\*(.+?)\*\*:\s*$", text)
        if head:
            current, abbr = _canonical_from_header(head.group(1))
            _add_alias(kb, current, current)
            if abbr:
                _add_alias(kb, abbr, current)
            continue
        item = re.match(
            r"^\s+\*\s+(Male|Female|All)\b.*?\((\d+)-(\d+)\s*yrs?\):\s*([\d.]+)\s*-\s*([\d.]+)\s*(\S+)", text
        )
        if item and current:
            kb.ranges.append(
                RangeRule(
                    current, item.group(1).lower(), int(item.group(2)), int(item.group(3)),
                    _dec(item.group(4)), _dec(item.group(5)), item.group(6), None, f"{path.name}, line {number}",
                )
            )


def _parse_biochemistry(kb: KnowledgeBase, path: Path) -> None:
    for number, text in _lines(path):
        if not text.startswith("|") or "---" in text:
            continue
        cells = [c.strip().strip("*").strip() for c in text.strip().strip("|").split("|")]
        if len(cells) < 7 or not cells[2].isdigit():
            continue  # header row
        name, sex, amin, amax, low, high, unit = cells[:7]
        _add_alias(kb, name, name)
        kb.ranges.append(
            RangeRule(name, sex.lower(), int(amin), int(amax), _dec(low), _dec(high), unit, None,
                      f"{path.name}, line {number}")
        )


def _parse_thyroid_urine(kb: KnowledgeBase, path: Path) -> None:
    for number, text in _lines(path):
        m = re.match(r"^\*\s+\*\*(.+?)\*\*:\s*(.+?)\s*\(Applicable to (All|Male|Female)\b.*?(\d+)-(\d+)\s*yrs", text)
        if not m:
            continue
        name, value, sex, amin, amax = m.groups()
        _add_alias(kb, name, name)
        num = re.match(r"([\d.]+)\s*-\s*([\d.]+)\s*(\S*)", value)
        source = f"{path.name}, line {number}"
        if num:
            kb.ranges.append(RangeRule(name, sex.lower(), int(amin), int(amax), _dec(num.group(1)),
                                       _dec(num.group(2)), num.group(3), None, source))
        else:
            kb.ranges.append(RangeRule(name, sex.lower(), int(amin), int(amax), None, None, "",
                                       value.strip(), source))


def _parse_urgent(kb: KnowledgeBase, path: Path) -> None:
    for number, text in _lines(path):
        if not text.startswith("|") or "---" in text:
            continue
        cells = [c.strip().strip("*").strip() for c in text.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        try:
            threshold = _dec(cells[2])
        except Exception:
            continue  # header row
        trigger = "less" if cells[1].lower().startswith("less") else "greater"
        kb.urgent.append(UrgentRule(cells[0], trigger, threshold, cells[3], f"{path.name}, line {number}"))


def _parse_safety(kb: KnowledgeBase, path: Path) -> None:
    for _, text in _lines(path):
        if re.match(r"^\d+\.\s+\*\*", text):
            kb.safety_rules.append(re.sub(r"\*\*", "", text))


def load_kb(data_dir: Path) -> KnowledgeBase:
    """Load all reference files. Missing files raise a clear error instead of silent wrong answers."""
    kb = KnowledgeBase()
    parsers = [
        ("2_medical_glossary.md", _parse_glossary),
        ("4_ranges_hematology.md", _parse_hematology),
        ("5_ranges_biochemistry.md", _parse_biochemistry),
        ("6_ranges_thyroid_urine.md", _parse_thyroid_urine),
        ("3_dangerous_urgent_values.md", _parse_urgent),
        ("1_lab_safety_rules.md", _parse_safety),
    ]
    for filename, parser in parsers:
        path = Path(data_dir) / filename
        if not path.exists():
            raise FileNotFoundError(f"Reference file missing: {path}")
        parser(kb, path)
    for alias, canonical in EXTRA_ALIASES.items():
        kb.aliases.setdefault(alias, canonical)
    log.info("Knowledge loaded: %d ranges, %d urgent rules, %d aliases", len(kb.ranges), len(kb.urgent),
             len(kb.aliases))
    return kb
