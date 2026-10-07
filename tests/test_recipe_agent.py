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
    result,
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
        f"Slot       : {result.get('slot')}"
    )

    candidate_ids = (
        result.get(
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


# ============================================================
# HELPER - GET CANDIDATE RECIPES
# ============================================================

def get_candidate_recipes(
    candidate_ids,
):
    """
    Get candidate recipe rows from the real Recipe KB.
    """

    df = load_recipe_kb()

    return df[
        df["recipe_id"].isin(
            candidate_ids
        )
    ]


# ============================================================
# HELPER - DEFAULT SLOT
# ============================================================

def default_slot(
    meal_type="Dinner",
):
    """
    Create a standard Manager meal slot.
    """

    return {
        "date": "2026-10-07",
        "meal_type": meal_type,
    }


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

    meal_slot = default_slot(
        "Dinner"
    )

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 1: Vegetarian Retrieval",
        user_state,
        result,
    )

    candidate_ids = (
        result[
            "candidate_recipe_ids"
        ]
    )

    assert candidate_ids

    assert len(
        candidate_ids
    ) <= 10

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
                "Vegetarian",
            )
            or
            _contains_label(
                recipe.get(
                    "health_labels"
                ),
                "Vegetarian",
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
        "preferred_meal_types": [],
    }

    meal_slot = default_slot(
        "Dinner"
    )

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 2: Dinner Retrieval",
        user_state,
        result,
    )

    candidate_ids = (
        result[
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
                "Dinner",
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

    meal_slot = default_slot(
        "Dinner"
    )

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 3: Indian Cuisine Retrieval",
        user_state,
        result,
    )

    candidate_ids = (
        result[
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
                "Indian",
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
        "preferred_meal_types": [],
    }

    meal_slot = default_slot(
        "Lunch"
    )

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 4: Vegetarian + Lunch + Indian",
        user_state,
        result,
    )

    candidate_ids = (
        result[
            "candidate_recipe_ids"
        ]
    )

    assert len(
        candidate_ids
    ) <= 10

    recipes = get_candidate_recipes(
        candidate_ids
    )

    for _, recipe in recipes.iterrows():

        vegetarian = (
            _contains_label(
                recipe.get(
                    "diet_labels"
                ),
                "Vegetarian",
            )
            or
            _contains_label(
                recipe.get(
                    "health_labels"
                ),
                "Vegetarian",
            )
        )

        lunch = (
            _contains_label(
                recipe.get(
                    "meal_type"
                ),
                "Lunch",
            )
        )

        assert vegetarian
        assert lunch


# ============================================================
# TEST 5
# NO MATCHING RECIPES
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

    meal_slot = default_slot(
        "Dinner"
    )

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 5: No Matching Recipes",
        user_state,
        result,
    )

    assert (
        result[
            "candidate_recipe_ids"
        ]
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

    meal_slot = default_slot(
        "Dinner"
    )

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 6: Maximum Candidate Count = 5",
        user_state,
        result,
    )

    candidate_ids = (
        result[
            "candidate_recipe_ids"
        ]
    )

    assert len(
        candidate_ids
    ) <= 5


# ============================================================
# TEST 7
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

    meal_slot = default_slot(
        "Dinner"
    )

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 7: Recipe ID Validity",
        user_state,
        result,
    )

    candidate_ids = (
        result[
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
# TEST 8
# MEAL SLOT OVERRIDES USER PREFERENCE
# ============================================================

def test_meal_slot_override():

    agent = RecipeAgent(
        max_candidates=10
    )

    # User generally prefers Lunch.
    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [
            "Lunch"
        ],
    }

    # Manager is currently requesting Dinner.
    meal_slot = {
        "date": "2026-10-07",
        "meal_type": "Dinner",
    }

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 8: Manager Meal Slot = Dinner",
        user_state,
        result,
    )

    candidate_ids = (
        result[
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
                "Dinner",
            )
        )


# ============================================================
# TEST 9
# EXACT NEW MANAGER OUTPUT CONTRACT
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

    meal_slot = {
        "date": "2026-10-07",
        "meal_type": "Dinner",
    }

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 9: Exact Manager Output Contract",
        user_state,
        result,
    )

    # Exact new top-level output.
    assert set(
        result.keys()
    ) == {
        "slot",
        "candidate_recipe_ids",
    }

    assert set(
        result["slot"].keys()
    ) == {
        "date",
        "meal_type",
    }

    assert (
        result["slot"]["date"]
        == "2026-10-07"
    )

    assert (
        result["slot"]["meal_type"]
        == "dinner"
    )

    assert isinstance(
        result[
            "candidate_recipe_ids"
        ],
        list,
    )

    assert (
        len(
            result[
                "candidate_recipe_ids"
            ]
        )
        <= 3
    )


# ============================================================
# TEST 10
# EMPTY SELECTED RECIPE LIST
# ============================================================

def test_empty_selected_recipe_list():

    agent = RecipeAgent(
        max_candidates=5
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    meal_slot = default_slot(
        "Dinner"
    )

    result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    print_result(
        "TEST 10: Empty Selected Recipe List",
        user_state,
        result,
    )

    assert isinstance(
        result[
            "candidate_recipe_ids"
        ],
        list,
    )

    assert (
        len(
            result[
                "candidate_recipe_ids"
            ]
        )
        <= 5
    )


# ============================================================
# TEST 11
# ONE SELECTED RECIPE MUST NOT REPEAT
# ============================================================

def test_selected_recipe_does_not_repeat():

    agent = RecipeAgent(
        max_candidates=5
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    first_slot = {
        "date": "2026-10-07",
        "meal_type": "Lunch",
    }

    first_result = agent.run(
        user_state=user_state,
        meal_slot=first_slot,
        selected_recipe_ids=[],
    )

    first_candidates = (
        first_result[
            "candidate_recipe_ids"
        ]
    )

    assert first_candidates

    # Simulate Manager selecting first candidate.
    selected_recipe = (
        first_candidates[0]
    )

    second_slot = {
        "date": "2026-10-07",
        "meal_type": "Dinner",
    }

    second_result = agent.run(
        user_state=user_state,
        meal_slot=second_slot,
        selected_recipe_ids=[
            selected_recipe
        ],
    )

    second_candidates = (
        second_result[
            "candidate_recipe_ids"
        ]
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "TEST 11: One Selected Recipe Does Not Repeat"
    )

    print(
        "=" * 70
    )

    print(
        f"Selected   : {selected_recipe}"
    )

    print(
        f"Candidates : {second_candidates}"
    )

    assert (
        selected_recipe
        not in second_candidates
    )


# ============================================================
# TEST 12
# MULTIPLE SELECTED RECIPES MUST NOT REPEAT
# ============================================================

def test_multiple_selected_recipes_do_not_repeat():

    agent = RecipeAgent(
        max_candidates=10
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    meal_slot = default_slot(
        "Dinner"
    )

    initial_result = agent.run(
        user_state=user_state,
        meal_slot=meal_slot,
        selected_recipe_ids=[],
    )

    initial_candidates = (
        initial_result[
            "candidate_recipe_ids"
        ]
    )

    assert len(
        initial_candidates
    ) >= 3

    selected_recipe_ids = (
        initial_candidates[
            :3
        ]
    )

    result = agent.run(
        user_state=user_state,

        meal_slot={
            "date": "2026-10-08",
            "meal_type": "Dinner",
        },

        selected_recipe_ids=
            selected_recipe_ids,
    )

    candidate_ids = (
        result[
            "candidate_recipe_ids"
        ]
    )

    print(
        "\n"
        + "=" * 70
    )

    print(
        "TEST 12: Multiple Selected Recipes"
    )

    print(
        "=" * 70
    )

    print(
        f"Selected   : "
        f"{selected_recipe_ids}"
    )

    print(
        f"Candidates : "
        f"{candidate_ids}"
    )

    assert set(
        selected_recipe_ids
    ).isdisjoint(
        set(
            candidate_ids
        )
    )


# ============================================================
# TEST 13
# SELECTED RECIPE ID NORMALIZATION
# ============================================================

def test_selected_recipe_id_normalization():

    agent = RecipeAgent(
        max_candidates=10
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    initial_result = agent.run(
        user_state=user_state,

        meal_slot={
            "date": "2026-10-07",
            "meal_type": "Dinner",
        },

        selected_recipe_ids=[],
    )

    initial_candidates = (
        initial_result[
            "candidate_recipe_ids"
        ]
    )

    assert len(
        initial_candidates
    ) >= 2

    recipe_1 = (
        initial_candidates[0]
    )

    recipe_2 = (
        initial_candidates[1]
    )

    # Deliberately lowercase, whitespace and duplicate.
    manager_selected = [
        f" {recipe_1.lower()} ",
        recipe_2.lower(),
        recipe_2,
    ]

    result = agent.run(
        user_state=user_state,

        meal_slot={
            "date": "2026-10-08",
            "meal_type": "Dinner",
        },

        selected_recipe_ids=
            manager_selected,
    )

    candidate_ids = (
        result[
            "candidate_recipe_ids"
        ]
    )

    assert (
        recipe_1.upper()
        not in candidate_ids
    )

    assert (
        recipe_2.upper()
        not in candidate_ids
    )


# ============================================================
# TEST 14
# SEQUENTIAL MANAGER REPETITION
# ============================================================

def test_sequential_manager_recipe_selection():
    """
    Simulates the real Manager workflow.

    Every time Manager selects a recipe, it is added to
    selected_recipe_ids and must never appear again.
    """

    agent = RecipeAgent(
        max_candidates=5
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    slots = [
        {
            "date": "2026-10-07",
            "meal_type": "Lunch",
        },
        {
            "date": "2026-10-07",
            "meal_type": "Dinner",
        },
        {
            "date": "2026-10-08",
            "meal_type": "Lunch",
        },
        {
            "date": "2026-10-08",
            "meal_type": "Dinner",
        },
    ]

    selected_recipe_ids = []

    print(
        "\n"
        + "=" * 70
    )

    print(
        "TEST 14: Sequential Manager Repetition"
    )

    print(
        "=" * 70
    )

    for slot in slots:

        result = agent.run(
            user_state=user_state,
            meal_slot=slot,
            selected_recipe_ids=
                selected_recipe_ids,
        )

        candidate_ids = (
            result[
                "candidate_recipe_ids"
            ]
        )

        print(
            f"\nSlot             : {slot}"
        )

        print(
            f"Already selected : "
            f"{selected_recipe_ids}"
        )

        print(
            f"Candidates       : "
            f"{candidate_ids}"
        )

        # Every old selection must be absent.
        assert set(
            selected_recipe_ids
        ).isdisjoint(
            set(
                candidate_ids
            )
        )

        if candidate_ids:

            selected_recipe = (
                candidate_ids[0]
            )

            assert (
                selected_recipe
                not in selected_recipe_ids
            )

            selected_recipe_ids.append(
                selected_recipe
            )

            print(
                f"Manager selected : "
                f"{selected_recipe}"
            )

    # All Manager selections must be unique.
    assert len(
        selected_recipe_ids
    ) == len(
        set(
            selected_recipe_ids
        )
    )


# ============================================================
# TEST 15
# ALL AVAILABLE RECIPES SELECTED
# ============================================================

def test_all_available_recipes_selected():

    agent = RecipeAgent(
        max_candidates=5
    )

    user_state = {
        "dietary_restrictions": [],
        "preferred_cuisines": [],
        "preferred_meal_types": [],
    }

    first_result = agent.run(
        user_state=user_state,

        meal_slot={
            "date": "2026-10-07",
            "meal_type": "Dinner",
        },

        selected_recipe_ids=[],
    )

    first_candidates = (
        first_result[
            "candidate_recipe_ids"
        ]
    )

    assert first_candidates

    recipes = get_candidate_recipes(
        first_candidates
    )

    filtered = (
        agent
        ._exclude_selected_recipes(
            recipes,
            first_candidates,
        )
    )

    assert filtered.empty


# ============================================================
# TEST 16
# FINAL REPETITION SAFETY CHECK
# ============================================================

def test_final_repetition_safety_check():

    agent = RecipeAgent()

    candidate_ids = [
        "R001",
        "R002",
        "R003",
        "R004",
        "R005",
    ]

    selected_recipe_ids = [
        "R001",
        "R003",
        "R005",
    ]

    result = (
        agent
        ._final_repetition_check(
            candidate_ids,
            selected_recipe_ids,
        )
    )

    assert result == [
        "R002",
        "R004",
    ]


# ============================================================
# TEST 17
# DUPLICATE OUTPUT PROTECTION
# ============================================================

def test_duplicate_candidate_protection():

    agent = RecipeAgent()

    candidate_ids = [
        "R001",
        "R001",
        "R002",
        "R002",
        "R003",
    ]

    result = (
        agent
        ._final_repetition_check(
            candidate_ids,
            selected_recipe_ids=[],
        )
    )

    assert result == [
        "R001",
        "R002",
        "R003",
    ]