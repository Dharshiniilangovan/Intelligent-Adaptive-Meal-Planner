import re
from pathlib import Path

import pandas as pd


# ============================================================
# FILE PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

MAPPING_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "recipe_ingredient_mapping.csv"
)

RECIPE_ID_PATTERN = re.compile(r"^R\d{5}$")


# ============================================================
# VALIDATE RECIPE ID
# ============================================================

def validate_recipe_id(recipe_id):
    """
    Validate recipe ID format.

    Expected format:
        R followed by 5 digits

    Examples:
        R03943 -> Valid
        R00001 -> Valid
        ABC    -> Invalid
        R39    -> Invalid
    """

    if recipe_id is None:
        return False

    recipe_id = str(recipe_id).strip().upper()

    if not recipe_id:
        return False

    return bool(RECIPE_ID_PATTERN.fullmatch(recipe_id))


# ============================================================
# GENERIC QUERY FUNCTION
# ============================================================

def query_by_id(df, column_name, query_id):
    """
    Query a DataFrame using a specified ID column.
    """

    if column_name not in df.columns:
        raise ValueError(
            f"Column '{column_name}' not found in the dataset."
        )

    query_id = str(query_id).strip().upper()

    return df[
        df[column_name]
        .astype(str)
        .str.strip()
        .str.upper()
        == query_id
    ].copy()


# ============================================================
# GET RECIPE INGREDIENTS
# ============================================================

def get_recipe_ingredients(recipe_id):
    """
    Retrieve all ingredients belonging to a recipe ID.

    Parameters:
        recipe_id (str):
            Recipe ID in the format R followed by 5 digits.

    Returns:
        pandas.DataFrame:
            Rows belonging to the requested recipe.
            Returns an empty DataFrame if the recipe does not exist.

    Raises:
        ValueError:
            If the recipe ID format is invalid.

        FileNotFoundError:
            If the mapping file does not exist.
    """

    # Normalize recipe ID
    recipe_id = str(recipe_id).strip().upper()

    # Validate recipe ID
    if not validate_recipe_id(recipe_id):
        raise ValueError(
            f"Invalid Recipe ID: {recipe_id}. "
            "Expected format: R followed by 5 digits "
            "(example: R03943)."
        )

    # Check mapping file
    if not MAPPING_FILE.exists():
        raise FileNotFoundError(
            f"Mapping file not found: {MAPPING_FILE}"
        )

    # Load mapping
    df = pd.read_csv(MAPPING_FILE)

    # Clean column names
    df.columns = df.columns.str.strip()

    # Check required column
    if "recipe_id" not in df.columns:
        raise ValueError(
            "Mapping file must contain a 'recipe_id' column."
        )

    # Query recipe
    return query_by_id(
        df=df,
        column_name="recipe_id",
        query_id=recipe_id
    )