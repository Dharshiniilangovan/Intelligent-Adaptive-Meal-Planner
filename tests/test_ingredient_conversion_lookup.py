
import pytest

from src.utils.ingredient_conversion_lookup import (
    load_ingredient_conversion_factors,
    convert_using_ingredient_factor,
)


@pytest.fixture(scope="module")
def factors():
    return load_ingredient_conversion_factors()


@pytest.mark.parametrize(
    "name,quantity,source,target,expected",
    [
        ("broccoli", 0.5, "head", "g", 150.0),
        ("egg", 2, "count", "g", 100.0),
        ("green onion", 1, "stalk", "g", 15.0),
        ("broccoli", 150, "g", "head", 0.5),
    ],
)
def test_dataset_piece_weight_conversions(
    factors,
    name,
    quantity,
    source,
    target,
    expected,
):
    result = convert_using_ingredient_factor(
        name,
        quantity,
        source,
        target,
        factors,
    )

    assert result["quantity"] == pytest.approx(expected)
    assert result["status"] == "estimated"


def test_unknown_volume_to_mass_stays_unresolved(factors):
    result = convert_using_ingredient_factor(
        "broccoli floret",
        125,
        "ml",
        "g",
        factors,
    )

    assert result["quantity"] is None
    assert result["status"] == "unresolved"


def test_same_unit_is_exact(factors):
    result = convert_using_ingredient_factor(
        "broccoli",
        300,
        "g",
        "g",
        factors,
    )

    assert result["quantity"] == 300
    assert result["status"] == "exact"
