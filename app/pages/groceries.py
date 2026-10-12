
"""Customer-facing grocery shopping list."""

import streamlit as st

from app.components.ui_state import result_basket
from app.components.presentation import money, number


st.title("Your shopping list")
st.caption(
    "Everything you need to prepare your planned meals."
)

basket = result_basket()

if not basket:
    st.info(
        "Generate a meal plan to see your shopping list."
    )

else:
    items = basket.get("items") or []

    # --------------------------------------------------
    # Total grocery cost
    # --------------------------------------------------

    total_cost = basket.get("planning_cost")

    if total_cost is None:
        total_cost = basket.get("projected_cost")

    complete = (
        basket.get(
            "planning_cost_complete",
            basket.get("projected_cost_complete", False),
        )
        is True
    )

    # --------------------------------------------------
    # Summary
    # --------------------------------------------------

    col1, col2 = st.columns(2)

    col1.metric(
        "Items to buy",
        len(items),
    )

    col2.metric(
        "Estimated shopping total",
        money(total_cost) if complete else "Not available",
    )

    st.caption(
        "Prices are for planning and may differ at checkout."
    )

    if not complete:
        st.warning(
            "Some grocery prices are unavailable. "
            "The complete shopping total cannot yet "
            "be calculated."
        )

    # --------------------------------------------------
    # Shopping list
    # --------------------------------------------------

    rows = []

    for item in items:

        # Ingredient name
        name = (
            item.get("name")
            or item.get("ingredient_name")
            or "Ingredient"
        )

        # ----------------------------------------------
        # Required ingredient quantity
        # ----------------------------------------------

        required_quantity = item.get(
            "required_quantity"
        )

        required_unit = (
            item.get("required_unit") or ""
        )

        if required_quantity is not None:
            required_text = (
                f"{number(required_quantity)} "
                f"{required_unit}"
            ).strip()
        else:
            required_text = "Not specified"

        # ----------------------------------------------
        # Retail package information
        # ----------------------------------------------

        package_quantity = item.get(
            "package_quantity"
        )

        package_unit = (
            item.get("package_unit") or ""
        )

        packages = item.get("packages")

        if (
            package_quantity is not None
            and packages is not None
        ):
            package_text = (
                f"{number(packages)} × "
                f"{number(package_quantity)} "
                f"{package_unit}"
            ).strip()

        elif packages is not None:
            package_text = (
                f"{number(packages)} package(s)"
            )

        else:
            package_text = "Not available"

        # ----------------------------------------------
        # Individual ingredient purchase cost
        # ----------------------------------------------

        item_cost = item.get(
            "effective_purchase_cost"
        )

        if item_cost is None:
            item_cost = item.get(
                "purchase_cost"
            )

        if item_cost is None:
            item_cost = item.get(
                "estimated_purchase_cost"
            )

        # ----------------------------------------------
        # Add customer-facing row
        # ----------------------------------------------

        rows.append({
            "Ingredient": str(name).title(),
            "Recipe requires": required_text,
            "Buy": package_text,
            "Cost": money(item_cost),
        })

    # --------------------------------------------------
    # Display shopping list
    # --------------------------------------------------

    if rows:
        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Ingredient": st.column_config.TextColumn(
                    "Ingredient",
                    width="medium",
                ),
                "Recipe requires": st.column_config.TextColumn(
                    "Recipe requires",
                    width="medium",
                ),
                "Buy": st.column_config.TextColumn(
                    "Buy",
                    width="medium",
                ),
                "Cost": st.column_config.TextColumn(
                    "Cost",
                    width="small",
                ),
            },
        )

    else:
        st.info(
            "No additional groceries are needed "
            "for your selected meals."
        )

    # --------------------------------------------------
    # Helpful notices
    # --------------------------------------------------

    unpriced = basket.get("unpriced_items") or []

    if unpriced:
        st.warning(
            "Prices are still unavailable for: "
            + ", ".join(map(str, unpriced))
        )

    if any(
        item.get("quantity_coverage_verified") is False
        for item in items
    ):
        st.caption(
            "Some package quantities are approximate. "
            "Check package sizes before purchasing."
        )
