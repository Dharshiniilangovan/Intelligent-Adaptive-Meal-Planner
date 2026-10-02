import sys
import os
import json
import math
from pathlib import Path

sys.path.append(
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
)

import scripts.mapping_retrieval_query


BASE_DIR = Path(__file__).resolve().parent.parent.parent
PANTRY_FILE = BASE_DIR / "data" / "sample" / "pantry.json"


def normalize_name(name):
    """Normalize ingredient names for comparison."""
    return str(name).strip().lower()


def normalize_unit(unit):
    """
    Normalize unit formatting only.

    Actual unit conversion such as kg -> g
    will be handled by the normalization layer.
    """
    return str(unit).strip().lower()


def is_unknown_quantity(quantity):
    """Check whether quantity is missing/NaN."""
    if quantity is None:
        return True

    try:
        return math.isnan(float(quantity))
    except (TypeError, ValueError):
        return False


def load_pantry():
    """Load pantry data from JSON."""

    if not PANTRY_FILE.exists():
        raise FileNotFoundError(
            f"Pantry file not found: {PANTRY_FILE}"
        )

    with open(PANTRY_FILE, "r") as file:
        return json.load(file)


def examine_pantry(pantry_data):
    """
    Convert pantry JSON into a dictionary indexed
    by normalized ingredient name.
    """

    if not isinstance(pantry_data, dict):
        raise ValueError("Pantry data should be a dictionary.")

    if "items" not in pantry_data:
        raise ValueError("Pantry data must contain an 'items' list.")

    return {
        normalize_name(item["name"]): {
            "quantity": item["quantity"],
            "unit": normalize_unit(item["unit"])
        }
        for item in pantry_data["items"]
    }


def fetch_recipe_ingredients(recipe_id):
    """
    Retrieve recipe ingredients and convert them
    into a dictionary indexed by ingredient name.
    """

    df = scripts.mapping_retrieval_query.get_recipe_ingredients(
        recipe_id
    )

    if df.empty:
        return {}

    return {
        normalize_name(row["ingredient_name"]): {
            "quantity": row["quantity"],
            "unit": normalize_unit(row["unit"])
        }
        for _, row in df.iterrows()
    }


def filter_ingredient_list(pantry_data, ingredient_names):
    """
    Compare recipe requirements with pantry contents.

    Returns only ingredients that need to be purchased.
    """

    if not isinstance(pantry_data, dict):
        raise ValueError("Pantry data should be a dictionary.")

    if not isinstance(ingredient_names, dict):
        raise ValueError(
            "Ingredient names should be a dictionary."
        )

    grocery_list = {}

    ingredients_not_in_pantry = (
        ingredient_names.keys() - pantry_data.keys()
    )

    ingredients_in_pantry = (
        ingredient_names.keys() & pantry_data.keys()
    )

    # -----------------------------------------
    # Ingredients completely missing
    # -----------------------------------------

    for ingredient in ingredients_not_in_pantry:

        required = ingredient_names[ingredient]["quantity"]
        required_unit = ingredient_names[ingredient]["unit"]

        if is_unknown_quantity(required):
            grocery_list[ingredient] = {
                "quantity": None,
                "unit": required_unit,
                "status": "quantity_unknown"
            }
        else:
            grocery_list[ingredient] = {
                "quantity": required,
                "unit": required_unit
            }

    # -----------------------------------------
    # Ingredients already present in pantry
    # -----------------------------------------

    for ingredient in ingredients_in_pantry:

        required = ingredient_names[ingredient]["quantity"]
        required_unit = ingredient_names[ingredient]["unit"]

        available = pantry_data[ingredient]["quantity"]
        pantry_unit = pantry_data[ingredient]["unit"]

        # Unknown recipe quantity
        if is_unknown_quantity(required):
            grocery_list[ingredient] = {
                "quantity": None,
                "unit": required_unit,
                "status": "quantity_unknown"
            }
            continue

        # Units must be converted before pantry subtraction
        if required_unit != pantry_unit:
            grocery_list[ingredient] = {
                "quantity": required,
                "unit": required_unit,
                "status": "unit_mismatch"
            }
            continue

        missing_quantity = max(
            float(required) - float(available),
            0
        )

        # Only add if something needs to be purchased
        if missing_quantity > 0:
            grocery_list[ingredient] = {
                "quantity": missing_quantity,
                "unit": required_unit
            }

    return grocery_list


if __name__ == "__main__":

    recipe_id = "R02533"

    ingredients = fetch_recipe_ingredients(recipe_id)
    pantry = examine_pantry(load_pantry())

    grocery_list = filter_ingredient_list(
        pantry,
        ingredients
    )

    print(f"\nRecipe: {recipe_id}")

    print("\nRequired Ingredients:")
    print(ingredients)

    print("\nPantry:")
    print(pantry)

    print("\nFinal Grocery List:")
    print(grocery_list)