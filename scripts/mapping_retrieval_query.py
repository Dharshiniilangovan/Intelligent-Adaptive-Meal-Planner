import pandas as pd
from pathlib import Path
import re


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


# ============================================================
# GENERIC QUERY FUNCTION
# ============================================================

def query_by_id(df, column_name, query_id):
    """
    Generic function to query a dataframe using an ID.
    """

    if column_name not in df.columns:
        raise ValueError(
            f"Column '{column_name}' not found in the dataset."
        )

    query_id = str(query_id).strip().upper()

    result = df[
        df[column_name]
        .astype(str)
        .str.strip()
        .str.upper()
        == query_id
    ]

    return result


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

        3943   -> Invalid
        ABC    -> Invalid
        R39    -> Invalid
        R123456 -> Invalid
    """

    if recipe_id is None:
        return False

    recipe_id = str(recipe_id).strip().upper()

    if not recipe_id:
        return False

    pattern = r"^R\d{5}$"

    return bool(re.fullmatch(pattern, recipe_id))


# ============================================================
# RECIPE QUERY
# ============================================================

def get_recipe_ingredients(recipe_id):
    """
    Retrieve all ingredients belonging to a recipe ID.

    Returns:
        DataFrame if recipe exists.
        Empty DataFrame if recipe does not exist.
    """

    # --------------------------------------------------------
    # Check mapping file exists
    # --------------------------------------------------------

    if not MAPPING_FILE.exists():
        raise FileNotFoundError(
            f"Mapping file not found:\n{MAPPING_FILE}"
        )

    # --------------------------------------------------------
    # Load mapping
    # --------------------------------------------------------

    df = pd.read_csv(MAPPING_FILE)

    # Clean column names
    df.columns = df.columns.str.strip()

    # --------------------------------------------------------
    # Check recipe_id column
    # --------------------------------------------------------

    if "recipe_id" not in df.columns:
        raise ValueError(
            "The mapping file does not contain "
            "a 'recipe_id' column."
        )

    # --------------------------------------------------------
    # Query recipe
    # --------------------------------------------------------

    result = query_by_id(
        df=df,
        column_name="recipe_id",
        query_id=recipe_id
    )

    return result


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    try:

        recipe_id = input(
            "Enter Recipe ID (example: R03943): "
        ).strip().upper()

        # ----------------------------------------------------
        # EMPTY INPUT
        # ----------------------------------------------------

        if not recipe_id:

            print("\nInvalid input.")
            print("Recipe ID cannot be empty.")

        # ----------------------------------------------------
        # INVALID FORMAT
        # ----------------------------------------------------

        elif not validate_recipe_id(recipe_id):

            print(f"\nInvalid Recipe ID: {recipe_id}")
            print(
                "Expected format: R followed by 5 digits "
                "(example: R03943)"
            )

        # ----------------------------------------------------
        # VALID FORMAT -> SEARCH
        # ----------------------------------------------------

        else:

            result = get_recipe_ingredients(recipe_id)

            # ------------------------------------------------
            # RECIPE DOES NOT EXIST
            # ------------------------------------------------

            if result.empty:

                print(
                    f"\nRecipe ID '{recipe_id}' "
                    "was not found."
                )

            # ------------------------------------------------
            # RECIPE EXISTS
            # ------------------------------------------------

            else:

                print(
                    f"\nIngredients for Recipe ID: "
                    f"{recipe_id}\n"
                )

                print(
                    result.to_csv(
                        index=False
                    )
                )

    # ========================================================
    # ERROR HANDLING
    # ========================================================

    except FileNotFoundError as error:

        print("\nFile Error:")
        print(error)

    except pd.errors.EmptyDataError:

        print(
            "\nError: The mapping CSV file is empty."
        )

    except pd.errors.ParserError:

        print(
            "\nError: Unable to read the mapping CSV file."
        )

    except ValueError as error:

        print("\nData Error:")
        print(error)

    except Exception as error:

        print("\nUnexpected Error:")
        print(error)