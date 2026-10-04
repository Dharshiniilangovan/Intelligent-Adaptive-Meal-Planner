from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import json


# ============================================================
# CONFIGURATION
# ============================================================

USERS_DIR = Path("data/users")


# ============================================================
# SUPPORTED UNITS
# ============================================================
# These units should already be standardized by the
# ingredient normalization pipeline.

SUPPORTED_UNITS = {
    # Weight
    "mg",
    "g",
    "kg",
    "oz",
    "lb",

    # Volume
    "ml",
    "l",
    "cup",
    "tablespoon",
    "teaspoon",

    # Count / cooking units
    "count",
    "piece",
    "packet",
    "package",
    "slice",
    "clove",
    "sprig",
    "head",
    "bunch",
    "stalk",
    "leaf",
    "wedge",
    "stick",
    "can",
    "serving",
    "handful",
    "pinch",
    "dash",

    # Special
    "to taste",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def is_missing(value: Any) -> bool:
    """Check whether a value is missing."""

    if value is None:
        return True

    if isinstance(value, str):
        return value.strip().lower() in {
            "",
            "none",
            "nan",
            "required",
            "unknown",
            "na",
            "n/a",
        }

    try:
        return value != value
    except Exception:
        return False


def normalize_name(name: Any) -> str:
    """Normalize ingredient names for matching."""

    if name is None:
        return ""

    return " ".join(
        str(name).strip().lower().split()
    )


# ============================================================
# USER STATE LOADER
# ============================================================

def load_user_state(
    users_dir: str | Path = USERS_DIR
) -> Dict[str, Any]:
    """
    Load the most recently modified user_state_*.json
    from data/users/.
    """

    users_path = Path(users_dir)

    if not users_path.exists():
        raise FileNotFoundError(
            f"Users directory not found: {users_path}"
        )

    user_state_files = sorted(
        users_path.glob("user_state_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not user_state_files:
        raise FileNotFoundError(
            f"No user_state_*.json files found in {users_path}"
        )

    latest_file = user_state_files[0]

    try:
        with latest_file.open(
            "r",
            encoding="utf-8"
        ) as file:
            user_state = json.load(file)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid User State JSON: {latest_file}\n"
            f"{error}"
        ) from error

    if not isinstance(user_state, dict):
        raise ValueError(
            "User State JSON must contain an object"
        )

    print(f"Loaded User State: {latest_file}")

    return user_state


# ============================================================
# COOKING TIME
# ============================================================

def parse_cooking_time(
    value: Any
) -> Optional[float]:
    """
    Convert common cooking-time formats into minutes.

    Examples:
        25          -> 25
        "25 min"    -> 25
        "30 mins"   -> 30
        "2 hours"   -> 120
    """

    if is_missing(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()

    # Numeric string
    try:
        return float(text)
    except ValueError:
        pass

    parts = text.split()

    if len(parts) >= 2:

        try:
            number = float(parts[0])
        except ValueError:
            return None

        unit = parts[1]

        if unit.startswith("min"):
            return number

        if (
            unit.startswith("hour")
            or unit.startswith("hr")
        ):
            return number * 60

    return None


def get_user_cooking_time(
    user_state: Dict[str, Any]
) -> Optional[float]:
    """
    Read the user's cooking-time preference.

    User State field:
        cook_time_preference_hrs

    Example:
        2 -> 120 minutes
    """

    value = user_state.get(
        "cook_time_preference_hrs"
    )

    if is_missing(value):
        return None

    try:
        hours = float(value)
    except (TypeError, ValueError):
        return None

    if hours < 0:
        return None

    return hours * 60


def check_cooking_time(
    recipe_time: Any,
    user_state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Check recipe cooking time against user's preference.
    """

    recipe_minutes = parse_cooking_time(
        recipe_time
    )

    user_max_minutes = get_user_cooking_time(
        user_state
    )

    # Recipe time unavailable
    if recipe_minutes is None:
        return {
            "status": "unknown",
            "passed": None,
            "reason": "Cooking time unavailable"
        }

    # User preference unavailable
    if user_max_minutes is None:
        return {
            "status": "unknown",
            "passed": None,
            "reason": (
                "Cooking-time preference unavailable"
            )
        }

    # Pass
    if recipe_minutes <= user_max_minutes:
        return {
            "status": "pass",
            "passed": True,
            "reason": (
                f"Recipe time {recipe_minutes:g} min "
                f"is within user's {user_max_minutes:g} min limit"
            )
        }

    # Fail
    return {
        "status": "fail",
        "passed": False,
        "reason": (
            f"Recipe time {recipe_minutes:g} min "
            f"exceeds user's {user_max_minutes:g} min limit"
        )
    }


# ============================================================
# INGREDIENT FEASIBILITY
# ============================================================

def check_ingredient_feasibility(
    ingredients: Iterable[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Check whether recipe ingredient information is usable.

    This does not perform conversions.
    """

    ingredients = list(ingredients or [])

    issues: List[Dict[str, Any]] = []

    if not ingredients:
        return {
            "status": "unknown",
            "passed": None,
            "reason": "No recipe ingredients provided",
            "issues": []
        }

    for ingredient in ingredients:

        ingredient_id = ingredient.get(
            "ingredient_id"
        )

        ingredient_name = ingredient.get(
            "ingredient_name"
        )

        quantity = ingredient.get(
            "quantity"
        )

        if quantity is None:
            quantity = ingredient.get(
                "quantity_per_serving"
            )

        unit = ingredient.get("unit")

        # Missing ingredient ID
        if is_missing(ingredient_id):
            issues.append({
                "ingredient_name": ingredient_name,
                "issue": "missing_ingredient_id"
            })

        # Missing ingredient name
        if is_missing(ingredient_name):
            issues.append({
                "ingredient_id": ingredient_id,
                "issue": "missing_ingredient_name"
            })

        # Missing quantity
        if is_missing(quantity):
            issues.append({
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient_name,
                "issue": "missing_quantity"
            })

        # Missing unit
        if is_missing(unit):
            issues.append({
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient_name,
                "issue": "missing_unit"
            })
            continue

        unit = str(unit).strip().lower()

        # Unsupported unit
        if unit not in SUPPORTED_UNITS:
            issues.append({
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient_name,
                "unit": unit,
                "issue": "unsupported_unit"
            })

    if issues:
        return {
            "status": "unknown",
            "passed": None,
            "reason": (
                "Ingredient information cannot "
                "be fully evaluated"
            ),
            "issues": issues
        }

    return {
        "status": "pass",
        "passed": True,
        "reason": "Ingredient information is usable",
        "issues": []
    }


# ============================================================
# PANTRY FROM USER STATE
# ============================================================

def get_pantry_from_user_state(
    user_state: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extract user's pantry from:

        user_state["ingredient_availability"]

    Example:

        {
            "Tomatoes": "5 counts",
            "Cheese": "200 grams"
        }
    """

    availability = user_state.get(
        "ingredient_availability",
        {}
    )

    if not isinstance(availability, dict):
        return []

    pantry = []

    for ingredient_name, quantity_info in availability.items():

        pantry.append({
            "ingredient_name": ingredient_name,
            "quantity": quantity_info
        })

    return pantry


# ============================================================
# PANTRY QUANTITY PARSER
# ============================================================

def parse_pantry_quantity(
    value: Any
) -> tuple[Optional[float], Optional[str]]:
    """
    Parse pantry strings such as:

        "5 counts"
        "200 grams"
        "1 kg"
        "500 ml"

    Returns:

        quantity, unit
    """

    if is_missing(value):
        return None, None

    text = str(value).strip().lower()

    parts = text.split()

    if len(parts) < 2:
        return None, None

    try:
        quantity = float(parts[0])
    except ValueError:
        return None, None

    unit_text = " ".join(parts[1:])

    # Common pantry unit forms
    unit_aliases = {
        "mg": "mg",
        "milligram": "mg",
        "milligrams": "mg",

        "g": "g",
        "gram": "g",
        "grams": "g",
        "gm": "g",

        "kg": "kg",
        "kilogram": "kg",
        "kilograms": "kg",

        "ml": "ml",
        "milliliter": "ml",
        "milliliters": "ml",

        "l": "l",
        "liter": "l",
        "liters": "l",

        "count": "count",
        "counts": "count",

        "piece": "piece",
        "pieces": "piece",

        "packet": "packet",
        "packets": "packet",

        "package": "package",
        "packages": "package",
    }

    unit = unit_aliases.get(unit_text)

    if unit is None:
        return None, None

    return quantity, unit


# ============================================================
# QUANTITY CONVERSION FOR PANTRY COMPARISON
# ============================================================

def convert_to_base_quantity(
    quantity: float,
    unit: str
) -> tuple[float, str]:
    """
    Convert only directly comparable units.

    Weight:
        mg -> g
        kg -> g

    Volume:
        l -> ml

    Count:
        piece -> count

    No ingredient-specific assumptions are made.
    """

    unit = unit.lower()

    # Weight
    if unit == "mg":
        return quantity / 1000, "g"

    if unit == "kg":
        return quantity * 1000, "g"

    if unit in {"g", "oz", "lb"}:
        return quantity, unit

    # Volume
    if unit == "l":
        return quantity * 1000, "ml"

    if unit == "ml":
        return quantity, "ml"

    # Count
    if unit == "piece":
        return quantity, "count"

    if unit == "count":
        return quantity, "count"

    # Other units remain unchanged
    return quantity, unit


# ============================================================
# MISSING INGREDIENTS
# ============================================================

def calculate_ingredient_availability(
    ingredients: Iterable[Dict[str, Any]],
    pantry: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Compare recipe-required ingredients with user pantry.

    Returns:

        already_available
        missing_ingredients
    """

    ingredients = list(ingredients or [])

    # --------------------------------------------------------
    # Create pantry lookup
    # --------------------------------------------------------

    pantry_lookup = {}

    for item in pantry:

        name = normalize_name(
            item.get("ingredient_name")
        )

        if not name:
            continue

        quantity, unit = parse_pantry_quantity(
            item.get("quantity")
        )

        pantry_lookup[name] = {
            "quantity": quantity,
            "unit": unit
        }

    # --------------------------------------------------------
    # Results
    # --------------------------------------------------------

    already_available = []
    missing_ingredients = []

    # --------------------------------------------------------
    # Compare every recipe ingredient
    # --------------------------------------------------------

    for ingredient in ingredients:

        ingredient_id = ingredient.get(
            "ingredient_id"
        )

        ingredient_name = ingredient.get(
            "ingredient_name"
        )

        recipe_quantity = ingredient.get(
            "quantity"
        )

        if recipe_quantity is None:
            recipe_quantity = ingredient.get(
                "quantity_per_serving"
            )

        recipe_unit = ingredient.get(
            "unit"
        )

        recipe_name_normalized = normalize_name(
            ingredient_name
        )

        # ----------------------------------------------------
        # Ingredient not in pantry
        # ----------------------------------------------------

        if recipe_name_normalized not in pantry_lookup:

            missing_ingredients.append({
                "ingredient_id":
                    ingredient_id,

                "ingredient_name":
                    ingredient_name,

                "required_quantity":
                    recipe_quantity,

                "missing_quantity":
                    recipe_quantity,

                "unit":
                    recipe_unit,

                "reason":
                    "Ingredient not available in pantry"
            })

            continue

        # ----------------------------------------------------
        # Pantry information
        # ----------------------------------------------------

        pantry_item = pantry_lookup[
            recipe_name_normalized
        ]

        pantry_quantity = pantry_item[
            "quantity"
        ]

        pantry_unit = pantry_item[
            "unit"
        ]

        # ----------------------------------------------------
        # Cannot compare pantry quantity
        # ----------------------------------------------------

        if (
            pantry_quantity is None
            or pantry_unit is None
        ):

            missing_ingredients.append({
                "ingredient_id":
                    ingredient_id,

                "ingredient_name":
                    ingredient_name,

                "required_quantity":
                    recipe_quantity,

                "missing_quantity":
                    "required",

                "unit":
                    recipe_unit,

                "reason":
                    "Pantry quantity cannot be interpreted"
            })

            continue

        # ----------------------------------------------------
        # Missing recipe quantity
        # ----------------------------------------------------

        if is_missing(recipe_quantity):

            missing_ingredients.append({
                "ingredient_id":
                    ingredient_id,

                "ingredient_name":
                    ingredient_name,

                "required_quantity":
                    "required",

                "missing_quantity":
                    "required",

                "unit":
                    recipe_unit,

                "reason":
                    "Recipe quantity unavailable"
            })

            continue

        # ----------------------------------------------------
        # Normalize recipe quantity
        # ----------------------------------------------------

        try:
            recipe_quantity_number = float(
                recipe_quantity
            )
        except (TypeError, ValueError):

            missing_ingredients.append({
                "ingredient_id":
                    ingredient_id,

                "ingredient_name":
                    ingredient_name,

                "required_quantity":
                    recipe_quantity,

                "missing_quantity":
                    "required",

                "unit":
                    recipe_unit,

                "reason":
                    "Recipe quantity cannot be interpreted"
            })

            continue

        # ----------------------------------------------------
        # Normalize units for comparison
        # ----------------------------------------------------

        recipe_unit_clean = str(
            recipe_unit
        ).strip().lower()

        recipe_base_quantity, recipe_base_unit = (
            convert_to_base_quantity(
                recipe_quantity_number,
                recipe_unit_clean
            )
        )

        pantry_base_quantity, pantry_base_unit = (
            convert_to_base_quantity(
                pantry_quantity,
                pantry_unit
            )
        )

        # ----------------------------------------------------
        # Units cannot be compared
        # ----------------------------------------------------

        if recipe_base_unit != pantry_base_unit:

            missing_ingredients.append({
                "ingredient_id":
                    ingredient_id,

                "ingredient_name":
                    ingredient_name,

                "required_quantity":
                    recipe_quantity,

                "missing_quantity":
                    recipe_quantity,

                "unit":
                    recipe_unit,

                "reason":
                    (
                        f"Cannot compare recipe unit "
                        f"{recipe_unit} with pantry unit "
                        f"{pantry_unit}"
                    )
            })

            continue

        # ----------------------------------------------------
        # Enough quantity available
        # ----------------------------------------------------

        if pantry_base_quantity >= recipe_base_quantity:

            already_available.append({

                "ingredient_id":
                    ingredient_id,

                "ingredient_name":
                    ingredient_name,

                "required_quantity":
                    recipe_quantity,

                "available_quantity":
                    pantry_item["quantity"],

                "unit":
                    recipe_unit,

                "status":
                    "enough"
            })

        # ----------------------------------------------------
        # Partial quantity available
        # ----------------------------------------------------

        else:

            missing_quantity = (
                recipe_base_quantity
                - pantry_base_quantity
            )

            # Round cleanly
            if missing_quantity.is_integer():
                missing_quantity = int(
                    missing_quantity
                )

            missing_ingredients.append({

                "ingredient_id":
                    ingredient_id,

                "ingredient_name":
                    ingredient_name,

                "required_quantity":
                    recipe_quantity,

                "available_quantity":
                    pantry_item["quantity"],

                "missing_quantity":
                    missing_quantity,

                "unit":
                    recipe_base_unit,

                "reason":
                    "Insufficient quantity in pantry"
            })

    return {
        "already_available":
            already_available,

        "missing_ingredients":
            missing_ingredients
    }


# ============================================================
# PANTRY UTILIZATION
# ============================================================

def calculate_pantry_utilization(
    ingredients: Iterable[Dict[str, Any]],
    pantry: List[Dict[str, Any]]
) -> float:
    """
    MVP pantry utilization:

        ingredients available in pantry
        -------------------------------
        total required ingredients
    """

    ingredients = list(ingredients or [])

    if not ingredients:
        return 0.0

    pantry_names = {
        normalize_name(
            item.get("ingredient_name")
        )
        for item in pantry
        if not is_missing(
            item.get("ingredient_name")
        )
    }

    available_count = 0

    for ingredient in ingredients:

        ingredient_name = normalize_name(
            ingredient.get(
                "ingredient_name"
            )
        )

        if ingredient_name in pantry_names:
            available_count += 1

    return round(
        available_count / len(ingredients),
        2
    )


# ============================================================
# MAIN MEMBER 3 FUNCTION
# ============================================================

def evaluate_recipe(
    candidate_recipe: Dict[str, Any],
    user_state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Plug-and-play Member 3 interface.

    Inputs:
        candidate_recipe
        user_state

    Outputs:
        cooking-time result
        ingredient feasibility
        pantry utilization
        already available ingredients
        missing ingredients
    """

    if not isinstance(
        candidate_recipe,
        dict
    ):
        raise TypeError(
            "candidate_recipe must be a dictionary"
        )

    if not isinstance(
        user_state,
        dict
    ):
        raise TypeError(
            "user_state must be a dictionary"
        )

    # --------------------------------------------------------
    # Get recipe ingredients
    # --------------------------------------------------------

    ingredients = candidate_recipe.get(
        "ingredients",
        []
    )

    if not isinstance(
        ingredients,
        list
    ):
        raise ValueError(
            "candidate_recipe['ingredients'] "
            "must be a list"
        )

    # --------------------------------------------------------
    # Get user's pantry
    # --------------------------------------------------------

    pantry = get_pantry_from_user_state(
        user_state
    )

    # --------------------------------------------------------
    # 1. Cooking-time constraint
    # --------------------------------------------------------

    time_result = check_cooking_time(
        candidate_recipe.get(
            "cooking_time_min"
        ),
        user_state
    )

    # --------------------------------------------------------
    # 2. Ingredient feasibility
    # --------------------------------------------------------

    ingredient_result = (
        check_ingredient_feasibility(
            ingredients
        )
    )

    # --------------------------------------------------------
    # 3. Pantry utilization
    # --------------------------------------------------------

    pantry_score = (
        calculate_pantry_utilization(
            ingredients,
            pantry
        )
    )

    # --------------------------------------------------------
    # 4. Already available / missing ingredients
    # --------------------------------------------------------

    availability_result = (
        calculate_ingredient_availability(
            ingredients,
            pantry
        )
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    return {

        "recipe_id":
            candidate_recipe.get(
                "recipe_id"
            ),

        "recipe_name":
            candidate_recipe.get(
                "recipe_name"
            ),

        "time_constraint":
            time_result,

        "ingredient_feasibility":
            ingredient_result,

        "pantry_utilization":
            pantry_score,

        "already_available":
            availability_result[
                "already_available"
            ],

        "missing_ingredients":
            availability_result[
                "missing_ingredients"
            ]
    }


# ============================================================
# DUMMY TEST
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Dummy Candidate Recipe
    #
    # Later this will come from the real workflow.
    # --------------------------------------------------------

    candidate_recipe = {

        "recipe_id":
            "R001",

        "recipe_name":
            "Tomato Cheese Rice",

        # Dummy cooking time for now
        "cooking_time_min":
            25,

        "ingredients": [

            {
                "ingredient_id":
                    "ING001",

                "ingredient_name":
                    "Tomatoes",

                "quantity":
                    2,

                "unit":
                    "count"
            },

            {
                "ingredient_id":
                    "ING002",

                "ingredient_name":
                    "Cheese",

                "quantity":
                    100,

                "unit":
                    "g"
            },

            {
                "ingredient_id":
                    "ING003",

                "ingredient_name":
                    "Rice",

                "quantity":
                    300,

                "unit":
                    "g"
            }
        ]
    }

    # --------------------------------------------------------
    # Load actual User State JSON
    # --------------------------------------------------------

    user_state = load_user_state(
        USERS_DIR
    )

    # --------------------------------------------------------
    # Run Member 3
    # --------------------------------------------------------

    result = evaluate_recipe(
        candidate_recipe,
        user_state
    )

    print(
        "\n Result:"
    )

    print(
        json.dumps(
            result,
            indent=2
        )
    )