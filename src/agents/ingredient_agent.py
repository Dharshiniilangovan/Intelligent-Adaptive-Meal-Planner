from __future__ import annotations

import math
import re
from typing import Any, Dict, List

from scripts.mapping_retrieval_query import get_recipe_ingredients

from src.pantry.pantry_service import (
    fetch_recipe_ingredients,
    filter_ingredient_list,
)


# ============================================================
# HELPERS
# ============================================================

def normalize_name(name: Any) -> str:
    """Normalize ingredient names for matching."""
    if name is None:
        return ""

    return " ".join(
        str(name).strip().lower().split()
    )


def parse_quantity_unit(value: Any) -> tuple[Any, str]:
    """
    Parse pantry availability values such as:

        "200 grams"
        "5 counts"
        "2 tablespoon"

    Returns:
        (quantity, unit)
    """
    if isinstance(value, dict):
        return (
            value.get("quantity"),
            str(value.get("unit", "")).strip().lower(),
        )

    if value is None:
        return None, ""

    text = str(value).strip()

    match = re.match(
        r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(.*)\s*$",
        text,
    )

    if not match:
        return None, ""

    quantity_text = match.group(1)
    unit = match.group(2).strip().lower()

    try:
        quantity = float(quantity_text)

        # Keep integers as integers where possible.
        if quantity.is_integer():
            quantity = int(quantity)
    except ValueError:
        quantity = None

    return quantity, unit


def normalize_unit(unit: Any) -> str:
    """Normalize common unit spellings without doing quantity conversion."""
    unit = str(unit or "").strip().lower()

    aliases = {
        "grams": "g",
        "gram": "g",
        "kgs": "kg",
        "kilograms": "kg",
        "kilogram": "kg",
        "milliliters": "ml",
        "milliliter": "ml",
        "liters": "l",
        "liter": "l",
        "counts": "count",
        "pieces": "piece",
        "piece": "piece",
        "tablespoons": "tablespoon",
        "tbsp": "tablespoon",
        "tablespoon": "tablespoon",
        "teaspoons": "teaspoon",
        "tsp": "teaspoon",
        "teaspoon": "teaspoon",
    }

    return aliases.get(unit, unit)


def pantry_to_dict(
    pantry_input: Any,
) -> Dict[str, Dict[str, Any]]:
    """
    Convert Manager/User-State pantry data into the dictionary
    format expected by the existing pantry_service.

    Supported input formats:

    1. User State / Manager dictionary:
       {
           "Tomatoes": "5 counts",
           "Cheese": "200 grams"
       }

    2. Structured dictionary:
       {
           "tomatoes": {
               "quantity": 5,
               "unit": "count"
           }
       }

    3. Structured list:
       [
           {
               "ingredient_id": "ING001",
               "ingredient_name": "rice",
               "quantity": 500,
               "unit": "g"
           }
       ]
    """

    pantry_dict: Dict[str, Dict[str, Any]] = {}

    if pantry_input is None:
        return pantry_dict

    # --------------------------------------------------------
    # Case 1 / 2: dictionary input
    # --------------------------------------------------------
    if isinstance(pantry_input, dict):

        for ingredient_name, value in pantry_input.items():

            name = normalize_name(ingredient_name)

            if not name:
                continue

            quantity, unit = parse_quantity_unit(value)

            pantry_dict[name] = {
                "quantity": quantity,
                "unit": normalize_unit(unit),
            }

        return pantry_dict

    # --------------------------------------------------------
    # Case 3: list input
    # --------------------------------------------------------
    if isinstance(pantry_input, list):

        for item in pantry_input:

            if not isinstance(item, dict):
                continue

            name = normalize_name(
                item.get("ingredient_name")
            )

            if not name:
                continue

            pantry_dict[name] = {
                "quantity": item.get("quantity"),
                "unit": normalize_unit(
                    item.get("unit", "")
                ),
            }

        return pantry_dict

    return pantry_dict


# ============================================================
# REQUIRED INGREDIENTS
# ============================================================


def _missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(math.isnan(value))
    except TypeError:
        return False


def requirements_from_rows(
    recipe_id: str,
    rows: Any,
) -> List[Dict[str, Any]]:
    """
    Convert one recipe's normalized-KB rows (a DataFrame) into
    required-ingredient records, one per row, in KB order.

    A recipe that lists the same ingredient twice (e.g. red and green
    bell pepper -> "bell pepper") keeps both occurrences. Each gets a
    stable occurrence_id "<recipe_id>#<row position in recipe>".
    """

    recipe_id = str(recipe_id).strip().upper()

    def clean(value: Any) -> Any:
        return None if _missing(value) else value

    required: List[Dict[str, Any]] = []

    for position, (_, row) in enumerate(rows.iterrows()):

        unit = row["unit"]

        required.append({
            "occurrence_id": f"{recipe_id}#{position}",
            "recipe_id": recipe_id,
            "ingredient_id": clean(row["ingredient_id"]),
            "ingredient_name": normalize_name(row["ingredient_name"]),
            "alias_name": clean(row["alias_name"]),

            # Original recipe values. A missing unit stays empty;
            # it is never filled in.
            "quantity": clean(row["quantity_per_serving"]),
            "unit": "" if _missing(unit) else normalize_unit(unit),
            # KB unit spelling exactly as stored (e.g. "gram"), used when
            # a requirement is passed on in its original unit.
            "kb_unit": "" if _missing(unit) else str(unit).strip().lower(),

            # Pre-normalized dataset values
            "normalized_quantity_per_serving": clean(
                row["normalized_quantity_per_serving"]
            ),
            "normalized_unit": clean(
                row["normalized_unit"]
            ),
            "conversion_status": clean(
                row["conversion_status"]
            ),
            "normalized_weight": clean(
                row["normalized_weight"]
            ),
        })

    return required


def get_required_ingredients(
    recipe_id: str,
) -> List[Dict[str, Any]]:
    """
    Retrieve recipe ingredients from the normalized KB.

    Preserve original and normalized measurements
    for Grocery Agent and Inventory State.
    """

    recipe_id = str(recipe_id).strip().upper()

    return requirements_from_rows(
        recipe_id,
        get_recipe_ingredients(recipe_id),
    )

# ============================================================
# PANTRY USED
# ============================================================

def get_pantry_used(
    required_ingredients: List[Dict[str, Any]],
    pantry: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Return recipe ingredients that are present
    in the user's pantry.

    This is presence-based for the MVP.
    """

    pantry_used: List[Dict[str, Any]] = []

    for ingredient in required_ingredients:

        name = normalize_name(
            ingredient.get("ingredient_name")
        )

        if name not in pantry:
            continue

        pantry_item = pantry[name]

        pantry_used.append(
            {
                "ingredient_id": ingredient.get(
                    "ingredient_id"
                ),
                "ingredient_name": ingredient.get(
                    "ingredient_name"
                ),
                "required_quantity": ingredient.get(
                    "quantity"
                ),
                "available_quantity": pantry_item.get(
                    "quantity"
                ),
                "unit": ingredient.get("unit"),
            }
        )

    return pantry_used


# ============================================================
# MISSING INGREDIENTS
# ============================================================

def get_missing_ingredients(
    required_ingredients_dict: Dict[str, Dict[str, Any]],
    pantry: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Reuse the existing pantry service to calculate
    ingredients that need to be purchased.
    """

    return filter_ingredient_list(
        pantry,
        required_ingredients_dict,
    )


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def build_missing_ingredients(
    recipe_id: str,
    required_ingredients: List[Dict[str, Any]],
    pantry: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Candidate-level shopping needs, computed with the same aggregation
    and pantry subtraction as the final Grocery Agent basket.

    - Repeated occurrences of an ingredient are summed when their
      normalized units are compatible and kept as separate entries
      when they are not (they are never overwritten by name).
    - Pantry stock is subtracted through the shared conversion rules.
    - Qualitative and unresolved-quantity requirements stay visible
      with quantity None; no amount is derived for them.

    "quantity"/"unit" are what GroceryService searches with: the
    original KB unit when the whole requirement is still needed and
    all its occurrences share that unit, otherwise the normalized
    unit. "normalized_quantity"/"normalized_unit" always hold the
    authoritative shortage used by the final basket.
    """
    from src.agents.grocery_agent import (
        _identity_keys,
        aggregate_requirements,
        collect_qualitative_requirements,
        collect_unresolved_quantity_requirements,
        subtract_inventory,
    )

    recipes = [{"recipe_id": recipe_id, "ingredients": required_ingredients}]
    occurrences = {
        ingredient.get("occurrence_id"): ingredient
        for ingredient in required_ingredients
    }
    pantry_list = [
        {"ingredient_name": name, "quantity": item.get("quantity"),
         "unit": item.get("unit")}
        for name, item in (pantry or {}).items()
    ]
    coverage = subtract_inventory(
        aggregate_requirements(recipes), pantry_list
    )

    missing: List[Dict[str, Any]] = []

    for record in coverage:
        shortage = record["purchase_required"]
        if shortage <= 1e-9:
            continue

        sources = record["source_requirements"]
        originals = [occurrences.get(s["occurrence_id"]) or {} for s in sources]
        kb_units = {o.get("kb_unit") for o in originals}
        original_amounts = [_as_float(s["quantity"]) for s in sources]

        quantity, unit = shortage, record["unit"]
        if (
            abs(shortage - record["required_quantity"]) <= 1e-9
            and len(kb_units) == 1
            and "" not in kb_units
            and None not in kb_units
            and None not in original_amounts
        ):
            quantity = sum(original_amounts)
            unit = kb_units.pop()

        name = record["ingredient_name"]
        pantry_item = (pantry or {}).get(normalize_name(name))
        if record.get("inventory_conversion_unresolved"):
            status = "unit_mismatch"
        elif pantry_item is not None and _as_float(pantry_item.get("quantity")) is None:
            status = "quantity_unknown"
        else:
            status = "missing"

        missing.append({
            "ingredient_id": record["ingredient_id"],
            "ingredient_name": name,
            "quantity": quantity,
            "unit": unit,
            "normalized_quantity": shortage,
            "normalized_unit": record["unit"],
            "required_quantity": record["required_quantity"],
            "pantry_used": record["inventory_used"],
            "conversion_status": record["conversion_status"],
            "normalization_status": record["normalization_status"],
            "inventory_conversion_estimated": record.get(
                "inventory_conversion_estimated", False
            ),
            "occurrence_ids": [s["occurrence_id"] for s in sources],
            "status": status,
        })

    def existing_entry(record):
        keys = _identity_keys(record)
        return next(
            (item for item in missing if _identity_keys(item) & keys),
            None,
        )

    # Unquantifiable needs: one entry per ingredient, or noted on the
    # measurable entry when one exists (as in the final basket).
    for record in collect_unresolved_quantity_requirements(recipes):
        existing = existing_entry(record)
        if existing is not None:
            existing["additional_unquantified_requirement"] = True
            existing["occurrence_ids"] += record["occurrence_ids"]
            continue
        missing.append({
            "ingredient_id": record["ingredient_id"],
            "ingredient_name": record["ingredient_name"],
            "quantity": None,
            "unit": "",
            "original_quantity": record["source_requirements"][0]["quantity"],
            "unresolved_reasons": record["reasons"],
            "occurrence_ids": record["occurrence_ids"],
            "status": (
                "unit_unknown"
                if "missing_unit" in record["reasons"]
                else "quantity_unknown"
            ),
        })

    for record in collect_qualitative_requirements(recipes):
        existing = existing_entry(record)
        if existing is not None:
            existing["additional_unquantified_requirement"] = True
            existing["occurrence_ids"] += record["occurrence_ids"]
            continue
        missing.append({
            "ingredient_id": record["ingredient_id"],
            "ingredient_name": record["ingredient_name"],
            "quantity": None,
            "unit": record["unit"],
            "instruction": record["instruction"],
            "occurrence_ids": record["occurrence_ids"],
            "status": "quantity_unknown",
        })

    return missing


def format_missing_ingredients(
    missing: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Convert existing pantry-service output
    into Ingredient Agent output format.
    """

    result: List[Dict[str, Any]] = []

    for ingredient_name, data in missing.items():

        result.append(
            {
                "ingredient_id": data.get(
                    "ingredient_id"
                ),
                "ingredient_name": ingredient_name,
                "quantity": data.get(
                    "quantity"
                ),
                "unit": data.get(
                    "unit"
                ),
                "status": data.get(
                    "status",
                    "missing",
                ),
            }
        )

    return result


# ============================================================
# INGREDIENT AGENT
# ============================================================

class IngredientAgent:
    """
    Day 4 Member 3 Ingredient Agent.

    Responsibilities:

        Recipe ID
            ↓
        Required ingredients
            ↓
        Pantry comparison
            ↓
        Missing ingredients
            ↓
        Structured output

    The Manager passes:
        recipe_id
        pantry
    """

    name = "ingredient"

    def run(
        self,
        *,
        recipe_id: str,
        pantry: Any,
    ) -> Dict[str, Any]:
        """
        Main Ingredient Agent interface.

        Called by Manager as:

            agent.run(
                recipe_id=recipe_id,
                pantry=pantry
            )
        """

        # ----------------------------------------------------
        # Validate recipe_id
        # ----------------------------------------------------

        if not recipe_id:
            return {
                "agent": self.name,
                "status": "failed",
                "data": {},
                "warnings": [],
                "errors": [
                    "recipe_id is required"
                ],
            }

        recipe_id = str(
            recipe_id
        ).strip().upper()

        # ----------------------------------------------------
        # Normalize pantry input
        # ----------------------------------------------------

        pantry_data = pantry_to_dict(
            pantry
        )

        # ----------------------------------------------------
        # Retrieve recipe ingredients (one record per KB row)
        # ----------------------------------------------------

        try:

            required_ingredients = get_required_ingredients(
                recipe_id
            )

        except (
            ValueError,
            FileNotFoundError,
        ) as error:

            return {
                "agent": self.name,
                "status": "failed",
                "data": {
                    "recipe_id": recipe_id
                },
                "warnings": [],
                "errors": [
                    str(error)
                ],
            }

        # ----------------------------------------------------
        # No recipe found
        # ----------------------------------------------------

        if not required_ingredients:

            return {
                "agent": self.name,
                "status": "failed",
                "data": {
                    "recipe_id": recipe_id
                },
                "warnings": [],
                "errors": [
                    f"No ingredients found for {recipe_id}"
                ],
            }

        # ----------------------------------------------------
        # Pantry used
        # ----------------------------------------------------

        pantry_used = get_pantry_used(
            required_ingredients,
            pantry_data,
        )

        # ----------------------------------------------------
        # Missing ingredients: same requirements and pantry
        # subtraction as the final Grocery Agent basket.
        # ----------------------------------------------------

        missing_ingredients = build_missing_ingredients(
            recipe_id,
            required_ingredients,
            pantry_data,
        )

        # ----------------------------------------------------
        # Unsupported / uncertain items
        # ----------------------------------------------------

        unsupported_items: List[Dict[str, Any]] = []

        for item in missing_ingredients:

            status = item.get("status")

            if status in {"unit_mismatch", "unit_unknown"}:
               unsupported_items.append(item)

        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------

        if unsupported_items:
            status = "partial"
        else:
            status = "success"

        # ----------------------------------------------------
        # Final AgentResult
        # ----------------------------------------------------

        return {
            "agent": self.name,
            "status": status,
            "data": {
                "recipe_id": recipe_id,
                "required_ingredients": required_ingredients,
                "pantry_used": pantry_used,
                "missing_ingredients": missing_ingredients,
                "unsupported_items": unsupported_items,
            },
            "warnings": [],
            "errors": [],
        }