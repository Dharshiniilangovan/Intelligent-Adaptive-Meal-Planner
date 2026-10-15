"""Minimal batch-cooking schedule for selected meals."""

from collections import defaultdict
from datetime import date, timedelta

# Cooking frequency is "sessions per week" of the user's own plan:
# consecutive 7-day windows starting on the planning start date.
WINDOW_DAYS = 7


def cooking_window(day: date, window_start: date) -> tuple[date, date]:
    """The 7-day planning window that contains `day`."""
    index = (day - window_start).days // WINDOW_DAYS
    start = window_start + timedelta(days=index * WINDOW_DAYS)
    return start, start + timedelta(days=WINDOW_DAYS - 1)


def window_label(day: date, window_start: date) -> str:
    start, end = cooking_window(day, window_start)
    return f"{start.isoformat()}/{end.isoformat()}"


def build_cooking_schedule(
    selected_meals: list[dict],
    max_sessions: int,
    max_storage_days: int = 1,
    window_start: date | None = None,
) -> dict:
    """Group meals into cooking sessions and check the frequency cap.

    One session cooks one recipe; it serves every portion of that
    recipe eaten within `max_storage_days` of the cook date. At most
    `max_sessions` sessions may start in each 7-day window counted from
    `window_start` (the planning start date; defaults to the earliest
    cooked meal). Calendar (ISO) weeks are not used, so a plan that
    starts mid-week does not get extra sessions at the week boundary.
    """
    if not isinstance(max_sessions, int) or isinstance(max_sessions, bool):
        raise ValueError("Cooking sessions must be an integer")

    if max_sessions < 1:
        raise ValueError("Cooking sessions must be at least 1")

    if max_storage_days < 0:
        raise ValueError("Storage days cannot be negative")

    grouped = defaultdict(list)

    for meal in selected_meals:

        # Prepared leftovers are already cooked.
        # Do not count them as new cooking sessions.
        if meal.get("meal_source") == "prepared_leftover":
            continue

        slot = meal["slot"]

        grouped[meal["recipe_id"]].append(
            {
                "slot_id": slot["slot_id"],
                "date": date.fromisoformat(slot["date"]),
            }
        )

    sessions = []

    for recipe_id, meals in sorted(grouped.items()):
        meals.sort(key=lambda x: (x["date"], x["slot_id"]))

        batch = []

        def finish_batch(items):
            if not items:
                return

            sessions.append(
                {
                    "session_id": f"B{len(sessions) + 1:03d}",
                    "recipe_id": recipe_id,
                    "cook_date": items[0]["date"].isoformat(),
                    "portions_prepared": len(items),
                    "meal_slot_ids": [
                        item["slot_id"] for item in items
                    ],
                }
            )

        for meal in meals:
            if not batch:
                batch = [meal]
                continue

            age = (meal["date"] - batch[0]["date"]).days

            if age <= max_storage_days:
                batch.append(meal)
            else:
                finish_batch(batch)
                batch = [meal]

        finish_batch(batch)

    sessions.sort(
        key=lambda s: (s["cook_date"], s["session_id"])
    )

    if window_start is None and sessions:
        window_start = date.fromisoformat(sessions[0]["cook_date"])

    # Enforce the limit within each 7-day planning window.
    weekly_counts = defaultdict(int)

    for session in sessions:
        label = window_label(
            date.fromisoformat(session["cook_date"]), window_start
        )
        session["window"] = label
        weekly_counts[label] += 1

    violations = {
        window: count
        for window, count in weekly_counts.items()
        if count > max_sessions
    }

    return {
        "sessions": sessions,
        "session_count": len(sessions),
        "weekly_session_counts": dict(weekly_counts),
        "max_sessions_per_week": max_sessions,
        "window_basis": "planning_start_date",
        "window_start": window_start.isoformat() if window_start else None,
        "valid": not violations,
        "violations": violations,
        "storage_assumption_days": max_storage_days,
    }


def max_coverable_slots(
    slots: list[dict],
    max_sessions: int,
    max_storage_days: int,
    window_start: date,
    sessions_used: dict | None = None,
    portions_per_session: int | None = None,
) -> int:
    """Most of `slots` that new cooking sessions could still serve.

    `slots` are {"date": date, ...} in plan order. A session starts on
    a slot's date and serves up to `portions_per_session` consecutive
    slots eaten within `max_storage_days` of cooking. `sessions_used`
    maps window labels to sessions already scheduled. This is the
    cooking-capacity limit only: recipe availability is not checked.
    """
    from functools import lru_cache

    used = dict(sessions_used or {})
    dates = [slot["date"] for slot in slots]
    labels = [window_label(day, window_start) for day in dates]
    count = len(dates)

    @lru_cache(maxsize=None)
    def best(index, label, spent):
        if index >= count:
            return 0
        # Leave this slot unfilled.
        result = best(index + 1, label, spent)
        # Or start a session here, if the window still allows one.
        here = labels[index]
        in_window = spent if here == label else 0
        if used.get(here, 0) + in_window < max_sessions:
            end = index
            limit = portions_per_session or count
            while (
                end + 1 < count
                and end + 1 - index < limit
                and (dates[end + 1] - dates[index]).days <= max_storage_days
            ):
                end += 1
            served = end - index + 1
            result = max(
                result, served + best(end + 1, here, in_window + 1)
            )
        return result

    return best(0, None, 0)
