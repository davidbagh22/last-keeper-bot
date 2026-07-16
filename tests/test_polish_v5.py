import unittest

from polish_v5 import OPEN_SPACES_TEXT
from quest_common import main_menu


class PolishV5Tests(unittest.TestCase):
    def test_all_open_space_addresses_are_visible(self):
        expected = (
            'Фойе, 1 этаж',
            'Фойе выставочного зала, 2 этаж',
            'Фойе кинозала, 3 этаж',
            'Фойе, −1 этаж',
            'Лофт №3, −1 этаж',
            'Фойе, 3 этаж',
        )
        for address in expected:
            self.assertIn(address, OPEN_SPACES_TEXT)
        self.assertIn('VR-зона «Русская изба»', OPEN_SPACES_TEXT)
        self.assertIn('VR-зона «От Ивана IV до современной России»', OPEN_SPACES_TEXT)

    def test_butterfly_effect_is_visually_locked_in_menu(self):
        markup = main_menu()
        labels = [button.text for row in markup.keyboard for button in row]
        self.assertIn('◻️ Эффект бабочки', labels)
        self.assertNotIn('🦋 Состояние Архива', labels)

    def test_admin_labels_are_mobile_sized(self):
        labels = (
            '🎛 Команды', '🎨 Распределить', '🎭 Ведущие', '👤 Доступы',
            '📊 Прогресс', '💬 Вопросы', '📣 Рассылка', '📤 Экспорт',
            '🦋 Финал', '⚙️ Ещё',
        )
        self.assertTrue(all(len(label) <= 16 for label in labels))


if __name__ == '__main__':
    unittest.main()
