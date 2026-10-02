import pytest

from src.pantry.pantry_service import filter_ingredient_list


# ---------------------------------------------------------
# 1. Ingredient completely missing from pantry
# ---------------------------------------------------------

def test_ingredient_not_in_pantry():
    pantry = {}

    required = {
        "rice": {
            "ingredient_id": "ING001",
            "alias_name": "['rice', 'white rice']",
            "quantity": 500,
            "unit": "gram"
        }
    }

    result = filter_ingredient_list(pantry, required)

    assert result == {
        "rice": {
            "ingredient_id": "ING001",
            "alias_name": "['rice', 'white rice']",
            "quantity": 500,
            "unit": "gram"
        }
    }


# ---------------------------------------------------------
# 2. Pantry has some, but not enough
# ---------------------------------------------------------

def test_pantry_has_insufficient_quantity():
    pantry = {
        "rice": {
            "quantity": 200,
            "unit": "gram"
        }
    }

    required = {
        "rice": {
            "ingredient_id": "ING001",
            "alias_name": "['rice', 'white rice']",
            "quantity": 500,
            "unit": "gram"
        }
    }

    result = filter_ingredient_list(pantry, required)

    assert result == {
        "rice": {
            "ingredient_id": "ING001",
            "alias_name": "['rice', 'white rice']",
            "quantity": 300,
            "unit": "gram"
        }
    }


# ---------------------------------------------------------
# 3. Pantry has exactly enough
# ---------------------------------------------------------

def test_pantry_has_exact_quantity():
    pantry = {
        "rice": {
            "quantity": 500,
            "unit": "gram"
        }
    }

    required = {
        "rice": {
            "ingredient_id": "ING001",
            "alias_name": "['rice', 'white rice']",
            "quantity": 500,
            "unit": "gram"
        }
    }

    result = filter_ingredient_list(pantry, required)

    assert result == {}


# ---------------------------------------------------------
# 4. Pantry has more than required
# ---------------------------------------------------------

def test_pantry_has_more_than_required():
    pantry = {
        "rice": {
            "quantity": 700,
            "unit": "gram"
        }
    }

    required = {
        "rice": {
            "ingredient_id": "ING001",
            "alias_name": "['rice', 'white rice']",
            "quantity": 500,
            "unit": "gram"
        }
    }

    result = filter_ingredient_list(pantry, required)

    assert result == {}


# ---------------------------------------------------------
# 5. Unit mismatch
# ---------------------------------------------------------

def test_unit_mismatch():
    pantry = {
        "butter": {
            "quantity": 0.5,
            "unit": "kilogram"
        }
    }

    required = {
        "butter": {
            "ingredient_id": "ING002",
            "alias_name": "['butter', 'unsalted butter']",
            "quantity": 2,
            "unit": "tablespoon"
        }
    }

    result = filter_ingredient_list(pantry, required)

    assert result == {
        "butter": {
            "ingredient_id": "ING002",
            "alias_name": "['butter', 'unsalted butter']",
            "quantity": 2,
            "unit": "tablespoon",
            "status": "unit_mismatch"
        }
    }


# ---------------------------------------------------------
# 6. Unknown recipe quantity
# ---------------------------------------------------------

def test_unknown_quantity():
    pantry = {}

    required = {
        "salt": {
            "ingredient_id": "ING003",
            "alias_name": "['salt', 'table salt']",
            "quantity": float("nan"),
            "unit": "to taste"
        }
    }

    result = filter_ingredient_list(pantry, required)

    assert result == {
        "salt": {
            "ingredient_id": "ING003",
            "alias_name": "['salt', 'table salt']",
            "quantity": None,
            "unit": "to taste",
            "status": "quantity_unknown"
        }
    }


# ---------------------------------------------------------
# 7. Multiple ingredients together
# ---------------------------------------------------------

def test_multiple_ingredients():
    pantry = {
        "rice": {
            "quantity": 200,
            "unit": "gram"
        },
        "carrot": {
            "quantity": 100,
            "unit": "gram"
        }
    }

    required = {
        "rice": {
            "ingredient_id": "ING001",
            "alias_name": "['rice', 'white rice']",
            "quantity": 500,
            "unit": "gram"
        },
        "carrot": {
            "ingredient_id": "ING004",
            "alias_name": "['carrot', 'carrots']",
            "quantity": 100,
            "unit": "gram"
        },
        "tofu": {
            "ingredient_id": "ING005",
            "alias_name": "['tofu', 'firm tofu']",
            "quantity": 300,
            "unit": "gram"
        }
    }

    result = filter_ingredient_list(pantry, required)

    assert result == {
        "rice": {
            "ingredient_id": "ING001",
            "alias_name": "['rice', 'white rice']",
            "quantity": 300,
            "unit": "gram"
        },
        "tofu": {
            "ingredient_id": "ING005",
            "alias_name": "['tofu', 'firm tofu']",
            "quantity": 300,
            "unit": "gram"
        }
    }


# ---------------------------------------------------------
# 8. Empty required ingredient list
# ---------------------------------------------------------

def test_empty_required_ingredients():
    pantry = {
        "rice": {
            "quantity": 200,
            "unit": "gram"
        }
    }

    result = filter_ingredient_list(pantry, {})

    assert result == {}


# ---------------------------------------------------------
# 9. Invalid pantry input
# ---------------------------------------------------------

def test_invalid_pantry_input():
    with pytest.raises(
        ValueError,
        match="Pantry data should be a dictionary"
    ):
        filter_ingredient_list([], {})


# ---------------------------------------------------------
# 10. Invalid required ingredients input
# ---------------------------------------------------------

def test_invalid_required_ingredients_input():
    with pytest.raises(
        ValueError,
        match="Ingredient names should be a dictionary"
    ):
        filter_ingredient_list({}, [])