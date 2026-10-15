
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


def test_consume_inventory_handles_insufficient_quantity():
    inventory = normalize_inventory({"Rice": "200 g"})

    updated = consume_inventory(
        inventory,
        [
            {
                "ingredient_name": "Rice",
                "quantity": 300,
                "unit": "g",
            }
        ],
    )

    assert updated["rice"]["quantity"] == 0
    assert inventory["rice"]["quantity"] == 200
    
def test_consume_inventory_rejects_incompatible_units():
    inventory = normalize_inventory({"Rice": "2 count"})

    with pytest.raises(ValueError, match="Incompatible inventory units"):
        consume_inventory(
            inventory,
            [{"ingredient_name": "Rice", "quantity": 100, "unit": "g"}],
        )


def test_no_negative_inventory():
    inventory = normalize_inventory({"Rice": "200 g"})

    updated = consume_inventory(
        inventory,
        [
            {
                "ingredient_name": "Rice",
                "quantity": 500,
                "unit": "g",
            }
        ],
    )

    assert updated["rice"]["quantity"] == 0
    assert updated["rice"]["quantity"] >= 0

    # Original inventory remains unchanged.
    assert inventory["rice"]["quantity"] == 200


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


def test_insufficient_estimated_consumption_does_not_mutate_input():
    inventory = normalize_inventory({
        "green onion": "0.1 bunch"
    })

    updated = consume_inventory(
        inventory,
        [
            {
                "ingredient_name": "green onion",
                "quantity": 20,
                "unit": "g",
            }
        ],
    )

    assert updated["green onion"]["quantity"] == pytest.approx(0.0)
    assert updated["green onion"]["conversion_status"] == "estimated"

    # Original inventory must remain unchanged.
    assert inventory["green onion"]["quantity"] == pytest.approx(0.1)

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


# ---------------------------------------------------------------------------
# Ingredient-specific unit reconciliation (shared KB lookup)
# ---------------------------------------------------------------------------

from src.agents.grocery_agent import subtract_inventory
from src.state.inventory_state import _subtract


def test_subtract_same_unit():
    assert _subtract(500, "g", 200, "g", "rice") == (pytest.approx(300.0), "normalized")


def test_subtract_kg_to_g_keeps_pantry_unit():
    remaining, status = _subtract(1, "kg", 250, "g", "rice")
    assert remaining == pytest.approx(0.75)
    assert status == "normalized"


def test_subtract_broccoli_grams_from_head():
    remaining, status = _subtract(1, "head", 150, "g", "broccoli")
    assert remaining == pytest.approx(0.5)
    assert status == "estimated"


def test_consume_broccoli_half_head_shortage_clamped():
    inventory = {"broccoli": {"quantity": 0.5, "unit": "heads"}}
    updated = consume_inventory(
        inventory,
        [{"ingredient_name": "Broccoli", "quantity": 300, "unit": "grams"}],
    )
    assert updated["broccoli"]["quantity"] == pytest.approx(0.0)
    assert updated["broccoli"]["conversion_status"] == "estimated"


def test_subtract_egg_grams_from_piece_clamped():
    remaining, status = _subtract(1, "piece", 100, "g", "egg")
    assert remaining == 0.0
    assert status == "estimated"


def test_subtract_insufficient_stock_clamps_to_zero():
    remaining, _ = _subtract(100, "g", 400, "g", "rice")
    assert remaining == 0.0


def test_subtract_volume_to_mass_stays_unresolved():
    with pytest.raises(ValueError, match="Incompatible inventory units"):
        _subtract(100, "g", 125, "ml", "broccoli florets")


def test_consume_kb_conversion_does_not_mutate_original():
    inventory = {"broccoli": {"quantity": 1.0, "unit": "head"}}
    updated = consume_inventory(
        inventory,
        [{"ingredient_name": "broccoli", "quantity": 150, "unit": "g"}],
    )
    assert inventory == {"broccoli": {"quantity": 1.0, "unit": "head"}}
    assert updated["broccoli"]["quantity"] == pytest.approx(0.5)
    assert updated["broccoli"]["unit"] == "head"


@pytest.mark.parametrize(
    "name, pantry_qty, pantry_unit, required_g",
    [
        ("broccoli", 0.5, "head", 300),
        ("broccoli", 1, "head", 150),
        ("egg", 1, "piece", 100),
    ],
)
def test_grocery_and_inventory_consume_same_amount(
    name, pantry_qty, pantry_unit, required_g
):
    grocery = subtract_inventory(
        [{"ingredient_name": name, "quantity": required_g, "unit": "g"}],
        [{"ingredient_name": name, "quantity": pantry_qty, "unit": pantry_unit}],
    )[0]

    remaining, _ = _subtract(pantry_qty, pantry_unit, required_g, "g", name)
    grams_per_unit = {"broccoli": 300.0, "egg": 50.0}[name]
    inventory_consumed_g = (pantry_qty - remaining) * grams_per_unit

    assert grocery["inventory_used"] == pytest.approx(inventory_consumed_g)
    assert grocery["purchase_required"] == pytest.approx(
        required_g - inventory_consumed_g
    )
