import unittest

from expert_ux import answer_keyboard, main_menu, numbered_options, progress_bar


class ExpertUxTests(unittest.TestCase):
    def test_progress_bar_is_stable(self):
        self.assertEqual(progress_bar(0, 4), '□□□□')
        self.assertEqual(progress_bar(2, 4), '■■□□')
        self.assertEqual(progress_bar(9, 4), '■■■■')

    def test_full_poll_text_is_in_message(self):
        options = (
            'Очень длинный вариант ответа, который не должен помещаться на кнопку',
            'Второй полный вариант ответа',
            'Третий полный вариант ответа',
        )
        rendered = numbered_options(options)
        for option in options:
            self.assertIn(option, rendered)
        self.assertIn('1️⃣', rendered)
        self.assertIn('3️⃣', rendered)

    def test_answer_buttons_are_short_numbers(self):
        markup = answer_keyboard('puzzle-answer:science', 3)
        texts = [button.text for row in markup.inline_keyboard for button in row]
        data = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertEqual(texts, ['1️⃣', '2️⃣', '3️⃣'])
        self.assertEqual(
            data,
            [
                'puzzle-answer:science:0',
                'puzzle-answer:science:1',
                'puzzle-answer:science:2',
            ],
        )

    def test_main_menu_explains_actions(self):
        markup = main_menu(admin=True)
        texts = [button.text for row in markup.keyboard for button in row]
        self.assertIn('📍 Куда идти', texts)
        self.assertIn('🧩 Испытания', texts)
        self.assertIn('ℹ️ Как играть', texts)
        self.assertIn('🛡 Панель Архивариуса', texts)


if __name__ == '__main__':
    unittest.main()
