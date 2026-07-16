import unittest

from game_data import TEAM_COLORS
from production_v6 import HOST_SCRIPTS, MECHANICS, SPACES, compact_menu, mechanic_for
from route_config import ROUTES
from team_games import GAMES


class ProductionV6Tests(unittest.TestCase):
    def test_participant_menu_has_four_primary_actions(self):
        labels = [button.text for row in compact_menu().keyboard for button in row]
        self.assertEqual(labels, ['📍 Сейчас', '🎮 Играть', '📜 Мой путь', '❓ Помощь'])

    def test_all_five_location_scripts_exist(self):
        self.assertEqual(set(HOST_SCRIPTS), {'culture', 'science', 'history', 'memory', 'open'})
        for opening, question in HOST_SCRIPTS.values():
            self.assertGreater(len(opening), 40)
            self.assertTrue(question.endswith('?'))

    def test_open_spaces_are_complete(self):
        self.assertEqual(len(SPACES), 7)
        self.assertEqual(len({key for key, _ in SPACES}), 7)

    def test_game_presentation_uses_all_mechanics(self):
        used = {mechanic_for(item.game_id)[0] for item in GAMES}
        self.assertEqual(used, {label for label, _ in MECHANICS})

    def test_150_participant_route_invariant(self):
        simulated = [(TEAM_COLORS[i % 5], ROUTES[TEAM_COLORS[i % 5]]) for i in range(150)]
        self.assertEqual(len(simulated), 150)
        counts = {team: sum(1 for assigned, _ in simulated if assigned == team) for team in TEAM_COLORS}
        self.assertEqual(set(counts.values()), {30})
        for _, route in simulated:
            self.assertEqual(len(route), 5)
            self.assertEqual(len(set(route)), 5)


if __name__ == '__main__':
    unittest.main()
