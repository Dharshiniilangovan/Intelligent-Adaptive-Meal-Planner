
from datetime import date
from types import SimpleNamespace

import pytest

from src.planning.meal_slot import MealSlot
from src.planning.plan_state import PlanState
from src.planning.multi_meal_planner import MultiMealPlanner
from src.agents.grocery_agent import (
    calculate_incremental_basket_cost,
)


CATALOG = [
    {
        "ingredient_id": "ING_OIL",
        "ingredient_name": "olive oil",
        "package_quantity": 500,
        "package_unit": "ml",
        "price": 5.25,
    }
]


def recipe(recipe_id, quantity):
    return {
        "recipe_id": recipe_id,
        "ingredients": [
            {
                "ingredient_id": "ING_OIL",
                "ingredient_name": "olive oil",
                "quantity": quantity,
                "unit": "ml",
            }
        ],
    }


def decision(recipe_id, quantity, price=5.25):
    return {
        "recipe_id": recipe_id,
        "status": "feasible",
        "ingredient": {
            "required_ingredients": recipe(
                recipe_id, quantity
            )["ingredients"]
        },
        "grocery": {
            "items": [
                {
                    "ingredient_id": "ING_OIL",
                    "ingredient_name": "olive oil",
                    "package_quantity": 500,
                    "package_unit": "ml",
                    "price_per_package": price,
                    "total_cost": price,
                    "purchase_basis": "exact_quantity",
                    "match_status": "matched",
                }
            ],
            "known_cost": price,
        },
    }


def make_state():
    slots = [
        MealSlot(date(2026, 10, 9), "lunch"),
        MealSlot(date(2026, 10, 9), "dinner"),
    ]

    return PlanState(
        slots=slots,
        initial_budget=50.0,
        initial_inventory={},
        current_inventory={},
    )


def make_planner():
    return MultiMealPlanner(
        manager=SimpleNamespace()
    )


def test_first_meal_purchases_package():
    result = calculate_incremental_basket_cost(
        [],
        recipe("R001", 30),
        inventory=[],
        product_catalog=CATALOG,
    )

    assert result["known_incremental_cost"] == 5.25
    assert result["projected_incremental_cost"] == 5.25


def test_second_meal_reuses_package():
    result = calculate_incremental_basket_cost(
        [recipe("R001", 30)],
        recipe("R002", 20),
        inventory=[],
        product_catalog=CATALOG,
    )

    assert result["known_incremental_cost"] == 0.0
    assert result["projected_incremental_cost"] == 0.0
    assert result["additional_items"][0]["additional_packages"] == 0


def test_third_meal_requires_additional_package():
    result = calculate_incremental_basket_cost(
        [recipe("R001", 400)],
        recipe("R002", 200),
        inventory=[],
        product_catalog=CATALOG,
    )

    assert result["known_incremental_cost"] == 5.25
    assert result["projected_incremental_cost"] == 5.25


def test_plan_state_tracks_incremental_spending():
    state = make_state()

    state.add_selected_meal(
        state.slots[0],
        "R001",
        decision("R001", 30),
        estimated_cost=5.25,
    )

    state.add_selected_meal(
        state.slots[1],
        "R002",
        decision("R002", 20),
        estimated_cost=0.0,
    )

    assert state.estimated_spent == 5.25
    assert state.remaining_budget == 44.75
    assert len(state.selected_meals) == 2


def test_final_basket_matches_incremental_spending():
    planner = make_planner()
    state = make_state()

    state.add_selected_meal(
        state.slots[0],
        "R001",
        decision("R001", 30),
        estimated_cost=5.25,
    )

    state.add_selected_meal(
        state.slots[1],
        "R002",
        decision("R002", 20),
        estimated_cost=0.0,
    )

    basket = planner._build_final_grocery_basket(state)

    assert basket["projected_cost_complete"] is True
    assert basket["projected_cost"] == pytest.approx(5.25)
    assert state.estimated_spent == pytest.approx(
        basket["projected_cost"]
    )


def test_llm_estimate_remains_provisional():
    estimated_catalog = [
        {
            "ingredient_name": "olive oil",
            "package_quantity": 500,
            "package_unit": "ml",
            "price": 5.25,
            "purchase_basis": "llm_estimated_package",
            "match_status": "estimated_no_retail_match",
            "estimated_total_cost": 5.25,
        }
    ]

    result = calculate_incremental_basket_cost(
        [],
        {
            "recipe_id": "R003",
            "ingredients": [
                {
                    "ingredient_name": "olive oil",
                    "quantity": 30,
                    "unit": "ml",
                }
            ],
        },
        inventory=[],
        product_catalog=estimated_catalog,
    )

    assert result["known_incremental_cost"] == 0.0
    assert result["projected_incremental_cost"] == 5.25
    assert result["projected_cost_complete"] is True


def test_non_budget_rejections_are_not_overridden():
    planner = make_planner()
    state = make_state()

    candidate = {
        "recipe_id": "R004",
        "status": "rejected",
        "reasoning": {
            "status": "rejected",
            "failed_constraints": [
                {
                    "constraint": "cooking_time",
                    "status": "fail",
                }
            ],
        },
    }

    planner._get_candidates = lambda **kwargs: ["R004"]
    planner._evaluate_candidate = lambda **kwargs: candidate

    result = planner._plan_single_slot(
        user_state={"budget": 50.0},
        slot=state.slots[0],
        plan_state=state,
    )

    assert result["selected"] is False
    assert len(state.selected_meals) == 0
    assert state.estimated_spent == 0.0
    assert len(state.rejected_candidates) == 1
