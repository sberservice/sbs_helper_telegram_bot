import unittest
from unittest.mock import MagicMock, patch

from src.common import database


class TestDatabaseContextManager(unittest.TestCase):
    """Tests for database context managers."""

    @patch("src.common.database.mysql.connector.connect")
    def test_get_db_connection_commits_on_success(self, mock_connect):
        """Commit should be called when no exception occurs."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_connect.return_value = mock_conn

        with database.get_db_connection() as conn:
            self.assertIs(conn, mock_conn)

        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()
        mock_conn.close.assert_called_once()

    @patch("src.common.database.mysql.connector.connect")
    def test_get_db_connection_rolls_back_on_exception(self, mock_connect):
        """Rollback should be called when an exception occurs."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_connect.return_value = mock_conn

        with self.assertRaises(ValueError):
            with database.get_db_connection():
                raise ValueError("boom")

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
        mock_conn.close.assert_called_once()

    def test_get_cursor_closes_cursor(self):
        """Cursor should be closed after context manager exits."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with database.get_cursor(mock_conn) as cursor:
            self.assertIs(cursor, mock_cursor)

        mock_cursor.close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
