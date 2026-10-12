"""Compact meal planning UI with explicit confirmation and live planner integration."""
from datetime import date
import re

import streamlit as st
from app.components.ui_state import current_pantry, csv_values, normalized_list
from src.input_parser.natural_language_parser import UserInputParser
from app.components.planner_bridge import generate


@st.cache_resource
def get_parser():
    return UserInputParser()


def duration_hint(text):
    match = re.search(r"\b(?:for\s+)?(\d{1,2})\s*days?\b", text, re.I)
    return int(match.group(1)) if match and 1 <= int(match.group(1)) <= 30 else None


def meal_hints(text):
    # UI assistance only, not a substitute for confirmed preferences.
    return [meal for meal in ("breakfast", "lunch", "dinner")
            if re.search(rf"\b{meal}s?\b", text, re.I)]


def comma_text(value):
    return ", ".join(normalized_list(value))


st.title("Plan meals that fit your life")
st.caption("Describe what you need. Review the interpretation before creating a meal plan.")

request = st.text_area(
    "What would you like to plan?",
    placeholder="Plan vegetarian lunches and dinners for 3 days under S$100, avoiding peanuts.",
    height=115,
    key="natural_language_request",
)

left, right = st.columns([1, 3])
with left:
    analyze = st.button("Analyze request →", type="primary", use_container_width=True)
with right:
    st.caption("The parser may miss details. Nothing is sent to the Planner until you confirm.")

if analyze:
    if not request.strip():
        st.error("Enter a request first.")
    else:
        try:
            parsed = get_parser().parse(request).to_dict()
        except Exception as exc:
            st.error(f"Could not analyze your request: {exc}")
        else:
            st.session_state.parsed_result = parsed
            st.session_state.confirmed_user_state = None
            st.session_state.planner_result = None
            st.session_state.pop("live_plan_state", None)
            st.session_state.pop("live_planner", None)
            st.session_state.pop("planner_user_state", None)
            st.session_state.last_request = request
            st.session_state.request_revision = st.session_state.get("request_revision", 0) + 1

parsed = st.session_state.get("parsed_result")
if parsed is not None:
    data = parsed.get("data") or {}
    revision = st.session_state.get("request_revision", 0)
    source_text = st.session_state.get("last_request", "")
    parsed_meals = [x.lower() for x in normalized_list(data.get("preferred_meal_types"))]
    parsed_diet = normalized_list(data.get("dietary_restrictions"))
    initial_meals = [m for m in ("breakfast", "lunch", "dinner")
                     if m in parsed_meals or m in meal_hints(source_text)]
    initial_days = duration_hint(source_text)
    budget = data.get("budget")
    allergies = normalized_list(data.get("allergies"))

    st.divider()
    st.subheader("Review your preferences")
    st.caption("These are suggestions, not confirmed facts. Please verify allergies and any missing fields.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Budget", f"S${float(budget):.2f}" if budget is not None else "Not detected")
    c2.metric("Duration", f"{initial_days} days" if initial_days else "Not detected")
    c3.metric("Meals", ", ".join(initial_meals).title() if initial_meals else "Not detected")

    d1, d2 = st.columns(2)
    with d1:
        st.write("**Dietary preferences:** " + (", ".join(parsed_diet) or "None detected"))
    with d2:
        st.write("**Allergies:** " + (", ".join(allergies) or "None detected — please confirm"))

    if not parsed.get("valid", False):
        st.warning("The parser reported invalid or incomplete data. Review the details before confirming.")
    for problem in (parsed.get("errors") or []) + (parsed.get("missing_fields") or []):
        st.caption(f"Parser note: {problem}")

    st.markdown("#### Confirm the essentials")
    with st.form(f"review_{revision}"):
        col_a, col_b = st.columns(2)
        with col_a:
            entered_budget = st.number_input(
                "Budget (SGD) *", min_value=0.01,
                value=float(budget) if budget is not None and float(budget) > 0 else None,
                placeholder="Enter your budget", key=f"budget_{revision}",
            )
            days = st.number_input(
                "Number of days *", min_value=1, max_value=30,
                value=initial_days, placeholder="Enter number of days", key=f"days_{revision}",
            )
        with col_b:
            start = st.date_input("Start date *", value=date.today(), key=f"start_{revision}")
            meals = st.multiselect(
                "Meal types *", ["breakfast", "lunch", "dinner"],
                default=initial_meals, key=f"meals_{revision}",
            )

        st.markdown("**Safety & dietary needs**")
        col_c, col_d = st.columns(2)
        diet_options = ["Vegetarian", "Vegan", "Gluten-Free", "Dairy-Free", "Halal", "Kosher"]
        with col_c:
            diet = st.multiselect(
                "Dietary restrictions", diet_options,
                default=[x for x in parsed_diet if x in diet_options],
                key=f"diet_{revision}",
            )
            other_diet = st.text_input(
                "Other dietary restrictions", value=", ".join(x for x in parsed_diet if x not in diet_options),
                placeholder="Comma-separated", key=f"other_diet_{revision}",
            )
        with col_d:
            allergy_text = st.text_input(
                "Allergies (comma-separated)", value=comma_text(data.get("allergies")),
                placeholder="e.g. peanut, shellfish", key=f"allergies_{revision}",
            )
            allergy_confirmed = st.checkbox(
                "I have checked my allergies (including confirming none if blank) *",
                key=f"allergy_confirm_{revision}",
            )

        with st.expander("More preferences (optional)", expanded=False):
            e1, e2 = st.columns(2)
            with e1:
                cuisines = st.text_input("Preferred cuisines", value=comma_text(data.get("preferred_cuisines")), key=f"cuisines_{revision}")
                likes = st.text_input("Preferred ingredients", value=comma_text(data.get("preferred_ingredients")), key=f"likes_{revision}")
                dislikes = st.text_input("Disliked ingredients", value=comma_text(data.get("disliked_ingredients")), key=f"dislikes_{revision}")
            with e2:
                parsed_hours = data.get("cook_time_preference_hrs")
                cook_minutes = st.number_input(
                    "Maximum cooking time per meal (minutes)", min_value=1, max_value=600,
                    value=round(float(parsed_hours) * 60) if parsed_hours is not None else None,
                    placeholder="No limit", key=f"cook_{revision}",
                )
                frequency = st.text_input("Cooking frequency", value=str(data.get("cook_frequency") or ""), key=f"frequency_{revision}")
                flexible = st.checkbox("Budget is flexible", value=bool(data.get("budget_flexible", False)), key=f"flexible_{revision}")
            st.caption(f"Pantry ingredients saved: {len(st.session_state.get('pantry_items', []))}. Manage them on the Pantry page.")

        submitted = st.form_submit_button("Confirm preferences →", type="primary", use_container_width=True)

    if submitted:
        if entered_budget is None or entered_budget <= 0:
            st.error("Enter a budget greater than zero.")
        elif days is None:
            st.error("Enter the number of days.")
        elif not meals:
            st.error("Choose at least one meal type.")
        elif not allergy_confirmed:
            st.error("Please review and confirm your allergy information.")
        else:
            confirmed = dict(data)
            confirmed.update({
                "budget": float(entered_budget),
                "budget_remaining": float(entered_budget),
                "days": int(days),
                "start_date": start.isoformat(),
                "preferred_meal_types": meals,
                "dietary_restrictions": list(dict.fromkeys(diet + csv_values(other_diet))),
                "allergies": csv_values(allergy_text),
                "preferred_cuisines": csv_values(cuisines),
                "preferred_ingredients": csv_values(likes),
                "disliked_ingredients": csv_values(dislikes),
                "cook_time_preference_hrs": cook_minutes / 60 if cook_minutes is not None else None,
                "cook_frequency": frequency.strip() or None,
                "budget_flexible": flexible,
                "ingredient_availability": current_pantry(),
            })
            st.session_state.confirmed_user_state = confirmed
            st.session_state.planner_result = None
            st.session_state.pop("live_plan_state", None)
            st.success("Preferences confirmed and saved for this session.")

    confirmed = st.session_state.get("confirmed_user_state")
    if confirmed:
        st.markdown("#### Ready for meal generation")
        st.write(f"**{confirmed['days']} days** · **{', '.join(confirmed['preferred_meal_types']).title()}** · **S${confirmed['budget']:.2f} budget**")
        with st.expander("View confirmed User State"):
            st.json(confirmed)
        if st.button("Generate meal plan", type="primary", use_container_width=True):
            with st.spinner("Planning meals and calculating groceries. This may take several minutes..."):
                try:
                    result, plan_state, planner_state, planner = generate(confirmed)
                except Exception as exc:
                    st.error(f"Meal generation failed: {exc}")
                else:
                    st.session_state.planner_result = result
                    st.session_state.live_plan_state = plan_state
                    st.session_state.planner_user_state = planner_state
                    st.session_state.live_planner = planner
                    st.session_state.completed_slot_ids = set()
                    st.success("Meal planning finished. See Dashboard, Groceries, and Nutrition.")
        result = st.session_state.get("planner_result")
        if result:
            validation = result.get("validation") or {}
            st.write("**Plan status:**", validation.get("status", "unknown"))
            for issue in validation.get("issues") or []:
                st.warning(str(issue))
            meals = (result.get("plan") or {}).get("selected_meals") or []
            for meal in meals:
                slot = meal.get("slot") or {}
                with st.container(border=True):
                    st.write(f"**{slot.get('slot_id', 'Meal')}**")
                    st.write("Recipe:", meal.get("recipe_id") or (meal.get("decision") or {}).get("recipe_id") or "See plan details")
