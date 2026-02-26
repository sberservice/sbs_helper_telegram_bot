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

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "https://qdrant.remote")
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_API_KEY", "secret")
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_LOCAL_MODE", True)
    def test_logs_effective_remote_configuration_on_init(self):
        """При инициализации индекса пишется диагностический лог эффективной remote-конфигурации."""
        with mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.logger.info") as mock_info:
            _ = LocalVectorIndex()

        self.assertTrue(
            any(
                "Эффективная конфигурация remote Qdrant" in str(call.args[0])
                for call in mock_info.call_args_list
            )
        )

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "")
    def test_get_client_stops_retries_after_qdrant_storage_lock(self):
        """После lock-ошибки локального хранилища повторные инициализации клиента не выполняются."""
        qdrant_error = RuntimeError(
            "Storage folder /tmp/qdrant is already accessed by another instance of Qdrant client"
        )
        fake_constructor = mock.Mock(side_effect=qdrant_error)
        fake_qdrant_module = types.SimpleNamespace(QdrantClient=fake_constructor)

        with mock.patch.dict("sys.modules", {"qdrant_client": fake_qdrant_module}):
            index = LocalVectorIndex()
            first_client = index._get_client()
            second_client = index._get_client()

        self.assertIsNone(first_client)
        self.assertIsNone(second_client)
        self.assertEqual(fake_constructor.call_count, 1)

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "https://qdrant.remote")
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD", 3)
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_LOCAL_MODE", True)
    def test_get_client_prefers_remote_when_available(self):
        """При доступном remote backend выбирается удалённый Qdrant-клиент."""

        class _RemoteClient:
            def get_collections(self):
                return {"collections": []}

        class _LocalClient:
            pass

        counters = {"remote": 0, "local": 0}

        def _constructor(**kwargs):
            if kwargs.get("url"):
                counters["remote"] += 1
                return _RemoteClient()
            counters["local"] += 1
            return _LocalClient()

        fake_qdrant_module = types.SimpleNamespace(QdrantClient=_constructor)
        with mock.patch.dict("sys.modules", {"qdrant_client": fake_qdrant_module}):
            index = LocalVectorIndex()
            client = index._get_client()

        self.assertIsNotNone(client)
        self.assertEqual(counters["remote"], 1)
        self.assertEqual(counters["local"], 0)

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "https://qdrant.remote")
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD", 2)
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS", 300)
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_LOCAL_MODE", True)
    def test_get_client_fallbacks_to_local_after_remote_failures_threshold(self):
        """После N ошибок remote backend временно отключается, клиент переключается на local."""

        class _RemoteClient:
            def get_collections(self):
                raise RuntimeError("remote unavailable")

        class _LocalClient:
            pass

        counters = {"remote": 0, "local": 0}

        def _constructor(**kwargs):
            if kwargs.get("url"):
                counters["remote"] += 1
                return _RemoteClient()
            counters["local"] += 1
            return _LocalClient()

        fake_qdrant_module = types.SimpleNamespace(QdrantClient=_constructor)
        with mock.patch.dict("sys.modules", {"qdrant_client": fake_qdrant_module}):
            index = LocalVectorIndex()
            first_client = index._get_client()
            second_client = index._get_client()
            third_client = index._get_client()

        self.assertIsNotNone(first_client)
        self.assertIsNotNone(second_client)
        self.assertIsNotNone(third_client)
        self.assertEqual(counters["remote"], 2)
        self.assertEqual(counters["local"], 1)

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "https://qdrant.remote")
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD", 1)
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS", 300)
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_LOCAL_MODE", True)
    def test_search_uses_local_when_remote_not_responding(self):
        """Поиск переключается на local backend, если remote не отвечает."""

        class _RemoteClient:
            def get_collections(self):
                return {"collections": []}

            def search(self, **_kwargs):
                raise RuntimeError("remote search failed")

        class _Point:
            def __init__(self):
                self.payload = {
                    "document_id": 101,
                    "chunk_index": 0,
                    "filename": "local_doc.md",
                    "chunk_text": "Локальный fallback результат",
                }
                self.score = 0.91

        class _LocalClient:
            def search(self, **_kwargs):
                return [_Point()]

        counters = {"remote": 0, "local": 0}

        def _constructor(**kwargs):
            if kwargs.get("url"):
                counters["remote"] += 1
                return _RemoteClient()
            counters["local"] += 1
            return _LocalClient()

        fake_qdrant_module = types.SimpleNamespace(QdrantClient=_constructor)
        with mock.patch.dict("sys.modules", {"qdrant_client": fake_qdrant_module}):
            index = LocalVectorIndex()
            result = index.search(query_vector=[0.1, 0.2], limit=5)

        self.assertEqual(counters["remote"], 1)
        self.assertEqual(counters["local"], 1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].source, "local_doc.md")

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "https://qdrant.remote")
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_LOCAL_MODE", True)
    def test_logs_remote_state_up_on_successful_connect(self):
        """При успешном подключении к remote backend пишется лог перехода в состояние UP."""

        class _RemoteClient:
            def get_collections(self):
                return {"collections": []}

        fake_qdrant_module = types.SimpleNamespace(QdrantClient=lambda **_kwargs: _RemoteClient())

        with mock.patch.dict("sys.modules", {"qdrant_client": fake_qdrant_module}):
            index = LocalVectorIndex()
            with mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.logger.info") as mock_info:
                _ = index._get_client()

        self.assertTrue(
            any("Состояние remote Qdrant: UP" in str(call.args[0]) for call in mock_info.call_args_list)
        )

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_URL", "https://qdrant.remote")
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_FAILURE_THRESHOLD", 1)
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_REMOTE_COOLDOWN_SECONDS", 60)
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_LOCAL_MODE", True)
    def test_logs_remote_state_cooldown_after_threshold(self):
        """После достижения порога ошибок remote backend пишет лог перехода в COOLDOWN."""

        class _RemoteClient:
            def get_collections(self):
                raise RuntimeError("remote unavailable")

        class _LocalClient:
            pass

        def _constructor(**kwargs):
            if kwargs.get("url"):
                return _RemoteClient()
            return _LocalClient()

        fake_qdrant_module = types.SimpleNamespace(QdrantClient=_constructor)

        with mock.patch.dict("sys.modules", {"qdrant_client": fake_qdrant_module}):
            index = LocalVectorIndex()
            with mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.logger.warning") as mock_warning:
                _ = index._get_client()

        self.assertTrue(
            any("Состояние remote Qdrant: COOLDOWN" in str(call.args[0]) for call in mock_warning.call_args_list)
        )


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

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_EMBEDDING_FP16", True)
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.LocalEmbeddingProvider._resolve_device", return_value="cuda")
    def test_fp16_enabled_calls_model_half_on_cuda(self, _mock_resolve_device):
        """При включённом FP16 на CUDA вызывается half() у embedding-модели."""
        captured = {"half_calls": 0}

        class _FakeSentenceTransformer:
            def __init__(self, model_name, device=None):
                captured["model_name"] = model_name
                captured["device"] = device

            def half(self):
                captured["half_calls"] += 1
                return self

        fake_module = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)
        provider = LocalEmbeddingProvider()

        with mock.patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            is_ready = provider.is_ready()

        self.assertTrue(is_ready)
        self.assertEqual(captured["device"], "cuda")
        self.assertEqual(captured["half_calls"], 1)

    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.ai_settings.AI_RAG_VECTOR_EMBEDDING_FP16", True)
    @mock.patch("src.sbs_helper_telegram_bot.ai_router.vector_search.LocalEmbeddingProvider._resolve_device", return_value="cpu")
    def test_fp16_enabled_ignored_on_cpu(self, _mock_resolve_device):
        """При включённом FP16 и CPU устройство half() не вызывается."""
        captured = {"half_calls": 0}

        class _FakeSentenceTransformer:
            def __init__(self, model_name, device=None):
                captured["model_name"] = model_name
                captured["device"] = device

            def half(self):
                captured["half_calls"] += 1
                return self

        fake_module = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)
        provider = LocalEmbeddingProvider()

        with mock.patch.dict("sys.modules", {"sentence_transformers": fake_module}):
            is_ready = provider.is_ready()

        self.assertTrue(is_ready)
        self.assertEqual(captured["device"], "cpu")
        self.assertEqual(captured["half_calls"], 0)


if __name__ == "__main__":
    unittest.main()
