import json
import math
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from recipe_scrapers import scrape_me


# ============================================================
# CONFIGURATION
# ============================================================

CSV_FILE = Path(
    r"data\processed\recipe_kb_clean.csv"
)

URL_COLUMN = "url"
TIME_COLUMN = "cooking_time_min"
RECIPE_NAME_COLUMN = "recipe_name"

# Test more recipes for a meaningful coverage estimate.
MAX_RECIPES_TO_PROCESS = 30

REQUEST_DELAY = 1

# ------------------------------------------------------------
# SIMILARITY SETTINGS
# ------------------------------------------------------------

MIN_NAME_SIMILARITY = 0.55

MIN_SIMILAR_RECIPES = 3

MAX_SIMILAR_RECIPES = 15

# Avoid using obviously strange existing values as references.
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
# NORMALIZATION HELPERS
# ============================================================

def normalize_minutes(value):

    if value is None:
        return None

    try:
        minutes = int(round(float(value)))

        if 0 <= minutes <= 24 * 60:
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

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return clean_text(value)


# ============================================================
# ISO-8601 DURATION
# ============================================================

def iso_duration_to_minutes(value):

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

    days = float(
        match.group(1) or 0
    )

    hours = float(
        match.group(2) or 0
    )

    minutes = float(
        match.group(3) or 0
    )

    seconds = float(
        match.group(4) or 0
    )

    total = round(
        days * 1440
        + hours * 60
        + minutes
        + seconds / 60
    )

    return normalize_minutes(
        total
    )


# ============================================================
# HUMAN DURATION PARSER
# ============================================================

def parse_duration_text(text):

    if text is None:
        return None

    text = str(text).strip().lower()

    if not text:
        return None

    # ISO duration
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
    # 1 hour 30 minutes
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

    if hours_match:

        hours = float(
            hours_match.group(1)
        )

        total = round(
            hours * 60
        )

        if minutes_match:

            total += int(
                minutes_match.group(1)
            )

        return normalize_minutes(
            total
        )

    # --------------------------------------------------------
    # 20-25 minutes
    # Use upper end.
    # --------------------------------------------------------

    range_match = re.search(
        r"(\d+)\s*-\s*(\d+)\s*"
        r"(?:minutes?|mins?|min)\b",
        text
    )

    if range_match:

        return normalize_minutes(
            range_match.group(2)
        )

    # --------------------------------------------------------
    # 30 minutes
    # --------------------------------------------------------

    if minutes_match:

        return normalize_minutes(
            minutes_match.group(1)
        )

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

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        return response.text, soup

    except Exception as e:

        print(
            f"Direct webpage request failed: {e}"
        )

        return None, None


# ============================================================
# METHOD 1: RECIPE-SCRAPERS
# ============================================================

def get_time_recipe_scrapers(url):

    try:

        scraper = scrape_me(
            url
        )

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
            f"recipe-scrapers failed: {e}"
        )

    return None, None, None, None


# ============================================================
# FIND JSON-LD RECIPE OBJECTS
# ============================================================

def find_recipe_objects(data):

    recipes = []

    if isinstance(data, dict):

        recipe_type = data.get(
            "@type"
        )

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
                find_recipe_objects(
                    value
                )
            )

    elif isinstance(data, list):

        for item in data:

            recipes.extend(
                find_recipe_objects(
                    item
                )
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

            data = json.loads(
                content
            )

        except Exception:
            continue

        recipes.extend(
            find_recipe_objects(
                data
            )
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

        minutes = (
            iso_duration_to_minutes(
                value
            )
        )

        if minutes is None:

            minutes = (
                parse_duration_text(
                    value
                )
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
# METHOD 3: MICRODATA
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

        minutes = (
            iso_duration_to_minutes(
                value
            )
        )

        if minutes is None:

            minutes = (
                parse_duration_text(
                    value
                )
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
# METHOD 4: VISIBLE COOK-TIME LABEL
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

            minutes = (
                parse_duration_text(
                    duration
                )
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
# METHOD 5: TOTAL TIME - PREP TIME
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

        total_minutes = (
            iso_duration_to_minutes(
                total_value
            )
        )

        if total_minutes is None:

            total_minutes = (
                parse_duration_text(
                    total_value
                )
            )

        prep_minutes = (
            iso_duration_to_minutes(
                prep_value
            )
        )

        if prep_minutes is None:

            prep_minutes = (
                parse_duration_text(
                    prep_value
                )
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

        if cooking_minutes >= 0:

            return (
                cooking_minutes,
                "derived_total_minus_prep",
                "MEDIUM_HIGH",
                False
            )

    return None, None, None, None


# ============================================================
# FLATTEN RECIPE INSTRUCTIONS
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
                flatten_instructions(
                    item
                )
            )

    elif isinstance(value, dict):

        text = value.get(
            "text"
        )

        if text:

            result.extend(
                flatten_instructions(
                    text
                )
            )

        elements = value.get(
            "itemListElement"
        )

        if elements:

            result.extend(
                flatten_instructions(
                    elements
                )
            )

    return result


# ============================================================
# EXTRACT COOKING DURATIONS
# ============================================================

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

    for match in pattern.finditer(
        text
    ):

        minutes = parse_duration_text(
            match.group(1)
        )

        if (
            minutes is not None
            and minutes > 0
        ):

            values.append(
                minutes
            )

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

        # ----------------------------------------------------
        # Avoid absurd totals caused by duplicated
        # instructions.
        # ----------------------------------------------------

        total = sum(
            durations
        )

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
    recipes,
    soup
):
    """
    Detect recipes where cooking time should legitimately be 0.

    This is deliberately conservative.
    """

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

    # --------------------------------------------------------
    # STRONG NO-COOK RECIPE TYPES
    # --------------------------------------------------------

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
        "salsa",
        "vinaigrette",
        "salad dressing",
        "dressing",
        "dip",
    ]

    matched_keyword = None

    for keyword in strong_keywords:

        if keyword in combined:

            matched_keyword = keyword
            break

    if matched_keyword is None:

        return (
            None,
            None,
            None,
            None
        )

    # --------------------------------------------------------
    # SAFETY CHECK:
    #
    # Do not classify as no-cook if instructions explicitly
    # contain cooking operations.
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

    # --------------------------------------------------------
    # HIGH CONFIDENCE NO-COOK
    # --------------------------------------------------------

    return (
        0,
        "no_cook_detection",
        "MEDIUM_HIGH",
        False
    )


# ============================================================
# BUILD REFERENCE DATASET
# ============================================================

def build_reference_dataset(df):
    """
    Build a clean set of recipes that already have known
    cooking times.

    These will be used for similarity estimation.
    """

    references = []

    for index, row in df.iterrows():

        time_value = row.get(
            TIME_COLUMN
        )

        if pd.isna(time_value):
            continue

        try:

            minutes = int(
                round(
                    float(time_value)
                )
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

                "is_vegetarian": row.get(
                    "is_vegetarian"
                ),

                "is_vegan": row.get(
                    "is_vegan"
                ),
            }
        )

    return references


# ============================================================
# WORD TOKEN HELPERS
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

    a_tokens = meaningful_tokens(
        a
    )

    b_tokens = meaningful_tokens(
        b
    )

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
        intersection
        / union
    )


# ============================================================
# RECIPE SIMILARITY SCORE
# ============================================================

def calculate_similarity(
    recipe_name,
    row,
    reference
):

    target_name = clean_text(
        recipe_name
    )

    sequence_score = (
        SequenceMatcher(
            None,
            target_name,
            reference["name"]
        )
        .ratio()
    )

    token_score = token_similarity(
        target_name,
        reference["name"]
    )

    # Name similarity is the strongest signal.
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

    # --------------------------------------------------------
    # CATEGORY BONUSES
    # --------------------------------------------------------

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
    """
    values:
        [(minutes, weight), ...]
    """

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
# METHOD 8: SIMILAR RECIPE ESTIMATION
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

    if (
        len(scored)
        < MIN_SIMILAR_RECIPES
    ):

        return (
            None,
            None,
            None,
            None
        )

    # --------------------------------------------------------
    # Check whether similar recipes actually agree.
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Remove extreme neighbors.
    # --------------------------------------------------------

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

    if (
        len(filtered)
        < MIN_SIMILAR_RECIPES
    ):

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

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

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
# CATEGORY MATCHING
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


# ============================================================
# ROBUST CATEGORY MEDIAN
# ============================================================

def robust_category_median(values):

    if len(values) < 5:
        return None

    series = pd.Series(
        values,
        dtype="float64"
    )

    q1 = series.quantile(
        0.25
    )

    q3 = series.quantile(
        0.75
    )

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
# METHOD 9: CATEGORY ESTIMATION
# ============================================================

def estimate_from_categories(
    row,
    references
):
    """
    Progressively relax category matching.

    Most specific first.
    """

    combinations = [
        # dish + meal + cuisine
        (
            True,
            True,
            True,
            "dish_meal_cuisine_estimate",
            "MEDIUM"
        ),

        # dish + meal
        (
            True,
            True,
            False,
            "dish_meal_estimate",
            "LOW_MEDIUM"
        ),

        # dish + cuisine
        (
            True,
            False,
            True,
            "dish_cuisine_estimate",
            "LOW_MEDIUM"
        ),

        # dish only
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
# MASTER EXTRACTION
# ============================================================

def get_recipe_time(
    recipe_name,
    url,
    row,
    references
):
    """
    Priority:

    EXACT / DERIVED
    ----------------
    1. recipe-scrapers
    2. JSON-LD
    3. Microdata
    4. Visible cook-time label
    5. totalTime - prepTime
    6. Explicit instruction durations
    7. No-cook detection

    ESTIMATION
    ----------
    8. Similar recipes
    9. Category median

    Returns:

        minutes
        source
        confidence
        is_estimated
    """

    soup = None
    recipes = []

    # ========================================================
    # 1. RECIPE-SCRAPERS
    # ========================================================

    if (
        pd.notna(url)
        and str(url).strip()
    ):

        url = str(url).strip()

        print(
            "1. Trying recipe-scrapers..."
        )

        result = get_time_recipe_scrapers(
            url
        )

        if result[0] is not None:
            return result

        # ====================================================
        # DOWNLOAD PAGE
        # ====================================================

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

            # ================================================
            # 2. JSON-LD
            # ================================================

            print(
                "2. Trying JSON-LD..."
            )

            result = get_time_json_ld(
                recipes
            )

            if result[0] is not None:
                return result

            # ================================================
            # 3. MICRODATA
            # ================================================

            print(
                "3. Trying Microdata..."
            )

            result = get_time_microdata(
                soup
            )

            if result[0] is not None:
                return result

            # ================================================
            # 4. VISIBLE LABEL
            # ================================================

            print(
                "4. Trying visible Cook Time..."
            )

            result = get_time_visible_labels(
                soup
            )

            if result[0] is not None:
                return result

            # ================================================
            # 5. TOTAL - PREP
            # ================================================

            print(
                "5. Trying totalTime - prepTime..."
            )

            result = get_time_total_minus_prep(
                recipes
            )

            if result[0] is not None:
                return result

            # ================================================
            # 6. INSTRUCTIONS
            # ================================================

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

    print(
        "7. Checking whether recipe is no-cook..."
    )

    result = detect_no_cook_recipe(
        recipe_name,
        row,
        recipes,
        soup
    )

    if result[0] is not None:
        return result

    # ========================================================
    # 8. SIMILAR RECIPE ESTIMATION
    # ========================================================

    print(
        "8. Trying similar recipes in dataset..."
    )

    result = estimate_from_similar_recipes(
        recipe_name,
        row,
        references
    )

    if result[0] is not None:
        return result

    # ========================================================
    # 9. CATEGORY ESTIMATION
    # ========================================================

    print(
        "9. Trying category-based estimate..."
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
# SAVE CSV
# ============================================================
#
# KEPT FOR LATER.
# CURRENTLY NOT CALLED.
#
# ============================================================

def save_csv(df):

    df.to_csv(
        CSV_FILE,
        index=False
    )

    return df


# ============================================================
# CHECK FILE
# ============================================================

if not CSV_FILE.exists():

    raise FileNotFoundError(
        f"\nCSV file not found:\n{CSV_FILE}"
    )


# ============================================================
# LOAD DATA
# ============================================================

print("=" * 70)
print("RECIPE COOKING TIME EXTRACTION - ADVANCED TEST")
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
            f"Required column missing: {column}"
        )


if TIME_COLUMN not in df.columns:

    df[TIME_COLUMN] = pd.NA


# ============================================================
# BUILD REFERENCE DATASET
# ============================================================

print(
    "\nBuilding reference dataset "
    "from recipes with known cooking times..."
)

references = build_reference_dataset(
    df
)

print(
    f"Reference recipes available: "
    f"{len(references):,}"
)


# ============================================================
# TEST RESULTS
# ============================================================

test_results = []

processed = 0
found = 0
exact_or_derived = 0
estimated = 0
failed = 0


# ============================================================
# PROCESS MISSING RECIPES
# ============================================================

for index, row in df.iterrows():

    if (
        MAX_RECIPES_TO_PROCESS is not None
        and processed
        >= MAX_RECIPES_TO_PROCESS
    ):
        break

    existing = row.get(
        TIME_COLUMN
    )

    if pd.notna(existing):

        existing_text = str(
            existing
        ).strip()

        if (
            existing_text
            and existing_text.lower()
            not in [
                "nan",
                "none",
                ""
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
        f"TEST RECIPE {processed}/"
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

        # ----------------------------------------------------
        # MEMORY ONLY.
        #
        # The CSV is NOT saved.
        # ----------------------------------------------------

        df.at[
            index,
            TIME_COLUMN
        ] = minutes

        print("\nRESULT")

        print(
            f"Cooking time : {minutes} minutes"
        )

        print(
            f"Source       : {source}"
        )

        print(
            f"Confidence   : {confidence}"
        )

        print(
            f"Estimated    : {is_estimated}"
        )

    else:

        failed += 1

        print(
            "\nRESULT"
        )

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

    time.sleep(
        REQUEST_DELAY
    )


# ============================================================
# FINAL SAVE CURRENTLY DISABLED
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
print("RESULTS")
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
    "All results are currently test-only."
)

print(
    f"Source CSV                 : "
    f"{CSV_FILE}"
)