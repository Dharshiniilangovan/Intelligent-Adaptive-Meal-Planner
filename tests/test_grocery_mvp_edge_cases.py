
import pytest

from src.agents.grocery_agent import (
    aggregate_requirements,
    build_plan_grocery_basket,
    subtract_inventory,
)


def test_unresolved_units_do_not_crash():
    recipes = [
        {
            "recipe_id": "R1",
            "ingredients": [
                {
                    "ingredient_name": "mystery vegetable",
                    "quantity": 2,
                    "unit": "tablespoon",
                }
            ],
        },
        {
            "recipe_id": "R2",
            "ingredients": [
                {
                    "ingredient_name": "mystery vegetable",
                    "quantity": 1,
                    "unit": "count",
                }
            ],
        },
    ]

    aggregated = aggregate_requirements(recipes)

    assert len(aggregated) == 2
    assert all(
        item["normalization_status"] == "unresolved"
        for item in aggregated
    )


def test_missing_product_price_is_not_free():
    recipes = [
        {
            "recipe_id": "R1",
            "ingredients": [
                {
                    "ingredient_name": "rice",
                    "quantity": 500,
                    "unit": "g",
                }
            ],
        }
    ]

    catalog = [
        {
            "ingredient_name": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "price": None,
        }
    ]

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=catalog,
    )

    assert basket["known_cost"] == 0
    assert basket["all_items_priced"] is False
    assert basket["projected_cost_complete"] is False
    assert "rice" in basket["unpriced_items"]


def test_estimated_carrot_not_verified():
    recipes = [
        {
            "recipe_id": "R1",
            "ingredients": [
                {
                    "ingredient_name": "carrot",
                    "quantity": 1,
                    "unit": "count",
                }
            ],
        }
    ]

    catalog = [
        {
            "ingredient_name": "carrot",
            "package_quantity": 500,
            "package_unit": "g",
            "price": 1.50,
        }
    ]

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=catalog,
    )

    assert basket["known_cost"] == 0
    assert basket["projected_cost"] == 1.50
    assert basket["all_items_priced"] is False
    assert basket["projected_cost_complete"] is True
    assert basket["items"][0]["conversion_status"] == "estimated"

def test_unresolved_units_not_counted_as_verified():
    recipes = [
        {
            "recipe_id": "R1",
            "ingredients": [
                {
                    "ingredient_name": "mystery vegetable",
                    "quantity": 2,
                    "unit": "tablespoon",
                }
            ],
        },
        {
            "recipe_id": "R2",
            "ingredients": [
                {
                    "ingredient_name": "mystery vegetable",
                    "quantity": 1,
                    "unit": "count",
                }
            ],
        },
    ]

    catalog = [
        {
            "ingredient_name": "mystery vegetable",
            "package_quantity": 500,
            "package_unit": "g",
            "price": 2.00,
        }
    ]

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=catalog,
    )

    assert basket["known_cost"] == 0
    assert basket["all_items_priced"] is False
    assert basket["projected_cost_complete"] is False
    assert basket["projected_cost"] is None

    assert len(basket["unresolved_requirements"]) == 2

    assert all(
        item["pricing_status"] == "unresolved_conversion"
        for item in basket["items"]
    )


def test_to_taste_requirement_is_preserved_separately():
    recipes = [
        {
            "recipe_id": "R1",
            "ingredients": [
                {
                    "ingredient_id": "ING3046",
                    "ingredient_name": "table salt",
                    "quantity": "required",
                    "unit": "to taste",
                }
            ],
        }
    ]

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=[],
    )

    assert len(basket["qualitative_requirements"]) == 1

    instruction = basket["qualitative_requirements"][0]
    assert instruction["ingredient_name"] == "table salt"
    assert instruction["quantity"] == "required"
    assert instruction["unit"] == "to taste"
    assert instruction["recipe_ids"] == ["R1"]

    # Qualitative instructions must not become numeric purchases.
    assert len(basket["items"]) == 1

    item = basket["items"][0]

    assert item["ingredient_id"] == "ING3046"
    assert item["name"] == "table salt"
    assert item["required_quantity"] is None
    assert item["required_unit"] == "to taste"
    assert item["purchase_basis"] == "qualitative_requirement"
    assert item["status"] == "quantity_unknown"
    assert item["packages"] is None
    assert item["purchase_cost"] is None
    assert item["estimated_purchase_cost"] is None
    assert item["quantity_coverage_verified"] is False

    # Grocery cost remains incomplete.
    assert basket["projected_cost_complete"] is False
    assert "table salt" in basket["unpriced_items"]

def test_insufficient_inventory_creates_grocery_shortage():
    recipes = [{
        "recipe_id": "R1",
        "ingredients": [{
            "ingredient_name": "rice",
            "quantity": 300,
            "unit": "g",
        }],
    }]

    inventory = [{
        "ingredient_name": "rice",
        "quantity": 200,
        "unit": "g",
    }]

    requirements = aggregate_requirements(recipes)

    result = subtract_inventory(
        requirements,
        inventory,
    )

    assert result[0]["required_quantity"] == 300
    assert result[0]["inventory_used"] == 200
    assert result[0]["purchase_required"] == 100

def test_preserved_volume_does_not_verify_mass_package():
    recipes = [{
        "recipe_id": "R30871",
        "ingredients": [{
            "ingredient_id": "ING0452",
            "ingredient_name": "broccoli floret",
            "quantity": 0.5,
            "unit": "cup",
            "normalized_quantity_per_serving": 125.0,
            "normalized_unit": "ml",
            "conversion_status": "volume_preserved_no_density",
        }],
    }]

    products = [{
        "ingredient_name": "broccoli floret",
        "package_quantity": 250,
        "package_unit": "g",
        "price": 2.50,
    }]

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=products,
    )

    item = next(
        item for item in basket["items"]
        if item["name"] == "broccoli floret"
    )

    assert item["required_quantity"] == 125.0
    assert item["required_unit"] == "ml"
    assert item["conversion_status"] == "volume_preserved_no_density"
    assert item["quantity_coverage_verified"] is False

    # Package is provisional, not verified.
    assert item["package_conversion_status"] != "exact"

    print("Preserved-volume package coverage PASSED")
def test_dataset_factor_broccoli_pantry_subtraction():
    from src.agents.grocery_agent import (
        aggregate_requirements,
        subtract_inventory,
    )

    recipes = [{
        "recipe_id": "R12345",
        "ingredients": [{
            "ingredient_name": "broccoli",
            "quantity": 300,
            "unit": "g",
        }],
    }]

    pantry = [{
        "ingredient_name": "broccoli",
        "quantity": 0.5,
        "unit": "head",
    }]

    requirements = aggregate_requirements(recipes)

    result = subtract_inventory(
        requirements,
        pantry,
    )

    item = result[0]

    assert item["required_quantity"] == 300
    assert item["inventory_used"] == 150
    assert item["purchase_required"] == 150
    assert item["inventory_conversion_estimated"] is True
    assert item["inventory_conversion_unresolved"] is False