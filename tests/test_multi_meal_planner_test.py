from datetime import date

import pytest

from src.planning.meal_slot import (
    generate_meal_slots,
)

from src.planning.plan_state import (
    PlanState,
)

from src.planning.plan_validator import (
    validate_plan,
)

from src.planning.multi_meal_planner import (
    MultiMealPlanner,
)

# ======================================================
# FAKES
# ======================================================


class FakeRecipeAgent:
    def __init__(self):
        self.calls = []

    def run(
        self,
        user_state,
        meal_slot,
        selected_recipe_ids=None,
        recent_cuisines=None,
        max_candidates=None,
    ):
        selected_recipe_ids = selected_recipe_ids or []

        self.calls.append(
            {
                "user_state": user_state,
                "meal_slot": meal_slot,
                "selected_recipe_ids": selected_recipe_ids,
                "max_candidates": max_candidates,
            }
        )

        candidates = [
            "R001",
            "R002",
            "R003",
            "R004",
            "R005",
            "R006",
            "R007",
        ]

        candidates = [
            recipe_id
            for recipe_id in candidates
            if recipe_id not in selected_recipe_ids
        ]

        if max_candidates is not None:
            candidates = candidates[:max_candidates]

        return {
            "agent": "recipe",
            "status": "success",
            "data": {"candidate_recipe_ids": candidates},
            "warnings": [],
            "errors": [],
        }


class FakeManager:
    def __init__(self):
        self.recipe_agent = FakeRecipeAgent()
        self.calls = []

    def evaluate_candidate(
        self,
        recipe_id,
        user_state,
        meal_context,
        defer_budget_to_planner=False,
    ):
        self.calls.append(recipe_id)

        if recipe_id == "R001":
            return {
                "recipe_id": recipe_id,
                "status": "rejected",
                "reasoning": {
                    "status": "rejected",
                    "hard_constraints": [
                        {
                            "constraint": "allergy",
                            "status": "fail",
                            "reason": "Peanut allergy",
                        }
                    ],
                    "failed_constraints": ["allergy"],
                },
            }

        # Give each recipe a distinct test ingredient.
        ingredient_id = f"ING_{recipe_id}"
        ingredient_name = f"test_ingredient_{recipe_id}"

        return {
            "recipe_id": recipe_id,
            "status": "feasible",
            "overall_score": 0.8,
            "recipe": {
                "recipe_id": recipe_id,
                "calories_per_serving": 450.0,
                "protein_g_per_serving": 20.0,
                "carbs_g_per_serving": 55.0,
                "fat_g_per_serving": 15.0,
            },
            "reasoning": {
                "status": "feasible",
                "hard_constraints": [
                    {
                        "constraint": "diet",
                        "status": "pass",
                    },
                    {
                        "constraint": "allergy",
                        "status": "pass",
                    },
                    {
                        "constraint": "cooking_time",
                        "status": "pass",
                    },
                    {
                        "constraint": "ingredient_feasibility",
                        "status": "pass",
                    },
                ],
            },
            "ingredient": {
                "recipe_id": recipe_id,
                "required_ingredients": [
                    {
                        "ingredient_id": ingredient_id,
                        "ingredient_name": ingredient_name,
                        "quantity": 100.0,
                        "unit": "g",
                    }
                ],
            },
            "grocery": {
                "recipe_id": recipe_id,
                "items": [
                    {
                        "ingredient_id": ingredient_id,
                        "ingredient": ingredient_name,
                        "required_quantity": 100.0,
                        "required_unit": "g",
                        "product_name": ingredient_name,
                        "package_quantity": 100.0,
                        "package_unit": "g",
                        "packages_needed": 1,
                        "price_per_package": 5.0,
                        "total_cost": 5.0,
                    }
                ],
                "known_cost": 5.0,
                "all_items_priced": True,
                "projected_cost": 5.0,
                "projected_cost_complete": True,
            },
        }


# ======================================================
# MEAL SLOT TESTS
# ======================================================


def test_generate_six_slots():

    slots = generate_meal_slots(
        start_date=date(
            2026,
            10,
            5,
        ),
        days=3,
        meal_types=[
            "lunch",
            "dinner",
        ],
    )

    assert len(slots) == 6

    assert slots[0].meal_type == "lunch"

    assert slots[1].meal_type == "dinner"


def test_slot_ids_are_unique():

    slots = generate_meal_slots(
        start_date=date(
            2026,
            10,
            5,
        ),
        days=3,
        meal_types=[
            "lunch",
            "dinner",
        ],
    )

    ids = [slot.slot_id for slot in slots]

    assert len(ids) == len(set(ids))


# ======================================================
# PLAN STATE TESTS
# ======================================================


def test_plan_state_budget():

    slots = generate_meal_slots(
        date(
            2026,
            10,
            5,
        ),
        1,
        ["lunch"],
    )

    state = PlanState(
        slots=slots,
        initial_budget=50.0,
    )

    state.add_selected_meal(
        slot=slots[0],
        recipe_id="R001",
        decision={"status": "feasible"},
        estimated_cost=12.0,
    )

    assert state.estimated_spent == 12.0

    assert state.remaining_budget == 38.0


def test_recipe_marked_used():

    slots = generate_meal_slots(
        date(
            2026,
            10,
            5,
        ),
        1,
        ["lunch"],
    )

    state = PlanState(
        slots=slots,
        initial_budget=50,
    )

    state.add_selected_meal(
        slots[0],
        "R100",
        {"status": "feasible"},
        5,
    )

    assert "R100" in state.used_recipe_ids


# ======================================================
# VALIDATOR TESTS
# ======================================================


def test_complete_plan_feasible():

    slots = generate_meal_slots(
        date(
            2026,
            10,
            5,
        ),
        1,
        ["lunch"],
    )

    state = PlanState(
        slots=slots,
        initial_budget=50,
    )

    state.add_selected_meal(
        slots[0],
        "R001",
        {"status": "feasible"},
        10,
    )

    result = validate_plan(
        state,
        all_items_priced=True,
        final_grocery_cost=10,
    )

    assert result["status"] == "feasible"


def test_over_budget_plan_infeasible():

    slots = generate_meal_slots(
        date(
            2026,
            10,
            5,
        ),
        1,
        ["lunch"],
    )

    state = PlanState(
        slots=slots,
        initial_budget=10,
    )

    state.add_selected_meal(
        slots[0],
        "R001",
        {"status": "feasible"},
        5,
    )

    result = validate_plan(
        state,
        all_items_priced=True,
        final_grocery_cost=20,
    )

    assert result["status"] == "infeasible"


def test_unknown_price_plan_uncertain():

    slots = generate_meal_slots(
        date(
            2026,
            10,
            5,
        ),
        1,
        ["lunch"],
    )

    state = PlanState(
        slots=slots,
        initial_budget=50,
    )

    state.add_selected_meal(
        slots[0],
        "R001",
        {"status": "feasible"},
        5,
    )

    result = validate_plan(
        state,
        all_items_priced=False,
        final_grocery_cost=5,
    )

    assert result["status"] == "uncertain"


# ======================================================
# MULTI-MEAL PLANNER
# ======================================================


def test_three_day_six_meal_plan():

    manager = FakeManager()

    planner = MultiMealPlanner(
        manager=manager,
        max_candidates_per_slot=7,
    )

    result = planner.plan_meals(
        user_state={
            "budget_remaining": 50,
        },
        start_date=date(
            2026,
            10,
            5,
        ),
        days=3,
        meal_types=[
            "lunch",
            "dinner",
        ],
    )

    plan = result["plan"]

    assert len(plan["slots"]) == 6

    assert len(plan["selected_meals"]) == 6

    assert result["validation"]["status"] == "feasible"


def test_rejected_candidate_retries():

    manager = FakeManager()

    planner = MultiMealPlanner(manager)

    result = planner.plan_meals(
        user_state={"budget_remaining": 50},
        start_date=date(
            2026,
            10,
            5,
        ),
        days=1,
        meal_types=["lunch"],
    )

    plan = result["plan"]

    # R001 should fail allergy

    assert any(item["recipe_id"] == "R001" for item in plan["rejected_candidates"])

    # Planner should retry and select R002

    assert plan["selected_meals"][0]["recipe_id"] == "R002"


def test_selected_recipe_not_repeated():

    manager = FakeManager()

    planner = MultiMealPlanner(manager)

    result = planner.plan_meals(
        user_state={"budget_remaining": 100},
        start_date=date(
            2026,
            10,
            5,
        ),
        days=2,
        meal_types=["lunch"],
    )

    selected = [item["recipe_id"] for item in result["plan"]["selected_meals"]]

    assert len(selected) == len(set(selected))
