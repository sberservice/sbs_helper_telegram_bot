"""Тесты DB-фильтрации терминов в Admin Web (GK Terms)."""

import unittest
from unittest.mock import MagicMock, patch


class TestGKTermsDBFilters(unittest.TestCase):
    """Тесты фильтров `get_terms_for_validation`."""

    @patch("admin_web.modules.gk_knowledge.db_terms.database.get_cursor")
    @patch("admin_web.modules.gk_knowledge.db_terms.database.get_db_connection")
    def test_min_confidence_filter_applied_to_sql(self, mock_get_conn, mock_get_cursor):
        """Порог confidence должен попадать в WHERE и в параметры запроса."""
        from admin_web.modules.gk_knowledge import db_terms

        conn_cm = MagicMock()
        conn = MagicMock()
        conn_cm.__enter__.return_value = conn
        conn_cm.__exit__.return_value = False
        mock_get_conn.return_value = conn_cm

        cursor_cm = MagicMock()
        cursor = MagicMock()
        cursor_cm.__enter__.return_value = cursor
        cursor_cm.__exit__.return_value = False
        mock_get_cursor.return_value = cursor_cm

        cursor.fetchone.return_value = {
            "cnt": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "fixed_terms": 0,
            "acronyms": 0,
        }
        cursor.fetchall.return_value = []

        rows, total, stats = db_terms.get_terms_for_validation(
            page=1,
            page_size=20,
            min_confidence=0.9,
        )

        self.assertEqual(rows, [])
        self.assertEqual(total, 0)
        self.assertEqual(stats["total"], 0)

        self.assertGreaterEqual(cursor.execute.call_count, 2)
        first_sql, first_params = cursor.execute.call_args_list[0][0]
        self.assertIn("t.confidence IS NOT NULL AND t.confidence >= %s", first_sql)
        self.assertIn(0.9, first_params)

    @patch("admin_web.modules.gk_knowledge.db_terms.database.get_cursor")
    @patch("admin_web.modules.gk_knowledge.db_terms.database.get_db_connection")
    def test_search_text_filter_applied_to_sql(self, mock_get_conn, mock_get_cursor):
        """Поиск по термину/определению должен попадать в WHERE и параметры."""
        from admin_web.modules.gk_knowledge import db_terms

        conn_cm = MagicMock()
        conn = MagicMock()
        conn_cm.__enter__.return_value = conn
        conn_cm.__exit__.return_value = False
        mock_get_conn.return_value = conn_cm

        cursor_cm = MagicMock()
        cursor = MagicMock()
        cursor_cm.__enter__.return_value = cursor
        cursor_cm.__exit__.return_value = False
        mock_get_cursor.return_value = cursor_cm

        cursor.fetchone.return_value = {
            "cnt": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "fixed_terms": 0,
            "acronyms": 0,
        }
        cursor.fetchall.return_value = []

        rows, total, stats = db_terms.get_terms_for_validation(
            page=1,
            page_size=20,
            search_text="ккт",
        )

        self.assertEqual(rows, [])
        self.assertEqual(total, 0)
        self.assertEqual(stats["total"], 0)

        self.assertGreaterEqual(cursor.execute.call_count, 2)
        first_sql, first_params = cursor.execute.call_args_list[0][0]
        self.assertIn("t.term LIKE %s ESCAPE", first_sql)
        self.assertIn("t.definition LIKE %s ESCAPE", first_sql)
        self.assertIn("%ккт%", first_params)


if __name__ == "__main__":
    unittest.main()
