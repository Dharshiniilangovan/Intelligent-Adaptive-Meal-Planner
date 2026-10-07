import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai
# from google.genai import types
from recipe_scrapers import scrape_me


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError(
        "\nGEMINI_API_KEY was not found in the .env file.\n"
        "Add:\n"
        "GEMINI_API_KEY=your_actual_key"
    )


# ============================================================
# CONFIGURATION
# ============================================================

CSV_FILE = Path(
    r"data\processed\recipe_kb_clean.csv"
)

URL_COLUMN = "url"
TIME_COLUMN = "cooking_time_min"
RECIPE_NAME_COLUMN = "recipe_name"

# ------------------------------------------------------------
# TEST MODE
# ------------------------------------------------------------
# Only missing cooking-time rows count toward this limit.
# Change to None later to process every missing recipe.
# ------------------------------------------------------------

MAX_RECIPES_TO_PROCESS = 15

REQUEST_DELAY = 1


# ============================================================
# GEMINI CONFIGURATION
# ============================================================

gemini_client = genai.Client(
    api_key=GEMINI_API_KEY
)

GEMINI_MODEL = "gemini-3.8-flash"


# ============================================================
# DATASET SIMILARITY SETTINGS
# ============================================================

MIN_NAME_SIMILARITY = 0.55
MIN_SIMILAR_RECIPES = 3
MAX_SIMILAR_RECIPES = 15

MIN_REFERENCE_TIME = 1
MAX_REFERENCE_TIME = 12 * 60


# ============================================================
# REQUEST HEADERS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_minutes(value):
    """
    Convert a value to positive integer minutes.

    Zero is deliberately rejected because we want a
    useful cooking-time value for the meal planner.
    No-cook recipes will continue to later fallback methods.
    """

    if value is None:
        return None

    try:

        minutes = int(
            round(float(value))
        )

        if 0 < minutes <= 24 * 60:
            return minutes

    except (TypeError, ValueError):
        pass

    return None

def clean_text(value):

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    value = str(value).lower()

    value = re.sub(
        r"[^a-z0-9\s]",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def normalize_category(value):

    return clean_text(value)


# ============================================================
# ISO-8601 DURATION -> MINUTES
# ============================================================

def iso_duration_to_minutes(value):
    """
    Examples:

    PT30M   -> 30
    PT1H    -> 60
    PT1H30M -> 90
    """

    if value is None:
        return None

    value = str(value).strip().upper()

    pattern = re.compile(
        r"^P"
        r"(?:(\d+(?:\.\d+)?)D)?"
        r"(?:T"
        r"(?:(\d+(?:\.\d+)?)H)?"
        r"(?:(\d+(?:\.\d+)?)M)?"
        r"(?:(\d+(?:\.\d+)?)S)?"
        r")?$"
    )

    match = pattern.match(value)

    if not match:
        return None

    days = float(match.group(1) or 0)
    hours = float(match.group(2) or 0)
    minutes = float(match.group(3) or 0)
    seconds = float(match.group(4) or 0)

    total = round(
        days * 1440
        + hours * 60
        + minutes
        + seconds / 60
    )

    return normalize_minutes(total)


# ============================================================
# HUMAN-READABLE DURATION -> MINUTES
# ============================================================

def parse_duration_text(text):

    if text is None:
        return None

    text = str(text).strip().lower()

    if not text:
        return None

    # --------------------------------------------------------
    # ISO duration
    # --------------------------------------------------------

    if text.upper().startswith("P"):

        result = iso_duration_to_minutes(
            text
        )

        if result is not None:
            return result

    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
    )

    # --------------------------------------------------------
    # HOUR RANGE
    # Example: 1-2 hours -> 120
    # --------------------------------------------------------

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*-\s*"
        r"(\d+(?:\.\d+)?)\s*"
        r"(?:hours?|hrs?|hr)\b",
        text
    )

    if match:

        upper_hours = float(
            match.group(2)
        )

        return normalize_minutes(
            upper_hours * 60
        )

    # --------------------------------------------------------
    # MINUTE RANGE
    # Example: 20-25 minutes -> 25
    # --------------------------------------------------------

    match = re.search(
        r"(\d+)\s*-\s*(\d+)\s*"
        r"(?:minutes?|mins?|min)\b",
        text
    )

    if match:

        return normalize_minutes(
            match.group(2)
        )

    # --------------------------------------------------------
    # HOURS + MINUTES
    # --------------------------------------------------------

    hours_match = re.search(
        r"(\d+(?:\.\d+)?)\s*"
        r"(?:hours?|hrs?|hr)\b",
        text
    )

    minutes_match = re.search(
        r"(\d+)\s*"
        r"(?:minutes?|mins?|min)\b",
        text
    )

    total = 0

    if hours_match:

        total += round(
            float(hours_match.group(1)) * 60
        )

    if minutes_match:

        total += int(
            minutes_match.group(1)
        )

    if total > 0:
        return normalize_minutes(total)

    return None


# ============================================================
# FETCH WEBPAGE
# ============================================================

def fetch_page(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
            allow_redirects=True
        )

        response.raise_for_status()

        html = response.text

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        return html, soup

    except Exception as e:

        print(
            f"   Direct webpage request failed: {e}"
        )

        return None, None


# ============================================================
# METHOD 1: RECIPE-SCRAPERS
# ============================================================

def get_time_recipe_scrapers(url):

    try:

        scraper = scrape_me(url)

        cook_time = scraper.cook_time()

        cook_time = normalize_minutes(
            cook_time
        )

        if cook_time is not None:

            return (
                cook_time,
                "recipe_scrapers_cooking",
                "HIGH",
                False
            )

    except Exception as e:

        print(
            f"   recipe-scrapers failed: {e}"
        )

    return None, None, None, None


# ============================================================
# JSON-LD HELPERS
# ============================================================

def find_recipe_objects(data):

    recipes = []

    if isinstance(data, dict):

        recipe_type = data.get("@type")

        is_recipe = False

        if isinstance(recipe_type, str):

            is_recipe = (
                recipe_type.lower()
                == "recipe"
            )

        elif isinstance(recipe_type, list):

            types = [
                str(item).lower()
                for item in recipe_type
            ]

            is_recipe = (
                "recipe" in types
            )

        if is_recipe:
            recipes.append(data)

        for value in data.values():

            recipes.extend(
                find_recipe_objects(value)
            )

    elif isinstance(data, list):

        for item in data:

            recipes.extend(
                find_recipe_objects(item)
            )

    return recipes


def get_json_ld_recipes(soup):

    recipes = []

    if soup is None:
        return recipes

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    for script in scripts:

        content = (
            script.string
            or script.get_text()
        )

        if not content:
            continue

        content = content.strip()

        try:

            data = json.loads(content)

        except Exception:
            continue

        recipes.extend(
            find_recipe_objects(data)
        )

    return recipes


# ============================================================
# METHOD 2: JSON-LD cookTime
# ============================================================

def get_time_json_ld(recipes):

    for recipe in recipes:

        value = recipe.get(
            "cookTime"
        )

        if not value:
            continue

        minutes = iso_duration_to_minutes(
            value
        )

        if minutes is None:

            minutes = parse_duration_text(
                value
            )

        if minutes is not None:

            return (
                minutes,
                "json_ld_cooking",
                "HIGH",
                False
            )

    return None, None, None, None


# ============================================================
# METHOD 3: MICRODATA cookTime
# ============================================================

def get_time_microdata(soup):

    if soup is None:
        return None, None, None, None

    elements = soup.find_all(
        attrs={
            "itemprop": re.compile(
                r"(^|\s)cookTime(\s|$)",
                re.IGNORECASE
            )
        }
    )

    for element in elements:

        value = (
            element.get("content")
            or element.get("datetime")
            or element.get("value")
            or element.get_text(
                " ",
                strip=True
            )
        )

        if not value:
            continue

        minutes = iso_duration_to_minutes(
            value
        )

        if minutes is None:

            minutes = parse_duration_text(
                value
            )

        if minutes is not None:

            return (
                minutes,
                "microdata_cooking",
                "HIGH",
                False
            )

    return None, None, None, None


# ============================================================
# METHOD 4: VISIBLE COOK TIME LABEL
# ============================================================

def get_time_visible_labels(soup):

    if soup is None:
        return None, None, None, None

    temp_soup = BeautifulSoup(
        str(soup),
        "html.parser"
    )

    for tag in temp_soup(
        [
            "script",
            "style",
            "noscript",
            "svg"
        ]
    ):
        tag.decompose()

    text = temp_soup.get_text(
        " ",
        strip=True
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    patterns = [
        (
            r"\bcook(?:ing)?\s*time"
            r"\s*[:\-]?\s*"
            r"((?:\d+(?:\.\d+)?\s*"
            r"(?:hours?|hrs?|hr)\s*)?"
            r"(?:\d+\s*"
            r"(?:minutes?|mins?|min))?)"
        ),

        (
            r"\btime\s+to\s+cook"
            r"\s*[:\-]?\s*"
            r"((?:\d+(?:\.\d+)?\s*"
            r"(?:hours?|hrs?|hr)\s*)?"
            r"(?:\d+\s*"
            r"(?:minutes?|mins?|min))?)"
        )
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE
        ):

            duration = (
                match.group(1)
                .strip()
            )

            if not duration:
                continue

            minutes = parse_duration_text(
                duration
            )

            if minutes is not None:

                return (
                    minutes,
                    "visible_cook_time_label",
                    "HIGH",
                    False
                )

    return None, None, None, None


# ============================================================
# METHOD 5: totalTime - prepTime
# ============================================================

def get_time_total_minus_prep(recipes):

    for recipe in recipes:

        if recipe.get("cookTime"):
            continue

        total_value = recipe.get(
            "totalTime"
        )

        prep_value = recipe.get(
            "prepTime"
        )

        if (
            not total_value
            or not prep_value
        ):
            continue

        total_minutes = iso_duration_to_minutes(
            total_value
        )

        if total_minutes is None:

            total_minutes = parse_duration_text(
                total_value
            )

        prep_minutes = iso_duration_to_minutes(
            prep_value
        )

        if prep_minutes is None:

            prep_minutes = parse_duration_text(
                prep_value
            )

        if (
            total_minutes is None
            or prep_minutes is None
        ):
            continue

        cooking_minutes = (
            total_minutes
            - prep_minutes
        )

        if cooking_minutes > 0:

            return (
                cooking_minutes,
                "derived_total_minus_prep",
                "MEDIUM_HIGH",
                False
            )

    return None, None, None, None


# ============================================================
# INSTRUCTION HELPERS
# ============================================================

def flatten_instructions(value):

    result = []

    if value is None:
        return result

    if isinstance(value, str):

        text = value.strip()

        if text:
            result.append(text)

    elif isinstance(value, list):

        for item in value:

            result.extend(
                flatten_instructions(item)
            )

    elif isinstance(value, dict):

        text = value.get("text")

        if text:

            result.extend(
                flatten_instructions(text)
            )

        elements = value.get(
            "itemListElement"
        )

        if elements:

            result.extend(
                flatten_instructions(elements)
            )

    return result


def extract_cooking_durations(text):

    if not text:
        return []

    text = (
        str(text)
        .lower()
        .replace("–", "-")
        .replace("—", "-")
    )

    verbs = (
        r"cook(?:ing)?|"
        r"bake|baking|"
        r"roast|roasting|"
        r"simmer|simmering|"
        r"boil|boiling|"
        r"grill|grilling|"
        r"broil|broiling|"
        r"fry|frying|"
        r"saute|sauté|"
        r"steam|steaming|"
        r"braise|braising|"
        r"poach|poaching|"
        r"sear|searing"
    )

    duration = (
        r"(?:"
        r"\d+(?:\.\d+)?\s*"
        r"(?:hours?|hrs?|hr)"
        r"(?:\s*(?:and\s*)?"
        r"\d+\s*"
        r"(?:minutes?|mins?|min))?"
        r"|"
        r"\d+\s*-\s*\d+\s*"
        r"(?:minutes?|mins?|min)"
        r"|"
        r"\d+\s*"
        r"(?:minutes?|mins?|min)"
        r")"
    )

    pattern = re.compile(
        rf"\b(?:{verbs})\b"
        rf"[^.!?;]{{0,100}}?"
        rf"({duration})",
        flags=re.IGNORECASE
    )

    values = []

    for match in pattern.finditer(text):

        minutes = parse_duration_text(
            match.group(1)
        )

        if (
            minutes is not None
            and minutes > 0
        ):

            values.append(minutes)

    return values


# ============================================================
# METHOD 6: INSTRUCTION DURATIONS
# ============================================================

def get_time_from_instructions(recipes):

    for recipe in recipes:

        instructions = flatten_instructions(
            recipe.get(
                "recipeInstructions"
            )
        )

        if not instructions:
            continue

        durations = []

        for instruction in instructions:

            durations.extend(
                extract_cooking_durations(
                    instruction
                )
            )

        durations = [
            value
            for value in durations
            if 0 < value <= 12 * 60
        ]

        if not durations:
            continue

        total = sum(durations)

        if 0 < total <= 12 * 60:

            return (
                total,
                "instructions_cooking_duration",
                "MEDIUM",
                False
            )

    return None, None, None, None


# ============================================================
# METHOD 7: NO-COOK DETECTION
# ============================================================

def detect_no_cook_recipe(
    recipe_name,
    row,
    recipes
):

    name = clean_text(
        recipe_name
    )

    dish_type = normalize_category(
        row.get(
            "dish_type",
            ""
        )
    )

    meal_type = normalize_category(
        row.get(
            "meal_type",
            ""
        )
    )

    combined = (
        name
        + " "
        + dish_type
        + " "
        + meal_type
    )

    strong_keywords = [
        "smoothie",
        "cocktail",
        "mocktail",
        "milkshake",
        "protein shake",
        "fruit shake",
        "no bake",
        "no cook",
        "overnight oats",
    ]

    keyword_found = any(
        keyword in combined
        for keyword in strong_keywords
    )

    if not keyword_found:

        return (
            None,
            None,
            None,
            None
        )

    # --------------------------------------------------------
    # Do not classify as no-cook if instructions contain
    # explicit heat/cooking operations.
    # --------------------------------------------------------

    cooking_verbs = re.compile(
        r"\b("
        r"bake|roast|boil|simmer|"
        r"grill|broil|fry|saute|sauté|"
        r"steam|braise|poach|sear|"
        r"cook for|cook until"
        r")\b",
        flags=re.IGNORECASE
    )

    for recipe in recipes:

        instructions = flatten_instructions(
            recipe.get(
                "recipeInstructions"
            )
        )

        instruction_text = " ".join(
            instructions
        )

        if cooking_verbs.search(
            instruction_text
        ):

            return (
                None,
                None,
                None,
                None
            )

    return (
        0,
        "no_cook_detection",
        "MEDIUM_HIGH",
        False
    )


# ============================================================
# METHOD 8: GEMINI 2.5 FLASH FALLBACK
# ============================================================

def get_time_gemini(
    recipe_name,
    url
):
    """
    Gemini 3.8 Flash fallback using Google's
    Interactions API + Google Search.

    Strategy:

    1. Search for the exact recipe.
    2. Prefer exact cooking/preparation time from the
       original recipe or reliable indexed sources.
    3. If exact information cannot be found, estimate
       a realistic time for the recipe.

    Returns:
        minutes,
        source,
        confidence,
        is_estimated
    """

    print(
        "7. Trying Gemini 3.8 Flash "
        "with Google Search..."
    )

    if pd.isna(recipe_name):
        recipe_name = ""

    recipe_name = str(
        recipe_name
    ).strip()

    if pd.isna(url):
        url = ""

    url = str(
        url
    ).strip()

    prompt = f"""
Find a useful time in minutes for this specific recipe.

RECIPE NAME:
{recipe_name}

ORIGINAL RECIPE URL:
{url}

==================================================
STEP 1 — SEARCH FOR THE EXACT RECIPE
==================================================

Use Google Search.

Search using:

- the exact recipe name
- the original URL
- the original domain
- indexed copies of the recipe
- other pages clearly referring to the same recipe

Prefer the original recipe page whenever possible.

If you find a reliable explicit cooking time for the
exact recipe, return that.

If the recipe is naturally a no-cook recipe such as a
smoothie, cocktail, shake, cold dip, or similar recipe,
look for its preparation/ready time instead so that the
database receives a useful positive time value.

Never return 0.

==================================================
STEP 2 — ESTIMATE IF EXACT INFORMATION IS MISSING
==================================================

If you cannot find a reliable exact time, estimate a
realistic amount of time required to make this specific
recipe.

Use the recipe name and likely cooking/preparation method.

Examples of factors to consider:

- baking time
- roasting time
- simmering time
- grilling time
- frying time
- boiling time
- assembly/blending time for no-cook recipes
- normal time required for this type of dish

The value must be useful for meal planning.

Do not return 0.

The value must be at least 1 minute.

Do not give an unrealistically precise estimate when
evidence is weak.

==================================================
OUTPUT
==================================================

Return EXACTLY these three lines:

TIME_MIN: <positive integer>
FOUND_EXACT_TIME: <YES or NO>
CONFIDENCE: <HIGH, MEDIUM, or LOW>

Example when search finds the exact recipe time:

TIME_MIN: 45
FOUND_EXACT_TIME: YES
CONFIDENCE: HIGH

Example when estimation is required:

TIME_MIN: 30
FOUND_EXACT_TIME: NO
CONFIDENCE: MEDIUM

Return no other text.
"""

    try:

        # ====================================================
        # GEMINI 3.8 INTERACTIONS API
        # ====================================================

        interaction = (
            gemini_client
            .interactions
            .create(
                model=GEMINI_MODEL,

                input=prompt,

                tools=[
                    {
                        "type": "google_search"
                    }
                ],

                generation_config={
                    "thinking_level": "low"
                }
            )
        )

        text = interaction.output_text

        if not text:

            print(
                "   Gemini returned no text."
            )

            return (
                None,
                None,
                None,
                None
            )

        text = text.strip()

        print(
            f"   Gemini response:\n{text}"
        )

        # ====================================================
        # EXTRACT TIME
        # ====================================================

        time_match = re.search(
            r"TIME_MIN\s*:\s*(\d+)",
            text,
            flags=re.IGNORECASE
        )

        if not time_match:

            print(
                "   Could not parse Gemini time."
            )

            return (
                None,
                None,
                None,
                None
            )

        minutes = int(
            time_match.group(1)
        )

        # ====================================================
        # ZERO / INVALID PROTECTION
        # ====================================================

        if minutes <= 0:

            print(
                "   Gemini returned zero or a "
                "negative value. Rejecting it."
            )

            return (
                None,
                None,
                None,
                None
            )

        if minutes > 24 * 60:

            print(
                "   Gemini returned an unreasonable "
                f"value: {minutes} minutes."
            )

            return (
                None,
                None,
                None,
                None
            )

        # ====================================================
        # EXACT OR ESTIMATED
        # ====================================================

        exact_match = re.search(
            r"FOUND_EXACT_TIME\s*:\s*"
            r"(YES|NO)",
            text,
            flags=re.IGNORECASE
        )

        if not exact_match:

            print(
                "   Gemini did not specify whether "
                "the result was exact."
            )

            return (
                None,
                None,
                None,
                None
            )

        found_exact = (
            exact_match
            .group(1)
            .upper()
            == "YES"
        )

        # ====================================================
        # CONFIDENCE
        # ====================================================

        confidence_match = re.search(
            r"CONFIDENCE\s*:\s*"
            r"(HIGH|MEDIUM|LOW)",
            text,
            flags=re.IGNORECASE
        )

        if confidence_match:

            confidence = (
                confidence_match
                .group(1)
                .upper()
            )

        else:

            confidence = (
                "MEDIUM"
                if found_exact
                else "LOW"
            )

        # ====================================================
        # RETURN EXACT RESULT
        # ====================================================

        if found_exact:

            print(
                f"   Gemini found exact/search-supported "
                f"time: {minutes} minutes"
            )

            return (
                minutes,
                "gemini_search_exact",
                confidence,
                False
            )

        # ====================================================
        # RETURN ESTIMATE
        # ====================================================

        print(
            f"   Gemini estimated time: "
            f"{minutes} minutes"
        )

        return (
            minutes,
            "gemini_estimate",
            confidence,
            True
        )

    except Exception as e:

        print(
            f"   Gemini API failed: {e}"
        )

        return (
            None,
            None,
            None,
            None
        )
# ============================================================
# DATASET REFERENCE SET
# ============================================================

def build_reference_dataset(df):

    references = []

    for index, row in df.iterrows():

        value = row.get(
            TIME_COLUMN
        )

        if pd.isna(value):
            continue

        try:

            minutes = int(
                round(float(value))
            )

        except (TypeError, ValueError):
            continue

        if not (
            MIN_REFERENCE_TIME
            <= minutes
            <= MAX_REFERENCE_TIME
        ):
            continue

        name = clean_text(
            row.get(
                RECIPE_NAME_COLUMN,
                ""
            )
        )

        if not name:
            continue

        references.append(
            {
                "index": index,

                "name": name,

                "minutes": minutes,

                "dish_type": normalize_category(
                    row.get(
                        "dish_type",
                        ""
                    )
                ),

                "meal_type": normalize_category(
                    row.get(
                        "meal_type",
                        ""
                    )
                ),

                "cuisine_type": normalize_category(
                    row.get(
                        "cuisine_type",
                        ""
                    )
                ),
            }
        )

    return references


# ============================================================
# SIMILARITY HELPERS
# ============================================================

STOP_WORDS = {
    "a",
    "an",
    "and",
    "the",
    "with",
    "of",
    "for",
    "in",
    "on",
    "to",
    "from",
    "style",
    "recipe",
    "easy",
    "best",
    "perfect",
    "homemade",
}


def meaningful_tokens(text):

    words = set(
        clean_text(text).split()
    )

    return {
        word
        for word in words
        if (
            len(word) >= 3
            and word not in STOP_WORDS
        )
    }


def token_similarity(a, b):

    a_tokens = meaningful_tokens(a)
    b_tokens = meaningful_tokens(b)

    if (
        not a_tokens
        or not b_tokens
    ):
        return 0.0

    intersection = len(
        a_tokens & b_tokens
    )

    union = len(
        a_tokens | b_tokens
    )

    if union == 0:
        return 0.0

    return (
        intersection / union
    )


def calculate_similarity(
    recipe_name,
    row,
    reference
):

    target_name = clean_text(
        recipe_name
    )

    sequence_score = SequenceMatcher(
        None,
        target_name,
        reference["name"]
    ).ratio()

    token_score = token_similarity(
        target_name,
        reference["name"]
    )

    score = (
        sequence_score * 0.45
        + token_score * 0.35
    )

    target_dish = normalize_category(
        row.get(
            "dish_type",
            ""
        )
    )

    target_meal = normalize_category(
        row.get(
            "meal_type",
            ""
        )
    )

    target_cuisine = normalize_category(
        row.get(
            "cuisine_type",
            ""
        )
    )

    if (
        target_dish
        and reference["dish_type"]
        and target_dish
        == reference["dish_type"]
    ):
        score += 0.10

    if (
        target_meal
        and reference["meal_type"]
        and target_meal
        == reference["meal_type"]
    ):
        score += 0.05

    if (
        target_cuisine
        and reference["cuisine_type"]
        and target_cuisine
        == reference["cuisine_type"]
    ):
        score += 0.05

    return min(
        score,
        1.0
    )


# ============================================================
# WEIGHTED MEDIAN
# ============================================================

def weighted_median(values):

    if not values:
        return None

    values = sorted(
        values,
        key=lambda item: item[0]
    )

    total_weight = sum(
        weight
        for _, weight in values
    )

    halfway = (
        total_weight / 2
    )

    cumulative = 0

    for minutes, weight in values:

        cumulative += weight

        if cumulative >= halfway:

            return int(
                round(minutes)
            )

    return int(
        round(values[-1][0])
    )


# ============================================================
# METHOD 9: SIMILAR RECIPES
# ============================================================

def estimate_from_similar_recipes(
    recipe_name,
    row,
    references
):

    scored = []

    for reference in references:

        score = calculate_similarity(
            recipe_name,
            row,
            reference
        )

        if score >= MIN_NAME_SIMILARITY:

            scored.append(
                (
                    score,
                    reference
                )
            )

    scored.sort(
        key=lambda item: item[0],
        reverse=True
    )

    scored = scored[
        :MAX_SIMILAR_RECIPES
    ]

    if len(scored) < MIN_SIMILAR_RECIPES:

        return (
            None,
            None,
            None,
            None
        )

    times = [
        item[1]["minutes"]
        for item in scored
    ]

    median = float(
        pd.Series(times).median()
    )

    deviations = [
        abs(value - median)
        for value in times
    ]

    mad = float(
        pd.Series(
            deviations
        ).median()
    )

    filtered = []

    for score, reference in scored:

        difference = abs(
            reference["minutes"]
            - median
        )

        threshold = max(
            15,
            mad * 3
        )

        if difference <= threshold:

            filtered.append(
                (
                    score,
                    reference
                )
            )

    if len(filtered) < MIN_SIMILAR_RECIPES:

        return (
            None,
            None,
            None,
            None
        )

    weighted_values = [
        (
            reference["minutes"],
            score ** 2
        )
        for score, reference
        in filtered
    ]

    estimated = weighted_median(
        weighted_values
    )

    if estimated is None:

        return (
            None,
            None,
            None,
            None
        )

    best_score = filtered[0][0]

    if (
        best_score >= 0.80
        and len(filtered) >= 4
    ):

        confidence = "MEDIUM_HIGH"

    elif (
        best_score >= 0.65
        and len(filtered) >= 3
    ):

        confidence = "MEDIUM"

    else:

        confidence = "LOW"

    return (
        estimated,
        "similar_recipe_estimate",
        confidence,
        True
    )


# ============================================================
# CATEGORY HELPERS
# ============================================================

def matching_category_times(
    row,
    references,
    require_dish=True,
    require_meal=False,
    require_cuisine=False
):

    target_dish = normalize_category(
        row.get(
            "dish_type",
            ""
        )
    )

    target_meal = normalize_category(
        row.get(
            "meal_type",
            ""
        )
    )

    target_cuisine = normalize_category(
        row.get(
            "cuisine_type",
            ""
        )
    )

    values = []

    for reference in references:

        if require_dish:

            if (
                not target_dish
                or reference["dish_type"]
                != target_dish
            ):
                continue

        if require_meal:

            if (
                not target_meal
                or reference["meal_type"]
                != target_meal
            ):
                continue

        if require_cuisine:

            if (
                not target_cuisine
                or reference["cuisine_type"]
                != target_cuisine
            ):
                continue

        values.append(
            reference["minutes"]
        )

    return values


def robust_category_median(values):

    if len(values) < 5:
        return None

    series = pd.Series(
        values,
        dtype="float64"
    )

    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)

    iqr = q3 - q1

    lower = max(
        0,
        q1 - 1.5 * iqr
    )

    upper = (
        q3 + 1.5 * iqr
    )

    filtered = series[
        (series >= lower)
        & (series <= upper)
    ]

    if len(filtered) < 5:
        return None

    return int(
        round(
            filtered.median()
        )
    )


# ============================================================
# METHOD 10: CATEGORY ESTIMATION
# ============================================================

def estimate_from_categories(
    row,
    references
):

    combinations = [
        (
            True,
            True,
            True,
            "dish_meal_cuisine_estimate",
            "MEDIUM"
        ),

        (
            True,
            True,
            False,
            "dish_meal_estimate",
            "LOW_MEDIUM"
        ),

        (
            True,
            False,
            True,
            "dish_cuisine_estimate",
            "LOW_MEDIUM"
        ),

        (
            True,
            False,
            False,
            "dish_type_estimate",
            "LOW"
        ),
    ]

    for (
        require_dish,
        require_meal,
        require_cuisine,
        source,
        confidence
    ) in combinations:

        values = matching_category_times(
            row,
            references,
            require_dish=require_dish,
            require_meal=require_meal,
            require_cuisine=require_cuisine
        )

        estimate = robust_category_median(
            values
        )

        if estimate is not None:

            return (
                estimate,
                source,
                confidence,
                True
            )

    return (
        None,
        None,
        None,
        None
    )


# ============================================================
# MASTER EXTRACTION FUNCTION
# ============================================================

def get_recipe_time(
    recipe_name,
    url,
    row,
    references
):
    """
    Priority:

    1. recipe-scrapers
    2. JSON-LD
    3. Microdata
    4. Visible Cook Time
    5. totalTime - prepTime
    6. Instruction cooking durations
    7. No-cook detection
    8. Gemini 2.5 Flash + Google Search
    9. Similar recipes
    10. Category estimate
    """

    soup = None
    recipes = []

    valid_url = (
        pd.notna(url)
        and str(url).strip()
    )

    # ========================================================
    # METHODS THAT REQUIRE THE ORIGINAL URL
    # ========================================================

    if valid_url:

        url = str(url).strip()

        # ----------------------------------------------------
        # 1. RECIPE-SCRAPERS
        # ----------------------------------------------------

        print(
            "1. Trying recipe-scrapers..."
        )

        result = get_time_recipe_scrapers(
            url
        )

        if result[0] is not None:
            return result

        # ----------------------------------------------------
        # DOWNLOAD WEBPAGE ONCE
        # ----------------------------------------------------

        print(
            "   Downloading webpage..."
        )

        html, soup = fetch_page(
            url
        )

        if soup is not None:

            recipes = get_json_ld_recipes(
                soup
            )

            # ------------------------------------------------
            # 2. JSON-LD
            # ------------------------------------------------

            print(
                "2. Trying JSON-LD..."
            )

            result = get_time_json_ld(
                recipes
            )

            if result[0] is not None:
                return result

            # ------------------------------------------------
            # 3. MICRODATA
            # ------------------------------------------------

            print(
                "3. Trying Microdata..."
            )

            result = get_time_microdata(
                soup
            )

            if result[0] is not None:
                return result

            # ------------------------------------------------
            # 4. VISIBLE LABEL
            # ------------------------------------------------

            print(
                "4. Trying visible Cook Time..."
            )

            result = get_time_visible_labels(
                soup
            )

            if result[0] is not None:
                return result

            # ------------------------------------------------
            # 5. TOTAL - PREP
            # ------------------------------------------------

            print(
                "5. Trying totalTime - prepTime..."
            )

            result = get_time_total_minus_prep(
                recipes
            )

            if result[0] is not None:
                return result

            # ------------------------------------------------
            # 6. INSTRUCTIONS
            # ------------------------------------------------

            print(
                "6. Trying instruction durations..."
            )

            result = get_time_from_instructions(
                recipes
            )

            if result[0] is not None:
                return result

    # ========================================================
    # 7. NO-COOK DETECTION
    # ========================================================

    # print(
    #     "7. Checking for no-cook recipe..."
    # )

    # result = detect_no_cook_recipe(
    #     recipe_name,
    #     row,
    #     recipes
    # )

    # if result[0] is not None:
    #     return result

    # ========================================================
    # 8. GEMINI
    # ========================================================

    result = get_time_gemini(
        recipe_name,
        url
    )

    if result[0] is not None:
        return result

    # ========================================================
    # 9. SIMILAR RECIPES
    # ========================================================

    print(
        "9. Trying similar recipes "
        "from dataset..."
    )

    result = estimate_from_similar_recipes(
        recipe_name,
        row,
        references
    )

    if result[0] is not None:
        return result

    # ========================================================
    # 10. CATEGORY ESTIMATION
    # ========================================================

    print(
        "10. Trying category estimate..."
    )

    result = estimate_from_categories(
        row,
        references
    )

    if result[0] is not None:
        return result

    return (
        None,
        None,
        None,
        None
    )


# ============================================================
# SAVE CSV FUNCTION
# ============================================================
#
# KEEP THIS FUNCTION.
# IT IS CURRENTLY NOT CALLED.
#
# ============================================================

def save_csv(df):

    df.to_csv(
        CSV_FILE,
        index=False
    )

    return df


# ============================================================
# CHECK CSV
# ============================================================

if not CSV_FILE.exists():

    raise FileNotFoundError(
        f"\nCSV file not found:\n{CSV_FILE}"
    )


# ============================================================
# LOAD CSV
# ============================================================

print("=" * 70)
print("RECIPE COOKING TIME EXTRACTION - GEMINI TEST")
print("=" * 70)

print(
    f"\nReading:\n{CSV_FILE}"
)

df = pd.read_csv(
    CSV_FILE
)

print(
    f"\nRecipes loaded: {len(df):,}"
)

print(
    f"\nColumns:\n{list(df.columns)}"
)


# ============================================================
# VALIDATE COLUMNS
# ============================================================

required_columns = [
    RECIPE_NAME_COLUMN,
    URL_COLUMN
]

for column in required_columns:

    if column not in df.columns:

        raise ValueError(
            f"\nRequired column missing: "
            f"{column}"
        )


if TIME_COLUMN not in df.columns:

    df[TIME_COLUMN] = pd.NA

    print(
        f"\nCreated in-memory column: "
        f"{TIME_COLUMN}"
    )

else:

    print(
        f"\nUsing existing column: "
        f"{TIME_COLUMN}"
    )


# ============================================================
# BUILD REFERENCE DATASET
# ============================================================

print(
    "\nBuilding reference dataset from recipes "
    "that already have cooking times..."
)

references = build_reference_dataset(
    df
)

print(
    f"Reference recipes available: "
    f"{len(references):,}"
)


# ============================================================
# TEST COUNTERS
# ============================================================

test_results = []

processed = 0
found = 0

exact_or_derived = 0
estimated = 0
failed = 0

gemini_exact = 0
gemini_estimated = 0


# ============================================================
# PROCESS MISSING RECIPES
# ============================================================

for index, row in df.iterrows():

    # --------------------------------------------------------
    # STOP AT TEST LIMIT
    # --------------------------------------------------------

    if (
        MAX_RECIPES_TO_PROCESS is not None
        and processed
        >= MAX_RECIPES_TO_PROCESS
    ):
        break

    existing = row.get(
        TIME_COLUMN
    )

    # --------------------------------------------------------
    # SKIP RECIPES THAT ALREADY HAVE A TIME
    # --------------------------------------------------------

    if pd.notna(existing):

        existing_text = str(
            existing
        ).strip()

        if (
            existing_text
            and existing_text.lower()
            not in [
                "",
                "nan",
                "none"
            ]
        ):
            continue

    processed += 1

    recipe_id = row.get(
        "recipe_id",
        f"Row-{index + 1}"
    )

    recipe_name = row.get(
        RECIPE_NAME_COLUMN,
        ""
    )

    url = row.get(
        URL_COLUMN
    )

    print("\n" + "=" * 70)

    print(
        f"TEST RECIPE "
        f"{processed}/"
        f"{MAX_RECIPES_TO_PROCESS}"
    )

    print(
        f"Recipe ID: {recipe_id}"
    )

    print(
        f"Recipe: {recipe_name}"
    )

    print(
        f"URL: {url}"
    )

    print("-" * 70)

    (
        minutes,
        source,
        confidence,
        is_estimated
    ) = get_recipe_time(
        recipe_name,
        url,
        row,
        references
    )

    # ========================================================
    # FOUND
    # ========================================================

    if minutes is not None:

        found += 1

        if is_estimated:
            estimated += 1

        else:
            exact_or_derived += 1

        if source == "gemini_search_exact":
            gemini_exact += 1

        if source == "gemini_estimate":
            gemini_estimated += 1

        # ----------------------------------------------------
        # MEMORY ONLY
        #
        # THIS DOES NOT SAVE TO THE CSV.
        # ----------------------------------------------------

        df.at[
            index,
            TIME_COLUMN
        ] = minutes

        print("\nRESULT")

        print(
            f"Cooking time : "
            f"{minutes} minutes"
        )

        print(
            f"Source       : "
            f"{source}"
        )

        print(
            f"Confidence   : "
            f"{confidence}"
        )

        print(
            f"Estimated    : "
            f"{is_estimated}"
        )

    # ========================================================
    # NOT FOUND
    # ========================================================

    else:

        failed += 1

        print("\nRESULT")

        print(
            "Cooking time : NOT FOUND"
        )

        print(
            "Source       : None"
        )

        print(
            "Confidence   : None"
        )

        print(
            "Estimated    : None"
        )

    # ========================================================
    # RECORD TEST RESULT
    # ========================================================

    test_results.append(
        {
            "recipe_id": recipe_id,
            "recipe_name": recipe_name,
            "cooking_time_min": minutes,
            "source": source,
            "confidence": confidence,
            "is_estimated": is_estimated,
        }
    )

    # ========================================================
    # SAVE CURRENTLY DISABLED
    # ========================================================

    # df = save_csv(df)

    # ========================================================
    # DELAY
    # ========================================================

    time.sleep(
        REQUEST_DELAY
    )


# ============================================================
# FINAL SAVE
# CURRENTLY DISABLED
# ============================================================

# df = save_csv(df)


# ============================================================
# RESULTS TABLE
# ============================================================

results_df = pd.DataFrame(
    test_results
)

print("\n")
print("=" * 70)
print("TEST RESULTS")
print("=" * 70)

if not results_df.empty:

    print(
        results_df.to_string(
            index=False
        )
    )


# ============================================================
# SUMMARY
# ============================================================

print("\n")
print("=" * 70)
print("SUMMARY")
print("=" * 70)

print(
    f"Recipes tested             : "
    f"{processed}"
)

print(
    f"Cooking times found        : "
    f"{found}"
)

print(
    f"Exact / derived values     : "
    f"{exact_or_derived}"
)

print(
    f"Estimated values           : "
    f"{estimated}"
)

print(
    f"Gemini exact/search values : "
    f"{gemini_exact}"
)

print(
    f"Gemini estimates           : "
    f"{gemini_estimated}"
)

print(
    f"Still missing              : "
    f"{failed}"
)

if processed > 0:

    coverage = (
        found
        / processed
        * 100
    )

    print(
        f"Coverage                   : "
        f"{coverage:.1f}%"
    )

print(
    "\nCSV MODIFIED               : NO"
)

print(
    "All results are test-only."
)

print(
    f"Source CSV                 : "
    f"{CSV_FILE}"
)