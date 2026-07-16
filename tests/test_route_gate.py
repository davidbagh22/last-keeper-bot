import tempfile
import unittest
from pathlib import Path

import app as game
from quest_common import current_stage, init_team_quest
from storage import Database, utcnow


class RouteGateIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db = game.db
        game.db = Database(str(Path(self.tempdir.name) / 'route-test.db'))
        await game.db.init()
        await init_team_quest()
        await game.db.execute(
            '''INSERT INTO users(
                telegram_id, username, full_name, age, organization, event_date,
                team, role, status, consent_at, created_at
            ) VALUES(1, 'tester', 'Тест Хранитель', 20, '', '2026-11-16',
                     'Красные', 'participant', 'confirmed', ?, ?)''',
            (utcnow(), utcnow()),
        )

    async def asyncTearDown(self):
        game.db = self.old_db
        self.tempdir.cleanup()

    async def test_codes_are_unique_four_digit_values(self):
        rows = await game.db.all('SELECT location_key, code FROM live_location_codes')
        self.assertEqual(len(rows), 5)
        codes = [str(row['code']) for row in rows]
        self.assertEqual(len(set(codes)), 5)
        self.assertTrue(all(code.isdigit() and len(code) == 4 for code in codes))

    async def test_next_stage_changes_only_after_unlock_record(self):
        user = await game.get_user(1)
        self.assertEqual(await current_stage(user), (0, 'culture'))
        await game.db.execute(
            '''INSERT INTO team_route_unlocks(
                event_date, team, location_key, step_index, unlocked_by, unlocked_at
            ) VALUES('2026-11-16', 'Красные', 'culture', 0, 1, ?)''',
            (utcnow(),),
        )
        user = await game.get_user(1)
        self.assertEqual(await current_stage(user), (1, 'science'))


if __name__ == '__main__':
    unittest.main()
