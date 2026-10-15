"""Adaptive replanning over real KB recipes (prices mocked, see
tests/planning_harness.py): meal replacement, pantry changes, prepared
leftovers, unavailable ingredients and uncertain package coverage."""
import copy
from datetime import date

import pytest

from src.agents.grocery_agent import build_plan_grocery_basket, classify_requirement
from src.state.inventory_state import add_purchase, consume_inventory
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
]
START = date(2026, 10, 7)


def kcal(recipe_id):
    return repository().get_recipe(recipe_id)["calories_per_serving"]


def sources(basket):
    """(slot_id, occurrence_id) of every measurable requirement source."""
    return {
        (source["slot_id"], source["occurrence_id"])
        for record in basket["purchase_requirements"]
        for source in record["source_requirements"]
    }


def line(basket, name):
    matches = [item for item in basket["items"] if item["name"] == name]
    return matches[0] if matches else None


@pytest.fixture(scope="module")
def base():
    planner, _ = build_planner({"lunch": POOL, "dinner": POOL})
    state = user_state(copy.deepcopy(PANTRY), budget=100, max_recipe_repetitions=1)
    result = planner.plan_meals(
        user_state=state, start_date=START, days=2,
        meal_types=["lunch", "dinner"],
        nutrition_targets=state["nutrition_targets"])
    return planner, state, result, planner.last_plan_state


def test_base_plan_fills_every_slot(base):
    _, _, result, plan_state = base

    assert len(result["plan"]["selected_meals"]) == 4
    assert result["grocery_basket"]["projected_cost_complete"] is True
    assert plan_state.estimated_spent == pytest.approx(
        result["grocery_basket"]["projected_cost"])


# ============================================================
# Scenario 1: replace a selected meal
# ============================================================

@pytest.fixture(scope="module")
def replaced(base):
    planner, state, result, plan_state = base
    snapshot = copy.deepcopy(plan_state.selected_meals)
    dinner = plan_state.slots[1].slot_id
    new = planner.replace_meal(state, plan_state, dinner)
    return new, planner.last_plan_state, snapshot, dinner


def test_replacement_changes_only_the_target_slot(base, replaced):
    _, _, result, plan_state = base
    new, new_state, snapshot, dinner = replaced
    before = dict(selected_ids(result["plan"]))
    after = dict(selected_ids(new["plan"]))

    assert after[dinner] != before[dinner]
    assert {k: v for k, v in after.items() if k != dinner} == {
        k: v for k, v in before.items() if k != dinner}
    kept_before = [m for m in snapshot if m["slot"]["slot_id"] != dinner]
    kept_after = [m for m in new_state.selected_meals if m["slot"]["slot_id"] != dinner]
    assert kept_after == kept_before
    # Input state untouched.
    assert plan_state.selected_meals == snapshot
    assert any(e.get("event") == "meal_replaced"
               and e.get("previous_recipe_id") == before[dinner]
               for e in new_state.execution_trace)


def test_replacement_swaps_requirements(base, replaced):
    _, _, result, plan_state = base
    new, new_state, _, dinner = replaced
    old_recipe = dict(selected_ids(result["plan"]))[dinner]
    new_recipe = dict(selected_ids(new["plan"]))[dinner]
    old_sources = sources(result["grocery_basket"])
    new_sources = sources(new["grocery_basket"])

    dinner_before = {s for s in old_sources if s[0] == dinner}
    dinner_after = {s for s in new_sources if s[0] == dinner}
    assert dinner_before and all(o.startswith(old_recipe) for _, o in dinner_before)
    assert dinner_after and all(o.startswith(new_recipe) for _, o in dinner_after)
    assert old_sources - dinner_before == new_sources - dinner_after


def test_replacement_recalculates_budget_nutrition_and_inventory(base, replaced):
    planner, _, result, plan_state = base
    new, new_state, _, dinner = replaced
    basket = new["grocery_basket"]

    # Basket rebuilt from scratch equals the replanned basket.
    assert planner._build_final_grocery_basket(new_state)["projected_cost"] == (
        basket["projected_cost"])
    assert new_state.estimated_spent == pytest.approx(basket["projected_cost"])

    for day, total in new["nutrition_summary"].items():
        recipes = [m["recipe_id"] for m in new_state.selected_meals
                   if m["slot"]["date"] == day]
        assert total["calories"] == pytest.approx(sum(kcal(r) for r in recipes), abs=0.1)

    # Reconciled from the original pantry; incomplete, so nothing committed.
    assert new_state.initial_inventory == plan_state.initial_inventory
    assert reconciliation_event(new["plan"])["event"] == "inventory_reconciliation_incomplete"
    assert new_state.current_inventory == new_state.initial_inventory


def test_replaced_recipe_is_not_offered_again_for_that_slot(base, replaced):
    planner, state, _, _ = base
    _, new_state, _, dinner = replaced
    again = planner.replace_meal(state, new_state, dinner)
    previous = {m["slot"]["slot_id"]: m["recipe_id"] for m in new_state.selected_meals}

    assert dict(selected_ids(again["plan"])).get(dinner) != previous[dinner]


def test_replace_rejects_completed_or_unknown_slots(base):
    planner, state, _, plan_state = base
    lunch = plan_state.slots[0].slot_id

    with pytest.raises(ValueError, match="completed"):
        planner.replace_meal(state, plan_state, lunch, completed_slot_ids={lunch})
    with pytest.raises(ValueError, match="Unknown meal slot"):
        planner.replace_meal(state, plan_state, "1999-01-01_lunch")


# ============================================================
# Scenario 2: pantry quantity changes
# ============================================================

def basket_with_pantry(planner, plan_state, pantry):
    changed = copy.deepcopy(plan_state)
    changed.initial_inventory = pantry
    return planner._build_final_grocery_basket(changed)


def total_required(basket, name):
    return sum(r["required_quantity"] for r in basket["purchase_requirements"]
               if r["ingredient_name"] == name)


@pytest.mark.parametrize("mushroom_g", [0.0, 50.0, 100.0, 150.0, 400.0])
def test_shortage_tracks_pantry_quantity(base, mushroom_g):
    planner, _, _, plan_state = base
    pantry = copy.deepcopy(plan_state.initial_inventory)
    pantry["mushroom"] = {"quantity": mushroom_g, "unit": "g"}
    snapshot = copy.deepcopy(pantry)

    basket = basket_with_pantry(planner, plan_state, pantry)
    required = total_required(basket, "mushroom")
    [record] = [r for r in basket["purchase_requirements"]
                if r["ingredient_name"] == "mushroom"]

    assert required > 0
    assert record["inventory_used"] == pytest.approx(min(required, mushroom_g))
    assert record["purchase_required"] == pytest.approx(max(0.0, required - mushroom_g))
    mushroom = line(basket, "mushroom")
    if mushroom_g >= required:
        assert mushroom is None
    else:
        assert mushroom["required_quantity"] == pytest.approx(required - mushroom_g)
    assert pantry == snapshot


def test_estimated_pantry_conversion_stays_estimated(base):
    planner, _, _, plan_state = base
    for cloves in (0.5, 2, 20):
        pantry = copy.deepcopy(plan_state.initial_inventory)
        pantry["garlic"] = {"quantity": float(cloves), "unit": "clove"}
        basket = basket_with_pantry(planner, plan_state, pantry)
        [garlic] = [r for r in basket["purchase_requirements"]
                    if r["ingredient_name"] == "garlic"]
        assert garlic["conversion_status"] == "estimated"
        assert garlic["inventory_conversion_estimated"] is True
        assert garlic["inventory_used"] == pytest.approx(
            min(garlic["required_quantity"], cloves * 3.0))
        if line(basket, "garlic"):
            assert line(basket, "garlic")["quantity_coverage_verified"] is False


def test_inventory_after_plan_is_never_negative_and_consumed_once(base):
    planner, _, result, plan_state = base
    basket = result["grocery_basket"]
    inventory = copy.deepcopy(plan_state.initial_inventory)
    resolved = {item["name"] for item in basket["items"]
                if item.get("package_conversion_status") in {"exact", "estimated"}}
    resolved |= {r["ingredient_name"] for r in basket["purchase_requirements"]
                 if r["purchase_required"] <= 1e-9}
    for item in basket["items"]:
        if item["name"] in resolved and item.get("packages"):
            inventory = add_purchase(inventory, {
                "ingredient_name": item["name"], "package_quantity": item["package_quantity"],
                "package_unit": item["package_unit"], "packages_needed": item["packages"]})
    after_purchase = copy.deepcopy(inventory)
    for meal in plan_state.selected_meals:
        for ingredient in meal["decision"]["ingredient"]["required_ingredients"]:
            if (ingredient["ingredient_name"] in resolved
                    and classify_requirement(ingredient)[0] == "measurable"):
                inventory = consume_inventory(inventory, [ingredient])

    assert all(item["quantity"] >= 0 for item in inventory.values())
    # Exact-unit stock: start + bought - required, each requirement once.
    for name in ("mushroom", "olive oil"):
        required = total_required(basket, name)
        if name in inventory:
            assert inventory[name]["quantity"] == pytest.approx(
                after_purchase[name]["quantity"] - required)


# ============================================================
# Scenario 3: prepared leftovers
# ============================================================

@pytest.fixture(scope="module")
def with_leftover(base):
    planner, state, result, plan_state = base
    cooked = plan_state.selected_meals[1]  # day-1 dinner
    leftover_state = copy.deepcopy(plan_state)
    leftover_state.record_prepared_leftover(
        leftover_id="L-DINNER-1", recipe_id=cooked["recipe_id"],
        servings_remaining=2, prepared_date="2026-10-07",
        storage="refrigerated", expires_on="2026-10-09")
    approved = dict(state, approved_leftover_ids=["L-DINNER-1"])
    day2_lunch = plan_state.slots[2].slot_id
    new = planner.replace_meal(approved, leftover_state, day2_lunch)
    return planner, approved, leftover_state, new, planner.last_plan_state, cooked, day2_lunch


def leftover_balance(plan_state, leftover_id="L-DINNER-1"):
    [leftover] = [l for l in plan_state.prepared_leftovers if l["leftover_id"] == leftover_id]
    used = sum(m.get("leftover_id") == leftover_id for m in plan_state.selected_meals)
    return leftover["servings_remaining"], used


def test_leftover_fills_slot_without_new_groceries(with_leftover):
    _, _, leftover_state, new, new_state, cooked, day2_lunch = with_leftover
    [meal] = [m for m in new_state.selected_meals if m["slot"]["slot_id"] == day2_lunch]

    assert meal["meal_source"] == "prepared_leftover"
    assert meal["recipe_id"] == cooked["recipe_id"]
    assert meal["estimated_cost"] == 0.0
    # The leftover recipe's raw ingredients come only from the cooking slot.
    recipe_sources = {s for s in sources(new["grocery_basket"])
                      if s[1].startswith(cooked["recipe_id"] + "#")}
    assert recipe_sources
    assert {slot for slot, _ in recipe_sources} == {cooked["slot"]["slot_id"]}
    assert day2_lunch not in {slot for slot, _ in sources(new["grocery_basket"])}


def test_leftover_servings_balance(with_leftover):
    _, _, leftover_state, _, new_state, _, _ = with_leftover

    assert leftover_balance(new_state) == (1, 1)
    assert leftover_balance(leftover_state) == (2, 0)


def test_leftover_nutrition_counts_the_reused_serving(with_leftover):
    _, _, _, new, new_state, cooked, day2_lunch = with_leftover
    day2 = day2_lunch.split("_")[0]
    recipes = [m["recipe_id"] for m in new_state.selected_meals
               if m["slot"]["date"] == day2]

    assert cooked["recipe_id"] in recipes
    assert new["nutrition_summary"][day2]["calories"] == pytest.approx(
        sum(kcal(r) for r in recipes), abs=0.1)
    assert not any(e.get("event") == "prepared_leftover_nutrition_unknown"
                   for e in new_state.execution_trace)


def test_repeated_replanning_never_double_counts_servings(with_leftover):
    planner, approved, _, _, state_1, _, day2_lunch = with_leftover
    original = 2

    day2_dinner = state_1.slots[3].slot_id
    state_2 = planner.replace_meal(approved, state_1, day2_dinner) and planner.last_plan_state
    remaining, used = leftover_balance(state_2)
    assert remaining + used == original

    state_3 = planner.skip_and_replan(approved, state_2, day2_lunch) and planner.last_plan_state
    remaining, used = leftover_balance(state_3)
    assert remaining + used == original
    assert any(e.get("event") == "prepared_leftover_released"
               for e in state_3.execution_trace)


# ============================================================
# Scenario 4: unavailable ingredient
# ============================================================

def one_slot_plan(pool, unavailable=(), pantry=PANTRY):
    planner, service = build_planner({"lunch": pool, "dinner": pool}, unavailable=unavailable)
    state = user_state(copy.deepcopy(pantry), budget=100, max_recipe_repetitions=1)
    return planner.plan_meals(user_state=state, start_date=START, days=1,
                              meal_types=["lunch"]), service


# Mushroom must be bought (none in the pantry) but cannot be.
NO_MUSHROOM = [p for p in PANTRY if p["ingredient_name"] != "mushroom"]


def test_pantry_stock_makes_unavailable_product_irrelevant():
    result, service = one_slot_plan(["R02821"], unavailable={"mushroom"})

    assert [r for _, r in selected_ids(result["plan"])] == ["R02821"]
    assert "mushroom" not in [name for _, name, _, _ in service.requests]


def test_unavailable_ingredient_moves_planner_to_an_alternative():
    result, _ = one_slot_plan(["R02821", "R09645"], unavailable={"mushroom"},
                              pantry=NO_MUSHROOM)
    plan = result["plan"]

    assert [r for _, r in selected_ids(plan)] == ["R09645"]
    assert {c["recipe_id"] for c in plan["uncertain_candidates"]} == {"R02821"}


def test_unavailable_ingredient_with_no_alternative_is_reported():
    result, _ = one_slot_plan(["R02821"], unavailable={"mushroom"}, pantry=NO_MUSHROOM)
    plan = result["plan"]

    assert plan["selected_meals"] == []
    assert any(e.get("event") == "slot_infeasible" for e in plan["execution_trace"])
    assert result["validation"]["status"] != "feasible"
    assert plan["uncertain_candidates"][0]["reason"] == {
        "type": "incomplete_grocery_projection", "blocking_items": ["mushroom"]}
    [infeasible] = [e for e in plan["execution_trace"] if e.get("event") == "slot_infeasible"]
    assert infeasible["candidates"] == [{
        "recipe_id": "R02821", "status": "uncertain",
        "reason": {"type": "incomplete_grocery_projection", "blocking_items": ["mushroom"]}}]


# ============================================================
# Scenario 5: uncertain grocery coverage
# ============================================================

def test_unconvertible_package_stays_provisional_and_uncommitted():
    result, _ = one_slot_plan(["R28835"])
    plan, basket = result["plan"], result["grocery_basket"]
    honey = line(basket, "honey")

    assert [r for _, r in selected_ids(plan)] == ["R28835"]
    assert honey["required_unit"] == "ml" and honey["package_unit"] == "g"
    assert honey["package_conversion_status"] == "unresolved"
    assert honey["purchase_basis"] == "minimum_retail_package"
    assert honey["leftover_quantity"] is None
    assert honey["quantity_coverage_verified"] is False
    assert honey["pricing_status"] == "estimated"
    event = reconciliation_event(plan)
    assert event["event"] == "inventory_reconciliation_incomplete"
    assert {"honey", "wheat", "cashew nut"} <= {
        u["ingredient_name"] for u in event["unverified_package_coverage"]}
    assert plan["inventory"]["current"] == plan["inventory"]["initial"]
    assert result["validation"]["status"] == "uncertain"
