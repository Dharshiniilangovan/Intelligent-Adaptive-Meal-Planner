
import pytest

from src.planning.plan_state import PlanState
from src.planning.multi_meal_planner import MultiMealPlanner


def make_plan_state(
    ingredient_name,
    required_quantity,
    required_unit,
    pantry=None,
    conversion_status="exact_mass",
):
    """Create a minimal plan with one recipe requirement."""

    state = PlanState(
        slots=[],
        initial_budget=100.0,
        initial_inventory=pantry or {},
        current_inventory=pantry.copy() if pantry else {},
    )

    ingredient = {
        "ingredient_name": ingredient_name,
        "quantity": required_quantity,
        "unit": required_unit,
    }

    # Dataset-first normalized requirement.
    if conversion_status == "volume_preserved_no_density":
        ingredient.update({
            "normalized_quantity_per_serving": required_quantity,
            "normalized_unit": required_unit,
            "conversion_status": conversion_status,
        })

    state.selected_meals = [{
        "recipe_id": "R12345",
        "decision": {
            "ingredient": {
                "required_ingredients": [ingredient],
            },
        },
    }]

    return state


def reconciliation_event(state):
    events = [
        event
        for event in state.execution_trace
        if event.get("event")
        == "inventory_reconciliation_incomplete"
    ]
    assert events, "Expected incomplete reconciliation event"
    return events[-1]


# ============================================================
# TEST 1: CONFIRMED GROCERY SHORTAGE
# ============================================================

def test_confirmed_shortage():
    planner = MultiMealPlanner(manager=None)

    state = make_plan_state(
        ingredient_name="rice",
        required_quantity=300,
        required_unit="g",
        pantry={
            "rice": {
                "quantity": 100.0,
                "unit": "g",
            },
        },
    )

    basket = {"items": []}

    result = planner._reconcile_final_inventory(
        state,
        basket,
    )

    assert result is True

    event = reconciliation_event(state)

    assert event["confirmed_shortage_count"] == 1
    assert event["confirmed_shortages"][0][
        "ingredient_name"
    ] == "rice"

    assert event["confirmed_shortages"][0][
        "purchase_required"
    ] == pytest.approx(200.0)

    assert event["unverified_package_count"] == 0

    # Incomplete reconciliation must not commit inventory.
    assert state.current_inventory["rice"]["quantity"] == 100.0


# ============================================================
# TEST 2: UNVERIFIED RETAIL PACKAGE COVERAGE
# ============================================================

def test_unverified_package_coverage():
    planner = MultiMealPlanner(manager=None)

    state = make_plan_state(
        ingredient_name="broccoli floret",
        required_quantity=125,
        required_unit="ml",
        pantry={},
        conversion_status="volume_preserved_no_density",
    )

    basket = {
        "items": [{
            "ingredient_name": "broccoli floret",
            "name": "broccoli floret",
            "package_quantity": 250,
            "package_unit": "g",
            "packages": 1,
            "quantity_coverage_verified": False,
            "package_conversion_status": "unresolved",
        }],
    }

    result = planner._reconcile_final_inventory(
        state,
        basket,
    )

    assert result is True

    event = reconciliation_event(state)

    assert event["unverified_package_count"] == 1

    unverified = event["unverified_package_coverage"][0]

    assert unverified["ingredient_name"] == "broccoli floret"
    assert unverified["required_unit"] == "ml"
    assert unverified["package_unit"] == "g"

    assert event["confirmed_shortage_count"] == 0

    # Do not commit unverified purchased stock.
    assert state.current_inventory == {}


# ============================================================
# TEST 3: FULLY COVERED REQUIREMENT
# ============================================================

def test_fully_covered_inventory():
    planner = MultiMealPlanner(manager=None)

    state = make_plan_state(
        ingredient_name="rice",
        required_quantity=300,
        required_unit="g",
        pantry={
            "rice": {
                "quantity": 100.0,
                "unit": "g",
            },
        },
    )

    basket = {
        "items": [{
            "name": "rice",
            "package_quantity": 400,
            "package_unit": "g",
            "packages": 1,
            "quantity_coverage_verified": True,
            "package_conversion_status": "exact",
        }],
    }

    result = planner._reconcile_final_inventory(
        state,
        basket,
    )

    assert result is True

    # Initial 100 g + purchased 400 g - required 300 g
    # = 200 g remaining.
    assert state.current_inventory["rice"]["quantity"] == (
        pytest.approx(200.0)
    )

    assert any(
        event.get("event") == "inventory_reconciled"
        for event in state.execution_trace
    )

    assert not any(
        event.get("event") == "inventory_reconciliation_incomplete"
        for event in state.execution_trace
    )
