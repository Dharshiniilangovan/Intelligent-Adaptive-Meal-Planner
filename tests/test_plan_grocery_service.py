import pytest

from src.agents.grocery_agent import (
    aggregate_requirements,
    subtract_inventory,
    calculate_packages,
    calculate_package_leftover,
    build_plan_grocery_basket,
    build_cost_summary,
)


# ============================================================
# TEST 1
# Aggregate same ingredient across recipes
# ============================================================


def test_aggregate_same_ingredient():

    recipes = [
        {
            "recipe_id": "R001",
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
            "recipe_id": "R002",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 400,
                    "unit": "g",
                }
            ],
        },
    ]

    result = aggregate_requirements(recipes)

    assert len(result) == 1

    rice = result[0]

    assert rice["ingredient_id"] == "ING001"
    assert rice["quantity"] == 700
    assert rice["unit"] == "g"

    assert set(rice["recipe_ids"]) == {
        "R001",
        "R002",
    }


# ============================================================
# TEST 2
# Multiple different ingredients
# ============================================================


def test_multiple_recipes_and_ingredients():

    recipes = [
        {
            "recipe_id": "R001",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 300,
                    "unit": "g",
                },
                {
                    "ingredient_id": "ING002",
                    "ingredient_name": "tofu",
                    "quantity": 200,
                    "unit": "g",
                },
            ],
        },
        {
            "recipe_id": "R002",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 400,
                    "unit": "g",
                },
                {
                    "ingredient_id": "ING003",
                    "ingredient_name": "carrot",
                    "quantity": 200,
                    "unit": "g",
                },
            ],
        },
        {
            "recipe_id": "R003",
            "ingredients": [
                {
                    "ingredient_id": "ING002",
                    "ingredient_name": "tofu",
                    "quantity": 300,
                    "unit": "g",
                }
            ],
        },
    ]

    result = aggregate_requirements(recipes)

    by_id = {
        item["ingredient_id"]: item
        for item in result
    }

    assert by_id["ING001"]["quantity"] == 700
    assert by_id["ING002"]["quantity"] == 500
    assert by_id["ING003"]["quantity"] == 200


# ============================================================
# TEST 3
# Pantry subtraction
# ============================================================


def test_pantry_subtraction():

    requirements = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 700,
            "unit": "g",
            "recipe_ids": [
                "R001",
                "R002",
            ],
        }
    ]

    inventory = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 500,
            "unit": "g",
        }
    ]

    result = subtract_inventory(
        requirements,
        inventory,
    )

    assert len(result) == 1

    rice = result[0]

    assert rice["required_quantity"] == 700
    assert rice["inventory_available"] == 500
    assert rice["inventory_used"] == 500
    assert rice["purchase_required"] == 200


# ============================================================
# TEST 4
# Pantry completely satisfies requirement
# ============================================================


def test_sufficient_pantry_requires_no_purchase():

    requirements = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 300,
            "unit": "g",
        }
    ]

    inventory = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 500,
            "unit": "g",
        }
    ]

    result = subtract_inventory(
        requirements,
        inventory,
    )

    rice = result[0]

    assert rice["inventory_used"] == 300
    assert rice["purchase_required"] == 0


# ============================================================
# TEST 5
# Zero pantry
# ============================================================


def test_zero_inventory():

    requirements = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 700,
            "unit": "g",
        }
    ]

    result = subtract_inventory(
        requirements,
        [],
    )

    assert result[0]["inventory_used"] == 0
    assert result[0]["purchase_required"] == 700


# ============================================================
# TEST 6
# Package rounding
# ============================================================


def test_package_rounding():

    assert calculate_packages(
        200,
        1000,
    ) == 1

    assert calculate_packages(
        1000,
        1000,
    ) == 1

    assert calculate_packages(
        1001,
        1000,
    ) == 2

    assert calculate_packages(
        2000,
        1000,
    ) == 2


# ============================================================
# TEST 7
# No purchase means zero packages
# ============================================================


def test_zero_requirement_zero_packages():

    assert calculate_packages(
        0,
        1000,
    ) == 0


# ============================================================
# TEST 8
# Package leftover
# ============================================================


def test_package_leftover():

    result = calculate_package_leftover(
        required_quantity=800,
        package_quantity=1000,
        packages=1,
    )

    assert result == 200


# ============================================================
# TEST 9
# Multiple packages leftover
# ============================================================


def test_multiple_package_leftover():

    result = calculate_package_leftover(
        required_quantity=1200,
        package_quantity=1000,
        packages=2,
    )

    assert result == 800


# ============================================================
# TEST 10
# CRITICAL TEST:
# Avoid duplicate package purchases
# ============================================================


def test_no_duplicate_purchase_across_recipes():

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
                    "quantity": 400,
                    "unit": "g",
                }
            ],
        },
    ]

    products = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "price": 3.80,
        }
    ]

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=products,
    )

    assert len(basket["items"]) == 1

    rice = basket["items"][0]

    # Total need:
    # 400g + 400g = 800g
    assert rice["required_quantity"] == 800

    # IMPORTANT:
    # Only ONE 1kg package.
    assert rice["packages"] == 1

    assert rice["purchased_quantity"] == 1000

    assert rice["purchase_cost"] == pytest.approx(
        3.80
    )

    assert rice["leftover_quantity"] == 200


# ============================================================
# TEST 11
# Pantry + package calculation
# ============================================================


def test_pantry_then_package_calculation():

    recipes = [
        {
            "recipe_id": "R001",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 700,
                    "unit": "g",
                }
            ],
        }
    ]

    inventory = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 500,
            "unit": "g",
        }
    ]

    products = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "price": 3.80,
        }
    ]

    basket = build_plan_grocery_basket(
        recipes,
        inventory,
        products,
    )

    rice = basket["items"][0]

    # 700 required - 500 pantry
    assert rice["required_quantity"] == 200

    assert rice["inventory_used"] == 500

    # Still need one whole package.
    assert rice["packages"] == 1

    assert rice["purchase_cost"] == pytest.approx(
        3.80
    )

    # Buy 1000g, only 200g needed.
    assert rice["leftover_quantity"] == 800


# ============================================================
# TEST 12
# Completely pantry-covered ingredient should not
# appear in shopping basket
# ============================================================


def test_no_purchase_when_inventory_is_sufficient():

    recipes = [
        {
            "recipe_id": "R001",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 300,
                    "unit": "g",
                }
            ],
        }
    ]

    inventory = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 500,
            "unit": "g",
        }
    ]

    products = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "price": 3.80,
        }
    ]

    basket = build_plan_grocery_basket(
        recipes,
        inventory,
        products,
    )

    assert basket["items"] == []

    assert basket["known_cost"] == 0

    assert basket["all_items_priced"] is True


# ============================================================
# TEST 13
# Unpriced ingredient
# ============================================================


def test_unpriced_ingredient():

    recipes = [
        {
            "recipe_id": "R001",
            "ingredients": [
                {
                    "ingredient_id": "ING002",
                    "ingredient_name": "tofu",
                    "quantity": 300,
                    "unit": "g",
                }
            ],
        }
    ]

    basket = build_plan_grocery_basket(
        recipe_requirements=recipes,
        inventory=[],
        product_catalog=[],
    )

    assert basket["all_items_priced"] is False

    assert "tofu" in basket["unpriced_items"]

    assert basket["known_cost"] == 0

    assert len(basket["items"]) == 1

    assert (
        basket["items"][0]["pricing_status"]
        == "unpriced"
    )

    assert (
        basket["items"][0]["purchase_cost"]
        is None
    )


# ============================================================
# TEST 14
# Product exists but price missing
# ============================================================


def test_product_with_missing_price():

    recipes = [
        {
            "recipe_id": "R001",
            "ingredients": [
                {
                    "ingredient_id": "ING002",
                    "ingredient_name": "tofu",
                    "quantity": 300,
                    "unit": "g",
                }
            ],
        }
    ]

    products = [
        {
            "ingredient_id": "ING002",
            "ingredient_name": "tofu",
            "package_quantity": 400,
            "package_unit": "g",
            "price": None,
        }
    ]

    basket = build_plan_grocery_basket(
        recipes,
        [],
        products,
    )

    assert basket["all_items_priced"] is False
    assert "tofu" in basket["unpriced_items"]


# ============================================================
# TEST 15
# Complete pricing
# ============================================================


def test_complete_pricing():

    recipes = [
        {
            "recipe_id": "R001",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 800,
                    "unit": "g",
                },
                {
                    "ingredient_id": "ING002",
                    "ingredient_name": "tofu",
                    "quantity": 500,
                    "unit": "g",
                },
            ],
        }
    ]

    products = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "price": 3.80,
        },
        {
            "ingredient_id": "ING002",
            "ingredient_name": "tofu",
            "package_quantity": 400,
            "package_unit": "g",
            "price": 2.50,
        },
    ]

    basket = build_plan_grocery_basket(
        recipes,
        [],
        products,
    )

    assert basket["all_items_priced"] is True
    assert basket["unpriced_items"] == []

    # Rice:
    # 1 × $3.80
    #
    # Tofu:
    # 500g requires 2 × 400g
    # 2 × $2.50 = $5.00
    #
    # Total = $8.80

    assert basket["known_cost"] == pytest.approx(
        8.80
    )


# ============================================================
# TEST 16
# Plan total
# ============================================================


def test_plan_total():

    recipes = [
        {
            "recipe_id": "R001",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 800,
                    "unit": "g",
                }
            ],
        },
        {
            "recipe_id": "R002",
            "ingredients": [
                {
                    "ingredient_id": "ING002",
                    "ingredient_name": "tofu",
                    "quantity": 500,
                    "unit": "g",
                }
            ],
        },
    ]

    products = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "price": 3.80,
        },
        {
            "ingredient_id": "ING002",
            "ingredient_name": "tofu",
            "package_quantity": 400,
            "package_unit": "g",
            "price": 2.50,
        },
    ]

    basket = build_plan_grocery_basket(
        recipes,
        [],
        products,
    )

    assert basket["known_cost"] == pytest.approx(
        8.80
    )


# ============================================================
# TEST 17
# Cost summary
# ============================================================


def test_cost_summary():

    basket = {
        "known_cost": 41.70,
        "all_items_priced": True,
        "unpriced_items": [],
    }

    summary = build_cost_summary(
        basket,
        initial_budget=50,
    )

    assert summary["initial_budget"] == 50.00

    assert (
        summary["known_grocery_cost"]
        == pytest.approx(41.70)
    )

    assert summary["remaining"] == pytest.approx(
        8.30
    )

    assert summary["all_items_priced"] is True


# ============================================================
# TEST 18
# Partial pricing must remain uncertain
# ============================================================


def test_cost_summary_preserves_partial_pricing():

    basket = {
        "known_cost": 37.20,
        "all_items_priced": False,
        "unpriced_items": ["tofu"],
    }

    summary = build_cost_summary(
        basket,
        initial_budget=50,
    )

    assert summary["known_grocery_cost"] == 37.20

    assert summary["remaining"] == pytest.approx(
        12.80
    )

    assert summary["all_items_priced"] is False

    assert summary["unpriced_items"] == [
        "tofu"
    ]


# ============================================================
# TEST 19
# Unit mismatch should not silently calculate cost
# ============================================================



def test_compatible_mass_units_are_priced_correctly():

    recipes = [
        {
            "recipe_id": "R001",
            "ingredients": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 500,
                    "unit": "g",
                }
            ],
        }
    ]

    products = [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "package_quantity": 1,
            "package_unit": "kg",
            "price": 3.80,
        }
    ]

    basket = build_plan_grocery_basket(
        recipes,
        [],
        products,
    )

    assert basket["all_items_priced"] is True
    assert basket["known_cost"] == 3.80
    assert basket["projected_cost"] == 3.80
    assert basket["projected_cost_complete"] is True

    assert len(basket["items"]) == 1

    item = basket["items"][0]

    assert item["packages"] == 1
    assert item["pricing_status"] == "priced"
    assert item["quantity_coverage_verified"] is True

def test_genuinely_incompatible_units_are_not_verified():

    recipes = [
        {
            "recipe_id": "R002",
            "ingredients": [
                {
                    "ingredient_id": "ING002",
                    "ingredient_name": "lettuce",
                    "quantity": 0.5,
                    "unit": "head",
                }
            ],
        }
    ]

    products = [
        {
            "ingredient_id": "ING002",
            "ingredient_name": "lettuce",
            "package_quantity": 150,
            "package_unit": "g",
            "price": 1.50,
        }
    ]

    basket = build_plan_grocery_basket(
        recipes,
        [],
        products,
    )

    assert basket["all_items_priced"] is False
    assert basket["known_cost"] == 0.0

    assert len(basket["items"]) == 1

    item = basket["items"][0]

    assert item["quantity_coverage_verified"] is False
    assert item.get("pricing_status") != "priced"
    assert basket["all_items_priced"] is False
    assert basket["known_cost"] == 0.0