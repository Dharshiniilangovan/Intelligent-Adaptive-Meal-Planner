
"""
Grocery Service with optional local Ollama price fallback.

Tavily remains the primary source.

Ollama is only used when no usable purchase cost
or quantity-based retail estimate exists.

LLM estimates remain separate from verified costs.
"""

from __future__ import annotations

import os
import math
from dataclasses import asdict
from src.cache.cache_service import cache_key as cache_key_fn
from src.grocery.ollama_price_estimator import GroceryPriceEstimate, OLLAMA_MODEL

from src.grocery.grocery_service import GroceryService
from src.grocery.ollama_price_estimator import (
    estimate_grocery_price,
)


class OllamaFallbackGroceryService(GroceryService):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.enable_ollama_fallback = (
            os.getenv(
                "ENABLE_OLLAMA_GROCERY_FALLBACK",
                "1",
            ) == "1"
        )

        self._ollama_estimate_cache = {}

    def get_grocery_option(
        self,
        ingredient_name,
        required_quantity=None,
        unit=None,
        *args,
        **kwargs,
    ):
        # First run the original Tavily pipeline.
        option = super().get_grocery_option(
            ingredient_name,
            required_quantity,
            unit,
            *args,
            **kwargs,
        )

        if not self.enable_ollama_fallback:
            return option

        # Preserve existing valid retail costs.
        if option.total_cost is not None:
            return option

        # Preserve existing quantity-based estimates
        # that use real retailer prices.
        if option.estimated_total_cost is not None:
            return option

        # Last resort: local LLM estimation.
        cache_key = (
            str(ingredient_name).strip().lower(),
            str(required_quantity),
            str(unit).strip().lower(),
        )

        persistent_key = cache_key_fn("ollama_grocery_v1", {
            "ingredient": cache_key[0], "quantity": cache_key[1],
            "unit": cache_key[2], "model": OLLAMA_MODEL,
        })
        if cache_key in self._ollama_estimate_cache:
            estimate = self._ollama_estimate_cache[cache_key]
        else:
            saved = self.persistent_cache.get("ollama_grocery_v1", persistent_key)
            try:
                estimate = GroceryPriceEstimate(**saved) if isinstance(saved, dict) else None
            except (TypeError, ValueError):
                estimate = None
            if estimate is not None:
                print(f"[SQLITE OLLAMA CACHE HIT] {ingredient_name}")
            else:
                print("[OLLAMA GROCERY FALLBACK]", ingredient_name)
                estimate = estimate_grocery_price(
                    ingredient_name=ingredient_name,
                    required_quantity=required_quantity,
                    required_unit=unit,
                )
            if estimate is not None:
                self._ollama_estimate_cache[cache_key] = estimate

        if estimate is None:
            option.note = (
                (option.note or "")
                + " Ollama could not provide a usable estimate."
            ).strip()

            return option

        # Reject malformed or implausible estimates before propagation.
                # Validate the Ollama estimate once.
        try:
            price = float(estimate.estimated_price_sgd)
            total = float(estimate.estimated_total_cost)
            count = int(estimate.estimated_packages_needed)
            qty = float(estimate.estimated_package_quantity)

            valid_numbers = all(
                math.isfinite(x)
                for x in (price, total, qty)
            )

            valid_ranges = (
                0 < price <= 1000
                and 0 < total <= 10000
                and qty > 0
                and 1 <= count <= 1000
            )

            valid_total = (
                abs(total - price * count)
                <= max(0.03, total * 0.01)
            )

            if not (
                valid_numbers
                and valid_ranges
                and valid_total
            ):
                if os.getenv("OLLAMA_GROCERY_DEBUG") == "1":
                    print(
                        "[OLLAMA FALLBACK REJECTED]",
                        ingredient_name,
                        {
                            "valid_numbers": valid_numbers,
                            "valid_ranges": valid_ranges,
                            "valid_total": valid_total,
                        },
                    )

                return option

        except (
            TypeError,
            ValueError,
            AttributeError,
            OverflowError,
        ) as exc:
            if os.getenv("OLLAMA_GROCERY_DEBUG") == "1":
                print(
                    "[OLLAMA FALLBACK ERROR]",
                    ingredient_name,
                    str(exc),
                )

            return option

        # Save only validated, successfully parsed estimates.
        if self.persistent_cache.get("ollama_grocery_v1", persistent_key) is None:
            self.persistent_cache.set(
                "ollama_grocery_v1", persistent_key, asdict(estimate), 7 * 86400
            )

        # Populate existing GroceryOption fields.
        # Do not claim a real retailer or verified price.
        option.product_name = estimate.estimated_product

        option.price_per_package = (
            estimate.estimated_price_sgd
        )

        option.package_quantity = (
            estimate.estimated_package_quantity
        )

        option.package_unit = (
            estimate.estimated_package_unit
        )

        option.packages_needed = (
            estimate.estimated_packages_needed
        )

        option.minimum_package_cost = None

        option.total_cost = None

        option.estimated_total_cost = (
            estimate.estimated_total_cost
        )

        option.purchase_basis = (
            "llm_estimated_package"
        )

        option.match_status = (
            "estimated_no_retail_match"
        )

        option.match_quality = None

        option.currency = "SGD"

        option.store = None

        option.source_url = None

        option.source_updated_at = None

        option.purchase_channel = (
            "availability_unverified"
        )

        option.quantity_estimated = True

        option.note = (
            "Unverified Singapore grocery price estimated "
            "by local Ollama. No live retailer price or "
            "package coverage was confirmed. "
            "Confidence: LOW."
        )

        return option
