"""Adaptive replanning: completed meals, prepared leftovers, and skipped slots."""
from datetime import date
from uuid import uuid4
import streamlit as st
from app.components.presentation import friendly_date, meal_label, show_meals
from app.components.state_persistence import get_workspace_id, save_ui_state
from app.components.background_jobs import start_background_job, read_background_job
from app.components.planning_jobs import read_job
from app.components.recipe_lookup import get_recipe_name


def slot_of(meal):
    return meal.get("slot") or {}


def slot_id_of(meal):
    return slot_of(meal).get("slot_id")


def day_of(meal):
    slot = slot_of(meal)
    return str(slot.get("date") or str(slot.get("slot_id") or "")[:10])


def label_of(meal):
    slot = slot_of(meal)
    recipe_id = meal.get("recipe_id") or (meal.get("decision") or {}).get("recipe_id")
    return f"{friendly_date(day_of(meal))} · {str(slot.get('meal_type') or 'Meal').title()} — {get_recipe_name(recipe_id)}"


def get_leftovers(plan_state, plan):
    if plan_state is not None:
        return list(getattr(plan_state, "prepared_leftovers", []) or [])
    return list(plan.get("prepared_leftovers") or [])


st.title("Adjust your meal plan")
st.caption("Mark meals eaten, record prepared leftovers, or skip an upcoming meal. Budget and preferences stay unchanged.")
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
locked = is_generating or is_replanning

if is_replanning:
    st.info("Replanning is in progress. You can visit other pages; the result will appear here when ready.")
    st.status("Updating your remaining meals...", state="running")

    @st.fragment(run_every="3s")
    def watch_replanning():
        current_id = st.session_state.get("replanning_job_id")
        current = read_background_job(workspace, current_id) if current_id else None
        status = current.get("status") if current else "unknown"
        if status in {"queued", "running"}:
            st.caption(f"Replanning status: {status.title()} (checking automatically every 3 seconds)")
        else:
            # Synchronize the completed result before redrawing the page.
            from app.components.background_status import sync_background_jobs
            sync_background_jobs()
            st.rerun(scope="app")

    watch_replanning()
if st.session_state.get("replanning_error"):
    st.error(st.session_state["replanning_error"])
if st.session_state.pop("replanning_done", False):
    st.success("Your meal plan was updated.")



if not meals:
    st.info("Your meal plan is being prepared." if is_generating else "No planned meals are available. Create a plan first.")
else:
    can_replan = all(x is not None for x in (planner, plan_state, user_state))
    if not can_replan:
        st.warning("Saved meals are available, but editing requires the live planning state. Reopen the original active session.")

    skipped = set()
    for entry in (plan.get("skipped_slots") or []):
        skipped.add(entry.get("slot_id") if isinstance(entry, dict) else entry)
    if plan_state is not None:
        for entry in (getattr(plan_state, "skipped_slots", []) or []):
            skipped.add(entry.get("slot_id") if isinstance(entry, dict) else entry)

    st.subheader("Mark meals already eaten")
    labels = {label_of(m): slot_id_of(m) for m in meals if slot_id_of(m) and slot_id_of(m) not in skipped}
    # Use a form to avoid rerunning the entire page on each checkbox selection.
    with st.form("completed_meals_form"):
        selected_completed = st.multiselect(
            "Meals completed", list(labels),
            default=[label for label, sid in labels.items() if sid in completed],
            key=f"completed_select_{st.session_state.get('completed_selection_revision', 0)}",
        )
        save_completed = st.form_submit_button("Save completed meals", disabled=locked)
    if save_completed:
        previous = set(completed)
        updated = {labels[label] for label in selected_completed}
        st.session_state["completed_slot_ids"] = updated
        try:
            save_ui_state()
        except Exception as exc:
            st.session_state["completed_slot_ids"] = previous
            st.error(f"Could not save completed meals: {exc}")
        else:
            completed = updated
            st.session_state["completed_selection_revision"] = (
                st.session_state.get("completed_selection_revision", 0) + 1
            )
            st.rerun()

    st.divider()
    st.subheader("Prepared leftovers")
    st.caption("Only record servings already cooked and safely stored. Replanning uses only leftovers you explicitly approve.")
    leftovers = get_leftovers(plan_state, plan)
    if leftovers:
        for leftover in leftovers:
            st.write(
                f"{leftover.get('leftover_id')} · {get_recipe_name(leftover.get('recipe_id'))} · "
                f"{leftover.get('servings_remaining', 0)} serving(s) · "
                f"{leftover.get('storage', 'unknown storage')} · "
                f"Expires {leftover.get('expires_on', 'unknown')}"
            )
    else:
        st.caption("No prepared leftovers recorded.")

    # Record only leftovers from meals in this plan. Never invent an expiry date.
    if can_replan:
        recipe_options = {}
        for meal in meals:
            recipe_id = meal.get("recipe_id")
            if recipe_id:
                recipe_options.setdefault(f"{meal_label(meal)} [{recipe_id}]", str(recipe_id))
        with st.expander("Record prepared leftovers"):
            if recipe_options:
                with st.form("record_leftovers_form"):
                    recipe_label = st.selectbox("Cooked recipe", list(recipe_options))
                    servings = st.number_input("Remaining cooked servings", min_value=1, step=1, value=1)
                    prepared = st.date_input("Prepared on", value=date.today())
                    expires = st.date_input("Use by", value=date.today())
                    storage = st.selectbox("Storage", ["refrigerated", "frozen"])
                    record = st.form_submit_button("Record leftovers", disabled=locked)
                if record:
                    if expires < prepared:
                        st.error("Use-by date must not precede the preparation date.")
                    elif prepared > date.today():
                        st.error("Preparation date cannot be in the future.")
                    else:
                        try:
                            leftover_id = "L" + uuid4().hex[:12].upper()
                            plan_state.record_prepared_leftover(
                                leftover_id=leftover_id,
                                recipe_id=recipe_options[recipe_label],
                                servings_remaining=int(servings),
                                prepared_date=prepared.isoformat(),
                                storage=storage,
                                expires_on=expires.isoformat(),
                            )
                            # Preserve nutrition metadata when available for the chosen recipe.
                            selected_meal = next((m for m in meals if str(m.get("recipe_id")) == recipe_options[recipe_label]), None)
                            if selected_meal:
                                nutrition = (selected_meal.get("decision") or {}).get("recipe") or {}
                                if nutrition:
                                    plan_state.prepared_leftovers[-1]["nutrition"] = nutrition
                            st.session_state["live_plan_state"] = plan_state
                            # Persist a serializable snapshot for display after refresh.
                            if isinstance(result.get("plan"), dict):
                                result["plan"]["prepared_leftovers"] = list(plan_state.prepared_leftovers)
                            save_ui_state()
                            st.success("Prepared leftovers recorded. Approve them below when skipping a meal.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Could not record leftovers: {exc}")

    st.divider()
    st.subheader("Skip an upcoming meal")
    today = date.today()
    choices = {}
    for meal in meals:
        sid = slot_id_of(meal)
        try:
            upcoming = date.fromisoformat(day_of(meal)) >= today
        except ValueError:
            upcoming = False
        if sid and sid not in completed and sid not in skipped and upcoming:
            choices[label_of(meal)] = sid

    # Backend checks dates and remaining servings before allocation.
    approved_options = {}
    for leftover in get_leftovers(plan_state, plan):
        try:
            valid = (
                int(leftover.get("servings_remaining") or 0) > 0
                and bool(leftover.get("storage"))
                and date.fromisoformat(str(leftover.get("expires_on"))) >= today
            )
        except (ValueError, TypeError):
            valid = False
        if valid and leftover.get("leftover_id"):
            recipe_name = get_recipe_name(
                            leftover.get("recipe_id")
                        )
            key = (
                f"{recipe_name}"
                f" · {leftover.get('servings_remaining', 0)} serving(s)"
                f" · Use by {friendly_date(leftover.get('expires_on'))}"
                f" · {leftover['leftover_id']}"
            )
            
            approved_options[key] = leftover["leftover_id"]

    if choices:
        with st.form("skip_meal_form"):
            selected = st.selectbox("Meal to skip", list(choices))
            approvals = st.multiselect(
                "Approve prepared leftovers for eligible remaining meals (optional)",
                list(approved_options),
            ) if approved_options else []
            st.caption("The skipped slot is removed. Completed meals remain fixed; approved leftovers may fill other unfinished slots.")
            submit_skip = st.form_submit_button("Skip meal and update plan", disabled=locked or not can_replan)
        if submit_skip:
            try:
                job_id = start_background_job(
                    workspace, "replan", planner=planner,
                    user_state=user_state, plan_state=plan_state,
                    slot_id=choices[selected], completed=set(completed),
                    approved_leftover_ids=[approved_options[x] for x in approvals],
                )
                print(f"[REPLAN UI SUBMITTED] job={job_id} slot={choices[selected]}", flush=True)
                st.session_state["replanning_job_id"] = job_id
                st.session_state["replanning_error"] = None
                save_ui_state()
                st.rerun()
            except Exception as exc:
                st.error(f"Could not start replanning: {exc}")
    else:
        st.info("There are no upcoming uncompleted meals available to skip.")

    st.divider()
    upcoming_display = [
        meal for meal in meals
        if slot_id_of(meal) not in completed
        and slot_id_of(meal) not in skipped
    ]
    completed_display = [
        meal for meal in meals if slot_id_of(meal) in completed
    ]
    st.subheader("Current meals")
    if upcoming_display:
        show_meals(upcoming_display)
    else:
        st.info("No uncompleted meals remain in your current plan.")

    with st.expander(f"Meals already eaten ({len(completed_display)})"):
        if completed_display:
            show_meals(completed_display)
        else:
            st.caption("No meals marked as eaten yet.")
