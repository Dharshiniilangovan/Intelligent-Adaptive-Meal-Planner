import asyncio
import httpx
import pandas as pd

INPUT = "data/processed/recipe_kb_clean.csv"
OUTPUT = "reports/recipe_url_validation.csv"

df = pd.read_csv(INPUT)


async def check_url(client, url, semaphore):
    async with semaphore:
        try:
            response = await client.get(
                url,
                follow_redirects=True,
            )

            if response.status_code in (404, 410):
                status = "broken"
            elif response.status_code == 200:
                status = "working"
            else:
                status = "uncertain"

            return {
                "url": url,
                "http_status": response.status_code,
                "status": status,
            }

        except httpx.RequestError:
            return {
                "url": url,
                "http_status": None,
                "status": "uncertain",
            }


async def main():
    semaphore = asyncio.Semaphore(10)

    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(
            *[check_url(client, url, semaphore) for url in df["url"].dropna().unique()]
        )

    report = pd.DataFrame(results)
    report.to_csv(OUTPUT, index=False)

    print("\nURL VALIDATION REPORT")
    print(report["status"].value_counts())

    total = len(report)
    broken = (report["status"] == "broken").sum()

    print(f"\nTotal URLs: {total}")
    print(f"Broken URLs: {broken}")
    print(f"Broken percentage: {broken / total * 100:.2f}%")


if __name__ == "__main__":
    asyncio.run(main())
