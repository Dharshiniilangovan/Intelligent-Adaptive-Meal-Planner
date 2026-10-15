"""Three days x lunch + dinner over real KB recipes (prices mocked,
see tests/planning_harness.py). Expected values are recomputed
independently from the KB rows of the selected recipes."""
import collections
import copy
import math
from datetime import date

import pytest

from src.agents.grocery_agent import classify_requirement
from src.agents.ingredient_agent import get_required_ingredients
from src.state.inventory_state import add_purchase
from tests.planning_harness import (
    build_planner,
    reconciliation_event,
    repository,
    selected_ids,
    user_state,
)

POOL = ["R28835", "R20231", "R19634", "R09645", "R03304", "R02821", "R18958", "R06690"]
PANTRY = [
    {"ingredient_name": "olive oil", "quantity": 30, "unit": "ml"},
    {"ingredient_name": "garlic", "quantity": 2, "unit": "clove"},
    {"ingredient_name": "mushroom", "quantity": 100, "unit": "g"},
    {"ingredient_name": "lemon juice", "quantity": 20, "unit": "ml"},
]
BUDGET = 120.0
SCHEDULE = {
    "2026-10-07": {"lunch": {"max_cooking_time": 30}, "dinner": {"max_cooking_time": 30}},
    "2026-10-08": {"lunch": {"max_cooking_time": 30}, "dinner": {"max_cooking_time": 20}},
    "2026-10-09": {"lunch": {"max_cooking_time": 30}, "dinner": {"max_cooking_time": 30}},
}


def run_plan(budget=BUDGET, pantry=PANTRY):
    planner, service = build_planner({"lunch": POOL, "dinner": POOL})
    state = user_state(copy.deepcopy(pantry), budget=budget, max_recipe_repetitions=1)
    snapshot = copy.deepcopy(state)
    result = planner.plan_meals(
        user_state=state, start_date=date(2026, 10, 7), days=3,
        meal_types=["lunch", "dinner"], schedule=SCHEDULE,
        nutrition_targets=state["nutrition_targets"])
    return result, planner.last_plan_state, state, snapshot, service


@pytest.fixture(scope="module")
def plan():
    return run_plan()


def kb_requirements(plan_state):
    """(slot_id, recipe_id, ingredient) for every selected KB occurrence."""
    rows = []
    for meal in plan_state.selected_meals:
        for ingredient in get_required_ingredients(meal["recipe_id"]):
            rows.append((meal["slot"]["slot_id"], meal["recipe_id"], ingredient))
    return rows


def expected_totals(plan_state):
    """name -> unit -> (normalized total, {recipe ids}, occurrences)."""
    totals = collections.defaultdict(lambda: collections.defaultdict(
        lambda: [0.0, set(), 0]))
    for _, recipe_id, ingredient in kb_requirements(plan_state):
        kind, normalized = classify_requirement(ingredient)
        if kind != "measurable":
            continue
        entry = totals[ingredient["ingredient_name"]][normalized["unit"]]
        entry[0] += normalized["quantity"]
        entry[1].add(recipe_id)
        entry[2] += 1
    return totals


def line(basket, name):
    matches = [item for item in basket["items"] if item["name"] == name]
    return matches[0] if matches else None


# 1. Slots ----------------------------------------------------------------

def test_all_six_slots_filled(plan):
    result, plan_state, *_ = plan

    assert len(plan_state.slots) == 6
    assert [s for s, _ in selected_ids(result["plan"])] == [
        s.slot_id for s in plan_state.slots]


# 2. Constraints ----------------------------------------------------------

def test_repetition_cooking_time_and_allergy_constraints(plan):
    result, plan_state, *_ = plan
    recipes = [r for _, r in selected_ids(result["plan"])]

    assert len(set(recipes)) == 6  # max_recipe_repetitions = 1
    for meal in plan_state.selected_meals:
        limit = SCHEDULE[meal["slot"]["date"]][meal["slot"]["meal_type"]]["max_cooking_time"]
        assert repository().get_recipe(meal["recipe_id"])["cooking_time_min"] <= limit
        names = [i["ingredient_name"] for i in get_required_ingredients(meal["recipe_id"])]
        assert not any("peanut" in name for name in names)


# 3. Shared-ingredient aggregation ---------------------------------------

def test_shared_ingredients_aggregate_across_days(plan):
    result, plan_state, *_ = plan
    basket = result["grocery_basket"]
    totals = expected_totals(plan_state)
    shared = {name: units for name, units in totals.items()
              if len({r for u in units.values() for r in u[1]}) > 1}

    assert {"garlic", "olive oil"} <= set(shared)
    for name, units in shared.items():
        for unit, (quantity, recipe_ids, occurrences) in units.items():
            [record] = [r for r in basket["purchase_requirements"]
                        if r["ingredient_name"] == name and r["unit"] == unit]
            assert record["required_quantity"] == pytest.approx(quantity), name
            assert set(record["recipe_ids"]) == recipe_ids, name
            assert len(record["source_requirements"]) == occurrences, name
            days = {s["slot_id"].split("_")[0] for s in record["source_requirements"]}
            assert days == {
                m["slot"]["date"] for m in plan_state.selected_meals
                if m["recipe_id"] in recipe_ids}


def test_every_occurrence_accounted_once_per_slot(plan):
    result, plan_state, *_ = plan
    basket = result["grocery_basket"]
    expected = collections.Counter(
        (slot, ingredient["occurrence_id"]) for slot, _, ingredient in kb_requirements(plan_state))
    seen = collections.Counter(
        (s["slot_id"], s["occurrence_id"])
        for r in basket["purchase_requirements"] for s in r["source_requirements"])
    seen.update((r["slot_id"], o) for r in basket["qualitative_requirements"]
                for o in r["occurrence_ids"])
    seen.update((s["slot_id"], s["occurrence_id"])
                for r in basket["unresolved_quantity_requirements"]
                for s in r["source_requirements"])

    assert seen == expected


# 4. Pantry subtracted once ----------------------------------------------

@pytest.mark.parametrize("name, unit, pantry_in_unit, estimated", [
    ("olive oil", "ml", 30.0, False),
    ("mushroom", "g", 100.0, False),
    ("lemon juice", "ml", 20.0, False),
    ("garlic", "g", 6.0, True),   # 2 cloves x 3 g (ingredient_conversions.py)
])
def test_pantry_subtracted_once_from_consolidated_total(plan, name, unit, pantry_in_unit, estimated):
    result, plan_state, *_ = plan
    totals = expected_totals(plan_state)
    if name not in totals:
        pytest.skip(f"{name} not used by the selected recipes")
    required = totals[name][unit][0]
    [record] = [r for r in result["grocery_basket"]["purchase_requirements"]
                if r["ingredient_name"] == name]

    assert record["inventory_used"] == pytest.approx(min(required, pantry_in_unit))
    assert record["purchase_required"] == pytest.approx(max(0.0, required - pantry_in_unit))
    assert record["inventory_conversion_estimated"] is estimated


# 5. Packages from shortages ---------------------------------------------

def test_packages_sized_from_shortage(plan):
    result, *_ = plan
    basket = result["grocery_basket"]
    shortage = {(r["ingredient_name"], r["unit"]): r["purchase_required"]
                for r in basket["purchase_requirements"]}
    checked = 0
    for item in basket["items"]:
        key = (item["name"], item["required_unit"])
        if key not in shortage:
            continue
        assert item["required_quantity"] == pytest.approx(shortage[key])
        if item["package_conversion_status"] == "exact" and item["required_unit"] == item["package_unit"]:
            assert item["packages"] == max(
                1, math.ceil(item["required_quantity"] / item["package_quantity"]))
            assert item["leftover_quantity"] == pytest.approx(
                item["packages"] * item["package_quantity"] - item["required_quantity"])
            checked += 1
    assert checked >= 3
    covered = [k for k, v in shortage.items() if v <= 1e-9]
    for name, unit in covered:
        assert not [i for i in basket["items"] if i["name"] == name and i["required_unit"] == unit]


def test_plan_level_shortage_found_a_product(plan):
    result, *_ = plan
    garlic = line(result["grocery_basket"], "garlic")

    # The pantry's 2 cloves cover any single recipe, so no candidate
    # priced garlic; the combined plan still has to buy it.
    assert "garlic" in result["grocery_basket"].get("plan_level_products", [])
    assert garlic["packages"] == 1
    assert garlic["effective_purchase_cost"] is not None


# 6-7. Estimated and unresolved stay visible -----------------------------

def test_estimated_and_unresolved_conversions_are_never_verified(plan):
    result, *_ = plan
    basket = result["grocery_basket"]
    estimated = [i for i in basket["items"] if
                 i.get("conversion_status") == "estimated"
                 or i.get("package_conversion_status") == "estimated"
                 or i.get("inventory_conversion_estimated")]
    unresolved = [i for i in basket["items"]
                  if i.get("package_conversion_status") == "unresolved"]

    assert estimated and unresolved
    for item in estimated + unresolved:
        assert item["quantity_coverage_verified"] is False
        assert item["pricing_status"] != "priced"
    for item in unresolved:
        assert item["leftover_quantity"] is None
        assert item["purchase_basis"] == "minimum_retail_package"
    event = reconciliation_event(result["plan"])
    assert {u["ingredient_name"] for u in event["unverified_package_coverage"]} == {
        i["name"] for i in unresolved}


# 8. Cost and budget -----------------------------------------------------

def test_cost_completeness_and_budget(plan):
    result, plan_state, *_ = plan
    basket = result["grocery_basket"]

    assert basket["projected_cost_complete"] is True
    assert basket["projection_missing"] == []
    assert basket["projected_cost"] == pytest.approx(
        sum(i["effective_purchase_cost"] for i in basket["items"]), abs=0.01)
    assert basket["known_cost"] == pytest.approx(
        sum(i["purchase_cost"] for i in basket["items"] if i["pricing_status"] == "priced"), abs=0.01)
    assert basket["known_cost"] < basket["projected_cost"] <= BUDGET
    assert plan_state.estimated_spent == pytest.approx(basket["projected_cost"])
    assert basket["all_items_priced"] is False


def test_tight_budget_leaves_slots_unfilled_and_reported():
    result, plan_state, *_ = run_plan(budget=40.0)
    plan = result["plan"]
    filled = {s for s, _ in selected_ids(plan)}
    unfilled = [s.slot_id for s in plan_state.slots if s.slot_id not in filled]

    assert unfilled
    assert result["grocery_basket"]["projected_cost"] <= 40.0
    assert {e["slot_id"] for e in plan["execution_trace"]
            if e.get("event") == "slot_infeasible"} == set(unfilled)
    assert any(isinstance(c["reason"], dict) and c["reason"].get("constraint") == "budget"
               for c in plan["rejected_candidates"])
    assert result["validation"]["status"] != "feasible"


# 9. Nutrition -----------------------------------------------------------

def test_nutrition_totals_per_day(plan):
    result, plan_state, *_ = plan
    summary = result["nutrition_summary"]

    assert set(summary) == set(SCHEDULE)
    for day in SCHEDULE:
        recipes = [repository().get_recipe(m["recipe_id"]) for m in plan_state.selected_meals
                   if m["slot"]["date"] == day]
        assert len(recipes) == 2
        assert summary[day]["calories"] == pytest.approx(
            sum(r["calories_per_serving"] for r in recipes), abs=0.1)
        assert summary[day]["protein_g"] == pytest.approx(
            sum(r["protein_g_per_serving"] for r in recipes), abs=0.1)


# 10. Reconciliation -----------------------------------------------------

def test_reconciliation_is_consistent_and_not_committed(plan):
    result, plan_state, state, snapshot, _ = plan
    event = reconciliation_event(result["plan"])

    assert event["event"] == "inventory_reconciliation_incomplete"
    assert event["confirmed_shortage_count"] == 0
    assert event["unresolved_quantity_count"] == 0
    assert plan_state.current_inventory == plan_state.initial_inventory
    assert state == snapshot
    assert result["validation"]["status"] == "uncertain"


def test_purchase_in_other_unit_merges_with_estimated_status():
    # Reconciliation adds a 300 g garlic package to 2 cloves in the pantry.
    inventory = {"garlic": {"quantity": 2.0, "unit": "clove"}}
    updated = add_purchase(inventory, {"ingredient_name": "garlic",
                                       "package_quantity": 300, "package_unit": "g",
                                       "packages_needed": 1})

    assert updated["garlic"] == {"quantity": 102.0, "unit": "clove",
                                 "conversion_status": "estimated"}
    assert inventory == {"garlic": {"quantity": 2.0, "unit": "clove"}}
    with pytest.raises(ValueError, match="Incompatible purchase units"):
        add_purchase({"honey": {"quantity": 10.0, "unit": "ml"}},
                     {"ingredient_name": "honey", "package_quantity": 400,
                      "package_unit": "g"})
