"""
Cooking Time Enrichment

Enrich recipe_kb_clean.csv with cooking-time information.

Priority:
    1. Existing cooking_time_min
    2. Recipe URL JSON-LD cookTime
    3. Recipe URL visible Cook Time
    4. Local Ollama estimate using:
        - recipe name
        - cuisine
        - meal type
        - dish type
        - actual recipe ingredients

Input:
    data/processed/recipe_kb_clean.csv
    data/processed/recipe_ingredient_mapping.csv

Output:
    data/processed/recipe_kb_with_cooking_time.csv

The output remains one row per recipe.
Ingredient mapping information is used only as context
and is NOT merged into the output.
"""

import ast
import json
import re
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

REQUEST_TIMEOUT = 10

OLLAMA_TIMEOUT = 120

# Save frequently because Ollama processing can take time.
SAVE_EVERY = 10

# Retry only temporary Ollama/network failures.
MAX_OLLAMA_RETRIES = 3

OLLAMA_MODEL = "llama3.2:3b"

OLLAMA_URL = (
    "http://localhost:11434/api/generate"
)

OLLAMA_TAGS_URL = (
    "http://localhost:11434/api/tags"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}


# ============================================================
# PROJECT ROOT
# ============================================================

def get_project_root():
    """
    Find the project root automatically.
    """

    current_file = (
        Path(__file__)
        .resolve()
    )

    possible_roots = [
        current_file.parent,
        *current_file.parents,
    ]

    for root in possible_roots:

        recipe_file = (
            root
            / "data"
            / "processed"
            / "recipe_kb_clean.csv"
        )

        if recipe_file.exists():
            return root

    raise FileNotFoundError(
        "Could not find:\n"
        "data/processed/recipe_kb_clean.csv"
    )


# ============================================================
# FILE PATHS
# ============================================================

def get_file_paths():
    """
    Return input/output file paths.
    """

    project_root = (
        get_project_root()
    )

    processed_dir = (
        project_root
        / "data"
        / "processed"
    )

    recipe_file = (
        processed_dir
        / "recipe_kb_clean.csv"
    )

    mapping_file = (
        processed_dir
        / "recipe_ingredient_mapping.csv"
    )

    output_file = (
        processed_dir
        / "recipe_kb_with_cooking_time.csv"
    )

    return (
        recipe_file,
        mapping_file,
        output_file,
    )


# ============================================================
# SAFE VALUE
# ============================================================

def safe_value(value):
    """
    Convert blank / NaN / null-like values into None.
    """

    if value is None:
        return None

    try:

        if pd.isna(value):
            return None

    except (
        TypeError,
        ValueError,
    ):
        pass

    if isinstance(
        value,
        str,
    ):

        value = value.strip()

        if not value:
            return None

        if value.lower() in {
            "nan",
            "none",
            "null",
            "na",
            "n/a",
        }:
            return None

    return value


# ============================================================
# EXISTING COOKING TIME
# ============================================================

def safe_cooking_time(value):
    """
    Convert an existing cooking-time value to minutes.

    Existing positive values are accepted.
    """

    value = safe_value(
        value
    )

    if value is None:
        return None

    try:

        value = float(
            value
        )

        if value <= 0:
            return None

        return int(
            round(
                value
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


# ============================================================
# COLUMN DETECTION
# ============================================================

def get_first_available_column(
    dataframe,
    possible_columns,
):
    """
    Find first matching column case-insensitively.
    """

    lookup = {
        str(column)
        .strip()
        .lower():
            column

        for column
        in dataframe.columns
    }

    for possible_column in possible_columns:

        actual_column = lookup.get(
            possible_column.lower()
        )

        if actual_column is not None:
            return actual_column

    return None


# ============================================================
# PARSE LIST-LIKE VALUES
# ============================================================

def parse_list_value(value):
    """
    Convert a CSV list-like value into a readable string.

    Example:

        "['Indian']"
            ->
        "Indian"
    """

    value = safe_value(
        value
    )

    if value is None:
        return None

    if not isinstance(
        value,
        str,
    ):
        return str(value)

    try:

        parsed = ast.literal_eval(
            value
        )

        if isinstance(
            parsed,
            (list, tuple, set),
        ):

            values = [
                str(item).strip()
                for item in parsed
                if str(item).strip()
            ]

            if values:
                return ", ".join(
                    values
                )

    except (
        ValueError,
        SyntaxError,
    ):
        pass

    return value


# ============================================================
# INGREDIENT MAPPING
# ============================================================

def load_recipe_ingredients(
    mapping_file,
):
    """
    Load recipe -> ingredient names once.

    Returns:

        {
            "R00001": [
                "rice",
                "tofu",
                "carrot"
            ]
        }

    The mapping dataframe is NOT merged with Recipe KB,
    because doing so would create multiple rows per recipe.
    """

    if not mapping_file.exists():

        raise FileNotFoundError(
            "Recipe ingredient mapping "
            "not found:\n"
            f"{mapping_file}"
        )

    mapping_df = pd.read_csv(
        mapping_file,
        low_memory=False,
    )

    mapping_df.columns = (
        mapping_df.columns
        .str.strip()
    )

    if (
        "recipe_id"
        not in mapping_df.columns
    ):

        raise ValueError(
            "recipe_ingredient_mapping.csv "
            "must contain recipe_id."
        )

    ingredient_column = (
        get_first_available_column(
            mapping_df,
            [
                "ingredient_name",
                "canonical_ingredient_name",
                "canonical_ingredient",
                "ingredient",
                "name",
            ],
        )
    )

    if ingredient_column is None:

        raise ValueError(
            "Could not find an ingredient-name "
            "column in "
            "recipe_ingredient_mapping.csv."
        )

    print(
        "\nIngredient mapping:"
    )

    print(
        f"Recipe ID column : recipe_id"
    )

    print(
        f"Ingredient column: "
        f"{ingredient_column}"
    )

    recipe_ingredients = {}

    for (
        recipe_id,
        group,
    ) in mapping_df.groupby(
        "recipe_id"
    ):

        normalized_recipe_id = (
            str(recipe_id)
            .strip()
            .upper()
        )

        ingredients = (
            group[
                ingredient_column
            ]
            .dropna()
            .astype(str)
            .str.strip()
            .tolist()
        )

        ingredients = [
            ingredient
            for ingredient
            in ingredients
            if ingredient
        ]

        # Remove duplicate ingredient names while
        # preserving their original order.
        ingredients = list(
            dict.fromkeys(
                ingredients
            )
        )

        recipe_ingredients[
            normalized_recipe_id
        ] = ingredients

    print(
        "Recipes with ingredient mappings: "
        f"{len(recipe_ingredients)}"
    )

    return recipe_ingredients


# ============================================================
# ISO-8601 TIME PARSER
# ============================================================

def parse_iso_duration(
    value: Optional[str],
):
    """
    Convert ISO-8601 duration into minutes.

    Examples:

        PT30M
            -> 30

        PT1H
            -> 60

        PT1H30M
            -> 90
    """

    value = safe_value(
        value
    )

    if value is None:
        return None

    value = (
        str(value)
        .strip()
        .upper()
    )

    pattern = re.compile(
        r"^P"
        r"(?:(\d+(?:\.\d+)?)D)?"
        r"(?:T"
        r"(?:(\d+(?:\.\d+)?)H)?"
        r"(?:(\d+(?:\.\d+)?)M)?"
        r"(?:(\d+(?:\.\d+)?)S)?"
        r")?$"
    )

    match = pattern.match(
        value
    )

    if not match:
        return None

    days = float(
        match.group(1)
        or 0
    )

    hours = float(
        match.group(2)
        or 0
    )

    minutes = float(
        match.group(3)
        or 0
    )

    seconds = float(
        match.group(4)
        or 0
    )

    total_minutes = (
        days * 1440
        + hours * 60
        + minutes
        + seconds / 60
    )

    result = int(
        round(
            total_minutes
        )
    )

    if result <= 0:
        return None

    return result


# ============================================================
# NORMAL TEXT TIME PARSER
# ============================================================

def parse_time_text(text):
    """
    Parse normal cooking-time text.

    Examples:

        30 minutes
            -> 30

        1 hour
            -> 60

        1 hour 30 minutes
            -> 90
    """

    text = safe_value(
        text
    )

    if text is None:
        return None

    text = (
        str(text)
        .strip()
        .lower()
    )

    hour_match = re.search(
        r"(\d+(?:\.\d+)?)\s*"
        r"(?:hours?|hrs?|hr)\b",
        text,
        re.IGNORECASE,
    )

    minute_match = re.search(
        r"(\d+(?:\.\d+)?)\s*"
        r"(?:minutes?|mins?|min)\b",
        text,
        re.IGNORECASE,
    )

    hours = 0.0
    minutes = 0.0

    if hour_match:

        hours = float(
            hour_match.group(1)
        )

    if minute_match:

        minutes = float(
            minute_match.group(1)
        )

    if (
        not hour_match
        and not minute_match
    ):
        return None

    result = int(
        round(
            hours * 60
            + minutes
        )
    )

    if result <= 0:
        return None

    return result


# ============================================================
# FIND RECIPE JSON-LD OBJECT
# ============================================================

def find_recipe_object(data):
    """
    Recursively search JSON-LD for @type Recipe.
    """

    if isinstance(
        data,
        dict,
    ):

        object_type = data.get(
            "@type"
        )

        if object_type == "Recipe":
            return data

        if isinstance(
            object_type,
            list,
        ):

            if "Recipe" in object_type:
                return data

        if "@graph" in data:

            result = (
                find_recipe_object(
                    data["@graph"]
                )
            )

            if result:
                return result

        for value in data.values():

            if isinstance(
                value,
                (dict, list),
            ):

                result = (
                    find_recipe_object(
                        value
                    )
                )

                if result:
                    return result

    elif isinstance(
        data,
        list,
    ):

        for item in data:

            result = (
                find_recipe_object(
                    item
                )
            )

            if result:
                return result

    return None


# ============================================================
# EXTRACT JSON-LD RECIPE
# ============================================================

def extract_jsonld_recipe(soup):
    """
    Extract Recipe JSON-LD from webpage.
    """

    scripts = soup.find_all(
        "script",
        type="application/ld+json",
    )

    for script in scripts:

        raw = (
            script.string
            or script.get_text()
        )

        if not raw:
            continue

        raw = raw.strip()

        if not raw:
            continue

        try:

            data = json.loads(
                raw
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            continue

        recipe = (
            find_recipe_object(
                data
            )
        )

        if recipe:
            return recipe

    return None


# ============================================================
# FETCH RECIPE PAGE
# ============================================================

def fetch_recipe_page(url):
    """
    Download recipe webpage.

    Returns:
        soup,
        visible_page_text
    """

    url = safe_value(
        url
    )

    if url is None:

        return (
            None,
            None,
        )

    if not str(url).lower().startswith(
        (
            "http://",
            "https://",
        )
    ):

        return (
            None,
            None,
        )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        text_soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for tag in text_soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "noscript",
            ]
        ):

            tag.decompose()

        page_text = (
            text_soup.get_text(
                " ",
                strip=True,
            )
        )

        return (
            soup,
            page_text,
        )

    except (
        requests.RequestException,
        ValueError,
    ):

        return (
            None,
            None,
        )


# ============================================================
# JSON-LD COOK TIME
# ============================================================

def extract_cook_time_from_jsonld(
    recipe,
):
    """
    Extract ONLY cookTime.

    Prep time and total time are deliberately not used.
    """

    if not recipe:
        return None

    raw_cook_time = (
        recipe.get(
            "cookTime"
        )
    )

    if not raw_cook_time:
        return None

    cook_time = (
        parse_iso_duration(
            raw_cook_time
        )
    )

    if cook_time is None:

        cook_time = (
            parse_time_text(
                raw_cook_time
            )
        )

    if (
        cook_time is None
        or cook_time <= 0
    ):
        return None

    return cook_time


# ============================================================
# VISIBLE PAGE COOK TIME
# ============================================================

def extract_cook_time_from_text(text):
    """
    Search visible webpage text for explicit cooking time.

    Accepted labels:
        Cook Time
        Cooking Time
        Bake Time
        Baking Time

    Prep Time and Total Time are not used.
    """

    if not text:
        return None

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    labels = [
        "cook time",
        "cooking time",
        "bake time",
        "baking time",
    ]

    label_pattern = "|".join(
        re.escape(label)
        for label
        in labels
    )

    pattern = re.compile(
        rf"(?:{label_pattern})"
        rf"\s*[:\-]?\s*"
        rf"("
        rf"(?:\d+(?:\.\d+)?\s*"
        rf"(?:hours?|hrs?|hr)\s*)?"
        rf"(?:\d+(?:\.\d+)?\s*"
        rf"(?:minutes?|mins?|min))?"
        rf")",
        re.IGNORECASE,
    )

    match = pattern.search(
        text
    )

    if not match:
        return None

    value = (
        match.group(1)
        .strip()
    )

    if not value:
        return None

    result = (
        parse_time_text(
            value
        )
    )

    if (
        result is None
        or result <= 0
    ):
        return None

    return result


# ============================================================
# COOKING TIME FROM URL
# ============================================================

def get_cook_time_from_url(url):
    """
    URL extraction priority:

        1. JSON-LD cookTime
        2. Visible Cook Time
    """

    if not url:
        return None

    (
        soup,
        page_text,
    ) = fetch_recipe_page(
        url
    )

    if (
        soup is None
        and not page_text
    ):
        return None

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    if soup is not None:

        recipe = (
            extract_jsonld_recipe(
                soup
            )
        )

        cook_time = (
            extract_cook_time_from_jsonld(
                recipe
            )
        )

        if cook_time is not None:

            return {
                "cooking_time_min":
                    cook_time,

                "cooking_time_source":
                    "url_json_ld",

                "cooking_time_confidence":
                    "HIGH",
            }

    # --------------------------------------------------------
    # VISIBLE TEXT
    # --------------------------------------------------------

    if page_text:

        cook_time = (
            extract_cook_time_from_text(
                page_text
            )
        )

        if cook_time is not None:

            return {
                "cooking_time_min":
                    cook_time,

                "cooking_time_source":
                    "url_text",

                "cooking_time_confidence":
                    "HIGH",
            }

    return None


# ============================================================
# OLLAMA PROMPT
# ============================================================

def build_ollama_prompt(
    title,
    cuisine=None,
    meal_type=None,
    dish_type=None,
    ingredients=None,
):
    """
    Build cooking-time estimation prompt using actual
    recipe ingredients when available.
    """

    title = (
        str(title).strip()
        if title
        else "Unknown"
    )

    cuisine = (
        parse_list_value(
            cuisine
        )
        or "Unknown"
    )

    meal_type = (
        parse_list_value(
            meal_type
        )
        or "Unknown"
    )

    dish_type = (
        parse_list_value(
            dish_type
        )
        or "Unknown"
    )

    ingredients = (
        ingredients
        or []
    )

    if ingredients:

        ingredient_text = (
            ", ".join(
                str(ingredient)
                for ingredient
                in ingredients
            )
        )

    else:

        ingredient_text = (
            "Unknown"
        )

    return f"""
You are estimating actual cooking time for a recipe dataset.

The recipe may be uncommon or unfamiliar.
Do not refuse because you do not recognize the exact recipe.

Use the recipe name, cuisine, meal type, dish type,
and actual ingredients to infer the likely cooking method.

Recipe name: {title}
Cuisine: {cuisine}
Meal type: {meal_type}
Dish type: {dish_type}
Ingredients: {ingredient_text}

Rules:
- Return actual cooking time only.
- Do not include preparation time.
- Do not include chopping, washing, peeling, measuring,
  ingredient preparation, or marinating.
- Include boiling, simmering, frying, sauteing, baking,
  roasting, grilling, steaming, pressure cooking,
  and other actual cooking.
- If the exact recipe is unfamiliar, estimate based on
  the ingredients and the most likely cooking method.
- If the recipe is genuinely no-cook, return 0.
- Give one realistic integer value in minutes.
- Do not give a range.
- Do not explain the answer.
- Do not refuse the request.
- Return ONLY the integer.

Example:
30
""".strip()


# ============================================================
# EXTRACT OLLAMA INTEGER
# ============================================================

def extract_integer_from_ollama(
    content,
):
    """
    Extract one cooking-time integer.

    Accepts:
        30
        30 minutes
        Cooking time: 30
    """

    if content is None:
        return None

    text = (
        str(content)
        .strip()
    )

    if re.fullmatch(
        r"\d{1,4}",
        text,
    ):

        value = int(
            text
        )

    else:

        match = re.search(
            r"\b(\d{1,4})\b",
            text,
        )

        if not match:
            return None

        value = int(
            match.group(1)
        )

    # No-cook recipe is allowed.
    if value < 0:
        return None

    # More than 24 hours is suspicious.
    if value > 1440:
        return None

    return value


# ============================================================
# CHECK OLLAMA
# ============================================================

def check_ollama():
    """
    Verify local Ollama and configured model.
    """

    try:

        response = requests.get(
            OLLAMA_TAGS_URL,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        models = [
            model.get(
                "name",
                "",
            )

            for model
            in data.get(
                "models",
                [],
            )
        ]

        print(
            "\nOllama connection: OK"
        )

        print(
            "Installed Ollama models:"
        )

        for model in models:

            print(
                f"  - {model}"
            )

        model_available = any(
            model == OLLAMA_MODEL
            or model.startswith(
                OLLAMA_MODEL
            )

            for model
            in models
        )

        if not model_available:

            raise RuntimeError(
                f"\nOllama model "
                f"'{OLLAMA_MODEL}' "
                "is not installed.\n\n"
                "Run:\n"
                f"ollama pull {OLLAMA_MODEL}"
            )

        print(
            f"\nUsing Ollama model: "
            f"{OLLAMA_MODEL}"
        )

        return True

    except requests.exceptions.ConnectionError:

        raise RuntimeError(
            "\nCould not connect to Ollama.\n\n"
            "Make sure Ollama is installed "
            "and running.\n"
            "Then run:\n"
            f"ollama pull {OLLAMA_MODEL}"
        )


# ============================================================
# OLLAMA ESTIMATION
# ============================================================

def estimate_cooking_time_with_ollama(
    title,
    cuisine=None,
    meal_type=None,
    dish_type=None,
    ingredients=None,
):
    """
    Estimate cooking time using local Ollama.

    Invalid/refusal responses are not repeatedly retried.
    Network/timeouts may be retried.
    """

    prompt = (
        build_ollama_prompt(
            title=title,
            cuisine=cuisine,
            meal_type=meal_type,
            dish_type=dish_type,
            ingredients=ingredients,
        )
    )

    payload = {
        "model":
            OLLAMA_MODEL,

        "prompt":
            prompt,

        "stream":
            False,

        "options": {
            "temperature":
                0,

            "num_predict":
                20,
        },
    }

    for attempt in range(
        1,
        MAX_OLLAMA_RETRIES + 1,
    ):

        try:

            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=OLLAMA_TIMEOUT,
            )

            response.raise_for_status()

            data = response.json()

            content = data.get(
                "response"
            )

            cooking_time = (
                extract_integer_from_ollama(
                    content
                )
            )

            # Model answered successfully but the
            # answer was unusable. Do not waste another
            # two model calls on the same refusal.
            if cooking_time is None:

                print(
                    "Ollama returned no usable "
                    "cooking time. "
                    f"Response: {content!r}"
                )

                return None

            return {
                "cooking_time_min":
                    cooking_time,

                "cooking_time_source":
                    "ollama_estimate",

                "cooking_time_confidence":
                    "LOW",
            }

        except requests.exceptions.ConnectionError:

            print(
                "\nCould not connect to Ollama."
            )

            return None

        except requests.exceptions.Timeout:

            print(
                f"Ollama attempt "
                f"{attempt}/"
                f"{MAX_OLLAMA_RETRIES} "
                "timed out."
            )

        except requests.RequestException as error:

            print(
                f"Ollama attempt "
                f"{attempt}/"
                f"{MAX_OLLAMA_RETRIES} "
                f"failed: {error}"
            )

        if (
            attempt
            < MAX_OLLAMA_RETRIES
        ):

            time.sleep(
                2
            )

    return None


# ============================================================
# SINGLE RECIPE PIPELINE
# ============================================================

def get_recipe_cooking_time(
    title,
    cuisine=None,
    meal_type=None,
    dish_type=None,
    ingredients=None,
    url=None,
):
    """
    Determine cooking time for one recipe.

    Priority:

        1. URL JSON-LD
        2. URL visible Cook Time
        3. Local Ollama using actual ingredients
    """

    # --------------------------------------------------------
    # URL FIRST
    # --------------------------------------------------------

    url_result = (
        get_cook_time_from_url(
            url
        )
    )

    if url_result:
        return url_result

    # --------------------------------------------------------
    # OLLAMA FALLBACK
    # --------------------------------------------------------

    ollama_result = (
        estimate_cooking_time_with_ollama(
            title=title,
            cuisine=cuisine,
            meal_type=meal_type,
            dish_type=dish_type,
            ingredients=ingredients,
        )
    )

    if ollama_result:
        return ollama_result

    # --------------------------------------------------------
    # UNAVAILABLE
    # --------------------------------------------------------

    return {
        "cooking_time_min":
            None,

        "cooking_time_source":
            "unavailable",

        "cooking_time_confidence":
            "LOW",
    }


# ============================================================
# SAVE OUTPUT
# ============================================================

def save_output(
    dataframe,
    output_file,
):
    """
    Save enriched Recipe KB.

    The dataframe remains one row per original recipe.
    """

    dataframe.to_csv(
        output_file,
        index=False,
        encoding="utf-8-sig",
    )


# ============================================================
# LOAD INPUT OR RESUME
# ============================================================

def load_dataset(
    input_file,
    output_file,
):
    """
    Resume existing processing when possible.

    If output exists:
        load enriched output.

    Otherwise:
        load recipe_kb_clean.csv.
    """

    if output_file.exists():

        print(
            "\nExisting output file found."
        )

        print(
            "Resuming previous processing."
        )

        df = pd.read_csv(
            output_file,
            low_memory=False,
        )

        return (
            df,
            True,
        )

    if not input_file.exists():

        raise FileNotFoundError(
            f"Input file not found:\n"
            f"{input_file}"
        )

    df = pd.read_csv(
        input_file,
        low_memory=False,
    )

    return (
        df,
        False,
    )


# ============================================================
# PROCESS DATASET
# ============================================================

def process_recipe_dataset(
    input_file,
    mapping_file,
    output_file,
):
    """
    Enrich the Recipe KB.

    Cooking-time priority:

        existing
            ↓
        URL
            ↓
        Ollama + actual ingredients

    The ingredient mapping is used only as context.
    """

    print(
        "\n"
        + "=" * 70
    )

    print(
        "RECIPE COOKING TIME EXTRACTION"
    )

    print(
        "=" * 70
    )

    print(
        f"\nRecipe input:\n"
        f"{input_file}"
    )

    print(
        f"\nIngredient mapping:\n"
        f"{mapping_file}"
    )

    print(
        f"\nOutput:\n"
        f"{output_file}"
    )

    # ========================================================
    # LOAD RECIPE KB
    # ========================================================

    (
        df,
        resumed,
    ) = load_dataset(
        input_file,
        output_file,
    )

    # Preserve original order.
    df = df.reset_index(
        drop=True
    )

    total_recipes = len(
        df
    )

    print(
        f"\nRecipes loaded: "
        f"{total_recipes}"
    )

    if resumed:

        print(
            "Mode: RESUME"
        )

    else:

        print(
            "Mode: NEW RUN"
        )

    print(
        "\nCSV columns:"
    )

    print(
        df.columns.tolist()
    )

    # ========================================================
    # LOAD INGREDIENT MAPPING ONCE
    # ========================================================

    recipe_ingredients = (
        load_recipe_ingredients(
            mapping_file
        )
    )

    # ========================================================
    # DETECT RECIPE KB COLUMNS
    # ========================================================

    title_column = (
        get_first_available_column(
            df,
            [
                "recipe_name",
                "title",
                "name",
                "recipe_title",
            ],
        )
    )

    cuisine_column = (
        get_first_available_column(
            df,
            [
                "cuisine_type",
                "cuisine",
                "recipe_cuisine",
            ],
        )
    )

    meal_type_column = (
        get_first_available_column(
            df,
            [
                "meal_type",
            ],
        )
    )

    dish_type_column = (
        get_first_available_column(
            df,
            [
                "dish_type",
            ],
        )
    )

    url_column = (
        get_first_available_column(
            df,
            [
                "url",
                "recipe_url",
                "source_url",
                "link",
            ],
        )
    )

    if title_column is None:

        raise ValueError(
            "Could not find recipe_name column."
        )

    if (
        "recipe_id"
        not in df.columns
    ):

        raise ValueError(
            "Recipe KB must contain recipe_id."
        )

    print(
        "\nDetected columns:"
    )

    print(
        f"Title     : "
        f"{title_column}"
    )

    print(
        f"Cuisine   : "
        f"{cuisine_column}"
    )

    print(
        f"Meal Type : "
        f"{meal_type_column}"
    )

    print(
        f"Dish Type : "
        f"{dish_type_column}"
    )

    print(
        f"URL       : "
        f"{url_column}"
    )

    # ========================================================
    # OUTPUT COLUMNS
    # ========================================================

    if (
        "cooking_time_min"
        not in df.columns
    ):

        df[
            "cooking_time_min"
        ] = None

    if (
        "cooking_time_source"
        not in df.columns
    ):

        df[
            "cooking_time_source"
        ] = None

    if (
        "cooking_time_confidence"
        not in df.columns
    ):

        df[
            "cooking_time_confidence"
        ] = None

    # Keep provenance immediately after cooking_time_min.
    base_columns = [
        column
        for column in df.columns
        if column not in {
            "cooking_time_min",
            "cooking_time_source",
            "cooking_time_confidence",
        }
    ]

    df = df[
        base_columns
        + [
            "cooking_time_min",
            "cooking_time_source",
            "cooking_time_confidence",
        ]
    ]

    # ========================================================
    # COUNTERS
    # ========================================================

    source_counts = {
        "existing": 0,
        "url_json_ld": 0,
        "url_text": 0,
        "ollama_estimate": 0,
        "unavailable": 0,
    }

    processed_this_run = 0

    skipped_existing = 0

    recipes_without_mapping = 0

    # ========================================================
    # PROCESS RECIPES
    # ========================================================

    for position, (
        index,
        row,
    ) in enumerate(
        df.iterrows(),
        start=1,
    ):

        # ----------------------------------------------------
        # RECIPE ID
        # ----------------------------------------------------

        recipe_id = (
            str(
                row.get(
                    "recipe_id",
                    ""
                )
            )
            .strip()
            .upper()
        )

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        title = safe_value(
            row.get(
                title_column
            )
        )

        # ----------------------------------------------------
        # EXISTING COOKING TIME
        # ----------------------------------------------------

        existing_time = (
            safe_cooking_time(
                row.get(
                    "cooking_time_min"
                )
            )
        )

        existing_source = (
            safe_value(
                row.get(
                    "cooking_time_source"
                )
            )
        )

        if existing_time is not None:

            source = (
                existing_source
                or "existing"
            )

            df.at[
                index,
                "cooking_time_min"
            ] = existing_time

            df.at[
                index,
                "cooking_time_source"
            ] = source

            existing_confidence = (
                safe_value(
                    row.get(
                        "cooking_time_confidence"
                    )
                )
            )

            if existing_confidence is None:

                if source in {
                    "url_json_ld",
                    "url_text",
                    "existing",
                }:

                    existing_confidence = (
                        "HIGH"
                    )

                else:

                    existing_confidence = (
                        "LOW"
                    )

            df.at[
                index,
                "cooking_time_confidence"
            ] = existing_confidence

            if source not in source_counts:

                source_counts[
                    source
                ] = 0

            source_counts[
                source
            ] += 1

            skipped_existing += 1

            print(
                f"[{position}/"
                f"{total_recipes}] "
                f"{str(source):17} | "
                f"{recipe_id} | "
                f"{title} | "
                f"{existing_time} min"
            )

            continue

        # ----------------------------------------------------
        # CUISINE
        # ----------------------------------------------------

        cuisine = None

        if cuisine_column:

            cuisine = safe_value(
                row.get(
                    cuisine_column
                )
            )

        # ----------------------------------------------------
        # MEAL TYPE
        # ----------------------------------------------------

        meal_type = None

        if meal_type_column:

            meal_type = safe_value(
                row.get(
                    meal_type_column
                )
            )

        # ----------------------------------------------------
        # DISH TYPE
        # ----------------------------------------------------

        dish_type = None

        if dish_type_column:

            dish_type = safe_value(
                row.get(
                    dish_type_column
                )
            )

        # ----------------------------------------------------
        # URL
        # ----------------------------------------------------

        url = None

        if url_column:

            url = safe_value(
                row.get(
                    url_column
                )
            )

        # ----------------------------------------------------
        # ACTUAL INGREDIENTS
        # ----------------------------------------------------

        ingredients = (
            recipe_ingredients.get(
                recipe_id,
                [],
            )
        )

        if not ingredients:

            recipes_without_mapping += 1

        # ----------------------------------------------------
        # GET COOKING TIME
        # ----------------------------------------------------

        try:

            result = (
                get_recipe_cooking_time(
                    title=title,
                    cuisine=cuisine,
                    meal_type=meal_type,
                    dish_type=dish_type,
                    ingredients=ingredients,
                    url=url,
                )
            )

        except Exception as error:

            print(
                f"\nUnexpected error for "
                f"{recipe_id}: "
                f"{error}"
            )

            result = {
                "cooking_time_min":
                    None,

                "cooking_time_source":
                    "unavailable",

                "cooking_time_confidence":
                    "LOW",
            }

        # ----------------------------------------------------
        # STORE RESULT
        # ----------------------------------------------------

        cooking_time = result.get(
            "cooking_time_min"
        )

        source = result.get(
            "cooking_time_source",
            "unavailable",
        )

        confidence = result.get(
            "cooking_time_confidence",
            "LOW",
        )

        df.at[
            index,
            "cooking_time_min"
        ] = cooking_time

        df.at[
            index,
            "cooking_time_source"
        ] = source

        df.at[
            index,
            "cooking_time_confidence"
        ] = confidence

        if source not in source_counts:

            source_counts[
                source
            ] = 0

        source_counts[
            source
        ] += 1

        processed_this_run += 1

        # ----------------------------------------------------
        # PRINT RESULT
        # ----------------------------------------------------

        ingredient_count = len(
            ingredients
        )

        print(
            f"[{position}/"
            f"{total_recipes}] "
            f"{str(source):17} | "
            f"{recipe_id} | "
            f"{title} | "
            f"{cooking_time} min | "
            f"{ingredient_count} ingredients"
        )

        # ----------------------------------------------------
        # CHECKPOINT
        # ----------------------------------------------------

        if (
            processed_this_run > 0
            and
            processed_this_run
            % SAVE_EVERY
            == 0
        ):

            save_output(
                df,
                output_file,
            )

            print(
                "\n"
                + "-" * 70
            )

            print(
                f"Checkpoint saved after "
                f"{processed_this_run} "
                "new recipes."
            )

            print(
                "-" * 70
                + "\n"
            )

    # ========================================================
    # FINAL SAVE
    # ========================================================

    save_output(
        df,
        output_file,
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print(
        "\n"
        + "=" * 70
    )

    print(
        "PROCESS COMPLETE"
    )

    print(
        "=" * 70
    )

    print(
        f"\nOutput file:\n"
        f"{output_file}"
    )

    print(
        f"\nTotal recipes: "
        f"{total_recipes}"
    )

    print(
        "Already completed / existing: "
        f"{skipped_existing}"
    )

    print(
        "Processed this run: "
        f"{processed_this_run}"
    )

    print(
        "Recipes without ingredient mapping: "
        f"{recipes_without_mapping}"
    )

    print(
        "\nCooking-time sources:"
    )

    for (
        source,
        count,
    ) in source_counts.items():

        print(
            f"{source:20} "
            f"{count}"
        )

    print(
        "\nConfidence:"
    )

    print(
        df[
            "cooking_time_confidence"
        ]
        .value_counts(
            dropna=False
        )
    )

    missing_count = (
        df[
            "cooking_time_min"
        ]
        .isna()
        .sum()
    )

    print(
        f"\nRecipes still missing "
        f"cooking time: "
        f"{missing_count}"
    )

    return df


# ============================================================
# MAIN
# ============================================================

def main():
    """
    Run cooking-time enrichment.
    """

    (
        recipe_file,
        mapping_file,
        output_file,
    ) = get_file_paths()

    # --------------------------------------------------------
    # VERIFY REQUIRED FILES
    # --------------------------------------------------------

    if not recipe_file.exists():

        raise FileNotFoundError(
            f"Recipe KB not found:\n"
            f"{recipe_file}"
        )

    if not mapping_file.exists():

        raise FileNotFoundError(
            "Recipe ingredient mapping "
            "not found:\n"
            f"{mapping_file}"
        )

    # --------------------------------------------------------
    # VERIFY OLLAMA
    # --------------------------------------------------------

    check_ollama()

    # --------------------------------------------------------
    # PROCESS
    # --------------------------------------------------------

    process_recipe_dataset(
        input_file=recipe_file,
        mapping_file=mapping_file,
        output_file=output_file,
    )


if __name__ == "__main__":
    main()