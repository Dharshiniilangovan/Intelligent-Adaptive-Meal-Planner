"""Additive adapter: never changes existing user_state.py or pantry_service.py."""
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.pantry_', suffix='.json', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_confirmed_pantry(user_state_path, items, pantry_path=None):
    """Preserve old schema: only measured items go into legacy availability.

    Unknown amounts are retained in a separate structured JSON file, not fabricated.
    """
    user_state_path = Path(user_state_path)
    state = json.loads(user_state_path.read_text(encoding='utf-8'))
    user_id = state.get('user_id')
    if not user_id:
        raise ValueError('User State requires user_id')
    if not isinstance(items, list):
        raise ValueError('items must be a list')
    availability = dict(state.get('ingredient_availability') or {})
    sidecar = ROOT / 'data' / 'pantry_images' / f'confirmed_{user_id}.json'
    if pantry_path is None:
        pantry_path = ROOT / 'data' / 'sample' / f'pantry_{user_id}.json'
    pantry_path = Path(pantry_path)
    pantry = {'user_id': user_id, 'items': []}
    if pantry_path.exists():
        pantry = json.loads(pantry_path.read_text(encoding='utf-8'))
        pantry.setdefault('items', [])
    by_name = {str(x['name']).casefold(): x for x in pantry['items']}
    for item in items:
        name = item['name']
        amount = item['quantity']
        unit = item['unit']
        if amount is None:
            # Keep unknown quantity out of legacy code that calls float() or split().
            continue
        availability[name] = f'{amount:g} {unit}'
        by_name[name.casefold()] = {'name': name, 'quantity': amount, 'unit': unit}
    state['ingredient_availability'] = availability
    pantry['items'] = list(by_name.values())
    _atomic_json(sidecar, {'user_id': user_id, 'items': items})
    _atomic_json(pantry_path, pantry)
    _atomic_json(user_state_path, state)
    return {'state': state, 'structured_pantry_path': str(sidecar), 'pantry_path': str(pantry_path)}
