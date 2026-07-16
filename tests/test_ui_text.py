import unittest

from ui_text import divider, section, stat


class UiTextTests(unittest.TestCase):
    def test_divider_is_compact(self):
        value = divider()
        self.assertTrue(value)
        self.assertLessEqual(len(value), 20)

    def test_section_has_emoji_and_bold_html(self):
        value = section('Сводка', '📌')
        self.assertIn('📌', value)
        self.assertIn('<b>Сводка</b>', value)

    def test_stat_is_readable(self):
        value = stat('Участников', 15, '👥')
        self.assertEqual(value, '👥 <b>Участников:</b> 15')


if __name__ == '__main__':
    unittest.main()
