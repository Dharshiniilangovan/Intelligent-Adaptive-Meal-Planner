
"""Look up human-readable recipe names from the Recipe KB."""

import csv
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RECIPE_KB = (
    PROJECT_ROOT / "data" / "processed" / "recipes_kb.csv"
)


@lru_cache(maxsize=1)
def load_recipe_names() -> dict[str, str]:
    """Load recipe IDs and names from the existing Recipe KB."""

    recipe_names = {}

    if not RECIPE_KB.exists():
        print(f"[RECIPE LOOKUP] File not found: {RECIPE_KB}")
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
            recipe_id = str(
                row.get("recipe_id") or ""
            ).strip().upper()

            recipe_name = str(
                row.get("recipe_name")
                or row.get("name")
                or row.get("title")
                or ""
            ).strip()

            if recipe_id and recipe_name:
                recipe_names[recipe_id] = recipe_name

    print(
        f"[RECIPE LOOKUP] Loaded {len(recipe_names)} recipes"
    )

    return recipe_names


def get_recipe_name(recipe_id: str) -> str:
    """Return the recipe name without exposing internal IDs."""

    if not recipe_id:
        return "Recipe details unavailable"

    recipe_id = str(recipe_id).strip().upper()

    name = load_recipe_names().get(recipe_id)

    if name:
        return name

    print(f"[RECIPE LOOKUP] Unknown recipe ID: {recipe_id}")

    return "Recipe details unavailable"


if __name__ == "__main__":
    print("\nRECIPE LOOKUP TEST")
    print("=" * 60)

    print("Recipe KB:", RECIPE_KB)

    test_recipe_ids = [
        "R15279",
        "R32630",
        "R35174",
        "R01296",
        "R01485",
    ]

    for recipe_id in test_recipe_ids:
        print(
            f"{recipe_id} -> {get_recipe_name(recipe_id)}"
        )

    print("=" * 60)
