"""scripts/debug_grocery_search.py — see exactly what Tavily returns for an ingredient and why
each page is used or dropped.

    python scripts/debug_grocery_search.py "fresh milk"
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.grocery.food_filter import search_queries  # noqa: E402
from src.grocery.grocery_service import GroceryService  # noqa: E402
from src.grocery.tavily_client import (SearchError, TavilyGroceryClient, is_product_page,  # noqa: E402
                                       normalize, store_for)

ingredient = sys.argv[1] if len(sys.argv) > 1 else "fresh milk"
client = TavilyGroceryClient()
service = GroceryService(client=client, verify_links=False)
print(f"API key loaded: {bool(client.api_key)}")
print(f"Ingredient: {ingredient!r} -> queries {search_queries(ingredient)}\n")

for query in search_queries(ingredient):
    try:
        data = client.search_raw(query)
    except SearchError as e:
        print(f"=== query {query!r}: FAILED - {e}\n")
        continue
    results = data.get("results") or []
    print(f"=== query 'price of {query} in Singapore': {len(results)} pages")
    for r in results:
        url = r.get("url", "")
        print(f"\n  {r.get('title', '')[:70]}")
        print(f"      {url}")
        domain, store = store_for(url)
        if not domain:
            print("      -> DROP: not a Singapore supermarket site")
            continue
        if not is_product_page(url):
            print("      -> DROP: not a product page (search/category/promo page)")
            continue
        p = normalize(r)
        if p is None:
            snippet = (r.get("content") or "").replace("\n", " ")[:120]
            print(f"      -> DROP: no price found in page text. Snippet: {snippet!r}")
            continue
        valid, rejected = service._filter(ingredient, [p])
        verdict = f"PASS ({valid[0]['match']}), package={valid[0]['package']}" if valid \
            else f"REJECT: {next(iter(rejected))}"
        print(f"      title={p['title']!r}  price=S${p['price']}  store={p['store']}")
        print(f"      -> {verdict}")
    print()