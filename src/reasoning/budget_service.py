"""src/budget/budget_service.py

Budget constraint logic for grocery purchase costs.

Supports:
- direct purchase-cost checks
- existing basket_summary format
- new GroceryService result format
"""


def check_budget(
    purchase_cost: float,
    remaining_budget: float,
    has_unknown_cost: bool = False,
) -> dict:
    """
    Check whether a known grocery purchase cost fits the budget.

    Returns:
        pass:
            Known cost is within budget and no costs are unknown.

        hard_fail:
            Known cost already exceeds the remaining budget.

        uncertain:
            Known cost is within budget, but one or more costs
            are still unknown.
    """

    purchase_cost = float(purchase_cost)
    remaining_budget = float(remaining_budget)

    if purchase_cost < 0:
        raise ValueError(
            "purchase_cost cannot be negative"
        )

    if remaining_budget < 0:
        raise ValueError(
            "remaining_budget cannot be negative"
        )

    # Known cost already exceeds budget.
    # This is a hard fail even if other costs are unknown.
    if purchase_cost > remaining_budget:
        return {
            "budget_status": "hard_fail",
            "known_purchase_cost": round(
                purchase_cost,
                2,
            ),
            "remaining_budget": round(
                remaining_budget,
                2,
            ),
            "budget_after_purchase": None,
            "reason": (
                "Known purchase cost exceeds "
                "remaining budget."
            ),
        }

    # Known cost fits, but some prices are unknown.
    if has_unknown_cost:
        return {
            "budget_status": "uncertain",
            "known_purchase_cost": round(
                purchase_cost,
                2,
            ),
            "remaining_budget": round(
                remaining_budget,
                2,
            ),
            "budget_after_purchase": None,
            "reason": (
                "One or more required grocery "
                "costs are unknown."
            ),
        }

    # Complete known cost fits budget.
    budget_after_purchase = round(
        remaining_budget - purchase_cost,
        2,
    )

    return {
        "budget_status": "pass",
        "known_purchase_cost": round(
            purchase_cost,
            2,
        ),
        "remaining_budget": round(
            remaining_budget,
            2,
        ),
        "budget_after_purchase":
            budget_after_purchase,
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
    Check the existing basket_summary() output against the budget.

    Expected basket format:

        {
            "estimated_total": 12.0,
            "known_subtotal": 12.0,
            "unknown_cost_items": [],
            "cost_complete": True
        }

    This function is kept for compatibility with existing project
    code and tests.
    """

    if not isinstance(basket, dict):
        raise TypeError(
            "basket must be a dictionary"
        )

    # Support the old known_subtotal field first.
    # Fall back to estimated_total if known_subtotal is absent.
    purchase_cost = basket.get(
        "known_subtotal"
    )

    if purchase_cost is None:
        purchase_cost = basket.get(
            "estimated_total",
            0,
        )

    unknown_items = basket.get(
        "unknown_cost_items",
        [],
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
    Check the newer GroceryService output against the budget.

    GroceryService returns:

        {
            "priced_products": [...],
            "incomplete_products": [...],
            "missing_products": [...]
        }

    This function allows the budget layer to consume that output
    directly.
    """

    if not isinstance(
        grocery_results,
        dict,
    ):
        raise TypeError(
            "grocery_results must be a dictionary"
        )

    priced_products = grocery_results.get(
        "priced_products",
        [],
    )

    incomplete_products = grocery_results.get(
        "incomplete_products",
        [],
    )

    missing_products = grocery_results.get(
        "missing_products",
        [],
    )

    known_purchase_cost = round(
        sum(
            float(item["total_cost"])
            for item in priced_products
            if item.get("total_cost")
            is not None
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
        has_unknown_cost=bool(
            unknown_items
        ),
    )

    # Extra information useful to the next feature.
    result["items_priced"] = len(
        priced_products
    )

    result["unknown_items"] = (
        unknown_items
    )

    return result


def print_budget_result(
    result: dict,
) -> None:
    """
    Print a short readable budget result.

    The complete dictionary is still returned to other features.
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
        "unknown_items",
        [],
    )

    if unknown_items:
        print()
        print(
            "Unknown costs: "
            + ", ".join(
                unknown_items
            )
        )

    print()
    print(
        result["reason"]
    )

# if __name__ == "__main__":

#     test_grocery_results = {
#         "priced_products": [
#             {
#                 "ingredient": "sour cream",
#                 "total_cost": 4.59,
#             },
#             {
#                 "ingredient": "cheddar cheese",
#                 "total_cost": 10.04,
#             },
#             {
#                 "ingredient": "cilantro",
#                 "total_cost": 1.80,
#             },
#             {
#                 "ingredient": "dijon mustard",
#                 "total_cost": 5.60,
#             },
#         ],
#         "incomplete_products": [],
#         "missing_products": [],
#     }

#     test_remaining_budget = 50.00

#     result = check_grocery_budget(
#         grocery_results=test_grocery_results,
#         remaining_budget=test_remaining_budget,
#     )

#     print_budget_result(
#         result
#     )