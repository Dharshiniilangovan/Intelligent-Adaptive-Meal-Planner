
"""Shared presentation utilities for the IAMP Streamlit application.

Used by:
- Dashboard
- Meal Planner
- Groceries
- Nutrition
- Pantry
- Adaptive Replanning

Features:
- Singapore dollar formatting
- Number formatting
- Image preview
- Friendly date formatting
- Recipe name lookup
- Validated original recipe URLs
- Compact vertical meal display
"""

import math
from datetime import date, datetime
from html import escape

import streamlit as st

from app.components.recipe_lookup import (
    get_recipe_name,
    get_recipe_details,
)


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
    """Display meals grouped by date with validated recipe URLs.

    Recipe IDs are used internally to retrieve recipe names
    and validated original URLs from the Recipe KB.

    Only URLs marked as working in the validation report
    are displayed.

    Layout:
        Date
            Breakfast    Recipe name
                         Original recipe URL

            Lunch        Recipe name
                         Original recipe URL

            Dinner       Recipe name
                         Original recipe URL
    """

    grouped = {}

    # ------------------------------------------------------
    # Collect meal information
    # ------------------------------------------------------

    for meal in meals or []:

        if not isinstance(meal, dict):
            continue

        slot = meal.get("slot") or {}
        decision = meal.get("decision") or {}

        # Meal date
        meal_date = (
            slot.get("date")
            or meal.get("date")
            or str(
                slot.get("slot_id")
                or meal.get("slot_id")
                or ""
            ).split("_")[0]
        )

        # Meal type
        meal_type = (
            slot.get("meal_type")
            or meal.get("meal_type")
            or "Meal"
        )

        # Recipe ID
        recipe_id = (
            meal.get("recipe_id")
            or decision.get("recipe_id")
            or decision.get("selected_recipe_id")
        )

        # Retrieve name and validated URL
        details = get_recipe_details(recipe_id)

        recipe_name = (
            details.get("recipe_name")
            or "Recipe details unavailable"
        )

        recipe_url = details.get("url")

        grouped.setdefault(
            str(meal_date), []
        ).append({
            "meal_type": str(meal_type).title(),
            "recipe_name": str(recipe_name),
            "recipe_url": recipe_url,
        })

    # ------------------------------------------------------
    # Meal ordering
    # ------------------------------------------------------

    meal_order = {
        "Breakfast": 0,
        "Lunch": 1,
        "Dinner": 2,
    }

    # ------------------------------------------------------
    # Styling
    # ------------------------------------------------------

    st.markdown(
        """
        <style>

        .iamp-day {
            margin-bottom: 24px;
        }

        .iamp-date {
            font-size: 19px;
            font-weight: 600;
            color: #26332B;
            margin-bottom: 10px;
        }

        .iamp-meal-line {
            display: grid;
            grid-template-columns: 95px minmax(0, 1fr);
            column-gap: 14px;
            align-items: start;
            padding: 7px 0;
        }

        .iamp-meal-label {
            color: #788279;
            font-size: 15px;
            padding-top: 2px;
        }

        .iamp-meal-content {
            min-width: 0;
        }

        .iamp-meal-name {
            color: #26332B;
            font-size: 16px;
            font-weight: 500;
            line-height: 1.45;
            overflow-wrap: anywhere;
        }

        .iamp-recipe-link {
            display: block;
            color: #37795A !important;
            font-size: 13px;
            line-height: 1.5;
            margin-top: 3px;
            text-decoration: underline;
            text-underline-offset: 2px;
            overflow-wrap: anywhere;
            word-break: break-word;
        }

        .iamp-recipe-link:hover {
            color: #24583F !important;
            text-decoration: underline;
        }

        .iamp-recipe-unavailable {
            display: block;
            color: #929B94;
            font-size: 12px;
            margin-top: 3px;
        }

        @media (max-width: 600px) {

            .iamp-meal-line {
                grid-template-columns: 75px minmax(0, 1fr);
                column-gap: 10px;
            }

            .iamp-meal-name {
                font-size: 15px;
            }

            .iamp-recipe-link {
                font-size: 12px;
            }

        }

        </style>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------
    # Build meal display
    # ------------------------------------------------------

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

            recipe_name = escape(
                meal["recipe_name"]
            )

            meal_type = escape(
                meal["meal_type"]
            )

            recipe_url = meal.get(
                "recipe_url"
            )

            # ------------------------------------------
            # Validated original recipe URL
            # ------------------------------------------

            if recipe_url:

                safe_recipe_url = escape(
                    str(recipe_url),
                    quote=True,
                )

                link_html = (
                    '<a class="iamp-recipe-link" '
                    f'href="{safe_recipe_url}" '
                    'target="_blank" '
                    'rel="noopener noreferrer">'
                    f'{safe_recipe_url}'
                    '</a>'
                )

            else:

                link_html = (
                    '<span class="iamp-recipe-unavailable">'
                    'Original recipe link unavailable'
                    '</span>'
                )

            # ------------------------------------------
            # One vertical meal row
            # ------------------------------------------

            meal_lines.append(
                '<div class="iamp-meal-line">'

                '<span class="iamp-meal-label">'
                f'{meal_type}'
                '</span>'

                '<div class="iamp-meal-content">'

                '<div class="iamp-meal-name">'
                f'{recipe_name}'
                '</div>'

                f'{link_html}'

                '</div>'

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

    # ------------------------------------------------------
    # Render
    # ------------------------------------------------------

    if html_parts:

        st.markdown(
            "\n".join(html_parts),
            unsafe_allow_html=True,
        )

    else:

        st.info(
            "No meals are available to display."
        )


# ==========================================================
# 6. ADAPTIVE REPLANNING MEAL LABEL
# ==========================================================

def meal_label(meal):
    """Create a readable meal label for adaptive replanning.

    This function deliberately returns text only.
    The skip-meal dropdown should not contain URLs.
    """

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

    recipe_name = get_recipe_name(
        recipe_id
    )

    return (
        f"{friendly_date(meal_date)}"
        f" — {str(meal_type).title()}"
        f" — {recipe_name}"
    )
