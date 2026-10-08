from src.reasoning.feasibility import check_ingredient_feasibility


def test_missing_quantity_returns_structured_unknown():
    """Missing quantity should produce a structured UNKNOWN result."""

    ingredients = [
        {
            "ingredient_id": "ING3046",
            "ingredient_name": "salt",
            "quantity": "required",
            "unit": "to taste",
        },
        {
            "ingredient_id": "ING2536",
            "ingredient_name": "pepper",
            "quantity": "required",
            "unit": "to taste",
        },
    ]

    result = check_ingredient_feasibility(ingredients)

    assert result["status"] == "unknown"
    assert result["passed"] is None

    assert "issues" in result
    assert len(result["issues"]) == 2

    assert result["issues"][0]["ingredient_id"] == "ING3046"
    assert result["issues"][0]["ingredient_name"] == "salt"
    assert result["issues"][0]["issue"] == "missing_quantity"

    assert result["issues"][1]["ingredient_id"] == "ING2536"
    assert result["issues"][1]["ingredient_name"] == "pepper"
    assert result["issues"][1]["issue"] == "missing_quantity"

def test_missing_unit_returns_structured_unknown():
    """Missing unit should produce a structured UNKNOWN result."""

    ingredients = [
        {
            "ingredient_id": "ING0992",
            "ingredient_name": "cooking spray",
            "quantity": "0.5",
            "unit": "nan",
        }
    ]

    result = check_ingredient_feasibility(ingredients)

    assert result["status"] == "unknown"
    assert result["passed"] is None

    assert "issues" in result
    assert len(result["issues"]) == 1

    assert result["issues"][0]["ingredient_id"] == "ING0992"
    assert result["issues"][0]["ingredient_name"] == "cooking spray"
    assert result["issues"][0]["issue"] == "missing_unit"

def test_unsupported_unit_returns_structured_unknown():
    """Unsupported units should produce a structured UNKNOWN result."""

    ingredients = [
        {
            "ingredient_id": "ING0001",
            "ingredient_name": "water",
            "quantity": "0.5",
            "unit": "quart",
        }
    ]

    result = check_ingredient_feasibility(ingredients)

    assert result["status"] == "unknown"
    assert result["passed"] is None

    assert "issues" in result
    assert len(result["issues"]) == 1

    assert result["issues"][0]["ingredient_id"] == "ING0001"
    assert result["issues"][0]["ingredient_name"] == "water"
    assert result["issues"][0]["issue"] == "unsupported_unit"

def test_steak_unit_returns_structured_unknown():
    """Ingredient-specific units should remain UNKNOWN if unsupported."""

    ingredients = [
        {
            "ingredient_id": "ING0002",
            "ingredient_name": "bone in ribeye",
            "quantity": "1.0",
            "unit": "steak",
        }
    ]

    result = check_ingredient_feasibility(ingredients)

    assert result["status"] == "unknown"
    assert result["passed"] is None

    assert "issues" in result
    assert len(result["issues"]) == 1

    assert result["issues"][0]["ingredient_id"] == "ING0002"
    assert result["issues"][0]["ingredient_name"] == "bone in ribeye"
    assert result["issues"][0]["issue"] == "unsupported_unit"