from src.cache.cache_service import PersistentCache
from src.grocery.grocery_service import GroceryService

cache = PersistentCache()

removed = 0

with cache._connect() as db:
    rows = db.execute(
        "SELECT category, key, value FROM cache"
    ).fetchall()

    import json

    for category, key, value in rows:
        try:
            data = json.loads(value)
        except (ValueError, TypeError):
            data = None

        invalid = False

        if category == "tavily_search_v1":
            valid = GroceryService._cacheable_products(data)
            invalid = not valid or len(valid) != len(data)

        elif category == "ollama_grocery_v1":
            invalid = not isinstance(data, dict)

            if not invalid:
                import math

                try:
                    price = float(data["estimated_price_sgd"])
                    quantity = float(
                        data["estimated_package_quantity"]
                    )
                    total = float(data["estimated_total_cost"])
                    count = int(data["estimated_packages_needed"])

                    invalid = not (
                        math.isfinite(price)
                        and math.isfinite(quantity)
                        and math.isfinite(total)
                        and price > 0
                        and quantity > 0
                        and count >= 1
                        and abs(total - price * count)
                        <= max(0.03, total * 0.01)
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                    OverflowError,
                ):
                    invalid = True

        if invalid:
            db.execute(
                "DELETE FROM cache WHERE category=? AND key=?",
                (category, key),
            )
            removed += 1

print(f"Removed {removed} invalid cache entries.")