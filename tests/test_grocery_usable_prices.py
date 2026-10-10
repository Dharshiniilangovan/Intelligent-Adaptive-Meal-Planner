
import pytest

from src.agents.grocery_agent import (
    build_plan_grocery_basket,
)


def test_tavily_and_ollama_prices_are_usable():
    recipes = [
        {
            "recipe_id": "TEST001",
            "ingredients": [
                {
                    "ingredient_id": "ING_TEST_A",
                    "ingredient_name": "test ingredient a",
                    "quantity": 100,
                    "unit": "g",
                },
                {
                    "ingredient_id": "ING_TEST_B",
                    "ingredient_name": "test ingredient b",
                    "quantity": 100,
                    "unit": "g",
                },
            ],
        }
    ]

    catalog = [
        {
            "ingredient_id": "ING_TEST_A",
            "ingredient_name": "test ingredient a",
            "package_quantity": 200,
            "package_unit": "g",
            "price": 2.0,
            "purchase_basis": "exact_quantity",
            "match_status": "matched",
        },
        {
            "ingredient_id": "ING_TEST_B",
            "ingredient_name": "test ingredient b",
            "package_quantity": 200,
            "package_unit": "g",
            "price": 3.0,
            "estimated_total_cost": 3.0,
            "purchase_basis": "llm_estimated_package",
            "match_status": "estimated_no_retail_match",
        },
    ]

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=catalog,
    )

    assert basket["projected_cost_complete"] is True
    assert basket["projected_cost"] == pytest.approx(5.0)
    assert basket["unpriced_items"] == []
    assert basket["all_items_priced"] is False
    assert basket["all_items_have_usable_cost"] is True

    assert all(
        item["effective_purchase_cost"] is not None
        for item in basket["items"]
    )
