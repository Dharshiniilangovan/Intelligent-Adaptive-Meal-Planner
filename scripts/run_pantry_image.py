"""Run from project root: python -m scripts.run_pantry_image --image PATH.
Output: ingredient_availability JSON saved in User State and printed.
"""
import argparse
import json
import mimetypes
import math
import os
import tempfile
from pathlib import Path

from src.pantry.image_pantry import (
    detect_image, refine_missing_quantities, load_kb,
    match_to_kb, consolidate_ingredients, format_pantry_record,
)

HEAD_VEGETABLES = {
    "cabbage", "green cabbage", "red cabbage", "napa cabbage",
    "lettuce", "green leaf lettuce", "iceberg lettuce", "romaine lettuce",
    "butter lettuce", "broccoli", "cauliflower",
}


def final_record(item):
    """Produce the five requested fields without inventing a quantity."""
    record = format_pantry_record(item)
    quantity = record.get("quantity")
    unit = record.get("unit")
    if item.get("quantity_scope") == "full_package":
        quantity, unit = None, None
    name = str(record.get("kb_ingredient_name") or record.get("ingredient_name") or "").strip().casefold()
    if name in HEAD_VEGETABLES:
        if unit in {"count", "counts", "piece", "pieces", "head", "heads"}:
            unit = "head"
        elif quantity is None and item.get("quantity_scope") != "full_package":
            unit = "head"
    return {
        "ingredient_name": record.get("ingredient_name"),
        "kb_ingredient_name": record.get("kb_ingredient_name"),
        "ingredient_id": record.get("ingredient_id"),
        "quantity": quantity,
        "unit": unit,
    }


DEFAULT_STATE = Path(
    "data/users/user_state_375b3cdf-b6d3-450e-80ac-ca0fe00f788a.json"
)


def format_ingredient_availability(ingredients):
    """Map every detected ingredient to a quantity string or 'Unknown'."""
    availability = {}
    for item in ingredients:
        name = item.get("kb_ingredient_name") or item.get("ingredient_name")
        if not name or not str(name).strip():
            continue
        name = str(name).strip()
        quantity, unit = item.get("quantity"), item.get("unit")
        value = "Unknown"
        if quantity is not None and not isinstance(quantity, bool) and unit and str(unit).strip():
            try:
                amount = float(quantity)
                if math.isfinite(amount) and amount > 0:
                    unit_text = str(unit).strip()
                    if unit_text.casefold() == "count":
                        unit_text = "counts"
                    value = f"{amount:g} {unit_text}"
            except (TypeError, ValueError):
                pass
        availability[name] = value
    return availability


def save_image_results_to_state(state_path, ingredients):
    """Update availability; remove any detailed image-detection array."""
    state_path = Path(state_path)
    if not state_path.is_file():
        raise FileNotFoundError(f"User State not found: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("User State must be a JSON object")
    expected_user_id = state_path.stem.removeprefix("user_state_")
    if state.get("user_id") != expected_user_id:
        raise ValueError("User State user_id does not match the target filename")

    # Replace the entire pantry inventory with this image's detections.
    # Unknown quantities are retained as the literal string "Unknown".
    state["ingredient_availability"] = format_ingredient_availability(ingredients)
    state.pop("pantry_image_ingredients", None)

    fd, temp_name = tempfile.mkstemp(
        prefix=".user_state_", suffix=".json", dir=state_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
        os.replace(temp_name, state_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return state_path.resolve()


def main():
    parser = argparse.ArgumentParser(description="Pantry image to ingredient availability JSON")
    parser.add_argument("--image", type=Path, help="Pantry image")
    parser.add_argument("--model", default="gemini-3.8-flash")
    parser.add_argument("--skip-quantity-refinement", action="store_true")
    parser.add_argument("--output", type=Path, default=None, help="Optional separate JSON copy")
    parser.add_argument("--confirmed-json", type=Path, help="Reviewed JSON with user_confirmed=true")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help="Existing User State JSON path")
    args = parser.parse_args()

    if args.confirmed_json:
        if not args.state:
            parser.error("--state is required with --confirmed-json")
        from src.pantry.pantry_state_adapter import save_confirmed_pantry
        payload = json.loads(args.confirmed_json.read_text(encoding="utf-8"))
        items = payload.get("ingredients") if isinstance(payload, dict) else payload
        if not isinstance(items, list) or not items:
            parser.error("Confirmed JSON must have a nonempty ingredients list")
        if not all(
            isinstance(x, dict) and x.get("user_confirmed") is True
            and x.get("ingredient_id") and x.get("kb_ingredient_name")
            and x.get("quantity_detected") == "remaining"
            and isinstance(x.get("quantity"), (int, float))
            and not isinstance(x.get("quantity"), bool)
            and x["quantity"] > 0 and x.get("unit")
            for x in items
        ):
            parser.error("Each item must be KB-matched and explicitly confirmed as remaining stock")
        confirmed = [
            {"name": x["kb_ingredient_name"], "quantity": x["quantity"], "unit": x["unit"]}
            for x in items
        ]
        result = save_confirmed_pantry(args.state, confirmed)
        print("Confirmed pantry saved:", result["structured_pantry_path"])
        return

    if not args.image or not args.image.is_file():
        parser.error(f"Image not found: {args.image}")
    mime, _ = mimetypes.guess_type(args.image.name)
    image_bytes = args.image.read_bytes()
    print("PANTRY IMAGE RECOGNITION")
    print("Model:", args.model)
    print("Analyzing pantry image...")
    detections = detect_image(image_bytes, mime_type=mime or "", model=args.model)
    if not args.skip_quantity_refinement:
        detections = refine_missing_quantities(
            detections, image_bytes, mime_type=mime or "", model=args.model
        )
    matched = match_to_kb(detections, kb=load_kb())
    consolidated = consolidate_ingredients(matched)
    ingredients = [final_record(item) for item in consolidated]
    saved_state = save_image_results_to_state(args.state, ingredients)

    # Print the newly saved availability (the old inventory was replaced).
    saved = json.loads(saved_state.read_text(encoding="utf-8"))
    output = {"ingredient_availability": saved["ingredient_availability"]}
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print("\n" + json.dumps(output, indent=2, ensure_ascii=False))
    print("Saved to User State:", saved_state)
    if args.output is not None:
        print("Separate JSON copy:", args.output.resolve())


if __name__ == "__main__":
    main()
