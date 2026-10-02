import re

# unit text -> (base unit, multiplier to base)
UNIT_TABLE = {
    # weight
    "mg": ("g", 0.001), "g": ("g", 1), "gm": ("g", 1), "gms": ("g", 1), "gram": ("g", 1), "grams": ("g", 1),
    "kg": ("g", 1000), "kgs": ("g", 1000), "kilogram": ("g", 1000), "kilograms": ("g", 1000),
    "oz": ("g", 28.35), "lb": ("g", 453.6), "lbs": ("g", 453.6),
    # volume
    "ml": ("ml", 1), "cl": ("ml", 10), "l": ("ml", 1000), "ltr": ("ml", 1000), "litre": ("ml", 1000),
    "litres": ("ml", 1000), "liter": ("ml", 1000), "liters": ("ml", 1000),
    "tsp": ("ml", 5), "teaspoon": ("ml", 5), "teaspoons": ("ml", 5),
    "tbsp": ("ml", 15), "tablespoon": ("ml", 15), "tablespoons": ("ml", 15),
    "cup": ("ml", 240), "cups": ("ml", 240),
    # count
    "pc": ("pcs", 1), "pcs": ("pcs", 1), "piece": ("pcs", 1), "pieces": ("pcs", 1),
    "unit": ("pcs", 1), "units": ("pcs", 1), "each": ("pcs", 1), "whole": ("pcs", 1),
    "s": ("pcs", 1), "'s": ("pcs", 1), "egg": ("pcs", 1), "eggs": ("pcs", 1),
}

_NUM = r"(\d+(?:\.\d+)?)"
_WEIGHT_VOL = r"(kg|kgs|g|gm|gms|grams?|mg|ml|cl|l|ltr|litres?|liters?|oz|lbs?)"
# "12 x 1L", "6x200ml", "2 x 500 g"
_MULTIPACK = re.compile(rf"(\d+)\s*[x×]\s*{_NUM}\s*{_WEIGHT_VOL}\b", re.IGNORECASE)
# "1.5L", "400g", "5 kg"
_SINGLE = re.compile(rf"{_NUM}\s*{_WEIGHT_VOL}\b", re.IGNORECASE)
# "10s", "5's", "30 pcs", "12 eggs"
_COUNT = re.compile(r"\b(\d+)\s*('s|s|pcs|pc|pieces|eggs)\b", re.IGNORECASE)


def to_base(quantity: float, unit: str) -> tuple[float, str] | None:
    """(700, 'g') -> (700, 'g');  (1.5, 'kg') -> (1500, 'g');  (2, 'cups') -> (480, 'ml').
    Returns None if the unit is unknown."""
    info = UNIT_TABLE.get(str(unit).strip().lower())
    if info is None or quantity is None:
        return None
    base, factor = info
    return float(quantity) * factor, base


def parse_package(title: str):
    """
    Extract package quantity from a product title.

    Priority:
    1. Multipacks
    2. Count-based packages
    3. Single weight/volume packages

    Eggs are special:
    their listed weight (e.g. 55g) often describes one egg,
    so weight alone must not be treated as the package quantity.
    """

    if not title:
        return None

    text = title.lower().strip()

    # ---------------------------------------------------------
    # 1. Multipack
    # Examples:
    #   12 x 1L
    #   6x200ml
    #   2 x 500g
    # ---------------------------------------------------------
    match = _MULTIPACK.search(text)

    if match:
        count = float(match.group(1))
        amount = float(match.group(2))
        unit = match.group(3).lower()

        if unit in UNIT_TABLE:
            base_unit, multiplier = UNIT_TABLE[unit]
            return count * amount * multiplier, base_unit

    # ---------------------------------------------------------
    # 2. Count-based packages
    # Examples:
    #   10s
    #   12 pcs
    #   30 pieces
    #   12 eggs
    # ---------------------------------------------------------
    match = _COUNT.search(text)

    if match:
        count = float(match.group(1))

        # Your _COUNT should identify the unit.
        raw_unit = match.group(2).lower()

        if raw_unit in UNIT_TABLE:
            base_unit, multiplier = UNIT_TABLE[raw_unit]
            return count * multiplier, base_unit

    # ---------------------------------------------------------
    # 3. Special handling for eggs
    # ---------------------------------------------------------
    egg_words = {"egg", "eggs"}

    if any(word in text.split() for word in egg_words):
        # If the title only gives something like "55g",
        # do NOT interpret it as the whole egg package.
        return None

    # ---------------------------------------------------------
    # 4. Single weight / volume
    # Examples:
    #   1.5L
    #   400g
    #   500ml
    # ---------------------------------------------------------
    match = _SINGLE.search(text)

    if match:
        amount = float(match.group(1))
        unit = match.group(2).lower()

        if unit in UNIT_TABLE:
            base_unit, multiplier = UNIT_TABLE[unit]
            return amount * multiplier, base_unit

    return None

def pretty(quantity: float, base: str) -> tuple[float, str]:
    """1500 g -> (1.5, 'kg'); 250 ml -> (250, 'ml'); 10 pcs -> (10, 'pcs')."""
    if base == "g" and quantity >= 1000:
        return round(quantity / 1000, 3), "kg"
    if base == "ml" and quantity >= 1000:
        return round(quantity / 1000, 3), "l"
    return round(quantity, 2), base