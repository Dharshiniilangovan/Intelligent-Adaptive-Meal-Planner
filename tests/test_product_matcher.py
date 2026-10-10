
from src.grocery.product_matcher import match_product
from src.grocery.grocery_service import parse_package


cases = [
    ("lemon juice","[BCRS] Homegrown Cold Pressed Juice - Lemon Honey & Ginger",False,),
    ("lemon juice","Santa Cruz Organic Bottle Juice - Pure Lemon",True,),
    ("fresh milk", "FairPrice Fresh Full Cream Milk", True),
    ("fresh milk", "FairPrice Strawberry Flavoured Milk", False),
    ("fresh milk", "FairPrice Chocolate Milk", False),
    ("fresh milk", "FairPrice UHT Milk", True),
    ("chicken breast", "Fresh Chicken Breast", True),
    ("chicken breast", "Chicken Nuggets", False),
    ("tomato", "Fresh Red Tomatoes", True),
    ("tomato", "Tomato Ketchup", False),
    ("potato", "Fresh Potatoes", True),
    ("potato", "Potato Chips", False),
    ("fresh milk","F & N Magnolia UHT Packet Milk - Fresh Milk",True,),
    ("lemon juice","[BCRS] FairPrice Calamansi Honey Lemon Juice",False,),
        
    (
        "strawberry",
        "FairPrice UHT Kids Flavoured Packet Milk - Strawberry",
        False,
    ),
    (
        "strawberry",
        "Pasar South Korea Strawberry",
        True,
    ),
    (
        "banana",
        "Banana Flavoured Milk",
        False,
    ),
    (
        "banana",
        "Good Nature Organic Banana",
        True,
    ),
        
    (
        "garlic",
        "FairPrice Garlic & Herbs Wraps",
        False,
    ),
    (
        "garlic",
        "Fresh China Garlic",
        True,
    ),
    (
        "garlic",
        "Garlic Bulbs",
        True,
    ),
    (
        "garlic",
        "FairPrice Garlic Powder",
        False,
    ),
    (
    "garlic",
    "FairPrice Chili Sauce - Ginger and Garlic",
    False,
    ),
    (
        "garlic",
        "Fresh Garlic Bulbs",
        True,
    ),
        
    (
        "corn",
        "FairPrice Corn Flour",
        False,
    ),
    (
        "corn",
        "Fresh Sweet Corn",
        True,
    ),
    (
        "corn",
        "Fresh Corn on the Cob",
        True,
    ),
    (
        "corn",
        "FairPrice Corn Starch",
        False,
    ),
    
    (
        "corn",
        "FairPrice Potato Chips - Roasted Corn",
        False,
    ),
    (
        "corn",
        "Corn Flavoured Potato Crisps",
        False,
    ),
    (
        "corn",
        "Fresh Sweet Corn",
        True,
    ),
    (
        "corn",
        "Fresh Corn on the Cob",
        True,
    ),

    
    (
        "black beans",
        "Pasar Dried Black Eye Beans",
        False,
    ),
    (
        "black beans",
        "Black Eyed Peas",
        False,
    ),
    (
        "black beans",
        "Organic Black Turtle Beans",
        True,
    ),
    (
        "black beans",
        "Biona Organic Black Beans",
        True,
    ),
    
    (
        "black beans",
        "AAA Fermented Black Bean",
        False,
    ),
    (
        "black beans",
        "Salted Fermented Black Beans",
        False,
    ),
    (
        "black beans",
        "Organic Black Turtle Beans",
        True,
    ),
    (
        "black beans",
        "Biona Organic Black Beans",
        True,
    ),

        
    (
        "strawberry",
        "Jinro Bottle Soju - Strawberry",
        False,
    ),
    (
        "strawberry",
        "Strawberry Flavoured Vodka",
        False,
    ),
    (
        "strawberry",
        "Fresh Korean Strawberries",
        True,
    ),
    (
        "strawberry",
        "Pasar Fresh Strawberry",
        True,
    ),

    (
        "strawberry",
        "Nissin Granola - Strawberry",
        False,
    ),
    (
        "strawberry",
        "Strawberry Breakfast Cereal",
        False,
    ),
    (
        "strawberry",
        "Strawberry Yogurt",
        False,
    ),
    (
        "strawberry",
        "Fresh Korean Strawberries",
        True,
    ),
    (
        "strawberry",
        "Pasar Fresh Strawberry",
        True,
    ),
    
    (
        "strawberry",
        "Scott's DHA Gummies - Strawberry",
        False,
    ),
    (
        "strawberry",
        "Strawberry Gummies",
        False,
    ),
    (
        "strawberry",
        "Fresh Korean Strawberries",
        True,
    ),
    (
        "strawberry",
        "Frozen Strawberries",
        True,
    ),
    (
        "banana",
        "Banana Breakfast Cereal",
        False,
    ),
    (
        "banana",
        "Fresh Cavendish Banana",
        True,
    ),
    (
        "apple",
        "Apple Juice",
        False,
    ),
    (
        "apple",
        "Fresh Red Apples",
        True,
    ),

]

failed = 0

for ingredient, product, expected in cases:
    result = match_product(ingredient, product)
    passed = result.accepted == expected

    print(
        f"{'PASS' if passed else 'FAIL'} | "
        f"{ingredient} -> {product} | "
        f"{result.match_type} | "
        f"{result.reason}"
    )

    if not passed:
        failed += 1

print(f"\nFailed: {failed}/{len(cases)}")

if failed:
    raise SystemExit(1)

package_cases = [
    ("1lt", (1000.0, "ml")),
    ("6 x 200ml", (1200.0, "ml")),
    ("6 packs of 200ml", (1200.0, "ml")),
    ("2 x 1.5L", (3000.0, "ml")),
    ("500g", (500.0, "g")),
    ("12 eggs", (12.0, "pcs")),
]

for text, expected in package_cases:
    actual = parse_package(text)

    print(
        "PASS" if actual == expected else "FAIL",
        text,
        actual,
    )
