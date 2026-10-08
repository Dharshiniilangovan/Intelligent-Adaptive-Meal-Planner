import unittest
from src.grocery.semantic_product_matcher import validate_product
from src.grocery.product_matcher import match_product

CASES = [
    ('almond','Magnum Ice Cream - Almond',False),
    ('almond','Raw Almonds',True),
    ('almond','Roasted Almonds',True),
    ('almond','Almond Milk',False),
    ('strawberry','Scott DHA Gummies - Strawberry',False),
    ('strawberry','Fresh Strawberries',True),
    ('black pepper','FairPrice Potato Chips - Black Pepper',False),
    ('black pepper','FairPrice Black Pepper - Coarse',True),
    ('corn','FairPrice Corn Flour',False),
    ('corn','Fresh Sweet Corn',True),
    ('cranberry sauce','Coles Cranberry Sauce',True),
    ('pizza crust','Mission Pizza Crust Wholemeal',True),
    ('mozzarella','Shredded Cheese - Mozzarella',True),
    ('brie','President My Dip Spreadable Cheese Brie',False),
    ('brie','President Brie Cheese',True),
    ('black beans','AAA Fermented Black Bean',False),
    ('black beans','Dried Black Beans',True),
    ('garlic powder','Malabar Garlic Powder',True),
    ('garlic','Garlic Powder',False),
    ('lemon juice','Santa Cruz Pure Lemon Juice',True),
]

class MatchingTests(unittest.TestCase):
    def test_retail_form(self):
        for ingredient, title, expected in CASES:
            with self.subTest(ingredient=ingredient,title=title):
                self.assertEqual(match_product(ingredient,title).accepted,expected)
    def test_wrong_url(self):
        r=validate_product('vine tomato','Cherry Tomato on Vine',
            'https://www.fairprice.com.sg/product/fresh-yellow-onion-500g-123')
        self.assertFalse(r.accepted)

if __name__=='__main__':
    unittest.main()
