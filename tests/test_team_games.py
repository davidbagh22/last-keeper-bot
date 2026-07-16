import unittest

from game_data import TEAM_COLORS
from route_config import ROUTES
from team_games import (
    GAMES,
    GAMES_BY_ID,
    GAMES_BY_TEAM_LOCATION,
    TEAM_GAMES,
    presented_correct_index,
    presented_options,
    validate_catalog,
)


class TeamGameCatalogTests(unittest.TestCase):
    def test_catalog_is_complete(self):
        self.assertEqual(validate_catalog(), [])
        self.assertEqual(len(GAMES), 50)
        self.assertEqual(len(GAMES_BY_ID), 50)

    def test_each_team_has_ten_unique_games(self):
        for team in TEAM_COLORS:
            games = TEAM_GAMES[team]
            self.assertEqual(len(games), 10)
            self.assertEqual(len({item.game_id for item in games}), 10)

    def test_two_games_are_attached_to_every_live_stage(self):
        for team in TEAM_COLORS:
            self.assertEqual(set(ROUTES[team]), {'culture', 'science', 'history', 'memory', 'open'})
            for location in ROUTES[team]:
                pair = GAMES_BY_TEAM_LOCATION[(team, location)]
                self.assertEqual(len(pair), 2)
                self.assertTrue(all(item.team == team for item in pair))
                self.assertTrue(all(item.location == location for item in pair))

    def test_mobile_buttons_can_remain_numeric(self):
        for item in GAMES:
            self.assertGreaterEqual(len(item.options), 2)
            self.assertLessEqual(len(item.options), 4)
            self.assertIn(item.correct, range(len(item.options)))

    def test_correct_answer_is_not_always_the_first_button(self):
        for team in TEAM_COLORS:
            positions = [presented_correct_index(item) for item in TEAM_GAMES[team]]
            self.assertGreater(len(set(positions)), 1, team)
            self.assertIn(0, positions)
            self.assertTrue(any(position > 0 for position in positions))

    def test_rotation_preserves_the_real_answer(self):
        for item in GAMES:
            shown = presented_options(item)
            shown_correct = presented_correct_index(item)
            self.assertEqual(shown[shown_correct], item.options[item.correct])


if __name__ == '__main__':
    unittest.main()
