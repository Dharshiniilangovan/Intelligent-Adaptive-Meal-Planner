
"""IAMP live meal planning page.

Natural-language request -> User State confirmation ->
live meal generation -> saved results.

No demo loader or saved-example mode is used.
"""

from datetime import date
import re

import streamlit as st

from app.components.ui_state import (
    current_pantry,
    csv_values,
    normalized_list,
)
from app.components.planner_bridge import generate
from app.components.preference_summary import show_preferences
from app.components.presentation import show_meals
from app.components.state_persistence import save_ui_state

from src.input_parser.natural_language_parser import UserInputParser


@st.cache_resource
def get_parser():
    return UserInputParser()


def duration_hint(text):
    match = re.search(
        r"\b(?:for\s+)?(\d{1,2})\s*days?\b",
        text,
        re.IGNORECASE,
    )
    days = int(match.group(1)) if match else None
    return days if days is not None and 1 <= days <= 30 else None


def meal_hints(text):
    return [
        meal
        for meal in ("breakfast", "lunch", "dinner")
        if re.search(rf"\b{meal}s?\b", text, re.IGNORECASE)
    ]


def comma_text(value):
    return ", ".join(normalized_list(value))


def reset_plan():
    """Clear an old plan only when explicitly replacing it."""

    st.session_state["planner_result"] = None

    # Retained as False for compatibility with existing pages.
    st.session_state["preview_mode_active"] = False

    for key in (
        "live_plan_state",
        "live_planner",
        "planner_user_state",
    ):
        st.session_state.pop(key, None)

    st.session_state["completed_slot_ids"] = set()


# ============================================================
# PAGE HEADER
# ============================================================

st.title("Plan meals that fit your life")

st.caption(
    "Describe your needs and review the details "
    "before creating your meal plan."
)


# ============================================================
# NATURAL LANGUAGE REQUEST
# ============================================================

request = st.text_area(
    "What would you like to plan?",
    placeholder=(
        "Plan vegetarian lunches and dinners for 3 days "
        "under S$100, avoiding peanuts."
    ),
    height=115,
    key="natural_language_request",
)


if st.button("Analyze request", type="primary"):

    if not request.strip():
        st.error("Enter a request first.")

    else:
        try:
            parsed = get_parser().parse(request).to_dict()

        except Exception as exc:
            st.error(f"Could not analyze your request: {exc}")

        else:
            st.session_state["parsed_result"] = parsed
            st.session_state["confirmed_user_state"] = None
            st.session_state["last_request"] = request

            st.session_state["request_revision"] = (
                st.session_state.get("request_revision", 0) + 1
            )

            # Keep the existing plan visible until the user
            # explicitly generates a replacement.
            st.session_state["preferences_changed_since_plan"] = True

            save_ui_state()

            st.success(
                "Request analyzed. Review your preferences below."
            )


# ============================================================
# REVIEW PARSED PREFERENCES
# ============================================================

parsed = st.session_state.get("parsed_result")

if parsed is not None:

    data = parsed.get("data") or {}
    revision = st.session_state.get("request_revision", 0)
    source_text = st.session_state.get("last_request", "")

    parsed_meals = [
        meal.lower()
        for meal in normalized_list(
            data.get("preferred_meal_types")
        )
    ]

    initial_meals = [
        meal
        for meal in ("breakfast", "lunch", "dinner")
        if meal in parsed_meals or meal in meal_hints(source_text)
    ]

    initial_days = duration_hint(source_text)
    parsed_diet = normalized_list(data.get("dietary_restrictions"))
    parsed_budget = data.get("budget")

    st.divider()
    st.subheader("Review your preferences")

    st.caption(
        "Check the information carefully, especially "
        "allergies and missing fields."
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Budget",
        (
            f"S${float(parsed_budget):.2f}"
            if parsed_budget is not None
            else "Not detected"
        ),
    )

    col2.metric(
        "Duration",
        f"{initial_days} days" if initial_days else "Not detected",
    )

    col3.metric(
        "Meals",
        ", ".join(m.title() for m in initial_meals)
        or "Not detected",
    )

    # ========================================================
    # PREFERENCE CONFIRMATION FORM
    # ========================================================

    with st.form(f"confirm_{revision}"):

        left, right = st.columns(2)

        with left:

            budget = st.number_input(
                "Budget (SGD) *",
                min_value=0.01,
                value=(
                    float(parsed_budget)
                    if parsed_budget is not None
                    and float(parsed_budget) > 0
                    else None
                ),
                placeholder="Enter your budget",
                key=f"budget_{revision}",
            )

            days = st.number_input(
                "Number of days *",
                min_value=1,
                max_value=30,
                value=initial_days,
                placeholder="Enter number of days",
                key=f"days_{revision}",
            )

        with right:

            start = st.date_input(
                "Start date *",
                value=date.today(),
                key=f"start_{revision}",
            )

            meals = st.multiselect(
                "Meal types *",
                ["breakfast", "lunch", "dinner"],
                default=initial_meals,
                key=f"meals_{revision}",
            )

        st.markdown("**Safety and dietary needs**")

        left, right = st.columns(2)

        diet_options = [
            "Vegetarian",
            "Vegan",
            "Gluten-Free",
            "Dairy-Free",
            "Halal",
            "Kosher",
        ]

        with left:

            diet = st.multiselect(
                "Dietary restrictions",
                diet_options,
                default=[
                    x for x in parsed_diet if x in diet_options
                ],
                key=f"diet_{revision}",
            )

            other_diet = st.text_input(
                "Other dietary restrictions",
                value=", ".join(
                    x for x in parsed_diet if x not in diet_options
                ),
                key=f"other_diet_{revision}",
            )

        with right:

            allergy_text = st.text_input(
                "Allergies (comma-separated)",
                value=comma_text(data.get("allergies")),
                placeholder="e.g. peanut, shellfish",
                key=f"allergies_{revision}",
            )

            allergy_confirmed = st.checkbox(
                "I have checked my allergies "
                "(including none if blank) *",
                key=f"allergy_confirm_{revision}",
            )

        # ====================================================
        # OPTIONAL PREFERENCES
        # ====================================================

        with st.expander("More preferences (optional)"):

            left, right = st.columns(2)

            with left:

                                
                cuisine_options = [
                    "American",
                    "Asian",
                    "British",
                    "Caribbean",
                    "Central Europe",
                    "Chinese",
                    "Eastern Europe",
                    "French",
                    "Greek",
                    "Indian",
                    "Italian",
                    "Japanese",
                    "Korean",
                    "Mediterranean",
                    "Mexican",
                    "Middle Eastern",
                    "Nordic",
                    "South American",
                    "South East Asian",
                    "World",
                    "Kosher",
                ]

                parsed_cuisines = [
                    str(cuisine).strip().lower()
                    for cuisine in normalized_list(
                        data.get("preferred_cuisines")
                    )
                ]

                cuisines = st.multiselect(
                    "Preferred cuisines",
                    options=cuisine_options,
                    default=[
                        option
                        for option in cuisine_options
                        if option.lower() in parsed_cuisines
                    ],
                    placeholder="Choose your preferred cuisines",
                    key=f"cuisines_{revision}",
                )


                likes = st.text_input(
                    "Preferred ingredients",
                    value=comma_text(
                        data.get("preferred_ingredients")
                    ),
                    key=f"likes_{revision}",
                )

                dislikes = st.text_input(
                    "Disliked ingredients",
                    value=comma_text(
                        data.get("disliked_ingredients")
                    ),
                    key=f"dislikes_{revision}",
                )

            with right:

                parsed_hours = data.get(
                    "cook_time_preference_hrs"
                )

                cook_minutes = st.number_input(
                    "Maximum cooking time per meal (minutes)",
                    min_value=1,
                    max_value=600,
                    value=(
                        round(float(parsed_hours) * 60)
                        if parsed_hours is not None
                        else None
                    ),
                    placeholder="No limit",
                    key=f"cook_{revision}",
                )

                raw_frequency = data.get("cook_frequency")

                frequency = st.number_input(
                    "Cooking frequency (times per week)",
                    min_value=0,
                    max_value=21,
                    value=(
                        int(raw_frequency)
                        if str(raw_frequency or "").isdigit()
                        else None
                    ),
                    placeholder="Not specified",
                    key=f"frequency_{revision}",
                )

                flexible = st.checkbox(
                    "Budget is flexible",
                    value=bool(
                        data.get("budget_flexible", False)
                    ),
                    key=f"flexible_{revision}",
                )

            st.caption(
                "Pantry items saved: "
                f"{len(st.session_state.get('pantry_items', []))}. "
                "Edit them on the Pantry page."
            )

        submitted = st.form_submit_button(
            "Confirm preferences",
            type="primary",
            use_container_width=True,
        )

    # ========================================================
    # SAVE CONFIRMED USER STATE
    # ========================================================

    if submitted:

        if budget is None or budget <= 0:
            st.error("Enter a budget greater than zero.")

        elif days is None:
            st.error("Enter the number of days.")

        elif not meals:
            st.error("Choose at least one meal type.")

        elif not allergy_confirmed:
            st.error(
                "Please review and confirm your allergy information."
            )

        else:

            confirmed = dict(data)

            confirmed.update({
                "budget": float(budget),
                "budget_remaining": float(budget),
                "days": int(days),
                "start_date": start.isoformat(),
                "preferred_meal_types": meals,
                "dietary_restrictions": list(
                    dict.fromkeys(
                        diet + csv_values(other_diet)
                    )
                ),
                "allergies": csv_values(allergy_text),
                "preferred_cuisines": [
                    cuisine.lower()
                    for cuisine in cuisines
                ],
                "preferred_ingredients": csv_values(likes),
                "disliked_ingredients": csv_values(dislikes),
                "cook_time_preference_hrs": (
                    cook_minutes / 60
                    if cook_minutes is not None
                    else None
                ),
                "cook_frequency": frequency,
                "budget_flexible": flexible,
                "budget_cap": (
                    float(budget) + 5.0
                    if flexible
                    else None
                ),
                "ingredient_availability": current_pantry(),
            })

            st.session_state["confirmed_user_state"] = confirmed

            # Do not delete the previous meal plan here.
            st.session_state["preferences_changed_since_plan"] = True

            save_ui_state()

            st.success("Preferences saved.")

    # ========================================================
    # LIVE MEAL PLAN GENERATION
    # ========================================================

    confirmed = st.session_state.get(
        "confirmed_user_state"
    )

    if confirmed:

        st.markdown(
            "#### Ready to create your meal plan"
        )

        st.write(
            f"{confirmed['days']} days · "
            f"{', '.join(m.title() for m in confirmed['preferred_meal_types'])} "
            f"· S${confirmed['budget']:.2f} budget"
        )

        show_preferences(confirmed)

        if st.button(
            "Generate meal plan",
            type="primary",
            use_container_width=True,
        ):

            with st.spinner(
                "Generating meals and calculating groceries. "
                "This may take a while..."
            ):

                try:
                    result, plan_state, planner_state, planner = (
                        generate(confirmed)
                    )

                except Exception as exc:
                    st.error(
                        f"Meal generation failed: {exc}"
                    )

                else:

                    # Replace the old result only after successful
                    # generation, preserving it if generation fails.
                    reset_plan()

                    st.session_state["planner_result"] = result
                    st.session_state["live_plan_state"] = plan_state
                    st.session_state["planner_user_state"] = planner_state
                    st.session_state["live_planner"] = planner

                    st.session_state["pantry_changed_since_plan"] = False
                    st.session_state["preferences_changed_since_plan"] = False

                    save_ui_state()

                    st.success(
                        "Your meal plan is ready. "
                        "Open Overview, Shopping List or Nutrition."
                    )

    # ========================================================
    # DISPLAY THE CURRENT PLAN
    # ========================================================

    result = st.session_state.get("planner_result")

    if result:

        if (
            st.session_state.get("pantry_changed_since_plan")
            or st.session_state.get("preferences_changed_since_plan")
        ):
            st.info(
                "Your preferences or pantry have changed since "
                "this meal plan was generated. "
                "The current plan is still available, but "
                "generate an updated plan to include your changes."
            )

        selected_meals = (
            (result.get("plan") or {})
            .get("selected_meals")
            or []
        )

        if selected_meals:
            st.markdown("#### Your planned meals")
            show_meals(selected_meals)
        else:
            st.info(
                "No meals could be planned with your "
                "current preferences."
            )
