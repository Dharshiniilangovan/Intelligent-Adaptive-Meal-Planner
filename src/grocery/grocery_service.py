"""src/grocery/grocery_service.py



Turn grocery ingredients into buyable FairPrice grocery options.



Responsibilities:

- receive missing ingredients from PantryService

- search FairPrice through TavilyGroceryClient

- validate ingredient/product relevance

- parse retail package quantities

- calculate packages required

- choose the best valid purchase

- preserve UNKNOWN/incomplete information instead of inventing values

- expose grocery-pricing completeness to the reasoning/budget layer



Other project modules should normally use:



    from src.grocery.grocery_service import get_grocery_results



    result = get_grocery_results(grocery_list)

"""



from __future__ import annotations



import math

import re

import statistics

import time



from collections import Counter

from dataclasses import asdict, dataclass, field

from datetime import datetime, timezone



import requests



from src.grocery.recipe_weight_estimator import estimate_recipe_weight




from src.grocery.food_filter import (
    check_match,
    search_queries,
    clean_ingredient,
)




from src.grocery.tavily_client import (

    SearchError,

    TavilyGroceryClient,

)



from src.grocery.units import (

    SMALL_MEASURES,

    parse_package,

    pretty,

    to_base,

)

from src.grocery.product_category_validator import (
    is_non_food_product,
)



from src.grocery.product_matcher import match_product
from src.grocery.semantic_product_matcher import validate_product



from src.grocery.ingredient_conversions import estimate_ingredient_mass





# ---------------------------------------------------------------------

# Configuration

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

        "known fake FairPrice listing pattern",

    ),

]





_SOFT_404 = re.compile(

    r"<title>[^<]*(404|not found|can.t (be )?found)[^<]*</title>",

    re.IGNORECASE,

)





# ---------------------------------------------------------------------

# Helpers

# ---------------------------------------------------------------------



def _now() -> str:

    return datetime.now(

        timezone.utc

    ).isoformat(

        timespec="seconds"

    )





def _positive_quantity(value) -> bool:

    """Return True when value is a usable positive quantity."""



    try:

        return value is not None and float(value) > 0

    except (TypeError, ValueError):

        return False





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

    estimated_total_cost: float | None = None



    currency: str | None = None

    store: str | None = None



    source_url: str | None = None

    source_updated_at: str | None = None



    minimum_package_cost: float | None = None

    purchase_basis: str | None = None



    estimated_required_quantity: float | None = None

    estimated_required_unit: str | None = None

    quantity_estimated: bool = False



    date_collected: str = field(

        default_factory=_now

    )



    # matched

    # matched_minimum_package

    # matched_no_quantity

    # no_match

    # error

    match_status: str = "no_match"



    # exact

    # strong

    # approximate

    match_quality: str | None = None

    purchase_channel: str | None = None



    search_query: str | None = None



    note: str = ""



    def to_dict(self) -> dict:

        return asdict(self)





# ---------------------------------------------------------------------

# Grocery service

# ---------------------------------------------------------------------



from src.cache.cache_service import PersistentCache, cache_key


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



        self.persistent_cache = PersistentCache()

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

    # Search + cache

    # -----------------------------------------------------------------



    
    def _search(
        self,
        query: str,
    ) -> list[dict]:
        """
        Search grocery products with an in-memory cache.

        Repeated equivalent queries reuse cached results
        until the cache TTL expires.
        """

        # Normalize whitespace and capitalization.
        # Do not remove ingredient identity words.
        key = " ".join(
            str(query or "").lower().split()
        )

        if not key:
            return []

        hit = self._search_cache.get(key)
        if hit is not None and time.time() - hit[0] < self.cache_ttl:
            print(f"[MEMORY TAVILY CACHE HIT] {query}")
            return hit[1]

        persistent_key = cache_key("tavily_search_v1", {"query": key, "client": type(self.client).__name__})
        cached = self.persistent_cache.get("tavily_search_v1", persistent_key)
        if isinstance(cached, list):
            print(f"[SQLITE TAVILY CACHE HIT] {query}")
            self._search_cache[key] = (time.time(), cached)
            return cached

        print(f"[LIVE TAVILY SEARCH] {query}")
        products = self.client.search(query)
        if isinstance(products, list) and products:
            self._search_cache[key] = (time.time(), products)
            self.persistent_cache.set("tavily_search_v1", persistent_key, products, self.cache_ttl)
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



        return GROCERY_STORE in text



    # -----------------------------------------------------------------

    # Product filtering

    # -----------------------------------------------------------------



   
    def _filter(
        self,
        ingredient: str,
        products: list[dict],
    ) -> tuple[list[dict], Counter]:
        """
        Validate FairPrice grocery products.

        Checks:
        1. Singapore availability
        2. SGD price
        3. FairPrice product source
        4. Valid product URL
        5. Ingredient/product compatibility
        6. Semantic product equivalence
        7. Food filtering
        8. Package extraction
        9. Price outliers

        Recipe descriptions are normalized before
        ingredient matching.

        The original ingredient remains unchanged
        in GroceryOption and agent output.
        """

        valid = []
        rejected = Counter()

        # -----------------------------------------------------
        # Normalize recipe ingredient description
        # -----------------------------------------------------

        cleaned_tokens = clean_ingredient(ingredient)

        matching_ingredient = (
            " ".join(cleaned_tokens)
            if cleaned_tokens
            else str(ingredient or "").strip()
        )

        for product in products:

            # -------------------------------------------------
            # Singapore only
            # -------------------------------------------------

            if product.get("country_code") not in (
                None,
                "SG",
            ):
                rejected["not sold in Singapore"] += 1
                continue

            if product.get("region") not in (
                None,
                "sg",
            ):
                rejected["not sold in Singapore"] += 1
                continue

            # -------------------------------------------------
            # SGD only
            # -------------------------------------------------

            if product.get("currency") != "SGD":
                rejected["not SGD"] += 1
                continue

            # -------------------------------------------------
            # Availability
            # -------------------------------------------------

            if product.get("in_stock") is False:
                rejected["out of stock"] += 1
                continue

            if product.get("availability") not in (
                None,
                "local",
            ):
                rejected["not locally available"] += 1
                continue

            # -------------------------------------------------
            # Price validation
            # -------------------------------------------------

            price = product.get("price")

            if price is None:
                rejected["missing price"] += 1
                continue

            if (
                not isinstance(price, (int, float))
                or isinstance(price, bool)
                or not math.isfinite(price)
                or price <= 0
            ):
                rejected["invalid price"] += 1
                continue

            if price > MAX_ITEM_PRICE:
                rejected[
                    "price too high for groceries"
                ] += 1
                continue

            # -------------------------------------------------
            # FairPrice only
            # -------------------------------------------------

            if not self._is_fairprice_product(product):
                rejected["not FairPrice"] += 1
                continue

            # -------------------------------------------------
            # Known invalid URLs
            # -------------------------------------------------

            url = product.get("url") or ""

            bad_reason = None

            for regex, reason in BAD_URL_PATTERNS:
                if regex.search(url):
                    bad_reason = reason
                    break

            if bad_reason:
                rejected[bad_reason] += 1
                continue

            # -------------------------------------------------
            # Product title
            # -------------------------------------------------

            title = product.get("title") or ""

            if not title:
                rejected["missing product title"] += 1
                continue


            if is_non_food_product(title, url):
                rejected["non-food product"] += 1
                continue
            # -------------------------------------------------
            # Product matcher
            # -------------------------------------------------

            match_result = match_product(
                ingredient_name=matching_ingredient,
                product_title=title,
            )

            if not match_result.accepted:
                rejected[match_result.reason] += 1
                continue

            # -------------------------------------------------
            # Semantic product equivalence
            # -------------------------------------------------

            equivalence = validate_product(
                matching_ingredient,
                title,
                url,
            )

            if not equivalence.accepted:
                rejected[equivalence.reason] += 1
                continue

            # -------------------------------------------------
            # Food filter
            # -------------------------------------------------

            ok, quality = check_match(
                ingredient=matching_ingredient,
                title=title,
                url=url,
                content=(
                    product.get("search_content")
                    or ""
                ),
                size_text=(
                    product.get("size_text")
                    or ""
                ),
            )

            if not ok:
                rejected[quality] += 1
                continue

            # Preserve conservative match classification.
            if match_result.match_type == "substitute":
                quality = "substitute"

            elif match_result.match_type == "partial":
                quality = "partial"

            # -------------------------------------------------
            # Package extraction
            # -------------------------------------------------

            package = (
                parse_package(product.get("title") or "")
                or parse_package(product.get("url") or "")
                or parse_package(
                    product.get("size_text") or ""
                )
                or parse_package(
                    product.get("product_text") or ""
                )
            )

            # -------------------------------------------------
            # Purchasing availability
            # -------------------------------------------------

            delivery_available = product.get(
                "delivery_available"
            )

            if delivery_available is False:
                purchase_channel = "in_store_only"

            elif delivery_available is True:
                purchase_channel = "delivery_or_in_store"

            else:
                purchase_channel = "availability_unverified"

            valid.append({
                **product,
                "match": quality,
                "package": package,
                "purchase_channel": purchase_channel,
            })

        return (
            self._drop_price_outliers(
                valid,
                rejected,
            ),
            rejected,
        )



    # -----------------------------------------------------------------

    # Price outlier handling

    # -----------------------------------------------------------------



    @staticmethod

    def _drop_price_outliers(

        valid: list[dict],

        rejected: Counter,

    ) -> list[dict]:



        """

        Remove extreme unit-price outliers only when products use the

        same normalized package base unit.



        Comparing $/g with $/ml or $/pcs would be meaningless, so

        medians are calculated separately for each package unit.

        """



        groups: dict[

            str,

            list[tuple[dict, float]],

        ] = {}



        for product in valid:



            package = product.get(

                "package"

            )



            price = product.get(

                "price"

            )



            if (

                not package

                or price is None

                or package[0] <= 0

            ):

                continue



            quantity, unit = package



            unit_price = (

                float(price)

                / float(quantity)

            )



            groups.setdefault(

                unit,

                [],

            ).append(

                (

                    product,

                    unit_price,

                )

            )



        rejected_ids = set()



        for entries in groups.values():



            # Too little evidence to safely call something an outlier.

            if len(entries) < 3:

                continue



            values = [

                unit_price

                for _, unit_price

                in entries

            ]



            median = statistics.median(

                values

            )



            if median <= 0:

                continue



            for product, unit_price in entries:



                if (

                    unit_price

                    > PRICE_OUTLIER_FACTOR

                    * median

                ):

                    rejected_ids.add(

                        id(product)

                    )



                    rejected[

                        "price outlier"

                    ] += 1



        return [

            product

            for product in valid

            if id(product)

            not in rejected_ids

        ]



    # -----------------------------------------------------------------

    # Candidate source quality

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



        if product.get(

            "package"

        ):

            score += 2



        if product.get(

            "product_text"

        ):

            score += 1



        if product.get(

            "search_content"

        ):

            score += 1



        return score



    # -----------------------------------------------------------------

    # Candidate ranking

    # -----------------------------------------------------------------





    
    def _rank(
        self,
        valid: list[dict],
        need: tuple[float, str] | None,
        estimated_need: tuple[float, str] | None = None,
        allow_minimum_package: bool = False,
    ) -> list[dict]:
        """
        Rank validated grocery products.

        Purchase calculation priority:
        1. Exact compatible quantity
        2. Recipe-specific estimated quantity
        3. One-package shopping assumption
        4. Unverified when fallback is not allowed

        Minimum-package purchases are assumptions,
        not verified quantity coverage.
        """

        MATCH_RANK = {
            "exact": 0,
            "strong": 1,
            "substitute": 2,
            "approximate": 3,
            "partial": 4,
        }

        for product in valid:
            product["packages"] = None
            product["total"] = None
            product["excess"] = None
            product["purchase_basis"] = None
            product["minimum_package_cost"] = None

            package = product.get("package")
            price = product.get("price")

            if price is None:
                continue

            try:
                price = float(price)
            except (TypeError, ValueError):
                continue

            if not math.isfinite(price) or price <= 0:
                continue

            product["minimum_package_cost"] = round(price, 2)

            # Exact quantity calculation.
            if (
                need is not None
                and package is not None
                and package[0] > 0
                and package[1] == need[1]
            ):
                packages = max(
                    1,
                    math.ceil(need[0] / package[0] - 1e-9),
                )

                product["packages"] = packages
                product["total"] = round(packages * price, 2)
                product["excess"] = max(
                    0.0,
                    packages * package[0] - need[0],
                )
                product["purchase_basis"] = "exact_quantity"

            # Ingredient-specific estimated quantity.
            elif (
                estimated_need is not None
                and package is not None
                and package[0] > 0
                and package[1] == estimated_need[1]
            ):
                packages = max(
                    1,
                    math.ceil(
                        estimated_need[0] / package[0] - 1e-9
                    ),
                )

                product["packages"] = packages
                product["total"] = round(packages * price, 2)
                product["excess"] = max(
                    0.0,
                    packages * package[0] - estimated_need[0],
                )
                product["purchase_basis"] = "estimated_quantity"

            # Minimum retail package fallback.
            elif allow_minimum_package:
                product["packages"] = 1
                product["total"] = round(price, 2)
                product["purchase_basis"] = "minimum_retail_package"

            else:
                product["purchase_basis"] = "unverified_quantity"

        def rank_key(product: dict):
            match_rank = MATCH_RANK.get(
                product.get("match"),
                99,
            )

            basis = product.get("purchase_basis")

            quantity_rank = {
                "exact_quantity": 0,
                "estimated_quantity": 1,
                "minimum_retail_package": 2,
                "unverified_quantity": 3,
            }.get(basis, 4)

            total = product.get("total")
            total_rank = (
                float(total)
                if total is not None
                else float("inf")
            )

            package = product.get("package")

            # For unresolved quantities, prefer a smaller
            # retail package when comparable package units
            # are available. Otherwise prefer lower cost.
            package_rank = (
                float(package[0])
                if (
                    basis == "minimum_retail_package"
                    and package is not None
                    and package[0] > 0
                )
                else float("inf")
            )

            excess = product.get("excess")
            excess_rank = (
                float(excess)
                if excess is not None
                else float("inf")
            )

            return (
                match_rank,
                quantity_rank,
                total_rank,
                excess_rank,
                -self._quality(product),
            )

        return sorted(valid, key=rank_key)




    # -----------------------------------------------------------------

    # Optional link verification

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

                    in (

                        404,

                        410,

                    )

                    or (

                        response.status_code

                        < 400

                        and _SOFT_404.search(

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



                # Network verification failure should not automatically

                # invalidate an otherwise usable Tavily result.

                self._link_cache[

                    url

                ] = True



        return self._link_cache[

            url

        ]



    # -----------------------------------------------------------------

    # Candidate collection

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



        """

        Run all safe ingredient queries and collect unique valid products.



        food_filter.search_queries() is responsible for preserving the

        ingredient identity. GroceryService deliberately does not create

        single-word fallback queries itself.

        """



        all_valid: dict[

            str,

            dict,

        ] = {}



        rejected = Counter()



        n_results = 0

        used_query = None



        queries = search_queries(

            ingredient

        )



        for query in queries:



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



                product_id = (

                    product.get(

                        "product_id"

                    )

                    or product.get(

                        "url"

                    )

                )



                if not product_id:

                    continue



                if (

                    product_id

                    not in all_valid

                ):

                    all_valid[

                        product_id

                    ] = product



            if (

                valid

                and used_query is None

            ):

                used_query = query



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

        recipe_id: str | None = None,

    ) -> GroceryOption:



        option = GroceryOption(

            ingredient_id=ingredient_id,

            ingredient_name=ingredient_name,

            required_quantity=required_quantity,

            required_unit=unit,

        )



        # -------------------------------------------------------------

        # Normalize recipe quantity

        # -------------------------------------------------------------



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



                option.note += (

                    f"required unit '{unit}' "

                    "cannot be converted to an exact "

                    "package quantity; minimum retail "

                    "purchase will be used when a valid "

                    "product is found. "

                )





        # -------------------------------------------------------------

        # Ingredient-specific estimated quantity

        #

        # Keep this separate from "need" so _rank()

        # does not mistake it for an exact conversion.

        # -------------------------------------------------------------





        # -------------------------------------------------------------

        # Estimated ingredient weight

        #

        # Priority:

        # 1. Recipe-specific source weight

        # 2. Supported ingredient-specific culinary conversion

        #

        # Never replace the exact "need" variable.

        # -------------------------------------------------------------



        estimated_need = None



        if recipe_id is not None:

            estimated_need = estimate_recipe_weight(

                recipe_id=recipe_id,

                ingredient_name=ingredient_name,

                quantity=required_quantity,

                unit=unit,

            )



        if estimated_need is None:

            estimated_need = estimate_ingredient_mass(

                ingredient_name=ingredient_name,

                quantity=required_quantity,

                unit=unit,

            )



        # Generic recipe pieces are not directly comparable to retail mass.
        # Use the ingredient-specific estimate, retaining estimated status.
        if (
            need is not None
            and need[1] == "pcs"
            and estimated_need is not None
            and estimated_need[1] == "g"
        ):
            need = None

        if estimated_need is not None:

            option.estimated_required_quantity = (

                estimated_need[0]

            )



            option.estimated_required_unit = (

                estimated_need[1]

            )



            option.quantity_estimated = True





        # -------------------------------------------------------------

        # Search

        # -------------------------------------------------------------



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

                f"search failed: {exc}"

            )



            option.note = (

                option.note.strip()

            )



            return option



        # -------------------------------------------------------------

        # No reliable match

        # -------------------------------------------------------------



        if not valid:



            reasons = ", ".join(

                f"{reason} ({count})"

                for reason, count

                in rejected.most_common(3)

            )



            if not reasons:

                reasons = "no search results"



            option.match_status = (

                "no_match"

            )



            option.note += (

                f"no reliable match among "

                f"{n_results} result(s): "

                f"{reasons}"

            )



            option.note = (

                option.note.strip()

            )



            return option



        option.search_query = (

            used_query

        )



        # -------------------------------------------------------------

        # Rank + choose

        # -------------------------------------------------------------





        
        normalized_unit = (
            str(unit).strip().lower()
            if unit is not None
            else ""
        )

        # Missing, invalid, or unsupported recipe units
        # can use one retail package as a shopping
        # assumption when no reliable conversion exists.
        #
        # Exact and estimated conversions are still
        # evaluated first inside _rank().

        allow_minimum_package = (
            need is None
            or estimated_need is None
        )

        # A known positive requirement with a usable
        # base unit may still be incompatible with the
        # retail package. In that case, _rank() will
        # attempt exact/estimated calculations first,
        # then use one retail package as an assumption.
        #
        # Invalid or negative numeric requirements
        # must not automatically become valid purchases.

        if required_quantity is not None:
            try:
                quantity_value = float(required_quantity)
            except (TypeError, ValueError):
                quantity_value = None

            if (
                quantity_value is not None
                and (
                    not math.isfinite(quantity_value)
                    or quantity_value <= 0
                )
            ):
                allow_minimum_package = False

        if normalized_unit == "to taste":
            allow_minimum_package = True

        ranked = self._rank(

            valid,

            need,

            estimated_need=estimated_need,

            allow_minimum_package=allow_minimum_package,

        )





        # Prefer products with a complete purchase cost.

        # Preserve the original ranking within each group.

        ranked = sorted(

            ranked,

            key=lambda product: (

                product.get("total") is None

            ),

        )



        broken = 0



        for product in ranked[:10]:



            if (

                self.verify_links

                and not self._link_ok(

                    product.get(

                        "url"

                    )

                )

            ):



                broken += 1

                continue



            # ---------------------------------------------------------

            # Product identity

            # ---------------------------------------------------------



            option.product_name = (

                product.get(

                    "title"

                )

            )



            option.price_per_package = (

                product.get(

                    "price"

                )

            )



            option.currency = (

                product.get(

                    "currency"

                )

            )



            option.store = (

                product.get(

                    "store"

                )

            )



            option.source_url = (

                product.get(

                    "url"

                )

            )



            option.source_updated_at = (

                product.get(

                    "source_updated_at"

                )

            )



            option.match_quality = (

                product.get(

                    "match"

                )

            )

            option.purchase_channel = (

                product.get("purchase_channel")

            )



            # ---------------------------------------------------------

            # Package

            # ---------------------------------------------------------



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

            # Purchase

            # ---------------------------------------------------------



            purchase_basis = (

                product.get(

                    "purchase_basis"

                )

            )



            option.purchase_basis = purchase_basis



            option.minimum_package_cost = (

                product.get("minimum_package_cost")

            )



            # ---------------------------------------------------------

            # Estimated quantity purchase

            #

            # Preserve the estimate separately.

            # Do not classify it as a verified total.

            # ---------------------------------------------------------



            if purchase_basis == "estimated_quantity":



                option.packages_needed = product.get("packages")



                option.estimated_total_cost = product.get("total")



                option.total_cost = None



                option.match_status = "matched_estimated_quantity"



                option.note += (

                    "purchase quantity calculated using an "

                    "approximate ingredient-specific conversion; "

                    "cost is an estimate, not a verified "

                    "quantity calculation. "

                )





            if (

                purchase_basis != "estimated_quantity"

                and product.get("total") is not None

            ):



                option.packages_needed = (

                    product.get(

                        "packages"

                    )

                )



                option.total_cost = (

                    product.get(

                        "total"

                    )

                )



                if (

                    purchase_basis

                    == "exact_quantity"

                ):



                    option.match_status = (

                        "matched"

                    )



                else:



                    option.match_status = (

                        "matched_minimum_package"

                    )



                    if not package:



                        option.note += (

                            "package size could not be "

                            "verified; using one valid "

                            "retail package as the minimum "

                            "purchase. "

                        )



                    elif need is None:



                        option.note += (

                            "recipe quantity cannot be "

                            "converted exactly to the retail "

                            "package unit; using one retail "

                            "package as the minimum purchase. "

                        )



                    else:



                        option.note += (

                            f"unit mismatch "

                            f"(need {need[1]}, "

                            f"package in {package[1]}); "

                            f"using one retail package as "

                            f"the minimum purchase. "

                        )



            # ---------------------------------------------------------

            # Should rarely occur because ranked products with prices

            # receive a minimum-retail-package calculation.

            # ---------------------------------------------------------



            elif purchase_basis == "estimated_quantity":

                pass



            elif _positive_quantity(required_quantity):



                option.match_status = (

                    "matched_no_quantity"

                )



                option.note += (

                    "valid product and price found, "

                    "but purchase quantity could not "

                    "be determined. "

                )



            else:



                option.match_status = (

                    "matched_no_quantity"

                )



                option.note += (

                    "required recipe quantity is missing "

                    "or invalid. "

                )



            # ---------------------------------------------------------

            # Match quality note

            # ---------------------------------------------------------



            if option.match_quality in (

                "approximate",

                "partial",

            ):

                option.note += (

                    "product is an approximate "

                    "ingredient match. "

                )



            elif option.match_quality == "substitute":

                option.note += (

                    "product is a possible substitute "

                    "rather than an exact ingredient match. "

                )



            if broken:



                option.note += (

                    f"skipped {broken} product(s) "

                    f"with broken links. "

                )



            option.note = (

                option.note.strip()

            )



            return option



        # -------------------------------------------------------------

        # Every ranked candidate failed link verification

        # -------------------------------------------------------------



        option.match_status = (

            "no_match"

        )



        option.note += (

            f"all top candidate product links "

            f"failed verification ({broken})."

        )



        option.note = (

            option.note.strip()

        )



        return option



    # -----------------------------------------------------------------

    # Single ingredient convenience

    # -----------------------------------------------------------------



    def search_grocery_product(

        self,

        ingredient_name: str,

    ) -> GroceryOption:



        return self.get_grocery_option(

            ingredient_name,

        )



    # -----------------------------------------------------------------

    # Grocery-list input

    # -----------------------------------------------------------------



    def get_grocery_list(

        self,

        items: list[dict] | dict,

        recipe_id: str | None = None,

    ) -> list[GroceryOption]:



        """

        Search and price every grocery item.



        Supported PantryService dictionary format:





            {

                "rice": {

                    "ingredient_id": "ING001",

                    "quantity": 500,

                    "unit": "g"

                }

            }



        Existing list format is also supported.

        """



        options: list[

            GroceryOption

        ] = []



        # -------------------------------------------------------------

        # PantryService dictionary

        # -------------------------------------------------------------



        if isinstance(

            items,

            dict,

        ):



            for (

                ingredient_name,

                item,

            ) in items.items():



                if not isinstance(

                    item,

                    dict,

                ):

                    raise TypeError(

                        f"grocery item for "

                        f"'{ingredient_name}' "

                        f"must be a dictionary"

                    )



                option = (

                    self.get_grocery_option(

                        ingredient_name=(

                            ingredient_name

                        ),

                        required_quantity=(
                            item["missing_quantity"]
                                if item.get("missing_quantity") is not None
                                else item.get("quantity")

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

                        recipe_id=recipe_id,

                    )

                )



                options.append(

                    option

                )



            return options



        # -------------------------------------------------------------

        # List format

        # -------------------------------------------------------------



        if isinstance(

            items,

            list,

        ):



            for item in items:



                if not isinstance(

                    item,

                    dict,

                ):

                    raise TypeError(

                        "every grocery-list item "

                        "must be a dictionary"

                    )



                ingredient_name = (

                    item.get(

                        "ingredient_name"

                    )

                    or item.get(

                        "ingredient"

                    )

                )



                if not ingredient_name:



                    raise ValueError(

                        "grocery item is missing "

                        "'ingredient_name'"

                    )



                option = (

                    self.get_grocery_option(

                        ingredient_name=(

                            ingredient_name

                        ),

                        required_quantity=(
                            item["missing_quantity"]
                                if item.get("missing_quantity") is not None
                                else item.get("quantity")

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

                        recipe_id=recipe_id,

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

    # Main service interface

    # -----------------------------------------------------------------



    def get_grocery_results(

        self,

        items: list[dict] | dict,

    ) -> dict:



        options = self.get_grocery_list(

            items

        )



        return grocery_summary(

            options

        )





# ---------------------------------------------------------------------

# Budget-compatible basket summary

# ---------------------------------------------------------------------



def basket_summary(

    options: list[GroceryOption],

) -> dict:



    """

    Compatibility summary for the existing BudgetService.



    UNKNOWN cost is preserved when any required item has no usable

    purchase cost.

    """



    priced = [

        option

        for option in options

        if option.total_cost is not None

    ]



    missing_price = [

        option.ingredient_name

        for option in options

        if option.price_per_package

        is None

    ]



    missing_package_calc = [

        option.ingredient_name

        for option in options

        if (

            option.price_per_package

            is not None

            and option.total_cost

            is None

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

            if option.total_cost

            is not None

        ),

        2,

    )



    cost_complete = (

        len(options) > 0

        and len(

            unknown_cost_items

        ) == 0

    )



    return {

        "items": len(options),



        "priced_items": len(priced),



        "estimated_total":

            known_subtotal,



        "missing_price":

            missing_price,



        "missing_package_calc":

            missing_package_calc,



        "known_subtotal":

            known_subtotal,



        "unknown_cost_items":

            unknown_cost_items,



        "cost_complete":

            cost_complete,

    }





# ---------------------------------------------------------------------

# Main grocery result

# ---------------------------------------------------------------------



def grocery_summary(

    options: list[GroceryOption],

) -> dict:



    """

    Build the Grocery -> Reasoning result.



    A required grocery item counts as priced only when a known purchase

    cost is available.



    all_items_priced=True only when every required grocery purchase has

    a known cost.

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





            "minimum_package_cost":

                option.minimum_package_cost,



            "purchase_basis":

                option.purchase_basis,



            "estimated_total_cost":

                option.estimated_total_cost,



            "estimated_required_quantity":

                option.estimated_required_quantity,



            "estimated_required_unit":

                option.estimated_required_unit,



            "quantity_estimated":

                option.quantity_estimated,



            "total_cost":

                option.total_cost,





            "currency":

                option.currency,



            "store":

                option.store,



            "source_url":

                option.source_url,



            "source_updated_at":

                option.source_updated_at,



            "date_collected":

                option.date_collected,



            "match_status":

                option.match_status,



            "match_quality":

                option.match_quality,



            "purchase_channel":

                option.purchase_channel,



            "search_query":

                option.search_query,



            "note":

                option.note,

        }



        # -------------------------------------------------------------

        # No reliable product/price

        # -------------------------------------------------------------



        if (

            option.product_name

            is None

            or option.price_per_package

            is None

        ):



            missing_products.append(

                item

            )



        # -------------------------------------------------------------

        # Product exists but purchase cost remains incomplete

        # -------------------------------------------------------------



        elif (

            option.total_cost

            is None

        ):



            incomplete_products.append(

                item

            )



        # -------------------------------------------------------------

        # Complete purchase

        # -------------------------------------------------------------



        else:



            priced_products.append(

                item

            )



    # -----------------------------------------------------------------

    # Completeness contract

    # -----------------------------------------------------------------



    known_cost = round(

        sum(

            item["total_cost"]

            for item

            in priced_products

            if item["total_cost"]

            is not None

        ),

        2,

    )





    # -------------------------------------------------------------



    # -------------------------------------------------------------

    # Projected shopping cost

    #

    # Separate from known_cost and verified budget evaluation.

    # -------------------------------------------------------------



    projected_subtotal = 0.0

    projected_items = 0

    projection_missing = []



    for option in options:





        # Only use a calculated purchase cost.

        #

        # Exact and permitted minimum-package purchases

        # have total_cost.

        #

        # Recipe-specific quantity estimates have

        # estimated_total_cost.

        #

        # An unverified_quantity must not become a

        # complete projection using one-package price.



        cost = None



        if (

            option.product_name is not None

            and option.price_per_package is not None

        ):

            if option.total_cost is not None:

                cost = option.total_cost



            elif option.estimated_total_cost is not None:

                cost = option.estimated_total_cost



        # Do not fall back to minimum_package_cost.

        # It is informational, not proof of coverage.





        if cost is None:

            projection_missing.append(

                option.ingredient_name

            )

            continue



        projected_subtotal += float(cost)

        projected_items += 1



    # IMPORTANT:

    # These calculations must be OUTSIDE the for loop.



    projected_cost_complete = (

        len(options) > 0

        and len(projection_missing) == 0

        and projected_items == len(options)

    )



    projected_cost = (

        round(projected_subtotal, 2)

        if projected_cost_complete

        else None

    )







    unpriced_items = [

        option.ingredient_name

        for option in options

        if option.total_cost

        is None

    ]
        # Separate unverified estimates from genuinely unknown prices.
    estimated_price_items = [
        option.ingredient_name
        for option in options
        if option.total_cost is None
        and option.estimated_total_cost is not None
    ]

    genuinely_unknown_price_items = [
        option.ingredient_name
        for option in options
        if option.total_cost is None
        and option.estimated_total_cost is None
    ]



    all_items_priced = (

        len(options) > 0

        and len(

            unpriced_items

        ) == 0

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



        # Grocery -> Reasoning contract

        "known_cost":

            known_cost,



        "all_items_priced":

            all_items_priced,



        "unpriced_items":

            unpriced_items,

        "estimated_price_items": estimated_price_items,

        "genuinely_unknown_price_items": genuinely_unknown_price_items,

        "all_items_have_price_or_estimate": (
            bool(options)
            and not genuinely_unknown_price_items
        ),



        # Compatibility aliases for existing budget code

        "estimated_total":

            known_cost,



        "known_subtotal":

            known_cost,



        "cost_complete":

            all_items_priced,



        "unknown_cost_items":

            unpriced_items,



        # Full product information

        "priced_products":

            priced_products,



        "incomplete_products":

            incomplete_products,



        "missing_products":

            missing_products,



        "projected_cost": projected_cost,

        "projected_cost_complete": projected_cost_complete,

        "projected_items": projected_items,

        "projection_missing": projection_missing,

    }





# ---------------------------------------------------------------------

# Terminal display

# ---------------------------------------------------------------------



def print_grocery_results(

    result: dict,

) -> None:



    print()



    print(

        "=" * 70

    )



    print(

        "FAIRPRICE GROCERY RESULTS"

    )



    print(

        "=" * 70

    )



    print()



    found_count = (

        result[

            "products_priced"

        ]

        + result[

            "products_incomplete"

        ]

    )



    print(

        f"Found: {found_count} / "

        f"{result['items_requested']}"

    )



    print(

        f"Missing: "

        f"{result['products_missing']}"

    )



    print(

        f"All items priced: "

        f"{result['all_items_priced']}"

    )



    print()



    # -----------------------------------------------------------------

    # Found products

    # -----------------------------------------------------------------



    all_found = (

        result[

            "priced_products"

        ]

        + result[

            "incomplete_products"

        ]

    )



    if all_found:



        print(

            "PRODUCTS FOUND"

        )



        print(

            "-" * 70

        )



        for item in all_found:



            ingredient = (

                item["ingredient"]

            )



            product = (

                item["product_name"]

                or "NA"

            )



            package_quantity = (

                item[

                    "package_quantity"

                ]

            )



            package_unit = (

                item[

                    "package_unit"

                ]

            )



            if (

                package_quantity

                is not None

                and package_unit

                is not None

            ):



                package_text = (

                    f"{package_quantity:g} "

                    f"{package_unit}"

                )



            else:



                package_text = "NA"



            price = (

                item[

                    "price_per_package"

                ]

            )



            if price is not None:



                price_text = (

                    f"S${price:.2f}"

                )



            else:



                price_text = "NA"



            total = (

                item[

                    "total_cost"

                ]

            )



            if total is not None:



                total_text = (

                    f"S${total:.2f}"

                )



            else:



                total_text = "NA"



            status = (

                item[

                    "match_status"

                ]

            )



            minimum_marker = (

                " *"

                if status

                == "matched_minimum_package"

                else ""

            )



            print(

                ingredient

            )



            print(

                f"  Product: "

                f"{product}"

            )



            print(

                f"  Match: "

                f"{item['match_quality'] or 'NA'}"

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

                f"  Packages needed: "

                f"{item['packages_needed']}"

            )



            print(

                f"  Purchase price: "

                f"{total_text}"

                f"{minimum_marker}"

            )



            if item.get(

                "note"

            ):



                print(

                    f"  Note: "

                    f"{item['note']}"

                )



            print()



    # -----------------------------------------------------------------

    # Minimum-package explanation

    # -----------------------------------------------------------------



    has_minimum_package = any(

        item[

            "match_status"

        ]

        == "matched_minimum_package"



        for item in result[

            "priced_products"

        ]

    )



    if has_minimum_package:



        print(

            "* Minimum retail package used "

            "where exact recipe/package quantity "

            "comparison was not possible."

        )



        print()



    # -----------------------------------------------------------------

    # Cost

    # -----------------------------------------------------------------



    print(

        f"Known grocery purchase cost: "

        f"S${result['known_cost']:.2f}"

    )



    if result[

        "all_items_priced"

    ]:



        print(

            "Pricing completeness: COMPLETE"

        )



    else:



        print(

            "Pricing completeness: INCOMPLETE"

        )



        print(

            "Unpriced items: "

            + ", ".join(

                result[

                    "unpriced_items"

                ]

            )

        )



    # -----------------------------------------------------------------

    # Missing products

    # -----------------------------------------------------------------



    print()



    print(

        "MISSING PRODUCTS"

    )



    print(

        "-" * 70

    )



    if not result[

        "missing_products"

    ]:



        print(

            "None"

        )



    else:



        for item in result[

            "missing_products"

        ]:



            print(

                f"- {item['ingredient']}"

            )



            if item.get(

                "note"

            ):



                print(

                    f"  {item['note']}"

                )





# ---------------------------------------------------------------------

# Module-level shared service

# ---------------------------------------------------------------------



_default_service: (

    GroceryService

    | None

) = None





def _service() -> GroceryService:



    global _default_service



    if _default_service is None:



        _default_service = (

            GroceryService()

        )



    return _default_service





# ---------------------------------------------------------------------

# Public convenience functions

# ---------------------------------------------------------------------



def search_grocery_product(

    ingredient_name: str,

) -> GroceryOption:



    return (

        _service()

        .search_grocery_product(

            ingredient_name

        )

    )





def get_grocery_option(

    ingredient_name: str,

    required_quantity: float | None = None,

    unit: str | None = None,

    ingredient_id: str | None = None,

) -> GroceryOption:



    return (

        _service()

        .get_grocery_option(

            ingredient_name=(

                ingredient_name

            ),

            required_quantity=(

                required_quantity

            ),

            unit=unit,

            ingredient_id=(

                ingredient_id

            ),

        )

    )





def get_grocery_results(

    items: list[dict] | dict,

) -> dict:



    """

    Main public Grocery interface.



    Example input:



        {

            "garlic powder": {

                "ingredient_id": "ING123",

                "quantity": 1,

                "unit": "pinch"

            }

        }



    Important output:



        {

            "known_cost": 4.89,

            "all_items_priced": True,

            "unpriced_items": [],

            ...

        }

    """



    return (

        _service()

        .get_grocery_results(

            items

        )

    )