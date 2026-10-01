import pytest

from src.knowledge.repository import CUISINE_GROUPS, DEFAULT_KB_PATH, RecipeRepository


@pytest.fixture(scope="module")
def repo():
    if not DEFAULT_KB_PATH.exists():
        pytest.skip("recipe_kb_clean.csv not found — run scripts/clean_recipe_kb.py first")
    return RecipeRepository.from_csv()


# ------------------------------------------------------------------ the KB itself
def test_ids_unique(repo):
    assert repo.to_frame()["recipe_id"].is_unique


def test_labels_are_clean(repo):
    df = repo.to_frame()
    for col in ["diet_labels", "health_labels", "cautions", "cuisine_type", "meal_type", "dish_type"]:
        for labels in df[col]:
            for label in labels:
                assert label == label.strip().lower() and "-" not in label and "/" not in label


# ------------------------------------------------------------------ get_recipe
def test_get_recipe_found(repo):
    first = repo.ids()[0]
    assert repo.get_recipe(first)["recipe_id"] == first


def test_get_recipe_lowercase_id(repo):
    first = repo.ids()[0]
    assert repo.get_recipe(first.lower())["recipe_id"] == first


def test_get_recipe_missing(repo):
    assert repo.get_recipe("R99999999") is None


# ------------------------------------------------------------------ single filters
@pytest.mark.parametrize("meal", ["dinner", "Dinner", "DINNER"])
def test_meal_type_case_insensitive(repo, meal):
    result = repo.filter_by_meal_type(meal)
    assert len(result) > 0
    assert all("dinner" in m for m in result.to_frame()["meal_type"])


def test_lunch_and_dinner_both_match_split_value(repo):
    assert len(repo.filter_by_meal_type("lunch")) == len(repo.filter_by_meal_type("dinner"))


def test_vegetarian(repo):
    df = repo.filter_by_diet("vegetarian").to_frame()
    assert len(df) > 0
    assert all("vegetarian" in h or "vegan" in h for h in df["health_labels"])


def test_vegan_is_subset_of_vegetarian(repo):
    vegan = set(repo.filter_by_diet("vegan").ids())
    vegetarian = set(repo.filter_by_diet("vegetarian").ids())
    assert vegan and vegan <= vegetarian


def test_diet_label(repo):
    df = repo.filter_by_diet("Low-Carb").to_frame()
    assert len(df) > 0
    assert all("low carb" in d for d in df["diet_labels"])


def test_asian_group(repo):
    df = repo.filter_by_cuisine("asian").to_frame()
    assert len(df) > 0
    assert all(CUISINE_GROUPS["asian"] & set(c) for c in df["cuisine_type"])


def test_max_calories(repo):
    df = repo.filter_by_max_calories(400).to_frame()
    assert len(df) > 0 and (df["calories_per_serving"] <= 400).all()


def test_exclude_cautions(repo):
    df = repo.exclude_cautions("gluten", "wheat").to_frame()
    assert all(not ({"gluten", "wheat"} & set(c)) for c in df["cautions"])


# ------------------------------------------------------------------ time (no data yet)
def test_max_time_warns_and_excludes_unknown(repo):
    with pytest.warns(UserWarning):
        assert len(repo.filter_by_max_time(30)) == 0


def test_max_time_include_unknown(repo):
    with pytest.warns(UserWarning):
        assert len(repo.filter_by_max_time(30, include_unknown=True)) == len(repo)


# ------------------------------------------------------------------ combinations
def test_vegetarian_dinner_combo(repo):
    df = repo.search(diet="vegetarian", meal="dinner", max_calories=500).to_frame()
    assert len(df) > 0
    assert df["is_vegetarian"].all()
    assert all("dinner" in m for m in df["meal_type"])
    assert (df["calories_per_serving"] <= 500).all()


def test_chaining_equals_search(repo):
    chained = repo.filter_by_diet("vegan").filter_by_meal_type("breakfast").filter_by_cuisine("asian")
    searched = repo.search(diet="vegan", meal="breakfast", cuisine="asian")
    assert set(chained.ids()) == set(searched.ids())


def test_multiple_diets(repo):
    df = repo.search(diet=["vegan", "gluten free"], meal="lunch").to_frame()
    assert len(df) > 0
    assert df["is_vegan"].all()
    assert all("gluten free" in h for h in df["health_labels"])