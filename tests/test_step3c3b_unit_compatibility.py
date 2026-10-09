
import pytest

from src.agents.grocery_agent import build_plan_grocery_basket


@pytest.mark.parametrize(
    "ingredient,required,required_unit,package,package_unit,price",
    [
        ("olive oil", 2, "tablespoon", 500, "ml", 5.25),
        ("rice", 500, "g", 1, "kg", 4.00),
        ("milk", 0.5, "l", 1000, "ml", 3.00),
        ("olive oil", 3, "teaspoon", 500, "ml", 5.25),
    ],
)
def test_compatible_units_calculate_packages(
    ingredient,
    required,
    required_unit,
    package,
    package_unit,
    price,
):
    result = build_plan_grocery_basket(
        recipe_requirements=[
            {
                "recipe_id": "R001",
                "ingredients": [
                    {
                        "ingredient_name": ingredient,
                        "quantity": required,
                        "unit": required_unit,
                    }
                ],
            }
        ],
        inventory=[],
        product_catalog=[
            {
                "ingredient_name": ingredient,
                "package_quantity": package,
                "package_unit": package_unit,
                "price": price,
            }
        ],
    )

    assert len(result["items"]) == 1

    item = result["items"][0]

    assert item["packages"] == 1
    assert item["quantity_coverage_verified"] is True
    assert item["pricing_status"] == "priced"
    assert result["known_cost"] == pytest.approx(price)
    assert result["projected_cost"] == pytest.approx(price)
    assert result["projected_cost_complete"] is True


def test_incompatible_units_remain_provisional():
    result = build_plan_grocery_basket(
        recipe_requirements=[
            {
                "recipe_id": "R002",
                "ingredients": [
                    {
                        "ingredient_name": "butter lettuce",
                        "quantity": 0.5,
                        "unit": "head",
                    }
                ],
            }
        ],
        inventory=[],
        product_catalog=[
            {
                "ingredient_name": "butter lettuce",
                "package_quantity": 150,
                "package_unit": "g",
                "price": 1.50,
                "purchase_basis": "llm_estimated_package",
                "match_status": "estimated_no_retail_match",
                "estimated_total_cost": 1.50,
            }
        ],
    )

    item = result["items"][0]

    assert item["quantity_coverage_verified"] is False
    assert item["purchase_basis"] == "minimum_retail_package"
    assert result["known_cost"] == 0.0
    assert result["projected_cost"] == pytest.approx(1.50)
    assert result["projected_cost_complete"] is True
