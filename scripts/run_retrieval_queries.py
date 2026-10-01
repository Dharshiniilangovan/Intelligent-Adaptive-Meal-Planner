import sys
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.knowledge.repository import RecipeRepository  # noqa: E402

REPORT_PATH = PROJECT_ROOT / "reports" / "retrieval_manual_tests.txt"

QUERIES = [
    ("Vegetarian dinner",                    dict(diet="vegetarian", meal="dinner")),
    ("Vegetarian dinner <= 30 min (strict)", dict(diet="vegetarian", meal="dinner", max_time=30)),
    ("Vegan breakfast",                      dict(diet="vegan", meal="breakfast")),
    ("Asian dinner under 500 kcal",          dict(cuisine="asian", meal="dinner", max_calories=500)),
    ("Italian, non-veg, >= 25 g protein",    dict(cuisine="italian", diet="non vegetarian", min_protein=25)),
    ("Low-carb dinner",                      dict(diet="low carb", meal="dinner")),
    ("Snack under 200 kcal",                 dict(meal="snack", max_calories=200)),
    ("Indian, no gluten or wheat",           dict(cuisine="indian", exclude=["gluten", "wheat"])),
    ("High-protein Mexican",                 dict(diet="high protein", cuisine="mexican")),
    ("Gluten-free vegan lunch",              dict(diet=["vegan", "gluten free"], meal="lunch")),
]


def main(examples_per_query: int = 5) -> None:
    repo = RecipeRepository.from_csv()
    lines = [f"Manual retrieval checks — {len(repo):,} recipes in KB", ""]

    for title, query in QUERIES:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = repo.search(**query).to_frame()
        lines.append(f"## {title}  {query}")
        lines.append(f"   -> {len(result):,} recipes")
        for w in caught:
            lines.append(f"   ! {w.message}")
        for _, r in result.head(examples_per_query).iterrows():
            lines.append(f"   {r['recipe_id']}  {r['recipe_name'][:50]:50}  "
                         f"cuisine={','.join(r['cuisine_type'])}  meal={','.join(r['meal_type'])}  "
                         f"{r['calories_per_serving']:.0f} kcal  {r['protein_g_per_serving']:.0f} g protein")
        lines.append("   Verdict: ______  (fill in after checking the names above)")
        lines.append("")

    report = "\n".join(lines)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()