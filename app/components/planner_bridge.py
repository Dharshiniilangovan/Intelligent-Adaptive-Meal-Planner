"""UI adapter to the existing GC1 end-to-end planner; no agent logic duplicated."""
from datetime import date


def build_user_state(confirmed: dict) -> dict:
    state = dict(confirmed)
    budget = float(state['budget'])
    state['budget_remaining'] = budget
    state['remaining_budget'] = budget
    state['dietary_restrictions'] = [x.lower() for x in state.get('dietary_restrictions', [])]
    state['allergies'] = [x.lower() for x in state.get('allergies', [])]
    state['preferred_meal_types'] = [x.lower() for x in state['preferred_meal_types']]
    pantry = state.get('ingredient_availability') or {}
    state['pantry'] = [
        {'ingredient_name': name, 'quantity': item['quantity'], 'unit': item['unit']}
        for name, item in pantry.items()
    ]
    return state


def get_planner():
    # Reuse exactly the component wiring tested by the existing Day 5 E2E.
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


def skip_meal(planner, state: dict, plan_state, slot_id: str, completed_slot_ids: set[str]):
    result = planner.skip_and_replan(
        user_state=state,
        plan_state=plan_state,
        slot_id=slot_id,
        completed_slot_ids=completed_slot_ids,
        nutrition_targets=state.get('nutrition_targets'),
    )
    if planner.last_plan_state is None:
        raise RuntimeError('Replanning did not retain a PlanState.')
    return result, planner.last_plan_state
