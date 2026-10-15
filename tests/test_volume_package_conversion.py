"""Retail-package matching for volume (ml) requirements.

Covers the eight Day 5 ingredients whose recipe requirement was
normalized to ml while the retail package is sold by mass/count.
Only ingredients with an in-repo density may become estimated;
everything else must stay unresolved and unverified.
"""
import pytest

from src.agents.grocery_agent import (
    aggregate_requirements,
    build_plan_grocery_basket,
    subtract_inventory,
)
from src.planning.multi_meal_planner import MultiMealPlanner
from src.planning.plan_state import PlanState
from src.state.inventory_state import _subtract, consume_inventory
from src.utils.ingredient_conversion_lookup import (
    convert_using_ingredient_factor,
)


def dataset_requirement(name, ml, status="volume_preserved_no_density"):
    return {
        "ingredient_name": name,
        "quantity": ml,
        "unit": "ml",
        "normalized_quantity_per_serving": ml,
        "normalized_unit": "ml",
        "conversion_status": status,
    }


def basket_item(ingredient, package_quantity, package_unit, inventory=None):
    basket = build_plan_grocery_basket(
        recipe_requirements=[{
            "recipe_id": "R30871",
            "ingredients": [ingredient],
        }],
        inventory=inventory or [],
        product_catalog=[{
            "ingredient_name": ingredient["ingredient_name"],
            "package_quantity": package_quantity,
            "package_unit": package_unit,
            "price": 2.00,
        }],
    )
    assert len(basket["items"]) == 1
    return basket, basket["items"][0]


# ============================================================
# Day 5 ingredients: resolved by in-repo density
# ============================================================

def test_green_onion_ml_to_bunch_is_estimated():
    # 30 ml = 2 tbsp; ingredient_conversions.py: 6 g/tbsp, 100 g/bunch.
    basket, item = basket_item(
        dataset_requirement("green onion", 30.0), 1, "bunch"
    )

    assert item["package_conversion_status"] == "estimated"
    assert item["packages"] == 1
    assert item["leftover_quantity"] == pytest.approx(0.88)
    assert item["quantity_coverage_verified"] is False
    assert item["pricing_status"] == "estimated"
    assert item["purchase_cost"] is None
    assert basket["known_cost"] == 0.0


# ============================================================
# Day 5 ingredients: no evidence -> must stay unresolved
# ============================================================

@pytest.mark.parametrize(
    "name, ml, status, package_quantity, package_unit",
    [
        ("ginger", 2.5, "volume_preserved_no_density", 100, "g"),
        ("broccoli floret", 125.0, "volume_preserved_no_density", 250, "g"),
        ("napa cabbage", 125.0, "volume_preserved_no_density", 1, "head"),
        ("bean sprout", 30.0, "volume_preserved_no_density", 200, "g"),
        ("wheat", 7.5, "volume_preserved_no_density", 1, "kg"),
        ("honey", 7.5, "exact_volume", 400, "g"),
        ("cashew nut", 30.0, "volume_preserved_no_density", 150, "g"),
    ],
)
def test_volume_without_density_stays_unresolved(
    name, ml, status, package_quantity, package_unit
):
    _, item = basket_item(
        dataset_requirement(name, ml, status),
        package_quantity,
        package_unit,
    )

    assert item["package_conversion_status"] == "unresolved"
    assert item["quantity_coverage_verified"] is False
    assert item["purchase_basis"] == "minimum_retail_package"
    assert item["packages"] == 1
    # No silent fallback: leftover cannot be computed across units.
    assert item["leftover_quantity"] is None
    assert item["purchase_cost"] is None


@pytest.mark.parametrize(
    "name",
    ["ginger", "broccoli floret", "napa cabbage", "bean sprout",
     "wheat", "honey", "cashew nut"],
)
def test_lookup_never_assumes_one_ml_is_one_gram(name):
    result = convert_using_ingredient_factor(name, 100, "ml", "g")

    assert result["quantity"] is None
    assert result["status"] == "unresolved"


def test_related_preparations_are_not_borrowed():
    # broccoli has a head weight; wheat flour has a CSV density.
    # Neither may be reused for florets or whole wheat.
    assert convert_using_ingredient_factor(
        "broccoli floret", 1, "head", "g"
    )["status"] == "unresolved"
    assert convert_using_ingredient_factor(
        "wheat", 7.5, "ml", "g"
    )["status"] == "unresolved"


def test_lookup_volume_density_for_green_onion():
    result = convert_using_ingredient_factor("green onion", 30, "ml", "g")

    assert result["quantity"] == pytest.approx(12.0)
    assert result["status"] == "estimated"


def test_lookup_volume_to_volume_not_routed_through_density():
    result = convert_using_ingredient_factor(
        "green onion", 15, "ml", "tablespoon"
    )

    assert result["status"] == "unresolved"


# ============================================================
# General fixes beyond the eight ingredients
# ============================================================

def test_package_step_uses_dataset_piece_weight():
    # Was "unresolved" in Day 5: KB has broccoli head = 300 g.
    _, item = basket_item(
        {"ingredient_name": "broccoli", "quantity": 150, "unit": "g"},
        1,
        "head",
    )

    assert item["package_conversion_status"] == "estimated"
    assert item["packages"] == 1
    assert item["leftover_quantity"] == pytest.approx(0.5)
    assert item["quantity_coverage_verified"] is False


def test_package_step_uses_ingredients_own_piece_weight():
    # The KB has a dataset-derived weight for "fried egg" itself.
    _, item = basket_item(
        {"ingredient_name": "fried egg", "quantity": 50, "unit": "g"},
        10,
        "pcs",
    )

    assert item["package_conversion_status"] == "estimated"
    assert item["leftover_quantity"] == pytest.approx(9.0)
    assert item["quantity_coverage_verified"] is False


def test_package_without_any_factor_stays_unresolved():
    _, item = basket_item(
        {"ingredient_name": "test herb", "quantity": 30, "unit": "g"},
        1,
        "head",
    )

    assert item["package_conversion_status"] == "unresolved"
    assert item["quantity_coverage_verified"] is False


def test_estimated_pantry_conversion_does_not_verify_package():
    requirement = {"ingredient_name": "broccoli", "quantity": 300, "unit": "g"}

    # Control: no pantry -> exact grams, exact package -> verified.
    _, control = basket_item(requirement, 500, "g")
    assert control["quantity_coverage_verified"] is True
    assert control["pricing_status"] == "priced"

    # 0.5 head -> ~150 g is an estimate, so the purchase is too.
    basket, item = basket_item(
        requirement,
        500,
        "g",
        inventory=[{"ingredient_name": "broccoli", "quantity": 0.5, "unit": "head"}],
    )

    assert item["inventory_used"] == pytest.approx(150.0)
    assert item["inventory_conversion_estimated"] is True
    assert item["package_conversion_status"] == "exact"
    assert item["quantity_coverage_verified"] is False
    assert item["pricing_status"] == "estimated"
    assert basket["known_cost"] == 0.0


def test_same_unit_estimated_stock_is_flagged():
    # 1 bunch green onion is normalized to an estimated 100 g.
    result = subtract_inventory(
        aggregate_requirements([{
            "recipe_id": "R1",
            "ingredients": [
                {"ingredient_name": "green onion", "quantity": 50, "unit": "g"}
            ],
        }]),
        [{"ingredient_name": "green onion", "quantity": 1, "unit": "bunch"}],
    )[0]

    assert result["inventory_used"] == pytest.approx(50.0)
    assert result["inventory_conversion_estimated"] is True


@pytest.mark.parametrize(
    "ingredient, package_quantity, package_unit, inventory",
    [
        (dataset_requirement("green onion", 30.0), 1, "bunch", None),
        (dataset_requirement("green onion", 30.0), 100, "g", None),
        (dataset_requirement("honey", 7.5, "exact_volume"), 400, "g", None),
        ({"ingredient_name": "broccoli", "quantity": 150, "unit": "g"}, 1, "head", None),
        ({"ingredient_name": "green onion", "quantity": 2, "unit": "tablespoon"}, 1, "bunch", None),
        ({"ingredient_name": "brown rice", "quantity": 0.25, "unit": "cup"}, 1, "kg", None),
        ({"ingredient_name": "broccoli", "quantity": 300, "unit": "g"}, 500, "g",
         [{"ingredient_name": "broccoli", "quantity": 0.5, "unit": "head"}]),
        ({"ingredient_name": "green onion", "quantity": 150, "unit": "g"}, 100, "g",
         [{"ingredient_name": "green onion", "quantity": 1, "unit": "bunch"}]),
    ],
)
def test_estimated_conversion_never_verifies_coverage(
    ingredient, package_quantity, package_unit, inventory
):
    _, item = basket_item(ingredient, package_quantity, package_unit, inventory)

    estimated = (
        item.get("package_conversion_status") != "exact"
        or item.get("conversion_status") != "exact"
        or item.get("inventory_conversion_estimated", False)
        or item.get("inventory_conversion_unresolved", False)
    )

    assert estimated
    assert item["quantity_coverage_verified"] is False
    assert item["pricing_status"] != "priced"


# ============================================================
# Inventory State and planner reconciliation stay consistent
# ============================================================

def test_inventory_state_consumes_green_onion_ml_from_bunch():
    inventory = {"green onion": {"quantity": 1.0, "unit": "bunch"}}

    updated = consume_inventory(
        inventory,
        [{"ingredient_name": "green onion", "quantity": 30, "unit": "ml"}],
    )

    assert updated["green onion"]["quantity"] == pytest.approx(0.88)
    assert updated["green onion"]["unit"] == "bunch"
    assert updated["green onion"]["conversion_status"] == "estimated"
    assert inventory["green onion"]["quantity"] == 1.0


def test_inventory_state_honey_ml_vs_g_stays_unresolved():
    with pytest.raises(ValueError, match="Incompatible inventory units"):
        _subtract(400, "g", 7.5, "ml", "honey")


def test_grocery_and_inventory_agree_on_green_onion_ml():
    grocery = subtract_inventory(
        aggregate_requirements([{
            "recipe_id": "R1",
            "ingredients": [dataset_requirement("green onion", 30.0)],
        }]),
        [{"ingredient_name": "green onion", "quantity": 1, "unit": "bunch"}],
    )[0]
    remaining, status = _subtract(1, "bunch", 30, "ml", "green onion")

    # 1 bunch = 100 g = 250 ml of chopped green onion.
    assert grocery["inventory_used"] == pytest.approx(30.0)
    assert grocery["purchase_required"] == pytest.approx(0.0)
    assert (1 - remaining) * 250 == pytest.approx(grocery["inventory_used"])
    assert status == "estimated"


def make_state(ingredient):
    state = PlanState(
        slots=[],
        initial_budget=100.0,
        initial_inventory={},
        current_inventory={},
    )
    state.selected_meals = [{
        "recipe_id": "R30871",
        "decision": {"ingredient": {"required_ingredients": [ingredient]}},
    }]
    return state


def test_reconciliation_reports_green_onion_as_estimated_not_unresolved():
    planner = MultiMealPlanner(manager=None)
    state = make_state(dataset_requirement("green onion", 30.0))
    basket = {"items": [{
        "name": "green onion",
        "package_quantity": 1.0,
        "package_unit": "bunch",
        "packages": 1,
        "quantity_coverage_verified": False,
        "package_conversion_status": "estimated",
    }]}

    assert planner._reconcile_final_inventory(state, basket) is True

    event = state.execution_trace[-1]
    assert event["event"] == "inventory_reconciled"
    assert event["estimated_conversion_count"] == 1
    assert event["estimated_conversions"][0]["ingredient_name"] == "green onion"


def test_reconciliation_keeps_honey_unresolved():
    planner = MultiMealPlanner(manager=None)
    state = make_state(dataset_requirement("honey", 7.5, "exact_volume"))
    basket = {"items": [{
        "name": "honey",
        "package_quantity": 400.0,
        "package_unit": "g",
        "packages": 1,
        "quantity_coverage_verified": False,
        "package_conversion_status": "unresolved",
    }]}

    assert planner._reconcile_final_inventory(state, basket) is True

    event = state.execution_trace[-1]
    assert event["event"] == "inventory_reconciliation_incomplete"
    assert event["unresolved_count"] == 1
    assert event["unverified_package_count"] == 1
    assert event["estimated_conversion_count"] == 0
    assert state.current_inventory == {}
