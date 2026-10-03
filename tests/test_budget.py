import pytest

from src.budget.budget_service import (
    check_budget,
    check_basket_budget,
)


def test_budget_pass():
    result = check_budget(
        purchase_cost=12,
        remaining_budget=50
    )

    assert result["budget_status"] == "pass"
    assert result["budget_after_purchase"] == 38.0


def test_budget_exact_amount_passes():
    result = check_budget(
        purchase_cost=12,
        remaining_budget=12
    )

    assert result["budget_status"] == "pass"
    assert result["budget_after_purchase"] == 0.0


def test_budget_hard_fail():
    result = check_budget(
        purchase_cost=12,
        remaining_budget=10
    )

    assert result["budget_status"] == "hard_fail"
    assert result["budget_after_purchase"] is None


def test_unknown_price_is_uncertain():
    result = check_budget(
        purchase_cost=6,
        remaining_budget=50,
        has_unknown_cost=True
    )

    assert result["budget_status"] == "uncertain"
    assert result["budget_after_purchase"] is None


def test_unknown_price_but_known_cost_already_over_budget():
    result = check_budget(
        purchase_cost=12,
        remaining_budget=10,
        has_unknown_cost=True
    )

    assert result["budget_status"] == "hard_fail"


def test_zero_purchase_cost_passes():
    result = check_budget(
        purchase_cost=0,
        remaining_budget=50
    )

    assert result["budget_status"] == "pass"
    assert result["budget_after_purchase"] == 50.0


def test_zero_budget_with_purchase_fails():
    result = check_budget(
        purchase_cost=5,
        remaining_budget=0
    )

    assert result["budget_status"] == "hard_fail"


def test_zero_cost_zero_budget_passes():
    result = check_budget(
        purchase_cost=0,
        remaining_budget=0
    )

    assert result["budget_status"] == "pass"


def test_negative_purchase_cost_rejected():
    with pytest.raises(ValueError):
        check_budget(
            purchase_cost=-5,
            remaining_budget=50
        )


def test_negative_remaining_budget_rejected():
    with pytest.raises(ValueError):
        check_budget(
            purchase_cost=5,
            remaining_budget=-10
        )


def test_basket_with_complete_cost_passes():
    basket = {
        "estimated_total": 12.0,
        "known_subtotal": 12.0,
        "unknown_cost_items": [],
        "cost_complete": True,
    }

    result = check_basket_budget(
        basket,
        remaining_budget=50
    )

    assert result["budget_status"] == "pass"


def test_basket_with_unknown_item_is_uncertain():
    basket = {
        "estimated_total": 6.0,
        "known_subtotal": 6.0,
        "unknown_cost_items": ["tofu"],
        "cost_complete": False,
    }

    result = check_basket_budget(
        basket,
        remaining_budget=50
    )

    assert result["budget_status"] == "uncertain"