import unittest

from game_data import LOCATIONS, final_archetype


class GameDataTests(unittest.TestCase):
    def test_locations_have_two_choices(self):
        self.assertEqual(set(LOCATIONS), {'culture', 'science', 'history', 'memory'})
        for location in LOCATIONS.values():
            self.assertEqual(len(location['choices']), 2)
            self.assertEqual(len(location['puzzle_options']), 3)

    def test_common_heritage(self):
        title, _, code = final_archetype({
            'memory': 4, 'unity': 4, 'cultural_code': 3,
            'responsibility': 4, 'truth': 2, 'living_language': 2,
        })
        self.assertEqual(title, 'Общее наследие')
        self.assertEqual(code, 'common_heritage')

    def test_living_archive(self):
        title, _, code = final_archetype({'living_language': 4, 'unity': 4, 'truth': 0})
        self.assertEqual(title, 'Живой архив')
        self.assertEqual(code, 'living_archive')

    def test_cold_progress(self):
        title, _, code = final_archetype({'progress': 6, 'unity': 0, 'cultural_code': 0})
        self.assertEqual(title, 'Холодный прогресс')
        self.assertEqual(code, 'cold_progress')


if __name__ == '__main__':
    unittest.main()
