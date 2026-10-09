import unittest
from src.grocery.grocery_service import GroceryService

class IntegrationTests(unittest.TestCase):
    def test_filter_rejects_wrong_product_form(self):
        service=GroceryService()
        def product(title,url):
            return {'title':title,'url':url,'store':'FairPrice',
                    'currency':'SGD','price':3.5,'size_text':'100g'}
        products=[
            product('Magnum Ice Cream - Almond','https://www.fairprice.com.sg/product/magnum-ice-cream-almond-123'),
            product('Raw Almonds 100g','https://www.fairprice.com.sg/product/raw-almonds-100g-123')]
        valid,rejected=service._filter('almond',products)
        self.assertEqual(len(valid),1)
        self.assertIn('Raw Almonds',valid[0]['title'])

if __name__=='__main__':
    unittest.main()
