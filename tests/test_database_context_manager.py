import unittest
from unittest.mock import MagicMock, patch

from src.common import database


class TestDatabaseContextManager(unittest.TestCase):
    """Тесты контекстных менеджеров для подключений к БД."""

    def setUp(self):
        """Сбросить пул перед каждым тестом, чтобы моки применялись корректно."""
        database.reset_pool()

    def tearDown(self):
        """Сбросить пул после каждого теста."""
        database.reset_pool()

    @patch("src.common.database._get_pool")
    def test_get_db_connection_commits_on_success(self, mock_get_pool):
        """Commit должен вызываться, когда нет исключения (пул)."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        with database.get_db_connection() as conn:
            self.assertIs(conn, mock_conn)

        mock_conn.commit.assert_called_once()
        mock_conn.rollback.assert_not_called()
        mock_conn.close.assert_called_once()

    @patch("src.common.database._get_pool")
    def test_get_db_connection_rolls_back_on_exception(self, mock_get_pool):
        """Rollback должен вызываться при исключении (пул)."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_conn
        mock_get_pool.return_value = mock_pool

        with self.assertRaises(ValueError):
            with database.get_db_connection():
                raise ValueError("boom")

        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()
        mock_conn.close.assert_called_once()

    @patch("src.common.database.mysql.connector.connect")
    def test_get_db_connection_custom_params_bypass_pool(self, mock_connect):
        """При нестандартных параметрах пул не используется, создаётся прямое подключение."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True
        mock_connect.return_value = mock_conn

        with database.get_db_connection(host="other_host") as conn:
            self.assertIs(conn, mock_conn)

        mock_connect.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_get_cursor_closes_cursor(self):
        """Курсор должен закрываться после выхода из контекстного менеджера."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with database.get_cursor(mock_conn) as cursor:
            self.assertIs(cursor, mock_cursor)

        mock_cursor.close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
