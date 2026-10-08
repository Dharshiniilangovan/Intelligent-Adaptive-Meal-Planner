
from dataclasses import dataclass



@dataclass(frozen=True)
class IngredientConversion:
    source: str
    grams_per_tablespoon: float | None = None
    grams_per_sprig: float | None = None
    preparation: str | None = None
    estimated: bool = True



# Approximate culinary measurements.
# These values should be checked against a trusted
# measurement reference before production use.
INGREDIENT_CONVERSIONS = {
    "sugar": IngredientConversion(
        grams_per_tablespoon=12.5,
        source="provisional culinary estimate",
    ),
    "white sugar": IngredientConversion(
        grams_per_tablespoon=12.5,
        source="provisional culinary estimate",
    ),
    "granulated sugar": IngredientConversion(
        grams_per_tablespoon=12.5,
        source="provisional culinary estimate",
    ),
}


def estimate_ingredient_mass(
    ingredient_name: str,
    quantity: float,
    unit: str,
) -> tuple[float, str] | None:
    """
    Estimate ingredient mass for supported
    culinary volume measurements.

    Returns (grams, 'g') or None.
    """

    if quantity is None or not unit:
        return None

    ingredient = ingredient_name.strip().lower()
    unit = unit.strip().lower()

    conversion = INGREDIENT_CONVERSIONS.get(
        ingredient
    )

    if conversion is None:
        return None

    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        return None

    if quantity <= 0:
        return None

    
    if unit in ("tablespoon", "tablespoons", "tbsp"):
        if conversion.grams_per_tablespoon is None:
            return None

        return (
            round(
                quantity * conversion.grams_per_tablespoon,
                2,
            ),
            "g",
        )

    if unit in ("teaspoon", "teaspoons", "tsp"):
        if conversion.grams_per_tablespoon is None:
            return None

        return (
            round(
                quantity
                * conversion.grams_per_tablespoon
                / 3,
                2,
            ),
            "g",
        )

    if unit in ("sprig", "sprigs"):
        if conversion.grams_per_sprig is None:
            return None

        return (
            round(
                quantity * conversion.grams_per_sprig,
                2,
            ),
            "g",
        )


    return None
