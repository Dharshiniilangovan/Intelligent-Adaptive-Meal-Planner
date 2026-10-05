from scripts.candidate_recipe import (
    load_recipe_kb,
    _contains_label,
)

from src.agents.recipe_agent import (
    RecipeAgent,
)


# ============================================================
# HELPER - PRINT TEST RESULT
# ============================================================

def print_result(
    title,
    user_state,
    result
):
    """
    Print compact Recipe Agent test output.
    """

    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    print(
        f"User State : {user_state}"
    )

    print(
        f"Status     : {result.get('status')}"
    )

    candidate_ids = (
        result
        .get(
            "data",
            {}
        )
        .get(
            "candidate_recipe_ids",
            []
        )
    )

    print(
        f"Count      : {len(candidate_ids)}"
    )

    print(
        f"Candidates : {candidate_ids}"
    )

    if result.get(
        "warnings"
    ):
        print(
            f"Warnings   : "
            f"{result['warnings']}"
        )

    if result.get(
        "errors"
    ):
        print(
            f"Errors     : "
            f"{result['errors']}"
        )


# ============================================================
# HELPER - GET CANDIDATE RECIPES
# ============================================================

def get_candidate_recipes(
    candidate_ids
):
    """
    Retrieve candidate rows from the real Recipe KB.
    """

    df = load_recipe_kb()

    return df[
        df["recipe_id"].isin(
            candidate_ids
        )
    ]


# ============================================================
# TEST 1
# VEGETARIAN RETRIEVAL
# ============================================================

def test_vegetarian_retrieval():

    agent = RecipeAgent(
        max_candidates=10
    )

    user_state = {
        "dietary_restrictions": [
            "Vegetarian"
        ],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    result = agent.run(
        user_state=user_state
    )

    print_result(
        "TEST 1: Vegetarian Retrieval",
        user_state,
        result
    )

    assert (
        result["status"]
        == "success"
    )

    candidate_ids = (
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ]
    )

    assert candidate_ids

    assert (
        len(candidate_ids)
        <= 10
    )

    recipes = get_candidate_recipes(
        candidate_ids
    )

    assert (
        len(recipes)
        == len(candidate_ids)
    )

    for _, recipe in recipes.iterrows():

        matches = (
            _contains_label(
                recipe.get(
                    "diet_labels"
                ),
                "Vegetarian"
            )
            or
            _contains_label(
                recipe.get(
                    "health_labels"
                ),
                "Vegetarian"
            )
        )

        assert matches


# ============================================================
# TEST 2
# MEAL TYPE RETRIEVAL
# ============================================================

def test_meal_type_retrieval():

    agent = RecipeAgent(
        max_candidates=10
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [
            "Dinner"
        ],
    }

    result = agent.run(
        user_state=user_state
    )

    print_result(
        "TEST 2: Dinner Retrieval",
        user_state,
        result
    )

    assert (
        result["status"]
        == "success"
    )

    candidate_ids = (
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ]
    )

    assert candidate_ids

    recipes = get_candidate_recipes(
        candidate_ids
    )

    for _, recipe in recipes.iterrows():

        assert (
            _contains_label(
                recipe.get(
                    "meal_type"
                ),
                "Dinner"
            )
        )


# ============================================================
# TEST 3
# CUISINE RETRIEVAL
# ============================================================

def test_cuisine_retrieval():

    agent = RecipeAgent(
        max_candidates=10
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [
            "Indian"
        ],
        "preferred_meal_types": [],
    }

    result = agent.run(
        user_state=user_state
    )

    print_result(
        "TEST 3: Indian Cuisine Retrieval",
        user_state,
        result
    )

    assert (
        result["status"]
        == "success"
    )

    candidate_ids = (
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ]
    )

    assert candidate_ids

    recipes = get_candidate_recipes(
        candidate_ids
    )

    for _, recipe in recipes.iterrows():

        assert (
            _contains_label(
                recipe.get(
                    "cuisine_type"
                ),
                "Indian"
            )
        )


# ============================================================
# TEST 4
# COMBINED CONSTRAINTS
# ============================================================

def test_combined_constraints():

    agent = RecipeAgent(
        max_candidates=10
    )

    user_state = {
        "dietary_restrictions": [
            "Vegetarian"
        ],
        "preferred_cuisines": [
            "Indian"
        ],
        "preferred_meal_types": [
            "Lunch"
        ],
    }

    result = agent.run(
        user_state=user_state
    )

    print_result(
        "TEST 4: Vegetarian + Lunch + Indian",
        user_state,
        result
    )

    assert (
        result["status"]
        == "success"
    )

    candidate_ids = (
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ]
    )

    assert (
        len(candidate_ids)
        <= 10
    )

    recipes = get_candidate_recipes(
        candidate_ids
    )

    for _, recipe in recipes.iterrows():

        vegetarian = (
            _contains_label(
                recipe.get(
                    "diet_labels"
                ),
                "Vegetarian"
            )
            or
            _contains_label(
                recipe.get(
                    "health_labels"
                ),
                "Vegetarian"
            )
        )

        lunch = (
            _contains_label(
                recipe.get(
                    "meal_type"
                ),
                "Lunch"
            )
        )

        assert vegetarian
        assert lunch


# ============================================================
# TEST 5
# NO RESULT
# ============================================================

def test_no_result():

    agent = RecipeAgent(
        max_candidates=10
    )

    user_state = {
        "dietary_restrictions": [
            "THIS_DIET_DOES_NOT_EXIST"
        ],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    result = agent.run(
        user_state=user_state
    )

    print_result(
        "TEST 5: No Matching Recipes",
        user_state,
        result
    )

    assert (
        result["status"]
        == "success"
    )

    assert (
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ]
        == []
    )

    assert result[
        "warnings"
    ]

    assert (
        "No candidate recipes"
        in result[
            "warnings"
        ][0]
    )

    assert (
        result["errors"]
        == []
    )


# ============================================================
# TEST 6
# MAXIMUM CANDIDATE COUNT
# ============================================================

def test_maximum_candidate_count():

    agent = RecipeAgent(
        max_candidates=5
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    result = agent.run(
        user_state=user_state
    )

    print_result(
        "TEST 6: Maximum Candidate Count = 5",
        user_state,
        result
    )

    assert (
        result["status"]
        == "success"
    )

    candidate_ids = (
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ]
    )

    assert (
        len(candidate_ids)
        <= 5
    )


# ============================================================
# TEST 7
# INVALID INPUT
# ============================================================

def test_invalid_input():

    agent = RecipeAgent()

    result = agent.run(
        user_state=None
    )

    print_result(
        "TEST 7: Invalid User State",
        None,
        result
    )

    assert (
        result["status"]
        == "failed"
    )

    assert (
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ]
        == []
    )

    assert (
        result["warnings"]
        == []
    )

    assert result[
        "errors"
    ]

    assert (
        "user_state is required"
        in result[
            "errors"
        ][0]
    )


# ============================================================
# TEST 8
# RECIPE ID VALIDITY
# ============================================================

def test_recipe_id_validity():

    agent = RecipeAgent(
        max_candidates=10
    )

    user_state = {
        "dietary_restrictions": [
            "Vegetarian"
        ],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    result = agent.run(
        user_state=user_state
    )

    print_result(
        "TEST 8: Recipe ID Validity",
        user_state,
        result
    )

    assert (
        result["status"]
        == "success"
    )

    candidate_ids = (
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ]
    )

    assert candidate_ids

    df = load_recipe_kb()

    valid_ids = set(
        df[
            "recipe_id"
        ]
        .astype(str)
        .tolist()
    )

    for recipe_id in candidate_ids:

        assert (
            recipe_id
            in valid_ids
        )


# ============================================================
# TEST 9
# MANAGER MEAL CONTEXT OVERRIDE
# ============================================================

def test_meal_context_override():

    agent = RecipeAgent(
        max_candidates=10
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [
            "Lunch"
        ],
    }

    meal_context = {
        "meal_type": "Dinner"
    }

    result = agent.run(
        user_state=user_state,
        meal_context=meal_context
    )

    print_result(
        "TEST 9: Manager Meal Context = Dinner",
        user_state,
        result
    )

    assert (
        result["status"]
        == "success"
    )

    candidate_ids = (
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ]
    )

    assert candidate_ids

    recipes = get_candidate_recipes(
        candidate_ids
    )

    for _, recipe in recipes.iterrows():

        assert (
            _contains_label(
                recipe.get(
                    "meal_type"
                ),
                "Dinner"
            )
        )


# ============================================================
# TEST 10
# EXACT AGENT OUTPUT CONTRACT
# ============================================================

def test_exact_output_contract():

    agent = RecipeAgent(
        max_candidates=3
    )

    user_state = {
        "dietary_restrictions": [
            "Vegetarian"
        ],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    result = agent.run(
        user_state=user_state
    )

    print_result(
        "TEST 10: Exact Recipe Agent Output Contract",
        user_state,
        result
    )

    # --------------------------------------------------------
    # EXACT TOP-LEVEL CONTRACT
    # --------------------------------------------------------

    assert set(
        result.keys()
    ) == {
        "agent",
        "status",
        "data",
        "warnings",
        "errors",
    }

    # --------------------------------------------------------
    # EXACT DATA CONTRACT
    # --------------------------------------------------------

    assert set(
        result["data"].keys()
    ) == {
        "candidate_recipe_ids"
    }

    # --------------------------------------------------------
    # VALUES
    # --------------------------------------------------------

    assert (
        result["agent"]
        == "recipe"
    )

    assert (
        result["status"]
        == "success"
    )

    assert isinstance(
        result[
            "data"
        ][
            "candidate_recipe_ids"
        ],
        list
    )

    assert (
        len(
            result[
                "data"
            ][
                "candidate_recipe_ids"
            ]
        )
        <= 3
    )

    assert isinstance(
        result["warnings"],
        list
    )

    assert isinstance(
        result["errors"],
        list
    )

    assert (
        result["errors"]
        == []
    )