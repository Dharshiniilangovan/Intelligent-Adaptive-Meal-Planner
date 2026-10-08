
import unittest

from src.grocery.semantic_product_matcher import (
    validate_product,
)


class SemanticMatcherV2Tests(unittest.TestCase):

    def test_product_identity(self):

        cases = [
            ("butter", "FairPrice Peanut Butter", False),
            ("butter", "FairPrice Salted Butter", True),
            ("lemon", "Pasar Lemon Grass", False),
            ("lemon", "Fresh Yellow Lemon", True),
            ("egg", "Chef Century Eggs", False),
            ("egg", "Fresh Chicken Eggs", True),
            ("egg yolk", "Salted Egg Yolk", False),
            ("egg yolk", "Fresh Egg Yolk", True),
            ("almond", "Magnum Almond Ice Cream", False),
            ("almond", "Raw Almonds", True),
            ("strawberry", "Strawberry Gummies", False),
            ("strawberry", "Fresh Strawberries", True),
            ("black pepper", "Black Pepper Potato Chips", False),
            ("black pepper", "Ground Black Pepper", True),
            ("corn", "Corn Flour", False),
            ("corn", "Fresh Sweet Corn", True),
            ("cranberry sauce", "Coles Cranberry Sauce", True),
            ("mozzarella", "Shredded Mozzarella Cheese", True),
            ("brie", "Brie Cheese Dip", False),
            ("brie", "Castello Brie Cheese", True),
            ("pizza crust", "Mission Pizza Crust Wholemeal", True),
            ("vegetable oil", "FairPrice Vegetable Oil", True),
            ("green onion", "Fresh Spring Onion", True),
            ("all purpose flour", "Plain All Purpose Flour", True),
            ("all purpose flour", "Gluten Free All Purpose Flour", False),
            ("black beans", "Fermented Black Beans", False),
            ("black beans", "Dried Black Beans", True),
        ]

        for ingredient, title, expected in cases:
            with self.subTest(
                ingredient=ingredient,
                title=title,
            ):
                result = validate_product(
                    ingredient,
                    title,
                )

                self.assertEqual(
                    result.accepted,
                    expected,
                    msg=result.reason,
                )

    def test_url_mismatch(self):

        result = validate_product(
            "vine tomato",
            "Cherry Tomato on Vine",
            "https://www.fairprice.com.sg/product/"
            "fresh-yellow-onion-500g-123",
        )

        self.assertFalse(result.accepted)


if __name__ == "__main__":
    unittest.main()
