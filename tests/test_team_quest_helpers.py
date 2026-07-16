import unittest

from game_data import TEAM_COLORS
from route_config import ROUTES
from team_quest import ordered_games, progress_bar


class TeamQuestHelperTests(unittest.TestCase):
    def test_progress_bar(self):
        self.assertEqual(progress_bar(0, 5), '□□□□□')
        self.assertEqual(progress_bar(3, 5), '■■■□□')
        self.assertEqual(progress_bar(9, 5), '■■■■■')

    def test_games_follow_each_team_route(self):
        for team in TEAM_COLORS:
            games = ordered_games(team)
            self.assertEqual(len(games), 10)
            locations = [item.location for item in games]
            expected = [location for location in ROUTES[team] for _ in range(2)]
            self.assertEqual(locations, expected)


if __name__ == '__main__':
    unittest.main()
