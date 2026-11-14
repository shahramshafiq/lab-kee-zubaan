"""Urdu words written ahead of time, so Urdu works instantly and also when the AI is slow or down.

Same rules as plain.py: simple words, nothing that names a disease for the patient.
"""

STATUS_UR = {
    "normal": "نارمل", "low": "کم", "high": "زیادہ", "urgent": "فوری توجہ",
    "cannot_classify": "فائلوں سے جانچ ممکن نہیں", "needs_demographics": "مزید معلومات درکار",
}

DISCLAIMER_UR = ("یہ وضاحت تشخیص نہیں ہے۔ بیماری کی تشخیص اور علاج کا فیصلہ صرف مستند ڈاکٹر کر سکتا ہے۔ "
                 "براہ کرم یہ رپورٹ اپنے ڈاکٹر کو دکھائیں۔")

PLAIN_UR = {
    "Hemoglobin": (
        "ہیموگلوبن خون کے سرخ خلیوں کا وہ حصہ ہے جو جسم میں آکسیجن پہنچاتا ہے۔",
        "کم قدر کا مطلب ہو سکتا ہے کہ خون میں آکسیجن لے جانے کی صلاحیت معمول سے کم ہے۔ اس کی کئی وجوہات ہو سکتی ہیں، اس لیے وجہ صرف ڈاکٹر بتا سکتا ہے۔",
        "زیادہ قدر کی کئی وجوہات ہو سکتی ہیں، مثلاً جسم میں پانی کی کمی۔ وجہ صرف ڈاکٹر بتا سکتا ہے۔",
    ),
    "White Blood Cell Count": (
        "سفید خلیے جسم کے محافظ ہیں اور جراثیم سے لڑتے ہیں۔",
        "کم قدر کا مطلب ہے کہ محافظ خلیے معمول سے کم ہیں۔ ڈاکٹر کو دکھانا ضروری ہے۔",
        "زیادہ قدر اکثر اس وقت ہوتی ہے جب جسم کسی چیز سے لڑ رہا ہو، لیکن اس کی اور وجوہات بھی ہو سکتی ہیں۔",
    ),
    "Platelet Count": (
        "پلیٹلیٹس خون جمانے میں مدد دیتے ہیں تاکہ چوٹ لگنے پر خون رک جائے۔",
        "کم قدر میں چوٹ لگنے پر خون بہنے یا نیل پڑنے کا امکان معمول سے زیادہ ہو سکتا ہے۔ ڈاکٹر سے ملیں۔",
        "زیادہ قدر کی کئی وجوہات ہو سکتی ہیں۔ وجہ ڈاکٹر بتا سکتا ہے۔",
    ),
    "Fasting Blood Sugar": (
        "یہ کئی گھنٹے کچھ کھائے بغیر خون میں شکر (گلوکوز) کی مقدار ہے۔",
        "کم قدر سے کمزوری، کپکپی یا چکر آ سکتے ہیں۔",
        "زیادہ قدر پر ڈاکٹر ٹیسٹ دوبارہ کرنے یا مزید ٹیسٹ کروانے کا کہہ سکتا ہے۔",
    ),
    "ALT": (
        "ALT ایک مددگار پروٹین (اینزائم) ہے جو زیادہ تر جگر میں ہوتا ہے۔",
        "کم ALT عموماً فکر کی بات نہیں ہوتی۔",
        "زیادہ قدر کی کئی وجوہات ہو سکتی ہیں، مثلاً کچھ دوائیں، بہت چکنی غذا یا انفیکشن۔ وجہ ڈاکٹر بتا سکتا ہے۔",
    ),
    "AST": (
        "AST ایک مددگار پروٹین ہے جو جگر اور پٹھوں میں ہوتا ہے۔",
        "کم AST عموماً فکر کی بات نہیں ہوتی۔",
        "زیادہ قدر کی وجوہات میں سخت ورزش، کچھ دوائیں یا جگر پر دباؤ شامل ہو سکتے ہیں۔ وجہ ڈاکٹر بتا سکتا ہے۔",
    ),
    "Cholesterol": (
        "کولیسٹرول خون میں چربی جیسی ایک چیز ہے۔ جسم کو اس کی کچھ مقدار چاہیے۔",
        "کم قدر عموماً فکر کی بات نہیں، پھر بھی ڈاکٹر کو بتائیں۔",
        "زیادہ قدر کا مطلب ہے کہ خون میں چربی معمول سے زیادہ ہے۔ ڈاکٹر خوراک اور ورزش کے بارے میں مشورہ دے سکتا ہے۔",
    ),
    "TSH": (
        "TSH دماغ کا وہ پیغام ہے جو گلے میں موجود تھائیرائیڈ غدود کو بتاتا ہے کہ اسے کتنا کام کرنا ہے۔",
        "کم قدر کا مطلب ہو سکتا ہے کہ تھائیرائیڈ کو کم کام کرنے کا کہا جا رہا ہے۔ فیصلہ ڈاکٹر کرتا ہے۔",
        "زیادہ قدر کا مطلب ہو سکتا ہے کہ دماغ تھائیرائیڈ سے زیادہ کام مانگ رہا ہے۔ فیصلہ ڈاکٹر کرتا ہے۔",
    ),
    "Urine pH": (
        "یہ بتاتا ہے کہ پیشاب کتنا تیزابی یا کھارا ہے۔ غذا، پانی اور دوائیں اسے بدل سکتی ہیں۔",
        "کم قدر کا مطلب ہے کہ پیشاب معمول سے زیادہ تیزابی ہے۔",
        "زیادہ قدر کا مطلب ہے کہ پیشاب معمول سے زیادہ کھارا ہے۔",
    ),
    "Urine Protein": (
        "عام طور پر پیشاب میں پروٹین بہت کم ہوتا ہے یا بالکل نہیں ہوتا۔ ‘نیگیٹو’ کا مطلب ہے کہ کوئی پروٹین نہیں ملا۔",
        "",
        "پیشاب میں پروٹین کئی وجوہات سے آ سکتا ہے، مثلاً بخار، سخت ورزش یا گردوں پر دباؤ۔ ڈاکٹر سے جانچ ضروری ہے۔",
    ),
}


# Test names in Urdu script, so the Urdu voice and the Urdu page do not mix in English words.
NAMES_UR = {
    "Hemoglobin": "ہیموگلوبن", "White Blood Cell Count": "سفید خلیات", "Platelet Count": "پلیٹلیٹس",
    "Fasting Blood Sugar": "فاسٹنگ بلڈ شوگر", "ALT": "اے ایل ٹی", "AST": "اے ایس ٹی", "Cholesterol": "کولیسٹرول",
    "TSH": "ٹی ایس ایچ", "Urine pH": "پیشاب کا پی ایچ", "Urine Protein": "پیشاب میں پروٹین",
}


def name_ur(test: str) -> str:
    return NAMES_UR.get(test, test)


def plain_ur(test: str, status: str):
    entry = PLAIN_UR.get(test)
    if not entry:
        return "", ""
    measures, low, high = entry
    return measures, (low if status == "low" else high if status == "high" else "")


def summary_ur(results, urgent: bool) -> str:
    total = len(results)
    normal = sum(1 for f in results if f["status"] == "normal")
    parts = [f"{total} میں سے {normal} نتائج نارمل ہیں۔"]
    for status, label in (("urgent", "فوری توجہ درکار ہے"), ("high", "زیادہ ہے"), ("low", "کم ہے")):
        names = [name_ur(f["test"]) for f in results if f["status"] == status]
        if names:
            parts.append(f"{'، '.join(names)}: {label}۔")
    unsure = [name_ur(f["test"]) for f in results if f["status"] in ("cannot_classify", "needs_demographics")]
    if unsure:
        parts.append(f"{'، '.join(unsure)}: لیب کی فائلوں سے جانچ ممکن نہیں ہوئی۔")
    if urgent:
        parts.append("براہ کرم آج ہی ڈاکٹر سے ملیں۔")
    parts.append("تشخیص صرف مستند ڈاکٹر کر سکتا ہے۔ یہ رپورٹ اپنے ڈاکٹر کو دکھائیں۔")
    return " ".join(parts)


def voice_ur(results, urgent: bool, needs) -> str:
    total = len(results)
    normal = sum(1 for f in results if f["status"] == "normal")
    parts = []
    if urgent:
        parts.append("اہم بات۔ ایک نتیجہ خطرناک سطح پر ہے۔ براہ کرم آج ہی ڈاکٹر سے ملیں۔")
    parts.append(f"{total} میں سے {normal} نتائج نارمل ہیں۔")
    odd = [f"{name_ur(f['test'])} {'کم' if f['status'] == 'low' else 'زیادہ'} ہے" for f in results if f["status"] in ("low", "high")]
    if odd:
        parts.append("، ".join(odd[:3]) + "۔")
    if needs:
        asks = " اور ".join({"age": "عمر", "sex": "جنس"}.get(n, n) for n in needs)
        parts.append(f"کچھ نتائج جانچنے کے لیے مجھے مریض کی {asks} چاہیے۔")
    parts.append("تشخیص صرف ڈاکٹر کر سکتا ہے۔")
    return " ".join(parts)


def questions_ur(results):
    qs = []
    for f in results:
        t = name_ur(f["test"])
        if f["status"] == "urgent":
            qs.append(f"میرا {t} کا نتیجہ فوری ہے۔ مجھے آج کیا کرنا چاہیے، اور کیا ابھی علاج یا ٹیسٹ کی ضرورت ہے؟")
        elif f["status"] in ("low", "high"):
            qs.append(f"میرا {t} {'کم' if f['status'] == 'low' else 'زیادہ'} ہے۔ میرے معاملے میں اس کی کیا وجہ ہو سکتی ہے؟")
        elif f["status"] in ("cannot_classify", "needs_demographics"):
            qs.append(f"لیب کی شیٹس {t} کو جانچ نہیں سکیں۔ مجھے اس نتیجے کو کیسے سمجھنا چاہیے؟")
    generic = ["کیا مجھے کوئی ٹیسٹ دوبارہ کروانا ہے، اور کب؟",
               "کیا اگلے ٹیسٹ سے پہلے مجھے اپنی خوراک، دوائیں یا روزمرہ معمول بدلنا چاہیے؟",
               "ان نتائج میں سے مجھے کس پر سب سے زیادہ نظر رکھنی چاہیے؟"]
    for g in generic:
        if len(qs) >= 3:
            break
        qs.append(g)
    return qs[:5]
