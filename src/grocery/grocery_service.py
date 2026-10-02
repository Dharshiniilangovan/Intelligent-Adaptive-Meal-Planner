"""src/grocery/grocery_service.py — turn an ingredient into a buyable Singapore grocery option.

    from src.grocery.grocery_service import get_grocery_option, search_grocery_product

    search_grocery_product("tofu")
    get_grocery_option("rice", 700, "g")      # -> packages needed + total purchase cost

Prices are fetched live (Tavily web search on Singapore supermarket sites) when called - no
pre-built database. Results are cached in memory for a few hours so the same ingredient isn't
searched twice per meal plan. If no reliable product is found, product and price are None (NA).
"""
import math
import re
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import requests

from src.grocery.tavily_client import SearchError, TavilyGroceryClient
from src.grocery.food_filter import check_match, search_queries, words
from src.grocery.units import parse_package, pretty, to_base

GROCERY_STORES = ("fairprice", "ntuc")
# Only accept products from known Singapore grocery retailers (Tavily searches only these sites,
# but this double-checks every result).
GROCERY_STORES_ONLY = True
MAX_ITEM_PRICE = 100.0          # SGD; no single grocery pack costs more than this
# Listing patterns verified as fake/dead during earlier testing
BAD_URL_PATTERNS = [
    (re.compile(r"fairprice\.com\.sg/product/.*-ifp-[a-z]+-\d+$", re.IGNORECASE),
     "known fake FairPrice listing pattern (pages return 404)"),
    (re.compile(r"amazon\.[a-z.]+/dp/\d{9}[\dX]\b", re.IGNORECASE),
     "Amazon book (ISBN), not a grocery item"),
]
PRICE_OUTLIER_FACTOR = 3.0      # drop products whose unit price is > 3x the median of the others
_SOFT_404 = re.compile(r"<title>[^<]*(404|not found|can.t (be )?found)[^<]*</title>", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- output contract
@dataclass
class GroceryOption:
    ingredient_id: str | None
    ingredient_name: str
    required_quantity: float | None = None
    required_unit: str | None = None
    product_name: str | None = None
    package_quantity: float | None = None
    package_unit: str | None = None
    packages_needed: int | None = None
    price_per_package: float | None = None
    total_cost: float | None = None
    currency: str | None = None
    store: str | None = None
    source_url: str | None = None
    source_updated_at: str | None = None
    date_collected: str = field(default_factory=_now)
    match_status: str = "no_match"      # matched | matched_no_quantity | no_match | error
    match_quality: str | None = None    # exact | approximate
    search_query: str | None = None     # what was actually searched
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- service
class GroceryService:
    def __init__(self, client: TavilyGroceryClient | None = None, verify_links: bool = False,
                 cache_ttl_hours: float = 6.0):
        self.client = client or TavilyGroceryClient()
        self.verify_links = verify_links
        self.cache_ttl = cache_ttl_hours * 3600
        self._search_cache: dict[str, tuple[float, list[dict]]] = {}
        self._link_cache: dict[str, bool] = {}
        self._http = requests.Session()
        self._http.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    # ---- step 1: fetch (cached)
    def _search(self, ingredient: str) -> list[dict]:
        key = " ".join(words(ingredient))
        hit = self._search_cache.get(key)
        if hit and time.time() - hit[0] < self.cache_ttl:
            return hit[1]
        products = self.client.search(ingredient)
        self._search_cache[key] = (time.time(), products)
        return products

    # ---- step 2: keep only real, buyable, food products that ARE the ingredient
    def _filter(self, ingredient: str, products: list[dict]) -> tuple[list[dict], Counter]:
        valid, rejected = [], Counter()
        for p in products:
            if p.get("country_code") not in (None, "SG") or p.get("region") not in (None, "sg"):
                rejected["not sold in Singapore"] += 1
            elif p["currency"] != "SGD":
                rejected["not SGD"] += 1
            elif p.get("in_stock") is False:
                rejected["out of stock"] += 1
            elif p.get("availability") not in (None, "local"):
                rejected[f"availability={p['availability']}"] += 1
            elif p["price"] > MAX_ITEM_PRICE:
                rejected["price too high for groceries"] += 1
            elif GROCERY_STORES_ONLY and not self._is_grocery_store(p):
                rejected["not a grocery store"] += 1
            elif any(rx.search(p.get("url") or "") for rx, _ in BAD_URL_PATTERNS):
                rejected[next(r for rx, r in BAD_URL_PATTERNS if rx.search(p.get("url") or ""))] += 1
            else:
                ok, quality = check_match(ingredient, p["title"])
                if not ok:
                    rejected[quality] += 1
                    continue
                package = parse_package(p["title"]) or parse_package(p.get("size_text") or "")
                valid.append({**p, "match": quality, "package": package})
        return self._drop_price_outliers(valid, rejected), rejected

    @staticmethod
    def _drop_price_outliers(valid: list[dict], rejected: Counter) -> list[dict]:
        """Listings with a unit price far above the others are usually bad data."""
        unit_prices = {id(p): p["price"] / p["package"][0] for p in valid if p["package"]}
        if len(unit_prices) < 3:
            return valid
        median = statistics.median(unit_prices.values())
        kept = []
        for p in valid:
            if id(p) in unit_prices and unit_prices[id(p)] > PRICE_OUTLIER_FACTOR * median:
                rejected["price outlier"] += 1
            else:
                kept.append(p)
        return kept

    @staticmethod
    def _is_grocery_store(p: dict) -> bool:
        text = f"{p.get('store', '')} {p.get('merchant_id', '')} {p.get('url', '')}".lower()
        text = text.replace("_", " ").replace("-", " ")
        return any(s in text for s in GROCERY_STORES)

    # ---- step 3: order the candidates (cheapest total purchase first when quantity is known)
    @staticmethod
    def _quality(p: dict) -> int:
        store = f"{p.get('store', '')} {p.get('merchant_id', '')}".lower().replace("_", " ")
        return (2 if any(s in store for s in GROCERY_STORES) else 0) \
            + (1 if p.get("source_updated_at") else 0) \
            + (1 if p.get("package") else 0)

    def _rank(self, valid: list[dict], need: tuple[float, str] | None) -> list[dict]:
        for p in valid:
            p["packages"] = p["total"] = None
            if need and p["package"] and p["package"][1] == need[1]:
                p["packages"] = max(1, math.ceil(need[0] / p["package"][0] - 1e-9))
                p["total"] = round(p["packages"] * p["price"], 2)
        exact_first = lambda p: 0 if p["match"] == "exact" else 1
        priced = sorted((p for p in valid if p["total"] is not None),
                        key=lambda p: (exact_first(p), p["total"], -self._quality(p)))
        others = sorted((p for p in valid if p["total"] is None),
                        key=lambda p: (exact_first(p), -self._quality(p), p["price"]))
        # exact matches always come before approximate ones
        return sorted(priced + others, key=exact_first)

    # ---- step 4: make sure the product page exists
    def _link_ok(self, url: str | None) -> bool:
        """False only when the page is DEFINITELY gone (404/410 or a 'not found' page).
        Stores often block scripts (403) or time out - that's 'unknown', not 'broken'."""
        if not url:
            return False
        if url not in self._link_cache:
            try:
                r = self._http.get(url, timeout=10, allow_redirects=True)
                gone = r.status_code in (404, 410) or (r.status_code < 400 and _SOFT_404.search(r.text[:50_000]))
                self._link_cache[url] = not gone
            except requests.RequestException:
                self._link_cache[url] = True
        return self._link_cache[url]

    # ---- try the specific query first, then a simpler one
    def _find_candidates(self, ingredient: str) -> tuple[list[dict], Counter, int, str | None]:
        all_valid, rejected, n_results, used = {}, Counter(), 0, None
        for query in search_queries(ingredient):
            products = self._search(query)
            n_results += len(products)
            valid, rej = self._filter(ingredient, products)
            rejected.update(rej)
            for p in valid:
                all_valid.setdefault(p["product_id"], p)
            if valid and used is None:
                used = query
            if any(p["match"] == "exact" for p in valid):
                break
        return list(all_valid.values()), rejected, n_results, used

    # ---------------------------------------------------------------- public API
    def get_grocery_option(self, ingredient_name: str, required_quantity: float | None = None,
                           unit: str | None = None, ingredient_id: str | None = None) -> GroceryOption:
        option = GroceryOption(ingredient_id=ingredient_id, ingredient_name=ingredient_name,
                               required_quantity=required_quantity, required_unit=unit)
        need = to_base(required_quantity, unit) if required_quantity is not None and unit else None
        if required_quantity is not None and unit and need is None:
            option.note = f"unknown unit '{unit}'. "

        try:
            valid, rejected, n_results, used_query = self._find_candidates(ingredient_name)
        except SearchError as e:
            option.match_status, option.note = "error", option.note + f"search failed: {e}"
            return option

        if not valid:
            reasons = ", ".join(f"{r} ({n})" for r, n in rejected.most_common(3)) or "no search results"
            option.note += f"no reliable match among {n_results} results: {reasons}"
            return option
        option.search_query = used_query

        broken = 0
        for p in self._rank(valid, need)[:5]:
            if self.verify_links and not self._link_ok(p["url"]):
                broken += 1
                continue
            option.product_name = p["title"]
            option.price_per_package = p["price"]
            option.currency = p["currency"]
            option.store = p["store"]
            option.source_url = p["url"]
            option.source_updated_at = p["source_updated_at"]
            option.match_quality = p["match"]
            if p["match"] == "approximate":
                option.note += "approximate match - check the product suits the recipe. "
            if p["package"]:
                option.package_quantity, option.package_unit = pretty(*p["package"])
            if p["total"] is not None:
                option.packages_needed, option.total_cost = p["packages"], p["total"]
                option.match_status = "matched"
            else:
                option.match_status = "matched_no_quantity"
                if need is None:
                    option.note += "no required quantity given; packages not calculated."
                elif not p["package"]:
                    option.note += "package size not found on the product page; packages not calculated."
                else:
                    option.note += (f"unit mismatch (need {need[1]}, package in {p['package'][1]}); "
                                    "packages not calculated.")
            if broken:
                option.note += f" skipped {broken} product(s) with broken links."
            option.note = option.note.strip()
            return option

        option.note += f"all top matches had broken product links ({broken})."
        return option

    def search_grocery_product(self, ingredient_name: str) -> GroceryOption:
        return self.get_grocery_option(ingredient_name)

    def get_grocery_list(self, items: list[dict]) -> list[GroceryOption]:
        """items: [{"ingredient_name": "rice", "quantity": 700, "unit": "g", "ingredient_id": "I001"}, ...]"""
        return [self.get_grocery_option(i["ingredient_name"], i.get("quantity"), i.get("unit"),
                                        i.get("ingredient_id")) for i in items]


def basket_summary(options: list[GroceryOption]) -> dict:
    priced = [o for o in options if o.total_cost is not None]
    return {
        "items": len(options),
        "priced_items": len(priced),
        "estimated_total": round(sum(o.total_cost for o in priced), 2),
        "missing_price": [o.ingredient_name for o in options if o.price_per_package is None],
        "missing_package_calc": [o.ingredient_name for o in options
                                 if o.price_per_package is not None and o.total_cost is None],
    }


# ---------------------------------------------------------------- simple module-level functions
_default_service: GroceryService | None = None


def _service() -> GroceryService:
    global _default_service
    if _default_service is None:
        _default_service = GroceryService()
    return _default_service


def search_grocery_product(ingredient_name: str) -> GroceryOption:
    return _service().search_grocery_product(ingredient_name)


def get_grocery_option(ingredient_name: str, required_quantity: float, unit: str,
                       ingredient_id: str | None = None) -> GroceryOption:
    return _service().get_grocery_option(ingredient_name, required_quantity, unit, ingredient_id)