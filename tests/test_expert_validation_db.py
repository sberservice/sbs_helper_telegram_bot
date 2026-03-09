"""Тесты SQL-фильтров модуля экспертной валидации."""

import unittest
from unittest.mock import MagicMock, patch

from admin_web.modules.expert_validation import db as ev_db


class TestExpertValidationDbQuestionSearch(unittest.TestCase):
    """Проверка поиска по тексту вопроса в выборке Q&A-пар."""

    @patch("admin_web.modules.expert_validation.db.database.get_cursor")
    @patch("admin_web.modules.expert_validation.db.database.get_db_connection")
    def test_question_text_filter_is_added_to_queries(
        self,
        mock_get_db_connection,
        mock_get_cursor,
    ):
        """Фильтр question_text добавляется в COUNT и DATA запросы."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"total": 0}
        mock_cursor.fetchall.return_value = []

        rows, total = ev_db.get_qa_pairs_for_validation(
            page=1,
            page_size=20,
            question_text="ошибка_кассы%",
        )

        self.assertEqual(rows, [])
        self.assertEqual(total, 0)
        self.assertEqual(mock_cursor.execute.call_count, 2)

        count_query, count_params = mock_cursor.execute.call_args_list[0][0]
        data_query, data_params = mock_cursor.execute.call_args_list[1][0]

        self.assertIn("qp.question_text LIKE %s", count_query)
        self.assertIn("ESCAPE", count_query)
        self.assertEqual(count_params, ("%ошибка\\_кассы\\%%",))

        self.assertIn("qp.question_text LIKE %s", data_query)
        self.assertEqual(data_params, ("%ошибка\\_кассы\\%%", 20, 0))

    @patch("admin_web.modules.expert_validation.db.database.get_cursor")
    @patch("admin_web.modules.expert_validation.db.database.get_db_connection")
    def test_question_text_filter_keeps_expert_param_order(
        self,
        mock_get_db_connection,
        mock_get_cursor,
    ):
        """При JOIN с экспертом параметр expert_telegram_id остаётся первым."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"total": 0}
        mock_cursor.fetchall.return_value = []

        ev_db.get_qa_pairs_for_validation(
            page=2,
            page_size=10,
            question_text="чек",
            expert_telegram_id=777,
        )

        data_query, data_params = mock_cursor.execute.call_args_list[1][0]
        self.assertIn("LEFT JOIN gk_expert_validations ev", data_query)
        self.assertEqual(data_params[0], 777)
        self.assertEqual(data_params[1], "%чек%")
        self.assertEqual(data_params[-2:], (10, 10))


class TestExpertValidationDbReviewOrdering(unittest.TestCase):
    """Проверка порядка выдачи для режима экспертной проверки."""

    @patch("admin_web.modules.expert_validation.db.database.get_cursor")
    @patch("admin_web.modules.expert_validation.db.database.get_db_connection")
    def test_review_low_confidence_first_overrides_sorting(
        self,
        mock_get_db_connection,
        mock_get_cursor,
    ):
        """В режиме проверки пары сортируются по возрастанию confidence."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_get_cursor.return_value.__enter__.return_value = mock_cursor

        mock_cursor.fetchone.return_value = {"total": 0}
        mock_cursor.fetchall.return_value = []

        ev_db.get_qa_pairs_for_validation(
            page=1,
            page_size=20,
            sort_by="created_at",
            sort_order="desc",
            review_low_confidence_first=True,
        )

        data_query, data_params = mock_cursor.execute.call_args_list[1][0]
        self.assertIn("ORDER BY qp.confidence ASC, qp.created_at DESC, qp.id DESC", data_query)
        self.assertNotIn("ORDER BY qp.created_at DESC", data_query)
        self.assertEqual(data_params, (20, 0))


if __name__ == "__main__":
    unittest.main()
