import tempfile
import unittest
from pathlib import Path

from production_v4 import create_startup_backup


class ProductionV4Tests(unittest.TestCase):
    def test_startup_backup_is_created_and_rotated(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / 'last_keeper.db'
            database.write_bytes(b'test-database')
            created = create_startup_backup(str(database), keep=2)
            self.assertIsNotNone(created)
            self.assertTrue(Path(created).exists())
            self.assertEqual(Path(created).read_bytes(), b'test-database')

    def test_render_storage_configuration_is_consistent(self):
        render = Path('render.yaml').read_text(encoding='utf-8')

        if 'plan: starter' in render:
            self.assertIn('mountPath: /var/data', render)
            self.assertIn('value: /var/data/last_keeper.db', render)
        elif 'plan: free' in render:
            self.assertNotIn('mountPath: /var/data', render)
            self.assertIn('value: /tmp/last_keeper.db', render)
        else:
            self.fail('render.yaml must explicitly use either starter or free plan')


if __name__ == '__main__':
    unittest.main()
