
"""Customer-facing meal plan dashboard."""

import streamlit as st

from app.components.presentation import money, show_meals
from app.components.preference_summary import show_preferences


st.title("Your meal plan")
st.caption("Your meals, organized around your preferences and budget.")


# def show_meals(meals):
#     """Display recipe names in equal-sized meal cards."""

#     import streamlit as st

#     grouped = {}

#     for meal in meals:
#         slot = meal.get("slot") or {}
#         decision = meal.get("decision") or {}

#         meal_date = (
#             slot.get("date")
#             or slot.get("slot_id", "").split("_")[0]
#         )

#         meal_type = (
#             slot.get("meal_type")
#             or "Meal"
#         )

#         recipe_id = (
#             meal.get("recipe_id")
#             or decision.get("recipe_id")
#             or decision.get("selected_recipe_id")
#         )

#         recipe_name = get_recipe_name(recipe_id)

#         grouped.setdefault(str(meal_date), []).append({
#             "meal_type": str(meal_type).title(),
#             "recipe_name": recipe_name,
#         })

#     for meal_date, day_meals in sorted(grouped.items()):

#         try:
#             formatted_date = date.fromisoformat(
#                 meal_date
#             ).strftime("%a, %d %b %Y")
#         except ValueError:
#             formatted_date = meal_date

#         st.markdown(f"#### {formatted_date}")

#         columns = st.columns(2, gap="medium")

#         for index, meal in enumerate(day_meals):

#             with columns[index % 2]:

#                 with st.container(
#                     border=True,
#                     height=150,
#                 ):
#                     st.caption(meal["meal_type"])

#                     st.markdown(
#                         f"**{meal['recipe_name']}**"
#                     )

result = st.session_state.get("planner_result") or {}
if st.session_state.get("pantry_changed_since_plan"):
    st.info(
        "Your pantry has changed since this meal plan was created. "
        "The meals and shopping list shown are from your previous plan. "
        "Generate an updated plan to include your new ingredients."
    )
confirmed = st.session_state.get("confirmed_user_state") or {}


if not result:
    st.info(
        "Your meal plan will appear here once you "
        "generate it."
    )

else:
    plan = result.get("plan") or {}
    meals = plan.get("selected_meals") or []

    basket = result.get("grocery_basket") or {}

    cost = basket.get("planning_cost")

    if cost is None:
        cost = basket.get("projected_cost")

    budget = confirmed.get("budget")

    # ---------------------------------------------
    # Overview
    # ---------------------------------------------

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Meals planned",
        len(meals),
    )

    col2.metric(
        "Grocery total",
        money(cost),
    )

    remaining = None

    if budget is not None and cost is not None:
        remaining = float(budget) - float(cost)

    col3.metric(
        "Budget remaining",
        money(remaining),
    )

    st.divider()

    # ---------------------------------------------
    # Meals
    # ---------------------------------------------

    if meals:
        st.subheader("Your meals")

        show_meals(meals)

    else:
        st.info(
            "We couldn't find meals matching your "
            "current preferences. Try adjusting "
            "your budget or meal requirements."
        )

    # ---------------------------------------------
    # Budget information
    # ---------------------------------------------

    if remaining is not None and remaining < 0:
        st.warning(
            "Your grocery list is above your budget. "
            "Consider adjusting your meal preferences."
        )

    elif cost is None:
        st.info(
            "The complete grocery cost isn't available yet."
        )

    # ---------------------------------------------
    # Preferences
    # ---------------------------------------------

    if confirmed:
        with st.expander("Your preferences"):
            show_preferences(confirmed)
