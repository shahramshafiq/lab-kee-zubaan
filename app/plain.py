"""Plain-word facts for each test (what it measures, what low or high can mean).

These are the fallback words used when the AI writer is off or fails. They never name a disease.
"""

DISCLAIMER = (
    "This explanation is not a diagnosis. Only a licensed medical doctor can diagnose a condition "
    "or decide on treatment. Please show this report to your doctor."
)

PLAIN = {
    "Hemoglobin": (
        "Hemoglobin is the part of your red blood cells that carries oxygen around your body.",
        "A low value can mean your blood is carrying less oxygen than usual. There are many possible reasons, so only a doctor can say why.",
        "A high value can happen for many reasons, for example when the body has less water than usual. Only a doctor can say why.",
    ),
    "White Blood Cell Count": (
        "White blood cells are the body's defenders. They help fight germs.",
        "A low value means fewer defenders than usual. There are many possible reasons, so a doctor needs to look at it.",
        "A high value means more defenders than usual. This is often seen when the body is busy fighting something, but there are many reasons.",
    ),
    "Platelet Count": (
        "Platelets are tiny cell pieces that help your blood clot, so a cut stops bleeding.",
        "A low value can mean you bruise or bleed more easily than usual. A doctor should check it.",
        "A high value can have many reasons. A doctor can tell which one applies to you.",
    ),
    "Fasting Blood Sugar": (
        "This is the amount of sugar (glucose) in your blood after you have not eaten for several hours.",
        "A low value means less sugar than usual, which can make a person feel shaky, weak or dizzy.",
        "A high value means more sugar than usual. A doctor may want to repeat the test or ask for other tests.",
    ),
    "ALT": (
        "ALT is a helper protein (an enzyme) found mostly in the liver. A little of it is normally in your blood.",
        "A low ALT is usually not a worry by itself.",
        "A high value can happen for many reasons, such as some medicines, very fatty food or an infection. A doctor can find out which one.",
    ),
    "AST": (
        "AST is a helper protein (an enzyme) found in the liver and in muscles.",
        "A low AST is usually not a worry by itself.",
        "A high value can happen for many reasons, such as heavy exercise, some medicines or liver stress. A doctor can find out which one.",
    ),
    "Cholesterol": (
        "Cholesterol is a fat-like substance in your blood. Your body needs some of it.",
        "A low value is usually not a worry by itself, but tell your doctor.",
        "A high value means there is more fat in the blood than usual. Over a long time this can strain the blood vessels, so a doctor may talk about food and exercise.",
    ),
    "TSH": (
        "TSH is a signal from the brain that tells your thyroid gland (in your neck) how hard to work.",
        "A low value can mean the thyroid is being told to work less. A doctor decides what it means.",
        "A high value can mean the brain is asking the thyroid to work harder. A doctor decides what it means.",
    ),
    "Urine pH": (
        "This shows how acidic or alkaline your urine is. Food, water and medicines can change it.",
        "A low value means more acidic urine than the usual range. Food and water can change this.",
        "A high value means more alkaline urine than the usual range. Food and water can change this.",
    ),
    "Urine Protein": (
        "Normally there is very little or no protein in urine. 'Negative' means none was found.",
        "",
        "Protein in the urine can come from many things, such as fever, hard exercise or the kidneys being strained. A doctor needs to check it.",
    ),
}


def plain_for(test: str, status: str):
    """Return the (measures, meaning) sentences for a test and status."""
    entry = PLAIN.get(test)
    if not entry:
        return "", ""
    measures, low, high = entry
    if status in ("low",):
        return measures, low
    if status in ("high",):
        return measures, high
    return measures, ""
