from datetime import date

from src.planning.plan_state import PlanState
from src.planning.meal_slot import MealSlot
from src.planning.multi_meal_planner import MultiMealPlanner
import pytest

def test_prepared_leftover_allocation():

    slot = MealSlot(
        date=date(2026, 10, 14),
        meal_type="dinner",
        max_cooking_time=30,
    )

    state = PlanState(
        slots=[slot],
        initial_budget=100,
    )

    state.record_prepared_leftover(
        leftover_id="L001",
        recipe_id="R12345",
        servings_remaining=3,
        prepared_date="2026-10-13",
        storage="refrigerated",
        expires_on="2026-10-16",
    )

    allocated, remaining_slots = (
        MultiMealPlanner._allocate_prepared_leftovers(
            plan_state=state,
            remaining_slots=[slot],
            approved_leftover_ids=["L001"],
        )
    )

    assert len(allocated) == 1
    assert len(remaining_slots) == 0

    assert allocated[0]["recipe_id"] == "R12345"
    assert allocated[0]["meal_source"] == "prepared_leftover"
    assert allocated[0]["estimated_cost"] == 0.0

    assert state.prepared_leftovers[0]["servings_remaining"] == 2

    assert any(
        event["event"] == "prepared_leftover_allocated"
        for event in state.execution_trace
    )

from copy import deepcopy
from datetime import date
from unittest.mock import patch

from src.planning.plan_state import PlanState
from src.planning.meal_slot import MealSlot
from src.planning.multi_meal_planner import MultiMealPlanner


def test_skip_and_replan_reuses_prepared_leftovers():

    # -----------------------------------------
    # 1. Create three meal slots
    # -----------------------------------------

    slots = [
        MealSlot(
            date=date(2026, 10, 13),
            meal_type="dinner",
            max_cooking_time=30,
        ),
        MealSlot(
            date=date(2026, 10, 14),
            meal_type="dinner",
            max_cooking_time=30,
        ),
        MealSlot(
            date=date(2026, 10, 15),
            meal_type="dinner",
            max_cooking_time=30,
        ),
    ]

    state = PlanState(
        slots=slots,
        initial_budget=100.0,
        initial_inventory={},
        current_inventory={},
    )

    # -----------------------------------------
    # 2. Record three prepared servings
    # -----------------------------------------

    state.record_prepared_leftover(
        leftover_id="L001",
        recipe_id="R12345",
        servings_remaining=3,
        prepared_date="2026-10-13",
        storage="refrigerated",
        expires_on="2026-10-16",
    )

    # Per-serving nutrition from the prepared recipe.
    state.prepared_leftovers[0]["nutrition"] = {
        "calories": 350,
        "protein_g": 14,
        "carbs_g": 45,
        "fat_g": 12,
    }

    # -----------------------------------------
    # 3. Preserve an already completed meal
    # -----------------------------------------

    completed_meal = {
        "slot": slots[0].to_dict(),
        "recipe_id": "R99999",
        "estimated_cost": 0.0,
        "decision": {
            "recipe_id": "R99999",
            "recipe": {
                "calories": 400,
                "protein_g": 20,
                "carbs_g": 50,
                "fat_g": 10,
            },
            "ingredient": {
                "required_ingredients": []
            },
            "grocery": {
                "items": []
            },
        },
    }

    state.selected_meals = [completed_meal]
    state.used_recipe_ids = {"R99999"}

    original_state = deepcopy(state)

    # -----------------------------------------
    # 4. Mock optimizer
    # -----------------------------------------

    def fake_optimizer(
        user_state,
        initial_state,
        beam_width,
    ):
        return deepcopy(initial_state)

    planner = MultiMealPlanner(manager=None)

    # -----------------------------------------
    # 5. Skip second meal and replan
    # -----------------------------------------

    with patch.object(
        planner,
        "_optimize_meal_plan",
        side_effect=fake_optimizer,
    ):
        result = planner.skip_and_replan(
            user_state={
                "budget": 100,
                "approved_leftover_ids": ["L001"],
            },
            plan_state=state,
            slot_id=slots[1].slot_id,
            completed_slot_ids={slots[0].slot_id},
        )

    # -----------------------------------------
    # 6. Check resulting plan
    # -----------------------------------------

    updated = result["plan"]
    selected = updated["selected_meals"]

    assert len(selected) == 2

    selected_ids = {
        meal["slot"]["slot_id"]
        for meal in selected
    }

    # Completed meal preserved.
    assert slots[0].slot_id in selected_ids

    # Skipped meal remains skipped.
    assert slots[1].slot_id not in selected_ids

    # Future slot filled using prepared leftovers.
    assert slots[2].slot_id in selected_ids

    leftover_meals = [
        meal
        for meal in selected
        if meal.get("meal_source") == "prepared_leftover"
    ]

    assert len(leftover_meals) == 1

    assert leftover_meals[0]["recipe_id"] == "R12345"
    assert leftover_meals[0]["leftover_id"] == "L001"
    assert leftover_meals[0]["estimated_cost"] == 0.0

    # -----------------------------------------
    # 7. Check remaining prepared servings
    # -----------------------------------------

    assert (
        updated["prepared_leftovers"][0][
            "servings_remaining"
        ] == 2
    )

    # Original state must not be mutated.
    assert (
        state.prepared_leftovers
        == original_state.prepared_leftovers
    )

    # -----------------------------------------
    # 8. Check grocery and inventory behavior
    # -----------------------------------------

    basket = result["grocery_basket"]

    assert basket["items"] == []

    # No raw ingredient consumption for leftovers.
    assert updated["inventory"]["current"] == {}

    # -----------------------------------------
    # 9. Check nutrition
    # -----------------------------------------
    
    nutrition = result["nutrition_summary"]

    # Completed meal: 400 calories, 20g protein
    # Leftover meal: 350 calories, 14g protein

    total_calories = sum(
       day.get("calories", 0)
       for day in nutrition.values()
    )

    total_protein = sum(
        day.get("protein_g", 0)
        for day in nutrition.values()
    )

    assert total_calories == pytest.approx(750)
    assert total_protein == pytest.approx(34)


    assert any(
        event.get("event") == "prepared_leftover_allocated"
        for event in updated["execution_trace"]
    )

    # -----------------------------------------
    # 10. Check skipped slot
    # -----------------------------------------

    assert any(
        item["slot_id"] == slots[1].slot_id
        for item in updated["skipped_slots"]
    )

    print("Leftover-aware replanning integration PASSED")

from src.planning.cooking_schedule import build_cooking_schedule


def test_prepared_leftover_does_not_create_cooking_session():

    selected_meals = [
        {
            "recipe_id": "R12345",
            "meal_source": "prepared_leftover",
            "slot": {
                "slot_id": "2026-10-14_dinner",
                "date": "2026-10-14",
            },
        }
    ]

    schedule = build_cooking_schedule(
        selected_meals=selected_meals,
        max_sessions=2,
    )

    assert schedule["session_count"] == 0
    assert schedule["sessions"] == []
    assert schedule["weekly_session_counts"] == {}
    assert schedule["valid"] is True
def test_all_leftover_plan_has_zero_grocery_cost():
    planner = MultiMealPlanner(manager=None)

    state = PlanState(
        slots=[],
        initial_budget=100,
    )

    state.selected_meals = [
        {
            "recipe_id": "R12345",
            "meal_source": "prepared_leftover",
            "estimated_cost": 0.0,
        }
    ]

    basket = planner._build_final_grocery_basket(state)

    assert basket["items"] == []
    assert basket["projected_cost"] == 0.0
    assert basket["projected_cost_complete"] is True
    assert basket["planning_cost"] == 0.0
    assert basket["planning_cost_complete"] is True


def test_mixed_leftover_and_new_recipe_real_optimizer(monkeypatch):
    """
    Verify that the real optimizer can combine:
    - One completed meal
    - One skipped meal
    - One prepared leftover
    - One newly selected recipe

    External recipe evaluation and grocery pricing are mocked.
    """
    from copy import deepcopy
    from datetime import date

    from src.planning.meal_slot import MealSlot
    from src.planning.plan_state import PlanState
    from src.planning.multi_meal_planner import MultiMealPlanner

    slots = [
        MealSlot(date=date(2026, 10, 13),
                 meal_type="dinner", max_cooking_time=30),
        MealSlot(date=date(2026, 10, 14),
                 meal_type="dinner", max_cooking_time=30),
        MealSlot(date=date(2026, 10, 15),
                 meal_type="dinner", max_cooking_time=30),
        MealSlot(date=date(2026, 10, 16),
                 meal_type="dinner", max_cooking_time=30),
    ]

    state = PlanState(
        slots=slots,
        initial_budget=100.0,
        initial_inventory={},
        current_inventory={},
    )

    state.record_prepared_leftover(
        leftover_id="L001",
        recipe_id="R12345",
        servings_remaining=1,
        prepared_date="2026-10-13",
        storage="refrigerated",
        expires_on="2026-10-16",
    )

    state.prepared_leftovers[0]["nutrition"] = {
        "calories": 350,
        "protein_g": 14,
        "carbs_g": 45,
        "fat_g": 12,
    }

    completed = {
        "slot": slots[0].to_dict(),
        "recipe_id": "R99999",
        "estimated_cost": 0.0,
        "decision": {
            "recipe_id": "R99999",
            "recipe": {
                "calories": 400,
                "protein_g": 20,
                "carbs_g": 50,
                "fat_g": 10,
            },
            "ingredient": {
                "required_ingredients": []
            },
            "grocery": {"items": []},
        },
    }

    state.selected_meals = [completed]
    state.used_recipe_ids = {"R99999"}

    planner = MultiMealPlanner(manager=None)

    # Mock recipe retrieval, not the optimizer.
    def fake_get_candidates(user_state, slot, plan_state):
        return ["RNEW01"]

    # Mock external Manager candidate evaluation.
    def fake_evaluate_candidate(
        user_state, slot, recipe_id, plan_state
    ):
        return {
            "recipe_id": recipe_id,
            "recipe": {
                "calories": 500,
                "protein_g": 25,
                "carbs_g": 60,
                "fat_g": 15,
            },
            "reasoning": {
                "hard_constraints": [
                    {"constraint": "allergy", "status": "pass"},
                    {"constraint": "diet", "status": "pass"},
                ],
            },
            "ingredient": {
                "required_ingredients": [
                    {
                        "ingredient_name": "rice",
                        "quantity": 100,
                        "unit": "g",
                    }
                ]
            },
            "grocery": {
                "items": [
                    {
                        "ingredient_name": "rice",
                        "package_quantity": 100,
                        "package_unit": "g",
                        "price": 5.0,
                    }
                ],
                "projected_cost_complete": True,
                "projected_cost": 5.0,
            },
        }

    # Deterministic grocery pricing for this integration test.
    # Preserve the production method for the all-leftover case.
    original_basket = planner._build_final_grocery_basket

    def fake_build_basket(plan_state):
        non_leftover = [
            meal
            for meal in plan_state.selected_meals
            if meal.get("meal_source") != "prepared_leftover"
        ]

        has_new_recipe = any(
            meal["recipe_id"] == "RNEW01"
            for meal in non_leftover
        )

        if not has_new_recipe:
            basket = original_basket(plan_state)

            # The completed fixture has no ingredient data.
            # Treat its already-paid cost as zero.
            if basket.get("projected_cost") is None:
                basket = {
                    **basket,
                    "projected_cost": 0.0,
                    "projected_cost_complete": True,
                    "planning_cost": 0.0,
                    "planning_cost_complete": True,
                }
            return basket

        return {
            "items": [
                {
                    "name": "rice",
                    "package_quantity": 100,
                    "package_unit": "g",
                    "packages": 1,
                    "purchase_cost": 5.0,
                }
            ],
            "known_cost": 5.0,
            "projected_cost": 5.0,
            "projected_cost_complete": True,
            "planning_cost": 5.0,
            "planning_cost_complete": True,
            "all_items_priced": True,
            "unpriced_items": [],
            "aggregated_requirements": [],
            "status": "complete",
        }

    monkeypatch.setattr(
        planner, "_get_candidates", fake_get_candidates
    )
    monkeypatch.setattr(
        planner, "_evaluate_candidate", fake_evaluate_candidate
    )
    monkeypatch.setattr(
        planner, "_build_final_grocery_basket", fake_build_basket
    )

    result = planner.skip_and_replan(
        user_state={
            "budget": 100,
            "approved_leftover_ids": ["L001"],
            "max_recipe_repetitions": 2,
            "cook_frequency": 2,
        },
        plan_state=state,
        slot_id=slots[1].slot_id,
        completed_slot_ids={slots[0].slot_id},
    )

    updated = result["plan"]
    selected = updated["selected_meals"]

    # All three non-skipped slots should be filled.
    assert len(selected) == 3

    by_slot = {
        meal["slot"]["slot_id"]: meal
        for meal in selected
    }

    # Completed meal preserved.
    assert by_slot[slots[0].slot_id]["recipe_id"] == "R99999"

    # Skipped meal excluded.
    assert slots[1].slot_id not in by_slot

    # Prepared leftover allocated.
    leftover = by_slot[slots[2].slot_id]
    assert leftover["meal_source"] == "prepared_leftover"
    assert leftover["recipe_id"] == "R12345"

    # Remaining slot filled by real optimizer.
    new_meal = by_slot[slots[3].slot_id]
    assert new_meal["recipe_id"] == "RNEW01"

    # One prepared serving consumed.
    assert (
        updated["prepared_leftovers"][0]["servings_remaining"]
        == 0
    )

    # Only the new recipe requires groceries.
    basket = result["grocery_basket"]
    assert basket["projected_cost"] == 5.0
    assert len(basket["items"]) == 1
    assert basket["items"][0]["name"] == "rice"

    # No leftover recipe ingredients purchased again.
    assert all(
        item.get("name") != "R12345"
        for item in basket["items"]
    )

    # Reconciliation uses only the new recipe's ingredients.
    assert updated["inventory"]["current"]["rice"]["quantity"] == 0

    # Nutrition includes completed, leftover and new meals.
    nutrition = result["nutrition_summary"]
    total_calories = sum(
        day.get("calories", 0)
        for day in nutrition.values()
    )
    assert total_calories == pytest.approx(1250)

    # Input state remains unchanged.
    assert state.prepared_leftovers[0]["servings_remaining"] == 1

    # Leftover allocation was recorded.
    assert any(
        event.get("event") == "prepared_leftover_allocated"
        for event in updated["execution_trace"]
    )

    print("Mixed leftover/new-recipe optimizer test PASSED")
