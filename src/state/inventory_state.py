"""Stateful inventory utilities for Day-5 meal planning.

Member 3 ownership:
    - evolving pantry/inventory state
    - consuming ingredients after a meal is selected
    - adding purchased packages back into inventory
    - simple pantry-utilization calculation

The module is deterministic and reusable.  It does not read a specific
user file and it does not perform grocery searches or final feasibility
reasoning.
"""

from __future__ import annotations

import copy
import math
from typing import Any

from src.grocery.units import to_base


# ---------------------------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------------------------

UNIT_ALIASES = {
    "gram": "g",
    "grams": "g",
    "gm": "g",
    "gms": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "kgs": "kg",
    "milliliter": "ml",
    "milliliters": "ml",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "tablespoons": "tablespoon",
    "tbsp": "tablespoon",
    "teaspoons": "teaspoon",
    "tsp": "teaspoon",
    "counts": "count",
    "pcs": "piece",
    "pieces": "piece",
}


def normalize_name(name: Any) -> str:
    """Normalize an ingredient name for dictionary lookup."""
    return " ".join(str(name or "").strip().lower().split())


def normalize_unit(unit: Any) -> str:
    """Normalize unit spelling without inventing conversions."""
    value = str(unit or "").strip().lower()
    return UNIT_ALIASES.get(value, value)


def _parse_quantity(value: Any) -> tuple[float | None, str]:
    """Parse values such as ``'200 grams'`` or structured quantity/unit data."""
    if isinstance(value, dict):
        quantity = value.get("quantity")
        unit = value.get("unit", "")
    else:
        text = str(value or "").strip()
        if not text:
            return None, ""
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            return None, ""
        quantity, unit = parts

    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        return None, normalize_unit(unit)

    return quantity, normalize_unit(unit)


def normalize_inventory(initial_inventory: Any) -> dict[str, dict[str, Any]]:
    """Convert common User-State/Manager pantry formats into one inventory format.

    Supported inputs:

    Dictionary::

        {
            "Rice": "500 grams",
            "Oil": "250 ml"
        }

    Structured dictionary::

        {
            "rice": {"quantity": 500, "unit": "g"}
        }

    Structured list::

        [
            {"ingredient_name": "rice", "quantity": 500, "unit": "g"}
        ]
    """
    inventory: dict[str, dict[str, Any]] = {}

    if initial_inventory is None:
        return inventory

    if isinstance(initial_inventory, dict):
        for raw_name, value in initial_inventory.items():
            name = normalize_name(raw_name)
            if not name:
                continue

            quantity, unit = _parse_quantity(value)
            inventory[name] = {
                "quantity": quantity,
                "unit": unit,
            }
        return inventory

    if isinstance(initial_inventory, list):
        for item in initial_inventory:
            if not isinstance(item, dict):
                continue

            name = normalize_name(item.get("ingredient_name", item.get("name")))
            if not name:
                continue

            inventory[name] = {
                "quantity": _as_float_or_none(item.get("quantity")),
                "unit": normalize_unit(item.get("unit", "")),
            }
        return inventory

    raise ValueError("initial_inventory must be a dictionary, list, or None")


def _as_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _convertible_quantity(quantity: float, unit: str) -> tuple[float, str] | None:
    """Convert a quantity to the project's common base unit where supported."""
    converted = to_base(float(quantity), normalize_unit(unit))
    if converted is None:
        return None
    return float(converted[0]), normalize_unit(converted[1])


def _subtract(
    available_quantity: float,
    available_unit: str,
    required_quantity: float,
    required_unit: str,
) -> float:
    """Return remaining quantity, validating unit compatibility."""
    available_unit = normalize_unit(available_unit)
    required_unit = normalize_unit(required_unit)

    if available_unit == required_unit:
        if available_quantity + 1e-9 < required_quantity:
            raise ValueError("Insufficient inventory")
        return max(0.0, available_quantity - required_quantity)

    available_base = _convertible_quantity(
        available_quantity,
        available_unit,
    )
    required_base = _convertible_quantity(
        required_quantity,
        required_unit,
    )

    if available_base is None or required_base is None:
        raise ValueError(
            f"Incompatible inventory units: {available_unit} vs {required_unit}"
        )

    if available_base[1] != required_base[1]:
        raise ValueError(
            f"Incompatible inventory units: {available_unit} vs {required_unit}"
        )

    if available_base[0] + 1e-9 < required_base[0]:
        raise ValueError("Insufficient inventory")

    remaining_base = max(0.0, available_base[0] - required_base[0])

    # Convert remaining base quantity back to the inventory's original unit.
    if available_base[1] == "g" and available_unit == "kg":
        return remaining_base / 1000.0
    if available_base[1] == "ml" and available_unit == "l":
        return remaining_base / 1000.0

    # Most other supported conversions can retain the base quantity.
    return remaining_base


def consume_inventory(
    inventory: dict[str, dict[str, Any]],
    required_ingredients: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Consume the quantities required by a selected recipe.

    A deep copy is returned so callers can keep the previous plan state.
    Inventory is never allowed to become negative.  An insufficient quantity
    or incompatible unit raises ``ValueError`` instead of silently assuming
    a conversion.
    """
    if not isinstance(inventory, dict):
        raise ValueError("inventory must be a dictionary")

    if not isinstance(required_ingredients, list):
        raise ValueError("required_ingredients must be a list")

    updated = copy.deepcopy(inventory)

    for ingredient in required_ingredients:
        if not isinstance(ingredient, dict):
            continue

        name = normalize_name(
            ingredient.get("ingredient_name", ingredient.get("name"))
        )
        if not name or name not in updated:
            raise ValueError(f"Ingredient not available in inventory: {name or '<unknown>'}")

        required_quantity = _as_float_or_none(ingredient.get("quantity", ingredient.get("required_quantity")))
        required_unit = normalize_unit(ingredient.get("unit", ingredient.get("required_unit", "")))

        if required_quantity is None:
            raise ValueError(f"Required quantity is unknown for {name}")

        item = updated[name]
        available_quantity = _as_float_or_none(item.get("quantity"))
        available_unit = normalize_unit(item.get("unit", ""))

        if available_quantity is None or not available_unit:
            raise ValueError(f"Inventory quantity/unit is unknown for {name}")

        item["quantity"] = _subtract(
            available_quantity,
            available_unit,
            required_quantity,
            required_unit,
        )
        item["unit"] = available_unit

    return updated


def _purchase_name(purchase: dict[str, Any]) -> str:
    return normalize_name(
        purchase.get("ingredient_name", purchase.get("ingredient", purchase.get("name")))
    )


def add_purchase(
    inventory: dict[str, dict[str, Any]],
    purchase: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Add a purchased grocery package to inventory.

    Preferred Grocery Agent fields are:

        ingredient / ingredient_name
        package_quantity
        package_unit
        packages_needed

    A fallback ``quantity`` + ``unit`` pair is also supported for simpler tests.
    """
    if not isinstance(inventory, dict):
        raise ValueError("inventory must be a dictionary")

    if not isinstance(purchase, dict):
        raise ValueError("purchase must be a dictionary")

    name = _purchase_name(purchase)
    if not name:
        raise ValueError("purchase ingredient name is required")

    package_quantity = _as_float_or_none(purchase.get("package_quantity"))
    package_unit = normalize_unit(purchase.get("package_unit", ""))
    packages_needed = purchase.get("packages_needed", 1)

    try:
        packages_needed = int(packages_needed)
    except (TypeError, ValueError):
        packages_needed = 1

    if package_quantity is None:
        package_quantity = _as_float_or_none(purchase.get("quantity"))
        package_unit = normalize_unit(purchase.get("unit", package_unit))

    if package_quantity is None or not package_unit:
        raise ValueError(f"Purchase quantity/unit is unknown for {name}")

    if packages_needed <= 0:
        raise ValueError("packages_needed must be greater than zero")

    added_quantity = package_quantity * packages_needed

    updated = copy.deepcopy(inventory)

    if name not in updated:
        updated[name] = {
            "quantity": added_quantity,
            "unit": package_unit,
        }
        return updated

    current = updated[name]
    current_quantity = _as_float_or_none(current.get("quantity"))
    current_unit = normalize_unit(current.get("unit", ""))

    if current_quantity is None or not current_unit:
        raise ValueError(f"Existing inventory quantity/unit is unknown for {name}")

    if current_unit == package_unit:
        current["quantity"] = current_quantity + added_quantity
        return updated

    current_base = _convertible_quantity(current_quantity, current_unit)
    added_base = _convertible_quantity(added_quantity, package_unit)

    if current_base is None or added_base is None or current_base[1] != added_base[1]:
        raise ValueError(
            f"Incompatible purchase units: {current_unit} vs {package_unit}"
        )

    combined_base = current_base[0] + added_base[0]

    if current_base[1] == "g" and current_unit == "kg":
        current["quantity"] = combined_base / 1000.0
    elif current_base[1] == "ml" and current_unit == "l":
        current["quantity"] = combined_base / 1000.0
    else:
        current["quantity"] = combined_base

    return updated


def pantry_utilization(
    required_ingredients: list[dict[str, Any]],
    inventory: dict[str, dict[str, Any]],
) -> float:
    """Calculate simple presence-based pantry utilization.

    This intentionally follows the Day-4 MVP definition:
        ingredients available in inventory / total required ingredients
    """
    if not required_ingredients:
        return 0.0

    inventory_names = set(inventory)
    available_count = 0

    for ingredient in required_ingredients:
        name = normalize_name(
            ingredient.get("ingredient_name", ingredient.get("name"))
        )
        if name in inventory_names:
            available_count += 1

    return round(available_count / len(required_ingredients), 4)
