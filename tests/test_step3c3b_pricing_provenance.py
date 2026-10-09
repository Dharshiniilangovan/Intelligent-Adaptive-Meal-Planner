
import pytest

from src.agents.grocery_agent import build_plan_grocery_basket


def make_basket(product):
    return build_plan_grocery_basket(
        recipe_requirements=[
            {
                "recipe_id": "R001",
                "ingredients": [
                    {
                        "ingredient_name": "olive oil",
                        "quantity": 30,
                        "unit": "ml",
                    }
                ],
            }
        ],
        inventory=[],
        product_catalog=[product],
    )


def product(**overrides):
    result = {
        "ingredient_name": "olive oil",
        "package_quantity": 500,
        "package_unit": "ml",
        "price": 5.25,
    }
    result.update(overrides)
    return result


def test_retail_exact_quantity():
    basket = make_basket(product(
        total_cost=5.25,
        purchase_basis="exact_quantity",
        match_status="matched",
        quantity_estimated=False,
    ))

    assert basket["known_cost"] == pytest.approx(5.25)
    assert basket["projected_cost"] == pytest.approx(5.25)
    assert basket["all_items_priced"] is True
    assert basket["items"][0]["price_source"] == "retail"


def test_ollama_estimate_is_not_verified():
    basket = make_basket(product(
        total_cost=None,
        estimated_total_cost=5.25,
        purchase_basis="llm_estimated_package",
        match_status="estimated_no_retail_match",
        quantity_estimated=True,
    ))

    assert basket["known_cost"] == 0.0
    assert basket["projected_cost"] == pytest.approx(5.25)
    assert basket["all_items_priced"] is False
    assert basket["items"][0]["price_source"] == "ollama_estimate"


def test_retail_quantity_estimate_is_not_verified():
    basket = make_basket(product(
        total_cost=None,
        estimated_total_cost=5.25,
        purchase_basis="estimated_quantity",
        match_status="matched_estimated_quantity",
        quantity_estimated=True,
    ))

    assert basket["known_cost"] == 0.0
    assert basket["projected_cost"] == pytest.approx(5.25)
    assert basket["all_items_priced"] is False
    assert (
        basket["items"][0]["price_source"]
        == "retail_estimated_quantity"
    )


def test_missing_price_is_incomplete():
    basket = make_basket(product(
        price=None,
        total_cost=None,
        estimated_total_cost=None,
    ))

    assert basket["known_cost"] == 0.0
    assert basket["projected_cost"] is None
    assert basket["projected_cost_complete"] is False
    assert "olive oil" in basket["projection_missing"]
