import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge.repository import LIST_COLS, normalize  # noqa: E402  same label rule as retrieval

DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "recipes_kb.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "recipe_kb_clean.csv"
POLICY_PATH = PROJECT_ROOT / "reports" / "missing_value_policy.md"

NUTRIENT_COLS = [
    "calories_per_serving", "weight_g_per_serving", "protein_g_per_serving", "carbs_g_per_serving",
    "fat_g_per_serving", "fiber_g_per_serving", "sugar_g_per_serving", "sodium_mg_per_serving",
    "calcium_mg_per_serving", "iron_mg_per_serving",
]
NOT_FOOD_PATTERN = r"face mask|body scrub|soap|candle"


# ----------------------------------------------------------------------------- Step 1
def parse_list(value) -> list:
    """'["Low-Carb","Balanced"]' -> ['Low-Carb', 'Balanced']; anything broken -> []."""
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def clean_list(value, split_slash: bool = False) -> list:
    """Normalize every label; 'lunch/dinner' -> ['lunch', 'dinner']; drop duplicates."""
    out = []
    for item in parse_list(value):
        for part in (str(item).split("/") if split_slash else [item]):
            label = normalize(part)
            if label and label not in out:
                out.append(label)
    return out


def standardize(kb: pd.DataFrame) -> pd.DataFrame:
    clean = kb.copy()
    for col in LIST_COLS:
        clean[col] = kb[col].map(lambda v, c=col: clean_list(v, split_slash=(c == "meal_type")))

    clean["recipe_id"] = clean["recipe_id"].astype(str).str.strip().str.upper()
    clean["recipe_name"] = (
        clean["recipe_name"].astype(str).str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .str.replace(r"\s+recipes?$", "", regex=True, flags=re.IGNORECASE)  # scraping artifact
    )

    clean["is_vegetarian"] = clean["health_labels"].map(lambda h: "vegetarian" in h or "vegan" in h)
    clean["is_vegan"] = clean["health_labels"].map(lambda h: "vegan" in h)
    if "cooking_time_min" not in clean.columns:
        clean["cooking_time_min"] = np.nan  # no time data in the source; never guessed
    return clean


# ----------------------------------------------------------------------------- Step 2
def apply_missing_value_rules(clean: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    removed = {}

    essential_missing = (
        clean["recipe_id"].isna() | clean["recipe_name"].isna() | (clean["recipe_name"].str.len() == 0)
        | clean["servings"].isna() | clean["calories_per_serving"].isna()
        | clean["cuisine_type"].map(len).eq(0) | clean["meal_type"].map(len).eq(0)
    )
    removed["missing id/name/servings/calories/cuisine/meal type"] = clean.loc[essential_missing, "recipe_name"].tolist()
    clean = clean[~essential_missing]

    not_food = clean["recipe_name"].str.contains(NOT_FOOD_PATTERN, case=False, regex=True)
    removed["not a food recipe"] = clean.loc[not_food, "recipe_name"].tolist()
    clean = clean[~not_food]

    return clean, removed


def validate(clean: pd.DataFrame) -> bool:
    checks = {
        "recipe_id unique": clean["recipe_id"].is_unique,
        "no empty names": (clean["recipe_name"].str.len() > 0).all(),
        "every recipe has cuisine and meal type":
            (clean["cuisine_type"].map(len) > 0).all() and (clean["meal_type"].map(len) > 0).all(),
        "labels lowercase, no '-' or '/'":
            all(l == l.lower() and "-" not in l and "/" not in l
                for col in LIST_COLS for labels in clean[col] for l in labels),
        "calories > 0": (clean["calories_per_serving"] > 0).all(),
    }
    for name, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return all(checks.values())


def main() -> None:
    ap = argparse.ArgumentParser(description="Clean the Recipe KB (Member 2).")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()

    kb = pd.read_csv(args.input)
    print(f"Loaded {len(kb):,} recipes from {args.input}")

    clean = standardize(kb)
    clean, removed = apply_missing_value_rules(clean)
    for reason, names in removed.items():
        print(f"Removed {len(names)} — {reason}{': ' + ', '.join(names) if names else ''}")

    print("Validation:")
    if not validate(clean):
        sys.exit("Validation failed — cleaned KB not written.")

    to_save = clean.copy()
    for col in LIST_COLS:
        to_save[col] = to_save[col].map(json.dumps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    to_save.to_csv(args.output, index=False)

    print(f"Saved {args.output.relative_to(PROJECT_ROOT)} ({len(to_save):,} recipes)")
    print(f"Saved {POLICY_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()