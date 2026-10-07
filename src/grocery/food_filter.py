"""src/grocery/food_filter.py

Clean recipe ingredient text, generate safe grocery search queries,
and determine whether a retail product is a reasonable match.

Design goals:
- preserve multi-word ingredient identity
- never reduce "garlic powder" to just "powder"
- allow useful fallbacks such as "cherry tomatoes" -> "tomatoes"
- reject obvious derived/non-ingredient products
- use title + URL + Tavily evidence when available
- avoid maintaining giant ingredient-specific blacklists
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import unquote, urlparse


_WORD = re.compile(r"[a-z]+")


# ---------------------------------------------------------------------
# Recipe/preparation words
#
# These are grammar/preparation/measurement words, NOT food names.
# ---------------------------------------------------------------------

DESCRIPTORS = {
    "fresh",
    "large",
    "small",
    "medium",
    "big",

    "boneless",
    "skinless",

    "chopped",
    "diced",
    "minced",
    "sliced",
    "grated",
    "shredded",
    "ground",
    "crushed",
    "peeled",
    "deveined",
    "trimmed",
    "halved",
    "quartered",
    "cubed",
    "julienned",

    "finely",
    "thinly",
    "roughly",
    "coarsely",
    "lightly",
    "freshly",

    "organic",
    "raw",
    "cooked",
    "uncooked",
    "ripe",
    "lean",

    "softened",
    "melted",
    "beaten",
    "packed",
    "divided",
    "optional",

    "room",
    "temperature",

    "cold",
    "warm",
    "hot",

    "rinsed",
    "drained",
    "washed",

    "about",
    "plus",
    "more",
    "into",
    "cut",

    "of",
    "and",
    "or",
    "for",
    "a",
    "an",
    "the",
    "to",
}


# Quantity/container words that describe how much of an ingredient is
# required rather than the identity of the ingredient itself.
PORTION_WORDS = {
    "piece",
    "pieces",

    "clove",
    "cloves",

    "sprig",
    "sprigs",

    "leaf",
    "leaves",

    "stalk",
    "stalks",

    "bunch",
    "bunches",

    "head",
    "heads",

    "slice",
    "slices",

    "pinch",
    "pinches",

    "dash",
    "dashes",

    "handful",
    "handfuls",
}


MEASUREMENT_WORDS = {
    "cup",
    "cups",

    "tbsp",
    "tablespoon",
    "tablespoons",

    "tsp",
    "teaspoon",
    "teaspoons",

    "mg",
    "g",
    "gm",
    "gms",
    "gram",
    "grams",

    "kg",
    "kgs",
    "kilogram",
    "kilograms",

    "ml",
    "cl",

    "l",
    "ltr",
    "litre",
    "litres",
    "liter",
    "liters",

    "oz",
    "ounce",
    "ounces",

    "lb",
    "lbs",
    "pound",
    "pounds",

    "pc",
    "pcs",

    "unit",
    "units",
}


# ---------------------------------------------------------------------
# Generic retail-product forms
#
# This is intentionally NOT a list of individual foods/brands.
#
# These words indicate that the requested ingredient is being used as
# an ingredient/flavour/material inside a different retail product.
# ---------------------------------------------------------------------

DERIVED_PRODUCT_FORMS = {
    # Prepared foods / flavour products
    "ketchup",
    "cracker",
    "crackers",
    "biscuit",
    "biscuits",
    "cookie",
    "cookies",
    "chocolate",
    "candy",
    "sweet",
    "sweets",
    "surprise",
    "confectionery",
    "surprise",
    "kimchi",
    "nugget",
    "nuggets",
    "sausage",
    "sausages",
    "cake",
    "cakes",
    "dessert",
    "pudding",
    "snack",
    "snacks",
    "stock",
    "cube",
    "cubes",
    "paste",
    "spread",
    "dressing",
    "marinade",

    # Generic animal/derived retail forms
    "food",
    "pouch",
    "kibble",
    "litter",

    # Non-grocery objects
    "cooker",
    "maker",
    "machine",
    "press",
    "container",
    "appliance",
    "phone",
    "iphone",
    "tablet",
    "laptop",
    "charger",
    "toy",

    # Household/personal care
    "detergent",
    "cleaner",
    "soap",
    "shampoo",
    "conditioner",
    "lotion",
    "bath",
    "soak",
    "scent",
    "scented",

    # Nutrition/formula
    "formula",
    "supplement",
    "capsule",
    "capsules",
    "vitamin",
    "vitamins",

    "deodorizer",
    "deodoriser",
    "airfreshener",
    "freshener",
    "refresher",
    "spray",
    }


# Context terms that strongly indicate that the title refers to pet food
# rather than the human grocery ingredient itself.
PET_CONTEXT = {
    "dog",
    "dogs",
    "cat",
    "cats",
    "puppy",
    "puppies",
    "kitten",
    "kittens",
    "pet",
    "pets",
}


# ---------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------

def _stem(word: str) -> str:
    """
    Small plural normalizer.

    This is deliberately conservative.
    """

    word = str(word).lower().strip()

    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"

    if len(word) > 4 and word.endswith("oes"):
        return word[:-2]

    if len(word) > 4 and word.endswith("ves"):
        # leaves -> leave
        return word[:-1]

    if (
        len(word) > 3
        and word.endswith("s")
        and not word.endswith("ss")
    ):
        return word[:-1]

    return word


def words(text: str) -> list[str]:
    """Return normalized lowercase words."""

    return [
        _stem(word)
        for word in _WORD.findall(
            str(text or "").lower()
        )
    ]


def _strip_recipe_notes(text: str) -> str:
    """Remove quantities/preparation notes from recipe ingredient text."""

    text = str(text or "").lower()

    # Parenthesized notes:
    # garlic (about 3 cloves)
    text = re.sub(
        r"\([^)]*\)",
        " ",
        text,
    )

    # Preparation after comma:
    # chicken breast, diced
    text = text.split(",", 1)[0]

    # Fractions such as 1/2.
    text = re.sub(
        r"\b\d+\s*/\s*\d+\b",
        " ",
        text,
    )

    # Numbers.
    text = re.sub(
        r"\b\d+(?:\.\d+)?\b",
        " ",
        text,
    )

    return text


def clean_ingredient(
    text: str,
) -> list[str]:
    """
    Return the meaningful identity tokens of a recipe ingredient.

    Examples:

        "3 garlic cloves, minced"
            -> ["garlic"]

        "2 boneless skinless chicken breasts, diced"
            -> ["chicken", "breast"]

        "1 cup fresh cherry tomatoes"
            -> ["cherry", "tomato"]

        "garlic powder"
            -> ["garlic", "powder"]
    """

    text = _strip_recipe_notes(
        text
    )

    raw = _WORD.findall(
        text
    )

    cleaned = []

    for raw_word in raw:

        word = _stem(
            raw_word
        )

        if word in DESCRIPTORS:
            continue

        if word in PORTION_WORDS:
            continue

        if word in MEASUREMENT_WORDS:
            continue

        if word:
            cleaned.append(
                word
            )

    return cleaned


def canonical_phrase(
    text: str,
) -> str:

    return " ".join(
        clean_ingredient(
            text
        )
    )


# ---------------------------------------------------------------------
# Product evidence
# ---------------------------------------------------------------------

def _url_tokens(
    url: str,
) -> list[str]:

    try:
        path = unquote(
            urlparse(
                str(url or "")
            ).path
        )

    except Exception:
        path = str(
            url or ""
        )

    path = (
        path
        .replace("-", " ")
        .replace("_", " ")
        .replace("/", " ")
    )

    return words(
        path
    )


def _evidence_tokens(
    title: str,
    url: str = "",
    content: str = "",
    size_text: str = "",
) -> list[str]:

    evidence = []

    evidence.extend(
        words(title)
    )

    evidence.extend(
        _url_tokens(url)
    )

    evidence.extend(
        words(content)
    )

    evidence.extend(
        words(size_text)
    )

    return evidence


# ---------------------------------------------------------------------
# Product-form validation
# ---------------------------------------------------------------------

def _derived_product_reason(
    ingredient_tokens: list[str],
    title_tokens: list[str],
    url_tokens: list[str],
) -> str | None:
    """
    Detect when the requested ingredient occurs inside a different
    retail product.

    IMPORTANT:
    Negative product-form checks use ONLY the product title and URL.
    Tavily/page text may contain recommendations and unrelated products.
    """

    ingredient_set = set(ingredient_tokens)

    identity_tokens = set(
        title_tokens + url_tokens
    )

    pet_context = (
        identity_tokens
        & PET_CONTEXT
    )

    if pet_context:
        return (
            "non-food/pet product: "
            + sorted(pet_context)[0]
        )

    forms = (
        identity_tokens
        & DERIVED_PRODUCT_FORMS
    ) - ingredient_set

    if forms:
        return (
            "processed product: "
            + sorted(forms)[0]
        )

    return None

# ---------------------------------------------------------------------
# Match scoring
# ---------------------------------------------------------------------

def _coverage(
    ingredient_tokens: list[str],
    evidence_tokens: list[str],
) -> float:

    if not ingredient_tokens:
        return 0.0

    ingredient_set = set(
        ingredient_tokens
    )

    evidence_set = set(
        evidence_tokens
    )

    return (
        len(
            ingredient_set
            & evidence_set
        )
        / len(
            ingredient_set
        )
    )


def _phrase_similarity(
    ingredient: str,
    title: str,
) -> float:

    ingredient_phrase = (
        canonical_phrase(
            ingredient
        )
    )

    title_phrase = " ".join(
        words(title)
    )

    if (
        not ingredient_phrase
        or not title_phrase
    ):
        return 0.0

    return SequenceMatcher(
        None,
        ingredient_phrase,
        title_phrase,
    ).ratio()


def check_match(
    ingredient: str,
    title: str,
    url: str = "",
    content: str = "",
    size_text: str = "",
) -> tuple[bool, str]:
    """
    Determine whether a retail product is suitable for the ingredient.

    Matching uses:
        - requested ingredient identity
        - product title
        - FairPrice URL
        - Tavily content
        - size/page evidence

    Returns:
        (True, "exact")
        (True, "strong")
        (True, "approximate")

    or:
        (False, reason)
    """

    core = clean_ingredient(
        ingredient
    )

    if not core:
        return (
            False,
            "ingredient has no usable identity",
        )

    core_set = set(
        core
    )

    title_tokens = words(title)

    url_tokens = _url_tokens(url)

    primary_tokens = (
        title_tokens
        + url_tokens
    )

    supporting_tokens = (
        words(content)
        + words(size_text)
    )

    evidence_tokens = (
        primary_tokens
        + supporting_tokens
    )

    title_set = set(title_tokens)
    primary_set = set(primary_tokens)
    evidence_set = set(evidence_tokens)

    # ---------------------------------------------------------
    # Wrong retail-product form
    # ---------------------------------------------------------

    bad_form = _derived_product_reason(
        core,
        title_tokens,
        url_tokens,
    )

    if bad_form:
        return (
            False,
            bad_form,
        )

    # ---------------------------------------------------------
    # EXACT
    # Requested identity explicitly appears in product title.
    # ---------------------------------------------------------

    if core_set <= title_set:
        return True, "exact"


    # ---------------------------------------------------------
    # STRONG
    # Requested identity appears across title + actual
    # FairPrice product URL.
    #
    # Page/snippet content alone cannot establish a strong match.
    # ---------------------------------------------------------

    if core_set <= primary_set:
        return True, "strong"

    # ---------------------------------------------------------
    # Single-word ingredients
    # ---------------------------------------------------------

    if len(core) == 1:

        token = core[0]

        if token in title_set:
            return (
                True,
                "exact",
            )

        if token in evidence_set:
            return (
                True,
                "strong",
            )

        return (
            False,
            f"ingredient identity missing: {token}",
        )

    # ---------------------------------------------------------
    # Multi-word approximate match
    #
    # This is intentionally stricter than "one word matched".
    # ---------------------------------------------------------

    coverage = _coverage(
        core,
        evidence_tokens,
    )

    similarity = (
        _phrase_similarity(
            ingredient,
            title,
        )
    )

    # Most ingredient identity must remain.
    if (
        coverage >= 0.75
        and similarity >= 0.35
    ):
        return (
            True,
            "approximate",
        )

    missing = [
        token
        for token in core
        if token not in evidence_set
    ]

    return (
        False,
        "ingredient identity missing: "
        + ", ".join(
            missing
        ),
    )


# ---------------------------------------------------------------------
# Safe search-query generation
# ---------------------------------------------------------------------

def search_queries(
    ingredient: str,
) -> list[str]:
    """
    Generate specific -> safe fallback queries.

    The important rule is:

        Never drop the identity-bearing first word from a multi-word
        ingredient simply because the last word is generic.

    Examples:

        garlic powder
            -> ["garlic powder", "garlic"]

        coconut milk
            -> ["coconut milk", "coconut"]

        black pepper
            -> ["black pepper"]

        cherry tomatoes
            -> ["cherry tomatoes", "tomatoes"]

        chicken breasts
            -> ["chicken breasts", "chicken"]

    The fallback is only retrieval expansion. check_match() still validates
    every returned product against the ORIGINAL ingredient.
    """

    cleaned = clean_ingredient(
        ingredient
    )

    if not cleaned:
        return []

    # Preserve a natural cleaned version for Tavily.
    stripped = _strip_recipe_notes(
        ingredient
    )

    raw_tokens = [
        token
        for token in _WORD.findall(
            stripped
        )
        if (
            _stem(token)
            not in DESCRIPTORS
            and _stem(token)
            not in PORTION_WORDS
            and _stem(token)
            not in MEASUREMENT_WORDS
        )
    ]

    if raw_tokens:
        full_query = " ".join(
            raw_tokens
        )
    else:
        full_query = " ".join(
            cleaned
        )

    queries = [
        full_query
    ]

    if len(cleaned) > 1:

        first = cleaned[0]
        last = cleaned[-1]

        # -----------------------------------------------------
        # Some last words are ingredient forms.
        #
        # Dropping "garlic" from "garlic powder" would be unsafe.
        # Dropping "coconut" from "coconut milk" would be unsafe.
        #
        # In these cases fallback to the identity-bearing word.
        # -----------------------------------------------------

        form_words = {
            "powder",
            "milk",
            "oil",
            "sauce",
            "flour",
            "vinegar",
            "paste",
            "cream",
            "cheese",
            "stock",
            "broth",
            "butter",
        }

        if last in form_words:

            # garlic powder -> garlic
            # coconut milk  -> coconut
            fallback = first

        else:

            # cherry tomato -> tomato
            # chicken breast -> chicken
            #
            # We use morphology/structure only for retrieval;
            # check_match() still validates the original request.
            if last in {
                "breast",
                "thigh",
                "fillet",
                "loin",
                "wing",
                "leg",
            }:
                fallback = first
            else:
                fallback = last

        if (
            fallback
            and fallback
            != full_query
        ):
            queries.append(
                fallback
            )

    return list(
        dict.fromkeys(
            queries
        )
    )