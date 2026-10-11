"""Run: python -m scripts.run_pantry_image --image data/pantry_image/images.jpg"""
import argparse
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from src.pantry.image_pantry import (
    detect_image, refine_missing_quantities, load_kb, match_to_kb, consolidate_ingredients, normalize_pantry_quantity, estimate_ingredient_mass
)


def main():
    parser = argparse.ArgumentParser(description='Pantry detection, KB lookup and JSON output')
    parser.add_argument('--image', type=Path, help='Image path for detection')
    parser.add_argument('--model', default='gemini-3.8-flash')
    parser.add_argument('--skip-quantity-refinement', action='store_true', help='Skip second image pass for missing quantities')
    parser.add_argument('--output', type=Path, default=Path('data/processed/pantry_image_output.json'))
    parser.add_argument('--confirmed-json', type=Path, help='Previously reviewed JSON with user_confirmed=true for each ingredient')
    parser.add_argument('--state', type=Path, help='Existing User State JSON; used only with --confirmed-json')
    args = parser.parse_args()
    if args.confirmed_json:
        if not args.state:
            parser.error('--state is required with --confirmed-json')
        from src.pantry.pantry_state_adapter import save_confirmed_pantry
        reviewed = json.loads(args.confirmed_json.read_text(encoding='utf-8'))
        items = reviewed.get('ingredients') if isinstance(reviewed, dict) else reviewed
        if not isinstance(items, list) or not items or not all(
            isinstance(x, dict) and x.get('user_confirmed') is True and x.get('kb_present') is True
            and x.get('ingredient_id') and not x.get('review_required', False)
            and x.get('quantity_scope') != 'full_package'
            for x in items
        ):
            parser.error('All ingredients must be KB-matched, reviewed, and user_confirmed=true before saving to User State')
        confirmed = [
            {'name': x['ingredient_name'], 'quantity': x.get('quantity'), 'unit': x.get('unit')}
            for x in items
        ]
        result = save_confirmed_pantry(args.state, confirmed)
        print('Confirmed pantry saved:', result['structured_pantry_path'])
        return
    if args.image is None or not args.image.is_file():
        parser.error(f'Image not found: {args.image}')
    mime, _ = mimetypes.guess_type(args.image.name)
    print('PANTRY IMAGE RECOGNITION')
    print('Model:', args.model)
    print('Analyzing pantry image...')
    image_bytes = args.image.read_bytes()
    detections = detect_image(image_bytes, mime_type=mime or '', model=args.model)
    if not args.skip_quantity_refinement:
        detections = refine_missing_quantities(detections, image_bytes, mime_type=mime or '', model=args.model)
    matched = match_to_kb(detections, kb=load_kb())
    ingredients = consolidate_ingredients(matched)
    for item in ingredients:
        # Original quantity and unit are preserved exactly as consolidated.
        normalized = normalize_pantry_quantity(
            item.get('quantity'), item.get('unit'), item.get('quantity_source', 'unknown')
        )
        item.update(normalized)
        # Keep original and standardized quantity intact. Mass is a separate
        # provisional culinary estimate, never an exact measurement.
        mass = estimate_ingredient_mass(
            item.get('ingredient_name'), item.get('quantity'), item.get('unit')
        ) if item.get('quantity_scope') != 'full_package' else None
        item['estimated_mass_g'] = mass[0] if mass else None
        item['mass_estimate_source'] = (
            'user_provided_provisional_conversion' if mass else None
        )
        item['is_package_capacity'] = item.get('quantity_scope') == 'full_package'
        if mass or item['is_package_capacity']:
            item['review_required'] = True
            reason = ('provisional_mass_conversion' if mass else 'full_package_capacity_not_remaining_stock')
            if reason not in item.setdefault('review_reasons', []):
                item['review_reasons'].append(reason)
        # Visual estimates and unsupported conversions always require review.
        if normalized['is_estimated'] or normalized['normalization_method'] == 'unsupported_unit':
            item['review_required'] = True
            reasons = item.setdefault('review_reasons', [])
            reason = 'estimated_quantity_requires_review' if normalized['is_estimated'] else 'unsupported_unit_for_normalization'
            if reason not in reasons:
                reasons.append(reason)
    payload = {
        'image_path': str(args.image),
        'model_requested': args.model,
        'processed_at': datetime.now(timezone.utc).isoformat(),
        'raw_detection_count': len(detections),
        'unique_ingredient_count': len(ingredients),
        'status': 'unconfirmed_image_detections',
        'ingredients': ingredients,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print('\nDETECTED INGREDIENTS')
    for item in ingredients:
        qty = f"{item['quantity']} {item['unit']}" if item['quantity'] is not None else 'Unknown'
        normalized_text = (f"{item['normalized_quantity']} {item['normalized_unit']}"
                           if item['normalized_quantity'] is not None else 'Unknown')
        mass_text = f" | Estimated mass: {item['estimated_mass_g']} g" if item['estimated_mass_g'] is not None else ''
        capacity_text = (' | ESTIMATED FULL PACKAGE QUANTITY (not remaining)' if item.get('quantity_source') == 'package_estimate' else ' | FULL PACKAGE QUANTITY (not remaining)') if item['is_package_capacity'] else ''
        flag = ' [REVIEW]' if item['review_required'] else ''
        print(f"{item['ingredient_name']} | Quantity: {qty} | Normalized: {normalized_text} | KB present: {item['kb_present']} | KB ID: {item['ingredient_id']} | Match: {item['match_method']}{mass_text}{capacity_text}{flag}")
        if item['quantity'] is None and item['detected_quantities']:
            evidence = ', '.join(f"{x['quantity']} {x['unit']}" for x in item['detected_quantities'])
            print('  Detected quantities (not summed):', evidence)
    print('Saved:', args.output.resolve())
    print('User State unchanged. JSON is not confirmed inventory.')


if __name__ == '__main__':
    main()
