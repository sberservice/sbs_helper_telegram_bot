"""Тесты главного меню с единым сертификационным рангом."""

import unittest
from unittest.mock import patch


class TestMainMenuCertification(unittest.TestCase):
    """Проверки рендера главного меню по данным аттестации."""

    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.get_user_certification_summary')
    def test_main_menu_contains_certification_rank_and_metrics(self, mock_summary):
        """Проверка, что меню показывает ранг, тесты и категории из аттестации."""
        from src.common.messages import get_main_menu_message

        mock_summary.return_value = {
            'certification_points': 210,
            'rank_name': 'Специалист',
            'rank_icon': '⭐',
            'passed_tests_count': 9,
            'passed_categories_count': 4,
            'next_rank_name': 'Эксперт',
            'points_to_next_rank': 110,
            'last_passed_score': 87.5,
        }

        message = get_main_menu_message(1001, 'Иван')

        self.assertIn('Аттестационный ранг', message)
        self.assertIn('Пройдено тестов', message)
        self.assertIn('Освоено категорий', message)
        self.assertIn('Специалист', message)
        self.assertIn('87\\.5', message)

    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.get_user_certification_summary', side_effect=Exception('boom'))
    def test_main_menu_fallback_on_error(self, _mock_summary):
        """Проверка безопасного fallback при ошибке получения профиля аттестации."""
        from src.common.messages import get_main_menu_message, MESSAGE_MAIN_MENU

        message = get_main_menu_message(1002, 'Петр')

        self.assertEqual(message, MESSAGE_MAIN_MENU)


if __name__ == '__main__':
    unittest.main()
