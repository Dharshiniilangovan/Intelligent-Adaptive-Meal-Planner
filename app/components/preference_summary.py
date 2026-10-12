"""Human-readable User State summary, without changing planner data."""
import streamlit as st


def readable_list(values, empty='Not specified'):
    return ', '.join(str(v) for v in (values or [])) or empty


def show_preferences(state):
    st.subheader('Your planning preferences')
    a, b, c = st.columns(3)
    a.metric('Budget', f"S${float(state['budget']):.2f}")
    b.metric('Duration', f"{state['days']} days")
    c.metric('Meals per day', len(state.get('preferred_meal_types') or []))
    left, right = st.columns(2)
    with left:
        st.write('**Start date**', state.get('start_date', 'Not specified'))
        st.write('**Meal types**', readable_list(state.get('preferred_meal_types')))
        st.write('**Dietary restrictions**', readable_list(state.get('dietary_restrictions'), 'None confirmed'))
        st.write('**Allergies**', readable_list(state.get('allergies'), 'None confirmed'))
        st.write('**Preferred cuisines**', readable_list(state.get('preferred_cuisines'), 'Any cuisine'))
        st.write('**Preferred ingredients**', readable_list(state.get('preferred_ingredients')))
    with right:
        st.write('**Disliked ingredients**', readable_list(state.get('disliked_ingredients'), 'None'))
        hours = state.get('cook_time_preference_hrs')
        st.write('**Cooking time limit**', f'{hours * 60:g} minutes' if hours is not None else 'No limit specified')
        st.write('**Cooking frequency**', state.get('cook_frequency') if state.get('cook_frequency') is not None else 'Not specified')
        st.write('**Budget flexibility**', 'Flexible' if state.get('budget_flexible') else 'Strict')
        cap = state.get('budget_cap')
        if cap is not None:
            st.write('**Maximum allowed budget**', f'S${float(cap):.2f}')
        st.write('**Pantry ingredients**', f"{len(state.get('ingredient_availability') or {})} confirmed")
