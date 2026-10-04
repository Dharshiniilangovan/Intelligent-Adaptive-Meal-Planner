import pytest

from src.reasoning.reasoning_engine import (
    evaluate_candidate
)


# ============================================================
# MOCK MEMBER OUTPUTS
# ============================================================

def dietary_pass(
    preference_score=0.8
):

    return {
        "recipe_id": "R001",

        "hard_constraints_passed": True,

        "diet": {
            "constraint": "diet",
            "passed": True,
            "reason":
                "Recipe satisfies dietary requirements"
        },

        "allergy": {
            "constraint": "allergy",
            "passed": True,
            "status": "safe",
            "reason":
                "Recipe satisfies allergy requirements"
        },

        "preference": {
            "score_type": "preference",
            "score": preference_score,
            "reason":
                "Preferred cuisine matched"
        }
    }


def feasibility_pass(
    pantry_score=0.6
):

    return {
        "recipe_id": "R001",

        "time_constraint": {
            "status": "pass",
            "passed": True,
            "reason":
                "Cooking time is within limit"
        },

        "ingredient_feasibility": {
            "status": "pass",
            "passed": True,
            "reason":
                "Ingredient information is usable"
        },

        "pantry_utilization":
            pantry_score,

        "already_available": [],

        "missing_ingredients": []
    }


def budget_pass():

    return {
        "budget_status": "pass",

        "known_purchase_cost": 20.0,

        "remaining_budget": 50.0,

        "budget_after_purchase": 30.0,

        "reason":
            "Purchase cost is within remaining budget"
    }


# ============================================================
# 1. EVERYTHING PASSES
# ============================================================

def test_candidate_is_feasible_when_all_hard_constraints_pass():

    result = evaluate_candidate(
        recipe_id="R001",

        dietary_result=
            dietary_pass(),

        feasibility_result=
            feasibility_pass(),

        budget_result=
            budget_pass()
    )

    assert (
        result["status"]
        == "feasible"
    )

    assert result["feasible"] is True

    assert (
        result["failed_constraints"]
        == []
    )

    assert (
        result["unknown_constraints"]
        == []
    )

    assert (
        result["overall_score"]
        is not None
    )


# ============================================================
# 2. DIET FAILURE -> REJECT
# ============================================================

def test_diet_failure_rejects_candidate():

    dietary = dietary_pass()

    dietary["diet"] = {
        "constraint": "diet",
        "passed": False,
        "reason":
            "Recipe does not satisfy vegetarian requirement"
    }

    result = evaluate_candidate(
        recipe_id="R001",
        dietary_result=dietary,
        feasibility_result=
            feasibility_pass(),
        budget_result=
            budget_pass()
    )

    assert (
        result["status"]
        == "rejected"
    )

    assert result["feasible"] is False

    assert any(
        failure["constraint"]
        == "diet"

        for failure
        in result[
            "failed_constraints"
        ]
    )


# ============================================================
# 3. ALLERGY FAILURE -> REJECT
# ============================================================

def test_allergy_failure_rejects_candidate():

    dietary = dietary_pass()

    dietary["allergy"] = {
        "constraint": "allergy",
        "passed": False,
        "status": "conflict",
        "reason":
            "Recipe contains peanut"
    }

    result = evaluate_candidate(
        recipe_id="R001",
        dietary_result=dietary,
        feasibility_result=
            feasibility_pass(),
        budget_result=
            budget_pass()
    )

    assert (
        result["status"]
        == "rejected"
    )

    assert any(
        failure["constraint"]
        == "allergy"

        for failure
        in result[
            "failed_constraints"
        ]
    )


# ============================================================
# 4. UNKNOWN ALLERGY -> UNCERTAIN
# ============================================================

def test_unknown_allergy_returns_uncertain():

    dietary = dietary_pass()

    dietary["allergy"] = {
        "constraint": "allergy",
        "passed": False,
        "status": "unknown",
        "reason":
            "Allergy safety could not be verified"
    }

    result = evaluate_candidate(
        recipe_id="R001",
        dietary_result=dietary,
        feasibility_result=
            feasibility_pass(),
        budget_result=
            budget_pass()
    )

    assert (
        result["status"]
        == "uncertain"
    )

    assert result["feasible"] is False

    assert any(
        unknown["constraint"]
        == "allergy"

        for unknown
        in result[
            "unknown_constraints"
        ]
    )


# ============================================================
# 5. COOKING TIME FAILURE -> REJECT
# ============================================================

def test_cooking_time_failure_rejects_candidate():

    feasibility = (
        feasibility_pass()
    )

    feasibility[
        "time_constraint"
    ] = {
        "status": "fail",
        "passed": False,
        "reason":
            "Recipe exceeds cooking-time limit"
    }

    result = evaluate_candidate(
        recipe_id="R001",
        dietary_result=
            dietary_pass(),
        feasibility_result=
            feasibility,
        budget_result=
            budget_pass()
    )

    assert (
        result["status"]
        == "rejected"
    )

    assert any(
        failure["constraint"]
        == "cooking_time"

        for failure
        in result[
            "failed_constraints"
        ]
    )


# ============================================================
# 6. UNKNOWN COOKING TIME -> UNCERTAIN
# ============================================================

def test_unknown_cooking_time_returns_uncertain():

    feasibility = (
        feasibility_pass()
    )

    feasibility[
        "time_constraint"
    ] = {
        "status": "unknown",
        "passed": None,
        "reason":
            "Cooking time unavailable"
    }

    result = evaluate_candidate(
        recipe_id="R001",
        dietary_result=
            dietary_pass(),
        feasibility_result=
            feasibility,
        budget_result=
            budget_pass()
    )

    assert (
        result["status"]
        == "uncertain"
    )


# ============================================================
# 7. BUDGET HARD FAIL -> REJECT
# ============================================================

def test_budget_failure_rejects_candidate():

    budget = {
        "budget_status":
            "hard_fail",

        "known_purchase_cost":
            60.0,

        "remaining_budget":
            50.0,

        "budget_after_purchase":
            None,

        "reason":
            "Known purchase cost exceeds remaining budget"
    }

    result = evaluate_candidate(
        recipe_id="R001",
        dietary_result=
            dietary_pass(),
        feasibility_result=
            feasibility_pass(),
        budget_result=
            budget
    )

    assert (
        result["status"]
        == "rejected"
    )

    assert any(
        failure["constraint"]
        == "budget"

        for failure
        in result[
            "failed_constraints"
        ]
    )


# ============================================================
# 8. UNKNOWN PRICE -> UNCERTAIN
# ============================================================

def test_uncertain_budget_returns_uncertain():

    budget = {
        "budget_status":
            "uncertain",

        "known_purchase_cost":
            20.0,

        "remaining_budget":
            50.0,

        "budget_after_purchase":
            None,

        "reason":
            "One or more grocery costs are unknown"
    }

    result = evaluate_candidate(
        recipe_id="R001",
        dietary_result=
            dietary_pass(),
        feasibility_result=
            feasibility_pass(),
        budget_result=
            budget
    )

    assert (
        result["status"]
        == "uncertain"
    )

    assert any(
        unknown["constraint"]
        == "budget"

        for unknown
        in result[
            "unknown_constraints"
        ]
    )


# ============================================================
# 9. SOFT SCORES ARE COMBINED
# ============================================================

def test_soft_scores_are_combined():

    result = evaluate_candidate(
        recipe_id="R001",

        dietary_result=
            dietary_pass(
                preference_score=0.8
            ),

        feasibility_result=
            feasibility_pass(
                pantry_score=0.6
            ),

        budget_result=
            budget_pass()
    )

    # Current soft scores:
    #
    # preference = 0.8
    # pantry     = 0.6
    #
    # average = 0.7

    assert result[
        "overall_score"
    ] == pytest.approx(
        0.7
    )


# ============================================================
# 10. HARD FAILURE OVERRIDES GOOD SOFT SCORES
# ============================================================

def test_hard_failure_overrides_soft_scores():

    dietary = dietary_pass(
        preference_score=1.0
    )

    dietary["diet"] = {
        "constraint": "diet",
        "passed": False,
        "reason":
            "Diet requirement failed"
    }

    result = evaluate_candidate(
        recipe_id="R001",
        dietary_result=dietary,
        feasibility_result=
            feasibility_pass(
                pantry_score=1.0
            ),
        budget_result=
            budget_pass()
    )

    assert (
        result["status"]
        == "rejected"
    )

    assert (
        result["overall_score"]
        is None
    )

    assert (
        result["soft_constraints"]
        is None
    )