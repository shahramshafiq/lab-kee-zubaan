"""Turns the engine's checked results into plain words.

The engine decides the facts. The AI only writes the sentences, and a checker throws the text away if it
contains a number that is not in the facts or sounds like a diagnosis. Then we use the plain fallback words.
"""
import copy
import hashlib
import json
import logging
import re
from collections import OrderedDict
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Set

from app import llm, observability

log = logging.getLogger(__name__)
_CACHE: "OrderedDict[str, Dict]" = OrderedDict()  # checked AI explanations, keyed by facts and language

LANGUAGES = {"en": "simple English", "roman_urdu": "simple Roman Urdu (Urdu written in English letters)",
             "ur": "simple Urdu (in Urdu script)"}

SYSTEM = (
    "You explain lab results to a worried patient or a family member in words a class 8 student can follow. "
    "Rules: use ONLY the facts you are given; never invent numbers, ranges or tests; keep every number exactly as given; "
    "never say the person has a disease or condition; say what a test measures and what a low or high value CAN mean in "
    "general; remind that only a licensed doctor can diagnose; if a value is urgent, say clearly to see a doctor today; "
    "if something could not be classified or a range could not be chosen, say so and do not guess. "
    "Return ONLY a JSON object: {\"summary\": string, \"voice\": string, \"tests\": {\"<test name>\": string}, "
    "\"questions\": [string]} with 3 to 5 questions for the doctor, based on the results that are not normal. "
    "\"voice\" is a spoken version of the summary for an older person: at most 45 words, very short sentences, "
    "no tables, say the urgent warning first if there is one."
)

# phrases that sound like a diagnosis
_DISEASES = (r"(?:anemi\w*|anaemi\w*|diabet\w*|hepatitis|cirrhosis|hypothyroid\w*|hyperthyroid\w*|thyroid (?:disease|disorder)|"
             r"kidney (?:disease|failure|damage)|liver (?:disease|damage|failure)|infection|cancer|leuk[a]?emi\w*|thrombocytop\w*|"
             r"thrombocytos\w*|leukocytosis|leukopeni\w*|jaundice|hyperglyc\w*|hypoglyc\w*|dyslipid\w*|hypercholesterol\w*)")
DIAGNOSIS = re.compile(
    r"\b(?:you|patient|he|she)\s+(?:(?:may|might|could|probably|likely|definitely)\s+)?"
    r"(?:have|has|are|is|suffer(?:s|ing)? from|(?:do not|don't) have)\s+(?:\w+\s+){0,2}" + _DISEASES
    + r"|\b(?:diagnosed with|diagnosis of|suffering from)\b"
    + r"|\b(?:aap\s*ko|aapko|mareez\s+ko)\b.{0,25}\b(?:diabetes|anemia|anaemia|hepatitis|jaundice|cancer|infection)\b.{0,12}\bhai\b"
    + "|آپ کو.{0,25}(?:ذیابیطس|خون کی کمی|یرقان|ہیپاٹائٹس|کینسر).{0,12}ہے",
    re.I)
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩"
                        "۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def deidentify(analysis: Dict) -> Dict:
    """A copy without the name or record number. The AI only needs age, sex and the results."""
    safe = copy.deepcopy(analysis)
    safe["patient"] = {"age": analysis["patient"].get("age"), "sex": analysis["patient"].get("sex")}
    return safe


def _facts(analysis: Dict) -> List[Dict]:
    facts = []
    for f in analysis["results"]:
        facts.append({
            "test": f["test"], "status": f["status"], "value": f["value_as_written"], "unit": f["unit_as_written"],
            "converted_to": f["conversion"], "normal_range": f["range_used"], "urgent_rule": f["urgent_rule"],
            "reason": f["reason"], "ask_for": f["ask"],
        })
    return facts


def _norm(n: str) -> str:
    """'6.50' and '6.5' are the same number; '120000' stays '120000'."""
    return format(Decimal(n).normalize(), "f")


def allowed_numbers(analysis: Dict) -> Set[str]:
    """Every number that may appear in the explanation (also '120' for 120000, as in '120 thousand')."""
    blob = json.dumps(_facts(analysis)) + json.dumps(analysis["patient"]) + " 3 4 5 1 2"
    found = {_norm(n) for n in re.findall(r"\d+(?:\.\d+)?", blob)}
    for n in list(found):
        if Decimal(n) >= 1000:
            found.add(_norm(str(Decimal(n) / 1000)))
    return found


def check_text(data: Dict, analysis: Dict) -> Optional[str]:
    """Return a problem description, or None when the text is safe to show."""
    texts = ([data.get("summary", ""), data.get("voice", "")] + list(data.get("tests", {}).values())
             + list(data.get("questions", [])))
    allowed = allowed_numbers(analysis)
    for t in texts:
        t = str(t).translate(_DIGITS)
        t = re.sub(r"(?<=\d),(?=\d{3})", "", t)  # 120,000 -> 120000
        if DIAGNOSIS.search(t):
            return "sounds like a diagnosis"
        for n in re.findall(r"\d+(?:\.\d+)?", t):
            if _norm(n) not in allowed:
                return f"number {n} is not in the facts"
    if analysis["summary"]["urgent"] and not re.search(r"doctor", data.get("summary", ""), re.I):
        return "urgent result without a doctor warning"
    return None


def check_answer(text: str, analysis: Dict) -> Optional[str]:
    """Same safety check for a chat answer: no invented numbers, no diagnosis."""
    return check_text({"summary": "", "voice": "", "tests": {"x": text}, "questions": []},
                      {**analysis, "summary": {**analysis["summary"], "urgent": False}})


def _valid_shape(data: Dict) -> bool:
    return (isinstance(data.get("summary"), str) and isinstance(data.get("tests"), dict)
            and isinstance(data.get("questions"), list) and 3 <= len(data["questions"]) <= 5)


def rules_summary(analysis: Dict) -> str:
    """The fallback summary, written by code from the checked statuses."""
    results = analysis["results"]
    total = len(results)
    normal = [f for f in results if f["status"] == "normal"]
    parts = [f"{len(normal)} of {total} results are in the normal range."]
    for label, status in (("urgent", "urgent"), ("high", "high"), ("low", "low")):
        names = [f["test"] for f in results if f["status"] == status]
        if names:
            parts.append(f"{', '.join(names)}: {label}.")
    unsure = [f["test"] for f in results if f["status"] in ("cannot_classify", "needs_demographics")]
    if unsure:
        parts.append(f"{', '.join(unsure)}: could not be judged from the lab's files (see the note on each test).")
    if analysis["summary"]["urgent"]:
        parts.append("Please see a doctor today about the urgent result.")
    parts.append("Only a licensed doctor can diagnose. Please show this report to your doctor.")
    return " ".join(parts)


def rules_voice(analysis: Dict) -> str:
    """A very short spoken summary written by code."""
    results = analysis["results"]
    normal = sum(1 for f in results if f["status"] == "normal")
    parts = []
    if analysis["summary"]["urgent"]:
        parts.append("Important. One result is at a dangerous level. Please see a doctor today.")
    parts.append(f"{normal} of {len(results)} results are normal.")
    odd = [f["test"] + " is " + f["status"] for f in results if f["status"] in ("low", "high")]
    if odd:
        parts.append("; ".join(odd[:3]) + ".")
    if analysis["summary"]["needs"]:
        parts.append("I need the patient's " + " and ".join(analysis["summary"]["needs"]) + " to check some results.")
    parts.append("Only a doctor can diagnose. Please show this report to your doctor.")
    return " ".join(parts)


def explain(analysis: Dict, language: str = "en", use_ai: bool = True,
            asker: Callable = llm.ask) -> Dict:
    """Return the analysis with an 'explanation' block. Never raises: falls back to the rules text."""
    fallback = {
        "summary": rules_summary(analysis),
        "voice": rules_voice(analysis),
        "tests": {f["test"]: " ".join(x for x in (f["what_it_measures"], f["what_it_can_mean"], f["reason"]) if x)
                  for f in analysis["results"]},
        "questions": analysis["questions_for_doctor"],
        "source": "rules",
        "language": "en",
    }
    out = dict(analysis)
    if not use_ai:
        out["explanation"] = fallback
        return out
    cache_key = hashlib.sha1((json.dumps(_facts(analysis), sort_keys=True) + "|" + language).encode()).hexdigest()
    if cache_key in _CACHE:  # same checked facts in the same language: same words, instantly
        _CACHE.move_to_end(cache_key)
        observability.count("explain_cache_hit")
        out["explanation"] = _CACHE[cache_key]
        return out
    try:
        prompt = (f"Write in {LANGUAGES.get(language, LANGUAGES['en'])}.\n"
                  f"Patient: {json.dumps(deidentify(analysis)['patient'])}\n"
                  f"Facts (already checked by the lab's rules, do not change them):\n"
                  f"{json.dumps(_facts(analysis), indent=1)}")
        data, problem = None, None
        for attempt in range(2):  # one more try, telling the model what was wrong
            extra = f"\n\nYour previous answer was rejected because: {problem}. Fix that and answer again." if problem else ""
            data = llm.ask_json(SYSTEM, prompt + extra, _valid_shape, asker=asker)
            problem = check_text(data, analysis)
            if not problem:
                break
            log.warning("AI text rejected (attempt %d): %s", attempt + 1, problem)
        if problem:
            out["explanation"] = fallback
            return out
        data["source"], data["language"] = "ai", language
        if not isinstance(data.get("voice"), str) or not data["voice"].strip():
            data["voice"] = fallback["voice"]
        # make sure every test has a sentence, even if the model skipped one
        for f in analysis["results"]:
            data["tests"].setdefault(f["test"], fallback["tests"].get(f["test"], ""))
        out["explanation"] = data
        _CACHE[cache_key] = data
        while len(_CACHE) > 256:
            _CACHE.popitem(last=False)
    except llm.LLMUnavailable as exc:
        log.warning("Using rules text instead of AI: %s", exc)
        observability.count("ai_fallback_to_rules")
        out["explanation"] = fallback
    return out
