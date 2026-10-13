
"""Convert Streamlit preferences to the canonical GC1 User State."""

import json
import math
import os
import tempfile
import uuid

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
USER_DIR = ROOT / "data" / "users"
PANTRY_DIR = ROOT / "data" / "sample"


USER_STATE_FIELDS = (
    "user_id",
    "budget",
    "cook_frequency",
    "cook_time_preference_hrs",
    "preferred_cuisines",
    "dietary_restrictions",
    "allergies",
    "preferred_meal_types",
    "preferred_ingredients",
    "disliked_ingredients",
    "budget_flexible",
    "budget_cap",
    "ingredient_availability",
)


def positive_quantity(value):
    if value is None or isinstance(value, bool):
        return None

    try:
        quantity = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(quantity) or quantity <= 0:
        return None

    return quantity


def format_quantity(quantity, unit):
    quantity = positive_quantity(quantity)
    unit = str(unit or "").strip()

    if quantity is None or not unit:
        return "Unknown"

    return f"{quantity:g} {unit}"


def convert_pantry(pantry_items):
    availability = {}

    for item in pantry_items or []:
        if not isinstance(item, dict):
            continue

        name = str(
            item.get("ingredient_name")
            or item.get("name")
            or ""
        ).strip()

        if not name:
            continue

        availability[name] = format_quantity(
            item.get("quantity"),
            item.get("unit"),
        )

    return availability


def clean_list(value):
    if not isinstance(value, list):
        return []

    return list(dict.fromkeys(
        str(item).strip()
        for item in value
        if item is not None and str(item).strip()
    ))


def build_ui_user_state(
    confirmed,
    pantry_items,
    user_id=None,
):
    """Return only the fields required by the GC1 User State."""

    existing_id = (
        user_id
        or confirmed.get("user_id")
    )

    uid = (
        str(uuid.UUID(str(existing_id)))
        if existing_id
        else str(uuid.uuid4())
    )

    budget = float(confirmed["budget"])

    if not math.isfinite(budget) or budget <= 0:
        raise ValueError("Budget must be positive.")

    flexible = bool(
        confirmed.get("budget_flexible", False)
    )

    frequency = confirmed.get("cook_frequency")

    if frequency is not None:
        frequency = int(frequency)

    cooking_hours = confirmed.get(
        "cook_time_preference_hrs"
    )

    if cooking_hours is not None:
        cooking_hours = float(cooking_hours)

    state = {
        "user_id": uid,
        "budget": budget,
        "cook_frequency": frequency,
        "cook_time_preference_hrs": cooking_hours,
        "preferred_cuisines": clean_list(
            confirmed.get("preferred_cuisines")
        ),
        "dietary_restrictions": clean_list(
            confirmed.get("dietary_restrictions")
        ),
        "allergies": clean_list(
            confirmed.get("allergies")
        ),
        "preferred_meal_types": clean_list(
            confirmed.get("preferred_meal_types")
        ),
        "preferred_ingredients": clean_list(
            confirmed.get("preferred_ingredients")
        ),
        "disliked_ingredients": clean_list(
            confirmed.get("disliked_ingredients")
        ),
        "budget_flexible": flexible,
        "budget_cap": budget + 5.0 if flexible else None,
        "ingredient_availability": convert_pantry(
            pantry_items
        ),
    }

    return state


def atomic_save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary = tempfile.mkstemp(
        prefix=".gc1_",
        suffix=".json",
        dir=path.parent,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                payload,
                f,
                indent=4,
                ensure_ascii=False,
            )

        os.replace(temporary, path)

    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save_canonical_user_state(state):
    """Save the exact User State and its corresponding pantry."""

    uid = str(uuid.UUID(str(state["user_id"])))

    user_path = USER_DIR / f"user_state_{uid}.json"
    pantry_path = PANTRY_DIR / f"pantry_{uid}.json"

    canonical = {
        field: state[field]
        for field in USER_STATE_FIELDS
    }

    pantry_items = []

    for name, value in canonical[
        "ingredient_availability"
    ].items():

        parts = str(value).strip().split(maxsplit=1)

        if len(parts) != 2:
            continue

        quantity = positive_quantity(parts[0])
        unit = parts[1].strip()

        if quantity is None or not unit:
            continue

        pantry_items.append({
            "name": name,
            "quantity": quantity,
            "unit": unit,
        })

    atomic_save(
        pantry_path,
        {
            "user_id": uid,
            "items": pantry_items,
        },
    )

    atomic_save(user_path, canonical)

    print("[USER STATE] Saved:", user_path)
    print("[PANTRY] Saved:", pantry_path)

    return user_path, pantry_path
