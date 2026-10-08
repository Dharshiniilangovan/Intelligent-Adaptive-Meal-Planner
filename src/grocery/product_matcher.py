

import re

import unicodedata

from dataclasses import dataclass
from src.grocery.semantic_product_matcher import validate_product





@dataclass

class MatchResult:

    accepted: bool

    match_type: str

    score: float

    reason: str





def normalize_word(word: str) -> str:

    """

    Normalize common ingredient plurals.

    """



    irregular = {

        "tomatoes": "tomato",

        "potatoes": "potato",

        "leaves": "leaf",

        "loaves": "loaf",

        "berries": "berry",

        "cherries": "cherry",

    }



    if word in irregular:

        return irregular[word]



    if len(word) > 4 and word.endswith("ies"):

        return word[:-3] + "y"



    if (

        len(word) > 3

        and word.endswith("s")

        and not word.endswith(("ss", "us", "is"))

    ):

        return word[:-1]



    return word    





def clean_text(value: str) -> str:

    value = unicodedata.normalize(

        "NFKC",

        str(value or ""),

    )



    value = value.lower()



    value = re.sub(

        r"[^a-z0-9\s]",

        " ",

        value,

    )



    words = value.split()



    words = [

        normalize_word(word)

        for word in words

    ]



    return " ".join(words)





def contains_phrase(text: str, phrase: str) -> bool:

    text = f" {clean_text(text)} "

    phrase = f" {clean_text(phrase)} "

    return phrase in text





# Product types that should not be substituted for

# the requested ingredient.





# Processed products that must not be treated as

# fresh or whole fruit ingredients.



FRESH_FRUIT_INCOMPATIBLE_FORMS = {

    "gummy",

    "gummies",

    "gummi",

    "gummie",

    "supplement",

    "supplements",

    "vitamin",

    "vitamins",

    "granola",

    "cereal",

    "muesli",

    "candy",

    "candies",

    "jam",

    "jelly",

    "syrup",

    "soju",

    "vodka",

    "liqueur",

    "yogurt",

    "yoghurt",

    "ice cream",

    "chocolate",

    "cookies",

    "biscuits",

    "chips",

    "crisps",

    "juice",

    "smoothie",

    "milk",

    "flavoured",

    "flavored",

}



FRESH_FRUIT_INGREDIENTS = {

    "strawberry",

    "banana",

    "apple",

    "blueberry",

    "raspberry",

    "blackberry",

    "grape",

    "peach",

    "nectarine",

    "pear",

    "mango",

    "pineapple",

    "watermelon",

    "papaya",

    "kiwi",

    "cherry",

}





INCOMPATIBLE_PRODUCTS = {

    "milk": [

        "strawberry", "chocolate", "flavoured",

        "flavored", "condensed", "evaporated",

        "milk powder", "formula", "growing up",

        "almond milk", "soy milk", "oat milk",

        "coconut milk", "milk tea",

    ],

    "chicken": [

        "nugget", "sausage", "popcorn chicken",

        "chicken stock", "chicken broth",

        "chicken seasoning", "chicken floss",

    ],

    "tomato": [

        "ketchup", "tomato sauce", "tomato paste",

        "tomato soup", "tomato puree",

        "tomato juice",

    ],

    "potato": [

        "potato chips", "potato crisps",

        "french fries", "mashed potato mix",

    ],

    "egg": [

        "egg noodle", "egg tofu", "egg tart",

        "egg mayonnaise",

    ],

    "rice": [

        "rice noodle", "rice cracker",

        "rice flour", "rice cake",

    ],

    "lemon juice": [

        "calamansi",

        "honey lemon",

        "lemon honey",

        "honey ginger",

        "lemon drink",

        "lemon tea",

        "lemonade",

        "cordial",

        "flavoured",

        "flavored",

    ],



    "strawberry": [

        "strawberry milk",

        "flavoured milk",

        "flavored milk",

        "milk",

        "yogurt",

        "yoghurt",

        "juice",

        "drink",

        "jam",

        "jelly",

        "candy",

        "syrup",

        "ice cream",

        "dessert",

        "granola",

        "cereal",

        "muesli",

        "oat bar",

        "breakfast bar",

        "protein bar",

        "energy bar",

        "yogurt",

        "yoghurt",

        "strawberry biscuits",

        "strawberry cookies",

        "strawberry cake",

        "strawberry ice cream",

        "soju",

        "wine",

        "beer",

        "vodka",

        "liqueur",

        "cocktail",

        "alcohol",

        "liquor",

        "flavoured drink",

        "flavored drink",

        "fruit drink",

        "strawberry syrup",

        "strawberry candy",

        "strawberry jam",



    ],



    "banana": [

        "banana milk",

        "flavoured milk",

        "flavored milk",

        "milk",

        "yogurt",

        "yoghurt",

        "juice",

        "drink",

        "chips",

        "cake",

        "bread",

        "flour",

        "dessert",

    ],



    "garlic": [

        "garlic bread",

        "garlic wrap",

        "garlic & herbs wrap",

        "garlic naan",

        "garlic sauce",

        "garlic paste",

        "garlic powder",

        "garlic salt",

        "garlic seasoning",

        "garlic butter",

        "garlic mayonnaise",

        "garlic chips",

        "garlic crackers",

        "garlic spread",

        "garlic dip",

        "garlic oil",

        "chili sauce",

        "chilli sauce",

        "ginger and garlic",

        "ginger garlic sauce",

        "garlic marinade",

        "garlic dressing",

        "garlic chutney",

    ],



    "corn": [

        "corn flour",

        "cornflour",

        "corn starch",

        "cornstarch",

        "corn chips",

        "corn flakes",

        "cornflakes",

        "popcorn",

        "corn oil",

        "corn syrup",

        "corn snack",

        "corn soup",

        "corn crackers",

        "corn tortillas",

        "potato chips",

        "chips",

        "crisps",

        "crackers",

        "snack",

        "snacks",

        "roasted corn flavour",

        "roasted corn flavor",

        "corn flavoured",

        "corn flavored",



    ],



    "black beans": [

        "black eye beans",

        "black eyed beans",

        "black-eye beans",

        "black-eyed beans",

        "blackeye beans",

        "black eyed peas",

        "black-eyed peas",

        "cowpeas",

        "black bean sauce",

        "black bean paste",    

        "fermented black bean",

        "fermented black beans",

        "salted black bean",

        "salted black beans",

        "black bean seasoning",

        "black bean paste",

        "black bean sauce",



    ],









}



# These are potential substitutions, not exact matches.

SUBSTITUTIONS = {

    "fresh milk": [

        "uht milk",

        "pure milk",

        "plain milk",

        "full cream milk",

        "low fat milk",

        "hl milk",

    ],

    "brown sugar": ["raw sugar"],

    "white sugar": ["granulated sugar"],

}





def match_product(

    ingredient_name: str,

    product_title: str,

) -> MatchResult:



    ingredient = clean_text(ingredient_name)

    product = clean_text(product_title)



    if not ingredient or not product:

        return MatchResult(

            False, "rejected", 0.0, "Empty ingredient or title"

        )



    ingredient_tokens = set(ingredient.split())

    product_tokens = set(product.split())





    # ---------------------------------------------------------

    # Sugar type classification

    #

    # Generic "sugar" means ordinary white granulated

    # sugar unless the recipe specifies another type.

    # ---------------------------------------------------------



    if ingredient == "sugar":



        # Different forms that should not be treated

        # as ordinary granulated sugar.

        incompatible = [

            "icing sugar",

            "powdered sugar",

            "confectioners sugar",

            "sugar cube",

            "sugar syrup",

            "liquid sugar",

        ]



        for phrase in incompatible:

            if contains_phrase(product, phrase):

                return MatchResult(

                    False,

                    "rejected",

                    0.0,

                    f"Different sugar form: {phrase}",

                )



        # Possible substitutes.

        substitutes = [

            "brown sugar",

            "caster sugar",

            "raw sugar",

            "demerara sugar",

        ]



        for phrase in substitutes:

            if contains_phrase(product, phrase):

                return MatchResult(

                    True,

                    "substitute",

                    0.75,

                    f"Possible sugar substitute: {phrase}",

                )



        # Ordinary white or granulated sugar.

        if (

            contains_phrase(product, "white sugar")

            or contains_phrase(product, "granulated sugar")

        ):

            return MatchResult(

                True,

                "exact",

                1.0,

                "Ordinary granulated sugar",

            )



        # Generic sugar products require further

        # evidence before being accepted as exact.

        return MatchResult(

            False,

            "rejected",

            0.0,

            "Sugar type not sufficiently specified",

        )





    # ---------------------------------------------------------

    # Fresh milk vs UHT milk

    #

    # UHT milk may contain "fresh milk" in its product

    # title, but it should not be classified as exact.

    # ---------------------------------------------------------



    if (

        ingredient == "fresh milk"

        and "uht" in product_tokens

    ):

        # Reject flavoured or otherwise incompatible

        # products before accepting UHT as a substitute.

        blocked = INCOMPATIBLE_PRODUCTS.get("milk", [])



        for phrase in blocked:

            if contains_phrase(product, phrase):

                return MatchResult(

                    False,

                    "rejected",

                    0.0,

                    f"Incompatible product: {phrase}",

                )



        return MatchResult(

            True,

            "substitute",

            0.75,

            "UHT milk is a substitute for fresh milk",

        )





    # ---------------------------------------------------------

    # Fresh fruit product-category safeguard

    #

    # Reject processed products containing fruit names

    # when the recipe requests the fruit itself.

    #

    # Examples:

    # strawberry -> strawberry gummies: rejected

    # strawberry -> fresh strawberries: accepted

    # banana -> banana cereal: rejected

    # ---------------------------------------------------------



    if ingredient in FRESH_FRUIT_INGREDIENTS:



        for form in FRESH_FRUIT_INCOMPATIBLE_FORMS:



            if contains_phrase(product, form):



                return MatchResult(

                    False,

                    "rejected",

                    0.0,

                    f"Processed fruit product: {form}",

                )







    # Reject incompatible product types.

    for category, blocked_phrases in INCOMPATIBLE_PRODUCTS.items():

        if (

            category in ingredient_tokens

            or contains_phrase(ingredient, category)

        ):

            for phrase in blocked_phrases:

                if contains_phrase(product, phrase):

                    # Do not reject when the ingredient

                    # explicitly requests this product type.

                    if not contains_phrase(ingredient, phrase):

                        return MatchResult(

                            False,

                            "rejected",

                            0.0,

                            f"Incompatible product: {phrase}",

                        )



    equivalence = validate_product(ingredient_name, product_title)
    if not equivalence.accepted:
        return MatchResult(False, "rejected", 0.0, equivalence.reason)

    # Exact phrase match.

    if contains_phrase(product, ingredient):

        return MatchResult(

            True, "exact", 1.0, "Full ingredient phrase found"

        )



    # All ingredient words found.

    if ingredient_tokens.issubset(product_tokens):

        return MatchResult(

            True, "exact", 0.95, "All ingredient tokens found"

        )



    # Known substitutions.

    for substitute in SUBSTITUTIONS.get(ingredient, []):

        if contains_phrase(product, substitute):

            return MatchResult(

                True,

                "substitute",

                0.75,

                f"Possible substitute: {substitute}",

            )



    # Conservative partial match.

    overlap = len(ingredient_tokens & product_tokens)

    coverage = overlap / len(ingredient_tokens)



    if coverage >= 0.8 and len(ingredient_tokens) >= 2:

        return MatchResult(

            True,

            "partial",

            0.65,

            "Most ingredient tokens found",

        )



    return MatchResult(

        False,

        "rejected",

        0.0,

        "Insufficient ingredient relevance",

    )
