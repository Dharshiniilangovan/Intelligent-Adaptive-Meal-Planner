
import pytest

from src.reasoning.budget_service import (
    check_budget,
    check_provisional_grocery_budget,
)


def test_verified_cost_within_budget():
    result = check_budget(
        purchase_cost=20.0,
        remaining_budget=50.0,
        has_unknown_cost=False,
    )

    assert result["budget_status"] == "pass"
    assert result["budget_after_purchase"] == 30.0


def test_known_cost_exceeds_budget():
    result = check_budget(
        purchase_cost=55.0,
        remaining_budget=50.0,
        has_unknown_cost=True,
    )

    assert result["budget_status"] == "hard_fail"


def test_unknown_prices_remain_uncertain():
    result = check_budget(
        purchase_cost=20.0,
        remaining_budget=50.0,
        has_unknown_cost=True,
    )

    assert result["budget_status"] == "uncertain"
    assert result["budget_after_purchase"] is None


def test_complete_projection_with_margin():
    result = check_provisional_grocery_budget(
        projected_cost=35.0,
        projected_cost_complete=True,
        remaining_budget=50.0,
        safety_margin=0.20,
    )

    assert result["budget_status"] == "pass"
    assert result["provisional"] is True
    assert result["projected_cost"] == 35.0


def test_incomplete_projection_is_uncertain():
    result = check_provisional_grocery_budget(
        projected_cost=None,
        projected_cost_complete=False,
        remaining_budget=50.0,
    )

    assert result["budget_status"] == "uncertain"


def test_projection_over_budget_fails():
    result = check_provisional_grocery_budget(
        projected_cost=55.0,
        projected_cost_complete=True,
        remaining_budget=50.0,
    )

    assert result["budget_status"] == "hard_fail"
