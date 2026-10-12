import json
from unittest.mock import patch
from src.grocery.ingredient_conversions import estimate_ingredient_mass, _lookup_missing_conversion
from src.state.inventory_state import consume_inventory


def test_unknown_ingredient_uses_existing_ollama_settings(monkeypatch):
    monkeypatch.setenv('OLLAMA_CONVERSION_FALLBACK', '1')
    monkeypatch.setenv('OLLAMA_API_KEY', 'test-key')
    _lookup_missing_conversion.cache_clear()
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'message': {'content': json.dumps({'grams_per_unit': 15, 'confidence': 'high'})}}
    with patch('requests.post', return_value=Response()) as request:
        result = consume_inventory({'sour cream': {'quantity': 250, 'unit': 'g'}},
            [{'ingredient_name': 'sour cream', 'quantity': 1, 'unit': 'tablespoon'}])
    assert result['sour cream']['quantity'] == 235
    assert request.call_count == 1
    _lookup_missing_conversion.cache_clear()


def test_unknown_conversion_stays_unresolved_by_default(monkeypatch):
    monkeypatch.delenv('OLLAMA_CONVERSION_FALLBACK', raising=False)
    _lookup_missing_conversion.cache_clear()
    assert estimate_ingredient_mass('unknown fictional food', 1, 'count') is None
