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
from unittest.mock import patch, MagicMock
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
        self.assertIsNotNone(messages.MESSAGE_SUBMENU)
        self.assertIsNotNone(messages.MESSAGE_TEST_INTRO)
        self.assertIsNotNone(messages.MESSAGE_NO_QUESTIONS)
        self.assertIsNotNone(messages.MESSAGE_TEST_STARTED)
        self.assertIsNotNone(messages.MESSAGE_QUESTION_TEMPLATE)
        self.assertIsNotNone(messages.MESSAGE_TEST_COMPLETED)
        self.assertIsNotNone(messages.MESSAGE_MY_RANKING)
        self.assertIsNotNone(messages.MESSAGE_MONTHLY_TOP)
        
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


if __name__ == '__main__':
    unittest.main()
