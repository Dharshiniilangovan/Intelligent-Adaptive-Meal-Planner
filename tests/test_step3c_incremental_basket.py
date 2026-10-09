
import pytest

from src.agents.grocery_agent import (
    calculate_incremental_basket_cost,
)


def recipe(recipe_id, quantity):
    return {
        "recipe_id": recipe_id,
        "ingredients": [
            {
                "ingredient_id": "ING_OIL",
                "ingredient_name": "olive oil",
                "quantity": quantity,
                "unit": "ml",
            }
        ],
    }


PRODUCT_CATALOG = [
    {
        "ingredient_id": "ING_OIL",
        "ingredient_name": "olive oil",
        "package_quantity": 500,
        "package_unit": "ml",
        "price": 5.25,
    }
]


def calculate(selected, candidate, inventory=None):
    return calculate_incremental_basket_cost(
        selected_recipe_requirements=selected,
        candidate_recipe_requirement=candidate,
        inventory=inventory or [],
        product_catalog=PRODUCT_CATALOG,
    )


def test_first_recipe_purchases_one_package():
    result = calculate(
        [],
        recipe("R001", 30),
    )

    assert result["known_incremental_cost"] == 5.25
    assert result["projected_incremental_cost"] == 5.25
    assert result["projected_cost_complete"] is True


def test_second_recipe_reuses_existing_package():
    result = calculate(
        [recipe("R001", 30)],
        recipe("R002", 20),
    )

    assert result["known_incremental_cost"] == 0.0
    assert result["projected_incremental_cost"] == 0.0

    oil = result["additional_items"][0]
    assert oil["additional_packages"] == 0


def test_additional_package_when_required():
    result = calculate(
        [recipe("R001", 400)],
        recipe("R002", 200),
    )

    assert result["known_incremental_cost"] == 5.25
    assert result["projected_incremental_cost"] == 5.25

    oil = result["additional_items"][0]
    assert oil["previous_packages"] == 1
    assert oil["new_packages"] == 2
    assert oil["additional_packages"] == 1


def test_existing_inventory_reduces_purchases():
    inventory = [
        {
            "ingredient_id": "ING_OIL",
            "ingredient_name": "olive oil",
            "quantity": 100,
            "unit": "ml",
        }
    ]

    result = calculate(
        [],
        recipe("R001", 50),
        inventory,
    )

    assert result["known_incremental_cost"] == 0.0
    assert result["projected_incremental_cost"] == 0.0


def test_shared_inventory_not_subtracted_twice():
    inventory = [
        {
            "ingredient_id": "ING_OIL",
            "ingredient_name": "olive oil",
            "quantity": 100,
            "unit": "ml",
        }
    ]

    result = calculate(
        [recipe("R001", 80)],
        recipe("R002", 40),
        inventory,
    )

    # Total requirement = 120 ml.
    # Pantry provides 100 ml.
    # Only 20 ml must be purchased.
    assert result["known_incremental_cost"] == 5.25
    assert result["projected_incremental_cost"] == 5.25


def test_incomplete_projection_is_not_zero():
    result = calculate_incremental_basket_cost(
        selected_recipe_requirements=[],
        candidate_recipe_requirement={
            "recipe_id": "R003",
            "ingredients": [
                {
                    "ingredient_name": "unknown spice",
                    "quantity": 10,
                    "unit": "g",
                }
            ],
        },
        inventory=[],
        product_catalog=[],
    )

    assert result["projected_cost_complete"] is False
    assert result["projected_incremental_cost"] is None
    assert "unknown spice" in result["projection_missing"]


def test_three_recipes_reuse_rice_and_buy_second_package():
    """
    Three recipes require 1200 g of rice.

    Retail package: 1000 g for SGD 4.

    Expected:
    - First recipe: buy one package, SGD 4
    - Second recipe: reuse remaining rice, SGD 0
    - Third recipe: buy another package, SGD 4
    - Final basket: two packages, SGD 8
    """

    from src.agents.grocery_agent import (
        calculate_incremental_basket_cost,
        build_plan_grocery_basket,
    )

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
        {
            "recipe_id": "R003",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 500,
                    "unit": "g",
                }
            ],
        },
    ]

    product_catalog = [
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
            "source_url": "https://www.fairprice.com.sg/",
        }
    ]

    original_inventory = []

    first = calculate_incremental_basket_cost(
        selected_recipe_requirements=[],
        candidate_recipe_requirement=recipes[0],
        inventory=original_inventory,
        product_catalog=product_catalog,
    )

    second = calculate_incremental_basket_cost(
        selected_recipe_requirements=recipes[:1],
        candidate_recipe_requirement=recipes[1],
        inventory=original_inventory,
        product_catalog=product_catalog,
    )

    third = calculate_incremental_basket_cost(
        selected_recipe_requirements=recipes[:2],
        candidate_recipe_requirement=recipes[2],
        inventory=original_inventory,
        product_catalog=product_catalog,
    )

    assert first["projected_cost_complete"] is True
    assert second["projected_cost_complete"] is True
    assert third["projected_cost_complete"] is True

    assert first["projected_incremental_cost"] == 4.0
    assert second["projected_incremental_cost"] == 0.0
    assert third["projected_incremental_cost"] == 4.0

    final_basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=original_inventory,
        product_catalog=product_catalog,
    )

    assert final_basket["projected_cost_complete"] is True
    assert final_basket["projected_cost"] == 8.0

    assert len(final_basket["items"]) == 1

    rice_item = final_basket["items"][0]

    assert rice_item["packages"] == 2

    total_incremental = sum(
        result["projected_incremental_cost"]
        for result in (first, second, third)
    )

    assert round(total_incremental, 2) == 8.0

    assert (
        round(total_incremental, 2)
        == final_basket["projected_cost"]
    )
