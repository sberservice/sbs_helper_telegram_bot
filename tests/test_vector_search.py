"""test_vector_search.py — тесты локального векторного поиска RAG."""

import types
import unittest
from unittest import mock

from src.sbs_helper_telegram_bot.ai_router.vector_search import LocalEmbeddingProvider, LocalVectorIndex


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


class TestLocalEmbeddingProvider(unittest.TestCase):
    """Проверки выбора устройства и инициализации embedding-модели."""

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_DEVICE", "auto")
    def test_resolve_device_auto_uses_cuda_when_available(self):
        """В режиме auto выбирается CUDA при доступном GPU."""
        captured = {}

        class _FakeSentenceTransformer:
            def __init__(self, model_name, device=None):
                captured["model_name"] = model_name
                captured["device"] = device

        fake_torch = types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda: True)
        )
        fake_st = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)

        provider = LocalEmbeddingProvider()
        with mock.patch.dict("sys.modules", {"torch": fake_torch, "sentence_transformers": fake_st}):
            is_ready = provider.is_ready()

        self.assertTrue(is_ready)
        self.assertEqual(captured["device"], "cuda")

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_DEVICE", "cuda")
    def test_resolve_device_forced_cuda_falls_back_to_cpu(self):
        """При принудительном CUDA без доступного GPU включается CPU fallback."""
        captured = {}

        class _FakeSentenceTransformer:
            def __init__(self, model_name, device=None):
                captured["model_name"] = model_name
                captured["device"] = device

        fake_torch = types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=lambda: False)
        )
        fake_st = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)

        provider = LocalEmbeddingProvider()
        with mock.patch.dict("sys.modules", {"torch": fake_torch, "sentence_transformers": fake_st}):
            is_ready = provider.is_ready()

        self.assertTrue(is_ready)
        self.assertEqual(captured["device"], "cpu")

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_DEVICE", "cuda")
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.LocalEmbeddingProvider._resolve_device", return_value="cuda")
    def test_ensure_model_loaded_passes_device_to_sentence_transformer(self, _mock_resolve_device):
        """Инициализация embedding-модели передаёт выбранный device в SentenceTransformer."""
        captured = {}

        class _FakeSentenceTransformer:
            def __init__(self, model_name, device=None):
                captured["model_name"] = model_name
                captured["device"] = device

        fake_module = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)

        provider = LocalEmbeddingProvider()

        with mock.patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            is_ready = provider.is_ready()

        self.assertTrue(is_ready)
        self.assertEqual(captured["model_name"], "BAAI/bge-m3")
        self.assertEqual(captured["device"], "cuda")


if __name__ == "__main__":
    unittest.main()
