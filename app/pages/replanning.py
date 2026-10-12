"""Simple skip-meal flow using the existing replanning backend."""
from datetime import date
import streamlit as st
from app.components.planner_bridge import skip_meal
from app.components.presentation import friendly_date, meal_label, show_meals

st.title('Adjust your meal plan')
result = st.session_state.get('planner_result') or {}
meals = (result.get('plan') or {}).get('selected_meals') or []
plan_state = st.session_state.get('live_plan_state')
user_state = st.session_state.get('planner_user_state')
planner = st.session_state.get('live_planner')
if not meals or plan_state is None or user_state is None or planner is None:
    st.info('Generate a meal plan first to make changes.')
else:
    completed = set(st.session_state.get('completed_slot_ids') or set())
    lookup = {}
    for meal in meals:
        slot = meal.get('slot') or {}
        slot_id = slot.get('slot_id')
        day = str(slot.get('date') or str(slot_id or '')[:10])
        if slot_id and slot_id not in completed and day >= date.today().isoformat():
            label = f"{friendly_date(day)} · {str(slot.get('meal_type') or 'Meal').title()} — {meal_label(meal)}"
            lookup[label] = slot_id
    st.subheader('Skip an upcoming meal')
    if lookup:
        selected = st.selectbox('Choose the meal you will skip', list(lookup))
        if st.button('Skip meal and update plan', type='primary'):
            with st.spinner('Updating your meals and shopping list...'):
                try:
                    updated, updated_state = skip_meal(planner, user_state, plan_state, lookup[selected], completed)
                except Exception as exc:
                    st.error('We could not update your plan. Please try again.')
                    with st.expander('Technical details'):
                        st.code(str(exc))
                else:
                    st.session_state.planner_result = updated
                    st.session_state.live_plan_state = updated_state
                    st.success('Your meal plan has been updated.')
                    st.rerun()
    else:
        st.info('There are no upcoming meals available to skip.')
    with st.expander('Mark meals already eaten'):
        labels = {}
        for meal in meals:
            slot = meal.get('slot') or {}
            slot_id = slot.get('slot_id')
            if slot_id:
                label = f"{friendly_date(slot.get('date'))} · {str(slot.get('meal_type') or 'Meal').title()} — {meal_label(meal)}"
                labels[label] = slot_id
        selected_completed = st.multiselect('Meals completed', list(labels), default=[label for label, slot_id in labels.items() if slot_id in completed])
        if st.button('Save completed meals'):
            st.session_state.completed_slot_ids = {labels[label] for label in selected_completed}
            st.success('Completed meals saved.')
    st.subheader('Current meals')
    show_meals(meals)
