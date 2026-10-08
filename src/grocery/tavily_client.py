"""src/grocery/tavily_client.py

Find Singapore grocery prices from FairPrice using Tavily web search.

For each ingredient, Tavily searches FairPrice and converts usable
FairPrice product pages into normalized product dictionaries containing:

    title
    price
    currency
    package-size text
    store
    URL
    stock status

Only individual FairPrice product pages are accepted. Search pages,
category pages, promotion pages, and pages without a reliable price
are rejected.
"""

import hashlib
import os
import re
from pathlib import Path
from urllib.parse import urlparse
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv


# ---------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


# ---------------------------------------------------------------------
# Grocery source
# ---------------------------------------------------------------------

GROCERY_DOMAIN = "fairprice.com.sg"
GROCERY_STORE = "FairPrice"


# ---------------------------------------------------------------------
# FairPrice page detection
# ---------------------------------------------------------------------

# Individual product pages.
_PRODUCT_URL = re.compile(
    r"/(product|products|p)/"
    r"|-i\d+(-s\d+)?\.html"
    r"|[-/]\d{5,}/?$",
    re.IGNORECASE,
)

# Pages that may contain many products/prices and therefore must not
# be treated as one grocery product.
_NON_PRODUCT_URL = re.compile(
    r"/(search|category|categories|promotions?|collections?|brands?|"
    r"recipes?|blog|deals|offers?|product-listing|tag)(/|$|\?)"
    r"|[?&](q|query|keyword|search|category|pageType|tag)=",
    re.IGNORECASE,
)

_OUT_OF_STOCK = re.compile(
    r"out of stock|sold out|currently unavailable|not available",
    re.IGNORECASE,
)
_DELIVERY_UNAVAILABLE = re.compile(
    r"unavailable\s+for\s+delivery"
    r"|not\s+available\s+for\s+delivery"
    r"|delivery\s+unavailable",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------
# Price extraction
# ---------------------------------------------------------------------

# Matches:
# $3.45
# S$3.45
# S$ 3.45
# SGD 3.45
_PRICE = re.compile(
    r"(?:S\$|SGD\s?|\$)\s?"
    r"(\d{1,4}(?:,\d{3})*(?:\.\d{1,2})?)"
)


_IGNORE_BEFORE = re.compile(
    r"\b("
    r"deliver\w*|above|min|minimum|spend|"
    r"voucher|cashback|shipping|fee|worth|"
    r"up to|earn|reward"
    r")\b[^$]{0,25}$",
    re.IGNORECASE,
)


_SAVE_BEFORE = re.compile(
    r"\b("
    r"save|saving|savings|discount"
    r")\b[^$]{0,20}$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------
# FairPrice title cleanup
# ---------------------------------------------------------------------

_TITLE_SUFFIX = re.compile(
    r"\s+[|\-–—]\s+.*"
    r"(fairprice|ntuc fairprice|singapore|online|shop).*$",
    re.IGNORECASE,
)


class SearchError(Exception):
    """Raised when Tavily itself fails rather than simply finding no products."""


def store_for(url: str) -> tuple[str | None, str | None]:
    """
    Return FairPrice information when a URL belongs to FairPrice.

    Subdomains such as omni.fairprice.com.sg are also recognised.
    """

    host = urlparse(url or "").netloc.lower().removeprefix("www.")

    if host == GROCERY_DOMAIN or host.endswith("." + GROCERY_DOMAIN):
        return GROCERY_DOMAIN, GROCERY_STORE

    return None, None


def is_product_page(url: str) -> bool:
    """
    Return True only when the URL looks like an individual product page.

    Category, search, tag and promotional pages are rejected because
    they may contain multiple products and multiple unrelated prices.
    """

    parsed = urlparse(url or "")

    path_and_query = parsed.path

    if parsed.query:
        path_and_query += "?" + parsed.query

    if _NON_PRODUCT_URL.search(path_and_query):
        return False

    return bool(_PRODUCT_URL.search(path_and_query))


def clean_title(title: str) -> str:
    """
    Remove FairPrice page decorations from a product title.

    Example:
        "Buy Meiji Fresh Milk 2L | FairPrice Singapore"
        -> "Meiji Fresh Milk 2L"
    """

    title = str(title or "")

    title = re.sub(
        r"^\s*buy\s+",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return _TITLE_SUFFIX.sub("", title).strip()




def extract_price(text: str) -> float | None:
    """
    Extract a reliable product selling price from Tavily text.

    Supports:
    - Explicit sale/current prices
    - FairPrice Offer + old price + savings
    - Product price + unit price
    - Old price minus savings
    - Single unambiguous selling price

    Rejects:
    - Savings amounts alone
    - Discounts alone
    - Delivery thresholds
    - Bottle deposits
    - Ambiguous multiple prices
    """

    if not text:
        return None

    text = str(text)

    money = (
        r"(?:S\s*\$|SGD\s*|\$)\s*"
        r"([\d,]+(?:\.\d{1,2})?)"
    )

    money_token = (
        r"(?:S\s*\$|SGD\s*|\$)\s*"
        r"[\d,]+(?:\.\d{1,2})?"
    )

    def valid_price(raw):
        try:
            value = float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            return None

        if 0 < value <= 1000:
            return round(value, 2)

        return None

    # ---------------------------------------------------------
    # Remove delivery/shipping thresholds.
    # ---------------------------------------------------------

    text = re.sub(
        r"\b(?:free\s+)?(?:delivery|shipping)"
        r"\s+(?:(?:on|for)\s+orders?\s+)?"
        r"(?:above|over|from|of|minimum)\s*"
        + money_token,
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # ---------------------------------------------------------
    # Remove unit prices.
    #
    # Examples:
    # $0.35/100g
    # S$1.20/kg
    # $0.50 per 100ml
    # ---------------------------------------------------------

    text = re.sub(
        money_token
        + r"\s*(?:/|per\s+)"
        + r"\s*(?:\d+(?:\.\d+)?\s*)?"
        + r"(?:kg|g|ml|l|litre|liter|pcs?|each)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # ---------------------------------------------------------
    # Explicit current selling prices.
    # ---------------------------------------------------------

    priority_patterns = [
        r"\b(?:sale|selling|current|offer|"
        r"discounted|special)\s+price\s*[:=]?\s*"
        + money,

        r"\b(?:now|only)\s*[:=]?\s*"
        + money,

        r"\bprice\s*[:=]\s*" + money,
    ]

    for pattern in priority_patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for raw in matches:
            price = valid_price(raw)

            if price is not None:
                return price

    # ---------------------------------------------------------
    # FairPrice promotion:
    #
    # Offer
    # $16.50
    # $18.20
    # Save $1.70Ends in 12h
    #
    # Verify:
    # 18.20 - 1.70 == 16.50
    # ---------------------------------------------------------

    offer_pattern = (
        r"\bOffer\b"
        r"[\s\S]{0,120}?"
        + money
        + r"\s*"
        + money
        + r"\s*"
        + r"\bSave\s*"
        + money
    )

    offer_match = re.search(
        offer_pattern,
        text,
        flags=re.IGNORECASE,
    )

    if offer_match:
        current = valid_price(offer_match.group(1))
        original = valid_price(offer_match.group(2))
        savings = valid_price(offer_match.group(3))

        if (
            current is not None
            and original is not None
            and savings is not None
            and abs(
                (original - savings) - current
            ) <= 0.02
        ):
            return current

    # ---------------------------------------------------------
    # Identify old-price-minus-savings layouts even
    # without an explicit Offer label.
    # ---------------------------------------------------------

    savings_match = re.search(
        r"\b(?:save|saving|savings)\s*"
        + money,
        text,
        flags=re.IGNORECASE,
    )

    if savings_match:
        savings = valid_price(
            savings_match.group(1)
        )

        before_savings = text[
            :savings_match.start()
        ]

        candidates = [
            valid_price(match.group(1))
            for match in re.finditer(
                money,
                before_savings,
                flags=re.IGNORECASE,
            )
        ]

        candidates = [
            value
            for value in candidates
            if value is not None
        ]

        if (
            savings is not None
            and len(candidates) >= 2
        ):
            current = candidates[-2]
            original = candidates[-1]

            if abs(
                (original - savings) - current
            ) <= 0.02:
                return current

    # ---------------------------------------------------------
    # Remove savings/discount amounts.
    # ---------------------------------------------------------

    text = re.sub(
        r"\b(?:save|saving|savings)\s*"
        + money_token,
        " ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        money_token
        + r"\s*(?:off|discount|savings?)\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # ---------------------------------------------------------
    # Remove bottle deposits.
    # ---------------------------------------------------------

    text = re.sub(
        r"\+\s*"
        + money_token
        + r"\s*(?:bottle\s+)?deposit\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # ---------------------------------------------------------
    # Remove explicitly labelled old prices.
    # ---------------------------------------------------------

    text = re.sub(
        r"\b(?:was|original\s+price|"
        r"regular\s+price|usual\s+price|before)"
        r"\s*[:=]?\s*"
        + money_token,
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # ---------------------------------------------------------
    # Collect remaining selling-price candidates.
    # ---------------------------------------------------------

    prices = []

    for match in re.finditer(
        money,
        text,
        flags=re.IGNORECASE,
    ):
        price = valid_price(match.group(1))

        if price is not None:
            prices.append(price)

    prices = sorted(set(prices))

    if len(prices) == 1:
        return prices[0]

    # Multiple prices without sufficient evidence.
    return None



def normalize(result: dict) -> dict | None:
    """
    Convert one Tavily result into the grocery product format.

    Returns None when the result is not a usable FairPrice product page
    or when a reliable product price cannot be extracted.
    """

    url = result.get("url") or ""

    domain, store = store_for(url)

    # FairPrice only.
    if not domain:
        return None

    # Reject categories, searches, tags and promotional pages.
    if not is_product_page(url):
        return None

    title = clean_title(
        result.get("title") or ""
    )

    
    # ---------------------------------------------------------
    # Recover product variants omitted from Tavily titles.
    #
    # Example:
    # Tavily title: Santa Cruz Organic Bottle Juice
    # Page title:   Santa Cruz Organic Bottle Juice - Pure Lemon
    # ---------------------------------------------------------

    import re

    snippet_text = result.get("content") or ""
    raw_text = result.get("raw_content") or ""

    combined_text = (
        snippet_text + "\n" + raw_text
    )

    if title:
        escaped_title = re.escape(title)

        variant_pattern = re.compile(
            escaped_title
            + r"\s*[-–]\s*"
            + r"([A-Za-z][A-Za-z0-9 &]{1,45})",
            re.IGNORECASE,
        )

        variant_match = variant_pattern.search(
            combined_text
        )

        if variant_match:
            variant = variant_match.group(1).strip()

            # Stop at typical product metadata boundaries.
            variant = re.split(
                r"\s*(?:\||\n|Brand:|"
                r"\d+\s*(?:ml|g|kg|l)\b)",
                variant,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()

            if variant:
                title = f"{title} - {variant}"


    snippet = result.get("content") or ""
    raw = result.get("raw_content") or ""

    if not title:
        return None

    # Try to locate the product title inside the raw page.
    # Starting near the product name reduces the chance of reading
    # unrelated prices elsewhere on a large page.
    if raw:
        start = raw.lower().find(
            title.lower()[:30]
        )
    else:
        start = -1

    if start < 0:
        start = 0

    raw_price_section = raw[
        start:
        start + 3000
    ]

    # Prefer raw product-page content.
    # Fall back to the Tavily search snippet if necessary.

    # Search-result content often preserves the product's displayed
# selling price even when FairPrice raw_content omits dynamic
# pricing information.
    # Tavily search content often contains the displayed price
# even when FairPrice raw_content does not contain dynamically
# rendered pricing information.
    price = extract_price(
        snippet
    )

    if price is None:
        price = extract_price(
            raw_price_section
        )

    if price is None:
        return None

    page_text = (
        f"{snippet} "
        f"{raw[start:start + 1500]}"
    )

    size_text = (
        f"{snippet[:500]} "
        f"{raw[start:start + 500]}"
    )

    return {
        "product_id": hashlib.sha1(
            url.encode()
        ).hexdigest()[:12],

        "title": title,

        "price": price,

        "currency": "SGD",

        "merchant_id": domain,

        "store": store,

        "url": url,

        "size_text": size_text,
         # NEW
        "search_content": snippet,
        "product_text": page_text,

        "availability": "local",

        "delivery_available": (
            False
            if _DELIVERY_UNAVAILABLE.search(page_text)
            else None
        ),

        "in_stock": (
            False
            if _OUT_OF_STOCK.search(page_text)
            else None
        ),

        "country_code": "SG",

        "region": "sg",

        # FairPrice/Tavily pages do not reliably provide the date on
        # which the displayed grocery price was last updated.
        "source_updated_at": None,
    }


def extract_product_price(text: str) -> float | None:
    """
    Extract a clearly labelled product price.

    Avoid guessing prices from unrelated dollar amounts,
    delivery thresholds, or percentage discounts.
    """
    if not text:
        return None

    text = str(text)

    # Remove delivery and shipping threshold statements.
    text = re.sub(
        r"(?:free\s+)?(?:delivery|shipping)"
        r".{0,60}?"
        r"(?:above|over|minimum|from)\s*"
        r"(?:S\$|SGD|\$)\s*[\d,]+(?:\.\d{1,2})?",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    patterns = [
        # Explicitly labelled price.
        r"(?:current\s+price|sale\s+price|"
        r"selling\s+price|product\s+price)"
        r"\s*[:=]?\s*(?:S\$|SGD|\$)\s*"
        r"([\d,]+(?:\.\d{1,2})?)",

        # Currency followed by price.
        r"(?:S\$|SGD|\$)\s*"
        r"([\d,]+(?:\.\d{1,2})?)",
    ]

    for pattern in patterns:
        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        for raw in matches:
            try:
                price = Decimal(raw.replace(",", ""))
            except InvalidOperation:
                continue

            if Decimal("0") < price <= Decimal("1000"):
                return float(price)

    return None



class TavilyGroceryClient:
    """
    Tavily client restricted to FairPrice grocery results.
    """

    def __init__(
        self,
        api_key: str | None = None,
        max_results: int = 15,
        search_depth: str = "basic",
    ):
        self.api_key = (
            api_key
            or os.environ.get("TAVILY_API_KEY", "")
        )

        self.max_results = max_results
        self.search_depth = search_depth
        self._client = None

    def _tavily(self):
        if self._client is None:

            if not self.api_key:
                raise SearchError(
                    "TAVILY_API_KEY is not set "
                    "(add it to .env)"
                )

            from tavily import TavilyClient

            self._client = TavilyClient(
                api_key=self.api_key
            )

        return self._client

    def search_raw(self, query: str) -> dict:
        """
        Search FairPrice through Tavily.

        The FairPrice restriction is handled by include_domains,
        so the text query itself does not need to contain the store name.
        """

        try:
            response = self._tavily().search(
            query=(f'site:fairprice.com.sg '
                    f'"{query}" '
                    f'FairPrice price "$"'
            ),
            search_depth=self.search_depth,
            max_results=self.max_results,
            include_domains=[GROCERY_DOMAIN],
            include_raw_content="text",
        )

            return response

        except SearchError:
            raise

        except Exception as exc:
            raise SearchError(
                f"Tavily search failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    def search(
        self,
        query: str,
        limit: int | None = None,
    ) -> list[dict]:

        search_terms = [
            query,
            f'"{query}"',
            f'"{query}" grocery',
        ]

        products = []
        seen_urls = set()

        for search_term in search_terms:

            results = (
                self.search_raw(search_term)
                .get("results")
                or []
            )

            normalized = [
                product
                for product in (
                    normalize(result)
                    for result in results
                )
                if product is not None
            ]

            for product in normalized:

                url = product.get("url")

                if url not in seen_urls:
                    seen_urls.add(url)
                    products.append(product)

            # We found usable individual FairPrice products.
            # Do not make unnecessary additional Tavily searches.
            # if products:
            #     break

        if limit is not None:
            return products[:limit]

        return products