
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
