"""Headless driver for the unchanged Streamlit replanning page.

Each run mirrors app/streamlit_app.py: restore the saved workspace,
sync finished planning and replanning jobs, then run
app/pages/replanning.py. (AppTest.switch_page would run the page alone,
skipping those steps.) The planner is the deterministic harness
planner; job and workspace files go to `state_dir`. show_meals is
wrapped to record exactly which meals Current meals and Meals already
eaten receive; rendering is unchanged.
"""
import time
import uuid
from pathlib import Path

ROOT = str(Path(__file__).resolve().parents[1])
POOL = ["R28835", "R20231", "R19634", "R09645", "R03304", "R02821", "R18958", "R06690"]
CONFIRMED = {
    "user_id": "FLOW_USER", "budget": 200.0, "cook_frequency": None,
    "cook_time_preference_hrs": 0.5, "preferred_cuisines": ["asian"],
    "dietary_restrictions": ["vegetarian"], "allergies": [],
    "preferred_meal_types": ["lunch", "dinner"], "preferred_ingredients": [],
    "disliked_ingredients": [], "budget_flexible": False, "budget_cap": None,
    "ingredient_availability": {"olive oil": {"quantity": 30, "unit": "ml"}},
}

SCRIPT = """
import runpy, sys
sys.path.insert(0, {root!r})
import streamlit as st
from app.components.state_persistence import load_ui_state
from app.components.planning_status import sync_planning_job
from app.components.background_status import sync_background_jobs
load_ui_state()
st.session_state.setdefault("completed_slot_ids", set())
st.session_state.setdefault("planning_job_id", None)
sync_planning_job()
sync_background_jobs()
runpy.run_path({root!r} + "/app/pages/replanning.py", run_name="__main__")
"""


class Flow:
    def __init__(self, state_dir, monkeypatch, workspace=None):
        import app.components.background_jobs as bj
        import app.components.planner_bridge as bridge
        import app.components.planning_jobs as pj
        import app.components.presentation as presentation
        import app.components.state_persistence as sp
        from tests.planning_harness import build_planner

        for module in (sp, bj, pj):
            monkeypatch.setattr(module, "STATE_DIR", Path(state_dir))
        monkeypatch.setattr(
            bridge, "get_planner",
            lambda: build_planner({"lunch": POOL, "dinner": POOL})[0])
        self.rendered = []
        original = presentation.show_meals

        def recording_show_meals(meals):
            self.rendered.append([dict(m) for m in meals or []])
            return original(meals)

        monkeypatch.setattr(presentation, "show_meals", recording_show_meals)
        self.bj, self.pj = bj, pj
        self.state_dir = Path(state_dir)
        self.workspace = workspace or str(uuid.uuid4())
        self.at = None

    def open(self):
        from streamlit.testing.v1 import AppTest
        self.at = AppTest.from_string(SCRIPT.format(root=ROOT), default_timeout=600)
        self.at.session_state["workspace_id"] = self.workspace
        return self.run()

    def run(self):
        self.rendered = []
        self.at.run()
        assert not self.at.exception, self.at.exception
        return self

    def generate(self, start="2026-10-15", days=5):
        self.at.session_state["confirmed_user_state"] = dict(CONFIRMED)
        job = self.pj.start_job(self.workspace, dict(CONFIRMED, start_date=start, days=days))
        self.at.session_state["planning_job_id"] = job
        self._wait(self.pj.read_job, job)
        return self.run()

    def _wait(self, read, job_id, timeout=300):
        deadline = time.time() + timeout
        while (read(self.workspace, job_id) or {}).get("status") in ("queued", "running"):
            assert time.time() < deadline, "job timed out"
            time.sleep(0.3)

    # ---------------- UI actions (existing controls) ----------------
    def button(self, label):
        return next(b for b in self.at.button if b.label == label)

    def select_completed(self, prefixes):
        widget = self.at.multiselect[0]
        widget.set_value([o for o in widget.options if o.startswith(tuple(prefixes))])
        return self

    def save_completed(self, prefixes):
        self.select_completed(prefixes)
        self.button("Save completed meals").click()
        return self.run()

    def record_leftover(self, recipe_id, prepared, use_by, servings=1):
        self.at.selectbox[0].set_value(
            next(o for o in self.at.selectbox[0].options if f"[{recipe_id}]" in o))
        self.at.number_input[0].set_value(servings)
        self.at.date_input[0].set_value(prepared)
        self.at.date_input[1].set_value(use_by)
        self.button("Record leftovers").click()
        return self.run()

    def skip(self, prefix, approve_all=True):
        widget = next(s for s in self.at.selectbox if s.label == "Meal to skip")
        widget.set_value(next(o for o in widget.options if o.startswith(prefix)))
        approvals = [m for m in self.at.multiselect if m.label.startswith("Approve")]
        if approve_all and approvals:
            approvals[0].set_value(approvals[0].options)
        self.button("Skip meal and update plan").click()
        self.run()
        self._wait(self.bj.read_background_job, self.at.session_state["replanning_job_id"])
        return self.run()

    # ---------------- observations ----------------
    @property
    def plan(self):
        return self.at.session_state["planner_result"]["plan"]

    @property
    def completed(self):
        return set(self.at.session_state["completed_slot_ids"])

    @property
    def current_meal_slots(self):
        return [m["slot"]["slot_id"] for m in self.rendered[0]] if self.rendered else []

    @property
    def history_meal_slots(self):
        return [m["slot"]["slot_id"] for m in self.rendered[1]] if len(self.rendered) > 1 else []

    def meal(self, slot_id):
        return next(m for m in self.plan["selected_meals"] if m["slot"]["slot_id"] == slot_id)

    def saved_workspace(self):
        import json
        return json.loads((self.state_dir / f"{self.workspace}.json").read_text())
