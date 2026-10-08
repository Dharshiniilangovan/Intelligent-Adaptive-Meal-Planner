
"""src/agents/grocery_agent.py

Grocery Agent.

The Grocery Agent receives missing ingredients from the
Ingredient Agent / Manager and uses GroceryService to obtain
purchasable FairPrice grocery options.

BudgetService checks whether the combined grocery purchase
cost fits the remaining budget.

The final recipe decision remains with the Reasoning Engine.
"""

import math

from src.agents.contracts import (
    AgentResult,
    AgentStatus,
)

from src.grocery.grocery_service import (
    GroceryService,
    grocery_summary,
)

from src.reasoning.budget_service import check_grocery_budget


class GroceryAgent:
    """
    Agent responsible for grocery purchasing facts.

    Input:
        recipe_id:
            Candidate recipe being evaluated.

        missing_ingredients:
            Ingredients that need to be purchased.

        remaining_budget:
            Available grocery budget. Optional.

    Output:
        Shared AgentResult containing grocery information,
        combined purchase cost, and budget feasibility.
    """

    def __init__(
        self,
        grocery_service: GroceryService | None = None,
    ):
        self.grocery_service = (
            grocery_service
            if grocery_service is not None
            else GroceryService()
        )

    def run(
        self,
        recipe_id: str,
        missing_ingredients: list[dict] | dict,
        remaining_budget: float | None = None,
    ) -> dict:
        """
        Find purchasable grocery options for missing ingredients.

        GroceryService performs:
        - FairPrice search
        - product filtering
        - price extraction
        - package parsing
        - package calculation
        - minimum-package fallback
        - caching

        BudgetService performs:
        - total known purchase cost checking
        - budget feasibility
        - remaining budget calculation
        - unknown-cost handling
        """

        # ---------------------------------------------------------
        # Validate recipe ID
        # ---------------------------------------------------------

        if not recipe_id:
            return AgentResult(
                agent="grocery",
                status=AgentStatus.FAILED,
                data={},
                warnings=[],
                errors=["recipe_id is required"],
            ).to_dict()

        # ---------------------------------------------------------
        # Validate missing ingredients
        # ---------------------------------------------------------

        if not isinstance(
            missing_ingredients,
            (list, dict),
        ):
            return AgentResult(
                agent="grocery",
                status=AgentStatus.FAILED,
                data={
                    "recipe_id": recipe_id,
                },
                warnings=[],
                errors=[
                    "missing_ingredients must be a list or dictionary"
                ],
            ).to_dict()

        # ---------------------------------------------------------
        # Nothing needs purchasing
        # ---------------------------------------------------------

        if not missing_ingredients:

            budget_result = None
            budget_status = "not_checked"

            if remaining_budget is not None:
                try:
                    budget_result = check_grocery_budget(
                        grocery_results={
                            "priced_products": [],
                            "incomplete_products": [],
                            "missing_products": [],
                        },
                        remaining_budget=remaining_budget,
                    )

                    budget_status = budget_result["budget_status"]

                except (TypeError, ValueError) as exc:
                    return AgentResult(
                        agent="grocery",
                        status=AgentStatus.FAILED,
                        data={
                            "recipe_id": recipe_id,
                        },
                        warnings=[],
                        errors=[
                            f"Budget validation failed: {exc}"
                        ],
                    ).to_dict()

            return AgentResult(
                agent="grocery",
                status=AgentStatus.SUCCESS,
                data={
                    "recipe_id": recipe_id, 
                    "items": [],
                    "known_cost": 0.0,
                    "all_items_priced": True,
                    "unpriced_items": [],
                    "projected_cost": 0.0,
                    "projected_cost_complete": True,
                    "projected_items": 0,
                    "projection_missing": [],

                    "budget": budget_result,
                    "budget_status": budget_status,
                    "remaining_budget": remaining_budget,
                    "budget_after_purchase": (
                        budget_result.get("budget_after_purchase")
                        if budget_result is not None
                        else None
                    ),
                },
                warnings=[],
                errors=[],
            ).to_dict()

        # ---------------------------------------------------------
        # Call existing GroceryService
        # ---------------------------------------------------------

        try:
            options = (
                self.grocery_service
                .get_grocery_list(
                    missing_ingredients,
                    recipe_id=recipe_id,
                )
            )

            
            # ---------------------------------------------------------
            # Prevent empty grocery results from being treated
            # as successfully priced purchases.
            # ---------------------------------------------------------

            if not options:
                return AgentResult(
                    agent="grocery",
                    status=AgentStatus.PARTIAL,
                    data={
                        "recipe_id": recipe_id,
                        "items": [],
                        "known_cost": 0.0,
                        "all_items_priced": False,
                        "unpriced_items": [
                            (
                                item.get("ingredient_name")
                                or item.get("ingredient")
                            )
                            for item in (
                                missing_ingredients.values()
                                if isinstance(missing_ingredients, dict)
                                else missing_ingredients
                            )
                            if isinstance(item, dict)
                        ] if isinstance(missing_ingredients, list) else list(missing_ingredients.keys()),
                        "budget": None,
                        "budget_status": "uncertain"
                            if remaining_budget is not None
                            else "not_checked",
                        "remaining_budget": remaining_budget,
                        "budget_after_purchase": None,
                    },
                    warnings=[
                        "Grocery lookup returned no products for "
                        "the requested missing ingredients."
                    ],
                    errors=[],
                ).to_dict()


            grocery_results = grocery_summary(options)

        except Exception as exc:
            return AgentResult(
                agent="grocery",
                status=AgentStatus.FAILED,
                data={
                    "recipe_id": recipe_id,
                },
                warnings=[],
                errors=[
                    f"Grocery lookup failed: {exc}"
                ],
            ).to_dict()

        # ---------------------------------------------------------
        # Known purchase cost
        #
        # Only products with a usable total_cost contribute.
        # Missing/incomplete products are NOT treated as free.
        # ---------------------------------------------------------

        known_cost = round(
            sum(
                float(item["total_cost"])
                for item in grocery_results["priced_products"]
                if item.get("total_cost") is not None
            ),
            2,
        )

        # ---------------------------------------------------------
        # Find items whose purchase cost is unknown
        # ---------------------------------------------------------

        unpriced_items = []

        for item in grocery_results["incomplete_products"]:
            ingredient = item.get("ingredient")

            if ingredient:
                unpriced_items.append(ingredient)

        for item in grocery_results["missing_products"]:
            ingredient = item.get("ingredient")

            if ingredient:
                unpriced_items.append(ingredient)

        # Remove duplicates while preserving order.
        unpriced_items = list(
            dict.fromkeys(unpriced_items)
        )

        # ---------------------------------------------------------
        # all_items_priced
        # ---------------------------------------------------------

        all_items_priced = (
            len(unpriced_items) == 0
        )

        # ---------------------------------------------------------
        # Warnings
        # ---------------------------------------------------------

        warnings = [
            f"No complete purchase price found for {ingredient}"
            for ingredient in unpriced_items
        ]

        
        # ---------------------------------------------------------
        # Warn when one retail package is assumed sufficient.
        #
        # The purchase price is known, but exact quantity
        # coverage has not been verified.
        # ---------------------------------------------------------

        for item in grocery_results["priced_products"]:

            if (
                item.get("purchase_basis") == "minimum_retail_package"
                or item.get("match_status") == "matched_minimum_package"
            ):

                ingredient = item.get(
                    "ingredient",
                    "unknown ingredient",
                )

                warnings.append(
                    f"{ingredient}: one retail package is "
                    "assumed sufficient; exact quantity "
                    "coverage is not verified."
                )


        # ---------------------------------------------------------
        # Agent status
        #
        # success:
        #   Every grocery item has a usable purchase cost.
        #
        # partial:
        #   Some costs remain unknown.
        #
        # failed:
        #   Invalid input or service failure.
        # ---------------------------------------------------------

        if all_items_priced:
            status = AgentStatus.SUCCESS
        else:
            status = AgentStatus.PARTIAL

        # ---------------------------------------------------------
        # Combine grocery items
        # ---------------------------------------------------------

        items = (
            grocery_results["priced_products"]
            + grocery_results["incomplete_products"]
            + grocery_results["missing_products"]
        )

        # ---------------------------------------------------------
        # BUDGET SERVICE INTEGRATION
        #
        # Pass actual GroceryService results.
        #
        # BudgetService returns:
        #   pass
        #   hard_fail
        #   uncertain
        #
        # If no budget was provided:
        #   not_checked
        # ---------------------------------------------------------

        budget_result = None
        budget_status = "not_checked"

        if remaining_budget is not None:

            try:
                budget_result = check_grocery_budget(
                    grocery_results=grocery_results,
                    remaining_budget=remaining_budget,
                )

                budget_status = budget_result["budget_status"]

            except (TypeError, ValueError) as exc:
                return AgentResult(
                    agent="grocery",
                    status=AgentStatus.FAILED,
                    data={
                        "recipe_id": recipe_id,
                        "items": items,
                        "known_cost": known_cost,
                        "all_items_priced": all_items_priced,
                        "unpriced_items": unpriced_items,
                    },
                    warnings=warnings,
                    errors=[
                        f"Budget validation failed: {exc}"
                    ],
                ).to_dict()

        
        # ---------------------------------------------------------
        # PROVISIONAL BUDGET EVALUATION
        #
        # Separate from the existing BudgetService decision.
        # Never overwrite budget_status or known_cost.
        # ---------------------------------------------------------

        estimated_budget_status = "not_checked"
        estimated_budget_after_purchase = None
        estimated_budget_reason = (
            "No remaining budget was provided."
        )

        projected_cost = grocery_results.get("projected_cost")
        projection_complete = grocery_results.get(
            "projected_cost_complete",
            False,
        )

        if remaining_budget is not None:

            if (
                not projection_complete
                or projected_cost is None
            ):
                estimated_budget_status = "uncertain"
                estimated_budget_reason = (
                    "One or more grocery items have no "
                    "reliable projected purchase cost."
                )

            else:
                projected_remaining = round(
                    float(remaining_budget)
                    - float(projected_cost),
                    2,
                )

                estimated_budget_after_purchase = (
                    projected_remaining
                )

                if projected_remaining >= 0:
                    estimated_budget_status = "pass"
                    estimated_budget_reason = (
                        "Projected grocery purchases fit "
                        "within the available budget. "
                        "This is a provisional estimate, "
                        "not a verified purchase total."
                    )

                else:
                    estimated_budget_status = "hard_fail"
                    estimated_budget_reason = (
                        "Projected grocery purchases exceed "
                        "the available budget. "
                        "This is a provisional estimate."
                    )


        # ---------------------------------------------------------
        # Shared AgentResult
        # ---------------------------------------------------------

        return AgentResult(
            agent="grocery",
            status=status,
            data={
                "recipe_id": recipe_id,

                "items": items,

                "known_cost": known_cost,

                
                # Provisional shopping estimate.
                # Does not affect the verified budget decision.
                "projected_cost": grocery_results.get(
                    "projected_cost"
                ),

                "projected_cost_complete": grocery_results.get(
                    "projected_cost_complete",
                    False,
                ),

                "projected_items": grocery_results.get(
                    "projected_items",
                    0,
                ),

                "projection_missing": grocery_results.get(
                    "projection_missing",
                    [],
                ),


                "all_items_priced": all_items_priced,

                "unpriced_items": unpriced_items,

                # BudgetService results
                "budget": budget_result,

                "budget_status": budget_status,

                
                "estimated_budget_status": (
                    estimated_budget_status
                ),

                "estimated_budget_after_purchase": (
                    estimated_budget_after_purchase
                ),

                "estimated_budget_reason": (
                    estimated_budget_reason
                ),


                "remaining_budget": remaining_budget,

                "budget_after_purchase": (
                    budget_result.get("budget_after_purchase")
                    if budget_result is not None
                    else None
                ),
            },
            warnings=warnings,
            errors=[],
        ).to_dict()


# ============================================================
# DAY 5 - PLAN-LEVEL GROCERY AGGREGATION
# Member 4
# ============================================================


def _ingredient_key(item):
    """
    Return a stable key for matching an ingredient.

    ingredient_id is preferred because names may have
    capitalization/spacing differences.
    """

    ingredient_id = item.get("ingredient_id")

    if ingredient_id:
        return str(ingredient_id).strip()

    name = (
        item.get("ingredient_name")
        or item.get("name")
        or ""
    )

    return name.strip().lower()


def _ingredient_name(item):
    """
    Get ingredient name regardless of whether the source uses
    'ingredient_name' or 'name'.
    """

    return (
        item.get("ingredient_name")
        or item.get("name")
        or ""
    ).strip()


def aggregate_requirements(recipe_requirements):
    """
    Combine ingredient requirements from ALL selected recipes.

    Example:
        Recipe A -> rice 300g
        Recipe B -> rice 400g

    Result:
        rice 700g

    Parameters
    ----------
    recipe_requirements : list

        [
            {
                "recipe_id": "R001",
                "ingredients": [
                    {
                        "ingredient_id": "ING001",
                        "ingredient_name": "rice",
                        "quantity": 300,
                        "unit": "g"
                    }
                ]
            }
        ]

    Returns
    -------
    list
        Aggregated ingredient requirements.
    """

    aggregated = {}

    for recipe in recipe_requirements or []:

        recipe_id = recipe.get("recipe_id")
        ingredients = recipe.get("ingredients", [])

        for ingredient in ingredients:

            key = _ingredient_key(ingredient)

            if not key:
                continue

            name = _ingredient_name(ingredient)

            try:
                quantity = float(
                    ingredient.get("quantity", 0) or 0
                )
            except (TypeError, ValueError):
                quantity = 0.0

            unit = ingredient.get("unit")

            if quantity <= 0:
                continue

            if key not in aggregated:
                aggregated[key] = {
                    "ingredient_id": ingredient.get("ingredient_id"),
                    "ingredient_name": name,
                    "quantity": 0.0,
                    "unit": unit,
                    "recipe_ids": [],
                }

            existing_unit = aggregated[key]["unit"]

            # Do not silently combine incompatible units.
            if (
                existing_unit
                and unit
                and existing_unit != unit
            ):
                raise ValueError(
                    f"Incompatible units for {name}: "
                    f"{existing_unit} vs {unit}"
                )

            aggregated[key]["quantity"] += quantity

            if (
                recipe_id is not None
                and recipe_id not in aggregated[key]["recipe_ids"]
            ):
                aggregated[key]["recipe_ids"].append(recipe_id)

    return list(aggregated.values())


def subtract_inventory(requirements, inventory):
    """
    Subtract existing pantry/inventory quantities from the
    aggregated plan requirements.

    Example:
        Required rice = 700g
        Pantry rice = 500g

    Purchase requirement = 200g
    """

    inventory_map = {}

    for item in inventory or []:

        key = _ingredient_key(item)

        if not key:
            continue

        try:
            quantity = float(
                item.get("quantity", 0) or 0
            )
        except (TypeError, ValueError):
            quantity = 0.0

        if key not in inventory_map:
            inventory_map[key] = {
                "quantity": quantity,
                "unit": item.get("unit"),
            }

        else:
            existing_unit = inventory_map[key]["unit"]
            current_unit = item.get("unit")

            if (
                existing_unit
                and current_unit
                and existing_unit == current_unit
            ):
                inventory_map[key]["quantity"] += quantity

    results = []

    for requirement in requirements or []:

        key = _ingredient_key(requirement)

        required_quantity = float(
            requirement.get("quantity", 0) or 0
        )

        required_unit = requirement.get("unit")

        inventory_item = inventory_map.get(key)

        inventory_available = 0.0

        if inventory_item:

            inventory_unit = inventory_item.get("unit")

            if (
                inventory_unit == required_unit
                or not inventory_unit
                or not required_unit
            ):
                inventory_available = max(
                    0.0,
                    float(
                        inventory_item.get("quantity", 0) or 0
                    ),
                )

        inventory_used = min(
            required_quantity,
            inventory_available,
        )

        purchase_required = max(
            0.0,
            required_quantity - inventory_used,
        )

        result = dict(requirement)

        result.update({
            "required_quantity": required_quantity,
            "inventory_available": inventory_available,
            "inventory_used": inventory_used,
            "purchase_required": purchase_required,
        })

        results.append(result)

    return results


def calculate_packages(
    required_quantity,
    package_quantity,
):
    """
    Calculate the number of whole packages that must be bought.

    Examples:
        need 200g, package 1000g -> 1
        need 1000g, package 1000g -> 1
        need 1001g, package 1000g -> 2
    """

    try:
        required_quantity = float(required_quantity)
        package_quantity = float(package_quantity)

    except (TypeError, ValueError):
        return None

    if required_quantity <= 0:
        return 0

    if package_quantity <= 0:
        return None

    return math.ceil(
        required_quantity / package_quantity
    )


def calculate_package_leftover(
    required_quantity,
    package_quantity,
    packages,
):
    """
    Calculate how much purchased product remains after
    satisfying the current requirement.
    """

    if packages is None:
        return None

    try:
        required_quantity = float(required_quantity)
        package_quantity = float(package_quantity)
        packages = int(packages)

    except (TypeError, ValueError):
        return None

    purchased_quantity = (
        package_quantity * packages
    )

    return max(
        0.0,
        purchased_quantity - required_quantity,
    )


def find_plan_product(
    requirement,
    product_catalog,
):
    """
    Find a grocery product for an ingredient.

    Matching order:
    1. ingredient_id
    2. normalized ingredient name
    """

    requirement_id = requirement.get("ingredient_id")

    # --------------------------------------------------------
    # 1. ID matching
    # --------------------------------------------------------

    if requirement_id:

        for product in product_catalog or []:

            if (
                str(
                    product.get("ingredient_id", "")
                ).strip()
                == str(requirement_id).strip()
            ):
                return product

    # --------------------------------------------------------
    # 2. Name matching
    # --------------------------------------------------------

    requirement_name = _ingredient_name(
        requirement
    ).lower()

    if requirement_name:

        for product in product_catalog or []:

            product_name = (
                product.get("ingredient_name")
                or product.get("name")
                or ""
            ).strip().lower()

            if product_name == requirement_name:
                return product

    return None


def build_plan_grocery_basket(
    recipe_requirements,
    inventory=None,
    product_catalog=None,
):
    """
    Build ONE grocery basket for the entire meal plan.

    This is the Member-4 Day-5 function.

    Steps:
    1. Aggregate ingredients across recipes.
    2. Subtract existing inventory.
    3. Find a grocery product.
    4. Calculate required package count.
    5. Calculate purchase cost.
    6. Calculate package leftovers.
    7. Track missing/unreliable pricing.

    This function reports grocery/cost facts.

    It does not decide whether the complete meal plan
    is feasible.
    """

    inventory = inventory or []
    product_catalog = product_catalog or []

    # ========================================================
    # STEP 1 - AGGREGATE ALL RECIPES
    # ========================================================

    aggregated = aggregate_requirements(
        recipe_requirements
    )

    # ========================================================
    # STEP 2 - SUBTRACT PANTRY
    # ========================================================

    purchase_requirements = subtract_inventory(
        aggregated,
        inventory,
    )

    basket_items = []
    known_cost = 0.0
    unpriced_items = []

    # ========================================================
    # STEP 3 - PRICE EACH AGGREGATED REQUIREMENT
    # ========================================================

    for requirement in purchase_requirements:

        purchase_required = float(
            requirement.get("purchase_required", 0) or 0
        )

        # Pantry completely satisfies this ingredient.
        if purchase_required <= 0:
            continue

        ingredient_id = requirement.get("ingredient_id")
        ingredient_name = _ingredient_name(requirement)
        required_unit = requirement.get("unit")

        product = find_plan_product(
            requirement,
            product_catalog,
        )

        # ====================================================
        # NO PRODUCT FOUND
        # ====================================================

        if product is None:

            unpriced_items.append(ingredient_name)

            basket_items.append({
                "ingredient_id": ingredient_id,
                "name": ingredient_name,
                "required_quantity": purchase_required,
                "required_unit": required_unit,
                "package_quantity": None,
                "package_unit": None,
                "packages": None,
                "purchased_quantity": None,
                "price_per_package": None,
                "purchase_cost": None,
                "leftover_quantity": None,
                "inventory_used": requirement.get(
                    "inventory_used", 0
                ),
                "recipe_ids": requirement.get(
                    "recipe_ids", []
                ),
                "pricing_status": "unpriced",
            })

            continue

        # ====================================================
        # READ PRODUCT DATA
        # ====================================================

        package_quantity = product.get("package_quantity")
        package_unit = product.get("package_unit")

        price = product.get("price")

        if price is None:
            price = product.get("price_per_package")

        # ====================================================
        # PACKAGE DATA MISSING
        # ====================================================

        try:
            package_quantity_float = float(package_quantity)
        except (TypeError, ValueError):
            package_quantity_float = None

        if (
            package_quantity_float is None
            or package_quantity_float <= 0
        ):

            unpriced_items.append(ingredient_name)

            basket_items.append({
                "ingredient_id": ingredient_id,
                "name": ingredient_name,
                "required_quantity": purchase_required,
                "required_unit": required_unit,
                "package_quantity": package_quantity,
                "package_unit": package_unit,
                "packages": None,
                "purchased_quantity": None,
                "price_per_package": price,
                "purchase_cost": None,
                "leftover_quantity": None,
                "inventory_used": requirement.get(
                    "inventory_used", 0
                ),
                "recipe_ids": requirement.get(
                    "recipe_ids", []
                ),
                "pricing_status": "invalid_package",
            })

            continue

        # ====================================================
        # UNIT CHECK
        # ====================================================

        if (
            package_unit
            and required_unit
            and package_unit != required_unit
        ):

            unpriced_items.append(ingredient_name)

            basket_items.append({
                "ingredient_id": ingredient_id,
                "name": ingredient_name,
                "required_quantity": purchase_required,
                "required_unit": required_unit,
                "package_quantity": package_quantity_float,
                "package_unit": package_unit,
                "packages": None,
                "purchased_quantity": None,
                "price_per_package": price,
                "purchase_cost": None,
                "leftover_quantity": None,
                "inventory_used": requirement.get(
                    "inventory_used", 0
                ),
                "recipe_ids": requirement.get(
                    "recipe_ids", []
                ),
                "pricing_status": "unit_mismatch",
            })

            continue

        # ====================================================
        # PRICE MISSING
        # ====================================================

        try:
            price_float = float(price)
        except (TypeError, ValueError):
            price_float = None

        if price_float is None:

            unpriced_items.append(ingredient_name)

            basket_items.append({
                "ingredient_id": ingredient_id,
                "name": ingredient_name,
                "required_quantity": purchase_required,
                "required_unit": required_unit,
                "package_quantity": package_quantity_float,
                "package_unit": package_unit,
                "packages": None,
                "purchased_quantity": None,
                "price_per_package": None,
                "purchase_cost": None,
                "leftover_quantity": None,
                "inventory_used": requirement.get(
                    "inventory_used", 0
                ),
                "recipe_ids": requirement.get(
                    "recipe_ids", []
                ),
                "pricing_status": "unpriced",
            })

            continue

        # ====================================================
        # PACKAGE CALCULATION
        # ====================================================

        packages = calculate_packages(
            purchase_required,
            package_quantity_float,
        )

        purchased_quantity = (
            packages * package_quantity_float
        )

        purchase_cost = (
            packages * price_float
        )

        leftover_quantity = calculate_package_leftover(
            purchase_required,
            package_quantity_float,
            packages,
        )

        known_cost += purchase_cost

        basket_items.append({
            "ingredient_id": ingredient_id,
            "name": ingredient_name,
            "required_quantity": purchase_required,
            "required_unit": required_unit,
            "package_quantity": package_quantity_float,
            "package_unit": package_unit,
            "packages": packages,
            "purchased_quantity": purchased_quantity,
            "price_per_package": round(price_float, 2),
            "purchase_cost": round(purchase_cost, 2),
            "leftover_quantity": leftover_quantity,
            "inventory_used": requirement.get(
                "inventory_used", 0
            ),
            "recipe_ids": requirement.get(
                "recipe_ids", []
            ),
            "pricing_status": "priced",
        })

    # Remove duplicate names while preserving order.
    unpriced_items = list(
        dict.fromkeys(unpriced_items)
    )

    return {
        "items": basket_items,
        "known_cost": round(known_cost, 2),
        "all_items_priced": len(unpriced_items) == 0,
        "unpriced_items": unpriced_items,
        "aggregated_requirements": aggregated,
        "purchase_requirements": purchase_requirements,
    }


def build_cost_summary(
    grocery_basket,
    initial_budget,
):
    """
    Return cost facts for the plan.

    This does NOT determine final plan feasibility.
    """

    known_cost = float(
        grocery_basket.get("known_cost", 0) or 0
    )

    initial_budget = float(initial_budget)

    remaining = (
        initial_budget - known_cost
    )

    return {
        "initial_budget": round(initial_budget, 2),
        "known_grocery_cost": round(known_cost, 2),
        "remaining": round(remaining, 2),
        "all_items_priced": grocery_basket.get(
            "all_items_priced",
            False,
        ),
        "unpriced_items": grocery_basket.get(
            "unpriced_items",
            [],
        ),
    }
