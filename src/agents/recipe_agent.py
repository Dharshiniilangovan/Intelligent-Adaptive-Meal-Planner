import json
from datetime import date
from pathlib import Path

import pandas as pd


# ============================================================
# REUSE EXISTING CANDIDATE RECIPE FUNCTIONS
# ============================================================

from scripts.candidate_recipe import (
    load_recipe_kb,
    filter_by_diet,
    filter_by_meal_type,
    filter_by_cuisine,
    retrieve_candidates,
)


# ============================================================
# SHARED AGENT CONTRACT
# ============================================================

from src.agents.contracts import (
    AgentResult,
    AgentStatus,
)


# ============================================================
# EXISTING REPOSITORY
# ============================================================

from src.knowledge.repository import (
    RecipeRepository,
    normalize,
)


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_MAX_CANDIDATES = 5

RECENT_CUISINE_WINDOW = 3


# ============================================================
# GENERIC HELPERS
# ============================================================

def _get_field(
    source,
    key,
    default=None,
):
    """
    Read a field from either a dictionary or object.
    """

    if source is None:
        return default

    if isinstance(source, dict):

        return source.get(
            key,
            default,
        )

    return getattr(
        source,
        key,
        default,
    )


def _as_list(value):
    """
    Convert input into a list.
    """

    if value is None:
        return []

    if isinstance(
        value,
        (list, tuple, set),
    ):
        return list(value)

    return [value]


def _clean_list(value):
    """
    Remove empty values.
    """

    return [
        item
        for item in _as_list(value)
        if str(item).strip()
    ]


# ============================================================
# RECIPE AGENT
# ============================================================

class RecipeAgent:
    """
    MEMBER 2
    SLOT-AWARE RECIPE CANDIDATE STRATEGY

    ----------------------------------------------------------
    INPUT FROM MANAGER
    ----------------------------------------------------------

    1. user_state

    2. meal_slot

       Example:

       {
           "date": "2026-10-07",
           "meal_type": "dinner",
           "max_cooking_time": 30
       }

    3. selected_recipe_ids

       Example:

       [
           "R001",
           "R024",
           "R133"
       ]

    4. recent_cuisines

       Optional:

       [
           "asian",
           "italian",
           "asian"
       ]

    ----------------------------------------------------------
    RESPONSIBILITIES
    ----------------------------------------------------------

    Existing candidate_recipe.py handles:

        - Recipe KB loading
        - Diet filtering
        - Meal-type filtering
        - Cuisine filtering
        - Base candidate retrieval

    RecipeAgent adds:

        - Current slot awareness
        - Manager-selected recipe exclusion
        - Optional cooking-time constraint
        - Basic cuisine variety
        - Duplicate protection
        - Candidate limit

    ----------------------------------------------------------
    HARD RULE
    ----------------------------------------------------------

    Any recipe present in selected_recipe_ids MUST NOT
    appear in candidate_recipe_ids.

    ----------------------------------------------------------
    COOKING TIME RULE
    ----------------------------------------------------------

    If cooking-time information is unavailable:

        SKIP cooking-time filtering.

    Continue using the other filters.
    """

    # ========================================================
    # INITIALIZE
    # ========================================================

    def __init__(
        self,
        max_candidates=DEFAULT_MAX_CANDIDATES,
        repository=None,
    ):

        if (
            not isinstance(max_candidates, int)
            or isinstance(max_candidates, bool)
            or max_candidates <= 0
        ):

            raise ValueError(
                "max_candidates must be a positive integer."
            )

        self.max_candidates = (
            max_candidates
        )

        self.repository = (
            repository
            if repository is not None
            else RecipeRepository.from_csv()
        )

    # ========================================================
    # FAILURE RESULT
    # ========================================================

    @staticmethod
    def _failure_result(
        error,
    ):
        """
        Return shared failure format.
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
    # USER REQUIREMENTS
    # ========================================================

    def _extract_user_requirements(
        self,
        user_state,
    ):
        """
        Extract only recipe-related User State fields.

        Recipe history is NOT read here.

        Manager owns selected_recipe_ids.
        """

        if user_state is None:

            raise ValueError(
                "user_state is required."
            )

        dietary_restrictions = (
            _clean_list(
                _get_field(
                    user_state,
                    "dietary_restrictions",
                    [],
                )
            )
        )

        preferred_cuisines = (
            _clean_list(
                _get_field(
                    user_state,
                    "preferred_cuisines",
                    [],
                )
            )
        )

        preferred_meal_types = (
            _clean_list(
                _get_field(
                    user_state,
                    "preferred_meal_types",
                    [],
                )
            )
        )

        return {

            "dietary_restrictions":
                dietary_restrictions,

            "preferred_cuisines":
                preferred_cuisines,

            "preferred_meal_types":
                preferred_meal_types,
        }

    # ========================================================
    # SLOT CONTEXT
    # ========================================================

    def _extract_slot_context(
        self,
        requirements,
        meal_slot,
    ):
        """
        Extract current slot supplied by Manager.
        """

        if meal_slot is None:

            raise ValueError(
                "meal_slot is required."
            )

        slot_date = _get_field(
            meal_slot,
            "date",
            None,
        )

        meal_type = _get_field(
            meal_slot,
            "meal_type",
            None,
        )

        max_cooking_time = _get_field(
            meal_slot,
            "max_cooking_time",
            None,
        )

        # ----------------------------------------------------
        # FALLBACK TO USER STATE
        # ----------------------------------------------------

        if not meal_type:

            preferred_meal_types = (
                requirements[
                    "preferred_meal_types"
                ]
            )

            if len(
                preferred_meal_types
            ) == 1:

                meal_type = (
                    preferred_meal_types[0]
                )

        if not meal_type:

            raise ValueError(
                "meal_type is required."
            )

        meal_type = (
            str(meal_type)
            .strip()
            .lower()
        )

        return {

            "date":
                slot_date,

            "meal_type":
                meal_type,

            "max_cooking_time":
                max_cooking_time,
        }

    # ========================================================
    # MANAGER SELECTED RECIPES
    # ========================================================

    @staticmethod
    def _normalize_selected_recipe_ids(
        selected_recipe_ids,
    ):
        """
        Normalize selected recipe IDs supplied by Manager.

        Example:

        [
            "r001",
            " R024 ",
            "R133"
        ]

        becomes:

        [
            "R001",
            "R024",
            "R133"
        ]
        """

        normalized_ids = []

        for recipe_id in _as_list(
            selected_recipe_ids
        ):

            if recipe_id is None:
                continue

            recipe_id = (
                str(recipe_id)
                .strip()
                .upper()
            )

            if not recipe_id:
                continue

            if (
                recipe_id
                not in normalized_ids
            ):

                normalized_ids.append(
                    recipe_id
                )

        return normalized_ids

    # ========================================================
    # RECENT CUISINES
    # ========================================================

    @staticmethod
    def _normalize_recent_cuisines(
        recent_cuisines,
    ):
        """
        Normalize optional cuisine history supplied
        by Manager.
        """

        normalized_cuisines = []

        for cuisine in _as_list(
            recent_cuisines
        ):

            if not str(
                cuisine
            ).strip():

                continue

            normalized_cuisine = (
                normalize(
                    cuisine
                )
            )

            if normalized_cuisine:

                normalized_cuisines.append(
                    normalized_cuisine
                )

        return normalized_cuisines[
            -RECENT_CUISINE_WINDOW:
        ]

    # ========================================================
    # BASE CANDIDATE RETRIEVAL
    # ========================================================

    def _retrieve_candidates(
        self,
        requirements,
        meal_type,
    ):
        """
        REUSE candidate_recipe.py.

        This method does NOT rewrite the existing
        diet / meal-type / cuisine filters.
        """

        diets = requirements[
            "dietary_restrictions"
        ]

        cuisines = requirements[
            "preferred_cuisines"
        ]

        # ----------------------------------------------------
        # SIMPLE CASE
        #
        # Reuse existing retrieve_candidates().
        # ----------------------------------------------------

        if (
            len(diets) <= 1
            and len(cuisines) <= 1
        ):

            diet = (
                diets[0]
                if diets
                else None
            )

            cuisine = (
                cuisines[0]
                if cuisines
                else None
            )

            candidates = (
                retrieve_candidates(
                    diet=diet,
                    meal_type=meal_type,
                    cuisine=cuisine,
                )
            )

            # ------------------------------------------------
            # CUISINE IS SOFT
            #
            # Retry without cuisine if preferred cuisine
            # returns nothing.
            # ------------------------------------------------

            if (
                candidates.empty
                and cuisine is not None
            ):

                candidates = (
                    retrieve_candidates(
                        diet=diet,
                        meal_type=meal_type,
                    )
                )

            return candidates

        # ----------------------------------------------------
        # MULTIPLE REQUIREMENTS
        #
        # Reuse existing candidate_recipe.py filter functions.
        # ----------------------------------------------------

        candidates = (
            load_recipe_kb()
        )

        # ----------------------------------------------------
        # DIET
        # ----------------------------------------------------

        for diet in diets:

            candidates = (
                filter_by_diet(
                    candidates,
                    diet,
                )
            )

            if candidates.empty:

                return candidates

        # ----------------------------------------------------
        # MEAL TYPE
        # ----------------------------------------------------

        if meal_type:

            candidates = (
                filter_by_meal_type(
                    candidates,
                    meal_type,
                )
            )

            if candidates.empty:

                return candidates

        # ----------------------------------------------------
        # CUISINE
        #
        # Cuisine remains a soft preference.
        # ----------------------------------------------------

        if cuisines:

            preferred_frames = []
            preferred_ids = set()

            for cuisine in cuisines:

                cuisine_candidates = (
                    filter_by_cuisine(
                        candidates,
                        cuisine,
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
                    ignore_index=True,
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

                candidates = (
                    pd.concat(
                        [
                            preferred,
                            remaining,
                        ],
                        ignore_index=True,
                    )
                )

        return candidates

    # ========================================================
    # HARD REPETITION EXCLUSION
    # ========================================================

    @staticmethod
    def _exclude_selected_recipes(
        candidates,
        selected_recipe_ids,
    ):
        """
        Remove recipes already selected by Manager.

        HARD CONSTRAINT.

        This is query-time exclusion.

        Nothing is deleted from Recipe KB.
        """

        if candidates.empty:

            return candidates

        if not selected_recipe_ids:

            return candidates

        if (
            "recipe_id"
            not in candidates.columns
        ):

            raise KeyError(
                "recipe_id column is missing "
                "from recipe candidates."
            )

        selected_set = set(
            selected_recipe_ids
        )

        candidate_ids = (
            candidates[
                "recipe_id"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        return candidates[
            ~candidate_ids.isin(
                selected_set
            )
        ].copy()

    # ========================================================
    # OPTIONAL COOKING TIME
    # ========================================================

    def _apply_cooking_time(
        self,
        candidates,
        max_cooking_time,
    ):
        """
        Apply cooking-time filtering ONLY when possible.

        ------------------------------------------------------
        CASE 1
        cooking_time_min column is unavailable
        ------------------------------------------------------

        Skip cooking-time filtering.

        ------------------------------------------------------
        CASE 2
        cooking_time_min exists but has no usable values
        ------------------------------------------------------

        Skip cooking-time filtering.

        ------------------------------------------------------
        CASE 3
        cooking-time data exists but Manager supplied
        no max_cooking_time
        ------------------------------------------------------

        Skip maximum-time filtering.

        ------------------------------------------------------
        CASE 4
        cooking-time data exists AND Manager supplied
        max_cooking_time
        ------------------------------------------------------

        Reuse RecipeRepository.filter_by_max_time()
        instead of rewriting the time-filter logic.
        """

        warnings = []

        if candidates.empty:

            return (
                candidates,
                warnings,
            )

        # ----------------------------------------------------
        # COOKING-TIME COLUMN DOES NOT EXIST
        # ----------------------------------------------------

        if (
            "cooking_time_min"
            not in candidates.columns
        ):

            warnings.append(
                "Cooking-time data unavailable; "
                "cooking-time filtering skipped."
            )

            return (
                candidates,
                warnings,
            )

        # ----------------------------------------------------
        # CHECK IF COLUMN CONTAINS USABLE VALUES
        # ----------------------------------------------------

        cooking_times = (
            pd.to_numeric(
                candidates[
                    "cooking_time_min"
                ],
                errors="coerce",
            )
        )

        if not cooking_times.notna().any():

            warnings.append(
                "No usable cooking-time values; "
                "cooking-time filtering skipped."
            )

            return (
                candidates,
                warnings,
            )

        # ----------------------------------------------------
        # MANAGER DID NOT SUPPLY TIME CONSTRAINT
        # ----------------------------------------------------

        if max_cooking_time is None:

            return (
                candidates,
                warnings,
            )

        # ----------------------------------------------------
        # VALIDATE TIME
        # ----------------------------------------------------

        try:

            max_cooking_time = float(
                max_cooking_time
            )

        except (
            TypeError,
            ValueError,
        ):

            warnings.append(
                "Invalid max cooking time; "
                "cooking-time filtering skipped."
            )

            return (
                candidates,
                warnings,
            )

        if max_cooking_time < 0:

            warnings.append(
                "Negative max cooking time; "
                "cooking-time filtering skipped."
            )

            return (
                candidates,
                warnings,
            )

        # ----------------------------------------------------
        # REUSE EXISTING REPOSITORY FILTER
        # ----------------------------------------------------

        valid_time_ids = set(
            self.repository
            .filter_by_max_time(
                max_cooking_time,
                include_unknown=False,
            )
            .ids()
        )

        valid_time_ids = {
            str(recipe_id)
            .strip()
            .upper()

            for recipe_id
            in valid_time_ids
        }

        # ----------------------------------------------------
        # KEEP ONLY RECIPES VALID FOR TIME LIMIT
        # ----------------------------------------------------

        normalized_candidate_ids = (
            candidates[
                "recipe_id"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        candidates = candidates[
            normalized_candidate_ids.isin(
                valid_time_ids
            )
        ].copy()

        return (
            candidates,
            warnings,
        )

    # ========================================================
    # CUISINE IDS
    # ========================================================

    @staticmethod
    def _cuisine_recipe_ids(
        candidates,
        cuisine,
    ):
        """
        Reuse candidate_recipe.py's cuisine filter.
        """

        if candidates.empty:

            return set()

        matching = (
            filter_by_cuisine(
                candidates,
                cuisine,
            )
        )

        if matching.empty:

            return set()

        return set(
            matching[
                "recipe_id"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
            .tolist()
        )

    # ========================================================
    # BASIC VARIETY
    # ========================================================

    def _rank_for_variety(
        self,
        candidates,
        preferred_cuisines,
        recent_cuisines,
    ):
        """
        Member 2 variety logic.

        Exact recipe:
            HARD exclusion handled earlier.

        Preferred cuisine:
            +1

        Recently selected cuisine:
            -1 per occurrence

        Cuisine remains a soft preference.
        """

        if candidates.empty:

            return candidates

        if (
            not preferred_cuisines
            and not recent_cuisines
        ):

            return candidates

        ranked = (
            candidates.copy()
        )

        ranked[
            "_original_order"
        ] = range(
            len(ranked)
        )

        ranked[
            "_variety_score"
        ] = 0

        # ----------------------------------------------------
        # PREFERRED CUISINE BOOST
        # ----------------------------------------------------

        for cuisine in preferred_cuisines:

            matching_ids = (
                self._cuisine_recipe_ids(
                    candidates,
                    cuisine,
                )
            )

            if not matching_ids:

                continue

            normalized_ids = (
                ranked[
                    "recipe_id"
                ]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            ranked.loc[
                normalized_ids.isin(
                    matching_ids
                ),
                "_variety_score",
            ] += 1

        # ----------------------------------------------------
        # RECENT CUISINE PENALTY
        # ----------------------------------------------------

        for cuisine in recent_cuisines:

            matching_ids = (
                self._cuisine_recipe_ids(
                    candidates,
                    cuisine,
                )
            )

            if not matching_ids:

                continue

            normalized_ids = (
                ranked[
                    "recipe_id"
                ]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            ranked.loc[
                normalized_ids.isin(
                    matching_ids
                ),
                "_variety_score",
            ] -= 1

        # ----------------------------------------------------
        # STABLE RANK
        # ----------------------------------------------------

        ranked = (
            ranked
            .sort_values(
                by=[
                    "_variety_score",
                    "_original_order",
                ],

                ascending=[
                    False,
                    True,
                ],

                kind="stable",
            )
        )

        ranked = (
            ranked
            .drop(
                columns=[
                    "_variety_score",
                    "_original_order",
                ]
            )
        )

        return ranked

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    @staticmethod
    def _remove_duplicate_recipes(
        candidates,
    ):
        """
        Remove duplicate recipe IDs.
        """

        if candidates.empty:

            return candidates

        if (
            "recipe_id"
            not in candidates.columns
        ):

            raise KeyError(
                "recipe_id column is missing."
            )

        candidates = (
            candidates.copy()
        )

        candidates[
            "recipe_id"
        ] = (
            candidates[
                "recipe_id"
            ]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        return (
            candidates
            .drop_duplicates(
                subset=[
                    "recipe_id"
                ],
                keep="first",
            )
        )

    # ========================================================
    # FINAL HARD REPETITION CHECK
    # ========================================================

    @staticmethod
    def _final_repetition_check(
        candidate_ids,
        selected_recipe_ids,
    ):
        """
        Final safety check.

        Manager-selected recipes can never escape
        into the final output.
        """

        selected_set = set(
            selected_recipe_ids
        )

        safe_ids = []

        for recipe_id in candidate_ids:

            recipe_id = (
                str(recipe_id)
                .strip()
                .upper()
            )

            if not recipe_id:

                continue

            # ------------------------------------------------
            # ALREADY SELECTED
            # ------------------------------------------------

            if recipe_id in selected_set:

                continue

            # ------------------------------------------------
            # DUPLICATE IN CURRENT OUTPUT
            # ------------------------------------------------

            if recipe_id in safe_ids:

                continue

            safe_ids.append(
                recipe_id
            )

        return safe_ids

    # ========================================================
    # RUN
    # ========================================================

    def run(
        self,
        user_state,
        meal_slot,
        selected_recipe_ids=None,
        recent_cuisines=None,
        max_candidates=None,
    ):
        """
        Generate candidates for ONE slot.

        Manager calls this method once per meal slot.

        Example:

        result = recipe_agent.run(

            user_state=user_state,

            meal_slot={
                "date": "2026-10-07",
                "meal_type": "dinner",
                "max_cooking_time": 30
            },

            selected_recipe_ids=[
                "R001",
                "R024",
                "R133"
            ],

            recent_cuisines=[
                "asian",
                "italian"
            ],

            max_candidates=5
        )
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
                "max_candidates must be a positive integer."
            )

        # ----------------------------------------------------
        # NORMALIZE MANAGER STATE
        # ----------------------------------------------------

        selected_recipe_ids = (
            self._normalize_selected_recipe_ids(
                selected_recipe_ids
            )
        )

        recent_cuisines = (
            self._normalize_recent_cuisines(
                recent_cuisines
            )
        )

        # ----------------------------------------------------
        # EXTRACT INPUT
        # ----------------------------------------------------

        try:

            requirements = (
                self._extract_user_requirements(
                    user_state
                )
            )

            slot_context = (
                self._extract_slot_context(
                    requirements,
                    meal_slot,
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
        # CANDIDATE PIPELINE
        # ----------------------------------------------------

        try:

            # =================================================
            # 1. EXISTING CANDIDATE RETRIEVAL
            # =================================================

            candidates = (
                self._retrieve_candidates(
                    requirements,

                    slot_context[
                        "meal_type"
                    ],
                )
            )

            # =================================================
            # 2. HARD REPETITION EXCLUSION
            # =================================================

            candidates = (
                self._exclude_selected_recipes(
                    candidates,

                    selected_recipe_ids,
                )
            )

            # =================================================
            # 3. OPTIONAL COOKING TIME
            #
            # Uses existing repository when applicable.
            # =================================================

            (
                candidates,
                time_warnings,
            ) = (
                self._apply_cooking_time(
                    candidates,

                    slot_context[
                        "max_cooking_time"
                    ],
                )
            )

            # =================================================
            # 4. DUPLICATE REMOVAL
            # =================================================

            candidates = (
                self._remove_duplicate_recipes(
                    candidates
                )
            )

            # =================================================
            # 5. BASIC VARIETY
            # =================================================

            candidates = (
                self._rank_for_variety(
                    candidates,

                    requirements[
                        "preferred_cuisines"
                    ],

                    recent_cuisines,
                )
            )

        except (
            ValueError,
            KeyError,
            FileNotFoundError,
        ) as error:

            return self._failure_result(
                error
            )

        # ----------------------------------------------------
        # GET IDS
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
                .str.strip()
                .str.upper()
                .tolist()
            )

        else:

            candidate_ids = []

        # ----------------------------------------------------
        # FINAL REPETITION PROTECTION
        # ----------------------------------------------------

        candidate_ids = (
            self._final_repetition_check(
                candidate_ids,

                selected_recipe_ids,
            )
        )

        # ----------------------------------------------------
        # LIMIT
        # ----------------------------------------------------

        candidate_ids = (
            candidate_ids[
                :limit
            ]
        )

        # ----------------------------------------------------
        # EXACT REQUIRED OUTPUT
        # ----------------------------------------------------

        return {

            "slot": {

                "date":
                    slot_context[
                        "date"
                    ],

                "meal_type":
                    slot_context[
                        "meal_type"
                    ],
            },

            "candidate_recipe_ids":
                candidate_ids,
        }


# ============================================================
# LOAD LATEST USER STATE
# ============================================================

def load_latest_user_state():
    """
    Load the latest User State.

    User State provides:

        diet
        cuisine
        meal preferences
        other user restrictions

    Previously selected recipes now come from Manager.
    """

    project_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    users_dir = (
        project_root
        / "data"
        / "users"
    )

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

    latest_user_state_file = max(
        user_state_files,

        key=lambda path:
            path.stat().st_mtime,
    )

    with open(
        latest_user_state_file,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(
            file
        )


# ============================================================
# STANDALONE INPUT
# ============================================================

def get_standalone_input():
    """
    Temporary standalone input.

    During Manager integration, Manager will supply:

        meal_slot
        selected_recipe_ids
        recent_cuisines

    This function only allows recipe_agent.py
    to be run independently.
    """

    meal_slot = {

        "date":
            date.today().isoformat(),

        "meal_type":
            "dinner",
    }

    # --------------------------------------------------------
    # WHEN TESTING MANUALLY, PUT ALREADY SELECTED RECIPES HERE
    # --------------------------------------------------------

    selected_recipe_ids = [
    ]

    # --------------------------------------------------------
    # OPTIONAL VARIETY CONTEXT
    # --------------------------------------------------------

    recent_cuisines = [
    ]

    return (
        meal_slot,
        selected_recipe_ids,
        recent_cuisines,
    )


# ============================================================
# PRINT
# ============================================================

def print_recipe_result(result, repository=None):
    """
    Print candidate recipe IDs along with
    recipe names and cooking times.
    """

    print("\n" + "=" * 70)
    print("RECIPE AGENT RESULT")
    print("=" * 70)

    print(json.dumps(result, indent=4))

    candidate_ids = result.get(
        "candidate_recipe_ids", []
    )

    if not candidate_ids:
        print("\nNo candidate recipes found.")
        return

    # Load recipe knowledge base
    df = load_recipe_kb()

    print("\n" + "=" * 70)
    print("CANDIDATE RECIPE COOKING TIMES")
    print("=" * 70)

    for recipe_id in candidate_ids:

        recipe = df[
            df["recipe_id"].astype(str).str.strip().str.upper()
            == str(recipe_id).strip().upper()
        ]

        if recipe.empty:
            print(f"\nRecipe ID: {recipe_id}")
            print("Recipe not found in knowledge base.")
            continue

        recipe_row = recipe.iloc[0]

        recipe_name = recipe_row.get(
            "recipe_name", "Unknown Recipe"
        )

        cooking_time = pd.to_numeric(
            recipe_row.get("cooking_time_min"),
            errors="coerce"
        )

        print(f"\nRecipe ID     : {recipe_id}")
        print(f"Recipe Name   : {recipe_name}")

        if pd.notna(cooking_time):
            print(f"Cooking Time  : {cooking_time:g} minutes")
        else:
            print("Cooking Time  : Not available")

    print("\n" + "=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():
    """
    Main only runs functions.

    No filtering or Recipe Agent business logic lives here.
    """

    user_state = (
        load_latest_user_state()
    )

    recipe_agent = (
        RecipeAgent(
            max_candidates=5
        )
    )

    (
        meal_slot,
        selected_recipe_ids,
        recent_cuisines,
    ) = (
        get_standalone_input()
    )

    result = (
        recipe_agent.run(

            user_state=
                user_state,

            meal_slot=
                meal_slot,

            selected_recipe_ids=
                selected_recipe_ids,

            recent_cuisines=
                recent_cuisines,

            max_candidates=5,
        )
    )

    print_recipe_result(
        result
    )


if __name__ == "__main__":
    main()