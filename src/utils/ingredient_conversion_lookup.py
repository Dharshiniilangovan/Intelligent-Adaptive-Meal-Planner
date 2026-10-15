import csv
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from statistics import median

from src.grocery.ingredient_conversions import estimate_ingredient_mass

DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "processed"
    / "recipe_ingredient_mapping_normalized_with_original_fallback.csv"
)

UNIT_ALIASES = {
    "count": "piece",
    "counts": "piece",
    "pcs": "piece",
    "pieces": "piece",
    "piece": "piece",
    "heads": "head",
    "head": "head",
    "stalks": "stalk",
    "stalk": "stalk",
    "bunches": "bunch",
    "bunch": "bunch",
    "gram": "g",
    "grams": "g",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "tbsp": "tablespoon",
    "tablespoons": "tablespoon",
    "tsp": "teaspoon",
    "teaspoons": "teaspoon",
}

# Exact volume sizes, matching the 15 ml tablespoon used by the
# normalized Ingredient KB.
VOLUME_UNIT_ML = {
    "ml": 1.0,
    "l": 1000.0,
    "tablespoon": 15.0,
    "teaspoon": 5.0,
}


def normalize_conversion_unit(unit):
    unit = str(unit or "").strip().lower()
    return UNIT_ALIASES.get(unit, unit)


@lru_cache(maxsize=4)
def load_ingredient_conversion_factors(
    dataset_path=None,
):
    """
    Build estimated grams-per-unit factors from the
    normalized Ingredient KB.

    Only estimated_piece_weight records are accepted.

    Conflicting factors are excluded rather than averaged
    into an unsupported conversion.
    """
    path = Path(dataset_path or DATASET_PATH)

    candidates = defaultdict(list)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            if (
                str(row.get("conversion_status") or "").strip()
                != "estimated_piece_weight"
            ):
                continue

            name = " ".join(
                str(row.get("ingredient_name") or "")
                .lower()
                .split()
            )

            unit = normalize_conversion_unit(
                row.get("unit")
            )

            if not name or not unit:
                continue

            try:
                original = float(
                    row["quantity_per_serving"]
                )
                weight = float(
                    row["normalized_weight"]
                )
            except (TypeError, ValueError, KeyError):
                continue

            if not (
                math.isfinite(original)
                and math.isfinite(weight)
                and original > 0
                and weight > 0
            ):
                continue

            grams_per_unit = weight / original

            candidates[(name, unit)].append(
                grams_per_unit
            )

    factors = {}

    for key, values in candidates.items():
        center = median(values)

        # Accept only tightly consistent estimates.
        if all(
            abs(value - center) <= max(0.01, center * 0.05)
            for value in values
        ):
            factors[key] = center

    return factors


LEGACY_TABLE_SOURCE = "src/grocery/ingredient_conversions.py"
DATASET_SOURCE = (
    "recipe_ingredient_mapping_normalized_with_original_fallback.csv "
    "(estimated_piece_weight)"
)


def _grams_per_ml(name):
    """
    Ingredient-specific density from the existing per-tablespoon
    estimates in src/grocery/ingredient_conversions.py.

    No generic density is assumed: unknown ingredients return None.
    """
    per_tablespoon = estimate_ingredient_mass(name, 1.0, "tablespoon")

    if per_tablespoon is None:
        return None

    return per_tablespoon[0] / VOLUME_UNIT_ML["tablespoon"]


def _grams_per_unit(name, unit, conversion_factors):
    """
    Return (grams per one unit, provenance) or None.

    Precedence matches normalize_requirement_quantity(),
    inventory_state._mass_in_grams() and the package step, which all
    consult the curated ingredient_conversions.py table before the
    dataset-derived factors, so every path yields the same grams for
    the same ingredient and unit.
    """
    if unit == "g":
        return 1.0, "exact"

    if unit in VOLUME_UNIT_ML:
        density = _grams_per_ml(name)
        if density is None:
            return None
        return (
            density * VOLUME_UNIT_ML[unit],
            f"{LEGACY_TABLE_SOURCE} grams_per_tablespoon / 15 ml",
        )

    estimated = estimate_ingredient_mass(name, 1.0, unit)

    if estimated is not None:
        return estimated[0], f"{LEGACY_TABLE_SOURCE} grams_per_{unit}"

    factor = conversion_factors.get((name, unit))

    if factor is not None:
        return factor, DATASET_SOURCE

    return None


def convert_using_ingredient_factor(
    ingredient_name,
    quantity,
    from_unit,
    to_unit,
    conversion_factors=None,
):
    """
    Convert ingredient-specific count-like units
    through estimated grams-per-unit factors.

    Volume units (ml, l, tablespoon, teaspoon) are bridged to mass
    only when the ingredient has an explicit per-tablespoon estimate.

    Exact mass/volume conversions remain the
    responsibility of the existing conversion service.

    Returns a structured result without fabricating
    unsupported measurements.
    """

    name = " ".join(
        str(ingredient_name or "").lower().split()
    )

    source_unit = normalize_conversion_unit(from_unit)
    target_unit = normalize_conversion_unit(to_unit)

    try:
        quantity = float(quantity)
    except (TypeError, ValueError, OverflowError):
        quantity = float("nan")

    unresolved = {
        "quantity": None,
        "unit": target_unit,
        "status": "unresolved",
    }

    if not math.isfinite(quantity) or quantity < 0:
        return unresolved

    if not source_unit or not target_unit:
        return unresolved

    if source_unit == target_unit:
        return {
            "quantity": quantity,
            "unit": target_unit,
            "status": "exact",
        }

    if conversion_factors is None:
        conversion_factors = (
            load_ingredient_conversion_factors()
        )

    # Volume-to-volume is an exact conversion handled by the
    # existing unit service; never label it via a density.
    if source_unit in VOLUME_UNIT_ML and target_unit in VOLUME_UNIT_ML:
        return unresolved

    source = _grams_per_unit(
        name, source_unit, conversion_factors
    )

    target = _grams_per_unit(
        name, target_unit, conversion_factors
    )

    if source is None or target is None:
        return unresolved

    source_factor, source_provenance = source
    target_factor, target_provenance = target

    if not (
        math.isfinite(source_factor)
        and math.isfinite(target_factor)
        and source_factor > 0
        and target_factor > 0
    ):
        return unresolved

    converted = (
        quantity * source_factor / target_factor
    )

    return {
        "quantity": converted,
        "unit": target_unit,
        "status": "estimated",
        # grams per one unit and where each factor came from.
        "factors": {
            source_unit: {
                "grams_per_unit": source_factor,
                "source": source_provenance,
            },
            target_unit: {
                "grams_per_unit": target_factor,
                "source": target_provenance,
            },
        },
    }
