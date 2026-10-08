from src.planning.plan_state import PlanState


def validate_plan(
    plan_state: PlanState,
    all_items_priced: bool = True,
    final_grocery_cost: float | None = None,
) -> dict:

    total_slots = len(plan_state.slots)

    selected_slots = len(
        plan_state.selected_meals
    )

    issues = []

    # --------------------------------
    # Check all slots filled
    # --------------------------------

    if selected_slots < total_slots:
        issues.append(
            f"Only {selected_slots}/{total_slots} "
            "meal slots were filled."
        )

    # --------------------------------
    # Final aggregated budget
    # --------------------------------

    if final_grocery_cost is not None:

        if final_grocery_cost > plan_state.initial_budget:

            issues.append(
                "Final aggregated grocery cost "
                "exceeds user budget."
            )

            return {
                "status": "infeasible",
                "issues": issues,
            }

    # --------------------------------
    # Pricing uncertainty
    # --------------------------------

    if not all_items_priced:

        return {
            "status": "uncertain",
            "issues": issues + [
                "Not all grocery items could be priced."
            ],
        }

    # --------------------------------
    # Missing meal slots
    # --------------------------------

    if selected_slots == 0:

        return {
            "status": "infeasible",
            "issues": issues,
        }

    if selected_slots < total_slots:

        return {
            "status": "partial",
            "issues": issues,
        }

    # --------------------------------
    # Complete valid plan
    # --------------------------------

    return {
        "status": "feasible",
        "issues": [],
    }