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
# ============================================================
# MEMBER 3
# Inventory + Nutrition
# ============================================================
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
# ============================================================
# MEMBER 4
# Plan Grocery Aggregation
# ============================================================
from src.agents.grocery_agent import (
    build_plan_grocery_basket,
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
        slots = generate_meal_slots(
            start_date=start_date,
            days=days,
            meal_types=meal_types,
            schedule=schedule,
        )
        # ========================================================
        # 2. INITIAL BUDGET
        # ========================================================
        initial_budget = self._get_budget(
            user_state
        )
        # ========================================================
        # 3. INITIAL INVENTORY
        # Member 3
        # ========================================================
        raw_pantry = (
            user_state.get("pantry")
            or user_state.get(
                "ingredient_availability"
            )
            or {}
        )
        initial_inventory = normalize_inventory(
            raw_pantry
        )
        # ========================================================
        # 4. CREATE PLAN STATE
        # ========================================================
        plan_state = PlanState(
            slots=slots,
            initial_budget=initial_budget,
            initial_inventory=initial_inventory,
            current_inventory=dict(
                initial_inventory
            ),
        )
        # ========================================================
        # 5. BUILD PLAN SLOT BY SLOT
        # ========================================================
        for slot in slots:
            slot_result = (
                self._plan_single_slot(
                    user_state=user_state,
                    slot=slot,
                    plan_state=plan_state,
                )
            )
            if not slot_result["selected"]:
                plan_state.mark_slot_infeasible(
                    slot
                )
                continue
            # ----------------------------------------------------
            # Candidate successfully selected
            # ----------------------------------------------------
            decision = slot_result[
                "decision"
            ]
            # ----------------------------------------------------
            # MEMBER 3
            # Update nutrition
            # ----------------------------------------------------
            self._update_nutrition(
                plan_state=plan_state,
                slot=slot,
                decision=decision,
            )
            # ----------------------------------------------------
            # MEMBER 3
            # Update evolving inventory
            # ----------------------------------------------------
            self._update_inventory(
                plan_state=plan_state,
                decision=decision,
            )
        # ========================================================
        # 6. MEMBER 4
        # BUILD FINAL AGGREGATED GROCERY BASKET
        # ========================================================
        final_grocery_basket = (
            self._build_final_grocery_basket(
                plan_state
            )
        )
        plan_state.final_grocery_basket = (
            final_grocery_basket
        )
        # ========================================================
        # 7. NUTRITION SUMMARY
        # ========================================================
        nutrition_summary = (
            summarize_nutrition(
                plan_state.nutrition_state
            )
        )
        nutrition_deviation = None
        if nutrition_targets:
            nutrition_deviation = (
                calculate_nutrition_deviation(
                    plan_state.nutrition_state,
                    nutrition_targets,
                )
            )
        # ========================================================
        # 8. FINAL PLAN VALIDATION
        # ========================================================
        final_cost = (
            final_grocery_basket.get(
                "known_cost"
            )
        )
        all_items_priced = (
            final_grocery_basket.get(
                "all_items_priced",
                False,
            )
        )
        validation = validate_plan(
            plan_state=plan_state,
            all_items_priced=
                all_items_priced,
            final_grocery_cost=
                final_cost,
        )
        plan_state.status = (
            validation["status"]
        )
        # ========================================================
        # 9. RETURN COMPLETE PLAN
        # ========================================================
        return {
            "plan":
                plan_state.to_dict(),
            "validation":
                validation,
            "grocery_basket":
                final_grocery_basket,
            "nutrition_summary":
                nutrition_summary,
            "nutrition_deviation":
                nutrition_deviation,
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
        meal_slot = {
            "date": slot.date.isoformat(),
            "meal_type": slot.meal_type,
            "max_cooking_time":
                slot.max_cooking_time,
        }
        response = self.manager.recipe_agent.run(
            user_state=user_state,
            meal_slot=meal_slot,
            selected_recipe_ids=list(
                plan_state.used_recipe_ids
            ),
            recent_cuisines=[],
            max_candidates=
                self.max_candidates_per_slot,
        )
        if not response:
            return []
        # ========================================================
        # Member 2's current RecipeAgent returns:
        #
        # {
        #     "slot": {...},
        #     "candidate_recipe_ids": [...]
        # }
        # ========================================================
        if isinstance(response, dict):
            # Current Member-2 format
            candidates = response.get(
                "candidate_recipe_ids"
            )
            # Backward-compatible fallback for AgentResult format
            if candidates is None:
                data = response.get(
                    "data",
                    {}
                )
                candidates = data.get(
                    "candidate_recipe_ids",
                    []
                )
        else:
            candidates = response
        # ========================================================
        # Normalize IDs
        # ========================================================
        result = []
        for candidate in candidates or []:
            if isinstance(candidate, str):
                recipe_id = (
                    candidate
                    .strip()
                    .upper()
                )
            elif isinstance(candidate, dict):
                recipe_id = (
                    candidate.get("recipe_id")
                    or candidate.get("id")
                )
                if recipe_id:
                    recipe_id = (
                        str(recipe_id)
                        .strip()
                        .upper()
                    )
            else:
                continue
            if not recipe_id:
                continue
            # Extra safety:
            # RecipeAgent already excludes selected recipes.
            if (
                recipe_id
                in plan_state.used_recipe_ids
            ):
                continue
            if recipe_id not in result:
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
        planning_user_state = dict(
            user_state
        )
        # Use CURRENT remaining budget.
        planning_user_state[
            "remaining_budget"
        ] = plan_state.remaining_budget
        # Use CURRENT inventory.
        planning_user_state[
            "pantry"
        ] = self._inventory_to_pantry(
            plan_state.current_inventory
        )
        meal_context = {
            "date":
                slot.date.isoformat(),
            "meal_type":
                slot.meal_type,
            "max_cooking_time":
                slot.max_cooking_time,
        }
        return (
            self.manager.evaluate_candidate(
                recipe_id=recipe_id,
                user_state=
                    planning_user_state,
                meal_context=
                    meal_context,
            )
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
        plan_state.nutrition_state = (
            aggregate_nutrition(
                nutrition_state=
                    plan_state.nutrition_state,
                date=
                    slot.date.isoformat(),
                nutrition=
                    recipe,
                servings=1.0,
            )
        )
        plan_state.execution_trace.append(
            {
                "event":
                    "nutrition_updated",
                "slot_id":
                    slot.slot_id,
                "recipe_id":
                    decision.get(
                        "recipe_id"
                    ),
            }
        )
    def _update_inventory(
    self,
    plan_state: PlanState,
    decision: dict,
) -> None:
        ingredient_data = (
            decision.get(
                "ingredient",
                {},
            )
        )
        grocery_data = (
            decision.get(
                "grocery",
                {},
            )
        )
        required_ingredients = (
            ingredient_data.get(
                "required_ingredients",
                [],
            )
        )
        grocery_items = (
            grocery_data.get(
                "items",
                [],
            )
        )
        inventory = (
            plan_state.current_inventory
        )
        # ========================================================
        # 1. ADD PURCHASED PACKAGES
        # ========================================================
        for item in grocery_items:
            package_quantity = (
                item.get(
                    "package_quantity"
                )
            )
            package_unit = (
                item.get(
                    "package_unit"
                )
            )
            packages_needed = (
                item.get(
                    "packages_needed"
                )
            )
            # Some outputs may use "packages".
            if packages_needed is None:
                packages_needed = (
                    item.get(
                        "packages"
                    )
                )
            if (
                package_quantity is None
                or package_unit is None
                or packages_needed is None
            ):
                continue
            purchase = {
                "ingredient_name":
                    (
                        item.get(
                            "ingredient"
                        )
                        or item.get(
                            "ingredient_name"
                        )
                        or item.get("name")
                    ),
                "package_quantity":
                    package_quantity,
                "package_unit":
                    package_unit,
                "packages_needed":
                    packages_needed,
            }
            try:
                inventory = add_purchase(
                    inventory,
                    purchase,
                )
            except ValueError as exc:
                plan_state.execution_trace.append(
                    {
                        "event":
                            "inventory_purchase_warning",
                        "reason":
                            str(exc),
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
                    "event":
                        "inventory_consumption_warning",
                    "recipe_id":
                        decision.get(
                            "recipe_id"
                        ),
                    "reason":
                        str(exc),
                }
            )
        plan_state.current_inventory = (
            inventory
        )
    @staticmethod
    def _inventory_to_pantry(
    inventory: dict,
) -> list[dict]:
        pantry = []
        for name, item in (
            inventory or {}
        ).items():
            pantry.append(
                {
                    "ingredient_name":
                        name,
                    "quantity":
                        item.get(
                            "quantity"
                        ),
                    "unit":
                        item.get(
                            "unit"
                        ),
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
        for selected in (
            plan_state.selected_meals
        ):
            recipe_id = selected.get(
                "recipe_id"
            )
            decision = selected.get(
                "decision",
                {},
            )
            # ----------------------------------------------------
            # Required ingredients
            # ----------------------------------------------------
            ingredient_data = (
                decision.get(
                    "ingredient",
                    {},
                )
            )
            required = (
                ingredient_data.get(
                    "required_ingredients",
                    [],
                )
            )
            recipe_requirements.append(
                {
                    "recipe_id":
                        recipe_id,
                    "ingredients":
                        required,
                }
            )
            # ----------------------------------------------------
            # Reuse product information already obtained
            # during candidate evaluation.
            #
            # This avoids unnecessary extra web calls.
            # ----------------------------------------------------
            grocery_data = (
                decision.get(
                    "grocery",
                    {},
                )
            )
            for item in grocery_data.get(
                "items",
                [],
            ):
                ingredient_name = (
                    item.get(
                        "ingredient"
                    )
                    or item.get(
                        "ingredient_name"
                    )
                    or item.get("name")
                )
                if not ingredient_name:
                    continue
                price = item.get(
                    "price_per_package"
                )
                product_catalog.append(
                    {
                        "ingredient_id":
                            item.get(
                                "ingredient_id"
                            ),
                        "ingredient_name":
                            ingredient_name,
                        "package_quantity":
                            item.get(
                                "package_quantity"
                            ),
                        "package_unit":
                            item.get(
                                "package_unit"
                            ),
                        "price":
                            price,
                    }
                )
        # ========================================================
        # INITIAL PANTRY
        #
        # Important:
        # Member 4's final aggregation must subtract the
        # ORIGINAL pantry, not the already-consumed final inventory.
        # ========================================================
        initial_inventory_list = (
            self._inventory_to_pantry(
                plan_state.initial_inventory
            )
        )
        # ========================================================
        # BUILD FINAL PLAN BASKET
        # ========================================================
        # If fake/unit-test candidates do not contain real
        # ingredient data, preserve the old fallback behaviour.
        if not recipe_requirements or not any(
            item["ingredients"]
            for item in recipe_requirements
        ):
            has_selected_meals = (
                len(plan_state.selected_meals) > 0
            )
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
                "status": (
                    "complete"
                    if has_selected_meals
                    else "empty_plan"
                ),
            }
        return build_plan_grocery_basket(
            recipe_requirements=
                recipe_requirements,
            inventory=
                initial_inventory_list,
            product_catalog=
                product_catalog,
        )
    @staticmethod
    def _extract_cost(decision: dict) -> float:
        grocery = decision.get("grocery") or {}
        budget = decision.get("budget_assessment") or {}

        # 1. Provisional pricing: use projected cost
        if budget.get("provisionally_accepted"):
            projected = grocery.get(
                "projected_cost",
                decision.get("projected_cost")
            )

            complete = grocery.get(
                "projected_cost_complete",
                decision.get("projected_cost_complete")
            )

            if complete is True and projected is not None:
                return float(projected)

            raise ValueError(
                "Provisional candidate has no complete projected cost"
            )

        # 2. Verified pricing: support both old and new formats
        known = grocery.get("known_cost")

        if known is None:
            known = decision.get("known_cost")

        if known is None:
            raise ValueError(
                "Verified candidate has no known cost"
            )

        return float(known)

    @staticmethod
    def _extract_reason(
    decision: dict,
) -> Any:
        if (
            decision.get("status")
            == "failed"
        ):
            return {
                "stage":
                    decision.get("stage"),
                "reason":
                    decision.get("reason"),
            }
        reasoning = decision.get(
            "reasoning",
            {},
        )
        status = reasoning.get(
            "status"
        )
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