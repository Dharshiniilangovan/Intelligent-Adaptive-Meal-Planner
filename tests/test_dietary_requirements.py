import pandas as pd

from scripts.candidate_recipe import load_recipe_kb

from src.reasoning.dietary_requirements import (
    check_diet_constraint,
    check_allergen_constraint,
    calculate_nutrition_score,
    calculate_preference_score,
)

from scripts.mapping_retrieval_query import (
    get_recipe_ingredients,
)


# ============================================================
# HELPER - GET REAL RECIPE
# ============================================================

def get_recipe(recipe_id):
    """
    Load one real recipe from recipe_kb_clean.csv.
    """

    df = load_recipe_kb()

    result = df[
        df["recipe_id"] == recipe_id
    ]

    assert not result.empty, (
        f"Recipe {recipe_id} not found in Recipe KB"
    )

    return result.iloc[0].to_dict()


# ============================================================
# HELPER - COMPACT TEST OUTPUT
# ============================================================

def print_test_details(
    title,
    recipe,
    user_state,
    result,
    intermediate=None
):
    """
    Print compact:
    recipe -> user input -> intermediate check -> result.
    """

    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    print(
        f"Recipe : "
        f"{recipe.get('recipe_id')} | "
        f"{recipe.get('recipe_name')}"
    )

    print(
        f"User   : {user_state}"
    )

    if intermediate:
        print(
            f"Check  : {intermediate}"
        )

    if "passed" in result:

        status = (
            "PASS"
            if result["passed"]
            else "FAIL"
        )

        print(
            f"Result : {status}"
        )

    if "score" in result:

        print(
            f"Score  : {result['score']}"
        )

    if result.get("status"):
        print(
            f"Status : {result['status']}"
        )

    if "reason" in result:

        print(
            f"Reason : {result['reason']}"
        )


# ============================================================
# HELPER - INGREDIENT RETRIEVAL
# ============================================================

def get_ingredient_preview(
    recipe_id,
    limit=8
):
    """
    Retrieve ingredients and create a short preview.
    """

    ingredient_df = get_recipe_ingredients(
        recipe_id
    )

    if ingredient_df.empty:

        return (
            ingredient_df,
            "No mapped ingredients"
        )

    if (
        "ingredient_name"
        not in ingredient_df.columns
    ):

        return (
            ingredient_df,
            "ingredient_name column unavailable"
        )

    names = (
        ingredient_df[
            "ingredient_name"
        ]
        .dropna()
        .astype(str)
        .tolist()
    )

    preview = names[:limit]

    text = ", ".join(
        preview
    )

    if len(names) > limit:

        text += (
            f" ... +{len(names) - limit} more"
        )

    return ingredient_df, text


# ============================================================
# TEST 1
# VEGETARIAN - PASS
# ============================================================

def test_vegetarian_pass():

    recipe = get_recipe(
        "R03943"
    )

    user_state = {
        "diet": ["Vegetarian"]
    }

    result = check_diet_constraint(
        recipe,
        user_state
    )

    print_test_details(
        "TEST 1: Vegetarian - PASS",
        recipe,
        user_state,
        result,
        intermediate=(
            f"is_vegetarian="
            f"{recipe.get('is_vegetarian')}"
        )
    )

    assert result["constraint"] == "diet"
    assert result["passed"] is True


# ============================================================
# TEST 2
# VEGAN - FAIL
# ============================================================

def test_vegan_fail():

    recipe = get_recipe(
        "R03943"
    )

    user_state = {
        "diet": ["Vegan"]
    }

    result = check_diet_constraint(
        recipe,
        user_state
    )

    print_test_details(
        "TEST 2: Vegan - FAIL",
        recipe,
        user_state,
        result,
        intermediate=(
            f"is_vegan="
            f"{recipe.get('is_vegan')}"
        )
    )

    assert result["constraint"] == "diet"
    assert result["passed"] is False


# ============================================================
# TEST 3
# LOW-CARB - PASS
# ============================================================

def test_low_carb_pass():

    recipe = get_recipe(
        "R03943"
    )

    user_state = {
        "diet": ["Low-Carb"]
    }

    result = check_diet_constraint(
        recipe,
        user_state
    )

    print_test_details(
        "TEST 3: Low-Carb - PASS",
        recipe,
        user_state,
        result,
        intermediate=(
            f"diet_labels="
            f"{recipe.get('diet_labels')}"
        )
    )

    assert result["constraint"] == "diet"
    assert result["passed"] is True


# ============================================================
# TEST 4
# MULTIPLE DIET REQUIREMENTS - PASS
# ============================================================

def test_multiple_diet_requirements_pass():

    recipe = get_recipe(
        "R20156"
    )

    user_state = {
        "diet": [
            "Vegan",
            "Gluten-Free",
            "High-Fiber",
            "Low-Sodium",
        ]
    }

    result = check_diet_constraint(
        recipe,
        user_state
    )

    intermediate = (
        f"diet={recipe.get('diet_labels')} | "
        f"health={recipe.get('health_labels')}"
    )

    print_test_details(
        "TEST 4: Multiple Diet Requirements - PASS",
        recipe,
        user_state,
        result,
        intermediate=intermediate
    )

    assert result["constraint"] == "diet"
    assert result["passed"] is True


# ============================================================
# TEST 5
# PEANUT ALLERGY - SAFE
# ============================================================

def test_peanut_allergy_pass():

    recipe = get_recipe(
        "R03943"
    )

    user_state = {
        "allergens": ["Peanut"]
    }

    _, ingredient_preview = (
        get_ingredient_preview(
            "R03943"
        )
    )

    result = check_allergen_constraint(
        recipe,
        user_state
    )

    intermediate = (
        f"health_labels="
        f"{recipe.get('health_labels')} | "
        f"ingredients={ingredient_preview}"
    )

    print_test_details(
        "TEST 5: Peanut Allergy - SAFE",
        recipe,
        user_state,
        result,
        intermediate=intermediate
    )

    assert result["constraint"] == "allergy"
    assert result["passed"] is True


# ============================================================
# TEST 6
# SULFITES CAUTION - HARD FAIL
# ============================================================

def test_sulfites_caution_fail():

    recipe = get_recipe(
        "R03943"
    )

    user_state = {
        "cautions": ["Sulfites"]
    }

    result = check_allergen_constraint(
        recipe,
        user_state
    )

    print_test_details(
        "TEST 6: Sulfites Caution - HARD FAIL",
        recipe,
        user_state,
        result,
        intermediate=(
            f"recipe cautions="
            f"{recipe.get('cautions')}"
        )
    )

    if result["passed"] is False:
        print("ALERT  : CAUTION DETECTED")

    assert result["constraint"] == "allergy"
    assert result["passed"] is False

    assert (
        "sulfites"
        in result["reason"].lower()
    )


# ============================================================
# TEST 7
# NUTRITION - EXACT TARGET
# ============================================================

def test_nutrition_exact_target():

    recipe = get_recipe(
        "R03943"
    )

    actual_calories = float(
        recipe[
            "calories_per_serving"
        ]
    )

    actual_protein = float(
        recipe[
            "protein_g_per_serving"
        ]
    )

    user_state = {
        "nutrition": {
            "calories":
                actual_calories,

            "protein":
                actual_protein,
        }
    }

    result = calculate_nutrition_score(
        recipe,
        user_state
    )

    intermediate = (
        f"calories actual={actual_calories:.2f}, "
        f"target={actual_calories:.2f} | "
        f"protein actual={actual_protein:.2f}, "
        f"target={actual_protein:.2f}"
    )

    print_test_details(
        "TEST 7: Nutrition Exact Target",
        recipe,
        user_state,
        result,
        intermediate=intermediate
    )

    assert result["score_type"] == "nutrition"
    assert result["status"] == "scored"
    assert result["score"] == 1.0

    assert (
        result["components"]["calories"]
        == 1.0
    )

    assert (
        result["components"]["protein"]
        == 1.0
    )


# ============================================================
# TEST 8
# NUTRITION - CLOSE TARGET
# ============================================================

def test_nutrition_closeness():

    recipe = get_recipe(
        "R03943"
    )

    actual_calories = float(
        recipe[
            "calories_per_serving"
        ]
    )

    target_calories = (
        actual_calories
        + 50
    )

    user_state = {
        "nutrition": {
            "calories":
                target_calories
        }
    }

    result = calculate_nutrition_score(
        recipe,
        user_state
    )

    intermediate = (
        f"actual={actual_calories:.2f} kcal | "
        f"target={target_calories:.2f} kcal | "
        f"difference=50 kcal"
    )

    print_test_details(
        "TEST 8: Nutrition Closeness",
        recipe,
        user_state,
        result,
        intermediate=intermediate
    )

    assert result["status"] == "scored"
    assert result["score"] is not None

    assert (
        0.0
        <= result["score"]
        <= 1.0
    )

    assert result["score"] > 0.0


# ============================================================
# TEST 9
# CUISINE PREFERENCE - MATCH
# ============================================================

def test_cuisine_preference_match():

    recipe = get_recipe(
        "R20156"
    )

    user_state = {
        "preferences": {
            "cuisines": ["Indian"],
            "disliked_ingredients": [],
        }
    }

    result = calculate_preference_score(
        recipe,
        user_state
    )

    intermediate = (
        f"recipe cuisine="
        f"{recipe.get('cuisine_type')} | "
        f"matched="
        f"{result['matched_cuisines']}"
    )

    print_test_details(
        "TEST 9: Indian Cuisine Preference - MATCH",
        recipe,
        user_state,
        result,
        intermediate=intermediate
    )

    assert result["score_type"] == "preference"

    assert (
        "indian"
        in result[
            "matched_cuisines"
        ]
    )

    assert result["score"] == 1.0


# ============================================================
# TEST 10
# DISLIKED INGREDIENT PRESENT - PENALTY
# ============================================================

def test_disliked_ingredient_penalty():

    recipe = get_recipe(
        "R03943"
    )

    neutral_user = {
        "preferences": {
            "cuisines": [],
            "disliked_ingredients": [],
        }
    }

    neutral_result = (
        calculate_preference_score(
            recipe,
            neutral_user
        )
    )

    ingredient_df, ingredient_preview = (
        get_ingredient_preview(
            "R03943"
        )
    )

    assert not ingredient_df.empty

    disliked_ingredient = (
        ingredient_df[
            "ingredient_name"
        ]
        .dropna()
        .iloc[0]
    )

    user_state = {
        "preferences": {
            "cuisines": [],

            "disliked_ingredients": [
                disliked_ingredient
            ],
        }
    }

    result = calculate_preference_score(
        recipe,
        user_state
    )

    intermediate = (
        f"ingredients={ingredient_preview} | "
        f"disliked={disliked_ingredient} | "
        f"matched="
        f"{result['matched_disliked_ingredients']} | "
        f"neutral score={neutral_result['score']}"
    )

    print_test_details(
        "TEST 10: Disliked Ingredient PRESENT - PENALTY",
        recipe,
        user_state,
        result,
        intermediate=intermediate
    )

    assert result["score_type"] == "preference"

    assert (
        0.0
        <= result["score"]
        <= 1.0
    )

    assert (
        result["score"]
        < neutral_result["score"]
    )

    assert (
        len(
            result[
                "matched_disliked_ingredients"
            ]
        )
        >= 1
    )


# ============================================================
# TEST 11
# REAL PEANUT ALLERGEN PRESENT - HARD FAIL
# ============================================================

def test_real_peanut_allergen_fail():

    df = load_recipe_kb()

    selected_recipe = None
    selected_ingredients = None

    for _, row in df.iterrows():

        recipe_id = row[
            "recipe_id"
        ]

        ingredient_df = (
            get_recipe_ingredients(
                recipe_id
            )
        )

        if ingredient_df.empty:
            continue

        if (
            "ingredient_name"
            not in ingredient_df.columns
        ):
            continue

        ingredient_names = (
            ingredient_df[
                "ingredient_name"
            ]
            .dropna()
            .astype(str)
            .str.lower()
        )

        contains_peanut = (
            ingredient_names
            .str.contains(
                r"\bpeanut\b",
                regex=True
            )
            .any()
        )

        if contains_peanut:

            selected_recipe = (
                row.to_dict()
            )

            selected_ingredients = (
                ingredient_df
            )

            break

    assert selected_recipe is not None, (
        "Could not find a peanut-containing recipe"
    )

    names = (
        selected_ingredients[
            "ingredient_name"
        ]
        .dropna()
        .astype(str)
        .tolist()
    )

    preview = ", ".join(
        names[:8]
    )

    if len(names) > 8:
        preview += (
            f" ... +{len(names) - 8} more"
        )

    user_state = {
        "allergens": ["Peanut"]
    }

    result = check_allergen_constraint(
        selected_recipe,
        user_state
    )

    print_test_details(
        "TEST 11: Peanut PRESENT - HARD FAIL",
        selected_recipe,
        user_state,
        result,
        intermediate=(
            f"ingredients={preview}"
        )
    )

    if result["passed"] is False:
        print(
            "ALERT  : PEANUT ALLERGEN DETECTED"
        )

    assert result["constraint"] == "allergy"
    assert result["passed"] is False

    assert (
        "peanut"
        in result["reason"].lower()
    )


# ============================================================
# TEST 12
# DISLIKED INGREDIENT ABSENT - NO PENALTY
# ============================================================

def test_disliked_ingredient_absent():

    recipe = get_recipe(
        "R03943"
    )

    neutral_user = {
        "preferences": {
            "cuisines": [],
            "disliked_ingredients": [],
        }
    }

    neutral_result = (
        calculate_preference_score(
            recipe,
            neutral_user
        )
    )

    user_state = {
        "preferences": {

            "cuisines": [],

            "disliked_ingredients": [
                "THIS_INGREDIENT_DOES_NOT_EXIST"
            ],
        }
    }

    result = calculate_preference_score(
        recipe,
        user_state
    )

    intermediate = (
        f"matched="
        f"{result['matched_disliked_ingredients']} | "
        f"neutral score={neutral_result['score']} | "
        f"final score={result['score']}"
    )

    print_test_details(
        "TEST 12: Disliked Ingredient ABSENT - NO PENALTY",
        recipe,
        user_state,
        result,
        intermediate=intermediate
    )

    assert (
        result[
            "matched_disliked_ingredients"
        ]
        == []
    )

    assert (
        result["score"]
        == neutral_result["score"]
    )


# ============================================================
# TEST 13
# CUISINE PREFERENCE - NO MATCH
# ============================================================

def test_cuisine_preference_no_match():

    recipe = get_recipe(
        "R20156"
    )

    user_state = {
        "preferences": {

            "cuisines": [
                "French"
            ],

            "disliked_ingredients": [],
        }
    }

    result = calculate_preference_score(
        recipe,
        user_state
    )

    intermediate = (
        f"recipe cuisine="
        f"{recipe.get('cuisine_type')} | "
        f"requested=French | "
        f"matched="
        f"{result['matched_cuisines']}"
    )

    print_test_details(
        "TEST 13: Cuisine Preference - NO MATCH",
        recipe,
        user_state,
        result,
        intermediate=intermediate
    )

    assert result["score_type"] == "preference"

    assert (
        result["matched_cuisines"]
        == []
    )

    assert result["score"] == 0.5


# ============================================================
# TEST 14
# NO NUTRITION TARGET - NOT SCORED
# ============================================================

def test_no_nutrition_target():

    recipe = get_recipe(
        "R03943"
    )

    user_state = {
        "nutrition": {}
    }

    result = calculate_nutrition_score(
        recipe,
        user_state
    )

    print_test_details(
        "TEST 14: No Nutrition Target - NOT SCORED",
        recipe,
        user_state,
        result,
        intermediate="No nutrition targets supplied"
    )

    assert result["score_type"] == "nutrition"

    assert (
        result["status"]
        == "not_scored"
    )

    assert result["score"] is None


# ============================================================
# TEST 15
# MULTIPLE DIETS - ONE REQUIREMENT FAILS
# ============================================================

def test_multiple_diet_one_failure():

    recipe = get_recipe(
        "R03943"
    )

    user_state = {
        "diet": [
            "Vegetarian",
            "Vegan",
        ]
    }

    result = check_diet_constraint(
        recipe,
        user_state
    )

    intermediate = (
        f"is_vegetarian="
        f"{recipe.get('is_vegetarian')} | "
        f"is_vegan="
        f"{recipe.get('is_vegan')}"
    )

    print_test_details(
        "TEST 15: Vegetarian + Vegan - ONE FAILS",
        recipe,
        user_state,
        result,
        intermediate=intermediate
    )

    assert result["constraint"] == "diet"
    assert result["passed"] is False

    assert (
        "vegan"
        in result["reason"].lower()
    )