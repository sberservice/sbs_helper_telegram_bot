"""
Unit tests for bot_settings module.

Tests cover:
- Getting and setting bot settings
- Invite system enabled/disabled logic
- User blocking based on invite system status
"""

import unittest
from unittest.mock import patch, MagicMock

from src.common.bot_settings import (
    get_setting,
    set_setting,
    is_invite_system_enabled,
    set_invite_system_enabled,
    check_if_user_from_invite,
    SETTING_INVITE_SYSTEM_ENABLED
)


class TestGetSetting(unittest.TestCase):
    """Tests for get_setting function."""

    @patch('src.common.bot_settings.database')
    def test_get_existing_setting(self, mock_database):
        """Test retrieving an existing setting."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = {'setting_value': 'test_value'}
        
        result = get_setting('test_key')
        
        self.assertEqual(result, 'test_value')
        mock_cursor.execute.assert_called_once()

    @patch('src.common.bot_settings.database')
    def test_get_nonexistent_setting(self, mock_database):
        """Test retrieving a non-existent setting returns None."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = None
        
        result = get_setting('nonexistent_key')
        
        self.assertIsNone(result)


class TestSetSetting(unittest.TestCase):
    """Tests for set_setting function."""

    @patch('src.common.bot_settings.database')
    def test_set_setting(self, mock_database):
        """Test setting a value."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        result = set_setting('test_key', 'test_value', 12345)
        
        self.assertTrue(result)
        mock_cursor.execute.assert_called_once()
        # Check that the query includes ON DUPLICATE KEY UPDATE
        query = mock_cursor.execute.call_args[0][0]
        self.assertIn('ON DUPLICATE KEY UPDATE', query)


class TestIsInviteSystemEnabled(unittest.TestCase):
    """Tests for is_invite_system_enabled function."""

    @patch('src.common.bot_settings.get_setting')
    def test_invite_system_enabled(self, mock_get_setting):
        """Test when invite system is enabled."""
        mock_get_setting.return_value = '1'
        
        result = is_invite_system_enabled()
        
        self.assertTrue(result)
        mock_get_setting.assert_called_once_with(SETTING_INVITE_SYSTEM_ENABLED)

    @patch('src.common.bot_settings.get_setting')
    def test_invite_system_disabled(self, mock_get_setting):
        """Test when invite system is disabled."""
        mock_get_setting.return_value = '0'
        
        result = is_invite_system_enabled()
        
        self.assertFalse(result)

    @patch('src.common.bot_settings.get_setting')
    def test_invite_system_default_enabled(self, mock_get_setting):
        """Test that invite system defaults to enabled when not set."""
        mock_get_setting.return_value = None
        
        result = is_invite_system_enabled()
        
        self.assertTrue(result)


class TestSetInviteSystemEnabled(unittest.TestCase):
    """Tests for set_invite_system_enabled function."""

    @patch('src.common.bot_settings.set_setting')
    def test_enable_invite_system(self, mock_set_setting):
        """Test enabling the invite system."""
        mock_set_setting.return_value = True
        
        result = set_invite_system_enabled(True, 12345)
        
        self.assertTrue(result)
        mock_set_setting.assert_called_once_with(SETTING_INVITE_SYSTEM_ENABLED, '1', 12345)

    @patch('src.common.bot_settings.set_setting')
    def test_disable_invite_system(self, mock_set_setting):
        """Test disabling the invite system."""
        mock_set_setting.return_value = True
        
        result = set_invite_system_enabled(False, 12345)
        
        self.assertTrue(result)
        mock_set_setting.assert_called_once_with(SETTING_INVITE_SYSTEM_ENABLED, '0', 12345)


class TestCheckIfUserFromInvite(unittest.TestCase):
    """Tests for check_if_user_from_invite function."""

    @patch('src.common.bot_settings.database')
    def test_user_from_invite_only(self, mock_database):
        """Test user who joined via invite and is not pre-invited."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        # First call: check invites, second call: check chat_members
        mock_cursor.fetchone.side_effect = [
            {'count': 1},  # User has consumed invite
            {'count': 0}   # User is not pre-invited
        ]
        
        result = check_if_user_from_invite(123456)
        
        self.assertTrue(result)

    @patch('src.common.bot_settings.database')
    def test_user_pre_invited_with_invite(self, mock_database):
        """Test user who is pre-invited AND has consumed invite."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        # First call: check invites, second call: check chat_members
        mock_cursor.fetchone.side_effect = [
            {'count': 1},  # User has consumed invite
            {'count': 1}   # User is also pre-invited
        ]
        
        result = check_if_user_from_invite(123456)
        
        # Should return False because they are pre-invited
        self.assertFalse(result)

    @patch('src.common.bot_settings.database')
    def test_user_no_invite(self, mock_database):
        """Test user who has not consumed any invite."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.side_effect = [
            {'count': 0},  # User has not consumed invite
            {'count': 0}   # User is not pre-invited
        ]
        
        result = check_if_user_from_invite(123456)
        
        # Should return False because they haven't used an invite
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
