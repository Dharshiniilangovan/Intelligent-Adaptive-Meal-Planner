
"""Validate Recipe KB URLs.

Run from project root:
    python -m scripts.validate_recipe_urls

Creates:
    reports/recipe_url_validation.csv
"""

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pandas as pd


INPUT = Path("data/processed/recipe_kb_clean.csv")
OUTPUT = Path("reports/recipe_url_validation.csv")

CONCURRENCY = 10
TIMEOUT = 15


def valid_http_url(value):
    if pd.isna(value):
        return False

    url = str(value).strip()
    parsed = urlparse(url)

    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.netloc)
    )


async def check_url(client, url, semaphore):
    async with semaphore:
        try:
            response = await client.get(
                url,
                follow_redirects=True,
            )

            status_code = response.status_code

            if status_code == 200:
                status = "working"
            elif status_code in (404, 410):
                status = "broken"
            else:
                status = "uncertain"

            return {
                "url": url,
                "http_status": status_code,
                "status": status,
                "final_url": str(response.url),
            }

        except httpx.RequestError as exc:
            print(
                "[URL CHECK ERROR]",
                url,
                str(exc),
            )

            return {
                "url": url,
                "http_status": None,
                "status": "uncertain",
                "final_url": None,
            }


async def main():

    if not INPUT.exists():
        raise FileNotFoundError(
            f"Recipe KB not found: {INPUT}"
        )

    df = pd.read_csv(
        INPUT,
        dtype=str,
        keep_default_na=False,
    )

    required_columns = {
        "recipe_id",
        "recipe_name",
        "url",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing Recipe KB columns: {sorted(missing)}"
        )

    df["url"] = df["url"].str.strip()

    unique_urls = [
        url
        for url in df["url"].unique()
        if valid_http_url(url)
    ]

    print("[URL VALIDATION] Recipes:", len(df))
    print("[URL VALIDATION] Unique URLs:", len(unique_urls))

    semaphore = asyncio.Semaphore(CONCURRENCY)

    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        limits=httpx.Limits(
            max_connections=CONCURRENCY,
            max_keepalive_connections=CONCURRENCY,
        ),
    ) as client:

        results = await asyncio.gather(
            *[
                check_url(client, url, semaphore)
                for url in unique_urls
            ]
        )

    status_lookup = {
        row["url"]: row
        for row in results
    }

    report_rows = []

    for _, recipe in df.iterrows():

        url = recipe["url"]

        validation = status_lookup.get(url)

        if validation is None:
            validation = {
                "http_status": None,
                "status": "uncertain",
                "final_url": None,
            }

        report_rows.append({
            "recipe_id": recipe["recipe_id"],
            "recipe_name": recipe["recipe_name"],
            "url": url,
            "http_status": validation["http_status"],
            "status": validation["status"],
            "final_url": validation["final_url"],
        })

    report = pd.DataFrame(report_rows)

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report.to_csv(
        OUTPUT,
        index=False,
    )

    print("\nURL VALIDATION REPORT")
    print("=" * 60)

    print(report["status"].value_counts())

    total = len(report)
    working = (report["status"] == "working").sum()
    broken = (report["status"] == "broken").sum()
    uncertain = (report["status"] == "uncertain").sum()

    print("\nTotal recipes:", total)
    print("Working URLs:", working)
    print("Broken URLs:", broken)
    print("Uncertain URLs:", uncertain)

    if total:
        print(
            f"Working percentage: {working / total * 100:.2f}%"
        )

    print("\nReport saved:", OUTPUT.resolve())


if __name__ == "__main__":
    asyncio.run(main())
