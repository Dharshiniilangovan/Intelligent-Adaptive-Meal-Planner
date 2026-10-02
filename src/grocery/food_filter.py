import re

NON_FOOD = [
    # pets
    "pet", "pets", "dog", "dogs", "cat", "cats", "puppy", "kitten", "kibble", "litter", "aquarium",
    "pedigree", "whiskas", "friskies", "purina", "iams", "cesar", "sheba", "felix", "loveabowl",
    "canin", "smartheart", "nutrience", "acana", "orijen", "kitten", "kibble",
    # appliances / kitchenware
    "cooker", "maker", "kettle", "blender", "juicer", "fryer", "oven", "microwave", "toaster",
    "machine", "appliance", "processor", "dispenser", "container", "lunchbox", "tumbler", "flask",
    "mug", "tray", "mould", "mold", "cutter", "press", "pan", "pot", "wok", "knife",
    "spatula", "storage", "scale", "steamer", "grinder",
    # household / personal care
    "detergent", "cleaner", "soap", "shampoo", "conditioner", "lotion", "wash", "tissue", "diaper",
    "wipes", "cosmetic", "skincare", "mask", "perfume", "fragrance", "candle", "bleach",
    "bath", "soak", "scent", "scented", "bubble", "body", "skin", "moisturiser", "moisturizer",
    # home / furniture
    "panel", "wall", "tile", "paint", "fabric", "curtain", "sofa", "furniture", "rug",
    # health
    "supplement", "vitamin", "vitamins", "capsule", "capsules", "tablet", "tablets", "collagen",
    # electronics / fashion / misc
    "phone", "iphone", "ipad", "macbook", "airpods", "watch", "charger", "cable", "speaker",
    "headphones", "laptop", "cover", "toy", "toys", "plush", "keychain", "sticker",
    "costume", "shirt", "book", "fake", "artificial", "replica", "seeds", "plant", "planter",
]

PROCESSED = [
    "sauce", "ketchup", "paste", "puree", "flavour", "flavor", "flavoured", "flavored", "chips",
    "crisps", "cracker", "crackers", "biscuit", "biscuits", "cookie", "cookies", "cake", "cakes",
    "candy", "chocolate", "soup", "stock", "cube", "cubes", "seasoning", "powder", "noodle",
    "noodles", "snack", "snacks", "nugget", "nuggets", "jam", "jelly", "drink", "drinks", "tea",
    "wafer", "bar", "bars", "ice cream", "yogurt", "yoghurt", "dessert", "pudding", "spread",
    "dressing", "marinade", "mix", "sausage", "sausages", "ball", "balls", "bun", "buns", "pie",
    "vinegar", "flour", "wine", "oil", "starch", "bran", "kinder", "surprise", "easter", "creme",
    "formula", "infant", "toddler", "growing",
]

# Words in recipe ingredient text that describe preparation/size, not the product itself
DESCRIPTORS = {
    "fresh", "large", "small", "medium", "big", "boneless", "skinless", "chopped", "diced", "minced",
    "sliced", "grated", "shredded", "ground", "crushed", "peeled", "deveined", "trimmed", "halved",
    "quartered", "cubed", "julienned", "finely", "thinly", "roughly", "coarsely", "lightly", "freshly",
    "organic", "raw", "cooked", "uncooked", "ripe", "lean", "extra", "virgin", "whole", "unsalted",
    "salted", "softened", "melted", "beaten", "packed", "divided", "optional", "taste", "room",
    "temperature", "cold", "warm", "hot", "dried", "rinsed", "drained", "washed", "of", "and", "or",
    "for", "a", "an", "the", "to", "about", "plus", "more", "into", "cut", "pieces", "piece",
    # portion words
    "clove", "sprig", "leaf", "leave", "stalk", "bunch", "head", "can", "tin", "slice", "pinch",
    "dash", "handful", "cup", "tbsp", "tsp", "tablespoon", "teaspoon", "g", "kg", "ml", "l", "oz", "lb",
}

# Main words too generic to match on their own ("breast" could be chicken or duck)
GENERIC_HEADS = {"breast", "thigh", "fillet", "leg", "wing", "mince", "meat", "steak", "chop",
                 "loin", "belly", "shoulder", "cheese", "milk", "oil", "sauce", "bean", "pepper"}

_TECH_SPECS = re.compile(r"\b\d+\s?(gb|tb|mah)\b|\b(5g|4g|bluetooth|wi-?fi|usb)\b", re.IGNORECASE)
_WORD = re.compile(r"[a-z]+")


def _stem(word: str) -> str:
    """Very small plural stemmer: tomatoes->tomato, eggs->egg, berries->berry, leaves->leave."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("oes"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def words(text: str) -> list[str]:
    return [_stem(w) for w in _WORD.findall(str(text).lower())]


def _core_tokens(text: str) -> list[str]:
    """Raw words of the ingredient with amounts, units and prep words removed (not stemmed)."""
    text = str(text).lower()
    text = re.sub(r"\([^)]*\)", " ", text)       # drop "(about 500g)"
    text = text.split(",")[0]                     # drop ", diced"
    raw = _WORD.findall(text)
    core = [w for w in raw if _stem(w) not in DESCRIPTORS]
    return core or raw


def clean_ingredient(text: str) -> list[str]:
    """'2 boneless skinless chicken breasts, diced (about 500g)' -> ['chicken', 'breast']"""
    return [_stem(w) for w in _core_tokens(text)]


_NON_FOOD_STEMS = {_stem(w) for w in NON_FOOD}
_PROCESSED_SINGLE = {_stem(w) for w in PROCESSED if " " not in w}
_PROCESSED_PHRASES = [p for p in PROCESSED if " " in p]


def check_match(ingredient: str, title: str) -> tuple[bool, str]:
    """Returns (ok, quality_or_reason): (True, 'exact'), (True, 'approximate') or (False, reason)."""
    core = clean_ingredient(ingredient)
    core_set = set(core)
    t_set = set(words(title))

    bad = (t_set & _NON_FOOD_STEMS) - core_set
    if bad:
        return False, f"non-food word: {sorted(bad)[0]}"
    if _TECH_SPECS.search(title):
        return False, "electronics spec in title"
    processed = (t_set & _PROCESSED_SINGLE) - core_set
    phrases = [p for p in _PROCESSED_PHRASES if p in title.lower() and p not in " ".join(core)]
    if processed or phrases:
        return False, f"processed product: {(sorted(processed) or phrases)[0]}"

    if core_set <= t_set:
        return True, "exact"
    head = core[-1]
    if head in t_set:
        if head in GENERIC_HEADS and len(core) > 1 and core[-2] not in t_set:
            return False, f"'{head}' matched but not '{core[-2]}'"
        return True, "approximate"
    return False, f"main ingredient word missing: {head}"


def search_queries(ingredient: str) -> list[str]:
    """
    Generate multiple search queries so that a product can still be found
    when the exact ingredient name is poorly indexed.

    The first query is always the exact/core ingredient.
    Additional queries provide supermarket/product context.
    """
    tokens = _core_tokens(ingredient)

    if not tokens:
        return []

    base = " ".join(tokens)

    queries = [
        base,
        f"{base} FairPrice Singapore",
        # f"{base} grocery Singapore",
    ]

    # For multi-word ingredients, also search using the main food head.
    if len(tokens) > 1:
        stemmed = [_stem(t) for t in tokens]

        if stemmed[-1] in GENERIC_HEADS and len(tokens) > 1:
            head = tokens[-2]
        else:
            head = tokens[-1]

        if head:
            queries.append(f"{head} FairPrice Singapore")

    # Remove duplicates while preserving order.
    return list(dict.fromkeys(queries))