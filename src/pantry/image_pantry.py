"""Gemini pantry image detection, KB matching and confirmation."""
import csv
import ast
from collections import OrderedDict
import os
import json
import math
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALIASES = ROOT / 'data/processed/INGREDIENT_ALIASES_MAPPED.csv'


def norm(value):
    return re.sub(r'\s+', ' ', str(value).strip().casefold()) if value is not None else ''


def load_ingredient_index(path=ALIASES):
    index = {}
    with open(path, encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            entry = {'ingredient_id': row['ingredient_id'], 'ingredient_name': row['ingredient_name']}
            for name in (row['ingredient_name'], row.get('alias_name', '')):
                if norm(name):
                    index.setdefault(norm(name), entry)
    return index


def _validated_quantity(quantity, unit, source):
    allowed_sources = {'visual_count', 'package_label', 'visual_estimate', 'package_capacity', 'package_estimate'}
    if source not in allowed_sources or quantity is None or not norm(unit):
        return None, None, 'unknown'
    try:
        if isinstance(quantity, bool):
            raise ValueError('Boolean quantity')
        quantity = float(quantity)
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError('Invalid quantity')
    except (ValueError, TypeError):
        return None, None, 'unknown'
    unit = norm(unit)
    if source == 'visual_count':
        if unit not in {'count', 'counts'} or not quantity.is_integer():
            return None, None, 'unknown'
        return int(quantity), 'count', source
    return quantity, unit, source


def _quantity_scope(source, supplied=None):
    """Use explicit model scope, but never treat package capacity as visible stock.

    Unknown/missing scope is resolved conservatively from quantity_source.
    """
    if source in {'package_label', 'package_capacity', 'package_estimate'}:
        return 'full_package'
    if source in {'visual_count', 'visual_estimate'}:
        return 'visible_amount'
    return 'unknown'


def _package_metadata(item, quantity, unit, source):
    scope = _quantity_scope(source, item.get('quantity_scope'))
    return {
        'quantity_scope': scope,
        'package_capacity': quantity if scope == 'full_package' else None,
        'package_capacity_unit': unit if scope == 'full_package' else None,
        'package_capacity_source': source if scope == 'full_package' else None,
        'remaining_quantity_verified': False if scope == 'full_package' else None,
    }


QUANTITY_SCOPE_INSTRUCTIONS = """
For EACH ingredient return ingredient_name, quantity, unit, quantity_source,
and quantity_scope. Distinguish what the quantity MEASURES, not merely whether
food happens to be in a container:
- visible_amount: count or estimated weight of VISIBLE food, including loose
  strawberries, blueberries, chopped fruit or vegetables inside clear trays.
  Use visual_count or visual_estimate. Transparent containers do NOT imply
  full-package capacity.
- full_package: labelled or estimated TOTAL capacity of a bottle, jar, carton,
  sealed packet, or other package, when remaining contents cannot be measured.
  Use package_label or package_estimate. It is NOT verified remaining stock.
- unknown: no defensible quantity; quantity and unit must be null.
If a package's remaining food is directly visible and you estimate that visible
portion, use visible_amount and visual_estimate, not full_package.
If counting is difficult, estimate visible mass in g or kg only with a visual
basis; otherwise return null. Do not invent weights or counts.
Example JSON: {"ingredients": [
 {"ingredient_name":"strawberries","quantity":200,"unit":"g",
  "quantity_source":"visual_estimate","quantity_scope":"visible_amount"},
 {"ingredient_name":"milk","quantity":1000,"unit":"ml",
  "quantity_source":"package_estimate","quantity_scope":"full_package"}
]}
"""


def _generate_with_fallback(client, prompt, image_bytes, mime_type, model):
    """Retry temporary server failures; fall back only to configured model."""
    from google.genai import types, errors
    last_error = None
    for current_model in dict.fromkeys([model, 'gemini-3.5-flash-lite']):
        for attempt in range(2):
            try:
                print(f'[Gemini] Trying model: {current_model}')
                response = client.models.generate_content(
                    model=current_model,
                    contents=[prompt, types.Part.from_bytes(data=image_bytes, mime_type=mime_type)],
                    config=types.GenerateContentConfig(
                        temperature=0, response_mime_type='application/json'))
                print(f'[Gemini] Model successful: {current_model}')
                return response
            except errors.ServerError as exc:
                last_error = exc
                if exc.code != 503:
                    raise
                if attempt == 0:
                    time.sleep(2)
            except errors.ClientError as exc:
                last_error = exc
                if exc.code == 404:
                    break
                raise
    raise RuntimeError('Configured Gemini models unavailable') from last_error


def refine_missing_quantities(detections, image_bytes, mime_type='image/jpeg',
                              model='gemini-3.5-flash-lite', client=None):
    """Second image pass for missing quantities, without changing known values."""
    pending = sorted({norm(item.get('ingredient_name')) for item in detections
                      if isinstance(item, dict) and item.get('quantity') is None
                      and norm(item.get('ingredient_name'))})
    if not pending:
        return detections
    if client is None:
        from dotenv import load_dotenv
        from google import genai
        load_dotenv(ROOT / '.env')
        key = os.getenv('GEMINI_API_KEY')
        if not key:
            print('[Quantity refinement] No API key; retaining unknown quantities.')
            return detections
        client = genai.Client(api_key=key)
    prompt = (
        'Reinspect this exact image ONLY for these already detected ingredients: '
        + json.dumps(pending) + '. Return JSON object with ingredients array. '
        'For each ingredient give ingredient_name, quantity, unit, quantity_source, quantity_scope. '
        'Count clearly visible items; if counting is unreliable, estimate visible weight '
        'in g or kg from visible portion size when defensible. Prefer head for whole cabbage, broccoli and lettuce; use visual_estimate '
        'for estimates, visual_count for counts, package_label for exact printed full package sizes, package_estimate for visually estimated full package sizes of bottles, jars, cartons or packs, '
        'unknown otherwise. Full package size is NOT remaining inventory, even for opened containers. '
        'If amount cannot reasonably be estimated use null for quantity and unit. '
        'Do not add any new ingredient. Return JSON only.'
        + QUANTITY_SCOPE_INSTRUCTIONS
    )
    try:
        response = _generate_with_fallback(client, prompt, image_bytes, mime_type, model)
        payload = json.loads(response.text or '{}')
        suggestions = payload.get('ingredients', [])
        if not isinstance(suggestions, list):
            raise ValueError('Invalid refinement response')
    except Exception as exc:
        print(f'[Quantity refinement] Unavailable ({type(exc).__name__}); retaining unknown values.')
        return detections
    proposed = {}
    for item in suggestions:
        if not isinstance(item, dict):
            continue
        name = norm(item.get('ingredient_name'))
        if name not in pending or name in proposed:
            continue
        quantity, unit, source = _validated_quantity(
            item.get('quantity'), item.get('unit'), item.get('quantity_source'))
        if quantity is not None:
            proposed[name] = (quantity, unit, source, _quantity_scope(source, item.get('quantity_scope')))
    updated = []
    for item in detections:
        row = dict(item)
        name = norm(row.get('ingredient_name'))
        if row.get('quantity') is None and name in proposed:
            row['quantity'], row['unit'], row['quantity_source'], row['quantity_scope'] = proposed[name]
            row.update(_package_metadata(row, row['quantity'], row['unit'], row['quantity_source']))
            row['quantity_refined'] = True
        updated.append(row)
    print(f'[Quantity refinement] Filled {sum(x.get("quantity_refined", False) for x in updated)} entries.')
    return updated


def detect_image(image_bytes, mime_type='image/jpeg', client=None, model='gemini-3.5-flash-lite'):
    """Detect visible ingredients with Gemini; keep existing output contract.

    Inject a google.genai.Client-compatible client for tests.
    """
    if mime_type not in {'image/jpeg', 'image/png', 'image/webp'}:
        raise ValueError('Only JPEG, PNG and WebP images are supported')
    if not image_bytes:
        raise ValueError('Image is empty')
    if len(image_bytes) > 10 * 1024 * 1024:
        raise ValueError('Image exceeds 10 MB')

    from google.genai import types
    if client is None:
        from dotenv import load_dotenv
        from google import genai
        load_dotenv(ROOT / '.env')
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError('GEMINI_API_KEY missing from project-root .env')
        client = genai.Client(api_key=api_key)

    prompt = """Inspect the entire refrigerator systematically, shelf by shelf.
Identify clearly visible foods. Return only a JSON object with an ingredients array.
For each entry include ingredient_name, quantity (positive number or null), unit
(string or null), and quantity_source.

QUANTITY PRIORITY:
1. For visibly measurable remaining contents, report the actual visible quantity
   with visual_count or visual_estimate. Do not pretend estimates are exact.
2. For bottles, jars, cartons, sealed packets and other packaged foods whose
   remaining contents cannot be measured, report the FULL PACKAGE quantity.
   Read exact printed package quantity when legible: source package_label.
   Otherwise cautiously estimate full package capacity from the container size
   only if defensible: source package_estimate.
3. Full package quantity is NEVER verified remaining inventory. Do not assume
   containers are full. Do not invent exact package sizes or invisible foods.
4. For unpackaged foods count distinct items. If counting is not reliable, estimate visible weight in g or kg from the portion size. Use visual_estimate and rounded values, never a generic default. For whole cabbage, broccoli, lettuce and cauliflower prefer unit head. Do not guess a mass without visual support.
5. If neither quantity nor full package size can be estimated reasonably, use
   quantity null, unit null, quantity_source unknown.
6. Allowed sources: visual_count, visual_estimate, package_label,
   package_estimate, unknown. Use units count, g, kg, ml, l, head, bunch etc.
7. Do not repeat the same physical item.

Example: {"ingredients":[
 {"ingredient_name":"milk","quantity":1000,"unit":"ml","quantity_source":"package_label"},
 {"ingredient_name":"carrot","quantity":3,"unit":"count","quantity_source":"visual_count"}
]}
"""

    prompt += '\n' + QUANTITY_SCOPE_INSTRUCTIONS
    response = _generate_with_fallback(client, prompt, image_bytes, mime_type, model)
    content = response.text
    if not content or not content.strip():
        raise ValueError('Empty Gemini vision response; check model access and response metadata')
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError('Gemini response was not valid JSON') from exc
    if not isinstance(data, dict) or not isinstance(data.get('ingredients'), list):
        raise ValueError('Invalid Gemini response: expected ingredients list')

    detected = []
    for item in data['ingredients']:
        if not isinstance(item, dict):
            raise ValueError('Invalid Gemini ingredient entry')
        name = norm(item.get('ingredient_name'))
        if not name:
            continue
        quantity, unit, source = _validated_quantity(
            item.get('quantity'), item.get('unit'), item.get('quantity_source', 'unknown')
        )
        detected.append({'ingredient_name': name, 'quantity': quantity,
                         'unit': unit, 'quantity_source': source,
                         **_package_metadata(item, quantity, unit, source)})
    return detected


def match_ingredients(names, index=None):
    index = index if index is not None else load_ingredient_index()
    output = []
    for ingredient in names:
        if isinstance(ingredient, str):
            name, quantity, unit, source = norm(ingredient), None, None, 'unknown'
        elif isinstance(ingredient, dict):
            name = norm(ingredient.get('ingredient_name', ingredient.get('detected_name', '')))
            quantity, unit, source = _validated_quantity(
                ingredient.get('quantity'), ingredient.get('unit'), ingredient.get('quantity_source', 'unknown')
            )
        else:
            raise ValueError('Ingredient must be a string or dictionary')
        if not name:
            continue
        match = index.get(name)
        output.append({'detected_name': name,
                       'ingredient_id': match['ingredient_id'] if match else None,
                       'name': match['ingredient_name'] if match else name,
                       'quantity': quantity, 'unit': unit, 'quantity_source': source,
                       'matched': bool(match)})
    return output


def confirm_pantry(reviewed, index=None):
    """Confirm reviewed items; preserve unknown quantities as None."""
    index = index if index is not None else load_ingredient_index()
    items = []
    for item in reviewed:
        name = norm(item['name'])
        match = index.get(name)
        if not match:
            raise ValueError(f'Ingredient not in KB: {name}. Choose a KB ingredient before confirming.')
        quantity = item.get('quantity')
        unit = norm(item.get('unit')) or None
        if quantity in ('', None):
            quantity, unit = None, None
        else:
            if isinstance(quantity, bool):
                raise ValueError(f'Invalid quantity for {name}')
            try:
                quantity = float(quantity)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'Invalid quantity for {name}') from exc
            if not math.isfinite(quantity) or quantity <= 0 or not unit:
                raise ValueError(f'Invalid quantity or unit for {name}')
        items.append({'ingredient_id': match['ingredient_id'],
                      'name': match['ingredient_name'], 'quantity': quantity, 'unit': unit})
    return items


# KB matching (merged from pantry_kb_matcher.py)
KB_PATH = ALIASES
def aliases_from_cell(cell):
    value = str(cell or '').strip()
    if value.startswith('[') and value.endswith(']'):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, (list, tuple)):
                return [str(x) for x in parsed if str(x).strip()]
        except (SyntaxError, ValueError):
            pass
    return [value] if value else []


def load_kb(path=KB_PATH):
    """Return exact-name and alias indexes; both formats of alias CSV supported."""
    exact, aliases = {}, {}
    with open(path, encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            entry = {'ingredient_id': row['ingredient_id'], 'ingredient_name': row['ingredient_name']}
            key = norm(entry['ingredient_name'])
            if key:
                exact.setdefault(key, entry)
            for alias in aliases_from_cell(row.get('alias_name')):
                key = norm(alias)
                if key:
                    aliases.setdefault(key, entry)
    return exact, aliases


# Semantic mappings are applied ONLY if their targets exist in the supplied KB.
# Review suggested mappings before treating them as confirmed pantry inventory.
SUGGESTIONS = {
    'fresh milk': 'milk',
    'salmon fillet': 'salmon',
    'yellow noodles': 'noodles',
    'red apple': 'apple',
    'soya bean drink': 'soy milk',
}


def match_to_kb(detections, kb=None):
    exact, aliases = kb if kb is not None else load_kb()
    results = []
    for item in detections:
        raw = item if isinstance(item, str) else item.get('ingredient_name', item.get('detected_name', ''))
        name = norm(raw)
        if not name:
            continue
        match = exact.get(name)
        method = 'exact' if match else None
        if not match:
            match = aliases.get(name)
            method = 'alias' if match else None
        if not match and name in SUGGESTIONS:
            match = exact.get(norm(SUGGESTIONS[name]))
            method = 'suggested' if match else None
        data = item if isinstance(item, dict) else {}
        results.append({
            'detected_name': name,
            'ingredient_id': match['ingredient_id'] if match else None,
            'name': match['ingredient_name'] if match else name,
            'quantity': data.get('quantity'),
            'unit': data.get('unit'),
            'quantity_source': data.get('quantity_source', 'unknown'),
            'matched': bool(match),
            'match_method': method,
            'quantity_scope': _quantity_scope(data.get('quantity_source', 'unknown'), data.get('quantity_scope')),
            **_package_metadata(data, data.get('quantity'), data.get('unit'), data.get('quantity_source', 'unknown')),
        })
    return results


# Consolidation (merged from pantry_consolidation.py)
def _valid_observation(item):
    """Keep a positive measured quantity and its unit, or an unknown pair."""
    q, unit = item.get('quantity'), item.get('unit')
    if q is None or not isinstance(unit, str) or not unit.strip() or isinstance(q, bool):
        return None, None
    try:
        number = float(q)
    except (TypeError, ValueError):
        return None, None
    if not math.isfinite(number) or number <= 0:
        return None, None
    if unit.strip().casefold() in {'count', 'counts'}:
        if not number.is_integer():
            return None, None
        return int(number), 'count'
    return int(number) if number.is_integer() else number, unit.strip().casefold()


def consolidate_ingredients(matched):
    """Produce one record per ingredient, retaining all detected quantity evidence.

    With duplicate observations, the aggregate total stays null unless a human
    establishes that the observations refer to distinct, non-overlapping items.
    """
    groups = OrderedDict()
    for item in matched:
        key = ('kb', str(item['ingredient_id'])) if item.get('ingredient_id') else (
            'unmatched', str(item.get('detected_name', '')).strip().casefold()
        )
        groups.setdefault(key, []).append(item)

    result = []
    for observations in groups.values():
        first = observations[0]
        duplicate = len(observations) > 1
        matched_kb = bool(first.get('ingredient_id'))
        evidence = []
        for observation in observations:
            q, unit = _valid_observation(observation)
            evidence.append({
                'detected_name': observation.get('detected_name'),
                'quantity': q,
                'unit': unit,
                'quantity_source': observation.get('quantity_source', 'unknown') if q is not None else 'unknown',
                'quantity_scope': _quantity_scope(observation.get('quantity_source', 'unknown') if q is not None else 'unknown', observation.get('quantity_scope')),
                **_package_metadata(observation, q, unit, observation.get('quantity_source', 'unknown') if q is not None else 'unknown'),
            })

        if not duplicate:
            quantity, unit = evidence[0]['quantity'], evidence[0]['unit']
            source = evidence[0]['quantity_source']
        else:
            quantity, unit, source = None, None, 'unknown'

        scope = _quantity_scope(source)
        reasons = []
        if scope == 'full_package':
            reasons.append('full_package_capacity_not_remaining_stock')
        if any(x.get('match_method') == 'suggested' for x in observations):
            reasons.append('semantic_kb_match_needs_review')
        if not matched_kb:
            reasons.append('ingredient_not_in_kb')
        if duplicate:
            reasons.append('multiple_observations_may_overlap')
        if quantity is None:
            reasons.append('total_quantity_unknown')

        result.append({
            'ingredient_id': first.get('ingredient_id'),
            'ingredient_name': first.get('name'),
            'kb_present': matched_kb,
            'match_method': first.get('match_method'),
            'detected_names': list(dict.fromkeys(x.get('detected_name') for x in observations)),
            'quantity': quantity,
            'unit': unit,
            'quantity_source': source,
            'quantity_scope': scope,
            **_package_metadata(first, quantity, unit, source),
            'detected_quantities': [
                {'quantity': x['quantity'], 'unit': x['unit'], 'quantity_source': x['quantity_source']}
                for x in evidence if x['quantity'] is not None
            ],
            'matched': matched_kb,
            'observations_count': len(observations),
            'observations': evidence,
            'review_required': bool(reasons),
            'review_reasons': reasons,
            'user_confirmed': False,
        })
    return result


# Unit standardization is intentionally separate from visual estimation.
# No per-piece weight is assumed without a verified conversion table.
def normalize_pantry_quantity(quantity, unit, quantity_source='unknown'):
    """Return standardized quantity metadata without inventing mass or volume.

    Supported conversions: kg->g, L->ml, and unit spelling aliases.
    count/head/bunch stay as counts/heads/bunches; they are NOT converted to g.
    """
    if quantity is None or unit is None:
        return {'normalized_quantity': None, 'normalized_unit': None,
                'normalization_method': 'unknown', 'is_estimated': False}
    if isinstance(quantity, bool):
        raise ValueError('Boolean quantity is invalid')
    try:
        amount = float(quantity)
    except (ValueError, TypeError) as exc:
        raise ValueError('Invalid quantity') from exc
    if not math.isfinite(amount) or amount <= 0:
        raise ValueError('Quantity must be positive and finite')
    u = norm(unit).replace('.', '')
    aliases = {
        'gram': 'g', 'grams': 'g', 'g': 'g',
        'kilogram': 'kg', 'kilograms': 'kg', 'kgs': 'kg', 'kg': 'kg',
        'milliliter': 'ml', 'milliliters': 'ml',
        'millilitre': 'ml', 'millilitres': 'ml', 'ml': 'ml',
        'liter': 'l', 'liters': 'l', 'litre': 'l', 'litres': 'l', 'l': 'l',
        'count': 'count', 'counts': 'count', 'piece': 'count',
        'pieces': 'count', 'pcs': 'count', 'pc': 'count',
        'head': 'head', 'heads': 'head',
        'bunch': 'bunch', 'bunches': 'bunch',
        'bottle': 'bottle', 'bottles': 'bottle',
        'pack': 'pack', 'packs': 'pack',
    }
    standard = aliases.get(u)
    if standard is None:
        return {'normalized_quantity': None, 'normalized_unit': None,
                'normalization_method': 'unsupported_unit',
                'is_estimated': quantity_source in {'visual_estimate', 'package_estimate'}}
    factor = {'kg': (1000, 'g'), 'l': (1000, 'ml')}
    multiplier, target = factor.get(standard, (1, standard))
    value = amount * multiplier
    if value.is_integer():
        value = int(value)
    return {
        'normalized_quantity': value,
        'normalized_unit': target,
        'normalization_method': 'unit_conversion' if multiplier != 1 else 'unit_standardization',
        'is_estimated': quantity_source in {'visual_estimate', 'package_estimate'},
    }


# User-provided provisional culinary conversions. Not measured package weights.
# Keep these separate from Gemini's original visual quantity.
INGREDIENT_MASS_FACTORS = {
    'sugar': {'tablespoon': 12.5}, 'white sugar': {'tablespoon': 12.5},
    'granulated sugar': {'tablespoon': 12.5},
    'white granulated sugar': {'tablespoon': 12.5},
    'butter lettuce': {'head': 150}, 'butterhead lettuce': {'head': 150},
    'lettuce': {'head': 300}, 'garlic': {'clove': 3},
    'lime': {'count': 65, 'wedge': 8}, 'fresh lime': {'count': 65, 'wedge': 8},
    'lemon': {'count': 100, 'wedge': 12},
    'firm tofu': {'count': 300}, 'tofu': {'count': 300},
    'carrot': {'tablespoon': 9, 'count': 70},
    'yellow onion': {'tablespoon': 10, 'count': 150},
    'onion': {'tablespoon': 10, 'count': 150},
    'green onion': {'tablespoon': 6, 'bunch': 100},
    'spring onion': {'tablespoon': 6, 'bunch': 100},
    'zucchini': {'tablespoon': 9, 'count': 200},
    'mint': {'tablespoon': 1.5, 'sprig': 1},
    'salt': {'tablespoon': 18, 'pinch': 0.35},
    'kosher salt': {'tablespoon': 15, 'pinch': 0.3},
    'fine sea salt': {'tablespoon': 18, 'pinch': 0.35},
    'black pepper': {'tablespoon': 7, 'pinch': 0.2},
    'garlic powder': {'tablespoon': 9, 'pinch': 0.3},
    'hoisin sauce': {'tablespoon': 17},
    'soy sauce': {'tablespoon': 16},
    'mustard seed': {'tablespoon': 9, 'pinch': 0.3},
    'mustard seeds': {'tablespoon': 9, 'pinch': 0.3},
}


def estimate_ingredient_mass(ingredient_name, quantity, unit):
    """Estimate grams using only the user's ingredient-specific conversion table.

    Returns (grams, 'g') or None. Never estimates remaining package contents.
    """
    if not ingredient_name or quantity is None or not unit or isinstance(quantity, bool):
        return None
    try:
        q = float(quantity)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(q) or q <= 0:
        return None
    factors = INGREDIENT_MASS_FACTORS.get(norm(ingredient_name))
    if not factors:
        return None
    units = {
        'piece': 'count', 'pieces': 'count', 'pc': 'count', 'pcs': 'count',
        'each': 'count', 'unit': 'count', 'counts': 'count',
        'heads': 'head', 'bunches': 'bunch', 'cloves': 'clove',
        'wedges': 'wedge', 'pinches': 'pinch', 'sprigs': 'sprig',
        'tablespoons': 'tablespoon', 'tbsp': 'tablespoon',
        'teaspoon': 'teaspoon', 'teaspoons': 'teaspoon', 'tsp': 'teaspoon',
    }
    u = norm(unit)
    u = units.get(u, u)
    scale = 1 / 3 if u == 'teaspoon' else 1
    if u == 'teaspoon':
        u = 'tablespoon'
    factor = factors.get(u)
    if factor is None:
        return None
    return round(q * factor * scale, 4), 'g'


def format_pantry_record(item):
    """Convert a consolidated detection to the requested seven-field JSON schema.

    'actual' means visually counted or label-read, not independently verified.
    'whole' denotes package capacity, never verified remaining contents.
    """
    source = item.get('quantity_source', 'unknown')
    quantity = item.get('quantity')
    unit = item.get('unit')
    if quantity is None:
        unit = None
        information = 'unknown'
        detected_scope = 'unknown'
    else:
        information = 'actual' if source in {'visual_count', 'package_label', 'package_capacity'} else 'estimated'
        detected_scope = 'whole' if item.get('quantity_scope') == 'full_package' else 'remaining'
    return {
        'ingredient_name': ', '.join(item.get('detected_names') or [item.get('ingredient_name', '')]),
        'kb_ingredient_name': item.get('ingredient_name') if item.get('kb_present') else None,
        'ingredient_id': item.get('ingredient_id') if item.get('kb_present') else None,
        'quantity': quantity,
        'unit': unit,
        'information': information,
        'quantity_detected': detected_scope,
    }
