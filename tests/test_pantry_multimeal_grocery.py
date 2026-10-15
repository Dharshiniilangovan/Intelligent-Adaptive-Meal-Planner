"""Realistic pantry subtraction and multi-meal grocery integration.

Uses the real normalized requirements of the Day 5 recipes
R30871 (lunch) and R28835 (dinner), retrieved through the Ingredient
Agent from the normalized Ingredient KB. Package sizes match the
Day 5 E2E basket (reports/day5_e2e_output.json).
"""
import copy

import pytest

from src.agents.grocery_agent import (
    aggregate_requirements,
    build_plan_grocery_basket,
    subtract_inventory,
)
from src.agents.ingredient_agent import get_required_ingredients
from src.state.inventory_state import _subtract, consume_inventory
from src.utils.ingredient_conversion_lookup import (
    convert_using_ingredient_factor,
)

LUNCH, DINNER = "R30871", "R28835"

PANTRY = [
    {"ingredient_name": "broccoli", "quantity": 0.25, "unit": "head"},
    {"ingredient_name": "brown rice", "quantity": 100, "unit": "g"},
    {"ingredient_name": "mushroom", "quantity": 50, "unit": "g"},
    {"ingredient_name": "pasta", "quantity": 100, "unit": "g"},
    {"ingredient_name": "olive oil", "quantity": 10, "unit": "ml"},
]

# Retail packages as observed in the Day 5 basket.
CATALOG = [
    {"ingredient_name": name, "package_quantity": quantity,
     "package_unit": unit, "price": price}
    for name, quantity, unit, price in [
        ("broccoli", 1, "head", 3.50),
        ("brown rice", 1, "kg", 4.00),
        ("mushroom", 250, "g", 2.50),
        ("pasta", 500, "g", 2.00),
        ("olive oil", 500, "ml", 8.00),
        ("ginger", 100, "g", 1.50),
        ("broccoli floret", 250, "g", 2.50),
    ]
]

# Required (combined), pantry used, shortage, pantry unit used.
EXPECTED = {
    "broccoli": (150.0, 75.0, 75.0),
    "brown rice": (187.5, 100.0, 87.5),
    "mushroom": (113.5, 50.0, 63.5),
    "pasta": (56.5, 56.5, 0.0),
    "olive oil": (22.5, 10.0, 12.5),
}


@pytest.fixture(scope="module")
def recipes():
    return [
        {"recipe_id": recipe_id,
         "ingredients": get_required_ingredients(recipe_id)}
        for recipe_id in (LUNCH, DINNER)
    ]


@pytest.fixture(scope="module")
def requirement(recipes):
    def find(recipe_id, name):
        recipe = next(r for r in recipes if r["recipe_id"] == recipe_id)
        return next(
            i for i in recipe["ingredients"] if i["ingredient_name"] == name
        )
    return find


@pytest.fixture
def coverage(recipes):
    pantry = copy.deepcopy(PANTRY)
    result = subtract_inventory(aggregate_requirements(recipes), pantry)
    assert pantry == PANTRY
    return {item["ingredient_name"]: item for item in result}


@pytest.fixture
def basket(recipes):
    return build_plan_grocery_basket(
        recipes, copy.deepcopy(PANTRY), copy.deepcopy(CATALOG)
    )


def basket_item(basket, name):
    matches = [item for item in basket["items"] if item["name"] == name]
    return matches[0] if matches else None


# ============================================================
# Section 2-3: real KB requirements and factors
# ============================================================

@pytest.mark.parametrize(
    "recipe_id, name, original, normalized, status",
    [
        (DINNER, "broccoli", ("0.5", "head"), ("150.0", "g"), "estimated_piece_weight"),
        (LUNCH, "brown rice", ("1.0", "cup"), ("187.5", "g"), "estimated_density"),
        (DINNER, "mushroom", ("113.5", "g"), ("113.5", "g"), "exact_mass"),
        (DINNER, "pasta", ("56.5", "g"), ("56.5", "g"), "exact_mass"),
        (LUNCH, "olive oil", ("1.0", "tablespoon"), ("15.0", "ml"), "exact_volume"),
        (DINNER, "olive oil", ("0.5", "tablespoon"), ("7.5", "ml"), "exact_volume"),
    ],
)
def test_kb_requirements_match_day5_recipes(
    requirement, recipe_id, name, original, normalized, status
):
    row = requirement(recipe_id, name)

    assert (row["quantity"], row["unit"]) == original
    assert (
        row["normalized_quantity_per_serving"], row["normalized_unit"]
    ) == normalized
    assert row["conversion_status"] == status


def test_broccoli_head_factor_is_dataset_derived_300g():
    result = convert_using_ingredient_factor("broccoli", 0.25, "head", "g")

    assert result["quantity"] == pytest.approx(75.0)
    assert result["status"] == "estimated"
    assert result["factors"]["head"]["grams_per_unit"] == 300.0
    assert "estimated_piece_weight" in result["factors"]["head"]["source"]


# ============================================================
# Section 4: pantry subtraction
# ============================================================

@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_pantry_used_and_shortage(coverage, name):
    required, used, shortage = EXPECTED[name]
    item = coverage[name]

    assert item["required_quantity"] == pytest.approx(required)
    assert item["inventory_used"] == pytest.approx(used)
    assert item["purchase_required"] == pytest.approx(shortage)


@pytest.mark.parametrize("name", ["brown rice", "mushroom", "pasta", "olive oil"])
def test_formula_for_compatible_units(coverage, name):
    item = coverage[name]
    available = next(p["quantity"] for p in PANTRY if p["ingredient_name"] == name)

    assert item["inventory_used"] == pytest.approx(
        min(item["required_quantity"], available)
    )
    assert item["purchase_required"] == pytest.approx(
        max(0.0, item["required_quantity"] - item["inventory_used"])
    )


def test_no_negative_shortage_or_double_use(coverage):
    for item in coverage.values():
        assert item["purchase_required"] >= 0
        assert item["inventory_used"] >= 0
        assert item["inventory_used"] <= item["required_quantity"] + 1e-9


def test_broccoli_stays_estimated_end_to_end(coverage):
    item = coverage["broccoli"]

    assert item["conversion_status"] == "estimated"
    assert item["inventory_conversion_estimated"] is True
    assert item["inventory_conversion_unresolved"] is False


def test_brown_rice_requirement_is_estimated_not_exact(coverage):
    item = coverage["brown rice"]

    assert item["conversion_status"] == "estimated"
    # Pantry grams are exact; only the cup->g requirement is estimated.
    assert item["inventory_conversion_estimated"] is False


def test_exact_items_carry_no_estimate(coverage):
    for name in ("mushroom", "pasta", "olive oil"):
        assert coverage[name]["conversion_status"] == "exact"
        assert coverage[name]["inventory_conversion_estimated"] is False


def test_unsupported_volume_items_stay_unresolved_with_pantry(recipes):
    pantry = [
        {"ingredient_name": "ginger", "quantity": 100, "unit": "g"},
        {"ingredient_name": "honey", "quantity": 400, "unit": "g"},
    ]
    result = {
        item["ingredient_name"]: item
        for item in subtract_inventory(aggregate_requirements(recipes), pantry)
    }

    for name in ("ginger", "honey"):
        assert result[name]["inventory_conversion_unresolved"] is True
        assert result[name]["inventory_used"] == 0.0
        assert result[name]["purchase_required"] == result[name]["required_quantity"]


def run_inventory_state(recipes, inventory):
    # Planner order: recipes consumed one after another.
    for recipe in recipes:
        for ingredient in recipe["ingredients"]:
            if ingredient["ingredient_name"] in inventory:
                inventory = consume_inventory(inventory, [ingredient])
    return inventory


def test_inventory_state_remaining_pantry(recipes):
    original = {
        p["ingredient_name"]: {"quantity": float(p["quantity"]), "unit": p["unit"]}
        for p in PANTRY
    }
    snapshot = copy.deepcopy(original)

    remaining = run_inventory_state(recipes, original)

    assert original == snapshot
    assert remaining["broccoli"] == {
        "quantity": 0.0, "unit": "head", "conversion_status": "estimated"
    }
    assert remaining["brown rice"]["quantity"] == 0.0
    assert remaining["brown rice"]["conversion_status"] == "estimated"
    assert remaining["mushroom"]["quantity"] == 0.0
    assert remaining["pasta"]["quantity"] == pytest.approx(43.5)
    assert remaining["pasta"]["conversion_status"] == "normalized"
    assert remaining["olive oil"]["quantity"] == 0.0
    for item in remaining.values():
        assert item["quantity"] >= 0


def test_grocery_and_inventory_agree_in_pantry_units(recipes, coverage):
    original = {
        p["ingredient_name"]: {"quantity": float(p["quantity"]), "unit": p["unit"]}
        for p in PANTRY
    }
    remaining = run_inventory_state(recipes, copy.deepcopy(original))

    for name in EXPECTED:
        consumed_in_pantry_unit = (
            original[name]["quantity"] - remaining[name]["quantity"]
        )
        grocery_used = coverage[name]["inventory_used"]
        if original[name]["unit"] != coverage[name]["unit"]:
            grocery_used = convert_using_ingredient_factor(
                name, grocery_used, coverage[name]["unit"], original[name]["unit"]
            )["quantity"]
        assert consumed_in_pantry_unit == pytest.approx(grocery_used), name

    assert original["broccoli"]["quantity"] - remaining["broccoli"]["quantity"] == (
        pytest.approx(0.25)
    )


def test_volume_preserved_requirement_agrees_across_agents(requirement):
    # 0.5 cup broccoli floret is 125 ml in the KB (250 ml cup). Inventory
    # State used to re-derive 120 ml from the 240 ml cup in units.py.
    row = requirement(LUNCH, "broccoli floret")
    grocery = subtract_inventory(
        aggregate_requirements([{"recipe_id": LUNCH, "ingredients": [row]}]),
        [{"ingredient_name": "broccoli floret", "quantity": 500, "unit": "ml"}],
    )[0]
    remaining = consume_inventory(
        {"broccoli floret": {"quantity": 500.0, "unit": "ml"}}, [row]
    )

    assert grocery["inventory_used"] == pytest.approx(125.0)
    assert 500.0 - remaining["broccoli floret"]["quantity"] == pytest.approx(125.0)


def test_inventory_state_clamps_shortage_without_error():
    remaining, status = _subtract(0.25, "head", 150, "g", "broccoli")

    assert remaining == 0.0
    assert status == "estimated"


# ============================================================
# Section 5: multi-meal aggregation
# ============================================================

def test_shared_olive_oil_aggregated_before_subtraction(coverage):
    oil = coverage["olive oil"]

    assert oil["quantity"] == pytest.approx(22.5)
    assert oil["unit"] == "ml"
    assert oil["recipe_ids"] == [LUNCH, DINNER]
    assert [
        (s["recipe_id"], s["quantity"], s["unit"])
        for s in oil["source_requirements"]
    ] == [(LUNCH, "1.0", "tablespoon"), (DINNER, "0.5", "tablespoon")]
    # Pantry deducted once from the 22.5 ml total, not 10 ml per recipe.
    assert oil["inventory_used"] == pytest.approx(10.0)
    assert oil["purchase_required"] == pytest.approx(12.5)


def test_single_recipe_ingredients_stay_independent(recipes):
    aggregated = aggregate_requirements(recipes)
    by_name = {}
    for record in aggregated:
        by_name.setdefault(record["ingredient_name"], []).append(record)

    assert all(len(records) == 1 for records in by_name.values())
    assert by_name["brown rice"][0]["recipe_ids"] == [LUNCH]
    assert by_name["broccoli"][0]["recipe_ids"] == [DINNER]
    assert by_name["mushroom"][0]["recipe_ids"] == [DINNER]
    assert by_name["pasta"][0]["recipe_ids"] == [DINNER]


def test_every_requirement_traceable_to_its_recipe(recipes):
    for record in aggregate_requirements(recipes):
        sources = record["source_requirements"]
        assert sources
        assert record["recipe_ids"] == list(
            dict.fromkeys(s["recipe_id"] for s in sources)
        )


@pytest.mark.parametrize("estimated_first", [True, False])
def test_aggregation_never_promotes_estimated_to_exact(requirement, estimated_first):
    estimated = requirement(DINNER, "broccoli")
    exact = {"ingredient_name": "broccoli", "ingredient_id": estimated["ingredient_id"],
             "quantity": 100, "unit": "g"}
    recipes = [
        {"recipe_id": DINNER, "ingredients": [estimated]},
        {"recipe_id": "R_EXACT", "ingredients": [exact]},
    ]
    if not estimated_first:
        recipes.reverse()

    [record] = aggregate_requirements(recipes)

    assert record["quantity"] == pytest.approx(250.0)
    assert record["conversion_status"] == "estimated"


def test_incompatible_unit_groups_are_not_summed(requirement):
    ml_row = requirement(LUNCH, "green onion")
    grams_row = {"ingredient_name": "green onion",
                 "ingredient_id": ml_row["ingredient_id"],
                 "quantity": 20, "unit": "g"}

    records = aggregate_requirements([
        {"recipe_id": LUNCH, "ingredients": [ml_row]},
        {"recipe_id": DINNER, "ingredients": [grams_row]},
    ])

    assert {(r["unit"], r["quantity"]) for r in records} == {
        ("ml", 30.0), ("g", 20.0)
    }
    for record in records:
        assert record["normalization_status"] == "unresolved"
        assert sorted(record["unresolved_units"]) == ["g", "ml"]


def test_synthetic_two_recipe_rice():
    recipes = [
        {"recipe_id": "RA", "ingredients": [
            {"ingredient_name": "rice", "quantity": 200, "unit": "g"}]},
        {"recipe_id": "RB", "ingredients": [
            {"ingredient_name": "rice", "quantity": 300, "unit": "g"}]},
    ]
    pantry = [{"ingredient_name": "rice", "quantity": 350, "unit": "g"}]

    [item] = subtract_inventory(aggregate_requirements(recipes), pantry)

    assert item["required_quantity"] == pytest.approx(500.0)
    assert item["inventory_used"] == pytest.approx(350.0)
    assert item["purchase_required"] == pytest.approx(150.0)
    assert item["recipe_ids"] == ["RA", "RB"]
    assert pantry[0]["quantity"] == 350

    inventory = {"rice": {"quantity": 350.0, "unit": "g"}}
    for recipe in recipes:
        inventory = consume_inventory(inventory, recipe["ingredients"])
    assert inventory["rice"]["quantity"] == 0.0


# ============================================================
# Section 6: grocery basket generation
# ============================================================

@pytest.mark.parametrize("name", ["broccoli", "brown rice", "mushroom", "olive oil"])
def test_purchase_sized_from_shortage_not_full_requirement(basket, name):
    item = basket_item(basket, name)

    assert item["required_quantity"] == pytest.approx(EXPECTED[name][2])
    assert item["inventory_used"] == pytest.approx(EXPECTED[name][1])


def test_fully_covered_ingredient_has_no_purchase_line(basket):
    assert basket_item(basket, "pasta") is None


@pytest.mark.parametrize(
    "name, packages, leftover, package_status",
    [
        # 87.5 g of a 1 kg pack: one whole package, 0.9125 kg left.
        ("brown rice", 1, 0.9125, "exact"),
        ("mushroom", 1, 186.5, "exact"),
        ("olive oil", 1, 487.5, "exact"),
        # 75 g of a 300 g head: one head, 0.75 head left (estimated).
        ("broccoli", 1, 0.75, "estimated"),
    ],
)
def test_package_rounding_and_leftover(basket, name, packages, leftover, package_status):
    item = basket_item(basket, name)

    assert item["packages"] == packages
    assert isinstance(item["packages"], int)
    assert item["purchased_quantity"] == pytest.approx(packages * item["package_quantity"])
    assert item["leftover_quantity"] == pytest.approx(leftover)
    assert item["package_conversion_status"] == package_status


def test_partial_package_rounds_up_to_whole_packages():
    basket = build_plan_grocery_basket(
        [{"recipe_id": "R1", "ingredients": [
            {"ingredient_name": "rice", "quantity": 1150, "unit": "g"}]}],
        [],
        [{"ingredient_name": "rice", "package_quantity": 1,
          "package_unit": "kg", "price": 4.0}],
    )
    item = basket["items"][0]

    assert item["packages"] == 2
    assert item["leftover_quantity"] == pytest.approx(0.85)


@pytest.mark.parametrize(
    "name, basis, verified, pricing",
    [
        ("mushroom", "calculated_quantity", True, "priced"),
        ("olive oil", "calculated_quantity", True, "priced"),
        ("brown rice", "estimated_quantity", False, "estimated"),
        ("broccoli", "estimated_quantity", False, "estimated"),
        ("ginger", "minimum_retail_package", False, "estimated"),
        ("broccoli floret", "minimum_retail_package", False, "estimated"),
    ],
)
def test_purchase_basis_and_verification(basket, name, basis, verified, pricing):
    item = basket_item(basket, name)

    assert item["purchase_basis"] == basis
    assert item["quantity_coverage_verified"] is verified
    assert item["pricing_status"] == pricing


def test_estimated_pantry_use_blocks_verification_even_with_exact_package():
    # Exact grams requirement and an exact gram package: only the
    # pantry head->g step is estimated, and that alone must block it.
    basket = build_plan_grocery_basket(
        [{"recipe_id": "R1", "ingredients": [
            {"ingredient_name": "broccoli", "quantity": 150, "unit": "g"}]}],
        [{"ingredient_name": "broccoli", "quantity": 0.25, "unit": "head"}],
        [{"ingredient_name": "broccoli", "package_quantity": 500,
          "package_unit": "g", "price": 3.0}],
    )
    item = basket["items"][0]

    assert item["conversion_status"] == "exact"
    assert item["package_conversion_status"] == "exact"
    assert item["inventory_conversion_estimated"] is True
    assert item["required_quantity"] == pytest.approx(75.0)
    assert item["quantity_coverage_verified"] is False
    assert item["pricing_status"] == "estimated"
    assert basket["known_cost"] == 0.0


@pytest.mark.parametrize("name", ["ginger", "broccoli floret"])
def test_unresolved_coverage_has_no_fabricated_leftover(basket, name):
    item = basket_item(basket, name)

    assert item["package_conversion_status"] == "unresolved"
    assert item["leftover_quantity"] is None
    assert item["packages"] == 1


def test_known_cost_counts_only_verified_purchases(basket):
    verified = [i for i in basket["items"] if i["quantity_coverage_verified"]]

    assert {i["name"] for i in verified} >= {"mushroom", "olive oil"}
    assert all(i["pricing_status"] == "priced" for i in verified)
    assert basket["known_cost"] == pytest.approx(
        sum(i["purchase_cost"] for i in verified)
    )
    for item in basket["items"]:
        if not item["quantity_coverage_verified"]:
            assert item["purchase_cost"] is None
