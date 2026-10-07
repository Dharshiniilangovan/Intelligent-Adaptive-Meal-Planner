"""
Day 5 - Member 4
Plan-Level Grocery Basket Verification

Run from project root:

    python -m scripts.verify_plan_grocery

This script uses controlled hard-coded inputs so that the expected
results are known and easy to verify.

It exercises the REAL implementation from:

    src.agents.grocery_agent

It does NOT reimplement the grocery logic here.
"""

from src.agents.grocery_agent import (
    aggregate_requirements,
    subtract_inventory,
    build_plan_grocery_basket,
    build_cost_summary,
)


LINE = "=" * 78
SUBLINE = "-" * 78


def heading(title):
    print()
    print(LINE)
    print(title)
    print(LINE)


def subheading(title):
    print()
    print(title)
    print(SUBLINE)


def money(value):
    if value is None:
        return "UNKNOWN"
    return f"${value:.2f}"


def qty(value):
    if value is None:
        return "N/A"

    value = float(value)

    if value.is_integer():
        return str(int(value))

    return f"{value:.2f}"


def pass_fail(condition):
    return "PASS" if condition else "FAIL"


def main():

    # ============================================================
    # CONTROLLED INTEGRATION INPUT
    # ============================================================

    recipes = [
        {
            "recipe_id": "R001",
            "recipe_name": "Vegetable Tofu Rice Bowl",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 400,
                    "unit": "g",
                },
                {
                    "ingredient_id": "ING002",
                    "ingredient_name": "tofu",
                    "quantity": 250,
                    "unit": "g",
                },
                {
                    "ingredient_id": "ING003",
                    "ingredient_name": "carrot",
                    "quantity": 150,
                    "unit": "g",
                },
            ],
        },

        {
            "recipe_id": "R002",
            "recipe_name": "Tofu Fried Rice",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 400,
                    "unit": "g",
                },
                {
                    "ingredient_id": "ING002",
                    "ingredient_name": "tofu",
                    "quantity": 250,
                    "unit": "g",
                },
                {
                    "ingredient_id": "ING004",
                    "ingredient_name": "onion",
                    "quantity": 200,
                    "unit": "g",
                },
            ],
        },

        {
            "recipe_id": "R003",
            "recipe_name": "Carrot Rice Bowl",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 300,
                    "unit": "g",
                },
                {
                    "ingredient_id": "ING003",
                    "ingredient_name": "carrot",
                    "quantity": 250,
                    "unit": "g",
                },
            ],
        },
    ]

    # ------------------------------------------------------------
    # Pantry before planning
    # ------------------------------------------------------------

    inventory = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 500,
            "unit": "g",
        },
        {
            "ingredient_id": "ING003",
            "ingredient_name": "carrot",
            "quantity": 100,
            "unit": "g",
        },
    ]

    # ------------------------------------------------------------
    # Controlled grocery product catalogue
    # ------------------------------------------------------------

    products = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "price": 3.80,
        },
        {
            "ingredient_id": "ING002",
            "ingredient_name": "tofu",
            "package_quantity": 400,
            "package_unit": "g",
            "price": 2.50,
        },
        {
            "ingredient_id": "ING003",
            "ingredient_name": "carrot",
            "package_quantity": 500,
            "package_unit": "g",
            "price": 2.20,
        },
        {
            "ingredient_id": "ING004",
            "ingredient_name": "onion",
            "package_quantity": 500,
            "package_unit": "g",
            "price": 1.80,
        },
    ]

    initial_budget = 20.00

    # ============================================================
    # HEADER
    # ============================================================

    heading(
        "DAY 5 - MEMBER 4 PLAN-LEVEL GROCERY VERIFICATION"
    )

    print()
    print("Purpose:")
    print(
        "Verify multi-recipe aggregation, pantry subtraction,"
    )
    print(
        "package calculation, duplicate purchase prevention,"
    )
    print(
        "leftovers, pricing, and final plan-level cost."
    )

    # ============================================================
    # 1. SELECTED RECIPES
    # ============================================================

    heading("1. SELECTED RECIPES")

    for index, recipe in enumerate(recipes, start=1):

        print(
            f"\n[{index}] "
            f"{recipe['recipe_id']} - "
            f"{recipe['recipe_name']}"
        )

        for ingredient in recipe["ingredients"]:

            print(
                f"    "
                f"{ingredient['ingredient_name']:<15}"
                f"{qty(ingredient['quantity']):>8} "
                f"{ingredient['unit']}"
            )

    # ============================================================
    # 2. RAW REQUIREMENTS
    # ============================================================

    heading("2. RAW RECIPE REQUIREMENTS")

    raw_count = 0

    for recipe in recipes:

        print(
            f"\n{recipe['recipe_id']} - "
            f"{recipe['recipe_name']}"
        )

        print(
            f"{'Ingredient':<25}"
            f"{'Quantity':>12}  "
            f"{'Unit':<10}"
        )

        print(SUBLINE)

        for ingredient in recipe["ingredients"]:

            raw_count += 1

            print(
                f"{ingredient['ingredient_name']:<25}"
                f"{qty(ingredient['quantity']):>12}  "
                f"{ingredient['unit']:<10}"
            )

    print()
    print(f"Raw ingredient rows: {raw_count}")

    # ============================================================
    # 3. AGGREGATION
    # ============================================================

    aggregated = aggregate_requirements(
        recipes
    )

    heading("3. PLAN-LEVEL AGGREGATION")

    print(
        f"{'Ingredient':<20}"
        f"{'Required':>12}  "
        f"{'Unit':<8}"
        f"{'Recipes':<25}"
    )

    print(SUBLINE)

    for item in aggregated:

        recipe_ids = ", ".join(
            item.get("recipe_ids", [])
        )

        print(
            f"{item['ingredient_name']:<20}"
            f"{qty(item['quantity']):>12}  "
            f"{str(item['unit']):<8}"
            f"{recipe_ids:<25}"
        )

    duplicates_merged = (
        raw_count - len(aggregated)
    )

    print()
    print(
        "Raw ingredient rows      : "
        f"{raw_count}"
    )

    print(
        "Aggregated ingredients   : "
        f"{len(aggregated)}"
    )

    print(
        "Duplicate rows merged    : "
        f"{duplicates_merged}"
    )

    # ============================================================
    # 4. PANTRY
    # ============================================================

    heading("4. INITIAL PANTRY")

    print(
        f"{'Ingredient':<25}"
        f"{'Available':>12}  "
        f"{'Unit':<10}"
    )

    print(SUBLINE)

    for item in inventory:

        print(
            f"{item['ingredient_name']:<25}"
            f"{qty(item['quantity']):>12}  "
            f"{item['unit']:<10}"
        )

    # ============================================================
    # 5. PANTRY SUBTRACTION
    # ============================================================

    purchase_requirements = subtract_inventory(
        aggregated,
        inventory,
    )

    heading("5. INVENTORY / PURCHASE REQUIREMENTS")

    print(
        f"{'Ingredient':<15}"
        f"{'Required':>10}"
        f"{'Available':>12}"
        f"{'Used':>10}"
        f"{'Buy':>10}  "
        f"{'Unit':<8}"
    )

    print(SUBLINE)

    for item in purchase_requirements:

        print(
            f"{item['ingredient_name']:<15}"
            f"{qty(item['required_quantity']):>10}"
            f"{qty(item['inventory_available']):>12}"
            f"{qty(item['inventory_used']):>10}"
            f"{qty(item['purchase_required']):>10}  "
            f"{str(item['unit']):<8}"
        )

    # ============================================================
    # 6. BUILD FINAL BASKET
    # ============================================================

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=inventory,
        product_catalog=products,
    )

    heading("6. PACKAGE CALCULATION")

    for item in basket["items"]:

        print()
        print(item["name"].upper())
        print(SUBLINE)

        print(
            f"Need to buy       : "
            f"{qty(item['required_quantity'])} "
            f"{item['required_unit']}"
        )

        print(
            f"Pantry used       : "
            f"{qty(item['inventory_used'])} "
            f"{item['required_unit']}"
        )

        print(
            f"Package size      : "
            f"{qty(item['package_quantity'])} "
            f"{item['package_unit']}"
        )

        print(
            f"Packages required : "
            f"{item['packages']}"
        )

        print(
            f"Purchased quantity: "
            f"{qty(item['purchased_quantity'])} "
            f"{item['package_unit']}"
        )

        print(
            f"Price per package : "
            f"{money(item['price_per_package'])}"
        )

        print(
            f"Purchase cost     : "
            f"{money(item['purchase_cost'])}"
        )

        print(
            f"Package leftover  : "
            f"{qty(item['leftover_quantity'])} "
            f"{item['package_unit']}"
        )

        print(
            f"Pricing status    : "
            f"{item['pricing_status']}"
        )

    # ============================================================
    # 7. FINAL GROCERY BASKET
    # ============================================================

    heading("7. FINAL PLAN GROCERY BASKET")

    print(
        f"{'Ingredient':<15}"
        f"{'Package':>12}"
        f"{'Qty':>8}"
        f"{'Each':>12}"
        f"{'Cost':>12}"
        f"{'Leftover':>12}"
    )

    print(SUBLINE)

    for item in basket["items"]:

        package_text = (
            f"{qty(item['package_quantity'])}"
            f"{item['package_unit']}"
        )

        leftover_text = (
            f"{qty(item['leftover_quantity'])}"
            f"{item['package_unit']}"
        )

        print(
            f"{item['name']:<15}"
            f"{package_text:>12}"
            f"{item['packages']:>8}"
            f"{money(item['price_per_package']):>12}"
            f"{money(item['purchase_cost']):>12}"
            f"{leftover_text:>12}"
        )

    print()
    print(
        f"Known grocery cost : "
        f"{money(basket['known_cost'])}"
    )

    print(
        f"All items priced   : "
        f"{basket['all_items_priced']}"
    )

    print(
        f"Unpriced items     : "
        f"{basket['unpriced_items']}"
    )

    # ============================================================
    # 8. COST SUMMARY
    # ============================================================

    cost_summary = build_cost_summary(
        basket,
        initial_budget=initial_budget,
    )

    heading("8. COST SUMMARY")

    print(
        f"Initial budget     : "
        f"{money(cost_summary['initial_budget'])}"
    )

    print(
        f"Known grocery cost : "
        f"{money(cost_summary['known_grocery_cost'])}"
    )

    print(
        f"Remaining          : "
        f"{money(cost_summary['remaining'])}"
    )

    print(
        f"All items priced   : "
        f"{cost_summary['all_items_priced']}"
    )

    # ============================================================
    # 9. EXPECTED VALUES
    # ============================================================

    #
    # Expected aggregation:
    #
    # Rice:
    #   400 + 400 + 300 = 1100g
    #   pantry = 500g
    #   buy = 600g
    #   package = 1000g
    #   packages = 1
    #   cost = $3.80
    #   leftover = 400g
    #
    # Tofu:
    #   250 + 250 = 500g
    #   package = 400g
    #   packages = 2
    #   cost = $5.00
    #   purchased = 800g
    #   leftover = 300g
    #
    # Carrot:
    #   150 + 250 = 400g
    #   pantry = 100g
    #   buy = 300g
    #   package = 500g
    #   packages = 1
    #   cost = $2.20
    #   leftover = 200g
    #
    # Onion:
    #   200g
    #   package = 500g
    #   packages = 1
    #   cost = $1.80
    #   leftover = 300g
    #
    # TOTAL:
    #
    #   3.80 + 5.00 + 2.20 + 1.80
    #   = $12.80
    #

    expected = {
        "rice": {
            "required": 600,
            "packages": 1,
            "cost": 3.80,
            "leftover": 400,
        },

        "tofu": {
            "required": 500,
            "packages": 2,
            "cost": 5.00,
            "leftover": 300,
        },

        "carrot": {
            "required": 300,
            "packages": 1,
            "cost": 2.20,
            "leftover": 200,
        },

        "onion": {
            "required": 200,
            "packages": 1,
            "cost": 1.80,
            "leftover": 300,
        },
    }

    basket_by_name = {
        item["name"].lower(): item
        for item in basket["items"]
    }

    # ============================================================
    # 10. AUTOMATIC VERIFICATION
    # ============================================================

    heading("9. AUTOMATIC INTEGRATION CHECKS")

    checks = []

    # ------------------------------------------------------------
    # Multiple recipes
    # ------------------------------------------------------------

    check = len(recipes) == 3

    checks.append(check)

    print(
        f"[{pass_fail(check)}] "
        "Multiple recipes processed"
    )

    # ------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------

    rice_aggregated = next(
        (
            item
            for item in aggregated
            if item["ingredient_name"].lower()
            == "rice"
        ),
        None,
    )

    check = (
        rice_aggregated is not None
        and rice_aggregated["quantity"] == 1100
    )

    checks.append(check)

    print(
        f"[{pass_fail(check)}] "
        "Duplicate rice requirements aggregated "
        "(400 + 400 + 300 = 1100g)"
    )

    # ------------------------------------------------------------
    # Pantry
    # ------------------------------------------------------------

    rice = basket_by_name.get("rice")

    check = (
        rice is not None
        and rice["required_quantity"] == 600
        and rice["inventory_used"] == 500
    )

    checks.append(check)

    print(
        f"[{pass_fail(check)}] "
        "Pantry subtracted before purchase "
        "(1100g - 500g = 600g)"
    )

    # ------------------------------------------------------------
    # Duplicate package prevention
    # ------------------------------------------------------------

    check = (
        rice is not None
        and rice["packages"] == 1
    )

    checks.append(check)

    print(
        f"[{pass_fail(check)}] "
        "No duplicate rice package purchase"
    )

    # ------------------------------------------------------------
    # Verify every expected grocery item
    # ------------------------------------------------------------

    for name, expected_item in expected.items():

        actual = basket_by_name.get(name)

        check = (
            actual is not None
            and actual["required_quantity"]
            == expected_item["required"]
            and actual["packages"]
            == expected_item["packages"]
            and abs(
                actual["purchase_cost"]
                - expected_item["cost"]
            ) < 0.001
            and actual["leftover_quantity"]
            == expected_item["leftover"]
        )

        checks.append(check)

        print(
            f"[{pass_fail(check)}] "
            f"{name.title()} package/cost/"
            f"leftover calculation"
        )

    # ------------------------------------------------------------
    # Pricing completeness
    # ------------------------------------------------------------

    check = (
        basket["all_items_priced"] is True
        and basket["unpriced_items"] == []
    )

    checks.append(check)

    print(
        f"[{pass_fail(check)}] "
        "Pricing completeness correctly reported"
    )

    # ------------------------------------------------------------
    # Total cost
    # ------------------------------------------------------------

    check = (
        abs(
            basket["known_cost"] - 12.80
        )
        < 0.001
    )

    checks.append(check)

    print(
        f"[{pass_fail(check)}] "
        "Final plan grocery cost = $12.80"
    )

    # ------------------------------------------------------------
    # Budget facts
    # ------------------------------------------------------------

    check = (
        abs(
            cost_summary["remaining"] - 7.20
        )
        < 0.001
    )

    checks.append(check)

    print(
        f"[{pass_fail(check)}] "
        "Cost summary remaining amount = $7.20"
    )

    # ============================================================
    # FINAL RESULT
    # ============================================================

    heading("FINAL MEMBER 4 RESULT")

    passed = sum(checks)
    total = len(checks)

    print(
        f"\nChecks passed: {passed}/{total}"
    )

    if all(checks):

        print()
        print(
            "RESULT: PASS"
        )

        print()
        print(
            "Plan-level grocery aggregation is working."
        )

        print(
            "Duplicate ingredients are aggregated before "
            "package purchasing."
        )

        print(
            "Pantry subtraction, package rounding, cost, "
            "and leftovers are working."
        )

    else:

        print()
        print(
            "RESULT: FAIL"
        )

        print()
        print(
            "One or more integration checks failed."
        )

        print(
            "Review the FAIL entries above."
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()