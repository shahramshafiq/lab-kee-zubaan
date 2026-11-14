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


MESSAGES_UR: Dict[str, str] = {
    "diagnosis": ("میں یہ نہیں بتا سکتا کہ آپ کو کوئی بیماری ہے یا نہیں۔ یہ صرف لائسنس یافتہ ڈاکٹر بتا سکتا ہے۔ "
                  "میں آپ کی رپورٹ کا ہر نمبر سمجھا سکتا ہوں اور ڈاکٹر سے پوچھنے کے سوالات بنا سکتا ہوں۔"),
    "treatment": ("میں دوا، خوراک یا علاج کے بارے میں مشورہ نہیں دے سکتا۔ براہ کرم اپنے ڈاکٹر یا فارماسسٹ سے پوچھیں۔ "
                  "میں آپ کے نتائج سمجھا سکتا ہوں اور ڈاکٹر کے لیے سوالات تیار کر سکتا ہوں۔"),
    "attack": ("میں صرف وہی لیب رپورٹ سمجھا سکتا ہوں جو آپ نے کھولی ہے، لیب کے اپنے اصولوں کے مطابق۔ "
               "میں اپنے اصول یا کردار نہیں بدل سکتا۔ براہ کرم اپنے نتائج کے بارے میں کوئی سوال پوچھیں۔"),
    "other_patient": ("میں صرف اسی رپورٹ کے بارے میں بات کر سکتا ہوں جو آپ نے کھولی ہے۔ میں کسی اور مریض کے نتائج نہیں بتا سکتا، "
                      "کیونکہ وہ نجی ہیں۔ کسی اور رپورٹ کے لیے براہ کرم لیب سے کہیں۔"),
}
MESSAGES_RU: Dict[str, str] = {
    "diagnosis": ("Main yeh nahin bata sakta ke aap ko koi bimari hai ya nahin. Yeh sirf licensed doctor bata sakta hai. "
                  "Main aap ki report ka har number samjha sakta hoon aur doctor se poochne ke sawal bana sakta hoon."),
    "treatment": ("Main dawa, khurak ya ilaj ke bare mein mashwara nahin de sakta. Meharbani karke apne doctor ya "
                  "pharmacist se poochein. Main aap ke nataij samjha sakta hoon aur doctor ke liye sawal tayyar kar sakta hoon."),
    "attack": ("Main sirf wohi lab report samjha sakta hoon jo aap ne kholi hai, lab ke apne usoolon ke mutabiq. "
               "Main apne usool ya kirdar nahin badal sakta. Meharbani karke apne nataij ke bare mein sawal poochein."),
    "other_patient": ("Main sirf usi report ke bare mein baat kar sakta hoon jo aap ne kholi hai. Main kisi aur mareez ke "
                      "nataij nahin bata sakta, kyun ke woh nijji hain. Kisi aur report ke liye lab se kahein."),
}


def message(kind: str, language: str = "en") -> str:
    """The fixed safe reply, in the language the person is using."""
    if language == "ur":
        return MESSAGES_UR.get(kind) or MESSAGES[kind]
    if language == "roman_urdu":
        return MESSAGES_RU.get(kind) or MESSAGES[kind]
    return MESSAGES.get(kind) or ""


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
