
"""Look up human-readable recipe names from the Recipe KB."""

import csv
import logging
import re

from functools import lru_cache
from pathlib import Path


logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RECIPE_KB = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "recipe_kb_clean.csv"
)


# ============================================================
# NORMALIZE RECIPE IDS
# ============================================================

def normalize_recipe_id(value):
    """Normalize recipe IDs before matching."""

    if value is None:
        return ""

    if isinstance(value, dict):
        value = (
            value.get("recipe_id")
            or value.get("id")
            or ""
        )

    value = str(value).strip().upper()

    # Remove invisible Unicode formatting characters.
    value = re.sub(
        r"[\u200b-\u200d\ufeff]",
        "",
        value,
    )

    # Normalize whitespace.
    value = re.sub(r"\s+", "", value)

    # Support numeric IDs such as R1296 -> R01296.
    match = re.fullmatch(r"R(\d+)", value)

    if match:
        value = f"R{int(match.group(1)):05d}"

    return value


# ============================================================
# LOAD RECIPE KB
# ============================================================

@lru_cache(maxsize=1)
def load_recipe_names():
    """Load recipe names indexed by normalized recipe ID."""

    recipe_names = {}

    print("\n[RECIPE LOOKUP] Loading Recipe KB")
    print("[RECIPE LOOKUP] Path:", RECIPE_KB)
    print("[RECIPE LOOKUP] Exists:", RECIPE_KB.exists())

    if not RECIPE_KB.is_file():
        logger.error(
            "Recipe KB not found: %s",
            RECIPE_KB,
        )
        return recipe_names

    with RECIPE_KB.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        print(
            "[RECIPE LOOKUP] CSV columns:",
            reader.fieldnames,
        )

        for row in reader:

            recipe_id = normalize_recipe_id(
                row.get("recipe_id")
            )

            recipe_name = str(
                row.get("recipe_name")
                or row.get("name")
                or row.get("title")
                or ""
            ).strip()

            if not recipe_id or not recipe_name:
                continue

            recipe_names[recipe_id] = recipe_name

    print(
        "[RECIPE LOOKUP] Loaded recipes:",
        len(recipe_names),
    )

    print("\n[RECIPE LOOKUP] Sample recipes:")

    for recipe_id, recipe_name in list(
        recipe_names.items()
    )[:5]:
        print(
            f"  {recipe_id} -> {recipe_name}"
        )

    return recipe_names


# ============================================================
# GET RECIPE NAME
# ============================================================

def get_recipe_name(recipe_id):
    """Return a human-readable recipe name."""

    if isinstance(recipe_id, dict):

        # Use an actual name already supplied by the Planner.
        direct_name = (
            recipe_id.get("recipe_name")
            or recipe_id.get("name")
            or recipe_id.get("title")
        )

        if direct_name:
            return str(direct_name).strip()

    normalized_id = normalize_recipe_id(recipe_id)

    if not normalized_id:
        return "Recipe details unavailable"

    recipes = load_recipe_names()

    recipe_name = recipes.get(normalized_id)

    if recipe_name:
        return recipe_name

    print(
        "[RECIPE LOOKUP] Unknown recipe ID:",
        repr(recipe_id),
    )

    print(
        "[RECIPE LOOKUP] Normalized ID:",
        repr(normalized_id),
    )

    print(
        "[RECIPE LOOKUP] Total available recipes:",
        len(recipes),
    )

    return "Recipe details unavailable"


# ============================================================
# DEBUG TEST
# ============================================================

if __name__ == "__main__":

    print("\n" + "=" * 65)
    print("RECIPE LOOKUP TEST")
    print("=" * 65)

    recipes = load_recipe_names()

    test_recipe_ids = [
        "R15279",
        "R32630",
        "R35174",
        "R01296",
        "R01485",
    ]

    for recipe_id in test_recipe_ids:

        name = get_recipe_name(recipe_id)

        print(
            f"{recipe_id:12} -> {name}"
        )

    print("\n" + "=" * 65)
    print("RECIPE LOOKUP TEST COMPLETE")
    print("=" * 65)
