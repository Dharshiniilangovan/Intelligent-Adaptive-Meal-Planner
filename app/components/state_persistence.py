
"""Persist confirmed IAMP preferences and pantry between sessions."""

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "data" / "ui_state"
STATE_FILE = STATE_DIR / "saved_user_state.json"


SAVED_KEYS = (
    "natural_language_request",
    "last_request",
    "parsed_result",
    "request_revision",
    "confirmed_user_state",
    "pantry_items",

    # Save generated results for Dashboard,
    # Groceries, Nutrition and Meal Planner.
    "planner_result",

    # Preserve whether the result is a saved example.
    "preview_mode_active",
    "pantry_changed_since_plan",
)



def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, set):
        return list(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def save_ui_state():
    """Save user preferences and pantry atomically."""

    STATE_DIR.mkdir(parents=True, exist_ok=True)

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
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                ensure_ascii=False,
                default=json_default,
            )

        os.replace(temp_path, STATE_FILE)

    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    return STATE_FILE


def load_ui_state():
    """Restore previously saved preferences and pantry."""

    if st.session_state.get("_ui_state_loaded"):
        return

    if STATE_FILE.exists():
        try:
            payload = json.loads(
                STATE_FILE.read_text(encoding="utf-8")
            )

            if isinstance(payload, dict):
                for key in SAVED_KEYS:
                    if key in payload:
                        st.session_state[key] = payload[key]

        except (OSError, ValueError, TypeError) as exc:
            st.warning(f"Could not restore saved preferences: {exc}")

    st.session_state.setdefault("pantry_items", [])
    st.session_state["_ui_state_loaded"] = True


def clear_saved_ui_state():
    """Delete saved preferences and pantry."""

    if STATE_FILE.exists():
        STATE_FILE.unlink()

    for key in SAVED_KEYS:
        st.session_state.pop(key, None)

    st.session_state["_ui_state_loaded"] = True
