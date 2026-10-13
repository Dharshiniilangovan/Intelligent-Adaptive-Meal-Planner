
"""Background generation jobs for IAMP."""

import json
import logging
import threading
import uuid

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app.components.planner_bridge import generate
from app.components.state_persistence import (
    STATE_DIR,
    atomic_write_json,
    validate_workspace_id,
)


logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="iamp-planning",
)

_LOCK = threading.RLock()
_ACTIVE = {}
_LIVE_RESULTS = {}


def now():
    return datetime.now(timezone.utc).isoformat()


def job_path(workspace_id, job_id):
    workspace_id = validate_workspace_id(workspace_id)
    job_id = str(uuid.UUID(str(job_id)))

    return (
        STATE_DIR
        / "jobs"
        / workspace_id
        / f"{job_id}.json"
    )


def read_job(workspace_id, job_id):
    if not job_id:
        return None

    path = job_path(workspace_id, job_id)

    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        logger.exception(
            "[PLAN JOB READ ERROR] job=%s",
            job_id,
        )
        return None


def write_job(workspace_id, job_id, payload):
    atomic_write_json(
        job_path(workspace_id, job_id),
        payload,
    )


def _worker(workspace_id, job_id, confirmed):
    """Run the backend without touching Streamlit."""

    job = read_job(workspace_id, job_id)

    if job is None:
        return

    job["status"] = "running"
    job["started_at"] = now()
    write_job(workspace_id, job_id, job)

    logger.info(
        "[PLAN START] workspace=%s job=%s",
        workspace_id,
        job_id,
    )

    try:
        result, plan_state, planner_state, planner = (
            generate(deepcopy(confirmed))
        )

        if not isinstance(result, dict):
            raise TypeError(
                "Planner returned an invalid result."
            )

        # Store the live objects in process memory for replanning.
        with _LOCK:
            _LIVE_RESULTS[(workspace_id, job_id)] = {
                "plan_state": plan_state,
                "planner_state": planner_state,
                "planner": planner,
            }

        # Save the completed result before marking the job done.
        job["result"] = result
        job["status"] = "completed"
        job["finished_at"] = now()
        job["error"] = None

        write_job(workspace_id, job_id, job)

        logger.info(
            "[PLAN COMPLETE] workspace=%s job=%s",
            workspace_id,
            job_id,
        )

    except Exception as exc:
        logger.exception(
            "[PLAN FAILED] workspace=%s job=%s",
            workspace_id,
            job_id,
        )

        failed = {
            "job_id": job_id,
            "workspace_id": workspace_id,
            "status": "failed",
            "error": str(exc),
            "finished_at": now(),
        }

        write_job(workspace_id, job_id, failed)

    finally:
        with _LOCK:
            if _ACTIVE.get(workspace_id) == job_id:
                _ACTIVE.pop(workspace_id, None)


def start_job(workspace_id, confirmed):
    """Start generation or reuse an active workspace job."""

    workspace_id = validate_workspace_id(workspace_id)

    if not isinstance(confirmed, dict):
        raise ValueError(
            "Confirmed preferences are required."
        )

    with _LOCK:
        active_id = _ACTIVE.get(workspace_id)

        if active_id:
            active = read_job(workspace_id, active_id)

            if active and active.get("status") in (
                "queued",
                "running",
            ):
                return active_id

        job_id = str(uuid.uuid4())

        job = {
            "job_id": job_id,
            "workspace_id": workspace_id,
            "status": "queued",
            "created_at": now(),
            "started_at": None,
            "finished_at": None,
            "error": None,
            "result": None,
        }

        write_job(workspace_id, job_id, job)

        _ACTIVE[workspace_id] = job_id

        try:
            _EXECUTOR.submit(
                _worker,
                workspace_id,
                job_id,
                deepcopy(confirmed),
            )
        except Exception:
            _ACTIVE.pop(workspace_id, None)
            raise

        return job_id


def get_live_objects(workspace_id, job_id):
    with _LOCK:
        return _LIVE_RESULTS.get(
            (workspace_id, job_id)
        )
