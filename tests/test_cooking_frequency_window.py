"""Cooking frequency caps cooking sessions per 7-day planning window.

Reproduces the reported plan: 7 days from Thursday 15 Oct 2026, lunch
and dinner (14 slots), 3 cooking sessions per week. ISO week 42 ends on
Sunday 18 Oct, so the old per-ISO-week count gave the plan 6 sessions
and the beam search still stranded Sunday.

Fake-manager tests make every recipe eligible, so only the cooking
schedule and the search decide which slots fill. The real-KB test uses
tests/planning_harness.py (catalog prices instead of live services).
"""
import copy
from datetime import date, timedelta

import pytest

from src.planning.cooking_schedule import (
    build_cooking_schedule,
    max_coverable_slots,
)
from src.planning.multi_meal_planner import MultiMealPlanner
from tests.planning_harness import (
    build_planner,
    reconciliation_event,
    user_state,
)
from tests.test_recipe_diversity_policy import SpecManager, spec

START = date(2026, 10, 15)  # Thursday, ISO week 42
SUNDAY = "2026-10-18"
WINDOW = "2026-10-15/2026-10-21"


def plan(specs=None, days=7, start=START, meal_types=("lunch", "dinner"), **state):
    specs = specs or {f"R{i:02d}": spec(float(i)) for i in range(1, 9)}
    planner = MultiMealPlanner(manager=SpecManager(specs), max_candidates_per_slot=10)
    user = {"budget_remaining": 500, "cook_frequency": 3, **state}
    result = planner.plan_meals(user_state=user, start_date=start, days=days,
                                meal_types=list(meal_types))
    return result, planner


def filled(result):
    return {m["slot"]["slot_id"] for m in result["plan"]["selected_meals"]}


def unfilled(result):
    return [s["slot_id"] for s in result["plan"]["slots"]
            if s["slot_id"] not in filled(result)]


def events(result, name):
    return [e for e in result["plan"]["execution_trace"] if e.get("event") == name]


def meal(recipe_id, day, meal_type="lunch"):
    return {"recipe_id": recipe_id,
            "slot": {"slot_id": f"{day}_{meal_type}", "date": day,
                     "meal_type": meal_type}}


# ============================================================
# Schedule: windows follow the plan, not the calendar week
# ============================================================

def test_sessions_counted_per_planning_window_not_iso_week():
    # Thu, Sat, Mon, Wed: two ISO weeks (2 + 2) but one 7-day plan.
    meals = [meal(r, d) for r, d in (("A", "2026-10-15"), ("B", "2026-10-17"),
                                     ("C", "2026-10-19"), ("D", "2026-10-21"))]

    schedule = build_cooking_schedule(meals, max_sessions=3, window_start=START)

    assert schedule["weekly_session_counts"] == {WINDOW: 4}
    assert schedule["violations"] == {WINDOW: 4}
    assert schedule["valid"] is False
    assert schedule["window_start"] == "2026-10-15"


def test_second_window_starts_seven_days_after_plan_start():
    meals = [meal("A", "2026-10-21"), meal("B", "2026-10-22")]

    schedule = build_cooking_schedule(meals, max_sessions=1, window_start=START)

    assert schedule["weekly_session_counts"] == {
        WINDOW: 1, "2026-10-22/2026-10-28": 1}
    assert schedule["valid"] is True
    assert [s["window"] for s in schedule["sessions"]] == [
        WINDOW, "2026-10-22/2026-10-28"]


def test_window_defaults_to_first_cook_date():
    meals = [meal("A", "2026-10-12"), meal("B", "2026-10-18"), meal("C", "2026-10-19")]

    schedule = build_cooking_schedule(meals, max_sessions=2)

    assert schedule["weekly_session_counts"] == {
        "2026-10-12/2026-10-18": 2, "2026-10-19/2026-10-25": 1}
    assert schedule["valid"] is True


def test_one_session_serves_every_portion_within_storage_days():
    days = ["2026-10-15", "2026-10-15", "2026-10-16", "2026-10-16", "2026-10-17"]
    meals = [meal("A", d, t) for d, t in zip(days, ["lunch", "dinner"] * 3)]

    kept_two_days = build_cooking_schedule(meals, max_sessions=1, max_storage_days=2)
    kept_one_day = build_cooking_schedule(meals, max_sessions=1, max_storage_days=1)

    [session] = kept_two_days["sessions"]
    assert session["portions_prepared"] == 5
    assert session["cook_date"] == "2026-10-15"
    assert kept_two_days["valid"] is True
    # With one-day storage the Saturday portion needs a second session.
    assert kept_one_day["session_count"] == 2
    assert kept_one_day["valid"] is False


def test_max_coverable_slots():
    slots = [{"date": START + timedelta(days=i // 2)} for i in range(14)]

    assert max_coverable_slots(slots, 3, 1, START) == 12
    assert max_coverable_slots(slots, 3, 2, START) == 14
    assert max_coverable_slots(slots, 3, 2, START, portions_per_session=4) == 12
    assert max_coverable_slots(slots, 3, 1, START, sessions_used={WINDOW: 2}) == 4


# ============================================================
# Planner: the reported 7-day / 14-slot / 3-session plan
# ============================================================

def test_reported_week_fills_all_slots_with_three_sessions():
    result, _ = plan(leftover_storage_days=2)
    schedule = result["plan"]["cooking_schedule"]

    assert unfilled(result) == []
    assert {f"{SUNDAY}_lunch", f"{SUNDAY}_dinner"} <= filled(result)
    assert schedule["weekly_session_counts"] == {WINDOW: 3}
    assert schedule["valid"] is True
    assert sum(s["portions_prepared"] for s in schedule["sessions"]) == 14
    # Batch cooking: every session serves several slots as leftovers.
    assert all(len(s["meal_slot_ids"]) >= 2 for s in schedule["sessions"])
    assert result["validation"]["status"] == "feasible"


def test_reported_week_with_one_day_storage_is_reported_not_stranded():
    # 3 sessions x (cook day + 1 day) = 6 days: 12 of 14 slots at most.
    result, planner = plan()
    schedule = result["plan"]["cooking_schedule"]

    assert len(filled(result)) == 12
    assert schedule["weekly_session_counts"] == {WINDOW: 3}
    assert schedule["valid"] is True
    assert result["validation"]["status"] == "partial"
    [capacity] = events(result, "cooking_capacity_insufficient")
    assert (capacity["max_fillable_slots"], capacity["requested_slots"]) == (12, 14)
    assert capacity["storage_days_needed"] == 2
    assert capacity["sessions_needed"] == 4
    [conflict] = [c for c in result["validation"]["constraint_conflicts"]
                  if c["constraint"] == "cook_frequency"]
    assert conflict["max_fillable_slots"] == 12
    assert any("can serve at most 12 of 14" in issue
               for issue in result["validation"]["issues"])
    # Each unfilled slot names the cooking-session cap as the reason.
    for event in events(result, "slot_infeasible"):
        assert event["candidates"]
        assert all(c["reason"]["constraint"] == "cook_frequency"
                   for c in event["candidates"])


def test_iso_week_boundary_does_not_strand_or_add_sessions():
    # Sat 17 Oct - Tue 20 Oct spans ISO weeks 42 and 43. One session per
    # week used to mean one per ISO week: two sessions in four days.
    result, _ = plan(days=4, start=date(2026, 10, 17), cook_frequency=1,
                     leftover_storage_days=3)
    schedule = result["plan"]["cooking_schedule"]

    assert unfilled(result) == []
    assert schedule["weekly_session_counts"] == {"2026-10-17/2026-10-23": 1}
    [session] = schedule["sessions"]
    assert session["portions_prepared"] == 8


def test_one_session_for_fourteen_slots_is_partial_with_reasons():
    result, _ = plan(cook_frequency=1)
    schedule = result["plan"]["cooking_schedule"]

    assert len(filled(result)) == 4
    assert schedule["session_count"] == 1
    assert result["validation"]["status"] == "partial"
    assert "Only 4/14 meal slots were filled." in result["validation"]["issues"]
    [capacity] = events(result, "cooking_capacity_insufficient")
    assert capacity["max_fillable_slots"] == 4
    assert len(events(result, "slot_infeasible")) == 10


def test_explicit_repetition_limit_bounds_batch_size_and_is_kept():
    # Limit 2 means at most 2 portions per batch: 3 sessions -> 6 slots.
    result, _ = plan(max_recipe_repetitions=2, leftover_storage_days=2)
    recipes = [m["recipe_id"] for m in result["plan"]["selected_meals"]]

    assert len(recipes) == 6
    assert max(recipes.count(r) for r in set(recipes)) <= 2
    assert result["plan"]["cooking_schedule"]["session_count"] == 3
    [capacity] = events(result, "cooking_capacity_insufficient")
    assert capacity["max_recipe_repetitions"] == 2
    assert capacity["max_fillable_slots"] == 6
    assert "storage_days_needed" not in capacity  # more storage cannot help
    assert capacity["sessions_needed"] == 7


def test_allergen_recipe_never_fills_a_slot_for_cooking_frequency():
    specs = {"SAFE": spec(5.0), "NUTS": spec(1.0, allergen=True)}

    result, _ = plan(specs, days=3, cook_frequency=1, leftover_storage_days=1)
    recipes = {m["recipe_id"] for m in result["plan"]["selected_meals"]}

    assert recipes == {"SAFE"}
    assert len(filled(result)) == 4
    assert result["plan"]["cooking_schedule"]["session_count"] == 1


def test_over_budget_batch_is_never_selected_to_fill_slots():
    specs = {"CHEAP": spec(5.0), "PRICY": spec(400.0)}

    result, _ = plan(specs, days=3, cook_frequency=2, leftover_storage_days=1,
                     budget_remaining=50)

    assert {m["recipe_id"] for m in result["plan"]["selected_meals"]} == {"CHEAP"}
    assert result["plan"]["budget"]["estimated_spent"] <= 50


def test_without_cook_frequency_no_capacity_report():
    result, _ = plan(cook_frequency=None)

    assert unfilled(result) == []
    assert result["plan"]["cooking_schedule"] == {}
    assert not events(result, "cooking_capacity_insufficient")


def test_invalid_storage_days_rejected():
    with pytest.raises(ValueError):
        plan(days=1, leftover_storage_days=-1)


def test_skip_and_replan_keeps_windows_anchored_to_plan_start():
    result, planner = plan(leftover_storage_days=2)
    state = planner.last_plan_state

    updated = planner.skip_and_replan(
        user_state={"budget_remaining": 500, "cook_frequency": 3,
                    "leftover_storage_days": 2},
        plan_state=state,
        slot_id="2026-10-15_lunch",
    )
    schedule = updated["plan"]["cooking_schedule"]

    assert schedule["window_start"] == "2026-10-15"
    assert schedule["weekly_session_counts"] == {WINDOW: 3}
    assert schedule["valid"] is True
    assert len(updated["plan"]["selected_meals"]) == 13


# ============================================================
# Real KB recipes: one batch covers several slots, inventory reconciled
# ============================================================

def test_kb_batch_cooking_across_iso_boundary():
    pool = ["R20231", "R09645", "R06690", "R19634"]
    planner, _ = build_planner({"lunch": pool, "dinner": pool})
    state = user_state([{"ingredient_name": "olive oil", "quantity": 30, "unit": "ml"}],
                       budget=150.0, cook_frequency=1, leftover_storage_days=2)
    snapshot = copy.deepcopy(state)

    result = planner.plan_meals(user_state=state, start_date=date(2026, 10, 18),
                                days=3, meal_types=["lunch", "dinner"])
    plan_dict = result["plan"]
    schedule = plan_dict["cooking_schedule"]

    assert len(plan_dict["selected_meals"]) == 6
    assert schedule["weekly_session_counts"] == {"2026-10-18/2026-10-24": 1}
    [session] = schedule["sessions"]
    assert session["portions_prepared"] == 6
    assert len({m["recipe_id"] for m in plan_dict["selected_meals"]}) == 1
    # Inventory reflects the batch actually selected, and no estimated
    # or unresolved line is reported as verified.
    assert reconciliation_event(plan_dict) is not None
    for item in result["grocery_basket"]["items"]:
        if item.get("package_conversion_status") != "exact":
            assert item.get("quantity_coverage_verified") is not True
    assert state == snapshot
