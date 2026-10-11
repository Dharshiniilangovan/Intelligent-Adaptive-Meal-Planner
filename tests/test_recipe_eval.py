import pandas as pd
from src.agents.recipe_check import DayEvaluator


def test_day5_filters_and_ranks():
    evaluator = DayEvaluator()
    evaluator.ingredients = {
        'R00001': ['tomato', 'cheese'],
        'R00002': ['peanut', 'tomato'],
        'R00003': ['tomato', 'onion'],
        'R00004': ['tomato'],
        'R00005': ['tomato', 'cheese'],
    }
    kb = pd.DataFrame([
        dict(recipe_id='R00001', recipe_name='Tomato cheese bake', dish_type="['main course']", health_labels="['vegetarian', 'peanut free']", is_vegetarian=True, cooking_time_min=40, protein_g_per_serving=20, fiber_g_per_serving=6, sodium_mg_per_serving=400),
        dict(recipe_id='R00002', recipe_name='Peanut stir fry', dish_type="['main course']", health_labels="['vegetarian']", is_vegetarian=True, cooking_time_min=40),
        dict(recipe_id='R00003', recipe_name='Tomato onion bake', dish_type="['main course']", health_labels="['vegetarian', 'peanut free']", is_vegetarian=True, cooking_time_min=40),
        dict(recipe_id='R00004', recipe_name='Tomato dipping sauce', dish_type="['sauce']", health_labels="['vegetarian', 'peanut free']", is_vegetarian=True, cooking_time_min=20),
        dict(recipe_id='R00005', recipe_name='Tomato cheese casserole', dish_type="['main course']", health_labels="['vegetarian', 'peanut free']", is_vegetarian=True, cooking_time_min=150),
    ])
    state = {'allergies':['Peanuts'], 'dietary_restrictions':['Vegetarian'], 'disliked_ingredients':['Onions'], 'ingredient_availability':{'Tomato':'2 counts'}}
    ranked, rejected = evaluator.evaluate(kb, state, max_time=120)
    assert set(r['recipe_id'] for r in ranked) == {'R00001', 'R00002'}
    assert set(r['recipe_id'] for r in rejected) == {'R00003','R00004','R00005'}
    assert all(r['reasons'] for r in rejected)
    assert ranked[0]['ingredient_reuse'] > 0


def test_allergies_are_delegated_to_reasoning_engine():
    evaluator = DayEvaluator(mapping_path='missing_mapping.csv')
    evaluator.ingredients = {'R00002': ['peanut', 'tomato']}
    candidates = pd.DataFrame([dict(recipe_id='R00002', recipe_name='Peanut stir fry',
        dish_type="['main course']", is_vegetarian=True, cooking_time_min=30)])
    ranked, rejected = evaluator.evaluate(candidates, {'allergies': ['Peanuts'],
        'dietary_restrictions': ['Vegetarian']}, max_time=120)
    assert [r['recipe_id'] for r in ranked] == ['R00002']
    assert not rejected
    # This is a handoff test, NOT a claim that peanuts are safe.
