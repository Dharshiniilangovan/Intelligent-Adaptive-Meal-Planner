from src.grocery.ingredient_conversions import estimate_ingredient_mass
from src.grocery.units import to_base, parse_package


def test_estimated_ingredient_weights():
    assert estimate_ingredient_mass('butter lettuce', .5, 'head') == (75.0, 'g')
    assert estimate_ingredient_mass('firm tofu', 1, 'pcs') == (300.0, 'g')
    assert estimate_ingredient_mass('fine sea salt', 1, 'pinch') == (.35, 'g')
    assert estimate_ingredient_mass('carrot', 2, 'tablespoon') == (18.0, 'g')
    assert estimate_ingredient_mass('lime', .5, 'wedge') == (4.0, 'g')
    assert estimate_ingredient_mass('unknown', 1, 'head') is None


def test_exact_units_remain_exact():
    assert to_base(.5, 'tablespoon') == (7.5, 'ml')
    assert to_base(.5, 'head') is None
    assert to_base(1, 'clove') is None
    assert parse_package('https://www.fairprice.com.sg/product/fresh-cucumber-0-66kg-10422143') == (660.0, 'g')
