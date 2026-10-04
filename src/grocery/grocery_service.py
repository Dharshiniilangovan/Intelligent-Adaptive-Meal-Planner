"""src/grocery/grocery_service.py

Turn grocery ingredients into buyable FairPrice grocery options.

The service:
- searches FairPrice through Tavily
- filters unrelated or unsafe results
- calculates package quantities and purchase costs where possible
- accepts the grocery_list dictionary produced by PantryService
- returns priced, incomplete, and missing grocery products
- keeps missing prices as None instead of zero

Other project features should normally use:

    from src.grocery.grocery_service import get_grocery_results

    result = get_grocery_results(grocery_list)
"""

import math
import re
import statistics
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import requests

from src.grocery.food_filter import (
    check_match,
    search_queries,
    words,
)
from src.grocery.tavily_client import (
    SearchError,
    TavilyGroceryClient,
)
from src.grocery.units import (
    parse_package,
    pretty,
    to_base,
)


# ---------------------------------------------------------------------
# Grocery configuration
# ---------------------------------------------------------------------

GROCERY_STORE = "fairprice"

MAX_ITEM_PRICE = 100.0

PRICE_OUTLIER_FACTOR = 3.0


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
    return datetime.now(
        timezone.utc
    ).isoformat(
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

    # matched | matched_minimum_package |
    # matched_no_quantity | no_match | error
    match_status: str = "no_match"

    # exact | approximate
    match_quality: str | None = None

    # Search query that produced the selected result
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
        self.client = (
            client
            or TavilyGroceryClient()
        )

        self.verify_links = verify_links

        self.cache_ttl = (
            cache_ttl_hours * 3600
        )

        self._search_cache: dict[
            str,
            tuple[float, list[dict]],
        ] = {}

        self._link_cache: dict[
            str,
            bool,
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
    # Search with cache
    # -----------------------------------------------------------------

    def _search(
        self,
        ingredient: str,
    ) -> list[dict]:

        key = " ".join(
            words(ingredient)
        )

        hit = self._search_cache.get(
            key
        )

        if (
            hit
            and
            time.time() - hit[0]
            < self.cache_ttl
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

        text = (
            f"{product.get('store', '')} "
            f"{product.get('merchant_id', '')} "
            f"{product.get('url', '')}"
        ).lower()

        return (
            GROCERY_STORE in text
        )

    # -----------------------------------------------------------------
    # Filter products
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
            if product.get(
                "country_code"
            ) not in (
                None,
                "SG",
            ):
                rejected[
                    "not sold in Singapore"
                ] += 1
                continue

            if product.get(
                "region"
            ) not in (
                None,
                "sg",
            ):
                rejected[
                    "not sold in Singapore"
                ] += 1
                continue

            # SGD only
            if product.get(
                "currency"
            ) != "SGD":
                rejected[
                    "not SGD"
                ] += 1
                continue

            # Out-of-stock products cannot be recommended
            if product.get(
                "in_stock"
            ) is False:
                rejected[
                    "out of stock"
                ] += 1
                continue

            # Local availability only
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

            # Product must have a usable price
            price = product.get(
                "price"
            )

            if price is None:
                rejected[
                    "missing price"
                ] += 1
                continue

            if not isinstance(
                price,
                (int, float),
            ):
                rejected[
                    "invalid price"
                ] += 1
                continue

            if price <= 0:
                rejected[
                    "invalid price"
                ] += 1
                continue

            if price > MAX_ITEM_PRICE:
                rejected[
                    "price too high for groceries"
                ] += 1
                continue

            # FairPrice only
            if not self._is_fairprice_product(
                product
            ):
                rejected[
                    "not FairPrice"
                ] += 1
                continue

            # Reject known invalid URLs
            bad_reason = None

            for regex, reason in (
                BAD_URL_PATTERNS
            ):
                if regex.search(
                    product.get("url")
                    or ""
                ):
                    bad_reason = reason
                    break

            if bad_reason:
                rejected[
                    bad_reason
                ] += 1
                continue

            # Check product relevance
            ok, quality = check_match(
                ingredient,
                product.get("title")
                or "",
            )

            if not ok:
                rejected[
                    quality
                ] += 1
                continue

            # Parse package size from title/page text
            package = (
                parse_package(
                    product.get("title")
                    or ""
                )
                or
                parse_package(
                    product.get("size_text")
                    or ""
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
    # Price outliers
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

            if (
                product.get("package")
                and
                product["package"][0] > 0
            )
        }

        if len(unit_prices) < 3:
            return valid

        median = statistics.median(
            unit_prices.values()
        )

        kept = []

        for product in valid:

            product_id = id(
                product
            )

            if (
                product_id in unit_prices
                and
                unit_prices[product_id]
                >
                PRICE_OUTLIER_FACTOR
                * median
            ):
                rejected[
                    "price outlier"
                ] += 1

            else:
                kept.append(
                    product
                )

        return kept

    # -----------------------------------------------------------------
    # Candidate quality
    # -----------------------------------------------------------------

    @staticmethod
    def _quality(
        product: dict,
    ) -> int:

        score = 0

        if (
            GroceryService
            ._is_fairprice_product(
                product
            )
        ):
            score += 2

        if product.get(
            "source_updated_at"
        ):
            score += 1

        if product.get(
            "package"
        ):
            score += 1

        return score

    # -----------------------------------------------------------------
    # Rank candidates
    # -----------------------------------------------------------------

    def _rank(
        self,
        valid: list[dict],
        need: tuple[
            float,
            str,
        ] | None,
    ) -> list[dict]:

        for product in valid:

            product[
                "packages"
            ] = None

            product[
                "total"
            ] = None

            package = product.get(
                "package"
            )

            # Exact package calculation when units match
            if (
                need
                and
                package
                and
                package[1] == need[1]
            ):

                product[
                    "packages"
                ] = max(
                    1,
                    math.ceil(
                        need[0]
                        / package[0]
                        - 1e-9
                    ),
                )

                product[
                    "total"
                ] = round(
                    product["packages"]
                    * product["price"],
                    2,
                )

        def exact_first(
            product: dict,
        ) -> int:

            return (
                0
                if product[
                    "match"
                ] == "exact"
                else 1
            )

        # Products with complete purchase calculation
        priced = sorted(
            (
                product
                for product
                in valid
                if product[
                    "total"
                ] is not None
            ),
            key=lambda product: (
                exact_first(
                    product
                ),
                product[
                    "total"
                ],
                -self._quality(
                    product
                ),
            ),
        )

        # Products where package calculation is incomplete
        others = sorted(
            (
                product
                for product
                in valid
                if product[
                    "total"
                ] is None
            ),
            key=lambda product: (
                exact_first(
                    product
                ),
                -self._quality(
                    product
                ),
                product[
                    "price"
                ],
            ),
        )

        return sorted(
            priced + others,
            key=exact_first,
        )

    # -----------------------------------------------------------------
    # Optional product link verification
    # -----------------------------------------------------------------

    def _link_ok(
        self,
        url: str | None,
    ) -> bool:

        if not url:
            return False

        if url not in self._link_cache:

            try:
                response = (
                    self._http.get(
                        url,
                        timeout=10,
                        allow_redirects=True,
                    )
                )

                gone = (
                    response.status_code
                    in (
                        404,
                        410,
                    )
                    or (
                        response.status_code
                        < 400
                        and
                        _SOFT_404.search(
                            response.text[
                                :50_000
                            ]
                        )
                    )
                )

                self._link_cache[
                    url
                ] = not gone

            except requests.RequestException:

                self._link_cache[
                    url
                ] = True

        return self._link_cache[
            url
        ]

    # -----------------------------------------------------------------
    # Search fallbacks
    # -----------------------------------------------------------------

    def _find_candidates(
        self,
        ingredient: str,
        need: tuple[
            float,
            str,
        ] | None = None,
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

        for query in search_queries(
            ingredient
        ):

            products = self._search(
                query
            )

            n_results += len(
                products
            )

            (
                valid,
                rejected_here,
            ) = self._filter(
                ingredient,
                products,
            )

            rejected.update(
                rejected_here
            )

            for product in valid:

                all_valid.setdefault(
                    product[
                        "product_id"
                    ],
                    product,
                )

            if (
                valid
                and
                used_query is None
            ):
                used_query = query

            # No quantity information:
            # an exact ingredient match is enough.
            if need is None:

                if any(
                    product[
                        "match"
                    ] == "exact"
                    for product
                    in valid
                ):
                    break

            # Quantity known:
            # continue searching for an exact compatible package.
            else:

                compatible_exact = any(
                    product[
                        "match"
                    ] == "exact"
                    and
                    product.get(
                        "package"
                    ) is not None
                    and
                    product[
                        "package"
                    ][1] == need[1]

                    for product
                    in valid
                )

                if compatible_exact:
                    break

        return (
            list(
                all_valid.values()
            ),
            rejected,
            n_results,
            used_query,
        )

    # -----------------------------------------------------------------
    # Single grocery option
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

        # Convert required quantity to base unit
        need = None

        if (
            required_quantity is not None
            and
            unit
        ):

            need = to_base(
                required_quantity,
                unit,
            )

            if need is None:
                option.note = (
                    f"unknown unit "
                    f"'{unit}'. "
                )

        # Search and filter products
        try:

            (
                valid,
                rejected,
                n_results,
                used_query,
            ) = self._find_candidates(
                ingredient_name,
                need,
            )

        except SearchError as exc:

            option.match_status = (
                "error"
            )

            option.note += (
                f"search failed: "
                f"{exc}"
            )

            return option

        # -------------------------------------------------------------
        # No reliable product
        # -------------------------------------------------------------

        if not valid:

            reasons = ", ".join(
                f"{reason} ({count})"
                for reason, count
                in rejected.most_common(
                    3
                )
            )

            if not reasons:
                reasons = (
                    "no search results"
                )

            option.note += (
                f"no reliable match "
                f"among {n_results} "
                f"results: {reasons}"
            )

            # Product and price remain None.
            return option

        option.search_query = (
            used_query
        )

        # -------------------------------------------------------------
        # Select best candidate
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
                    product.get(
                        "url"
                    )
                )
            ):
                broken += 1
                continue

            option.product_name = (
                product[
                    "title"
                ]
            )

            option.price_per_package = (
                product[
                    "price"
                ]
            )

            option.currency = (
                product[
                    "currency"
                ]
            )

            option.store = (
                product[
                    "store"
                ]
            )

            option.source_url = (
                product[
                    "url"
                ]
            )

            option.source_updated_at = (
                product.get(
                    "source_updated_at"
                )
            )

            option.match_quality = (
                product[
                    "match"
                ]
            )

            if (
                product[
                    "match"
                ]
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
            # Normal complete package calculation
            # ---------------------------------------------------------

            if (
                product[
                    "total"
                ]
                is not None
            ):

                option.packages_needed = (
                    product[
                        "packages"
                    ]
                )

                option.total_cost = (
                    product[
                        "total"
                    ]
                )

                option.match_status = (
                    "matched"
                )

            # ---------------------------------------------------------
            # Exact package calculation could not be completed
            # ---------------------------------------------------------

            else:

                try:
                    has_required_quantity = (
                        required_quantity
                        is not None
                        and
                        float(
                            required_quantity
                        ) > 0
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    has_required_quantity = (
                        False
                    )

                # -----------------------------------------------------
                # Ingredient needs purchasing and product price exists.
                #
                # Use one retail package as the minimum purchase.
                # -----------------------------------------------------

                if (
                    option.price_per_package
                    is not None
                    and
                    has_required_quantity
                ):

                    option.packages_needed = 1

                    option.total_cost = round(
                        float(
                            option.price_per_package
                        ),
                        2,
                    )

                    option.match_status = (
                        "matched_minimum_package"
                    )

                    if not package:

                        option.note += (
                            "exact package quantity could "
                            "not be calculated because "
                            "package size was not available; "
                            "using one retail package as the "
                            "minimum purchase."
                        )

                    elif need is None:

                        option.note += (
                            "required quantity could not "
                            "be converted; using one retail "
                            "package as the minimum purchase."
                        )

                    else:

                        option.note += (
                            f"unit mismatch "
                            f"(need {need[1]}, "
                            f"package in "
                            f"{package[1]}); "
                            f"using one retail package as "
                            f"the minimum purchase."
                        )

                # -----------------------------------------------------
                # No usable required quantity
                # -----------------------------------------------------

                else:

                    option.match_status = (
                        "matched_no_quantity"
                    )

                    option.note += (
                        "purchase quantity could "
                        "not be calculated."
                    )

            if broken:

                option.note += (
                    f" skipped {broken} "
                    f"product(s) with "
                    f"broken links."
                )

            option.note = (
                option.note.strip()
            )

            return option

        option.note += (
            f"all top matches had "
            f"broken product links "
            f"({broken})."
        )

        return option

    # -----------------------------------------------------------------
    # Single ingredient convenience method
    # -----------------------------------------------------------------

    def search_grocery_product(
        self,
        ingredient_name: str,
    ) -> GroceryOption:

        return self.get_grocery_option(
            ingredient_name
        )

    # -----------------------------------------------------------------
    # Dynamic grocery-list input
    # -----------------------------------------------------------------

    def get_grocery_list(
        self,
        items: list[dict] | dict,
    ) -> list[GroceryOption]:
        """
        Search and price every grocery item.

        Accepts the dictionary produced directly by PantryService:

            {
                "rice": {
                    "ingredient_id": "ING001",
                    "quantity": 500,
                    "unit": "g"
                }
            }

        Existing list format is also supported.
        """

        options = []

        # -------------------------------------------------------------
        # PantryService dictionary format
        # -------------------------------------------------------------

        if isinstance(
            items,
            dict,
        ):

            for (
                ingredient_name,
                item,
            ) in items.items():

                option = (
                    self.get_grocery_option(
                        ingredient_name=(
                            ingredient_name
                        ),
                        required_quantity=(
                            item.get(
                                "quantity"
                            )
                        ),
                        unit=(
                            item.get(
                                "unit"
                            )
                        ),
                        ingredient_id=(
                            item.get(
                                "ingredient_id"
                            )
                        ),
                    )
                )

                options.append(
                    option
                )

            return options

        # -------------------------------------------------------------
        # Existing list format
        # -------------------------------------------------------------

        if isinstance(
            items,
            list,
        ):

            for item in items:

                option = (
                    self.get_grocery_option(
                        ingredient_name=(
                            item[
                                "ingredient_name"
                            ]
                        ),
                        required_quantity=(
                            item.get(
                                "quantity"
                            )
                        ),
                        unit=(
                            item.get(
                                "unit"
                            )
                        ),
                        ingredient_id=(
                            item.get(
                                "ingredient_id"
                            )
                        ),
                    )
                )

                options.append(
                    option
                )

            return options

        raise TypeError(
            "items must be a PantryService grocery-list "
            "dictionary or a list of grocery item dictionaries"
        )

    # -----------------------------------------------------------------
    # Main interface for other project features
    # -----------------------------------------------------------------

    def get_grocery_results(
        self,
        items: list[dict] | dict,
    ) -> dict:
        """
        Search all required grocery items and return a clean
        dictionary for other project features.
        """

        options = self.get_grocery_list(
            items
        )

        return grocery_summary(
            options
        )


# ---------------------------------------------------------------------
# Existing grocery basket summary
# ---------------------------------------------------------------------

def basket_summary(
    options: list[GroceryOption],
) -> dict:
    """
    Summarise grocery purchase results.

    Keeps the original compatibility fields used by the
    budget layer while also supporting the current grocery logic.
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
            option.price_per_package is not None
            and option.total_cost is None
        )
    ]

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
        "items": len(options),

        "priced_items": len(priced),

        "estimated_total": known_subtotal,

        "missing_price": missing_price,

        "missing_package_calc": missing_package_calc,

        # Compatibility with BudgetService
        "known_subtotal": known_subtotal,

        "unknown_cost_items": unknown_cost_items,

        "cost_complete": (
            len(unknown_cost_items) == 0
        ),
    }

# ---------------------------------------------------------------------
# Main grocery result returned to other project features
# ---------------------------------------------------------------------

def grocery_summary(
    options: list[GroceryOption],
) -> dict:
    """
    Build the grocery result returned to other project features.

    priced_products:
        Product and purchase price are available.

        This includes:
        - exact package calculations
        - minimum one-package purchases when units cannot be
          directly compared

    incomplete_products:
        Product and price were found, but a usable purchase
        quantity could still not be determined.

    missing_products:
        No reliable available FairPrice product/price was found.
    """

    priced_products = []
    incomplete_products = []
    missing_products = []

    for option in options:

        item = {
            "ingredient_id":
                option.ingredient_id,

            "ingredient":
                option.ingredient_name,

            "required_quantity":
                option.required_quantity,

            "required_unit":
                option.required_unit,

            "product_name":
                option.product_name,

            "package_quantity":
                option.package_quantity,

            "package_unit":
                option.package_unit,

            "packages_needed":
                option.packages_needed,

            "price_per_package":
                option.price_per_package,

            "total_cost":
                option.total_cost,

            "currency":
                option.currency,

            "store":
                option.store,

            "source_url":
                option.source_url,

            "match_status":
                option.match_status,

            "match_quality":
                option.match_quality,

            "search_query":
                option.search_query,

            "note":
                option.note,
        }

        # -------------------------------------------------------------
        # Missing product / missing price
        # -------------------------------------------------------------

        if (
            option.product_name
            is None
            or
            option.price_per_package
            is None
        ):

            missing_products.append(
                item
            )

        # -------------------------------------------------------------
        # Product/price found but purchase value still incomplete
        # -------------------------------------------------------------

        elif (
            option.total_cost
            is None
        ):

            incomplete_products.append(
                item
            )

        # -------------------------------------------------------------
        # Usable purchase price
        # -------------------------------------------------------------

        else:

            priced_products.append(
                item
            )

    return {
        "items_requested":
            len(options),

        "products_priced":
            len(
                priced_products
            ),

        "products_incomplete":
            len(
                incomplete_products
            ),

        "products_missing":
            len(
                missing_products
            ),

        "priced_products":
            priced_products,

        "incomplete_products":
            incomplete_products,

        "missing_products":
            missing_products,
    }


# ---------------------------------------------------------------------
# Terminal display helper
# ---------------------------------------------------------------------

def print_grocery_results(
    result: dict,
) -> None:
    """
    Print a concise grocery result for development/testing.

    The complete result dictionary is still returned by
    get_grocery_results() for use by other project features.
    """

    print()
    print("=" * 70)
    print("FAIRPRICE GROCERY RESULTS")
    print("=" * 70)
    print()

    found_count = (
        result["products_priced"]
        + result["products_incomplete"]
    )

    print(
        f"Found: {found_count} / "
        f"{result['items_requested']}"
    )

    print(
        f"Missing: "
        f"{result['products_missing']}"
    )

    # -------------------------------------------------------------
    # Products found
    # -------------------------------------------------------------

    all_found = (
        result["priced_products"]
        + result["incomplete_products"]
    )

    if all_found:
        print()
        print("PRODUCTS FOUND")
        print("-" * 70)

        for item in all_found:

            ingredient = item["ingredient"]

            product = (
                item["product_name"]
                or "NA"
            )

            # -----------------------------------------------------
            # Package size
            # -----------------------------------------------------

            package_quantity = item[
                "package_quantity"
            ]

            package_unit = item[
                "package_unit"
            ]

            if (
                package_quantity is not None
                and
                package_unit is not None
            ):
                package_text = (
                    f"{package_quantity:g} "
                    f"{package_unit}"
                )
            else:
                package_text = "NA"

            # -----------------------------------------------------
            # Price
            # -----------------------------------------------------

            price = item[
                "price_per_package"
            ]

            if price is not None:
                price_text = (
                    f"S${price:.2f}"
                )
            else:
                price_text = "NA"

            # -----------------------------------------------------
            # Purchase price
            # -----------------------------------------------------

            total = item[
                "total_cost"
            ]

            if total is not None:
                total_text = (
                    f"S${total:.2f}"
                )
            else:
                total_text = "NA"

            # -----------------------------------------------------
            # Minimum-package marker
            # -----------------------------------------------------

            status = item[
                "match_status"
            ]

            minimum_marker = (
                " *"
                if status
                == "matched_minimum_package"
                else ""
            )

            # -----------------------------------------------------
            # Print product
            # -----------------------------------------------------

            print(
                f"{ingredient}"
            )

            print(
                f"  Product: "
                f"{product}"
            )

            print(
                f"  Package size: "
                f"{package_text}"
            )

            print(
                f"  Price: "
                f"{price_text}"
            )

            print(
                f"  Purchase price: "
                f"{total_text}"
                f"{minimum_marker}"
            )

            print()

    # -------------------------------------------------------------
    # Minimum-package explanation
    # -------------------------------------------------------------

    has_minimum_package = any(
        item["match_status"]
        == "matched_minimum_package"
        for item in result[
            "priced_products"
        ]
    )

    if has_minimum_package:
        print(
            "* Minimum 1 package used where "
            "recipe and product units could not "
            "be directly compared."
        )

        print()

    # -------------------------------------------------------------
    # Total purchase price
    # -------------------------------------------------------------

    total_purchase = round(
        sum(
            item["total_cost"]
            for item in result[
                "priced_products"
            ]
            if item["total_cost"]
            is not None
        ),
        2,
    )

    print(
        f"Total grocery purchase: "
        f"S${total_purchase:.2f}"
    )

    # -------------------------------------------------------------
    # Missing products
    # -------------------------------------------------------------

    print()
    print("MISSING PRODUCTS")
    print("-" * 70)

    if not result[
        "missing_products"
    ]:
        print("None")

    else:

        for item in result[
            "missing_products"
        ]:

            print(
                f"- {item['ingredient']}"
            )


# ---------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------

_default_service: GroceryService | None = None


def _service() -> GroceryService:
    """
    Return the shared GroceryService instance.
    """

    global _default_service

    if _default_service is None:
        _default_service = GroceryService()

    return _default_service


def search_grocery_product(
    ingredient_name: str,
) -> GroceryOption:
    """
    Search for one grocery product.
    """

    return _service().search_grocery_product(
        ingredient_name
    )


def get_grocery_option(
    ingredient_name: str,
    required_quantity: float,
    unit: str,
    ingredient_id: str | None = None,
) -> GroceryOption:
    """
    Get one priced grocery option.
    """

    return _service().get_grocery_option(
        ingredient_name,
        required_quantity,
        unit,
        ingredient_id,
    )


def get_grocery_results(
    items: list[dict] | dict,
) -> dict:
    """
    Main interface for other project modules.

    Input:
        grocery_list produced by PantryService

    Output:
        {
            "items_requested": ...,
            "products_priced": ...,
            "products_incomplete": ...,
            "products_missing": ...,
            "priced_products": [...],
            "incomplete_products": [...],
            "missing_products": [...]
        }
    """

    return _service().get_grocery_results(
        items
    )


# ---------------------------------------------------------------------
# Manual test
# ---------------------------------------------------------------------

# if __name__ == "__main__":

#     # Sample input only for manually checking GroceryService.
#     #
#     # This is NOT used by the real application.
#     # The real application passes the dynamic grocery_list produced
#     # by PantryService into get_grocery_results().

#     test_grocery_list = {
#         "sour cream": {
#             "ingredient_id": "ING3248",
#             "quantity": 1.5,
#             "unit": "tablespoon",
#         },

#         "cheddar cheese": {
#             "ingredient_id": "ING0658",
#             "quantity": 1.5,
#             "unit": "tablespoon",
#         },

#         "cilantro": {
#             "ingredient_id": "ING0870",
#             "quantity": 1.0,
#             "unit": "sprig",
#         },

#         "dijon mustard": {
#             "ingredient_id": "ING1203",
#             "quantity": 1.0,
#             "unit": "pinch",
#         },
#     }

#     result = get_grocery_results(
#         test_grocery_list
#     )

#     print_grocery_results(
#         result
#     )