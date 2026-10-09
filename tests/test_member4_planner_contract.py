
"""
Member 4 incremental grocery contract tests.

These tests verify the input/output contract that the
MultiMealPlanner and Manager must use.

No live Tavily or Ollama calls are required here.
"""

from src.agents.grocery_agent import (
    build_plan_grocery_basket,
    calculate_incremental_basket_cost,
)


def test_incremental_contract_for_planner():
    recipes = [
        {
            "recipe_id": "R001",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 400,
                    "unit": "g",
                }
            ],
        },
        {
            "recipe_id": "R002",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 300,
                    "unit": "g",
                }
            ],
        },
    ]

    catalog = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "price": 4.0,
            "total_cost": 4.0,
            "purchase_basis": "exact_quantity",
            "match_status": "matched",
            "quantity_estimated": False,
        }
    ]

    first = calculate_incremental_basket_cost(
        selected_recipe_requirements=[],
        candidate_recipe_requirement=recipes[0],
        inventory=[],
        product_catalog=catalog,
    )

    second = calculate_incremental_basket_cost(
        selected_recipe_requirements=recipes[:1],
        candidate_recipe_requirement=recipes[1],
        inventory=[],
        product_catalog=catalog,
    )

    assert first["projected_incremental_cost"] == 4.0
    assert second["projected_incremental_cost"] == 0.0

    assert first["projected_cost_complete"] is True
    assert second["projected_cost_complete"] is True

    assert "known_incremental_cost" in first
    assert "projected_incremental_cost" in first
    assert "before_basket" in first
    assert "after_basket" in first
    assert "additional_items" in first
    assert "projection_missing" in first

    final_basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=catalog,
    )

    assert final_basket["projected_cost"] == 4.0

    assert round(
        first["projected_incremental_cost"]
        + second["projected_incremental_cost"],
        2,
    ) == final_basket["projected_cost"]


def test_incremental_contract_preserves_original_inventory():
    recipe = {
        "recipe_id": "R001",
        "ingredients": [
            {
                "ingredient_id": "ING001",
                "ingredient_name": "rice",
                "quantity": 400,
                "unit": "g",
            }
        ],
    }

    original_inventory = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 200,
            "unit": "g",
        }
    ]

    catalog = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "price": 4.0,
            "total_cost": 4.0,
            "purchase_basis": "exact_quantity",
            "match_status": "matched",
            "quantity_estimated": False,
        }
    ]

    original_snapshot = [
        dict(item)
        for item in original_inventory
    ]

    result = calculate_incremental_basket_cost(
        selected_recipe_requirements=[],
        candidate_recipe_requirement=recipe,
        inventory=original_inventory,
        product_catalog=catalog,
    )

    assert result["projected_incremental_cost"] == 4.0

    assert original_inventory == original_snapshot

    after = result["after_basket"]

    assert after["items"][0]["inventory_used"] == 200.0
    assert after["items"][0]["packages"] == 1
