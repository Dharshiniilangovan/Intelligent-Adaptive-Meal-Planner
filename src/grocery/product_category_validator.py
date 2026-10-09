
import re


NON_FOOD_CATEGORIES = {
    "laundry",
    "sanitizer",
    "detergent",
    "dishwashing",
    "dishwasher",
    "floor cleaner",
    "toilet cleaner",
    "air freshener",
    "fabric softener",
    "shampoo",
    "conditioner",
    "toothpaste",
    "mouthwash",
    "body wash",
    "hand wash",
    "soap",
    "disinfectant",
    "deodorant",
    "perfume",
    "insect repellent",
    "cleaning spray",
    "surface cleaner",
    "bleach",
}


def is_non_food_product(
    title: str,
    url: str = "",
) -> bool:
    """
    Reject clearly non-food retail products.

    Checks product title and URL independently
    of the requested ingredient.
    """

    text = f"{title} {url}".lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    text = f" {text} "

    for category in NON_FOOD_CATEGORIES:
        normalized = f" {category} "

        if normalized in text:
            return True

    return False
