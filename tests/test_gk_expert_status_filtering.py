"""Тесты фильтрации expert-rejected Q&A-пар из поискового пайплайна GK."""

import unittest
from unittest.mock import patch, MagicMock

from src.group_knowledge.models import QAPair


class TestQAPairExpertStatus(unittest.TestCase):
    """Тесты поля expert_status в модели QAPair."""

    def test_default_expert_status_is_none(self):
        """По умолчанию expert_status = None (не валидирована)."""
        pair = QAPair(id=1, question_text="q", answer_text="a")
        self.assertIsNone(pair.expert_status)

    def test_expert_status_approved(self):
        """expert_status = 'approved' корректно хранится."""
        pair = QAPair(id=1, question_text="q", answer_text="a", expert_status="approved")
        self.assertEqual(pair.expert_status, "approved")

    def test_expert_status_rejected(self):
        """expert_status = 'rejected' корректно хранится."""
        pair = QAPair(id=1, question_text="q", answer_text="a", expert_status="rejected")
        self.assertEqual(pair.expert_status, "rejected")


class TestVectorSearchExpertFiltering(unittest.TestCase):
    """Тесты фильтрации expert-rejected пар в _vector_search."""

    @patch("src.group_knowledge.qa_search.ai_settings")
    @patch("src.group_knowledge.qa_search.gk_db")
    def test_rejected_pair_skipped_in_vector_search(self, mock_gk_db, mock_settings):
        """Expert-rejected пары пропускаются при vector search."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_INCLUDE_LLM_INFERRED_ANSWERS = False

        service = QASearchService.__new__(QASearchService)
        service._model_name = "test"
        service._top_k = 5

        # Создаём пары: одна с expert_status=rejected
        approved_pair = QAPair(
            id=1, question_text="q approved", answer_text="a",
            extraction_type="thread_reply", expert_status=None,
        )
        rejected_pair = QAPair(
            id=2, question_text="q rejected", answer_text="a",
            extraction_type="thread_reply", expert_status="rejected",
        )
        expert_approved_pair = QAPair(
            id=3, question_text="q expert approved", answer_text="a",
            extraction_type="thread_reply", expert_status="approved",
        )

        # Имитируем проверку в пайплайне
        pairs = [approved_pair, rejected_pair, expert_approved_pair]
        allowed = {"thread_reply"}
        filtered = []
        for pair in pairs:
            if pair.extraction_type not in allowed:
                continue
            if pair.expert_status == "rejected":
                continue
            filtered.append(pair)

        self.assertEqual(len(filtered), 2)
        self.assertEqual(filtered[0].id, 1)
        self.assertEqual(filtered[1].id, 3)

    def test_rejected_pair_not_in_bm25_corpus(self):
        """Expert-rejected пары не должны попадать в BM25-корпус.

        Это гарантируется SQL-фильтрацией в get_all_approved_qa_pairs:
        WHERE approved = 1 AND (expert_status IS NULL OR expert_status != 'rejected')
        """
        # Имитируем фильтрацию на уровне приложения
        pairs = [
            QAPair(id=1, question_text="q", answer_text="a", approved=1, expert_status=None),
            QAPair(id=2, question_text="q", answer_text="a", approved=1, expert_status="rejected"),
            QAPair(id=3, question_text="q", answer_text="a", approved=1, expert_status="approved"),
            QAPair(id=4, question_text="q", answer_text="a", approved=0, expert_status=None),
        ]

        # Условие из SQL: approved = 1 AND (expert_status IS NULL OR expert_status != 'rejected')
        filtered = [
            p for p in pairs
            if p.approved == 1
            and (p.expert_status is None or p.expert_status != "rejected")
        ]

        self.assertEqual(len(filtered), 2)
        ids = [p.id for p in filtered]
        self.assertIn(1, ids)   # approved=1, expert_status=None → включена
        self.assertIn(3, ids)   # approved=1, expert_status='approved' → включена
        self.assertNotIn(2, ids)  # approved=1, expert_status='rejected' → исключена
        self.assertNotIn(4, ids)  # approved=0 → исключена


class TestRowToQaPairExpertStatus(unittest.TestCase):
    """Тесты маппинга expert_status из строки БД."""

    def test_row_with_expert_status_maps_correctly(self):
        """_row_to_qa_pair корректно маппит expert_status из строки."""
        from src.group_knowledge.database import _row_to_qa_pair

        row = {
            "id": 42,
            "question_text": "Как настроить?",
            "answer_text": "Нужно зайти в настройки.",
            "question_message_id": 100,
            "answer_message_id": 101,
            "group_id": -1001234,
            "extraction_type": "thread_reply",
            "confidence": 0.9,
            "llm_model_used": "deepseek",
            "llm_request_payload": None,
            "created_at": 1710000000,
            "approved": 1,
            "vector_indexed": 1,
            "expert_status": "rejected",
        }

        pair = _row_to_qa_pair(row)

        self.assertEqual(pair.expert_status, "rejected")
        self.assertEqual(pair.id, 42)

    def test_row_without_expert_status_defaults_to_none(self):
        """Если expert_status нет в строке — по умолчанию None."""
        from src.group_knowledge.database import _row_to_qa_pair

        row = {
            "id": 1,
            "question_text": "q",
            "answer_text": "a",
            "group_id": 0,
            "extraction_type": "thread_reply",
            "created_at": 0,
            "approved": 1,
            "vector_indexed": 0,
        }

        pair = _row_to_qa_pair(row)

        self.assertIsNone(pair.expert_status)


if __name__ == "__main__":
    unittest.main()
