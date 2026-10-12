
"""Shared presentation utilities for the IAMP Streamlit application.

Used by:
- Dashboard
- Meal Planner
- Groceries
- Nutrition
- Pantry
- Adaptive Replanning

Keep all shared display functions in this file.
"""

import math
from datetime import date, datetime
from html import escape

import streamlit as st

from app.components.recipe_lookup import get_recipe_name


# ==========================================================
# 1. CURRENCY FORMATTING
# ==========================================================

def money(value):
    """Format prices in Singapore dollars."""

    if value is None:
        return "Not available"

    try:
        amount = float(value)

        if not math.isfinite(amount):
            return "Not available"

        return f"S${amount:,.2f}"

    except (TypeError, ValueError):
        return "Not available"


# ==========================================================
# 2. NUMBER FORMATTING
# ==========================================================

def number(value, decimals=2):
    """Format ingredient quantities and nutrition values."""

    if value is None:
        return "Not available"

    try:
        amount = float(value)

        if not math.isfinite(amount):
            return "Not available"

        if decimals == 0:
            return f"{amount:,.0f}"

        return (
            f"{amount:,.{decimals}f}"
            .rstrip("0")
            .rstrip(".")
        )

    except (TypeError, ValueError):
        return str(value)


# ==========================================================
# 3. IMAGE PREVIEW
# ==========================================================

def preview_image(uploaded_file, width=260):
    """Display images at a consistent, smaller width."""

    st.image(
        uploaded_file,
        width=width,
    )


# ==========================================================
# 4. HUMAN-READABLE DATE
# ==========================================================

def friendly_date(value):
    """Convert dates into a readable format."""

    if value is None:
        return "Date unavailable"

    if isinstance(value, datetime):
        return value.strftime("%a, %d %b %Y")

    if isinstance(value, date):
        return value.strftime("%a, %d %b %Y")

    try:
        parsed = date.fromisoformat(str(value))

        return parsed.strftime(
            "%a, %d %b %Y"
        )

    except (ValueError, TypeError):
        return str(value)


# ==========================================================
# 5. MEAL DISPLAY
# ==========================================================

def show_meals(meals):
    """Display meals as compact rows grouped by date.

    Recipe IDs are used internally to retrieve recipe
    names from the Recipe Knowledge Base.

    Users only see recipe names.
    """

    grouped = {}

    for meal in meals:

        if not isinstance(meal, dict):
            continue

        slot = meal.get("slot") or {}
        decision = meal.get("decision") or {}

        # ----------------------------------------------
        # Meal date
        # ----------------------------------------------

        meal_date = (
            slot.get("date")
            or meal.get("date")
            or str(
                slot.get("slot_id")
                or meal.get("slot_id")
                or ""
            ).split("_")[0]
        )

        # ----------------------------------------------
        # Meal type
        # ----------------------------------------------

        meal_type = (
            slot.get("meal_type")
            or meal.get("meal_type")
            or "Meal"
        )

        # ----------------------------------------------
        # Recipe ID
        # ----------------------------------------------

        recipe_id = (
            meal.get("recipe_id")
            or decision.get("recipe_id")
            or decision.get("selected_recipe_id")
        )

        # ----------------------------------------------
        # Recipe name
        # ----------------------------------------------

        recipe_name = get_recipe_name(
            recipe_id
        )

        grouped.setdefault(
            str(meal_date), []
        ).append({
            "meal_type": str(meal_type).title(),
            "recipe_name": recipe_name,
        })

    # ----------------------------------------------
    # Meal ordering
    # ----------------------------------------------

    meal_order = {
        "Breakfast": 0,
        "Lunch": 1,
        "Dinner": 2,
    }

    # ----------------------------------------------
    # Styling
    # ----------------------------------------------

    st.markdown(
        """
        <style>

        .iamp-day {
            margin-bottom: 20px;
        }

        .iamp-date {
            font-size: 19px;
            font-weight: 600;
            color: #26332B;
            margin-bottom: 8px;
        }

        .iamp-meal-line {
            display: grid;
            grid-template-columns: 95px minmax(0, 1fr);
            column-gap: 14px;
            align-items: baseline;
            padding: 4px 0;
        }

        .iamp-meal-label {
            color: #788279;
            font-size: 15px;
        }

        .iamp-meal-name {
            color: #26332B;
            font-size: 16px;
            font-weight: 500;
            line-height: 1.45;
            overflow-wrap: anywhere;
        }

        @media (max-width: 600px) {
            .iamp-meal-line {
                grid-template-columns: 75px minmax(0, 1fr);
                column-gap: 10px;
            }
        }

        </style>
        """,
        unsafe_allow_html=True,
    )

    # ----------------------------------------------
    # Build meal display
    # ----------------------------------------------

    html_parts = []

    for meal_date, day_meals in sorted(
        grouped.items()
    ):

        formatted_date = friendly_date(
            meal_date
        )

        day_meals.sort(
            key=lambda item: meal_order.get(
                item["meal_type"],
                99,
            )
        )

        meal_lines = []

        for meal in day_meals:

            meal_lines.append(
                '<div class="iamp-meal-line">'
                '<span class="iamp-meal-label">'
                f'{escape(meal["meal_type"])}'
                '</span>'
                '<span class="iamp-meal-name">'
                f'{escape(meal["recipe_name"])}'
                '</span>'
                '</div>'
            )

        html_parts.append(
            '<div class="iamp-day">'
            '<div class="iamp-date">'
            f'{escape(formatted_date)}'
            '</div>'
            f'{"".join(meal_lines)}'
            '</div>'
        )

    if html_parts:
        st.markdown(
            "\n".join(html_parts),
            unsafe_allow_html=True,
        )

    else:
        st.info(
            "No meals are available to display."
        )


def meal_label(meal):
    """Create a readable meal label for adaptive replanning."""

    if not isinstance(meal, dict):
        return "Meal unavailable"

    slot = meal.get("slot") or {}
    decision = meal.get("decision") or {}

    slot_id = (
        slot.get("slot_id")
        or meal.get("slot_id")
        or ""
    )

    meal_date = (
        slot.get("date")
        or meal.get("date")
        or str(slot_id).split("_")[0]
    )

    meal_type = (
        slot.get("meal_type")
        or meal.get("meal_type")
        or "Meal"
    )

    recipe_id = (
        meal.get("recipe_id")
        or decision.get("recipe_id")
        or decision.get("selected_recipe_id")
    )

    recipe_name = get_recipe_name(recipe_id)

    return (
        f"{friendly_date(meal_date)}"
        f" — {str(meal_type).title()}"
        f" — {recipe_name}"
    )
