import tempfile
import time
import unittest
from pathlib import Path
from src.cache.cache_service import PersistentCache, cache_key


class CacheTests(unittest.TestCase):
    def test_persists_across_instances_and_exports(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cache.db'
            first = PersistentCache(path)
            key = cache_key('tavily', {'query': 'tofu'})
            first.set('tavily', key, [{'price': 2.5}], 60)
            second = PersistentCache(path)
            self.assertEqual(second.get('tavily', key), [{'price': 2.5}])
            self.assertEqual(second.export_json(Path(directory) / 'export.json'), 1)

    def test_expiry_and_miss(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = PersistentCache(Path(directory) / 'cache.db')
            self.assertIsNone(cache.get('test', 'absent'))
            cache.set('test', 'key', {'ok': True}, 0.01)
            time.sleep(0.03)
            self.assertIsNone(cache.get('test', 'key'))

    def test_key_order_independent(self):
        self.assertEqual(cache_key('a', {'x': 1, 'y': 2}), cache_key('a', {'y': 2, 'x': 1}))


if __name__ == '__main__':
    unittest.main()
