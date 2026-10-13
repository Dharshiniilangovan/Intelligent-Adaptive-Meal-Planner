
"""Display customer-friendly IAMP meal-planning preferences.

The canonical User State does not contain planning duration
or start date. These are stored separately in Streamlit.
"""

import streamlit as st


def readable_list(value):
    """Format preference lists for display."""

    if not value:
        return "No preference"

    if isinstance(value, str):
        return value.strip() or "No preference"

    if isinstance(value, (list, tuple, set)):
        values = [
            str(item).strip().title()
            for item in value
            if str(item).strip()
        ]
        return ", ".join(values) if values else "No preference"

    return str(value)


def show_preferences(state):
    """Display the confirmed preferences without exposing JSON."""

    if not state:
        st.info("No preferences have been confirmed yet.")
        return

    st.subheader("Your planning preferences")

    budget = state.get("budget")

    days = st.session_state.get("planning_days")

    meal_types = state.get("preferred_meal_types") or []

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Budget",
        f"S${float(budget):.2f}"
        if budget is not None
        else "Not specified",
    )

    col2.metric(
        "Duration",
        f"{days} days"
        if days is not None
        else "Not specified",
    )

    col3.metric(
        "Meals per day",
        len(meal_types),
    )

    left, right = st.columns(2)

    with left:

        st.markdown("**Dietary preferences**")

        st.write(
            "Dietary restrictions:",
            readable_list(
                state.get("dietary_restrictions")
            ),
        )

        st.write(
            "Allergies:",
            readable_list(
                state.get("allergies")
            ),
        )

        st.write(
            "Preferred cuisines:",
            readable_list(
                state.get("preferred_cuisines")
            ),
        )

        st.write(
            "Preferred ingredients:",
            readable_list(
                state.get("preferred_ingredients")
            ),
        )

        st.write(
            "Disliked ingredients:",
            readable_list(
                state.get("disliked_ingredients")
            ),
        )

    with right:

        st.markdown("**Cooking preferences**")

        cook_time = state.get(
            "cook_time_preference_hrs"
        )

        if cook_time is not None:
            try:
                minutes = round(float(cook_time) * 60)
                cook_time_text = f"{minutes} minutes"
            except (TypeError, ValueError):
                cook_time_text = "Not specified"
        else:
            cook_time_text = "Not specified"

        st.write(
            "Maximum cooking time:",
            cook_time_text,
        )

        frequency = state.get("cook_frequency")

        st.write(
            "Cooking frequency:",
            (
                f"{frequency} times per week"
                if frequency is not None
                else "Not specified"
            ),
        )

        st.write(
            "Budget flexibility:",
            "Flexible"
            if state.get("budget_flexible")
            else "Fixed",
        )

        start_date = st.session_state.get(
            "planning_start_date"
        )

        st.write(
            "Start date:",
            start_date or "Not specified",
        )

    pantry = state.get("ingredient_availability") or {}

    st.markdown("**Pantry ingredients**")

    if pantry:

        for ingredient, quantity in pantry.items():

            st.write(
                f"{str(ingredient).title()}: {quantity}"
            )

    else:

        st.caption(
            "No pantry ingredients have been added."
        )
