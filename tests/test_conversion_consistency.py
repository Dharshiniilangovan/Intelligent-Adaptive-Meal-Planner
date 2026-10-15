"""Recipe -> Grocery -> Inventory -> Planner conversion consistency.

Complements test_volume_package_conversion.py with provenance,
ingredient-identity, shared-pantry and verification-invariant checks.
"""
import itertools

import pytest

from src.agents.grocery_agent import (
    aggregate_requirements,
    build_plan_grocery_basket,
    subtract_inventory,
)
from src.grocery.ingredient_conversions import (
    INGREDIENT_CONVERSIONS,
    estimate_ingredient_mass,
)
from src.planning.multi_meal_planner import MultiMealPlanner
from src.planning.plan_state import PlanState
from src.state.inventory_state import _subtract, consume_inventory
from src.utils.ingredient_conversion_lookup import (
    DATASET_SOURCE,
    LEGACY_TABLE_SOURCE,
    convert_using_ingredient_factor,
)


def plan_basket(ingredients, catalog, inventory=None):
    return build_plan_grocery_basket(
        recipe_requirements=[
            {"recipe_id": f"R{index}", "ingredients": [ingredient]}
            for index, ingredient in enumerate(ingredients)
        ],
        inventory=inventory or [],
        product_catalog=catalog,
    )


def grocery_coverage(recipes, pantry):
    return subtract_inventory(aggregate_requirements(recipes), pantry)


# ============================================================
# Green onion 0.88 bunch: exact provenance
# ============================================================

def test_green_onion_factors_come_from_curated_table():
    entry = INGREDIENT_CONVERSIONS["green onion"]

    assert entry.grams_per_tablespoon == 6
    assert entry.grams_per_bunch == 100
    assert entry.estimated is True
    assert "provisional" in entry.source
    # The table has no ml entry: ml is never read as grams.
    assert estimate_ingredient_mass("green onion", 30, "ml") is None


def test_green_onion_package_provenance_is_reported():
    basket = plan_basket(
        [{
            "ingredient_name": "green onion",
            "quantity": 2.0,
            "unit": "tablespoon",
            "normalized_quantity_per_serving": 30.0,
            "normalized_unit": "ml",
            "conversion_status": "volume_preserved_no_density",
        }],
        [{"ingredient_name": "green onion", "package_quantity": 1,
          "package_unit": "bunch", "price": 1.20}],
    )
    item = basket["items"][0]
    factors = item["package_conversion_factors"]

    # 30 ml * (6 g / 15 ml) = 12 g; 12 g / 100 g per bunch = 0.12 bunch.
    assert factors["ml"]["grams_per_unit"] == pytest.approx(0.4)
    assert factors["ml"]["source"] == (
        f"{LEGACY_TABLE_SOURCE} grams_per_tablespoon / 15 ml"
    )
    assert factors["bunch"]["grams_per_unit"] == pytest.approx(100.0)
    assert factors["bunch"]["source"] == f"{LEGACY_TABLE_SOURCE} grams_per_bunch"
    assert item["leftover_quantity"] == pytest.approx(0.88)
    assert item["package_conversion_status"] == "estimated"
    assert item["quantity_coverage_verified"] is False


def test_dataset_factor_provenance_is_reported():
    result = convert_using_ingredient_factor("broccoli", 150, "g", "head")

    assert result["factors"]["head"] == {
        "grams_per_unit": 300.0,
        "source": DATASET_SOURCE,
    }


def test_exact_package_has_no_estimated_factors():
    item = plan_basket(
        [{"ingredient_name": "rice", "quantity": 500, "unit": "g"}],
        [{"ingredient_name": "rice", "package_quantity": 1,
          "package_unit": "kg", "price": 4.0}],
    )["items"][0]

    assert item["package_conversion_status"] == "exact"
    assert item["package_conversion_factors"] is None


# ============================================================
# Ingredient identity and preparation state
# ============================================================

@pytest.mark.parametrize(
    "alias, unit",
    [
        ("baby carrot", "piece"),
        ("baby zucchini", "piece"),
        ("baby onions", "piece"),
        ("powdered sugar", "tablespoon"),
        ("dried mint", "tablespoon"),
        ("ground mustard seed", "tablespoon"),
        ("canned black beans", "cup"),
        ("sauteed onions", "piece"),
    ],
)
def test_preparation_variants_do_not_borrow_factors(alias, unit):
    assert estimate_ingredient_mass(alias, 1, unit) is None


@pytest.mark.parametrize(
    "alias, unit, grams",
    [
        ("carrots", "piece", 70.0),
        ("carrots, raw", "piece", 70.0),
        ("plum tomatoes", "piece", 65.0),
        ("green onions", "bunch", 100.0),
        ("black-pepper", "tablespoon", 7.0),
    ],
)
def test_spelling_variants_keep_factors(alias, unit, grams):
    assert estimate_ingredient_mass(alias, 1, unit) == (grams, "g")


def test_broccoli_florets_do_not_use_broccoli_head():
    assert convert_using_ingredient_factor(
        "broccoli floret", 1, "head", "g"
    )["status"] == "unresolved"

    with pytest.raises(ValueError, match="Incompatible inventory units"):
        _subtract(1, "head", 100, "g", "broccoli floret")


def test_fried_egg_uses_its_own_dataset_factor():
    result = convert_using_ingredient_factor("fried egg", 50, "g", "piece")

    assert result["quantity"] == pytest.approx(1.0)
    assert result["factors"]["piece"]["source"] == DATASET_SOURCE
    # An unlisted egg preparation does not fall back to "egg".
    assert convert_using_ingredient_factor(
        "scrambled egg", 50, "g", "piece"
    )["status"] == "unresolved"


# ============================================================
# Exact conversions and pantry subtraction
# ============================================================

@pytest.mark.parametrize(
    "available, available_unit, required, required_unit, remaining",
    [
        (1, "kg", 250, "g", 0.75),
        (500, "g", 0.25, "kg", 250.0),
        (1, "l", 250, "ml", 0.75),
        (500, "ml", 0.25, "l", 250.0),
    ],
)
def test_exact_metric_subtraction(
    available, available_unit, required, required_unit, remaining
):
    assert _subtract(
        available, available_unit, required, required_unit, "milk"
    ) == (pytest.approx(remaining), "normalized")


def test_egg_piece_pantry_subtraction_grocery_side():
    item = grocery_coverage(
        [{"recipe_id": "R1", "ingredients": [
            {"ingredient_name": "egg", "quantity": 100, "unit": "g"}
        ]}],
        [{"ingredient_name": "egg", "quantity": 1, "unit": "piece"}],
    )[0]

    assert item["required_quantity"] == 100
    assert item["inventory_used"] == pytest.approx(50.0)
    assert item["purchase_required"] == pytest.approx(50.0)
    assert item["inventory_conversion_estimated"] is True


def test_insufficient_pantry_clamps_without_error():
    inventory = {"broccoli": {"quantity": 0.25, "unit": "head"}}

    updated = consume_inventory(
        inventory,
        [{"ingredient_name": "broccoli", "quantity": 1000, "unit": "g"}],
    )

    assert updated["broccoli"]["quantity"] == 0.0
    assert inventory["broccoli"]["quantity"] == 0.25


def test_multiple_recipes_share_pantry_without_double_counting():
    recipes = [
        {"recipe_id": "R1", "ingredients": [
            {"ingredient_name": "broccoli", "quantity": 150, "unit": "g"}]},
        {"recipe_id": "R2", "ingredients": [
            {"ingredient_name": "broccoli", "quantity": 200, "unit": "g"}]},
    ]
    pantry = [{"ingredient_name": "broccoli", "quantity": 1, "unit": "head"}]

    grocery = grocery_coverage(recipes, pantry)
    assert len(grocery) == 1
    assert grocery[0]["required_quantity"] == pytest.approx(350.0)
    assert grocery[0]["inventory_used"] == pytest.approx(300.0)
    assert grocery[0]["purchase_required"] == pytest.approx(50.0)
    assert pantry[0]["quantity"] == 1

    inventory = {"broccoli": {"quantity": 1.0, "unit": "head"}}
    for recipe in recipes:
        inventory = consume_inventory(inventory, recipe["ingredients"])
    assert inventory["broccoli"]["quantity"] == 0.0


def test_mixed_unit_groups_share_one_pantry_stock():
    # Same ingredient in ml and in g forms two requirement groups;
    # the single pantry bunch must be drawn down once, not twice.
    recipes = [
        {"recipe_id": "R1", "ingredients": [
            {"ingredient_name": "green onion", "quantity": 2, "unit": "tablespoon",
             "normalized_quantity_per_serving": 30.0, "normalized_unit": "ml",
             "conversion_status": "volume_preserved_no_density"}]},
        {"recipe_id": "R2", "ingredients": [
            {"ingredient_name": "green onion", "quantity": 95, "unit": "g"}]},
    ]
    pantry = [{"ingredient_name": "green onion", "quantity": 1, "unit": "bunch"}]

    coverage = {item["unit"]: item for item in grocery_coverage(recipes, pantry)}

    # 1 bunch = 100 g. 30 ml = 12 g; the g group then has 88 g left.
    used_grams = (
        coverage["ml"]["inventory_used"] * 0.4
        + coverage["g"]["inventory_used"]
    )
    assert used_grams == pytest.approx(100.0)
    assert coverage["g"]["purchase_required"] == pytest.approx(7.0)


# ============================================================
# Grocery Agent vs Inventory State
# ============================================================

@pytest.mark.parametrize(
    "name, pantry_qty, pantry_unit, required, required_unit, grams_per_pantry_unit",
    [
        ("broccoli", 0.5, "head", 300, "g", 300.0),
        ("egg", 2, "piece", 60, "g", 50.0),
        ("green onion", 1, "bunch", 30, "ml", 100.0),
        # carrot is in both tables (dataset 65 g, curated 70 g):
        # both paths must apply the same one.
        ("carrot", 1, "piece", 15, "ml", 70.0),
        ("plum tomato", 1, "piece", 100, "g", 65.0),
    ],
)
def test_grocery_and_inventory_consume_same_grams(
    name, pantry_qty, pantry_unit, required, required_unit, grams_per_pantry_unit
):
    grocery = grocery_coverage(
        [{"recipe_id": "R1", "ingredients": [
            {"ingredient_name": name, "quantity": required, "unit": required_unit}
        ]}],
        [{"ingredient_name": name, "quantity": pantry_qty, "unit": pantry_unit}],
    )[0]
    remaining, status = _subtract(
        pantry_qty, pantry_unit, required, required_unit, name
    )

    inventory_grams = (pantry_qty - remaining) * grams_per_pantry_unit
    if required_unit == "ml":
        density = convert_using_ingredient_factor(name, 1, "ml", "g")["quantity"]
        grocery_grams = grocery["inventory_used"] * density
    else:
        grocery_grams = grocery["inventory_used"]

    assert grocery_grams == pytest.approx(inventory_grams)
    assert status == "estimated"
    assert grocery["inventory_conversion_estimated"] is True


# ============================================================
# Verification invariant
# ============================================================

GRID_REQUIREMENTS = [
    {"ingredient_name": "broccoli", "quantity": 150, "unit": "g"},
    {"ingredient_name": "broccoli", "quantity": 1, "unit": "head"},
    {"ingredient_name": "green onion", "quantity": 2, "unit": "tablespoon"},
    {"ingredient_name": "green onion", "quantity": 2, "unit": "tablespoon",
     "normalized_quantity_per_serving": 30.0, "normalized_unit": "ml",
     "conversion_status": "volume_preserved_no_density"},
    {"ingredient_name": "honey", "quantity": 0.5, "unit": "tablespoon",
     "normalized_quantity_per_serving": 7.5, "normalized_unit": "ml",
     "conversion_status": "exact_volume"},
    {"ingredient_name": "egg", "quantity": 2, "unit": "count",
     "normalized_quantity_per_serving": 100.0, "normalized_unit": "g",
     "conversion_status": "estimated_piece_weight"},
    {"ingredient_name": "rice", "quantity": 300, "unit": "g"},
    {"ingredient_name": "milk", "quantity": 250, "unit": "ml"},
]
GRID_PACKAGES = [(500, "g"), (1, "kg"), (1, "head"), (1, "bunch"),
                 (10, "pcs"), (1, "l"), (400, "ml")]
GRID_PANTRIES = [
    None,
    {"quantity": 0.25, "unit": "head"},
    {"quantity": 1, "unit": "piece"},
    {"quantity": 50, "unit": "g"},
    {"quantity": 0.5, "unit": "bunch"},
]


def _exact_inputs(item):
    return (
        item.get("conversion_status") == "exact"
        and item.get("package_conversion_status") == "exact"
        and item.get("normalization_status") == "resolved"
        and not item.get("inventory_conversion_estimated")
        and not item.get("inventory_conversion_unresolved")
    )


@pytest.mark.parametrize(
    "requirement, package, pantry",
    list(itertools.product(GRID_REQUIREMENTS, GRID_PACKAGES, GRID_PANTRIES)),
)
def test_verified_coverage_requires_every_step_exact(requirement, package, pantry):
    name = requirement["ingredient_name"]
    basket = plan_basket(
        [requirement],
        [{"ingredient_name": name, "package_quantity": package[0],
          "package_unit": package[1], "price": 2.0}],
        inventory=[dict(pantry, ingredient_name=name)] if pantry else None,
    )

    for item in basket["items"]:
        if item["quantity_coverage_verified"]:
            assert _exact_inputs(item), item
        if not _exact_inputs(item):
            assert item["quantity_coverage_verified"] is False
            assert item["pricing_status"] != "priced"


# ============================================================
# Planner commit behavior
# ============================================================

def test_incomplete_reconciliation_does_not_commit_inventory():
    pantry = {"rice": {"quantity": 500.0, "unit": "g"}}
    state = PlanState(
        slots=[],
        initial_budget=100.0,
        initial_inventory={"rice": dict(pantry["rice"])},
        current_inventory={"rice": dict(pantry["rice"])},
    )
    state.selected_meals = [{
        "recipe_id": "R28835",
        "decision": {"ingredient": {"required_ingredients": [
            {"ingredient_name": "rice", "quantity": 100, "unit": "g"},
            {"ingredient_name": "honey", "quantity": 7.5, "unit": "ml",
             "normalized_quantity_per_serving": 7.5, "normalized_unit": "ml",
             "conversion_status": "exact_volume"},
        ]}},
    }]
    basket = {"items": [{
        "name": "honey", "package_quantity": 400.0, "package_unit": "g",
        "packages": 1, "quantity_coverage_verified": False,
        "package_conversion_status": "unresolved",
    }]}

    assert MultiMealPlanner(manager=None)._reconcile_final_inventory(
        state, basket
    ) is True

    event = state.execution_trace[-1]
    assert event["event"] == "inventory_reconciliation_incomplete"
    assert event["unresolved_conversions"] == [
        {"ingredient_name": "honey", "unit": "ml"}
    ]
    # Rice was coverable, but nothing is committed while honey is not.
    assert state.current_inventory == pantry
    assert state.initial_inventory == pantry
