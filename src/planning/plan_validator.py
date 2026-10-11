from src.planning.plan_state import PlanState


from src.planning.plan_state import PlanState


def validate_plan(
    plan_state: PlanState,
    all_items_priced: bool = True,
    final_grocery_cost: float | None = None,
) -> dict:

    skipped_ids = {item["slot_id"] for item in plan_state.skipped_slots}

    active_slots = [
        slot for slot in plan_state.slots if slot.slot_id not in skipped_ids
    ]

    total_slots = len(active_slots)

    selected_slots = sum(
        1
        for meal in plan_state.selected_meals
        if meal["slot"]["slot_id"] not in skipped_ids
    )

    issues = []

    if selected_slots < total_slots:
        issues.append(f"Only {selected_slots}/{total_slots} meal slots were filled.")

    # Known budget violation always makes the plan infeasible.
    if (
        final_grocery_cost is not None
        and final_grocery_cost > plan_state.initial_budget
    ):
        issues.append("Final grocery cost exceeds budget.")
        return {"status": "infeasible", "issues": issues}

    # No selected meals.
    if selected_slots == 0:
        return {"status": "infeasible", "issues": issues}

    # Some slots could not be filled.
    if selected_slots < total_slots:
        if not all_items_priced:
            issues.append("Some grocery prices are unavailable.")

        return {"status": "partial", "issues": issues}

    # All slots filled, but final cost is not fully verified.
    if not all_items_priced or final_grocery_cost is None:
        issues.append("Complete grocery cost could not be verified.")
        return {"status": "uncertain", "issues": issues}

    return {"status": "feasible", "issues": []}
