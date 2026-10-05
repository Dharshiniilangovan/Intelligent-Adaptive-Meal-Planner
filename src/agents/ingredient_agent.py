from __future__ import annotations

from typing import Any, Dict, List
import json

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


def pantry_list_to_dict(
    pantry_list: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Convert Manager pantry list into the dictionary format
    expected by the existing pantry_service.

    Input:

    [
        {
            "ingredient_id": "ING001",
            "ingredient_name": "rice",
            "quantity": 500,
            "unit": "g"
        }
    ]

    Output:

    {
        "rice": {
            "quantity": 500,
            "unit": "g"
        }
    }
    """

    pantry_dict = {}

    for item in pantry_list:

        if not isinstance(item, dict):
            continue

        name = normalize_name(
            item.get("ingredient_name")
        )

        if not name:
            continue

        pantry_dict[name] = {
            "quantity": item.get("quantity"),
            "unit": str(
                item.get("unit", "")
            ).strip().lower()
        }

    return pantry_dict


# ============================================================
# REQUIRED INGREDIENTS
# ============================================================

def get_required_ingredients(
    recipe_id: str
) -> List[Dict[str, Any]]:
    """
    Retrieve recipe ingredients using the existing
    recipe-ingredient mapping tool.
    """

    ingredients = fetch_recipe_ingredients(
        recipe_id
    )

    required = []

    for ingredient_name, data in ingredients.items():

        required.append({

            "ingredient_id":
                data.get("ingredient_id"),

            "ingredient_name":
                ingredient_name,

            "alias_name":
                data.get("alias_name"),

            "quantity":
                data.get("quantity"),

            "unit":
                data.get("unit")
        })

    return required


# ============================================================
# PANTRY USED
# ============================================================

def get_pantry_used(
    required_ingredients: List[Dict[str, Any]],
    pantry: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Return recipe ingredients that are present
    in the user's pantry.

    This is presence-based for the MVP.
    """

    pantry_used = []

    for ingredient in required_ingredients:

        name = normalize_name(
            ingredient.get("ingredient_name")
        )

        if name not in pantry:
            continue

        pantry_item = pantry[name]

        pantry_used.append({

            "ingredient_id":
                ingredient.get(
                    "ingredient_id"
                ),

            "ingredient_name":
                ingredient.get(
                    "ingredient_name"
                ),

            "required_quantity":
                ingredient.get(
                    "quantity"
                ),

            "available_quantity":
                pantry_item.get(
                    "quantity"
                ),

            "unit":
                ingredient.get(
                    "unit"
                )
        })

    return pantry_used


# ============================================================
# MISSING INGREDIENTS
# ============================================================

def get_missing_ingredients(
    required_ingredients_dict: Dict[str, Dict[str, Any]],
    pantry: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """
    Reuse the existing pantry service to calculate
    the ingredients that need to be purchased.
    """

    return filter_ingredient_list(
        pantry,
        required_ingredients_dict
    )


def format_missing_ingredients(
    missing: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Convert the existing pantry-service output
    into the Ingredient Agent output format.
    """

    result = []

    for ingredient_name, data in missing.items():

        result.append({

            "ingredient_id":
                data.get(
                    "ingredient_id"
                ),

            "ingredient_name":
                ingredient_name,

            "quantity":
                data.get(
                    "quantity"
                ),

            "unit":
                data.get(
                    "unit"
                ),

            "status":
                data.get(
                    "status",
                    "missing"
                )
        })

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
    """

    name = "ingredient"

    def run(
        self,
        manager_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Main Ingredient Agent interface.

        Expected input:

        {
            "recipe_id": "R03943",
            "pantry": [
                {
                    "ingredient_id": "ING001",
                    "ingredient_name": "rice",
                    "quantity": 500,
                    "unit": "g"
                }
            ]
        }
        """

        # ----------------------------------------------------
        # Validate input
        # ----------------------------------------------------

        if not isinstance(
            manager_input,
            dict
        ):

            return {
                "agent": self.name,
                "status": "failed",
                "data": {},
                "warnings": [],
                "errors": [
                    "Manager input must be a dictionary"
                ]
            }

        recipe_id = manager_input.get(
            "recipe_id"
        )

        if not recipe_id:

            return {
                "agent": self.name,
                "status": "failed",
                "data": {},
                "warnings": [],
                "errors": [
                    "recipe_id is required"
                ]
            }

        recipe_id = str(
            recipe_id
        ).strip().upper()

        pantry_input = manager_input.get(
            "pantry",
            []
        )

        if not isinstance(
            pantry_input,
            list
        ):

            return {
                "agent": self.name,
                "status": "failed",
                "data": {},
                "warnings": [],
                "errors": [
                    "pantry must be a list"
                ]
            }

        # ----------------------------------------------------
        # Convert pantry to existing service format
        # ----------------------------------------------------

        pantry = pantry_list_to_dict(
            pantry_input
        )

        # ----------------------------------------------------
        # Retrieve required ingredients
        # ----------------------------------------------------

        try:

            recipe_ingredients = (
                fetch_recipe_ingredients(
                    recipe_id
                )
            )

        except (
            ValueError,
            FileNotFoundError
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
                ]
            }

        # ----------------------------------------------------
        # No recipe found
        # ----------------------------------------------------

        if not recipe_ingredients:

            return {
                "agent": self.name,
                "status": "failed",
                "data": {
                    "recipe_id": recipe_id
                },
                "warnings": [],
                "errors": [
                    f"No ingredients found for {recipe_id}"
                ]
            }

        # ----------------------------------------------------
        # Required ingredient list
        # ----------------------------------------------------

        required_ingredients = (
            get_required_ingredients(
                recipe_id
            )
        )

        # ----------------------------------------------------
        # Pantry used
        # ----------------------------------------------------

        pantry_used = get_pantry_used(
            required_ingredients,
            pantry
        )

        # ----------------------------------------------------
        # Missing ingredients
        # ----------------------------------------------------

        missing_raw = get_missing_ingredients(
            recipe_ingredients,
            pantry
        )

        missing_ingredients = (
            format_missing_ingredients(
                missing_raw
            )
        )

        # ----------------------------------------------------
        # Unsupported / uncertain items
        # ----------------------------------------------------

        unsupported_items = []

        for item in missing_ingredients:

            status = item.get(
                "status"
            )

            if status in {
                "unit_mismatch",
                "quantity_unknown"
            }:

                unsupported_items.append(
                    item
                )

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

            "agent":
                self.name,

            "status":
                status,

            "data": {

                "recipe_id":
                    recipe_id,

                "required_ingredients":
                    required_ingredients,

                "pantry_used":
                    pantry_used,

                "missing_ingredients":
                    missing_ingredients,

                "unsupported_items":
                    unsupported_items
            },

            "warnings": [],

            "errors": []
        }


# ============================================================
# DUMMY MANAGER INPUT
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # This simulates what the Manager Agent will eventually
    # send to the Ingredient Agent.
    #
    # Later:
    #
    # manager_input = manager_agent_output
    #
    # The Ingredient Agent itself will NOT change.
    # --------------------------------------------------------

    manager_input = {

        "recipe_id":
            "R03943",

        "pantry": [

            {
                "ingredient_id":
                    "ING0614",

                "ingredient_name":
                    "cauliflower",

                "quantity":
                    1,

                "unit":
                    "head"
            },

            {
                "ingredient_id":
                    "ING3248",

                "ingredient_name":
                    "sour cream",

                "quantity":
                    2,

                "unit":
                    "tablespoon"
            },

            {
                "ingredient_id":
                    "ING0658",

                "ingredient_name":
                    "cheddar cheese",

                "quantity":
                    1,

                "unit":
                    "tablespoon"
            }
        ]
    }

    # --------------------------------------------------------
    # Create Agent
    # --------------------------------------------------------

    agent = IngredientAgent()

    # --------------------------------------------------------
    # Run Agent
    # --------------------------------------------------------

    result = agent.run(
        manager_input
    )

    # --------------------------------------------------------
    # Print result
    # --------------------------------------------------------

    print(
        json.dumps(
            result,
            indent=2,
            default=str
        )
    )