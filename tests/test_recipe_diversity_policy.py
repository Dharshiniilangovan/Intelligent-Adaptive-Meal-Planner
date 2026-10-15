"""Recipe diversity and the ingredient-uncertainty selection policy.

Diversity/constraint tests use a small configurable fake Manager so the
expected plan is exact. Policy tests use real KB recipes through
tests/planning_harness.py (catalog prices instead of live services).
"""
import copy
from datetime import date

import pytest

from src.agents.grocery_agent import (
    build_plan_grocery_basket,
    classify_projection_gaps,
)
from src.planning.multi_meal_planner import MultiMealPlanner
from tests.planning_harness import (
    build_planner,
    reconciliation_event,
    selected_ids,
    user_state,
)

START = date(2026, 10, 12)


# ============================================================
# Configurable fake Manager
# ============================================================

class Recipes:
    def __init__(self, ids):
        self.ids = ids

    def run(self, user_state, meal_slot, selected_recipe_ids=None,
            recent_cuisines=None, max_candidates=None):
        return {"status": "success",
                "data": {"candidate_recipe_ids": list(self.ids)},
                "warnings": [], "errors": []}


class SpecManager:
    """Each recipe: list of (name, quantity, unit) plus flags.

    Every ingredient is sold as a 500 g / 500 ml package at `price`.
    """

    def __init__(self, specs):
        self.specs = specs
        self.recipe_agent = Recipes(list(specs))

    def evaluate_candidate(self, recipe_id, user_state, meal_context,
                           defer_budget_to_planner=False):
        spec = self.specs[recipe_id]
        allergy = "fail" if spec.get("allergen") else "pass"
        ingredients, items = [], []
        for position, (name, quantity, unit) in enumerate(spec["ingredients"]):
            ingredients.append({"occurrence_id": f"{recipe_id}#{position}",
                                "ingredient_id": f"ID_{name}", "ingredient_name": name,
                                "quantity": quantity, "unit": unit})
            package_unit = "ml" if unit == "ml" else "g"
            items.append({"ingredient_id": f"ID_{name}", "ingredient": name,
                          "package_quantity": 500.0, "package_unit": package_unit,
                          "packages_needed": 1, "price_per_package": spec["price"],
                          "total_cost": spec["price"]})
        return {
            "recipe_id": recipe_id, "status": "feasible",
            "recipe": {"recipe_id": recipe_id, "calories_per_serving": 500.0,
                       "protein_g_per_serving": 20.0},
            "reasoning": {"status": "feasible", "hard_constraints": [
                {"constraint": "diet", "status": "pass"},
                {"constraint": "allergy", "status": allergy},
                {"constraint": "cooking_time", "status": "pass"}]},
            "ingredient": {"recipe_id": recipe_id, "required_ingredients": ingredients},
            "grocery": {"recipe_id": recipe_id, "items": items,
                        "known_cost": spec["price"], "all_items_priced": True,
                        "projected_cost": spec["price"], "projected_cost_complete": True},
        }


def spec(price, *ingredients, **flags):
    return {"price": price,
            "ingredients": list(ingredients) or [(f"own_{price}", 100, "g")],
            **flags}


def plan(specs, days=1, meal_types=("lunch", "dinner"), **state):
    planner = MultiMealPlanner(manager=SpecManager(specs), max_candidates_per_slot=10)
    user = {"budget_remaining": 100, **state}
    result = planner.plan_meals(user_state=user, start_date=START, days=days,
                                meal_types=list(meal_types))
    return result, planner.last_plan_state


def recipes(result):
    return [recipe for _, recipe in selected_ids(result["plan"])]


def events(result, name):
    return [e for e in result["plan"]["execution_trace"] if e.get("event") == name]


# ============================================================
# Diversity
# ============================================================

def test_distinct_recipes_when_enough_alternatives():
    specs = {f"R{i}": spec(float(i)) for i in range(1, 8)}

    result, _ = plan(specs, days=3)

    assert len(recipes(result)) == 6
    assert len(set(recipes(result))) == 6


def test_required_repeat_is_not_placed_in_adjacent_slots():
    # 4 slots, 3 recipes, limit 2: one recipe must repeat, and every
    # repeat costs the same (shared package). Names are chosen so the
    # cost/ID tie-break alone would put the repeat in the same day
    # (RZ, RY, RA, RA); only the recency penalty prevents that.
    specs = {"RZ": spec(1.0), "RY": spec(2.0), "RA": spec(3.0)}

    result, plan_state = plan(specs, days=2)
    chosen = recipes(result)

    assert len(chosen) == 4 and len(set(chosen)) == 3
    for day in ("2026-10-12", "2026-10-13"):
        same_day = [m["recipe_id"] for m in plan_state.selected_meals
                    if m["slot"]["date"] == day]
        assert len(set(same_day)) == 2
    assert all(a != b for a, b in zip(chosen, chosen[1:]))


def test_default_limit_is_not_relaxed_without_consent():
    result, _ = plan({"RA": spec(1.0)}, days=1, meal_types=("breakfast", "lunch", "dinner"))

    assert recipes(result) == ["RA", "RA"]
    [request] = events(result, "repetition_relaxation_requires_confirmation")
    assert (request["limit"], request["filled_with_limit"], request["filled_if_relaxed"]) == (2, 2, 3)
    assert not events(result, "repetition_limit_relaxed")
    [conflict] = result["validation"]["constraint_conflicts"]
    assert conflict["limit"] == 2
    assert result["validation"]["status"] == "partial"
    [unfilled] = events(result, "slot_infeasible")
    assert unfilled["candidates"] == [{
        "recipe_id": "RA", "status": "rejected",
        "reason": {"constraint": "max_recipe_repetitions", "status": "fail",
                   "limit": 2, "times_selected": 2}}]


def test_default_limit_relaxed_only_with_consent():
    result, _ = plan({"RA": spec(1.0)}, days=1, meal_types=("breakfast", "lunch", "dinner"),
                     allow_repetition_relaxation=True)

    assert recipes(result) == ["RA", "RA", "RA"]
    [relaxed] = events(result, "repetition_limit_relaxed")
    assert relaxed["filled_with_limit"] == 2 and relaxed["filled_if_relaxed"] == 3


def test_explicit_limit_is_never_relaxed():
    result, _ = plan({"RA": spec(1.0)}, days=1, max_recipe_repetitions=1,
                     allow_repetition_relaxation=True)

    assert recipes(result) == ["RA"]
    assert not events(result, "repetition_limit_relaxed")
    assert not events(result, "repetition_relaxation_requires_confirmation")


# ============================================================
# Hard constraints are never traded for diversity
# ============================================================

def test_allergen_recipe_never_selected_for_diversity():
    specs = {"SAFE": spec(5.0), "ALLERGEN": spec(1.0, allergen=True)}

    result, _ = plan(specs, days=1, max_recipe_repetitions=1)

    assert recipes(result) == ["SAFE"]
    [unfilled] = events(result, "slot_infeasible")
    reasons = {c["recipe_id"]: c["reason"] for c in unfilled["candidates"]}
    assert any(r.get("constraint") == "allergy" and r.get("status") == "fail"
               for r in reasons["ALLERGEN"])
    assert reasons["SAFE"]["constraint"] == "max_recipe_repetitions"


def test_over_budget_recipe_never_selected_for_diversity():
    specs = {"CHEAP": spec(10.0), "PRICEY": spec(95.0)}

    result, _ = plan(specs, days=1, max_recipe_repetitions=1)
    chosen = recipes(result)

    assert "PRICEY" not in chosen or chosen == ["PRICEY"]
    assert result["grocery_basket"]["projected_cost"] <= 100
    budget_failures = [c for c in result["plan"]["rejected_candidates"]
                       if isinstance(c["reason"], dict)
                       and c["reason"].get("constraint") == "budget"]
    assert budget_failures


def test_conditional_cost_is_a_lower_bound_for_budget():
    # The priced part alone exceeds the budget: rejected even though a
    # "to taste" item is unpriced.
    specs = {"RX": spec(150.0, ("rice", 100, "g"))}
    specs["RX"]["ingredients"].append(("salt", "required", "to taste"))

    result, _ = plan(specs, days=1, meal_types=("lunch",))

    assert recipes(result) == []
    [rejection] = [c for c in result["plan"]["rejected_candidates"]
                   if isinstance(c["reason"], dict)]
    assert rejection["reason"]["constraint"] == "budget"
    assert rejection["reason"]["cost_is_lower_bound"] is True


# ============================================================
# Uncertainty policy: projection gaps
# ============================================================

def basket(ingredients, catalog):
    return build_plan_grocery_basket(
        [{"recipe_id": "R1", "ingredients": ingredients}], [], catalog)


def test_projection_gap_categories():
    result = basket(
        [{"ingredient_name": "salt", "quantity": "required", "unit": "to taste"},
         {"ingredient_name": "stock", "quantity": "required", "unit": "as needed"},
         {"ingredient_name": "sesame seed", "quantity": "0.5", "unit": ""},
         {"ingredient_name": "saffron", "quantity": 1, "unit": "g"},
         {"ingredient_name": "thyme", "quantity": 0.5, "unit": "sprig"},
         {"ingredient_name": "thyme", "quantity": 1, "unit": "pinch"},
         {"ingredient_name": "allspice", "quantity": 1, "unit": "pinch"}],
        [{"ingredient_name": "allspice", "package_quantity": 30,
          "package_unit": "g", "price": 2.5},
         {"ingredient_name": "thyme", "package_quantity": 1,
          "package_unit": "bunch", "price": 1.8}],
    )
    gaps = {(g["name"], g["category"], g["blocks_selection"])
            for g in result["projection_gaps"]}

    assert gaps == {
        ("salt", "qualitative_discretionary", False),
        ("stock", "qualitative_unspecified", True),
        ("sesame seed", "missing_quantity_or_unit", True),
        ("saffron", "missing_product_or_price", True),
        ("thyme", "incompatible_unit_groups", True),
    }
    assert result["selection_projection_complete"] is False
    assert result["projected_cost"] is None
    # Unconvertible pinch with a product: one provisional package.
    [allspice] = [i for i in result["items"] if i["name"] == "allspice"]
    assert allspice["packages"] == 1
    assert allspice["package_conversion_status"] == "unresolved"
    assert allspice["purchase_basis"] == "minimum_retail_package"
    assert allspice["quantity_coverage_verified"] is False
    assert allspice["leftover_quantity"] is None
    assert result["priced_subtotal"] == pytest.approx(2.5)


def test_only_discretionary_gap_allows_selection_without_zero_cost():
    result = basket(
        [{"ingredient_name": "rice", "quantity": 100, "unit": "g"},
         {"ingredient_name": "salt", "quantity": "required", "unit": "to taste"}],
        [{"ingredient_name": "rice", "package_quantity": 500, "package_unit": "g",
          "price": 2.0}],
    )
    [salt] = [i for i in result["items"] if i["name"] == "salt"]

    assert result["selection_projection_complete"] is True
    assert result["discretionary_unpriced_items"] == ["salt"]
    assert result["projected_cost"] is None
    assert result["projected_cost_complete"] is False
    assert result["priced_subtotal"] == pytest.approx(2.0)
    assert salt["effective_purchase_cost"] is None
    assert salt["quantity_coverage_verified"] is False


def test_classify_projection_gaps_ignores_priced_lines():
    assert classify_projection_gaps([{"name": "rice", "effective_purchase_cost": 2.0}]) == []


def test_candidate_gate_ignores_only_discretionary_items():
    planner = MultiMealPlanner(manager=None)
    decision = {
        "ingredient": {"required_ingredients": [
            {"ingredient_name": "salt", "quantity": "required", "unit": "to taste"},
            {"ingredient_name": "cornstarch", "quantity": 5, "unit": "g"}]},
        "grocery": {"projected_cost_complete": False,
                    "projection_missing": ["salt", "cornstarch"]},
    }

    assert planner._candidate_projection_blockers(decision) == ["cornstarch"]
    decision["grocery"]["projection_missing"] = ["salt"]
    assert planner._candidate_projection_blockers(decision) == []
    decision["grocery"]["projection_missing"] = []
    assert planner._candidate_projection_blockers(decision) == [
        "unspecified grocery projection gap"]


# ============================================================
# Real KB recipes through the planner
# ============================================================

PANTRY = [{"ingredient_name": "olive oil", "quantity": 30, "unit": "ml"}]


def kb_plan(pool, meal_types=("lunch",), days=1, unavailable=(), **state):
    planner, _ = build_planner({"lunch": pool, "dinner": pool}, unavailable=unavailable)
    user = user_state(copy.deepcopy(PANTRY), budget=100, **state)
    result = planner.plan_meals(user_state=user, start_date=START, days=days,
                                meal_types=list(meal_types))
    return result, planner.last_plan_state


def test_salt_to_taste_recipe_selected_conditionally():
    # R15279: every requirement measurable except "salt to taste".
    result, _ = kb_plan(["R15279"], unavailable={"salt"})
    validation, basket_ = result["validation"], result["grocery_basket"]

    assert recipes(result) == ["R15279"]
    assert validation["conditional_selections"] == [
        {"slot_id": "2026-10-12_lunch", "recipe_id": "R15279", "unpriced_items": ["salt"]}]
    assert validation["status"] == "uncertain"
    assert basket_["projected_cost"] is None
    assert basket_["priced_subtotal"] > 0
    [salt] = [i for i in basket_["items"] if i["name"] == "salt"]
    assert salt["effective_purchase_cost"] is None
    assert salt["purchase_basis"] == "qualitative_requirement"
    assert basket_["known_cost"] == pytest.approx(
        sum(i["purchase_cost"] for i in basket_["items"] if i["pricing_status"] == "priced"))


def test_pinch_and_to_taste_recipe_selectable_with_provisional_package():
    # R39173: salt + black pepper to taste, cayenne by the pinch.
    result, _ = kb_plan(["R39173"])
    [cayenne] = [i for i in result["grocery_basket"]["items"] if i["name"] == "cayenne pepper"]

    assert recipes(result) == ["R39173"]
    assert cayenne["packages"] == 1
    assert cayenne["quantity_coverage_verified"] is False
    assert cayenne["package_conversion_status"] in {"unresolved", "estimated"}
    assert sorted(result["validation"]["conditional_selections"][0]["unpriced_items"]) == [
        "black pepper", "salt"]


def test_missing_unit_essential_ingredient_still_blocks():
    result, _ = kb_plan(["R30871"])
    plan_ = result["plan"]

    assert recipes(result) == []
    [unfilled] = events(result, "slot_infeasible")
    [candidate] = unfilled["candidates"]
    assert candidate["recipe_id"] == "R30871"
    assert candidate["reason"]["projection_missing"] == ["sesame seed"]
    assert result["validation"]["status"] == "infeasible"


def test_kb_plan_prefers_distinct_recipes_over_cheaper_repeat():
    pool = ["R28835", "R15279", "R39173", "R22063"]
    result, plan_state = kb_plan(pool, meal_types=("lunch", "dinner"), days=2)
    chosen = recipes(result)

    assert len(chosen) == 4
    assert len(set(chosen)) == 4
    # Hard constraints held for every selection.
    for meal in plan_state.selected_meals:
        constraints = meal["decision"]["reasoning"]["hard_constraints"]
        assert all(c["status"] == "pass" for c in constraints if c["constraint"] != "budget")
    assert result["grocery_basket"]["priced_subtotal"] <= 100


# ============================================================
# Inventory reconciliation follows the selected (diverse) plan
# ============================================================

def test_reconciliation_commits_the_actual_diverse_plan():
    specs = {
        "RA": spec(2.0, ("rice", 150, "g"), ("bean", 100, "g")),
        "RB": spec(3.0, ("rice", 150, "g"), ("oil", 20, "ml")),
        "RC": spec(4.0, ("rice", 150, "g"), ("tofu", 200, "g")),
    }
    planner = MultiMealPlanner(manager=SpecManager(specs), max_candidates_per_slot=10)
    user = {"budget_remaining": 100, "max_recipe_repetitions": 1,
            "pantry": {"rice": "200 g", "oil": "50 ml"}}
    snapshot = copy.deepcopy(user)
    result = planner.plan_meals(user_state=user, start_date=START, days=1,
                                meal_types=["breakfast", "lunch", "dinner"])
    state = planner.last_plan_state

    assert sorted(recipes(result)) == ["RA", "RB", "RC"]
    assert reconciliation_event(result["plan"])["event"] == "inventory_reconciled"
    current = state.current_inventory
    # rice: 200 pantry + 1 x 500 bought - 3 x 150 used = 250
    assert current["rice"]["quantity"] == pytest.approx(250.0)
    # oil: 50 pantry covers 20; nothing bought
    assert current["oil"]["quantity"] == pytest.approx(30.0)
    for name, used in (("bean", 100), ("tofu", 200)):
        assert current[name]["quantity"] == pytest.approx(500.0 - used)
    assert all(item["quantity"] >= 0 for item in current.values())
    assert state.initial_inventory == {"rice": {"quantity": 200.0, "unit": "g"},
                                       "oil": {"quantity": 50.0, "unit": "ml"}}
    assert user == snapshot


def test_reconciliation_reflects_replanned_selection():
    specs = {
        "RA": spec(2.0, ("rice", 150, "g")),
        "RB": spec(3.0, ("rice", 150, "g"), ("oil", 20, "ml")),
        "RC": spec(4.0, ("tofu", 200, "g")),
    }
    planner = MultiMealPlanner(manager=SpecManager(specs), max_candidates_per_slot=10)
    user = {"budget_remaining": 100, "max_recipe_repetitions": 1,
            "pantry": {"rice": "200 g"}}
    planner.plan_meals(user_state=user, start_date=START, days=1,
                       meal_types=["lunch", "dinner"])
    first = planner.last_plan_state
    first_snapshot = copy.deepcopy(first.selected_meals)
    first_inventory = copy.deepcopy(first.current_inventory)
    dinner = first.slots[1].slot_id
    replaced = planner.replace_meal(user, first, dinner)
    state = planner.last_plan_state
    chosen = dict(selected_ids(replaced["plan"]))

    assert chosen[dinner] != dict(selected_ids({"selected_meals": first.selected_meals}))[dinner]
    basket_ = replaced["grocery_basket"]
    planned = {m["recipe_id"] for m in state.selected_meals}
    assert {r for rec in basket_["purchase_requirements"] for r in rec["recipe_ids"]} == planned
    rice_needed = 150.0 * sum(r in {"RA", "RB"} for r in planned)
    if reconciliation_event(replaced["plan"])["event"] == "inventory_reconciled":
        rice_bought = sum(i["packages"] * i["package_quantity"]
                          for i in basket_["items"] if i["name"] == "rice")
        assert state.current_inventory["rice"]["quantity"] == pytest.approx(
            200.0 + rice_bought - rice_needed)
    assert first.selected_meals == first_snapshot
    assert first.current_inventory == first_inventory
    assert state.initial_inventory == {"rice": {"quantity": 200.0, "unit": "g"}}
