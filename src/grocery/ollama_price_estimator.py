
"""
Local Ollama grocery price estimator for Singapore.

Tavily remains the primary source of real retail prices.
Ollama provides a last-resort, unverified estimate.

The LLM suggests:
- a suitable grocery product
- a typical retail package size
- an estimated price per package

Python calculates:
- packages needed
- total estimated purchase cost

Never treat Ollama estimates as verified retailer prices.
"""

from __future__ import annotations

import json
import math
import os
import re

from dataclasses import asdict, dataclass

import requests

from src.grocery.ingredient_conversions import estimate_ingredient_mass


OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://localhost:11434/api/chat",
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_GROCERY_MODEL",
    "mistral:latest",
)

def _debug_failure(reason, details=None):
    """Print the reason an Ollama estimate was rejected."""
    if os.getenv("OLLAMA_GROCERY_DEBUG", "0") != "1":
        return

    print(f"[OLLAMA PRICE DEBUG] {reason}")

    if details is not None:
        print(f"  Details: {details}")


# ---------------------------------------------------------
# Output contract
# ---------------------------------------------------------

@dataclass
class GroceryPriceEstimate:
    ingredient_name: str
    estimated_product: str
    estimated_package_quantity: float
    estimated_package_unit: str
    estimated_price_sgd: float
    estimated_packages_needed: int
    estimated_total_cost: float

    currency: str = "SGD"
    price_source: str = "ollama_estimate"
    price_confidence: str = "LOW"
    verified: bool = False

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------
# Numeric validation
# ---------------------------------------------------------

def _positive_number(value):
    if isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number) or number <= 0:
        return None

    return number


# ---------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------

def _parse_json(text):
    if not isinstance(text, str):
        return None

    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        pass

    # Some local models wrap JSON in Markdown.
    match = re.search(r"\{[\s\S]*\}", text)

    if not match:
        return None

    try:
        result = json.loads(match.group())
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------

UNIT_ALIASES = {
    "gram": "g",
    "grams": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "piece": "pcs",
    "pieces": "pcs",
    "count": "pcs",
    "unit": "pcs",
    "heads": "head",
    "tbsp": "tablespoon",
    "tbs": "tablespoon",
    "tablespoons": "tablespoon",
    "tsp": "teaspoon",
    "teaspoons": "teaspoon",
    "packs": "pack",
    "packets": "pack",
    "packet": "pack",
    "bunches": "bunch",
}


def normalize_unit(unit):
    text = str(unit or "").strip().lower()

    if text in {"nan", "none", "null"}:
        return ""

    return UNIT_ALIASES.get(text, text)


BASE_UNITS = {
    "g": ("mass", 1.0),
    "kg": ("mass", 1000.0),
    "ml": ("volume", 1.0),
    "l": ("volume", 1000.0),
    "pcs": ("count", 1.0),
    "head": ("head", 1.0),
    "tablespoon": ("volume", 15.0),
    "teaspoon": ("volume", 5.0),
    "clove": ("clove", 1.0),
    "stalk": ("stalk", 1.0),
    "sprig": ("sprig", 1.0),
    "pinch": ("pinch", 1.0),
    "wedge": ("wedge", 1.0),
}


# ---------------------------------------------------------
# Deterministic package calculation
# ---------------------------------------------------------

def calculate_packages_needed(
    required_quantity,
    required_unit,
    package_quantity,
    package_unit,
):
    """
    Return:
        (packages_needed, quantity_calculation_supported)

    If units are compatible, calculate the number of
    packages mathematically.

    If units are incompatible or unknown, assume one
    ordinary retail package as a provisional estimate.

    The package size itself is still model-generated
    and therefore unverified.
    """

    required = _positive_number(required_quantity)

    package = _positive_number(package_quantity)

    if package is None:
        return 1, False

    if required is None:
        return 1, False

    required_unit = normalize_unit(required_unit)
    package_unit = normalize_unit(package_unit)

    required_info = BASE_UNITS.get(required_unit)
    package_info = BASE_UNITS.get(package_unit)

    if (
        required_info is not None
        and package_info is not None
        and required_info[0] == package_info[0]
    ):
        required_base = (
            required * required_info[1]
        )

        package_base = (
            package * package_info[1]
        )

        if package_base <= 0:
            return 1, False

        count = math.ceil(
            required_base / package_base
        )

        return max(1, count), True

    # Examples:
    # 2 tablespoons green onion -> one retail pack
    # 1 tablespoon hoisin sauce -> one bottle
    # 0.5 wedge lime -> one retail package
    #
    # No reliable conversion is available.
    return 1, False


# ---------------------------------------------------------
# Product description package extraction
# ---------------------------------------------------------

DESCRIPTION_PACKAGE = re.compile(
    r"(?<!\w)"
    r"(\d+(?:\.\d+)?)"
    r"\s*"
    r"(kg|g|ml|l)\b",
    flags=re.IGNORECASE,
)


def package_from_description(product_name):
    """
    Extract an explicit mass or volume package size
    from the estimated product description.

    Examples:
        Plain Tofu (500g pack) -> (500, 'g')
        Jasmine Rice 5kg -> (5, 'kg')

    Returns None when no explicit package size exists.
    """

    text = str(product_name or "")

    matches = list(
        DESCRIPTION_PACKAGE.finditer(text)
    )

    if not matches:
        return None

    # Prefer the last explicit size in the description.
    match = matches[-1]

    quantity = _positive_number(
        match.group(1)
    )

    unit = normalize_unit(
        match.group(2)
    )

    if quantity is None:
        return None

    return quantity, unit


# ---------------------------------------------------------
# Package consistency validation
# ---------------------------------------------------------

def reconcile_package(
    product_name,
    package_quantity,
    package_unit,
):
    """
    Reconcile the structured package size with
    an explicit package size in the product name.

    If the product description specifies a physical
    size, prefer that size when the structured fields
    are missing, generic, or contradictory.

    This is still unverified LLM-generated information.
    """

    quantity = _positive_number(
        package_quantity
    )

    unit = normalize_unit(
        package_unit
    )

    description_package = (
        package_from_description(product_name)
    )

    if description_package is not None:
        description_quantity, description_unit = (
            description_package
        )

        if (
            quantity is None
            or unit not in BASE_UNITS
        ):
            return (
                description_quantity,
                description_unit,
            )

        current_info = BASE_UNITS.get(unit)
        description_info = BASE_UNITS.get(
            description_unit
        )

        if (
            current_info is not None
            and description_info is not None
            and current_info[0] == description_info[0]
        ):
            current_base = (
                quantity * current_info[1]
            )

            description_base = (
                description_quantity
                * description_info[1]
            )

            if not math.isclose(
                current_base,
                description_base,
                rel_tol=0.01,
                abs_tol=0.01,
            ):
                return (
                    description_quantity,
                    description_unit,
                )

        elif (
            unit in {"pcs", "pack", "bunch"}
            and description_unit in {"g", "kg", "ml", "l"}
        ):
            return (
                description_quantity,
                description_unit,
            )

    return quantity, unit


# ---------------------------------------------------------
# Main Ollama estimator
# ---------------------------------------------------------

def estimate_grocery_price(
    ingredient_name: str,
    required_quantity=None,
    required_unit=None,
    timeout=90,
):
    """
    Estimate the purchase cost of an ordinary grocery
    product typically sold in Singapore.

    Returns GroceryPriceEstimate or None.

    The model does not browse FairPrice and cannot
    verify current prices.
    """

    ingredient = str(
        ingredient_name or ""
    ).strip()

    if not ingredient:
        return None

    quantity = _positive_number(
        required_quantity
    )

    unit = normalize_unit(
        required_unit
    )

    # Step 1 ingredient-specific mass estimates take precedence
    # over generic volume conversion for solid ingredients.
    coverage_quantity, coverage_unit = quantity, unit
    if quantity is not None:
        mass = estimate_ingredient_mass(ingredient, quantity, unit)
        if mass is not None:
            coverage_quantity, coverage_unit = mass

    # -----------------------------------------------------
    # System prompt
    # -----------------------------------------------------

    system_prompt = """
You estimate grocery purchase costs for home cooking
in Singapore, using NTUC FairPrice as a typical
supermarket reference.

You are a local language model without live internet
or supermarket website access.

You CANNOT verify current FairPrice prices, stock,
product listings, or promotions.

RETAILER AND BRAND RULES:

1. FairPrice is the supermarket, not necessarily
   the product brand.

2. Consider economical products from ANY suitable
   brand that could reasonably be sold at FairPrice.

3. Do not automatically select FairPrice house-brand.

4. Prefer the lowest reasonable TOTAL PURCHASE COST
   for a suitable product and retail package.

5. Do not invent a specific branded product when
   uncertain. Use a generic product description.

6. Do not claim that a product or price was verified
   on the FairPrice website.

INGREDIENT RULES:

7. Preserve the exact requested ingredient identity.

8. Never substitute unrelated products.

9. Never choose cleaning products, cosmetics,
   medicines, supplements, alcohol, or unrelated
   flavoured products.

10. Butter means dairy butter, not peanut butter.

11. Egg means ordinary fresh eggs.

12. Lime means fresh lime, not lime-flavoured items.

13. Green onion may be called spring onion or scallion.

14. Butter lettuce may be called butterhead lettuce.

15. Hoisin sauce must be actual hoisin sauce.

PACKAGE RULES:

16. Suggest a typical economical retail package
    size sold in Singapore supermarkets.

17. The package size must describe ONE retail
    package, not the recipe quantity.

18. Use physical units when known:
    g, kg, ml, l, pcs, head.

19. Use pack or bunch only when the physical
    package weight or count is genuinely unknown.

20. If the product description says 500g,
    return package quantity 500 and unit g.

21. If the product description says 5kg,
    return package quantity 5 and unit kg.

22. Do not convert tablespoons, teaspoons, wedges,
    pinches, or "to taste" into exact grams without
    reliable ingredient-specific evidence.

23. Do not calculate the number of packages.

24. Do not calculate the total purchase cost.

25. Python will calculate packages needed and
    estimated total purchase cost.

PRICE RULES:

26. Estimate a realistic, economical SGD price
    for ONE suggested retail package.

27. Do not invent special promotions or discounts.

28. If a reasonable estimate cannot be made,
    return null for the price.

29. All estimates are unverified and LOW confidence.

OUTPUT FORMAT:

Return ONLY one valid JSON object:

{
  "ingredient_name": "string",
  "estimated_product": "string",
  "estimated_package_quantity": 0,
  "estimated_package_unit": "g",
  "estimated_price_sgd": 0,
  "currency": "SGD"
}

Use numeric values for quantities and prices.

Do not include:
- estimated_packages_needed
- estimated_total_cost
- confidence
- retailer URLs
- explanations
- Markdown
"""

    # -----------------------------------------------------
    # User prompt
    # -----------------------------------------------------

    user_prompt = f"""
Estimate an economical grocery retail package and its
approximate purchase price in Singapore.

Ingredient: {ingredient}

Recipe requirement:
Quantity: {quantity if quantity is not None else "unknown"}
Unit: {unit if unit else "unknown"}

Choose a normal suitable product, from any brand,
that could reasonably be sold at NTUC FairPrice.

The price must represent ONE retail package.

Do not calculate how many packages are required.
Do not calculate the total purchase cost.

Return only the requested JSON object.
"""

    # -----------------------------------------------------
    # Ollama request
    # -----------------------------------------------------

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0,
        },
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=timeout,
        )

        response.raise_for_status()

        body = response.json()

        content = (
            body.get("message", {})
            .get("content", "")
        )

        data = _parse_json(content)

    except (
        requests.RequestException,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:
        _debug_failure(
            "Ollama request or response failed",
            f"{type(exc).__name__}: {exc}",
        )
        return None

    if not data:
        _debug_failure(
            "Ollama returned invalid or empty JSON",
            str(content)[:500],
        )
        return None

    if not data:
        return None

    # -----------------------------------------------------
    # Validate model response
    # -----------------------------------------------------

    product = str(
        data.get("estimated_product")
        or ingredient
    ).strip()

    price = _positive_number(
        data.get("estimated_price_sgd")
    )

    if not product:
        _debug_failure(
            "Missing product name",
            data,
        )
        return None

    if price is None or price > 1000:
        _debug_failure(
            "Invalid estimated price",
            data,
        )
        return None

    if str(data.get("currency", "SGD")).upper() != "SGD":
        _debug_failure(
            "Currency is not SGD",
            data,
        )
        return None

    package_quantity = data.get(
        "estimated_package_quantity"
    )

    package_unit = data.get(
        "estimated_package_unit"
    )

    # -----------------------------------------------------
    # Reconcile package size
    # -----------------------------------------------------

    package_quantity, package_unit = (
        reconcile_package(
            product_name=product,
            package_quantity=package_quantity,
            package_unit=package_unit,
        )
    )

    if (
        package_quantity is None
        or package_unit not in {
            "g", "kg", "ml", "l",
            "pcs", "head", "pack",
            "bunch", "clove", "stalk",
            "sprig",
        }
    ):
        _debug_failure(
            "Invalid retail package",
            {
                "product": product,
                "package_quantity": package_quantity,
                "package_unit": package_unit,
                "model_response": data,
            },
        )
        return None

    # -----------------------------------------------------
    # Calculate packages using Python
    # -----------------------------------------------------

    packages_needed, quantity_supported = (
        calculate_packages_needed(
            required_quantity=coverage_quantity,
            required_unit=coverage_unit,
            package_quantity=package_quantity,
            package_unit=package_unit,
        )
    )

    # Do not trust LLM package counts or totals.
    estimated_total = round(
        price * packages_needed,
        2,
    )

    return GroceryPriceEstimate(
        ingredient_name=ingredient,
        estimated_product=product,
        estimated_package_quantity=package_quantity,
        estimated_package_unit=package_unit,
        estimated_price_sgd=round(price, 2),
        estimated_packages_needed=packages_needed,
        estimated_total_cost=estimated_total,
        currency="SGD",
        price_source="ollama_estimate",
        price_confidence="LOW",
        verified=False,
    )
