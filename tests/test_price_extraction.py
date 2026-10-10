
from src.grocery.tavily_client import extract_price


def main():
    cases = [
        (
            "Savings amount is not product price",
            (
                "Biona Organic Lemon Juice "
                "Save $3.38 Till 1st Jan 2027. "
                "1 L|Brand:Biona Organic."
            ),
            None,
        ),
        (
            "Product price with savings",
            "Fresh Milk $3.31 Save $0.50",
            3.31,
        ),
        (
            "Bottle deposit without product price",
            "FairPrice Lemon Drink +$2.40 deposit",
            None,
        ),
        (
            "Single product price",
            "FairPrice Fresh Milk 950ml S$3.31",
            3.31,
        ),
        (
            "Original and sale price",
            "Was S$4.50 Now S$3.31",
            3.31,
        ),
        (
            "Delivery threshold",
            "Fresh Milk S$3.31 Free delivery on orders above S$59",
            3.31,
        ),
        (
            "Clearly labelled selling price",
            "Regular price S$4.50 Sale price S$3.31",
            3.31,
        ),
        (
            "No product price",
            "FairPrice Fresh Milk 950ml",
            None,
        ),
        (
            "FairPrice promotional price",
            "Offer $3.90 $4.23 Save $0.33 Till 1st Nov 2026",
            3.90,
        ),
        
        (
            "Discount amount is not product price",
            "Biona Organic Black Beans @ $0.24 Off. Grab now!",
            None,
        ),
        (
            "Discount after SGD price",
            "Product S$1.20 discount",
            None,
        ),
        (
            "Savings after SGD amount",
            "Product SGD 0.50 savings",
            None,
        ),
        (
            "Product price followed by savings",
            "Product $3.50. Save $0.24",
            3.50,
        ),
        (
            "Product price followed by discount",
            "Product $3.50. $0.24 Off",
            3.50,
        ),

        
    ]

    failed = 0

    for name, text, expected in cases:
        actual = extract_price(text)

        passed = actual == expected

        print(
            f"{'PASS' if passed else 'FAIL'} | "
            f"{name} | "
            f"Expected: {expected} | "
            f"Actual: {actual}"
        )

        if not passed:
            failed += 1

    print()
    print(f"Failed: {failed}/{len(cases)}")


if __name__ == "__main__":
    main()
