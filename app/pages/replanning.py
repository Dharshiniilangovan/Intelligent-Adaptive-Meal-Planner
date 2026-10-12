"""Live skip-meal integration with existing MultiMealPlanner."""
import streamlit as st
from app.components.planner_bridge import skip_meal

st.title('Adaptive replanning')
result = st.session_state.get('planner_result') or {}
plan = result.get('plan') or {}
meals = plan.get('selected_meals') or []
state = st.session_state.get('live_plan_state')
user_state = st.session_state.get('planner_user_state')
planner = st.session_state.get('live_planner')
if not meals or state is None or user_state is None or planner is None:
    st.info('Generate a meal plan before replanning.')
else:
    completed = set(st.session_state.get('completed_slot_ids') or set())
    choices = {}
    for meal in meals:
        slot = meal.get('slot') or {}
        slot_id = slot.get('slot_id')
        if slot_id and slot_id not in completed:
            choices[slot_id] = slot_id
    if not choices:
        st.info('No unfinished planned meals remain to skip.')
    else:
        selected = st.selectbox('Future meal to skip', list(choices))
        st.caption('Completed meals will be preserved. Do not mark meals completed unless they have actually been eaten.')
        if st.button('Skip selected meal and replan', type='primary'):
            with st.spinner('Recalculating meals, inventory and grocery basket...'):
                try:
                    updated, updated_state = skip_meal(planner, user_state, state, selected, completed)
                except Exception as exc:
                    st.error(f'Replanning failed: {exc}')
                else:
                    st.session_state.planner_result = updated
                    st.session_state.live_plan_state = updated_state
                    st.success('Replanning completed. Review the updated plan and budget.')
                    st.rerun()
    with st.expander('Mark completed meals'):
        all_ids = [m.get('slot', {}).get('slot_id') for m in meals]
        all_ids = [x for x in all_ids if x]
        selected_completed = st.multiselect('Already completed', all_ids, default=[x for x in completed if x in all_ids])
        if st.button('Save completed meals'):
            st.session_state.completed_slot_ids = set(selected_completed)
            st.success('Completed meal selection saved.')
    st.subheader('Current validation')
    st.json(result.get('validation') or {})
