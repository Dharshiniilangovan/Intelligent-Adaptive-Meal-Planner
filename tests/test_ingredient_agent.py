import pytest

from src.agents.ingredient_agent import IngredientAgent


def test_ingredient_agent_manager_contract():
    """Verify the Agent interface expected by Manager."""

    agent = IngredientAgent()

    result = agent.run(
        recipe_id="R03943",
        pantry={}
    )

    assert isinstance(result, dict)

    assert result["agent"] == "ingredient"

    assert result["status"] in {
        "success",
        "partial",
        "failed",
    }

    assert isinstance(result["data"], dict)
    assert isinstance(result["warnings"], list)
    assert isinstance(result["errors"], list)


def test_ingredient_agent_valid_recipe():
    """Verify a valid recipe returns ingredient information."""

    agent = IngredientAgent()

    result = agent.run(
        recipe_id="R03943",
        pantry={}
    )

    assert result["status"] in {
        "success",
        "partial",
    }

    data = result["data"]

    assert data["recipe_id"] == "R03943"
    assert "required_ingredients" in data
    assert "pantry_used" in data
    assert "missing_ingredients" in data
    assert "unsupported_items" in data

    assert isinstance(data["required_ingredients"], list)
    assert isinstance(data["pantry_used"], list)
    assert isinstance(data["missing_ingredients"], list)
    assert isinstance(data["unsupported_items"], list)


def test_ingredient_agent_with_pantry():
    """Verify pantry ingredients are detected correctly."""

    agent = IngredientAgent()

    pantry = {
        "Cauliflower": "1 head",
        "Sour Cream": "2 tablespoon",
        "Cheddar Cheese": "1 tablespoon",
    }

    result = agent.run(
        recipe_id="R03943",
        pantry=pantry,
    )

    assert result["status"] in {
        "success",
        "partial",
    }

    data = result["data"]

    assert len(data["required_ingredients"]) > 0
    assert len(data["pantry_used"]) > 0
    assert len(data["missing_ingredients"]) > 0


def test_ingredient_agent_empty_pantry():
    """Verify all required ingredients are treated as missing."""

    agent = IngredientAgent()

    result = agent.run(
        recipe_id="R03943",
        pantry={}
    )

    assert result["status"] in {
        "success",
        "partial",
    }

    data = result["data"]

    assert len(data["required_ingredients"]) > 0
    assert len(data["pantry_used"]) == 0
    assert len(data["missing_ingredients"]) > 0


def test_ingredient_agent_invalid_recipe():
    """Verify invalid recipe IDs return a failed result."""

    agent = IngredientAgent()

    result = agent.run(
        recipe_id="INVALID_RECIPE",
        pantry={}
    )

    assert result["agent"] == "ingredient"
    assert result["status"] == "failed"
    assert len(result["errors"]) > 0



def test_ingredient_agent_normalizes_units():
    """Verify raw unit aliases are normalized in ingredient output."""

    agent = IngredientAgent()

    result = agent.run(
        recipe_id="R16472",
        pantry={}
    )

    assert result["status"] in {
        "success",
        "partial",
    }

    ingredients = result["data"]["required_ingredients"]

    units = {
        ingredient["ingredient_name"]: ingredient["unit"]
        for ingredient in ingredients
    }

    assert units["vodka"] == "g"
    assert units["cranberry juice"] == "g"
    assert units["orange juice"] == "g"
