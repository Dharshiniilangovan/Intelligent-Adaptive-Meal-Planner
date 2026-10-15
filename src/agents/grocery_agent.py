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
from src.reasoning.budget_service import (
    check_grocery_budget,
    check_provisional_grocery_budget,
)
from src.grocery.units import to_base
from src.grocery.ingredient_conversions import (
    estimate_ingredient_mass,
)
from src.utils.ingredient_conversion_lookup import (
    convert_using_ingredient_factor,
)
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
        # PROVISIONAL BUDGET SERVICE RESULT
        #
        # Separate from the strict BudgetService result.
        # Does not overwrite known_cost or budget_status.
        # ---------------------------------------------------------
        try:
            provisional_budget_result = (
                check_provisional_grocery_budget(
                    projected_cost=projected_cost,
                    projected_cost_complete=projection_complete,
                    remaining_budget=remaining_budget,
                    safety_margin=0.20,
                )
            )
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
                    f"Provisional budget validation failed: {exc}"
                ],
            ).to_dict()
        # ---------------------------------------------------------
        # OPTIONAL PLANNING BUDGET INFORMATION
        #
        # This does not modify BudgetService results.
        # It does not turn LLM estimates into verified costs.
        # ---------------------------------------------------------
        planning_budget_status = budget_status
        planning_budget_source = "verified"
        if budget_status == "not_checked":
            planning_budget_source = "not_checked"
        elif (
            budget_status == "uncertain"
            and projection_complete
            and projected_cost is not None
        ):
            if estimated_budget_status == "pass":
                planning_budget_status = "provisional_pass"
                planning_budget_source = "estimated"
            elif estimated_budget_status == "hard_fail":
                planning_budget_status = "provisional_hard_fail"
                planning_budget_source = "estimated"
            else:
                planning_budget_status = "uncertain"
                planning_budget_source = "incomplete"
        elif budget_status == "uncertain":
            planning_budget_source = "incomplete"
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
                 "planning_budget_status": (
                    planning_budget_status
                ),
                "planning_budget_source": (
                    planning_budget_source
                ),
                "provisional_budget": (
                    provisional_budget_result
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

def normalize_requirement_quantity(name, quantity, unit):
    original_quantity = quantity
    original_unit = str(unit or "").strip().lower()
    ingredient_name = " ".join(str(name or "").lower().split())

    try:
        quantity = float(quantity)
    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(quantity) or quantity <= 0:
        return None

    unit = original_unit

    # Preserve existing sesame oil special case.
    if ingredient_name == "sesame oil" and unit in {
        "pinch",
        "pinches",
    }:
        return {
            "quantity": round(quantity * 0.25, 4),
            "unit": "ml",
            "conversion_status": "estimated",
            "original_quantity": original_quantity,
            "original_unit": original_unit,
        }

    # Preserve exact physical volume and mass conversions.
    # These do not require ingredient-specific estimates.
    exact = to_base(quantity, unit)

    # if exact is not None and exact[1] in {"g", "ml"}:
    if (
    exact is not None
    and exact[1] in {"g", "ml"}
    and not (
        exact[1] == "ml"
        and ingredient_name not in {
            "oil",
            "vegetable oil",
            "cooking oil",
        }
        and estimate_ingredient_mass(name, quantity, unit) is not None
    )
):
        return {
            "quantity": exact[0],
            "unit": exact[1],
            "conversion_status": "exact",
            "original_quantity": original_quantity,
            "original_unit": original_unit,
        }

    # Prefer ingredient-specific estimates for count, bunch,
    # clove, and other non-standard recipe units.
    estimated = estimate_ingredient_mass(
        name,
        quantity,
        unit,
    )

    if estimated is not None:
        return {
            "quantity": estimated[0],
            "unit": estimated[1],
            "conversion_status": "estimated",
            "original_quantity": original_quantity,
            "original_unit": original_unit,
        }

    # Generic count conversions remain exact when no
    # ingredient-specific mass estimate is available.
    if exact is not None:
        return {
            "quantity": exact[0],
            "unit": exact[1],
            "conversion_status": "exact",
            "original_quantity": original_quantity,
            "original_unit": original_unit,
        }

    return {
        "quantity": quantity,
        "unit": unit,
        "conversion_status": "unresolved",
        "original_quantity": original_quantity,
        "original_unit": original_unit,
    }
# def normalize_requirement_quantity(name, quantity, unit):
#     original_quantity = quantity
#     original_unit = str(unit or "").strip().lower()
#     ingredient_name = " ".join(str(name or "").lower().split())
#     try:
#         quantity = float(quantity)
#     except (TypeError, ValueError, OverflowError):
#         return None
#     if not math.isfinite(quantity) or quantity <= 0:
#         return None
#     unit = original_unit
#     # A pinch is not a standard liquid measurement.
#     # This is an explicitly provisional MVP assumption.
#     if ingredient_name == "sesame oil" and unit in {
#         "pinch",
#         "pinches",
#     }:
#         return {
#             "quantity": round(quantity * 0.25, 4),
#             "unit": "ml",
#             "conversion_status": "estimated",
#             "original_quantity": original_quantity,
#             "original_unit": original_unit,
#         }
#     # Ingredient-specific mass conversions first.
#     estimated = estimate_ingredient_mass(
#         name,
#         quantity,
#         unit,
#     )
#     if estimated is not None:
#         return {
#             "quantity": estimated[0],
#             "unit": estimated[1],
#             "conversion_status": "estimated",
#             "original_quantity": original_quantity,
#             "original_unit": original_unit,
#         }
#     # General physical-unit conversion.
#     exact = to_base(quantity, unit)
#     if exact is not None:
#         return {
#             "quantity": exact[0],
#             "unit": exact[1],
#             "conversion_status": "exact",
#             "original_quantity": original_quantity,
#             "original_unit": original_unit,
#         }
#     return {
#         "quantity": quantity,
#         "unit": unit,
#         "conversion_status": "unresolved",
#         "original_quantity": original_quantity,
#         "original_unit": original_unit,
#     }

# ============================================================
# REQUIREMENT CLASSIFICATION
#
# Every recipe ingredient occurrence is exactly one of:
#   measurable   numeric quantity with a unit (its conversion may
#                still be exact, estimated or unresolved)
#   qualitative  "to taste", "as needed", ...
#   unresolved   quantity or unit cannot be determined, so no
#                numeric requirement can be formed
# Aggregation, the grocery basket and inventory reconciliation all
# use this one classifier so no occurrence is dropped or counted twice.
# ============================================================

QUALITATIVE_INSTRUCTIONS = {
    "to taste",
    "as needed",
    "as required",
    "required",
}

_MISSING_TEXT = {"", "nan", "none", "null"}

_STATUS_PRIORITY = {
    "exact": 0,
    "estimated": 1,
    "volume_preserved_no_density": 2,
    "unresolved": 3,
}

_DATASET_STATUS_MAP = {
    "exact_mass": "exact",
    "exact_volume": "exact",
    "estimated_density": "estimated",
    "estimated_piece_weight": "estimated",
    "volume_retained": "volume_preserved_no_density",
    "volume_preserved_no_density": "volume_preserved_no_density",
    "unresolved": "unresolved",
}


def _clean_text(value):
    """Lower-case text, with None/NaN/"nan" treated as missing."""
    if value is None:
        return ""
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    text = str(value).strip().lower()
    return "" if text in _MISSING_TEXT else text


def _positive_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _original_measurement(ingredient):
    quantity = ingredient.get(
        "quantity",
        ingredient.get("quantity_per_serving"),
    )
    unit = ingredient.get("unit")
    return quantity, unit


def classify_requirement(ingredient):
    """
    Classify one recipe ingredient occurrence.

    Returns one of:
        ("measurable", normalized_measurement)
        ("qualitative", instruction)
        ("unresolved", reason)

    Never invents a quantity, unit or density.
    """
    if not _ingredient_key(ingredient):
        return "unresolved", "missing_ingredient_identity"

    quantity, unit = _original_measurement(ingredient)
    quantity_text = (
        _clean_text(quantity) if isinstance(quantity, str) else ""
    )
    unit_text = _clean_text(unit)

    if unit_text in QUALITATIVE_INSTRUCTIONS:
        return "qualitative", unit_text
    if quantity_text in QUALITATIVE_INSTRUCTIONS:
        return "qualitative", quantity_text

    # Prefer pre-normalized dataset measurements.
    dataset_quantity = _positive_number(
        ingredient.get("normalized_quantity_per_serving")
    )
    dataset_unit = _clean_text(ingredient.get("normalized_unit"))
    dataset_status = _clean_text(ingredient.get("conversion_status"))

    if (
        dataset_quantity is not None
        and dataset_unit
        and dataset_status in _DATASET_STATUS_MAP
    ):
        return "measurable", {
            "quantity": dataset_quantity,
            "unit": dataset_unit,
            "conversion_status": _DATASET_STATUS_MAP[dataset_status],
            "original_quantity": quantity,
            "original_unit": unit,
        }

    # Legacy (non-KB) input, or KB rows without usable values.
    if _clean_text(quantity) == "":
        return "unresolved", "missing_quantity"
    if _positive_number(quantity) is None:
        return "unresolved", "invalid_quantity"
    if not unit_text:
        return "unresolved", "missing_unit"

    # Do not reinterpret explicitly unresolved dataset values
    # as exact measurements.
    if dataset_status == "unresolved":
        return "unresolved", "unresolved_measurement"

    normalized = normalize_requirement_quantity(
        name=_ingredient_name(ingredient),
        quantity=quantity,
        unit=unit,
    )
    if normalized is None:
        return "unresolved", "invalid_quantity"

    return "measurable", normalized


def _occurrence_id(ingredient):
    return ingredient.get("occurrence_id")


def _identity_keys(item):
    """ID and normalized name, so records match on either."""
    keys = set()
    ingredient_id = str(item.get("ingredient_id") or "").strip()
    if ingredient_id:
        keys.add(("id", ingredient_id))
    name = " ".join(_ingredient_name(item).lower().split())
    if name:
        keys.add(("name", name))
    return keys


def aggregate_requirements(recipe_requirements):
    """
    Aggregate measurable ingredient requirements across recipes.

    Priority:
    1. Use pre-normalized dataset values when available.
    2. Fall back to runtime normalization for legacy inputs.
    3. Preserve original quantities and conversion uncertainty.
    4. Never combine incompatible units.

    Qualitative and unresolved occurrences are not aggregated here;
    collect_qualitative_requirements() and
    collect_unresolved_quantity_requirements() report them.
    """
    aggregated = {}

    for recipe in recipe_requirements or []:
        recipe_id = recipe.get("recipe_id")

        for ingredient in recipe.get("ingredients", []):
            if not isinstance(ingredient, dict):
                continue

            kind, normalized = classify_requirement(ingredient)

            if kind != "measurable":
                continue

            key = _ingredient_key(ingredient)
            name = _ingredient_name(ingredient)

            quantity = normalized["quantity"]
            unit = normalized["unit"]
            conversion_status = normalized["conversion_status"]

            group_key = (key, unit)

            if group_key not in aggregated:
                aggregated[group_key] = {
                    "ingredient_id": ingredient.get("ingredient_id"),
                    "ingredient_name": name,
                    "quantity": 0.0,
                    "unit": unit,
                    "recipe_ids": [],
                    "conversion_status": conversion_status,
                    "normalization_status": (
                        "unresolved"
                        if conversion_status == "unresolved"
                        else "resolved"
                    ),
                    "source_requirements": [],
                }

            record = aggregated[group_key]
            record["quantity"] += quantity

            current_status = record["conversion_status"]

            if (
                _STATUS_PRIORITY[conversion_status]
                > _STATUS_PRIORITY[current_status]
            ):
                record["conversion_status"] = conversion_status

            if conversion_status == "unresolved":
                record["normalization_status"] = "unresolved"

            record["source_requirements"].append({
                "recipe_id": recipe_id,
                "slot_id": recipe.get("slot_id"),
                "occurrence_id": _occurrence_id(ingredient),
                "quantity": normalized["original_quantity"],
                "unit": normalized["original_unit"],
                "conversion_status": conversion_status,
            })

            if (
                recipe_id is not None
                and recipe_id not in record["recipe_ids"]
            ):
                record["recipe_ids"].append(recipe_id)

    # -----------------------------------------
    # Identify incompatible unit groups
    # -----------------------------------------

    ingredient_groups = {}

    for (ingredient_key, unit), record in aggregated.items():
        ingredient_groups.setdefault(
            ingredient_key, []
        ).append(record)

    for records in ingredient_groups.values():
        if len(records) > 1:
            units = [record["unit"] for record in records]

            for record in records:
                record["normalization_status"] = "unresolved"
                record["unresolved_units"] = units

    return list(aggregated.values())


def collect_unresolved_quantity_requirements(recipe_requirements):
    """
    Report ingredient occurrences whose quantity or unit cannot be
    determined (e.g. KB rows with no unit such as R30871 sesame seed).

    One record per ingredient, merged across recipes, keeping every
    source occurrence. No quantity, unit or package is invented.
    """
    records = {}

    for recipe in recipe_requirements or []:
        recipe_id = recipe.get("recipe_id")

        for ingredient in recipe.get("ingredients", []):
            if not isinstance(ingredient, dict):
                continue

            kind, reason = classify_requirement(ingredient)

            if kind != "unresolved":
                continue

            key = _ingredient_key(ingredient) or (
                f"unidentified:{_occurrence_id(ingredient) or id(ingredient)}"
            )
            quantity, unit = _original_measurement(ingredient)

            record = records.setdefault(key, {
                "ingredient_id": ingredient.get("ingredient_id"),
                "ingredient_name": _ingredient_name(ingredient),
                "requirement_type": "unresolved",
                "recipe_ids": [],
                "occurrence_ids": [],
                "reasons": [],
                "source_requirements": [],
            })

            record["source_requirements"].append({
                "recipe_id": recipe_id,
                "slot_id": recipe.get("slot_id"),
                "occurrence_id": _occurrence_id(ingredient),
                "quantity": quantity,
                "unit": unit,
                "conversion_status": ingredient.get("conversion_status"),
                "reason": reason,
            })
            record["occurrence_ids"].append(_occurrence_id(ingredient))

            if reason not in record["reasons"]:
                record["reasons"].append(reason)

            if (
                recipe_id is not None
                and recipe_id not in record["recipe_ids"]
            ):
                record["recipe_ids"].append(recipe_id)

    return list(records.values())

# def subtract_inventory(requirements, inventory):
#     """
#     Deduct pantry stock from aggregated requirements.
#     Does not mutate the original inventory.
#     Does not consume the same pantry stock twice.
#     """
#     stock_map = {}
#     for item in inventory or []:
        
#         key = _ingredient_key(item)
#         if not key:
#             continue
#         name = _ingredient_name(item)
#         normalized = normalize_requirement_quantity(
#             name,
#             item.get("quantity"),
#             item.get("unit"),
#         )
#         if normalized is None:
#             continue
#         stock_map.setdefault(key, []).append({
#             "quantity": normalized["quantity"],
#             "unit": normalized["unit"],
#             "conversion_status": normalized["conversion_status"],
#         })
#     results = []
#     for requirement in requirements or []:
#         key = _ingredient_key(requirement)
#         required = float(requirement.get("quantity", 0))
#         required_unit = requirement.get("unit")
#         remaining = required
#         inventory_used = 0.0
#         inventory_unresolved = False
#         for stock in stock_map.get(key, []):
#             if remaining <= 0:
#                 break
#             # Requirements and inventory must share a
#             # comparable normalized unit.
#             if stock["unit"] != required_unit:
#                 inventory_unresolved = True
#                 continue
#             available = max(0.0, stock["quantity"])
#             consumed = min(remaining, available)
#             remaining -= consumed
#             inventory_used += consumed
#             stock["quantity"] -= consumed
#         result = dict(requirement)
#         result.update({
#             "required_quantity": required,
#             "inventory_available": inventory_used,
#             "inventory_used": inventory_used,
#             "purchase_required": max(0.0, remaining),
#             "inventory_conversion_unresolved": inventory_unresolved,
#         })
#         results.append(result)
#     return results

def subtract_inventory(requirements, inventory):
    """
    Deduct pantry stock from aggregated requirements.

    - Does not mutate the original inventory.
    - Does not consume pantry stock twice.
    - Uses existing normalized measurements.
    - Uses dataset-derived conversions when units differ.
    - Preserves estimated conversion uncertainty.
    """

    def pantry_match_key(item):
        name = _ingredient_name(item)
        return " ".join(name.lower().split())

    stock_map = {}

    # ========================================================
    # 1. NORMALIZE PANTRY STOCK
    # ========================================================

    for item in inventory or []:

        key = pantry_match_key(item)

        if not key:
            continue

        name = _ingredient_name(item)

        normalized = normalize_requirement_quantity(
            name,
            item.get("quantity"),
            item.get("unit"),
        )

        if normalized is None:
            continue

        stock_map.setdefault(key, []).append({
            "quantity": normalized["quantity"],
            "unit": normalized["unit"],
            "conversion_status": normalized["conversion_status"],
        })

    results = []

    # ========================================================
    # 2. SUBTRACT PANTRY FROM REQUIREMENTS
    # ========================================================

    for requirement in requirements or []:

        key = pantry_match_key(requirement)

        required = float(
            requirement.get("quantity", 0)
        )

        required_unit = requirement.get("unit")

        remaining = required
        inventory_used = 0.0
        inventory_unresolved = False
        estimated_inventory_conversion = False

        for stock in stock_map.get(key, []):

            if remaining <= 1e-9:
                break

            available = max(
                0.0,
                stock["quantity"],
            )

            if available <= 0:
                continue

            # =================================================
            # CASE 1: COMPATIBLE UNITS
            # =================================================

            if stock["unit"] == required_unit:

                consumed = min(
                    remaining,
                    available,
                )

                remaining -= consumed
                inventory_used += consumed

                stock["quantity"] = max(
                    0.0,
                    available - consumed,
                )

                # Stock normalized via an estimate (e.g. 1 bunch -> g)
                # keeps that uncertainty even when units now match.
                if (
                    consumed > 0
                    and stock.get("conversion_status") == "estimated"
                ):
                    estimated_inventory_conversion = True

                continue

            # =================================================
            # CASE 2: DATASET-DERIVED CONVERSION
            # =================================================

            conversion = convert_using_ingredient_factor(
                ingredient_name=key,
                quantity=available,
                from_unit=stock["unit"],
                to_unit=required_unit,
            )

            if conversion["quantity"] is None:

                inventory_unresolved = True
                continue

            available_in_required_unit = max(
                0.0,
                conversion["quantity"],
            )

            if available_in_required_unit <= 0:
                continue

            consumed = min(
                remaining,
                available_in_required_unit,
            )

            remaining -= consumed
            inventory_used += consumed

            # Convert consumed quantity back into pantry units.
            # This avoids consuming the same stock twice.
            consumed_in_stock_unit = (
                available
                * consumed
                / available_in_required_unit
            )

            stock["quantity"] = max(
                0.0,
                available - consumed_in_stock_unit,
            )

            estimated_inventory_conversion = True

        # =====================================================
        # 3. BUILD RESULT
        # =====================================================

        result = dict(requirement)

        result.update({
            "required_quantity": required,
            "inventory_available": inventory_used,
            "inventory_used": inventory_used,
            "purchase_required": max(
                0.0,
                remaining,
            ),
            "inventory_conversion_unresolved": (
                inventory_unresolved
            ),
            "inventory_conversion_estimated": (
                estimated_inventory_conversion
            ),
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
def collect_qualitative_requirements(recipe_requirements):
    """Preserve non-numeric ingredient instructions separately."""
    qualitative = []
    by_key = {}
    for recipe in recipe_requirements or []:
        recipe_id = recipe.get("recipe_id")
        for ingredient in recipe.get("ingredients", []):
            if not isinstance(ingredient, dict):
                continue
            kind, instruction = classify_requirement(ingredient)
            if kind != "qualitative":
                continue
            raw_quantity = ingredient.get("quantity")
            name = _ingredient_name(ingredient)
            key = (
                ingredient.get("ingredient_id"),
                name.lower(),
                instruction,
                recipe_id,
                recipe.get("slot_id"),
            )
            if key in by_key:
                # Same instruction repeated within one recipe.
                by_key[key]["occurrence_ids"].append(
                    _occurrence_id(ingredient)
                )
                continue
            entry = {
                "ingredient_id": ingredient.get("ingredient_id"),
                "ingredient_name": name,
                "requirement_type": "qualitative",
                "instruction": instruction,
                "quantity": raw_quantity,
                "unit": instruction,
                "recipe_id": recipe_id,
                "slot_id": recipe.get("slot_id"),
                "recipe_ids": [recipe_id] if recipe_id is not None else [],
                "occurrence_ids": [_occurrence_id(ingredient)],
            }
            by_key[key] = entry
            qualitative.append(entry)
    return qualitative
# Ingredient uncertainty policy for grocery projection.
#
#   exact / estimated measurable   priced normally; estimates never
#                                  verify quantity coverage
#   unresolved package conversion  one provisional package, priced,
#                                  never verified (non-blocking)
#   qualitative "to taste"         discretionary amount; recipe may be
#                                  selected conditionally, cost left
#                                  unpriced (non-blocking)
#   other qualitative instruction  ("as needed", ...) blocking
#   missing quantity or unit       essential amount unknown: blocking
#   no product / price / package   no cost evidence: blocking
DISCRETIONARY_INSTRUCTIONS = {"to taste"}


def classify_projection_gaps(basket_items):
    """Category and selection impact of every unpriced basket line."""
    gaps = []
    for item in basket_items:
        if item.get("effective_purchase_cost") is not None:
            continue
        basis = item.get("purchase_basis")
        if basis == "qualitative_requirement":
            discretionary = item.get("instruction") in DISCRETIONARY_INSTRUCTIONS
            category = (
                "qualitative_discretionary" if discretionary
                else "qualitative_unspecified"
            )
            blocks = not discretionary
        elif basis == "unresolved_requirement":
            category, blocks = "missing_quantity_or_unit", True
        elif item.get("pricing_status") == "unresolved_conversion":
            category = (
                "incompatible_unit_groups"
                if item.get("unresolved_units")
                else "unconvertible_unit_without_product"
            )
            blocks = True
        else:
            category, blocks = "missing_product_or_price", True
        gaps.append({
            "name": item.get("name"),
            "category": category,
            "blocks_selection": blocks,
        })
    return gaps


def build_plan_grocery_basket(
    recipe_requirements,
    inventory=None,
    product_catalog=None,
):
    """
    Build one grocery basket for the full meal plan.
    Backward-compatible input/output structure.
    Important:
    The current MultiMealPlanner passes a reduced
    product catalog without reliable price-source
    metadata. Such prices are treated as projections,
    not automatically verified retail costs.
    """
    import math
    inventory = inventory or []
    product_catalog = product_catalog or []
    qualitative_requirements = collect_qualitative_requirements(
        recipe_requirements
    )
    unresolved_quantity_requirements = (
        collect_unresolved_quantity_requirements(recipe_requirements)
    )
    # Ingredients that also need an amount nobody can quantify:
    # no purchase of theirs can be verified as sufficient.
    unquantified_keys = set().union(*(
        _identity_keys(requirement)
        for requirement in (
            qualitative_requirements + unresolved_quantity_requirements
        )
    ))
    aggregated = aggregate_requirements(
        recipe_requirements
    )
    purchase_requirements = subtract_inventory(
        aggregated,
        inventory,
    )
    unresolved_requirements = [
        requirement
        for requirement in purchase_requirements
        if (
            requirement.get("normalization_status")
            == "unresolved"
            or requirement.get(
                "conversion_status"
            ) == "unresolved"
        )
    ]
    basket_items = []
    known_cost = 0.0
    projected_cost = 0.0
    unpriced_items = []
    projection_missing = []
    warnings = []
    unit_aliases = {
        "tbsp": "tablespoon",
        "tbs": "tablespoon",
        "tablespoons": "tablespoon",
        "tsp": "teaspoon",
        "teaspoons": "teaspoon",
        "gram": "g",
        "grams": "g",
        "kilogram": "kg",
        "kilograms": "kg",
        "milliliter": "ml",
        "milliliters": "ml",
        "millilitre": "ml",
        "millilitres": "ml",
        "liter": "l",
        "liters": "l",
        "litre": "l",
        "litres": "l",
        "piece": "pcs",
        "pieces": "pcs",
        "count": "pcs",
        "heads": "head",
    }
    unit_info = {
        "tablespoon": ("volume", 15.0),
        "teaspoon": ("volume", 5.0),
        "g": ("mass", 1.0),
        "kg": ("mass", 1000.0),
        "ml": ("volume", 1.0),
        "l": ("volume", 1000.0),
        "pcs": ("count", 1.0),
        "head": ("head", 1.0),
        "clove": ("clove", 1.0),
        "stalk": ("stalk", 1.0),
        "sprig": ("sprig", 1.0),
    }
    def normalize_unit(value):
        text = str(value or "").strip().lower()
        if text in {"nan", "none", "null"}:
            return ""
        return unit_aliases.get(text, text)
    def positive_number(value):
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number <= 0:
            return None
        return number
    def convert_requirement(
        quantity,
        from_unit,
        to_unit,
    ):
        """
        Convert required quantity into package units.
        Returns None if no safe conversion exists.
        """
        from_unit = normalize_unit(from_unit)
        to_unit = normalize_unit(to_unit)
        if from_unit == to_unit and from_unit:
            return quantity
        source = unit_info.get(from_unit)
        target = unit_info.get(to_unit)
        if (
            source is None
            or target is None
            or source[0] != target[0]
        ):
            return None
        return (
            quantity * source[1] / target[1]
        )
    def estimate_package_conversion(
        quantity,
        from_unit,
        to_unit,
        ingredient_name,
    ):
        """Estimate package units through ingredient-specific mass data.
        This is a provisional fallback only. It must not be treated
        as exact retail quantity coverage.

        Uses the shared Ingredient KB lookup, so package sizing,
        pantry subtraction and Inventory State apply the same factors.
        Returns (quantity in package units, factor provenance) or
        (None, None) when no ingredient-specific evidence exists.
        """
        from_unit = normalize_unit(from_unit)
        to_unit = normalize_unit(to_unit)
        source_quantity, source_unit = (
            (quantity * 1000.0, "g") if from_unit == "kg"
            else (quantity, from_unit)
        )
        target_scale, target_unit = (
            (1000.0, "g") if to_unit == "kg"
            else (1.0, to_unit)
        )
        conversion = convert_using_ingredient_factor(
            ingredient_name=ingredient_name,
            quantity=source_quantity,
            from_unit=source_unit,
            to_unit=target_unit,
        )
        if (
            conversion["status"] == "estimated"
            and conversion["quantity"] is not None
        ):
            return (
                conversion["quantity"] / target_scale,
                conversion.get("factors"),
            )
        return None, None
    def implausible_package(quantity, unit, ingredient):
        """
        Conservative sanity checks for ordinary
        household grocery packages.
        These are heuristic checks, not product
        verification.
        """
        unit = normalize_unit(unit)
        if unit == "kg" and quantity > 25:
            return True
        if unit == "g" and quantity > 25000:
            return True
        if unit == "l" and quantity > 25:
            return True
        if unit == "ml" and quantity > 25000:
            return True
        return False
    for requirement in purchase_requirements:
        required = positive_number(
            requirement.get("purchase_required")
        )
        if required is None:
            continue
        ingredient_id = requirement.get(
            "ingredient_id"
        )
        ingredient_name = _ingredient_name(
            requirement
        )
        required_unit = normalize_unit(
            requirement.get("unit")
        )
        product = find_plan_product(
            requirement,
            product_catalog,
        )
        base_item = {
            "ingredient_id": ingredient_id,
            "name": ingredient_name,
            "required_quantity": required,
            "required_unit": required_unit,
            "package_quantity": None,
            "package_unit": None,
            "packages": None,
            "purchased_quantity": None,
            "price_per_package": None,
            "purchase_cost": None,
            "estimated_purchase_cost": None,
            "leftover_quantity": None,
            "inventory_used": requirement.get(
                "inventory_used", 0
            ),
            "recipe_ids": requirement.get(
                "recipe_ids", []
            ),
            "pricing_status": "unpriced",
            "purchase_basis": None,
            "quantity_coverage_verified": False,
            "price_source": "unknown",
            "conversion_status": requirement.get(
                "conversion_status", "exact"
            ),
            "volume_preserved_no_density": (requirement.get("conversion_status")== "volume_preserved_no_density"),
            "normalization_status": requirement.get(
                "normalization_status", "resolved"
            ),
            "inventory_conversion_unresolved": requirement.get(
                "inventory_conversion_unresolved", False
            ),
            "inventory_conversion_estimated": requirement.get(
                "inventory_conversion_estimated", False
            ),
            "additional_unquantified_requirement": bool(
                _identity_keys(requirement) & unquantified_keys
            ),
        }
        # Incompatible unit groups for one ingredient (e.g. thyme in
        # sprigs and in pinches) cannot be sized or priced as one line.
        # A single measurement in an unconvertible unit (pinch, count,
        # packet) is matched like any other unresolved package
        # conversion: one provisional package, never verified.
        # aggregate_requirements() marks every unresolved conversion as
        # normalization "unresolved"; only "unresolved_units" identifies
        # several incompatible unit groups for one ingredient.
        incompatible_groups = bool(requirement.get("unresolved_units"))
        base_item["unresolved_units"] = requirement.get("unresolved_units")
        unconvertible_unit = (
            requirement.get("conversion_status") == "unresolved"
        )
        if incompatible_groups or (unconvertible_unit and product is None):
            base_item["pricing_status"] = "unresolved_conversion"
            base_item["price_source"] = "unknown"
            unpriced_items.append(ingredient_name)
            projection_missing.append(ingredient_name)
            warnings.append(
                f"{ingredient_name}: unresolved quantity conversion. "
                "Purchase quantity cannot be verified."
            )
            basket_items.append(base_item)
            continue
        if product is None:
            unpriced_items.append(ingredient_name)
            projection_missing.append(ingredient_name)
            basket_items.append(base_item)
            continue
        package_quantity = positive_number(
            product.get("package_quantity")
        )
        package_unit = normalize_unit(
            product.get("package_unit")
        )
        price = positive_number(
            product.get("price")
            if product.get("price") is not None
            else product.get("price_per_package")
        )
        base_item["package_quantity"] = (
            package_quantity
        )
        base_item["package_unit"] = package_unit
        base_item["price_per_package"] = (
            round(price, 2)
            if price is not None
            else None
        )
        if price is None:
            unpriced_items.append(ingredient_name)
            projection_missing.append(ingredient_name)
            basket_items.append(base_item)
            continue
        if package_quantity is None:
            unpriced_items.append(ingredient_name)
            projection_missing.append(ingredient_name)
            base_item["pricing_status"] = "invalid_package"
            basket_items.append(base_item)
            continue
        if implausible_package(
            package_quantity,
            package_unit,
            ingredient_name,
        ):
            warnings.append(
                f"{ingredient_name}: implausible package "
                f"size {package_quantity} {package_unit}"
            )
            unpriced_items.append(ingredient_name)
            projection_missing.append(ingredient_name)
            base_item["pricing_status"] = (
                "implausible_package"
            )
            basket_items.append(base_item)
            continue
        # Preserve the existing strict plan-basket
        # contract for different unit strings.
        #
        # A separate provisional calculation can
        # still be added later without changing
        # pricing_status.
        converted_required = convert_requirement(
            required,
            required_unit,
            package_unit,
        )
        estimated_package_conversion = False
        package_conversion_factors = None
        if converted_required is None:
            (
                converted_required,
                package_conversion_factors,
            ) = estimate_package_conversion(
                required,
                required_unit,
                package_unit,
                ingredient_name,
            )
            estimated_package_conversion = (
                converted_required is not None
            )
        if converted_required is not None:
            packages = math.ceil(
                converted_required / package_quantity
            )
            packages = max(1, packages)
            purchased_quantity = (
                packages * package_quantity
            )
            leftover_quantity = max(
                0.0,
                purchased_quantity - converted_required,
            )
            conversion_is_exact = (
                requirement.get("conversion_status", "exact") == "exact"
            )
            normalization_resolved = (
                requirement.get("normalization_status", "resolved")
                == "resolved"
            )
            inventory_resolved = not requirement.get(
                "inventory_conversion_unresolved", False
            )
            # Pantry stock subtracted through an estimated conversion
            # makes the remaining purchase quantity an estimate too.
            inventory_exact = not requirement.get(
                "inventory_conversion_estimated", False
            )
            quantity_supported = (
                conversion_is_exact
                and not estimated_package_conversion
                and normalization_resolved
                and inventory_resolved
                and inventory_exact
                and not base_item["additional_unquantified_requirement"]
            )
            if estimated_package_conversion:
                warnings.append(
                    f"{ingredient_name}: estimated ingredient-specific "
                    "conversion used for package sizing; quantity "
                    "coverage is provisional."
                )
            is_llm_product = (
                product.get("purchase_basis") == "llm_estimated_package"
                or product.get("match_status") == "estimated_no_retail_match"
            )
            if quantity_supported:
                purchase_basis = "calculated_quantity"
            elif is_llm_product:
                purchase_basis = "minimum_retail_package"
            else:
                purchase_basis = "estimated_quantity"
        else:
            # No reliable conversion exists between the
            # required ingredient unit and retail package unit.
            #
            # One package is only a provisional shopping
            # suggestion, NOT proof of sufficient inventory.

            packages = 1

            # Quantity remains expressed in the package unit.
            # Inventory must not interpret this as recipe units.
            purchased_quantity = package_quantity

            # Leftover cannot be calculated without a
            # compatible unit conversion.
            leftover_quantity = None

            purchase_basis = "minimum_retail_package"

            # Explicitly mark coverage as unverified.
            quantity_supported = False
            warnings.append(
                f"{ingredient_name}: package coverage unresolved "
                f"(required {required} {required_unit}, "
                f"package {package_quantity} {package_unit}). "
                "One package is a provisional minimum purchase; "
                "inventory sufficiency is not verified."
            )
        estimated_purchase_cost = round(
            packages * price,
            2,
        )
        projected_cost += estimated_purchase_cost
        # Only count as known when explicit source
        # evidence is available in the catalog.
        #
        # The current planner strips that metadata,
        # so its reduced catalog normally remains
        # provisional.
        retail_total = positive_number(
            product.get("total_cost")
        )
        estimated_total = positive_number(
            product.get("estimated_total_cost")
        )
        source_basis = product.get("purchase_basis")
        source_status = product.get("match_status")
        is_llm = (
            source_basis == "llm_estimated_package"
            or source_status == "estimated_no_retail_match"
        )
        has_estimated_quantity = (
            product.get("quantity_estimated") is True
            or source_basis == "estimated_quantity"
            or source_status == "matched_estimated_quantity"
        )
        has_estimated_source = (
            estimated_total is not None
            and retail_total is None
        )
        has_retail_evidence = (
            price is not None
            and not is_llm
            and not has_estimated_quantity
            and not has_estimated_source
        )
        conversion_is_exact = (
            requirement.get("conversion_status", "exact") == "exact"
        )
        normalization_resolved = (
            requirement.get("normalization_status", "resolved")
            == "resolved"
        )
        inventory_resolved = not requirement.get(
            "inventory_conversion_unresolved", False
        )
        inventory_exact = not requirement.get(
            "inventory_conversion_estimated", False
        )
        if (
            has_retail_evidence
            and quantity_supported
            and conversion_is_exact
            and normalization_resolved
            and inventory_resolved
            and inventory_exact
            and not base_item["additional_unquantified_requirement"]
        ):
            known_cost += estimated_purchase_cost
            base_item["purchase_cost"] = (
                estimated_purchase_cost
            )
            base_item["pricing_status"] = "priced"
            base_item["price_source"] = "retail"
        else:
            base_item["estimated_purchase_cost"] = (
                estimated_purchase_cost
            )
            base_item["pricing_status"] = "estimated"
            base_item["price_source"] = (
                "ollama_estimate"
                if is_llm
                else (
                    "retail_estimated_quantity"
                    if (
                        has_estimated_quantity
                        or not conversion_is_exact
                    )
                    else "unverified"
                )
            )

        # Accepted cost for meal planning and budgeting.
        # Includes both Tavily and Ollama prices.
        base_item["planning_purchase_cost"] = (
            estimated_purchase_cost

        )
        base_item.update({
            "packages": packages,
            "purchased_quantity": purchased_quantity,
            "leftover_quantity": leftover_quantity,
            "purchase_basis": purchase_basis,
            "package_conversion_status": (
                "estimated"
                if estimated_package_conversion
                else (
                    "exact"
                    if converted_required is not None
                    else "unresolved"
                )
            ),
            # Grams-per-unit and source of each estimated factor.
            "package_conversion_factors": package_conversion_factors,
            "quantity_coverage_verified": (
                quantity_supported
            ),
        })
        # Usable purchase cost for shopping and planning.
        # This includes verified retailer costs and
        # provisional Tavily/Ollama estimates.
        #
        # Keep purchase_cost as verified-only.
        effective_cost = (
            base_item.get("purchase_cost")
        )
        if effective_cost is None:
            effective_cost = base_item.get(
                "estimated_purchase_cost"
            )
        base_item["effective_purchase_cost"] = (
            round(float(effective_cost), 2)
            if effective_cost is not None
            else None
        )
        base_item["display_cost"] = base_item.get(
        "effective_purchase_cost"
        )
        base_item["has_usable_price"] = (
            base_item["display_cost"] is not None
        )
        base_item["cost_is_estimated"] = (
            base_item.get("pricing_status") != "priced"
        )
        basket_items.append(base_item)
    existing_ids = {
        str(item["ingredient_id"]).strip()
        for item in basket_items if item.get("ingredient_id")
    }
    existing_names = {
        str(item.get("name") or "").strip().lower()
        for item in basket_items
    }

    # Unresolved-quantity requirements (e.g. no unit in the KB) stay
    # visible: no package count, price or shortage is invented, and
    # the missing cost keeps the projection incomplete.
    for requirement in unresolved_quantity_requirements:
        ingredient_id = requirement.get("ingredient_id")
        ingredient_name = str(
            requirement.get("ingredient_name") or ""
        ).strip()
        display_name = ingredient_name or "unidentified ingredient"
        existing = next(
            (
                item for item in basket_items
                if (
                    ingredient_id
                    and str(item.get("ingredient_id") or "").strip()
                    == str(ingredient_id).strip()
                )
                or (
                    ingredient_name
                    and str(item.get("name") or "").strip().lower()
                    == ingredient_name.lower()
                )
            ),
            None,
        )
        if existing is not None:
            # A measurable line already exists for this ingredient;
            # keep one line and record the unquantified need on it.
            existing["unresolved_quantity_sources"] = (
                requirement["source_requirements"]
            )
            continue

        basket_items.append({
            "ingredient_id": ingredient_id,
            "name": display_name,
            "required_quantity": None,
            "required_unit": None,
            "original_measurements": [
                {
                    "recipe_id": source["recipe_id"],
                    "occurrence_id": source["occurrence_id"],
                    "quantity": source["quantity"],
                    "unit": source["unit"],
                }
                for source in requirement["source_requirements"]
            ],
            "unresolved_reasons": requirement["reasons"],
            "occurrence_ids": requirement["occurrence_ids"],
            "package_quantity": None,
            "package_unit": None,
            "packages": None,
            "purchased_quantity": None,
            "price_per_package": None,
            "purchase_cost": None,
            "estimated_purchase_cost": None,
            "effective_purchase_cost": None,
            "display_cost": None,
            "has_usable_price": False,
            "cost_is_estimated": False,
            "leftover_quantity": None,
            "inventory_used": None,
            "recipe_ids": requirement["recipe_ids"],
            "pricing_status": "unresolved_quantity",
            "price_source": "unknown",
            "purchase_basis": "unresolved_requirement",
            "conversion_status": "unresolved",
            "package_conversion_status": None,
            "quantity_coverage_verified": False,
            "status": "quantity_unknown",
        })
        if ingredient_id:
            existing_ids.add(str(ingredient_id).strip())
        existing_names.add(display_name.lower())
        projection_missing.append(display_name)
        warnings.append(
            f"{display_name}: recipe quantity or unit unresolved "
            f"({', '.join(requirement['reasons'])}); included in the "
            "shopping list without a package or cost estimate."
        )

    # Add qualitative requirements as shopping-list entries without inventing quantities.

    for requirement in qualitative_requirements:
        ingredient_id = requirement.get("ingredient_id")
        ingredient_name = str(requirement.get("ingredient_name") or "").strip()
        if not ingredient_name:
            continue
        if (ingredient_id and str(ingredient_id).strip() in existing_ids) or (
            ingredient_name.lower() in existing_names
        ):
            continue

        basket_items.append({
            "ingredient_id": ingredient_id,
            "name": ingredient_name,
            "required_quantity": None,
            "required_unit": requirement.get("unit") or "unknown",
            "instruction": requirement.get("instruction"),
            "package_quantity": None,
            "package_unit": None,
            "packages": None,
            "purchased_quantity": None,
            "price_per_package": None,
            "purchase_cost": None,
            "estimated_purchase_cost": None,
            "effective_purchase_cost": None,
            "display_cost": None,
            "has_usable_price": False,
            "cost_is_estimated": False,
            "leftover_quantity": None,
            "inventory_used": 0.0,
            "recipe_ids": requirement.get("recipe_ids", []),
            "pricing_status": "unpriced",
            "price_source": "unknown",
            "purchase_basis": "qualitative_requirement",
            "quantity_coverage_verified": False,
            "status": "quantity_unknown",
        })
        if ingredient_id:
            existing_ids.add(str(ingredient_id).strip())
        existing_names.add(ingredient_name.lower())
        projection_missing.append(ingredient_name)
        warnings.append(
            f"{ingredient_name}: quantity unknown; included in shopping list without a cost estimate."
        )

    unpriced_items = list(
        dict.fromkeys(
            item.get("name")
            for item in basket_items
            if item.get("effective_purchase_cost") is None
        )
    )
    projection_gaps = classify_projection_gaps(basket_items)
    projection_missing = list(
        dict.fromkeys(projection_missing)
    )
    projection_complete = (
        len(projection_missing) == 0
    )
    all_items_have_usable_cost = (
        len(projection_missing) == 0
        and all(
            item.get("effective_purchase_cost") is not None
            for item in basket_items
        )
    )
    return {
        "items": basket_items,
        "known_cost": round(known_cost, 2),
        "unresolved_requirements": unresolved_requirements,
        # Lines without a cost, each with its policy category and
        # whether it blocks recipe selection (see
        # classify_projection_gaps). projected_cost stays None while
        # any gap exists; priced_subtotal is only a lower bound.
        "projection_gaps": projection_gaps,
        "selection_blocking_items": [
            gap["name"] for gap in projection_gaps if gap["blocks_selection"]
        ],
        "discretionary_unpriced_items": [
            gap["name"] for gap in projection_gaps if not gap["blocks_selection"]
        ],
        "selection_projection_complete": not any(
            gap["blocks_selection"] for gap in projection_gaps
        ),
        "priced_subtotal": round(projected_cost, 2),
        # Recipe requirements with no determinable quantity or unit.
        # Reported separately from unresolved package conversions.
        "unresolved_quantity_requirements": (
            unresolved_quantity_requirements
        ),
        "unresolved_quantity_count": len(
            unresolved_quantity_requirements
        ),
        "all_items_priced": all(
            item.get("pricing_status") == "priced"
            for item in basket_items
        ),
        "all_items_have_usable_cost": all(
            item.get("effective_purchase_cost") is not None
            for item in basket_items
        ),
        "qualitative_requirements": qualitative_requirements,
        "unpriced_items": unpriced_items,
        "aggregated_requirements": aggregated,
        "purchase_requirements": purchase_requirements,
        "projected_cost": (
            round(projected_cost, 2)
            if projection_complete
            else None
        ),
        "projected_cost_complete": (
            projection_complete
        ),
        "projection_missing": projection_missing,
        "warnings": warnings,
                "all_items_have_usable_cost": (
            all_items_have_usable_cost
        ),
          "planning_cost": (
            round(projected_cost, 2)
            if projection_complete
            else None
        ),
        "planning_cost_complete": projection_complete,
    }

def calculate_incremental_basket_cost(
    selected_recipe_requirements,
    candidate_recipe_requirement,
    inventory=None,
    product_catalog=None,
):
    """
    Calculate the additional grocery purchase cost
    caused by adding one candidate recipe.
    Both baskets use the SAME original inventory
    and product catalog.
    Verified and estimated costs remain separate.
    """
    import math
    selected = list(selected_recipe_requirements or [])
    if not isinstance(candidate_recipe_requirement, dict):
        raise TypeError(
            "candidate_recipe_requirement must be a dictionary"
        )
    if not isinstance(
        candidate_recipe_requirement.get("ingredients", []),
        list,
    ):
        raise ValueError(
            "Candidate ingredients must be a list"
        )
    # Use the same initial inventory for both calculations.
    inventory = inventory if inventory is not None else []
    product_catalog = (
        product_catalog if product_catalog is not None else []
    )
    # Basket before adding the candidate.
    before = build_plan_grocery_basket(
        recipe_requirements=selected,
        inventory=inventory,
        product_catalog=product_catalog,
    )
    # Basket after adding the candidate.
    after = build_plan_grocery_basket(
        recipe_requirements=(
            selected + [candidate_recipe_requirement]
        ),
        inventory=inventory,
        product_catalog=product_catalog,
    )
    def valid_cost(value):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(number) or number < 0:
            return None
        return number
    before_known = valid_cost(before.get("known_cost"))
    after_known = valid_cost(after.get("known_cost"))
    if before_known is None or after_known is None:
        raise ValueError("Invalid known basket cost")
    # Known retail cost difference.
    known_increment = round(
        after_known - before_known, 2
    )
    # Negative increments indicate inconsistent pricing,
    # product selection, or source classification.
    if known_increment < -0.01:
        raise ValueError(
            "Known basket cost decreased after adding "
            "a recipe. Check product catalog consistency."
        )
    known_increment = max(0.0, known_increment)
    before_complete = (
        before.get("projected_cost_complete") is True
    )
    after_complete = (
        after.get("projected_cost_complete") is True
    )
    projection_complete = (
        before_complete and after_complete
    )
    projected_increment = None
    if projection_complete:
        before_projected = valid_cost(
            before.get("projected_cost")
        )
        after_projected = valid_cost(
            after.get("projected_cost")
        )
        if (
            before_projected is None
            or after_projected is None
        ):
            projection_complete = False
        else:
            difference = round(
                after_projected - before_projected, 2
            )
            if difference < -0.01:
                raise ValueError(
                    "Projected basket cost decreased after "
                    "adding a recipe. Check pricing consistency."
                )
            projected_increment = max(
                0.0, difference
            )
    # Identify products that require additional packages.
    before_items = {
        (
            item.get("ingredient_id")
            or item.get("name", "").strip().lower()
        ): item
        for item in before.get("items", [])
    }
    additional_items = []
    for item in after.get("items", []):
        key = (
            item.get("ingredient_id")
            or item.get("name", "").strip().lower()
        )
        previous = before_items.get(key, {})
        old_packages = previous.get("packages")
        new_packages = item.get("packages")
        additional_packages = None
        if (
            isinstance(old_packages, int)
            and isinstance(new_packages, int)
        ):
            additional_packages = (
                new_packages - old_packages
            )
        elif (
            not previous
            and isinstance(new_packages, int)
        ):
            additional_packages = new_packages
        additional_items.append({
            "ingredient_id": item.get("ingredient_id"),
            "name": item.get("name"),
            "previous_packages": old_packages,
            "new_packages": new_packages,
            "additional_packages": additional_packages,
            "price_per_package": item.get(
                "price_per_package"
            ),
            "pricing_status": item.get(
                "pricing_status"
            ),
        })
    return {
        "known_incremental_cost": known_increment,
        "projected_incremental_cost": projected_increment,
        "projected_cost_complete": projection_complete,
        "before_known_cost": round(before_known, 2),
        "after_known_cost": round(after_known, 2),
        "before_projected_cost": (
            before.get("projected_cost")
        ),
        "after_projected_cost": (
            after.get("projected_cost")
        ),
        "before_basket": before,
        "after_basket": after,
        "additional_items": additional_items,
        "projection_missing": list(
            after.get("projection_missing", [])
        ),
    }
def build_cost_summary(
    grocery_basket,
    initial_budget,
):
    """
    Summarize verified and projected grocery spending.
    Known cost:
        Cost supported by verified retail pricing rules.
    Projected cost:
        Complete grocery estimate, including Tavily
        and Ollama prices and provisional quantities.
    Both Tavily and Ollama prices count equally toward
    projected grocery spending.
    A complete projection is not necessarily verified.
    """
    import math
    def valid_money(value, field_name):
        if isinstance(value, bool):
            raise ValueError(
                f"{field_name} must be numeric"
            )
        try:
            number = float(value)
        except (
            TypeError,
            ValueError,
            OverflowError,
        ):
            raise ValueError(
                f"{field_name} must be numeric"
            ) from None
        if not math.isfinite(number) or number < 0:
            raise ValueError(
                f"{field_name} must be finite and nonnegative"
            )
        return round(number, 2)
    if not isinstance(grocery_basket, dict):
        raise TypeError(
            "grocery_basket must be a dictionary"
        )
    initial_budget = valid_money(
        initial_budget,
        "initial_budget",
    )
    known_cost = valid_money(
        grocery_basket.get("known_cost", 0),
        "known_cost",
    )
    projection_complete = (
        grocery_basket.get(
            "projected_cost_complete"
        ) is True
    )
    raw_projected = grocery_basket.get(
        "projected_cost"
    )
    projected_cost = None
    if (
        projection_complete
        and raw_projected is not None
    ):
        projected_cost = valid_money(
            raw_projected,
            "projected_cost",
        )
        if projected_cost + 0.01 < known_cost:
            raise ValueError(
                "Projected cost cannot be below known cost"
            )
    else:
        projection_complete = False
    known_remaining = round(
        initial_budget - known_cost,
        2,
    )
    projected_remaining = (
        round(
            initial_budget - projected_cost,
            2,
        )
        if projected_cost is not None
        else None
    )
    unpriced_items = list(
        grocery_basket.get(
            "unpriced_items", []
        ) or []
    )
    projection_missing = list(
        grocery_basket.get(
            "projection_missing", []
        ) or []
    )
    estimated_component = (
        round(
            projected_cost - known_cost,
            2,
        )
        if projected_cost is not None
        else None
    )
    # Preserve the existing verified-price contract.
    # Do not infer verification merely because every
    # ingredient has a usable projected price.
    all_items_priced = (
        grocery_basket.get(
            "all_items_priced"
        ) is True
    )
    # Tavily and Ollama estimates are both accepted
    # as usable planning costs when the complete
    # projected grocery basket is available.
    all_items_have_usable_cost = (
        grocery_basket.get(
            "all_items_have_usable_cost"
        ) is True
        or projection_complete
    )
    # Verified means all items have verified pricing.
    # Provisional means a complete projected cost exists,
    # but one or more prices or quantities are estimated.
    # Incomplete means no complete cost is available.
    if (
        all_items_priced
        and projection_complete
        and projected_cost is not None
    ):
        budget_verification = "verified"
    elif (
        projection_complete
        and projected_cost is not None
    ):
        budget_verification = "provisional"
    else:
        budget_verification = "incomplete"
    return {
        "initial_budget": initial_budget,
        "known_grocery_cost": known_cost,
        "remaining": known_remaining,
        "all_items_priced": all_items_priced,
        "all_items_have_usable_cost": (
            all_items_have_usable_cost
        ),
        "unpriced_items": unpriced_items,
        "projected_grocery_cost": projected_cost,
        "projected_cost_complete": (
            projection_complete
        ),
        "estimated_cost_component": (
            estimated_component
        ),
        "known_remaining_budget": (
            known_remaining
        ),
        "projected_remaining_budget": (
            projected_remaining
        ),
        "projection_missing": (
            projection_missing
        ),
        "known_cost_within_budget": (
            known_cost <= initial_budget
        ),
        "projected_cost_within_budget": (
            projected_cost <= initial_budget
            if projected_cost is not None
            else None
        ),
        "budget_verification": (
            budget_verification
        ),
    }
