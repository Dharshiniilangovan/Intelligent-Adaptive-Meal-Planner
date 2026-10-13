
"""Session-specific persistence for the IAMP Streamlit MVP.

Each workspace has a separate JSON file.

A workspace ID is needed to restore a workspace after
a browser session ends. This is local MVP storage,
not an authenticated multi-user system.
"""

import json
import os
import re
import tempfile
import uuid

from datetime import date, datetime
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "data" / "ui_state"

SAVED_KEYS = (
    "natural_language_request",
    "last_request",
    "parsed_result",
    "request_revision",
    "confirmed_user_state",
    "pantry_items",
    "planner_result",
    "preview_mode_active",
    "pantry_changed_since_plan",
    "preferences_changed_since_plan",
)


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, set):
        return list(value)

    raise TypeError(
        f"Cannot serialize {type(value).__name__}"
    )


def validate_workspace_id(workspace_id):
    """Accept only UUID workspace identifiers."""

    try:
        return str(uuid.UUID(str(workspace_id)))
    except (TypeError, ValueError, AttributeError):
        raise ValueError("Invalid workspace ID") from None


def get_workspace_id():
    """Create an independent workspace for this Streamlit session."""

    if "workspace_id" not in st.session_state:
        st.session_state["workspace_id"] = str(
            uuid.uuid4()
        )

    return st.session_state["workspace_id"]


def workspace_file(workspace_id=None):
    """Return the JSON path for one workspace."""

    workspace_id = validate_workspace_id(
        workspace_id or get_workspace_id()
    )

    return STATE_DIR / f"{workspace_id}.json"


def save_ui_state():
    """Save the current workspace without affecting others."""

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = workspace_file()

    payload = {
        key: st.session_state.get(key)
        for key in SAVED_KEYS
    }

    fd, temp_path = tempfile.mkstemp(
        prefix=".iamp_",
        suffix=".json",
        dir=STATE_DIR,
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
            temp_path,
            path,
        )

    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    return path


def load_ui_state():
    """Load only the active workspace's saved state."""

    if st.session_state.get("_ui_state_loaded"):
        return

    path = workspace_file()

    if path.exists():

        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            if isinstance(payload, dict):

                for key in SAVED_KEYS:
                    if key in payload:
                        st.session_state[key] = payload[key]

        except (OSError, ValueError, TypeError) as exc:
            st.warning(
                f"Could not restore workspace: {exc}"
            )

    st.session_state.setdefault(
        "pantry_items",
        [],
    )

    st.session_state["_ui_state_loaded"] = True


def switch_workspace(workspace_id):
    """Open an existing workspace using its ID."""

    workspace_id = validate_workspace_id(
        workspace_id
    )

    path = workspace_file(workspace_id)

    if not path.exists():
        raise FileNotFoundError(
            "Workspace not found."
        )

    for key in SAVED_KEYS:
        st.session_state.pop(key, None)

    st.session_state["workspace_id"] = workspace_id
    st.session_state["_ui_state_loaded"] = False

    load_ui_state()


def clear_saved_ui_state():
    """Clear the active workspace."""

    path = workspace_file()

    if path.exists():
        path.unlink()

    for key in SAVED_KEYS:
        st.session_state.pop(key, None)

    st.session_state["_ui_state_loaded"] = True
