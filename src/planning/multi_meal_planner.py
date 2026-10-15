# src/planning/multi_meal_planner.py
from datetime import date
from typing import Any
from src.planning.meal_slot import (
    MealSlot,
    generate_meal_slots,
)
from src.planning.plan_state import (
    PlanState,
)
from src.planning.plan_validator import (
    validate_plan,
)
from src.agents.grocery_agent import calculate_incremental_basket_cost
from src.state.inventory_state import (
    normalize_inventory,
    add_purchase,
    consume_inventory,
)
from src.state.nutrition_tracker import (
    aggregate_nutrition,
    calculate_nutrition_deviation,
    summarize_nutrition,
)
from src.agents.grocery_agent import (
    build_plan_grocery_basket,
)
from src.planning.cooking_schedule import (
    build_cooking_schedule,
    max_coverable_slots,
)
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
        self.last_plan_state: PlanState | None = None
        # Products found for plan-level shortages (see
        # _discover_missing_products), keyed by ingredient name.
        self._plan_product_cache: dict[str, list[dict]] = {}
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
        nutrition_targets: dict | None = None,
    ) -> dict:
        # ========================================================
        # 1. GENERATE MEAL SLOTS
        # ========================================================
        print(">>>>>>>>>Getting the meals now!! in plan meals<<<<<<<<<<<,")
        slots = generate_meal_slots(
            start_date=start_date,
            days=days,
            meal_types=meal_types,
            schedule=schedule,
        )
        print(f"Slots>>>>>>>>>>>>>>>{slots}<<<<<<<<<<<<")
        # ========================================================
        # 2. INITIAL BUDGET
        # ========================================================
        initial_budget = self._get_budget(user_state)
        print(f"Getting budget>>>>>>>>>>{initial_budget}<<<<<<<<<\n")
        # ========================================================
        # 3. INITIAL INVENTORY
        # Member 3
        # ========================================================
        raw_pantry = (
            user_state.get("pantry") or user_state.get("ingredient_availability") or {}
        )
        initial_inventory = normalize_inventory(raw_pantry)
        print(f"Getting initial inven: >>>>>>>>>>>{initial_inventory}<<<<<<")
        # ========================================================
        # 4. CREATE PLAN STATE
        # ========================================================
        plan_state = PlanState(
            slots=slots,
            initial_budget=initial_budget,
            initial_inventory=initial_inventory,
            current_inventory=dict(initial_inventory),
        )
        print(f"plan state: >>>>>>>>>>>{plan_state}<<<<<<<<<<<\n")
        # ========================================================
        # 5. OPTIMIZE COMPLETE MEAL PLAN
        # ========================================================
        optimized_state = self._optimize_meal_plan(
            user_state=user_state,
            initial_state=plan_state,
            beam_width=5,
            window_start=start_date,
        )
        plan_state = optimized_state
        # Mark slots that were not filled.
        selected_slot_ids = {
            meal["slot"]["slot_id"] for meal in plan_state.selected_meals
        }
        for slot in slots:
            if slot.slot_id not in selected_slot_ids:
                plan_state.mark_slot_infeasible(
                    slot, self._slot_candidate_report(plan_state, slot.slot_id)
                )
        # ========================================================
        # 5B. UPDATE NUTRITION AFTER SELECTION
        # ========================================================
        for selected in plan_state.selected_meals:
            slot_data = selected["slot"]
            matching_slot = next(
                slot for slot in slots if slot.slot_id == slot_data["slot_id"]
            )
            self._update_nutrition(
                plan_state=plan_state,
                slot=matching_slot,
                decision=selected["decision"],
            )
        # ========================================================
        # 6. MEMBER 4
        # BUILD FINAL AGGREGATED GROCERY BASKET
        # ========================================================
        final_grocery_basket = self._build_final_grocery_basket(plan_state)
        print(f"final grocery basket>>>>>{final_grocery_basket}<<<<<<<\n")
        plan_state.final_grocery_basket = final_grocery_basket
        # Reconcile inventory after final basket selection.
        reconciliation_trace_start = len(plan_state.execution_trace)
        inventory_ok = self._reconcile_final_inventory(
            plan_state=plan_state,
            final_grocery_basket=final_grocery_basket,
        )
        inventory_reconciliation_incomplete = any(
            event.get("event") == "inventory_reconciliation_incomplete"
            for event in plan_state.execution_trace[reconciliation_trace_start:]
        )
        # ========================================================
        # 7. NUTRITION SUMMARY
        # ========================================================
        nutrition_summary = summarize_nutrition(plan_state.nutrition_state)
        print(f"nutrition summ. >>>>>{nutrition_summary}<<<<<<<\n")
        nutrition_deviation = None
        if nutrition_targets:
            nutrition_deviation = calculate_nutrition_deviation(
                plan_state.nutrition_state,
                nutrition_targets,
            )
            print(
                f"nutritional devi.>>>>>{nutrition_deviation} and targets : {nutrition_targets}<<<<<<<\n"
            )
        # ========================================================
        # 8. FINAL PLAN VALIDATION
        # ========================================================
        if final_grocery_basket.get("planning_cost_complete") is True:
            final_cost = final_grocery_basket.get("planning_cost")
        elif final_grocery_basket.get("projected_cost_complete") is True:
            final_cost = final_grocery_basket.get("projected_cost")
        else:
            final_cost = None
        all_items_priced = final_grocery_basket.get(
            "all_items_priced",
            False,
        )
        validation = validate_plan(
            plan_state=plan_state,
            all_items_priced=all_items_priced,
            final_grocery_cost=final_cost,
            projected_cost_complete=final_grocery_basket.get(
                "projected_cost_complete", False
            ),
        )
        if not inventory_ok:
            validation["issues"].append("Final inventory reconciliation failed.")
            validation["status"] = "infeasible"
        elif inventory_reconciliation_incomplete:
            validation["issues"].append(
                "Some ingredient quantities or retail package "
                "coverage could not be verified."
            )

            if validation["status"] == "feasible":
                validation["status"] = "uncertain"
       
        print(f"validation of plan >>>>>{validation}<<<<<<<\n")
        # --------------------------------------------------------
        # Cooking-frequency scheduling
        # --------------------------------------------------------
        cooking_frequency = user_state.get("cook_frequency")
        if cooking_frequency is not None:
            cooking_schedule = build_cooking_schedule(
                selected_meals=plan_state.selected_meals,
                max_sessions=int(cooking_frequency),
                max_storage_days=self._leftover_storage_days(user_state),
                window_start=start_date,
            )
            plan_state.cooking_schedule = cooking_schedule
            if not cooking_schedule["valid"]:
                validation["status"] = "infeasible"
                validation["issues"].append(
                    "Cooking frequency exceeded: " f"{cooking_schedule['violations']}"
                )
        self._annotate_validation(plan_state, validation)
        plan_state.status = validation["status"]
        self.last_plan_state = plan_state
        # ========================================================
        # 9. RETURN COMPLETE PLAN
        # ========================================================
        return {
            "plan": plan_state.to_dict(),
            "validation": validation,
            "grocery_basket": final_grocery_basket,
            "nutrition_summary": nutrition_summary,
            "nutrition_deviation": nutrition_deviation,
        }
    # ============================================================
    # ADAPTIVE REPLANNING
    # ============================================================
    @staticmethod
    def _allocate_prepared_leftovers(
        plan_state,
        remaining_slots,
        approved_leftover_ids,
    ):
        from copy import deepcopy
        from datetime import date
        leftovers = deepcopy(plan_state.prepared_leftovers)
        allocated_meals = []
        unfilled_slots = []
        approved = set(approved_leftover_ids or [])
        for slot in remaining_slots:
            allocated = False
            for leftover in leftovers:
                leftover_id = leftover.get("leftover_id")
                if leftover_id not in approved:
                    continue
                if leftover.get("servings_remaining", 0) < 1:
                    continue
                if not leftover.get("storage"):
                    continue
                try:
                    prepared = date.fromisoformat(
                        leftover["prepared_date"]
                    )
                    expiry = date.fromisoformat(
                        leftover["expires_on"]
                    )
                except (KeyError, ValueError, TypeError):
                    continue
                if not (prepared <= slot.date <= expiry):
                    continue
                recipe_id = leftover["recipe_id"]
                # Per-serving nutrition: recorded with the leftover, or
                # taken from the meal that cooked it. Never silently zero.
                nutrition = leftover.get("nutrition") or next(
                    (
                        (meal.get("decision") or {}).get("recipe")
                        for meal in plan_state.selected_meals
                        if meal.get("recipe_id") == recipe_id
                        and meal.get("meal_source") != "prepared_leftover"
                        and (meal.get("decision") or {}).get("recipe")
                    ),
                    None,
                )
                if not nutrition:
                    plan_state.execution_trace.append({
                        "event": "prepared_leftover_nutrition_unknown",
                        "slot_id": slot.slot_id,
                        "leftover_id": leftover_id,
                        "recipe_id": recipe_id,
                    })
                allocated_meals.append({
                    "slot": slot.to_dict(),
                    "recipe_id": recipe_id,
                    "meal_source": "prepared_leftover",
                    "leftover_id": leftover_id,
                    "estimated_cost": 0.0,
                    "decision": {
                        "recipe_id": recipe_id,
                        "recipe": deepcopy(nutrition or {}),
                        "ingredient": {
                            "required_ingredients": []
                        },
                        "grocery": {
                            "items": []
                        },
                    },
                })
                leftover["servings_remaining"] -= 1
                plan_state.execution_trace.append({
                    "event": "prepared_leftover_allocated",
                    "slot_id": slot.slot_id,
                    "leftover_id": leftover_id,
                    "recipe_id": recipe_id,
                })
                allocated = True
                break
            if not allocated:
                unfilled_slots.append(slot)
        # Approval alone never consumes a leftover; say why an approved
        # batch was not used (its serving count is left unchanged).
        used_ids = {meal["leftover_id"] for meal in allocated_meals}
        by_id = {item.get("leftover_id"): item for item in leftovers}
        for leftover_id in sorted(approved - used_ids):
            leftover = by_id.get(leftover_id)
            reason = MultiMealPlanner._unused_leftover_reason(
                leftover, remaining_slots
            )
            plan_state.execution_trace.append({
                "event": "prepared_leftover_not_used",
                "leftover_id": leftover_id,
                "reason": reason,
                "servings_remaining": (
                    leftover.get("servings_remaining") if leftover else None
                ),
            })
        plan_state.prepared_leftovers = leftovers
        return allocated_meals, unfilled_slots

    @staticmethod
    def _unused_leftover_reason(leftover, remaining_slots) -> str:
        from datetime import date
        if leftover is None:
            return "unknown_leftover"
        if leftover.get("servings_remaining", 0) < 1:
            return "no_servings_remaining"
        if not leftover.get("storage"):
            return "storage_unknown"
        try:
            prepared = date.fromisoformat(leftover["prepared_date"])
            expiry = date.fromisoformat(leftover["expires_on"])
        except (KeyError, ValueError, TypeError):
            return "invalid_dates"
        if not remaining_slots:
            return "no_remaining_slots"
        if all(slot.date > expiry for slot in remaining_slots):
            return "expired_before_remaining_slots"
        if all(slot.date < prepared for slot in remaining_slots):
            return "prepared_after_remaining_slots"
        if all(not (prepared <= slot.date <= expiry) for slot in remaining_slots):
            return "no_remaining_slot_within_dates"
        return "eligible_slots_filled_by_other_leftovers"
    def skip_and_replan(
        self,
        user_state: dict,
        plan_state: PlanState,
        slot_id: str,
        completed_slot_ids: set[str] | None = None,
        nutrition_targets: dict | None = None,
    ) -> dict:
        """Skip one slot and replan unfinished slots without changing the input state."""
        from copy import deepcopy
        if not isinstance(user_state, dict):
            raise TypeError("user_state must be a dictionary")
        if not isinstance(plan_state, PlanState):
            raise TypeError("plan_state must be a PlanState instance")
        completed_ids = set(completed_slot_ids or set())
        original_slots = list(plan_state.slots)
        slots_by_id = {slot.slot_id: slot for slot in original_slots}
        if slot_id not in slots_by_id:
            raise ValueError(f"Unknown meal slot: {slot_id}")
        unknown_ids = completed_ids - set(slots_by_id)
        if unknown_ids:
            raise ValueError(f"Unknown completed slot IDs: {sorted(unknown_ids)}")
        if slot_id in completed_ids:
            raise ValueError("Cannot skip a meal marked as completed")
        if any(item.get("slot_id") == slot_id for item in plan_state.skipped_slots):
            raise ValueError(f"Meal slot is already skipped: {slot_id}")
        selected_by_slot = {
            meal.get("slot", {}).get("slot_id"): meal
            for meal in plan_state.selected_meals
            if meal.get("slot", {}).get("slot_id")
        }
        missing = completed_ids - set(selected_by_slot)
        if missing:
            raise ValueError(
                f"Completed slots must have selected meals: {sorted(missing)}"
            )
        rebuilt = deepcopy(plan_state)
        rebuilt.mark_slot_skipped(slots_by_id[slot_id])
        skipped_ids = {item["slot_id"] for item in rebuilt.skipped_slots}
        completed_meals = [
            deepcopy(selected_by_slot[slot.slot_id])
            for slot in original_slots
            if slot.slot_id in completed_ids
        ]
        remaining_slots = [
            slot
            for slot in original_slots
            if slot.slot_id not in completed_ids and slot.slot_id not in skipped_ids
        ]
        # A leftover already allocated in this plan was approved by the
        # user earlier. The page offers only batches with servings left,
        # so a later skip would otherwise release the serving and cook
        # that slot fresh instead.
        previously_allocated = [
            meal.get("leftover_id")
            for meal in plan_state.selected_meals
            if meal.get("meal_source") == "prepared_leftover"
            and meal.get("leftover_id")
        ]
        if previously_allocated:
            user_state = dict(user_state)
            user_state["approved_leftover_ids"] = list(dict.fromkeys(
                list(user_state.get("approved_leftover_ids") or [])
                + previously_allocated
            ))
        return self._replan_remaining_slots(
            user_state=user_state,
            rebuilt=rebuilt,
            original_slots=original_slots,
            kept_meals=completed_meals,
            remaining_slots=remaining_slots,
            nutrition_targets=nutrition_targets,
            trace_event={
                "event": "plan_rebuilt_after_skip",
                "skipped_slot_id": slot_id,
                "completed_slot_ids": sorted(completed_ids),
            },
        )

    def replace_meal(
        self,
        user_state: dict,
        plan_state: PlanState,
        slot_id: str,
        completed_slot_ids: set[str] | None = None,
        nutrition_targets: dict | None = None,
    ) -> dict:
        """Replace the recipe in one slot, keeping every other meal.

        The previous recipe is excluded for that slot. Grocery basket,
        budget, nutrition and inventory reconciliation are recomputed
        from the original pantry. The input state is not changed.
        """
        from copy import deepcopy
        if not isinstance(user_state, dict):
            raise TypeError("user_state must be a dictionary")
        if not isinstance(plan_state, PlanState):
            raise TypeError("plan_state must be a PlanState instance")
        completed_ids = set(completed_slot_ids or set())
        original_slots = list(plan_state.slots)
        slots_by_id = {slot.slot_id: slot for slot in original_slots}
        if slot_id not in slots_by_id:
            raise ValueError(f"Unknown meal slot: {slot_id}")
        if slot_id in completed_ids:
            raise ValueError("Cannot replace a meal marked as completed")
        if any(item.get("slot_id") == slot_id for item in plan_state.skipped_slots):
            raise ValueError(f"Meal slot is skipped: {slot_id}")
        current = next(
            (
                meal for meal in plan_state.selected_meals
                if meal.get("slot", {}).get("slot_id") == slot_id
            ),
            None,
        )
        if current is None:
            raise ValueError(f"No selected meal to replace in slot: {slot_id}")
        previous_recipe_id = current.get("recipe_id")
        rebuilt = deepcopy(plan_state)
        kept_meals = [
            deepcopy(meal) for meal in plan_state.selected_meals
            if meal.get("slot", {}).get("slot_id") != slot_id
        ]
        excluded = {
            key: set(value)
            for key, value in (
                user_state.get("excluded_recipe_ids_by_slot") or {}
            ).items()
        }
        excluded.setdefault(slot_id, set()).add(previous_recipe_id)
        replan_user_state = dict(user_state)
        replan_user_state["excluded_recipe_ids_by_slot"] = excluded
        return self._replan_remaining_slots(
            user_state=replan_user_state,
            rebuilt=rebuilt,
            original_slots=original_slots,
            kept_meals=kept_meals,
            remaining_slots=[slots_by_id[slot_id]],
            nutrition_targets=nutrition_targets,
            trace_event={
                "event": "meal_replaced",
                "slot_id": slot_id,
                "previous_recipe_id": previous_recipe_id,
                "completed_slot_ids": sorted(completed_ids),
            },
        )

    def _replan_remaining_slots(
        self,
        user_state: dict,
        rebuilt: PlanState,
        original_slots: list,
        kept_meals: list[dict],
        remaining_slots: list,
        nutrition_targets: dict | None,
        trace_event: dict,
    ) -> dict:
        """Re-optimize remaining slots around kept meals and recompute
        basket, budget, nutrition and inventory from the original pantry."""
        from copy import deepcopy
        slots_by_id = {slot.slot_id: slot for slot in original_slots}
        skipped_ids = {item["slot_id"] for item in rebuilt.skipped_slots}
        completed_meals = kept_meals
        # A leftover serving allocated to a slot that is now being
        # re-planned (or skipped) is available again. Without this the
        # serving stays decremented while no meal uses it.
        kept_slot_ids = {
            meal.get("slot", {}).get("slot_id") for meal in kept_meals
        }
        for meal in rebuilt.selected_meals:
            slot_id = meal.get("slot", {}).get("slot_id")
            if (
                meal.get("meal_source") != "prepared_leftover"
                or slot_id in kept_slot_ids
            ):
                continue
            for leftover in rebuilt.prepared_leftovers:
                if leftover.get("leftover_id") == meal.get("leftover_id"):
                    leftover["servings_remaining"] = (
                        leftover.get("servings_remaining", 0) + 1
                    )
                    rebuilt.execution_trace.append({
                        "event": "prepared_leftover_released",
                        "slot_id": slot_id,
                        "leftover_id": leftover.get("leftover_id"),
                    })
                    break
        leftover_meals, remaining_slots = (
            self._allocate_prepared_leftovers(
                plan_state=rebuilt,
                remaining_slots=remaining_slots,
                approved_leftover_ids=user_state.get(
                    "approved_leftover_ids", []
                ),
            )
        )
        rebuilt.selected_meals = completed_meals + leftover_meals
        rebuilt.used_recipe_ids = {
            meal["recipe_id"]
            for meal in rebuilt.selected_meals
        }
        rebuilt.rejected_candidates = []
        rebuilt.uncertain_candidates = []
        rebuilt.nutrition_state = {}
        rebuilt.current_inventory = deepcopy(rebuilt.initial_inventory)
        rebuilt.final_grocery_basket = {}
        rebuilt.status = "building"
        # Estimate the combined grocery cost for meals already completed.
        completed_basket = self._build_final_grocery_basket(rebuilt)
        completed_cost = completed_basket.get("projected_cost")
        if completed_cost is None:
            # Lower bound when only discretionary items are unpriced.
            completed_cost = completed_basket.get("priced_subtotal")
        if completed_cost is None:
            completed_cost = completed_basket.get("known_cost")
        if completed_cost is None:
            completed_cost = sum(
                max(float(meal.get("estimated_cost") or 0.0), 0.0)
                for meal in completed_meals
            )
        rebuilt.estimated_spent = max(float(completed_cost or 0.0), 0.0)
        # Reuse the existing optimizer only for unfinished slots.
        rebuilt.slots = remaining_slots
        # Cooking windows stay anchored to the original plan start.
        window_start = min(slot.date for slot in original_slots)
        optimized = self._optimize_meal_plan(
            user_state=user_state,
            initial_state=rebuilt,
            beam_width=5,
        )
        # Restore the original schedule order and full slot list.
        optimized.slots = original_slots
        selected_by_slot = {
            meal.get("slot", {}).get("slot_id"): meal
            for meal in optimized.selected_meals
            if meal.get("slot", {}).get("slot_id")
        }
        optimized.selected_meals = [
            selected_by_slot[slot.slot_id]
            for slot in original_slots
            if slot.slot_id in selected_by_slot
        ]
        optimized.used_recipe_ids = {
            meal["recipe_id"] for meal in optimized.selected_meals
        }
        selected_ids = set(selected_by_slot)
        for slot in original_slots:
            if slot.slot_id not in selected_ids and slot.slot_id not in skipped_ids:
                optimized.mark_slot_infeasible(
                    slot, self._slot_candidate_report(optimized, slot.slot_id)
                )
        # Recalculate nutrition for the retained and newly selected meals.
        optimized.nutrition_state = {}
        for meal in optimized.selected_meals:
            meal_slot_id = meal.get("slot", {}).get("slot_id")
            if meal_slot_id in slots_by_id:
                self._update_nutrition(
                    plan_state=optimized,
                    slot=slots_by_id[meal_slot_id],
                    decision=meal.get("decision") or {},
                )
        basket = self._build_final_grocery_basket(optimized)
        optimized.final_grocery_basket = basket
        reconciliation_trace_start = len(optimized.execution_trace)
        inventory_ok = self._reconcile_final_inventory(optimized, basket)
        inventory_reconciliation_incomplete = any(
            event.get("event") == "inventory_reconciliation_incomplete"
            for event in optimized.execution_trace[reconciliation_trace_start:]
        )
        nutrition_summary = summarize_nutrition(optimized.nutrition_state)
        nutrition_deviation = None
        if nutrition_targets:
            nutrition_deviation = calculate_nutrition_deviation(
                optimized.nutrition_state, nutrition_targets
            )
        if basket.get("all_items_priced") is True:
            final_cost = basket.get("known_cost")
        elif basket.get("projected_cost_complete") is True:
            final_cost = basket.get("projected_cost")
        else:
            final_cost = None
        validation = validate_plan(
            plan_state=optimized,
            all_items_priced=basket.get("all_items_priced", False),
            final_grocery_cost=final_cost,
            projected_cost_complete=basket.get("projected_cost_complete", False),
        )
        if not inventory_ok:
            validation["issues"].append("Final inventory reconciliation failed.")
            validation["status"] = "infeasible"
        elif inventory_reconciliation_incomplete:
            validation["issues"].append(
                "Some ingredient quantities or retail package "
                "coverage could not be verified."
            )
            if validation["status"] == "feasible":
                validation["status"] = "uncertain"
        # Recalculate cooking sessions after adaptive replanning.
        cooking_frequency = user_state.get("cook_frequency")
        if cooking_frequency is not None:
            cooking_schedule = build_cooking_schedule(
                selected_meals=optimized.selected_meals,
                max_sessions=int(cooking_frequency),
                max_storage_days=self._leftover_storage_days(user_state),
                window_start=window_start,
            )
            optimized.cooking_schedule = cooking_schedule
            if not cooking_schedule["valid"]:
                validation["status"] = "infeasible"
                validation["issues"].append(
                    "Cooking frequency exceeded: " f"{cooking_schedule['violations']}"
                )
        else:
            optimized.cooking_schedule = {}
        self._annotate_validation(optimized, validation)
        optimized.status = validation["status"]
        optimized.execution_trace.append(dict(trace_event))
        self.last_plan_state = optimized
        return {
            "plan": optimized.to_dict(),
            "validation": validation,
            "grocery_basket": basket,
            "nutrition_summary": nutrition_summary,
            "nutrition_deviation": nutrition_deviation,
        }
    # PLAN ONE MEAL SLOT
    # ============================================================
    def _evaluate_candidates_for_slot(
        self,
        user_state: dict,
        slot: MealSlot,
        plan_state: PlanState,
    ) -> list[dict]:
        """
        Evaluate recipe candidates for one meal slot.
        Checks non-budget hard constraints and combined
        grocery basket affordability.
        Returns feasible candidates sorted by total cost.
        Does not select meals or update budget.
        """
        candidate_ids = self._get_candidates(
            user_state=user_state,
            slot=slot,
            plan_state=plan_state,
        )
        feasible_candidates = []
        max_repeats = int(
            user_state.get(
                "max_recipe_repetitions",
                2,
            )
        )
        for recipe_id in candidate_ids:
            recipe_count = sum(
                meal["recipe_id"] == recipe_id for meal in plan_state.selected_meals
            )
            if recipe_count >= max_repeats:
                # Hard limit: recorded so every skipped alternative
                # has a stated reason.
                plan_state.add_rejection(
                    slot=slot,
                    recipe_id=recipe_id,
                    reason={
                        "constraint": "max_recipe_repetitions",
                        "status": "fail",
                        "limit": max_repeats,
                        "times_selected": recipe_count,
                    },
                )
                continue
            decision = self._evaluate_candidate(
                user_state=user_state,
                slot=slot,
                recipe_id=recipe_id,
                plan_state=plan_state,
            )
            reasoning = decision.get("reasoning") or {}
            constraints = reasoning.get("hard_constraints") or []
            non_budget = [
                item for item in constraints if item.get("constraint") != "budget"
            ]
            if not non_budget or any(
                item.get("status") != "pass" for item in non_budget
            ):
                plan_state.add_rejection(
                    slot=slot,
                    recipe_id=recipe_id,
                    reason=non_budget or "Hard constraints not verified",
                )
                continue
            blocking = self._candidate_projection_blockers(decision)
            if blocking:
                plan_state.add_uncertain(
                    slot=slot,
                    recipe_id=recipe_id,
                    reason={
                        "type": "incomplete_grocery_projection",
                        "blocking_items": blocking,
                    },
                )
                continue
            from copy import deepcopy
            trial_state = deepcopy(plan_state)
            trial_state.selected_meals.append(
                {
                    "slot": slot.to_dict(),
                    "recipe_id": recipe_id,
                    "decision": decision,
                    "estimated_cost": 0.0,
                }
            )
            try:
                trial_basket = self._build_final_grocery_basket(trial_state)
            except ValueError as exc:
                plan_state.add_uncertain(
                    slot=slot,
                    recipe_id=recipe_id,
                    reason={
                        "type": "grocery_aggregation_error",
                        "message": str(exc),
                    },
                )
                continue
            projected_total, conditional_items = self._selection_cost(trial_basket)
            if projected_total is None:
                missing = trial_basket.get(
                    "selection_blocking_items",
                    trial_basket.get("projection_missing", []),
                )
                unpriced = trial_basket.get(
                    "unpriced_items",
                    [],
                )
                plan_state.add_uncertain(
                    slot=slot,
                    recipe_id=recipe_id,
                    reason={
                        "type": "combined_basket_incomplete",
                        "projection_missing": missing,
                        "unpriced_items": unpriced,
                    },
                )
                continue
            # With discretionary unpriced items the total is a lower
            # bound; exceeding the budget is still a definite failure.
            if projected_total > plan_state.initial_budget:
                plan_state.add_rejection(
                    slot=slot,
                    recipe_id=recipe_id,
                    reason={
                        "constraint": "budget",
                        "status": "fail",
                        "projected_plan_cost": projected_total,
                        "cost_is_lower_bound": bool(conditional_items),
                        "budget": plan_state.initial_budget,
                    },
                )
                continue
            # Rebuild the current partial plan's basket.
            # Use the same original pantry for both baskets.
            if plan_state.selected_meals:
                current_basket = self._build_final_grocery_basket(plan_state)
                previous_total, _ = self._selection_cost(current_basket)
                if previous_total is None:
                    plan_state.add_uncertain(
                        slot=slot,
                        recipe_id=recipe_id,
                        reason="Existing combined basket cost incomplete",
                    )
                    continue
            else:
                previous_total = 0.0
            incremental_cost = round(
                projected_total - previous_total,
                2,
            )
            if incremental_cost < -0.01:
                plan_state.add_uncertain(
                    slot=slot,
                    recipe_id=recipe_id,
                    reason=(
                        "Combined basket cost decreased after "
                        "adding a recipe. Check product consistency."
                    ),
                )
                continue
            incremental_cost = max(0.0, incremental_cost)
            own_discretionary = self._discretionary_items(decision)
            feasible_candidates.append(
                {
                    "recipe_id": recipe_id,
                    "decision": decision,
                    "incremental_cost": incremental_cost,
                    "total_cost": projected_total,
                    # Selectable only with discretionary ("to taste")
                    # items left unpriced; plan cost stays incomplete.
                    "conditional_items": sorted(
                        set(conditional_items) & set(own_discretionary)
                    ),
                }
            )
        feasible_candidates.sort(
            key=lambda item: (
                item["total_cost"],
                item["recipe_id"],
            )
        )
        return feasible_candidates
    @staticmethod
    def _slot_candidate_report(plan_state: PlanState, slot_id: str) -> list[dict]:
        """Why each evaluated candidate did not fill an unfilled slot."""
        report = {}
        for status, entries in (
            ("rejected", plan_state.rejected_candidates),
            ("uncertain", plan_state.uncertain_candidates),
        ):
            for entry in entries:
                if entry.get("slot_id") == slot_id:
                    report[entry.get("recipe_id")] = {
                        "recipe_id": entry.get("recipe_id"),
                        "status": status,
                        "reason": entry.get("reason"),
                    }
        return list(report.values())

    @staticmethod
    def _annotate_validation(plan_state: PlanState, validation: dict) -> None:
        """Surface conditional selections and repetition conflicts."""
        conditional = [
            {
                "slot_id": (meal.get("slot") or {}).get("slot_id"),
                "recipe_id": meal.get("recipe_id"),
                "unpriced_items": meal.get("conditional_items"),
            }
            for meal in plan_state.selected_meals
            if meal.get("conditional_items")
        ]
        if conditional:
            validation["conditional_selections"] = conditional
            validation["issues"].append(
                f"{len(conditional)} meal(s) selected with unpriced "
                "'to taste' ingredients; their grocery cost is incomplete."
            )
            if validation["status"] == "feasible":
                validation["status"] = "uncertain"
        conflicts = [
            event for event in plan_state.execution_trace
            if event.get("event") == "repetition_relaxation_requires_confirmation"
        ]
        if conflicts:
            conflict = conflicts[-1]
            validation.setdefault("constraint_conflicts", []).append({
                key: value for key, value in conflict.items() if key != "event"
            })
            validation["issues"].append(
                f"Recipe repetition limit ({conflict['limit']}) left "
                f"{conflict['filled_if_relaxed'] - conflict['filled_with_limit']} "
                "more slot(s) unfilled; confirmation is required before "
                "repeating recipes."
            )
        capacity = [
            event for event in plan_state.execution_trace
            if event.get("event") == "cooking_capacity_insufficient"
        ]
        if capacity:
            limit = capacity[-1]
            validation.setdefault("constraint_conflicts", []).append({
                "constraint": "cook_frequency",
                **{key: value for key, value in limit.items() if key != "event"},
            })
            message = (
                f"Cooking {limit['cook_frequency']} time(s) per 7-day window, "
                f"with leftovers eaten within {limit['leftover_storage_days']} "
                f"day(s) of cooking and at most "
                f"{limit['max_recipe_repetitions']} portion(s) per recipe, "
                f"can serve at most "
                f"{limit['max_fillable_slots']} of "
                f"{limit['requested_slots']} meal slots."
            )
            options = []
            if limit.get("storage_days_needed") is not None:
                options.append(
                    f"keep leftovers {limit['storage_days_needed']} day(s)"
                )
            if limit.get("sessions_needed") is not None:
                options.append(
                    f"cook {limit['sessions_needed']} time(s) per week"
                )
            if options:
                message += " All slots need: " + " or ".join(options) + "."
            validation["issues"].append(message)

    @staticmethod
    def _discretionary_items(decision: dict) -> list[str]:
        """Names of this candidate's "to taste" requirements."""
        from src.agents.grocery_agent import (
            DISCRETIONARY_INSTRUCTIONS,
            classify_requirement,
        )
        names = []
        required = (decision.get("ingredient") or {}).get("required_ingredients") or []
        for ingredient in required:
            if not isinstance(ingredient, dict):
                continue
            kind, detail = classify_requirement(ingredient)
            if kind == "qualitative" and detail in DISCRETIONARY_INSTRUCTIONS:
                name = ingredient.get("ingredient_name") or ingredient.get("name")
                if name:
                    names.append(str(name).strip().lower())
        return sorted(set(names))

    def _candidate_projection_blockers(self, decision: dict) -> list[str]:
        """Candidate-level grocery gaps that block selection.

        Discretionary "to taste" items may stay unpriced; any other
        unpriced item (no product, missing quantity or unit) blocks.
        """
        grocery = decision.get("grocery") or {}
        if grocery.get("projected_cost_complete"):
            return []
        missing = [
            str(name).strip().lower()
            for name in grocery.get("projection_missing") or []
        ]
        if not missing:
            # Incomplete without a list of causes: stay conservative.
            return ["unspecified grocery projection gap"]
        discretionary = set(self._discretionary_items(decision))
        return [name for name in missing if name not in discretionary]

    @staticmethod
    def _selection_cost(basket: dict) -> tuple[float | None, list[str]]:
        """(cost used for selection, discretionary unpriced items).

        None when a blocking gap exists. With only discretionary gaps
        the cost is the priced subtotal, a lower bound.
        """
        if basket.get("projected_cost_complete") and basket.get("projected_cost") is not None:
            return float(basket["projected_cost"]), []
        if basket.get("selection_projection_complete") and basket.get("priced_subtotal") is not None:
            return (
                float(basket["priced_subtotal"]),
                list(basket.get("discretionary_unpriced_items") or []),
            )
        return None, []

    # Optimise meal plan
    def _optimize_meal_plan(
        self,
        user_state: dict,
        initial_state: PlanState,
        beam_width: int = 5,
        window_start: date | None = None,
    ) -> PlanState:
        """
        Find an affordable meal plan while preferring recipe diversity.
        Ranking:
        1. Valid cooking schedule (when cook_frequency is set).
        2. More meal slots still reachable: slots filled plus remaining
           slots the cooking sessions left in each 7-day window (and
           leftovers of batches already cooked) could still serve.
           Without this, diversity spends every session early and later
           slots are stranded.
        3. More meal slots filled.
        4. More unique recipes.
        5. Fewer repeats of the same recipe in adjacent slots
           (e.g. lunch and dinner on the same day).
        6. Fewer meals selected only conditionally (with unpriced
           "to taste" items).
        7. Lower combined projected grocery cost.
        The repetition limit is a hard constraint. The default limit is
        relaxed only with explicit consent
        (user_state["allow_repetition_relaxation"] is True); otherwise
        the planner reports what relaxing would fill and leaves the
        slots unfilled.
        """
        from copy import deepcopy
        total_possible_meals = len(initial_state.slots)
        configured_limit = user_state.get("max_recipe_repetitions")
        # strict_limit = (
        #     max(1, int(configured_limit)) if configured_limit is not None else 2
        # )
        # configured_limit = user_state.get("max_recipe_repetitions")

        strict_limit = (
            max(1, int(configured_limit))if configured_limit is not None
            else len(initial_state.slots)
        )
        cooking_frequency = user_state.get("cook_frequency")
        if cooking_frequency is not None:
            cooking_frequency = int(cooking_frequency)
            if cooking_frequency < 1:
                raise ValueError("cook_frequency must be at least 1")
        storage_days = self._leftover_storage_days(user_state)
        if window_start is None:
            # Earliest date of the plan: during replanning the slots
            # are only the unfinished ones, so kept and skipped slots
            # count too.
            window_start = min(
                [slot.date for slot in initial_state.slots]
                + [
                    date.fromisoformat(meal["slot"]["date"])
                    for meal in initial_state.selected_meals
                    if (meal.get("slot") or {}).get("date")
                ]
                + [
                    date.fromisoformat(str(item["slot_id"]).split("_")[0])
                    for item in initial_state.skipped_slots
                    if item.get("slot_id")
                ],
                default=None,
            )
        def cooking_schedule_for(state):
            if cooking_frequency is None:
                return None
            return build_cooking_schedule(
                selected_meals=state.selected_meals,
                max_sessions=cooking_frequency,
                max_storage_days=storage_days,
                window_start=window_start,
            )
        def reachable_slots(state, remaining, max_repeats):
            if cooking_frequency is None:
                return len(state.selected_meals) + len(remaining)
            return self._reachable_slots(
                state, remaining, max_repeats,
                cooking_frequency, storage_days, window_start,
            )
        meal_order = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}
        def slot_position(meal):
            slot = meal.get("slot") or {}
            return (
                str(slot.get("date") or ""),
                meal_order.get(slot.get("meal_type"), 9),
                str(slot.get("slot_id") or ""),
            )
        def adjacent_repeats(state):
            meals = sorted(state.selected_meals, key=slot_position)
            return sum(
                1
                for previous, current in zip(meals, meals[1:])
                if previous.get("recipe_id") == current.get("recipe_id")
            )
        def ranking_key(state, remaining=(), max_repeats=None):
            schedule = cooking_schedule_for(state)
            return (
                0 if schedule is None or schedule["valid"] else 1,
                -reachable_slots(
                    state, remaining, max_repeats or total_possible_meals
                ),
                -len(state.selected_meals),
                -len(state.used_recipe_ids),
                adjacent_repeats(state),
                sum(1 for meal in state.selected_meals if meal.get("conditional_items")),
                round(state.estimated_spent, 2),
            )
        def search(search_user_state):
            max_repeats = int(search_user_state["max_recipe_repetitions"])
            beams = [deepcopy(initial_state)]
            for position, slot in enumerate(initial_state.slots):
                remaining = initial_state.slots[position + 1:]
                next_beams = []
                for state in beams:
                    candidates = self._evaluate_candidates_for_slot(
                        user_state=search_user_state,
                        slot=slot,
                        plan_state=state,
                    )
                    for candidate in candidates:
                        trial = deepcopy(state)
                        trial.add_selected_meal(
                            slot=slot,
                            recipe_id=candidate["recipe_id"],
                            decision=candidate["decision"],
                            estimated_cost=candidate["incremental_cost"],
                        )
                        if candidate.get("conditional_items"):
                            trial.selected_meals[-1]["conditional_items"] = (
                                candidate["conditional_items"]
                            )
                        # The consolidated basket total is authoritative.
                        trial.estimated_spent = candidate["total_cost"]
                        cooking_schedule = cooking_schedule_for(trial)
                        if (
                            cooking_schedule is not None
                            and not cooking_schedule["valid"]
                        ):
                            # Recorded so an unfilled slot shows that
                            # an otherwise eligible recipe needed one
                            # more cooking session than allowed.
                            state.add_rejection(
                                slot=slot,
                                recipe_id=candidate["recipe_id"],
                                reason={
                                    "constraint": "cook_frequency",
                                    "status": "fail",
                                    "limit": cooking_frequency,
                                    "leftover_storage_days": storage_days,
                                    "window_sessions": cooking_schedule[
                                        "violations"
                                    ],
                                },
                            )
                            continue
                        next_beams.append(trial)
                    # Keep a skip-slot branch for partial plans.
                    next_beams.append(deepcopy(state))
                next_beams.sort(
                    key=lambda state: ranking_key(state, remaining, max_repeats)
                )
                beams = next_beams[:beam_width]
            return min(beams, key=ranking_key)
        strict_user_state = dict(user_state)
        strict_user_state["max_recipe_repetitions"] = strict_limit
        best_state = search(strict_user_state)
        # The default limit is never relaxed silently. Explicit user
        # limits are never relaxed at all.
        if (
            configured_limit is None
            and len(best_state.selected_meals) < total_possible_meals
        ):
            relaxed_user_state = dict(user_state)
            relaxed_user_state["max_recipe_repetitions"] = max(
                strict_limit, total_possible_meals
            )
            relaxed_state = search(relaxed_user_state)
            gain = len(relaxed_state.selected_meals) - len(best_state.selected_meals)
            if gain > 0:
                details = {
                    "limit": strict_limit,
                    "filled_with_limit": len(best_state.selected_meals),
                    "filled_if_relaxed": len(relaxed_state.selected_meals),
                    "relaxed_selection": [
                        {
                            "slot_id": (meal.get("slot") or {}).get("slot_id"),
                            "recipe_id": meal.get("recipe_id"),
                        }
                        for meal in sorted(
                            relaxed_state.selected_meals, key=slot_position
                        )
                    ],
                }
                if user_state.get("allow_repetition_relaxation") is True:
                    best_state = relaxed_state
                    best_state.execution_trace.append({
                        "event": "repetition_limit_relaxed",
                        "reason": "allow_repetition_relaxation was set by the user",
                        **details,
                    })
                else:
                    best_state.execution_trace.append({
                        "event": "repetition_relaxation_requires_confirmation",
                        "message": (
                            "Not enough distinct eligible recipes for every "
                            "slot within the repetition limit. Set "
                            "allow_repetition_relaxation=True to accept "
                            "repeated recipes."
                        ),
                        **details,
                    })
        if (
            cooking_frequency is not None
            and len(best_state.selected_meals) < total_possible_meals
        ):
            relaxed = any(
                event.get("event") == "repetition_limit_relaxed"
                for event in best_state.execution_trace
            )
            self._report_cooking_capacity(
                best_state, initial_state,
                cooking_frequency, storage_days, window_start,
                max(strict_limit, total_possible_meals) if relaxed else strict_limit,
            )
        return best_state

    @staticmethod
    def _leftover_storage_days(user_state: dict) -> int:
        """Days a cooked batch may be eaten after cooking (default 1).

        A user setting, never inferred: the default keeps the
        planner's original one-day assumption.
        """
        value = user_state.get("leftover_storage_days")
        if value is None:
            return 1
        if isinstance(value, bool) or int(value) != value or int(value) < 0:
            raise ValueError("leftover_storage_days must be a whole number >= 0")
        return int(value)

    @staticmethod
    def _reachable_slots(
        state, remaining, max_repeats,
        cooking_frequency, storage_days, window_start,
    ) -> int:
        """Filled slots plus remaining slots cooking capacity can serve.

        A remaining slot is served by leftovers of a batch already
        cooked (within storage_days, repetition limit permitting) or
        by a new session, at most cooking_frequency per 7-day window.
        Recipe availability is not checked, so this is optimistic.
        """
        schedule = build_cooking_schedule(
            selected_meals=state.selected_meals,
            max_sessions=cooking_frequency,
            max_storage_days=storage_days,
            window_start=window_start,
        )
        usage = {}
        for meal in state.selected_meals:
            usage[meal["recipe_id"]] = usage.get(meal["recipe_id"], 0) + 1
        latest_batch = {}
        for session in schedule["sessions"]:
            latest_batch[session["recipe_id"]] = date.fromisoformat(
                session["cook_date"]
            )
        needs_session = []
        extended = 0
        for slot in remaining:
            recipe_id = next(
                (
                    recipe for recipe, cooked in sorted(latest_batch.items())
                    if 0 <= (slot.date - cooked).days <= storage_days
                    and usage.get(recipe, 0) < max_repeats
                ),
                None,
            )
            if recipe_id is not None:
                usage[recipe_id] = usage.get(recipe_id, 0) + 1
                extended += 1
            else:
                needs_session.append({"date": slot.date})
        return len(state.selected_meals) + extended + max_coverable_slots(
            needs_session,
            max_sessions=cooking_frequency,
            max_storage_days=storage_days,
            window_start=window_start,
            sessions_used=schedule["weekly_session_counts"],
            portions_per_session=max_repeats,
        )

    @classmethod
    def _report_cooking_capacity(
        cls, best_state, initial_state,
        cooking_frequency, storage_days, window_start, max_repeats,
    ) -> None:
        """Explain when cooking capacity leaves slots unfilled.

        Capacity is the most slots cooking_frequency sessions per 7-day
        window can serve, with leftovers kept storage_days days and at
        most max_repeats portions per recipe. Recipe availability is
        not considered.
        """
        slots = initial_state.slots
        requested = len(slots) + len(initial_state.selected_meals)

        def capacity(sessions, days):
            return cls._reachable_slots(
                initial_state, slots, max_repeats, sessions, days, window_start
            )

        max_fillable = capacity(cooking_frequency, storage_days)
        if max_fillable >= requested:
            return
        event = {
            "event": "cooking_capacity_insufficient",
            "cook_frequency": cooking_frequency,
            "leftover_storage_days": storage_days,
            "window_start": window_start.isoformat() if window_start else None,
            "max_recipe_repetitions": max_repeats,
            "requested_slots": requested,
            "max_fillable_slots": max_fillable,
            "filled_slots": len(best_state.selected_meals),
        }
        # What would make every slot reachable (reported, not applied).
        for days in range(storage_days + 1, 8):
            if capacity(cooking_frequency, days) >= requested:
                event["storage_days_needed"] = days
                break
        for sessions in range(cooking_frequency + 1, requested + 1):
            if capacity(sessions, storage_days) >= requested:
                event["sessions_needed"] = sessions
                break
        best_state.execution_trace.append(event)

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
        Retrieve new recipes and include previously selected
        recipes as potential reuse candidates.
        Recipe repetition is limited during candidate evaluation.
        """
        meal_slot = {
            "date": slot.date.isoformat(),
            "meal_type": slot.meal_type,
            "max_cooking_time": slot.max_cooking_time,
        }
        max_repeats = int(
            user_state.get(
                "max_recipe_repetitions",
                2,
            )
        )
        usage_counts = {}
        for meal in plan_state.selected_meals:
            recipe_id = meal["recipe_id"]
            usage_counts[recipe_id] = usage_counts.get(recipe_id, 0) + 1
        # Reuse candidates are already known to the planner.
        reuse_ids = [
            recipe_id
            for recipe_id in usage_counts
            if usage_counts[recipe_id] < max_repeats
        ]
        # Ask Recipe Agent for new recipes.
        # Existing recipe IDs remain excluded from retrieval,
        # but are reintroduced locally as reuse candidates.
        response = self.manager.recipe_agent.run(
            user_state=user_state,
            meal_slot=meal_slot,
            selected_recipe_ids=list(plan_state.used_recipe_ids),
            recent_cuisines=[],
            max_candidates=self.max_candidates_per_slot,
        )
        if isinstance(response, dict):
            candidates = response.get("candidate_recipe_ids")
            if candidates is None:
                data = response.get("data") or {}
                candidates = data.get("candidate_recipe_ids", [])
        elif isinstance(response, list):
            candidates = response
        else:
            candidates = []
        result = []
        # Prioritize reuse candidates to encourage
        # ingredient sharing and batch-friendly plans.
        for recipe_id in reuse_ids:
            if recipe_id not in result:
                result.append(recipe_id)
        for candidate in candidates or []:
            if isinstance(candidate, str):
                recipe_id = candidate.strip().upper()
            elif isinstance(candidate, dict):
                recipe_id = candidate.get("recipe_id") or candidate.get("id")
                if recipe_id:
                    recipe_id = str(recipe_id).strip().upper()
            else:
                continue
            if not recipe_id:
                continue
            if recipe_id not in result:
                result.append(recipe_id)
        # A replaced recipe is not offered again for the same slot.
        excluded = (
            user_state.get("excluded_recipe_ids_by_slot") or {}
        ).get(slot.slot_id) or ()
        return [recipe_id for recipe_id in result if recipe_id not in excluded]
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
        planning_user_state = dict(user_state)
        # Use CURRENT remaining budget.
        planning_user_state["remaining_budget"] = plan_state.remaining_budget
        # Use CURRENT inventory.
        planning_user_state["pantry"] = self._inventory_to_pantry(
            plan_state.current_inventory
        )
        meal_context = {
            "date": slot.date.isoformat(),
            "meal_type": slot.meal_type,
            "max_cooking_time": slot.max_cooking_time,
        }
        return self.manager.evaluate_candidate(
            recipe_id=recipe_id,
            user_state=planning_user_state,
            meal_context=meal_context,
            defer_budget_to_planner=True,
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
            return float(user_state["budget_remaining"])
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
        return float(budget or 0.0)
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
            or decision.get("failed_constraints")
            or decision.get("unknown_constraints")
            or decision.get("errors")
            or "unspecified"
        )
    def _update_nutrition(
        self,
        plan_state: PlanState,
        slot: MealSlot,
        decision: dict,
    ) -> None:
        recipe = decision.get(
            "recipe",
            {},
        )
        if not recipe:
            return
        plan_state.nutrition_state = aggregate_nutrition(
            nutrition_state=plan_state.nutrition_state,
            date=slot.date.isoformat(),
            nutrition=recipe,
            servings=1.0,
        )
        plan_state.execution_trace.append(
            {
                "event": "nutrition_updated",
                "slot_id": slot.slot_id,
                "recipe_id": decision.get("recipe_id"),
            }
        )
    def _reconcile_final_inventory(
        self,
        plan_state: PlanState,
        final_grocery_basket: dict,
    ) -> bool:
        """Reconcile original pantry + planned purchases - selected recipes.

        An ordinary shortage is reported as incomplete, not an exception.
        Do not commit inventory when measurable requirements are uncovered.
        """
        from copy import deepcopy
        from src.agents.grocery_agent import (
            aggregate_requirements,
            classify_requirement,
            collect_unresolved_quantity_requirements,
            subtract_inventory,
        )

        inventory = deepcopy(plan_state.initial_inventory)
        qualitative_requirements = []

        # Add planned packages before checking ingredient coverage.
        for item in final_grocery_basket.get("items", []):
            packages = item.get("packages")
            # Lines with no planned package (qualitative, unresolved
            # quantity or conversion, no product) add nothing; the
            # coverage check below reports each of them explicitly.
            if packages is None or packages == 0:
                continue
            if item.get("package_quantity") is None or not item.get("package_unit"):
                plan_state.execution_trace.append({
                    "event": "inventory_reconciliation_incomplete",
                    "reason": f"Missing package quantity or unit for {item.get('name')}",
                })
                return True
            try:
                inventory = add_purchase(inventory, {
                    "ingredient_name": item.get("name"),
                    "package_quantity": item["package_quantity"],
                    "package_unit": item["package_unit"],
                    "packages_needed": packages,
                })
            except ValueError as exc:
                plan_state.execution_trace.append({
                    "event": "inventory_reconciliation_failed",
                    "reason": str(exc),
                })
                return False

        recipe_requirements = []
        all_requirements = []
        for selected in plan_state.selected_meals:
            if selected.get("meal_source") == "prepared_leftover":
                continue
            decision = selected.get("decision") or {}
            required = (decision.get("ingredient") or {}).get("required_ingredients", [])
            ingredients = [i for i in required if isinstance(i, dict)]
            measurable = []
            # Same classifier as the grocery basket, so each occurrence
            # is measurable, qualitative or unresolved exactly once.
            for ingredient in ingredients:
                kind, _ = classify_requirement(ingredient)
                if kind == "qualitative":
                    qualitative_requirements.append({
                        "event": "qualitative_requirement_unresolved",
                        "recipe_id": selected.get("recipe_id"),
                        "ingredient_name": ingredient.get("ingredient_name") or ingredient.get("name"),
                        "occurrence_id": ingredient.get("occurrence_id"),
                        "quantity": ingredient.get("quantity", ingredient.get("required_quantity")),
                        "unit": str(ingredient.get("unit", ingredient.get("required_unit", "")) or "").strip().lower(),
                    })
                elif kind == "measurable":
                    measurable.append(ingredient)
            slot_id = (selected.get("slot") or {}).get("slot_id")
            recipe_requirements.append({
                "recipe_id": selected.get("recipe_id"),
                "slot_id": slot_id,
                "ingredients": measurable,
            })
            all_requirements.append({
                "recipe_id": selected.get("recipe_id"),
                "slot_id": slot_id,
                "ingredients": ingredients,
            })

        # Quantity or unit unknown: never treated as covered.
        unresolved_quantity_requirements = [
            {
                "ingredient_id": record["ingredient_id"],
                "ingredient_name": record["ingredient_name"],
                "recipe_ids": record["recipe_ids"],
                "occurrence_ids": record["occurrence_ids"],
                "reasons": record["reasons"],
            }
            for record in collect_unresolved_quantity_requirements(
                all_requirements
            )
        ]

        # Compare ALL requirements at once, so pantry stock is never counted twice.
        aggregated = aggregate_requirements(recipe_requirements)
        coverage = subtract_inventory(aggregated, self._inventory_to_pantry(inventory))
        confirmed_shortages = []
        unverified_package_coverage = []
        unresolved_conversions = []
        # Covered only through an estimated conversion; reported so
        # estimates are never presented as verified coverage.
        estimated_conversions = []

        basket_items = final_grocery_basket.get("items", [])

        def matching_purchase(requirement):
            ingredient_id = requirement.get("ingredient_id")
            name = str(
                requirement.get("ingredient_name") or ""
            ).strip().lower()

            for product in basket_items:
                product_id = product.get("ingredient_id")
                product_name = str(
                    product.get("name")
                    or product.get("ingredient_name")
                    or ""
                ).strip().lower()

                if ingredient_id and product_id:
                    if ingredient_id == product_id:
                        return product
                elif name and name == product_name:
                    return product

            return None

        for item in coverage:
            name = item.get("ingredient_name")
            unit = item.get("unit")
            missing = item.get("purchase_required")
            purchase = matching_purchase(item)

            unresolved = (
                item.get("inventory_conversion_unresolved") is True
                or item.get("normalization_status") == "unresolved"
                or item.get("conversion_status") == "unresolved"
            )

            if unresolved:
                unresolved_conversions.append({
                    "ingredient_name": name,
                    "unit": unit,
                })
            elif (
                item.get("inventory_conversion_estimated") is True
                or item.get("conversion_status") == "estimated"
                or (purchase or {}).get("package_conversion_status")
                == "estimated"
            ):
                estimated_conversions.append({
                    "ingredient_name": name,
                    "unit": unit,
                })

            if missing is None:
                unresolved_conversions.append({
                    "ingredient_name": name,
                    "unit": unit,
                    "reason": "Unknown remaining requirement",
                })
                continue

            try:
                missing = float(missing)
            except (TypeError, ValueError):
                unresolved_conversions.append({
                    "ingredient_name": name,
                    "unit": unit,
                    "reason": "Invalid remaining requirement",
                })
                continue

            if missing <= 1e-6:
                continue

            if (
                purchase is not None
                and purchase.get("packages") is not None
                and float(purchase.get("packages") or 0) > 0
                and purchase.get("quantity_coverage_verified") is False
            ):
                unverified_package_coverage.append({
                    "ingredient_name": name,
                    "required_unit": unit,
                    "purchase_required": missing,
                    "package_quantity": purchase.get(
                        "package_quantity"
                    ),
                    "package_unit": purchase.get(
                        "package_unit"
                    ),
                    "package_conversion_status": purchase.get(
                        "package_conversion_status"
                    ),
                })
            else:
                confirmed_shortages.append({
                    "ingredient_name": name,
                    "purchase_required": missing,
                    "unit": unit,
                })

        if (
            confirmed_shortages
            or unverified_package_coverage
            or unresolved_conversions
            or unresolved_quantity_requirements
        ):
            plan_state.execution_trace.extend(
                qualitative_requirements
            )

            plan_state.execution_trace.append({
                "event": "inventory_reconciliation_incomplete",
                "reason": (
                    "Some ingredient requirements remain "
                    "uncovered or cannot be verified."
                ),
                "confirmed_shortage_count": len(
                    confirmed_shortages
                ),
                "confirmed_shortages": confirmed_shortages,
                "unverified_package_count": len(
                    unverified_package_coverage
                ),
                "unverified_package_coverage": (
                    unverified_package_coverage
                ),
                "unresolved_count": len(
                    unresolved_conversions
                ) + len(qualitative_requirements),
                "unresolved_conversions": unresolved_conversions,
                # Missing quantity/unit in the recipe itself; separate
                # from unresolved conversions and package coverage.
                "unresolved_quantity_count": len(
                    unresolved_quantity_requirements
                ),
                "unresolved_quantity_requirements": (
                    unresolved_quantity_requirements
                ),
                "estimated_conversion_count": len(
                    estimated_conversions
                ),
                "estimated_conversions": estimated_conversions,
            })

            # Do not commit unverified inventory.
            # True means no fatal reconciliation exception,
            # not that inventory is fully reconciled.
            return True

        

        errors = []
        for recipe in recipe_requirements:
            for ingredient in recipe["ingredients"]:
                try:
                    inventory = consume_inventory(inventory, [ingredient])
                except ValueError as exc:
                    errors.append({
                        "recipe_id": recipe["recipe_id"],
                        "ingredient_name": ingredient.get("ingredient_name") or ingredient.get("name"),
                        "reason": str(exc),
                    })
        if errors:
            plan_state.execution_trace.append({
                "event": "inventory_reconciliation_failed",
                "reason": "Ingredient conversions or inventory data could not be reconciled",
                "error_count": len(errors),
                "details": errors,
            })
            return False

        plan_state.current_inventory = inventory
        plan_state.execution_trace.extend(qualitative_requirements)
        if qualitative_requirements:
            plan_state.execution_trace.append({
                "event": "inventory_reconciliation_incomplete",
                "reason": "Qualitative ingredient quantities remain unresolved",
                "unresolved_count": len(qualitative_requirements),
            })
        else:
            plan_state.execution_trace.append({
                "event": "inventory_reconciled",
                "selected_meals": len(plan_state.selected_meals),
                "estimated_conversion_count": len(
                    estimated_conversions
                ),
                "estimated_conversions": estimated_conversions,
            })
        return True

    def _update_inventory(
        self,
        plan_state: PlanState,
        decision: dict,
    ) -> None:
        ingredient_data = decision.get(
            "ingredient",
            {},
        )
        grocery_data = decision.get(
            "grocery",
            {},
        )
        required_ingredients = ingredient_data.get(
            "required_ingredients",
            [],
        )
        grocery_items = grocery_data.get(
            "items",
            [],
        )
        inventory = plan_state.current_inventory
        # ========================================================
        # 1. ADD PURCHASED PACKAGES
        # ========================================================
        for item in grocery_items:
            package_quantity = item.get("package_quantity")
            package_unit = item.get("package_unit")
            packages_needed = item.get("packages_needed")
            # Some outputs may use "packages".
            if packages_needed is None:
                packages_needed = item.get("packages")
            if (
                package_quantity is None
                or package_unit is None
                or packages_needed is None
            ):
                continue
            purchase = {
                "ingredient_name": (
                    item.get("ingredient")
                    or item.get("ingredient_name")
                    or item.get("name")
                ),
                "package_quantity": package_quantity,
                "package_unit": package_unit,
                "packages_needed": packages_needed,
            }
            try:
                inventory = add_purchase(
                    inventory,
                    purchase,
                )
            except ValueError as exc:
                plan_state.execution_trace.append(
                    {
                        "event": "inventory_purchase_warning",
                        "reason": str(exc),
                    }
                )
        # ========================================================
        # 2. CONSUME RECIPE INGREDIENTS
        # ========================================================
        try:
            inventory = consume_inventory(
                inventory,
                required_ingredients,
            )
        except ValueError as exc:
            # Do NOT crash the whole planner.
            #
            # Keep trace so this can be investigated.
            plan_state.execution_trace.append(
                {
                    "event": "inventory_consumption_warning",
                    "recipe_id": decision.get("recipe_id"),
                    "reason": str(exc),
                }
            )
        plan_state.current_inventory = inventory
    @staticmethod
    def _inventory_to_pantry(
        inventory: dict,
    ) -> list[dict]:
        pantry = []
        for name, item in (inventory or {}).items():
            pantry.append(
                {
                    "ingredient_name": name,
                    "quantity": item.get("quantity"),
                    "unit": item.get("unit"),
                }
            )
        return pantry
    def _build_final_grocery_basket(
        self,
        plan_state: PlanState,
    ) -> dict:
        recipe_requirements = []
        product_catalog = []
        # ========================================================
        # COLLECT DATA FROM SELECTED MEALS
        # ========================================================
        for selected in plan_state.selected_meals:
            if selected.get("meal_source") == "prepared_leftover":
                continue
            recipe_id = selected.get("recipe_id")
            decision = selected.get(
                "decision",
                {},
            )
            # ----------------------------------------------------
            # Required ingredients
            # ----------------------------------------------------
            ingredient_data = decision.get(
                "ingredient",
                {},
            )
            required = ingredient_data.get(
                "required_ingredients",
                [],
            )
            recipe_requirements.append(
                {
                    "recipe_id": recipe_id,
                    # Same recipe in two slots stays traceable per meal.
                    "slot_id": (selected.get("slot") or {}).get("slot_id"),
                    "ingredients": required,
                }
            )
            # ----------------------------------------------------
            # Reuse product information already obtained
            # during candidate evaluation.
            #
            # This avoids unnecessary extra web calls.
            # ----------------------------------------------------
            grocery_data = decision.get(
                "grocery",
                {},
            )
            for item in grocery_data.get(
                "items",
                [],
            ):
                ingredient_name = (
                    item.get("ingredient")
                    or item.get("ingredient_name")
                    or item.get("name")
                )
                if not ingredient_name:
                    continue
                # Preserve original Grocery Agent evidence.
                # Do not turn estimated prices into verified prices.
                price = item.get("price")
                if price is None:
                    price = item.get("price_per_package")
                product_catalog.append(
                    {
                        **item,
                        "ingredient_id": item.get("ingredient_id"),
                        "ingredient_name": ingredient_name,
                        "package_quantity": item.get("package_quantity"),
                        "package_unit": item.get("package_unit"),
                        "price": price,
                    }
                )
        # ========================================================
        # INITIAL PANTRY
        #
        # Important:
        # Member 4's final aggregation must subtract the
        # ORIGINAL pantry, not the already-consumed final inventory.
        # ========================================================
        initial_inventory_list = self._inventory_to_pantry(plan_state.initial_inventory)
        only_prepared_leftovers = (
            bool(plan_state.selected_meals)
            and all(
                meal.get("meal_source") == "prepared_leftover"
                for meal in plan_state.selected_meals
            )
        )
        if only_prepared_leftovers:
            return {
                "items": [],
                "known_cost": 0.0,
                "projected_cost": 0.0,
                "projected_cost_complete": True,
                "planning_cost": 0.0,
                "planning_cost_complete": True,
                "all_items_priced": True,
                "all_items_have_usable_cost": True,
                "unpriced_items": [],
                "projection_missing": [],
                "aggregated_requirements": [],
                "purchase_requirements": [],
                "qualitative_requirements": [],
                "unresolved_requirements": [],
                "warnings": [],
                "status": "complete",
            }
        # ========================================================
        # BUILD FINAL PLAN BASKET
        # ========================================================
        # If fake/unit-test candidates do not contain real
        # ingredient data, preserve the old fallback behaviour.
        if not recipe_requirements or not any(
            item["ingredients"] for item in recipe_requirements
        ):
            has_selected_meals = len(plan_state.selected_meals) > 0
            return {
                "items": [],
                "known_cost": round(
                    plan_state.estimated_spent,
                    2,
                ),
                # An empty plan has nothing to price, so it must
                # not be reported as a successfully priced plan.
                "all_items_priced": has_selected_meals,
                "unpriced_items": [],
                "aggregated_requirements": [],
                "status": ("complete" if has_selected_meals else "empty_plan"),
            }
        basket = build_plan_grocery_basket(
            recipe_requirements=recipe_requirements,
            inventory=initial_inventory_list,
            product_catalog=product_catalog,
        )
        discovered = self._discover_missing_products(basket)
        if not discovered:
            return basket
        basket = build_plan_grocery_basket(
            recipe_requirements=recipe_requirements,
            inventory=initial_inventory_list,
            product_catalog=product_catalog + discovered,
        )
        basket["plan_level_products"] = sorted(
            {item["ingredient_name"] for item in discovered}
        )
        return basket

    def _discover_missing_products(self, basket: dict) -> list[dict]:
        """Find products for combined-plan shortages no candidate priced.

        Each candidate's grocery lookup only covers that recipe's own
        shortage. When the pantry covers an ingredient for each recipe
        alone but not for the combined plan (e.g. 2 garlic cloves in the
        pantry, three recipes needing 1-2 cloves each), no selected
        decision carries a product and the line would stay unpriced.
        Products are cached per planner; quantities are still sized by
        the final basket from the plan-level shortage.
        """
        grocery_agent = getattr(self.manager, "grocery_agent", None)
        if grocery_agent is None:
            return []
        needed = [
            item for item in basket.get("items", [])
            if item.get("pricing_status") == "unpriced"
            and item.get("package_quantity") is None
            and item.get("purchase_basis") is None
            and item.get("required_quantity")
        ]
        if not needed:
            return []
        to_request = [
            item for item in needed
            if item["name"] not in self._plan_product_cache
        ]
        if to_request:
            try:
                result = grocery_agent.run(
                    recipe_id="PLAN_SHORTAGE",
                    missing_ingredients=[
                        {
                            "ingredient_id": item.get("ingredient_id"),
                            "ingredient_name": item["name"],
                            "quantity": item["required_quantity"],
                            "unit": item.get("required_unit"),
                        }
                        for item in to_request
                    ],
                )
            except Exception:
                result = {}
            found = ((result or {}).get("data") or {}).get("items") or []
            for item in to_request:
                self._plan_product_cache[item["name"]] = []
            for product in found:
                name = product.get("ingredient") or product.get("ingredient_name")
                if not name or name not in self._plan_product_cache:
                    continue
                price = product.get("price")
                if price is None:
                    price = product.get("price_per_package")
                self._plan_product_cache[name].append({
                    **product,
                    "ingredient_id": product.get("ingredient_id"),
                    "ingredient_name": name,
                    "price": price,
                })
        return [
            product
            for item in needed
            for product in self._plan_product_cache.get(item["name"], [])
        ]
    @staticmethod
    def _extract_cost(decision: dict) -> float:
        """
        Extract the total cost of ONE candidate recipe.
        Returns:
            Complete projected cost, or complete verified cost.
        Raises:
            ValueError when no complete cost is available.
        Important:
            This is a standalone candidate cost.
            It is NOT the incremental cost of adding a
            recipe to the combined meal-plan basket.
        """
        grocery = decision.get("grocery")
        if not isinstance(grocery, dict):
            raise ValueError("Candidate has no valid grocery result")
        # Prefer verified cost when every item is priced.
        if grocery.get("all_items_priced") is True:
            known = grocery.get("known_cost")
            if known is not None:
                cost = float(known)
                if cost >= 0:
                    return cost
        # Otherwise use a complete provisional projection.
        if grocery.get("projected_cost_complete") is True:
            projected = grocery.get("projected_cost")
            if projected is not None:
                cost = float(projected)
                if cost >= 0:
                    return cost
        # Never silently interpret missing prices as zero.
        raise ValueError("Candidate grocery cost is incomplete")
    @staticmethod
    def _extract_reason(
        decision: dict,
    ) -> Any:
        if decision.get("status") == "failed":
            return {
                "stage": decision.get("stage"),
                "reason": decision.get("reason"),
            }
        reasoning = decision.get(
            "reasoning",
            {},
        )
        status = reasoning.get("status")
        if status == "rejected":
            return reasoning.get(
                "failed_constraints",
                [],
            )
        if status == "uncertain":
            return reasoning.get(
                "unknown_constraints",
                [],
            )
        return "unspecified"
