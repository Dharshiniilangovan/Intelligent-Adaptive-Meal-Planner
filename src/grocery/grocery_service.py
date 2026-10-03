"""src/grocery/grocery_service.py

Turn an ingredient into a buyable FairPrice grocery option.

Prices are fetched live through Tavily/FairPrice and cached in memory.
Products are filtered for:

- Singapore availability
- SGD currency
- FairPrice source
- stock availability
- realistic grocery prices
- food/product relevance
- usable package information

If no reliable product is found, product and price remain None (NA).
"""

import math
import re
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import requests

from src.grocery.food_filter import check_match, search_queries, words
from src.grocery.tavily_client import SearchError, TavilyGroceryClient
from src.grocery.units import parse_package, pretty, to_base


# ---------------------------------------------------------------------
# Grocery source
# ---------------------------------------------------------------------

GROCERY_STORE = "fairprice"

MAX_ITEM_PRICE = 100.0

PRICE_OUTLIER_FACTOR = 3.0


# Listing patterns known to be unreliable or invalid.
BAD_URL_PATTERNS = [
    (
        re.compile(
            r"fairprice\.com\.sg/product/.*-ifp-[a-z]+-\d+$",
            re.IGNORECASE,
        ),
        "known fake FairPrice listing pattern (pages return 404)",
    ),
]


_SOFT_404 = re.compile(
    r"<title>[^<]*(404|not found|can.t (be )?found)[^<]*</title>",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    )


# ---------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------

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

    date_collected: str = field(
        default_factory=_now
    )

    # matched | matched_no_quantity | no_match | error
    match_status: str = "no_match"

    # exact | approximate
    match_quality: str | None = None

    # Query that produced the selected result
    search_query: str | None = None

    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------
# Grocery service
# ---------------------------------------------------------------------

class GroceryService:

    def __init__(
        self,
        client: TavilyGroceryClient | None = None,
        verify_links: bool = False,
        cache_ttl_hours: float = 6.0,
    ):
        self.client = client or TavilyGroceryClient()

        self.verify_links = verify_links

        self.cache_ttl = (
            cache_ttl_hours * 3600
        )

        self._search_cache: dict[
            str,
            tuple[float, list[dict]]
        ] = {}

        self._link_cache: dict[
            str,
            bool
        ] = {}

        self._http = requests.Session()

        self._http.headers["User-Agent"] = (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )

    # -----------------------------------------------------------------
    # Step 1: search with cache
    # -----------------------------------------------------------------

    def _search(
        self,
        ingredient: str,
    ) -> list[dict]:

        key = " ".join(
            words(ingredient)
        )

        hit = self._search_cache.get(key)

        if (
            hit
            and time.time() - hit[0] < self.cache_ttl
        ):
            return hit[1]

        products = self.client.search(
            ingredient
        )

        self._search_cache[key] = (
            time.time(),
            products,
        )

        return products

    # -----------------------------------------------------------------
    # FairPrice validation
    # -----------------------------------------------------------------

    @staticmethod
    def _is_fairprice_product(
        product: dict,
    ) -> bool:
        """
        Defensive FairPrice validation.

        Tavily is already restricted to fairprice.com.sg, but this
        prevents manually supplied, cached or unexpected results from
        another retailer from entering the grocery basket.
        """

        text = (
            f"{product.get('store', '')} "
            f"{product.get('merchant_id', '')} "
            f"{product.get('url', '')}"
        ).lower()

        return GROCERY_STORE in text

    # -----------------------------------------------------------------
    # Step 2: filter results
    # -----------------------------------------------------------------

    def _filter(
        self,
        ingredient: str,
        products: list[dict],
    ) -> tuple[list[dict], Counter]:

        valid = []
        rejected = Counter()

        for product in products:

            # Singapore only
            if product.get("country_code") not in (
                None,
                "SG",
            ):
                rejected[
                    "not sold in Singapore"
                ] += 1
                continue

            if product.get("region") not in (
                None,
                "sg",
            ):
                rejected[
                    "not sold in Singapore"
                ] += 1
                continue

            # SGD only
            if product.get("currency") != "SGD":
                rejected["not SGD"] += 1
                continue

            # Out-of-stock products cannot be recommended.
            if product.get("in_stock") is False:
                rejected["out of stock"] += 1
                continue

            # Local products only.
            if product.get(
                "availability"
            ) not in (
                None,
                "local",
            ):
                rejected[
                    f"availability="
                    f"{product.get('availability')}"
                ] += 1
                continue

            price = product.get("price")

            # Product must have a usable numeric price.
            if price is None:
                rejected["missing price"] += 1
                continue

            if not isinstance(
                price,
                (int, float),
            ):
                rejected["invalid price"] += 1
                continue

            if price <= 0:
                rejected["invalid price"] += 1
                continue

            if price > MAX_ITEM_PRICE:
                rejected[
                    "price too high for groceries"
                ] += 1
                continue

            # FairPrice only.
            if not self._is_fairprice_product(
                product
            ):
                rejected[
                    "not FairPrice"
                ] += 1
                continue

            # Reject known bad URLs.
            bad_reason = None

            for regex, reason in BAD_URL_PATTERNS:
                if regex.search(
                    product.get("url") or ""
                ):
                    bad_reason = reason
                    break

            if bad_reason:
                rejected[bad_reason] += 1
                continue

            # Check that the product is actually the requested food.
            ok, quality = check_match(
                ingredient,
                product.get("title") or "",
            )

            if not ok:
                rejected[quality] += 1
                continue

            # Try title first, then Tavily page text.
            package = (
                parse_package(
                    product.get("title") or ""
                )
                or
                parse_package(
                    product.get("size_text") or ""
                )
            )

            valid.append(
                {
                    **product,
                    "match": quality,
                    "package": package,
                }
            )

        return (
            self._drop_price_outliers(
                valid,
                rejected,
            ),
            rejected,
        )

    # -----------------------------------------------------------------
    # Remove suspicious price outliers
    # -----------------------------------------------------------------

    @staticmethod
    def _drop_price_outliers(
        valid: list[dict],
        rejected: Counter,
    ) -> list[dict]:

        unit_prices = {
            id(product):
                product["price"]
                / product["package"][0]

            for product in valid

            if product.get("package")
            and product["package"][0] > 0
        }

        # Not enough products to determine a reliable median.
        if len(unit_prices) < 3:
            return valid

        median = statistics.median(
            unit_prices.values()
        )

        kept = []

        for product in valid:

            product_id = id(product)

            if (
                product_id in unit_prices
                and
                unit_prices[product_id]
                > PRICE_OUTLIER_FACTOR * median
            ):
                rejected[
                    "price outlier"
                ] += 1
            else:
                kept.append(product)

        return kept

    # -----------------------------------------------------------------
    # Candidate quality
    # -----------------------------------------------------------------

    @staticmethod
    def _quality(
        product: dict,
    ) -> int:

        score = 0

        if GroceryService._is_fairprice_product(
            product
        ):
            score += 2

        if product.get(
            "source_updated_at"
        ):
            score += 1

        if product.get("package"):
            score += 1

        return score

    # -----------------------------------------------------------------
    # Step 3: rank candidates
    # -----------------------------------------------------------------

    def _rank(
        self,
        valid: list[dict],
        need: tuple[float, str] | None,
    ) -> list[dict]:

        for product in valid:

            product["packages"] = None
            product["total"] = None

            package = product.get(
                "package"
            )

            if (
                need
                and package
                and package[1] == need[1]
            ):

                product["packages"] = max(
                    1,
                    math.ceil(
                        need[0]
                        / package[0]
                        - 1e-9
                    ),
                )

                product["total"] = round(
                    product["packages"]
                    * product["price"],
                    2,
                )

        def exact_first(
            product: dict,
        ) -> int:
            return (
                0
                if product["match"] == "exact"
                else 1
            )

        # Products where total purchase cost can be calculated.
        priced = sorted(
            (
                product
                for product in valid
                if product["total"] is not None
            ),
            key=lambda product: (
                exact_first(product),
                product["total"],
                -self._quality(product),
            ),
        )

        # Products where package math could not be completed.
        others = sorted(
            (
                product
                for product in valid
                if product["total"] is None
            ),
            key=lambda product: (
                exact_first(product),
                -self._quality(product),
                product["price"],
            ),
        )

        # Exact matches always remain ahead of approximate matches.
        return sorted(
            priced + others,
            key=exact_first,
        )

    # -----------------------------------------------------------------
    # Step 4: optional link verification
    # -----------------------------------------------------------------

    def _link_ok(
        self,
        url: str | None,
    ) -> bool:

        if not url:
            return False

        if url not in self._link_cache:

            try:
                response = self._http.get(
                    url,
                    timeout=10,
                    allow_redirects=True,
                )

                gone = (
                    response.status_code
                    in (404, 410)
                    or (
                        response.status_code < 400
                        and
                        _SOFT_404.search(
                            response.text[:50_000]
                        )
                    )
                )

                self._link_cache[url] = (
                    not gone
                )

            except requests.RequestException:
                # FairPrice may block automated requests.
                # Network failure does not prove the page is invalid.
                self._link_cache[url] = True

        return self._link_cache[url]

    # -----------------------------------------------------------------
    # Try ingredient search fallbacks
    # -----------------------------------------------------------------

    def _find_candidates(
        self,
        ingredient: str,
        need: tuple[float, str] | None = None,
    ) -> tuple[
        list[dict],
        Counter,
        int,
        str | None,
    ]:

        all_valid = {}
        rejected = Counter()

        n_results = 0
        used_query = None

        for query in search_queries(ingredient):

            products = self._search(query)

            n_results += len(products)

            valid, rejected_here = self._filter(
                ingredient,
                products,
            )

            rejected.update(rejected_here)

            for product in valid:
                all_valid.setdefault(
                    product["product_id"],
                    product,
                )

            if valid and used_query is None:
                used_query = query

            # -----------------------------------------------------
            # Stop early only when we have a useful exact match.
            #
            # If a quantity/unit is known, the product package
            # should use the same base unit so purchase cost can
            # actually be calculated.
            # -----------------------------------------------------

            if need is None:

                if any(
                    product["match"] == "exact"
                    for product in valid
                ):
                    break

            else:

                compatible_exact = any(
                    product["match"] == "exact"
                    and product.get("package") is not None
                    and product["package"][1] == need[1]
                    for product in valid
                )

                if compatible_exact:
                    break

        return (
            list(all_valid.values()),
            rejected,
            n_results,
            used_query,
        )

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def get_grocery_option(
        self,
        ingredient_name: str,
        required_quantity: float | None = None,
        unit: str | None = None,
        ingredient_id: str | None = None,
    ) -> GroceryOption:

        option = GroceryOption(
            ingredient_id=ingredient_id,
            ingredient_name=ingredient_name,
            required_quantity=required_quantity,
            required_unit=unit,
        )

        need = None

        if (
            required_quantity is not None
            and unit
        ):
            need = to_base(
                required_quantity,
                unit,
            )

            if need is None:
                option.note = (
                    f"unknown unit '{unit}'. "
                )

        try:
        
            valid, rejected, n_results, used_query = (
            self._find_candidates(
                ingredient_name,
                need,
            )
        )

        except SearchError as exc:

            option.match_status = "error"

            option.note += (
                f"search failed: {exc}"
            )

            return option

        # -------------------------------------------------------------
        # No reliable product
        # -------------------------------------------------------------

        if not valid:

            reasons = ", ".join(
                f"{reason} ({count})"
                for reason, count
                in rejected.most_common(3)
            )

            if not reasons:
                reasons = "no search results"

            option.note += (
                f"no reliable match among "
                f"{n_results} results: "
                f"{reasons}"
            )

            # Important:
            # price remains None rather than becoming zero.
            return option

        option.search_query = used_query

        # -------------------------------------------------------------
        # Select best product
        # -------------------------------------------------------------

        broken = 0

        for product in self._rank(
            valid,
            need,
        )[:5]:

            if (
                self.verify_links
                and
                not self._link_ok(
                    product.get("url")
                )
            ):
                broken += 1
                continue

            option.product_name = (
                product["title"]
            )

            option.price_per_package = (
                product["price"]
            )

            option.currency = (
                product["currency"]
            )

            option.store = (
                product["store"]
            )

            option.source_url = (
                product["url"]
            )

            option.source_updated_at = (
                product.get(
                    "source_updated_at"
                )
            )

            option.match_quality = (
                product["match"]
            )

            if (
                product["match"]
                == "approximate"
            ):
                option.note += (
                    "approximate match - "
                    "check the product suits "
                    "the recipe. "
                )

            package = product.get(
                "package"
            )

            if package:
                (
                    option.package_quantity,
                    option.package_unit,
                ) = pretty(
                    *package
                )

            # ---------------------------------------------------------
            # Complete package calculation
            # ---------------------------------------------------------

            if product["total"] is not None:

                option.packages_needed = (
                    product["packages"]
                )

                option.total_cost = (
                    product["total"]
                )

                option.match_status = (
                    "matched"
                )

            # ---------------------------------------------------------
            # Product and price found, but purchase quantity unknown
            # ---------------------------------------------------------

            else:

                option.match_status = (
                    "matched_no_quantity"
                )

                if need is None:

                    if (
                        required_quantity is None
                        or not unit
                    ):
                        option.note += (
                            "no required quantity given; "
                            "packages not calculated."
                        )

                    else:
                        option.note += (
                            "required quantity could not "
                            "be converted; packages not "
                            "calculated."
                        )

                elif not package:

                    option.note += (
                        "package size not found on "
                        "the product page; packages "
                        "not calculated."
                    )

                else:

                    option.note += (
                        f"unit mismatch "
                        f"(need {need[1]}, "
                        f"package in {package[1]}); "
                        f"packages not calculated."
                    )

            if broken:
                option.note += (
                    f" skipped {broken} "
                    f"product(s) with broken links."
                )

            option.note = (
                option.note.strip()
            )

            return option

        option.note += (
            f"all top matches had broken "
            f"product links ({broken})."
        )

        return option

    def search_grocery_product(
        self,
        ingredient_name: str,
    ) -> GroceryOption:

        return self.get_grocery_option(
            ingredient_name
        )

    def get_grocery_list(
        self,
        items: list[dict],
    ) -> list[GroceryOption]:

        return [
            self.get_grocery_option(
                item["ingredient_name"],
                item.get("quantity"),
                item.get("unit"),
                item.get("ingredient_id"),
            )
            for item in items
        ]


# ---------------------------------------------------------------------
# Basket summary
# ---------------------------------------------------------------------

def basket_summary(
    options: list[GroceryOption],
) -> dict:
    """
    Summarise grocery purchase costs.

    estimated_total is retained for backwards compatibility.

    known_subtotal contains only grocery items whose final purchase
    cost could be calculated.

    cost_complete is False whenever one or more required grocery
    items have an unknown final cost.
    """

    priced = [
        option
        for option in options
        if option.total_cost is not None
    ]

    missing_price = [
        option.ingredient_name
        for option in options
        if option.price_per_package is None
    ]

    missing_package_calc = [
        option.ingredient_name
        for option in options
        if (
            option.price_per_package
            is not None
            and
            option.total_cost
            is None
        )
    ]

    # Any item without a final purchase cost makes the complete basket
    # cost unknown.
    unknown_cost_items = [
        option.ingredient_name
        for option in options
        if option.total_cost is None
    ]

    known_subtotal = round(
        sum(
            option.total_cost
            for option in priced
        ),
        2,
    )

    return {
        # Existing fields
        "items": len(options),
        "priced_items": len(priced),
        "estimated_total": known_subtotal,
        "missing_price": missing_price,
        "missing_package_calc": (
            missing_package_calc
        ),

        # Budget-reasoning fields
        "known_subtotal": known_subtotal,
        "unknown_cost_items": (
            unknown_cost_items
        ),
        "cost_complete": (
            len(unknown_cost_items) == 0
        ),
    }


# ---------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------

_default_service: GroceryService | None = None


def _service() -> GroceryService:

    global _default_service

    if _default_service is None:
        _default_service = GroceryService()

    return _default_service


def search_grocery_product(
    ingredient_name: str,
) -> GroceryOption:

    return _service().search_grocery_product(
        ingredient_name
    )


def get_grocery_option(
    ingredient_name: str,
    required_quantity: float,
    unit: str,
    ingredient_id: str | None = None,
) -> GroceryOption:

    return _service().get_grocery_option(
        ingredient_name,
        required_quantity,
        unit,
        ingredient_id,
    )