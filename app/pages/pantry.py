"""Manual pantry editing and image upload preview."""
import streamlit as st
from app.components.ui_state import current_pantry

st.title("Pantry")
st.caption("Only confirmed quantities are sent to the planner. Image recognition is not connected yet.")
with st.form("add_pantry", clear_on_submit=True):
    name = st.text_input("Ingredient name")
    qty = st.number_input("Quantity", min_value=0.0, value=None, placeholder="Required")
    unit = st.selectbox("Unit", ["g", "kg", "ml", "l", "pcs", "cup", "tbsp", "tsp", "bunch", "head", "pack"])
    add = st.form_submit_button("Add / update ingredient")
if add:
    if not name.strip() or qty is None or qty <= 0:
        st.error("Enter an ingredient and a positive quantity.")
    else:
        cleaned = name.strip().lower()
        items = [x for x in st.session_state.pantry_items if x["ingredient_name"] != cleaned]
        items.append({"ingredient_name": cleaned, "quantity": float(qty), "unit": unit})
        st.session_state.pantry_items = items
        st.session_state.confirmed_user_state = None  # Require reconfirmation after pantry edits.
        st.success("Pantry saved. Reconfirm your meal-planning preferences before generating.")

if st.session_state.pantry_items:
    st.subheader("Current pantry")
    edited = st.data_editor(
        st.session_state.pantry_items,
        num_rows="dynamic", hide_index=True, use_container_width=True,
        key="pantry_editor",
    )
    if st.button("Save pantry edits"):
        normalized = []
        errors = []
        for item in edited:
            try:
                name = str(item.get("ingredient_name") or "").strip().lower()
                quantity = float(item.get("quantity"))
                unit = str(item.get("unit") or "").strip()
                if not name or quantity <= 0 or not unit:
                    raise ValueError("invalid ingredient")
                normalized.append({"ingredient_name": name, "quantity": quantity, "unit": unit})
            except (TypeError, ValueError):
                errors.append(item)
        if errors or len({x["ingredient_name"] for x in normalized}) != len(normalized):
            st.error("All rows need unique ingredient names, positive quantities, and units.")
        else:
            st.session_state.pantry_items = normalized
            st.session_state.confirmed_user_state = None
            st.success("Pantry updated. Reconfirm preferences before generating.")
    st.json(current_pantry())
else:
    st.info("Your pantry is empty.")

st.divider()
st.subheader("Pantry image (preview only)")
image = st.file_uploader("Upload JPG or PNG", type=["jpg", "jpeg", "png"])
if image:
    st.image(image, caption="Uploaded pantry image", use_container_width=True)
    st.warning("Automatic ingredient recognition is not connected. Add ingredients manually, including their quantities.")
