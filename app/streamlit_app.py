"""IAMP Streamlit entry point. Run from the repository root."""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.components.ui_state import initialize_state
from app.components.theme import apply_theme

st.set_page_config(
    page_title="IAMP | Meal planning",
    layout="wide",
    initial_sidebar_state="expanded",
)
initialize_state()
apply_theme()

with st.sidebar:
    st.markdown(
        '<div class="iamp-brand"><div class="iamp-wordmark">IAMP</div>'
        '<div class="iamp-tagline">Intelligent Adaptive Meal Planner<br>'
        'A simpler way to plan everyday meals.</div></div>',
        unsafe_allow_html=True,
    )
    st.divider()

pages = {
    "Planning": [
        st.Page("pages/meal_planner.py", title="Create a meal plan", default=True),
    ],
    "Your workspace": [
        st.Page("pages/dashboard.py", title="Overview"),
        st.Page("pages/pantry.py", title="My pantry"),
        st.Page("pages/groceries.py", title="Shopping list"),
        st.Page("pages/nutrition.py", title="Nutrition"),
        st.Page("pages/replanning.py", title="Adjust my plan"),
    ],
}

navigation = st.navigation(pages)
navigation.run()
