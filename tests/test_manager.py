from __future__ import annotations

import pytest

from src.agents.manager import ManagerAgent


RECIPES = {
    "R001": {"recipe_id": "R001", "recipe_name": "Recipe 1"},
    "R002": {"recipe_id": "R002", "recipe_name": "Recipe 2"},
    "R003": {"recipe_id": "R003", "recipe_name": "Recipe 3"},
}


class FakeRecipeAgent:
    def __init__(self, candidates=None, status="success"):
        self.candidates = ["R001", "R002"] if candidates is None else candidates
        self.status = status
        self.calls = 0

    def run(self, **kwargs):
        self.calls += 1
        return {
            "agent": "recipe",
            "status": self.status,
            "data": {"candidate_recipe_ids": self.candidates},
            "warnings": [],
            "errors": [] if self.status != "failed" else ["recipe failure"],
        }


class FakeIngredientAgent:
    def __init__(self, fail_ids=None):
        self.fail_ids = set(fail_ids or [])
        self.calls = []

    def run(self, recipe_id, pantry):
        self.calls.append(recipe_id)
        if recipe_id in self.fail_ids:
            return {
                "agent": "ingredient",
                "status": "failed",
                "data": {},
                "warnings": [],
                "errors": ["ingredient failure"],
            }
        return {
            "agent": "ingredient",
            "status": "success",
            "data": {
                "recipe_id": recipe_id,
                "required_ingredients": [
                    {"ingredient_id": "I1", "ingredient_name": "rice", "quantity": 100, "unit": "g"}
                ],
                "pantry_used": [],
                "missing_ingredients": [
                    {"ingredient_id": "I1", "ingredient_name": "rice", "quantity": 100, "unit": "g"}
                ],
                "unsupported_items": [],
            },
            "warnings": [],
            "errors": [],
        }


class FakeGroceryAgent:
    def __init__(self, costs=None, priced=None):
        self.costs = costs or {"R001": 8.0, "R002": 15.0, "R003": 5.0}
        self.priced = priced or {"R001": True, "R002": True, "R003": True}
        self.calls = []

    def run(self, recipe_id, missing_ingredients):
        self.calls.append(recipe_id)
        return {
            "agent": "grocery",
            "status": "success",
            "data": {
                "recipe_id": recipe_id,
                "items": [],
                "known_cost": self.costs[recipe_id],
                "all_items_priced": self.priced[recipe_id],
                "unpriced_items": [] if self.priced[recipe_id] else ["rice"],
            },
            "warnings": [],
            "errors": [],
        }


def recipe_lookup(recipe_id):
    return RECIPES.get(recipe_id)


def fake_dietary(recipe, user_state):
    return {"recipe_id": recipe["recipe_id"], "mock": "dietary"}


def fake_feasibility(recipe, user_state):
    return {"recipe_id": recipe["recipe_id"], "mock": "feasibility"}


def fake_budget(*, purchase_cost, remaining_budget, has_unknown_cost=False):
    if purchase_cost > remaining_budget:
        status = "hard_fail"
    elif has_unknown_cost:
        status = "uncertain"
    else:
        status = "pass"
    return {
        "budget_status": status,
        "known_purchase_cost": purchase_cost,
        "remaining_budget": remaining_budget,
    }


def candidate_evaluator_from(status_by_id, score_by_id=None):
    score_by_id = score_by_id or {}

    def evaluate(*, recipe_id, dietary_result, feasibility_result, budget_result):
        # Budget uncertainty/failure always has precedence in this fake,
        # mirroring Day-3 semantics.
        if budget_result["budget_status"] == "hard_fail":
            status = "rejected"
        elif budget_result["budget_status"] == "uncertain":
            status = "uncertain"
        else:
            status = status_by_id.get(recipe_id, "feasible")
        return {
            "recipe_id": recipe_id,
            "status": status,
            "feasible": status == "feasible",
            "failed_constraints": [] if status != "rejected" else [{"constraint": "mock"}],
            "unknown_constraints": [] if status != "uncertain" else [{"constraint": "budget"}],
            "soft_constraints": {} if status == "feasible" else None,
            "overall_score": score_by_id.get(recipe_id, 0.5) if status == "feasible" else None,
        }

    return evaluate


def build_manager(recipe_agent=None, ingredient_agent=None, grocery_agent=None, evaluator=None):
    return ManagerAgent(
        recipe_agent=recipe_agent or FakeRecipeAgent(),
        ingredient_agent=ingredient_agent or FakeIngredientAgent(),
        grocery_agent=grocery_agent or FakeGroceryAgent(),
        recipe_lookup=recipe_lookup,
        dietary_evaluator=fake_dietary,
        feasibility_evaluator=fake_feasibility,
        budget_evaluator=fake_budget,
        candidate_evaluator=evaluator or candidate_evaluator_from({}),
    )


USER = {"budget": 20.0, "pantry": []}


def test_one_feasible_candidate_is_selected():
    manager = build_manager(
        recipe_agent=FakeRecipeAgent(["R001"]),
        evaluator=candidate_evaluator_from({"R001": "feasible"}, {"R001": 0.8}),
    )
    result = manager.plan(USER, {"meal_type": "dinner"})
    assert result["result"] == "success"
    assert result["selected_recipe"]["recipe_id"] == "R001"


def test_multiple_feasible_candidates_select_highest_score():
    manager = build_manager(
        evaluator=candidate_evaluator_from(
            {"R001": "feasible", "R002": "feasible"},
            {"R001": 0.70, "R002": 0.85},
        )
    )
    result = manager.plan(USER)
    assert result["selected_recipe"]["recipe_id"] == "R002"
    assert [x["recipe_id"] for x in result["feasible_candidates"]] == ["R002", "R001"]


def test_no_recipe_candidates_stops_without_downstream_calls():
    ingredients = FakeIngredientAgent()
    groceries = FakeGroceryAgent()
    manager = build_manager(
        recipe_agent=FakeRecipeAgent([]),
        ingredient_agent=ingredients,
        grocery_agent=groceries,
    )
    result = manager.plan(USER)
    assert result["result"] == "no_candidates"
    assert ingredients.calls == []
    assert groceries.calls == []


def test_ingredient_failure_only_fails_that_candidate_and_continues():
    ingredients = FakeIngredientAgent(fail_ids={"R001"})
    manager = build_manager(
        ingredient_agent=ingredients,
        evaluator=candidate_evaluator_from({"R002": "feasible"}, {"R002": 0.8}),
    )
    result = manager.plan(USER)
    assert result["selected_recipe"]["recipe_id"] == "R002"
    assert result["candidate_results"]["R001"]["status"] == "failed"
    assert result["candidate_results"]["R001"]["stage"] == "ingredient_agent"


def test_unpriced_grocery_makes_budget_uncertain_and_not_selectable():
    groceries = FakeGroceryAgent(
        costs={"R001": 8.0, "R002": 15.0, "R003": 5.0},
        priced={"R001": False, "R002": True, "R003": True},
    )
    manager = build_manager(
        recipe_agent=FakeRecipeAgent(["R001"]),
        grocery_agent=groceries,
        evaluator=candidate_evaluator_from({"R001": "feasible"}, {"R001": 0.95}),
    )
    result = manager.plan(USER)
    assert result["result"] == "no_feasible_candidate"
    assert result["uncertain_candidates"][0]["recipe_id"] == "R001"


def test_rejected_high_score_never_beats_feasible_candidate():
    manager = build_manager(
        evaluator=candidate_evaluator_from(
            {"R001": "rejected", "R002": "feasible"},
            {"R001": 0.99, "R002": 0.60},
        )
    )
    result = manager.plan(USER)
    assert result["selected_recipe"]["recipe_id"] == "R002"
    assert any(x["recipe_id"] == "R001" for x in result["rejected_candidates"])


def test_all_candidates_rejected_or_uncertain_returns_no_feasible():
    manager = build_manager(
        evaluator=candidate_evaluator_from(
            {"R001": "rejected", "R002": "uncertain"}
        )
    )
    result = manager.plan(USER)
    assert result["result"] == "no_feasible_candidate"
    assert result["selected_recipe"] is None
    assert len(result["rejected_candidates"]) == 1
    assert len(result["uncertain_candidates"]) == 1


def test_candidate_limit_and_duplicate_removal():
    manager = build_manager(
        recipe_agent=FakeRecipeAgent(["R001", "R001", "R002", "R003"]),
        evaluator=candidate_evaluator_from({"R001": "feasible", "R002": "feasible"}),
    )
    result = manager.plan(USER, max_candidates=2)
    recipe_trace = result["execution_trace"][0]
    assert recipe_trace["candidate_count"] == 2
    assert set(result["candidate_results"]) == {"R001", "R002"}


def test_invalid_max_candidates_rejected():
    manager = build_manager()
    with pytest.raises(ValueError):
        manager.plan(USER, max_candidates=0)
