
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

    assert updated["rice"]["quantity"] == pytest.approx(200.0)
    assert inventory["rice"]["quantity"] == 500.0


def test_consume_inventory_can_convert_kg_to_g():
    inventory = normalize_inventory({"Rice": "1 kg"})

    updated = consume_inventory(
        inventory,
        [{"ingredient_name": "Rice", "quantity": 300, "unit": "g"}],
    )

    assert updated["rice"]["unit"] == "kg"
    assert updated["rice"]["quantity"] == pytest.approx(0.7)


def test_consume_inventory_rejects_insufficient_quantity():
    inventory = normalize_inventory({"Rice": "200 g"})

    with pytest.raises(ValueError, match="Insufficient inventory"):
        consume_inventory(
            inventory,
            [{"ingredient_name": "Rice", "quantity": 300, "unit": "g"}],
        )


def test_consume_inventory_rejects_incompatible_units():
    inventory = normalize_inventory({"Rice": "2 count"})

    with pytest.raises(ValueError, match="Incompatible inventory units"):
        consume_inventory(
            inventory,
            [{"ingredient_name": "Rice", "quantity": 100, "unit": "g"}],
        )


def test_no_negative_inventory():
    inventory = normalize_inventory({"Rice": "200 g"})
    original = {name: item.copy() for name, item in inventory.items()}

    with pytest.raises(ValueError):
        consume_inventory(
            inventory,
            [{"ingredient_name": "Rice", "quantity": 201, "unit": "g"}],
        )

    assert inventory == original


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

    assert updated["rice"]["quantity"] == pytest.approx(1200.0)


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

    assert after_meal["rice"]["quantity"] == pytest.approx(500.0)


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

    assert pantry_utilization(required, inventory) == 0.5


def test_consume_inventory_converts_ml_back_to_cups():
    inventory = normalize_inventory({"Oil": "1 cup"})

    updated = consume_inventory(
        inventory,
        [{"ingredient_name": "Oil", "quantity": 120, "unit": "ml"}],
    )

    assert updated["oil"]["quantity"] == pytest.approx(0.5)
    assert updated["oil"]["unit"] == "cup"
    assert inventory["oil"]["quantity"] == 1.0


def test_consume_inventory_converts_ml_back_to_tablespoons():
    inventory = normalize_inventory({"Oil": "2 tablespoons"})

    updated = consume_inventory(
        inventory,
        [{"ingredient_name": "Oil", "quantity": 15, "unit": "ml"}],
    )

    assert updated["oil"]["quantity"] == pytest.approx(1.0)
    assert updated["oil"]["unit"] == "tablespoon"
    assert inventory["oil"]["quantity"] == 2.0


@pytest.mark.parametrize(
    (
        "inventory_quantity",
        "inventory_unit",
        "required_quantity",
        "required_unit",
        "expected",
    ),
    [
        (1, "kg", 250, "g", 0.75),
        (2, "litres", 500, "ml", 1.5),
        (1, "cup", 60, "ml", 0.75),
        (2, "tablespoons", 5, "ml", pytest.approx(5 / 3)),
        (3, "count", 1, "piece", 2.0),
    ],
)
def test_consume_inventory_supports_shared_unit_conversions(
    inventory_quantity,
    inventory_unit,
    required_quantity,
    required_unit,
    expected,
):
    inventory = normalize_inventory({
        "test ingredient": f"{inventory_quantity} {inventory_unit}"
    })

    updated = consume_inventory(
        inventory,
        [{
            "ingredient_name": "test ingredient",
            "quantity": required_quantity,
            "unit": required_unit,
        }],
    )

    assert updated["test ingredient"]["quantity"] == pytest.approx(expected)


@pytest.mark.parametrize(
    (
        "inventory_quantity",
        "inventory_unit",
        "required_quantity",
        "required_unit",
    ),
    [
        (1, "kg", 1, "count"),
        (500, "g", 100, "ml"),
        (1, "cup", 1, "piece"),
        (1, "pinch", 1, "g"),
        (1, "unknown_unit", 1, "g"),
    ],
)
def test_consume_inventory_rejects_unsupported_conversions(
    inventory_quantity,
    inventory_unit,
    required_quantity,
    required_unit,
):
    inventory = normalize_inventory({
        "test ingredient": {
            "quantity": inventory_quantity,
            "unit": inventory_unit,
        }
    })
    original = {
        name: item.copy()
        for name, item in inventory.items()
    }

    with pytest.raises(ValueError, match="Incompatible inventory units"):
        consume_inventory(
            inventory,
            [{
                "ingredient_name": "test ingredient",
                "quantity": required_quantity,
                "unit": required_unit,
            }],
        )

    assert inventory == original


def test_consume_green_onion_bunch_using_estimated_mass():
    inventory = normalize_inventory({"green onion": "1 bunch"})

    updated = consume_inventory(
        inventory,
        [{
            "ingredient_name": "green onion",
            "quantity": 2,
            "unit": "tablespoon",
        }],
    )

    # Provisional estimates: 100 g/bunch and 6 g/tablespoon.
    assert updated["green onion"]["quantity"] == pytest.approx(0.88)
    assert updated["green onion"]["unit"] == "bunch"
    assert updated["green onion"]["conversion_status"] == "estimated"

    # Consumption must not mutate the original inventory.
    assert inventory["green onion"]["quantity"] == 1.0
    assert "conversion_status" not in inventory["green onion"]


def test_failed_estimated_consumption_does_not_mutate_inventory():
    inventory = normalize_inventory({"green onion": "0.1 bunch"})
    original = {
        name: item.copy()
        for name, item in inventory.items()
    }

    with pytest.raises(ValueError, match="Insufficient inventory"):
        consume_inventory(
            inventory,
            [{
                "ingredient_name": "green onion",
                "quantity": 2,
                "unit": "tablespoon",
            }],
        )

    assert inventory == original


@pytest.mark.parametrize("name,grams_per_cup", [
    ("masa harina", 120), ("black beans", 172), ("lettuce", 36),
])
def test_r32630_cup_requirements_from_gram_inventory(name, grams_per_cup):
    inventory = normalize_inventory({name: "500 g"})
    result = consume_inventory(inventory, [
        {"ingredient_name": name, "quantity": 0.25, "unit": "cup"}
    ])
    assert result[name]["quantity"] == pytest.approx(500 - grams_per_cup * 0.25)
    assert result[name]["conversion_status"] == "estimated"
    assert inventory[name]["quantity"] == 500
