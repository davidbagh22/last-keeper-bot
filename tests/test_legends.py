import unittest
from collections import Counter

from game_data import TEAM_COLORS
from legend_engine import (
    LOCATION_DILEMMAS,
    TEAM_FOUNDATIONS,
    VALUE_LABELS,
    legend_paragraph,
    legend_title,
    values_visual,
)
from team_games import TEAM_GAMES


class LegendEngineTests(unittest.TestCase):
    def test_every_live_location_has_two_value_dilemmas(self):
        self.assertEqual(set(LOCATION_DILEMMAS), {'culture', 'science', 'history', 'memory', 'open'})
        for location, dilemmas in LOCATION_DILEMMAS.items():
            self.assertEqual(len(dilemmas), 2, location)
            for dilemma in dilemmas:
                self.assertEqual(len(dilemma.options), 3)
                self.assertEqual(len({option.code for option in dilemma.options}), 3)
                self.assertTrue(all(option.effects for option in dilemma.options))

    def test_five_teams_have_different_foundational_legends(self):
        self.assertEqual(set(TEAM_FOUNDATIONS), set(TEAM_COLORS))
        titles = [TEAM_FOUNDATIONS[team][0] for team in TEAM_COLORS]
        texts = [TEAM_FOUNDATIONS[team][1] for team in TEAM_COLORS]
        self.assertEqual(len(set(titles)), 5)
        self.assertEqual(len(set(texts)), 5)

    def test_each_team_has_ten_games_for_ten_personal_choices(self):
        for team in TEAM_COLORS:
            self.assertEqual(len(TEAM_GAMES[team]), 10)

    def test_legend_is_deterministic_and_readable(self):
        values = Counter({'memory': 8, 'truth': 6, 'unity': 2})
        self.assertEqual(legend_title(values, 'Fallback'), 'Стражи подлинной памяти')
        self.assertIn(VALUE_LABELS['memory'], values_visual(values))
        self.assertIn('вы', legend_paragraph(values).lower())


if __name__ == '__main__':
    unittest.main()
