"""scripts/verify_grocery_source.py — Task 1: does BuyWhere give usable grocery data?

Searches the test ingredients LIVE and records, per ingredient:
    search worked? / product matched? / price? / package size? / store? / link?
plus EVERY raw product BuyWhere returned, with its URL and why it passed or was rejected.

Writes reports/grocery_source_verification.md

Run from the repo root:
    python scripts/verify_grocery_source.py
"""
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.grocery.tavily_client import SearchError
from src.grocery.food_filter import search_queries  # noqa: E402
from src.grocery.grocery_service import GroceryService  # noqa: E402

TEST_INGREDIENTS = [
    ("firm tofu", 1.0, "count"),
    ("soy sauce", 2.0, "tablespoon"),
    ("olive oil", 2.0, "tablespoon"),
    ("apple cider vinegar", 2.0, "tablespoon"),
    ("garlic powder", 1.0, "pinch"),
    ("fine sea salt", 1.0, "pinch"),
    ("black pepper", 1.0, "pinch"),
    ("liquid smoke", 0.5, "teaspoon"),
]
REPORT_PATH = PROJECT_ROOT / "reports" / "grocery_source_verification.md"


def yes_no(value) -> str:
    return "yes" if value else "no"


def cell(value) -> str:
    """Make a value safe inside a markdown table cell."""
    return str(value if value not in (None, "") else "NA").replace("|", "/").replace("\n", " ")


def link(url: str | None) -> str:
    return f"[link]({url})" if url else "NA"


def product_table(service: GroceryService, ingredient: str, products: list[dict]) -> list[str]:
    """One row per raw product: what it is, where it's from, and the pipeline's verdict."""
    rows = ["| # | Product | Price | Store | Country | Verdict | URL |",
            "|---|---|---|---|---|---|---|"]
    for i, p in enumerate(products, start=1):
        valid, rejected = service._filter(ingredient, [p])
        verdict = f"PASS ({valid[0]['match']})" if valid else f"REJECT: {next(iter(rejected))}"
        rows.append(f"| {i} | {cell(p['title'])} | {p['price']} {p['currency']} | {cell(p['store'])} | "
                    f"{cell(p.get('country_code'))} | {cell(verdict)} | {link(p.get('url'))} |")
    return rows


def main() -> None:
    service = GroceryService(verify_links=True)
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary_rows, details = [], []

    for name, qty, unit in TEST_INGREDIENTS:
        print(f"Checking {name} ...")
        section = [f"### {name} (need {qty} {unit})"]
        search_ok = True
        raw_count = 0

        # --- raw results per query, with URLs and verdicts
        for query in search_queries(name):
            try:
                products = service._search(query)
            except SearchError as e:
                search_ok = False
                section.append(f"\n**Query '{query}': search failed** — {cell(e)}\n")
                continue
            raw_count += len(products)
            section.append(f"\n**Query '{query}': {len(products)} raw results**\n")
            if products:
                section += product_table(service, name, products)

        # --- what the pipeline finally chose
        option = service.get_grocery_option(name, qty, unit)
        section += [
            "",
            f"- **Chosen:** {cell(option.product_name)}",
            f"- **Package:** {cell(option.package_quantity)} {option.package_unit or ''} | "
            f"**Price/package:** {cell(option.price_per_package)} {option.currency or ''} | "
            f"**Packages needed:** {cell(option.packages_needed)} | **Total:** {cell(option.total_cost)}",
            f"- **Store:** {cell(option.store)} | **Source updated:** {cell(option.source_updated_at)}",
            f"- **URL:** {option.source_url or 'NA'}",
            f"- **Status:** {option.match_status} ({option.match_quality or '-'} match). {option.note}",
            "",
        ]
        details.append("\n".join(section))

        summary_rows.append([
            name, f"{yes_no(search_ok)} ({raw_count})", yes_no(option.product_name),
            yes_no(option.price_per_package is not None), yes_no(option.package_quantity is not None),
            yes_no(option.store), link(option.source_url) if option.source_url else "-",
            yes_no(option.source_updated_at) if option.product_name else "-",
        ])

    header = ("| Ingredient | Search worked (results) | Product matched | Price | Package size "
              "| Store | URL | Source timestamp |\n|---|---|---|---|---|---|---|---|")
    table = "\n".join("| " + " | ".join(r) + " |" for r in summary_rows)
    report = (f"# Grocery source verification — Tavliy Search\n\nRun: {run_time}\n\n"
              f"## Summary\n\n{header}\n{table}\n\n## Details\n\n" + "\n".join(details) +
              "\n## Manual check\nOpen the URLs above and confirm each product and price on the store's page.\n")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print("\n" + header + "\n" + table)
    print(f"\nSaved {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()