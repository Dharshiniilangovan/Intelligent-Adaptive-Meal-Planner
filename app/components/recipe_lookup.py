
"""Look up recipe names and validated URLs from GC1 Recipe KB."""

import csv
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]

RECIPE_KB = ROOT / "data" / "processed" / "recipe_kb_clean.csv"

URL_REPORT = ROOT / "reports" / "recipe_url_validation_with_ids.csv"


def normalize_recipe_id(recipe_id):
    return str(recipe_id or "").strip().upper()


def safe_url(url):
    url = str(url or "").strip()
    parsed = urlparse(url)

    if (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.netloc
    ):
        return url

    return None


@lru_cache(maxsize=1)
def load_recipes():
    recipes = {}

    if not RECIPE_KB.is_file():
        print("[RECIPE LOOKUP] KB not found:", RECIPE_KB)
        return recipes

    with RECIPE_KB.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:

        for row in csv.DictReader(file):

            recipe_id = normalize_recipe_id(
                row.get("recipe_id")
            )

            if not recipe_id:
                continue

            recipes[recipe_id] = {
                "recipe_id": recipe_id,
                "recipe_name": str(
                    row.get("recipe_name") or ""
                ).strip(),
                "url": safe_url(row.get("url")),
            }

    print(
        "[RECIPE LOOKUP] Loaded",
        len(recipes),
        "recipes",
    )

    return recipes


@lru_cache(maxsize=1)
def load_url_validation():
    statuses = {}

    if not URL_REPORT.is_file():
        print(
            "[RECIPE LOOKUP] URL validation report missing:",
            URL_REPORT,
        )
        return statuses

    with URL_REPORT.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:

        for row in csv.DictReader(file):

            recipe_id = normalize_recipe_id(
                row.get("recipe_id")
            )

            if not recipe_id:
                continue

            statuses[recipe_id] = {
                "status": str(
                    row.get("status") or ""
                ).strip().lower(),
                "url": safe_url(row.get("url")),
                "final_url": safe_url(
                    row.get("final_url")
                ),
            }

    return statuses


def get_recipe_details(recipe_id):
    """Return recipe name and only a validated working URL."""

    recipe_id = normalize_recipe_id(recipe_id)

    recipe = load_recipes().get(recipe_id)

    if not recipe:
        return {
            "recipe_id": recipe_id,
            "recipe_name": "Recipe details unavailable",
            "url": None,
            "url_status": "unknown",
        }

    validation = load_url_validation().get(recipe_id)

    working_url = None
    status = "not_checked"

    if validation:
        status = validation["status"]

        # Require the validation record to match
        # the URL currently stored in the Recipe KB.
        if (
            status == "working"
            and validation["url"] == recipe["url"]
        ):
            working_url = (
                validation["final_url"]
                or recipe["url"]
            )

    return {
        "recipe_id": recipe_id,
        "recipe_name": (
            recipe["recipe_name"]
            or "Recipe details unavailable"
        ),
        "url": working_url,
        "url_status": status,
    }


def get_recipe_name(recipe_id):
    """Backward-compatible recipe name lookup."""

    return get_recipe_details(recipe_id)["recipe_name"]


def get_recipe_url(recipe_id):
    """Return only a URL that passed validation."""

    return get_recipe_details(recipe_id)["url"]


if __name__ == "__main__":

    for recipe_id in (
        "R15279",
        "R32630",
        "R35174",
        "R01296",
        "R01485",
    ):
        print(
            recipe_id,
            "->",
            get_recipe_details(recipe_id),
        )
