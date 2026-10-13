
"""Adapter between canonical GC1 User State and MultiMealPlanner."""

import math
from datetime import date


def build_user_state(confirmed: dict) -> dict:
    """Convert canonical User State into Planner-compatible input."""

    state = dict(confirmed)

    budget = float(state["budget"])

    state["budget_remaining"] = budget
    state["remaining_budget"] = budget

    state["budget_cap"] = (
        budget + 5.0
        if state.get("budget_flexible")
        else None
    )

    for field in (
        "dietary_restrictions",
        "allergies",
        "preferred_meal_types",
        "preferred_cuisines",
        "preferred_ingredients",
        "disliked_ingredients",
    ):
        state[field] = [
            str(value).strip().lower()
            for value in (state.get(field) or [])
            if str(value).strip()
        ]

    availability = (
        state.get("ingredient_availability") or {}
    )

    pantry = []

    for name, value in availability.items():

        if isinstance(value, dict):
            quantity_value = value.get("quantity")
            unit = str(value.get("unit") or "").strip()

        elif isinstance(value, str):
            parts = value.strip().split(maxsplit=1)

            if len(parts) != 2:
                continue

            quantity_value, unit = parts

        else:
            continue

        try:
            quantity = float(quantity_value)
        except (TypeError, ValueError):
            continue

        if (
            not math.isfinite(quantity)
            or quantity <= 0
            or not unit
        ):
            continue

        pantry.append({
            "ingredient_name": name,
            "quantity": quantity,
            "unit": unit,
        })

    state["pantry"] = pantry

    return state


def get_planner():
    from scripts.run_day5_e2e import build_system
    return build_system()


def generate(confirmed: dict):
    """Generate meals using the existing GC1 Planner.

    The background worker passes a planning payload containing
    canonical User State plus start_date and days.

    The additional planning fields are not saved in the
    canonical User State JSON.
    """

    start = confirmed.get("start_date")
    days = confirmed.get("days")

    if not start:
        raise ValueError("Planning start date is missing.")

    if days is None:
        raise ValueError("Planning duration is missing.")

    planning_date = date.fromisoformat(str(start))
    planning_days = int(days)

    if not 1 <= planning_days <= 30:
        raise ValueError("Planning days must be between 1 and 30.")

    state = build_user_state(confirmed)

    planner = get_planner()

    result = planner.plan_meals(
        user_state=state,
        start_date=planning_date,
        days=planning_days,
        meal_types=list(state["preferred_meal_types"]),
        nutrition_targets=state.get("nutrition_targets"),
    )

    if planner.last_plan_state is None:
        raise RuntimeError(
            "Planner did not retain a PlanState."
        )

    return (
        result,
        planner.last_plan_state,
        state,
        planner,
    )


def skip_meal(
    planner,
    state,
    plan_state,
    slot_id,
    completed_slot_ids,
):
    result = planner.skip_and_replan(
        user_state=state,
        plan_state=plan_state,
        slot_id=slot_id,
        completed_slot_ids=completed_slot_ids,
        nutrition_targets=state.get("nutrition_targets"),
    )

    if planner.last_plan_state is None:
        raise RuntimeError(
            "Replanning did not retain a PlanState."
        )

    return result, planner.last_plan_state
