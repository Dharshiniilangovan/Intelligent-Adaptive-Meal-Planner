
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


@pytest.mark.parametrize(
    "ingredient,quantity,unit,package_unit,expected_leftover",
    [
        ("butter lettuce", 0.5, "head", "head", 0.5),
        ("green onion", 2, "tablespoon", "bunch", 0.88),
        ("lime", 0.5, "wedge", "pcs", 1 - 4 / 65),
    ],
)
def test_ingredient_specific_package_estimates_remain_provisional(
    ingredient,
    quantity,
    unit,
    package_unit,
    expected_leftover,
):
    result = build_plan_grocery_basket(
        recipe_requirements=[
            {
                "recipe_id": "R_ESTIMATE",
                "ingredients": [
                    {
                        "ingredient_name": ingredient,
                        "quantity": quantity,
                        "unit": unit,
                    }
                ],
            }
        ],
        inventory=[],
        product_catalog=[
            {
                "ingredient_name": ingredient,
                "package_quantity": 1,
                "package_unit": package_unit,
                "price": 2.00,
            }
        ],
    )

    assert len(result["items"]) == 1
    item = result["items"][0]

    # One package should cover each estimated requirement.
    assert item["packages"] == 1

    # The conversion must remain provisional.
    assert item["quantity_coverage_verified"] is False
    assert item["pricing_status"] == "estimated"
    assert item["purchase_cost"] is None
    assert item["estimated_purchase_cost"] == pytest.approx(2.00)

    # Package leftovers are estimated in package units.
    assert item["leftover_quantity"] == pytest.approx(
        expected_leftover
    )

    # Estimated purchases affect projection, not known cost.
    assert result["known_cost"] == pytest.approx(0.0)
    assert result["projected_cost"] == pytest.approx(2.00)

    assert any(
        "estimated ingredient-specific conversion" in warning
        for warning in result["warnings"]
    )


def test_pantry_fully_covers_requirement_and_skips_purchase():
    result = build_plan_grocery_basket(
        recipe_requirements=[
            {
                "recipe_id": "R_PANTRY_FULL",
                "ingredients": [
                    {
                        "ingredient_name": "rice",
                        "quantity": 200,
                        "unit": "g",
                    }
                ],
            }
        ],
        inventory=[
            {
                "ingredient_name": "Rice",
                "quantity": 500,
                "unit": "g",
            }
        ],
        product_catalog=[
            {
                "ingredient_name": "rice",
                "package_quantity": 1,
                "package_unit": "kg",
                "price": 4.00,
            }
        ],
    )

    # Pantry stock covers the recipe requirement.
    assert result["items"] == []
    assert result["known_cost"] == pytest.approx(0.0)
    assert result["projected_cost"] == pytest.approx(0.0)


def test_pantry_partially_covers_requirement_across_mass_units():
    result = build_plan_grocery_basket(
        recipe_requirements=[
            {
                "recipe_id": "R_PANTRY_PARTIAL",
                "ingredients": [
                    {
                        "ingredient_name": "rice",
                        "quantity": 1200,
                        "unit": "g",
                    }
                ],
            }
        ],
        inventory=[
            {
                "ingredient_name": "Rice",
                "quantity": 1,
                "unit": "kg",
            }
        ],
        product_catalog=[
            {
                "ingredient_name": "rice",
                "package_quantity": 1,
                "package_unit": "kg",
                "price": 4.00,
            }
        ],
    )

    assert len(result["items"]) == 1
    item = result["items"][0]

    # 1 kg from the pantry covers 1,000 g of the 1,200 g requirement.
    assert item["inventory_used"] == pytest.approx(1000.0)
    assert item["required_quantity"] == pytest.approx(200.0)
    assert item["packages"] == 1
    assert item["purchase_cost"] == pytest.approx(4.00)
