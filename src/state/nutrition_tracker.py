"""Nutrition state utilities for Day-5 multi-meal planning.

Member 3 ownership:
    - daily nutrition aggregation
    - simple deviation against daily targets

The functions are deterministic and reusable. They do not retrieve recipes
or make feasibility decisions.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from typing import Any


NUTRIENT_ALIASES = {
    "calories": "calories",
    "calories_per_serving": "calories",
    "kcal": "calories",
    "protein": "protein_g",
    "protein_g": "protein_g",
    "protein_g_per_serving": "protein_g",
    "carbs": "carbs_g",
    "carbs_g": "carbs_g",
    "carbs_g_per_serving": "carbs_g",
    "fat": "fat_g",
    "fat_g": "fat_g",
    "fat_g_per_serving": "fat_g",
    "fiber": "fiber_g",
    "fiber_g": "fiber_g",
    "fiber_g_per_serving": "fiber_g",
    "sugar": "sugar_g",
    "sugar_g": "sugar_g",
    "sugar_g_per_serving": "sugar_g",
    "sodium": "sodium_mg",
    "sodium_mg": "sodium_mg",
    "sodium_mg_per_serving": "sodium_mg",
    "calcium": "calcium_mg",
    "calcium_mg": "calcium_mg",
    "calcium_mg_per_serving": "calcium_mg",
    "iron": "iron_mg",
    "iron_mg": "iron_mg",
    "iron_mg_per_serving": "iron_mg",
}


DEFAULT_NUTRIENTS = (
    "calories",
    "protein_g",
    "carbs_g",
    "fat_g",
    "fiber_g",
    "sugar_g",
    "sodium_mg",
    "calcium_mg",
    "iron_mg",
)


def _as_number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return number


def _canonical_nutrient(name: str) -> str:
    key = str(name).strip().lower()
    return NUTRIENT_ALIASES.get(key, key)


def _extract_nutrition(source: Mapping[str, Any]) -> dict[str, float]:
    """Extract supported nutrition fields from a recipe or nutrient mapping."""
    result: dict[str, float] = {}

    for key, value in source.items():
        canonical = _canonical_nutrient(str(key))
        if canonical not in DEFAULT_NUTRIENTS:
            continue

        # Prefer explicit per-serving values when the source contains them.
        result[canonical] = _as_number(value)

    return result


def aggregate_nutrition(
    nutrition_state: dict[str, dict[str, float]],
    date: str,
    nutrition: Mapping[str, Any],
    servings: float = 1.0,
) -> dict[str, dict[str, float]]:
    """Add one selected meal's nutrition to a day.

    ``nutrition`` can be the recipe KB row directly because the current KB
    already exposes ``*_per_serving`` fields.
    """
    if not isinstance(nutrition_state, dict):
        raise ValueError("nutrition_state must be a dictionary")
    if not date:
        raise ValueError("date is required")
    if not isinstance(nutrition, Mapping):
        raise ValueError("nutrition must be a mapping")

    try:
        servings = float(servings)
    except (TypeError, ValueError):
        raise ValueError("servings must be numeric") from None

    if servings <= 0:
        raise ValueError("servings must be greater than zero")

    updated = copy.deepcopy(nutrition_state)
    day = updated.setdefault(
        str(date),
        {nutrient: 0.0 for nutrient in DEFAULT_NUTRIENTS},
    )

    # Ensure all known keys exist even if the state was initialized manually.
    for nutrient in DEFAULT_NUTRIENTS:
        day.setdefault(nutrient, 0.0)

    extracted = _extract_nutrition(nutrition)

    for nutrient, value in extracted.items():
        # Recipe KB values are already per serving.  If a caller passes a
        # raw total instead, they can use servings=1 and that value is used as
        # given. The planner's normal path is per-serving values.
        day[nutrient] += value * servings

    return updated


def calculate_nutrition_deviation(
    nutrition_state: dict[str, dict[str, float]],
    daily_targets: Mapping[str, Any],
) -> dict[str, Any]:
    """Calculate daily absolute deviations and mean absolute deviation.

    Example target input::

        {"calories": 1800, "protein_g": 70}
    """
    if not isinstance(nutrition_state, dict):
        raise ValueError("nutrition_state must be a dictionary")
    if not isinstance(daily_targets, Mapping):
        raise ValueError("daily_targets must be a mapping")

    targets = {
        _canonical_nutrient(str(key)): _as_number(value)
        for key, value in daily_targets.items()
        if _canonical_nutrient(str(key)) in DEFAULT_NUTRIENTS
    }

    daily: dict[str, dict[str, float]] = {}

    for date, totals in nutrition_state.items():
        daily[str(date)] = {}
        for nutrient, target in targets.items():
            actual = _as_number(totals.get(nutrient, 0.0))
            daily[str(date)][nutrient] = round(abs(actual - target), 4)

    mean_absolute_deviation: dict[str, float] = {}

    for nutrient in targets:
        deviations = [
            day[nutrient]
            for day in daily.values()
            if nutrient in day
        ]
        mean_absolute_deviation[nutrient] = (
            round(sum(deviations) / len(deviations), 4)
            if deviations
            else 0.0
        )

    return {
        "daily": daily,
        "mean_absolute_deviation": mean_absolute_deviation,
        "targets": targets,
    }


def summarize_nutrition(
    nutrition_state: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Return a clean daily nutrition summary."""
    return {
        str(date): {
            nutrient: round(_as_number(values.get(nutrient, 0.0)), 4)
            for nutrient in DEFAULT_NUTRIENTS
        }
        for date, values in nutrition_state.items()
    }
