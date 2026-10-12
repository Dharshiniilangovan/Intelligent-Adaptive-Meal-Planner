"""Adapter to existing GC1 E2E planner; no changes to backend agents."""
from datetime import date


def build_user_state(confirmed: dict) -> dict:
    state = dict(confirmed)
    budget = float(state['budget'])
    state['budget_remaining'] = budget
    state['remaining_budget'] = budget
    state['budget_cap'] = budget + 5.0 if state.get('budget_flexible') else None
    for field in ('dietary_restrictions', 'allergies', 'preferred_meal_types',
                  'preferred_cuisines', 'preferred_ingredients', 'disliked_ingredients'):
        state[field] = [str(x).strip().lower() for x in (state.get(field) or []) if str(x).strip()]
    pantry = state.get('ingredient_availability') or {}
    state['pantry'] = [
        {'ingredient_name': name, 'quantity': float(item['quantity']), 'unit': item['unit']}
        for name, item in pantry.items()
    ]
    return state


def get_planner():
    from scripts.run_day5_e2e import build_system
    return build_system()


def generate(confirmed: dict):
    planner = get_planner()
    state = build_user_state(confirmed)
    result = planner.plan_meals(
        user_state=state,
        start_date=date.fromisoformat(confirmed['start_date']),
        days=int(confirmed['days']),
        meal_types=list(state['preferred_meal_types']),
        nutrition_targets=state.get('nutrition_targets'),
    )
    if planner.last_plan_state is None:
        raise RuntimeError('Planner did not retain a PlanState.')
    return result, planner.last_plan_state, state, planner


def skip_meal(planner, state, plan_state, slot_id, completed_slot_ids):
    result = planner.skip_and_replan(
        user_state=state, plan_state=plan_state, slot_id=slot_id,
        completed_slot_ids=completed_slot_ids,
        nutrition_targets=state.get('nutrition_targets'),
    )
    if planner.last_plan_state is None:
        raise RuntimeError('Replanning did not retain a PlanState.')
    return result, planner.last_plan_state
