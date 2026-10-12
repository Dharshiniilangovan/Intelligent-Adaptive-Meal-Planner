"""Real planner overview; no invented results."""
import streamlit as st
from app.components.ui_state import result_basket

st.title('Your meal plan')
confirmed = st.session_state.get('confirmed_user_state') or {}
result = st.session_state.get('planner_result') or {}
plan = result.get('plan') or {}
basket = result_basket()
meals = plan.get('selected_meals') or []
cols = st.columns(3)
cols[0].metric('Budget', f"S${confirmed['budget']:.2f}" if confirmed else 'Not set')
cols[1].metric('Meals selected', len(meals) if result else '—')
cost = basket.get('projected_cost')
cols[2].metric('Grocery planning cost', f'S${cost:.2f}' if cost is not None else 'Unavailable')
if not result:
    st.info('Analyze your request and generate a meal plan to see results here.')
else:
    validation = result.get('validation') or {}
    st.write('**Validation:**', validation.get('status', 'unknown'))
    for issue in validation.get('issues') or []:
        st.warning(str(issue))
    st.subheader('Selected meals')
    for meal in meals:
        slot = meal.get('slot') or {}
        with st.container(border=True):
            st.write(f"**{slot.get('slot_id', 'Meal')}**")
            st.write('Recipe ID:', meal.get('recipe_id') or (meal.get('decision') or {}).get('recipe_id') or 'Unavailable')
    if not meals:
        st.warning('No meals were selected. Review the validation issues.')
