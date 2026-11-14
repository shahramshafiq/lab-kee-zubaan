"""Guardrails for what a user may ask. Rules first, so the answer is the same every time and the AI never sees it.

Categories: other patient, diagnosis request, treatment request, instruction attack, out of scope.
"""
import re
from typing import Dict, Optional

DIAGNOSIS_ASK = re.compile(
    r"\b(do i have|am i (diabetic|anemic|anaemic|sick|ill|dying)|do i suffer|what (disease|illness|condition) do i|"
    r"is it (cancer|diabetes|hepatitis)|diagnose me|what is wrong with me|which disease|"
    r"mujhe .{0,30}(hai kya|to nahi)|kya mujhe|meri bimari|mujhe kya bimari)\b"
    r"|کیا مجھے|میری بیماری", re.I)

TREATMENT_ASK = re.compile(
    r"\b(what (medicine|medication|drug|tablet|pill|antibiotic)|which (medicine|medication|drug|tablet)|dose|dosage|"
    r"should i (take|stop|start|skip|increase|decrease)|can i (take|stop|skip)|prescribe|treatment for me|cure|"
    r"dawa|dawai|ilaaj|ilaj)\b|دوا|علاج", re.I)

ATTACK = re.compile(
    r"(ignore|forget|disregard|override|bypass)\s+(all\s+|any\s+|the\s+|your\s+|previous\s+|prior\s+|above\s+)*"
    r"(instructions?|rules?|prompts?|guidelines?|restrictions?)"
    r"|\b(system prompt|developer mode|jailbreak|you are now|act as|pretend (to be|you are)|reveal your (prompt|instructions))\b"
    r"|\b(DAN mode|sudo|admin override)\b", re.I)

MESSAGES: Dict[str, str] = {
    "diagnosis": ("I cannot tell you whether you have a disease. Only a licensed medical doctor can diagnose. "
                  "I can explain what each number in your report measures and give you questions to ask your doctor."),
    "treatment": ("I cannot advise on medicines, doses or treatment. Please ask your doctor or pharmacist. "
                  "I can explain your results and prepare questions for your doctor."),
    "attack": ("I can only explain the lab report you opened, using the lab's own rules. I cannot change my rules or "
               "my role. Please ask a question about your results."),
}


def classify_question(question: str) -> Optional[str]:
    """Return 'attack', 'diagnosis', 'treatment' or None. Other-patient requests are handled in chat.py."""
    q = question.strip()
    if ATTACK.search(q):
        return "attack"
    if DIAGNOSIS_ASK.search(q):
        return "diagnosis"
    if TREATMENT_ASK.search(q):
        return "treatment"
    return None


def clean_test_name(name: str) -> str:
    """Names from a report may end up in a prompt: keep them short and plain."""
    name = re.sub(r"[^\w\s\-/().%,+؀-ۿ]", "", name or "")
    name = re.sub(r"\s+", " ", name).strip()[:60]
    if ATTACK.search(name):
        return "unreadable test name"
    return name or "unreadable test name"
