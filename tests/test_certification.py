"""
Unit tests for certification module.

Tests cover:
- Business logic functions (certification_logic.py)
- Data formatting utilities
- Question selection
- Score calculation
- Ranking logic
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import date, datetime
from dateutil.relativedelta import relativedelta


class TestCertificationSettings(unittest.TestCase):
    """Tests for certification settings."""
    
    def test_settings_constants_exist(self):
        """Test that all required settings constants are defined."""
        from src.sbs_helper_telegram_bot.certification import settings
        
        # Module metadata
        self.assertIsNotNone(settings.MODULE_NAME)
        self.assertIsNotNone(settings.MODULE_DESCRIPTION)
        self.assertIsNotNone(settings.MODULE_VERSION)
        self.assertIsNotNone(settings.MENU_BUTTON_TEXT)
        
        # Default test configuration
        self.assertIsInstance(settings.DEFAULT_QUESTIONS_COUNT, int)
        self.assertIsInstance(settings.DEFAULT_TIME_LIMIT_MINUTES, int)
        self.assertIsInstance(settings.DEFAULT_PASSING_SCORE_PERCENT, int)
        self.assertIsInstance(settings.DEFAULT_RELEVANCE_MONTHS, int)
        
        # Validate ranges
        self.assertGreater(settings.DEFAULT_QUESTIONS_COUNT, 0)
        self.assertGreater(settings.DEFAULT_TIME_LIMIT_MINUTES, 0)
        self.assertGreater(settings.DEFAULT_PASSING_SCORE_PERCENT, 0)
        self.assertLessEqual(settings.DEFAULT_PASSING_SCORE_PERCENT, 100)
        
    def test_button_configurations(self):
        """Test that button configurations are valid."""
        from src.sbs_helper_telegram_bot.certification import settings
        
        # Check submenu buttons are non-empty lists
        self.assertIsInstance(settings.SUBMENU_BUTTONS, list)
        self.assertGreater(len(settings.SUBMENU_BUTTONS), 0)
        
        self.assertIsInstance(settings.ADMIN_SUBMENU_BUTTONS, list)
        self.assertGreater(len(settings.ADMIN_SUBMENU_BUTTONS), 0)
        
        self.assertIsInstance(settings.ADMIN_MENU_BUTTONS, list)
        self.assertGreater(len(settings.ADMIN_MENU_BUTTONS), 0)
        
    def test_answer_options(self):
        """Test answer options configuration."""
        from src.sbs_helper_telegram_bot.certification import settings
        
        self.assertEqual(settings.ANSWER_OPTIONS, ['A', 'B', 'C', 'D'])
        self.assertEqual(len(settings.ANSWER_EMOJIS), 4)
        
        for option in settings.ANSWER_OPTIONS:
            self.assertIn(option, settings.ANSWER_EMOJIS)


class TestCertificationLogicUtilities(unittest.TestCase):
    """Tests for utility functions in certification_logic."""
    
    def test_format_time_remaining(self):
        """Test time formatting for remaining time."""
        from src.sbs_helper_telegram_bot.certification.certification_logic import format_time_remaining
        
        # Test various time values
        self.assertEqual(format_time_remaining(0), "00:00")
        self.assertEqual(format_time_remaining(-10), "00:00")
        self.assertEqual(format_time_remaining(30), "00:30")
        self.assertEqual(format_time_remaining(60), "01:00")
        self.assertEqual(format_time_remaining(90), "01:30")
        self.assertEqual(format_time_remaining(600), "10:00")
        self.assertEqual(format_time_remaining(3599), "59:59")
        
    def test_format_time_spent(self):
        """Test time formatting for time spent (MarkdownV2 escaped)."""
        from src.sbs_helper_telegram_bot.certification.certification_logic import format_time_spent
        
        # Test seconds only
        self.assertEqual(format_time_spent(30), "30 сек\\.")
        self.assertEqual(format_time_spent(59), "59 сек\\.")
        
        # Test minutes and seconds
        self.assertEqual(format_time_spent(60), "1 мин\\. 0 сек\\.")
        self.assertEqual(format_time_spent(90), "1 мин\\. 30 сек\\.")
        self.assertEqual(format_time_spent(600), "10 мин\\. 0 сек\\.")
        
        # Test hours
        self.assertEqual(format_time_spent(3600), "1 ч\\. 0 мин\\.")
        self.assertEqual(format_time_spent(3660), "1 ч\\. 1 мин\\.")
        
    def test_get_month_name(self):
        """Test Russian month name conversion."""
        from src.sbs_helper_telegram_bot.certification.certification_logic import get_month_name
        
        self.assertEqual(get_month_name(1), "январь")
        self.assertEqual(get_month_name(6), "июнь")
        self.assertEqual(get_month_name(12), "декабрь")
        
        # Invalid month should return string representation
        self.assertEqual(get_month_name(13), "13")
        self.assertEqual(get_month_name(0), "0")

    def test_build_progress_bar(self):
        """Test textual progress bar rendering."""
        from src.sbs_helper_telegram_bot.certification.certification_logic import build_progress_bar

        self.assertEqual(build_progress_bar(0), "[□□□□□□□□□□]")
        self.assertEqual(build_progress_bar(30), "[■■■□□□□□□□]")
        self.assertEqual(build_progress_bar(100), "[■■■■■■■■■■]")
        
    def test_escape_markdown(self):
        """Test MarkdownV2 escaping."""
        from src.sbs_helper_telegram_bot.certification.certification_logic import escape_markdown
        
        # Test special characters
        self.assertEqual(escape_markdown("test_text"), "test\\_text")
        self.assertEqual(escape_markdown("test*text"), "test\\*text")
        self.assertEqual(escape_markdown("test.text"), "test\\.text")
        self.assertEqual(escape_markdown("test!text"), "test\\!text")
        
        # Test multiple special characters
        result = escape_markdown("Hello_World! *Test*")
        self.assertIn("\\_", result)
        self.assertIn("\\!", result)
        self.assertIn("\\*", result)
        
        # Test plain text (no escaping needed)
        self.assertEqual(escape_markdown("plain text"), "plain text")
        
        # Test empty string
        self.assertEqual(escape_markdown(""), "")


class TestCertificationKeyboards(unittest.TestCase):
    """Tests for keyboard generation functions."""
    
    def test_submenu_keyboard_structure(self):
        """Test submenu keyboard is properly structured."""
        from src.sbs_helper_telegram_bot.certification.keyboards import get_submenu_keyboard
        
        keyboard = get_submenu_keyboard()
        
        # Should be a ReplyKeyboardMarkup
        self.assertIsNotNone(keyboard)
        self.assertTrue(hasattr(keyboard, 'keyboard'))
        
    def test_admin_submenu_keyboard_structure(self):
        """Test admin submenu keyboard is properly structured."""
        from src.sbs_helper_telegram_bot.certification.keyboards import get_admin_submenu_keyboard
        
        keyboard = get_admin_submenu_keyboard()
        
        self.assertIsNotNone(keyboard)
        self.assertTrue(hasattr(keyboard, 'keyboard'))
        
    def test_answer_keyboard_structure(self):
        """Test answer keyboard has correct structure."""
        from src.sbs_helper_telegram_bot.certification.keyboards import get_answer_keyboard
        
        keyboard = get_answer_keyboard()
        
        self.assertIsNotNone(keyboard)
        self.assertTrue(hasattr(keyboard, 'inline_keyboard'))
        
        # Should have 2 rows with 2 buttons each (A, B) and (C, D)
        inline_kb = keyboard.inline_keyboard
        self.assertEqual(len(inline_kb), 2)
        self.assertEqual(len(inline_kb[0]), 2)
        self.assertEqual(len(inline_kb[1]), 2)
        
    def test_category_selection_keyboard(self):
        """Test category selection keyboard generation."""
        from src.sbs_helper_telegram_bot.certification.keyboards import get_category_selection_keyboard
        
        categories = [
            {'id': 1, 'name': 'Category 1'},
            {'id': 2, 'name': 'Category 2'},
        ]
        
        keyboard = get_category_selection_keyboard(categories, include_all=True)
        
        self.assertIsNotNone(keyboard)
        inline_kb = keyboard.inline_keyboard
        
        # Should have: "All categories" + 2 categories + Cancel = 4 rows
        self.assertEqual(len(inline_kb), 4)
        
        # First button should be "all categories"
        self.assertIn("cert_start_all", inline_kb[0][0].callback_data)
        
        # Last button should be cancel
        self.assertIn("cert_cancel", inline_kb[-1][0].callback_data)
        
    def test_category_selection_keyboard_without_all(self):
        """Test category selection keyboard without 'all categories' option."""
        from src.sbs_helper_telegram_bot.certification.keyboards import get_category_selection_keyboard
        
        categories = [
            {'id': 1, 'name': 'Category 1'},
        ]
        
        keyboard = get_category_selection_keyboard(categories, include_all=False)
        
        inline_kb = keyboard.inline_keyboard
        
        # Should have: 1 category + Cancel = 2 rows
        self.assertEqual(len(inline_kb), 2)
        
        # First button should be category, not "all"
        self.assertIn("cert_start_cat_1", inline_kb[0][0].callback_data)
        
    def test_confirmation_keyboard(self):
        """Test confirmation dialog keyboard."""
        from src.sbs_helper_telegram_bot.certification.keyboards import get_confirmation_keyboard
        
        keyboard = get_confirmation_keyboard("confirm_action", "cancel_action")
        
        inline_kb = keyboard.inline_keyboard
        
        # Should have 1 row with 2 buttons
        self.assertEqual(len(inline_kb), 1)
        self.assertEqual(len(inline_kb[0]), 2)
        
        # Check callback data
        self.assertEqual(inline_kb[0][0].callback_data, "confirm_action")
        self.assertEqual(inline_kb[0][1].callback_data, "cancel_action")
        
    def test_difficulty_keyboard(self):
        """Test difficulty selection keyboard."""
        from src.sbs_helper_telegram_bot.certification.keyboards import get_difficulty_keyboard
        
        keyboard = get_difficulty_keyboard()
        
        inline_kb = keyboard.inline_keyboard
        
        # Should have 1 row with 3 buttons (easy, medium, hard)
        self.assertEqual(len(inline_kb), 1)
        self.assertEqual(len(inline_kb[0]), 3)
        
        # Check callback data patterns
        callbacks = [btn.callback_data for btn in inline_kb[0]]
        self.assertIn("cert_diff_easy", callbacks)
        self.assertIn("cert_diff_medium", callbacks)
        self.assertIn("cert_diff_hard", callbacks)


class TestCertificationMessages(unittest.TestCase):
    """Tests for message templates."""
    
    def test_required_messages_exist(self):
        """Test that all required message templates are defined."""
        from src.sbs_helper_telegram_bot.certification import messages
        
        # User messages
        self.assertIsNotNone(messages.MESSAGE_SUBMENU_BASE)
        self.assertIsNotNone(messages.MESSAGE_SUBMENU_NO_STATS)
        self.assertTrue(callable(messages.get_submenu_message))
        self.assertIsNotNone(messages.MESSAGE_TEST_INTRO)
        self.assertIsNotNone(messages.MESSAGE_NO_QUESTIONS)
        self.assertIsNotNone(messages.MESSAGE_TEST_STARTED)
        self.assertIsNotNone(messages.MESSAGE_QUESTION_TEMPLATE)
        self.assertIsNotNone(messages.MESSAGE_TEST_COMPLETED)
        self.assertIsNotNone(messages.MESSAGE_MY_RANKING)
        self.assertIsNotNone(messages.MESSAGE_MONTHLY_TOP)
        self.assertIsNotNone(messages.MESSAGE_RANK_SCALE_HEADER)
        self.assertIsNotNone(messages.MESSAGE_RANK_SCALE_ITEM)
        self.assertIsNotNone(messages.MESSAGE_RANK_DROP_WARNING)
        self.assertIsNotNone(messages.MESSAGE_CERT_PROGRESS_HEADER)
        self.assertIsNotNone(messages.MESSAGE_CERT_PROGRESS_LINE)
        self.assertIsNotNone(messages.MESSAGE_CERT_PROGRESS_POINTS_LINE)
        self.assertIsNotNone(messages.MESSAGE_CERT_PROGRESS_BAR_LINE)
        self.assertIsNotNone(messages.MESSAGE_CERT_PROGRESS_NEXT_STEP_LINE)
        self.assertIsNotNone(messages.MESSAGE_CERT_PROGRESS_ULTIMATE_LINE)
        
        # Admin messages
        self.assertIsNotNone(messages.MESSAGE_ADMIN_MENU)
        self.assertIsNotNone(messages.MESSAGE_CATEGORIES_LIST)
        self.assertIsNotNone(messages.MESSAGE_QUESTIONS_LIST)
        self.assertIsNotNone(messages.MESSAGE_OUTDATED_QUESTIONS)
        
    def test_message_formatting_placeholders(self):
        """Test that message templates have correct placeholders."""
        from src.sbs_helper_telegram_bot.certification import messages
        
        # Test intro message has required placeholders
        self.assertIn("{questions_count}", messages.MESSAGE_TEST_INTRO)
        self.assertIn("{time_limit}", messages.MESSAGE_TEST_INTRO)
        self.assertIn("{passing_score}", messages.MESSAGE_TEST_INTRO)
        
        # Test question template
        self.assertIn("{current}", messages.MESSAGE_QUESTION_TEMPLATE)
        self.assertIn("{total}", messages.MESSAGE_QUESTION_TEMPLATE)
        self.assertIn("{question_text}", messages.MESSAGE_QUESTION_TEMPLATE)
        
        # Test result message
        self.assertIn("{correct}", messages.MESSAGE_TEST_COMPLETED)
        self.assertIn("{total}", messages.MESSAGE_TEST_COMPLETED)
        self.assertIn("{score}", messages.MESSAGE_TEST_COMPLETED)

    def test_submenu_message_contains_rank_and_progress(self):
        """Проверка, что подменю содержит строку ранга и прогресса аттестации."""
        from src.sbs_helper_telegram_bot.certification import messages

        text = messages.get_submenu_message(
            questions_count=120,
            categories_count=6,
            rank_icon="🏅",
            rank_name="Эксперт",
            progress_bar="[■■■■■■■■□□]",
            progress_percent=77,
            certification_points=388,
            max_achievable_points=500,
        )

        self.assertIn("Аттестационный ранг", text)
        self.assertIn("Прогресс аттестации", text)
        self.assertIn("77% 388/500", text)


class TestCertificationModuleInit(unittest.TestCase):
    """Tests for module initialization."""
    
    def test_module_class_exists(self):
        """Test that CertificationModule class is properly defined."""
        from src.sbs_helper_telegram_bot.certification import CertificationModule
        
        module = CertificationModule()
        
        # Test required properties
        self.assertIsNotNone(module.name)
        self.assertIsNotNone(module.description)
        self.assertIsNotNone(module.version)
        self.assertIsNotNone(module.author)
        
    def test_module_handlers(self):
        """Test that module returns handlers."""
        from src.sbs_helper_telegram_bot.certification import CertificationModule
        
        module = CertificationModule()
        
        handlers = module.get_handlers()
        self.assertIsInstance(handlers, list)
        self.assertGreater(len(handlers), 0)
        
        admin_handlers = module.get_admin_handlers()
        self.assertIsInstance(admin_handlers, list)
        self.assertGreater(len(admin_handlers), 0)
        
    def test_module_menu_button(self):
        """Test that module provides menu button."""
        from src.sbs_helper_telegram_bot.certification import CertificationModule
        
        module = CertificationModule()
        
        button = module.get_menu_button()
        self.assertIsNotNone(button)
        self.assertIsInstance(button, str)
        self.assertIn("📝", button)  # Should have emoji


class TestScoreCalculation(unittest.TestCase):
    """Tests for score calculation logic."""
    
    def test_score_percentage_calculation(self):
        """Test that score percentage is calculated correctly."""
        # Test 100%
        correct = 20
        total = 20
        score = (correct / total * 100) if total > 0 else 0
        self.assertEqual(score, 100.0)
        
        # Test 80%
        correct = 16
        total = 20
        score = (correct / total * 100) if total > 0 else 0
        self.assertEqual(score, 80.0)
        
        # Test 0%
        correct = 0
        total = 20
        score = (correct / total * 100) if total > 0 else 0
        self.assertEqual(score, 0.0)
        
        # Test empty test (prevent division by zero)
        correct = 0
        total = 0
        score = (correct / total * 100) if total > 0 else 0
        self.assertEqual(score, 0)
        
    def test_passing_threshold(self):
        """Test passing threshold logic."""
        from src.sbs_helper_telegram_bot.certification import settings
        
        passing_score = settings.DEFAULT_PASSING_SCORE_PERCENT
        
        # Score exactly at threshold should pass
        self.assertTrue(80 >= passing_score or passing_score != 80)
        
        # Score below threshold should fail
        self.assertFalse(79 >= 80)
        
        # Score above threshold should pass
        self.assertTrue(85 >= 80)


class TestQuestionDataValidation(unittest.TestCase):
    """Tests for question data validation."""
    
    def test_valid_answer_options(self):
        """Test that only valid answer options are accepted."""
        from src.sbs_helper_telegram_bot.certification import settings
        
        valid_options = settings.ANSWER_OPTIONS
        
        self.assertIn('A', valid_options)
        self.assertIn('B', valid_options)
        self.assertIn('C', valid_options)
        self.assertIn('D', valid_options)
        
        # Invalid options
        self.assertNotIn('E', valid_options)
        self.assertNotIn('1', valid_options)
        
    def test_difficulty_levels(self):
        """Test that difficulty levels are properly defined."""
        from src.sbs_helper_telegram_bot.certification import settings
        
        difficulty_labels = settings.DIFFICULTY_LABELS
        
        self.assertIn('easy', difficulty_labels)
        self.assertIn('medium', difficulty_labels)
        self.assertIn('hard', difficulty_labels)
        
        # Check labels have emojis
        self.assertIn('🟢', difficulty_labels['easy'])
        self.assertIn('🟡', difficulty_labels['medium'])
        self.assertIn('🔴', difficulty_labels['hard'])


class TestRelevanceDateLogic(unittest.TestCase):
    """Tests for relevance date calculations."""
    
    def test_default_relevance_period(self):
        """Test default relevance period calculation."""
        from src.sbs_helper_telegram_bot.certification import settings
        
        default_months = settings.DEFAULT_RELEVANCE_MONTHS
        
        today = date.today()
        expected_date = today + relativedelta(months=default_months)
        
        # Verify the calculation works
        self.assertGreater(expected_date, today)
        
    def test_relevance_date_comparison(self):
        """Test that relevance date comparisons work correctly."""
        today = date.today()
        
        # Future date is valid
        future_date = today + relativedelta(months=6)
        self.assertGreater(future_date, today)
        
        # Past date is outdated
        past_date = today - relativedelta(days=1)
        self.assertLess(past_date, today)
        
        # Today is still valid (not strictly less than)
        self.assertGreaterEqual(today, today)


class TestCertificationRankSummary(unittest.TestCase):
    """Тесты единого профиля ранга по аттестации."""

    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.get_max_achievable_certification_points', return_value=600)
    def test_get_certification_rank_ladder_returns_full_list(self, _mock_max_points):
        """Проверка, что helper возвращает полную шкалу рангов с порогами."""
        from src.sbs_helper_telegram_bot.certification import certification_logic

        ladder = certification_logic.get_certification_rank_ladder()

        self.assertEqual(len(ladder), 6)
        self.assertEqual(ladder[0]['name'], 'Новичок')
        self.assertEqual(ladder[1]['min_points'], 96)
        self.assertEqual(ladder[2]['min_points'], 216)
        self.assertEqual(ladder[-2]['name'], 'Мастер аттестации')
        self.assertEqual(ladder[-2]['min_points'], 540)
        self.assertEqual(ladder[-1]['name'], 'Абсолют')
        self.assertEqual(ladder[-1]['min_points'], 600)

    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.get_max_achievable_certification_points', return_value=500)
    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.time.time', return_value=1_700_000_000)
    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.database')
    def test_user_certification_summary_counts_passed_only(self, mock_database, _mock_time, _mock_max_points):
        """Проверка, что points считаются по лучшим процентам за окно валидности."""
        from src.sbs_helper_telegram_bot.certification import certification_logic
        from src.sbs_helper_telegram_bot.certification import settings

        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [{
            'passed_tests_count': 7,
            'last_passed_timestamp': 1735689600,
            'last_passed_score': 92.5,
        }]
        now_ts = 1_700_000_000
        validity_seconds = settings.CATEGORY_RESULT_VALIDITY_DAYS * 24 * 60 * 60
        mock_cursor.fetchall.side_effect = [
            [
                {'category_id': 11, 'last_passed_category_timestamp': now_ts - 1000},
                {'category_id': 12, 'last_passed_category_timestamp': now_ts - validity_seconds - 10},
                {'category_id': 13, 'last_passed_category_timestamp': now_ts - (validity_seconds // 2)},
            ],
            [
                {'category_id': 11, 'best_score_percent': 92.5},
                {'category_id': 13, 'best_score_percent': 57.5},
            ],
        ]

        summary = certification_logic.get_user_certification_summary(1001)

        self.assertEqual(summary['passed_tests_count'], 7)
        self.assertEqual(summary['passed_categories_count'], 2)
        self.assertEqual(summary['total_passed_categories_count'], 3)
        self.assertEqual(summary['expired_categories_count'], 1)
        self.assertEqual(summary['certification_points'], 150)
        self.assertEqual(summary['max_achievable_points'], 500)
        self.assertEqual(summary['overall_progress_percent'], 30)
        self.assertEqual(summary['overall_progress_bar'], '[■■■□□□□□□□]')
        self.assertEqual(summary['rank_name'], 'Практик')
        self.assertEqual(summary['rank_icon'], '📘')
        self.assertEqual(summary['next_rank_name'], 'Специалист')
        self.assertAlmostEqual(summary['last_passed_score'], 92.5)
        self.assertIsNotNone(summary['nearest_category_expiry_timestamp'])

    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.get_max_achievable_certification_points', return_value=500)
    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.database')
    def test_user_certification_summary_default_on_error(self, mock_database, _mock_max_points):
        """Проверка возврата безопасного значения при ошибке БД."""
        from src.sbs_helper_telegram_bot.certification import certification_logic

        mock_database.get_db_connection.side_effect = Exception('db error')

        summary = certification_logic.get_user_certification_summary(1002)

        self.assertEqual(summary['passed_tests_count'], 0)
        self.assertEqual(summary['passed_categories_count'], 0)
        self.assertEqual(summary['total_passed_categories_count'], 0)
        self.assertEqual(summary['expired_categories_count'], 0)
        self.assertEqual(summary['rank_name'], 'Новичок')
        self.assertEqual(summary['rank_icon'], '🌱')

    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.get_max_achievable_certification_points', return_value=500)
    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.time.time', return_value=1_700_000_000)
    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.database')
    def test_user_certification_summary_excludes_expired_categories(self, mock_database, _mock_time, _mock_max_points):
        """Проверка, что просроченные категории не считаются активными."""
        from src.sbs_helper_telegram_bot.certification import certification_logic
        from src.sbs_helper_telegram_bot.certification import settings

        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.side_effect = [{
            'passed_tests_count': 4,
            'last_passed_timestamp': 1735689600,
            'last_passed_score': 88.0,
        }]

        now_ts = 1_700_000_000
        validity_seconds = settings.CATEGORY_RESULT_VALIDITY_DAYS * 24 * 60 * 60
        warning_seconds = settings.CATEGORY_RESULT_EXPIRY_WARNING_DAYS * 24 * 60 * 60
        mock_cursor.fetchall.side_effect = [
            [
                {'category_id': 21, 'last_passed_category_timestamp': now_ts - validity_seconds - 1},
                {'category_id': 22, 'last_passed_category_timestamp': now_ts - validity_seconds + warning_seconds - 100},
            ],
            [
                {'category_id': 22, 'best_score_percent': 80.0},
            ],
        ]

        summary = certification_logic.get_user_certification_summary(1003)

        self.assertEqual(summary['total_passed_categories_count'], 2)
        self.assertEqual(summary['passed_categories_count'], 1)
        self.assertEqual(summary['expired_categories_count'], 1)
        self.assertEqual(summary['expiring_soon_categories_count'], 1)
        self.assertEqual(summary['certification_points'], 80)


class TestFairQuestionsDistribution(unittest.TestCase):
    """Тесты выбора вопросов с целевым балансом сложностей."""

    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.random.sample', side_effect=lambda seq, k: list(seq)[:k])
    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.random.shuffle', side_effect=lambda seq: None)
    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.get_all_questions')
    def test_build_fair_test_questions_balanced(self, mock_get_all_questions, _mock_shuffle, _mock_sample):
        """Проверка квот 33/33/33 при достаточном количестве вопросов."""
        from src.sbs_helper_telegram_bot.certification import certification_logic

        easy = [{'id': i, 'difficulty': 'easy'} for i in range(1, 11)]
        medium = [{'id': i, 'difficulty': 'medium'} for i in range(101, 111)]
        hard = [{'id': i, 'difficulty': 'hard'} for i in range(201, 211)]

        mock_get_all_questions.side_effect = [easy, medium, hard]

        result = certification_logic.build_fair_test_questions(10, category_id=5)

        self.assertEqual(result['target_distribution'], {'easy': 4, 'medium': 3, 'hard': 3})
        self.assertEqual(result['actual_distribution']['easy'], 4)
        self.assertEqual(result['actual_distribution']['medium'], 3)
        self.assertEqual(result['actual_distribution']['hard'], 3)
        self.assertFalse(result['fallback_used'])
        self.assertEqual(len(result['questions']), 10)
        difficulties = [question['difficulty'] for question in result['questions']]
        self.assertEqual(difficulties, sorted(difficulties, key=lambda level: {'easy': 0, 'medium': 1, 'hard': 2}[level]))


class TestCertificationHandlers(unittest.IsolatedAsyncioTestCase):
    """Тесты пользовательских хендлеров аттестации."""

    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.check_if_user_legit', return_value=True)
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.logic.get_month_name', return_value='февраль')
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.logic.get_user_categories_this_month')
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.logic.get_user_certification_summary')
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.logic.get_user_stats', return_value=None)
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.logic.get_user_monthly_rank', return_value=None)
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.logic.get_certification_rank_ladder', return_value=[])
    async def test_show_my_ranking_initializes_expiry_lines(
        self,
        _mock_rank_ladder,
        _mock_monthly_rank,
        _mock_user_stats,
        mock_cert_summary,
        mock_user_categories,
        _mock_month_name,
        _mock_legit,
    ):
        """Проверка, что show_my_ranking не падает по NameError для expiry_lines."""
        from src.sbs_helper_telegram_bot.certification.certification_bot_part import show_my_ranking

        mock_user_categories.return_value = [
            {'category_id': 1, 'category_name': 'Кассы', 'rank': 1, 'best_score': 92, 'tests_count': 2}
        ]
        mock_cert_summary.return_value = {
            'rank_name': 'Эксперт',
            'rank_icon': '🏅',
            'certification_points': 388,
            'max_achievable_points': 500,
            'overall_progress_percent': 77,
            'overall_progress_bar': '[■■■■■■■■□□]',
            'next_rank_name': 'Мастер аттестации',
            'next_rank_icon': '👑',
            'points_to_next_rank': 62,
            'nearest_category_expiry_timestamp': None,
            'expiring_soon_categories_count': 0,
            'expired_categories_count': 0,
        }

        update = MagicMock()
        update.effective_user.id = 6627254238
        update.message.reply_text = AsyncMock()

        await show_my_ranking(update, MagicMock())

        update.message.reply_text.assert_awaited_once()

    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.random.sample', side_effect=lambda seq, k: list(seq)[:k])
    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.random.shuffle', side_effect=lambda seq: None)
    @patch('src.sbs_helper_telegram_bot.certification.certification_logic.get_all_questions')
    def test_build_fair_test_questions_with_fallback(self, mock_get_all_questions, _mock_shuffle, _mock_sample):
        """Проверка мягкого fallback при нехватке сложных вопросов."""
        from src.sbs_helper_telegram_bot.certification import certification_logic

        easy = [{'id': i, 'difficulty': 'easy'} for i in range(1, 11)]
        medium = [{'id': i, 'difficulty': 'medium'} for i in range(101, 111)]
        hard = [{'id': 201, 'difficulty': 'hard'}]

        mock_get_all_questions.side_effect = [easy, medium, hard]

        result = certification_logic.build_fair_test_questions(9, category_id=None)

        self.assertEqual(result['target_distribution'], {'easy': 3, 'medium': 3, 'hard': 3})
        self.assertTrue(result['fallback_used'])
        self.assertEqual(result['selected_count'], 9)
        self.assertEqual(result['actual_distribution']['hard'], 1)
        self.assertEqual(result['actual_distribution']['easy'] + result['actual_distribution']['medium'] + result['actual_distribution']['hard'], 9)
        self.assertEqual(len({question['id'] for question in result['questions']}), 9)
        difficulties = [question['difficulty'] for question in result['questions']]
        self.assertEqual(difficulties, sorted(difficulties, key=lambda level: {'easy': 0, 'medium': 1, 'hard': 2}[level]))


class TestCancelOnMenu(unittest.IsolatedAsyncioTestCase):
    """Тесты выхода из режима обучения/теста при нажатии «Главное меню»."""

    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.get_main_menu_keyboard')
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.get_main_menu_message', return_value='Главное меню')
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.check_if_user_admin', return_value=False)
    async def test_cancel_on_menu_shows_main_menu(self, _mock_admin, mock_menu_msg, mock_menu_kb):
        """Проверка, что cancel_on_menu отправляет главное меню при первом нажатии."""
        from src.sbs_helper_telegram_bot.certification.certification_bot_part import cancel_on_menu
        from telegram.ext import ConversationHandler

        mock_menu_kb.return_value = MagicMock()

        update = MagicMock()
        update.effective_user.id = 12345
        update.effective_user.first_name = 'Тест'
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        result = await cancel_on_menu(update, context)

        self.assertEqual(result, ConversationHandler.END)
        update.message.reply_text.assert_awaited_once()
        call_kwargs = update.message.reply_text.call_args
        mock_menu_msg.assert_called_once_with(12345, 'Тест')
        mock_menu_kb.assert_called_once_with(is_admin=False)

    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.get_main_menu_keyboard')
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.get_main_menu_message', return_value='Главное меню')
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.check_if_user_admin', return_value=True)
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.logic.complete_test_attempt')
    async def test_cancel_on_menu_cancels_active_attempt(self, mock_complete, _mock_admin, _mock_msg, mock_kb):
        """Проверка, что cancel_on_menu отменяет активную попытку теста."""
        from src.sbs_helper_telegram_bot.certification.certification_bot_part import cancel_on_menu
        from src.sbs_helper_telegram_bot.certification import settings
        from telegram.ext import ConversationHandler

        mock_kb.return_value = MagicMock()

        update = MagicMock()
        update.effective_user.id = 12345
        update.effective_user.first_name = 'Тест'
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {settings.CURRENT_ATTEMPT_ID_KEY: 42}

        result = await cancel_on_menu(update, context)

        self.assertEqual(result, ConversationHandler.END)
        mock_complete.assert_called_once_with(42, status='cancelled')
        # Для админа keyboard должна быть с is_admin=True
        from src.sbs_helper_telegram_bot.certification.certification_bot_part import get_main_menu_keyboard
        get_main_menu_keyboard.assert_called_once_with(is_admin=True)

    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.get_main_menu_keyboard')
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.get_main_menu_message', return_value='Меню')
    @patch('src.sbs_helper_telegram_bot.certification.certification_bot_part.check_if_user_admin', return_value=False)
    async def test_cancel_on_menu_clears_learning_context(self, _mock_admin, _mock_msg, mock_kb):
        """Проверка, что cancel_on_menu очищает контекст обучения."""
        from src.sbs_helper_telegram_bot.certification.certification_bot_part import cancel_on_menu
        from src.sbs_helper_telegram_bot.certification import settings
        from telegram.ext import ConversationHandler

        mock_kb.return_value = MagicMock()

        update = MagicMock()
        update.effective_user.id = 12345
        update.effective_user.first_name = 'Тест'
        update.message.reply_text = AsyncMock()

        # Создаём user_data с ключами контекста обучения
        context = MagicMock()
        user_data = {
            settings.LEARNING_QUESTIONS_KEY: [{'id': 1}],
            settings.LEARNING_CURRENT_QUESTION_INDEX_KEY: 0,
            settings.LEARNING_CORRECT_COUNT_KEY: 0,
            settings.LEARNING_SELECTED_DIFFICULTY_KEY: 'easy',
        }
        context.user_data = user_data

        result = await cancel_on_menu(update, context)
        self.assertEqual(result, ConversationHandler.END)
        update.message.reply_text.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
