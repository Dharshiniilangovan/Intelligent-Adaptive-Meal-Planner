
"""scripts/verify_grocery_source.py

Member 4 - Grocery Source + Budget Verification

Tests:
1. Live Tavily/FairPrice grocery search.
2. Ingredient/product matching.
3. Package quantity extraction.
4. Price per package.
5. Packages required.
6. Total purchase cost per ingredient.
7. Combined grocery purchase cost.
8. Budget feasibility.
9. Remaining budget.
10. Unknown or incomplete grocery costs.

Output:
    reports/grocery_source_verification.md

Run:
    python scripts/verify_grocery_source.py
"""

import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.grocery.tavily_client import SearchError
from src.grocery.food_filter import search_queries
from src.grocery.grocery_service import GroceryService
from src.reasoning.budget_service import check_grocery_budget


# ============================================================
# TEST CONFIGURATION
# ============================================================

RECIPE_ID = "R03699"

# Change this to test different budgets.
REMAINING_BUDGET = 50.00

TEST_INGREDIENTS = [
    ("strawberry", 2.0, "tablespoon"),
    ("banana", 1.0, "tablespoon"),
    ("sugar", 2.0, "tablespoon"),
    ("lemon juice", 1.0, "pinch"),
]

REPORT_PATH = (
    PROJECT_ROOT
    / "reports"
    / "grocery_source_verification.md"
)


# ============================================================
# HELPERS
# ============================================================

def yes_no(value) -> str:
    return "yes" if value else "no"


def cell(value) -> str:
    """Make values safe for Markdown table cells."""

    if value is None or value == "":
        return "NA"

    return (
        str(value)
        .replace("|", "/")
        .replace("\n", " ")
    )


def link(url: str | None) -> str:
    return f"[link]({url})" if url else "NA"


def money(value) -> str:
    """Format SGD prices."""

    if value is None:
        return "NA"

    return f"S${float(value):.2f}"


def product_table(
    service: GroceryService,
    ingredient: str,
    products: list[dict],
) -> list[str]:
    """Show every raw product and why it passed or failed."""

    rows = [
        "| # | Product | Price | Store | Country | Verdict | URL |",
        "|---|---|---|---|---|---|---|",
    ]

    for i, product in enumerate(products, start=1):

        valid, rejected = service._filter(
            ingredient,
            [product],
        )

        if valid:
            verdict = (
                f"PASS ({valid[0]['match']})"
            )
        else:
            verdict = (
                f"REJECT: {next(iter(rejected), 'unknown reason')}"
            )

        rows.append(
            f"| {i} "
            f"| {cell(product.get('title'))} "
            f"| {cell(product.get('price'))} "
            f"{cell(product.get('currency'))} "
            f"| {cell(product.get('store'))} "
            f"| {cell(product.get('country_code'))} "
            f"| {cell(verdict)} "
            f"| {link(product.get('url'))} |"
        )

    return rows


# ============================================================
# MAIN VERIFICATION
# ============================================================

def main() -> None:

    service = GroceryService(
        verify_links=True
    )

    run_time = datetime.now().strftime(
        "%Y-%m-%d %H:%M"
    )

    summary_rows = []
    details = []

    # BudgetService expects these categories.
    priced_products = []
    incomplete_products = []
    missing_products = []

    # ========================================================
    # STEP 1 - SEARCH AND PRICE INGREDIENTS
    # ========================================================

    for name, qty, unit in TEST_INGREDIENTS:

        print(f"\nChecking {name} ...")

        section = [
            f"### {name} (need {qty} {unit})"
        ]

        search_ok = True
        raw_count = 0

        # ----------------------------------------------------
        # RAW TAVILY RESULTS
        # ----------------------------------------------------

        for query in search_queries(name):

            try:
                products = service._search(query)

            except SearchError as exc:

                search_ok = False

                section.append(
                    f"\n**Query '{query}': "
                    f"search failed** - {cell(exc)}\n"
                )

                continue

            raw_count += len(products)

            section.append(
                f"\n**Query '{query}': "
                f"{len(products)} raw results**\n"
            )

            if products:
                section.extend(
                    product_table(
                        service,
                        name,
                        products,
                    )
                )

        # ----------------------------------------------------
        # FINAL PRODUCT SELECTION
        # ----------------------------------------------------

        option = service.get_grocery_option(
            ingredient_name=name,
            required_quantity=qty,
            unit=unit,
        )

        # ----------------------------------------------------
        # CLASSIFY FOR BUDGET SERVICE
        # ----------------------------------------------------

        item = {
            "ingredient": name,
            "required_quantity": qty,
            "required_unit": unit,

            "product_name": option.product_name,

            "package_quantity": option.package_quantity,
            "package_unit": option.package_unit,

            "packages_needed": option.packages_needed,

            "price_per_package": option.price_per_package,
            "total_cost": option.total_cost,

            "currency": option.currency,
            "store": option.store,

            "source_url": option.source_url,

            "match_status": option.match_status,
            "match_quality": option.match_quality,

            "note": option.note,
        }

        if (
            option.product_name is None
            or option.price_per_package is None
        ):
            missing_products.append(item)

        elif option.total_cost is None:
            incomplete_products.append(item)

        else:
            priced_products.append(item)

        # ----------------------------------------------------
        # INGREDIENT REPORT
        # ----------------------------------------------------

        section.extend([
            "",
            f"- **Chosen:** {cell(option.product_name)}",

            (
                f"- **Package:** "
                f"{cell(option.package_quantity)} "
                f"{option.package_unit or ''} | "
                f"**Price/package:** "
                f"{money(option.price_per_package)} | "
                f"**Packages needed:** "
                f"{cell(option.packages_needed)} | "
                f"**Total:** {money(option.total_cost)}"
            ),

            (
                f"- **Store:** {cell(option.store)} | "
                f"**Source updated:** "
                f"{cell(option.source_updated_at)}"
            ),

            (
                f"- **URL:** "
                f"{option.source_url or 'NA'}"
            ),

            (
                f"- **Status:** "
                f"{option.match_status} "
                f"({option.match_quality or '-'} match). "
                f"{option.note}"
            ),

            "",
        ])

        details.append(
            "\n".join(section)
        )

        summary_rows.append([
            name,

            f"{yes_no(search_ok)} ({raw_count})",

            yes_no(option.product_name),

            yes_no(
                option.price_per_package is not None
            ),

            yes_no(
                option.package_quantity is not None
            ),

            yes_no(option.store),

            cell(option.packages_needed),

            money(option.total_cost),

            link(option.source_url)
            if option.source_url else "-",

            yes_no(option.source_updated_at)
            if option.product_name else "-",
        ])

        print(
            f"  Product: "
            f"{option.product_name or 'NOT FOUND'}"
        )

        print(
            f"  Price/package: "
            f"{money(option.price_per_package)}"
        )

        print(
            f"  Packages needed: "
            f"{cell(option.packages_needed)}"
        )

        print(
            f"  Purchase cost: "
            f"{money(option.total_cost)}"
        )

        print(
            f"  Status: {option.match_status}"
        )

    # ========================================================
    # STEP 2 - COMBINE GROCERY COSTS
    # ========================================================

    known_cost = round(
        sum(
            float(item["total_cost"])
            for item in priced_products
            if item.get("total_cost") is not None
        ),
        2,
    )

    unpriced_items = [
        item["ingredient"]
        for item in (
            incomplete_products
            + missing_products
        )
    ]

    all_items_priced = (
        len(unpriced_items) == 0
    )

    grocery_results = {
        "priced_products": priced_products,
        "incomplete_products": incomplete_products,
        "missing_products": missing_products,

        "known_cost": known_cost,
        "all_items_priced": all_items_priced,
        "unpriced_items": unpriced_items,
    }

    # ========================================================
    # STEP 3 - BUDGET FEASIBILITY
    # ========================================================

    budget_result = check_grocery_budget(
        grocery_results=grocery_results,
        remaining_budget=REMAINING_BUDGET,
    )

    budget_status = budget_result["budget_status"]

    budget_after_purchase = budget_result.get(
        "budget_after_purchase"
    )

    # ========================================================
    # STEP 4 - BUILD SUMMARY TABLE
    # ========================================================

    header = (
        "| Ingredient | Search worked (results) "
        "| Product matched | Price | Package size "
        "| Store | Packages | Purchase cost "
        "| URL | Source timestamp |\n"
        "|---|---|---|---|---|---|---|---|---|---|"
    )

    table = "\n".join(
        "| " + " | ".join(row) + " |"
        for row in summary_rows
    )

    # ========================================================
    # STEP 5 - BUDGET REPORT
    # ========================================================

    budget_lines = [
        "## Grocery Budget Verification",
        "",
        f"**Recipe ID:** {RECIPE_ID}",
        "",
        f"**Available budget:** {money(REMAINING_BUDGET)}",
        "",
        f"**Known grocery cost:** {money(known_cost)}",
        "",
        f"**Total ingredients:** {len(TEST_INGREDIENTS)}",
        "",
        f"**Priced ingredients:** {len(priced_products)}",
        "",
        f"**Incomplete ingredients:** {len(incomplete_products)}",
        "",
        f"**Missing ingredients:** {len(missing_products)}",
        "",
        f"**All items priced:** {yes_no(all_items_priced)}",
        "",
        f"**Budget status:** {budget_status.upper()}",
        "",
        (
            f"**Budget after purchase:** "
            f"{money(budget_after_purchase)}"
        ),
        "",
        f"**Reason:** {budget_result['reason']}",
        "",
    ]

    if unpriced_items:
        budget_lines.extend([
            "### Unpriced Ingredients",
            "",
        ])

        for ingredient in unpriced_items:
            budget_lines.append(
                f"- {ingredient}"
            )

        budget_lines.append("")

    # Minimum retail package estimates.
    estimated_items = [
        item["ingredient"]
        for item in priced_products
        if item.get("match_status")
        == "matched_minimum_package"
    ]

    if estimated_items:
        budget_lines.extend([
            "### Estimated Purchase Quantities",
            "",
            (
                "These ingredients use a minimum retail "
                "package estimate because the exact required "
                "quantity could not be compared with the "
                "product package."
            ),
            "",
        ])

        for ingredient in estimated_items:
            budget_lines.append(
                f"- {ingredient}"
            )

        budget_lines.append("")

    # ========================================================
    # STEP 6 - WRITE MARKDOWN REPORT
    # ========================================================

    report = (
        "# Grocery Source and Budget Verification\n\n"
        f"Run: {run_time}\n\n"
        f"Recipe: {RECIPE_ID}\n\n"

        "## Grocery Summary\n\n"

        + header
        + "\n"
        + table
        + "\n\n"

        + "\n".join(budget_lines)
        + "\n\n"

        + "## Detailed Product Verification\n\n"
        + "\n".join(details)

        + "\n\n## Manual Check\n\n"
        + (
            "Open the product URLs and confirm "
            "product identity, package size, "
            "availability, and actual retail price.\n"
        )
    )

    REPORT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_PATH.write_text(
        report,
        encoding="utf-8",
    )

    # ========================================================
    # STEP 7 - TERMINAL OUTPUT
    # ========================================================

    print("\n" + "=" * 70)
    print("GROCERY + BUDGET VERIFICATION")
    print("=" * 70)

    print(f"\nRecipe ID: {RECIPE_ID}")

    print(
        f"Total ingredients: "
        f"{len(TEST_INGREDIENTS)}"
    )

    print(
        f"Priced ingredients: "
        f"{len(priced_products)}"
    )

    print(
        f"Unpriced ingredients: "
        f"{len(unpriced_items)}"
    )

    print(
        f"\nKnown grocery cost: "
        f"{money(known_cost)}"
    )

    print(
        f"Available budget: "
        f"{money(REMAINING_BUDGET)}"
    )

    print(
        f"Budget status: "
        f"{budget_status.upper()}"
    )

    print(
        f"Budget after purchase: "
        f"{money(budget_after_purchase)}"
    )

    print(
        f"\nReason: "
        f"{budget_result['reason']}"
    )

    if unpriced_items:
        print(
            "\nUnpriced ingredients: "
            + ", ".join(unpriced_items)
        )

    if estimated_items:
        print(
            "\nMinimum-package estimates: "
            + ", ".join(estimated_items)
        )

    print(
        f"\nSaved report: "
        f"{REPORT_PATH.relative_to(PROJECT_ROOT)}"
    )


if __name__ == "__main__":
    main()
