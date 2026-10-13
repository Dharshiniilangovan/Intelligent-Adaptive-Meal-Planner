
"""IAMP Streamlit application entry point.

Run from the repository root:

    python -m streamlit run app/streamlit_app.py

Restores saved user preferences, pantry ingredients,
and generated meal-plan results between sessions.
"""

import sys
from pathlib import Path

# ============================================================
# PROJECT ROOT
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ============================================================
# IMPORTS
# ============================================================

import streamlit as st

from app.components.state_persistence import load_ui_state
from app.components.ui_state import initialize_state
from app.components.theme import apply_theme


# ============================================================
# STREAMLIT PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="IAMP | Meal planning",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# RESTORE SAVED USER STATE
# ============================================================

# Restore saved preferences, pantry, and generated plan
# before initializing any default session-state values.
load_ui_state()


# ============================================================
# INITIALIZE MISSING SESSION VALUES
# ============================================================

# initialize_state() must use setdefault() rather than
# unconditional assignments for persistent values.
initialize_state()

# These defaults should not overwrite restored data.
st.session_state.setdefault("planner_result", None)
st.session_state.setdefault("confirmed_user_state", None)
st.session_state.setdefault("parsed_result", None)
st.session_state.setdefault("pantry_items", [])
st.session_state.setdefault("preview_mode_active", False)
st.session_state.setdefault("completed_slot_ids", set())


# ============================================================
# APPLY EXISTING IAMP THEME
# ============================================================

apply_theme()


# ============================================================
# SIDEBAR BRANDING
# ============================================================


with st.sidebar:
    st.markdown(
        '<div class="iamp-brand">'
        '<div class="iamp-wordmark">IAMP</div>'
        '<div class="iamp-tagline">'
        'Intelligent Adaptive Meal Planner<br>'
        'A simpler way to plan everyday meals.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.divider()



# ============================================================
# APPLICATION NAVIGATION
# ============================================================

pages = {

    "Planning": [

        st.Page(
            "pages/meal_planner.py",
            title="Create a meal plan",
            default=True,
        ),

    ],

    "Your workspace": [

        st.Page(
            "pages/dashboard.py",
            title="Overview",
        ),

        st.Page(
            "pages/pantry.py",
            title="My pantry",
        ),

        st.Page(
            "pages/groceries.py",
            title="Shopping list",
        ),

        st.Page(
            "pages/nutrition.py",
            title="Nutrition",
        ),

        st.Page(
            "pages/replanning.py",
            title="Adjust my plan",
        ),

    ],

}


# ============================================================
# RUN SELECTED PAGE
# ============================================================

navigation = st.navigation(pages)

navigation.run()
