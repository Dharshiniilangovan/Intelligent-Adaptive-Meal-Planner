
import json
import math
from functools import lru_cache
from pathlib import Path

import pandas as pd

from src.grocery.units import to_base


RAW_RECIPE_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "recipes.csv"
)


# Raw Edamam <unit> placeholders that we permit
# as individual produce counts.
#
# Only use this for known whole-produce ingredients.
# Do not globally interpret <unit> as count.

WHOLE_PRODUCE_COUNT_INGREDIENTS = {
    "lemon",
    "lime",
    "orange",
    "apple",
    "banana",
    "pear",
    "peach",
    "nectarine",
    "tomato",
    "vine tomato",
    "vine tomatoes",
    "strawberry",
    "potato",
    "onion",
    "avocado",
}


@lru_cache(maxsize=1)
def load_raw_recipes():
    return pd.read_csv(
        RAW_RECIPE_FILE,
        dtype={"recipie_id": str},
    )



def normalize_name(name):
    """
    Normalize ingredient names for recipe-weight matching.

    Only normalize explicitly supported plural forms.
    Avoid broad stemming that could merge different foods.
    """

    text = " ".join(
        str(name).strip().lower().split()
    )

    plural_aliases = {
        "vine tomatoes": "vine tomato",
        "tomatoes": "tomato",
        "strawberries": "strawberry",
        "blueberries": "blueberry",
        "raspberries": "raspberry",
        "blackberries": "blackberry",
        "bananas": "banana",
        "lemons": "lemon",
        "limes": "lime",
        "apples": "apple",
        "potatoes": "potato",
        "onions": "onion",
    }

    return plural_aliases.get(text, text)



def estimate_recipe_weight(
    recipe_id: str,
    ingredient_name: str,
    quantity: float,
    unit: str,
) -> tuple[float, str] | None:
    """
    Estimate ingredient weight using the original
    recipe's ingredient quantity and source weight.

    Returns (estimated_grams, 'g') or None.

    Only compatible measurement units are supported.
    """

    if not recipe_id or not ingredient_name or not unit:
        return None

    try:
        required_quantity = float(quantity)
    except (TypeError, ValueError):
        return None

    if (
        not math.isfinite(required_quantity)
        or required_quantity <= 0
    ):
        return None

    recipes = load_raw_recipes()

    matches = recipes[
        recipes["recipie_id"].astype(str).str.strip()
        == str(recipe_id).strip()
    ]

    if len(matches) != 1:
        return None

    try:
        raw_ingredients = json.loads(
            matches.iloc[0]["ingredients"]
        )
    except (TypeError, ValueError):
        return None

    target = normalize_name(ingredient_name)

    matching = [
        item
        for item in raw_ingredients
        if isinstance(item, dict)
        and normalize_name(item.get("food", "")) == target
    ]

    # Avoid guessing when duplicate ingredient entries exist.
    if len(matching) != 1:
        return None

    item = matching[0]

    try:
        raw_quantity = float(item["quantity"])
        raw_weight = float(item["weight"])
    except (KeyError, TypeError, ValueError):
        return None

    if (
        not math.isfinite(raw_quantity)
        or not math.isfinite(raw_weight)
        or raw_quantity <= 0
        or raw_weight <= 0
    ):
        return None

    raw_unit = normalize_name(item.get("measure", ""))
    required_unit = normalize_name(unit)

    
    # ---------------------------------------------------------
    # Interpret a raw <unit> placeholder as an individual
    # produce count only for explicitly supported foods.
    # ---------------------------------------------------------

    if (
        raw_unit == "<unit>"
        and required_unit in {
            "count",
            "piece",
            "pieces",
        }
        and target in WHOLE_PRODUCE_COUNT_INGREDIENTS
    ):
        raw_unit = required_unit


    # Count-family units must refer to the same physical unit.
    # For example, sprig -> sprig is valid,
    # but clove -> head is not.
    count_units = {
        "count", "piece", "pieces",
        "clove", "cloves",
        "head", "heads",
        "sprig", "sprigs",
        "stalk", "stalks",
    }

    singular = {
        "pieces": "piece",
        "cloves": "clove",
        "heads": "head",
        "sprigs": "sprig",
        "stalks": "stalk",
    }

    if raw_unit in count_units or required_unit in count_units:
        raw_normalized = singular.get(raw_unit, raw_unit)
        required_normalized = singular.get(
            required_unit, required_unit
        )

        if raw_normalized != required_normalized:
            return None

        ratio = required_quantity / raw_quantity

    else:
        raw_base = to_base(raw_quantity, raw_unit)
        required_base = to_base(
            required_quantity, required_unit
        )

        if raw_base is None or required_base is None:
            return None

        if raw_base[1] != required_base[1]:
            return None

        if raw_base[0] <= 0:
            return None

        ratio = required_base[0] / raw_base[0]

    estimated_grams = raw_weight * ratio

    if (
        not math.isfinite(estimated_grams)
        or estimated_grams <= 0
    ):
        return None

    return round(estimated_grams, 2), "g"
