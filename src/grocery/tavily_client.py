"""src/grocery/tavily_client.py — find Singapore grocery prices with Tavily web search.

For each ingredient it searches "price of <ingredient> in Singapore", restricted to Singapore
supermarket websites, and turns each search result (a web page) into a product dict:
title, price (SGD), package size text, store, url.

    client = TavilyGroceryClient()        # reads TAVILY_API_KEY from .env / environment
    products = client.search("fresh milk")

Results are web pages, not a product database, so price and size are EXTRACTED from the page
text. Pages where no price can be found are dropped (never guessed).
"""
import json
import hashlib
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Singapore supermarket websites -> store name shown to users
SG_GROCERY_DOMAINS = {
    "fairprice.com.sg": "FairPrice",
    "coldstorage.com.sg": "Cold Storage",
    # "shengsiong.com.sg": "Sheng Siong",
    # "giant.sg": "Giant",
    # "redmart.lazada.sg": "RedMart",
}

# Product pages vs. search/category/promo pages
_PRODUCT_URL = re.compile(r"/(product|products|p)/|-i\d+(-s\d+)?\.html|[-/]\d{5,}/?$", re.IGNORECASE)
_OUT_OF_STOCK = re.compile(r"out of stock|sold out|currently unavailable|not available", re.IGNORECASE)
_NON_PRODUCT_URL = re.compile(
    r"/(search|category|categories|promotions?|collections?|brands?|recipes?|blog|deals|offers?)(/|$)"
    r"|[?&](q|query|keyword|search)=", re.IGNORECASE)

# "$3.45", "S$ 3.45", "SGD 3.45"
_PRICE = re.compile(r"(?:S\$|SGD\s?|\$)\s?(\d{1,4}(?:,\d{3})*(?:\.\d{1,2})?)")
# Prices next to these words are banners/fees, not the product price
# (whole words only - "Offer" in "campaign labelOffer" must NOT count as "off")
_IGNORE_BEFORE = re.compile(r"\b(deliver\w*|above|min|minimum|spend|save|voucher|cashback|over|free|"
                            r"shipping|fee|off|worth|up to|earn|reward)\b[^$]{0,25}$", re.IGNORECASE)
# Title suffixes like " | FairPrice Singapore", " - Cold Storage"
_TITLE_SUFFIX = re.compile(r"\s+[|\-–—]\s+.*(fairprice|cold storage|sheng siong|giant|redmart|lazada|"
                           r"singapore|online|shop).*$", re.IGNORECASE)


class SearchError(Exception):
    """The price source failed (bad key, quota, network...) - NOT the same as 'no products'."""


def store_for(url: str) -> tuple[str | None, str | None]:
    """'https://www.fairprice.com.sg/product/x' -> ('fairprice.com.sg', 'FairPrice')."""
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    for domain, name in SG_GROCERY_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return domain, name
    return None, None


def is_product_page(url: str) -> bool:
    path = urlparse(url or "").path + ("?" + urlparse(url or "").query if urlparse(url or "").query else "")
    return bool(_PRODUCT_URL.search(path)) and not _NON_PRODUCT_URL.search(path)


def clean_title(title: str) -> str:
    title = re.sub(r"^\s*buy\s+", "", str(title or ""), flags=re.IGNORECASE)
    return _TITLE_SUFFIX.sub("", title).strip()


def extract_price(text: str) -> float | None:
    text = str(text or "")

    matches = list(_PRICE.finditer(text))
    prices = []

    for m in matches:
        after = text[m.end():m.end() + 30]

        # Ignore unit prices such as $0.35/100g
        if after.lstrip().startswith("/"):
            continue

        value = float(m.group(1).replace(",", ""))

        if 0 < value <= 1000:
            prices.append(value)

    if not prices:
        return None

    # Sort prices from smallest to largest
    prices.sort()

    # 3 prices -> take the middle price
    if len(prices) == 3:
        return round(prices[1], 2)

    # 2 prices -> take the larger/2nd price
    if len(prices) == 2:
        return round(prices[1], 2)

    # 1 price -> take that price
    return round(prices[0], 2)

def normalize(result: dict) -> dict | None:
    """One Tavily result -> product dict, or None if it isn't a usable SG product page with a price."""
    url = result.get("url") or ""
    domain, store = store_for(url)
    if not domain or not is_product_page(url):
        return None
    title = clean_title(result.get("title") or "")
    snippet = result.get("content") or ""
    raw = result.get("raw_content") or ""
    # Price: the search snippet first, then the page text after the product name
    start = raw.lower().find(title.lower()[:30]) if title else -1
    price = extract_price(
    raw[max(start, 0):max(start, 0) + 3000]
    ) or extract_price(snippet)
    if not title or price is None:
        return None
    page_text = f"{snippet} {raw[max(start, 0):max(start, 0) + 1500]}"
    return {
        "product_id": hashlib.sha1(url.encode()).hexdigest()[:12],
        "title": title,
        "price": price,
        "currency": "SGD",
        "merchant_id": domain,
        "store": store,
        "url": url,
        "size_text": f"{snippet[:500]} {raw[max(start, 0):max(start, 0) + 500]}",
        "availability": "local",
        "in_stock": False if _OUT_OF_STOCK.search(page_text) else None,
        "country_code": "SG",
        "region": "sg",
        "source_updated_at": None,     # web pages don't say when the price was set
    }


class TavilyGroceryClient:
    def __init__(self, api_key: str | None = None, max_results: int = 10, search_depth: str = "basic"):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")
        self.max_results = max_results
        self.search_depth = search_depth
        self._client = None

    def _tavily(self):
        if self._client is None:
            if not self.api_key:
                raise SearchError("TAVILY_API_KEY is not set (add it to .env)")
            from tavily import TavilyClient
            self._client = TavilyClient(api_key=self.api_key)
        return self._client

    def search_raw(self, query: str) -> dict:
        try:
            response = self._tavily().search(
                query=f"price of {query} in Singapore",
                search_depth=self.search_depth,
                max_results=self.max_results,
                include_domains=list(SG_GROCERY_DOMAINS),
                include_raw_content="text",
            )
            return response

        except SearchError:
            raise
        except Exception as e:
            raise SearchError(
                f"Tavily search failed: {type(e).__name__}: {e}"
            ) from e
    def search(self, query: str, limit: int | None = None) -> list[dict]:
        results = self.search_raw(query).get("results") or []
        return [p for p in (normalize(r) for r in results) if p is not None]

# if __name__ == "__main__":
#     client = TavilyGroceryClient()

#     result = client.search_raw("eggs")

#     print(json.dumps(result, indent=2, ensure_ascii=False))