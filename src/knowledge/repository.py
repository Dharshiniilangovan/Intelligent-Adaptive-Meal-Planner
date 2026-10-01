import json
import warnings
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KB_PATH = PROJECT_ROOT / "data" / "processed" / "recipe_kb_clean.csv"

LIST_COLS = ["diet_labels", "health_labels", "cautions", "cuisine_type", "meal_type", "dish_type"]

# Broad cuisine words a user might ask for -> the cuisine labels that exist in the KB
CUISINE_GROUPS = {
    "asian": {"asian", "chinese", "japanese", "korean", "south east asian", "indian"},
    "european": {"italian", "french", "british", "greek", "nordic", "central europe",
                 "eastern europe", "mediterranean"},
    "latin american": {"mexican", "south american", "caribbean"},
}


def normalize(text: str) -> str:
    """Same rule used when cleaning the KB: lowercase, '-'/'_' -> space, single spaces."""
    return " ".join(str(text).strip().lower().replace("-", " ").replace("_", " ").split())


def load_kb(path: str | Path = DEFAULT_KB_PATH) -> pd.DataFrame:
    """Read the cleaned KB and turn the JSON list columns back into Python lists."""
    df = pd.read_csv(path)
    for col in LIST_COLS:
        df[col] = df[col].map(json.loads)
    return df


class RecipeRepository:
    def __init__(self, df: pd.DataFrame):
        self.df = df.reset_index(drop=True)

    @classmethod
    def from_csv(cls, path: str | Path = DEFAULT_KB_PATH) -> "RecipeRepository":
        return cls(load_kb(path))

    # ---------------------------------------------------------------- basics
    def __len__(self) -> int:
        return len(self.df)

    def ids(self) -> list[str]:
        return self.df["recipe_id"].tolist()

    def to_frame(self) -> pd.DataFrame:
        return self.df.copy()

    def _where(self, mask) -> "RecipeRepository":
        return RecipeRepository(self.df[mask])

    # ---------------------------------------------------------------- lookup
    def get_recipe(self, recipe_id: str) -> dict | None:
        """One recipe as a dict, or None if the id doesn't exist."""
        match = self.df[self.df["recipe_id"] == str(recipe_id).strip().upper()]
        return None if match.empty else match.iloc[0].to_dict()

    # ---------------------------------------------------------------- filters
    def filter_by_meal_type(self, meal: str) -> "RecipeRepository":
        """'dinner', 'lunch', 'breakfast', 'snack', 'brunch', 'teatime' (any case)."""
        meal = normalize(meal)
        return self._where(self.df["meal_type"].map(lambda meals: meal in meals))

    def filter_by_cuisine(self, cuisine: str) -> "RecipeRepository":
        """A KB cuisine ('italian', 'south east asian') or a group ('asian', 'european')."""
        cuisine = normalize(cuisine)
        wanted = CUISINE_GROUPS.get(cuisine, {cuisine})
        return self._where(self.df["cuisine_type"].map(lambda cs: bool(wanted & set(cs))))

    def filter_by_diet(self, diet: str) -> "RecipeRepository":
        """'vegetarian', 'vegan', 'non vegetarian', or any diet/health label
        such as 'low carb', 'high protein', 'gluten free', 'dairy free'."""
        diet = normalize(diet)
        if diet == "vegetarian":
            return self._where(self.df["is_vegetarian"])
        if diet == "vegan":
            return self._where(self.df["is_vegan"])
        if diet in ("non vegetarian", "nonvegetarian", "non veg"):
            return self._where(~self.df["is_vegetarian"])
        return self._where(self.df["diet_labels"].map(lambda d: diet in d)
                           | self.df["health_labels"].map(lambda h: diet in h))

    def filter_by_max_time(self, minutes: float, include_unknown: bool = False) -> "RecipeRepository":
        """Recipes ready in <= `minutes`.

        The current KB has NO cooking-time data (cooking_time_min is NA for every recipe).
        We don't guess: recipes with unknown time are EXCLUDED unless include_unknown=True.
        """
        if "cooking_time_min" not in self.df.columns:
            raise KeyError("KB has no cooking_time_min column")
        times = self.df["cooking_time_min"]
        known = times.notna()
        if not known.any():
            warnings.warn("No cooking time data in the KB yet; filter_by_max_time cannot verify time.",
                          UserWarning, stacklevel=2)
        mask = known & (times <= minutes)
        if include_unknown:
            mask = mask | ~known
        return self._where(mask)

    def filter_by_max_calories(self, kcal: float) -> "RecipeRepository":
        return self._where(self.df["calories_per_serving"] <= kcal)

    def filter_by_min_protein(self, grams: float) -> "RecipeRepository":
        return self._where(self.df["protein_g_per_serving"] >= grams)

    def exclude_cautions(self, *cautions: str) -> "RecipeRepository":
        """Drop recipes with any of these cautions, e.g. exclude_cautions('gluten', 'tree nuts')."""
        bad = {normalize(c) for c in cautions}
        return self._where(self.df["cautions"].map(lambda c: not (bad & set(c))))

    # ---------------------------------------------------------------- combined
    def search(self, meal: str | None = None, diet: str | list[str] | None = None, cuisine: str | None = None,
               max_time: float | None = None, include_unknown_time: bool = False,
               max_calories: float | None = None, min_protein: float | None = None,
               exclude: list[str] | None = None) -> "RecipeRepository":
        """Apply several filters at once; any argument left as None is ignored.
        `diet` can be one label or a list, e.g. diet=["vegan", "gluten free"]."""
        repo = self
        if meal:
            repo = repo.filter_by_meal_type(meal)
        for d in ([diet] if isinstance(diet, str) else diet or []):
            repo = repo.filter_by_diet(d)
        if cuisine:
            repo = repo.filter_by_cuisine(cuisine)
        if max_time is not None:
            repo = repo.filter_by_max_time(max_time, include_unknown=include_unknown_time)
        if max_calories is not None:
            repo = repo.filter_by_max_calories(max_calories)
        if min_protein is not None:
            repo = repo.filter_by_min_protein(min_protein)
        if exclude:
            repo = repo.exclude_cautions(*exclude)
        return repo