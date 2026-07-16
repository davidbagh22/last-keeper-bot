import os
import tempfile
import unittest

from storage import Database, utcnow


class StorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        handle, self.path = tempfile.mkstemp(suffix='.db')
        os.close(handle)
        self.db = Database(self.path)
        await self.db.init()

    async def asyncTearDown(self):
        os.unlink(self.path)

    async def test_admin_roundtrip(self):
        await self.db.execute(
            'INSERT INTO admin_users(telegram_id, added_by, added_at) VALUES(?, ?, ?)',
            (123, 1, utcnow()),
        )
        row = await self.db.one('SELECT telegram_id FROM admin_users WHERE telegram_id = ?', (123,))
        self.assertEqual(row['telegram_id'], 123)

    async def test_settings_roundtrip(self):
        await self.db.set_setting('game_status', 'paused')
        self.assertEqual(await self.db.setting('game_status'), 'paused')


if __name__ == '__main__':
    unittest.main()
