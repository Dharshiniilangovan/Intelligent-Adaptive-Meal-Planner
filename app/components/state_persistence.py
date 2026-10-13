
"""Workspace-specific persistence for the IAMP Streamlit application.

Stores:
- Natural-language requests
- Confirmed User State
- Pantry ingredients
- Planning dates and duration
- Generated meal plans
- Background generation job IDs
- Completed meals

Each workspace has its own JSON file.
"""

import json
import os
import tempfile
import uuid
import threading

from datetime import date, datetime
from pathlib import Path

import streamlit as st


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[2]

STATE_DIR = ROOT / "data" / "ui_state"

STATE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# SAVED SESSION STATE KEYS
# ============================================================

SAVED_KEYS = (
    "natural_language_request",
    "last_request",
    "parsed_result",
    "request_revision",
    "confirmed_user_state",
    "user_id",
    "planning_days",
    "planning_start_date",
    "pantry_items",
    "planner_result",
    "preview_mode_active",
    "pantry_changed_since_plan",
    "preferences_changed_since_plan",
    "planning_job_id",
    "planning_job_error",
    "completed_slot_ids",
    "pantry_detection_job_id",
    "pantry_detection_error",
    "image_candidates",
    "replanning_job_id",
    "replanning_error",
)


# ============================================================
# FILE LOCK
# ============================================================

_FILE_LOCK = threading.RLock()


# ============================================================
# JSON SERIALIZATION
# ============================================================

def json_default(value):
    """Serialize supported Python values into JSON."""

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, set):
        return list(value)

    if isinstance(value, Path):
        return str(value)

    raise TypeError(
        f"Cannot serialize {type(value).__name__}"
    )


# ============================================================
# WORKSPACE IDENTIFICATION
# ============================================================

def validate_workspace_id(workspace_id):
    """Validate a workspace UUID."""

    try:
        return str(uuid.UUID(str(workspace_id)))

    except (TypeError, ValueError, AttributeError):
        raise ValueError(
            "Invalid workspace ID."
        ) from None


def get_workspace_id():
    """Return the active workspace or create a new one."""

    if "workspace_id" not in st.session_state:

        st.session_state["workspace_id"] = str(
            uuid.uuid4()
        )

    return validate_workspace_id(
        st.session_state["workspace_id"]
    )


def workspace_file(workspace_id=None):
    """Return the workspace-specific JSON file."""

    workspace_id = validate_workspace_id(
        workspace_id or get_workspace_id()
    )

    return STATE_DIR / f"{workspace_id}.json"


# ============================================================
# ATOMIC JSON WRITE
# ============================================================

def atomic_write_json(path, payload):
    """Safely write JSON without leaving partial files."""

    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _FILE_LOCK:

        fd, temp_name = tempfile.mkstemp(
            prefix=".iamp_",
            suffix=".json",
            dir=path.parent,
        )

        try:

            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as handle:

                json.dump(
                    payload,
                    handle,
                    indent=2,
                    ensure_ascii=False,
                    default=json_default,
                )

            os.replace(
                temp_name,
                path,
            )

        finally:

            if os.path.exists(temp_name):
                os.unlink(temp_name)


# ============================================================
# SAVE UI STATE
# ============================================================

def save_ui_state():
    """Save the current workspace's persistent session data."""

    path = workspace_file()

    payload = {
        key: st.session_state.get(key)
        for key in SAVED_KEYS
    }

    atomic_write_json(
        path,
        payload,
    )

    print(
        "[UI STATE SAVED]",
        path,
    )

    return path


# ============================================================
# LOAD UI STATE
# ============================================================

def load_ui_state():
    """Restore saved workspace data into Streamlit session state."""

    if st.session_state.get("_ui_state_loaded"):
        return

    path = workspace_file()

    if path.exists():

        try:

            with _FILE_LOCK:

                payload = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )

            if not isinstance(payload, dict):
                raise ValueError(
                    "Saved workspace must contain a JSON object."
                )

            for key in SAVED_KEYS:

                if key in payload:
                    st.session_state[key] = payload[key]

            # Restore completed meals as a set.
            completed = st.session_state.get(
                "completed_slot_ids"
            )

            if isinstance(completed, list):
                st.session_state[
                    "completed_slot_ids"
                ] = set(completed)

            print(
                "[UI STATE LOADED]",
                path,
            )

        except (
            OSError,
            ValueError,
            TypeError,
        ) as exc:

            st.warning(
                f"Could not restore saved workspace: {exc}"
            )

    st.session_state.setdefault(
        "pantry_items",
        [],
    )

    st.session_state.setdefault(
        "planner_result",
        None,
    )

    st.session_state.setdefault(
        "confirmed_user_state",
        None,
    )

    st.session_state.setdefault(
        "completed_slot_ids",
        set(),
    )

    st.session_state["_ui_state_loaded"] = True


# ============================================================
# SWITCH WORKSPACE
# ============================================================

def switch_workspace(workspace_id):
    """Switch to an existing saved workspace."""

    workspace_id = validate_workspace_id(
        workspace_id
    )

    path = workspace_file(
        workspace_id
    )

    if not path.is_file():
        raise FileNotFoundError(
            "Workspace not found."
        )

    # Remove previous workspace-specific state.
    for key in SAVED_KEYS:
        st.session_state.pop(
            key,
            None,
        )

    # Live Planner objects cannot safely be transferred.
    for key in (
        "live_plan_state",
        "live_planner",
        "planner_user_state",
        "completed_slot_ids",
    ):
        st.session_state.pop(
            key,
            None,
        )

    st.session_state[
        "workspace_id"
    ] = workspace_id

    st.session_state[
        "_ui_state_loaded"
    ] = False

    load_ui_state()

    print(
        "[WORKSPACE SWITCHED]",
        workspace_id,
    )


# ============================================================
# CLEAR CURRENT WORKSPACE
# ============================================================

def clear_saved_ui_state():
    """Clear the active workspace's saved UI state."""

    path = workspace_file()

    with _FILE_LOCK:
        if path.exists():
            path.unlink()

    for key in SAVED_KEYS:
        st.session_state.pop(
            key,
            None,
        )

    for key in (
        "live_plan_state",
        "live_planner",
        "planner_user_state",
    ):
        st.session_state.pop(
            key,
            None,
        )

    st.session_state[
        "completed_slot_ids"
    ] = set()

    st.session_state[
        "_ui_state_loaded"
    ] = True

    print(
        "[UI WORKSPACE CLEARED]",
        path,
    )
