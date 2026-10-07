# src/planning/multi_meal_planner.py

from datetime import date
from typing import Any

from src.planning.meal_slot import MealSlot, generate_meal_slots
from src.planning.plan_state import PlanState
from src.planning.plan_validator import validate_plan


class MultiMealPlanner:
    """
    Orchestrates planning across multiple meal slots.

    Responsibilities:
    - Generate meal slots
    - Ask Recipe Agent for candidates
    - Evaluate candidates through existing Manager workflow
    - Retry rejected/uncertain candidates
    - Select feasible candidates
    - Update PlanState
    - Validate final plan

    This class DOES NOT implement:
    - Recipe retrieval
    - Ingredient processing
    - Pantry subtraction
    - Grocery search
    - Budget reasoning
    - Allergy/diet reasoning
    """

    def __init__(
        self,
        manager,
        max_candidates_per_slot: int = 5,
    ):
        self.manager = manager
        self.max_candidates_per_slot = max_candidates_per_slot

    # ============================================================
    # PUBLIC ENTRY POINT
    # ============================================================

    def plan_meals(
        self,
        user_state: dict,
        start_date: date,
        days: int,
        meal_types: list[str],
        schedule: dict | None = None,
    ) -> dict:
        """
        Build a multi-day, multi-meal plan.

        Example:
            3 days
            ["lunch", "dinner"]

        produces:
            6 meal slots.
        """

        # --------------------------------------------------------
        # 1. Generate meal slots
        # --------------------------------------------------------

        slots = generate_meal_slots(
            start_date=start_date,
            days=days,
            meal_types=meal_types,
            schedule=schedule,
        )

        # --------------------------------------------------------
        # 2. Determine initial budget
        # --------------------------------------------------------

        initial_budget = self._get_budget(user_state)

        # --------------------------------------------------------
        # 3. Create temporary Plan State
        # --------------------------------------------------------

        plan_state = PlanState(
            slots=slots,
            initial_budget=initial_budget,
        )

        # --------------------------------------------------------
        # 4. Fill each meal slot
        # --------------------------------------------------------

        for slot in slots:

            slot_result = self._plan_single_slot(
                user_state=user_state,
                slot=slot,
                plan_state=plan_state,
            )

            if not slot_result["selected"]:

                plan_state.mark_slot_infeasible(slot)

        # --------------------------------------------------------
        # 5. Final plan validation
        # --------------------------------------------------------

        validation = validate_plan(
            plan_state=plan_state,

            # TEMPORARY:
            # Member 4's final aggregated grocery basket
            # should eventually provide these two values.
            all_items_priced=True,

            final_grocery_cost=plan_state.estimated_spent,
        )

        plan_state.status = validation["status"]

        # --------------------------------------------------------
        # 6. Return final result
        # --------------------------------------------------------

        return {
            "plan": plan_state.to_dict(),
            "validation": validation,
        }

    # ============================================================
    # PLAN ONE MEAL SLOT
    # ============================================================

    def _plan_single_slot(
        self,
        user_state: dict,
        slot: MealSlot,
        plan_state: PlanState,
    ) -> dict:
        """
        Attempt to find one feasible recipe for one meal slot.

        Example:
            Monday Dinner

            R001 -> rejected
            R014 -> uncertain
            R027 -> feasible

            Select R027.
        """

        # --------------------------------------------------------
        # 1. Get candidates
        # --------------------------------------------------------

        candidate_ids = self._get_candidates(
            user_state=user_state,
            slot=slot,
            plan_state=plan_state,
        )

        if not candidate_ids:

            return {
                "selected": False,
                "reason": "no_candidates",
            }

        # Bounded retry
        candidate_ids = candidate_ids[
            : self.max_candidates_per_slot
        ]

        # --------------------------------------------------------
        # 2. Evaluate candidates sequentially
        # --------------------------------------------------------

        for recipe_id in candidate_ids:

            decision = self._evaluate_candidate(
                user_state=user_state,
                slot=slot,
                recipe_id=recipe_id,
                plan_state=plan_state,
            )

            status = str(
                decision.get("status", "")
            ).lower()

            # ====================================================
            # FEASIBLE
            # ====================================================

            if status == "feasible":

                estimated_cost = self._extract_cost(
                    decision
                )

                plan_state.add_selected_meal(
                    slot=slot,
                    recipe_id=recipe_id,
                    decision=decision,
                    estimated_cost=estimated_cost,
                )

                return {
                    "selected": True,
                    "recipe_id": recipe_id,
                    "decision": decision,
                }

            # ====================================================
            # UNCERTAIN
            # ====================================================

            if status == "uncertain":

                plan_state.add_uncertain(
                    slot=slot,
                    recipe_id=recipe_id,
                    reason=self._extract_reason(
                        decision
                    ),
                )

                # Try another candidate
                continue

            # ====================================================
            # REJECTED
            # ====================================================

            plan_state.add_rejection(
                slot=slot,
                recipe_id=recipe_id,
                reason=self._extract_reason(
                    decision
                ),
            )

            # Try another candidate

        # --------------------------------------------------------
        # 3. No feasible candidate
        # --------------------------------------------------------

        return {
            "selected": False,
            "reason": "all_candidates_exhausted",
        }

    # ============================================================
    # GET RECIPE CANDIDATES
    # ============================================================

    def _get_candidates(
        self,
        user_state: dict,
        slot: MealSlot,
        plan_state: PlanState,
    ) -> list[str]:
        """
        Ask the existing Recipe Agent for candidates.

        This method DOES NOT perform recipe retrieval itself.
        """

        meal_context = {
            "date": slot.date.isoformat(),

            "meal_type": slot.meal_type,

            "max_cooking_time":
                slot.max_cooking_time,

            # Member 2 can use these to prevent repetition.
            "used_recipe_ids":
                list(plan_state.used_recipe_ids),

            "exclude_recipe_ids":
                list(plan_state.used_recipe_ids),

            "remaining_budget":
                plan_state.remaining_budget,
        }

        # --------------------------------------------------------
        # Call existing Recipe Agent
        # --------------------------------------------------------

        response = self.manager.recipe_agent.run(
            user_state=user_state,
            meal_context=meal_context,
        )

        if not response:
            return []

        # --------------------------------------------------------
        # Day-4 AgentResult contract
        # --------------------------------------------------------

        if isinstance(response, dict):

            data = response.get(
                "data",
                response,
            )

            candidates = (
                data.get("candidate_recipe_ids")
                or data.get("recipe_ids")
                or data.get("candidates")
                or []
            )

        else:

            candidates = response

        # --------------------------------------------------------
        # Normalize candidate IDs
        # --------------------------------------------------------

        result = []

        for candidate in candidates:

            # Candidate already just recipe ID

            if isinstance(candidate, str):

                recipe_id = candidate

            # Candidate represented as object/dict

            elif isinstance(candidate, dict):

                recipe_id = (
                    candidate.get("recipe_id")
                    or candidate.get("id")
                )

            else:

                continue

            if not recipe_id:
                continue

            # ----------------------------------------------------
            # Prevent exact repetition
            # ----------------------------------------------------

            if recipe_id in plan_state.used_recipe_ids:
                continue

            # Prevent duplicate candidate IDs

            if recipe_id in result:
                continue

            result.append(recipe_id)

        return result

    # ============================================================
    # EVALUATE ONE CANDIDATE
    # ============================================================

    def _evaluate_candidate(
        self,
        user_state: dict,
        slot: MealSlot,
        recipe_id: str,
        plan_state: PlanState,
    ) -> dict:
        """
        Send one candidate through the EXISTING Day-4 workflow.

        Manager should internally use:

            Ingredient Agent
                ->
            Grocery Agent
                ->
            Reasoning Engine

        This planner does not duplicate that logic.
        """

        # --------------------------------------------------------
        # Copy user state
        # --------------------------------------------------------

        planning_user_state = dict(user_state)

        # Current plan budget must be used,
        # not original budget.

        planning_user_state[
            "budget_remaining"
        ] = plan_state.remaining_budget

        # --------------------------------------------------------
        # Current meal context
        # --------------------------------------------------------

        meal_context = {
            "date":
                slot.date.isoformat(),

            "meal_type":
                slot.meal_type,

            "max_cooking_time":
                slot.max_cooking_time,

            "recipe_id":
                recipe_id,

            "used_recipe_ids":
                list(plan_state.used_recipe_ids),
        }

        # --------------------------------------------------------
        # EXISTING MANAGER INTERFACE
        # --------------------------------------------------------

        if hasattr(
            self.manager,
            "evaluate_candidate",
        ):

            return self.manager.evaluate_candidate(
                recipe_id=recipe_id,
                user_state=planning_user_state,
                meal_context=meal_context,
            )

        if hasattr(
            self.manager,
            "process_candidate",
        ):

            return self.manager.process_candidate(
                recipe_id=recipe_id,
                user_state=planning_user_state,
                meal_context=meal_context,
            )

        raise AttributeError(
            "Manager must provide either "
            "evaluate_candidate() or "
            "process_candidate()."
        )

    # ============================================================
    # BUDGET HELPER
    # ============================================================

    @staticmethod
    def _get_budget(
        user_state: dict,
    ) -> float:
        """
        Support either:

            budget_remaining: 50

        or:

            budget: {
                total: 50,
                remaining: 40
            }

        or:

            budget: 50
        """

        if "budget_remaining" in user_state:

            return float(
                user_state["budget_remaining"]
            )

        budget = user_state.get(
            "budget",
            0.0,
        )

        if isinstance(budget, dict):

            return float(
                budget.get(
                    "remaining",
                    budget.get(
                        "total",
                        0.0,
                    ),
                )
            )

        return float(
            budget or 0.0
        )

    # ============================================================
    # COST HELPER
    # ============================================================

    @staticmethod
    def _extract_cost(
        decision: dict,
    ) -> float:
        """
        Extract estimated candidate purchase cost
        without depending strongly on one output shape.
        """

        possible_keys = (
            "known_cost",
            "purchase_cost",
            "estimated_cost",
            "total_cost",
        )

        # Top-level result

        for key in possible_keys:

            value = decision.get(key)

            if value is not None:

                return float(value)

        # Grocery result nested inside decision

        grocery = decision.get(
            "grocery",
            {},
        )

        if isinstance(grocery, dict):

            for key in possible_keys:

                value = grocery.get(key)

                if value is not None:

                    return float(value)

        return 0.0

    # ============================================================
    # REJECTION REASON HELPER
    # ============================================================

    @staticmethod
    def _extract_reason(
        decision: dict,
    ) -> Any:
        """
        Preserve useful explanation from
        the Reasoning Engine.
        """

        return (
            decision.get("reason")
            or decision.get(
                "failed_constraints"
            )
            or decision.get(
                "unknown_constraints"
            )
            or decision.get("errors")
            or "unspecified"
        )