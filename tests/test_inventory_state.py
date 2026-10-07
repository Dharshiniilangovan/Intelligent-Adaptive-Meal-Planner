import pytest

from src.state.inventory_state import (
    add_purchase,
    consume_inventory,
    normalize_inventory,
    pantry_utilization,
)


def test_normalize_user_state_inventory():
    inventory = normalize_inventory({
        "Rice": "500 grams",
        "Oil": "250 ml",
    })

    print("\n=== NORMALIZED INVENTORY ===")
    print(inventory)

    assert inventory == {
        "rice": {"quantity": 500.0, "unit": "g"},
        "oil": {"quantity": 250.0, "unit": "ml"},
    }


def test_consume_inventory_updates_remaining_quantity():
    inventory = normalize_inventory({"Rice": "500 g"})
    updated = consume_inventory(
        inventory,
        [{"ingredient_name": "Rice", "quantity": 300, "unit": "g"}],
    )

    print("\n=== INVENTORY AFTER CONSUMPTION ===")
    print(updated)

    assert updated["rice"]["quantity"] == 200.0
    assert inventory["rice"]["quantity"] == 500.0


def test_consume_inventory_can_convert_kg_to_g():
    inventory = normalize_inventory({"Rice": "1 kg"})
    updated = consume_inventory(
        inventory,
        [{"ingredient_name": "Rice", "quantity": 300, "unit": "g"}],
    )

    print("\n=== KG TO G INVENTORY CONVERSION ===")
    print(updated)

    assert updated["rice"]["unit"] == "kg"
    assert updated["rice"]["quantity"] == pytest.approx(0.7)


def test_consume_inventory_rejects_insufficient_quantity():
    inventory = normalize_inventory({"Rice": "200 g"})

    with pytest.raises(ValueError, match="Insufficient inventory"):
        consume_inventory(
            inventory,
            [{"ingredient_name": "Rice", "quantity": 300, "unit": "g"}],
        )

    print("\n=== INSUFFICIENT INVENTORY ===")
    print("Correctly rejected: requested 300 g, available 200 g")


def test_consume_inventory_rejects_incompatible_units():
    inventory = normalize_inventory({"Rice": "2 count"})

    with pytest.raises(ValueError, match="Incompatible inventory units"):
        consume_inventory(
            inventory,
            [{"ingredient_name": "Rice", "quantity": 100, "unit": "g"}],
        )

    print("\n=== INCOMPATIBLE UNITS ===")
    print("Correctly rejected: count cannot be consumed as grams")


def test_no_negative_inventory():
    inventory = normalize_inventory({"Rice": "200 g"})

    with pytest.raises(ValueError):
        consume_inventory(
            inventory,
            [{"ingredient_name": "Rice", "quantity": 201, "unit": "g"}],
        )

    print("\n=== NO NEGATIVE INVENTORY ===")
    print(inventory)


def test_add_purchase_package_to_existing_inventory():
    inventory = normalize_inventory({"Rice": "200 g"})

    updated = add_purchase(
        inventory,
        {
            "ingredient": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "packages_needed": 1,
        },
    )

    print("\n=== INVENTORY AFTER PURCHASE ===")
    print(updated)

    assert updated["rice"]["quantity"] == 1200.0


def test_purchase_leftover_can_be_reused():
    inventory = normalize_inventory({"Rice": "200 g"})

    after_purchase = add_purchase(
        inventory,
        {
            "ingredient": "rice",
            "package_quantity": 1000,
            "package_unit": "g",
            "packages_needed": 1,
        },
    )

    after_meal = consume_inventory(
        after_purchase,
        [{"ingredient_name": "rice", "quantity": 700, "unit": "g"}],
    )

    print("\n=== LEFTOVER REUSE ===")
    print("After purchase:", after_purchase)
    print("After meal:", after_meal)

    assert after_meal["rice"]["quantity"] == 500.0


def test_pantry_utilization():
    inventory = normalize_inventory({
        "Rice": "500 g",
        "Oil": "250 ml",
    })

    required = [
        {"ingredient_name": "Rice", "quantity": 300, "unit": "g"},
        {"ingredient_name": "Tofu", "quantity": 200, "unit": "g"},
        {"ingredient_name": "Oil", "quantity": 20, "unit": "ml"},
        {"ingredient_name": "Carrot", "quantity": 100, "unit": "g"},
    ]

    utilization = pantry_utilization(required, inventory)

    print("\n=== PANTRY UTILIZATION ===")
    print(f"{utilization * 100:.1f}%")

    assert utilization == 0.5