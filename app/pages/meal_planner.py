
"""IAMP meal planning with canonical User State and background jobs."""

from datetime import date
import math
import re

import streamlit as st

from app.components.ui_state import (
    current_pantry,
    csv_values,
    normalized_list,
)
from app.components.preference_summary import show_preferences
from app.components.presentation import show_meals
from app.components.state_persistence import (
    save_ui_state,
    get_workspace_id,
)
from app.components.planning_jobs import (
    start_job,
    read_job,
)
from app.components.user_state_adapter import (
    build_ui_user_state,
    save_canonical_user_state,
)
from src.input_parser.natural_language_parser import UserInputParser

from app.components.user_state_adapter import (
    build_ui_user_state,
    save_canonical_user_state,
)


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


def positive_float(value):
    try:
        number = float(value)
        if math.isfinite(number) and number > 0:
            return number
    except (TypeError, ValueError):
        pass
    return None


def unique_values(values):
    return list(dict.fromkeys(values))


st.title("Plan meals that fit your life")
st.caption(
    "Describe your needs and review the details "
    "before creating your meal plan."
)

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
            st.session_state["preferences_changed_since_plan"] = True
            save_ui_state()
            st.success("Request analyzed. Review your preferences below.")


parsed = st.session_state.get("parsed_result")

if parsed is not None:

    data = parsed.get("data") or {}
    revision = st.session_state.get("request_revision", 0)
    source_text = st.session_state.get("last_request", "")

    previous_state = (
        st.session_state.get("confirmed_user_state") or {}
    )

    parsed_meals = [
        str(x).strip().lower()
        for x in normalized_list(
            data.get("preferred_meal_types")
        )
    ]

    initial_meals = [
        meal
        for meal in ("breakfast", "lunch", "dinner")
        if meal in parsed_meals or meal in meal_hints(source_text)
    ]

    initial_days = duration_hint(source_text)

    if initial_days is None:
        initial_days = st.session_state.get("planning_days")

    parsed_budget = positive_float(data.get("budget"))

    parsed_diet = normalized_list(
        data.get("dietary_restrictions")
    )

    st.divider()
    st.subheader("Review your preferences")
    st.caption(
        "Check the information carefully, especially "
        "allergies and missing fields."
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Budget",
        f"S${parsed_budget:.2f}"
        if parsed_budget is not None else "Not detected",
    )
    col2.metric(
        "Duration",
        f"{initial_days} days"
        if initial_days else "Not detected",
    )
    col3.metric(
        "Meals",
        ", ".join(x.title() for x in initial_meals)
        or "Not detected",
    )

    # ========================================================
    # CONFIRMATION FORM
    # ========================================================

    with st.form(f"confirm_{revision}"):

        left, right = st.columns(2)

        with left:
            budget = st.number_input(
                "Budget (SGD) *",
                min_value=0.01,
                value=parsed_budget,
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
            saved_start = st.session_state.get(
                "planning_start_date"
            )

            try:
                initial_start = (
                    date.fromisoformat(saved_start)
                    if saved_start else date.today()
                )
            except (TypeError, ValueError):
                initial_start = date.today()

            start = st.date_input(
                "Start date *",
                value=initial_start,
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

        known_diet = {
            str(x).strip().lower()
            for x in parsed_diet
        }

        with left:
            diet = st.multiselect(
                "Dietary restrictions",
                diet_options,
                default=[
                    option for option in diet_options
                    if option.lower() in known_diet
                ],
                key=f"diet_{revision}",
            )

            other_diet = st.text_input(
                "Other dietary restrictions",
                value=", ".join(
                    str(x) for x in parsed_diet
                    if str(x).strip().lower()
                    not in {d.lower() for d in diet_options}
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
        # CUISINE AND COOKING PREFERENCES
        # ====================================================

        st.markdown("**Cuisine and cooking preferences**")

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

        parsed_cuisines = {
            str(x).strip().lower()
            for x in normalized_list(
                data.get("preferred_cuisines")
            )
        }

        cuisines = st.multiselect(
            "Preferred cuisines",
            options=cuisine_options,
            default=[
                option for option in cuisine_options
                if option.lower() in parsed_cuisines
            ],
            placeholder="Choose your preferred cuisines",
            key=f"cuisines_{revision}",
        )

        left, right = st.columns(2)

        with left:
            parsed_hours = positive_float(
                data.get("cook_time_preference_hrs")
            )

            initial_minutes = (
                max(1, min(600, round(parsed_hours * 60)))
                if parsed_hours is not None else None
            )

            cook_minutes = st.number_input(
                "Maximum cooking time per meal (minutes)",
                min_value=1,
                max_value=600,
                value=initial_minutes,
                placeholder="No limit",
                key=f"cook_{revision}",
            )

        with right:
            raw_frequency = data.get("cook_frequency")

            try:
                initial_frequency = (
                    int(raw_frequency)
                    if raw_frequency is not None else None
                )
            except (TypeError, ValueError):
                initial_frequency = None

            if initial_frequency is not None:
                initial_frequency = max(
                    0, min(21, initial_frequency)
                )

            frequency = st.number_input(
                "Cooking frequency (times per week)",
                min_value=0,
                max_value=21,
                value=initial_frequency,
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

        # ====================================================
        # OPTIONAL INGREDIENT PREFERENCES
        # ====================================================

        with st.expander("More preferences (optional)"):

            left, right = st.columns(2)

            with left:
                likes = st.text_input(
                    "Preferred ingredients",
                    value=comma_text(
                        data.get("preferred_ingredients")
                    ),
                    placeholder="e.g. broccoli, tofu, rice",
                    key=f"likes_{revision}",
                )

            with right:
                dislikes = st.text_input(
                    "Disliked ingredients",
                    value=comma_text(
                        data.get("disliked_ingredients")
                    ),
                    placeholder="e.g. mushroom, eggplant",
                    key=f"dislikes_{revision}",
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
    # BUILD AND SAVE CANONICAL USER STATE
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
            preferences = dict(data)

            preferences.update({
                "budget": float(budget),
                "cook_frequency": frequency,
                "cook_time_preference_hrs": (
                    cook_minutes / 60
                    if cook_minutes is not None else None
                ),
                "preferred_cuisines": cuisines,
                "dietary_restrictions": unique_values(
                    diet + csv_values(other_diet)
                ),
                "allergies": csv_values(allergy_text),
                "preferred_meal_types": meals,
                "preferred_ingredients": csv_values(likes),
                "disliked_ingredients": csv_values(dislikes),
                "budget_flexible": flexible,
            })

            # Keep the user ID stable for this workspace.
            existing_id = (
                st.session_state.get("user_id")
                or previous_state.get("user_id")
            )

            try:
                confirmed_state = build_ui_user_state(
                    confirmed=preferences,
                    pantry_items=st.session_state.get(
                        "pantry_items", []
                    ),
                    user_id=existing_id,
                )

                save_canonical_user_state(confirmed_state)

            except (OSError, TypeError, ValueError) as exc:
                st.error(
                    f"Could not save your preferences: {exc}"
                )

            else:
                st.session_state["user_id"] = (
                    confirmed_state["user_id"]
                )

                st.session_state["confirmed_user_state"] = (
                    confirmed_state
                )

                # These are planning parameters, not
                # fields of the canonical User State.
                st.session_state["planning_days"] = int(days)
                st.session_state["planning_start_date"] = (
                    start.isoformat()
                )

                st.session_state[
                    "preferences_changed_since_plan"
                ] = True

                save_ui_state()
                st.success("Preferences saved.")

    
    # ========================================================
    # BACKGROUND MEAL GENERATION
    # ========================================================

    confirmed = st.session_state.get(
        "confirmed_user_state"
    )

    if confirmed:

        days_to_plan = st.session_state.get(
            "planning_days"
        )

        start_to_plan = st.session_state.get(
            "planning_start_date"
        )

        st.markdown(
            "#### Ready to create your meal plan"
        )

        if days_to_plan:
            st.write(
                f"{days_to_plan} days · "
                f"{', '.join(str(x).title() for x in confirmed['preferred_meal_types'])} "
                f"· S${confirmed['budget']:.2f} budget"
            )

        show_preferences(confirmed)

        workspace_id = get_workspace_id()

        job_id = st.session_state.get(
            "planning_job_id"
        )

        job = (
            read_job(workspace_id, job_id)
            if job_id
            else None
        )

        is_generating = bool(
            job
            and job.get("status") in ("queued", "running")
        )

        if is_generating:
            st.info(
                "Your meal plan is being generated. "
                "You can visit other pages while it runs."
            )

        if st.button(
            "Generating meal plan..."
            if is_generating
            else "Generate meal plan",
            type="primary",
            use_container_width=True,
            disabled=is_generating,
        ):

            if not days_to_plan or not start_to_plan:
                st.error(
                    "Confirm your planning duration and "
                    "start date before generating meals."
                )

            else:
                try:
                    # ========================================
                    # 1. REBUILD CANONICAL USER STATE
                    # ========================================

                    latest_pantry = st.session_state.get(
                        "pantry_items", []
                    )

                    canonical_state = build_ui_user_state(
                        confirmed=confirmed,
                        pantry_items=latest_pantry,
                        user_id=(
                            st.session_state.get("user_id")
                            or confirmed.get("user_id")
                        ),
                    )

                    # ========================================
                    # 2. SAVE USER STATE AND PANTRY JSON
                    # ========================================

                    save_canonical_user_state(
                        canonical_state
                    )

                    # Keep the same user ID.
                    st.session_state["user_id"] = (
                        canonical_state["user_id"]
                    )

                    # Store the refreshed canonical state.
                    st.session_state[
                        "confirmed_user_state"
                    ] = canonical_state

                    # ========================================
                    # 3. BUILD TEMPORARY PLANNING PAYLOAD
                    # ========================================

                    planning_payload = dict(
                        canonical_state
                    )

                    # These are Planner-only parameters.
                    # They do NOT enter canonical User State.
                    planning_payload["days"] = int(
                        days_to_plan
                    )

                    planning_payload["start_date"] = (
                        start_to_plan
                    )

                    # ========================================
                    # 4. DEBUG USER STATE
                    # ========================================

                    print("\n" + "=" * 60)
                    print("[MEAL PLANNER] USER STATE CHECK")
                    print("=" * 60)

                    print(
                        "User ID:",
                        canonical_state["user_id"],
                    )

                    print(
                        "Budget:",
                        canonical_state["budget"],
                    )

                    print(
                        "Days:",
                        planning_payload["days"],
                    )

                    print(
                        "Start date:",
                        planning_payload["start_date"],
                    )

                    print(
                        "Pantry ingredients:",
                        canonical_state[
                            "ingredient_availability"
                        ],
                    )

                    print("=" * 60)

                    # ========================================
                    # 5. START BACKGROUND GENERATION
                    # ========================================

                    job_id = start_job(
                        workspace_id,
                        planning_payload,
                    )

                    st.session_state[
                        "planning_job_id"
                    ] = job_id

                    st.session_state[
                        "planning_job_error"
                    ] = None

                    # Preserve existing meal plan until
                    # the new plan finishes successfully.
                    save_ui_state()

                    print(
                        "[MEAL PLANNER] Background job started:",
                        job_id,
                    )

                    st.rerun()

                except Exception as exc:

                    print(
                        "[MEAL PLANNER ERROR]",
                        repr(exc),
                    )

                    st.error(
                        f"Could not start meal generation: {exc}"
                    )

    # ========================================================
    # DISPLAY CURRENT PLAN
    # ========================================================

    result = st.session_state.get(
        "planner_result"
    )

    if result:

        if (
            st.session_state.get(
                "pantry_changed_since_plan"
            )
            or st.session_state.get(
                "preferences_changed_since_plan"
            )
        ):
            st.info(
                "Your preferences or pantry have changed "
                "since this plan was created. "
                "The existing plan remains available."
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
