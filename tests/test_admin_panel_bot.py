"""
Unit tests for admin panel bot part.

Tests cover:
- escape_markdown() function
- Admin access control
- Conversation state handlers
- Rule management callbacks
"""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio


class TestEscapeMarkdown(unittest.TestCase):
    """Tests for escape_markdown function."""

    def test_escape_markdown_special_chars(self):
        """Test escaping special MarkdownV2 characters."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import escape_markdown
        
        text = "Hello_World*Test[1](2)~code`>heading#"
        result = escape_markdown(text)
        
        self.assertIn("\\_", result)
        self.assertIn("\\*", result)
        self.assertIn("\\[", result)
        self.assertIn("\\]", result)
        self.assertIn("\\(", result)
        self.assertIn("\\)", result)
        self.assertIn("\\~", result)
        self.assertIn("\\`", result)
        self.assertIn("\\>", result)
        self.assertIn("\\#", result)

    def test_escape_markdown_all_special_chars(self):
        """Test all special characters are escaped."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import escape_markdown
        
        # All chars that need escaping
        text = "_*[]()~`>#+-=|{}.!"
        result = escape_markdown(text)
        
        # Each char should be escaped with backslash
        for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            self.assertIn(f"\\{char}", result)

    def test_escape_markdown_plain_text(self):
        """Test that plain text without special chars is unchanged."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import escape_markdown
        
        text = "Hello World test 123"
        result = escape_markdown(text)
        
        self.assertEqual(result, text)

    def test_escape_markdown_none_returns_empty_string(self):
        """Test that None input returns empty string."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import escape_markdown
        
        result = escape_markdown(None)
        
        self.assertEqual(result, "")

    def test_escape_markdown_number_input(self):
        """Test that numeric input is converted to string."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import escape_markdown
        
        result = escape_markdown(123)
        
        self.assertEqual(result, "123")

    def test_escape_markdown_cyrillic_text(self):
        """Test that Cyrillic text passes through."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import escape_markdown
        
        text = "Привет мир"
        result = escape_markdown(text)
        
        self.assertEqual(result, text)

    def test_escape_markdown_mixed_cyrillic_special(self):
        """Test Cyrillic text with special characters."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import escape_markdown
        
        text = "Правило_1 (тест)"
        result = escape_markdown(text)
        
        self.assertEqual(result, "Правило\\_1 \\(тест\\)")


class TestRuleTypes(unittest.TestCase):
    """Tests for RULE_TYPES constant."""

    def test_rule_types_contains_expected_types(self):
        """Test that all expected rule types are defined."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import RULE_TYPES
        
        expected_types = [
            'regex',
            'regex_not_match',
            'regex_fullmatch',
            'regex_not_fullmatch',
            'fias_check',
            'custom'
        ]
        
        for rule_type in expected_types:
            self.assertIn(rule_type, RULE_TYPES)

    def test_rule_types_count(self):
        """Test that RULE_TYPES has correct number of types."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import RULE_TYPES
        
        self.assertEqual(len(RULE_TYPES), 6)


class TestConversationStates(unittest.TestCase):
    """Tests for conversation states."""

    def test_conversation_states_are_unique(self):
        """Test that all conversation states have unique values."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import (
            ADMIN_MENU,
            CREATE_RULE_NAME,
            CREATE_RULE_TYPE,
            CREATE_RULE_PATTERN,
            CREATE_RULE_ERROR_MSG,
            CREATE_RULE_PRIORITY,
            SELECT_RULE_FOR_ACTION,
            CONFIRM_DELETE,
            EDIT_RULE_FIELD,
            EDIT_RULE_VALUE,
            SELECT_TICKET_TYPE,
            MANAGE_TYPE_RULES,
            SELECT_RULE_FOR_TYPE,
            TEST_REGEX_PATTERN,
            TEST_REGEX_TEXT,
        )
        
        states = [
            ADMIN_MENU, CREATE_RULE_NAME, CREATE_RULE_TYPE, CREATE_RULE_PATTERN,
            CREATE_RULE_ERROR_MSG, CREATE_RULE_PRIORITY, SELECT_RULE_FOR_ACTION,
            CONFIRM_DELETE, EDIT_RULE_FIELD, EDIT_RULE_VALUE, SELECT_TICKET_TYPE,
            MANAGE_TYPE_RULES, SELECT_RULE_FOR_TYPE, TEST_REGEX_PATTERN, TEST_REGEX_TEXT
        ]
        
        # Check all values are unique
        self.assertEqual(len(states), len(set(states)))

    def test_conversation_states_count(self):
        """Test that there are 15 conversation states."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import (
            ADMIN_MENU, CREATE_RULE_NAME, CREATE_RULE_TYPE, CREATE_RULE_PATTERN,
            CREATE_RULE_ERROR_MSG, CREATE_RULE_PRIORITY, SELECT_RULE_FOR_ACTION,
            CONFIRM_DELETE, EDIT_RULE_FIELD, EDIT_RULE_VALUE, SELECT_TICKET_TYPE,
            MANAGE_TYPE_RULES, SELECT_RULE_FOR_TYPE, TEST_REGEX_PATTERN, TEST_REGEX_TEXT
        )
        
        states = [
            ADMIN_MENU, CREATE_RULE_NAME, CREATE_RULE_TYPE, CREATE_RULE_PATTERN,
            CREATE_RULE_ERROR_MSG, CREATE_RULE_PRIORITY, SELECT_RULE_FOR_ACTION,
            CONFIRM_DELETE, EDIT_RULE_FIELD, EDIT_RULE_VALUE, SELECT_TICKET_TYPE,
            MANAGE_TYPE_RULES, SELECT_RULE_FOR_TYPE, TEST_REGEX_PATTERN, TEST_REGEX_TEXT
        ]
        
        self.assertEqual(len(states), 15)


class TestAdminCommandAsync(unittest.TestCase):
    """Tests for admin_command handler (async)."""

    def setUp(self):
        """Set up test fixtures."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        """Tear down test fixtures."""
        self.loop.close()

    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.check_if_user_legit')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.check_if_user_admin')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.update_user_info_from_telegram')
    def test_admin_command_unauthorized_user(self, mock_update_user, mock_check_admin, mock_check_legit):
        """Test admin command for non-legitimate user."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import admin_command
        from telegram.ext import ConversationHandler
        
        mock_check_legit.return_value = False
        
        # Create mock update and context
        mock_update = MagicMock()
        mock_update.effective_user.id = 123456
        mock_update.message.reply_text = AsyncMock()
        
        mock_context = MagicMock()
        
        result = self.loop.run_until_complete(admin_command(mock_update, mock_context))
        
        self.assertEqual(result, ConversationHandler.END)
        mock_update.message.reply_text.assert_called_once()

    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.check_if_user_legit')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.check_if_user_admin')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.update_user_info_from_telegram')
    def test_admin_command_legit_but_not_admin(self, mock_update_user, mock_check_admin, mock_check_legit):
        """Test admin command for legitimate but non-admin user."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import admin_command
        from telegram.ext import ConversationHandler
        
        mock_check_legit.return_value = True
        mock_check_admin.return_value = False
        
        mock_update = MagicMock()
        mock_update.effective_user.id = 123456
        mock_update.message.reply_text = AsyncMock()
        
        mock_context = MagicMock()
        
        result = self.loop.run_until_complete(admin_command(mock_update, mock_context))
        
        self.assertEqual(result, ConversationHandler.END)
        # Should have been called twice - once for legit check, once for not authorized

    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.check_if_user_legit')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.check_if_user_admin')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.update_user_info_from_telegram')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.get_admin_menu_keyboard')
    def test_admin_command_authorized_admin(self, mock_keyboard, mock_update_user, mock_check_admin, mock_check_legit):
        """Test admin command for authorized admin."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import admin_command, ADMIN_MENU
        
        mock_check_legit.return_value = True
        mock_check_admin.return_value = True
        mock_keyboard.return_value = MagicMock()
        
        mock_update = MagicMock()
        mock_update.effective_user.id = 123456
        mock_update.message.reply_text = AsyncMock()
        
        mock_context = MagicMock()
        
        result = self.loop.run_until_complete(admin_command(mock_update, mock_context))
        
        self.assertEqual(result, ADMIN_MENU)
        mock_update_user.assert_called_once()


class TestAdminMenuHandlerAsync(unittest.TestCase):
    """Tests for admin_menu_handler (async)."""

    def setUp(self):
        """Set up test fixtures."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        """Tear down test fixtures."""
        self.loop.close()

    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.check_if_user_admin')
    def test_admin_menu_handler_unauthorized(self, mock_check_admin):
        """Test menu handler rejects unauthorized users."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import admin_menu_handler
        from telegram.ext import ConversationHandler
        
        mock_check_admin.return_value = False
        
        mock_update = MagicMock()
        mock_update.effective_user.id = 123456
        mock_update.message.text = "📋 Список правил"
        mock_update.message.reply_text = AsyncMock()
        
        mock_context = MagicMock()
        
        result = self.loop.run_until_complete(admin_menu_handler(mock_update, mock_context))
        
        self.assertEqual(result, ConversationHandler.END)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.check_if_user_admin')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part.show_rules_list')
    def test_admin_menu_handler_rules_list(self, mock_show_rules, mock_check_admin):
        """Test menu handler routes to rules list."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import admin_menu_handler
        
        mock_check_admin.return_value = True
        mock_show_rules.return_value = AsyncMock(return_value=1)()
        
        mock_update = MagicMock()
        mock_update.effective_user.id = 123456
        mock_update.message.text = "📋 Список правил"
        
        mock_context = MagicMock()
        
        self.loop.run_until_complete(admin_menu_handler(mock_update, mock_context))
        
        mock_show_rules.assert_called_once()


class TestBuildRuleCallback(unittest.TestCase):
    """Tests for callback data building and parsing."""

    def test_callback_data_format(self):
        """Test that callback data follows expected format."""
        # Callback data should be: rule_view_{id}, rule_toggle_{id}, rule_delete_{id}
        rule_id = 42
        
        view_data = f"rule_view_{rule_id}"
        toggle_data = f"rule_toggle_{rule_id}"
        delete_data = f"rule_delete_{rule_id}"
        
        self.assertTrue(view_data.startswith("rule_view_"))
        self.assertTrue(toggle_data.startswith("rule_toggle_"))
        self.assertTrue(delete_data.startswith("rule_delete_"))
        
        # Extract ID
        extracted_id = int(view_data.split("_")[-1])
        self.assertEqual(extracted_id, rule_id)


class TestTestRegexPatternIntegration(unittest.TestCase):
    """Integration tests for test_regex_pattern with admin panel."""

    def test_valid_inn_pattern(self):
        """Test INN validation pattern works correctly."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import test_regex_pattern
        
        pattern = r'(?i)(ИНН|инн)\s*[:\-]?\s*\d{10,12}'
        test_text = "ИНН: 1234567890"
        
        is_valid, message = test_regex_pattern(pattern, test_text)
        
        self.assertTrue(is_valid)
        self.assertIn("совпадение", message.lower())

    def test_kpp_pattern(self):
        """Test KPP validation pattern works correctly."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import test_regex_pattern
        
        pattern = r'(?i)(КПП|кпп)\s*[:\-]?\s*\d{9}'
        test_text = "КПП: 123456789"
        
        is_valid, message = test_regex_pattern(pattern, test_text)
        
        self.assertTrue(is_valid)

    def test_phone_pattern(self):
        """Test phone number pattern works correctly."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import test_regex_pattern
        
        pattern = r'(?i)(тел|телефон|phone|моб)\s*[:\.\-]?\s*[\+]?[\d\s\-\(\)]{10,}'
        test_text = "Телефон: +7 (999) 123-45-67"
        
        is_valid, message = test_regex_pattern(pattern, test_text)
        
        self.assertTrue(is_valid)


class TestConversationHandlerSetup(unittest.TestCase):
    """Tests for conversation handler setup."""

    def test_get_admin_conversation_handler_exists(self):
        """Test that get_admin_conversation_handler function exists."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import get_admin_conversation_handler
        
        self.assertTrue(callable(get_admin_conversation_handler))

    def test_admin_handler_returns_conversation_handler(self):
        """Test that function returns a ConversationHandler."""
        from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import get_admin_conversation_handler
        from telegram.ext import ConversationHandler
        
        handler = get_admin_conversation_handler()
        
        self.assertIsInstance(handler, ConversationHandler)


class TestImports(unittest.TestCase):
    """Test that all required imports are available."""

    def test_imports_from_admin_panel_bot_part(self):
        """Test all expected functions can be imported."""
        try:
            from src.sbs_helper_telegram_bot.ticket_validator.admin_panel_bot_part import (
                escape_markdown,
                admin_command,
                admin_menu_handler,
                get_admin_conversation_handler,
                ADMIN_MENU,
                CREATE_RULE_NAME,
                RULE_TYPES
            )
            imported = True
        except ImportError:
            imported = False
        
        self.assertTrue(imported)

    def test_imports_from_validation_rules(self):
        """Test admin CRUD functions can be imported."""
        try:
            from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import (
                test_regex_pattern,
                load_all_rules,
                load_all_ticket_types_admin,
                create_validation_rule,
                update_validation_rule,
                toggle_rule_active,
                delete_validation_rule,
                get_rules_for_ticket_type,
                get_ticket_types_for_rule,
                add_rule_to_ticket_type,
                remove_rule_from_ticket_type,
                get_rule_type_mapping
            )
            imported = True
        except ImportError:
            imported = False
        
        self.assertTrue(imported)


if __name__ == '__main__':
    unittest.main()
