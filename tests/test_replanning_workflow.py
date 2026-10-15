"""Streamlit adaptive-replanning workflow, end to end.

Screenshot sequence over real KB recipes (prices mocked, see
tests/planning_harness.py): plan Thu 15 - Sun 18 Oct 2026, mark Thursday
lunch + dinner and Friday lunch eaten, record one leftover serving of
Thursday's dinner, skip Saturday lunch, approve the leftover, replan.

Backend tests run the real background worker (app/components/
background_jobs._work). The UI test drives the unchanged replanning page
with Streamlit's AppTest. Job and workspace files go to tmp_path.
"""
import copy
import json
import time
import uuid
from datetime import date

import pytest

import app.components.background_jobs as background_jobs
from app.components.state_persistence import json_default
from src.planning.meal_slot import MealSlot
from src.planning.multi_meal_planner import MultiMealPlanner
from src.planning.plan_state import PlanState
from tests.planning_harness import build_planner, repository, user_state

POOL = ["R28835", "R20231", "R19634", "R09645", "R03304", "R02821", "R18958", "R06690"]
PANTRY = [
    {"ingredient_name": "olive oil", "quantity": 30, "unit": "ml"},
    {"ingredient_name": "garlic", "quantity": 2, "unit": "clove"},
    {"ingredient_name": "mushroom", "quantity": 100, "unit": "g"},
]
COMPLETED = {"2026-10-15_lunch", "2026-10-15_dinner", "2026-10-16_lunch"}
SKIPPED = "2026-10-17_lunch"


def kcal(recipe_id):
    return repository().get_recipe(recipe_id)["calories_per_serving"]


def initial_plan():
    planner, _ = build_planner({"lunch": POOL, "dinner": POOL})
    state = user_state(copy.deepcopy(PANTRY), budget=150, max_recipe_repetitions=1)
    result = planner.plan_meals(
        user_state=state, start_date=date(2026, 10, 15), days=4,
        meal_types=["lunch", "dinner"], nutrition_targets=state["nutrition_targets"])
    return planner, state, result, planner.last_plan_state


def by_slot(plan):
    return {m["slot"]["slot_id"]: m for m in plan["selected_meals"]}


def replan_with_leftover(tmp_path, monkeypatch, use_by, servings=1, prepared="2026-10-15"):
    """Record a leftover of Thursday dinner, skip Saturday lunch, approve it."""
    monkeypatch.setattr(background_jobs, "STATE_DIR", tmp_path)
    planner, state, result, plan_state = initial_plan()
    cooked = by_slot(result["plan"])["2026-10-15_dinner"]
    # As recorded by app/pages/replanning.py.
    plan_state.record_prepared_leftover(
        leftover_id="L000000000001", recipe_id=cooked["recipe_id"],
        servings_remaining=servings, prepared_date=prepared,
        storage="refrigerated", expires_on=use_by)
    plan_state.prepared_leftovers[-1]["nutrition"] = cooked["decision"]["recipe"]
    displayed = copy.deepcopy(plan_state)
    workspace = str(uuid.uuid4())
    job = {"workspace_id": workspace, "job_id": str(uuid.uuid4()),
           "kind": "replan", "status": "queued"}
    background_jobs._work(job, {
        "planner": planner, "user_state": state, "plan_state": plan_state,
        "slot_id": SKIPPED, "completed": set(COMPLETED),
        "approved_leftover_ids": ["L000000000001"]})
    saved = background_jobs.read_background_job(workspace, job["job_id"])
    assert saved["status"] == "completed", saved.get("error")
    live = background_jobs.get_live_replan(workspace, job["job_id"])
    return {"before": result, "after": saved["result"], "state": live["plan_state"],
            "displayed": displayed, "plan_state": plan_state, "cooked": cooked,
            "user_state": state}


@pytest.fixture(scope="module")
def valid(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        return replan_with_leftover(tmp_path_factory.mktemp("jobs"), mp, "2026-10-17")


@pytest.fixture(scope="module")
def expired(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        return replan_with_leftover(tmp_path_factory.mktemp("jobs"), mp, "2026-10-15")


# ============================================================
# Completed meals, skipped slot, persistence
# ============================================================

def test_completed_meals_are_kept_unchanged(valid):
    before, after = by_slot(valid["before"]["plan"]), by_slot(valid["after"]["plan"])
    for slot_id in COMPLETED:
        assert json.dumps(after[slot_id], sort_keys=True, default=str) == \
            json.dumps(before[slot_id], sort_keys=True, default=str)


def test_skipped_slot_is_excluded_and_not_refilled(valid):
    plan = valid["after"]["plan"]

    assert plan["skipped_slots"] == [{"slot_id": SKIPPED, "reason": "user_skipped"}]
    assert SKIPPED not in by_slot(plan)
    assert set(by_slot(plan)) == {s["slot_id"] for s in plan["slots"]} - {SKIPPED}
    sources = {s["slot_id"] for r in valid["after"]["grocery_basket"]["purchase_requirements"]
               for s in r["source_requirements"]}
    assert SKIPPED not in sources


def test_worker_does_not_mutate_the_displayed_state(valid):
    assert valid["plan_state"].prepared_leftovers == valid["displayed"].prepared_leftovers
    assert valid["plan_state"].skipped_slots == []
    assert "approved_leftover_ids" not in valid["user_state"]


def test_persisted_result_matches_backend_state(valid):
    persisted = json.loads(json.dumps(valid["after"], default=json_default))
    backend = json.loads(json.dumps(valid["state"].to_dict(), default=json_default))

    assert persisted["plan"]["selected_meals"] == backend["selected_meals"]
    assert persisted["plan"]["prepared_leftovers"] == backend["prepared_leftovers"]
    assert persisted["plan"]["skipped_slots"] == backend["skipped_slots"]


# ============================================================
# Leftover allocation
# ============================================================

def test_valid_leftover_fills_first_eligible_unfinished_slot(valid):
    meal = by_slot(valid["after"]["plan"])["2026-10-16_dinner"]

    assert meal["meal_source"] == "prepared_leftover"
    assert meal["leftover_id"] == "L000000000001"
    assert meal["recipe_id"] == valid["cooked"]["recipe_id"]
    [leftover] = valid["after"]["plan"]["prepared_leftovers"]
    assert leftover["servings_remaining"] == 0
    assert (leftover["prepared_date"], leftover["expires_on"], leftover["storage"]) == (
        "2026-10-15", "2026-10-17", "refrigerated")
    allocated = [e for e in valid["after"]["plan"]["execution_trace"]
                 if e["event"] == "prepared_leftover_allocated"]
    assert [e["slot_id"] for e in allocated] == ["2026-10-16_dinner"]


def test_leftover_adds_no_groceries_or_cooking(valid):
    recipe_id = valid["cooked"]["recipe_id"]
    sources = [(s["slot_id"], s["recipe_id"])
               for r in valid["after"]["grocery_basket"]["purchase_requirements"]
               for s in r["source_requirements"]]

    assert {slot for slot, rid in sources if rid == recipe_id} == {"2026-10-15_dinner"}
    assert "2026-10-16_dinner" not in {slot for slot, _ in sources}
    assert valid["after"]["plan"]["budget"]["estimated_spent"] == \
        valid["after"]["grocery_basket"]["projected_cost"]


def test_nutrition_counts_the_leftover_serving(valid):
    after = by_slot(valid["after"]["plan"])
    expected = {}
    for meal in after.values():
        day = meal["slot"]["date"]
        expected[day] = expected.get(day, 0.0) + kcal(meal["recipe_id"])

    summary = valid["after"]["nutrition_summary"]
    assert {d: round(v["calories"], 1) for d, v in summary.items()} == \
        {d: round(v, 1) for d, v in expected.items()}


def test_inventory_starts_from_original_pantry(valid):
    state = valid["state"]
    assert state.initial_inventory == valid["displayed"].initial_inventory
    for name, entry in state.current_inventory.items():
        assert entry["quantity"] >= 0


def test_expired_leftover_is_never_allocated(expired):
    plan = expired["after"]["plan"]

    assert all(m.get("meal_source") != "prepared_leftover" for m in plan["selected_meals"])
    assert plan["prepared_leftovers"][0]["servings_remaining"] == 1
    [unused] = [e for e in plan["execution_trace"] if e["event"] == "prepared_leftover_not_used"]
    assert unused["reason"] == "expired_before_remaining_slots"
    assert unused["servings_remaining"] == 1
    # The slot is cooked fresh instead, with its own groceries.
    sources = {s["slot_id"] for r in expired["after"]["grocery_basket"]["purchase_requirements"]
               for s in r["source_requirements"]}
    assert "2026-10-16_dinner" in sources


# ============================================================
# Allocation rules (direct)
# ============================================================

def slots(*days):
    return [MealSlot(date=date(2026, 10, d), meal_type=t) for d in days for t in ("lunch", "dinner")]


def state_with(servings, prepared, expires, storage="refrigerated"):
    state = PlanState(slots=[], initial_budget=100.0)
    state.record_prepared_leftover(
        leftover_id="L1", recipe_id="R1", servings_remaining=servings,
        prepared_date=prepared, storage=storage, expires_on=expires)
    state.prepared_leftovers[0]["nutrition"] = {"calories": 400}
    return state


def test_never_allocated_more_than_available_servings():
    state = state_with(2, "2026-10-15", "2026-10-20")

    meals, unfilled = MultiMealPlanner._allocate_prepared_leftovers(state, slots(16, 17), ["L1"])

    assert [m["slot"]["slot_id"] for m in meals] == ["2026-10-16_lunch", "2026-10-16_dinner"]
    assert len(unfilled) == 2
    assert state.prepared_leftovers[0]["servings_remaining"] == 0


def test_never_allocated_before_preparation_date():
    state = state_with(2, "2026-10-17", "2026-10-20")

    meals, _ = MultiMealPlanner._allocate_prepared_leftovers(state, slots(16, 17), ["L1"])

    assert [m["slot"]["date"] for m in meals] == ["2026-10-17", "2026-10-17"]


def test_unapproved_leftover_is_not_used_or_reported():
    state = state_with(2, "2026-10-15", "2026-10-20")

    meals, unfilled = MultiMealPlanner._allocate_prepared_leftovers(state, slots(16), [])

    assert meals == [] and len(unfilled) == 2
    assert state.prepared_leftovers[0]["servings_remaining"] == 2
    assert not any(e["event"] == "prepared_leftover_not_used" for e in state.execution_trace)


@pytest.mark.parametrize("prepared, expires, storage, reason", [
    ("2026-10-18", "2026-10-20", "refrigerated", "prepared_after_remaining_slots"),
    ("2026-10-10", "2026-10-12", "refrigerated", "expired_before_remaining_slots"),
    ("2026-10-15", "2026-10-20", "", "storage_unknown"),
    ("2026-10-15", "not-a-date", "refrigerated", "invalid_dates"),
])
def test_approved_but_unused_leftover_is_explained(prepared, expires, storage, reason):
    state = state_with(2, prepared, expires, storage)

    meals, _ = MultiMealPlanner._allocate_prepared_leftovers(state, slots(16, 17), ["L1"])

    assert meals == []
    [event] = [e for e in state.execution_trace if e["event"] == "prepared_leftover_not_used"]
    assert (event["reason"], event["servings_remaining"]) == (reason, 2)
    assert state.prepared_leftovers[0]["servings_remaining"] == 2


# ============================================================
# Unchanged Streamlit page, driven headless
# ============================================================

PAGE = """
import runpy, sys, pathlib
sys.path.insert(0, {root!r})
import app.components.state_persistence as sp, app.components.background_jobs as bj
sp.STATE_DIR = pathlib.Path({out!r}); bj.STATE_DIR = pathlib.Path({out!r})
from app.components.background_status import sync_background_jobs
sync_background_jobs()  # as app/streamlit_app.py does on every run
runpy.run_path({root!r} + "/app/pages/replanning.py", run_name="__main__")
"""


def test_streamlit_page_flow_updates_state_and_display(tmp_path):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    import app.components.state_persistence as persistence

    root = str(Path(__file__).resolve().parents[1])
    saved_dirs = (persistence.STATE_DIR, background_jobs.STATE_DIR)
    planner, state, result, plan_state = initial_plan()
    at = AppTest.from_string(PAGE.format(root=root, out=str(tmp_path)), default_timeout=300)
    workspace = str(uuid.uuid4())
    at.session_state["workspace_id"] = workspace
    at.session_state["planner_result"] = result
    at.session_state["live_planner"] = planner
    at.session_state["live_plan_state"] = plan_state
    at.session_state["planner_user_state"] = state
    at.session_state["completed_slot_ids"] = set()
    try:
        at.run()
        eaten = at.multiselect[0]
        eaten.set_value([o for o in eaten.options
                         if o.startswith("Thu,") or o.startswith("Fri, 16 Oct 2026 · Lunch")])
        at.button[0].click().run()
        assert at.session_state["completed_slot_ids"] == COMPLETED

        recipe_id = by_slot(result["plan"])["2026-10-15_dinner"]["recipe_id"]
        at.selectbox[0].set_value(next(o for o in at.selectbox[0].options if recipe_id in o))
        at.number_input[0].set_value(1)
        at.date_input[0].set_value(date(2026, 10, 15))
        at.date_input[1].set_value(date(2026, 10, 17))
        next(b for b in at.button if b.label == "Record leftovers").click().run()
        [leftover] = at.session_state["live_plan_state"].prepared_leftovers
        assert (leftover["recipe_id"], leftover["servings_remaining"]) == (recipe_id, 1)

        skip = next(s for s in at.selectbox if s.label == "Meal to skip")
        skip.set_value(next(o for o in skip.options if o.startswith("Sat, 17 Oct 2026 · Lunch")))
        approve = next(m for m in at.multiselect if m.label.startswith("Approve"))
        approve.set_value(approve.options)
        next(b for b in at.button if b.label == "Skip meal and update plan").click().run()
        job_id = at.session_state["replanning_job_id"]
        deadline = time.time() + 240
        while background_jobs.read_background_job(workspace, job_id)["status"] in ("queued", "running"):
            assert time.time() < deadline
            time.sleep(0.5)
        at.run()
    finally:
        persistence.STATE_DIR, background_jobs.STATE_DIR = saved_dirs

    assert not at.exception
    plan = at.session_state["planner_result"]["plan"]
    live = at.session_state["live_plan_state"]
    assert plan["selected_meals"] == live.to_dict()["selected_meals"]
    assert live.skipped_slots == [{"slot_id": SKIPPED, "reason": "user_skipped"}]
    assert by_slot(plan)["2026-10-16_dinner"]["meal_source"] == "prepared_leftover"
    assert live.prepared_leftovers[0]["servings_remaining"] == 0
    saved = json.loads((tmp_path / f"{workspace}.json").read_text())
    assert set(saved["completed_slot_ids"]) == COMPLETED
    assert saved["planner_result"]["plan"]["selected_meals"] == \
        json.loads(json.dumps(plan["selected_meals"], default=json_default))
    # Display: completed meals in history, skipped slot not active.
    assert any(e.label == "Meals already eaten (3)" for e in at.expander)
    skip_options = next(s for s in at.selectbox if s.label == "Meal to skip").options
    assert not any(o.startswith("Sat, 17 Oct 2026 · Lunch") for o in skip_options)
    assert not any(o.startswith("Thu,") for o in skip_options)
    assert any(o.startswith("Fri, 16 Oct 2026 · Dinner") for o in skip_options)
