import pandas as pd

from scripts.mapping_retrieval_query import (
    get_recipe_ingredients,
    validate_recipe_id,
    MAPPING_FILE
)


# ============================================================
# VALID TEST 1
# ============================================================

def test_valid_recipe_1():

    recipe_id = "R03943"

    assert validate_recipe_id(recipe_id) is True

    result = get_recipe_ingredients(recipe_id)

    assert not result.empty

    assert all(
        result["recipe_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        == recipe_id
    )


# ============================================================
# VALID TEST 2
# ============================================================

def test_valid_recipe_2():

    recipe_id = "R16472"

    assert validate_recipe_id(recipe_id) is True

    result = get_recipe_ingredients(recipe_id)

    assert not result.empty

    assert all(
        result["recipe_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        == recipe_id
    )


# ============================================================
# INVALID TEST 1
# WRONG RECIPE ID FORMAT
# ============================================================

def test_invalid_recipe_format():

    recipe_id = "ABC123"

    assert validate_recipe_id(recipe_id) is False


# ============================================================
# INVALID TEST 2
# VALID FORMAT BUT RECIPE DOES NOT EXIST
# ============================================================

def test_recipe_not_found():

    df = pd.read_csv(MAPPING_FILE)

    existing_ids = set(
        df["recipe_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Automatically find an unused recipe ID
    recipe_id = None

    for i in range(100000):

        candidate = f"R{i:05d}"

        if candidate not in existing_ids:
            recipe_id = candidate
            break

    # Make sure an unused ID was found
    assert recipe_id is not None

    # Make sure format itself is valid
    assert validate_recipe_id(recipe_id) is True

    # Call the actual mapping retrieval function
    result = get_recipe_ingredients(recipe_id)

    # No recipe should be returned
    assert result.empty