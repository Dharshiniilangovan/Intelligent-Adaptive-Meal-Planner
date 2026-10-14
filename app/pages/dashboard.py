"""Meal plan overview with original recipe ingredient quantities."""
import streamlit as st

from app.components.presentation import money, show_meals, friendly_date
from app.components.preference_summary import show_preferences
from app.components.recipe_lookup import get_recipe_details
from app.components.recipe_ingredients import ingredients_for_recipe

st.title('Your meal plan')
st.caption('Your planned meals and their needed ingredients.')

result = st.session_state.get('planner_result') or {}
confirmed = st.session_state.get('confirmed_user_state') or {}

if st.session_state.get('pantry_changed_since_plan'):
    st.info('Your pantry has changed since this plan was created. The displayed plan is the previous snapshot.')

if not result:
    st.info('Your meal plan will appear here once you generate it.')
else:
    plan = result.get('plan') or {}
    meals = plan.get('selected_meals') or []
    basket = result.get('grocery_basket') or result.get('final_grocery_basket') or {}
    cost = basket.get('planning_cost')
    if cost is None:
        cost = basket.get('projected_cost')
    budget = confirmed.get('budget')
    remaining = float(budget) - float(cost) if budget is not None and cost is not None else None

    a, b, c = st.columns(3)
    a.metric('Meals planned', len(meals))
    b.metric('Grocery total', money(cost))
    c.metric('Budget remaining', money(remaining))
    st.divider()

    if meals:
        st.subheader('Your meals')
        show_meals(meals)
        st.divider()
        st.subheader('Ingredients for each planned meal')
        st.caption('Original quantities per serving from recipe_ingredient_mapping.csv. These are recipe requirements, not quantities remaining to buy. No unit conversion is applied.')
        for index, meal in enumerate(meals):
            if not isinstance(meal, dict):
                continue
            slot = meal.get('slot') or {}
            decision = meal.get('decision') or {}
            recipe_id = meal.get('recipe_id') or decision.get('recipe_id') or decision.get('selected_recipe_id')
            details = get_recipe_details(recipe_id)
            day = slot.get('date') or str(slot.get('slot_id') or '')[:10]
            kind = str(slot.get('meal_type') or 'Meal').title()
            heading = f"{friendly_date(day)} · {kind} — {details['recipe_name']}"
            with st.expander(heading, expanded=(len(meals) == 1)):
                ingredients = ingredients_for_recipe(recipe_id)
                if ingredients:
                    st.dataframe(
                        ingredients,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            'ingredient': st.column_config.TextColumn('Ingredient'),
                            'quantity': st.column_config.TextColumn('Quantity per serving'),
                            'unit': st.column_config.TextColumn('Original unit'),
                        },
                    )
                    st.caption('Quantities shown are per serving, exactly as recorded in the Recipe KB.')
                else:
                    st.info('No ingredient mapping is available for this recipe.')
    else:
        st.info('No meals were selected for this plan.')

    if remaining is not None and remaining < 0:
        st.warning('The estimated grocery total exceeds the budget.')
    elif cost is None:
        st.info('The complete grocery cost is not available.')

    if confirmed:
        with st.expander('Your preferences'):
            show_preferences(confirmed)
