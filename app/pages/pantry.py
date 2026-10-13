"""Pantry management with background image detection and optional quantities."""
import math
import streamlit as st
from app.components.presentation import preview_image
from app.components.state_persistence import get_workspace_id, save_ui_state
from app.components.background_jobs import start_background_job, read_background_job

UNITS = ["g", "kg", "ml", "l", "count", "head", "bunch", "pack", "cup", "tbsp", "tsp", "clove", "piece"]
HEAD_VEGETABLES = {"cabbage", "green cabbage", "red cabbage", "napa cabbage", "lettuce", "green leaf lettuce", "iceberg lettuce", "romaine lettuce", "butter lettuce", "broccoli", "cauliflower"}
ALIASES = {"grams": "g", "gram": "g", "kilograms": "kg", "kilogram": "kg", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml", "liter": "l", "liters": "l", "litre": "l", "litres": "l", "counts": "count", "pieces": "piece", "pcs": "piece", "heads": "head", "bunches": "bunch", "packs": "pack"}

st.session_state.setdefault("pantry_items", [])
st.session_state.setdefault("image_candidates", [])


def quantity_or_none(value):
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValueError("Quantity must be a number or left blank.") from None
    if not math.isfinite(n) or n <= 0:
        raise ValueError("Quantity must be positive or left blank.")
    return n


def clean_unit(value):
    value = str(value or "").strip().lower()
    return ALIASES.get(value, value)


def validated_item(name, amount, unit):
    name = str(name or "").strip().lower()
    if not name:
        raise ValueError("Ingredient name is required.")
    amount = quantity_or_none(amount)
    unit = clean_unit(unit)
    if amount is None and not unit:
        return {"ingredient_name": name, "quantity": None, "unit": None}
    if amount is None or not unit:
        raise ValueError(f"Enter both quantity and unit for {name}, or leave both blank.")
    if unit not in UNITS:
        raise ValueError(f"Unsupported unit for {name}: {unit}")
    return {"ingredient_name": name, "quantity": amount, "unit": unit}



def save_items(items):
    """Save pantry and synchronize canonical GC1 User State."""

    from app.components.user_state_adapter import (
        convert_pantry,
        save_canonical_user_state,
    )

    st.session_state["pantry_items"] = items

    # Preserve the existing meal plan.
    st.session_state["pantry_changed_since_plan"] = True

    # Convert structured UI pantry into canonical format.
    availability = convert_pantry(items)

    confirmed = st.session_state.get(
        "confirmed_user_state"
    )

    if confirmed:
        updated_state = dict(confirmed)

        updated_state["ingredient_availability"] = (
            availability
        )

        # Keep canonical User State synchronized.
        save_canonical_user_state(updated_state)

        st.session_state[
            "confirmed_user_state"
        ] = updated_state

        print(
            "[PANTRY USER STATE SYNC]",
            availability,
        )

    # Save the Streamlit workspace.
    save_ui_state()

    print(
        "[PANTRY UPDATED]",
        "items=", len(items),
        "plan_preserved=",
        bool(st.session_state.get("planner_result")),
    )


def candidate_name(candidate):
    return str(candidate.get("kb_ingredient_name") or candidate.get("ingredient_name") or candidate.get("name") or candidate.get("detected_name") or "").strip()


def candidate_suggestion(candidate):
    if candidate.get("quantity_scope") != "visible_amount" or candidate.get("observations_count", 1) > 1:
        return None, None
    try:
        amount = quantity_or_none(candidate.get("quantity"))
    except ValueError:
        return None, None
    unit = clean_unit(candidate.get("unit"))
    if amount is None or unit not in UNITS:
        return None, None
    if candidate_name(candidate).casefold() in HEAD_VEGETABLES and unit in {"count", "piece"}:
        unit = "head"
    return amount, unit


st.title("My pantry")
st.caption("Add ingredients you have, or upload a photo. Quantities may be left unknown.")
st.subheader("Add an ingredient")
with st.form("add_pantry", clear_on_submit=True):
    name = st.text_input("Ingredient name")
    c1, c2 = st.columns(2)
    amount = c1.number_input("Quantity (optional)", min_value=0.0, value=None, placeholder="Unknown")
    unit = c2.selectbox("Unit (optional)", [""] + UNITS, format_func=lambda x: x or "Not specified")
    add = st.form_submit_button("Add ingredient", use_container_width=True)
if add:
    try:
        item = validated_item(name, amount, unit)
        items = [x for x in st.session_state["pantry_items"] if str(x.get("ingredient_name", "")).lower() != item["ingredient_name"]]
        items.append(item)
        save_items(items)
        st.success("Ingredient added.")
    except (ValueError, OSError, TypeError) as exc:
        st.error(str(exc))

st.divider()
st.subheader("Your ingredients")
items = st.session_state["pantry_items"]
if items:
    editor_key = f"pantry_editor_{st.session_state.get('pantry_revision', 0)}"
    edited = st.data_editor(
        items, num_rows="dynamic", hide_index=True, use_container_width=True,
        key=editor_key,
        column_config={
            "ingredient_name": st.column_config.TextColumn("Ingredient", required=True),
            "quantity": st.column_config.NumberColumn("Quantity (optional)", min_value=0.0),
            "unit": st.column_config.SelectboxColumn("Unit (optional)", options=[""] + UNITS),
        },
    )
    if st.button("Save pantry changes"):
        try:
            cleaned = []
            seen = set()
            for row in edited:
                item = validated_item(row.get("ingredient_name"), row.get("quantity"), row.get("unit"))
                if item["ingredient_name"] in seen:
                    raise ValueError("Duplicate ingredient: " + item["ingredient_name"])
                seen.add(item["ingredient_name"])
                cleaned.append(item)
            save_items(cleaned)
            st.session_state["pantry_revision"] = st.session_state.get("pantry_revision", 0) + 1
            st.rerun()
        except (ValueError, TypeError, OSError) as exc:
            st.error(str(exc))
else:
    st.info("Your pantry is empty.")

st.divider()
st.subheader("Add ingredients from a photo")
workspace = get_workspace_id()
job_id = st.session_state.get("pantry_detection_job_id")
job = read_background_job(workspace, job_id) if job_id else None
busy = bool(job and job.get("status") in {"queued", "running"})
if busy:
    st.info("Analyzing your pantry image. You can visit other pages while this runs.")
    if st.button("Check image analysis status"):
        st.rerun()
if st.session_state.get("pantry_detection_error"):
    st.error(st.session_state["pantry_detection_error"])
if st.session_state.pop("pantry_detection_done", False):
    st.success("Image analysis finished. Review detected ingredients below.")

upload = st.file_uploader("Choose a pantry image", type=["jpg", "jpeg", "png"])
if upload is not None:
    preview_image(upload, width=260)
    if st.button("Detect ingredients in image", type="primary", disabled=busy):
        try:
            job_id = start_background_job(
                workspace, "pantry", image_bytes=upload.getvalue(),
                mime_type=upload.type or "image/jpeg",
            )
            st.session_state["pantry_detection_job_id"] = job_id
            st.session_state["pantry_detection_error"] = None
            st.session_state["image_candidates"] = []
            st.session_state.pop("image_review", None)
            save_ui_state()
            st.rerun()
        except Exception as exc:
            st.error(f"Could not start image analysis: {exc}")

candidates = st.session_state.get("image_candidates") or []
if candidates:
    st.markdown("#### Review detected ingredients")
    st.caption("Only confirm amounts actually remaining. You can include ingredients with unknown quantities.")
    rows = []
    for candidate in candidates:
        q, u = candidate_suggestion(candidate)
        rows.append({"Include": bool(candidate.get("ingredient_id")), "Ingredient": candidate_name(candidate), "Quantity": q, "Unit": u or ""})
    reviewed = st.data_editor(
        rows, hide_index=True, use_container_width=True, key="image_review",
        column_config={
            "Include": st.column_config.CheckboxColumn("Include"),
            "Ingredient": st.column_config.TextColumn("Ingredient", disabled=True),
            "Quantity": st.column_config.NumberColumn("Quantity (optional)", min_value=0.0),
            "Unit": st.column_config.SelectboxColumn("Unit (optional)", options=[""] + UNITS),
        },
    )
    if st.button("Add reviewed ingredients to pantry", type="primary"):
        try:
            additions = []
            for index, row in enumerate(reviewed):
                if not row.get("Include"):
                    continue
                candidate = candidates[index]
                name = str(
                    row.get("Ingredient")
                    or candidate_name(candidate)
                    or ""
                ).strip().lower()

                if not name:
                    raise ValueError("Ingredient name cannot be empty.")
                additions.append(validated_item(candidate_name(candidate), row.get("Quantity"), row.get("Unit")))
            if not additions:
                raise ValueError("Select at least one ingredient.")
            new_items = list(st.session_state["pantry_items"])
            for item in additions:
                new_items = [x for x in new_items if str(x.get("ingredient_name", "")).lower() != item["ingredient_name"]]
                new_items.append(item)
            save_items(new_items)
            st.session_state["image_candidates"] = []
            st.session_state.pop("image_review", None)
            st.session_state["pantry_revision"] = st.session_state.get("pantry_revision", 0) + 1
            st.success("Reviewed ingredients added to your pantry.")
            st.rerun()
        except (ValueError, TypeError, OSError) as exc:
            st.error(str(exc))
