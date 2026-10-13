
"""Pantry management with Gemini-assisted image detection.

Only quantities reviewed and confirmed by the user
are included in meal planning.
"""

import math

import streamlit as st

from app.components.presentation import preview_image
from app.components.state_persistence import save_ui_state


# ============================================================
# INITIALIZE SESSION STATE
# ============================================================

if "pantry_items" not in st.session_state:
    st.session_state["pantry_items"] = []

if "image_candidates" not in st.session_state:
    st.session_state["image_candidates"] = []


UNITS = [
    "g", "kg", "ml", "l", "count", "head",
    "bunch", "pack", "cup", "tbsp", "tsp",
    "clove", "piece",
]

HEAD_VEGETABLES = {
    "cabbage", "green cabbage", "red cabbage",
    "napa cabbage", "lettuce", "green leaf lettuce",
    "iceberg lettuce", "romaine lettuce",
    "butter lettuce", "broccoli", "cauliflower",
}



def invalidate_plan():
    """Preserve existing plan while recording pantry changes.

    Pantry updates should not erase the user's previous
    meal plan, shopping list, or nutrition summary.

    The existing plan remains a snapshot until the user
    explicitly regenerates or replans.
    """

    # Keep planner_result unchanged.
    # Keep confirmed_user_state unchanged.
    # Keep preview_mode_active unchanged.

    # Mark that pantry has changed since the plan was generated.
    st.session_state["pantry_changed_since_plan"] = True

    # Save updated pantry and existing plan together.
    from app.components.state_persistence import save_ui_state

    save_ui_state()

    print(
        "[PANTRY UPDATED]",
        "items=",
        len(st.session_state.get("pantry_items", [])),
        "existing_plan_preserved=",
        bool(st.session_state.get("planner_result")),
    )


def valid_quantity(value):
    """Return positive finite quantity or None."""

    if value is None or isinstance(value, bool):
        return None

    try:
        quantity = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(quantity) or quantity <= 0:
        return None

    return quantity


def candidate_name(candidate):
    """Return the KB ingredient name where available."""

    return str(
        candidate.get("ingredient_name")
        or candidate.get("name")
        or candidate.get("detected_name")
        or ""
    ).strip()


def candidate_suggestion(candidate):
    """Return a safe quantity suggestion from image detection.

    Full-package capacity is never used as remaining pantry stock.
    """

    if candidate.get("observations_count", 1) > 1:
        return None, None

    scope = candidate.get("quantity_scope")

    if scope != "visible_amount":
        return None, None

    quantity = valid_quantity(candidate.get("quantity"))
    unit = str(candidate.get("unit") or "").strip().lower()

    if quantity is None or not unit:
        return None, None

    if candidate_name(candidate).casefold() in HEAD_VEGETABLES:
        if unit in {"count", "counts", "piece", "pieces"}:
            unit = "head"

    return quantity, unit


def normalize_unit(unit):
    """Normalize simple unit aliases for pantry storage."""

    unit = str(unit or "").strip().lower()

    aliases = {
        "grams": "g",
        "gram": "g",
        "kilogram": "kg",
        "kilograms": "kg",
        "milliliter": "ml",
        "milliliters": "ml",
        "millilitre": "ml",
        "millilitres": "ml",
        "liter": "l",
        "litre": "l",
        "liters": "l",
        "litres": "l",
        "counts": "count",
        "pieces": "piece",
        "pcs": "piece",
        "heads": "head",
        "bunches": "bunch",
        "packs": "pack",
    }

    return aliases.get(unit, unit)


# ============================================================
# PAGE HEADER
# ============================================================

st.title("My pantry")

st.caption(
    "Add ingredients you already have, or upload a photo "
    "to identify ingredients and review their quantities."
)


# ============================================================
# MANUAL PANTRY ENTRY
# ============================================================

st.subheader("Add an ingredient")

with st.form("add_pantry", clear_on_submit=True):

    ingredient_name = st.text_input("Ingredient name")

    left, right = st.columns(2)

    with left:
        quantity = st.number_input(
            "Quantity",
            min_value=0.0,
            value=None,
            placeholder="Enter quantity",
        )

    with right:
        unit = st.selectbox("Unit", UNITS)

    submitted = st.form_submit_button(
        "Add ingredient",
        width="stretch",
    )

if submitted:

    name = ingredient_name.strip().lower()
    amount = valid_quantity(quantity)

    if not name or amount is None:
        st.error("Enter an ingredient name and positive quantity.")

    else:
        existing = [
            item
            for item in st.session_state["pantry_items"]
            if item["ingredient_name"].lower() != name
        ]

        existing.append({
            "ingredient_name": name,
            "quantity": amount,
            "unit": unit,
        })

        st.session_state["pantry_items"] = existing

        invalidate_plan()
        save_ui_state()

        st.success("Ingredient added to your pantry.")


# ============================================================
# CURRENT PANTRY
# ============================================================

st.divider()

st.subheader("Your ingredients")

pantry_items = st.session_state["pantry_items"]

if pantry_items:

    edited = st.data_editor(
        pantry_items,
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        key="pantry_editor",
        column_config={
            "ingredient_name": st.column_config.TextColumn(
                "Ingredient",
                required=True,
            ),
            "quantity": st.column_config.NumberColumn(
                "Quantity",
                min_value=0.0,
            ),
            "unit": st.column_config.SelectboxColumn(
                "Unit",
                options=UNITS,
                required=True,
            ),
        },
    )

    if st.button("Save pantry changes"):

        cleaned = []
        seen = set()

        try:
            for item in edited:

                name = str(
                    item.get("ingredient_name") or ""
                ).strip().lower()

                amount = valid_quantity(
                    item.get("quantity")
                )

                unit = normalize_unit(
                    item.get("unit")
                )

                if not name or amount is None or not unit:
                    raise ValueError(
                        "Each ingredient needs a name, "
                        "positive quantity, and unit."
                    )

                if name in seen:
                    raise ValueError(
                        f"Duplicate ingredient: {name}"
                    )

                seen.add(name)

                cleaned.append({
                    "ingredient_name": name,
                    "quantity": amount,
                    "unit": unit,
                })

        except ValueError as exc:
            st.error(str(exc))

        else:
            st.session_state["pantry_items"] = cleaned

            invalidate_plan()
            save_ui_state()

            st.success("Pantry changes saved.")
            st.rerun()

else:
    st.info("Your pantry is empty. Add an ingredient to begin.")


# ============================================================
# PANTRY IMAGE UPLOAD
# ============================================================

st.divider()

st.subheader("Add ingredients from a photo")

upload = st.file_uploader(
    "Choose a pantry image",
    type=["jpg", "jpeg", "png"],
)

if upload is not None:

    preview_image(upload, width=260)

    if st.button(
        "Detect ingredients in image",
        type="primary",
    ):

        try:
            from src.pantry.image_pantry import (
                detect_image,
                refine_missing_quantities,
                match_to_kb,
                consolidate_ingredients,
                load_kb,
            )

            with st.spinner("Analyzing your pantry image..."):

                image_bytes = upload.getvalue()

                detections = detect_image(
                    image_bytes,
                    mime_type=upload.type,
                )

                if isinstance(detections, dict):
                    detections = (
                        detections.get("ingredients") or []
                    )

                # Second Gemini pass for missing quantities.
                detections = refine_missing_quantities(
                    detections,
                    image_bytes,
                    mime_type=upload.type,
                )

                matched = match_to_kb(
                    detections,
                    kb=load_kb(),
                )

                candidates = consolidate_ingredients(
                    matched
                )

                st.session_state["image_candidates"] = candidates

                # Clear previous review edits.
                st.session_state.pop("image_review", None)

                print(
                    "[PANTRY UI] Detected:",
                    len(detections),
                    "Matched:",
                    sum(
                        bool(x.get("ingredient_id"))
                        for x in candidates
                    ),
                    "Candidates:",
                    len(candidates),
                )

            if candidates:
                st.success(
                    f"Found {len(candidates)} ingredients. "
                    "Review them below."
                )
            else:
                st.info(
                    "No ingredients were identified. "
                    "You can add them manually."
                )

        except Exception as exc:
            st.error(
                f"Image detection failed: {exc}"
            )


# ============================================================
# REVIEW IMAGE DETECTIONS
# ============================================================

candidates = (
    st.session_state.get("image_candidates") or []
)

if candidates:

    st.markdown("#### Review detected ingredients")

    st.caption(
        "Suggested quantities are based on visible food only. "
        "For packaged items, enter how much remains, "
        "not the quantity printed on the package."
    )

    rows = []

    for candidate in candidates:

        suggested_quantity, suggested_unit = (
            candidate_suggestion(candidate)
        )

        rows.append({
            "Include": bool(candidate.get("ingredient_id")),
            "Ingredient": candidate_name(candidate),
            "Quantity": suggested_quantity,
            "Unit": suggested_unit,
        })

    reviewed = st.data_editor(
        rows,
        hide_index=True,
        width="stretch",
        key="image_review",
        column_config={
            "Include": st.column_config.CheckboxColumn(
                "Include",
            ),
            "Ingredient": st.column_config.TextColumn(
                "Ingredient",
                required=True,
            ),
            "Quantity": st.column_config.NumberColumn(
                "Quantity",
                min_value=0.0,
                step=0.1,
            ),
            "Unit": st.column_config.SelectboxColumn(
                "Unit",
                options=UNITS,
            ),
        },
    )

    if st.button(
        "Add reviewed ingredients to pantry",
        type="primary",
    ):

        selected = [
            (index, row)
            for index, row in enumerate(reviewed)
            if row.get("Include")
        ]

        if not selected:
            st.warning("Select at least one ingredient.")

        else:
            try:
                new_items = list(
                    st.session_state["pantry_items"]
                )

                # Validate every selected row before saving.
                additions = []

                for index, row in selected:

                    candidate = candidates[index]

                    if not candidate.get("ingredient_id"):
                        raise ValueError(
                            f"{candidate_name(candidate)} is not "
                            "matched to the Ingredient KB."
                        )

                    # Preserve the canonical KB ingredient name.
                    name = candidate_name(candidate).lower()

                    amount = valid_quantity(
                        row.get("Quantity")
                    )

                    unit = normalize_unit(
                        row.get("Unit")
                    )

                    if amount is None or not unit:
                        raise ValueError(
                            f"Enter a positive quantity and unit "
                            f"for {name}."
                        )

                    if unit not in UNITS:
                        raise ValueError(
                            f"Unsupported unit for {name}: {unit}"
                        )

                    additions.append({
                        "ingredient_name": name,
                        "quantity": amount,
                        "unit": unit,
                    })

                for item in additions:

                    new_items = [
                        existing
                        for existing in new_items
                        if existing["ingredient_name"].lower()
                        != item["ingredient_name"]
                    ]

                    new_items.append(item)

            except (TypeError, ValueError) as exc:
                st.error(str(exc))

            else:
                st.session_state["pantry_items"] = new_items

                invalidate_plan()
                save_ui_state()

                st.session_state["image_candidates"] = []
                st.session_state.pop("image_review", None)

                st.success(
                    "Ingredients added to your pantry. "
                    "Please reconfirm your preferences "
                    "before generating a meal plan."
                )

                st.rerun()
