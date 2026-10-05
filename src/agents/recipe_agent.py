"""
Member 2 - Recipe Agent

Receives User State and optional meal context,
uses the existing candidate_recipe.py retrieval tools,
and returns candidate recipe IDs.

Final dietary/allergy verification is handled by
the Reasoning Engine.
"""

import json
from pathlib import Path

import pandas as pd

from scripts.candidate_recipe import (
    load_recipe_kb,
    filter_by_diet,
    filter_by_meal_type,
    filter_by_cuisine,
    retrieve_candidates,
)


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_MAX_CANDIDATES = 10

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

RECIPE_AGENT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "recipe_agent"
    / "recipe_agent_result.json"
)


# ============================================================
# USER STATE HELPERS
# ============================================================

def _get_user_field(
    user_state,
    key,
    default=None
):
    """
    Read a field from either a User State object
    or dictionary.
    """

    if isinstance(user_state, dict):
        return user_state.get(
            key,
            default
        )

    return getattr(
        user_state,
        key,
        default
    )


def _as_list(value):
    """
    Convert a value into a list.
    """

    if value is None:
        return []

    if isinstance(
        value,
        (list, tuple, set)
    ):
        return list(value)

    return [value]


# ============================================================
# OUTPUT HELPERS
# ============================================================

def _save_result(result):
    """
    Save the exact Recipe Agent result as JSON.

    Output:
        data/recipe_agent/recipe_agent_result.json
    """

    RECIPE_AGENT_OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        RECIPE_AGENT_OUTPUT,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=4,
            ensure_ascii=False
        )


def _print_result(result):
    """
    Print Recipe Agent output in the required
    structured format.
    """

    print("\n" + "=" * 70)
    print("RECIPE AGENT OUTPUT")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=4
        )
    )


def _output_result(result):
    """
    Save and print the Recipe Agent result.

    The same result is returned by RecipeAgent.run().
    """

    _save_result(
        result
    )

    _print_result(
        result
    )


# ============================================================
# RECIPE AGENT
# ============================================================

class RecipeAgent:
    """
    Recipe Agent.

    Input:
        user_state
        optional meal_context

    Output:
        {
            "agent": "recipe",
            "status": "success",
            "data": {
                "candidate_recipe_ids": [...]
            },
            "warnings": [],
            "errors": []
        }
    """

    def __init__(
        self,
        max_candidates=DEFAULT_MAX_CANDIDATES
    ):

        if (
            not isinstance(max_candidates, int)
            or isinstance(max_candidates, bool)
            or max_candidates <= 0
        ):
            raise ValueError(
                "max_candidates must be "
                "a positive integer."
            )

        self.max_candidates = (
            max_candidates
        )


    # ========================================================
    # EXTRACT REQUIREMENTS
    # ========================================================

    def _extract_requirements(
        self,
        user_state,
        meal_context=None
    ):
        """
        Extract recipe requirements from User State.

        Uses:
            dietary_restrictions
            preferred_cuisines
            preferred_meal_types

        If Manager provides meal_context["meal_type"],
        it overrides preferred_meal_types.
        """

        if user_state is None:
            raise ValueError(
                "user_state is required."
            )

        if meal_context is None:
            meal_context = {}

        if not isinstance(
            meal_context,
            dict
        ):
            raise ValueError(
                "meal_context must be a dictionary."
            )

        # ----------------------------------------------------
        # DIETARY RESTRICTIONS
        # ----------------------------------------------------

        dietary_restrictions = [
            value
            for value in _as_list(
                _get_user_field(
                    user_state,
                    "dietary_restrictions",
                    []
                )
            )
            if str(value).strip()
        ]

        # ----------------------------------------------------
        # PREFERRED CUISINES
        # ----------------------------------------------------

        preferred_cuisines = [
            value
            for value in _as_list(
                _get_user_field(
                    user_state,
                    "preferred_cuisines",
                    []
                )
            )
            if str(value).strip()
        ]

        # ----------------------------------------------------
        # MEAL TYPE
        #
        # Manager meal context has priority.
        # ----------------------------------------------------

        context_meal_type = (
            meal_context.get(
                "meal_type"
            )
        )

        if (
            context_meal_type is not None
            and str(context_meal_type).strip()
        ):
            meal_types = [
                context_meal_type
            ]

        else:
            meal_types = [
                value
                for value in _as_list(
                    _get_user_field(
                        user_state,
                        "preferred_meal_types",
                        []
                    )
                )
                if str(value).strip()
            ]

        return {
            "dietary_restrictions":
                dietary_restrictions,

            "meal_types":
                meal_types,

            "preferred_cuisines":
                preferred_cuisines,
        }


    # ========================================================
    # SIMPLE RETRIEVAL
    # ========================================================

    def _retrieve_simple(
        self,
        requirements
    ):
        """
        Use retrieve_candidates() directly when there
        is at most one diet, meal type and cuisine.
        """

        diets = requirements[
            "dietary_restrictions"
        ]

        meal_types = requirements[
            "meal_types"
        ]

        cuisines = requirements[
            "preferred_cuisines"
        ]

        diet = (
            diets[0]
            if diets
            else None
        )

        meal_type = (
            meal_types[0]
            if meal_types
            else None
        )

        cuisine = (
            cuisines[0]
            if cuisines
            else None
        )

        # ----------------------------------------------------
        # USE EXISTING CANDIDATE RETRIEVAL
        # ----------------------------------------------------

        candidates = retrieve_candidates(
            diet=diet,
            meal_type=meal_type,
            cuisine=cuisine
        )

        # ----------------------------------------------------
        # CUISINE FALLBACK
        #
        # Cuisine is a preference rather than a hard
        # constraint.
        # ----------------------------------------------------

        if (
            candidates.empty
            and cuisine is not None
        ):
            candidates = retrieve_candidates(
                diet=diet,
                meal_type=meal_type
            )

        return candidates


    # ========================================================
    # MULTIPLE REQUIREMENTS
    # ========================================================

    def _retrieve_multiple(
        self,
        requirements
    ):
        """
        Handle multiple User State values using the
        existing candidate_recipe.py functions.

        Diet:
            AND logic

        Meal type:
            OR logic

        Cuisine:
            preference / prioritization
        """

        diets = requirements[
            "dietary_restrictions"
        ]

        meal_types = requirements[
            "meal_types"
        ]

        cuisines = requirements[
            "preferred_cuisines"
        ]

        # ----------------------------------------------------
        # LOAD RECIPE KB USING EXISTING FUNCTION
        # ----------------------------------------------------

        candidates = load_recipe_kb()

        # ----------------------------------------------------
        # DIETARY RESTRICTIONS
        # ----------------------------------------------------

        for diet in diets:

            candidates = filter_by_diet(
                candidates,
                diet
            )

            if candidates.empty:
                return candidates

        # ----------------------------------------------------
        # MEAL TYPES
        #
        # Existing candidate_recipe.py supports:
        #
        # Lunch/Dinner
        # ----------------------------------------------------

        if meal_types:

            meal_type_input = "/".join(
                str(meal_type)
                for meal_type in meal_types
            )

            candidates = filter_by_meal_type(
                candidates,
                meal_type_input
            )

        if candidates.empty:
            return candidates

        # ----------------------------------------------------
        # PREFERRED CUISINES
        #
        # Cuisine is treated as a preference.
        # Preferred cuisine recipes appear first.
        # ----------------------------------------------------

        if cuisines:

            preferred_frames = []
            preferred_ids = set()

            for cuisine in cuisines:

                cuisine_candidates = (
                    filter_by_cuisine(
                        candidates,
                        cuisine
                    )
                )

                if cuisine_candidates.empty:
                    continue

                preferred_frames.append(
                    cuisine_candidates
                )

                preferred_ids.update(
                    cuisine_candidates[
                        "recipe_id"
                    ].tolist()
                )

            if preferred_frames:

                preferred = pd.concat(
                    preferred_frames,
                    ignore_index=True
                )

                preferred = (
                    preferred
                    .drop_duplicates(
                        subset=[
                            "recipe_id"
                        ]
                    )
                )

                remaining = candidates[
                    ~candidates[
                        "recipe_id"
                    ].isin(
                        preferred_ids
                    )
                ]

                candidates = pd.concat(
                    [
                        preferred,
                        remaining,
                    ],
                    ignore_index=True
                )

        return candidates


    # ========================================================
    # RETRIEVE CANDIDATES
    # ========================================================

    def _retrieve_candidates(
        self,
        requirements
    ):
        """
        Choose simple or multiple-value retrieval.
        """

        diets = requirements[
            "dietary_restrictions"
        ]

        meal_types = requirements[
            "meal_types"
        ]

        cuisines = requirements[
            "preferred_cuisines"
        ]

        simple_input = (
            len(diets) <= 1
            and len(meal_types) <= 1
            and len(cuisines) <= 1
        )

        if simple_input:

            return self._retrieve_simple(
                requirements
            )

        return self._retrieve_multiple(
            requirements
        )


    # ========================================================
    # FAILURE RESULT
    # ========================================================

    @staticmethod
    def _failure_result(
        error
    ):
        """
        Create the shared Recipe Agent failure format.
        """

        return {
            "agent": "recipe",

            "status": "failed",

            "data": {
                "candidate_recipe_ids": []
            },

            "warnings": [],

            "errors": [
                str(error)
            ],
        }


    # ========================================================
    # PUBLIC ENTRY POINT
    # ========================================================

    def run(
        self,
        user_state,
        meal_context=None,
        max_candidates=None
    ):
        """
        Execute Recipe Agent.

        Manager calls this method directly.

        The same result is:
            1. saved as JSON
            2. printed to terminal
            3. returned to Manager
        """

        # ----------------------------------------------------
        # CANDIDATE LIMIT
        # ----------------------------------------------------

        limit = (
            self.max_candidates
            if max_candidates is None
            else max_candidates
        )

        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit <= 0
        ):

            result = self._failure_result(
                "max_candidates must be "
                "a positive integer"
            )

            _output_result(
                result
            )

            return result

        # ----------------------------------------------------
        # EXTRACT INPUT
        # ----------------------------------------------------

        try:

            requirements = (
                self._extract_requirements(
                    user_state,
                    meal_context
                )
            )

        except (
            TypeError,
            ValueError,
        ) as error:

            result = self._failure_result(
                error
            )

            _output_result(
                result
            )

            return result

        # ----------------------------------------------------
        # RETRIEVE CANDIDATES
        # ----------------------------------------------------

        try:

            candidates = (
                self._retrieve_candidates(
                    requirements
                )
            )

        except (
            ValueError,
            FileNotFoundError,
        ) as error:

            result = self._failure_result(
                error
            )

            _output_result(
                result
            )

            return result

        # ----------------------------------------------------
        # LIMIT CANDIDATES
        # ----------------------------------------------------

        candidates = (
            candidates
            .head(limit)
            .copy()
        )

        # ----------------------------------------------------
        # EXTRACT RECIPE IDS
        # ----------------------------------------------------

        if (
            "recipe_id"
            in candidates.columns
        ):

            candidate_ids = (
                candidates[
                    "recipe_id"
                ]
                .astype(str)
                .tolist()
            )

        else:

            candidate_ids = []

        # ----------------------------------------------------
        # WARNINGS
        # ----------------------------------------------------

        warnings = []

        if not candidate_ids:

            warnings.append(
                "No candidate recipes matched "
                "retrieval criteria"
            )

        # ----------------------------------------------------
        # EXACT REQUIRED OUTPUT CONTRACT
        # ----------------------------------------------------

        result = {
            "agent": "recipe",

            "status": "success",

            "data": {
                "candidate_recipe_ids":
                    candidate_ids
            },

            "warnings":
                warnings,

            "errors":
                [],
        }

        # ----------------------------------------------------
        # SAVE + PRINT
        # ----------------------------------------------------

        _output_result(
            result
        )

        # ----------------------------------------------------
        # RETURN TO MANAGER
        # ----------------------------------------------------

        return result