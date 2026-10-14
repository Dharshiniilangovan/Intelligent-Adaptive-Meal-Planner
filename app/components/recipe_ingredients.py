"""Read original per-serving ingredient quantities from the Recipe KB mapping."""
import csv
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

MAPPING = Path(__file__).resolve().parents[2] / 'data' / 'processed' / 'recipe_ingredient_mapping.csv'


@lru_cache(maxsize=1)
def _ingredients_by_recipe():
    result = defaultdict(list)
    if not MAPPING.is_file():
        print(f'[RECIPE INGREDIENTS] Missing mapping: {MAPPING}', flush=True)
        return result
    with MAPPING.open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            recipe_id = str(row.get('recipe_id') or '').strip().upper()
            name = str(row.get('ingredient_name') or '').strip()
            quantity = str(row.get('quantity_per_serving') or '').strip()
            unit = str(row.get('unit') or '').strip()
            if recipe_id and name:
                result[recipe_id].append({'ingredient': name, 'quantity': quantity, 'unit': unit})
    return result


def ingredients_for_recipe(recipe_id):
    """Return original Recipe KB rows, without converting or guessing units."""
    return list(_ingredients_by_recipe().get(str(recipe_id or '').strip().upper(), []))
