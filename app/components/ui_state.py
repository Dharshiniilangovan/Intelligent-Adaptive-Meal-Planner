"""Session state helpers shared by all Streamlit pages."""
import streamlit as st


def initialize_state():
    defaults = {
        "parsed_result": None,
        "confirmed_user_state": None,
        "pantry_items": [],
        "planner_result": None,
        "request_revision": 0,
        "last_request": "",
        "pantry_revision": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def csv_values(text):
    return list(dict.fromkeys(s.strip() for s in (text or "").split(",") if s.strip()))


def normalized_list(value):
    if isinstance(value, list):
        return [str(x) for x in value if x is not None]
    return []


def current_pantry():
    return {
        item["ingredient_name"]: {"quantity": item["quantity"], "unit": item["unit"]}
        for item in st.session_state.pantry_items
    }


def result_basket():
    result = st.session_state.get("planner_result") or {}
    return result.get("grocery_basket") or result.get("final_grocery_basket") or {}


def canonical_pantry():
    """Convert UI pantry rows into the original GC1 User State format."""

    from app.components.user_state_adapter import convert_pantry

    return convert_pantry(
        st.session_state.get("pantry_items", [])
    )

