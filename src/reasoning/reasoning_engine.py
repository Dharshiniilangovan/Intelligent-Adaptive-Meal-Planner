"""
Central Reasoning Engine

This module DOES NOT implement domain-specific reasoning.

Domain reasoning is owned by:

    dietary_requirements.py
        - diet
        - allergy
        - preference

    feasibility.py
        - cooking time
        - ingredient feasibility
        - pantry utilization

    budget_service.py
        - budget feasibility
        - unknown grocery costs

The engine integrates their outputs and produces the
final decision for one candidate recipe.

Possible final states:

    feasible
    rejected
    uncertain
"""


# ============================================================
# DIETARY / ALLERGY / PREFERENCE ADAPTER
# ============================================================

def adapt_dietary_result(
    dietary_result: dict
) -> dict:

    hard_results = []
    soft_results = []

    # --------------------------------------------------------
    # DIET
    # --------------------------------------------------------

    diet = dietary_result.get(
        "diet",
        {}
    )

    if diet:

        hard_results.append({
            "constraint": "diet",
            "source": "dietary_requirements",
            "status": (
                "pass"
                if diet.get("passed") is True
                else "fail"
            ),
            "reason": diet.get(
                "reason",
                "Dietary result unavailable"
            )
        })

    # --------------------------------------------------------
    # ALLERGY
    # --------------------------------------------------------

    allergy = dietary_result.get(
        "allergy",
        {}
    )

    if allergy:

        allergy_status = allergy.get(
            "status"
        )

        if allergy.get("passed") is True:

            normalized_status = "pass"

        elif allergy_status == "unknown":

            normalized_status = "unknown"

        else:

            normalized_status = "fail"

        hard_results.append({
            "constraint": "allergy",
            "source": "dietary_requirements",
            "status": normalized_status,
            "reason": allergy.get(
                "reason",
                "Allergy result unavailable"
            )
        })

    # --------------------------------------------------------
    # PREFERENCE SCORE
    # --------------------------------------------------------

    preference = dietary_result.get(
        "preference",
        {}
    )

    preference_score = preference.get(
        "score"
    )

    if preference_score is not None:

        soft_results.append({
            "constraint": "preference",
            "source": "dietary_requirements",
            "score": float(
                preference_score
            ),
            "reason": preference.get(
                "reason",
                "Preference score calculated"
            )
        })

    return {
        "hard": hard_results,
        "soft": soft_results
    }


# ============================================================
# FEASIBILITY / PANTRY ADAPTER
# ============================================================

def adapt_feasibility_result(
    feasibility_result: dict
) -> dict:

    hard_results = []
    soft_results = []

    # --------------------------------------------------------
    # COOKING TIME
    # --------------------------------------------------------

    time_result = feasibility_result.get(
        "time_constraint",
        {}
    )

    if time_result:

        time_status = time_result.get(
            "status",
            "unknown"
        )

        if time_status not in {
            "pass",
            "fail",
            "unknown"
        }:
            time_status = "unknown"

        hard_results.append({
            "constraint": "cooking_time",
            "source": "feasibility",
            "status": time_status,
            "reason": time_result.get(
                "reason",
                "Cooking-time result unavailable"
            )
        })

    # --------------------------------------------------------
    # INGREDIENT FEASIBILITY
    # --------------------------------------------------------

    ingredient_result = (
        feasibility_result.get(
            "ingredient_feasibility",
            {}
        )
    )

    if ingredient_result:

        ingredient_status = (
            ingredient_result.get(
                "status",
                "unknown"
            )
        )

        if ingredient_status not in {
            "pass",
            "fail",
            "unknown"
        }:
            ingredient_status = "unknown"

        hard_results.append({
            "constraint":
                "ingredient_feasibility",

            "source":
                "feasibility",

            "status":
                ingredient_status,

            "reason":
                ingredient_result.get(
                    "reason",
                    (
                        "Ingredient feasibility "
                        "result unavailable"
                    )
                )
        })

    # --------------------------------------------------------
    # PANTRY UTILIZATION
    # --------------------------------------------------------

    pantry_score = (
        feasibility_result.get(
            "pantry_utilization"
        )
    )

    if pantry_score is not None:

        pantry_score = max(
            0.0,
            min(
                1.0,
                float(pantry_score)
            )
        )

        soft_results.append({
            "constraint":
                "pantry_utilization",

            "source":
                "feasibility",

            "score":
                pantry_score,

            "reason":
                (
                    "Pantry utilization score "
                    "calculated from available "
                    "ingredients"
                )
        })

    return {
        "hard": hard_results,
        "soft": soft_results
    }


# ============================================================
# BUDGET ADAPTER
# ============================================================

def adapt_budget_result(
    budget_result: dict
) -> dict:

    hard_results = []

    budget_status = budget_result.get(
        "budget_status"
    )

    if budget_status == "pass":

        normalized_status = "pass"

    elif budget_status == "hard_fail":

        normalized_status = "fail"

    else:

        # Member 4 currently returns:
        # "uncertain"
        normalized_status = "unknown"

    hard_results.append({
        "constraint": "budget",
        "source": "budget_service",
        "status": normalized_status,
        "reason": budget_result.get(
            "reason",
            "Budget result unavailable"
        ),
        "known_purchase_cost":
            budget_result.get(
                "known_purchase_cost"
            ),
        "remaining_budget":
            budget_result.get(
                "remaining_budget"
            )
    })

    return {
        "hard": hard_results,
        "soft": []
    }


# ============================================================
# COMBINE ALL REPORTS
# ============================================================

def combine_reports(
    dietary_result: dict,
    feasibility_result: dict,
    budget_result: dict
) -> dict:

    dietary = adapt_dietary_result(
        dietary_result
    )

    feasibility = (
        adapt_feasibility_result(
            feasibility_result
        )
    )

    budget = adapt_budget_result(
        budget_result
    )

    hard_results = (
        dietary["hard"]
        + feasibility["hard"]
        + budget["hard"]
    )

    soft_results = (
        dietary["soft"]
        + feasibility["soft"]
        + budget["soft"]
    )

    return {
        "hard": hard_results,
        "soft": soft_results
    }


# ============================================================
# HARD CONSTRAINT EVALUATION
# ============================================================

def evaluate_hard_constraints(
    hard_results: list
) -> dict:

    failures = [
        result
        for result in hard_results
        if result["status"] == "fail"
    ]

    unknowns = [
        result
        for result in hard_results
        if result["status"] == "unknown"
    ]

    # --------------------------------------------------------
    # FAIL takes priority
    # --------------------------------------------------------

    if failures:

        return {
            "status": "rejected",
            "passed": False,
            "failures": failures,
            "unknowns": unknowns
        }

    # --------------------------------------------------------
    # No failures, but missing/uncertain information
    # --------------------------------------------------------

    if unknowns:

        return {
            "status": "uncertain",
            "passed": False,
            "failures": [],
            "unknowns": unknowns
        }

    # --------------------------------------------------------
    # Everything passed
    # --------------------------------------------------------

    return {
        "status": "passed",
        "passed": True,
        "failures": [],
        "unknowns": []
    }


# ============================================================
# SOFT CONSTRAINT EVALUATION
# ============================================================

def evaluate_soft_constraints(
    soft_results: list
) -> dict:

    if not soft_results:

        return {
            "overall_score": None,
            "scores": []
        }

    scores = [
        result["score"]
        for result in soft_results
    ]

    # MVP baseline:
    # equal weighting.
    #
    # This can later be replaced with
    # empirically justified weights.
    overall_score = (
        sum(scores)
        / len(scores)
    )

    return {
        "overall_score": round(
            overall_score,
            4
        ),
        "scores": soft_results
    }


# ============================================================
# MAIN ENGINE
# ============================================================

def evaluate_candidate(
    recipe_id: str,
    dietary_result: dict,
    feasibility_result: dict,
    budget_result: dict
) -> dict:

    # --------------------------------------------------------
    # 1. Normalize/combine all member reports
    # --------------------------------------------------------

    reports = combine_reports(
        dietary_result=dietary_result,
        feasibility_result=feasibility_result,
        budget_result=budget_result
    )

    # --------------------------------------------------------
    # 2. Evaluate all hard constraints
    # --------------------------------------------------------

    hard_evaluation = (
        evaluate_hard_constraints(
            reports["hard"]
        )
    )

    # --------------------------------------------------------
    # 3. HARD FAIL -> REJECT
    # --------------------------------------------------------

    if (
        hard_evaluation["status"]
        == "rejected"
    ):

        return {
            "recipe_id": recipe_id,
            "status": "rejected",
            "feasible": False,

            "hard_constraints":
                reports["hard"],

            "failed_constraints":
                hard_evaluation[
                    "failures"
                ],

            "unknown_constraints":
                hard_evaluation[
                    "unknowns"
                ],

            "soft_constraints": None,

            "overall_score": None
        }

    # --------------------------------------------------------
    # 4. UNKNOWN -> UNCERTAIN
    # --------------------------------------------------------

    if (
        hard_evaluation["status"]
        == "uncertain"
    ):

        return {
            "recipe_id": recipe_id,
            "status": "uncertain",
            "feasible": False,

            "hard_constraints":
                reports["hard"],

            "failed_constraints": [],

            "unknown_constraints":
                hard_evaluation[
                    "unknowns"
                ],

            "soft_constraints": None,

            "overall_score": None
        }

    # --------------------------------------------------------
    # 5. All hard constraints passed
    #    -> evaluate soft constraints
    # --------------------------------------------------------

    soft_evaluation = (
        evaluate_soft_constraints(
            reports["soft"]
        )
    )

    return {
        "recipe_id": recipe_id,
        "status": "feasible",
        "feasible": True,

        "hard_constraints":
            reports["hard"],

        "failed_constraints": [],

        "unknown_constraints": [],

        "soft_constraints":
            soft_evaluation[
                "scores"
            ],

        "overall_score":
            soft_evaluation[
                "overall_score"
            ]
    }