"""scripts/verify_agent_chain.py

Manual integration verification for:

Manager-style input
        ↓
REAL IngredientAgent
        ↓
missing_ingredients
        ↓
REAL GroceryAgent
        ↓
Demo GroceryService
        ↓
shared AgentResult contract

This script does NOT call Tavily.

The purpose is to verify that the Ingredient Agent output can be
passed directly into the Grocery Agent and that the Grocery Agent
returns the shared contract expected by Manager.
"""

import os
import sys
from pprint import pprint


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
    )
)

if PROJECT_ROOT not in sys.path:
    sys.path.insert(
        0,
        PROJECT_ROOT,
    )


# ============================================================
# IMPORTS
# ============================================================

from src.agents.contracts import (
    normalize_agent_result,
)

from src.agents.ingredient_agent import (
    IngredientAgent,
)

from src.agents.grocery_agent import (
    GroceryAgent,
)

from src.grocery.grocery_service import (
    GroceryOption,
)


# ============================================================
# DEMO GROCERY SERVICE
# ============================================================

class DemoGroceryService:
    """
    Deterministic replacement for GroceryService.

    IngredientAgent is REAL.
    GroceryAgent is REAL.

    Only the external grocery search is replaced so that this
    integration verification does not depend on Tavily/API results.
    """

    def get_grocery_list(
        self,
        items,
        recipe_id=None,
    ):
        options = []

        for item in items:

            ingredient_name = item.get(
                "ingredient_name",
                "unknown ingredient",
            )

            quantity = item.get(
                "quantity"
            )

            unit = item.get(
                "unit"
            )

            ingredient_id = item.get(
                "ingredient_id"
            )

            # ----------------------------------------------------
            # Create deterministic grocery result
            # ----------------------------------------------------

            option = GroceryOption(
                ingredient_id=ingredient_id,

                ingredient_name=ingredient_name,

                required_quantity=quantity,

                required_unit=unit,

                product_name=(
                    f"Demo FairPrice "
                    f"{ingredient_name}"
                ),

                package_quantity=500,

                package_unit="g",

                packages_needed=1,

                price_per_package=2.50,

                total_cost=2.50,

                currency="SGD",

                store="FairPrice",

                source_url=(
                    "https://www.fairprice.com.sg/"
                    "product/demo-product"
                ),

                match_status="matched",

                match_quality="exact",

                note=(
                    "Demo grocery product used for "
                    "integration verification."
                ),
            )

            options.append(
                option
            )

        return options


# ============================================================
# DISPLAY HELPERS
# ============================================================

def heading(
    title: str,
) -> None:

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print()


def print_pantry(
    pantry: list,
) -> None:

    print("Pantry:")

    if not pantry:
        print("  None")
        return

    for item in pantry:

        print(
            f"- "
            f"{item.get('ingredient_name')}: "
            f"{item.get('quantity')} "
            f"{item.get('unit')}"
        )


def print_missing_ingredients(
    missing_ingredients: list,
) -> None:

    if not missing_ingredients:

        print(
            "No ingredients need purchasing."
        )

        return

    for item in missing_ingredients:

        print(
            f"- "
            f"{item.get('ingredient_name')}: "
            f"{item.get('quantity')} "
            f"{item.get('unit')}"
        )

        print(
            f"  Ingredient ID: "
            f"{item.get('ingredient_id')}"
        )

        print(
            f"  Pantry status: "
            f"{item.get('status')}"
        )


def print_grocery_items(
    items: list,
) -> None:

    if not items:

        print(
            "No grocery items."
        )

        return

    for item in items:

        print(
            f"- {item.get('ingredient')}"
        )

        print(
            f"  Required: "
            f"{item.get('required_quantity')} "
            f"{item.get('required_unit')}"
        )

        print(
            f"  Product: "
            f"{item.get('product_name') or 'NA'}"
        )

        package_quantity = item.get(
            "package_quantity"
        )

        package_unit = item.get(
            "package_unit"
        )

        if (
            package_quantity is not None
            and package_unit is not None
        ):

            package_text = (
                f"{package_quantity:g} "
                f"{package_unit}"
            )

        else:

            package_text = "NA"

        print(
            f"  Package: "
            f"{package_text}"
        )

        packages_needed = item.get(
            "packages_needed"
        )

        print(
            f"  Packages needed: "
            f"{packages_needed if packages_needed is not None else 'NA'}"
        )

        price = item.get(
            "price_per_package"
        )

        if price is not None:

            print(
                f"  Price/package: "
                f"S${price:.2f}"
            )

        else:

            print(
                "  Price/package: NA"
            )

        total = item.get(
            "total_cost"
        )

        if total is not None:

            print(
                f"  Purchase cost: "
                f"S${total:.2f}"
            )

        else:

            print(
                "  Purchase cost: NA"
            )

        print(
            f"  Match status: "
            f"{item.get('match_status')}"
        )

        print()


# ============================================================
# MAIN VERIFICATION
# ============================================================

def main():

    # --------------------------------------------------------
    # Manager-style input
    # --------------------------------------------------------

    recipe_id = "R03943"

    pantry = [
        {
            "ingredient_id":
                "ING0614",

            "ingredient_name":
                "cauliflower",

            "quantity":
                1,

            "unit":
                "head",
        },

        {
            "ingredient_id":
                "ING3248",

            "ingredient_name":
                "sour cream",

            "quantity":
                2,

            "unit":
                "tablespoon",
        },
    ]

    # ========================================================
    # STEP 1
    # ========================================================

    heading(
        "1. MANAGER-STYLE INPUT"
    )

    print(
        f"Recipe ID: {recipe_id}"
    )

    print()

    print_pantry(
        pantry
    )

    # ========================================================
    # STEP 2 - REAL INGREDIENT AGENT
    # ========================================================

    ingredient_agent = (
        IngredientAgent()
    )

    ingredient_result = (
        ingredient_agent.run(
            recipe_id=recipe_id,
            pantry=pantry,
        )
    )

    # Validate exactly like Manager does.
    ingredient_result = (
        normalize_agent_result(
            ingredient_result,
            "ingredient",
        )
    )

    heading(
        "2. REAL INGREDIENT AGENT OUTPUT"
    )

    print(
        f"Agent: "
        f"{ingredient_result['agent']}"
    )

    print(
        f"Status: "
        f"{ingredient_result['status']}"
    )

    if ingredient_result[
        "errors"
    ]:

        print()

        print("Errors:")

        for error in ingredient_result[
            "errors"
        ]:

            print(
                f"- {error}"
            )

    # Stop if Ingredient Agent failed.

    if (
        ingredient_result[
            "status"
        ]
        == "failed"
    ):

        heading(
            "INTEGRATION FAILED"
        )

        print(
            "Ingredient Agent failed, "
            "so Grocery Agent was not called."
        )

        return

    ingredient_data = (
        ingredient_result[
            "data"
        ]
    )

    required_ingredients = (
        ingredient_data.get(
            "required_ingredients",
            [],
        )
    )

    pantry_used = (
        ingredient_data.get(
            "pantry_used",
            [],
        )
    )

    missing_ingredients = (
        ingredient_data.get(
            "missing_ingredients",
            [],
        )
    )

    print()
    print(
        f"Required ingredients: "
        f"{len(required_ingredients)}"
    )

    print(
        f"Pantry ingredients used: "
        f"{len(pantry_used)}"
    )

    print(
        f"Ingredients to purchase: "
        f"{len(missing_ingredients)}"
    )

    print()

    print(
        "Missing ingredients:"
    )

    print_missing_ingredients(
        missing_ingredients
    )

    # ========================================================
    # STEP 3 - EXACT HANDOFF
    # ========================================================

    heading(
        "3. INGREDIENT -> GROCERY HANDOFF"
    )

    print(
        "This is the exact missing_ingredients "
        "data produced by IngredientAgent:"
    )

    print()

    pprint(
        missing_ingredients,
        sort_dicts=False,
    )

    print()

    print(
        "The same data is now passed directly "
        "to GroceryAgent.run()."
    )

    # ========================================================
    # STEP 4 - REAL GROCERY AGENT
    # ========================================================

    grocery_agent = GroceryAgent(
        grocery_service=(
            DemoGroceryService()
        )
    )

    grocery_result = (
        grocery_agent.run(
            recipe_id=recipe_id,

            missing_ingredients=(
                missing_ingredients
            ),
        )
    )

    # Validate exactly like Manager does.
    grocery_result = (
        normalize_agent_result(
            grocery_result,
            "grocery",
        )
    )

    heading(
        "4. REAL GROCERY AGENT OUTPUT"
    )

    print(
        f"Agent: "
        f"{grocery_result['agent']}"
    )

    print(
        f"Status: "
        f"{grocery_result['status']}"
    )

    grocery_data = (
        grocery_result[
            "data"
        ]
    )

    known_cost = grocery_data.get(
        "known_cost",
        0.0,
    )

    all_items_priced = (
        grocery_data.get(
            "all_items_priced",
            False,
        )
    )

    unpriced_items = (
        grocery_data.get(
            "unpriced_items",
            [],
        )
    )

    print(
        f"Recipe: "
        f"{grocery_data.get('recipe_id')}"
    )

    print(
        f"Known grocery cost: "
        f"S${known_cost:.2f}"
    )

    print(
        f"All items priced: "
        f"{all_items_priced}"
    )

    print(
        f"Unpriced items: "
        f"{unpriced_items if unpriced_items else 'None'}"
    )

    print()

    print(
        "Grocery items:"
    )

    print()

    print_grocery_items(
        grocery_data.get(
            "items",
            [],
        )
    )

    # ========================================================
    # STEP 5 - CONTRACT CHECK
    # ========================================================

    heading(
        "5. SHARED CONTRACT CHECK"
    )

    print(
        "Ingredient Agent:"
    )

    print(
        f"  agent    = "
        f"{ingredient_result['agent']}"
    )

    print(
        f"  status   = "
        f"{ingredient_result['status']}"
    )

    print(
        f"  warnings = "
        f"{ingredient_result['warnings']}"
    )

    print(
        f"  errors   = "
        f"{ingredient_result['errors']}"
    )

    print()

    print(
        "Grocery Agent:"
    )

    print(
        f"  agent    = "
        f"{grocery_result['agent']}"
    )

    print(
        f"  status   = "
        f"{grocery_result['status']}"
    )

    print(
        f"  warnings = "
        f"{grocery_result['warnings']}"
    )

    print(
        f"  errors   = "
        f"{grocery_result['errors']}"
    )

    # ========================================================
    # STEP 6 - VERIFY EXPECTED MANAGER FIELDS
    # ========================================================

    heading(
        "6. MANAGER COMPATIBILITY CHECK"
    )

    required_grocery_fields = [
        "recipe_id",
        "items",
        "known_cost",
        "all_items_priced",
        "unpriced_items",
    ]

    missing_fields = [
        field
        for field
        in required_grocery_fields
        if field not in grocery_data
    ]

    if missing_fields:

        print(
            "Manager compatibility: FAILED"
        )

        print(
            "Missing Grocery Agent fields:"
        )

        for field in missing_fields:

            print(
                f"- {field}"
            )

    else:

        print(
            "Manager compatibility: OK"
        )

        print()

        print(
            "Manager can read:"
        )

        print(
            f"- known_cost = "
            f"{grocery_data['known_cost']}"
        )

        print(
            f"- all_items_priced = "
            f"{grocery_data['all_items_priced']}"
        )

        print(
            f"- unpriced_items = "
            f"{grocery_data['unpriced_items']}"
        )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    heading(
        "7. INTEGRATION RESULT"
    )

    if missing_fields:

        print(
            "FAILED"
        )

        print()

        print(
            "The Grocery Agent output does not yet "
            "contain every field expected by Manager."
        )

    else:

        print(
            "SUCCESS"
        )

        print()

        print(
            "Real IngredientAgent output was passed "
            "directly into the real GroceryAgent."
        )

        print()

        print(
            "Ingredient Agent contract:       OK"
        )

        print(
            "Ingredient -> Grocery handoff:   OK"
        )

        print(
            "Grocery Agent contract:          OK"
        )

        print(
            "Manager-compatible grocery data: OK"
        )

        print()

        print(
            "NOTE: GroceryService is simulated in this "
            "verification script."
        )

        print(
            "Real Tavily/FairPrice retrieval is tested "
            "separately by the grocery pipeline."
        )


if __name__ == "__main__":
    main()