"""Day 5 recipe suitability and ranking; allergy validation belongs to the Reasoning Engine."""
import ast
import re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MAPPING = ROOT / 'data' / 'processed' / 'recipe_ingredient_mapping.csv'
NON_MEALS = re.compile(r'\b(dip|dipping sauce|sauce|dressing|marinade|condiment|gravy|syrup|spread|chutney|relish|pesto|salsa)\b', re.I)

def words(value):
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, (list, tuple, set)):
                return words(parsed)
        except (ValueError, SyntaxError):
            pass
        return [value.strip().lower()] if value.strip() else []
    return [str(value).strip().lower()]

def matches(text, term):
    return bool(re.search(r'(?<!\w)' + re.escape(term.lower()) + r'(?!\w)', text.lower()))

class DayEvaluator:
    def __init__(self, mapping_path=MAPPING):
        self.ingredients = {}
        if Path(mapping_path).exists():
            mapping = pd.read_csv(mapping_path, usecols=['recipe_id', 'ingredient_name'])
            mapping['recipe_id'] = mapping['recipe_id'].astype(str).str.strip().str.upper()
            self.ingredients = mapping.groupby('recipe_id')['ingredient_name'].apply(
                lambda s: [str(x).lower().strip() for x in s.dropna()]
            ).to_dict()

    def evaluate(self, candidates, user_state, meal_type='dinner', recent_cuisines=(), max_time=None):
        accepted, rejected = [], []
        disliked = words(user_state.get('disliked_ingredients', []))
        diets = words(user_state.get('dietary_restrictions', []))
        preferred = words(user_state.get('preferred_ingredients', []))
        available = user_state.get('ingredient_availability') or {}
        available_names = words(list(available) if isinstance(available, dict) else available)
        cuisines = words(user_state.get('preferred_cuisines', []))
        recent = words(recent_cuisines)
        for _, row in candidates.iterrows():
            rid = str(row['recipe_id']).strip().upper()
            reasons = []
            name = str(row.get('recipe_name', '') or '')
            dish = ' '.join(words(row.get('dish_type')))
            ingredients = self.ingredients.get(rid, [])
            labels = words(row.get('health_labels'))
            diet_labels = words(row.get('diet_labels'))
            if NON_MEALS.search(name) or NON_MEALS.search(dish):
                reasons.append('Standalone sauce/dip/condiment is not a full meal')
            # Allergies are deliberately NOT checked here. The Reasoning Engine
            # must validate ingredient-level allergy safety before final selection.
            if not ingredients and disliked:
                reasons.append('Ingredient list unavailable; cannot check disliked ingredients')
            for item in disliked:
                if any(matches(ing, item) or (item.endswith('s') and matches(ing, item[:-1])) for ing in ingredients):
                    reasons.append(f'Disliked ingredient: {item}')
            for diet in diets:
                if diet == 'vegetarian':
                    if str(row.get('is_vegetarian', '')).lower() not in ('true', '1') and 'vegetarian' not in labels:
                        reasons.append('Vegetarian diet not verified')
                elif diet == 'vegan':
                    if str(row.get('is_vegan', '')).lower() not in ('true', '1') and 'vegan' not in labels:
                        reasons.append('Vegan diet not verified')
                elif diet not in labels + diet_labels:
                    reasons.append(f'Diet restriction not verified: {diet}')
            if max_time is not None:
                time = pd.to_numeric(row.get('cooking_time_min'), errors='coerce')
                if pd.isna(time) or time < 0:
                    reasons.append('Cooking time unavailable')
                elif time > float(max_time):
                    reasons.append(f'Cooking time {time:g} exceeds {float(max_time):g} minutes')
            if reasons:
                rejected.append({'recipe_id': rid, 'reasons': list(dict.fromkeys(reasons))})
                continue
            # All scores normalized to [0, 1]. Missing nutrition is neutral, not invented.
            protein = pd.to_numeric(row.get('protein_g_per_serving'), errors='coerce')
            fiber = pd.to_numeric(row.get('fiber_g_per_serving'), errors='coerce')
            sodium = pd.to_numeric(row.get('sodium_mg_per_serving'), errors='coerce')
            calories = pd.to_numeric(row.get('calories_per_serving'), errors='coerce')
            nutrient_scores = [min(max(float(protein) / 25, 0), 1) if pd.notna(protein) else .5,
                               min(max(float(fiber) / 8, 0), 1) if pd.notna(fiber) else .5,
                               max(0, 1 - max(float(sodium) - 600, 0) / 1400) if pd.notna(sodium) else .5]
            nutrition = sum(nutrient_scores) / len(nutrient_scores)
            meal_score = 1.0 if 'main course' in dish else .7
            if pd.notna(calories) and float(calories) < 200:
                meal_score *= .65
            reuse = sum(any(matches(ing, p) for p in preferred + available_names) for ing in ingredients) / max(len(ingredients), 1)
            recipe_cuisines = words(row.get('cuisine_type'))
            variety = .5 + (.5 if any(c in cuisines for c in recipe_cuisines) else 0) - (.4 if any(c in recent for c in recipe_cuisines) else 0)
            variety = min(max(variety, 0), 1)
            score = round(.35 * meal_score + .35 * nutrition + .20 * reuse + .10 * variety, 5)
            accepted.append({'recipe_id': rid, 'score': score, 'meal_suitability': round(meal_score, 4),
                             'nutrition': round(nutrition, 4), 'ingredient_reuse': round(reuse, 4),
                             'cuisine_variety': round(variety, 4)})
        accepted.sort(key=lambda r: (-r['score'], r['recipe_id']))
        return accepted, rejected
