"""Run from project root: python -m scripts.run_pantry_image --image PATH.
Output: five-field JSON saved under pantry_image_ingredients in User State.
"""
import argparse
import json
import mimetypes
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
    # Full-package capacity is not known remaining stock.
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


def save_image_results_to_state(state_path, ingredients):
    """Save unconfirmed detections without changing ingredient_availability."""
    state_path = Path(state_path)
    if not state_path.is_file():
        raise FileNotFoundError(f"User State not found: {state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("User State must be a JSON object")
    expected_user_id = state_path.stem.removeprefix("user_state_")
    if state.get("user_id") != expected_user_id:
        raise ValueError("User State user_id does not match the target filename")
    state["pantry_image_ingredients"] = ingredients
    # Atomic replace to avoid leaving a partial JSON file on write failure.
    fd, temp_name = tempfile.mkstemp(prefix=".user_state_", suffix=".json", dir=state_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
        os.replace(temp_name, state_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return state_path.resolve()


def main():
    parser = argparse.ArgumentParser(description="Pantry image to five-field JSON")
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
        detections = refine_missing_quantities(detections, image_bytes, mime_type=mime or "", model=args.model)
    matched = match_to_kb(detections, kb=load_kb())
    consolidated = consolidate_ingredients(matched)
    ingredients = [final_record(item) for item in consolidated]
    saved_state = save_image_results_to_state(args.state, ingredients)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({"ingredients": ingredients}, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nDETECTED INGREDIENTS")
    for item in ingredients:
        qty = item["quantity"] if item["quantity"] is not None else "Unknown"
        unit = item["unit"] or "Unknown"
        print(f"{item['ingredient_name']} | KB: {item['kb_ingredient_name']} | ID: {item['ingredient_id']} | Quantity: {qty} | Unit: {unit}")
    print("Saved to User State:", saved_state)
    if args.output is not None:
        print("Separate JSON copy:", args.output.resolve())
    print("Saved under pantry_image_ingredients; ingredient_availability unchanged.")


if __name__ == "__main__":
    main()
