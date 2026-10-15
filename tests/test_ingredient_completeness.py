"""Ingredient completeness: no recipe ingredient may silently disappear.

Every retrieved ingredient occurrence must be accounted for exactly once
as a measurable, qualitative or unresolved requirement: at
classification, after aggregation, and at the grocery basket boundary.
"""
import collections
import copy
from datetime import date

import pandas as pd
import pytest

from scripts.mapping_retrieval_query import MAPPING_FILE
from src.agents.grocery_agent import (
    aggregate_requirements,
    build_plan_grocery_basket,
    classify_requirement,
    collect_qualitative_requirements,
    collect_unresolved_quantity_requirements,
    subtract_inventory,
)
from src.agents.ingredient_agent import (
    IngredientAgent,
    get_required_ingredients,
    requirements_from_rows,
)
from src.planning.meal_slot import generate_meal_slots
from src.planning.multi_meal_planner import MultiMealPlanner
from src.planning.plan_state import PlanState
from src.reasoning.dietary_requirements import evaluate_dietary_requirements
from src.state.inventory_state import consume_inventory

LUNCH, DINNER = "R30871", "R28835"


def recipes_for(*recipe_ids):
    return [
        {"recipe_id": recipe_id,
         "ingredients": get_required_ingredients(recipe_id)}
        for recipe_id in recipe_ids
    ]


def occurrence_ids(recipes):
    return [
        ingredient["occurrence_id"]
        for recipe in recipes
        for ingredient in recipe["ingredients"]
    ]


def accounted_after_aggregation(recipes):
    """Occurrence ids per category from the aggregation-stage outputs."""
    return {
        "measurable": [
            source["occurrence_id"]
            for record in aggregate_requirements(recipes)
            for source in record["source_requirements"]
        ],
        "qualitative": [
            occurrence
            for record in collect_qualitative_requirements(recipes)
            for occurrence in record["occurrence_ids"]
        ],
        "unresolved": [
            occurrence
            for record in collect_unresolved_quantity_requirements(recipes)
            for occurrence in record["occurrence_ids"]
        ],
    }


def accounted_in_basket(basket):
    return {
        "measurable": [
            source["occurrence_id"]
            for record in basket["purchase_requirements"]
            for source in record["source_requirements"]
        ],
        "qualitative": [
            occurrence
            for record in basket["qualitative_requirements"]
            for occurrence in record["occurrence_ids"]
        ],
        "unresolved": [
            occurrence
            for record in basket["unresolved_quantity_requirements"]
            for occurrence in record["occurrence_ids"]
        ],
    }


def assert_each_exactly_once(expected, accounted):
    counts = collections.Counter(
        occurrence for ids in accounted.values() for occurrence in ids
    )
    assert counts == collections.Counter(expected)
    assert all(count == 1 for count in counts.values())


def basket_line(basket, name):
    lines = [item for item in basket["items"] if item["name"] == name]
    assert len(lines) <= 1, f"duplicate basket lines for {name}"
    return lines[0] if lines else None


# ============================================================
# R30871 sesame seed: retrieval and classification
# ============================================================

def test_r30871_sesame_seed_is_retrieved_with_missing_unit():
    rows = get_required_ingredients(LUNCH)
    sesame = [row for row in rows if row["ingredient_name"] == "sesame seed"]

    assert len(rows) == 12
    assert sesame == [{
        "occurrence_id": "R30871#11",
        "recipe_id": LUNCH,
        "ingredient_id": "ING3127",
        "ingredient_name": "sesame seed",
        "alias_name": "['sesame seed', 'sesame seeds', 'sesame) seeds']",
        "quantity": "0.5",
        "unit": "",
        "kb_unit": "",
        "normalized_quantity_per_serving": "0.5",
        "normalized_unit": None,
        "conversion_status": "unresolved",
        "normalized_weight": None,
    }]
    assert classify_requirement(sesame[0]) == ("unresolved", "missing_unit")


def test_r30871_sesame_seed_reaches_the_final_basket():
    basket = build_plan_grocery_basket(recipes_for(LUNCH, DINNER), [], [])
    line = basket_line(basket, "sesame seed")

    assert line is not None
    assert line["ingredient_id"] == "ING3127"
    assert line["recipe_ids"] == [LUNCH]
    assert line["occurrence_ids"] == ["R30871#11"]
    assert line["original_measurements"] == [{
        "recipe_id": LUNCH, "occurrence_id": "R30871#11",
        "quantity": "0.5", "unit": "",
    }]
    assert line["unresolved_reasons"] == ["missing_unit"]
    assert line["pricing_status"] == "unresolved_quantity"
    assert line["purchase_basis"] == "unresolved_requirement"
    # Nothing is invented.
    for field in ("required_quantity", "required_unit", "packages",
                  "package_quantity", "purchase_cost",
                  "estimated_purchase_cost", "effective_purchase_cost",
                  "leftover_quantity"):
        assert line[field] is None, field
    assert line["quantity_coverage_verified"] is False
    assert basket["unresolved_quantity_count"] == 1
    assert "sesame seed" in basket["projection_missing"]
    assert "sesame seed" in basket["unpriced_items"]


def test_ingredient_agent_does_not_pass_unitless_amount_as_quantity():
    result = IngredientAgent().run(recipe_id=LUNCH, pantry={})
    missing = {
        item["ingredient_name"]: item
        for item in result["data"]["missing_ingredients"]
    }

    assert missing["sesame seed"]["quantity"] is None
    assert missing["sesame seed"]["original_quantity"] == "0.5"
    assert missing["sesame seed"]["status"] == "unit_unknown"
    assert missing["sesame seed"] in result["data"]["unsupported_items"]
    assert result["status"] == "partial"


# ============================================================
# Classification of incomplete measurements
# ============================================================

@pytest.mark.parametrize(
    "quantity, unit, reason",
    [
        (None, "g", "missing_quantity"),
        ("", "g", "missing_quantity"),
        ("nan", "g", "missing_quantity"),
        (float("nan"), "g", "missing_quantity"),
        ("a few", "g", "invalid_quantity"),
        (0, "g", "invalid_quantity"),
        (-2, "g", "invalid_quantity"),
        (0.5, None, "missing_unit"),
        (0.5, "", "missing_unit"),
        (0.5, "nan", "missing_unit"),
        (0.5, float("nan"), "missing_unit"),
    ],
)
def test_incomplete_measurements_are_unresolved(quantity, unit, reason):
    ingredient = {"ingredient_id": "ING1", "ingredient_name": "x",
                  "quantity": quantity, "unit": unit}

    assert classify_requirement(ingredient) == ("unresolved", reason)


@pytest.mark.parametrize(
    "quantity, unit, instruction",
    [
        ("required", "to taste", "to taste"),
        (None, "to taste", "to taste"),
        ("as needed", "", "as needed"),
        ("required", "g", "required"),
        (1, "as required", "as required"),
    ],
)
def test_qualitative_requirements(quantity, unit, instruction):
    ingredient = {"ingredient_id": "ING1", "ingredient_name": "salt",
                  "quantity": quantity, "unit": unit}

    assert classify_requirement(ingredient) == ("qualitative", instruction)


@pytest.mark.parametrize("unit", ["handful", "xyz", "pinch"])
def test_unsupported_unit_stays_measurable_with_unresolved_conversion(unit):
    ingredient = {"ingredient_id": "ING1", "ingredient_name": "parsley",
                  "quantity": 1, "unit": unit}

    kind, normalized = classify_requirement(ingredient)
    assert kind == "measurable"
    assert normalized["unit"] == unit
    assert normalized["conversion_status"] == "unresolved"

    basket = build_plan_grocery_basket(
        [{"recipe_id": "R1", "ingredients": [ingredient]}], [], []
    )
    line = basket_line(basket, "parsley")
    assert line["pricing_status"] == "unresolved_conversion"
    assert line["packages"] is None
    assert basket["projected_cost_complete"] is False


def test_missing_identity_is_reported_not_dropped():
    ingredient = {"occurrence_id": "R1#0", "quantity": 1, "unit": "g"}
    recipes = [{"recipe_id": "R1", "ingredients": [ingredient]}]

    [record] = collect_unresolved_quantity_requirements(recipes)

    assert record["occurrence_ids"] == ["R1#0"]
    assert record["reasons"] == ["missing_ingredient_identity"]
    assert aggregate_requirements(recipes) == []


# ============================================================
# Completeness invariant
# ============================================================

INVARIANT_RECIPES = [
    (LUNCH, DINNER),           # Day 5 plan; sesame seed has no unit
    ("R02533",),               # bell pepper twice, salt/pepper to taste
    ("R18471",),               # olive oil x3, one with no unit
    ("R01279",),               # chile paste twice
    (LUNCH, "R18471", "R02533"),
]


@pytest.mark.parametrize("recipe_ids", INVARIANT_RECIPES)
def test_invariant_at_classification(recipe_ids):
    recipes = recipes_for(*recipe_ids)
    expected = occurrence_ids(recipes)
    by_kind = collections.defaultdict(list)
    for recipe in recipes:
        for ingredient in recipe["ingredients"]:
            by_kind[classify_requirement(ingredient)[0]].append(
                ingredient["occurrence_id"]
            )

    assert len(expected) == len(set(expected))
    assert_each_exactly_once(expected, by_kind)


@pytest.mark.parametrize("recipe_ids", INVARIANT_RECIPES)
def test_invariant_after_aggregation(recipe_ids):
    recipes = recipes_for(*recipe_ids)

    assert_each_exactly_once(
        occurrence_ids(recipes), accounted_after_aggregation(recipes)
    )


@pytest.mark.parametrize("recipe_ids", INVARIANT_RECIPES)
def test_invariant_at_basket_boundary(recipe_ids):
    recipes = recipes_for(*recipe_ids)
    basket = build_plan_grocery_basket(recipes, [], [])

    assert_each_exactly_once(occurrence_ids(recipes), accounted_in_basket(basket))

    # An ingredient never appears in two categories of line. Several
    # measurable lines are allowed only for incompatible unit groups
    # (e.g. thyme: 0.5 sprig and 1 pinch), which are never summed.
    category = {"qualitative_requirement": "qualitative",
                "unresolved_requirement": "unresolved"}
    lines_by_name = collections.defaultdict(list)
    for item in basket["items"]:
        lines_by_name[item["name"]].append(item)
    for name, lines in lines_by_name.items():
        kinds = {category.get(line["purchase_basis"], "measurable") for line in lines}
        assert len(kinds) == 1, name
        if len(lines) > 1:
            assert kinds == {"measurable"}
            assert len({line["required_unit"] for line in lines}) == len(lines)
            assert all(line["normalization_status"] == "unresolved" for line in lines)
    names = set(lines_by_name)
    for record in basket["purchase_requirements"]:
        if record["purchase_required"] > 0:
            assert record["ingredient_name"] in names
    for record in (basket["qualitative_requirements"]
                   + basket["unresolved_quantity_requirements"]):
        assert record["ingredient_name"] in names


def test_invariant_holds_across_entire_knowledge_base():
    """All 73,862 KB rows: none lost, none counted twice."""
    frame = pd.read_csv(MAPPING_FILE)
    frame.columns = frame.columns.str.strip()
    total = 0
    for recipe_id, rows in frame.groupby("recipe_id", sort=False):
        recipes = [{"recipe_id": recipe_id,
                    "ingredients": requirements_from_rows(recipe_id, rows)}]
        expected = occurrence_ids(recipes)
        total += len(expected)
        assert_each_exactly_once(expected, accounted_after_aggregation(recipes))
    assert total == len(frame)


# ============================================================
# Duplicate occurrences and shared ingredients
# ============================================================

def test_duplicate_occurrences_within_a_recipe_are_both_kept():
    # R02533: "1 red bell pepper" and "1 green bell pepper".
    recipes = recipes_for("R02533")
    peppers = [i for i in recipes[0]["ingredients"]
               if i["ingredient_name"] == "bell pepper"]
    [record] = [r for r in aggregate_requirements(recipes)
                if r["ingredient_name"] == "bell pepper"]

    assert [p["occurrence_id"] for p in peppers] == ["R02533#4", "R02533#5"]
    assert record["quantity"] == pytest.approx(150.0)
    assert [s["occurrence_id"] for s in record["source_requirements"]] == [
        "R02533#4", "R02533#5"
    ]
    assert record["recipe_ids"] == ["R02533"]


def test_mixed_categories_for_one_ingredient_in_one_recipe():
    # R18471 lists olive oil as 1 pinch, 1 pinch and a unitless 0.5.
    basket = build_plan_grocery_basket(recipes_for("R18471"), [], [])
    line = basket_line(basket, "extra virgin olive oil")
    [measurable] = [r for r in basket["purchase_requirements"]
                    if r["ingredient_name"] == "extra virgin olive oil"]
    [unresolved] = [r for r in basket["unresolved_quantity_requirements"]
                    if r["ingredient_name"] == "extra virgin olive oil"]

    assert measurable["quantity"] == pytest.approx(2.0)
    assert measurable["unit"] == "pinch"
    assert len(measurable["source_requirements"]) == 2
    assert unresolved["occurrence_ids"] == ["R18471#23"]
    # One shopping line, carrying the unquantified source as well.
    assert line["unresolved_quantity_sources"][0]["occurrence_id"] == "R18471#23"
    assert line["additional_unquantified_requirement"] is True
    assert line["quantity_coverage_verified"] is False


def sesame(recipe_id, position):
    return {"occurrence_id": f"{recipe_id}#{position}", "recipe_id": recipe_id,
            "ingredient_id": "ING3127", "ingredient_name": "sesame seed",
            "quantity": "0.5", "unit": "",
            "normalized_quantity_per_serving": "0.5", "normalized_unit": None,
            "conversion_status": "unresolved"}


def test_multiple_recipes_sharing_an_unresolved_ingredient():
    recipes = [
        {"recipe_id": "RA", "ingredients": [sesame("RA", 0)]},
        {"recipe_id": "RB", "ingredients": [sesame("RB", 3)]},
    ]
    basket = build_plan_grocery_basket(recipes, [], [])
    [record] = basket["unresolved_quantity_requirements"]
    line = basket_line(basket, "sesame seed")

    assert record["recipe_ids"] == ["RA", "RB"]
    assert record["occurrence_ids"] == ["RA#0", "RB#3"]
    # Unitless amounts are never summed into a number.
    assert "quantity" not in record
    assert line["recipe_ids"] == ["RA", "RB"]
    assert line["occurrence_ids"] == ["RA#0", "RB#3"]
    assert line["required_quantity"] is None
    assert basket["unresolved_quantity_count"] == 1


def test_unresolved_and_measurable_same_ingredient_one_unverified_line():
    measurable = {"occurrence_id": "RA#0", "ingredient_id": "ING3127",
                  "ingredient_name": "sesame seed", "quantity": 10, "unit": "g"}
    basket = build_plan_grocery_basket(
        [{"recipe_id": "RA", "ingredients": [measurable]},
         {"recipe_id": "RB", "ingredients": [sesame("RB", 0)]}],
        [],
        [{"ingredient_id": "ING3127", "ingredient_name": "sesame seed",
          "package_quantity": 100, "package_unit": "g", "price": 1.8}],
    )
    line = basket_line(basket, "sesame seed")

    assert line["required_quantity"] == pytest.approx(10.0)
    assert line["package_conversion_status"] == "exact"
    # RB needs an unknown extra amount: coverage cannot be verified.
    assert line["additional_unquantified_requirement"] is True
    assert line["unresolved_quantity_sources"][0]["occurrence_id"] == "RB#0"
    assert line["quantity_coverage_verified"] is False
    assert line["pricing_status"] == "estimated"
    assert basket["known_cost"] == 0.0
    assert_each_exactly_once(["RA#0", "RB#0"], accounted_in_basket(basket))


def test_qualitative_need_also_blocks_verification():
    exact = {"ingredient_id": "ING3046", "ingredient_name": "salt",
             "quantity": 5, "unit": "g"}
    to_taste = {"ingredient_id": "ING3046", "ingredient_name": "salt",
                "quantity": "required", "unit": "to taste"}
    catalog = [{"ingredient_id": "ING3046", "ingredient_name": "salt",
                "package_quantity": 500, "package_unit": "g", "price": 1.0}]

    alone = build_plan_grocery_basket(
        [{"recipe_id": "RA", "ingredients": [exact]}], [], catalog)
    both = build_plan_grocery_basket(
        [{"recipe_id": "RA", "ingredients": [exact]},
         {"recipe_id": "RB", "ingredients": [to_taste]}], [], catalog)

    assert basket_line(alone, "salt")["quantity_coverage_verified"] is True
    line = basket_line(both, "salt")
    assert line["quantity_coverage_verified"] is False
    assert line["pricing_status"] == "estimated"
    assert len(both["items"]) == 1


# ============================================================
# Pricing completeness
# ============================================================

def test_missing_price_is_never_zero():
    basket = build_plan_grocery_basket(
        recipes_for(LUNCH, DINNER),
        [],
        [{"ingredient_name": "olive oil", "package_quantity": 500,
          "package_unit": "ml", "price": 8.0}],
    )

    assert basket["projected_cost"] is None
    assert basket["projected_cost_complete"] is False
    assert basket["planning_cost"] is None
    assert basket["planning_cost_complete"] is False
    assert basket["all_items_priced"] is False
    assert basket["all_items_have_usable_cost"] is False


def test_basket_with_only_measured_items_still_completes():
    recipes = [{"recipe_id": "R1", "ingredients": [
        {"ingredient_name": "rice", "quantity": 200, "unit": "g"}]}]
    basket = build_plan_grocery_basket(
        recipes, [],
        [{"ingredient_name": "rice", "package_quantity": 1,
          "package_unit": "kg", "price": 4.0}])

    assert basket["unresolved_quantity_requirements"] == []
    assert basket["unresolved_quantity_count"] == 0
    assert basket["projected_cost"] == pytest.approx(4.0)
    assert basket["projected_cost_complete"] is True


# ============================================================
# Pantry subtraction consistency
# ============================================================

def test_unresolved_ingredient_in_pantry_is_not_subtracted():
    recipes = recipes_for(LUNCH)
    pantry = [
        {"ingredient_name": "sesame seed", "quantity": 50, "unit": "g"},
        {"ingredient_name": "brown rice", "quantity": 100, "unit": "g"},
    ]
    snapshot = copy.deepcopy(pantry)

    coverage = {r["ingredient_name"]: r
                for r in subtract_inventory(aggregate_requirements(recipes), pantry)}

    assert pantry == snapshot
    assert "sesame seed" not in coverage
    assert coverage["brown rice"]["inventory_used"] == pytest.approx(100.0)
    assert coverage["brown rice"]["purchase_required"] == pytest.approx(87.5)

    basket = build_plan_grocery_basket(recipes, pantry, [])
    line = basket_line(basket, "sesame seed")
    assert line["inventory_used"] is None
    assert line["required_quantity"] is None


def test_inventory_state_measurable_consumption_unchanged():
    inventory = {"brown rice": {"quantity": 100.0, "unit": "g"},
                 "sesame seed": {"quantity": 50.0, "unit": "g"}}
    measurable = [i for i in get_required_ingredients(LUNCH)
                  if classify_requirement(i)[0] == "measurable"]

    updated = consume_inventory(inventory, measurable)

    assert updated["brown rice"]["quantity"] == 0.0
    assert updated["sesame seed"] == {"quantity": 50.0, "unit": "g"}


# ============================================================
# Inventory reconciliation
# ============================================================

def plan_state_with(recipes, pantry=None):
    pantry = pantry or {}
    state = PlanState(
        slots=[],
        initial_budget=100.0,
        initial_inventory=copy.deepcopy(pantry),
        current_inventory=copy.deepcopy(pantry),
    )
    state.selected_meals = [
        {"recipe_id": recipe["recipe_id"],
         "decision": {"ingredient": {"required_ingredients": recipe["ingredients"]}}}
        for recipe in recipes
    ]
    return state


def last_reconciliation_event(state):
    return [e for e in state.execution_trace
            if str(e.get("event", "")).startswith("inventory_reconcil")][-1]


def test_reconciliation_reports_unresolved_quantity_separately():
    rice = {"occurrence_id": "RA#0", "ingredient_name": "rice",
            "quantity": 100, "unit": "g"}
    recipes = [{"recipe_id": "RA", "ingredients": [rice, sesame("RA", 1)]}]
    pantry = {"rice": {"quantity": 500.0, "unit": "g"},
              "sesame seed": {"quantity": 50.0, "unit": "g"}}
    state = plan_state_with(recipes, pantry)
    basket = build_plan_grocery_basket(
        recipes, MultiMealPlanner._inventory_to_pantry(pantry), [])

    assert MultiMealPlanner(manager=None)._reconcile_final_inventory(
        state, basket) is True

    event = last_reconciliation_event(state)
    assert event["event"] == "inventory_reconciliation_incomplete"
    assert event["unresolved_quantity_count"] == 1
    assert event["unresolved_quantity_requirements"] == [{
        "ingredient_id": "ING3127", "ingredient_name": "sesame seed",
        "recipe_ids": ["RA"], "occurrence_ids": ["RA#1"],
        "reasons": ["missing_unit"],
    }]
    assert event["unresolved_conversions"] == []
    assert event["unverified_package_count"] == 0
    # Rice alone was coverable; nothing is committed while sesame is unknown.
    assert state.current_inventory == pantry


def test_reconciliation_of_real_day5_plan_lists_sesame_seed():
    recipes = recipes_for(LUNCH, DINNER)
    state = plan_state_with(recipes)
    basket = build_plan_grocery_basket(recipes, [], [])

    MultiMealPlanner(manager=None)._reconcile_final_inventory(state, basket)
    event = last_reconciliation_event(state)

    assert event["event"] == "inventory_reconciliation_incomplete"
    assert [r["ingredient_name"] for r in event["unresolved_quantity_requirements"]] == [
        "sesame seed"
    ]
    assert "sesame seed" not in [
        r["ingredient_name"] for r in event["unresolved_conversions"]
    ]


def test_unpackaged_lines_do_not_short_circuit_reconciliation():
    # A "1 pinch" line has no package. Reconciliation must still run
    # the full coverage check instead of stopping at the first line.
    pinch = {"ingredient_name": "parsley", "quantity": 1, "unit": "pinch"}
    rice = {"ingredient_name": "rice", "quantity": 300, "unit": "g"}
    recipes = [{"recipe_id": "RA", "ingredients": [pinch, rice]}]
    state = plan_state_with(recipes, {"rice": {"quantity": 100.0, "unit": "g"}})
    basket = build_plan_grocery_basket(recipes, [], [])

    MultiMealPlanner(manager=None)._reconcile_final_inventory(state, basket)
    event = last_reconciliation_event(state)

    assert event["unresolved_conversions"] == [
        {"ingredient_name": "parsley", "unit": "pinch"}
    ]
    # Nothing covers the pinch either, so it is also a shortage.
    assert event["confirmed_shortages"] == [
        {"ingredient_name": "parsley", "purchase_required": 1.0, "unit": "pinch"},
        {"ingredient_name": "rice", "purchase_required": 200.0, "unit": "g"},
    ]


def test_qualitative_only_reconciliation_still_commits():
    rice = {"ingredient_name": "rice", "quantity": 100, "unit": "g"}
    salt = {"ingredient_name": "salt", "quantity": "required", "unit": "to taste"}
    state = plan_state_with(
        [{"recipe_id": "RA", "ingredients": [rice, salt]}],
        {"rice": {"quantity": 500.0, "unit": "g"},
         "salt": {"quantity": 100.0, "unit": "g"}},
    )

    MultiMealPlanner(manager=None)._reconcile_final_inventory(state, {"items": []})

    assert state.current_inventory["rice"]["quantity"] == pytest.approx(400.0)
    assert last_reconciliation_event(state)["reason"] == (
        "Qualitative ingredient quantities remain unresolved"
    )


def test_prepared_leftover_meals_are_not_reconciled():
    state = plan_state_with([])
    state.selected_meals = [{
        "recipe_id": LUNCH,
        "meal_source": "prepared_leftover",
        "decision": {"ingredient": {
            "required_ingredients": get_required_ingredients(LUNCH)}},
    }]

    MultiMealPlanner(manager=None)._reconcile_final_inventory(state, {"items": []})

    assert last_reconciliation_event(state)["event"] == "inventory_reconciled"


# ============================================================
# Planner selection and constraints
# ============================================================

class SesameManager:
    """R100 has a unitless ingredient; R200 is fully measurable."""

    class _Recipes:
        def run(self, **kwargs):
            return {"status": "success",
                    "data": {"candidate_recipe_ids": ["R100", "R200"]},
                    "warnings": [], "errors": []}

    def __init__(self):
        self.recipe_agent = self._Recipes()

    def evaluate_candidate(self, recipe_id, user_state, meal_context,
                           defer_budget_to_planner=False):
        ingredients = [{"occurrence_id": f"{recipe_id}#0",
                        "ingredient_id": f"ING_{recipe_id}",
                        "ingredient_name": f"base_{recipe_id}",
                        "quantity": 100.0, "unit": "g"}]
        items = [{"ingredient_id": f"ING_{recipe_id}",
                  "ingredient": f"base_{recipe_id}",
                  "package_quantity": 100.0, "package_unit": "g",
                  "packages_needed": 1, "price_per_package": 2.0,
                  "total_cost": 2.0}]
        if recipe_id == "R100":
            ingredients.append(sesame(recipe_id, 1))
            items.append({"ingredient_id": "ING3127", "ingredient": "sesame seed",
                          "package_quantity": 100.0, "package_unit": "g",
                          "packages_needed": 1, "estimated_total_cost": 1.8,
                          "purchase_basis": "llm_estimated_package",
                          "match_status": "estimated_no_retail_match"})
        return {
            "recipe_id": recipe_id,
            "status": "feasible",
            "recipe": {"recipe_id": recipe_id, "calories_per_serving": 400.0},
            "reasoning": {"status": "feasible", "hard_constraints": [
                {"constraint": "diet", "status": "pass"},
                {"constraint": "allergy", "status": "pass"},
                {"constraint": "cooking_time", "status": "pass"},
            ]},
            "ingredient": {"recipe_id": recipe_id,
                           "required_ingredients": ingredients},
            "grocery": {"recipe_id": recipe_id, "items": items,
                        "known_cost": 2.0, "all_items_priced": False,
                        "projected_cost": 3.8 if recipe_id == "R100" else 2.0,
                        "projected_cost_complete": True},
        }


def test_planner_skips_recipe_made_uncertain_by_unresolved_ingredient():
    planner = MultiMealPlanner(manager=SesameManager(), max_candidates_per_slot=2)

    result = planner.plan_meals(
        user_state={"budget_remaining": 50, "max_recipe_repetitions": 1},
        start_date=date(2026, 10, 12), days=1, meal_types=["lunch"],
    )
    plan = result["plan"]

    assert [m["recipe_id"] for m in plan["selected_meals"]] == ["R200"]
    uncertain = [c for c in plan["uncertain_candidates"] if c["recipe_id"] == "R100"]
    assert uncertain
    assert "sesame seed" in uncertain[0]["reason"]["projection_missing"]


def test_allergy_check_still_sees_unresolved_ingredient():
    recipe = {"recipe_id": LUNCH, "ingredients": get_required_ingredients(LUNCH)}

    def allergy_status(allergies):
        return evaluate_dietary_requirements(
            recipe, {"allergies": allergies, "dietary_preferences": []}
        )["allergy"]["status"]

    assert allergy_status([]) == "safe"
    assert allergy_status(["sesame"]) == "conflict"
