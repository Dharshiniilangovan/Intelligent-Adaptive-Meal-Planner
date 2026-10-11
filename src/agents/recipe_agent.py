import json
import contextlib
import io
from datetime import date
from pathlib import Path

import pandas as pd
from src.agents.recipe_check import DayEvaluator

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

def _get_field(source, key, default=None):
    """
    Read a field from either a dictionary or object.
    """

    if source is None:
        return default

    if isinstance(source, dict):
        return source.get(key, default)

    return getattr(source, key, default)


def _as_list(value):
    """
    Convert input into a list.
    """

    if value is None:
        return []

    if isinstance(value, (list, tuple, set)):
        return list(value)

    return [value]


def _clean_list(value):
    """
    Remove empty values.
    """

    return [
        item
        for item in _as_list(value)
        if item is not None and str(item).strip()
    ]


def build_semantic_query(user_state, meal_type=None):
    """Create a semantic query solely from the existing User State fields."""
    terms = []
    for field in ("preferred_cuisines", "dietary_restrictions"):
        terms.extend(str(v).strip() for v in _clean_list(_get_field(user_state, field, [])))
    if meal_type:
        terms.append(str(meal_type).strip())
    else:
        terms.extend(str(v).strip() for v in _clean_list(_get_field(user_state, "preferred_meal_types", [])))
    terms.extend(str(v).strip() for v in _clean_list(_get_field(user_state, "preferred_ingredients", [])))
    return " ".join(t for t in terms if t) or "meal recipe"


# ============================================================
# RECIPE AGENT
# ============================================================

class RecipeAgent:
    """
    SLOT-AWARE RECIPE CANDIDATE AGENT

    INPUT:
        user_state
        meal_slot
        selected_recipe_ids
        recent_cuisines

    FEATURES:
        - Dietary filtering
        - Meal-type filtering
        - Cuisine preferences
        - Previously selected recipe exclusion
        - Cooking-time preference from User State
        - Manager cooking-time override
        - Cuisine variety ranking
        - Duplicate removal
        - Candidate limit

    COOKING TIME PRIORITY:

        1. Manager max_cooking_time
        2. User State cook_time_preference_hrs
        3. Skip filtering when no limit exists
    """

    # ========================================================
    # INITIALIZE
    # ========================================================

    def __init__(
        self,
        max_candidates=DEFAULT_MAX_CANDIDATES,
        repository=None,
        rag=None,
    ):

        if (
            not isinstance(max_candidates, int)
            or isinstance(max_candidates, bool)
            or max_candidates <= 0
        ):
            raise ValueError(
                "max_candidates must be a positive integer."
            )

        self.recipe_check = DayEvaluator()
        self.rag = rag
        self.max_candidates = max_candidates

        self.repository = (
            repository
            if repository is not None
            else RecipeRepository.from_csv()
        )

    # ========================================================
    # FAILURE RESULT
    # ========================================================

    @staticmethod
    def _failure_result(error):

        return AgentResult(
            agent="recipe",
            status=AgentStatus.FAILED,
            data={
                "candidate_recipe_ids": []
            },
            warnings=[],
            errors=[str(error)],
        ).to_dict()

    @staticmethod
    def _save_rejection_report(
        slot_context,
        rejected_candidates,
        ranked_candidates,
        notes=None
    ):
        """
        Save rejection reports in a single JSON file.
        Each execution overwrites the previous report.
        """

        report_dir = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "processed"
            / "recipe_rejection_reports"
        )

        report_dir.mkdir(parents=True, exist_ok=True)

        # Use one fixed filename
        path = report_dir / "rejected_recipes.json"

        meal_type = str(
            slot_context.get("meal_type") or "unknown"
        )

        report = {
            "slot": {
                "date": slot_context.get("date"),
                "meal_type": meal_type
            },
            "rejected_candidates": rejected_candidates,
            "ranked_candidates": ranked_candidates,
        }

        if notes:
            report["notes"] = notes

        # Overwrite the previous JSON report
        path.write_text(
            json.dumps(report, indent=4, default=str),
            encoding="utf-8"
        )
    # ========================================================
    # USER REQUIREMENTS
    # ========================================================

    def _extract_user_requirements(self, user_state):
        """
        Extract recipe-related User State fields.

        Cooking-time preference is stored in HOURS.

        Example:
            cook_time_preference_hrs = 2

        Converted:
            max_cooking_time = 120 minutes
        """

        if user_state is None:
            raise ValueError(
                "user_state is required."
            )

        dietary_restrictions = _clean_list(
            _get_field(
                user_state,
                "dietary_restrictions",
                [],
            )
        )

        preferred_cuisines = _clean_list(
            _get_field(
                user_state,
                "preferred_cuisines",
                [],
            )
        )

        preferred_meal_types = _clean_list(
            _get_field(
                user_state,
                "preferred_meal_types",
                [],
            )
        )

        # ----------------------------------------------------
        # COOKING TIME FROM USER STATE
        # ----------------------------------------------------

        cook_time_preference_hrs = _get_field(
            user_state,
            "cook_time_preference_hrs",
            None,
        )

        max_cooking_time = None

        if cook_time_preference_hrs is not None:

            try:
                hours = float(
                    cook_time_preference_hrs
                )

                if not 0 <= hours < float("inf"):
                    raise ValueError(
                        "cook_time_preference_hrs must "
                        "be a finite non-negative number."
                    )

                max_cooking_time = hours * 60

            except (TypeError, ValueError):
                raise ValueError(
                    "Invalid cook_time_preference_hrs "
                    "in User State."
                )

        return {
            "dietary_restrictions":
                dietary_restrictions,

            "preferred_cuisines":
                preferred_cuisines,

            "preferred_meal_types":
                preferred_meal_types,

            "max_cooking_time":
                max_cooking_time,
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
        Extract current meal slot.

        Manager cooking-time constraint overrides
        User State cooking-time preference.
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
        # USER STATE FALLBACK
        # ----------------------------------------------------

        if max_cooking_time is None:

            max_cooking_time = requirements.get(
                "max_cooking_time"
            )

        # ----------------------------------------------------
        # MEAL TYPE FALLBACK
        # ----------------------------------------------------

        if not meal_type:

            preferred_meal_types = requirements[
                "preferred_meal_types"
            ]

            if len(preferred_meal_types) == 1:
                meal_type = preferred_meal_types[0]

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
            "date": slot_date,
            "meal_type": meal_type,
            "max_cooking_time": max_cooking_time,
        }

    # ========================================================
    # MANAGER SELECTED RECIPES
    # ========================================================

    @staticmethod
    def _normalize_selected_recipe_ids(
        selected_recipe_ids,
    ):

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

            if (
                recipe_id
                and recipe_id not in normalized_ids
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

        normalized_cuisines = []

        for cuisine in _as_list(
            recent_cuisines
        ):

            if cuisine is None:
                continue

            if not str(cuisine).strip():
                continue

            normalized_cuisine = normalize(
                cuisine
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
        Reuse existing candidate_recipe.py filters.
        """

        diets = requirements[
            "dietary_restrictions"
        ]

        cuisines = requirements[
            "preferred_cuisines"
        ]

        # ----------------------------------------------------
        # SIMPLE CASE
        # ----------------------------------------------------

        if len(diets) <= 1:
            # Cuisine is a soft preference; variety ranking handles it later.
            return retrieve_candidates(
                diet=diets[0] if diets else None,
                meal_type=meal_type,
            )

        # ----------------------------------------------------
        # MULTIPLE REQUIREMENTS
        # ----------------------------------------------------

        candidates = load_recipe_kb()

        # Dietary restrictions
        for diet in diets:

            candidates = filter_by_diet(
                candidates,
                diet,
            )

            if candidates.empty:
                return candidates

        # Meal type
        if meal_type:

            candidates = filter_by_meal_type(
                candidates,
                meal_type,
            )

            if candidates.empty:
                return candidates

        # Cuisine preferences
        if cuisines:

            preferred_frames = []
            preferred_ids = set()

            for cuisine in cuisines:

                cuisine_candidates = filter_by_cuisine(
                    candidates,
                    cuisine,
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

                preferred = preferred.drop_duplicates(
                    subset=["recipe_id"]
                )

                remaining = candidates[
                    ~candidates[
                        "recipe_id"
                    ].isin(preferred_ids)
                ]

                candidates = pd.concat(
                    [
                        preferred,
                        remaining,
                    ],
                    ignore_index=True,
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

        if candidates.empty:
            return candidates

        if not selected_recipe_ids:
            return candidates

        if "recipe_id" not in candidates.columns:
            raise KeyError(
                "recipe_id column is missing."
            )

        selected_set = set(
            selected_recipe_ids
        )

        candidate_ids = (
            candidates["recipe_id"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        return candidates[
            ~candidate_ids.isin(selected_set)
        ].copy()

    # ========================================================
    # COOKING TIME FILTER
    # ========================================================

    
    def _apply_cooking_time(
        self,
        candidates,
        max_cooking_time,
    ):
        """
        Apply cooking-time filtering using the existing Recipe KB.

        If cooking_time_min is missing from the candidate DataFrame,
        retrieve it from the Recipe KB using recipe_id.

        Rules:
        - No time limit: keep all candidates.
        - Known cooking time <= limit: keep recipe.
        - Missing, invalid or excessive cooking time: exclude recipe.
        - No matching recipes: return an empty DataFrame.
        """

        warnings = []

        if candidates.empty:
            return candidates.copy(), warnings

        if max_cooking_time is None:
            return candidates.copy(), warnings

        try:
            limit = float(max_cooking_time)
        except (TypeError, ValueError):
            raise ValueError("Invalid cooking-time limit.")

        if not 0 <= limit < float("inf"):
            raise ValueError("Invalid cooking-time limit.")

        candidates = candidates.copy()

        if "recipe_id" not in candidates.columns:
            raise KeyError("recipe_id missing from candidates.")

        candidates["recipe_id"] = (
            candidates["recipe_id"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        # ========================================================
        # LOAD COOKING TIMES FROM RECIPE KB
        # ========================================================

        if "cooking_time_min" not in candidates.columns:

            print(
                "[TIME] Cooking-time column missing "
                "from candidates. Loading from Recipe KB."
            )

            recipe_kb = load_recipe_kb()

            if "cooking_time_min" not in recipe_kb.columns:
                warnings.append(
                    "cooking_time_min is missing from Recipe KB."
                )
                return candidates.iloc[0:0].copy(), warnings

            time_lookup = recipe_kb[
                ["recipe_id", "cooking_time_min"]
            ].copy()

            time_lookup["recipe_id"] = (
                time_lookup["recipe_id"]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            time_lookup = time_lookup.drop_duplicates(
                subset=["recipe_id"],
                keep="first"
            )

            candidates = candidates.merge(
                time_lookup,
                on="recipe_id",
                how="left",
                validate="many_to_one"
            )

        # ========================================================
        # FILTER USING COOKING TIME
        # ========================================================

        cooking_times = pd.to_numeric(
            candidates["cooking_time_min"],
            errors="coerce"
        )

        valid_mask = (
            cooking_times.notna()
            & cooking_times.ge(0)
            & cooking_times.le(limit)
        )

        filtered = candidates.loc[valid_mask].copy()

        print("\n========== COOKING TIME FILTER ==========")
        print("Maximum cooking time:", limit, "minutes")
        print("Candidates before:", len(candidates))
        print("Candidates with known times:", cooking_times.notna().sum())
        print("Candidates after:", len(filtered))

        if filtered.empty:
            warnings.append(
                "No recipes satisfy the cooking-time limit."
            )

        return filtered, warnings


    # ========================================================
    # CUISINE IDS
    # ========================================================

    @staticmethod
    def _cuisine_recipe_ids(
        candidates,
        cuisine,
    ):

        if candidates.empty:
            return set()

        matching = filter_by_cuisine(
            candidates,
            cuisine,
        )

        if matching.empty:
            return set()

        return set(
            matching["recipe_id"]
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

        if candidates.empty:
            return candidates

        if (
            not preferred_cuisines
            and not recent_cuisines
        ):
            return candidates

        ranked = candidates.copy()

        ranked["_original_order"] = range(
            len(ranked)
        )

        ranked["_variety_score"] = 0

        # Preferred cuisine boost
        for cuisine in preferred_cuisines:

            matching_ids = self._cuisine_recipe_ids(
                candidates,
                cuisine,
            )

            if not matching_ids:
                continue

            normalized_ids = (
                ranked["recipe_id"]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            ranked.loc[
                normalized_ids.isin(matching_ids),
                "_variety_score",
            ] += 1

        # Recent cuisine penalty
        for cuisine in recent_cuisines:

            matching_ids = self._cuisine_recipe_ids(
                candidates,
                cuisine,
            )

            if not matching_ids:
                continue

            normalized_ids = (
                ranked["recipe_id"]
                .astype(str)
                .str.strip()
                .str.upper()
            )

            ranked.loc[
                normalized_ids.isin(matching_ids),
                "_variety_score",
            ] -= 1

        ranked = ranked.sort_values(
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

        ranked = ranked.drop(
            columns=[
                "_variety_score",
                "_original_order",
            ]
        )

        return ranked

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    @staticmethod
    def _remove_duplicate_recipes(
        candidates,
    ):

        if candidates.empty:
            return candidates

        if "recipe_id" not in candidates.columns:
            raise KeyError(
                "recipe_id column is missing."
            )

        candidates = candidates.copy()

        candidates["recipe_id"] = (
            candidates["recipe_id"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        return candidates.drop_duplicates(
            subset=["recipe_id"],
            keep="first",
        )

    # ========================================================
    # FINAL REPETITION CHECK
    # ========================================================

    @staticmethod
    def _final_repetition_check(
        candidate_ids,
        selected_recipe_ids,
    ):

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

            if recipe_id in selected_set:
                continue

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
        Generate candidates for one meal slot.

        Cooking time is automatically read from
        User State unless Manager overrides it.
        """

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
        # EXTRACT REQUIREMENTS
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

        except (TypeError, ValueError) as error:

            return self._failure_result(
                error
            )

        # ----------------------------------------------------
        # CANDIDATE PIPELINE
        # ----------------------------------------------------

        try:

            candidates = self._retrieve_candidates(
                requirements,
                slot_context["meal_type"],
            )

            # A valid request with no matching recipes is NOT an agent failure.
            # Keep the Manager output contract and save a diagnostic report.
            if candidates.empty:
                self._save_rejection_report(
                    slot_context,
                    rejected_candidates=[],
                    ranked_candidates=[],
                    notes=["No recipes match the dietary and meal-type constraints."],
                )
                return {
                    "slot": {
                        "date": slot_context["date"],
                        "meal_type": slot_context["meal_type"],
                    },
                    "candidate_recipe_ids": [],
                }

            # Semantic retrieval narrows eligible candidates only when requested.
            # All existing structured filters, time limits and ranking remain active.
            if self.rag is not None and not candidates.empty:
                semantic_query = build_semantic_query(user_state, slot_context["meal_type"])
                print("[RAG] Generated query:", semantic_query)
                # Rank all indexed recipes to avoid losing feasible recipes in a small top-k.
                semantic = self.rag.retrieve(query=semantic_query, top_k=len(self.rag.documents))
                ranked_ids = [str(x).strip().upper() for x in semantic.candidate_recipe_ids]
                order = {rid: i for i, rid in enumerate(ranked_ids)}
                candidates = candidates.copy()
                normalized = candidates["recipe_id"].astype(str).str.strip().str.upper()
                candidates["_semantic_order"] = normalized.map(order)
                candidates = candidates[candidates["_semantic_order"].notna()]
                candidates = candidates.sort_values("_semantic_order", kind="stable").drop(columns=["_semantic_order"])
                print("[RAG] Eligible ranked candidates:", len(candidates))

            candidates = self._exclude_selected_recipes(
                candidates,
                selected_recipe_ids,
            )

            print("[TIME] Candidates before filtering:", len(candidates))
            print("[TIME] Effective limit (minutes):", slot_context["max_cooking_time"])
            if "cooking_time_min" in candidates.columns:
                observed_times = pd.to_numeric(
                    candidates["cooking_time_min"], errors="coerce"
                )
                print("[TIME] Known times:", int(observed_times.notna().sum()))
                print("[TIME] Missing/invalid times:", int(observed_times.isna().sum()))
                if slot_context["max_cooking_time"] is not None:
                    within_limit = (
                        observed_times.ge(0)
                        & observed_times.le(float(slot_context["max_cooking_time"]))
                    )
                    print("[TIME] Within limit:", int(within_limit.sum()))
            else:
                print("[TIME] cooking_time_min column is missing")

            before_time = candidates.copy()
            candidates, time_warnings = (
                self._apply_cooking_time(
                    candidates,
                    slot_context["max_cooking_time"],
                )
            )
            print("[TIME] Candidates after filtering:", len(candidates))
            kept_ids = set(candidates["recipe_id"].astype(str).str.upper())
            time_rejected = []
            for _, record in before_time.iterrows():
                rid = str(record["recipe_id"]).strip().upper()
                if rid not in kept_ids:
                    time_rejected.append({"recipe_id": rid, "reasons": ["Cooking time missing or exceeds limit"]})
            for warning in time_warnings:
                print("[TIME] Warning:", warning)

            candidates = self._remove_duplicate_recipes(
                candidates
            )

            # Recipe suitability and scoring; price and allergy checks are excluded.
            eligible, check_rejected = self.recipe_check.evaluate(
                candidates, user_state, slot_context["meal_type"],
                recent_cuisines, slot_context["max_cooking_time"],
            )
            check_rejected = time_rejected + check_rejected
            check_scores = {item["recipe_id"]: item for item in eligible}
            candidates = candidates[
                candidates["recipe_id"].astype(str).str.upper().isin(check_scores)
            ].copy()
            candidates["_recipe_score"] = candidates["recipe_id"].astype(str).str.upper().map(
                lambda rid: check_scores[rid]["score"]
            )
            candidates = candidates.sort_values("_recipe_score", ascending=False, kind="stable")
            candidates = candidates.drop(columns=["_recipe_score"])

            # Keep the existing variety method available, but combined scoring uses the
            # combined score to avoid overriding nutrition and reuse ranking.
            # Cuisine variety is already part of combined scoring.

        except (
            ValueError,
            KeyError,
            FileNotFoundError,
        ) as error:

            return self._failure_result(
                error
            )

        # ----------------------------------------------------
        # GET CANDIDATE IDS
        # ----------------------------------------------------

        if "recipe_id" in candidates.columns:

            candidate_ids = (
                candidates["recipe_id"]
                .astype(str)
                .str.strip()
                .str.upper()
                .tolist()
            )

        else:
            candidate_ids = []

        candidate_ids = (
            self._final_repetition_check(
                candidate_ids,
                selected_recipe_ids,
            )
        )

        candidate_ids = candidate_ids[:limit]

        self._save_rejection_report(
            slot_context,
            rejected_candidates=check_rejected,
            ranked_candidates=[check_scores[rid] for rid in candidate_ids],
        )

        return {
            "slot": {
                "date": slot_context["date"],
                "meal_type": slot_context["meal_type"],
            },
            "candidate_recipe_ids": candidate_ids,
        }


# ============================================================
# LOAD LATEST USER STATE
# ============================================================

def load_latest_user_state():

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
        key=lambda path: path.stat().st_mtime,
    )

    with open(
        latest_user_state_file,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


# ============================================================
# STANDALONE INPUT
# ============================================================

def get_standalone_input():
    """
    Manager will eventually supply these values.

    The cooking-time limit is deliberately omitted
    so the User State preference is used automatically.
    """

    meal_slot = {
        "date": date.today().isoformat(),
        "meal_type": "dinner",
    }

    selected_recipe_ids = []

    recent_cuisines = []

    return (
        meal_slot,
        selected_recipe_ids,
        recent_cuisines,
    )


# ============================================================
# PRINT RESULT
# ============================================================

def print_recipe_result(result):
    """
    Print final Recipe Agent output and cooking times.
    """

    print("\n" + "=" * 70)
    print("RECIPE AGENT RESULT")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=4,
        )
    )

    candidate_ids = result.get(
        "candidate_recipe_ids",
        [],
    )

    if not candidate_ids:

        print("\nNo candidate recipes found.")
        return

    df = load_recipe_kb()

    if "cooking_time_min" not in df.columns:

        print(
            "\nCooking-time column is not available "
            "in the loaded recipe KB."
        )
        return

    df = df.copy()

    df["recipe_id"] = (
        df["recipe_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    print("\n" + "=" * 70)
    print("CANDIDATE RECIPE COOKING TIMES")
    print("=" * 70)

    for recipe_id in candidate_ids:

        matching = df[
            df["recipe_id"] == recipe_id
        ]

        if matching.empty:

            print(
                f"\nRecipe ID: {recipe_id}"
            )

            print(
                "Recipe not found."
            )

            continue

        recipe = matching.iloc[0]

        recipe_name = recipe.get(
            "recipe_name",
            "Unknown Recipe",
        )

        cooking_time = pd.to_numeric(
            recipe.get("cooking_time_min"),
            errors="coerce",
        )

        print(
            f"\nRecipe ID    : {recipe_id}"
        )

        print(
            f"Recipe Name  : {recipe_name}"
        )

        if pd.notna(cooking_time):

            print(
                f"Cooking Time : "
                f"{cooking_time:g} minutes"
            )

        else:

            print(
                "Cooking Time : Not available"
            )

    print("\n" + "=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():
    # Suppress internal diagnostic prints in standalone mode.
    with contextlib.redirect_stdout(io.StringIO()):
        user_state = load_latest_user_state()
        from src.knowledge.recipe_rag import RecipeRAG
        rag = RecipeRAG()
        index_path = Path(__file__).resolve().parents[2] / "data" / "processed" / "recipe_numpy.npz"
        if index_path.exists():
            try:
                rag.load_index(index_path)
            except (ValueError, RuntimeError, FileNotFoundError):
                rag.build_index()
                rag.save_index(index_path)
        else:
            rag.build_index()
            rag.save_index(index_path)
        recipe_agent = RecipeAgent(max_candidates=5, rag=rag)
        meal_slot, selected_recipe_ids, recent_cuisines = get_standalone_input()
        result = recipe_agent.run(
            user_state=user_state,
            meal_slot=meal_slot,
            selected_recipe_ids=selected_recipe_ids,
            recent_cuisines=recent_cuisines,
            max_candidates=5,
        )
    print_recipe_result(result)


if __name__ == "__main__":
    main()
