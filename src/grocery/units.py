"""src/grocery/units.py

Grocery quantity normalization and retail package parsing.

Conversions are only performed inside compatible physical unit families.
Count and small recipe measures remain explicit rather than receiving
invented gram/ml conversions.
"""

from __future__ import annotations

import re


UNIT_TABLE = {
    # ---------------------------------------------------------
    # Mass -> grams
    # ---------------------------------------------------------
    "mg": ("g", 0.001),
    "g": ("g", 1.0),
    "gm": ("g", 1.0),
    "gms": ("g", 1.0),
    "gram": ("g", 1.0),
    "grams": ("g", 1.0),

    "kg": ("g", 1000.0),
    "kgs": ("g", 1000.0),
    "kilogram": ("g", 1000.0),
    "kilograms": ("g", 1000.0),

    "oz": ("g", 28.3495),
    "ounce": ("g", 28.3495),
    "ounces": ("g", 28.3495),

    "lb": ("g", 453.592),
    "lbs": ("g", 453.592),
    "pound": ("g", 453.592),
    "pounds": ("g", 453.592),

    # ---------------------------------------------------------
    # Volume -> ml
    # ---------------------------------------------------------
    "ml": ("ml", 1.0),
    "milliliter": ("ml", 1.0),
    "milliliters": ("ml", 1.0),
    "millilitre": ("ml", 1.0),
    "millilitres": ("ml", 1.0),

    "cl": ("ml", 10.0),

    "l": ("ml", 1000.0),
    "ltr": ("ml", 1000.0),
    "litre": ("ml", 1000.0),
    "litres": ("ml", 1000.0),
    "liter": ("ml", 1000.0),
    "liters": ("ml", 1000.0),

    "tsp": ("ml", 5.0),
    "teaspoon": ("ml", 5.0),
    "teaspoons": ("ml", 5.0),

    "tbsp": ("ml", 15.0),
    "tablespoon": ("ml", 15.0),
    "tablespoons": ("ml", 15.0),

    "cup": ("ml", 240.0),
    "cups": ("ml", 240.0),

    "fl oz": ("ml", 29.5735),
    "fluid ounce": ("ml", 29.5735),
    "fluid ounces": ("ml", 29.5735),

    # ---------------------------------------------------------
    # Count
    # ---------------------------------------------------------
    "pc": ("pcs", 1.0),
    "pcs": ("pcs", 1.0),
    "piece": ("pcs", 1.0),
    "pieces": ("pcs", 1.0),

    "count": ("pcs", 1.0),
    "unit": ("pcs", 1.0),
    "units": ("pcs", 1.0),
    "each": ("pcs", 1.0),
    "whole": ("pcs", 1.0),

    "egg": ("pcs", 1.0),
    "eggs": ("pcs", 1.0),

    "clove": ("pcs", 1.0),
    "cloves": ("pcs", 1.0),

    "head": ("pcs", 1.0),
    "heads": ("pcs", 1.0),

    "stalk": ("pcs", 1.0),
    "stalks": ("pcs", 1.0),

    "sprig": ("pcs", 1.0),
    "sprigs": ("pcs", 1.0),

    "slice": ("pcs", 1.0),
    "slices": ("pcs", 1.0),

    "can": ("pcs", 1.0),
    "cans": ("pcs", 1.0),

    "tin": ("pcs", 1.0),
    "tins": ("pcs", 1.0),

    "packet": ("pcs", 1.0),
    "packets": ("pcs", 1.0),

    "pack": ("pcs", 1.0),
    "packs": ("pcs", 1.0),

    "bottle": ("pcs", 1.0),
    "bottles": ("pcs", 1.0),

    "jar": ("pcs", 1.0),
    "jars": ("pcs", 1.0),

    # FairPrice-style count notation
    "s": ("pcs", 1.0),
    "'s": ("pcs", 1.0),
}


SMALL_MEASURES = {
    "pinch",
    "pinches",
    "dash",
    "dashes",
    "handful",
    "handfuls",
    "to taste",
}


def unit_family(unit: str | None) -> str | None:
    """Return the physical family for a recipe/product unit."""

    if not unit:
        return None

    normalized = str(unit).strip().lower()

    if normalized in SMALL_MEASURES:
        return "small_measure"

    info = UNIT_TABLE.get(normalized)

    if info is None:
        return None

    base = info[0]

    if base == "g":
        return "mass"

    if base == "ml":
        return "volume"

    if base == "pcs":
        return "count"

    return None


def to_base(
    quantity: float,
    unit: str,
) -> tuple[float, str] | None:
    """
    Convert compatible measurable quantities to their family base.

    Small recipe measures intentionally return None because a pinch/dash
    does not have one universally valid physical conversion.
    """

    if quantity is None or not unit:
        return None

    normalized = str(unit).strip().lower()

    if normalized in SMALL_MEASURES:
        return None

    info = UNIT_TABLE.get(normalized)

    if info is None:
        return None

    base, factor = info

    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        return None

    if quantity < 0:
        return None

    return quantity * factor, base


_NUM = r"(\d+(?:\.\d+)?)"

_WEIGHT_VOL = (
    r"(kg|kgs|kilograms?|"
    r"g|gm|gms|grams?|mg|"
    r"ml|cl|l|ltr|litres?|liters?|"
    r"oz|ounces?|lbs?|pounds?)"
)

_MULTIPACK = re.compile(
    rf"\b(\d+)\s*[x×]\s*{_NUM}\s*{_WEIGHT_VOL}\b",
    re.IGNORECASE,
)

_SINGLE = re.compile(
    rf"\b{_NUM}\s*{_WEIGHT_VOL}\b",
    re.IGNORECASE,
)

_COUNT = re.compile(
    r"\b(\d+)\s*"
    r"('s|s|pcs?|pieces?|eggs?|"
    r"packs?|packets?|bottles?|jars?|cans?|tins?)\b",
    re.IGNORECASE,
)


def parse_package(text: str):
    """
    Extract the total retail package quantity.

    Examples:
        12 x 1L -> 12000 ml
        6 x 200ml -> 1200 ml
        500g -> 500 g
        12 eggs -> 12 pcs
        10s -> 10 pcs
    """

    if not text:
        return None

    text = str(text).lower().strip()

    # ---------------------------------------------------------
    # Multipack
    # ---------------------------------------------------------

    match = _MULTIPACK.search(text)

    if match:
        count = float(match.group(1))
        amount = float(match.group(2))
        unit = match.group(3).lower()

        info = UNIT_TABLE.get(unit)

        if info:
            base, factor = info
            return count * amount * factor, base

    # ---------------------------------------------------------
    # Count package
    # ---------------------------------------------------------

    match = _COUNT.search(text)

    if match:
        count = float(match.group(1))
        return count, "pcs"

    # ---------------------------------------------------------
    # Eggs:
    # a value such as 55g commonly refers to egg grading rather
    # than total retail package mass.
    # ---------------------------------------------------------

    token_set = set(re.findall(r"[a-z]+", text))

    if "egg" in token_set or "eggs" in token_set:
        return None

    # ---------------------------------------------------------
    # Single physical package
    # ---------------------------------------------------------

    match = _SINGLE.search(text)

    if match:
        amount = float(match.group(1))
        unit = match.group(2).lower()

        info = UNIT_TABLE.get(unit)

        if info:
            base, factor = info
            return amount * factor, base

    return None


def compatible(
    need: tuple[float, str] | None,
    package: tuple[float, str] | None,
) -> bool:
    """Whether normalized recipe and package quantities are comparable."""

    if need is None or package is None:
        return False

    return need[1] == package[1]


def pretty(
    quantity: float,
    base: str,
) -> tuple[float, str]:

    if base == "g" and quantity >= 1000:
        return round(quantity / 1000, 3), "kg"

    if base == "ml" and quantity >= 1000:
        return round(quantity / 1000, 3), "l"

    if base == "pcs":
        return round(quantity, 2), "pcs"

    return round(quantity, 2), base