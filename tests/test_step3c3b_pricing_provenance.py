
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



from src.agents.grocery_agent import (
    build_plan_grocery_basket,
    calculate_incremental_basket_cost,
)


def _mixed_source_recipes():
    return [
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
                    "ingredient_id": "ING002",
                    "ingredient_name": "hoisin sauce",
                    "quantity": 100,
                    "unit": "g",
                }
            ],
        },
        {
            "recipe_id": "R003",
            "ingredients": [
                {
                    "ingredient_id": "ING003",
                    "ingredient_name": "unknown ingredient",
                    "quantity": 100,
                    "unit": "g",
                }
            ],
        },
    ]


def _mixed_source_products():
    return [
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
        },
        {
            "ingredient_id": "ING002",
            "ingredient_name": "hoisin sauce",
            "package_quantity": 250,
            "package_unit": "g",
            "price": 3.5,
            "total_cost": None,
            "estimated_total_cost": 3.5,
            "purchase_basis": "llm_estimated_package",
            "match_status": "estimated_no_retail_match",
            "quantity_estimated": True,
            "source_url": None,
        },
    ]


def test_mixed_sources_keep_verified_and_estimated_separate():
    recipes = _mixed_source_recipes()[:2]

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=_mixed_source_products(),
    )

    assert basket["projected_cost_complete"] is True
    assert basket["known_cost"] == 4.0
    assert basket["projected_cost"] == 7.5

    assert basket["all_items_priced"] is False

    items = {
        item["name"]: item
        for item in basket["items"]
    }

    rice = items["rice"]
    hoisin = items["hoisin sauce"]

    assert rice["pricing_status"] == "priced"
    assert rice["price_source"] == "retail"
    assert rice["purchase_cost"] == 4.0

    assert hoisin["pricing_status"] == "estimated"
    assert hoisin["price_source"] == "ollama_estimate"
    assert hoisin["purchase_cost"] is None
    assert hoisin["estimated_purchase_cost"] == 3.5

    assert "hoisin sauce" in basket["unpriced_items"]


def test_unknown_price_never_becomes_zero():
    basket = build_plan_grocery_basket(
        recipe_requirements=_mixed_source_recipes(),
        inventory=[],
        product_catalog=_mixed_source_products(),
    )

    assert basket["known_cost"] == 4.0

    assert basket["projected_cost_complete"] is False
    assert basket["projected_cost"] is None

    assert "unknown ingredient" in basket["projection_missing"]
    assert "unknown ingredient" in basket["unpriced_items"]

    items = {
        item["name"]: item
        for item in basket["items"]
    }

    unknown = items["unknown ingredient"]

    assert unknown["purchase_cost"] is None
    assert unknown["estimated_purchase_cost"] is None
    assert unknown["pricing_status"] == "unpriced"


def test_incremental_mixed_sources_preserve_projection_completeness():
    recipes = _mixed_source_recipes()
    products = _mixed_source_products()

    first = calculate_incremental_basket_cost(
        selected_recipe_requirements=[],
        candidate_recipe_requirement=recipes[0],
        inventory=[],
        product_catalog=products,
    )

    second = calculate_incremental_basket_cost(
        selected_recipe_requirements=recipes[:1],
        candidate_recipe_requirement=recipes[1],
        inventory=[],
        product_catalog=products,
    )

    third = calculate_incremental_basket_cost(
        selected_recipe_requirements=recipes[:2],
        candidate_recipe_requirement=recipes[2],
        inventory=[],
        product_catalog=products,
    )

    assert first["projected_cost_complete"] is True
    assert first["known_incremental_cost"] == 4.0
    assert first["projected_incremental_cost"] == 4.0

    assert second["projected_cost_complete"] is True
    assert second["known_incremental_cost"] == 0.0
    assert second["projected_incremental_cost"] == 3.5

    assert third["projected_cost_complete"] is False
    assert third["projected_incremental_cost"] is None

    assert "unknown ingredient" in third["projection_missing"]

    # The known-cost increment must not include
    # an invented price for the unknown ingredient.
    assert third["known_incremental_cost"] == 0.0
