"""
test_rag_service.py — тесты сервиса RAG базы знаний.
"""

import builtins
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.sbs_helper_telegram_bot.ai_router.messages import (
    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED,
    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED,
)
from src.sbs_helper_telegram_bot.ai_router.rag_service import RagKnowledgeService


class TestRagKnowledgeService(unittest.IsolatedAsyncioTestCase):
    """Тесты RagKnowledgeService."""

    class _FakeMySqlError(Exception):
        """Тестовая ошибка MySQL с атрибутом errno."""

        def __init__(self, errno: int):
            super().__init__(f"MySQL error: {errno}")
            self.errno = errno

    def test_supported_file_extensions(self):
        """Проверка поддерживаемых расширений файлов."""
        service = RagKnowledgeService()
        self.assertTrue(service.is_supported_file("manual.pdf"))
        self.assertTrue(service.is_supported_file("rules.DOCX"))
        self.assertTrue(service.is_supported_file("notes.txt"))
        self.assertTrue(service.is_supported_file("kb.md"))
        self.assertTrue(service.is_supported_file("d200.html"))
        self.assertTrue(service.is_supported_file("index.HTM"))
        self.assertFalse(service.is_supported_file("archive.zip"))

    def test_extract_html_text(self):
        """HTML корректно очищается от тегов и служебных блоков."""
        html = b"<html><head><style>.x{}</style><script>1+1</script></head><body><h1>SLA</h1><p>4 hours</p></body></html>"
        text = RagKnowledgeService._extract_html_text(html)
        self.assertIn("SLA", text)
        self.assertIn("4 hours", text)
        self.assertNotIn("1+1", text)

    def test_split_text_fallback(self):
        """Fallback-splitter делит текст на несколько чанков."""
        long_text = "A" * 3500
        chunks = RagKnowledgeService._split_text(long_text)
        self.assertGreaterEqual(len(chunks), 3)

    def test_split_text_skips_langchain_import_on_python_314(self):
        """На Python 3.14+ не выполняется импорт langchain, используется fallback."""

        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name.startswith("langchain"):
                raise AssertionError("Импорт langchain не должен вызываться на Python 3.14+")
            return original_import(name, *args, **kwargs)

        with patch.object(RagKnowledgeService, "_is_langchain_splitter_supported", return_value=False):
            with patch("builtins.__import__", side_effect=guarded_import):
                chunks = RagKnowledgeService._split_text("B" * 3500)

        self.assertGreaterEqual(len(chunks), 3)

    def test_format_log_source_truncates_long_value(self):
        """Длинный source в логах сокращается с многоточием для читаемости."""
        source = "https://wiki.example.ru/" + ("very_long_section_" * 20) + "tail"

        compact = RagKnowledgeService._format_log_source(source, max_length=48)

        self.assertLessEqual(len(compact), 48)
        self.assertIn("…", compact)

    def test_build_prefilter_priority_snapshot_multiline(self):
        """Snapshot prefilter формируется в многострочном виде с разложением score."""
        docs = [
            (71, "doc_with_really_long_name_" * 6, "summary", 1.075),
            (65, "pax_s300.html", "summary", 1.044),
        ]
        vector_scores = {71: 0.625, 65: 0.574}

        snapshot = RagKnowledgeService._build_prefilter_priority_snapshot(
            docs,
            vector_scores,
            vector_weight=0.6,
        )

        self.assertIn("1. doc=71", snapshot)
        self.assertIn("2. doc=65", snapshot)
        self.assertIn("summary=1.075", snapshot)
        self.assertIn("lexical=0.700", snapshot)
        self.assertIn("vec=0.625", snapshot)
        self.assertIn("vec_w=0.375", snapshot)
        self.assertIn("\n", snapshot)

    def test_build_prefilter_priority_snapshot_uses_vector_weight(self):
        """В prefilter snapshot видно изменение weighted vec при смене vector-weight."""
        docs = [(66, "vx520.html", "summary", 5.614)]
        vector_scores = {66: 0.491}

        snapshot_low = RagKnowledgeService._build_prefilter_priority_snapshot(
            docs,
            vector_scores,
            vector_weight=1.0,
        )
        snapshot_high = RagKnowledgeService._build_prefilter_priority_snapshot(
            docs,
            vector_scores,
            vector_weight=10.0,
        )

        self.assertIn("vec=0.491", snapshot_low)
        self.assertIn("vec_w=0.491", snapshot_low)
        self.assertIn("vec_w=4.910", snapshot_high)

    def test_build_selected_priority_snapshot_multiline(self):
        """Snapshot selected формируется в многострочном виде с fused/summary score."""
        chunks = [
            (1.087, "https://wiki.example.ru/" + ("abc_" * 24), "chunk", 74, 12),
            (1.060, "iras_k900.html", "chunk", 63, 4),
        ]
        summary_scores = {74: 0.736, 63: 0.702}
        component_scores = {
            (74, "chunk"): (0.9, 0.95),
            (63, "chunk"): (0.8, 0.9),
        }

        snapshot = RagKnowledgeService._build_selected_priority_snapshot(
            chunks,
            summary_scores,
            component_scores=component_scores,
            lexical_weight=0.4,
            vector_weight=0.6,
        )

        self.assertIn("1. doc=74 chunk=12", snapshot)
        self.assertIn("2. doc=63 chunk=4", snapshot)
        self.assertIn("fused=1.087", snapshot)
        self.assertIn("summary=0.736", snapshot)
        self.assertIn("origin=global", snapshot)
        self.assertIn("lex_raw=0.450", snapshot)
        self.assertIn("lex_bonus=0.450", snapshot)
        self.assertIn("lex_total=0.900", snapshot)
        self.assertIn("hybrid=(0.900*0.400)+(0.950*0.600)=0.930", snapshot)
        self.assertIn("summary_bonus=", snapshot)
        self.assertIn("\n", snapshot)

    def test_build_relative_summary_scores_uses_min_max(self):
        """Нормализация summary-score в retrieval-пуле использует min-max диапазон 0..1."""
        normalized = RagKnowledgeService._build_relative_summary_scores({10: 10.0, 11: 6.0, 12: 8.0})

        self.assertAlmostEqual(normalized[10], 1.0)
        self.assertAlmostEqual(normalized[11], 0.0)
        self.assertAlmostEqual(normalized[12], 0.5)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_SCORE_CAP", 2.5)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_BONUS_WEIGHT", 0.45)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_POSTRANK_WEIGHT", 0.2)
    def test_summary_bonus_uses_normalized_summary_score(self):
        """Summary-бонусы используют нормализованный score документа в диапазоне 0..1."""
        lexical_bonus = RagKnowledgeService._summary_score_bonus(10.0)
        postrank_bonus = RagKnowledgeService._summary_postrank_bonus(10.0)

        self.assertAlmostEqual(lexical_bonus, 0.45)
        self.assertAlmostEqual(postrank_bonus, 0.2)

        lexical_bonus_partial = RagKnowledgeService._summary_score_bonus(1.25)
        postrank_bonus_partial = RagKnowledgeService._summary_postrank_bonus(1.25)

        self.assertAlmostEqual(lexical_bonus_partial, 0.225)
        self.assertAlmostEqual(postrank_bonus_partial, 0.1)

    def test_build_selected_priority_snapshot_marks_prefilter_and_fallback_origin(self):
        """Snapshot selected помечает происхождение документа: prefilter/fallback/global."""
        chunks = [
            (1.2, "doc-prefilter.txt", "chunk-a", 10),
            (1.1, "doc-fallback.txt", "chunk-b", 99),
            (1.0, "doc-global.txt", "chunk-c", 500),
        ]

        snapshot = RagKnowledgeService._build_selected_priority_snapshot(
            chunks,
            summary_scores={10: 2.0},
            prefilter_scope_doc_ids=[10, 99],
            base_prefilter_doc_ids=[10],
        )

        self.assertIn("doc=10", snapshot)
        self.assertIn("origin=prefilter", snapshot)
        self.assertIn("doc=99", snapshot)
        self.assertIn("origin=fallback", snapshot)
        self.assertIn("doc=500", snapshot)
        self.assertIn("origin=global", snapshot)

    def test_build_selected_top_docs_snapshot_returns_unique_doc_ids_in_rank_order(self):
        """Snapshot top docs для retrieval-лога содержит уникальные doc-id по порядку ранжирования."""
        chunks = [
            (3.5, "d200.html", "chunk-1", 7),
            (3.4, "d200.html", "chunk-2", 7),
            (3.3, "vx820.html", "chunk-1", 118),
            (3.2, "vx520.html", "chunk-1", 117),
            (3.1, "vx520.html", "chunk-2", 117),
            (3.0, "d230.html", "chunk-1", 113),
        ]

        snapshot = RagKnowledgeService._build_selected_top_docs_snapshot(chunks, max_docs=5)

        self.assertEqual(snapshot, "7,118,117,113")

    def test_build_selected_component_scores_uses_merge_dedup_key(self):
        """Компоненты lexical/vector собираются по dedup-ключу (document_id, chunk_text.strip)."""
        lexical = [
            (1.5, "doc-a.txt", "chunk A", 7),
            (1.2, "doc-a.txt", "chunk A", 7),
        ]
        vector = [
            (0.9, "doc-a.txt", "chunk A", 7),
            (0.7, "doc-a.txt", "chunk A", 7),
        ]

        components = RagKnowledgeService._build_selected_component_scores(lexical, vector)

        self.assertEqual(components[(7, "chunk A")], (1.5, 0.9))

    def test_get_chunking_diagnostics(self):
        """Диагностика chunking возвращает ожидаемые поля и стратегии."""
        service = RagKnowledgeService()

        with patch.object(service, "_is_langchain_splitter_supported", return_value=True):
            with patch.object(service, "_resolve_text_slicer_name", return_value="RecursiveCharacterTextSplitter(langchain.text_splitter)"):
                with patch(
                    "src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_html_splitter_enabled",
                    return_value=True,
                ):
                    diagnostics = service.get_chunking_diagnostics()

        self.assertEqual(diagnostics["chunk_size"], 1000)
        self.assertEqual(diagnostics["chunk_overlap"], 150)
        self.assertEqual(diagnostics["text_slicer"], "RecursiveCharacterTextSplitter(langchain.text_splitter)")
        self.assertEqual(diagnostics["html_strategy"], "html_semantic_preserving_splitter_with_fallback")
        self.assertEqual(diagnostics["plain_text_strategy"], "extract_text_then_split_text")
        self.assertTrue(diagnostics["html_splitter_enabled"])
        self.assertTrue(diagnostics["langchain_splitter_supported"])

    def test_split_html_payload_uses_semantic_splitter_when_available(self):
        """HTML-чанкинг использует результат semantic-splitter, если он вернул чанки."""
        service = RagKnowledgeService()
        html = b"<html><body><h1>SLA</h1><p>4 hours</p></body></html>"

        with patch.object(service, "_split_html_with_semantic_preserving_splitter", return_value=["SLA\n4 hours"]) as mock_splitter:
            with patch.object(service, "_extract_html_text") as mock_extract:
                chunks = service._split_html_payload(html)

        self.assertEqual(chunks, ["SLA\n4 hours"])
        mock_splitter.assert_called_once()
        mock_extract.assert_not_called()

    def test_split_html_payload_falls_back_when_semantic_splitter_empty(self):
        """При пустом результате semantic-splitter включается fallback по очищенному тексту."""
        service = RagKnowledgeService()
        html = b"<html><body><h1>SLA</h1><p>4 hours</p></body></html>"

        with patch.object(service, "_split_html_with_semantic_preserving_splitter", return_value=[]):
            with patch.object(service, "_extract_html_text", return_value="SLA 4 hours") as mock_extract:
                with patch.object(service, "_split_text", return_value=["SLA 4 hours"]) as mock_split_text:
                    chunks = service._split_html_payload(html)

        self.assertEqual(chunks, ["SLA 4 hours"])
        mock_extract.assert_called_once()
        mock_split_text.assert_called_once_with("SLA 4 hours")

    def test_split_html_payload_skips_semantic_splitter_when_disabled_in_settings(self):
        """При выключенном флаге HTML splitter используется только fallback path."""
        service = RagKnowledgeService()
        html = b"<html><body><h1>SLA</h1><p>4 hours</p></body></html>"

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_html_splitter_enabled", return_value=False):
            with patch.object(service, "_split_html_with_semantic_preserving_splitter") as mock_semantic_splitter:
                with patch.object(service, "_extract_html_text", return_value="SLA 4 hours") as mock_extract:
                    with patch.object(service, "_split_text", return_value=["SLA 4 hours"]) as mock_split_text:
                        chunks = service._split_html_payload(html)

        self.assertEqual(chunks, ["SLA 4 hours"])
        mock_semantic_splitter.assert_not_called()
        mock_extract.assert_called_once()
        mock_split_text.assert_called_once_with("SLA 4 hours")

    def test_split_html_with_semantic_splitter_flattens_headers_into_chunks(self):
        """Заголовки из metadata переносятся в начало текстового чанка."""
        service = RagKnowledgeService()

        class FakeDoc:
            def __init__(self, page_content, metadata):
                self.page_content = page_content
                self.metadata = metadata

        fake_docs = [
            FakeDoc("Подробные условия", {"h1": "SLA", "h2": "Критический"}),
        ]

        class FakeSplitter:
            def __init__(self, headers_to_split_on):
                self.headers_to_split_on = headers_to_split_on

            def split_text(self, html):
                return fake_docs

        with patch.object(service, "_get_html_splitter_class", return_value=FakeSplitter):
            with patch.object(service, "_split_text", return_value=["SLA\nКритический\nПодробные условия"]) as mock_split_text:
            chunks = service._split_html_with_semantic_preserving_splitter("<h1>SLA</h1><h2>Критический</h2><p>Подробные условия</p>")

        self.assertEqual(chunks, ["SLA\nКритический\nПодробные условия"])
        mock_split_text.assert_called_once_with("SLA\nКритический\nПодробные условия")

    def test_build_html_splitter_falls_back_to_header_only_signature(self):
        """Инициализация HTML splitter корректно откатывается на старую сигнатуру конструктора."""

        class HeaderOnlySplitter:
            def __init__(self, headers_to_split_on):
                self.headers_to_split_on = headers_to_split_on

        splitter = RagKnowledgeService._build_html_splitter(HeaderOnlySplitter)

        self.assertEqual(
            splitter.headers_to_split_on,
            [("h1", "h1"), ("h2", "h2"), ("h3", "h3"), ("h4", "h4"), ("h5", "h5"), ("h6", "h6")],
        )

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_search_relevant_chunks_scoring(self, mock_get_cursor, mock_get_db_connection):
        """Retrieval возвращает наиболее релевантный чанк."""
        service = RagKnowledgeService()

        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {
                "chunk_text": "SLA выезда 4 часа при критическом инциденте",
                "chunk_index": 8,
                "filename": "reglament.txt",
            },
            {
                "chunk_text": "Нерелевантный текст про отпуск",
                "chunk_index": 2,
                "filename": "other.txt",
            },
        ]

        result = service._search_relevant_chunks("Какой SLA выезда?", limit=1)
        self.assertEqual(len(result), 1)
        self.assertIn("SLA", result[0][2])
        self.assertEqual(result[0][4], 8)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_lexical_scorer", return_value="bm25")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_search_relevant_chunks_bm25_scoring(self, mock_get_cursor, mock_get_db_connection, mock_norm, mock_mode):
        """В режиме BM25 retrieval приоритизирует чанк с более сильным токенным совпадением."""
        service = RagKnowledgeService()

        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {
                "chunk_text": "SLA выезда 4 часа при критическом инциденте",
                "chunk_index": 8,
                "filename": "reglament.txt",
                "document_id": 11,
            },
            {
                "chunk_text": "Общие правила графика отпусков",
                "chunk_index": 2,
                "filename": "other.txt",
                "document_id": 12,
            },
            {
                "chunk_text": "Регламент отпусков и графика смен",
                "chunk_index": 3,
                "filename": "other2.txt",
                "document_id": 13,
            },
        ]

        result = service._search_relevant_chunks("Какой SLA выезда?", limit=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "reglament.txt")
        self.assertEqual(result[0][4], 8)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_uses_cache(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve,
        mock_version,
    ):
        """Повторный одинаковый вопрос берётся из кэша без повторного вызова LLM."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(1.2, "reglament.txt", "SLA по критическим заявкам составляет 4 часа.", 1)],
            ["[Summary | reglament.txt]\nSLA и порядок эскалации"],
        )

        provider = AsyncMock()
        provider.chat.return_value = "SLA 4 часа"
        mock_get_provider.return_value = provider

        q = "Какой SLA по критическим заявкам?"
        first = await service.answer_question(q, user_id=77)
        second = await service.answer_question(q, user_id=77)

        self.assertEqual(first, "SLA 4 часа")
        self.assertEqual(second, "SLA 4 часа")
        provider.chat.assert_awaited_once()

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_progress_callback_emits_stages_and_skips_on_cache_hit(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve,
        mock_version,
    ):
        """Прогресс RAG эмитится на cache-miss и не эмитится при cache-hit."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(1.2, "reglament.txt", "SLA по критическим заявкам составляет 4 часа.", 1)],
            ["[Summary | reglament.txt]\nSLA и порядок эскалации"],
        )

        provider = AsyncMock()
        provider.chat.return_value = "SLA 4 часа"
        mock_get_provider.return_value = provider

        progress = AsyncMock()
        q = "Какой SLA по критическим заявкам?"

        first = await service.answer_question(q, user_id=77, on_progress=progress)
        self.assertEqual(first, "SLA 4 часа")
        self.assertEqual(progress.await_count, 2)
        self.assertEqual(progress.await_args_list[0].args[0], AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED)
        self.assertEqual(progress.await_args_list[1].args[0], AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED)

        progress.reset_mock()
        second = await service.answer_question(q, user_id=77, on_progress=progress)
        self.assertEqual(second, "SLA 4 часа")
        progress.assert_not_awaited()
        provider.chat.assert_awaited_once()

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_directory_ingest_summary_model_override", return_value="deepseek-reasoner")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    def test_generate_document_summary_uses_directory_ingest_model_override(
        self,
        mock_get_provider,
        mock_get_override,
    ):
        """Для scope=directory_ingest summary вызывается с model_override из env-конфига."""
        service = RagKnowledgeService()
        provider = MagicMock()
        provider.chat = AsyncMock(return_value="Краткое summary")
        provider.get_model_name.return_value = "deepseek-chat"
        mock_get_provider.return_value = provider

        summary, model_name = service._generate_document_summary(
            filename="manual.txt",
            chunks=["Полезный текст документа"],
            user_id=17,
            summary_model_scope="directory_ingest",
        )

        self.assertEqual(summary, "Краткое summary")
        self.assertEqual(model_name, "deepseek-reasoner")
        provider.chat.assert_awaited_once()
        chat_kwargs = provider.chat.await_args.kwargs
        self.assertEqual(chat_kwargs.get("purpose"), "rag_summary")
        self.assertEqual(chat_kwargs.get("model_override"), "deepseek-reasoner")
        provider.get_model_name.assert_not_called()

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.warning")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL", "invalid-model")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_directory_ingest_summary_model_override", return_value=None)
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    def test_generate_document_summary_invalid_override_falls_back_to_default_model(
        self,
        mock_get_provider,
        mock_get_override,
        mock_logger_warning,
    ):
        """Невалидный env override для directory-ingest логируется и не ломает summary-вызов."""
        service = RagKnowledgeService()
        provider = MagicMock()
        provider.chat = AsyncMock(return_value="Краткое summary")
        provider.get_model_name.return_value = "deepseek-chat"
        mock_get_provider.return_value = provider

        summary, model_name = service._generate_document_summary(
            filename="manual.txt",
            chunks=["Полезный текст документа"],
            user_id=18,
            summary_model_scope="directory_ingest",
        )

        self.assertEqual(summary, "Краткое summary")
        self.assertEqual(model_name, "deepseek-chat")
        provider.chat.assert_awaited_once()
        chat_kwargs = provider.chat.await_args.kwargs
        self.assertIsNone(chat_kwargs.get("model_override"))
        provider.get_model_name.assert_called_once_with(purpose="rag_summary")
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("Некорректное значение AI_RAG_DIRECTORY_INGEST_SUMMARY_MODEL")
                for call in mock_logger_warning.call_args_list
            )
        )

    @patch.object(RagKnowledgeService, "_compute_summary_vector_scores", return_value={})
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_prefilter_documents_by_summary(self, mock_get_cursor, mock_get_db_connection, mock_vec_scores):
        """Prefilter по summary выбирает документы с максимальной lexical-релевантностью."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {"document_id": 1, "summary_text": "SLA выезда 4 часа и эскалация", "filename": "sla.txt"},
            {"document_id": 2, "summary_text": "Отпуск и график", "filename": "hr.txt"},
            {"document_id": 3, "summary_text": "График дежурств и отпусков", "filename": "ops.txt"},
        ]

        rows, vec_scores = service._prefilter_documents_by_summary(
            question="Какой SLA выезда",
            question_tokens=service._tokenize("Какой SLA выезда"),
            limit=2,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][1], "sla.txt")
        self.assertIsInstance(vec_scores, dict)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_MATCH_PHRASE_WEIGHT", 0.0)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT", 1.0)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_lexical_scorer", return_value="bm25")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    @patch.object(RagKnowledgeService, "_compute_summary_vector_scores", return_value={})
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_prefilter_documents_by_summary_bm25(
        self,
        mock_get_cursor,
        mock_get_db_connection,
        mock_vec_scores,
        mock_norm,
        mock_mode,
    ):
        """Summary-prefilter в режиме BM25 отдаёт приоритет документу с релевантным summary."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {"document_id": 1, "summary_text": "SLA выезда 4 часа и эскалация", "filename": "sla.txt"},
            {"document_id": 2, "summary_text": "Отпуск и график", "filename": "hr.txt"},
            {"document_id": 3, "summary_text": "График дежурств и отпусков", "filename": "ops.txt"},
        ]

        rows, _ = service._prefilter_documents_by_summary(
            question="Какой SLA выезда",
            question_tokens=service._tokenize("Какой SLA выезда"),
            limit=2,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_ru_normalization_mode", return_value="lemma_then_stem")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=True)
    def test_tokenize_applies_ru_normalization(self, mock_norm_enabled, mock_norm_mode):
        """Токенизация применяет RU-нормализацию, когда флаг включён."""
        service = RagKnowledgeService()

        with patch.object(service, "_lemmatize_ru_token", side_effect=lambda token: "магазин" if token == "магазины" else token):
            with patch.object(service, "_stem_ru_token", side_effect=lambda token: "магаз" if token == "магазин" else token):
                tokens = service._tokenize("Магазины X5 работают")

        self.assertIn("магаз", tokens)
        self.assertIn("работают", tokens)

    def test_score_corpus_bm25_scores_relevant_document_higher(self):
        """BM25-счётчик отдаёт больший score более релевантному документу."""
        corpus = [
            ["sla", "выезд", "критический", "инцидент"],
            ["отпуск", "график", "выходные"],
            ["регламент", "отпуск", "график", "дежурство"],
        ]
        query = ["sla", "выезд"]

        scores = RagKnowledgeService._score_corpus_bm25(corpus, query)

        self.assertEqual(len(scores), 3)
        self.assertGreater(scores[0], scores[1])

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_search_relevant_chunks_uses_summary_bonus(self, mock_get_cursor, mock_get_db_connection):
        """Ранжирование чанков усиливается бонусом summary-релевантности документа."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {"chunk_text": "SLA", "filename": "doc-low.txt", "document_id": 10},
            {"chunk_text": "SLA", "filename": "doc-high.txt", "document_id": 11},
        ]

        rows = service._search_relevant_chunks(
            "Какой SLA",
            limit=2,
            prefiltered_doc_ids=[10, 11],
            summary_scores={10: 0.1, 11: 1.2},
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "doc-high.txt")

    def test_score_summary_text_prefers_exact_phrase(self):
        """Фразовое совпадение в summary даёт заметный приоритет над чистым token-overlap."""
        service = RagKnowledgeService()
        question = "X5 shop group"
        tokens = service._tokenize(question)

        phrase_score = service._score_summary_text(
            summary_text="Регламент X5 shop group для SLA магазинов.",
            question_tokens=tokens,
            question=question,
        )
        token_only_score = service._score_summary_text(
            summary_text="Регламент shop operations group для SLA магазинов.",
            question_tokens=tokens,
            question=question,
        )

        self.assertGreater(phrase_score, token_only_score)

    def test_word_boundary_match_rejects_substring(self):
        """Word-boundary match \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0435\u0442 \u0441 \u043f\u043e\u0434\u0441\u0442\u0440\u043e\u043a\u043e\u0439: 'x5' \u043d\u0435 \u043d\u0430\u0445\u043e\u0434\u0438\u0442 'vx520'."""
        self.assertTrue(RagKnowledgeService._word_boundary_match("x5", "\u0440\u0435\u0433\u043b\u0430\u043c\u0435\u043d\u0442 x5 \u043c\u0430\u0433\u0430\u0437\u0438\u043d\u043e\u0432"))
        self.assertFalse(RagKnowledgeService._word_boundary_match("x5", "\u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b vx520 \u043e\u0431\u0441\u043b\u0443\u0436\u0438\u0432\u0430\u043d\u0438\u0435"))
        self.assertTrue(RagKnowledgeService._word_boundary_match("x5", "X5-\u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b"))
        self.assertFalse(RagKnowledgeService._word_boundary_match("", "\u0442\u0435\u043a\u0441\u0442"))
        self.assertFalse(RagKnowledgeService._word_boundary_match("x5", ""))

    def test_score_summary_text_x5_vs_vx520(self):
        """\u0424\u0440\u0430\u0437\u043e\u0432\u044b\u0439 \u043c\u0430\u0442\u0447 X5 \u043d\u0435 \u0441\u0440\u0430\u0431\u0430\u0442\u044b\u0432\u0430\u0435\u0442 \u043d\u0430 VX520 \u0431\u043b\u0430\u0433\u043e\u0434\u0430\u0440\u044f word-boundary."""
        service = RagKnowledgeService()
        question = "X5 shop"
        tokens = service._tokenize(question)

        score_x5 = service._score_summary_text(
            summary_text="\u0420\u0435\u0433\u043b\u0430\u043c\u0435\u043d\u0442 X5 shop \u0434\u043b\u044f SLA \u043c\u0430\u0433\u0430\u0437\u0438\u043d\u043e\u0432.",
            question_tokens=tokens,
            question=question,
        )
        score_vx520 = service._score_summary_text(
            summary_text="\u0420\u0435\u0433\u043b\u0430\u043c\u0435\u043d\u0442 VX520 shop \u0434\u043b\u044f \u0442\u0435\u0440\u043c\u0438\u043d\u0430\u043b\u043e\u0432.",
            question_tokens=tokens,
            question=question,
        )

        self.assertGreater(
            score_x5,
            score_vx520,
            "X5 summary \u0434\u043e\u043b\u0436\u043d\u043e \u0441\u043a\u043e\u0440\u0438\u0442\u044c\u0441\u044f \u0437\u043d\u0430\u0447\u0438\u0442\u0435\u043b\u044c\u043d\u043e \u0432\u044b\u0448\u0435 VX520 summary",
        )

    def test_cosine_dot_normalized_vectors(self):
        """\u0421\u043a\u0430\u043b\u044f\u0440\u043d\u043e\u0435 \u043f\u0440\u043e\u0438\u0437\u0432\u0435\u0434\u0435\u043d\u0438\u0435 L2-\u043d\u043e\u0440\u043c\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0445 \u0432\u0435\u043a\u0442\u043e\u0440\u043e\u0432 \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442 cosine similarity."""
        same = RagKnowledgeService._cosine_dot([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        self.assertAlmostEqual(same, 1.0, places=5)

        orthogonal = RagKnowledgeService._cosine_dot([1.0, 0.0], [0.0, 1.0])
        self.assertAlmostEqual(orthogonal, 0.0, places=5)

        partial = RagKnowledgeService._cosine_dot([0.6, 0.8], [0.8, 0.6])
        self.assertAlmostEqual(partial, 0.96, places=5)

    def test_compute_summary_vector_scores_graceful_when_no_provider(self):
        """_compute_summary_vector_scores \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442 {} \u043a\u043e\u0433\u0434\u0430 embedding-\u043f\u0440\u043e\u0432\u0430\u0439\u0434\u0435\u0440 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d."""
        service = RagKnowledgeService()

        with patch.object(service, "_get_embedding_provider", return_value=None):
            scores = service._compute_summary_vector_scores(
                question="X5 shop",
                summaries=[(1, "summary X5"), (2, "summary VX520")],
            )

        self.assertEqual(scores, {})

    def test_compute_summary_vector_scores_returns_similarities(self):
        """_compute_summary_vector_scores \u0432\u043e\u0437\u0432\u0440\u0430\u0449\u0430\u0435\u0442 \u043a\u043e\u0441\u0438\u043d\u0443\u0441\u043d\u043e\u0435 \u0441\u0445\u043e\u0434\u0441\u0442\u0432\u043e \u0434\u043b\u044f \u043a\u0430\u0436\u0434\u043e\u0433\u043e summary."""
        service = RagKnowledgeService()

        mock_provider = MagicMock()
        mock_provider.encode_texts.side_effect = [
            [[1.0, 0.0, 0.0]],
            [[0.9, 0.1, 0.0], [0.1, 0.9, 0.0]],
        ]

        with patch.object(service, "_get_embedding_provider", return_value=mock_provider):
            with patch.object(service, "_get_corpus_version", return_value=42):
                scores = service._compute_summary_vector_scores(
                    question="X5 shop",
                    summaries=[(10, "summary X5"), (20, "summary VX520")],
                )

        self.assertIn(10, scores)
        self.assertIn(20, scores)
        self.assertGreater(scores[10], scores[20])

    def test_compute_summary_vector_scores_uses_cache(self):
        """_compute_summary_vector_scores \u043a\u044d\u0448\u0438\u0440\u0443\u0435\u0442 \u044d\u043c\u0431\u0435\u0434\u0434\u0438\u043d\u0433\u0438 summary \u0438 \u043d\u0435 \u043f\u0435\u0440\u0435\u0437\u0430\u043f\u0440\u0430\u0448\u0438\u0432\u0430\u0435\u0442."""
        service = RagKnowledgeService()

        mock_provider = MagicMock()
        mock_provider.encode_texts.side_effect = [
            [[1.0, 0.0]],
            [[0.9, 0.1]],
            [[0.5, 0.5]],
        ]

        with patch.object(service, "_get_embedding_provider", return_value=mock_provider):
            with patch.object(service, "_get_corpus_version", return_value=1):
                service._compute_summary_vector_scores(
                    question="Q1",
                    summaries=[(10, "summary A")],
                )
                scores2 = service._compute_summary_vector_scores(
                    question="Q2",
                    summaries=[(10, "summary A")],
                )

        self.assertEqual(mock_provider.encode_texts.call_count, 3)
        self.assertIn(10, scores2)

    @patch.object(RagKnowledgeService, "_build_summary_blocks", return_value=[])
    @patch.object(RagKnowledgeService, "_determine_retrieval_mode", return_value="hybrid")
    @patch.object(RagKnowledgeService, "_merge_retrieval_candidates", return_value=[])
    @patch.object(RagKnowledgeService, "_search_relevant_chunks_vector", return_value=[])
    @patch.object(RagKnowledgeService, "_search_relevant_chunks", return_value=[])
    @patch.object(RagKnowledgeService, "_get_fallback_active_document_ids", return_value=[99, 100])
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_PREFILTER_FALLBACK_DOCS", 2)
    @patch.object(
        RagKnowledgeService,
        "_prefilter_documents_by_summary",
        return_value=([(5, "x5.txt", "summary with x5 shop group", 2.1)], {}),
    )
    def test_retrieve_context_uses_summary_prefilter_fallback_docs(
        self,
        mock_prefilter,
        mock_fallback,
        mock_search_lexical,
        mock_search_vector,
        mock_merge,
        mock_mode,
        mock_summary_blocks,
    ):
        """При summary-hit retrieval добавляет fallback-документы для сохранения recall."""
        service = RagKnowledgeService()

        service._retrieve_context_for_question("X5 shop group SLA", limit=5)

        mock_prefilter.assert_called_once()
        _, kwargs = mock_search_lexical.call_args
        self.assertEqual(kwargs["prefiltered_doc_ids"], [5, 99, 100])
        self.assertEqual(kwargs["summary_scores"], {5: 2.1})
        self.assertEqual(kwargs["normalized_summary_scores"], {5: 1.0})
        mock_fallback.assert_called_once_with(exclude_document_ids=[5], limit=2)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYBRID_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_POSTRANK_WEIGHT", 0.2)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_SCORE_CAP", 2.5)
    def test_merge_retrieval_candidates_applies_summary_postrank_bonus(self):
        """Post-merge bonus поднимает документы с высоким summary-score при равном vector score."""
        service = RagKnowledgeService()
        lexical = []
        vector = [
            (0.9, "doc-low.txt", "chunk-low", 1),
            (0.9, "doc-high.txt", "chunk-high", 2),
        ]

        rows = service._merge_retrieval_candidates(
            lexical_chunks=lexical,
            vector_chunks=vector,
            limit=2,
            summary_scores={2: 2.0},
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "doc-high.txt")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYBRID_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_LEXICAL_WEIGHT", 0.4)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_SEMANTIC_WEIGHT", 0.6)
    def test_merge_retrieval_candidates_hybrid(self):
        """Hybrid-слияние объединяет lexical и vector кандидаты с дедупликацией."""
        service = RagKnowledgeService()
        lexical = [
            (1.2, "doc-a.txt", "шаг 1 флешка", 1),
            (0.8, "doc-b.txt", "шаг 2", 2),
        ]
        vector = [
            (0.9, "doc-a.txt", "шаг 1 флешка", 1),
            (0.95, "doc-c.txt", "USB Flash update", 3),
        ]

        rows = service._merge_retrieval_candidates(lexical_chunks=lexical, vector_chunks=vector, limit=3)

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][1], "doc-a.txt")
        self.assertEqual(rows[1][1], "doc-c.txt")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYBRID_ENABLED", False)
    def test_merge_retrieval_candidates_vector_only(self):
        """При выключенном hybrid используются только vector-кандидаты."""
        service = RagKnowledgeService()
        lexical = [(1.5, "doc-a.txt", "lexical", 1)]
        vector = [(0.7, "doc-v.txt", "vector", 9)]

        rows = service._merge_retrieval_candidates(lexical_chunks=lexical, vector_chunks=vector, limit=2)

        self.assertEqual(rows, vector)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.info")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.time.perf_counter", side_effect=[10.0, 10.125])
    def test_upsert_vectors_for_chunks_logs_duration_ms(
        self,
        mock_perf_counter,
        mock_logger_info,
    ):
        """Лог upsert векторов содержит длительность операции в миллисекундах."""
        service = RagKnowledgeService()
        chunks = [{"document_id": 1, "chunk_index": 0, "chunk_text": "тест"}]

        embedding_provider = MagicMock()
        embedding_provider.encode_texts.return_value = [[0.1, 0.2]]
        vector_index = MagicMock()
        vector_index.upsert_chunks.return_value = 1

        with patch.object(service, "_get_embedding_provider", return_value=embedding_provider):
            with patch.object(service, "_get_vector_index", return_value=vector_index):
                with patch.object(service, "_record_chunk_embedding_metadata"):
                    result = service._upsert_vectors_for_chunks(chunks)

        self.assertEqual(result, 1)
        self.assertEqual(mock_perf_counter.call_count, 2)
        mock_logger_info.assert_called_once_with(
            "RAG vector upsert: chunks=%s duration_ms=%.2f",
            1,
            125.0,
        )

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.info")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_ENABLED", False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYBRID_ENABLED", False)
    @patch.object(RagKnowledgeService, "_merge_retrieval_candidates")
    @patch.object(RagKnowledgeService, "_search_relevant_chunks_vector")
    @patch.object(RagKnowledgeService, "_search_relevant_chunks")
    @patch.object(RagKnowledgeService, "_prefilter_documents_by_summary")
    def test_retrieve_context_logs_retrieval_mode_lexical_only(
        self,
        mock_prefilter,
        mock_search_lexical,
        mock_search_vector,
        mock_merge,
        mock_logger_info,
    ):
        """В логи пишется режим lexical_only для retrieval-цикла."""
        service = RagKnowledgeService()
        mock_prefilter.return_value = ([], {})
        mock_search_lexical.return_value = [(1.0, "kb.txt", "lexical block", 10)]
        mock_search_vector.return_value = []
        mock_merge.return_value = [(1.0, "kb.txt", "lexical block", 10)]

        chunks, summary_blocks = service._retrieve_context_for_question("Как прошить d200", limit=5)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(summary_blocks, [])
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("RAG retrieval:")
                and len(call.args) > 1
                and call.args[1] == "lexical_only"
                for call in mock_logger_info.call_args_list
            )
        )
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("RAG retrieval:")
                and "prefilter_scope_docs=%s" in call.args[0]
                and "lexical_scorer=%s" in call.args[0]
                for call in mock_logger_info.call_args_list
            )
        )
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("RAG retrieval:")
                and "selected_unique_docs=%s" in call.args[0]
                and "selected_top_docs=%s" in call.args[0]
                for call in mock_logger_info.call_args_list
            )
        )
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("RAG priority evidence:")
                for call in mock_logger_info.call_args_list
            )
        )

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.build_rag_prompt")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_passes_summary_blocks_to_prompt(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve,
        mock_version,
        mock_build_prompt,
    ):
        """answer_question передаёт summary-блоки в build_rag_prompt."""
        service = RagKnowledgeService(cache_ttl_seconds=300)
        mock_retrieve.return_value = (
            [(1.5, "reglament.txt", "SLA 4 часа", 11)],
            ["[Summary | reglament.txt]\nСводка по SLA"],
        )
        mock_build_prompt.return_value = "prompt"

        provider = AsyncMock()
        provider.chat.return_value = "Ответ"
        mock_get_provider.return_value = provider

        result = await service.answer_question("Какой SLA?", user_id=44)

        self.assertEqual(result, "Ответ")
        mock_build_prompt.assert_called_once()
        _, kwargs = mock_build_prompt.call_args
        self.assertEqual(kwargs.get("summary_blocks"), ["[Summary | reglament.txt]\nСводка по SLA"])

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_list_documents(self, mock_get_cursor, mock_get_db_connection):
        """Список документов возвращает агрегированные записи."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {
                "id": 10,
                "filename": "manual.pdf",
                "status": "active",
                "chunks_count": 42,
                "source_type": "telegram",
                "source_url": None,
                "uploaded_by": 100,
                "created_at": "2026-02-22 12:00:00",
                "updated_at": "2026-02-22 12:00:00",
            }
        ]

        items = service.list_documents(status="active", limit=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["filename"], "manual.pdf")

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_get_document(self, mock_get_cursor, mock_get_db_connection):
        """Детальная карточка документа возвращается по ID."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {
            "id": 11,
            "filename": "rules.docx",
            "status": "archived",
            "chunks_count": 10,
        }

        item = service.get_document(11)
        self.assertIsNotNone(item)
        self.assertEqual(item["status"], "archived")

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_set_document_status_not_found(self, mock_get_cursor, mock_get_db_connection):
        """Изменение статуса для отсутствующего документа возвращает False."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None

        changed = service.set_document_status(999, "archived", updated_by=1)
        self.assertFalse(changed)

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_set_document_status_changes_active_document(self, mock_get_cursor, mock_get_db_connection):
        """Изменение статуса active-документа инициирует SQL-обновление."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {
            "status": "active",
            "filename": "manual.pdf",
        }

        changed = service.set_document_status(5, "archived", updated_by=42)
        self.assertTrue(changed)
        self.assertGreaterEqual(cursor.execute.call_count, 3)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService.set_document_status")
    def test_delete_document_soft(self, mock_set_status):
        """Мягкое удаление делегируется в set_document_status."""
        service = RagKnowledgeService()
        mock_set_status.return_value = True
        ok = service.delete_document(3, updated_by=1, hard_delete=False)
        self.assertTrue(ok)
        mock_set_status.assert_called_once_with(3, "deleted", 1)

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._bump_corpus_version")
    def test_ingest_reactivates_existing_non_active_hash(
        self,
        mock_bump,
        mock_get_cursor,
        mock_get_db_connection,
    ):
        """При совпадении content_hash неактивный документ реактивируется без новой вставки."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {
            "id": 77,
            "status": "archived",
        }

        result = service.ingest_document_from_bytes(
            filename="rules.txt",
            payload=b"test content",
            uploaded_by=100,
            source_type="filesystem",
            source_url="/kb/rules.txt",
        )

        self.assertEqual(result["document_id"], 77)
        self.assertEqual(result["is_duplicate"], 1)
        self.assertEqual(result["reactivated"], 1)
        self.assertGreaterEqual(cursor.execute.call_count, 2)
        mock_bump.assert_called_once()

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._bump_corpus_version")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._split_text")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._extract_text")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._generate_document_summary")
    def test_ingest_persists_document_summary(
        self,
        mock_generate_summary,
        mock_extract_text,
        mock_split_text,
        mock_bump,
        mock_get_cursor,
        mock_get_db_connection,
    ):
        """При ingest создаётся запись в rag_document_summaries."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        cursor.lastrowid = 321
        mock_extract_text.return_value = "Полезный текст документа"
        mock_split_text.return_value = ["Первый чанк", "Второй чанк"]
        mock_generate_summary.return_value = ("Краткое summary документа", "deepseek-chat")

        result = service.ingest_document_from_bytes(
            filename="manual.txt",
            payload=b"payload",
            uploaded_by=7,
            source_type="filesystem",
            source_url="/kb/manual.txt",
        )

        self.assertEqual(result["document_id"], 321)
        self.assertEqual(result["is_duplicate"], 0)

        sql_calls = [args[0] for args, _ in cursor.execute.call_args_list if args]
        self.assertTrue(any("INSERT INTO rag_document_summaries" in call for call in sql_calls))
        mock_generate_summary.assert_called_once()
        mock_bump.assert_called_once()

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.time.sleep")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.warning")
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._split_text")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._extract_text")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._generate_document_summary")
    @patch.object(RagKnowledgeService, "_upsert_vectors_for_chunks")
    def test_ingest_retries_on_lock_wait_timeout(
        self,
        mock_upsert_vectors,
        mock_generate_summary,
        mock_extract_text,
        mock_split_text,
        mock_get_cursor,
        mock_get_db_connection,
        mock_logger_warning,
        mock_sleep,
    ):
        """Ingest повторяет транзакцию при lock timeout и завершает загрузку."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        cursor.lastrowid = 555
        mock_extract_text.return_value = "Полезный текст документа"
        mock_split_text.return_value = ["Первый чанк"]
        mock_generate_summary.return_value = ("Краткое summary документа", "deepseek-chat")

        state = {"insert_failed_once": False}

        def execute_side_effect(query, *args, **kwargs):
            if "INSERT INTO rag_documents" in query and not state["insert_failed_once"]:
                state["insert_failed_once"] = True
                raise self._FakeMySqlError(1205)
            return None

        cursor.execute.side_effect = execute_side_effect

        result = service.ingest_document_from_bytes(
            filename="manual.txt",
            payload=b"payload",
            uploaded_by=7,
            source_type="filesystem",
            source_url="/kb/manual.txt",
        )

        self.assertEqual(result["document_id"], 555)
        self.assertEqual(result["is_duplicate"], 0)
        self.assertEqual(result["chunks_count"], 1)
        self.assertTrue(state["insert_failed_once"])
        self.assertEqual(
            sum(1 for call in cursor.execute.call_args_list if "INSERT INTO rag_documents" in call.args[0]),
            2,
        )
        mock_sleep.assert_called_once()
        mock_upsert_vectors.assert_called_once()
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("Повтор DB-операции после временной ошибки MySQL")
                for call in mock_logger_warning.call_args_list
            )
        )

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_list_documents_by_source(self, mock_get_cursor, mock_get_db_connection):
        """Документы корректно фильтруются по source_type и source_url префиксу."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {
                "id": 1,
                "source_type": "filesystem",
                "source_url": "/kb/doc1.txt",
                "status": "active",
                "content_hash": "abc",
            }
        ]

        rows = service.list_documents_by_source(
            source_type="filesystem",
            source_url_prefix="/kb/",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_type"], "filesystem")
        cursor.execute.assert_called_once()

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_ENABLED", True)
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_backfill_vector_index_dry_run(self, mock_get_cursor, mock_get_db_connection):
        """Dry-run backfill считает чанки без записи в векторный индекс."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {
                "id": 10,
                "filename": "manual.txt",
                "source_type": "filesystem",
                "chunk_index": 0,
                "chunk_text": "Шаг 1",
            },
            {
                "id": 10,
                "filename": "manual.txt",
                "source_type": "filesystem",
                "chunk_index": 1,
                "chunk_text": "Шаг 2",
            },
        ]

        stats = service.backfill_vector_index(batch_size=10, dry_run=True)

        self.assertEqual(stats["documents_total"], 1)
        self.assertEqual(stats["documents_processed"], 1)
        self.assertEqual(stats["chunks_indexed"], 2)
        self.assertEqual(stats["errors"], 0)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.time.sleep")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.warning")
    @patch("src.common.database.get_cursor")
    @patch("src.common.database.get_db_connection")
    def test_record_chunk_embedding_metadata_retries_on_lock_wait(
        self,
        mock_get_db_connection,
        mock_get_cursor,
        mock_logger_warning,
        mock_sleep,
    ):
        """При lock timeout запись метаданных повторяется и завершается успешно."""
        service = RagKnowledgeService()
        mock_get_db_connection.return_value.__enter__.return_value = object()
        cursor = MagicMock()
        cursor.executemany.side_effect = [self._FakeMySqlError(1205), None]
        mock_get_cursor.return_value.__enter__.return_value = cursor

        service._record_chunk_embedding_metadata(
            chunks=[{"document_id": 1, "chunk_index": 0, "chunk_text": "text"}],
            embeddings=[[0.1, 0.2]],
            status="ready",
            error_message=None,
        )

        self.assertEqual(cursor.executemany.call_count, 2)
        mock_sleep.assert_called_once()
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("Повтор сохранения rag_chunk_embeddings")
                for call in mock_logger_warning.call_args_list
            )
        )

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.time.sleep")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.warning")
    @patch("src.common.database.get_cursor")
    @patch("src.common.database.get_db_connection")
    def test_record_chunk_embedding_metadata_does_not_retry_non_retryable_error(
        self,
        mock_get_db_connection,
        mock_get_cursor,
        mock_logger_warning,
        mock_sleep,
    ):
        """Неретраибельная ошибка БД логируется без повторов."""
        service = RagKnowledgeService()
        mock_get_db_connection.return_value.__enter__.return_value = object()
        cursor = MagicMock()
        cursor.executemany.side_effect = self._FakeMySqlError(1064)
        mock_get_cursor.return_value.__enter__.return_value = cursor

        service._record_chunk_embedding_metadata(
            chunks=[{"document_id": 2, "chunk_index": 1, "chunk_text": "text"}],
            embeddings=[[0.3, 0.4]],
            status="ready",
            error_message=None,
        )

        self.assertEqual(cursor.executemany.call_count, 1)
        mock_sleep.assert_not_called()
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("Не удалось сохранить rag_chunk_embeddings")
                for call in mock_logger_warning.call_args_list
            )
        )


    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.time.sleep")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.warning")
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    @patch.object(RagKnowledgeService, "_delete_vector_document")
    def test_delete_document_retries_on_lock_wait(
        self,
        mock_delete_vector,
        mock_get_cursor,
        mock_get_db_connection,
        mock_logger_warning,
        mock_sleep,
    ):
        """Hard-delete повторяет транзакцию при lock timeout; Qdrant вызывается после коммита MySQL."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"status": "active", "filename": "doc.txt"}

        state = {"delete_failed_once": False}

        def execute_side_effect(query, *args, **kwargs):
            if "DELETE FROM rag_documents" in query and not state["delete_failed_once"]:
                state["delete_failed_once"] = True
                raise self._FakeMySqlError(1205)
            return None

        cursor.execute.side_effect = execute_side_effect

        result = service.delete_document(document_id=42, updated_by=7, hard_delete=True)

        self.assertTrue(result)
        self.assertTrue(state["delete_failed_once"])
        mock_delete_vector.assert_called_once_with(42)
        mock_sleep.assert_called_once()
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("Повтор DB-операции после временной ошибки MySQL")
                for call in mock_logger_warning.call_args_list
            )
        )

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.time.sleep")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.warning")
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    @patch.object(RagKnowledgeService, "_set_vector_document_status")
    def test_set_document_status_retries_on_lock_wait(
        self,
        mock_set_vector_status,
        mock_get_cursor,
        mock_get_db_connection,
        mock_logger_warning,
        mock_sleep,
    ):
        """set_document_status повторяет транзакцию при lock timeout; Qdrant — после коммита MySQL."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"status": "active", "filename": "doc.txt"}

        state = {"update_failed_once": False}

        def execute_side_effect(query, *args, **kwargs):
            if "UPDATE rag_documents" in query and not state["update_failed_once"]:
                state["update_failed_once"] = True
                raise self._FakeMySqlError(1205)
            return None

        cursor.execute.side_effect = execute_side_effect

        result = service.set_document_status(document_id=42, new_status="archived", updated_by=7)

        self.assertTrue(result)
        self.assertTrue(state["update_failed_once"])
        mock_set_vector_status.assert_called_once_with(42, "archived")
        mock_sleep.assert_called_once()
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("Повтор DB-операции после временной ошибки MySQL")
                for call in mock_logger_warning.call_args_list
            )
        )

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    @patch.object(RagKnowledgeService, "_set_vector_document_status")
    def test_ingest_reactivation_calls_qdrant_after_commit(
        self,
        mock_set_vector_status,
        mock_get_cursor,
        mock_get_db_connection,
    ):
        """При реактивации документа Qdrant обновляется после коммита MySQL транзакции."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = {"id": 99, "status": "deleted"}

        result = service.ingest_document_from_bytes(
            filename="manual.txt",
            payload=b"payload",
            uploaded_by=7,
        )

        self.assertEqual(result["document_id"], 99)
        self.assertEqual(result["is_duplicate"], 1)
        self.assertEqual(result["reactivated"], 1)
        mock_set_vector_status.assert_called_once_with(99, "active")


if __name__ == "__main__":
    unittest.main()
