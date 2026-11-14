"""Unit names and conversions. Every conversion is shown to the user as a formula."""
from decimal import Decimal
from typing import Optional, Tuple

# Different spellings of the same unit. Left side is what a report may say (lower case, no spaces).
_SYNONYMS = {
    "cells/mcl": "cells/ul",
    "/ul": "cells/ul",
    "/mcl": "cells/ul",
    "cells/mm3": "cells/ul",
    "/mm3": "cells/ul",
    "/cumm": "cells/ul",       # per cubic millimetre is the same volume as a microlitre
    "/cu.mm": "cells/ul",
    "cells/cumm": "cells/ul",
    "iu/l": "u/l",
    "uiu/ml": "miu/l",
    "mu/l": "miu/l",
}

# (test, from unit) -> (factor, target unit). Factors are the usual textbook ones.
# The lab files do not list any conversions, so these live in code and are shown to the user.
_CONVERSIONS = {
    ("Fasting Blood Sugar", "mmol/l"): (Decimal("18"), "mg/dl"),
    ("Cholesterol", "mmol/l"): (Decimal("38.67"), "mg/dl"),
    ("Hemoglobin", "g/l"): (Decimal("0.1"), "g/dl"),
}
for _test in ("Platelet Count", "White Blood Cell Count"):
    for _unit in ("10^3/ul", "x10^3/ul", "k/ul", "10*3/ul", "10^9/l", "x10^9/l", "giga/l"):
        _CONVERSIONS[(_test, _unit)] = (Decimal("1000"), "cells/ul")


def norm_unit(unit: str) -> str:
    """Lower case, no spaces, one spelling per unit."""
    u = (unit or "").strip().lower().replace("µ", "u").replace("μ", "u").replace(" ", "")
    return _SYNONYMS.get(u, u)


def convert(test: str, value: Decimal, unit_raw: str, target_unit: str) -> Optional[Tuple[Decimal, str]]:
    """Return (value in target unit, readable steps), or None if it cannot be converted."""
    src, dst = norm_unit(unit_raw), norm_unit(target_unit)
    if src == dst:
        return value, ""
    rule = _CONVERSIONS.get((test, src))
    if not rule or rule[1] != dst:
        return None
    factor = rule[0]
    result = (value * factor).quantize(Decimal("0.01")).normalize()
    steps = f"{value.normalize():f} {unit_raw} x {factor:f} = {result:f} {target_unit}"
    return result, steps
