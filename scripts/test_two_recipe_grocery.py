
"""
GC1 - Two-recipe combined grocery budget test.

Tests:
1. Both recipes independently.
2. Combined grocery basket.
3. Shared retail package reuse.
4. Incremental purchase cost.
5. Tavily + Ollama projected pricing.
6. S$50 budget feasibility.

Does not modify the Meal Planner or Manager.
"""

import csv
from dataclasses import asdict

from src.agents.grocery_agent import (
    aggregate_requirements,
    build_plan_grocery_basket,
    calculate_incremental_basket_cost,
)
from src.grocery.ollama_fallback_service import (
    OllamaFallbackGroceryService,
)
from src.reasoning.budget_service import (
    get_usable_grocery_cost,
    check_provisional_grocery_budget,
)


RECIPE_IDS = ("R01485", "R21444")
BUDGET = 50.0


def load_recipes():
    recipes = {
        recipe_id: {
            "recipe_id": recipe_id,
            "ingredients": [],
        }
        for recipe_id in RECIPE_IDS
    }

    with open(
        "data/processed/recipe_ingredient_mapping.csv",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            recipe_id = row["recipe_id"]

            if recipe_id not in recipes:
                continue

            recipes[recipe_id]["ingredients"].append({
                "ingredient_id": row["ingredient_id"],
                "ingredient_name": row["ingredient_name"],
                "quantity": row["quantity_per_serving"],
                "unit": row["unit"],
            })

    for recipe_id, recipe in recipes.items():
        if not recipe["ingredients"]:
            raise ValueError(
                f"No ingredients found for {recipe_id}"
            )

    return recipes


def build_product_catalog(recipes):
    requirements = aggregate_requirements(
        list(recipes.values())
    )

    service = OllamaFallbackGroceryService(
        verify_links=False,
    )

    catalog = []

    for requirement in requirements:
        name = requirement["ingredient_name"]

        search_name = (
            "canned chickpeas"
            if name.strip().lower() == "of chickpea"
            else name
        )

        option = service.get_grocery_option(
            ingredient_name=search_name,
            required_quantity=requirement["quantity"],
            unit=requirement["unit"],
            ingredient_id=requirement.get("ingredient_id"),
        )

        product = asdict(option)

        product["ingredient_id"] = requirement.get(
            "ingredient_id"
        )
        product["ingredient_name"] = name
        product["price"] = product.get(
            "price_per_package"
        )

        catalog.append(product)

        print(
            "[CATALOG]",
            name,
            "| Price:",
            product.get("price_per_package"),
            "| Estimated total:",
            product.get("estimated_total_cost"),
            "| Match:",
            product.get("match_status"),
        )

    return catalog


def print_basket(title, basket):
    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)

    for item in basket.get("items", []):
        cost = item.get("effective_purchase_cost")

        if cost is None:
            cost = item.get("purchase_cost")

        if cost is None:
            cost = item.get("estimated_purchase_cost")

        print(
            item.get("name"),
            "| Required:",
            item.get("required_quantity"),
            item.get("required_unit"),
            "| Packages:",
            item.get("packages"),
            "| Cost:",
            cost,
            "| Source:",
            item.get("price_source"),
        )

    print("Known cost:", basket.get("known_cost"))
    print("Projected cost:", basket.get("projected_cost"))
    print(
        "Projection complete:",
        basket.get("projected_cost_complete"),
    )
    print(
        "Missing:",
        basket.get("projection_missing"),
    )


def main():
    recipes = load_recipes()

    print("\nLoading product catalog...")
    catalog = build_product_catalog(recipes)

    first = recipes["R01485"]
    second = recipes["R21444"]

    first_basket = build_plan_grocery_basket(
        recipe_requirements=[first],
        inventory=[],
        product_catalog=catalog,
    )

    second_basket = build_plan_grocery_basket(
        recipe_requirements=[second],
        inventory=[],
        product_catalog=catalog,
    )

    combined_basket = build_plan_grocery_basket(
        recipe_requirements=[first, second],
        inventory=[],
        product_catalog=catalog,
    )

    print_basket(
        "R01485 STANDALONE BASKET",
        first_basket,
    )

    print_basket(
        "R21444 STANDALONE BASKET",
        second_basket,
    )

    print_basket(
        "COMBINED GROCERY BASKET",
        combined_basket,
    )

    incremental = calculate_incremental_basket_cost(
        selected_recipe_requirements=[first],
        candidate_recipe_requirement=second,
        inventory=[],
        product_catalog=catalog,
    )

    print("\n" + "=" * 75)
    print("INCREMENTAL COST")
    print("=" * 75)

    print(
        "Before projected cost:",
        incremental.get("before_projected_cost"),
    )
    print(
        "After projected cost:",
        incremental.get("after_projected_cost"),
    )
    print(
        "Incremental projected cost:",
        incremental.get("projected_incremental_cost"),
    )

    usable_cost = get_usable_grocery_cost(
        combined_basket
    )

    budget_result = check_provisional_grocery_budget(
        projected_cost=usable_cost,
        projected_cost_complete=combined_basket.get(
            "projected_cost_complete",
            False,
        ),
        remaining_budget=BUDGET,
        safety_margin=0.0,
    )

    print("\n" + "=" * 75)
    print("COMBINED BUDGET RESULT")
    print("=" * 75)

    print("Usable cost:", usable_cost)
    print(
        "Budget status:",
        budget_result["budget_status"],
    )
    print(
        "Remaining budget:",
        budget_result["budget_after_purchase"],
    )
    print("Reason:", budget_result["reason"])

    if combined_basket.get("projected_cost_complete"):
        assert usable_cost is not None

        assert abs(
            usable_cost
            - incremental["after_projected_cost"]
        ) < 0.01

        print(
            "\nPASS: Combined basket and incremental "
            "cost calculations agree!"
        )

    else:
        print(
            "\nINCOMPLETE: Some combined grocery "
            "prices are still unavailable."
        )


if __name__ == "__main__":
    main()
