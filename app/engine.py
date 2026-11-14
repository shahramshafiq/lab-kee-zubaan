"""The rules engine. Code (not the AI) decides every status, so the same report always gives the same answer.

Statuses: normal, low, high, urgent, cannot_classify, needs_demographics.
"""
import logging
from decimal import Decimal
from typing import Dict, List, Optional

from app import config
from app.extract import Patient, RawResult
from app.knowledge import KnowledgeBase, RangeRule
from app.plain import DISCLAIMER, plain_for
from app.units import convert

log = logging.getLogger(__name__)


def _num(d: Optional[Decimal]):
    """Decimal to a JSON-friendly number without trailing zeros."""
    if d is None:
        return None
    d = d.normalize()
    return int(d) if d == d.to_integral() else float(d)


def _missing(patient: Patient, rules: List[RangeRule], strict: bool) -> List[str]:
    """Which demographic fields we must ask for before a range can be chosen."""
    missing = []
    if patient.age is None:
        missing.append("age")
    needs_sex = strict or any(r.sex != "all" for r in rules)
    if patient.sex is None and needs_sex:
        missing.append("sex")
    return missing


def _urgent_check(canonical: str, value: Decimal, unit_raw: str, kb: KnowledgeBase):
    """Return (rule, std value) if the value hits or passes a dangerous threshold."""
    for rule in kb.urgent:
        if rule.test != canonical:
            continue
        converted = convert(canonical, value, unit_raw, rule.unit)
        if converted is None:
            continue
        std = converted[0]
        # "hit or pass": a value exactly on the threshold counts as urgent (the safe side).
        hit = std <= rule.threshold if rule.trigger == "less" else std >= rule.threshold
        if hit:
            return rule, std
    return None, None


def _base(res: RawResult, canonical: Optional[str]) -> Dict:
    return {
        "test_as_written": res.name,
        "test": canonical or res.name,
        "value_as_written": res.qualitative if res.qualitative else f"{res.comparator}{_num(res.value)}",
        "unit_as_written": res.unit,
        "line": res.line,
        "status": "cannot_classify",
        "direction": None,
        "value_standard": None,
        "unit_standard": None,
        "conversion": None,
        "range_used": None,
        "urgent_rule": None,
        "reason": "",
        "ask": [],
    }


def classify(res: RawResult, patient: Patient, kb: KnowledgeBase, strict: bool) -> Dict:
    canonical = kb.canonical(res.name)
    out = _base(res, canonical)

    rules = [r for r in kb.ranges if canonical and r.test == canonical]
    if not canonical or not rules:
        out["reason"] = "cannot be classified from the files: no matching normal range for this test."
        return out

    # 1) danger check first: it does not depend on age or sex
    if res.value is not None and not res.comparator:
        urgent_rule, std = _urgent_check(canonical, res.value, res.unit, kb)
        if urgent_rule:
            out.update(
                status="urgent",
                direction="low" if urgent_rule.trigger == "less" else "high",
                value_standard=_num(std),
                unit_standard=urgent_rule.unit,
                urgent_rule={"trigger": urgent_rule.trigger, "threshold": _num(urgent_rule.threshold),
                             "unit": urgent_rule.unit, "source": urgent_rule.source},
                reason=f"This value is past the dangerous limit in {urgent_rule.source}. Please see a doctor today.",
            )
            conv = convert(canonical, res.value, res.unit, urgent_rule.unit)
            out["conversion"] = conv[1] or None
            # still try to show the normal range if we can; do not block the warning on it
            _attach_range(out, res, patient, rules, strict)
            return out

    # 2) the right range needs age and sex (lab safety rule 3)
    missing = _missing(patient, rules, strict)
    if missing:
        out["status"] = "needs_demographics"
        out["ask"] = missing
        out["reason"] = ("The right normal range cannot be chosen because the report does not give the patient's "
                         + " and ".join(missing) + ". Please provide it. I will not guess it.")
        return out

    _attach_range(out, res, patient, rules, strict)
    if out["status"] != "cannot_classify" or out["reason"]:
        return out
    return out


def _attach_range(out: Dict, res: RawResult, patient: Patient, rules: List[RangeRule], strict: bool) -> None:
    """Pick the range, convert the unit, compare. Fills status unless already urgent."""
    if _missing(patient, rules, strict):
        return
    candidates = [r for r in rules if r.sex in (patient.sex, "all") and r.age_min <= patient.age <= r.age_max]
    if not candidates:
        if out["status"] != "urgent":
            out["reason"] = (f"cannot be classified from the files: no normal range for age {patient.age}, "
                             f"sex {patient.sex}.")
        return
    rule = candidates[0]
    out["range_used"] = {
        "low": _num(rule.low), "high": _num(rule.high), "qualitative": rule.qualitative, "unit": rule.unit,
        "sex": rule.sex, "age_min": rule.age_min, "age_max": rule.age_max, "source": rule.source,
    }

    if rule.qualitative is not None:  # for example urine protein: Negative
        value = (res.qualitative or "").lower()
        if not value:
            out["reason"] = "cannot be classified from the files: this test needs a word result such as Negative."
            return
        normal = value in ("negative", "nil", "absent", "not detected", "normal")
        out["status"], out["direction"] = ("normal", None) if normal else ("high", "high")
        out["reason"] = f"Normal is {rule.qualitative} ({rule.source})."
        return

    if res.value is None or res.comparator:
        out["reason"] = ("cannot be classified from the files: the value is not an exact number "
                         f"({res.comparator or ''}{res.qualitative or ''}).")
        return

    converted = convert(rule.test, res.value, res.unit, rule.unit)
    if converted is None:
        if out["status"] != "urgent":
            out["reason"] = (f"cannot be classified from the files: the unit '{res.unit}' cannot be converted "
                             f"to '{rule.unit}'.")
        return
    value, steps = converted
    out["value_standard"], out["unit_standard"] = _num(value), rule.unit
    if steps:
        out["conversion"] = steps
    if out["status"] == "urgent":
        return  # keep the urgent label, range shown for context
    # a value exactly on a limit is NORMAL (edge-case rule in the range sheets)
    if value < rule.low:
        out["status"], out["direction"] = "low", "low"
    elif value > rule.high:
        out["status"], out["direction"] = "high", "high"
    else:
        out["status"], out["direction"] = "normal", None
    out["reason"] = (f"Normal for this patient is {_num(rule.low)} to {_num(rule.high)} {rule.unit} "
                     f"({rule.source}); a value exactly on a limit counts as normal.")


def doctor_questions(findings: List[Dict]) -> List[str]:
    """3 to 5 questions, built from the results that are not normal."""
    qs: List[str] = []
    for f in findings:
        t = f["test"]
        if f["status"] == "urgent":
            qs.append(f"My {t} result is marked urgent. What should I do today, and do I need treatment or tests right now?")
        elif f["status"] in ("low", "high"):
            qs.append(f"My {t} is {f['status']}. What could be causing this in my case?")
        elif f["status"] in ("cannot_classify", "needs_demographics"):
            qs.append(f"The lab sheets could not judge my {t}. How should I understand this result?")
    generic = [
        "Do I need to repeat any test, and when?",
        "Should I change my food, medicines or daily routine before the next test?",
        "Which of these results should I watch most closely?",
    ]
    for g in generic:
        if len(qs) >= 3:
            break
        qs.append(g)
    return qs[:5]


def analyze(patient: Patient, kb: KnowledgeBase, strict: Optional[bool] = None) -> Dict:
    strict = config.STRICT_DEMOGRAPHICS if strict is None else strict
    findings = [classify(r, patient, kb, strict) for r in patient.results]
    for f in findings:
        measures, meaning = plain_for(f["test"], f["status"])
        f["what_it_measures"], f["what_it_can_mean"] = measures, meaning

    counts: Dict[str, int] = {}
    for f in findings:
        counts[f["status"]] = counts.get(f["status"], 0) + 1
    asks = sorted({a for f in findings for a in f["ask"]})
    urgent = [f for f in findings if f["status"] == "urgent"]
    return {
        "patient": {
            "name": patient.name, "age": patient.age, "sex": patient.sex, "mrn": patient.mrn,
            "age_as_written": patient.age_raw, "sex_as_written": patient.sex_raw,
        },
        "results": findings,
        "summary": {"counts": counts, "urgent": bool(urgent), "needs": asks},
        "urgent_warning": ("URGENT: one or more values are at a dangerous level. See a doctor today."
                           if urgent else ""),
        "questions_for_doctor": doctor_questions(findings),
        "disclaimer": DISCLAIMER,
    }
