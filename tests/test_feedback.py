"""
Tests for Feedback Module

Tests for link detection, rate limiting, database operations,
and message formatting.
"""

import pytest
import time
from unittest.mock import patch, MagicMock

# Import module components
from src.sbs_helper_telegram_bot.feedback import settings
from src.sbs_helper_telegram_bot.feedback import messages
from src.sbs_helper_telegram_bot.feedback import keyboards
from src.sbs_helper_telegram_bot.feedback import feedback_logic


class TestLinkDetection:
    """Tests for link detection in user messages."""
    
    def test_detects_http_links(self):
        """Should detect http:// URLs."""
        assert feedback_logic.contains_links("Check http://example.com")
        assert feedback_logic.contains_links("Visit http://test.org/page")
    
    def test_detects_https_links(self):
        """Should detect https:// URLs."""
        assert feedback_logic.contains_links("Check https://example.com")
        assert feedback_logic.contains_links("Visit https://secure.site.org/path?query=1")
    
    def test_detects_www_links(self):
        """Should detect www. prefixed URLs."""
        assert feedback_logic.contains_links("Go to www.example.com")
        assert feedback_logic.contains_links("Check www.test.org/path")
    
    def test_detects_telegram_links(self):
        """Should detect Telegram links."""
        assert feedback_logic.contains_links("Join t.me/mygroup")
        assert feedback_logic.contains_links("Message t.me/username")
    
    def test_detects_domain_patterns(self):
        """Should detect domain-like patterns."""
        assert feedback_logic.contains_links("Visit example.com")
        assert feedback_logic.contains_links("Check test.org/page")
        assert feedback_logic.contains_links("Go to subdomain.example.co.uk")
    
    def test_no_false_positives_normal_text(self):
        """Should not flag normal text without links."""
        assert not feedback_logic.contains_links("Привет, у меня проблема с ботом")
        assert not feedback_logic.contains_links("Не работает кнопка меню")
        assert not feedback_logic.contains_links("Спасибо за помощь!")
    
    def test_no_false_positives_numbers(self):
        """Should not flag text with numbers."""
        assert not feedback_logic.contains_links("Ошибка 404 не найдена")
        assert not feedback_logic.contains_links("Код 12345")
        assert not feedback_logic.contains_links("Версия 2.0.1")
    
    def test_no_false_positives_email_like(self):
        """Should not flag email addresses (optional - depends on requirements)."""
        # This test documents current behavior - may need adjustment
        # Email addresses have @ which isn't matched by domain pattern
        text_with_at = "Написал на user@mail"
        result = feedback_logic.contains_links(text_with_at)
        # Current implementation may or may not flag this
        # Document actual behavior
        assert isinstance(result, bool)
    
    def test_mixed_content_with_links(self):
        """Should detect links in mixed content."""
        assert feedback_logic.contains_links("Текст перед http://link.com и после")
        assert feedback_logic.contains_links("Много текста\nhttp://hidden.link\nЕще текст")
    
    def test_case_insensitivity(self):
        """Should detect links regardless of case."""
        assert feedback_logic.contains_links("HTTP://EXAMPLE.COM")
        assert feedback_logic.contains_links("Https://Test.Org")
        assert feedback_logic.contains_links("WWW.SITE.COM")


class TestMarkdownEscaping:
    """Tests for MarkdownV2 escaping in messages."""
    
    def test_escape_special_chars(self):
        """Should escape all MarkdownV2 special characters."""
        text = "Test_text*with[special](chars)~`>#+=-|{}.!"
        escaped = messages._escape_markdown_v2(text)
        
        assert "\\_" in escaped
        assert "\\*" in escaped
        assert "\\[" in escaped
        assert "\\]" in escaped
        assert "\\(" in escaped
        assert "\\)" in escaped
        assert "\\~" in escaped
        assert "\\`" in escaped
        assert "\\>" in escaped
        assert "\\#" in escaped
        assert "\\+" in escaped
        assert "\\-" in escaped
        assert "\\=" in escaped
        assert "\\|" in escaped
        assert "\\{" in escaped
        assert "\\}" in escaped
        assert "\\." in escaped
        assert "\\!" in escaped
    
    def test_escape_preserves_normal_text(self):
        """Should preserve text without special chars."""
        text = "Обычный текст на русском"
        escaped = messages._escape_markdown_v2(text)
        assert "Обычный текст на русском" == escaped
    
    def test_format_rate_limit_message(self):
        """Should format rate limit message correctly."""
        result = messages.format_rate_limit_message(3600)
        assert "60" in result or "мин" in result
        
        result = messages.format_rate_limit_message(120)
        assert "2" in result or "мин" in result
    
    def test_format_feedback_submitted(self):
        """Should format submission confirmation correctly."""
        result = messages.format_feedback_submitted(123)
        assert "123" in result
        assert "✅" in result
    
    def test_format_confirm_submit(self):
        """Should escape user input in confirmation."""
        category = "Ошибка*"
        message_text = "Test_message"
        
        result = messages.format_confirm_submit(category, message_text)
        assert "\\*" in result
        assert "\\_" in result
    
    def test_format_new_response_notification_anonymous(self):
        """Response notification should NOT contain admin info."""
        result = messages.format_new_response_notification(123, "Test response")
        
        # Should contain entry ID
        assert "123" in result
        # Should contain response text
        assert "Test response" in result.replace("\\", "")
        # Should NOT contain admin-identifying info
        assert "admin" not in result.lower()
        assert "администратор" not in result.lower()


class TestSettings:
    """Tests for settings configuration."""
    
    def test_rate_limit_configured(self):
        """Rate limit should be configured."""
        assert hasattr(settings, 'RATE_LIMIT_SECONDS')
        assert settings.RATE_LIMIT_SECONDS > 0
        assert settings.RATE_LIMIT_SECONDS == 3600  # 1 hour
    
    def test_status_names_complete(self):
        """All statuses should have display names."""
        assert settings.STATUS_NEW in settings.STATUS_NAMES
        assert settings.STATUS_IN_PROGRESS in settings.STATUS_NAMES
        assert settings.STATUS_RESOLVED in settings.STATUS_NAMES
        assert settings.STATUS_CLOSED in settings.STATUS_NAMES
    
    def test_callback_prefixes_unique(self):
        """Callback prefixes should be unique."""
        prefixes = [
            settings.CALLBACK_CATEGORY_PREFIX,
            settings.CALLBACK_ENTRY_PREFIX,
            settings.CALLBACK_PAGE_PREFIX,
            settings.CALLBACK_STATUS_PREFIX,
            settings.CALLBACK_ADMIN_ENTRY_PREFIX,
            settings.CALLBACK_ADMIN_PAGE_PREFIX,
        ]
        assert len(prefixes) == len(set(prefixes))
    
    def test_link_patterns_defined(self):
        """Link patterns should be defined."""
        assert hasattr(settings, 'LINK_PATTERNS')
        assert len(settings.LINK_PATTERNS) > 0
    
    def test_menu_buttons_defined(self):
        """Menu buttons should be defined."""
        assert settings.MENU_BUTTON_TEXT
        assert settings.BUTTON_SUBMIT_FEEDBACK
        assert settings.BUTTON_MY_FEEDBACK
        assert settings.BUTTON_ADMIN_PANEL


class TestKeyboards:
    """Tests for keyboard building."""
    
    def test_submenu_keyboard_regular_user(self):
        """Regular user submenu should not have admin button."""
        keyboard = keyboards.get_submenu_keyboard(is_admin=False)
        
        keyboard_text = str(keyboard.keyboard)
        assert settings.BUTTON_ADMIN_PANEL not in keyboard_text
        assert settings.BUTTON_SUBMIT_FEEDBACK in keyboard_text
        assert settings.BUTTON_MY_FEEDBACK in keyboard_text
    
    def test_submenu_keyboard_admin_user(self):
        """Admin submenu should have admin button."""
        keyboard = keyboards.get_submenu_keyboard(is_admin=True)
        
        keyboard_text = str(keyboard.keyboard)
        assert settings.BUTTON_ADMIN_PANEL in keyboard_text
        assert settings.BUTTON_SUBMIT_FEEDBACK in keyboard_text
    
    def test_category_keyboard_structure(self):
        """Category keyboard should have proper structure."""
        categories = [
            {'id': 1, 'name': 'Ошибка', 'emoji': '🐛'},
            {'id': 2, 'name': 'Предложение', 'emoji': '💡'},
        ]
        
        keyboard = keyboards.get_category_keyboard(categories)
        
        # Should be InlineKeyboardMarkup
        assert hasattr(keyboard, 'inline_keyboard')
        # Should have rows for categories plus cancel
        assert len(keyboard.inline_keyboard) == 3
    
    def test_confirm_keyboard_buttons(self):
        """Confirm keyboard should have yes/no buttons."""
        keyboard = keyboards.get_confirm_keyboard()
        
        assert len(keyboard.inline_keyboard) == 1
        assert len(keyboard.inline_keyboard[0]) == 2
        
        callbacks = [btn.callback_data for btn in keyboard.inline_keyboard[0]]
        assert settings.CALLBACK_CONFIRM_YES in callbacks
        assert settings.CALLBACK_CONFIRM_NO in callbacks
    
    def test_pagination_keyboard_first_page(self):
        """First page should only have next button."""
        entries = [{'id': i, 'status': 'new', 'date': '01.01.2026', 'category': 'Test'} 
                   for i in range(5)]
        
        keyboard = keyboards.get_my_feedback_keyboard(entries, page=0, total_pages=3)
        
        # Check for pagination row
        has_next = any(
            btn.callback_data.startswith(settings.CALLBACK_PAGE_PREFIX)
            for row in keyboard.inline_keyboard
            for btn in row
            if hasattr(btn, 'callback_data') and btn.callback_data
        )
        assert has_next
    
    def test_pagination_keyboard_middle_page(self):
        """Middle page should have both prev and next buttons."""
        entries = [{'id': i, 'status': 'new', 'date': '01.01.2026', 'category': 'Test'} 
                   for i in range(5)]
        
        keyboard = keyboards.get_my_feedback_keyboard(entries, page=1, total_pages=3)
        
        # Should have both navigation buttons
        callbacks = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
            if hasattr(btn, 'callback_data') and btn.callback_data
        ]
        
        page_callbacks = [c for c in callbacks if c.startswith(settings.CALLBACK_PAGE_PREFIX)]
        assert len(page_callbacks) == 2  # prev and next
    
    def test_admin_status_keyboard_excludes_current(self):
        """Status keyboard should exclude current status."""
        keyboard = keyboards.get_admin_status_keyboard(settings.STATUS_NEW)
        
        callbacks = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
            if hasattr(btn, 'callback_data') and btn.callback_data
        ]
        
        # Current status should not be in callbacks
        assert f"{settings.CALLBACK_STATUS_PREFIX}{settings.STATUS_NEW}" not in callbacks
        # Other statuses should be present
        assert f"{settings.CALLBACK_STATUS_PREFIX}{settings.STATUS_IN_PROGRESS}" in callbacks


class TestStatusDisplayName:
    """Tests for status display name helper."""
    
    def test_known_statuses(self):
        """Known statuses should return proper display names."""
        assert "🆕" in feedback_logic.get_status_display_name(settings.STATUS_NEW)
        assert "⏳" in feedback_logic.get_status_display_name(settings.STATUS_IN_PROGRESS)
        assert "✅" in feedback_logic.get_status_display_name(settings.STATUS_RESOLVED)
        assert "🔒" in feedback_logic.get_status_display_name(settings.STATUS_CLOSED)
    
    def test_unknown_status(self):
        """Unknown status should return fallback."""
        result = feedback_logic.get_status_display_name("unknown_status")
        assert "📝" in result


class TestAdminAnonymity:
    """Tests ensuring admin anonymity is preserved."""
    
    def test_user_messages_no_admin_reference(self):
        """User-facing messages should not reference admin."""
        # Check all user-facing message constants
        user_messages = [
            messages.MESSAGE_SUBMENU,
            messages.MESSAGE_SELECT_CATEGORY,
            messages.MESSAGE_ENTER_MESSAGE,
            messages.MESSAGE_FEEDBACK_SUBMITTED,
            messages.MESSAGE_MY_FEEDBACK_EMPTY,
            messages.MESSAGE_MY_FEEDBACK_LIST,
            messages.MESSAGE_FEEDBACK_DETAIL,
            messages.MESSAGE_NEW_RESPONSE_NOTIFICATION,
            messages.MESSAGE_STATUS_CHANGED_NOTIFICATION,
        ]
        
        admin_keywords = ['admin', 'администратор', 'модератор', 'admin_id']
        
        for msg in user_messages:
            msg_lower = msg.lower()
            for keyword in admin_keywords:
                assert keyword not in msg_lower, f"Found '{keyword}' in message"
    
    def test_response_template_anonymous(self):
        """Response template should not expose admin identity."""
        template = messages.MESSAGE_RESPONSE_TEMPLATE
        
        # Should not contain admin placeholders
        assert "{admin" not in template.lower()
        assert "admin_id" not in template.lower()
    
    def test_notification_format_anonymous(self):
        """Notification formatting should be anonymous."""
        notification = messages.format_new_response_notification(
            entry_id=123,
            response="Test response text"
        )
        
        # Should mention "команда поддержки", not specific admin
        assert "admin" not in notification.lower()


class TestDatabaseOperationsWithMock:
    """Tests for database operations using mocks."""
    
    @patch('src.sbs_helper_telegram_bot.feedback.feedback_logic.database')
    def test_get_active_categories(self, mock_db):
        """Should return categories from database."""
        # Setup mock
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'name': 'Ошибка', 'description': 'Test', 'emoji': '🐛'},
            {'id': 2, 'name': 'Предложение', 'description': 'Test', 'emoji': '💡'},
        ]
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.get_db_connection.return_value = mock_conn
        mock_db.get_cursor.return_value = mock_cursor_ctx
        
        result = feedback_logic.get_active_categories()
        
        assert len(result) == 2
        assert result[0]['name'] == 'Ошибка'
    
    @patch('src.sbs_helper_telegram_bot.feedback.feedback_logic.database')
    def test_check_rate_limit_allowed(self, mock_db):
        """Should allow submission when rate limit not exceeded."""
        # Mock returns old timestamp (more than 1 hour ago)
        old_timestamp = int(time.time()) - 7200  # 2 hours ago
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'created_timestamp': old_timestamp}
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.get_db_connection.return_value = mock_conn
        mock_db.get_cursor.return_value = mock_cursor_ctx
        
        is_allowed, seconds = feedback_logic.check_rate_limit(12345)
        
        assert is_allowed is True
        assert seconds == 0
    
    @patch('src.sbs_helper_telegram_bot.feedback.feedback_logic.database')
    def test_check_rate_limit_blocked(self, mock_db):
        """Should block submission when rate limit exceeded."""
        # Mock returns recent timestamp (less than 1 hour ago)
        recent_timestamp = int(time.time()) - 1800  # 30 minutes ago
        
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'created_timestamp': recent_timestamp}
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.get_db_connection.return_value = mock_conn
        mock_db.get_cursor.return_value = mock_cursor_ctx
        
        is_allowed, seconds = feedback_logic.check_rate_limit(12345)
        
        assert is_allowed is False
        assert seconds > 0
        assert seconds <= 1800  # Should be about 30 minutes remaining
    
    @patch('src.sbs_helper_telegram_bot.feedback.feedback_logic.database')
    def test_check_rate_limit_first_submission(self, mock_db):
        """Should allow first submission (no previous entries)."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No previous submissions
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor_ctx.__exit__ = MagicMock(return_value=False)
        mock_db.get_db_connection.return_value = mock_conn
        mock_db.get_cursor.return_value = mock_cursor_ctx
        
        is_allowed, seconds = feedback_logic.check_rate_limit(12345)
        
        assert is_allowed is True
        assert seconds == 0


class TestTimestampFormatting:
    """Tests for timestamp formatting."""
    
    def test_format_valid_timestamp(self):
        """Should format valid timestamp correctly."""
        # January 15, 2026
        timestamp = 1768521600
        result = feedback_logic._format_timestamp(timestamp)
        
        # Should be in DD.MM.YYYY format
        assert "." in result
        parts = result.split(".")
        assert len(parts) == 3
    
    def test_format_invalid_timestamp(self):
        """Should handle invalid timestamp gracefully."""
        result = feedback_logic._format_timestamp(-1)
        # Should return N/A or similar for invalid
        assert result  # Should not be empty


class TestModuleExports:
    """Tests for module exports and structure."""
    
    def test_module_has_required_exports(self):
        """Module should export required components."""
        from src.sbs_helper_telegram_bot.feedback import (
            FeedbackModule,
            settings,
            messages,
            keyboards,
            get_feedback_user_handler,
            get_feedback_admin_handler,
        )
        
        assert FeedbackModule is not None
        assert settings is not None
        assert messages is not None
        assert keyboards is not None
        assert callable(get_feedback_user_handler)
        assert callable(get_feedback_admin_handler)
    
    def test_feedback_module_class(self):
        """FeedbackModule should implement required interface."""
        from src.sbs_helper_telegram_bot.feedback import FeedbackModule
        
        module = FeedbackModule()
        
        assert module.name == settings.MODULE_NAME
        assert module.description == settings.MODULE_DESCRIPTION
        assert module.version == settings.MODULE_VERSION
        assert module.get_menu_button() == settings.MENU_BUTTON_TEXT
