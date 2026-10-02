import pandas as pd

from scripts.candidate_recipe import (
    load_recipe_kb,
    filter_by_diet,
    filter_by_health_label,
    filter_by_meal_type,
    filter_by_cuisine,
    filter_by_calorie_range,
    retrieve_candidates,
)


# ============================================================
# HELPER FUNCTION
# ============================================================

def print_results(title, result):
    """
    Print a compact preview of test results.
    Shows only the first 3 matching recipes.
    """

    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    print(f"Total recipes found: {len(result)}")

    if result.empty:
        print("No matching recipes found.")
    else:
        print("\nFirst 3 recipes:")
        print(result.head(3).to_string(index=False))


# ============================================================
# TEST 1 - LOAD RECIPE KB
# ============================================================

def test_load_recipe_kb():

    df = load_recipe_kb()

    print("\n" + "=" * 70)
    print("TEST 1: Load Recipe KB")
    print("=" * 70)
    print(f"Total recipes loaded: {len(df)}")
    print("\nFirst 3 recipes:")
    print(df.head(3).to_string(index=False))

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "recipe_id" in df.columns


# ============================================================
# TEST 2 - DIET FILTER
# ============================================================

def test_filter_by_diet():

    df = load_recipe_kb()

    result = filter_by_diet(
        df,
        "Low-Carb"
    )

    print_results(
        "TEST 2: Diet = Low-Carb",
        result
    )

    assert isinstance(result, pd.DataFrame)

    assert all(
        result.apply(
            lambda row:
                "low-carb" in str(
                    row.get("diet_labels", "")
                ).lower()
                or
                "low-carb" in str(
                    row.get("health_labels", "")
                ).lower(),
            axis=1
        )
    )


# ============================================================
# TEST 3 - HEALTH LABEL FILTER
# ============================================================

def test_filter_by_health_label():

    df = load_recipe_kb()

    result = filter_by_health_label(
        df,
        "Vegetarian"
    )

    print_results(
        "TEST 3: Health Label = Vegetarian",
        result
    )

    assert isinstance(result, pd.DataFrame)
    assert not result.empty

    assert all(
        result["health_labels"]
        .astype(str)
        .str.lower()
        .str.contains("vegetarian")
    )


# ============================================================
# TEST 4 - MEAL TYPE FILTER
# ============================================================

def test_filter_by_meal_type():

    df = load_recipe_kb()

    result = filter_by_meal_type(
        df,
        "lunch/dinner"
    )

    print_results(
        "TEST 4: Meal Type = Lunch/Dinner",
        result
    )

    assert isinstance(result, pd.DataFrame)
    assert not result.empty

    assert all(
        result["meal_type"]
        .astype(str)
        .str.lower()
        .str.contains("lunch/dinner")
    )


# ============================================================
# TEST 5 - CUISINE FILTER
# ============================================================

def test_filter_by_cuisine():

    df = load_recipe_kb()

    result = filter_by_cuisine(
        df,
        "Indian"
    )

    print_results(
        "TEST 5: Cuisine = Indian",
        result
    )

    assert isinstance(result, pd.DataFrame)
    assert not result.empty

    assert all(
        result["cuisine_type"]
        .astype(str)
        .str.lower()
        .str.contains("indian")
    )


# ============================================================
# TEST 6 - CALORIE RANGE
# ============================================================

def test_calorie_range():

    df = load_recipe_kb()

    result = filter_by_calorie_range(
        df,
        min_calories=200,
        max_calories=600
    )

    print_results(
        "TEST 6: Calories = 200 to 600",
        result
    )

    assert isinstance(result, pd.DataFrame)

    calories = pd.to_numeric(
        result["calories_per_serving"],
        errors="coerce"
    )

    assert all(calories >= 200)
    assert all(calories <= 600)


# ============================================================
# TEST 7 - VEGETARIAN + INDIAN
# ============================================================

def test_vegetarian_indian():

    result = retrieve_candidates(
        health_label="Vegetarian",
        cuisine="Indian"
    )

    print_results(
        "TEST 7: Vegetarian + Indian",
        result
    )

    assert isinstance(result, pd.DataFrame)

    if not result.empty:

        assert all(
            result["health_labels"]
            .astype(str)
            .str.lower()
            .str.contains("vegetarian")
        )

        assert all(
            result["cuisine_type"]
            .astype(str)
            .str.lower()
            .str.contains("indian")
        )


# ============================================================
# TEST 8 - VEGETARIAN + INDIAN + LUNCH/DINNER
# ============================================================

def test_vegetarian_indian_lunch_dinner():

    result = retrieve_candidates(
        health_label="Vegetarian",
        cuisine="Indian",
        meal_type="lunch/dinner"
    )

    print_results(
        "TEST 8: Vegetarian + Indian + Lunch/Dinner",
        result
    )

    assert isinstance(result, pd.DataFrame)

    if not result.empty:

        assert all(
            result["health_labels"]
            .astype(str)
            .str.lower()
            .str.contains("vegetarian")
        )

        assert all(
            result["cuisine_type"]
            .astype(str)
            .str.lower()
            .str.contains("indian")
        )

        assert all(
            result["meal_type"]
            .astype(str)
            .str.lower()
            .str.contains("lunch/dinner")
        )


# ============================================================
# TEST 9 - LOW-CARB + VEGETARIAN + MAX 600 CALORIES
# ============================================================

def test_low_carb_vegetarian_max_600():

    result = retrieve_candidates(
        diet="Low-Carb",
        health_label="Vegetarian",
        max_calories=600
    )

    print_results(
        "TEST 9: Low-Carb + Vegetarian + Maximum 600 Calories",
        result
    )

    assert isinstance(result, pd.DataFrame)

    if not result.empty:

        assert all(
            result["health_labels"]
            .astype(str)
            .str.lower()
            .str.contains("vegetarian")
        )

        calories = pd.to_numeric(
            result["calories_per_serving"],
            errors="coerce"
        )

        assert all(calories <= 600)


# ============================================================
# TEST 10 - NO MATCHING RECIPES
# ============================================================

def test_no_matching_recipes():

    result = retrieve_candidates(
        cuisine="THIS_CUISINE_DOES_NOT_EXIST"
    )

    print_results(
        "TEST 10: No Matching Recipes",
        result
    )

    assert isinstance(result, pd.DataFrame)
    assert result.empty