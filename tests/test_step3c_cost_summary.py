
import pytest

from src.agents.grocery_agent import build_cost_summary


def test_complete_verified_basket():
    basket = {
        "known_cost": 20.0,
        "projected_cost": 20.0,
        "projected_cost_complete": True,
        "all_items_priced": True,
        "unpriced_items": [],
        "projection_missing": [],
    }

    result = build_cost_summary(basket, 50.0)

    assert result["known_grocery_cost"] == 20.0
    assert result["projected_grocery_cost"] == 20.0
    assert result["remaining"] == 30.0
    assert result["projected_remaining_budget"] == 30.0
    assert result["budget_verification"] == "verified"


def test_provisional_basket():
    basket = {
        "known_cost": 20.0,
        "projected_cost": 28.0,
        "projected_cost_complete": True,
        "all_items_priced": False,
        "unpriced_items": ["butter lettuce"],
        "projection_missing": [],
    }

    result = build_cost_summary(basket, 50.0)

    assert result["known_grocery_cost"] == 20.0
    assert result["projected_grocery_cost"] == 28.0
    assert result["estimated_cost_component"] == 8.0
    assert result["known_remaining_budget"] == 30.0
    assert result["projected_remaining_budget"] == 22.0
    assert result["budget_verification"] == "provisional"


def test_incomplete_projection():
    basket = {
        "known_cost": 10.0,
        "projected_cost": None,
        "projected_cost_complete": False,
        "all_items_priced": False,
        "unpriced_items": ["hoisin sauce"],
        "projection_missing": ["hoisin sauce"],
    }

    result = build_cost_summary(basket, 50.0)

    assert result["projected_grocery_cost"] is None
    assert result["projected_remaining_budget"] is None
    assert result["projected_cost_within_budget"] is None
    assert result["budget_verification"] == "incomplete"


def test_projected_cost_below_known_rejected():
    basket = {
        "known_cost": 25.0,
        "projected_cost": 15.0,
        "projected_cost_complete": True,
        "all_items_priced": False,
    }

    with pytest.raises(ValueError):
        build_cost_summary(basket, 50.0)


def test_projected_cost_exceeds_budget():
    basket = {
        "known_cost": 20.0,
        "projected_cost": 55.0,
        "projected_cost_complete": True,
        "all_items_priced": False,
    }

    result = build_cost_summary(basket, 50.0)

    assert result["known_cost_within_budget"] is True
    assert result["projected_cost_within_budget"] is False
    assert result["projected_remaining_budget"] == -5.0
