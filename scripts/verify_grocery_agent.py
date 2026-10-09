"""scripts/verify_grocery_agent.py

Manual verification of the Grocery Agent output contract.

Uses dummy GroceryService data so no Tavily/API call is required.

Run:
    python -m scripts.verify_grocery_agent
"""

import json

from src.agents.contracts import (
    normalize_agent_result,
)

from src.agents.grocery_agent import (
    GroceryAgent,
)

from src.grocery.grocery_service import (
    GroceryOption,
)


class DemoGroceryService:
    """
    Deterministic GroceryService used only for verification.
    """

    def get_grocery_list(
        self,
        items,
        recipe_id=None,
    ):
        return [
            GroceryOption(
                ingredient_id="ING001",
                ingredient_name="rice",
                required_quantity=1300,
                required_unit="g",

                product_name="FairPrice Jasmine Rice",
                package_quantity=500,
                package_unit="g",
                packages_needed=3,

                price_per_package=2.00,
                total_cost=6.00,

                currency="SGD",
                store="FairPrice",

                match_status="matched",
                match_quality="exact",
            ),

            GroceryOption(
                ingredient_id="ING002",
                ingredient_name="cheddar cheese",
                required_quantity=1.5,
                required_unit="tablespoon",

                product_name="Cheddar Cheese",
                package_quantity=500,
                package_unit="g",
                packages_needed=1,

                price_per_package=10.04,
                total_cost=10.04,

                currency="SGD",
                store="FairPrice",

                match_status="matched_minimum_package",
                match_quality="exact",

                note=(
                    "Unit mismatch; using one retail "
                    "package as the minimum purchase."
                ),
            ),
        ]


def main():

    # ---------------------------------------------------------
    # Input normally received from Ingredient Agent
    # ---------------------------------------------------------

    missing_ingredients = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 1300,
            "unit": "g",
        },
        {
            "ingredient_id": "ING002",
            "ingredient_name": "cheddar cheese",
            "quantity": 1.5,
            "unit": "tablespoon",
        },
    ]

    # ---------------------------------------------------------
    # Run real Grocery Agent
    # ---------------------------------------------------------

    agent = GroceryAgent(
        grocery_service=DemoGroceryService()
    )

    result = agent.run(
        recipe_id="R001",
        missing_ingredients=missing_ingredients,
        remaining_budget=50.00,
    )

    # ---------------------------------------------------------
    # Validate using the same shared contract Manager uses
    # ---------------------------------------------------------

    result = normalize_agent_result(
        result,
        "grocery",
    )

    # ---------------------------------------------------------
    # Print exact Grocery Agent output
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print("GROCERY AGENT OUTPUT")
    print("=" * 70)
    print()

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()