import unittest

from game_data import TEAM_COLORS
from location_hosts import LOCATION_KEYS, current_key
from quest_common import main_menu
from route_config import ROUTES


class LocationHostTests(unittest.TestCase):
    def test_all_five_locations_have_host_role(self):
        self.assertEqual(LOCATION_KEYS, ('culture', 'science', 'history', 'memory', 'open'))
        self.assertEqual(len(set(LOCATION_KEYS)), 5)

    def test_current_location_respects_each_team_route(self):
        for team in TEAM_COLORS:
            route = ROUTES[team]
            self.assertEqual(current_key(team, set()), route[0])
            self.assertEqual(current_key(team, {route[0]}), route[1])
            self.assertIsNone(current_key(team, set(route)))

    def test_host_button_is_separate_from_admin_button(self):
        host_menu = main_menu(admin=False, host=True)
        host_texts = [button.text for row in host_menu.keyboard for button in row]
        self.assertIn('🎭 Панель ведущего', host_texts)
        self.assertNotIn('🛡 Управление проектом', host_texts)

        admin_menu = main_menu(admin=True, host=False)
        admin_texts = [button.text for row in admin_menu.keyboard for button in row]
        self.assertIn('🛡 Управление проектом', admin_texts)
        self.assertNotIn('🎭 Панель ведущего', admin_texts)


if __name__ == '__main__':
    unittest.main()
