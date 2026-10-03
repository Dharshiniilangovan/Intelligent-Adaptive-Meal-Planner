"""
Budget constraint logic for recipe grocery purchases.

A recipe can have three budget states:

pass
    Complete purchase cost is known and fits the budget.

hard_fail
    Known purchase cost already exceeds the remaining budget.

uncertain
    Some grocery costs are unknown, so affordability cannot
    safely be confirmed.
"""


BUDGET_PASS = "pass"
BUDGET_HARD_FAIL = "hard_fail"
BUDGET_UNCERTAIN = "uncertain"


def check_budget(
    purchase_cost,
    remaining_budget,
    has_unknown_cost=False
):
    """
    Check whether a grocery purchase fits the user's
    remaining budget.

    Parameters
    ----------
    purchase_cost : float
        Known grocery purchase subtotal.

    remaining_budget : float
        User's remaining available budget.

    has_unknown_cost : bool
        True when one or more required grocery items do not
        have a reliable final purchase cost.

    Returns
    -------
    dict
        Structured budget decision.
    """

    if purchase_cost is None:
        purchase_cost = 0.0
        has_unknown_cost = True

    purchase_cost = float(purchase_cost)
    remaining_budget = float(remaining_budget)

    if purchase_cost < 0:
        raise ValueError("purchase_cost cannot be negative")

    if remaining_budget < 0:
        raise ValueError("remaining_budget cannot be negative")

    # ---------------------------------------------------------
    # HARD FAIL
    #
    # If the known subtotal already exceeds the budget,
    # unknown items cannot make the recipe affordable.
    # ---------------------------------------------------------
    if purchase_cost > remaining_budget:
        return {
            "budget_status": BUDGET_HARD_FAIL,
            "known_purchase_cost": round(purchase_cost, 2),
            "remaining_budget": round(remaining_budget, 2),
            "budget_after_purchase": None,
            "reason": "Known purchase cost exceeds remaining budget.",
        }

    # ---------------------------------------------------------
    # UNCERTAIN
    #
    # Known cost currently fits, but at least one required
    # item's final cost is unknown.
    # ---------------------------------------------------------
    if has_unknown_cost:
        return {
            "budget_status": BUDGET_UNCERTAIN,
            "known_purchase_cost": round(purchase_cost, 2),
            "remaining_budget": round(remaining_budget, 2),
            "budget_after_purchase": None,
            "reason": "One or more required grocery costs are unknown.",
        }

    # ---------------------------------------------------------
    # PASS
    #
    # All costs are known and total cost fits the budget.
    # ---------------------------------------------------------
    return {
        "budget_status": BUDGET_PASS,
        "known_purchase_cost": round(purchase_cost, 2),
        "remaining_budget": round(remaining_budget, 2),
        "budget_after_purchase": round(
            remaining_budget - purchase_cost,
            2
        ),
        "reason": "Purchase cost is within the remaining budget.",
    }


def check_basket_budget(basket, remaining_budget):
    """
    Convenience function connecting grocery basket_summary()
    directly to budget reasoning.
    """

    return check_budget(
        purchase_cost=basket.get(
            "known_subtotal",
            basket.get("estimated_total", 0.0)
        ),
        remaining_budget=remaining_budget,
        has_unknown_cost=not basket.get(
            "cost_complete",
            False
        ),
    )