
"""Connect background jobs to Streamlit session state."""

import logging

import streamlit as st

from app.components.planning_jobs import (
    read_job,
    get_live_objects,
)
from app.components.state_persistence import (
    get_workspace_id,
    save_ui_state,
)


logger = logging.getLogger(__name__)


def sync_planning_job():
    """Restore completed jobs when the app reruns."""

    job_id = st.session_state.get("planning_job_id")

    if not job_id:
        return

    workspace_id = get_workspace_id()
    job = read_job(workspace_id, job_id)

    if job is None:
        st.session_state["planning_job_error"] = (
            "The generation job could not be found."
        )
        st.session_state["planning_job_id"] = None
        save_ui_state()
        return

    status = job.get("status")

    if status in ("queued", "running"):
        return

    if status == "failed":
        st.session_state["planning_job_error"] = (
            job.get("error") or "Meal generation failed."
        )
        st.session_state["planning_job_id"] = None
        save_ui_state()
        return

    if status != "completed":
        return

    result = job.get("result")

    if not isinstance(result, dict):
        st.session_state["planning_job_error"] = (
            "The completed plan could not be restored."
        )
        return

    st.session_state["planner_result"] = result

    live = get_live_objects(workspace_id, job_id)

    if live:
        st.session_state["live_plan_state"] = live["plan_state"]
        st.session_state["planner_user_state"] = live["planner_state"]
        st.session_state["live_planner"] = live["planner"]
    else:
        # Live objects cannot be restored from JSON.
        for key in (
            "live_plan_state",
            "planner_user_state",
            "live_planner",
        ):
            st.session_state.pop(key, None)

    st.session_state["preview_mode_active"] = False
    st.session_state["completed_slot_ids"] = set()
    st.session_state["pantry_changed_since_plan"] = False
    st.session_state["preferences_changed_since_plan"] = False
    st.session_state["planning_job_error"] = None

    # Persist the completed plan before clearing its job ID.
    previous_id = st.session_state["planning_job_id"]
    st.session_state["planning_job_id"] = None

    try:
        save_ui_state()
    except Exception:
        logger.exception(
            "[PLAN SAVE ERROR] job=%s",
            previous_id,
        )
        st.session_state["planning_job_id"] = previous_id
        st.session_state["planning_job_error"] = (
            "The plan is ready, but saving failed."
        )
        return

    logger.info(
        "[PLAN RESTORED] workspace=%s job=%s",
        workspace_id,
        previous_id,
    )


def show_planning_status():
    """Display generation status without exposing developer details."""

    job_id = st.session_state.get("planning_job_id")

    if job_id:
        job = read_job(get_workspace_id(), job_id)

        if job and job.get("status") in ("queued", "running"):
            st.info(
                "Your meal plan is being prepared. "
                "You can continue browsing the app."
            )

            if st.button(
                "Check generation status",
                key="check_planning_status",
            ):
                sync_planning_job()
                st.rerun()

            return

    error = st.session_state.get("planning_job_error")

    if error:
        st.error(error)
