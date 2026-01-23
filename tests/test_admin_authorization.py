"""
Unit tests for admin authorization functions.

Tests cover:
- check_if_user_admin() function
- set_user_admin() function
- Edge cases and error handling
"""

import unittest
from unittest.mock import patch, MagicMock


class TestCheckIfUserAdmin(unittest.TestCase):
    """Tests for check_if_user_admin function."""

    @patch('src.common.telegram_user.database.get_db_connection')
    @patch('src.common.telegram_user.database.get_cursor')
    def test_check_if_user_admin_returns_true_when_admin(self, mock_get_cursor, mock_get_conn):
        """Test that check_if_user_admin returns True when user has is_admin=1."""
        from src.common.telegram_user import check_if_user_admin
        
        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"is_admin": 1}
        
        # Execute
        result = check_if_user_admin(123456)
        
        # Assert
        self.assertTrue(result)
        mock_cursor.execute.assert_called_once()
        
    @patch('src.common.telegram_user.database.get_db_connection')
    @patch('src.common.telegram_user.database.get_cursor')
    def test_check_if_user_admin_returns_false_when_not_admin(self, mock_get_cursor, mock_get_conn):
        """Test that check_if_user_admin returns False when user has is_admin=0."""
        from src.common.telegram_user import check_if_user_admin
        
        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"is_admin": 0}
        
        # Execute
        result = check_if_user_admin(123456)
        
        # Assert
        self.assertFalse(result)

    @patch('src.common.telegram_user.database.get_db_connection')
    @patch('src.common.telegram_user.database.get_cursor')
    def test_check_if_user_admin_returns_false_when_user_not_found(self, mock_get_cursor, mock_get_conn):
        """Test that check_if_user_admin returns False when user doesn't exist."""
        from src.common.telegram_user import check_if_user_admin
        
        # Setup mock - no result
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = None
        
        # Execute
        result = check_if_user_admin(999999)
        
        # Assert
        self.assertFalse(result)

    @patch('src.common.telegram_user.database.get_db_connection')
    @patch('src.common.telegram_user.database.get_cursor')
    def test_check_if_user_admin_uses_correct_sql(self, mock_get_cursor, mock_get_conn):
        """Test that correct SQL query is used for admin check."""
        from src.common.telegram_user import check_if_user_admin
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"is_admin": 0}
        
        telegram_id = 123456
        check_if_user_admin(telegram_id)
        
        # Verify the SQL and parameters
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        self.assertIn("is_admin", sql.lower())
        self.assertIn("users", sql.lower())
        self.assertEqual(params, (telegram_id,))


class TestSetUserAdmin(unittest.TestCase):
    """Tests for set_user_admin function."""

    @patch('src.common.telegram_user.database.get_db_connection')
    @patch('src.common.telegram_user.database.get_cursor')
    def test_set_user_admin_grant_admin_success(self, mock_get_cursor, mock_get_conn):
        """Test granting admin status to a user."""
        from src.common.telegram_user import set_user_admin
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        
        result = set_user_admin(123456, True)
        
        self.assertTrue(result)
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[0], 1)  # is_admin = 1
        self.assertEqual(params[1], 123456)  # telegram_id

    @patch('src.common.telegram_user.database.get_db_connection')
    @patch('src.common.telegram_user.database.get_cursor')
    def test_set_user_admin_revoke_admin_success(self, mock_get_cursor, mock_get_conn):
        """Test revoking admin status from a user."""
        from src.common.telegram_user import set_user_admin
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        
        result = set_user_admin(123456, False)
        
        self.assertTrue(result)
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[0], 0)  # is_admin = 0
        self.assertEqual(params[1], 123456)  # telegram_id

    @patch('src.common.telegram_user.database.get_db_connection')
    @patch('src.common.telegram_user.database.get_cursor')
    def test_set_user_admin_returns_false_when_user_not_found(self, mock_get_cursor, mock_get_conn):
        """Test that set_user_admin returns False when user doesn't exist."""
        from src.common.telegram_user import set_user_admin
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 0  # No rows updated
        
        result = set_user_admin(999999, True)
        
        self.assertFalse(result)

    @patch('src.common.telegram_user.database.get_db_connection')
    @patch('src.common.telegram_user.database.get_cursor')
    def test_set_user_admin_default_is_true(self, mock_get_cursor, mock_get_conn):
        """Test that is_admin defaults to True when not specified."""
        from src.common.telegram_user import set_user_admin
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        
        set_user_admin(123456)  # No second argument
        
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[0], 1)  # is_admin = 1 (default True)


if __name__ == '__main__':
    unittest.main()
