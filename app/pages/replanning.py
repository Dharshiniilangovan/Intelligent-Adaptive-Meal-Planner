"""Adjust My Plan: only skip an upcoming meal or mark meals eaten."""
from datetime import date
import streamlit as st
from app.components.presentation import friendly_date, meal_label, show_meals
from app.components.state_persistence import get_workspace_id, save_ui_state
from app.components.background_jobs import start_background_job, read_background_job
from app.components.planning_jobs import read_job


def slot_of(meal):
    return meal.get("slot") or {}


def slot_id_of(meal):
    return slot_of(meal).get("slot_id")


def day_of(meal):
    slot = slot_of(meal)
    return str(slot.get("date") or str(slot.get("slot_id") or "")[:10])


def label_of(meal):
    slot = slot_of(meal)
    return f"{friendly_date(day_of(meal))} · {str(slot.get('meal_type') or 'Meal').title()} — {meal_label(meal)}"


st.title("Adjust your meal plan")
st.caption("Skip an upcoming meal or mark meals you have already eaten.")
result = st.session_state.get("planner_result") or {}
plan = result.get("plan") or {}
meals = plan.get("selected_meals") or []
planner = st.session_state.get("live_planner")
plan_state = st.session_state.get("live_plan_state")
user_state = st.session_state.get("planner_user_state")
completed = set(st.session_state.get("completed_slot_ids") or [])
workspace = get_workspace_id()

planning_id = st.session_state.get("planning_job_id")
planning_job = read_job(workspace, planning_id) if planning_id else None
is_generating = bool(planning_job and planning_job.get("status") in {"queued", "running"})
replan_id = st.session_state.get("replanning_job_id")
replan_job = read_background_job(workspace, replan_id) if replan_id else None
is_replanning = bool(replan_job and replan_job.get("status") in {"queued", "running"})

if is_replanning:
    st.info("Your remaining meals are being updated. You can browse other pages while this runs.")
    if st.button("Check meal update status"):
        st.rerun()
if st.session_state.get("replanning_error"):
    st.error(st.session_state["replanning_error"])
if st.session_state.pop("replanning_done", False):
    st.success("Your meal plan has been updated.")

if not meals:
    st.info("Your meal plan is being prepared." if is_generating else "Create a meal plan first to make adjustments.")
else:
    can_replan = all(x is not None for x in (planner, plan_state, user_state))
    if not can_replan:
        st.info("Your saved meals are available below, but skipping meals requires the original live planning session.")

    # The backend owns skip history; read it from the live PlanState when possible.
    skipped = set()
    for entry in (plan.get("skipped_slots") or []):
        if isinstance(entry, dict):
            skipped.add(entry.get("slot_id"))
        elif isinstance(entry, str):
            skipped.add(entry)
    if plan_state is not None:
        for entry in (getattr(plan_state, "skipped_slots", None) or []):
            if isinstance(entry, dict):
                skipped.add(entry.get("slot_id"))
            elif isinstance(entry, str):
                skipped.add(entry)

    st.subheader("Skip an upcoming meal")
    today = date.today().isoformat()
    choices = {}
    for meal in meals:
        sid = slot_id_of(meal)
        day = day_of(meal)
        if sid and sid not in completed and sid not in skipped and day >= today:
            choices[label_of(meal)] = sid
    if choices:
        selected = st.selectbox("Choose the meal you want to skip", list(choices), key="skip_meal_selection")
        st.caption("Completed meals stay unchanged. The remaining plan and shopping list will be recalculated.")
        if st.button("Skip meal and update plan", type="primary", use_container_width=True,
                     disabled=not can_replan or is_generating or is_replanning):
            try:
                job_id = start_background_job(
                    workspace, "replan", planner=planner, user_state=user_state,
                    plan_state=plan_state, slot_id=choices[selected], completed=set(completed),
                )
                st.session_state["replanning_job_id"] = job_id
                st.session_state["replanning_error"] = None
                save_ui_state()
                st.rerun()
            except Exception as exc:
                print("[REPLANNING START ERROR]", repr(exc))
                st.error("Could not start updating your plan.")
    else:
        st.info("There are no upcoming meals available to skip.")

    st.divider()
    with st.expander("Mark meals already eaten"):
        labels = {}
        for meal in meals:
            sid = slot_id_of(meal)
            if sid and sid not in skipped:
                labels[label_of(meal)] = sid
        defaults = [label for label, sid in labels.items() if sid in completed]
        selected_completed = st.multiselect("Meals completed", list(labels), default=defaults, key="completed_meals_selection")
        if st.button("Save completed meals", disabled=is_generating or is_replanning):
            previous = set(completed)
            st.session_state["completed_slot_ids"] = {labels[label] for label in selected_completed}
            try:
                save_ui_state()
            except Exception as exc:
                st.session_state["completed_slot_ids"] = previous
                print("[COMPLETED MEALS SAVE ERROR]", repr(exc))
                st.error("Could not save completed meals.")
            else:
                st.success("Completed meals saved.")

    st.divider()
    st.subheader("Your current meals")
    show_meals(meals)
