from src.reasoning.feasibility import check_ingredient_feasibility


def test_valid_ingredient_ids_pass():
    """Ingredients with valid IDs and names should PASS."""

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

    assert result["status"] == "pass"
    assert result["passed"] is True
    assert result["issues"] == []


def test_missing_ingredient_id_returns_unknown():
    """Missing ingredient ID should produce UNKNOWN."""

    ingredients = [
        {
            "ingredient_id": None,
            "ingredient_name": "salt",
            "quantity": "1",
            "unit": "teaspoon",
        }
    ]

    result = check_ingredient_feasibility(ingredients)

    assert result["status"] == "unknown"
    assert result["passed"] is None

    assert any(
        issue["issue"] == "missing_ingredient_id"
        for issue in result["issues"]
    )


def test_missing_ingredient_name_returns_unknown():
    """Missing ingredient name should produce UNKNOWN."""

    ingredients = [
        {
            "ingredient_id": "ING3046",
            "ingredient_name": None,
            "quantity": "1",
            "unit": "teaspoon",
        }
    ]

    result = check_ingredient_feasibility(ingredients)

    assert result["status"] == "unknown"
    assert result["passed"] is None

    assert any(
        issue["issue"] == "missing_ingredient_name"
        for issue in result["issues"]
    )


def test_qualitative_quantity_does_not_fail():
    """
    Qualitative quantities such as 'required' and 'to taste'
    should NOT make an ingredient UNKNOWN.

    Ingredient ID is what determines ingredient validity.
    """

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

    assert result["status"] == "pass"
    assert result["passed"] is True


def test_missing_unit_does_not_fail_ingredient_id():
    """
    Missing/unknown unit does not invalidate the ingredient ID.

    Unit handling belongs to quantity/pantry/grocery logic.
    """

    ingredients = [
        {
            "ingredient_id": "ING0992",
            "ingredient_name": "cooking spray",
            "quantity": "0.5",
            "unit": "nan",
        }
    ]

    result = check_ingredient_feasibility(ingredients)

    assert result["status"] == "pass"
    assert result["passed"] is True


def test_unsupported_unit_does_not_fail_ingredient_id():
    """
    Unsupported units should not make the ingredient ID invalid.
    """

    ingredients = [
        {
            "ingredient_id": "ING0001",
            "ingredient_name": "water",
            "quantity": "0.5",
            "unit": "quart",
        }
    ]

    result = check_ingredient_feasibility(ingredients)

    assert result["status"] == "pass"
    assert result["passed"] is True


def test_ingredient_specific_unit_does_not_fail_id():
    """
    Ingredient-specific units such as 'steak' do not invalidate
    the ingredient ID.
    """

    ingredients = [
        {
            "ingredient_id": "ING0002",
            "ingredient_name": "bone in ribeye",
            "quantity": "1.0",
            "unit": "steak",
        }
    ]

    result = check_ingredient_feasibility(ingredients)

    assert result["status"] == "pass"
    assert result["passed"] is True


def test_empty_ingredients_returns_unknown():
    """No ingredients should produce UNKNOWN."""

    result = check_ingredient_feasibility([])

    assert result["status"] == "unknown"
    assert result["passed"] is None