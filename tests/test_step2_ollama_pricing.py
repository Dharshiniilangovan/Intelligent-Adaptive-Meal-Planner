from unittest.mock import patch
from src.grocery.ollama_price_estimator import calculate_packages_needed, estimate_grocery_price


def test_liquid_tablespoons():
    assert calculate_packages_needed(2, 'tablespoon', 20, 'ml') == (2, True)


def test_solids_use_step1_mass():
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'message': {'content': '{"estimated_product":"Carrot 10g","estimated_package_quantity":10,"estimated_package_unit":"g","estimated_price_sgd":1.50,"currency":"SGD"}'}}
    with patch('src.grocery.ollama_price_estimator.requests.post', return_value=Response()):
        result = estimate_grocery_price('carrot', 2, 'tablespoon')
    assert result is not None
    assert result.estimated_packages_needed == 2
    assert result.estimated_total_cost == 3.0
    assert result.verified is False


def test_reject_non_sgd():
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'message': {'content': '{"estimated_product":"Tofu 300g","estimated_package_quantity":300,"estimated_package_unit":"g","estimated_price_sgd":2,"currency":"USD"}'}}
    with patch('src.grocery.ollama_price_estimator.requests.post', return_value=Response()):
        assert estimate_grocery_price('tofu', 100, 'g') is None
