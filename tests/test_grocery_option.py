
from src.grocery.grocery_service import GroceryService


def main():
    service = GroceryService()

    print("=" * 60)
    print("GROCERY PURCHASE COST TEST")
    print("=" * 60)

    option = service.get_grocery_option(
        ingredient_name="fresh milk",
        required_quantity=1500,
        unit="ml",
    )

    print("\nIngredient:", option.ingredient_name)
    print("Product:", option.product_name)
    print("Match quality:", option.match_quality)
    print("Match status:", option.match_status)

    print(
        "Package:",
        option.package_quantity,
        option.package_unit,
    )

    print("Price per package:", option.price_per_package)
    print("Packages needed:", option.packages_needed)
    print("Total purchase cost:", option.total_cost)

    print("Store:", option.store)
    print("Source URL:", option.source_url)
    print("Notes:", option.note)

    print("\n" + "=" * 60)

    if (
        option.total_cost is not None
        and option.match_status == "matched"
    ):
        print("PASS: Complete purchase cost calculated")
    else:
        print("CHECK: Purchase cost not fully verified")
    
    print("\n" + "=" * 60)
    print("MULTIPLE INGREDIENT GROCERY TEST")
    print("=" * 60)

    ingredients = [
        ("tomato", 500, "g"),
        ("potato", 1000, "g"),
        ("chicken breast", 500, "g"),
        ("eggs", 6, "pcs"),
        ("garlic", 100, "g"),
    ]

    for name, quantity, unit in ingredients:
        print(f"\n{'-' * 50}")
        print(f"Ingredient: {name}")
        print(f"Required: {quantity} {unit}")

        try:
            result = service.get_grocery_option(
                ingredient_name=name,
                required_quantity=quantity,
                unit=unit,
            )

            print("Product:", result.product_name)
            print("Match quality:", result.match_quality)
            print("Match status:", result.match_status)
            print(
                "Package:",
                result.package_quantity,
                result.package_unit,
            )
            print("Price:", result.price_per_package)
            print("Packages needed:", result.packages_needed)
            print("Total cost:", result.total_cost)
            print("URL:", result.source_url)
            print("Notes:", result.note)

            if (
                result.match_status == "matched"
                and result.total_cost is not None
            ):
                print("RESULT: COMPLETE PURCHASE COST")

            elif result.total_cost is not None:
                print("RESULT: COST EXISTS, CHECK QUANTITY COVERAGE")

            else:
                print("RESULT: INCOMPLETE PURCHASE COST")

        except Exception as exc:
            print(
                "ERROR:",
                type(exc).__name__,
                str(exc),
            )



if __name__ == "__main__":
    main()
