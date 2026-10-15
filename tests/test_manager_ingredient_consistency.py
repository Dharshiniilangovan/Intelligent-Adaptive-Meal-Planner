"""Candidate-level (Manager / Ingredient Agent) requirements must match
the authoritative final Grocery Agent basket.

Before the fix the Ingredient Agent built missing ingredients from a
dict keyed by ingredient name (last KB row wins) and compared pantry
units as raw strings ("gram" != "g"), so candidates were evaluated
with undercounted or pantry-blind quantities.
"""
import pandas as pd
import pytest

from scripts.mapping_retrieval_query import MAPPING_FILE
from src.agents.grocery_agent import build_plan_grocery_basket
from src.agents.ingredient_agent import (
    IngredientAgent,
    build_missing_ingredients,
    get_required_ingredients,
    pantry_to_dict,
    requirements_from_rows,
)
from src.agents.manager import ManagerAgent


def occurrence(recipe_id, position, name, quantity, unit, **extra):
    return {"occurrence_id": f"{recipe_id}#{position}", "recipe_id": recipe_id,
            "ingredient_id": extra.pop("ingredient_id", f"ID_{name}"),
            "ingredient_name": name, "quantity": quantity, "unit": unit,
            "kb_unit": unit, **extra}


def by_name(missing, name):
    return [item for item in missing if item["ingredient_name"] == name]


def candidate_vs_final(recipe_id, required, pantry):
    """(candidate, final) measurable shortages and unquantified names."""
    pantry_data = pantry_to_dict(pantry)
    missing = build_missing_ingredients(recipe_id, required, pantry_data)
    basket = build_plan_grocery_basket(
        [{"recipe_id": recipe_id, "ingredients": required}],
        [dict(ingredient_name=name, **item) for name, item in pantry_data.items()],
        [],
    )
    candidate = sorted(
        (m["ingredient_name"], m["normalized_unit"], round(m["normalized_quantity"], 6))
        for m in missing if "normalized_quantity" in m
    )
    final = sorted(
        (r["ingredient_name"], r["unit"], round(r["purchase_required"], 6))
        for r in basket["purchase_requirements"] if r["purchase_required"] > 1e-9
    )
    unquantified = (
        sorted(m["ingredient_name"] for m in missing if m["quantity"] is None),
        sorted(i["name"] for i in basket["items"]
               if i.get("purchase_basis") in {"qualitative_requirement",
                                              "unresolved_requirement"}),
    )
    return candidate, final, unquantified, missing


# ============================================================
# Repeated occurrences
# ============================================================

def test_compatible_repeats_are_combined():
    required = [occurrence("RX", 0, "olive oil", "1.0", "tablespoon"),
                occurrence("RX", 1, "olive oil", "2.0", "tablespoon")]

    [oil] = build_missing_ingredients("RX", required, {})

    # Whole requirement in its shared original unit for GroceryService,
    # and the normalized authoritative amount.
    assert (oil["quantity"], oil["unit"]) == (3.0, "tablespoon")
    assert (oil["normalized_quantity"], oil["normalized_unit"]) == (45.0, "ml")
    assert oil["occurrence_ids"] == ["RX#0", "RX#1"]


def test_incompatible_repeats_are_not_combined():
    required = [occurrence("RX", 0, "olive oil", "1.0", "tablespoon"),
                occurrence("RX", 1, "olive oil", "20", "g")]

    entries = build_missing_ingredients("RX", required, {})

    assert sorted((e["normalized_quantity"], e["normalized_unit"]) for e in entries) == [
        (15.0, "ml"), (20.0, "g")
    ]
    assert all(e["normalization_status"] == "unresolved" for e in entries)
    assert sorted(o for e in entries for o in e["occurrence_ids"]) == ["RX#0", "RX#1"]


def test_mixed_original_units_use_normalized_amount():
    required = [occurrence("RX", 0, "olive oil", "1.0", "tablespoon"),
                occurrence("RX", 1, "olive oil", "1.0", "teaspoon")]

    [oil] = build_missing_ingredients("RX", required, {})

    assert (oil["quantity"], oil["unit"]) == (20.0, "ml")


@pytest.mark.parametrize(
    "recipe_id, name, quantity, unit, normalized, occurrences",
    [
        # "1 red bell pepper" + "1 green bell pepper"
        ("R02533", "bell pepper", 1.0, "count", (150.0, "g"), ["R02533#4", "R02533#5"]),
        # red + yellow chile paste
        ("R01279", "chile paste", 1.0, "teaspoon", (5.0, "ml"), None),
    ],
)
def test_real_repeated_ingredients_are_not_undercounted(
    recipe_id, name, quantity, unit, normalized, occurrences
):
    result = IngredientAgent().run(recipe_id=recipe_id, pantry={})
    [entry] = by_name(result["data"]["missing_ingredients"], name)

    assert (entry["quantity"], entry["unit"]) == (quantity, unit)
    assert (entry["normalized_quantity"], entry["normalized_unit"]) == normalized
    assert len(entry["occurrence_ids"]) == 2
    if occurrences:
        assert entry["occurrence_ids"] == occurrences


def test_r18471_keeps_every_olive_oil_and_thyme_occurrence():
    missing = IngredientAgent().run(recipe_id="R18471", pantry={})["data"][
        "missing_ingredients"]

    [oil] = by_name(missing, "extra virgin olive oil")
    assert (oil["quantity"], oil["unit"]) == (2.0, "pinch")
    assert oil["additional_unquantified_requirement"] is True
    assert oil["occurrence_ids"] == ["R18471#2", "R18471#10", "R18471#23"]

    thyme = sorted((t["quantity"], t["unit"]) for t in by_name(missing, "thyme"))
    assert thyme == [(0.5, "sprig"), (1.0, "pinch")]


# ============================================================
# Pantry subtraction at candidate level
# ============================================================

def test_pantry_units_are_converted_not_string_compared():
    # KB says "gram"/"tablespoon"; pantry says "g"/"ml".
    result = IngredientAgent().run(
        recipe_id="R28835", pantry={"mushroom": "50 grams", "olive oil": "5 ml"})
    missing = result["data"]["missing_ingredients"]
    [mushroom] = by_name(missing, "mushroom")
    [oil] = by_name(missing, "olive oil")

    assert (mushroom["quantity"], mushroom["unit"]) == (63.5, "g")
    assert mushroom["pantry_used"] == pytest.approx(50.0)
    assert mushroom["status"] == "missing"
    assert (oil["quantity"], oil["unit"]) == (2.5, "ml")
    assert oil["pantry_used"] == pytest.approx(5.0)
    assert result["data"]["unsupported_items"] == []


def test_fully_covered_ingredient_is_not_missing():
    missing = IngredientAgent().run(
        recipe_id="R28835", pantry={"pasta": "1 kg"})["data"]["missing_ingredients"]

    assert by_name(missing, "pasta") == []


def test_estimated_pantry_conversion_is_flagged():
    missing = IngredientAgent().run(
        recipe_id="R28835", pantry={"broccoli": "0.25 head"})["data"]["missing_ingredients"]
    [broccoli] = by_name(missing, "broccoli")

    assert (broccoli["quantity"], broccoli["unit"]) == (75.0, "g")
    assert broccoli["conversion_status"] == "estimated"
    assert broccoli["inventory_conversion_estimated"] is True


def test_incompatible_pantry_unit_is_unit_mismatch():
    result = IngredientAgent().run(recipe_id="R28835", pantry={"honey": "400 g"})
    [honey] = by_name(result["data"]["missing_ingredients"], "honey")

    assert honey["status"] == "unit_mismatch"
    assert honey["normalized_quantity"] == pytest.approx(7.5)
    assert honey["pantry_used"] == 0.0
    assert honey in result["data"]["unsupported_items"]


def test_pantry_with_unknown_quantity_is_flagged():
    missing = build_missing_ingredients(
        "RX", [occurrence("RX", 0, "rice", "100", "g")],
        {"rice": {"quantity": None, "unit": "g"}},
    )

    assert missing[0]["status"] == "quantity_unknown"
    assert missing[0]["normalized_quantity"] == 100.0


# ============================================================
# Missing units and qualitative requirements
# ============================================================

def test_missing_unit_and_qualitative_stay_visible():
    missing = IngredientAgent().run(recipe_id="R30871", pantry={})["data"][
        "missing_ingredients"]
    [sesame] = by_name(missing, "sesame seed")

    assert sesame["quantity"] is None
    assert sesame["status"] == "unit_unknown"
    assert sesame["unresolved_reasons"] == ["missing_unit"]
    assert sesame["original_quantity"] == "0.5"

    salt = by_name(IngredientAgent().run(recipe_id="R02533", pantry={})["data"][
        "missing_ingredients"], "salt")
    assert salt == [{"ingredient_id": "ING3046", "ingredient_name": "salt",
                     "quantity": None, "unit": "to taste", "instruction": "to taste",
                     "occurrence_ids": ["R02533#7"], "status": "quantity_unknown"}]


# ============================================================
# Candidate-level == final Grocery Agent
# ============================================================

@pytest.mark.parametrize(
    "recipe_id, pantry",
    [
        ("R02533", {}),
        ("R01279", {}),
        ("R18471", {"extra virgin olive oil": "100 ml"}),
        ("R30871", {"brown rice": "100 g", "olive oil": "10 ml"}),
        ("R28835", {"olive oil": "5 ml", "mushroom": "50 g"}),
        ("R28835", {"broccoli": "0.25 head", "pasta": "1 kg", "honey": "400 g"}),
    ],
)
def test_candidate_matches_final_basket(recipe_id, pantry):
    candidate, final, unquantified, missing = candidate_vs_final(
        recipe_id, get_required_ingredients(recipe_id), pantry)

    assert candidate == final
    assert unquantified[0] == unquantified[1]


def test_candidate_matches_final_across_entire_knowledge_base():
    frame = pd.read_csv(MAPPING_FILE)
    frame.columns = frame.columns.str.strip()
    checked = rows = 0
    for recipe_id, recipe_rows in frame.groupby("recipe_id", sort=False):
        required = requirements_from_rows(recipe_id, recipe_rows)
        candidate, final, unquantified, missing = candidate_vs_final(
            recipe_id, required, {})
        assert candidate == final, recipe_id
        assert unquantified[0] == unquantified[1], recipe_id
        # Every KB occurrence is represented exactly once.
        assert sorted(o for m in missing for o in m["occurrence_ids"]) == sorted(
            r["occurrence_id"] for r in required), recipe_id
        checked += 1
        rows += len(required)
    assert checked == frame["recipe_id"].nunique()
    assert rows == len(frame)


# ============================================================
# Manager wiring: grocery input and allergy evaluation
# ============================================================

class RecordingGroceryAgent:
    def __init__(self):
        self.received = None

    def run(self, recipe_id, missing_ingredients):
        self.received = missing_ingredients
        return {"agent": "grocery", "status": "success",
                "data": {"recipe_id": recipe_id, "items": [], "known_cost": 0.0,
                         "all_items_priced": True, "projected_cost": 0.0,
                         "projected_cost_complete": True},
                "warnings": [], "errors": []}


def run_manager(recipe_id):
    seen = {}
    grocery = RecordingGroceryAgent()

    def dietary(recipe, user_state):
        seen["ingredients"] = recipe["ingredients"]
        return {"status": "pass"}

    manager = ManagerAgent(
        recipe_agent=None,
        ingredient_agent=IngredientAgent(),
        grocery_agent=grocery,
        recipe_lookup=lambda rid: {"recipe_id": rid},
        dietary_evaluator=dietary,
        feasibility_evaluator=lambda recipe, state: {"status": "pass"},
        candidate_evaluator=lambda **kwargs: {"status": "feasible"},
    )
    manager.evaluate_candidate(recipe_id, {"pantry": {}, "budget": 50},
                               defer_budget_to_planner=True)
    return grocery.received, seen["ingredients"]


def test_manager_sends_full_quantities_to_grocery_agent():
    received, _ = run_manager("R02533")
    [pepper] = by_name(received, "bell pepper")

    assert (pepper["quantity"], pepper["unit"]) == (1.0, "count")


def test_allergy_evaluation_sees_every_occurrence():
    _, ingredients = run_manager("R18471")
    kb_rows = get_required_ingredients("R18471")

    assert [i["occurrence_id"] for i in ingredients] == [
        r["occurrence_id"] for r in kb_rows]
    assert sum(i["ingredient_name"] == "extra virgin olive oil" for i in ingredients) == 3
