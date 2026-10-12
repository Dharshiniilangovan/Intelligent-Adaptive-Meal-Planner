"""Daily nutrition presented in familiar units."""
import streamlit as st
from app.components.presentation import friendly_date, number

st.title('Daily nutrition')
result = st.session_state.get('planner_result') or {}
summary = result.get('nutrition_summary') or {}
if not summary:
    st.info('Generate a meal plan to see your nutrition summary.')
else:
    rows = []
    for day, values in sorted(summary.items()):
        if not isinstance(values, dict):
            continue
        rows.append({
            'Day': friendly_date(day),
            'Calories (kcal)': number(values.get('calories'), 0),
            'Protein (g)': number(values.get('protein_g')),
            'Carbs (g)': number(values.get('carbs_g')),
            'Fat (g)': number(values.get('fat_g')),
            'Fibre (g)': number(values.get('fiber_g')),
        })
    if rows:
        st.dataframe(rows, hide_index=True, use_container_width=True)
        chart = {day: values.get('calories') for day, values in sorted(summary.items())
                 if isinstance(values, dict) and isinstance(values.get('calories'), (int, float))}
        if chart:
            st.subheader('Calories by day')
            st.bar_chart(chart)
    else:
        st.info('Daily nutrition information is not available.')
