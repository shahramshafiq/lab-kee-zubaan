"""Makes text sound natural when spoken: '12,000' becomes 'twelve thousand', 'g/dL' becomes 'grams per deciliter',
'ALT' is spelled out as letters. Applied to everything the voice says (never to what is shown on screen).
"""
import re

from num2words import num2words

# ---------- units ----------
UNITS = {
    "en": [
        ("cells/mcL", "cells per microliter"), ("cells/uL", "cells per microliter"), ("mIU/L", "milli international units per liter"),
        ("uIU/mL", "micro international units per milliliter"), ("mmol/L", "millimoles per liter"),
        ("mg/dL", "milligrams per deciliter"), ("g/dL", "grams per deciliter"), ("g/L", "grams per liter"),
        ("IU/L", "international units per liter"), ("U/L", "units per liter"), ("ng/mL", "nanograms per milliliter"),
    ],
    "ur": [
        ("cells/mcL", "خلیے فی مائیکرولیٹر"), ("cells/uL", "خلیے فی مائیکرولیٹر"), ("mIU/L", "ملی انٹرنیشنل یونٹ فی لیٹر"),
        ("uIU/mL", "مائیکرو انٹرنیشنل یونٹ فی ملی لیٹر"), ("mmol/L", "ملی مول فی لیٹر"),
        ("mg/dL", "ملی گرام فی ڈیسی لیٹر"), ("g/dL", "گرام فی ڈیسی لیٹر"), ("g/L", "گرام فی لیٹر"),
        ("IU/L", "انٹرنیشنل یونٹ فی لیٹر"), ("U/L", "یونٹ فی لیٹر"), ("ng/mL", "نینوگرام فی ملی لیٹر"),
    ],
}
# ---------- short names read as letters ----------
LETTERS = {
    "en": {"ALT": "A L T", "AST": "A S T", "TSH": "T S H", "WBC": "W B C", "PLT": "P L T", "FBS": "F B S", "pH": "P H",
           "SGPT": "S G P T", "SGOT": "S G O T", "MRN": "M R N"},
    "ur": {"ALT": "اے ایل ٹی", "AST": "اے ایس ٹی", "TSH": "ٹی ایس ایچ", "WBC": "ڈبلیو بی سی", "PLT": "پی ایل ٹی",
           "FBS": "ایف بی ایس", "pH": "پی ایچ", "SGPT": "ایس جی پی ٹی", "SGOT": "ایس جی او ٹی"},
}

# ---------- Urdu numbers (they have their own word for every number up to 99) ----------
_UR_0_99 = (
    "صفر ایک دو تین چار پانچ چھ سات آٹھ نو دس گیارہ بارہ تیرہ چودہ پندرہ سولہ سترہ اٹھارہ انیس بیس "
    "اکیس بائیس تئیس چوبیس پچیس چھبیس ستائیس اٹھائیس انتیس تیس اکتیس بتیس تینتیس چونتیس پینتیس چھتیس سینتیس اڑتیس انتالیس چالیس "
    "اکتالیس بیالیس تینتالیس چوالیس پینتالیس چھیالیس سینتالیس اڑتالیس انچاس پچاس "
    "اکیاون باون ترپن چون پچپن چھپن ستاون اٹھاون انسٹھ ساٹھ اکسٹھ باسٹھ تریسٹھ چوسٹھ پینسٹھ چھیاسٹھ سڑسٹھ اڑسٹھ انہتر ستر "
    "اکہتر بہتر تہتر چوہتر پچھتر چھہتر ستتر اٹھہتر اناسی اسی اکیاسی بیاسی تراسی چوراسی پچاسی چھیاسی ستاسی اٹھاسی نواسی نوے "
    "اکیانوے بیانوے ترانوے چورانوے پچانوے چھیانوے ستانوے اٹھانوے ننانوے"
).split()
assert len(_UR_0_99) == 100


def urdu_number(n: int) -> str:
    """0 to 999,999,999 in Urdu words, using crore (karor), lakh and hazaar like people say it."""
    if n < 100:
        return _UR_0_99[n]
    parts = []
    for size, word in ((10_000_000, "کروڑ"), (100_000, "لاکھ"), (1000, "ہزار"), (100, "سو")):
        if n >= size:
            parts.append(f"{urdu_number(n // size)} {word}")
            n %= size
    if n:
        parts.append(_UR_0_99[n])
    return " ".join(parts)


def _speak_number(match: "re.Match", lang: str) -> str:
    text = match.group(0)
    try:
        if "." in text:
            whole, frac = text.split(".", 1)
            if lang == "ur":
                digits = " ".join(_UR_0_99[int(d)] for d in frac)
                return f"{urdu_number(int(whole))} اعشاریہ {digits}"
            return num2words(int(whole), lang="en") + " point " + " ".join(num2words(int(d), lang="en") for d in frac)
        value = int(text)
        if value > 999_999_999:
            return text  # too long to say as one number: leave the digits
        return urdu_number(value) if lang == "ur" else num2words(value, lang="en")
    except Exception:
        return text


def to_speech(text: str, language: str = "en") -> str:
    """The text as it should be SPOKEN. Roman Urdu is read with an English voice, so it uses the English rules."""
    lang = "ur" if language == "ur" else "en"
    out = text
    for written, spoken in UNITS[lang]:
        out = out.replace(written, f" {spoken} ")
    out = re.sub(r"(?<=\d),(?=\d{3}\b)", "", out)                       # 12,000 -> 12000
    between = " سے " if lang == "ur" else " to "
    out = re.sub(r"(?<=\d)\s*[-–—‑]\s*(?=\d)", between, out)  # 7-55 -> 7 to 55
    for short, spelled in LETTERS[lang].items():
        out = re.sub(rf"\b{re.escape(short)}\b", spelled, out)
    out = re.sub(r"\d+(?:\.\d+)?", lambda m: _speak_number(m, lang), out)
    out = re.sub(r"\s+", " ", out).strip()
    return re.sub(r"\s+([.,;:!?،۔])", r"\1", out)  # no space before punctuation
