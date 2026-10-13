"""Synchronize completed pantry and replanning jobs into Streamlit."""
import logging
import streamlit as st
from app.components.background_jobs import read_background_job, get_live_replan
from app.components.state_persistence import get_workspace_id, save_ui_state

LOG = logging.getLogger(__name__)


def sync_background_jobs():
    workspace = get_workspace_id()
    for kind, id_key, error_key in (
        ("pantry", "pantry_detection_job_id", "pantry_detection_error"),
        ("replan", "replanning_job_id", "replanning_error"),
    ):
        job_id = st.session_state.get(id_key)
        if not job_id:
            continue
        job = read_background_job(workspace, job_id)
        if not job:
            st.session_state[error_key] = "The previous job is unavailable. Please try again."
            st.session_state[id_key] = None
            save_ui_state()
            continue
        if job.get("status") in ("queued", "running"):
            continue
        if job.get("status") == "failed":
            st.session_state[error_key] = job.get("error") or "Processing failed."
            st.session_state[id_key] = None
            save_ui_state()
            continue
        if job.get("status") != "completed":
            continue
        if kind == "pantry":
            st.session_state["image_candidates"] = job.get("result") or []
            st.session_state["pantry_detection_done"] = True
            st.session_state.pop("image_review", None)
        else:
            live = get_live_replan(workspace, job_id)
            if live is None:
                st.session_state[error_key] = (
                    "The updated plan is saved, but the editable planning state is unavailable."
                )
                for key in ("live_planner", "live_plan_state", "planner_user_state"):
                    st.session_state.pop(key, None)
            else:
                st.session_state["live_planner"] = live["planner"]
                st.session_state["live_plan_state"] = live["plan_state"]
                st.session_state["planner_user_state"] = live["user_state"]
                st.session_state[error_key] = None
            st.session_state["planner_result"] = job["result"]
            st.session_state["replanning_done"] = True
            # Do not clear pantry/preference changed flags: replanning uses original inputs.
        st.session_state[id_key] = None
        st.session_state[error_key] = None if kind == "pantry" else st.session_state.get(error_key)
        try:
            save_ui_state()
        except Exception:
            LOG.exception("Failed to persist %s job %s", kind, job_id)
            st.session_state[id_key] = job_id
            st.session_state[error_key] = "Result is ready, but saving failed."
