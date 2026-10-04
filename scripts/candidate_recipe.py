import ast
from pathlib import Path

import pandas as pd
from src.knowledge.repository import normalize


# ============================================================
# FILE PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

RECIPE_KB_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "recipe_kb_clean.csv"
)


# ============================================================
# LOAD RECIPE KB
# ============================================================

def load_recipe_kb(recipe_file=RECIPE_KB_FILE):
    """
    Load the Recipe Knowledge Base.
    """

    if not recipe_file.exists():
        raise FileNotFoundError(
            f"Recipe KB file not found: {recipe_file}"
        )

    df = pd.read_csv(recipe_file)

    # Clean column names
    df.columns = df.columns.str.strip()

    if "recipe_id" not in df.columns:
        raise ValueError(
            "Recipe KB must contain a 'recipe_id' column."
        )

    # Clean recipe IDs
    df["recipe_id"] = (
        df["recipe_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    return df


# ============================================================
# HELPER FUNCTION
# ============================================================

def _contains_label(value, target):
    """
    Check whether a list-like or string column contains
    the requested label.
    """

    if pd.isna(value):
        return False

    target = normalize(target)

    if not target:
        return False

    if isinstance(value, str):
        try:
            parsed_value = ast.literal_eval(value)

            if isinstance(parsed_value, list):
                return any(
                    normalize(item) == target
                    for item in parsed_value
                )

        except (ValueError, SyntaxError):
            pass

    return normalize(value) == target

# ============================================================
# FILTER BY DIET
# ============================================================

def filter_by_diet(df, diet):
    """
    Filter recipes using both diet_labels and health_labels.

    This allows requirements such as:
        Vegetarian
        Vegan
        Low-Carb
        High-Protein
        etc.
    """

    if diet is None or not str(diet).strip():
        return df.copy()

    mask = pd.Series(False, index=df.index)

    if "diet_labels" in df.columns:
        mask |= df["diet_labels"].apply(
            lambda value: _contains_label(value, diet)
        )

    if "health_labels" in df.columns:
        mask |= df["health_labels"].apply(
            lambda value: _contains_label(value, diet)
        )

    return df[mask].copy()


# ============================================================
# FILTER BY HEALTH LABEL
# ============================================================

def filter_by_health_label(df, health_label):
    """
    Filter recipes by a health label.

    Example:
        Vegetarian
        Vegan
        Gluten-Free
    """

    if health_label is None or not str(health_label).strip():
        return df.copy()

    if "health_labels" not in df.columns:
        raise ValueError(
            "Recipe KB does not contain 'health_labels'."
        )

    mask = df["health_labels"].apply(
        lambda value: _contains_label(value, health_label)
    )

    return df[mask].copy()


# ============================================================
# FILTER BY MEAL TYPE
# ============================================================

def filter_by_meal_type(df, meal_type):
    """
    Filter recipes by meal type.
    """

    if meal_type is None or not str(meal_type).strip():
        return df.copy()

    if "meal_type" not in df.columns:
        raise ValueError(
            "Recipe KB does not contain 'meal_type'."
        )

    # Handles input such as "lunch/dinner"
    requested_types = [
        normalize(item)
        for item in str(meal_type).split("/")
    ]

    def matches(value):

        if pd.isna(value):
            return False

        try:
            parsed_value = ast.literal_eval(value)

            if isinstance(parsed_value, list):
                recipe_types = [
                    normalize(item)
                    for item in parsed_value
                ]

                return any(
                    meal in recipe_types
                    for meal in requested_types
                )

        except (ValueError, SyntaxError):
            pass

        return normalize(value) in requested_types

    mask = df["meal_type"].apply(matches)

    return df[mask].copy()


# ============================================================
# FILTER BY CUISINE
# ============================================================

def filter_by_cuisine(df, cuisine):
    """
    Filter recipes by cuisine.
    """

    if cuisine is None or not str(cuisine).strip():
        return df.copy()
    if df.empty:
        return df.copy()

    if "cuisine_type" not in df.columns:
        raise ValueError(
            "Recipe KB does not contain 'cuisine_type'."
        )

    mask = df["cuisine_type"].apply(
        lambda value: _contains_label(value, cuisine)
    )

    return df[mask].copy()


# ============================================================
# FILTER BY CALORIE RANGE
# ============================================================

def filter_by_calorie_range(
    df,
    min_calories=None,
    max_calories=None
):
    """
    Filter recipes by calories per serving.
    """

    if min_calories is None and max_calories is None:
        return df.copy()

    if "calories_per_serving" not in df.columns:
        raise ValueError(
            "Recipe KB does not contain "
            "'calories_per_serving'."
        )

    result = df.copy()

    result["calories_per_serving"] = pd.to_numeric(
        result["calories_per_serving"],
        errors="coerce"
    )

    if min_calories is not None:
        result = result[
            result["calories_per_serving"]
            >= float(min_calories)
        ]

    if max_calories is not None:
        result = result[
            result["calories_per_serving"]
            <= float(max_calories)
        ]

    return result.copy()


# ============================================================
# RETRIEVE CANDIDATE RECIPES
# ============================================================

def retrieve_candidates(
    diet=None,
    health_label=None,
    meal_type=None,
    cuisine=None,
    min_calories=None,
    max_calories=None,
    recipe_file=RECIPE_KB_FILE
):
    """
    Retrieve candidate recipes based on user requirements.

    All provided constraints are applied together.

    Returns:
        DataFrame containing eligible candidate recipes.
    """

    df = load_recipe_kb(recipe_file)

    # Diet constraint
    df = filter_by_diet(
        df,
        diet
    )

    # Health-label constraint
    df = filter_by_health_label(
        df,
        health_label
    )

    # Meal-type constraint
    df = filter_by_meal_type(
        df,
        meal_type
    )

    # Cuisine constraint
    df = filter_by_cuisine(
        df,
        cuisine
    )

    # Calorie constraint
    df = filter_by_calorie_range(
        df,
        min_calories,
        max_calories
    )

    # ========================================================
    # OUTPUT COLUMNS
    # ========================================================

    output_columns = [
        "recipe_id",
        "recipe_name",

        "diet_labels",
        "health_labels",
        "cautions",

        "cuisine_type",
        "meal_type",
        "dish_type",


    ]

    output_columns = [
        column
        for column in output_columns
        if column in df.columns
    ]

    return df[output_columns].reset_index(drop=True)
