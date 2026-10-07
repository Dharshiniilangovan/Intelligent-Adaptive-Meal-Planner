import pytest

from src.state.nutrition_tracker import (
    aggregate_nutrition,
    calculate_nutrition_deviation,
    summarize_nutrition,
)


def test_aggregate_daily_nutrition():
    state = {}

    state = aggregate_nutrition(
        state,
        "2026-10-05",
        {
            "calories_per_serving": 550,
            "protein_g_per_serving": 25,
        },
    )

    state = aggregate_nutrition(
        state,
        "2026-10-05",
        {
            "calories_per_serving": 650,
            "protein_g_per_serving": 35,
        },
    )

    print("\n=== DAILY NUTRITION ===")
    print(state)

    assert state["2026-10-05"]["calories"] == 1200.0
    assert state["2026-10-05"]["protein_g"] == 60.0


def test_aggregate_supports_multiple_days():
    state = {}

    state = aggregate_nutrition(
        state,
        "2026-10-05",
        {"calories": 1750, "protein": 68},
    )
    state = aggregate_nutrition(
        state,
        "2026-10-06",
        {"calories": 1820, "protein": 73},
    )

    summary = summarize_nutrition(state)

    print("\n=== MULTI-DAY NUTRITION ===")
    print(summary)

    assert summary["2026-10-05"]["calories"] == 1750.0
    assert summary["2026-10-06"]["protein_g"] == 73.0


def test_aggregate_with_two_servings():
    state = aggregate_nutrition(
        {},
        "2026-10-05",
        {"calories_per_serving": 500, "protein_g_per_serving": 20},
        servings=2,
    )

    print("\n=== TWO-SERVING NUTRITION ===")
    print(state)

    assert state["2026-10-05"]["calories"] == 1000.0
    assert state["2026-10-05"]["protein_g"] == 40.0


def test_calculate_nutrition_deviation():
    state = {
        "2026-10-05": {
            "calories": 1750,
            "protein_g": 68,
        },
        "2026-10-06": {
            "calories": 1850,
            "protein_g": 72,
        },
    }

    result = calculate_nutrition_deviation(
        state,
        {"calories": 1800, "protein_g": 70},
    )

    print("\n=== NUTRITION DEVIATION ===")
    print(result)

    assert result["daily"]["2026-10-05"]["calories"] == 50.0
    assert result["daily"]["2026-10-06"]["calories"] == 50.0
    assert result["mean_absolute_deviation"]["calories"] == 50.0
    assert result["mean_absolute_deviation"]["protein_g"] == 2.0


def test_zero_deviation_when_target_is_met():
    state = {
        "2026-10-05": {
            "calories": 1800,
            "protein_g": 70,
        }
    }

    result = calculate_nutrition_deviation(
        state,
        {"calories": 1800, "protein_g": 70},
    )

    print("\n=== ZERO NUTRITION DEVIATION ===")
    print(result)

    assert result["mean_absolute_deviation"]["calories"] == 0.0
    assert result["mean_absolute_deviation"]["protein_g"] == 0.0


def test_invalid_servings_rejected():
    with pytest.raises(ValueError):
        aggregate_nutrition(
            {},
            "2026-10-05",
            {"calories": 500},
            servings=0,
        )

    print("\n=== INVALID SERVINGS ===")
    print("Correctly rejected servings=0")