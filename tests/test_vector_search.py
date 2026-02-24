"""test_vector_search.py — тесты локального векторного поиска RAG."""

import unittest

from src.sbs_helper_telegram_bot.ai_router.vector_search import LocalVectorIndex


class TestLocalVectorIndex(unittest.TestCase):
    """Проверки формирования фильтров для Qdrant."""

    def test_build_search_filter_with_allowed_document_ids(self):
        """Фильтр для списка document_id строится без ValidationError и использует MatchAny."""
        try:
            from qdrant_client import models
        except Exception as exc:
            self.skipTest(f"qdrant_client недоступен: {exc}")

        index = LocalVectorIndex()
        query_filter = index._build_search_filter([11, 12, 0, -1])

        self.assertIsNotNone(query_filter)
        self.assertIsInstance(query_filter, models.Filter)

        dumped = query_filter.model_dump(mode="python")
        must_conditions = dumped.get("must") or []
        self.assertEqual(len(must_conditions), 2)

        document_filter = must_conditions[1]
        match_payload = document_filter.get("match") or {}
        self.assertEqual(match_payload.get("any"), [11, 12])


if __name__ == "__main__":
    unittest.main()
