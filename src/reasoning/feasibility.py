from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


# ============================================================
# SUPPORTED UNITS
# ============================================================
# These units are expected to already be standardized
# by the ingredient normalization pipeline.

SUPPORTED_UNITS = {
    # Weight
    "g",
    "kg",
    "mg",
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
    """
    Check whether a value is missing.
    """

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
        return value != value  # NaN
    except Exception:
        return False


# ============================================================
# COOKING TIME
# ============================================================

def parse_cooking_time(value: Any) -> Optional[float]:
    """
    Convert common cooking-time values into minutes.

    Examples:
        25          -> 25
        "25 min"    -> 25
        "1 hour"    -> 60
        "1.5 hours" -> 90

    Returns None if unavailable/unrecognized.
    """

    if is_missing(value):
        return None

    # Already numeric
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()

    # Plain numeric string
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

        if unit.startswith("hour") or unit.startswith("hr"):
            return number * 60

    return None


def check_cooking_time(
    recipe_time: Any,
    max_cooking_time: Any
) -> Dict[str, Any]:
    """
    Check whether recipe cooking time satisfies
    the user's maximum cooking-time constraint.
    """

    recipe_minutes = parse_cooking_time(recipe_time)

    # Recipe cooking time is unavailable
    if recipe_minutes is None:

        return {
            "status": "unknown",
            "passed": None,
            "reason": "Cooking time unavailable"
        }

    # User did not specify a cooking-time limit
    if is_missing(max_cooking_time):

        return {
            "status": "pass",
            "passed": True,
            "reason": "No cooking-time constraint specified"
        }

    max_minutes = parse_cooking_time(max_cooking_time)

    # User's maximum time cannot be interpreted
    if max_minutes is None:

        return {
            "status": "unknown",
            "passed": None,
            "reason": "Maximum cooking time unavailable"
        }

    # Hard constraint
    if recipe_minutes <= max_minutes:

        return {
            "status": "pass",
            "passed": True,
            "reason": (
                f"Recipe time {recipe_minutes:g} min is within "
                f"the {max_minutes:g} min limit"
            )
        }

    return {
        "status": "fail",
        "passed": False,
        "reason": (
            f"Recipe time {recipe_minutes:g} min exceeds "
            f"the {max_minutes:g} min limit"
        )
    }


# ============================================================
# INGREDIENT FEASIBILITY
# ============================================================

def check_ingredient_feasibility(
    ingredients: Iterable[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Check whether ingredient information is usable.

    This function DOES NOT perform conversions.

    It only checks:
        - ingredient ID
        - ingredient name
        - quantity
        - unit
        - supported unit
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

        ingredient_id = ingredient.get("ingredient_id")
        ingredient_name = ingredient.get("ingredient_name")

        # ----------------------------------------------------
        # Quantity
        # ----------------------------------------------------

        # Support both:
        # quantity
        # quantity_per_serving

        quantity = ingredient.get("quantity")

        if quantity is None:
            quantity = ingredient.get("quantity_per_serving")

        # Missing quantity
        if is_missing(quantity):

            issues.append({
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient_name,
                "issue": "missing_quantity"
            })

        # ----------------------------------------------------
        # Ingredient ID
        # ----------------------------------------------------

        if is_missing(ingredient_id):

            issues.append({
                "ingredient_name": ingredient_name,
                "issue": "missing_ingredient_id"
            })

        # ----------------------------------------------------
        # Ingredient name
        # ----------------------------------------------------

        if is_missing(ingredient_name):

            issues.append({
                "ingredient_id": ingredient_id,
                "issue": "missing_ingredient_name"
            })

        # ----------------------------------------------------
        # Unit
        # ----------------------------------------------------

        unit = ingredient.get("unit")

        if is_missing(unit):

            issues.append({
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient_name,
                "issue": "missing_unit"
            })

            continue

        unit = str(unit).strip().lower()

        # ----------------------------------------------------
        # Unsupported unit
        # ----------------------------------------------------

        if unit not in SUPPORTED_UNITS:

            issues.append({
                "ingredient_id": ingredient_id,
                "ingredient_name": ingredient_name,
                "unit": unit,
                "issue": "unsupported_unit"
            })

    # --------------------------------------------------------
    # Return result
    # --------------------------------------------------------

    if issues:

        return {
            "status": "unknown",
            "passed": None,
            "reason": (
                "Ingredient information cannot be fully evaluated"
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
# PANTRY UTILIZATION
# ============================================================

def calculate_pantry_utilization(
    ingredients: Iterable[Dict[str, Any]],
    pantry: Any
) -> float:
    """
    MVP pantry utilization:

        available ingredients
        ---------------------
        total required ingredients

    Ingredient ID is preferred.

    Pantry can be:

        [
            {...},
            {...}
        ]

    OR:

        {
            "items": [...]
        }
    """

    ingredients = list(ingredients or [])

    if not ingredients:
        return 0.0

    # --------------------------------------------------------
    # Accept different pantry structures
    # --------------------------------------------------------

    if isinstance(pantry, dict):

        pantry_items = pantry.get("items", [])

        if not isinstance(pantry_items, list):
            pantry_items = []

    elif isinstance(pantry, list):

        pantry_items = pantry

    else:

        pantry_items = []

    # --------------------------------------------------------
    # Pantry ingredient IDs
    # --------------------------------------------------------

    pantry_ids = set()

    for item in pantry_items:

        ingredient_id = item.get("ingredient_id")

        if not is_missing(ingredient_id):

            pantry_ids.add(
                str(ingredient_id).strip().upper()
            )

    # --------------------------------------------------------
    # Pantry ingredient names
    # --------------------------------------------------------

    pantry_names = set()

    for item in pantry_items:

        name = item.get("ingredient_name")

        if is_missing(name):
            name = item.get("name")

        if not is_missing(name):

            pantry_names.add(
                str(name).strip().lower()
            )

    # --------------------------------------------------------
    # Count available ingredients
    # --------------------------------------------------------

    available_count = 0

    for ingredient in ingredients:

        ingredient_id = ingredient.get(
            "ingredient_id"
        )

        ingredient_name = ingredient.get(
            "ingredient_name"
        )

        id_match = False
        name_match = False

        if not is_missing(ingredient_id):

            id_match = (
                str(ingredient_id)
                .strip()
                .upper()
                in pantry_ids
            )

        if not is_missing(ingredient_name):

            name_match = (
                str(ingredient_name)
                .strip()
                .lower()
                in pantry_names
            )

        if id_match or name_match:
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
    user_state: Dict[str, Any],
    pantry: Any
) -> Dict[str, Any]:
    """
    Plug-and-play Member 3 interface.

    INPUT
    -----

    candidate_recipe:
        Candidate recipe JSON from the workflow.

    user_state:
        User requirements / current user state.

    pantry:
        Pantry data.

    OUTPUT
    ------

    Standardized Member 3 result.
    """

    if not isinstance(candidate_recipe, dict):

        raise TypeError(
            "candidate_recipe must be a dictionary"
        )

    if not isinstance(user_state, dict):

        raise TypeError(
            "user_state must be a dictionary"
        )

    # --------------------------------------------------------
    # Get ingredients
    # --------------------------------------------------------

    ingredients = candidate_recipe.get(
        "ingredients",
        []
    )

    if not isinstance(ingredients, list):

        raise ValueError(
            "candidate_recipe['ingredients'] "
            "must be a list"
        )

    # --------------------------------------------------------
    # Get cooking-time constraint
    # --------------------------------------------------------

    max_cooking_time = user_state.get(
        "max_cooking_time"
    )

    # Also support future structure:
    #
    # "schedule": {
    #     "max_cooking_time": 30
    # }

    if max_cooking_time is None:

        schedule = user_state.get(
            "schedule",
            {}
        )

        if isinstance(schedule, dict):

            max_cooking_time = schedule.get(
                "max_cooking_time"
            )

    # --------------------------------------------------------
    # 1. Cooking-time check
    # --------------------------------------------------------

    time_result = check_cooking_time(
        candidate_recipe.get(
            "cooking_time_min"
        ),
        max_cooking_time
    )

    # --------------------------------------------------------
    # 2. Ingredient feasibility
    # --------------------------------------------------------

    ingredient_result = check_ingredient_feasibility(
        ingredients
    )

    # --------------------------------------------------------
    # 3. Pantry utilization
    # --------------------------------------------------------

    pantry_score = calculate_pantry_utilization(
        ingredients,
        pantry
    )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    return {

        "recipe_id":
            candidate_recipe.get("recipe_id"),

        "recipe_name":
            candidate_recipe.get("recipe_name"),

        "time_constraint":
            time_result,

        "ingredient_feasibility":
            ingredient_result,

        "pantry_utilization":
            pantry_score
    }


# ============================================================
# DUMMY TEST
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # Dummy candidate recipe
    #
    # This represents the JSON that will eventually come
    # from the real workflow.
    # --------------------------------------------------------

    candidate_recipe = {

        "recipe_id":
            "R001",

        "recipe_name":
            "Tofu Fried Rice",

        # Dummy cooking time 
        "cooking_time_min":
            25,

        "ingredients": [

            {
                "ingredient_id":
                    "ING001",

                "ingredient_name":
                    "rice",

                "quantity":
                    500,

                "unit":
                    "g"
            },

            {
                "ingredient_id":
                    "ING002",

                "ingredient_name":
                    "tofu",

                "quantity":
                    300,

                "unit":
                    "g"
            },

            {
                "ingredient_id":
                    "ING003",

                "ingredient_name":
                    "carrot",

                "quantity":
                    100,

                "unit":
                    "g"
            }
        ]
    }

    # --------------------------------------------------------
    # Dummy user state
    # --------------------------------------------------------

    user_state = {

        "max_cooking_time":
            30
    }

    # --------------------------------------------------------
    # Dummy pantry
    # --------------------------------------------------------

    pantry = [

        {
            "ingredient_id":
                "ING001",

            "ingredient_name":
                "rice",

            "quantity":
                700,

            "unit":
                "g"
        },

        {
            "ingredient_id":
                "ING003",

            "ingredient_name":
                "carrot",

            "quantity":
                100,

            "unit":
                "g"
        }
    ]

    # --------------------------------------------------------
    # Run Member 3
    # --------------------------------------------------------

    result = evaluate_recipe(
        candidate_recipe,
        user_state,
        pantry
    )

    # Pretty JSON output
    import json

    print(
        json.dumps(
            result,
            indent=2
        )
    )