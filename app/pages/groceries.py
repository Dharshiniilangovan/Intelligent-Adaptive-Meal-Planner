"""Read-only grocery view; respects price source and completeness."""
import streamlit as st
from app.components.ui_state import result_basket

st.title("Groceries")
basket = result_basket()
if not basket:
    st.info("No grocery basket yet. This page will show real Grocery Agent results after planner integration.")
else:
    items = basket.get("items") or []
    if basket.get("projected_cost_complete") is True:
        st.metric("Total planning cost", f"S${basket['projected_cost']:.2f}")
        st.caption("Planning cost may include model-generated estimates; it is not necessarily a verified checkout price.")
    else:
        st.warning("The grocery total is incomplete; missing prices are not treated as zero.")
    st.dataframe([{
        "Ingredient": x.get("name"), "Required": x.get("required_quantity"),
        "Required unit": x.get("required_unit"), "Package size": x.get("package_quantity"),
        "Package unit": x.get("package_unit"), "Packages": x.get("packages"),
        "Cost (SGD)": x.get("effective_purchase_cost"),
        "Price source": x.get("price_source"),
        "Coverage verified": x.get("quantity_coverage_verified"),
    } for x in items], hide_index=True, use_container_width=True)
    if basket.get("unpriced_items"):
        st.warning(f"Unpriced items: {', '.join(basket['unpriced_items'])}")
