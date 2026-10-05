"""src/agents/grocery_agent.py

Grocery Agent.

The Grocery Agent receives missing ingredients from the
Ingredient Agent / Manager and uses the existing GroceryService
to obtain purchasable FairPrice grocery options.

The agent does not:
- implement grocery search itself
- parse prices itself
- calculate package quantities itself
- calculate budget feasibility
- make the final recipe decision

Those responsibilities remain in the existing deterministic services.
"""

from src.agents.contracts import (
    AgentResult,
    AgentStatus,
)

from src.grocery.grocery_service import (
    GroceryService,
    grocery_summary,
)


class GroceryAgent:
    """
    Agent responsible for grocery purchasing facts.

    Input:
        recipe_id:
            Candidate recipe being evaluated.

        missing_ingredients:
            Ingredients that still need to be purchased,
            normally produced by the Ingredient Agent.

    Output:
        Shared AgentResult dictionary containing:

        {
            "agent": "grocery",
            "status": "success | partial | failed",
            "data": {
                "recipe_id": ...,
                "items": [...],
                "known_cost": ...,
                "all_items_priced": ...,
                "unpriced_items": [...]
            },
            "warnings": [...],
            "errors": [...]
        }
    """

    def __init__(
        self,
        grocery_service: GroceryService | None = None,
    ):
        """
        Use an injected GroceryService when provided.

        This allows:
        - deterministic unit tests
        - reuse of GroceryService caching
        - real GroceryService use in production
        """

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

        GroceryService performs:
        - FairPrice search
        - product filtering
        - price extraction
        - package parsing
        - package calculation
        - minimum-package fallback
        - caching

        GroceryAgent only orchestrates the service and converts its
        output into the shared agent contract.
        """

        # ---------------------------------------------------------
        # Validate recipe ID
        # ---------------------------------------------------------

        if not recipe_id:

            return AgentResult(
                agent="grocery",
                status=AgentStatus.FAILED,
                data={},
                warnings=[],
                errors=[
                    "recipe_id is required"
                ],
            ).to_dict()

        # ---------------------------------------------------------
        # Validate missing ingredients
        # ---------------------------------------------------------

        if not isinstance(
            missing_ingredients,
            (list, dict),
        ):

            return AgentResult(
                agent="grocery",
                status=AgentStatus.FAILED,
                data={
                    "recipe_id": recipe_id,
                },
                warnings=[],
                errors=[
                    (
                        "missing_ingredients must be "
                        "a list or dictionary"
                    )
                ],
            ).to_dict()

        # ---------------------------------------------------------
        # Nothing needs purchasing
        # ---------------------------------------------------------

        if not missing_ingredients:

            return AgentResult(
                agent="grocery",
                status=AgentStatus.SUCCESS,
                data={
                    "recipe_id":
                        recipe_id,

                    "items":
                        [],

                    "known_cost":
                        0.0,

                    "all_items_priced":
                        True,

                    "unpriced_items":
                        [],
                },
                warnings=[],
                errors=[],
            ).to_dict()

        # ---------------------------------------------------------
        # Call existing GroceryService
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

            return AgentResult(
                agent="grocery",
                status=AgentStatus.FAILED,
                data={
                    "recipe_id": recipe_id,
                },
                warnings=[],
                errors=[
                    (
                        "Grocery lookup failed: "
                        f"{exc}"
                    )
                ],
            ).to_dict()

        # ---------------------------------------------------------
        # Known purchase cost
        # ---------------------------------------------------------
        #
        # Only products with a usable total_cost contribute.
        #
        # Missing/incomplete products are NOT treated as zero-cost
        # completed purchases.
        # ---------------------------------------------------------

        known_cost = round(
            sum(
                float(
                    item["total_cost"]
                )
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
        # Find items whose complete purchase cost is unknown
        # ---------------------------------------------------------

        unpriced_items = []

        for item in grocery_results[
            "incomplete_products"
        ]:

            ingredient = item.get(
                "ingredient"
            )

            if ingredient:
                unpriced_items.append(
                    ingredient
                )

        for item in grocery_results[
            "missing_products"
        ]:

            ingredient = item.get(
                "ingredient"
            )

            if ingredient:
                unpriced_items.append(
                    ingredient
                )

        # Remove duplicates while preserving order.
        unpriced_items = list(
            dict.fromkeys(
                unpriced_items
            )
        )

        # ---------------------------------------------------------
        # all_items_priced
        # ---------------------------------------------------------

        all_items_priced = (
            len(unpriced_items) == 0
        )

        # ---------------------------------------------------------
        # Warnings
        # ---------------------------------------------------------

        warnings = [
            (
                "No complete purchase price "
                f"found for {ingredient}"
            )
            for ingredient
            in unpriced_items
        ]

        # ---------------------------------------------------------
        # Agent status
        # ---------------------------------------------------------
        #
        # success:
        #     Every required grocery item has a usable purchase cost.
        #
        # partial:
        #     Grocery processing succeeded, but one or more costs
        #     remain unknown.
        #
        # failed:
        #     Reserved for invalid input/service failures above.
        # ---------------------------------------------------------

        if all_items_priced:
            status = AgentStatus.SUCCESS
        else:
            status = AgentStatus.PARTIAL

        # ---------------------------------------------------------
        # Combine grocery items
        # ---------------------------------------------------------

        items = (
            grocery_results[
                "priced_products"
            ]
            + grocery_results[
                "incomplete_products"
            ]
            + grocery_results[
                "missing_products"
            ]
        )

        # ---------------------------------------------------------
        # Shared AgentResult
        # ---------------------------------------------------------

        return AgentResult(
            agent="grocery",

            status=status,

            data={
                "recipe_id":
                    recipe_id,

                "items":
                    items,

                "known_cost":
                    known_cost,

                "all_items_priced":
                    all_items_priced,

                "unpriced_items":
                    unpriced_items,
            },

            warnings=warnings,

            errors=[],
        ).to_dict()