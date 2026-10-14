"""Background pantry detection and adaptive replanning jobs.

Jobs survive page navigation, but running threads do not survive a server restart.
"""
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone

from app.components.state_persistence import STATE_DIR, atomic_write_json, validate_workspace_id

LOG = logging.getLogger(__name__)
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="iamp-extra")
_LOCK = threading.RLock()
_ACTIVE = {}
_LIVE = {}


def _time():
    return datetime.now(timezone.utc).isoformat()


def _path(workspace_id, job_id):
    workspace_id = validate_workspace_id(workspace_id)
    job_id = str(uuid.UUID(str(job_id)))
    return STATE_DIR / "background_jobs" / workspace_id / f"{job_id}.json"


def read_background_job(workspace_id, job_id):
    if not job_id:
        return None
    try:
        path = _path(workspace_id, job_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError, TypeError):
        LOG.exception("Cannot read background job %s", job_id)
        return None


def _write(job):
    atomic_write_json(_path(job["workspace_id"], job["job_id"]), job)


def _detect(image_bytes, mime_type):
    from src.pantry.image_pantry import (
        detect_image, refine_missing_quantities, match_to_kb,
        consolidate_ingredients, load_kb,
    )
    detections = detect_image(image_bytes, mime_type=mime_type)
    if isinstance(detections, dict):
        detections = detections.get("ingredients") or []
    detections = refine_missing_quantities(detections, image_bytes, mime_type=mime_type)
    if isinstance(detections, dict):
        detections = detections.get("ingredients") or []
    return consolidate_ingredients(match_to_kb(detections, kb=load_kb()))


def _work(job, args):
    key = (job["workspace_id"], job["kind"])
    job = dict(job)
    try:
        print(f"[BACKGROUND JOB RUNNING] kind={job['kind']} id={job['job_id']}", flush=True)
        job["status"] = "running"
        job["started_at"] = _time()
        _write(job)
        if job["kind"] == "pantry":
            result = _detect(args["image_bytes"], args["mime_type"])
        elif job["kind"] == "replan":
            from app.components.planner_bridge import skip_meal
            # Never mutate the currently displayed PlanState during work.
            planner = args["planner"]
            plan_state = deepcopy(args["plan_state"])
            user_state = deepcopy(args["user_state"])
            user_state["approved_leftover_ids"] = list(args.get("approved_leftover_ids", []))
            print(f"[REPLAN START] slot={args['slot_id']} completed={len(args['completed'])} approved_leftovers={len(user_state['approved_leftover_ids'])}", flush=True)
            result, updated_state = skip_meal(
                planner, user_state, plan_state,
                args["slot_id"], set(args["completed"]),
            )
            with _LOCK:
                _LIVE[(job["workspace_id"], job["job_id"])] = {
                    "planner": planner,
                    "plan_state": updated_state,
                    "user_state": user_state,
                }
        else:
            raise ValueError("Unsupported job kind")
        job["result"] = result
        job["status"] = "completed"
        job["finished_at"] = _time()
        _write(job)
        LOG.info("Background job completed: %s", job["job_id"])
        print(f"[BACKGROUND JOB COMPLETED] kind={job['kind']} id={job['job_id']}", flush=True)
    except Exception as exc:
        LOG.exception("Background job failed: %s", job["job_id"])
        print(f"[BACKGROUND JOB FAILED] kind={job['kind']} id={job['job_id']} error={exc}", flush=True)
        job["status"] = "failed"
        job["error"] = str(exc)
        job["finished_at"] = _time()
        _write(job)
    finally:
        with _LOCK:
            if _ACTIVE.get(key) == job["job_id"]:
                _ACTIVE.pop(key, None)


def start_background_job(workspace_id, kind, **kwargs):
    workspace_id = validate_workspace_id(workspace_id)
    if kind not in {"pantry", "replan"}:
        raise ValueError("Unsupported job kind")
    key = (workspace_id, kind)
    with _LOCK:
        existing = _ACTIVE.get(key)
        if existing:
            current = read_background_job(workspace_id, existing)
            if current and current.get("status") in {"queued", "running"}:
                return existing
        job_id = str(uuid.uuid4())
        job = {
            "workspace_id": workspace_id, "job_id": job_id, "kind": kind,
            "status": "queued", "created_at": _time(),
            "started_at": None, "finished_at": None,
            "result": None, "error": None,
        }
        _write(job)
        _ACTIVE[key] = job_id
        print(f"[BACKGROUND JOB QUEUED] kind={kind} id={job_id}", flush=True)
        try:
            _POOL.submit(_work, job, kwargs)
        except Exception:
            _ACTIVE.pop(key, None)
            raise
        return job_id


def get_live_replan(workspace_id, job_id):
    with _LOCK:
        return _LIVE.get((validate_workspace_id(workspace_id), job_id))
