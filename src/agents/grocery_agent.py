"""src/agents/grocery_agent.py

Grocery Agent.

The Grocery Agent receives missing ingredients from the
Ingredient Agent / Manager and uses the existing GroceryService
to obtain purchasable FairPrice grocery options.

The agent does not:
- implement grocery search itself
- parse prices itself
- calculate budget feasibility
- make the final recipe decision

Those responsibilities remain in their existing services.
"""

from src.grocery.grocery_service import (
    GroceryService,
    grocery_summary,
)


class GroceryAgent:
    """
    Agent responsible for grocery purchasing facts.

    Input:
        recipe_id
        missing_ingredients

    Output:
        structured AgentResult containing:
        - grocery items
        - known purchase cost
        - whether all items were priced
        - unpriced ingredients
    """

    def __init__(
        self,
        grocery_service: GroceryService | None = None,
    ):
        self.grocery_service = (
            grocery_service
            or GroceryService()
        )

    def run(
        self,
        recipe_id: str,
        missing_ingredients: list[dict] | dict,
    ) -> dict:
        """
        Find purchasable grocery options for missing ingredients.
        """

        # ---------------------------------------------------------
        # Basic input validation
        # ---------------------------------------------------------

        if not recipe_id:
            return {
                "agent": "grocery",
                "status": "failed",
                "data": {},
                "warnings": [],
                "errors": [
                    "recipe_id is required"
                ],
            }

        if not isinstance(
            missing_ingredients,
            (list, dict),
        ):
            return {
                "agent": "grocery",
                "status": "failed",
                "data": {
                    "recipe_id": recipe_id,
                },
                "warnings": [],
                "errors": [
                    "missing_ingredients must be a list or dictionary"
                ],
            }

        # ---------------------------------------------------------
        # Nothing needs purchasing
        # ---------------------------------------------------------

        if not missing_ingredients:
            return {
                "agent": "grocery",
                "status": "success",
                "data": {
                    "recipe_id": recipe_id,
                    "items": [],
                    "known_cost": 0.0,
                    "all_items_priced": True,
                    "unpriced_items": [],
                },
                "warnings": [],
                "errors": [],
            }

        # ---------------------------------------------------------
        # GroceryService
        # ---------------------------------------------------------

        try:
            options = (
                self.grocery_service
                .get_grocery_list(
                    missing_ingredients
                )
            )

            grocery_results = (
                grocery_summary(
                    options
                )
            )

        except Exception as exc:
            return {
                "agent": "grocery",
                "status": "failed",
                "data": {
                    "recipe_id": recipe_id,
                },
                "warnings": [],
                "errors": [
                    f"Grocery lookup failed: {exc}"
                ],
            }

        # ---------------------------------------------------------
        # Calculate known purchase cost
        # ---------------------------------------------------------

        known_cost = round(
            sum(
                item["total_cost"]
                for item
                in grocery_results[
                    "priced_products"
                ]
                if item.get(
                    "total_cost"
                ) is not None
            ),
            2,
        )

        # ---------------------------------------------------------
        # Collect anything without a complete purchase price
        # ---------------------------------------------------------

        unpriced_items = []

        for item in grocery_results[
            "incomplete_products"
        ]:
            unpriced_items.append(
                item["ingredient"]
            )

        for item in grocery_results[
            "missing_products"
        ]:
            unpriced_items.append(
                item["ingredient"]
            )

        all_items_priced = (
            len(unpriced_items) == 0
        )

        # ---------------------------------------------------------
        # Warnings
        # ---------------------------------------------------------

        warnings = []

        for ingredient in unpriced_items:
            warnings.append(
                f"No complete purchase price found for {ingredient}"
            )

        # ---------------------------------------------------------
        # Agent status
        # ---------------------------------------------------------

        if all_items_priced:
            status = "success"
        else:
            status = "partial"

        # ---------------------------------------------------------
        # Structured result
        # ---------------------------------------------------------

        return {
            "agent": "grocery",

            "status": status,

            "data": {
                "recipe_id":
                    recipe_id,

                "items":
                    (
                        grocery_results[
                            "priced_products"
                        ]
                        + grocery_results[
                            "incomplete_products"
                        ]
                        + grocery_results[
                            "missing_products"
                        ]
                    ),

                "known_cost":
                    known_cost,

                "all_items_priced":
                    all_items_priced,

                "unpriced_items":
                    unpriced_items,
            },

            "warnings":
                warnings,

            "errors": [],
        }


# if __name__ == "__main__":

#     test_missing_ingredients = [
#         {
#             "ingredient_id": "ING3248",
#             "ingredient_name": "sour cream",
#             "quantity": 1.5,
#             "unit": "tablespoon",
#         },
#         {
#             "ingredient_id": "ING0658",
#             "ingredient_name": "cheddar cheese",
#             "quantity": 1.5,
#             "unit": "tablespoon",
#         },
#         {
#             "ingredient_id": "ING0870",
#             "ingredient_name": "cilantro",
#             "quantity": 1.0,
#             "unit": "sprig",
#         },
#         {
#             "ingredient_id": "ING1203",
#             "ingredient_name": "dijon mustard",
#             "quantity": 1.0,
#             "unit": "pinch",
#         },
#     ]

#     agent = GroceryAgent()

#     result = agent.run(
#         recipe_id="TEST_RECIPE",
#         missing_ingredients=test_missing_ingredients,
#     )

#     print()
#     print("=" * 60)
#     print("GROCERY AGENT RESULT")
#     print("=" * 60)

#     print(f"Agent: {result['agent']}")
#     print(f"Status: {result['status']}")

#     data = result["data"]

#     print(
#         f"Known cost: "
#         f"S${data.get('known_cost', 0):.2f}"
#     )

#     print(
#         f"All items priced: "
#         f"{data.get('all_items_priced')}"
#     )

#     print()

#     for item in data.get("items", []):

#         ingredient = item.get(
#             "ingredient",
#             "unknown"
#         )

#         product = item.get(
#             "product_name"
#         ) or "NA"

#         package_quantity = item.get(
#             "package_quantity"
#         )

#         package_unit = item.get(
#             "package_unit"
#         )

#         packages_needed = item.get(
#             "packages_needed"
#         )

#         total_cost = item.get(
#             "total_cost"
#         )

#         match_status = item.get(
#             "match_status"
#         )

#         if (
#             package_quantity is not None
#             and package_unit is not None
#         ):
#             package = (
#                 f"{package_quantity:g} "
#                 f"{package_unit}"
#             )
#         else:
#             package = "NA"

#         if total_cost is not None:
#             cost = f"S${total_cost:.2f}"
#         else:
#             cost = "NA"

#         print(ingredient)
#         print(f"  Product: {product}")
#         print(f"  Package: {package}")
#         print(
#             f"  Packages needed: "
#             f"{packages_needed if packages_needed is not None else 'NA'}"
#         )
#         print(f"  Purchase cost: {cost}")
#         print(f"  Match: {match_status}")
#         print()

#     if result["warnings"]:
#         print("Warnings:")

#         for warning in result["warnings"]:
#             print(f"  - {warning}")

#     if result["errors"]:
#         print("Errors:")

#         for error in result["errors"]:
#             print(f"  - {error}")