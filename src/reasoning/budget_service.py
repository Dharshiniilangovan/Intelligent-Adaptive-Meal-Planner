
"""
src/budget/budget_service.py

Budget constraint logic for grocery purchase costs.

Supports:
- Direct purchase-cost checks
- Existing basket_summary format
- GroceryService result format
- Provisional Tavily and Ollama grocery prices
- Complete projected grocery budget calculations

Tavily and Ollama prices are equally usable for planning.
Verified and estimated price provenance remains separate.
"""

import math


def check_budget(
    purchase_cost: float,
    remaining_budget: float,
    has_unknown_cost: bool = False,
) -> dict:
    """
    Check whether a known grocery purchase cost fits the budget.

    Returns:
        pass:
            Cost fits and no costs are unknown.

        hard_fail:
            Cost exceeds the remaining budget.

        uncertain:
            Cost fits, but some costs are unknown.
    """

    purchase_cost = float(purchase_cost)
    remaining_budget = float(remaining_budget)

    if not math.isfinite(purchase_cost):
        raise ValueError("purchase_cost must be finite")

    if not math.isfinite(remaining_budget):
        raise ValueError("remaining_budget must be finite")

    if purchase_cost < 0:
        raise ValueError(
            "purchase_cost cannot be negative"
        )

    if remaining_budget < 0:
        raise ValueError(
            "remaining_budget cannot be negative"
        )

    if purchase_cost > remaining_budget:
        return {
            "budget_status": "hard_fail",
            "known_purchase_cost": round(
                purchase_cost, 2
            ),
            "remaining_budget": round(
                remaining_budget, 2
            ),
            "budget_after_purchase": None,
            "reason": (
                "Known purchase cost exceeds "
                "remaining budget."
            ),
        }

    if has_unknown_cost:
        return {
            "budget_status": "uncertain",
            "known_purchase_cost": round(
                purchase_cost, 2
            ),
            "remaining_budget": round(
                remaining_budget, 2
            ),
            "budget_after_purchase": None,
            "reason": (
                "One or more required grocery "
                "costs are unknown."
            ),
        }

    budget_after_purchase = round(
        remaining_budget - purchase_cost, 2
    )

    return {
        "budget_status": "pass",
        "known_purchase_cost": round(
            purchase_cost, 2
        ),
        "remaining_budget": round(
            remaining_budget, 2
        ),
        "budget_after_purchase": budget_after_purchase,
        "reason": (
            "Purchase cost is within the "
            "remaining budget."
        ),
    }


def check_basket_budget(
    basket: dict,
    remaining_budget: float,
) -> dict:
    """
    Check the existing basket_summary output.

    Expected format:
        {
            "estimated_total": 12.0,
            "known_subtotal": 12.0,
            "unknown_cost_items": [],
            "cost_complete": True
        }

    Preserves backward compatibility.
    """

    if not isinstance(basket, dict):
        raise TypeError(
            "basket must be a dictionary"
        )

    purchase_cost = basket.get("known_subtotal")

    if purchase_cost is None:
        purchase_cost = basket.get(
            "estimated_total", 0
        )

    unknown_items = basket.get(
        "unknown_cost_items", []
    )

    cost_complete = basket.get(
        "cost_complete",
        len(unknown_items) == 0,
    )

    has_unknown_cost = (
        not cost_complete
        or bool(unknown_items)
    )

    return check_budget(
        purchase_cost=purchase_cost,
        remaining_budget=remaining_budget,
        has_unknown_cost=has_unknown_cost,
    )


def check_grocery_budget(
    grocery_results: dict,
    remaining_budget: float,
) -> dict:
    """
    Check GroceryService results against the budget.

    Expected format:
        {
            "priced_products": [...],
            "incomplete_products": [...],
            "missing_products": [...]
        }

    Preserves the existing strict GroceryService
    result contract.
    """

    if not isinstance(grocery_results, dict):
        raise TypeError(
            "grocery_results must be a dictionary"
        )

    priced_products = grocery_results.get(
        "priced_products", []
    )

    incomplete_products = grocery_results.get(
        "incomplete_products", []
    )

    missing_products = grocery_results.get(
        "missing_products", []
    )

    known_purchase_cost = round(
        sum(
            float(item["total_cost"])
            for item in priced_products
            if item.get("total_cost") is not None
        ),
        2,
    )

    unknown_items = []

    for item in incomplete_products:
        unknown_items.append(
            item.get(
                "ingredient",
                "unknown ingredient",
            )
        )

    for item in missing_products:
        unknown_items.append(
            item.get(
                "ingredient",
                "unknown ingredient",
            )
        )

    result = check_budget(
        purchase_cost=known_purchase_cost,
        remaining_budget=remaining_budget,
        has_unknown_cost=bool(unknown_items),
    )

    result["items_priced"] = len(
        priced_products
    )

    result["unknown_items"] = unknown_items

    return result


def check_provisional_grocery_budget(
    projected_cost,
    projected_cost_complete,
    remaining_budget,
    safety_margin=0.0,
):
    """
    Evaluate a complete projected grocery purchase cost.

    Both Tavily and Ollama prices are accepted equally
    for budget planning.

    A projected cost can pass the budget check even
    when individual prices are estimates.

    Missing or incomplete costs are not treated as zero.

    The result remains provisional because the prices
    may not all be independently verified.
    """

    if remaining_budget is None:
        return {
            "budget_status": "not_checked",
            "provisional": True,
            "reason": "No remaining budget provided.",
            "projected_cost": projected_cost,
            "budget_after_purchase": None,
        }

    try:
        budget = float(remaining_budget)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(
            "remaining_budget must be numeric"
        )

    if not math.isfinite(budget) or budget < 0:
        raise ValueError(
            "remaining_budget must be finite and nonnegative"
        )

    if (
        not projected_cost_complete
        or projected_cost is None
    ):
        return {
            "budget_status": "uncertain",
            "provisional": True,
            "reason": (
                "Projected grocery costs are incomplete."
            ),
            "projected_cost": projected_cost,
            "budget_after_purchase": None,
        }

    try:
        cost = float(projected_cost)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(
            "projected_cost must be numeric"
        )

    if not math.isfinite(cost) or cost < 0:
        raise ValueError(
            "projected_cost must be finite and nonnegative"
        )

    try:
        safety_margin = float(safety_margin)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(
            "safety_margin must be numeric"
        )

    if (
        not math.isfinite(safety_margin)
        or not 0 <= safety_margin < 1
    ):
        raise ValueError(
            "safety_margin must be between 0 and 1"
        )

    remaining = round(
        budget - cost, 2
    )

    allowed_cost = budget * (
        1 - safety_margin
    )

    if cost <= allowed_cost:
        status = "pass"
        reason = (
            "Projected grocery cost fits within the "
            "budget including the provisional safety margin."
        )

    elif cost > budget:
        status = "hard_fail"
        reason = (
            "Projected grocery cost exceeds the budget."
        )

    else:
        status = "uncertain"
        reason = (
            "Projected grocery cost fits the nominal budget "
            "but exceeds the provisional safety-margin limit."
        )

    return {
        "budget_status": status,
        "provisional": True,
        "reason": reason,
        "projected_cost": round(cost, 2),
        "budget_after_purchase": remaining,
        "safety_margin": safety_margin,
    }


def print_budget_result(
    result: dict,
) -> None:
    """
    Print a readable budget result.

    Preserves the existing output structure.
    """

    print()
    print("=" * 60)
    print("BUDGET CHECK")
    print("=" * 60)
    print()

    known_cost = result[
        "known_purchase_cost"
    ]

    remaining_budget = result[
        "remaining_budget"
    ]

    print(
        f"Grocery purchase: "
        f"S${known_cost:.2f}"
    )

    print(
        f"Remaining budget: "
        f"S${remaining_budget:.2f}"
    )

    budget_after = result.get(
        "budget_after_purchase"
    )

    if budget_after is not None:
        print(
            f"Budget after purchase: "
            f"S${budget_after:.2f}"
        )
    else:
        print(
            "Budget after purchase: NA"
        )

    print()

    status = result[
        "budget_status"
    ]

    if status == "pass":
        print("Status: PASS")

    elif status == "hard_fail":
        print("Status: HARD FAIL")

    else:
        print("Status: UNCERTAIN")

    unknown_items = result.get(
        "unknown_items", []
    )

    if unknown_items:
        print()
        print(
            "Unknown costs: "
            + ", ".join(unknown_items)
        )

    print()
    print(result["reason"])


def get_usable_grocery_cost(
    grocery: dict,
) -> float | None:
    """
    Return the complete grocery cost usable for planning.

    Tavily and Ollama prices are treated equally
    when calculating the projected budget.

    Priority:
        1. Complete projected grocery cost
        2. Complete verified grocery cost

    Never treat missing prices as zero.
    """

    if not isinstance(grocery, dict):
        return None

    if grocery.get(
        "projected_cost_complete"
    ) is True:

        cost = grocery.get(
            "projected_cost"
        )

        if cost is not None:
            try:
                cost = float(cost)
            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                return None

            if (
                math.isfinite(cost)
                and cost >= 0
            ):
                return round(cost, 2)

            return None

    if grocery.get(
        "all_items_priced"
    ) is True:

        cost = grocery.get(
            "known_cost"
        )

        if cost is not None:
            try:
                cost = float(cost)
            except (
                TypeError,
                ValueError,
                OverflowError,
            ):
                return None

            if (
                math.isfinite(cost)
                and cost >= 0
            ):
                return round(cost, 2)

    return None
