"""scripts/verify_budget.py

End-to-end verification of the Intelligent Adaptive Meal Planner
grocery pricing and budget constraint.

Pipeline verified:

Recipe
    ->
Recipe ingredients
    ->
Pantry comparison
    ->
Ingredients that must be purchased
    ->
Tavily / FairPrice grocery pricing
    ->
Basket summary
    ->
Budget constraint
    ->
PASS / HARD FAIL / UNCERTAIN

The script uses the existing pantry_service.py, grocery_service.py
and budget_service.py implementations.

A detailed Markdown report is written to:

    reports/budget_verification.md

Run from the project root:

    python scripts/verify_budget.py
"""

import sys
from pathlib import Path


# ---------------------------------------------------------------------
# Project imports
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.pantry.pantry_service import (
    load_pantry,
    examine_pantry,
    fetch_recipe_ingredients,
    filter_ingredient_list,
)

from src.grocery.grocery_service import (
    GroceryService,
    basket_summary,
)

from src.reasoning.budget_service import (
    check_basket_budget,
)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

RECIPE_ID = "R03943"

BUDGETS_TO_CHECK = [
    100.00,
    50.00,
    20.00,
    10.00,
    1.00,
]

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "budget_verification.md"
)


# ---------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------

def money(value):
    if value is None:
        return "NA"

    return f"${float(value):.2f}"


def status_label(status):
    labels = {
        "pass": "PASS",
        "hard_fail": "HARD FAIL",
        "uncertain": "UNCERTAIN",
    }

    return labels.get(
        status,
        str(status).upper(),
    )


def yes_no(value):
    return "Yes" if value else "No"


# ---------------------------------------------------------------------
# Pantry -> grocery conversion
# ---------------------------------------------------------------------

def prepare_grocery_items(grocery_list):
    """
    Convert pantry_service grocery output into the list format
    expected by GroceryService.get_grocery_list().

    pantry_service returns:

        {
            "rice": {
                "ingredient_id": "...",
                "alias_name": "...",
                "quantity": 500,
                "unit": "g"
            }
        }

    GroceryService expects:

        [
            {
                "ingredient_name": "rice",
                "ingredient_id": "...",
                "quantity": 500,
                "unit": "g"
            }
        ]
    """

    items = []

    for ingredient_name, data in grocery_list.items():

        items.append(
            {
                "ingredient_id": data.get(
                    "ingredient_id"
                ),
                "ingredient_name": ingredient_name,
                "quantity": data.get(
                    "quantity"
                ),
                "unit": data.get(
                    "unit"
                ),
            }
        )

    return items


# ---------------------------------------------------------------------
# Step 1: recipe + pantry
# ---------------------------------------------------------------------

def get_required_grocery_list(recipe_id):
    """
    Use the existing pantry implementation to determine which
    recipe ingredients still need to be purchased.
    """

    print("=" * 70)
    print("RECIPE + PANTRY CHECK")
    print("=" * 70)
    print()

    print(
        f"Recipe ID: {recipe_id}"
    )

    print(
        "\nRetrieving recipe ingredients..."
    )

    ingredients = fetch_recipe_ingredients(
        recipe_id
    )

    print(
        f"Recipe ingredients found: "
        f"{len(ingredients)}"
    )

    print(
        "\nLoading pantry..."
    )

    pantry = examine_pantry(
        load_pantry()
    )

    print(
        f"Pantry items found: "
        f"{len(pantry)}"
    )

    print(
        "\nComparing recipe requirements "
        "against pantry..."
    )

    grocery_list = filter_ingredient_list(
        pantry,
        ingredients,
    )

    print(
        f"Ingredients requiring purchase: "
        f"{len(grocery_list)}"
    )

    print()

    if not grocery_list:
        print(
            "Nothing needs to be purchased."
        )

    else:

        for ingredient_name, data in grocery_list.items():

            quantity = data.get(
                "quantity"
            )

            unit = data.get(
                "unit"
            )

            status = data.get(
                "status"
            )

            print(
                f"  {ingredient_name}: "
                f"{quantity if quantity is not None else 'UNKNOWN'} "
                f"{unit or ''}"
            )

            if status:
                print(
                    f"    Pantry status: "
                    f"{status}"
                )

    return (
        ingredients,
        pantry,
        grocery_list,
    )


# ---------------------------------------------------------------------
# Step 2: grocery pricing
# ---------------------------------------------------------------------

def get_live_grocery_prices(
    grocery_list,
):
    """
    Send only ingredients that need purchasing into GroceryService.

    GroceryService then searches FairPrice through Tavily and
    calculates package requirements and final purchase costs.
    """

    print()
    print("=" * 70)
    print("LIVE FAIRPRICE GROCERY PRICING")
    print("=" * 70)
    print()

    items = prepare_grocery_items(
        grocery_list
    )

    service = GroceryService(
        verify_links=False
    )

    options = []

    for item in items:

        ingredient_name = (
            item["ingredient_name"]
        )

        print(
            f"Searching: "
            f"{ingredient_name}"
        )

        option = service.get_grocery_option(
            ingredient_name=ingredient_name,
            required_quantity=item.get(
                "quantity"
            ),
            unit=item.get(
                "unit"
            ),
            ingredient_id=item.get(
                "ingredient_id"
            ),
        )

        options.append(option)

        print(
            f"  Product       : "
            f"{option.product_name or 'NA'}"
        )

        print(
            f"  Price/package : "
            f"{money(option.price_per_package)}"
        )

        if (
            option.package_quantity is not None
            and
            option.package_unit is not None
        ):
            package = (
                f"{option.package_quantity} "
                f"{option.package_unit}"
            )
        else:
            package = "NA"

        print(
            f"  Package       : {package}"
        )

        print(
            f"  Packs needed  : "
            f"{option.packages_needed if option.packages_needed is not None else 'NA'}"
        )

        print(
            f"  Purchase cost : "
            f"{money(option.total_cost)}"
        )

        print(
            f"  Match status  : "
            f"{option.match_status}"
        )

        print(
            f"  Match quality : "
            f"{option.match_quality or 'NA'}"
        )

        print(
            f"  Search query  : "
            f"{option.search_query or 'NA'}"
        )

        print(
            f"  Store         : "
            f"{option.store or 'NA'}"
        )

        print(
            f"  Source        : "
            f"{option.source_url or 'NA'}"
        )

        if option.note:

            print(
                f"  Note          : "
                f"{option.note}"
            )

        print()

    basket = basket_summary(
        options
    )

    return (
        items,
        options,
        basket,
    )


# ---------------------------------------------------------------------
# Step 3: budget
# ---------------------------------------------------------------------

def verify_budgets(
    basket,
):
    """
    Check several remaining-budget values against the same
    grocery basket.
    """

    print()
    print("=" * 70)
    print("BUDGET CONSTRAINT")
    print("=" * 70)
    print()

    print(
        f"Known grocery subtotal : "
        f"{money(basket['known_subtotal'])}"
    )

    print(
        f"Complete cost known    : "
        f"{yes_no(basket['cost_complete'])}"
    )

    print(
        f"Unknown cost items     : "
        f"{basket['unknown_cost_items'] or 'None'}"
    )

    print()

    results = []

    for remaining_budget in BUDGETS_TO_CHECK:

        result = check_basket_budget(
            basket,
            remaining_budget,
        )

        results.append(
            {
                "remaining_budget":
                    remaining_budget,
                "result":
                    result,
            }
        )

        print(
            f"Budget: "
            f"{money(remaining_budget)}"
        )

        print(
            f"  Decision       : "
            f"{status_label(result['budget_status'])}"
        )

        print(
            f"  Known cost     : "
            f"{money(result['known_purchase_cost'])}"
        )

        print(
            f"  Budget after   : "
            f"{money(result['budget_after_purchase'])}"
        )

        print(
            f"  Reason         : "
            f"{result['reason']}"
        )

        print()

    return results


# ---------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------

def build_report(
    recipe_id,
    ingredients,
    pantry,
    grocery_list,
    options,
    basket,
    budget_results,
):
    """
    Build detailed end-to-end verification documentation.
    """

    lines = []

    lines.append(
        "# End-to-End Grocery + Budget Verification"
    )

    lines.append("")

    lines.append(
        "This report verifies the complete flow from recipe "
        "ingredients and pantry contents through live FairPrice "
        "pricing and the budget constraint."
    )

    lines.append("")

    lines.append(
        f"**Recipe ID:** `{recipe_id}`"
    )

    lines.append("")

    # =============================================================
    # Recipe requirements
    # =============================================================

    lines.append(
        "## 1. Recipe Requirements"
    )

    lines.append("")

    lines.append(
        "| Ingredient | Ingredient ID | Alias | "
        "Required Quantity | Unit |"
    )

    lines.append(
        "|---|---|---|---:|---|"
    )

    for name, data in ingredients.items():

        quantity = data.get(
            "quantity"
        )

        lines.append(
            f"| {name} "
            f"| {data.get('ingredient_id', 'NA')} "
            f"| {data.get('alias_name', 'NA')} "
            f"| {quantity if quantity is not None else 'NA'} "
            f"| {data.get('unit', 'NA')} |"
        )

    lines.append("")

    # =============================================================
    # Pantry
    # =============================================================

    lines.append(
        "## 2. Pantry Contents"
    )

    lines.append("")

    lines.append(
        "| Ingredient | Available Quantity | Unit |"
    )

    lines.append(
        "|---|---:|---|"
    )

    for name, data in pantry.items():

        lines.append(
            f"| {name} "
            f"| {data.get('quantity', 'NA')} "
            f"| {data.get('unit', 'NA')} |"
        )

    lines.append("")

    # =============================================================
    # Required grocery list
    # =============================================================

    lines.append(
        "## 3. Grocery List After Pantry Comparison"
    )

    lines.append("")

    if grocery_list:

        lines.append(
            "| Ingredient | Ingredient ID | "
            "Quantity to Buy | Unit | Pantry Status |"
        )

        lines.append(
            "|---|---|---:|---|---|"
        )

        for name, data in grocery_list.items():

            quantity = data.get(
                "quantity"
            )

            lines.append(
                f"| {name} "
                f"| {data.get('ingredient_id', 'NA')} "
                f"| {quantity if quantity is not None else 'UNKNOWN'} "
                f"| {data.get('unit', 'NA')} "
                f"| {data.get('status', 'needs_purchase')} |"
            )

    else:

        lines.append(
            "All required recipe ingredients are already "
            "available in the pantry."
        )

    lines.append("")

    # =============================================================
    # Grocery prices
    # =============================================================

    lines.append(
        "## 4. Live FairPrice Grocery Results"
    )

    lines.append("")

    if options:

        lines.append(
            "| Ingredient | Product | Price / Package | "
            "Package | Packs | Purchase Cost | "
            "Match Status | Match Quality |"
        )

        lines.append(
            "|---|---|---:|---|---:|---:|---|---|"
        )

        for option in options:

            if (
                option.package_quantity is not None
                and
                option.package_unit is not None
            ):
                package = (
                    f"{option.package_quantity} "
                    f"{option.package_unit}"
                )
            else:
                package = "NA"

            lines.append(
                f"| {option.ingredient_name} "
                f"| {option.product_name or 'NA'} "
                f"| {money(option.price_per_package)} "
                f"| {package} "
                f"| {option.packages_needed if option.packages_needed is not None else 'NA'} "
                f"| {money(option.total_cost)} "
                f"| {option.match_status} "
                f"| {option.match_quality or 'NA'} |"
            )

    else:

        lines.append(
            "No grocery purchases were required."
        )

    lines.append("")

    # =============================================================
    # Sources
    # =============================================================

    lines.append(
        "### FairPrice Sources"
    )

    lines.append("")

    if options:

        for option in options:

            if option.source_url:

                lines.append(
                    f"- **{option.ingredient_name}:** "
                    f"[{option.product_name}]"
                    f"({option.source_url})"
                )

            else:

                lines.append(
                    f"- **{option.ingredient_name}:** "
                    f"No reliable FairPrice product page found."
                )

    else:

        lines.append(
            "No grocery sources were required."
        )

    lines.append("")

    # =============================================================
    # Basket
    # =============================================================

    lines.append(
        "## 5. Basket Summary"
    )

    lines.append("")

    lines.append(
        f"- Grocery items requiring purchase: "
        f"**{basket['items']}**"
    )

    lines.append(
        f"- Items with known final cost: "
        f"**{basket['priced_items']}**"
    )

    lines.append(
        f"- Known subtotal: "
        f"**{money(basket['known_subtotal'])}**"
    )

    lines.append(
        f"- Complete purchase cost known: "
        f"**{yes_no(basket['cost_complete'])}**"
    )

    missing = (
        ", ".join(
            basket["unknown_cost_items"]
        )
        if basket["unknown_cost_items"]
        else "None"
    )

    lines.append(
        f"- Unknown-cost items: "
        f"**{missing}**"
    )

    lines.append("")

    # =============================================================
    # Budget
    # =============================================================

    lines.append(
        "## 6. Budget Constraint"
    )

    lines.append("")

    lines.append(
        "| Remaining Budget | Known Grocery Cost | "
        "Complete Cost Known? | Decision | "
        "Budget After Purchase |"
    )

    lines.append(
        "|---:|---:|---|---|---:|"
    )

    for item in budget_results:

        result = item["result"]

        lines.append(
            f"| {money(item['remaining_budget'])} "
            f"| {money(result['known_purchase_cost'])} "
            f"| {yes_no(basket['cost_complete'])} "
            f"| **{status_label(result['budget_status'])}** "
            f"| {money(result['budget_after_purchase'])} |"
        )

    lines.append("")

    # =============================================================
    # Reasoning
    # =============================================================

    lines.append(
        "## 7. Decision Reasoning"
    )

    lines.append("")

    for item in budget_results:

        result = item["result"]

        lines.append(
            f"### Budget {money(item['remaining_budget'])}"
        )

        lines.append("")

        lines.append(
            f"- Decision: "
            f"**{status_label(result['budget_status'])}**"
        )

        lines.append(
            f"- Known purchase cost: "
            f"**{money(result['known_purchase_cost'])}**"
        )

        lines.append(
            f"- Complete cost known: "
            f"**{yes_no(basket['cost_complete'])}**"
        )

        lines.append(
            f"- Budget after purchase: "
            f"**{money(result['budget_after_purchase'])}**"
        )

        lines.append(
            f"- Reason: {result['reason']}"
        )

        lines.append("")

    # =============================================================
    # Pipeline
    # =============================================================

    lines.append(
        "## 8. Verified Pipeline"
    )

    lines.append("")

    lines.append("```text")
    lines.append(f"Recipe {recipe_id}")
    lines.append("        |")
    lines.append("        v")
    lines.append("Recipe ingredient retrieval")
    lines.append("        |")
    lines.append("        v")
    lines.append("Pantry comparison")
    lines.append("        |")
    lines.append("        v")
    lines.append("Ingredients still requiring purchase")
    lines.append("        |")
    lines.append("        v")
    lines.append("Tavily -> FairPrice")
    lines.append("        |")
    lines.append("        v")
    lines.append("Grocery product + package price")
    lines.append("        |")
    lines.append("        v")
    lines.append("Basket summary")
    lines.append("        |")
    lines.append("        v")
    lines.append("Budget constraint")
    lines.append("        |")
    lines.append("        v")
    lines.append("PASS / HARD FAIL / UNCERTAIN")
    lines.append("```")

    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():

    print()
    print("=" * 70)
    print("INTELLIGENT ADAPTIVE MEAL PLANNER")
    print("END-TO-END GROCERY + BUDGET VERIFICATION")
    print("=" * 70)
    print()

    # -------------------------------------------------------------
    # Recipe -> pantry -> grocery requirements
    # -------------------------------------------------------------

    (
        ingredients,
        pantry,
        grocery_list,
    ) = get_required_grocery_list(
        RECIPE_ID
    )

    # -------------------------------------------------------------
    # Grocery requirements -> Tavily/FairPrice
    # -------------------------------------------------------------

    (
        grocery_items,
        options,
        basket,
    ) = get_live_grocery_prices(
        grocery_list
    )

    # -------------------------------------------------------------
    # Basket -> budget constraint
    # -------------------------------------------------------------

    budget_results = verify_budgets(
        basket
    )

    # -------------------------------------------------------------
    # Documentation
    # -------------------------------------------------------------

    report = build_report(
        recipe_id=RECIPE_ID,
        ingredients=ingredients,
        pantry=pantry,
        grocery_list=grocery_list,
        options=options,
        basket=basket,
        budget_results=budget_results,
    )

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )

    print()
    print("=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)

    print(
        f"\nDetailed report:\n"
        f"{REPORT_PATH}"
    )


if __name__ == "__main__":
    main()