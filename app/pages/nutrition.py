"""Nutrition display for future planner output."""
import streamlit as st

st.title("Nutrition")
result = st.session_state.get("planner_result") or {}
summary = result.get("nutrition_summary") or result.get("nutrition")
if not summary:
    st.info("No nutrition results yet. Connect the real planner to populate this page.")
else:
    if isinstance(summary, dict):
        rows = [{"Date": day, **values} for day, values in summary.items() if isinstance(values, dict)]
        if rows:
            st.dataframe(rows, hide_index=True, use_container_width=True)
        else:
            st.json(summary)
    else:
        st.write(summary)
