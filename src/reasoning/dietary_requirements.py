"""
Member 2:

Dietary + Allergy hard constraints
Preference soft score
"""

import ast
import json
from pathlib import Path

import pandas as pd

from src.knowledge.repository import (
    CUISINE_GROUPS,
    normalize,
)

from scripts.mapping_retrieval_query import (
    get_recipe_ingredients,
)


# ============================================================
# PROJECT PATH
# ============================================================

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


# ============================================================
# USER INPUT ALIASES
# ============================================================

DIET_ALIASES = {
    "nonvegetarian": "non vegetarian",
    "non veg": "non vegetarian",
    "low sodium diet": "low sodium",
    "high fibre": "high fiber",
    "high fibre diet": "high fiber",
    "low carbohydrate": "low carb",
    "low carbohydrate diet": "low carb",
    "high protein diet": "high protein",
    "low fat diet": "low fat",
    "gluten free diet": "gluten free",
    "dairy free diet": "dairy free",
}


ALLERGEN_ALIASES = {
    "peanuts": "peanut",
    "groundnut": "peanut",
    "groundnuts": "peanut",

    "tree nuts": "tree nut",
    "nuts": "tree nut",

    "dairy": "milk",
    "milk/dairy": "milk",

    "eggs": "egg",

    "soya": "soy",
    "soybean": "soy",

    "wheat/gluten": "gluten",

    "shell fish": "shellfish",

    "sulphite": "sulfites",
    "sulphites": "sulfites",
}


# ============================================================
# ALLERGEN RULES
# ============================================================

ALLERGEN_RULES = {

    "peanut": {
        "free_label": "peanut free",
        "cautions": {"peanuts"},
        "terms": {
            "peanut",
            "groundnut",
        },
    },

    "tree nut": {
        "free_label": "tree nut free",
        "cautions": {"tree nuts"},
        "terms": {
            "almond",
            "cashew",
            "walnut",
            "pecan",
            "pistachio",
            "hazelnut",
            "macadamia",
            "brazil nut",
        },
    },

    "milk": {
        "free_label": "dairy free",
        "cautions": {"milk"},
        "terms": {
            "milk",
            "buttermilk",
            "cheese",
            "butter",
            "cream",
            "yogurt",
            "whey",
            "casein",
            "ghee",
        },
    },

    "egg": {
        "free_label": "egg free",
        "cautions": {"eggs"},
        "terms": {
            "egg",
        },
    },

    "soy": {
        "free_label": "soy free",
        "cautions": {"soy"},
        "terms": {
            "soy",
            "soya",
            "soybean",
            "tofu",
            "miso",
            "tempeh",
            "edamame",
        },
    },

    "wheat": {
        "free_label": "gluten free",
        "cautions": {
            "wheat",
            "gluten",
        },
        "terms": {
            "wheat",
        },
    },

    "gluten": {
        "free_label": "gluten free",
        "cautions": {
            "gluten",
            "wheat",
        },
        "terms": {
            "wheat",
            "gluten",
            "barley",
            "rye",
        },
    },

    "fish": {
        "free_label": "fish free",
        "cautions": set(),
        "terms": {
            "fish",
            "salmon",
            "tuna",
            "anchovy",
            "sardine",
            "cod",
            "trout",
            "haddock",
            "mackerel",
        },
    },

    "shellfish": {
        "free_label": "shellfish free",
        "cautions": {"shellfish"},
        "terms": {
            "shellfish",
            "shrimp",
            "prawn",
            "crab",
            "lobster",
            "crayfish",
            "crawfish",
        },
    },

    "sesame": {
        "free_label": None,
        "cautions": set(),
        "terms": {
            "sesame",
            "tahini",
        },
    },

    "sulfites": {
        "free_label": None,
        "cautions": {"sulfites"},
        "terms": {
            "sulfite",
            "sulfites",
        },
    },

    "fodmap": {
        "free_label": None,
        "cautions": {"fodmap"},
        "terms": set(),
    },
}


# ============================================================
# GENERAL HELPERS
# ============================================================

def _as_list(value):
    """
    Convert CSV/list-like values into a Python list.
    """

    if value is None:
        return []

    if isinstance(
        value,
        (list, tuple, set)
    ):
        return list(value)

    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass

    if isinstance(value, str):

        value = value.strip()

        if not value:
            return []

        for parser in (
            json.loads,
            ast.literal_eval,
        ):

            try:

                parsed = parser(value)

                if isinstance(
                    parsed,
                    (list, tuple, set)
                ):
                    return list(parsed)

            except (
                ValueError,
                SyntaxError,
                TypeError,
                json.JSONDecodeError,
            ):
                pass

        return [value]

    return [value]


def _normalized_set(value):
    """
    Normalize a list-like recipe field.
    """

    return {
        normalize(item)
        for item in _as_list(value)
        if str(item).strip()
    }


def _get_user_field(
    user_state,
    key,
    default=None
):
    """
    Read a field from either the User State object
    or the saved User State JSON dictionary.
    """

    if isinstance(
        user_state,
        dict
    ):
        return user_state.get(
            key,
            default
        )

    return getattr(
        user_state,
        key,
        default
    )


def _get_user_list(
    user_state,
    key
):
    """
    Retrieve and normalize a list from User State.
    """

    value = _get_user_field(
        user_state,
        key,
        []
    )

    return [
        normalize(item)
        for item in _as_list(value)
        if str(item).strip()
    ]


def _to_bool(value):
    """
    Safely convert recipe boolean-like values.
    """

    if value is None:
        return None

    try:

        if pd.isna(value):
            return None

    except (TypeError, ValueError):
        pass

    if isinstance(value, bool):
        return value

    value = normalize(value)

    if value in {
        "true",
        "1",
        "yes",
    }:
        return True

    if value in {
        "false",
        "0",
        "no",
    }:
        return False

    return None


def _phrase_match(
    text,
    term
):
    """
    Match complete ingredient words/phrases.

    peanut -> peanut butter = match
    egg -> eggplant = no match
    wheat -> buckwheat = no match
    """

    return (
        f" {normalize(term)} "
        in
        f" {normalize(text)} "
    )


# ============================================================
# LOAD USER STATE
# ============================================================

def load_user_state(
    user_id=None
):
    """
    Load the actual User State JSON created by user_state.py.

    Expected directory:

        data/users/

    If user_id is supplied:
        user_state_<user_id>.json is loaded.

    Otherwise:
        the most recently modified User State JSON is loaded.
    """

    users_dir = (
        PROJECT_ROOT
        / "data"
        / "users"
    )

    if not users_dir.exists():

        raise FileNotFoundError(
            f"User State directory not found: "
            f"{users_dir}"
        )

    # --------------------------------------------------------
    # SPECIFIC USER
    # --------------------------------------------------------

    if user_id:

        user_state_file = (
            users_dir
            / f"user_state_{user_id}.json"
        )

        if not user_state_file.exists():

            raise FileNotFoundError(
                f"User State not found: "
                f"{user_state_file}"
            )

    # --------------------------------------------------------
    # MOST RECENT USER STATE
    # --------------------------------------------------------

    else:

        user_state_files = list(
            users_dir.glob(
                "user_state_*.json"
            )
        )

        if not user_state_files:

            raise FileNotFoundError(
                "No User State JSON files found in "
                f"{users_dir}"
            )

        user_state_file = max(
            user_state_files,
            key=lambda path:
                path.stat().st_mtime
        )

    # --------------------------------------------------------
    # READ USER STATE
    # --------------------------------------------------------

    with open(
        user_state_file,
        "r",
        encoding="utf-8"
    ) as file:

        user_state = json.load(
            file
        )

    return (
        user_state,
        user_state_file
    )


# ============================================================
# RECIPE INGREDIENT LOOKUP
# ============================================================

def _get_recipe_ingredients(recipe):
    """
    Retrieve actual recipe ingredients using the existing
    mapping_retrieval_query.py module.
    """

    recipe_id = str(
        recipe.get(
            "recipe_id",
            ""
        )
    ).strip().upper()

    if not recipe_id:
        return set()

    try:

        ingredient_df = (
            get_recipe_ingredients(
                recipe_id
            )
        )

    except (
        ValueError,
        FileNotFoundError,
    ):
        return set()

    if ingredient_df.empty:
        return set()

    if (
        "ingredient_name"
        not in ingredient_df.columns
    ):
        return set()

    return {
        normalize(name)
        for name
        in ingredient_df[
            "ingredient_name"
        ].dropna()
        if str(name).strip()
    }


# ============================================================
# HARD CONSTRAINT 1 - DIET
# ============================================================

def check_diet_constraint(
    recipe,
    user_state
):
    """
    HARD constraint.

    Gets dietary input directly from:

        user_state["dietary_restrictions"]

    All dietary requirements must pass.
    """

    requirements = _get_user_list(
        user_state,
        "dietary_restrictions"
    )

    requirements = [
        DIET_ALIASES.get(
            requirement,
            requirement
        )
        for requirement
        in requirements
    ]

    if not requirements:

        return {
            "constraint": "diet",
            "passed": True,
            "reason":
                "No dietary restriction specified",
        }

    diet_labels = _normalized_set(
        recipe.get(
            "diet_labels"
        )
    )

    health_labels = _normalized_set(
        recipe.get(
            "health_labels"
        )
    )

    labels = (
        diet_labels
        | health_labels
    )

    is_vegetarian = _to_bool(
        recipe.get(
            "is_vegetarian"
        )
    )

    is_vegan = _to_bool(
        recipe.get(
            "is_vegan"
        )
    )

    failed = []

    for requirement in requirements:

        # ----------------------------------------------------
        # VEGETARIAN
        # ----------------------------------------------------

        if requirement == "vegetarian":

            passed = (
                is_vegetarian is True
                or is_vegan is True
                or "vegetarian"
                in health_labels
                or "vegan"
                in health_labels
            )

        # ----------------------------------------------------
        # VEGAN
        # ----------------------------------------------------

        elif requirement == "vegan":

            passed = (
                is_vegan is True
                or "vegan"
                in health_labels
            )

        # ----------------------------------------------------
        # NON VEGETARIAN
        # ----------------------------------------------------

        elif requirement == "non vegetarian":

            passed = (
                is_vegetarian is False
            )

        # ----------------------------------------------------
        # OTHER DIET LABELS
        # ----------------------------------------------------

        else:

            passed = (
                requirement
                in labels
            )

        if not passed:

            failed.append(
                requirement
            )

    if failed:

        return {
            "constraint": "diet",
            "passed": False,
            "reason":
                "Recipe does not satisfy "
                "dietary requirement(s): "
                + ", ".join(failed),
        }

    return {
        "constraint": "diet",
        "passed": True,
        "reason":
            "Recipe satisfies dietary "
            "requirement(s): "
            + ", ".join(requirements),
    }


# ============================================================
# HARD CONSTRAINT 2 - ALLERGY
# ============================================================

def check_allergen_constraint(
    recipe,
    user_state
):
    """
    HARD constraint.

    Gets allergy input directly from:

        user_state["allergies"]

    Checks:

        1. actual mapped ingredients
        2. recipe cautions
        3. health/free labels

    Actual ingredient/caution conflicts override
    free health labels.
    """

    allergens = _get_user_list(
        user_state,
        "allergies"
    )

    allergens = [
        ALLERGEN_ALIASES.get(
            allergen,
            allergen
        )
        for allergen
        in allergens
    ]

    allergens = list(
        dict.fromkeys(
            allergens
        )
    )

    if not allergens:

        return {
            "constraint": "allergy",
            "passed": True,
            "status": "safe",
            "alert": False,
            "reason":
                "No allergies specified",
        }

    health_labels = _normalized_set(
        recipe.get(
            "health_labels"
        )
    )

    cautions = _normalized_set(
        recipe.get(
            "cautions"
        )
    )

    ingredients = (
        _get_recipe_ingredients(
            recipe
        )
    )

    conflicts = {}
    uncertain = []

    for allergen in allergens:

        rule = ALLERGEN_RULES.get(
            allergen
        )

        # ----------------------------------------------------
        # UNKNOWN ALLERGEN
        # ----------------------------------------------------

        if rule is None:

            rule = {
                "free_label":
                    f"{allergen} free",

                "cautions":
                    {allergen},

                "terms":
                    {allergen},
            }

        matches = []

        # ----------------------------------------------------
        # 1. CHECK ACTUAL INGREDIENTS
        # ----------------------------------------------------

        for ingredient in ingredients:

            if any(
                _phrase_match(
                    ingredient,
                    term
                )
                for term
                in rule["terms"]
            ):

                matches.append(
                    f"ingredient: {ingredient}"
                )

        # ----------------------------------------------------
        # 2. CHECK RECIPE CAUTIONS
        # ----------------------------------------------------

        for caution in cautions:

            if (
                caution
                in rule["cautions"]
            ):

                matches.append(
                    f"caution: {caution}"
                )

                continue

            if any(
                _phrase_match(
                    caution,
                    term
                )
                for term
                in rule["terms"]
            ):

                matches.append(
                    f"caution: {caution}"
                )

        # ----------------------------------------------------
        # HARD CONFLICT FOUND
        # ----------------------------------------------------

        if matches:

            conflicts[
                allergen
            ] = sorted(
                set(matches)
            )

            continue

        # ----------------------------------------------------
        # 3. CHECK FREE HEALTH LABEL
        # ----------------------------------------------------

        free_label = (
            rule["free_label"]
        )

        if (
            free_label
            and free_label
            in health_labels
        ):

            continue

        # No conflict found, but safety cannot
        # be positively verified.
        uncertain.append(
            allergen
        )

    # --------------------------------------------------------
    # ALLERGEN CONFLICT
    # --------------------------------------------------------

    if conflicts:

        details = "; ".join(
            f"{allergen}: "
            + ", ".join(matches)

            for allergen, matches
            in conflicts.items()
        )

        return {
            "constraint": "allergy",
            "passed": False,
            "status": "conflict",
            "alert": True,
            "reason":
                "Recipe conflicts with "
                "allergy requirement(s): "
                + details,
        }

    # --------------------------------------------------------
    # UNKNOWN SAFETY
    # --------------------------------------------------------

    if uncertain:

        return {
            "constraint": "allergy",
            "passed": False,
            "status": "unknown",
            "alert": True,
            "reason":
                "Allergy safety could not be "
                "verified for: "
                + ", ".join(uncertain),
        }

    # --------------------------------------------------------
    # SAFE
    # --------------------------------------------------------

    return {
        "constraint": "allergy",
        "passed": True,
        "status": "safe",
        "alert": False,
        "reason":
            "Recipe satisfies specified "
            "allergy requirements",
    }


# ============================================================
# SOFT SCORE - PREFERENCE
# ============================================================

def _cuisine_matches(
    preferred_cuisine,
    recipe_cuisines
):
    """
    Match exact cuisine or existing broad cuisine groups.
    """

    accepted = (
        CUISINE_GROUPS.get(
            preferred_cuisine,
            {preferred_cuisine}
        )
    )

    return bool(
        accepted
        & recipe_cuisines
    )


def calculate_preference_score(
    recipe,
    user_state
):
    """
    SOFT score.

    Gets preference input directly from:

        user_state["preferred_cuisines"]
        user_state["disliked_ingredients"]

    Preferred cuisine increases score.

    Disliked ingredients decrease score but do not
    hard-reject the recipe.
    """

    preferred_cuisines = (
        _get_user_list(
            user_state,
            "preferred_cuisines"
        )
    )

    disliked_ingredients = (
        _get_user_list(
            user_state,
            "disliked_ingredients"
        )
    )

    recipe_cuisines = (
        _normalized_set(
            recipe.get(
                "cuisine_type"
            )
        )
    )

    # --------------------------------------------------------
    # CUISINE MATCH
    # --------------------------------------------------------

    matched_cuisines = [
        cuisine

        for cuisine
        in preferred_cuisines

        if _cuisine_matches(
            cuisine,
            recipe_cuisines
        )
    ]

    # --------------------------------------------------------
    # DISLIKED INGREDIENT MATCH
    # --------------------------------------------------------

    ingredients = set()

    if disliked_ingredients:

        ingredients = (
            _get_recipe_ingredients(
                recipe
            )
        )

    matched_dislikes = []

    for dislike in disliked_ingredients:

        if any(
            _phrase_match(
                ingredient,
                dislike
            )

            for ingredient
            in ingredients
        ):

            matched_dislikes.append(
                dislike
            )

    matched_dislikes = sorted(
        set(
            matched_dislikes
        )
    )

    # ========================================================
    # MVP PREFERENCE SCORE
    #
    # Neutral baseline = 0.5
    # Cuisine match    = up to +0.5
    # Disliked item    = -0.25 each
    # ========================================================

    score = 0.5

    if preferred_cuisines:

        match_ratio = (
            len(
                matched_cuisines
            )
            /
            len(
                preferred_cuisines
            )
        )

        score += (
            0.5
            * match_ratio
        )

    score -= (
        0.25
        * len(
            matched_dislikes
        )
    )

    score = max(
        0.0,
        min(
            1.0,
            score
        )
    )

    reasons = []

    if preferred_cuisines:

        if matched_cuisines:

            reasons.append(
                "preferred cuisine matched: "
                + ", ".join(
                    matched_cuisines
                )
            )

        else:

            reasons.append(
                "no preferred cuisine matched"
            )

    if matched_dislikes:

        reasons.append(
            "disliked ingredient(s) present: "
            + ", ".join(
                matched_dislikes
            )
        )

    if not reasons:

        reasons.append(
            "no preference signal supplied"
        )

    return {
        "score_type":
            "preference",

        "score":
            round(
                score,
                4
            ),

        "matched_cuisines":
            matched_cuisines,

        "matched_disliked_ingredients":
            matched_dislikes,

        "reason":
            "; ".join(
                reasons
            ),
    }


# ============================================================
# COMPLETE MEMBER 2 EVALUATION
# ============================================================

def evaluate_dietary_requirements(
    recipe,
    user_state
):
    """
    Evaluate one candidate recipe using the actual
    User State input.
    """

    diet_result = (
        check_diet_constraint(
            recipe,
            user_state
        )
    )

    allergy_result = (
        check_allergen_constraint(
            recipe,
            user_state
        )
    )

    preference_result = (
        calculate_preference_score(
            recipe,
            user_state
        )
    )

    return {
        "user_id":
            _get_user_field(
                user_state,
                "user_id"
            ),

        "recipe_id":
            recipe.get(
                "recipe_id"
            ),

        "recipe_name":
            recipe.get(
                "recipe_name"
            ),

        "hard_constraints_passed":
            (
                diet_result["passed"]
                and
                allergy_result["passed"]
            ),

        "diet":
            diet_result,

        "allergy":
            allergy_result,

        "preference":
            preference_result,
    }


# ============================================================
# SAVE RESULT TO JSON
# ============================================================

def save_dietary_evaluation(
    result
):
    """
    Save output to:

        data/dietary_requirements/
        dietary_result_<recipe_id>.json
    """

    output_dir = (
        PROJECT_ROOT
        / "data"
        / "dietary_requirements"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    recipe_id = str(
        result.get(
            "recipe_id",
            "unknown"
        )
    ).strip().upper()

    output_file = (
        output_dir
        / f"dietary_result_{recipe_id}.json"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=4,
            ensure_ascii=False
        )

    return output_file


# ============================================================
# PRINT RESULT
# ============================================================

def print_dietary_evaluation(
    result
):
    """
    Print dietary evaluation in a compact format.
    """

    print("\n" + "=" * 70)
    print("DIETARY REQUIREMENT EVALUATION")
    print("=" * 70)

    print(
        f"User ID    : "
        f"{result.get('user_id')}"
    )

    print(
        f"Recipe     : "
        f"{result.get('recipe_id')} | "
        f"{result.get('recipe_name')}"
    )

    # --------------------------------------------------------
    # HARD CONSTRAINTS
    # --------------------------------------------------------

    print("\n[HARD CONSTRAINTS]")

    diet = result[
        "diet"
    ]

    print(
        "Diet       : "
        + (
            "PASS"
            if diet["passed"]
            else "FAIL"
        )
    )

    print(
        f"Reason     : "
        f"{diet['reason']}"
    )

    allergy = result[
        "allergy"
    ]

    print(
        "Allergy    : "
        + (
            "PASS"
            if allergy["passed"]
            else "FAIL"
        )
    )

    print(
        f"Status     : "
        f"{allergy.get('status')}"
    )

    print(
        f"Reason     : "
        f"{allergy['reason']}"
    )

    if allergy.get(
        "alert",
        False
    ):

        print(
            "ALERT      : ALLERGY WARNING"
        )

    # --------------------------------------------------------
    # SOFT SCORE
    # --------------------------------------------------------

    print("\n[SOFT SCORE]")

    preference = result[
        "preference"
    ]

    print(
        f"Preference : "
        f"{preference['score']}"
    )

    print(
        f"Reason     : "
        f"{preference['reason']}"
    )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    print("\n[FINAL RESULT]")

    print(
        "Eligible   : "
        + (
            "YES"
            if result[
                "hard_constraints_passed"
            ]
            else "NO"
        )
    )

    print("=" * 70)


# ============================================================
# DIRECT RUN
# ============================================================

if __name__ == "__main__":

    from scripts.candidate_recipe import (
        load_recipe_kb,
    )

    print(
        "Running dietary requirements evaluation..."
    )

    # --------------------------------------------------------
    # 1. LOAD ACTUAL USER STATE
    # --------------------------------------------------------

    try:

        user_state, user_state_file = (
            load_user_state()
        )

    except FileNotFoundError as error:

        print(
            f"ERROR: {error}"
        )

        raise SystemExit(1)

    print(
        "\nUser State loaded from:"
    )

    print(
        user_state_file
    )

    # --------------------------------------------------------
    # 2. DISPLAY INPUT FROM USER STATE
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("INPUT FROM USER STATE")
    print("=" * 70)

    print(
        f"User ID    : "
        f"{user_state.get('user_id')}"
    )

    print(
        f"Diet       : "
        f"{user_state.get('dietary_restrictions', [])}"
    )

    print(
        f"Allergies  : "
        f"{user_state.get('allergies', [])}"
    )

    print(
        f"Cuisines   : "
        f"{user_state.get('preferred_cuisines', [])}"
    )

    print(
        f"Dislikes   : "
        f"{user_state.get('disliked_ingredients', [])}"
    )

    # --------------------------------------------------------
    # 3. LOAD RECIPE
    # --------------------------------------------------------

    df = load_recipe_kb()

    recipe_id = "R03943"

    recipe_rows = df[
        df["recipe_id"]
        == recipe_id
    ]

    if recipe_rows.empty:

        print(
            f"Recipe {recipe_id} not found."
        )

        raise SystemExit(1)

    recipe = (
        recipe_rows
        .iloc[0]
        .to_dict()
    )

    print("\n" + "=" * 70)
    print("RECIPE INPUT")
    print("=" * 70)

    print(
        f"Recipe ID   : "
        f"{recipe.get('recipe_id')}"
    )

    print(
        f"Recipe Name : "
        f"{recipe.get('recipe_name')}"
    )

    # --------------------------------------------------------
    # 4. EVALUATE RECIPE
    # --------------------------------------------------------

    result = (
        evaluate_dietary_requirements(
            recipe,
            user_state
        )
    )

    # --------------------------------------------------------
    # 5. PRINT RESULT
    # --------------------------------------------------------

    print_dietary_evaluation(
        result
    )

    # --------------------------------------------------------
    # 6. SAVE JSON RESULT
    # --------------------------------------------------------

    output_file = (
        save_dietary_evaluation(
            result
        )
    )

    print(
        "\nJSON output saved to:"
    )

    print(
        output_file
    )