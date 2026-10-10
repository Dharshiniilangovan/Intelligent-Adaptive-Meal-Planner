"""GC1 Step 2C: live grocery source and pricing propagation diagnostic.
Run from repository root: python -m scripts.verify_step2c_pricing
Requires Tavily credentials and running Ollama for actual fallback checks.
"""
from __future__ import annotations

import os
from collections import Counter
from unittest.mock import patch

from src.grocery.grocery_service import GroceryOption, GroceryService, grocery_summary
from src.grocery.ollama_fallback_service import OllamaFallbackGroceryService


def category(option):
    if option.total_cost is not None:
        return "RETAIL_KNOWN"
    if option.estimated_total_cost is not None:
        return "ESTIMATED"
    return "UNKNOWN"


def print_option(label, option):
    print(f"\n{label}: {category(option)}")
    for name in ("ingredient_name", "product_name", "required_quantity", "required_unit",
                 "package_quantity", "package_unit", "packages_needed", "price_per_package",
                 "total_cost", "estimated_total_cost", "minimum_package_cost", "purchase_basis",
                 "match_status", "source_url", "note"):
        print(f"  {name}: {getattr(option, name, None)}")
    if option.total_cost is not None:
        assert option.total_cost >= 0
    if option.estimated_total_cost is not None:
        assert option.estimated_total_cost >= 0


def main():
    print("STEP 2C - LIVE GROCERY PRICING DIAGNOSTIC")
    print("Fallback env:", os.getenv("ENABLE_OLLAMA_GROCERY_FALLBACK", "1"))
    service = OllamaFallbackGroceryService()
    print("Actual service:", type(service).__name__)

    # Force a deterministic Tavily failure to verify fallback integration;
    # this section can call the local Ollama model.
    with patch.object(GroceryService, "get_grocery_option", return_value=GroceryOption(
        ingredient_id=None, ingredient_name="hoisin sauce", required_quantity=1,
        required_unit="tablespoon", match_status="no_match"
    )):
        fallback = service.get_grocery_option("hoisin sauce", 1, "tablespoon")
    print_option("FORCED TAVILY MISS -> OLLAMA", fallback)
    if service.enable_ollama_fallback:
        print("Fallback result:", "ESTIMATE RETURNED" if fallback.estimated_total_cost is not None else "NO USABLE ESTIMATE")
    if fallback.purchase_basis == "llm_estimated_package":
        assert fallback.total_cost is None, "Ollama estimate must not become verified retail cost"
        assert fallback.source_url is None, "Ollama estimate must not claim retailer URL"

    cases = [("cucumber", 660, "g"), ("tofu", 56.5, "g"),
             ("olive oil", 2, "tablespoon"), ("butter lettuce", 0.5, "head")]
    results = [fallback]
    for name, qty, unit in cases:
        try:
            option = service.get_grocery_option(name, qty, unit)
        except Exception as exc:
            print(f"\n{name}: ERROR {type(exc).__name__}: {exc}")
            continue
        print_option("LIVE " + name, option)
        results.append(option)

    summary = grocery_summary(results)
    print("\nSUMMARY")
    for key in ("known_cost", "all_items_priced", "unpriced_items",
                "estimated_price_items", "genuinely_unknown_price_items",
                "all_items_have_price_or_estimate"):
        print(f"  {key}: {summary.get(key)}")
    counts = Counter(category(option) for option in results)
    print("CATEGORIES:", dict(counts))
    assert len(summary["estimated_price_items"]) == counts["ESTIMATED"]
    assert len(summary["genuinely_unknown_price_items"]) == counts["UNKNOWN"]
    assert summary["all_items_priced"] == (counts["RETAIL_KNOWN"] == len(results))
    print("\nPASS: summary categorization and estimate/verified separation")
    print("NOTE: This is a diagnostic, not proof that retailer prices are accurate or Day 5 basket reconciles.")


if __name__ == "__main__":
    main()
