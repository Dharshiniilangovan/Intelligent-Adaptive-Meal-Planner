import json

from src.input_parser.natural_language_parser import (
    UserInputParser,
    build_ollama_prompt,
)


parser = UserInputParser()


def test_budget():
    result = parser.parse("I have a budget of $50.")
    assert result.valid
    assert result.data["budget"] == 50.0


def test_budget_with_time_period():
    result = parser.parse("I have $50 for the next three days.")
    assert result.valid
    assert result.data["budget"] == 50.0
    assert result.data["ingredient_availability"] == {}


def test_allergy():
    result = parser.parse("I am allergic to peanuts.")
    assert result.valid
    assert result.data["allergies"] == ["Peanuts"]


def test_dietary_restriction():
    result = parser.parse("I am vegetarian.")
    assert result.valid
    assert result.data["dietary_restrictions"] == ["Vegetarian"]


def test_cuisine():
    result = parser.parse("I prefer Asian food.")
    assert result.valid
    assert result.data["preferred_cuisines"] == ["Asian"]


def test_cooking_time():
    result = parser.parse("I can cook for 30 minutes.")
    assert result.valid
    assert result.data["cook_time_preference_hrs"] == 0.5


def test_cooking_frequency():
    result = parser.parse("I cook 3 times a week.")
    assert result.valid
    assert result.data["cook_frequency"] == 3


def test_unknown_pantry_quantity():
    result = parser.parse("I have rice and tofu.")
    assert result.valid
    assert result.data["ingredient_availability"] == {
        "Rice": None,
        "Tofu": None,
    }


def test_pantry_quantity():
    result = parser.parse("I have 2 kg potatoes.")
    assert result.valid
    assert result.data["ingredient_availability"] == {
        "Potatoes": {
            "quantity": 2.0,
            "unit": "kg",
        }
    }


def test_pantry_phrase_cleanup():
    result = parser.parse(
        "I prefer Asian food. "
        "I have 2 kg of rice and some tofu."
    )
    assert result.valid
    assert result.data["preferred_cuisines"] == ["Asian"]
    assert result.data["preferred_ingredients"] == []
    assert result.data["ingredient_availability"] == {
        "Rice": {"quantity": 2.0, "unit": "kg"},
        "Tofu": None,
    }


def test_budget_and_pantry_together():
    result = parser.parse(
        "I have $50 for the next three days. "
        "I am vegetarian. "
        "I have 2 kg of rice and some tofu."
    )
    assert result.valid
    assert result.data["budget"] == 50.0
    assert result.data["ingredient_availability"] == {
        "Rice": {"quantity": 2.0, "unit": "kg"},
        "Tofu": None,
    }


def test_multiple_constraints():
    text = (
        "I have $50 for the next three days. "
        "I'm vegetarian, allergic to peanuts, "
        "and prefer Asian food. "
        "I have rice and tofu."
    )
    result = parser.parse(text)
    assert result.valid
    assert result.data["budget"] == 50.0
    assert result.data["dietary_restrictions"] == ["Vegetarian"]
    assert result.data["allergies"] == ["Peanuts"]
    assert result.data["preferred_cuisines"] == ["Asian"]
    assert result.data["ingredient_availability"] == {
        "Rice": None,
        "Tofu": None,
    }


def test_invalid_budget():
    result = parser.validate({"budget": -10})
    assert not result.valid
    assert "budget cannot be negative" in result.errors


def test_missing_required_fields():
    result = parser.validate(
        {},
        required_fields=["budget", "cook_frequency"],
    )
    assert not result.valid
    assert result.missing_fields == [
        "budget",
        "cook_frequency",
    ]


def test_llm_json_output():
    llm = lambda prompt: json.dumps({
        "budget": 50,
        "dietary_restrictions": ["Vegetarian"],
        "allergies": ["Peanuts"],
        "preferred_cuisines": ["Asian"],
        "ingredient_availability": {
            "rice": None,
            "tofu": None,
        },
    })
    result = UserInputParser(llm=llm).parse("dummy")
    assert result.valid
    assert result.data["budget"] == 50.0
    assert result.data["ingredient_availability"]["rice"] is None


def test_llm_prompt():
    prompt = build_ollama_prompt("I have rice.")
    assert "Do not invent values" in prompt
    assert "Unknown pantry quantities must be null" in prompt


def test_budget_ceiling_under_dollars():
    result = parser.parse("Plan meals under $30.")
    assert result.valid
    assert result.data["budget"] == 30.0


def test_budget_ceiling_singapore_dollars():
    result = parser.parse("Keep my budget up to S$50.")
    assert result.valid
    assert result.data["budget"] == 50.0


def test_llm_invalid_json_falls_back_deterministically():
    result = UserInputParser(llm=lambda prompt: "not json").parse(
        "I have a budget of $45 and I am vegetarian."
    )
    assert result.data["budget"] == 45.0
    assert result.data["dietary_restrictions"] == ["Vegetarian"]
    assert any("fallback used" in error for error in result.errors)
