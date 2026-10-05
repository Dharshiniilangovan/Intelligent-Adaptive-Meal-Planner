"""
Member 2 - Recipe Agent

Receives User State and optional meal context from Manager,
uses the existing candidate_recipe.py retrieval tools,
and returns candidate recipe IDs.

Final dietary/allergy verification is handled later
by the Reasoning Engine.
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

from src.agents.contracts import (
    AgentResult,
    AgentStatus,
)


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_MAX_CANDIDATES = 10


# ============================================================
# USER STATE HELPERS
# ============================================================

def _get_user_field(
    user_state,
    key,
    default=None
):
    """
    Read a field from either:

    User State object:
        user_state.dietary_restrictions

    or dictionary:
        user_state["dietary_restrictions"]
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
# RECIPE AGENT
# ============================================================

class RecipeAgent:
    """
    Recipe Agent.

    Input:
        user_state
        optional meal_context
        optional max_candidates

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

        User State fields used:
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
        # Manager's current meal context has priority over
        # the user's general meal preference.
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
        Use the existing retrieve_candidates() directly
        when there is at most one diet, one meal type,
        and one cuisine.
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
        # REUSE EXISTING CANDIDATE RETRIEVAL
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
        #
        # If no preferred cuisine recipe exists,
        # retry using diet and meal type only.
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
        Handle list-valued User State requirements while
        reusing existing candidate_recipe.py functions.

        Dietary restrictions:
            AND logic

        Meal types:
            OR logic

        Preferred cuisines:
            prioritization
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
        # LOAD USING EXISTING CANDIDATE TOOL
        # ----------------------------------------------------

        candidates = load_recipe_kb()

        # ----------------------------------------------------
        # DIETARY RESTRICTIONS
        #
        # Example:
        # Vegetarian AND Low-Carb
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
        # candidate_recipe.py already supports:
        #
        # Lunch/Dinner
        #
        # Therefore:
        #
        # ["Lunch", "Dinner"]
        #
        # becomes:
        #
        # "Lunch/Dinner"
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
        # Cuisine is a preference.
        #
        # Preferred cuisine recipes are moved to the front.
        # Other valid recipes remain available.
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
        Select the appropriate existing retrieval path.
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
        Return the shared AgentResult failure format.
        """

        return AgentResult(
            agent="recipe",

            status=AgentStatus.FAILED,

            data={
                "candidate_recipe_ids": []
            },

            warnings=[],

            errors=[
                str(error)
            ],
        ).to_dict()


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

            return self._failure_result(
                "max_candidates must be "
                "a positive integer"
            )

        # ----------------------------------------------------
        # EXTRACT MANAGER / USER STATE INPUT
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

            return self._failure_result(
                error
            )

        # ----------------------------------------------------
        # EXISTING CANDIDATE RETRIEVAL
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

            return self._failure_result(
                error
            )

        # ----------------------------------------------------
        # LIMIT DOWNSTREAM WORK
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
        # REMOVE DUPLICATE IDS WHILE PRESERVING ORDER
        # ----------------------------------------------------

        candidate_ids = list(
            dict.fromkeys(
                candidate_ids
            )
        )

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
        # SHARED AGENT RESULT
        # ----------------------------------------------------

        return AgentResult(
            agent="recipe",

            status=AgentStatus.SUCCESS,

            data={
                "candidate_recipe_ids":
                    candidate_ids
            },

            warnings=
                warnings,

            errors=[],
        ).to_dict()


# ============================================================
# TEMPORARY MAIN - STANDALONE CHECK ONLY
#
# Remove this block when Manager integration is complete.
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # PROJECT ROOT
    # --------------------------------------------------------

    project_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    # --------------------------------------------------------
    # USER STATE DIRECTORY
    # --------------------------------------------------------

    users_dir = (
        project_root
        / "data"
        / "users"
    )

    # --------------------------------------------------------
    # FIND EXISTING USER STATE FILES
    # --------------------------------------------------------

    user_state_files = list(
        users_dir.glob(
            "user_state_*.json"
        )
    )

    if not user_state_files:

        raise FileNotFoundError(
            f"No User State files found in: "
            f"{users_dir}"
        )

    # --------------------------------------------------------
    # USE MOST RECENT USER STATE
    # --------------------------------------------------------

    latest_user_state_file = max(
        user_state_files,
        key=lambda path:
            path.stat().st_mtime
    )

    # --------------------------------------------------------
    # LOAD USER STATE
    # --------------------------------------------------------

    with open(
        latest_user_state_file,
        "r",
        encoding="utf-8"
    ) as file:

        user_state = json.load(
            file
        )

    # --------------------------------------------------------
    # PRINT INPUT
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("RECIPE AGENT INPUT")
    print("=" * 70)

    print(
        json.dumps(
            user_state,
            indent=4
        )
    )

    # --------------------------------------------------------
    # CREATE RECIPE AGENT
    # --------------------------------------------------------

    recipe_agent = RecipeAgent(
        max_candidates=10
    )

    # --------------------------------------------------------
    # RUN RECIPE AGENT
    #
    # No meal_context is supplied for this standalone check.
    # The agent therefore uses preferred_meal_types from
    # User State.
    # --------------------------------------------------------

    result = recipe_agent.run(
        user_state=user_state,
        max_candidates=10
    )

    # --------------------------------------------------------
    # PRINT OUTPUT
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("RECIPE AGENT OUTPUT")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=4
        )
    )