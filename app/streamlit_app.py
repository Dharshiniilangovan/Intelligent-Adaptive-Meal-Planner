
"""IAMP Streamlit application entry point.

Run from the repository root:

    python -m streamlit run app/streamlit_app.py

Features:
- Workspace-specific User State persistence
- Saved preferences and pantry
- Saved generated meal plans
- Background meal generation
- Generation status across all pages
- Independent user workspaces
- Existing IAMP theme and navigation
"""

import sys
from pathlib import Path
from app.components.background_status import sync_background_jobs


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

from app.components.state_persistence import (
    load_ui_state,
    get_workspace_id,
    switch_workspace,
)

from app.components.planning_status import (
    sync_planning_job,
    show_planning_status,
)

from app.components.ui_state import initialize_state
from app.components.theme import apply_theme


# ============================================================
# STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="IAMP | Meal planning",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# RESTORE USER WORKSPACE
# ============================================================

# Restore saved preferences, pantry, and meal-plan results
# before initializing missing session-state values.

load_ui_state()


# ============================================================
# INITIALIZE SESSION STATE
# ============================================================

initialize_state()

# These defaults must not overwrite restored data.

st.session_state.setdefault("planner_result", None)
st.session_state.setdefault("confirmed_user_state", None)
st.session_state.setdefault("parsed_result", None)
st.session_state.setdefault("pantry_items", [])
st.session_state.setdefault("preview_mode_active", False)
st.session_state.setdefault("completed_slot_ids", set())

# Background generation state.
st.session_state.setdefault("planning_job_id", None)
st.session_state.setdefault("planning_job_error", None)

# Track changes made after a plan was generated.
st.session_state.setdefault(
    "pantry_changed_since_plan",
    False,
)

st.session_state.setdefault(
    "preferences_changed_since_plan",
    False,
)


# ============================================================
# SYNCHRONIZE BACKGROUND GENERATION
# ============================================================

# This runs whenever Streamlit reruns the application,
# including when the user navigates between pages.
#
# If a background job has completed, its saved result
# is restored into st.session_state["planner_result"].
#
# The Planner itself is NOT restarted here.

sync_planning_job()
sync_background_jobs()


# ============================================================
# APPLY EXISTING IAMP THEME
# ============================================================

apply_theme()


# ============================================================
# SIDEBAR BRANDING AND WORKSPACE MANAGEMENT
# ============================================================

with st.sidebar:

    # --------------------------------------------------------
    # IAMP BRANDING
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # SAVED WORKSPACE
    # --------------------------------------------------------

    with st.expander("My saved workspace"):

        workspace_id = get_workspace_id()

        st.caption(
            "Your preferences, pantry, and meal plans "
            "are saved in this workspace. "
            "Keep this ID to reopen it later."
        )

        st.code(
            workspace_id,
            language=None,
        )

        entered_id = st.text_input(
            "Open a saved workspace",
            placeholder="Enter workspace ID",
            key="workspace_id_input",
        )

        if st.button(
            "Open workspace",
            key="open_saved_workspace",
        ):

            if not entered_id.strip():

                st.warning(
                    "Enter a workspace ID first."
                )

            else:

                try:

                    switch_workspace(
                        entered_id.strip()
                    )

                except (
                    ValueError,
                    FileNotFoundError,
                ) as exc:

                    st.error(
                        str(exc)
                    )

                else:

                    # Synchronize the newly selected workspace
                    # on the next full application rerun.

                    st.rerun()


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
# BACKGROUND GENERATION STATUS
# ============================================================

# Display the status of an active generation job.
#
# Users can navigate between pages while the job runs.
# Completed results are collected by sync_planning_job()
# during the next full application rerun.

show_planning_status()


# ============================================================
# RUN SELECTED PAGE
# ============================================================

navigation = st.navigation(pages)

navigation.run()
