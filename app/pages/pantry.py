
"""Manual and Gemini-assisted pantry review.

Only confirmed quantities enter meal planning.
"""

import streamlit as st

from app.components.presentation import preview_image


st.title("My pantry")
st.caption(
    "Review ingredients and quantities before including "
    "them in your meal plan."
)

if "pantry_items" not in st.session_state:
    st.session_state.pantry_items = []

if "image_candidates" not in st.session_state:
    st.session_state.image_candidates = []


def candidate_name(candidate):
    """Get the ingredient name from supported detector fields."""
    return str(
        candidate.get("ingredient_name")
        or candidate.get("canonical_name")
        or candidate.get("matched_name")
        or candidate.get("name")
        or candidate.get("detected_name")
        or ""
    ).strip()


def invalidate_plan():
    """Require reconfirmation after pantry changes."""
    st.session_state.confirmed_user_state = None
    st.session_state.planner_result = None
    st.session_state.pop("live_plan_state", None)
    st.session_state.pop("live_planner", None)
    st.session_state.pop("planner_user_state", None)


# ==========================================================
# 1. MANUAL PANTRY ENTRY
# ==========================================================

st.subheader("Add an ingredient")

with st.form("add_pantry", clear_on_submit=True):

    name = st.text_input("Ingredient name")

    c1, c2 = st.columns(2)

    qty = c1.number_input(
        "Quantity",
        min_value=0.0,
        value=None,
        placeholder="Enter quantity",
    )

    unit = c2.selectbox(
        "Unit",
        [
            "g", "kg", "ml", "l", "pcs",
            "cup", "tbsp", "tsp",
            "bunch", "head", "pack",
        ],
    )

    submitted = st.form_submit_button("Add ingredient")

    if submitted:
        if not name.strip() or qty is None or qty <= 0:
            st.error(
                "Enter an ingredient name and positive quantity."
            )
        else:
            key = name.strip().lower()

            st.session_state.pantry_items = [
                item
                for item in st.session_state.pantry_items
                if item["ingredient_name"].lower() != key
            ]

            st.session_state.pantry_items.append({
                "ingredient_name": key,
                "quantity": float(qty),
                "unit": unit,
            })

            invalidate_plan()

            st.success(
                "Ingredient saved. Reconfirm your preferences "
                "before planning."
            )


# ==========================================================
# 2. CURRENT PANTRY
# ==========================================================

if st.session_state.pantry_items:

    st.subheader("Current pantry")

    edited = st.data_editor(
        st.session_state.pantry_items,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key="pantry_editor",
    )

    if st.button("Save pantry changes"):

        clean = []
        seen = set()

        try:
            for item in edited:

                ingredient = str(
                    item.get("ingredient_name") or ""
                ).strip().lower()

                quantity = float(item.get("quantity"))

                item_unit = str(
                    item.get("unit") or ""
                ).strip()

                if (
                    not ingredient
                    or ingredient in seen
                    or quantity <= 0
                    or not item_unit
                ):
                    raise ValueError(
                        "Use unique ingredient names, "
                        "positive quantities and valid units."
                    )

                seen.add(ingredient)

                clean.append({
                    "ingredient_name": ingredient,
                    "quantity": quantity,
                    "unit": item_unit,
                })

        except (TypeError, ValueError) as exc:
            st.error(f"Invalid pantry entry: {exc}")

        else:
            st.session_state.pantry_items = clean

            invalidate_plan()

            st.success(
                "Pantry updated. Reconfirm your preferences "
                "before planning."
            )

else:
    st.info("No ingredients added yet.")


# ==========================================================
# 3. PANTRY IMAGE UPLOAD
# ==========================================================

st.divider()

st.subheader("Add ingredients from a photo")

upload = st.file_uploader(
    "Choose a pantry image",
    type=["jpg", "jpeg", "png"],
)

if upload is not None:

    # Small, consistent preview.
    preview_image(upload, width=260)

    if st.button("Detect ingredients in image"):

        try:
            from src.pantry.image_pantry import (
                detect_image,
                match_to_kb,
                consolidate_ingredients,
            )

            with st.spinner("Analyzing the image..."):

                detected = detect_image(
                    upload.getvalue(),
                    mime_type=upload.type,
                )

                print(
                    "\n[PANTRY DEBUG] Raw detection:",
                    repr(detected)[:3000],
                )

                if isinstance(detected, dict):
                    detected = (
                        detected.get("ingredients") or []
                    )

                matched = match_to_kb(detected)

                print(
                    "\n[PANTRY DEBUG] KB matched:",
                    repr(matched)[:3000],
                )

                candidates = consolidate_ingredients(
                    matched
                )

                st.session_state.image_candidates = (
                    candidates
                )

                # Reset previous image-review edits.
                st.session_state.pop(
                    "image_review",
                    None,
                )

                print(
                    "\n[PANTRY DEBUG] Consolidated:",
                    repr(candidates)[:3000],
                )

        except Exception as exc:
            st.error(
                f"Image detection failed: {exc}"
            )


# ==========================================================
# 4. REVIEW DETECTED INGREDIENTS
# ==========================================================

candidates = (
    st.session_state.get("image_candidates") or []
)

if candidates:

    print("\n[PANTRY DEBUG] Detected candidates:")

    for candidate in candidates[:5]:
        print(repr(candidate))

    st.caption(
        "Review the detected ingredients and enter the "
        "amount you actually have. Quantities are not "
        "automatically assumed from the image."
    )

    rows = []

    for candidate in candidates:

        rows.append({
            "Include": False,
            "Ingredient": candidate_name(candidate),
            "Quantity": None,
            "Unit": "",
        })

    print("\n[PANTRY DEBUG] Rows passed to editor:")

    for row in rows[:5]:
        print(repr(row))

    reviewed = st.data_editor(
        rows,
        hide_index=True,
        use_container_width=True,
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
                options=[
                    "g", "kg", "ml", "l", "pcs",
                    "cup", "tbsp", "tsp",
                    "bunch", "head", "pack",
                ],
            ),
        },
    )

    # ======================================================
    # 5. ADD CONFIRMED INGREDIENTS TO PANTRY
    # ======================================================

    if st.button("Add reviewed quantities to pantry"):

        chosen = [
            row
            for row in reviewed
            if row.get("Include")
        ]

        try:
            if not chosen:
                raise ValueError(
                    "Select at least one ingredient."
                )

            new_items = list(
                st.session_state.pantry_items
            )

            for row in chosen:

                ingredient = str(
                    row.get("Ingredient") or ""
                ).strip()

                if not ingredient:
                    raise ValueError(
                        "A selected ingredient has no name."
                    )

                # Match the reviewed row back to its
                # original detected ingredient.
                candidate = next(
                    (
                        item
                        for item in candidates
                        if candidate_name(item).lower()
                        == ingredient.lower()
                    ),
                    None,
                )

                if (
                    candidate is None
                    or not candidate.get("ingredient_id")
                ):
                    raise ValueError(
                        f"Ingredient not matched in KB: "
                        f"{ingredient}"
                    )

                quantity_value = row.get("Quantity")
                selected_unit = str(
                    row.get("Unit") or ""
                ).strip()

                if (
                    quantity_value is None
                    or not selected_unit
                ):
                    raise ValueError(
                        f"Confirm quantity and unit for "
                        f"{ingredient}"
                    )

                quantity_value = float(
                    quantity_value
                )

                if quantity_value <= 0:
                    raise ValueError(
                        "Quantities must be positive."
                    )

                normalized_name = (
                    ingredient.lower()
                )

                new_items = [
                    item
                    for item in new_items
                    if item["ingredient_name"]
                    != normalized_name
                ]

                new_items.append({
                    "ingredient_name": normalized_name,
                    "quantity": quantity_value,
                    "unit": selected_unit,
                })

        except (ValueError, TypeError) as exc:
            st.error(str(exc))

        else:
            st.session_state.pantry_items = (
                new_items
            )

            invalidate_plan()

            st.session_state.image_candidates = []

            st.session_state.pop(
                "image_review",
                None,
            )

            st.success(
                "Reviewed ingredients added to your pantry. "
                "Reconfirm your preferences before planning."
            )

            st.rerun()
