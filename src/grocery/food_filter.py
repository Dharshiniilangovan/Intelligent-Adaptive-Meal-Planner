"""Ingredient normalization, safe FairPrice queries, and product relevance checks."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import unquote, urlparse

_WORD = re.compile(r"[a-z]+")

DESCRIPTORS = set('''fresh large small medium big boneless skinless chopped diced minced sliced grated shredded ground crushed peeled deveined trimmed halved quartered cubed julienned finely thinly roughly coarsely lightly freshly organic raw cooked uncooked ripe lean softened melted beaten packed divided optional room temperature cold warm hot rinsed drained washed about plus more into cut of and or for a an the to'''.split())
PORTION_WORDS = set('''piece pieces clove cloves sprig sprigs leaf leaves stalk stalks bunch bunches head heads slice slices pinch pinches dash dashes handful handfuls'''.split())
MEASUREMENT_WORDS = set('''cup cups tbsp tablespoon tablespoons tsp teaspoon teaspoons mg g gm gms gram grams kg kgs kilogram kilograms ml cl l ltr litre litres liter liters oz ounce ounces lb lbs pound pounds pc pcs unit units'''.split())

DERIVED_PRODUCT_FORMS = set('''ketchup cracker crackers biscuit biscuits cookie cookies chocolate candy sweets surprise confectionery kimchi nugget nuggets sausage sausages cake cakes dessert pudding snack snacks stock cube cubes paste spread dressing marinade food pouch kibble litter cooker maker machine press container appliance phone iphone tablet laptop charger toy detergent cleaner soap shampoo conditioner lotion bath soak scent scented formula supplement capsule capsules vitamin vitamins deodorizer deodoriser airfreshener freshener refresher spray gummy gummies granola cereal soju vodka icecream'''.split())
PET_CONTEXT = set('dog dogs cat cats puppy puppies kitten kittens pet pets'.split())

FRESH_FRUIT_SEARCH_TERMS = {
    'strawberry':'strawberries', 'banana':'bananas', 'apple':'apples',
    'blueberry':'blueberries', 'raspberry':'raspberries',
    'blackberry':'blackberries', 'grape':'grapes', 'peach':'peaches',
    'nectarine':'nectarines', 'pear':'pears', 'mango':'mangoes',
    'pineapple':'pineapples', 'watermelon':'watermelons',
    'papaya':'papayas', 'kiwi':'kiwis', 'cherry':'cherries',
}


def _stem(word: str) -> str:
    word = str(word).lower().strip()
    if len(word) > 4 and word.endswith('ies'):
        return word[:-3] + 'y'
    if len(word) > 4 and word.endswith('oes'):
        return word[:-2]
    if len(word) > 4 and word.endswith('ves'):
        return word[:-1]
    if len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word


def words(text: str) -> list[str]:
    return [_stem(word) for word in _WORD.findall(str(text or '').lower())]


def _strip_recipe_notes(text: str) -> str:
    """Remove recipe quantities and preparation notes, not food identity."""
    text = str(text or '').lower()
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = text.split(',', 1)[0]
    text = re.sub(r'\b\d+\s*/\s*\d+\b', ' ', text)
    text = re.sub(r'\b\d+(?:\.\d+)?\b', ' ', text)
    return text


def clean_ingredient(text: str) -> list[str]:
    raw = _WORD.findall(_strip_recipe_notes(text))
    return [w for token in raw if (w := _stem(token)) and w not in DESCRIPTORS and w not in PORTION_WORDS and w not in MEASUREMENT_WORDS]


def canonical_phrase(text: str) -> str:
    return ' '.join(clean_ingredient(text))


def _url_tokens(url: str) -> list[str]:
    try:
        path = unquote(urlparse(str(url or '')).path)
    except (TypeError, ValueError):
        path = str(url or '')
    return words(path.replace('-', ' ').replace('_', ' ').replace('/', ' '))


def _evidence_tokens(title: str, url: str = '', content: str = '', size_text: str = '') -> list[str]:
    return words(title) + _url_tokens(url) + words(content) + words(size_text)


def _derived_product_reason(ingredient_tokens: list[str], title_tokens: list[str], url_tokens: list[str]) -> str | None:
    requested = set(ingredient_tokens)
    identity = set(title_tokens + url_tokens)
    pets = identity & PET_CONTEXT
    if pets:
        return 'non-food/pet product: ' + sorted(pets)[0]
    extra_forms = {'sauce', 'wrap', 'wraps', 'milk', 'juice', 'drink', 'drinks', 'bread', 'chips', 'syrup'}
    unwanted = (identity & extra_forms) - requested
    if unwanted:
        return 'processed product: ' + sorted(unwanted)[0]
    unwanted = (identity & DERIVED_PRODUCT_FORMS) - requested
    if unwanted:
        return 'processed product: ' + sorted(unwanted)[0]
    return None


def _coverage(ingredient_tokens: list[str], evidence_tokens: list[str]) -> float:
    if not ingredient_tokens:
        return 0.0
    return len(set(ingredient_tokens) & set(evidence_tokens)) / len(set(ingredient_tokens))


def _phrase_similarity(ingredient: str, title: str) -> float:
    left = canonical_phrase(ingredient)
    right = ' '.join(words(title))
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def check_match(ingredient: str, title: str, url: str = '', content: str = '', size_text: str = '') -> tuple[bool, str]:
    """Conservative relevance check; snippet text alone cannot establish exactness."""
    core = clean_ingredient(ingredient)
    if not core:
        return False, 'ingredient has no usable identity'
    title_tokens = words(title)
    url_tokens = _url_tokens(url)
    primary = title_tokens + url_tokens
    evidence = primary + words(content) + words(size_text)
    bad_form = _derived_product_reason(core, title_tokens, url_tokens)
    if bad_form:
        return False, bad_form
    core_set = set(core)
    if core_set <= set(title_tokens):
        return True, 'exact'
    if core_set <= set(primary):
        return True, 'strong'
    if len(core) == 1:
        token = core[0]
        if token in set(evidence):
            return True, 'strong'
        return False, f'ingredient identity missing: {token}'
    if _coverage(core, evidence) >= 0.75 and _phrase_similarity(ingredient, title) >= 0.35:
        return True, 'approximate'
    missing = [token for token in core if token not in set(evidence)]
    return False, 'ingredient identity missing: ' + ', '.join(missing)


def search_queries(ingredient: str) -> list[str]:
    """Generate identity-preserving Tavily queries, specific first."""
    cleaned = clean_ingredient(ingredient)
    if not cleaned:
        return []
    stripped = _strip_recipe_notes(ingredient)
    raw_tokens = [t for t in _WORD.findall(stripped) if _stem(t) not in DESCRIPTORS | PORTION_WORDS | MEASUREMENT_WORDS]
    full_query = ' '.join(raw_tokens) if raw_tokens else ' '.join(cleaned)
    original_tokens = _WORD.findall(stripped)
    important = {'fresh', 'frozen', 'smoked', 'dried', 'ground', 'whole'}
    queries = []
    if any(t in important for t in original_tokens):
        queries.append(' '.join(original_tokens))
    normalized = ' '.join(cleaned)
    if normalized in FRESH_FRUIT_SEARCH_TERMS:
        plural = FRESH_FRUIT_SEARCH_TERMS[normalized]
        queries.extend([f'fresh {plural}', f'fresh {normalized}', f'{normalized} fruit'])
    queries.append(full_query)
    if stripped.strip().lower() == 'sugar':
        queries = ['white granulated sugar', 'white sugar', *queries]
    if len(cleaned) > 1:
        first, last = cleaned[0], cleaned[-1]
        forms = {'powder', 'milk', 'oil', 'sauce', 'flour', 'vinegar', 'paste', 'cream', 'cheese', 'stock', 'broth', 'butter'}
        fallback = first if last in forms or last in {'breast', 'thigh', 'fillet', 'loin', 'wing', 'leg'} else last
        if fallback != full_query:
            queries.append(fallback)
    return list(dict.fromkeys(queries))
