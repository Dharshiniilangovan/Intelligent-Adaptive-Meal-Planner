"""Manager Agent for Day-4 multi-agent orchestration.

The Manager owns sequencing only. It does NOT reimplement recipe retrieval,
ingredient/pantry logic, grocery pricing, or constraint reasoning.
"""

from __future__ import annotations

from uuid import uuid4
from typing import Any, Callable

from src.agents.contracts import AgentStatus, normalize_agent_result
from src.reasoning.budget_service import check_budget
from src.reasoning.dietary_requirements import evaluate_dietary_requirements
from src.reasoning.feasibility import evaluate_recipe as evaluate_feasibility
from src.reasoning.reasoning_engine import evaluate_candidate
from src.state.workflow_state import WorkflowState


class ManagerAgent:
    """Coordinate Recipe -> Ingredient -> Grocery -> Reasoning.

    Dependencies are injected so the Manager can be unit-tested with fakes and
    later connected to the real agents without changing orchestration logic.
    """

    def __init__(
        self,
        recipe_agent: Any,
        ingredient_agent: Any,
        grocery_agent: Any,
        recipe_lookup: Callable[[str], dict | None],
        *,
        dietary_evaluator: Callable[[dict, Any], dict] = evaluate_dietary_requirements,
        feasibility_evaluator: Callable[[dict, dict], dict] = evaluate_feasibility,
        budget_evaluator: Callable[..., dict] = check_budget,
        candidate_evaluator: Callable[..., dict] = evaluate_candidate,
    ) -> None:
        self.recipe_agent = recipe_agent
        self.ingredient_agent = ingredient_agent
        self.grocery_agent = grocery_agent
        self.recipe_lookup = recipe_lookup
        self.dietary_evaluator = dietary_evaluator
        self.feasibility_evaluator = feasibility_evaluator
        self.budget_evaluator = budget_evaluator
        self.candidate_evaluator = candidate_evaluator

    def plan(
        self,
        user_state: Any,
        meal_context: dict[str, Any] | None = None,
        *,
        max_candidates: int = 10,
    ) -> dict[str, Any]:
        """Run one planning request and return a structured Manager result."""
        if max_candidates <= 0:
            raise ValueError("max_candidates must be > 0")

        meal_context = meal_context or {}
        workflow = WorkflowState(
            request_id=str(uuid4()),
            user_state=user_state,
        )
        # ------------------------------------------------------------
        # 1. Recipe Agent
        # ------------------------------------------------------------
        try:
            raw_recipe_result = self.recipe_agent.run(
                user_state=user_state,
                meal_context=meal_context,
                max_candidates=max_candidates,
            )
            recipe_result = normalize_agent_result(raw_recipe_result, "recipe")
        except Exception as exc:
            workflow.status = "failed"
            workflow.errors.append(str(exc))
            workflow.trace("recipe_agent", status="failed", error=str(exc))
            return self._final_response(workflow, result="recipe_agent_failed")

        workflow.warnings.extend(recipe_result["warnings"])
        workflow.errors.extend(recipe_result["errors"])

        if recipe_result["status"] == AgentStatus.FAILED.value:
            workflow.status = "failed"
            workflow.trace("recipe_agent", status="failed")
            return self._final_response(workflow, result="recipe_agent_failed")

        candidate_ids = recipe_result["data"].get("candidate_recipe_ids", [])
        if not isinstance(candidate_ids, list):
            workflow.status = "failed"
            workflow.errors.append("candidate_recipe_ids must be a list")
            return self._final_response(workflow, result="invalid_recipe_agent_output")

        # Preserve order, remove duplicates, cap downstream work.
        candidate_ids = list(dict.fromkeys(str(x) for x in candidate_ids))[:max_candidates]
        workflow.candidate_recipe_ids = candidate_ids
        workflow.trace(
            "recipe_agent",
            status=recipe_result["status"],
            candidate_count=len(candidate_ids),
        )

        if not candidate_ids:
            workflow.status = "completed"
            return self._final_response(workflow, result="no_candidates")

        # ------------------------------------------------------------
        # 2. Evaluate each candidate independently
        # ------------------------------------------------------------
        for recipe_id in candidate_ids:
            self._evaluate_one_candidate(
                workflow=workflow,
                recipe_id=recipe_id,
                user_state=user_state,
            )

        # ------------------------------------------------------------
        # 3. Partition results and rank FEASIBLE candidates only
        # ------------------------------------------------------------
        feasible = [
            item for item in workflow.candidate_results.values()
            if item.get("status") == "feasible"
        ]
        uncertain = [
            item for item in workflow.candidate_results.values()
            if item.get("status") == "uncertain"
        ]
        rejected = [
            item for item in workflow.candidate_results.values()
            if item.get("status") in {"rejected", "failed"}
        ]

        feasible.sort(
            key=lambda item: self._score_for_sort(item),
            reverse=True,
        )

        if feasible:
            selected = feasible[0]
            workflow.selected_recipe_id = selected["recipe_id"]
            workflow.status = "completed"
            workflow.trace(
                "manager_selection",
                status="selected",
                recipe_id=workflow.selected_recipe_id,
                overall_score=selected["reasoning"].get("overall_score"),
            )
            return self._final_response(
                workflow,
                result="success",
                feasible=feasible,
                uncertain=uncertain,
                rejected=rejected,
                selected=selected,
            )

        workflow.status = "completed"
        workflow.trace("manager_selection", status="no_feasible_candidate")
        return self._final_response(
            workflow,
            result="no_feasible_candidate",
            feasible=[],
            uncertain=uncertain,
            rejected=rejected,
        )

    def _evaluate_one_candidate(
        self,
        *,
        workflow: WorkflowState,
        recipe_id: str,
        user_state: Any,
    ) -> None:
        recipe = self.recipe_lookup(recipe_id)
        if recipe is None:
            self._record_failed_candidate(
                workflow, recipe_id, "recipe_lookup", "Recipe not found"
            )
            return

        # Ingredient Agent -------------------------------------------------
        try:
            raw_ingredient = self.ingredient_agent.run(
                recipe_id=recipe_id,
                pantry=self._pantry_from_user_state(user_state),
            )
            ingredient_result = normalize_agent_result(raw_ingredient, "ingredient")
        except Exception as exc:
            self._record_failed_candidate(
                workflow, recipe_id, "ingredient_agent", str(exc)
            )
            return

        workflow.trace(
            "ingredient_agent",
            recipe_id=recipe_id,
            status=ingredient_result["status"],
        )

        if ingredient_result["status"] == AgentStatus.FAILED.value:
            self._record_failed_candidate(
                workflow,
                recipe_id,
                "ingredient_agent",
                "; ".join(ingredient_result["errors"]) or "Ingredient agent failed",
            )
            return

        ingredient_data = ingredient_result["data"]
        missing_ingredients = ingredient_data.get("missing_ingredients", [])

        # Grocery Agent ----------------------------------------------------
        try:
            raw_grocery = self.grocery_agent.run(
                recipe_id=recipe_id,
                missing_ingredients=missing_ingredients,
            )
            grocery_result = normalize_agent_result(raw_grocery, "grocery")
        except Exception as exc:
            self._record_failed_candidate(
                workflow, recipe_id, "grocery_agent", str(exc)
            )
            return

        workflow.trace(
            "grocery_agent",
            recipe_id=recipe_id,
            status=grocery_result["status"],
            known_cost=grocery_result["data"].get("known_cost"),
            all_items_priced=grocery_result["data"].get("all_items_priced"),
        )

        if grocery_result["status"] == AgentStatus.FAILED.value:
            self._record_failed_candidate(
                workflow,
                recipe_id,
                "grocery_agent",
                "; ".join(grocery_result["errors"]) or "Grocery agent failed",
            )
            return

        grocery_data = grocery_result["data"]

        # Build the candidate shape expected by Day-3 evaluators.
        candidate_recipe = dict(recipe)
        candidate_recipe["ingredients"] = ingredient_data.get(
            "required_ingredients",
            recipe.get("ingredients", []),
        )

        # Domain reasoning -------------------------------------------------
        try:
            dietary_result = self.dietary_evaluator(candidate_recipe, user_state)
            feasibility_result = self.feasibility_evaluator(candidate_recipe, self._state_as_dict(user_state))
            budget_result = self._evaluate_budget(grocery_data, user_state)
            reasoning = self.candidate_evaluator(
                recipe_id=recipe_id,
                dietary_result=dietary_result,
                feasibility_result=feasibility_result,
                budget_result=budget_result,
            )
        except Exception as exc:
            self._record_failed_candidate(
                workflow, recipe_id, "reasoning_engine", str(exc)
            )
            return

        workflow.trace(
            "reasoning",
            recipe_id=recipe_id,
            decision=reasoning.get("status"),
            overall_score=reasoning.get("overall_score"),
        )

        workflow.candidate_results[recipe_id] = {
            "recipe_id": recipe_id,
            "status": reasoning.get("status", "failed"),
            "recipe": recipe,
            "ingredient": ingredient_data,
            "grocery": grocery_data,
            "reasoning": reasoning,
            "warnings": (
                ingredient_result["warnings"] + grocery_result["warnings"]
            ),
        }

    def _evaluate_budget(self, grocery_data: dict[str, Any], user_state: Any) -> dict:
        known_cost = float(grocery_data.get("known_cost", 0.0) or 0.0)
        all_items_priced = bool(grocery_data.get("all_items_priced", False))
        remaining_budget = self._remaining_budget(user_state)
        return self.budget_evaluator(
            purchase_cost=known_cost,
            remaining_budget=remaining_budget,
            has_unknown_cost=not all_items_priced,
        )

    @staticmethod
    def _remaining_budget(user_state: Any) -> float:
        if isinstance(user_state, dict):
            budget = user_state.get("remaining_budget", user_state.get("budget"))
        else:
            budget = getattr(
                user_state,
                "remaining_budget",
                getattr(user_state, "budget", None),
            )
        if budget is None:
            raise ValueError("User state must provide budget or remaining_budget")
        return float(budget)

    @staticmethod
    def _pantry_from_user_state(user_state: Any) -> Any:
        if isinstance(user_state, dict):
            return user_state.get(
                "pantry",
                user_state.get("ingredient_availability", {}),
            )
        return getattr(
            user_state,
            "pantry",
            getattr(user_state, "ingredient_availability", {}),
        )

    @staticmethod
    def _state_as_dict(user_state: Any) -> dict[str, Any]:
        if isinstance(user_state, dict):
            return user_state
        if hasattr(user_state, "__dict__"):
            return dict(vars(user_state))
        raise TypeError("user_state must be a dictionary or object with attributes")

    @staticmethod
    def _score_for_sort(candidate: dict[str, Any]) -> float:
        score = candidate.get("reasoning", {}).get("overall_score")
        return float(score) if score is not None else float("-inf")

    @staticmethod
    def _record_failed_candidate(
        workflow: WorkflowState,
        recipe_id: str,
        stage: str,
        reason: str,
    ) -> None:
        workflow.candidate_results[recipe_id] = {
            "recipe_id": recipe_id,
            "status": "failed",
            "stage": stage,
            "reason": reason,
        }
        workflow.trace(
            stage,
            recipe_id=recipe_id,
            status="failed",
            reason=reason,
        )

    @staticmethod
    def _final_response(
        workflow: WorkflowState,
        *,
        result: str,
        feasible: list[dict] | None = None,
        uncertain: list[dict] | None = None,
        rejected: list[dict] | None = None,
        selected: dict | None = None,
    ) -> dict[str, Any]:
        return {
            "status": workflow.status,
            "result": result,
            "request_id": workflow.request_id,
            "selected_recipe": selected,
            "feasible_candidates": feasible or [],
            "uncertain_candidates": uncertain or [],
            "rejected_candidates": rejected or [],
            "candidate_results": workflow.candidate_results,
            "warnings": workflow.warnings,
            "errors": workflow.errors,
            "execution_trace": workflow.execution_trace,
        }
    
    def evaluate_candidate(
        self,
        recipe_id: str,
        user_state: Any,
        meal_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        

        workflow = WorkflowState(
            request_id=str(uuid4()),
            user_state=user_state,
        )

        self._evaluate_one_candidate(
            workflow=workflow,
            recipe_id=recipe_id,
            user_state=user_state,
        )

        result = workflow.candidate_results.get(
            recipe_id
        )

        if result is None:
            return {
                "recipe_id": recipe_id,
                "status": "failed",
                "reason": (
                    "Candidate evaluation produced "
                    "no result."
                ),
                "execution_trace":
                    workflow.execution_trace,
            }

        # Preserve workflow trace for debugging/reporting.
        result = dict(result)

        result["execution_trace"] = (
            workflow.execution_trace
        )

        return result
