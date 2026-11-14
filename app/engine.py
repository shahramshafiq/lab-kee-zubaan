"""The rules engine. Code (not the AI) decides every status, so the same report always gives the same answer.

Statuses: normal, low, high, urgent, cannot_classify, needs_demographics.
"""
import logging
import re
from decimal import Decimal
from typing import Dict, List, Optional

from app import config
from app.extract import Patient, RawResult
from app.knowledge import KnowledgeBase, RangeRule
from app.plain import DISCLAIMER, plain_for
from app.units import convert, norm_unit

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


def _urgent_check(canonical: str, value: Decimal, unit_raw: str, kb: KnowledgeBase, comparator: str = ""):
    """Return (rule, std value) if the value hits or passes a dangerous threshold."""
    for rule in kb.urgent:
        if rule.test != canonical:
            continue
        converted = convert(canonical, value, unit_raw, rule.unit)
        if converted is None:
            continue
        std = converted[0]
        # "hit or pass": a value exactly on the threshold counts as urgent (the safe side).
        if not comparator:
            hit = std <= rule.threshold if rule.trigger == "less" else std >= rule.threshold
        elif comparator in ("<", "<="):   # '<10': every value below it is past a 'less than' limit of 50
            hit = rule.trigger == "less" and std <= rule.threshold
        else:                             # '>1000': every value above it is past a 'greater than' limit of 1000
            hit = rule.trigger == "greater" and std >= rule.threshold
        if hit:
            return rule, std
    return None, None


def _base(res: RawResult, canonical: Optional[str]) -> Dict:
    shown = res.qualitative if res.qualitative else f"{res.comparator}{_num(res.value)}" if res.value is not None else (res.value_text or "no result")
    return {
        "test_as_written": res.name,
        "test": canonical or res.name,
        "value_as_written": shown,
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
        "next_code": "",           # which standard next-step text the page shows, in the chosen language
        "next_step": "",           # what the patient can do when a result cannot be classified (never a guess)
        "can_provide_range": False,  # True: the patient may type the normal range printed on their own report
        "user_range": False,       # True: the status was decided with a range the patient typed in
    }


NEXT_NO_RANGE = ("Look next to this result on your report for a column called 'reference range' or 'normal range'. "
                 "If a range is printed there, type it below and I will compare your value with it. I will say clearly "
                 "that the range came from you, not from the lab files. If nothing is printed, ask the lab which range "
                 "they use.")
NEXT_NO_UNIT = ("The unit is missing next to this value, so comparing it would be a guess. Check which unit your report "
                "prints for it (for example g/dL or mg/dL), and ask the lab if none is printed.")
NEXT_ASK_LAB = "Please ask your doctor or the lab how to read this result. I cannot judge it from the files I have."


def _apply_user_range(out: Dict, res: RawResult, given) -> None:
    """The patient typed the normal range from their own report. Compare in the unit written on the report."""
    low, high = given
    value = res.value
    out["range_used"] = {"low": _num(low), "high": _num(high), "qualitative": None, "unit": res.unit, "sex": "all",
                         "age_min": None, "age_max": None, "source": "the range you typed from your report"}
    out["user_range"] = True
    out["can_provide_range"] = True
    out["status"], out["direction"] = (("low", "low") if value < low else ("high", "high") if value > high
                                         else ("normal", None))
    out["reason"] = (f"Compared with the range you typed from your report ({_num(low)} to {_num(high)} {res.unit}). "
                     "This range is not from the lab files, so please confirm it with your doctor.")
    out["next_step"], out["next_code"] = "", ""


def classify(res: RawResult, patient: Patient, kb: KnowledgeBase, strict: bool, user_ranges=None) -> Dict:
    canonical = kb.canonical(res.name)
    out = _base(res, canonical)
    if res.missing_reason:  # named in the report, but there is nothing usable to compare
        out["reason"] = "cannot be classified from the files: " + res.missing_reason + "."
        out["next_step"] = ("Ask the lab or your doctor for this result in a clear form. I will not guess a value or "
                            "a range for it.")
        out["next_code"] = "missing"
        if res.alt_value is not None and canonical:  # '1,200': never guessed, but a danger limit must not be missed
            rule, std = _urgent_check(canonical, res.alt_value, res.alt_unit, kb)
            if rule:
                out.update(
                    status="urgent", direction="low" if rule.trigger == "less" else "high", value_standard=_num(std),
                    unit_standard=rule.unit,
                    urgent_rule={"trigger": rule.trigger, "threshold": _num(rule.threshold), "unit": rule.unit,
                                 "source": rule.source},
                    reason=(f"The number is written with a comma ({res.value_text}). Read as {_num(res.alt_value)} it is "
                            f"past the dangerous limit in {rule.source}. Please see a doctor today, and check the exact "
                            "value on the report."))
                out["next_step"], out["next_code"] = "", ""
        return out

    rules = [r for r in kb.ranges if canonical and r.test == canonical]
    if not canonical or not rules:
        out["reason"] = "cannot be classified from the files: no matching normal range for this test."
        numeric = res.value is not None and not res.comparator
        out["can_provide_range"] = numeric
        out["next_step"] = NEXT_NO_RANGE if numeric else NEXT_ASK_LAB
        out["next_code"] = "no_range" if numeric else "ask_lab"
        given = (user_ranges or {}).get(res.name.strip().lower())
        if numeric and given:
            _apply_user_range(out, res, given)
        return out

    # 1) danger check first: it does not depend on age or sex
    if res.value is not None:
        urgent_rule, std = _urgent_check(canonical, res.value, res.unit, kb, res.comparator)
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
            out["next_step"], out["next_code"] = NEXT_ASK_LAB, "ask_lab"
        return
    rule = candidates[0]
    out["range_used"] = {
        "low": _num(rule.low), "high": _num(rule.high), "qualitative": rule.qualitative, "unit": rule.unit,
        "sex": rule.sex, "age_min": rule.age_min, "age_max": rule.age_max, "source": rule.source,
    }

    if rule.qualitative is not None:  # for example urine protein: Negative
        # a word result ('Negative') or a plus sign style result ('1+') are both read as text
        value = (res.qualitative or (f"{res.value.normalize():f}{res.unit}" if res.value is not None else "")).lower()
        if not value:
            out["reason"] = "cannot be classified from the files: this test needs a word result such as Negative."
            return
        normal = value in ("negative", "nil", "absent", "not detected", "normal")
        if not normal and not re.match(r"^(positive|present|detected|\d\s*\+|\+{1,4})", value):
            # the sheet only says what is normal. Words such as Trace are not covered, so no label is guessed.
            out["reason"] = (f"cannot be classified from the files: the sheet says normal is {rule.qualitative}, "
                             f"and does not say how to read '{res.qualitative or value}'.")
            out["next_step"], out["next_code"] = "Ask your doctor what this result means for you. I will not guess it.", "ask_lab"
            return
        out["status"], out["direction"] = ("normal", None) if normal else ("high", "high")
        out["reason"] = f"Normal is {rule.qualitative} ({rule.source})."
        return

    if res.value is None or res.comparator:
        if out["status"] == "urgent":
            return  # '<10' or '>1000' is past a danger limit: keep the urgent label and its reason
        out["reason"] = ("cannot be classified from the files: the value is not an exact number "
                         f"({res.comparator or ''}{res.qualitative or ''}).")
        out["next_step"], out["next_code"] = ("A result such as '<5' or a word result needs a doctor's reading. Ask "
                            "your doctor what it means for you."), "not_exact"
        return

    converted = convert(rule.test, res.value, res.unit, rule.unit)
    if converted is None:
        if out["status"] != "urgent":
            if not res.unit:
                out["reason"] = ("cannot be classified from the files: no unit was written next to the value, "
                                 f"so it cannot be compared safely with {rule.unit}.")
                out["next_step"], out["next_code"] = NEXT_NO_UNIT, "no_unit"
            else:
                out["reason"] = (f"cannot be classified from the files: the unit '{res.unit}' cannot be converted "
                                 f"to '{rule.unit}'.")
                out["next_step"], out["next_code"] = ("I do not know how to convert this unit safely. Check whether your "
                                    "report prints the same result in another unit, and ask the lab if you are not sure."), "unit_convert"
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


def _with_unit(f: Dict) -> str:
    return f"{f['value_as_written']} {f['unit_as_written']}".strip()


def doctor_questions(findings: List[Dict]) -> List[str]:
    """3 to 5 questions a thoughtful patient would really ask, built from the actual results (never vague)."""
    qs: List[str] = []
    order = {"urgent": 0, "low": 1, "high": 1, "cannot_classify": 2}
    for f in sorted((x for x in findings if x["status"] in order), key=lambda x: order[x["status"]]):
        t, shown = f["test"], _with_unit(f)
        rng = f.get("range_used") or {}
        span = f"{rng['low']} to {rng['high']} {rng['unit']}" if rng.get("low") is not None else ""
        if f["status"] == "urgent":
            qs.append(f"My {t} is {shown}, which is at a dangerous level. Do I need to go to a hospital today, "
                      "and what should be checked or repeated first?")
        elif f["status"] in ("low", "high"):
            qs.append(f"My {t} is {shown}, {f['status']} against a normal range of {span}. Is that enough to need "
                      "treatment, or should we repeat it first, and what would you check next to find the reason?")
        elif f["can_provide_range"]:
            qs.append(f"My {t} was {shown}, but I could not check it against a normal range. Which range does your lab "
                      "use for it, and is my value normal for me?")
        else:
            qs.append(f"I could not read my {t} result ({shown}) with confidence. What does it mean for me?")
    pool = [
        "Could a medicine, a supplement, fasting or a recent illness have changed these results?",
        "Which of these results should I repeat, and how soon?",
        "Are any of these results connected to each other, and does that change what you would do?",
    ]
    if not any(f["status"] in ("urgent", "low", "high", "cannot_classify") for f in findings):
        pool = ["All my results are normal. Is there anything about my age, family history or symptoms that these tests "
                "would not show?",
                "How often should I repeat this set of tests?",
                "Which tests would you add if I develop symptoms?"]
    for q in pool:
        if len(qs) >= 3:
            break
        qs.append(q)
    return qs[:5]


def _merge_repeats(patient: Patient, kb: KnowledgeBase) -> List[RawResult]:
    """The same test written twice with the same value is shown once. The same test with two different values is a
    conflict: both are kept and marked, because the report itself does not say which one is right."""
    groups: Dict[str, List[RawResult]] = {}
    order: List[str] = []
    for r in patient.results:
        key = (kb.canonical(r.name) or r.name).strip().lower()
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)
    out: List[RawResult] = []
    for key in order:
        seen, unique = set(), []
        for r in groups[key]:
            sig = (r.value, r.qualitative, r.comparator, norm_unit(r.unit or ""), r.missing_reason)
            if sig not in seen:
                seen.add(sig)
                unique.append(r)
        if len(unique) > 1:
            values = " and ".join(f"{u.comparator}{_num(u.value) if u.value is not None else u.qualitative or '?'} {u.unit}".strip()
                                  for u in unique)
            for u in unique:
                if not u.missing_reason:
                    u.missing_reason = (f"the report lists this test more than once with different values ({values}) "
                                        "and does not say which one is right")
        out.extend(unique)
    return out


def analyze(patient: Patient, kb: KnowledgeBase, strict: Optional[bool] = None, user_ranges=None) -> Dict:
    strict = config.STRICT_DEMOGRAPHICS if strict is None else strict
    findings = [classify(r, patient, kb, strict, user_ranges) for r in _merge_repeats(patient, kb)]
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
