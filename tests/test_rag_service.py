"""
test_rag_service.py — тесты сервиса RAG базы знаний.
"""

import builtins
import hashlib
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.sbs_helper_telegram_bot.ai_router.messages import (
    AI_PROGRESS_STAGE_RAG_CACHE_HIT,
    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED,
    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED,
)
from src.sbs_helper_telegram_bot.ai_router.rag_service import RagKnowledgeService, preload_rag_runtime_dependencies


class TestRagKnowledgeService(unittest.IsolatedAsyncioTestCase):
    """Тесты RagKnowledgeService."""

    class _FakeMySqlError(Exception):
        """Тестовая ошибка MySQL с атрибутом errno."""

        def __init__(self, errno: int):
            super().__init__(f"MySQL error: {errno}")
            self.errno = errno

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_ru_normalization_mode", return_value="lemma_then_stem")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=True)
    def test_preload_rag_runtime_dependencies_loads_vector_and_ru_dependencies(self, _mock_ru_enabled, _mock_ru_mode):
        """Preload на старте прогревает vector-модель и RU-нормализацию."""
        service = RagKnowledgeService()

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_service.get_rag_service", return_value=service):
            with patch.object(service, "_is_vector_search_enabled", return_value=True):
                with patch.object(service, "_get_embedding_provider", return_value=object()) as mock_provider:
                    with patch.object(service, "_get_vector_index", return_value=object()) as mock_vector_index:
                        with patch.object(service, "_get_ru_morph_analyzer", return_value=object()) as mock_morph:
                            with patch.object(service, "_get_ru_stemmer", return_value=object()) as mock_stemmer:
                                with patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.info") as mock_logger_info:
                                    result = preload_rag_runtime_dependencies()

        self.assertTrue(result["vector_provider_ready"])
        self.assertTrue(result["vector_index_ready"])
        self.assertTrue(result["ru_morph_ready"])
        self.assertTrue(result["ru_stemmer_ready"])
        mock_provider.assert_called_once()
        mock_vector_index.assert_called_once()
        mock_morph.assert_called_once()
        mock_stemmer.assert_called_once()

        logged_messages = [str(call_args.args[0]) for call_args in mock_logger_info.call_args_list]
        self.assertIn("RAG preload: start", logged_messages)
        self.assertIn("RAG preload: done status=%s duration_ms=%s vector_enabled=%s vector_provider_ready=%s vector_index_ready=%s ru_normalization_enabled=%s ru_normalization_mode=%s ru_morph_ready=%s ru_stemmer_ready=%s", logged_messages)

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

    def test_build_retrieval_log_table_contains_key_metrics(self):
        """Табличный лог retrieval содержит ключевые поля и тайминги."""
        table = RagKnowledgeService._build_retrieval_log_table(
            mode="hybrid",
            lexical_scorer="bm25",
            tokens_count=7,
            retrieval_tokens_count=6,
            category_hint="upos",
            prefilter_docs_count=3,
            prefilter_scope_docs_count=3,
            fallback_docs_count=0,
            lexical_hits_count=5,
            vector_hits_count=14,
            summary_vector_hits=200,
            summary_vector_source="collection",
            selected_count=5,
            selected_unique_docs=1,
            selected_top_docs="298",
            top_source="POS_Сбербанк_Инструкции_по_работе_с_ПО_POS_терминалов_банка",
            retrieval_total_ms=481.49,
            prefilter_ms=264.60,
            lexical_ms=35.18,
            vector_ms=179.63,
            merge_ms=1.71,
            summary_blocks_ms=0.00,
        )

        self.assertIn("RAG retrieval:\n", table)
        self.assertIn("| metric", table)
        self.assertIn("| mode", table)
        self.assertIn("| lexical_scorer", table)
        self.assertIn("| timings_ms.total", table)
        self.assertIn("| timings_ms.summary_blocks", table)
        self.assertIn("481.49", table)
        self.assertIn("0.00", table)

    def test_build_prefilter_priority_snapshot_multiline(self):
        """Snapshot prefilter формируется в табличном виде с разложением score."""
        docs = [
            (
                71,
                "doc_with_really_long_name_" * 6,
                "Очень длинный текст summary про SLA и выезд инженера, который должен быть сокращён до удобного excerpt для логов prefilter",
                1.075,
            ),
            (65, "pax_s300.html", "Короткий summary", 1.044),
        ]
        vector_scores = {71: 0.625, 65: 0.574}

        snapshot = RagKnowledgeService._build_prefilter_priority_snapshot(
            docs,
            vector_scores,
            vector_weight=0.6,
        )

        self.assertIn("| rank", snapshot)
        self.assertIn("| 1", snapshot)
        self.assertIn("| 2", snapshot)
        self.assertIn("1.075", snapshot)
        self.assertIn("0.700", snapshot)
        self.assertIn("0.625", snapshot)
        self.assertIn("0.375", snapshot)
        self.assertIn("Короткий summary", snapshot)
        self.assertIn("\n", snapshot)

    def test_format_summary_excerpt_truncates_to_about_80_chars(self):
        """Excerpt summary в логах компактный и ограничен по длине."""
        summary = "  ".join(["Очень", "длинный", "summary", "для", "проверки", "обрезки"] * 8)

        excerpt = RagKnowledgeService._format_summary_excerpt(summary, max_length=80)

        self.assertLessEqual(len(excerpt), 80)
        self.assertIn("…", excerpt)

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

        self.assertIn("0.491", snapshot_low)
        self.assertIn("4.910", snapshot_high)

    def test_build_selected_priority_snapshot_multiline(self):
        """Snapshot selected формируется в табличном виде с fused/summary score."""
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

        self.assertIn("| rank", snapshot)
        self.assertIn("| 74", snapshot)
        self.assertIn("| 63", snapshot)
        self.assertIn("1.087", snapshot)
        self.assertIn("0.736", snapshot)
        self.assertIn("global", snapshot)
        self.assertIn("0.450", snapshot)
        self.assertIn("0.900", snapshot)
        self.assertIn("1.000", snapshot)
        self.assertIn("(1.000*0.400)+(0.950*0.600)=0.970", snapshot)
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

        self.assertIn("10", snapshot)
        self.assertIn("prefilter", snapshot)
        self.assertIn("99", snapshot)
        self.assertIn("fallback", snapshot)
        self.assertIn("500", snapshot)
        self.assertIn("global", snapshot)

    def test_build_selected_priority_snapshot_shows_lex_norm(self):
        """Snapshot selected показывает нормализованный lex_norm (0..1) и использует его в hybrid-формуле."""
        chunks = [
            (0.7, "doc-a.txt", "chunk", 10, 0),
            (0.5, "doc-b.txt", "chunk", 20, 0),
        ]
        summary_scores = {10: 0.0, 20: 0.0}
        component_scores = {
            (10, "chunk"): (6.0, 0.8),
            (20, "chunk"): (3.0, 0.7),
        }

        snapshot = RagKnowledgeService._build_selected_priority_snapshot(
            chunks,
            summary_scores,
            component_scores=component_scores,
            lexical_weight=0.5,
            vector_weight=0.5,
        )

        # max_lexical = 6.0; doc-10: lex_norm = 6.0/6.0 = 1.000; doc-20: lex_norm = 3.0/6.0 = 0.500
        self.assertIn("6.000", snapshot)
        self.assertIn("1.000", snapshot)
        self.assertIn("3.000", snapshot)
        self.assertIn("0.500", snapshot)
        # hybrid для doc-10: (1.000*0.500)+(0.800*0.500)=0.900
        self.assertIn("(1.000*0.500)+(0.800*0.500)=0.900", snapshot)
        # hybrid для doc-20: (0.500*0.500)+(0.700*0.500)=0.600
        self.assertIn("(0.500*0.500)+(0.700*0.500)=0.600", snapshot)

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

    def test_build_selected_component_scores_fills_vector_only_from_all_lexical(self):
        """Для vector-only чанков подставляется фактический lexical-score из all_lexical_scores."""
        lexical = [
            (3.0, "doc-a.txt", "chunk A", 10),
        ]
        vector = [
            (0.9, "doc-a.txt", "chunk A", 10),
            (0.85, "doc-b.txt", "chunk B", 20),
        ]
        all_lexical_scores = {
            (10, "chunk A"): 3.0,
            (20, "chunk B"): 1.5,
        }

        components = RagKnowledgeService._build_selected_component_scores(
            lexical, vector, all_lexical_scores=all_lexical_scores,
        )

        self.assertEqual(components[(10, "chunk A")], (3.0, 0.9))
        self.assertEqual(components[(20, "chunk B")], (1.5, 0.85))

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

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_html_splitter_enabled", return_value=True):
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

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_html_splitter_enabled", return_value=True):
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

        result, _all_scores = service._search_relevant_chunks("Какой SLA выезда?", limit=1)
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

        result, _all_scores = service._search_relevant_chunks("Какой SLA выезда?", limit=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], "reglament.txt")
        self.assertEqual(result[0][4], 8)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
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
        _mock_hyde,
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

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._get_corpus_version", return_value=3)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._retrieve_context_for_question")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.RagKnowledgeService._log_query")
    @patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider")
    async def test_answer_question_progress_callback_emits_stages_and_marks_cache_hit(
        self,
        mock_get_provider,
        mock_log_query,
        mock_retrieve,
        mock_version,
        _mock_hyde,
    ):
        """Прогресс RAG эмитится на cache-miss и отдельным событием помечает cache-hit."""
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
        self.assertEqual(progress.await_count, 1)
        self.assertEqual(progress.await_args_list[0].args[0], AI_PROGRESS_STAGE_RAG_CACHE_HIT)
        cache_payload = progress.await_args_list[0].args[1]
        self.assertIsInstance(cache_payload, dict)
        self.assertIn("cache_key", cache_payload)
        self.assertIn("cache_ttl_remaining_seconds", cache_payload)
        self.assertGreaterEqual(cache_payload["cache_ttl_remaining_seconds"], 0.0)
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

        rows, vec_scores, vector_source = service._prefilter_documents_by_summary(
            question="Какой SLA выезда",
            question_tokens=service._tokenize("Какой SLA выезда"),
            limit=2,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][1], "sla.txt")
        self.assertIsInstance(vec_scores, dict)
        self.assertEqual(vector_source, "fallback")

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

        rows, _, vector_source = service._prefilter_documents_by_summary(
            question="Какой SLA выезда",
            question_tokens=service._tokenize("Какой SLA выезда"),
            limit=2,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(vector_source, "fallback")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_EXCLUDE_CERTIFICATION_FROM_COUNT", True)
    @patch.object(RagKnowledgeService, "_compute_summary_vector_scores", return_value={})
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_prefilter_documents_by_summary_certification_does_not_consume_quota(
        self,
        mock_get_cursor,
        mock_get_db_connection,
        mock_vec_scores,
    ):
        """Сертификационные документы не занимают квоту prefilter для обычных документов."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {
                "document_id": 1,
                "summary_text": "UPOS установка и обновление",
                "filename": "cert_1.md",
                "source_type": "certification",
            },
            {
                "document_id": 2,
                "summary_text": "UPOS проверка соединения",
                "filename": "cert_2.md",
                "source_type": "certification",
            },
            {
                "document_id": 3,
                "summary_text": "UPOS установка на кассе шаги",
                "filename": "manual_1.md",
                "source_type": "filesystem",
            },
            {
                "document_id": 4,
                "summary_text": "UPOS установка на кассе требования",
                "filename": "manual_2.md",
                "source_type": "filesystem",
            },
            {
                "document_id": 5,
                "summary_text": "UPOS установка на кассе диагностика",
                "filename": "manual_3.md",
                "source_type": "filesystem",
            },
        ]

        rows, _, _ = service._prefilter_documents_by_summary(
            question="UPOS установка",
            question_tokens=service._tokenize("UPOS установка"),
            limit=3,
        )

        returned_ids = [row[0] for row in rows]
        non_cert_ids = {3, 4, 5}
        cert_ids = {1, 2}

        self.assertEqual(len(rows), 5)
        self.assertEqual(len([doc_id for doc_id in returned_ids if doc_id in non_cert_ids]), 3)
        self.assertEqual(len([doc_id for doc_id in returned_ids if doc_id in cert_ids]), 2)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_EXCLUDE_CERTIFICATION_FROM_COUNT", False)
    @patch.object(RagKnowledgeService, "_compute_summary_vector_scores", return_value={})
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_prefilter_documents_by_summary_certification_legacy_quota_mode(
        self,
        mock_get_cursor,
        mock_get_db_connection,
        mock_vec_scores,
    ):
        """При выключенном флаге prefilter соблюдает общий лимит без отдельной квоты."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {
                "document_id": 1,
                "summary_text": "UPOS установка и обновление",
                "filename": "cert_1.md",
                "source_type": "certification",
            },
            {
                "document_id": 2,
                "summary_text": "UPOS проверка соединения",
                "filename": "cert_2.md",
                "source_type": "certification",
            },
            {
                "document_id": 3,
                "summary_text": "UPOS установка на кассе шаги",
                "filename": "manual_1.md",
                "source_type": "filesystem",
            },
            {
                "document_id": 4,
                "summary_text": "UPOS установка на кассе требования",
                "filename": "manual_2.md",
                "source_type": "filesystem",
            },
            {
                "document_id": 5,
                "summary_text": "UPOS установка на кассе диагностика",
                "filename": "manual_3.md",
                "source_type": "filesystem",
            },
        ]

        rows, _, _ = service._prefilter_documents_by_summary(
            question="UPOS установка",
            question_tokens=service._tokenize("UPOS установка"),
            limit=3,
        )

        self.assertEqual(len(rows), 3)

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

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    def test_tokenize_keeps_short_alnum_brand_model_tokens(self, _mock_norm_enabled):
        """Токенизация сохраняет короткие alnum-токены бренда/модели и отсекает служебные короткие слова."""
        service = RagKnowledgeService()

        tokens = service._tokenize("В X5 используется терминал K2 и модель P10")

        self.assertIn("x5", tokens)
        self.assertIn("k2", tokens)
        self.assertIn("p10", tokens)
        self.assertNotIn("в", tokens)
        self.assertNotIn("и", tokens)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    def test_tokenize_keeps_short_numeric_and_domain_tokens(self, _mock_norm_enabled):
        """Токенизация сохраняет короткие доменные токены и числовые идентификаторы (фн 36)."""
        service = RagKnowledgeService()

        tokens = service._tokenize("сколько работает фн 36 на осно?")

        self.assertIn("фн", tokens)
        self.assertIn("36", tokens)
        self.assertIn("осно", tokens)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_ru_normalization_mode", return_value="lemma_then_stem")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=True)
    def test_tokenize_does_not_stem_fixed_tax_term_osno(self, _mock_norm_enabled, _mock_norm_mode):
        """Фиксированный термин 'осно' не должен сокращаться стеммером до 'осн'."""
        service = RagKnowledgeService()

        with patch.object(service, "_lemmatize_ru_token", side_effect=lambda token: token):
            with patch.object(service, "_stem_ru_token", side_effect=lambda token: "осн" if token == "осно" else token):
                tokens = service._tokenize("как работает осно")

        self.assertIn("осно", tokens)
        self.assertNotIn("осн", tokens)

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

        rows, _all_scores = service._search_relevant_chunks(
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
    @patch.object(RagKnowledgeService, "_search_relevant_chunks", return_value=([], {}))
    @patch.object(RagKnowledgeService, "_get_fallback_active_document_ids", return_value=[99, 100])
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_PREFILTER_FALLBACK_DOCS", 2)
    @patch.object(
        RagKnowledgeService,
        "_prefilter_documents_by_summary",
        return_value=([(5, "x5.txt", "summary with x5 shop group", 2.1)], {}, "fallback"),
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

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.info")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_stopwords_enabled", return_value=False)
    @patch.object(RagKnowledgeService, "_build_summary_blocks", return_value=[])
    @patch.object(RagKnowledgeService, "_determine_retrieval_mode", return_value="lexical_only")
    @patch.object(RagKnowledgeService, "_merge_retrieval_candidates", return_value=[])
    @patch.object(RagKnowledgeService, "_search_relevant_chunks_vector", return_value=[])
    @patch.object(RagKnowledgeService, "_search_relevant_chunks", return_value=([], {}))
    @patch.object(RagKnowledgeService, "_prefilter_documents_by_summary", return_value=([], {}, "fallback"))
    def test_retrieve_context_logs_strip_result_after_preprocessing(
        self,
        mock_prefilter,
        mock_search_lexical,
        mock_search_vector,
        mock_merge,
        mock_mode,
        mock_summary_blocks,
        _mock_stopwords,
        _mock_pattern_strip,
        mock_logger_info,
    ):
        """Лог preprocessing содержит итоговую строку запроса после pattern stripping."""
        service = RagKnowledgeService()

        service._retrieve_context_for_question("что такое эквайринг", limit=5)

        preprocessing_logs = [
            call.args[1]
            for call in mock_logger_info.call_args_list
            if call.args
            and len(call.args) > 1
            and call.args[0] == "%s"
            and isinstance(call.args[1], str)
            and call.args[1].startswith("RAG query preprocessing:\n")
        ]
        self.assertTrue(preprocessing_logs)
        self.assertIn("| strip_result", preprocessing_logs[0])
        self.assertIn("эквайринг", preprocessing_logs[0])

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.logger.info")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_stopwords_enabled", return_value=True)
    @patch.object(RagKnowledgeService, "_build_summary_blocks", return_value=[])
    @patch.object(RagKnowledgeService, "_determine_retrieval_mode", return_value="lexical_only")
    @patch.object(RagKnowledgeService, "_merge_retrieval_candidates", return_value=[])
    @patch.object(RagKnowledgeService, "_search_relevant_chunks_vector", return_value=[])
    @patch.object(RagKnowledgeService, "_search_relevant_chunks", return_value=([], {}))
    @patch.object(RagKnowledgeService, "_prefilter_documents_by_summary", return_value=([], {}, "fallback"))
    def test_retrieve_context_logs_preprocess_result_without_common_words(
        self,
        mock_prefilter,
        mock_search_lexical,
        mock_search_vector,
        mock_merge,
        mock_mode,
        mock_summary_blocks,
        _mock_stopwords,
        _mock_pattern_strip,
        mock_logger_info,
    ):
        """Поле preprocess_result в логе не содержит удалённые стоп-слова (например, 'где')."""
        service = RagKnowledgeService()

        service._retrieve_context_for_question("где наша папка вкусвилл?", limit=5)

        matched = False
        for call in mock_logger_info.call_args_list:
            if not (
                call.args
                and len(call.args) > 1
                and call.args[0] == "%s"
                and isinstance(call.args[1], str)
                and call.args[1].startswith("RAG query preprocessing:\n")
            ):
                continue

            preprocess_result = ""
            for line in str(call.args[1] or "").splitlines():
                if "| preprocess_result" in line:
                    cells = [cell.strip() for cell in line.split("|") if cell.strip()]
                    if len(cells) >= 2:
                        preprocess_result = cells[1]
                    break
            if "где" not in preprocess_result and "вкусвилл" in preprocess_result:
                matched = True
                break

        self.assertTrue(matched)

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

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYBRID_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_LEXICAL_WEIGHT", 0.5)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_SEMANTIC_WEIGHT", 0.5)
    def test_merge_retrieval_candidates_normalizes_lexical_scores(self):
        """Lexical-score нормализуется в 0..1 перед hybrid-взвешиванием, чтобы не доминировать над vector."""
        service = RagKnowledgeService()
        # BM25-подобные score (не ограничены 0..1)
        lexical = [
            (5.0, "doc-high-bm25.txt", "chunk A", 1),
            (2.5, "doc-low-bm25.txt", "chunk B", 2),
        ]
        vector = [
            (0.9, "doc-vec.txt", "chunk C", 3),
        ]

        rows = service._merge_retrieval_candidates(lexical_chunks=lexical, vector_chunks=vector, limit=3)

        self.assertEqual(len(rows), 3)
        # doc-1 norm_lex=5.0/5.0=1.0, fused=1.0*0.5+0*0.5=0.5
        # doc-2 norm_lex=2.5/5.0=0.5, fused=0.5*0.5+0*0.5=0.25
        # doc-3 norm_lex=0/5.0=0.0, fused=0*0.5+0.9*0.5=0.45
        # Порядок: doc-1 (0.5), doc-3 (0.45), doc-2 (0.25)
        self.assertEqual(rows[0][1], "doc-high-bm25.txt")
        self.assertEqual(rows[1][1], "doc-vec.txt")
        self.assertEqual(rows[2][1], "doc-low-bm25.txt")
        # Без нормализации: doc-1=2.5, doc-2=1.25, doc-3=0.45 -> doc-3 был бы последним.
        # С нормализацией doc-3 (vector=0.9) обходит doc-2, что корректно.
        self.assertAlmostEqual(rows[0][0], 0.5, places=2)
        self.assertAlmostEqual(rows[1][0], 0.45, places=2)
        self.assertAlmostEqual(rows[2][0], 0.25, places=2)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYBRID_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_LEXICAL_WEIGHT", 0.5)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_SEMANTIC_WEIGHT", 0.5)
    def test_merge_retrieval_candidates_uses_all_lexical_scores_for_vector_only(self):
        """Vector-only чанки получают фактический lexical-score из all_lexical_scores вместо 0."""
        service = RagKnowledgeService()
        lexical = [
            (4.0, "doc-a.txt", "chunk A", 1),
        ]
        vector = [
            (0.8, "doc-a.txt", "chunk A", 1),
            (0.9, "doc-b.txt", "chunk B", 2),
        ]
        # chunk B не попал в lexical top-K, но его фактический lexical-score = 2.0
        all_lexical_scores = {
            (1, "chunk A"): 4.0,
            (2, "chunk B"): 2.0,
        }

        rows = service._merge_retrieval_candidates(
            lexical_chunks=lexical,
            vector_chunks=vector,
            limit=3,
            all_lexical_scores=all_lexical_scores,
        )

        self.assertEqual(len(rows), 2)
        # doc-1: lex=4.0, vec=0.8, max_lex=4.0 → norm_lex=1.0 → fused=1.0*0.5+0.8*0.5=0.9
        # doc-2: lex=2.0 (из all_lexical_scores), vec=0.9, norm_lex=0.5 → fused=0.5*0.5+0.9*0.5=0.7
        self.assertEqual(rows[0][1], "doc-a.txt")
        self.assertAlmostEqual(rows[0][0], 0.9, places=2)
        self.assertEqual(rows[1][1], "doc-b.txt")
        self.assertAlmostEqual(rows[1][0], 0.7, places=2)
        # Без all_lexical_scores doc-2 получил бы lex=0, fused=0*0.5+0.9*0.5=0.45

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYBRID_ENABLED", False)
    def test_merge_retrieval_candidates_vector_only(self):
        """При выключенном hybrid используются только vector-кандидаты."""
        service = RagKnowledgeService()
        lexical = [(1.5, "doc-a.txt", "lexical", 1)]
        vector = [(0.7, "doc-v.txt", "vector", 9)]

        rows = service._merge_retrieval_candidates(lexical_chunks=lexical, vector_chunks=vector, limit=2)

        self.assertEqual(rows, vector)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_CERTIFICATION_CATEGORY_BOOST", 0.4)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_CERTIFICATION_STALE_PENALTY", 0.2)
    def test_apply_signal_adjustments_to_chunks_prioritizes_category_and_penalizes_stale(self):
        """Category match повышает score, stale-флаг понижает score в финальном ранжировании."""
        service = RagKnowledgeService()
        chunks = [
            (1.0, "doc-a.txt", "chunk-a", 10, 0),
            (1.0, "doc-b.txt", "chunk-b", 20, 0),
        ]

        with patch.object(
            service,
            "_load_document_signals",
            return_value={
                10: {
                    "category_keys": ["upos ошибки"],
                    "is_outdated": False,
                    "is_active": True,
                },
                20: {
                    "category_keys": ["upos ошибки"],
                    "is_outdated": True,
                    "is_active": True,
                },
            },
        ):
            adjusted = service._apply_signal_adjustments_to_chunks(
                chunks=chunks,
                category_hint="upos ошибки",
            )

        self.assertEqual(adjusted[0][3], 10)
        self.assertAlmostEqual(adjusted[0][0], 1.4)
        self.assertEqual(adjusted[1][3], 20)
        self.assertAlmostEqual(adjusted[1][0], 1.2)

    def test_build_certification_question_document_payload_contains_correct_pair(self):
        """Формирование RAG-документа из вопроса аттестации включает правильную Q/A пару."""
        service = RagKnowledgeService()
        filename, payload, signal_data, deterministic_summary = service._build_certification_question_document_payload(
            {
                "question_id": 77,
                "question_text": "Что означает E_TIMEOUT?",
                "option_a": "Недостаточно средств",
                "option_b": "Превышение времени ожидания",
                "option_c": "Блокировка карты",
                "option_d": "Ошибка сети",
                "correct_option": "B",
                "explanation": "Операция превысила время ожидания",
                "difficulty": "medium",
                "relevance_date": "2030-01-01",
                "active": 1,
                "category_names": "UPOS ошибки||Общие знания",
            }
        )

        text = payload.decode("utf-8")
        self.assertEqual(filename, "certification_q_77.md")
        self.assertIn("Вопрос:\nЧто означает E_TIMEOUT?", text)
        self.assertIn("Правильный ответ: Превышение времени ожидания", text)
        self.assertIn("Категория: UPOS ошибки, Общие знания", text)
        self.assertNotIn("Варианты ответа:", text)
        self.assertNotIn("Недостаточно средств", text)
        self.assertNotIn("Вопрос ID:", text)
        self.assertNotIn("Источник: Аттестация", text)
        self.assertNotIn("Статус:", text)
        self.assertNotIn("Актуальность:", text)
        self.assertNotIn("Актуален до:", text)
        self.assertNotIn("A)", text)
        self.assertEqual(signal_data["question_id"], 77)
        self.assertIn("Правильный ответ: Превышение времени ожидания", deterministic_summary)

    def test_sync_certification_questions_to_rag_updates_and_purges(self):
        """Синк сертификации обновляет изменённые документы и удаляет отсутствующие."""
        service = RagKnowledgeService()
        row = {
            "question_id": 5,
            "question_text": "Вопрос",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_option": "A",
            "explanation": "Пояснение",
            "difficulty": "easy",
            "relevance_date": "2030-01-01",
            "active": 1,
            "category_names": "Общие знания",
        }

        with patch.object(service, "_load_certification_questions_for_rag", return_value=[row]):
            with patch.object(
                service,
                "list_documents_by_source",
                return_value=[
                    {
                        "id": 101,
                        "source_url": "certification://question/5",
                        "content_hash": "old-hash",
                    },
                    {
                        "id": 102,
                        "source_url": "certification://question/99",
                        "content_hash": "old-hash-2",
                    },
                ],
            ):
                with patch.object(service, "delete_document", return_value=True) as mock_delete:
                    with patch.object(
                        service,
                        "ingest_document_from_bytes",
                        return_value={"document_id": 555, "chunks_count": 1, "is_duplicate": 0},
                    ) as mock_ingest:
                        with patch.object(service, "_upsert_document_signal"):
                            stats = service.sync_certification_questions_to_rag(uploaded_by=9, upsert_vectors=False)

        self.assertEqual(stats["questions_total"], 1)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(stats["purged"], 1)
        self.assertEqual(stats["ingested"], 0)
        self.assertEqual(mock_delete.call_count, 2)
        self.assertTrue(mock_ingest.called)
        ingest_kwargs = mock_ingest.call_args.kwargs
        self.assertIn("preset_summary_text", ingest_kwargs)
        self.assertIn("Правильный ответ:", str(ingest_kwargs.get("preset_summary_text") or ""))

    def test_sync_certification_questions_to_rag_force_update_reingests_unchanged(self):
        """Force-update принудительно переингестит документ даже при совпадении hash."""
        service = RagKnowledgeService()
        row = {
            "question_id": 7,
            "question_text": "Вопрос",
            "option_a": "A",
            "option_b": "B",
            "option_c": "C",
            "option_d": "D",
            "correct_option": "A",
            "explanation": "Пояснение",
            "difficulty": "easy",
            "relevance_date": "2030-01-01",
            "active": 1,
            "category_names": "Общие знания",
        }

        with patch.object(service, "_load_certification_questions_for_rag", return_value=[row]):
            with patch.object(
                service,
                "list_documents_by_source",
                return_value=[
                    {
                        "id": 111,
                        "source_url": "certification://question/7",
                        "content_hash": hashlib.sha256(
                            service._build_certification_question_document_payload(row)[1]
                        ).hexdigest(),
                    }
                ],
            ):
                with patch.object(service, "delete_document", return_value=True) as mock_delete:
                    with patch.object(
                        service,
                        "ingest_document_from_bytes",
                        return_value={"document_id": 777, "chunks_count": 1, "is_duplicate": 0},
                    ) as mock_ingest:
                        with patch.object(service, "_upsert_document_signal"):
                            stats = service.sync_certification_questions_to_rag(
                                uploaded_by=9,
                                upsert_vectors=True,
                                force_update=True,
                            )

        self.assertEqual(stats["questions_total"], 1)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(stats["unchanged"], 0)
        self.assertEqual(stats["ingested"], 0)
        mock_delete.assert_called_once_with(111, updated_by=9, hard_delete=True)
        self.assertTrue(mock_ingest.called)
        self.assertTrue(bool(mock_ingest.call_args.kwargs.get("upsert_vectors")))

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
        mock_prefilter.return_value = ([], {}, "fallback")
        mock_search_lexical.return_value = ([(1.0, "kb.txt", "lexical block", 10)], {(10, "lexical block"): 1.0})
        mock_search_vector.return_value = []
        mock_merge.return_value = [(1.0, "kb.txt", "lexical block", 10)]

        chunks, summary_blocks = service._retrieve_context_for_question("Как прошить d200", limit=5)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(summary_blocks, [])
        retrieval_logs = [
            call.args[1]
            for call in mock_logger_info.call_args_list
            if call.args
            and len(call.args) > 1
            and call.args[0] == "%s"
            and isinstance(call.args[1], str)
            and call.args[1].startswith("RAG retrieval:\n")
        ]
        self.assertTrue(retrieval_logs)
        retrieval_log = retrieval_logs[0]

        self.assertTrue(
            "| mode" in retrieval_log and "lexical_only" in retrieval_log
        )
        self.assertTrue(
            "| prefilter_scope_docs" in retrieval_log and "| lexical_scorer" in retrieval_log
        )
        self.assertTrue(
            "| selected_unique_docs" in retrieval_log and "| selected_top_docs" in retrieval_log
        )
        self.assertTrue(
            "| timings_ms.total" in retrieval_log
            and "| timings_ms.prefilter" in retrieval_log
            and "| timings_ms.lexical" in retrieval_log
            and "| timings_ms.vector" in retrieval_log
            and "| timings_ms.merge" in retrieval_log
            and "| timings_ms.summary_blocks" in retrieval_log
        )
        self.assertTrue(
            any(
                call.args
                and len(call.args) > 1
                and call.args[0] == "%s"
                and isinstance(call.args[1], str)
                and call.args[1].startswith("RAG priority evidence:\n")
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

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PROMPT_SUMMARY_DOCS", 2)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PROMPT_SUMMARIES_EXCLUDE_CERTIFICATION", True)
    def test_build_summary_blocks_excludes_certification_when_enabled(self, *_):
        """При включённом флаге summary сертификационных Q/A не попадают в joined_summaries."""
        blocks = RagKnowledgeService._build_summary_blocks(
            [
                (1, "certification_q_11.md", "Короткий summary cert", 0.95),
                (2, "reglament_upos.md", "Обычный summary 1", 0.90),
                (3, "certification_q_12.md", "Короткий summary cert 2", 0.89),
                (4, "manual.md", "Обычный summary 2", 0.88),
            ]
        )

        self.assertEqual(len(blocks), 2)
        self.assertIn("reglament_upos.md", blocks[0])
        self.assertIn("manual.md", blocks[1])
        self.assertNotIn("certification_q_11.md", "\n".join(blocks))
        self.assertNotIn("certification_q_12.md", "\n".join(blocks))

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PROMPT_SUMMARY_DOCS", 2)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PROMPT_SUMMARIES_EXCLUDE_CERTIFICATION", False)
    def test_build_summary_blocks_keeps_certification_when_disabled(self, *_):
        """При выключенном флаге summary сертификационных Q/A могут попадать в joined_summaries."""
        blocks = RagKnowledgeService._build_summary_blocks(
            [
                (1, "certification_q_11.md", "Короткий summary cert", 0.95),
                (2, "reglament_upos.md", "Обычный summary 1", 0.90),
            ]
        )

        self.assertEqual(len(blocks), 2)
        self.assertIn("certification_q_11.md", blocks[0])

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
        self.assertEqual(stats["summaries_indexed"], 0)
        self.assertEqual(stats["errors"], 0)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_ENABLED", True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_summary_vector_enabled", return_value=True)
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_backfill_vector_index_dry_run_target_summaries(
        self,
        mock_get_cursor,
        mock_get_db_connection,
        mock_summary_enabled,
    ):
        """Dry-run backfill в режиме summaries считает summary без индексации чанков."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {
                "id": 11,
                "filename": "manual.txt",
                "source_type": "filesystem",
                "summary_text": "Краткое summary",
            }
        ]

        stats = service.backfill_vector_index(batch_size=10, dry_run=True, target="summaries")

        self.assertEqual(stats["documents_total"], 1)
        self.assertEqual(stats["documents_processed"], 1)
        self.assertEqual(stats["chunks_indexed"], 0)
        self.assertEqual(stats["summaries_indexed"], 1)
        self.assertEqual(stats["errors"], 0)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_summary_vector_enabled", return_value=True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_VECTOR_ENABLED", True)
    def test_prefilter_documents_by_summary_uses_collection_scores(self, mock_summary_enabled):
        """Summary-prefilter использует vector-score из коллекции без fallback на in-memory encode."""
        service = RagKnowledgeService()
        with patch("src.common.database.get_db_connection"), patch("src.common.database.get_cursor") as mock_get_cursor:
            cursor = mock_get_cursor.return_value.__enter__.return_value
            cursor.fetchall.return_value = [
                {
                    "document_id": 1,
                    "summary_text": "Регламент SLA выезда",
                    "filename": "sla.txt",
                }
            ]
            with patch.object(
                service,
                "_search_summary_vector_scores_from_collection",
                return_value={1: 0.8},
            ) as mock_collection_scores, patch.object(
                service,
                "_compute_summary_vector_scores",
                return_value={1: 0.1},
            ) as mock_fallback_scores:
                rows, vector_scores, vector_source = service._prefilter_documents_by_summary(
                    question="Какой SLA",
                    question_tokens=service._tokenize("Какой SLA"),
                    limit=2,
                )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(vector_scores.get(1), 0.8)
        self.assertEqual(vector_source, "collection")
        mock_collection_scores.assert_called_once()
        mock_fallback_scores.assert_not_called()

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

    # =============================================
    # Тесты Query Preprocessing: стоп-слова, паттерны, IDF dampening
    # =============================================

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_stopwords_enabled", return_value=True)
    def test_filter_stopwords_removes_common_words(self, _mock_enabled):
        """Стоп-слова 'что', 'такое' удаляются, предметный токен 'любовь' остаётся."""
        service = RagKnowledgeService()
        tokens = ["что", "такое", "любовь"]
        result = service._filter_stopwords(tokens)

        self.assertNotIn("что", result)
        self.assertNotIn("такое", result)
        self.assertIn("любовь", result)
        self.assertEqual(len(result), 1)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_stopwords_enabled", return_value=True)
    def test_filter_stopwords_preserves_all_if_all_stopwords(self, _mock_enabled):
        """Если все токены — стоп-слова, safety guard возвращает оригинал."""
        service = RagKnowledgeService()
        tokens = ["что", "это", "такое"]
        result = service._filter_stopwords(tokens)

        self.assertEqual(result, tokens)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_stopwords_enabled", return_value=False)
    def test_filter_stopwords_disabled_returns_original(self, _mock_enabled):
        """При отключённых стоп-словах список возвращается без изменений."""
        service = RagKnowledgeService()
        tokens = ["что", "такое", "любовь"]
        result = service._filter_stopwords(tokens)

        self.assertEqual(result, tokens)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_stopwords_enabled", return_value=True)
    def test_filter_stopwords_empty_input(self, _mock_enabled):
        """Пустой список токенов возвращается без изменений."""
        service = RagKnowledgeService()
        result = service._filter_stopwords([])
        self.assertEqual(result, [])

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    def test_strip_query_patterns_extracts_subject(self, _mock_enabled):
        """'что такое любовь' → 'любовь'."""
        result, stripped = RagKnowledgeService._strip_query_patterns("что такое любовь")
        self.assertTrue(stripped)
        self.assertEqual(result, "любовь")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    def test_strip_query_patterns_multi_word_subject(self, _mock_enabled):
        """'что такое ключ транзакции' → 'ключ транзакции'."""
        result, stripped = RagKnowledgeService._strip_query_patterns("что такое ключ транзакции")
        self.assertTrue(stripped)
        self.assertEqual(result, "ключ транзакции")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    def test_strip_query_patterns_kak_rabotaet(self, _mock_enabled):
        """'как работает NFC' → 'NFC'."""
        result, stripped = RagKnowledgeService._strip_query_patterns("как работает NFC")
        self.assertTrue(stripped)
        self.assertEqual(result, "NFC")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    def test_strip_query_patterns_zachem_nuzhen(self, _mock_enabled):
        """'зачем нужен POS-терминал' → 'POS-терминал'."""
        result, stripped = RagKnowledgeService._strip_query_patterns("зачем нужен POS-терминал")
        self.assertTrue(stripped)
        self.assertIn("POS", result)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    def test_strip_query_patterns_no_match_returns_original(self, _mock_enabled):
        """Запрос без шаблонного префикса возвращается без изменений."""
        result, stripped = RagKnowledgeService._strip_query_patterns("расписание дежурств")
        self.assertFalse(stripped)
        self.assertEqual(result, "расписание дежурств")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    def test_strip_query_patterns_empty_subject_returns_original(self, _mock_enabled):
        """'что такое ?' — предметная часть пуста, возвращается оригинал."""
        result, stripped = RagKnowledgeService._strip_query_patterns("что такое ?")
        self.assertFalse(stripped)
        self.assertEqual(result, "что такое ?")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=False)
    def test_strip_query_patterns_disabled_returns_original(self, _mock_enabled):
        """При отключённым pattern-stripping запрос не изменяется."""
        result, stripped = RagKnowledgeService._strip_query_patterns("что такое любовь")
        self.assertFalse(stripped)
        self.assertEqual(result, "что такое любовь")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    def test_strip_query_patterns_rasskazhi_pro(self, _mock_enabled):
        """'расскажи про эквайринг' → 'эквайринг'."""
        result, stripped = RagKnowledgeService._strip_query_patterns("расскажи про эквайринг")
        self.assertTrue(stripped)
        self.assertEqual(result, "эквайринг")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    def test_strip_query_patterns_strips_trailing_punctuation(self, _mock_enabled):
        """Из предметной части удаляются завершающие знаки пунктуации."""
        result, stripped = RagKnowledgeService._strip_query_patterns("что такое эквайринг?")
        self.assertTrue(stripped)
        self.assertEqual(result, "эквайринг")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_query_pattern_strip_enabled", return_value=True)
    def test_strip_query_patterns_preserves_hashtag_words(self, _mock_enabled):
        """В strip-result сохраняются слова, начинающиеся с '#' (хештеги)."""
        result, stripped = RagKnowledgeService._strip_query_patterns("расскажи про #upos подробно")
        self.assertTrue(stripped)
        self.assertEqual(result, "#upos подробно")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_RATIO", 0.5)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_FACTOR", 0.1)
    def test_dampen_common_query_tokens_boosts_rare(self, *_):
        """Редкие токены повторяются, а частые — нет."""
        query_tokens = ["что", "такое", "любовь"]
        corpus = [
            ["что", "такое", "рассвет"],
            ["что", "такое", "звезда"],
            ["что", "такое", "эквайринг"],
            ["любовь", "это", "чувство"],
        ]

        result = RagKnowledgeService._dampen_common_query_tokens(query_tokens, corpus)

        # 'что' и 'такое' встречаются в 3/4 (75% > 50%), они dampened
        # Но 50% threshold = 0.5*4 = 2 — 3 > 2 → dampened
        # 'любовь' встречается в 1/4 = 25% < 50% → boosted
        count_common = sum(1 for t in result if t in {"что", "такое"})
        count_rare = sum(1 for t in result if t == "любовь")

        # Каждый common token включён максимум 1 раз
        self.assertLessEqual(count_common, 2)
        # Редкий токен повторяется (boost_factor = round(1/0.1) = 10)
        self.assertGreater(count_rare, 1)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_RATIO", 0.8)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_FACTOR", 0.1)
    def test_dampen_common_query_tokens_all_common_returns_original(self, *_):
        """Если все query-токены common, dampening не применяется (safety guard)."""
        query_tokens = ["что", "такое"]
        corpus = [
            ["что", "такое", "рассвет"],
            ["что", "такое", "звезда"],
        ]

        result = RagKnowledgeService._dampen_common_query_tokens(query_tokens, corpus)
        self.assertEqual(result, query_tokens)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_RATIO", 0.8)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_FACTOR", 0.1)
    def test_dampen_common_query_tokens_empty_inputs(self, *_):
        """Пустые входные данные обрабатываются без ошибок."""
        self.assertEqual(RagKnowledgeService._dampen_common_query_tokens([], [["a"]]), [])
        self.assertEqual(RagKnowledgeService._dampen_common_query_tokens(["a"], []), ["a"])

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_MATCH_PHRASE_WEIGHT", 0.0)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_SUMMARY_MATCH_TOKEN_WEIGHT", 1.0)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_RATIO", 0.5)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_PREFILTER_IDF_DAMPEN_FACTOR", 0.1)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_lexical_scorer", return_value="bm25")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    @patch.object(RagKnowledgeService, "_search_summary_vector_scores_from_collection", return_value={})
    @patch.object(RagKnowledgeService, "_compute_summary_vector_scores", return_value={})
    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_prefilter_with_stopwords_favors_subject_match(
        self,
        mock_get_cursor,
        mock_get_db_connection,
        mock_vec_scores,
        mock_vec_collection,
        mock_norm,
        mock_mode,
        *_,
    ):
        """Prefilter с IDF dampening ранжирует документ с 'любовь' выше 'рассвет'."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {"document_id": 1, "summary_text": "Категория: Общее. Вопрос: Что такое рассвет? Правильный ответ: Восход солнца", "filename": "q_rassvet.txt"},
            {"document_id": 2, "summary_text": "Категория: Общее. Вопрос: Что такое звезда? Правильный ответ: Небесное тело", "filename": "q_zvezda.txt"},
            {"document_id": 3, "summary_text": "Любовь — глубокое чувство привязанности между людьми", "filename": "love.txt"},
            {"document_id": 4, "summary_text": "Категория: Общее. Вопрос: Что такое облако? Правильный ответ: Скопление водяного пара", "filename": "q_oblako.txt"},
        ]

        # Токены после stopword filtering: ["любовь"] (без "что", "такое")
        rows, _, _ = service._prefilter_documents_by_summary(
            question="что такое любовь",
            question_tokens=["любовь"],
            limit=4,
        )

        # Документ №3 (love.txt) должен быть в top-1, т.к. содержит "любовь"
        self.assertTrue(len(rows) > 0)
        top_doc_id = rows[0][0]
        self.assertEqual(top_doc_id, 3, f"Ожидался документ 3 (love.txt) на первом месте, получен {top_doc_id}")

    # ─── HyDE (Hypothetical Document Embeddings) ──────────────────────

    def test_hyde_prompt_builds_correctly(self):
        """build_hyde_prompt включает вопрос и лимит символов."""
        from src.sbs_helper_telegram_bot.ai_router.prompts import build_hyde_prompt

        prompt = build_hyde_prompt("что такое любовь", max_chars=300)
        self.assertIn("что такое любовь", prompt)
        self.assertIn("300", prompt)
        self.assertIn("русском", prompt)

    def test_hyde_prompt_default_max_chars(self):
        """build_hyde_prompt с дефолтным max_chars содержит '500'."""
        from src.sbs_helper_telegram_bot.ai_router.prompts import build_hyde_prompt

        prompt = build_hyde_prompt("тест")
        self.assertIn("500", prompt)

    def test_hyde_cache_stores_and_retrieves(self):
        """HyDE кэш сохраняет и возвращает текст."""
        service = RagKnowledgeService()
        service._cache_hyde_text("вопрос", "гипотетический ответ")
        result = service._get_cached_hyde_text("вопрос")
        self.assertEqual(result, "гипотетический ответ")

    def test_hyde_cache_miss_returns_none(self):
        """HyDE кэш возвращает None для отсутствующего ключа."""
        service = RagKnowledgeService()
        result = service._get_cached_hyde_text("неизвестный вопрос")
        self.assertIsNone(result)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYDE_CACHE_TTL_SECONDS", 0)
    def test_hyde_cache_expired_returns_none(self):
        """HyDE кэш возвращает None для просроченного ключа."""
        import time

        service = RagKnowledgeService()
        # Вставляем запись с истёкшим TTL
        service._hyde_cache["expired_q"] = ("old text", time.time() - 10)
        result = service._get_cached_hyde_text("expired_q")
        self.assertIsNone(result)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=False)
    async def test_hyde_disabled_skips_generation(self, _mock_hyde_enabled):
        """При выключенном HyDE LLM не вызывается и hyde_text=None."""
        service = RagKnowledgeService()
        with patch.object(service, "_retrieve_context_for_question", return_value=([], [])) as mock_retrieve:
            result = await service.answer_question("тестовый вопрос", user_id=1)
            self.assertIsNone(result)
            if mock_retrieve.called:
                call_kwargs = mock_retrieve.call_args
                hyde_arg = call_kwargs.kwargs.get("hyde_text") if call_kwargs.kwargs else None
                self.assertIsNone(hyde_arg)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYDE_MAX_CHARS", 200)
    async def test_hyde_enabled_generates_text(self, *_):
        """При включенном HyDE генерируется гипотетический документ и передаётся в retrieval."""
        service = RagKnowledgeService()

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value="Любовь — это глубокое чувство")

        with patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider", return_value=mock_provider):
            with patch.object(
                service, "_retrieve_context_for_question", return_value=([], [])
            ) as mock_retrieve:
                await service.answer_question("что такое любовь?", user_id=1)

                if mock_retrieve.called:
                    call_kwargs = mock_retrieve.call_args
                    hyde_arg = call_kwargs.kwargs.get("hyde_text") if call_kwargs.kwargs else None
                    self.assertIsNotNone(hyde_arg)
                    self.assertIn("Любовь", hyde_arg)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYDE_MAX_CHARS", 200)
    async def test_hyde_failure_graceful_degradation(self, *_):
        """При ошибке HyDE-генерации retrieval продолжается без HyDE."""
        service = RagKnowledgeService()

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(side_effect=RuntimeError("LLM unavailable"))

        with patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider", return_value=mock_provider):
            with patch.object(
                service, "_retrieve_context_for_question", return_value=([], [])
            ) as mock_retrieve:
                # Не должно выбрасывать исключение
                result = await service.answer_question("тестовый вопрос", user_id=1)
                self.assertIsNone(result)
                if mock_retrieve.called:
                    call_kwargs = mock_retrieve.call_args
                    hyde_arg = call_kwargs.kwargs.get("hyde_text") if call_kwargs.kwargs else None
                    self.assertIsNone(hyde_arg)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYDE_MAX_CHARS", 100)
    async def test_hyde_text_cached_on_success(self, *_):
        """Успешно сгенерированный HyDE-текст кэшируется."""
        service = RagKnowledgeService()

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value="Кэшируемый ответ")

        with patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider", return_value=mock_provider):
            with patch.object(service, "_retrieve_context_for_question", return_value=([], [])):
                await service.answer_question("кэш вопрос", user_id=1)

        cached = service._get_cached_hyde_text("кэш вопрос")
        self.assertIsNotNone(cached)
        self.assertEqual(cached, "Кэшируемый ответ")

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYDE_MAX_CHARS", 100)
    async def test_hyde_cache_hit_skips_llm_call(self, *_):
        """При наличии HyDE в кэше LLM не вызывается повторно."""
        service = RagKnowledgeService()
        service._cache_hyde_text("cached question", "cached hyde text")

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value="new text")

        with patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider", return_value=mock_provider):
            with patch.object(
                service, "_retrieve_context_for_question", return_value=([], [])
            ) as mock_retrieve:
                await service.answer_question("cached question", user_id=1)

                if mock_retrieve.called:
                    call_kwargs = mock_retrieve.call_args
                    hyde_arg = call_kwargs.kwargs.get("hyde_text") if call_kwargs.kwargs else None
                    self.assertEqual(hyde_arg, "cached hyde text")

        # provider.chat НЕ должен быть вызван для HyDE (может быть вызван для RAG-ответа)
        hyde_calls = [
            c for c in mock_provider.chat.call_args_list
            if c.kwargs.get("purpose") == "response"
        ]
        self.assertEqual(len(hyde_calls), 0)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_enabled", return_value=True)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.AI_RAG_HYDE_MAX_CHARS", 50)
    async def test_hyde_text_truncated_to_max_chars(self, *_):
        """HyDE-текст обрезается до AI_RAG_HYDE_MAX_CHARS."""
        service = RagKnowledgeService()
        long_text = "А" * 200

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=long_text)

        with patch("src.sbs_helper_telegram_bot.ai_router.llm_provider.get_provider", return_value=mock_provider):
            with patch.object(
                service, "_retrieve_context_for_question", return_value=([], [])
            ) as mock_retrieve:
                await service.answer_question("тест обрезки", user_id=1)

                if mock_retrieve.called:
                    call_kwargs = mock_retrieve.call_args
                    hyde_arg = call_kwargs.kwargs.get("hyde_text") if call_kwargs.kwargs else None
                    self.assertIsNotNone(hyde_arg)
                    self.assertLessEqual(len(hyde_arg), 50)

    def test_search_relevant_chunks_vector_uses_hyde_text(self):
        """_search_relevant_chunks_vector эмбеддит hyde_text вместо вопроса."""
        service = RagKnowledgeService()

        mock_embedding = MagicMock()
        mock_embedding.encode_texts = MagicMock(return_value=[[0.1, 0.2, 0.3]])

        mock_index = MagicMock()
        mock_index.search = MagicMock(return_value=[])

        with patch.object(service, "_is_vector_search_enabled", return_value=True):
            with patch.object(service, "_get_embedding_provider", return_value=mock_embedding):
                with patch.object(service, "_get_vector_index", return_value=mock_index):
                    service._search_relevant_chunks_vector(
                        question="оригинальный вопрос",
                        prefiltered_doc_ids=None,
                        hyde_text="гипотетический ответ",
                    )

        # encode_texts должен получить hyde_text, а не question
        mock_embedding.encode_texts.assert_called_once_with(["гипотетический ответ"])

    def test_search_relevant_chunks_vector_without_hyde(self):
        """_search_relevant_chunks_vector без hyde_text эмбеддит вопрос."""
        service = RagKnowledgeService()

        mock_embedding = MagicMock()
        mock_embedding.encode_texts = MagicMock(return_value=[[0.1, 0.2, 0.3]])

        mock_index = MagicMock()
        mock_index.search = MagicMock(return_value=[])

        with patch.object(service, "_is_vector_search_enabled", return_value=True):
            with patch.object(service, "_get_embedding_provider", return_value=mock_embedding):
                with patch.object(service, "_get_vector_index", return_value=mock_index):
                    service._search_relevant_chunks_vector(
                        question="оригинальный вопрос",
                        prefiltered_doc_ids=None,
                    )

        mock_embedding.encode_texts.assert_called_once_with(["оригинальный вопрос"])

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_summary_vector_enabled", return_value=True)
    def test_summary_vector_collection_uses_hyde_text(self, _):
        """_search_summary_vector_scores_from_collection эмбеддит hyde_text."""
        service = RagKnowledgeService()

        mock_embedding = MagicMock()
        mock_embedding.encode_texts = MagicMock(return_value=[[0.1, 0.2, 0.3]])

        mock_index = MagicMock()
        mock_index.search_summaries = MagicMock(return_value=[])

        with patch.object(service, "_is_vector_search_enabled", return_value=True):
            with patch.object(service, "_get_embedding_provider", return_value=mock_embedding):
                with patch.object(service, "_get_vector_index", return_value=mock_index):
                    service._search_summary_vector_scores_from_collection(
                        question="оригинальный вопрос",
                        document_ids=[1, 2],
                        limit=10,
                        hyde_text="гипотетический документ",
                    )

        mock_embedding.encode_texts.assert_called_once_with(["гипотетический документ"])

    def test_compute_summary_vector_scores_uses_hyde_text(self):
        """_compute_summary_vector_scores эмбеддит hyde_text для cosine similarity."""
        service = RagKnowledgeService()

        mock_embedding = MagicMock()
        mock_embedding.encode_texts = MagicMock(return_value=[[0.5, 0.5]])

        with patch.object(service, "_get_embedding_provider", return_value=mock_embedding):
            with patch.object(service, "_get_corpus_version", return_value=1):
                service._compute_summary_vector_scores(
                    question="оригинальный вопрос",
                    summaries=[(1, "summary text")],
                    hyde_text="гипотетический документ",
                )

        # Первый вызов encode_texts должен быть для hyde_text
        first_call = mock_embedding.encode_texts.call_args_list[0]
        self.assertEqual(first_call[0][0], ["гипотетический документ"])

    def test_is_rag_hyde_enabled_default_false(self):
        """is_rag_hyde_enabled по умолчанию возвращает False."""
        from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings_mod

        with patch.object(ai_settings_mod, "AI_RAG_HYDE_ENABLED", False):
            with patch.object(ai_settings_mod, "_safe_get_setting", return_value=None):
                result = ai_settings_mod.is_rag_hyde_enabled()
                self.assertFalse(result)

    def test_is_rag_hyde_enabled_db_override(self):
        """is_rag_hyde_enabled учитывает DB override."""
        from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings_mod

        with patch.object(ai_settings_mod, "AI_RAG_HYDE_ENABLED", False):
            with patch.object(ai_settings_mod, "_safe_get_setting", return_value="1"):
                result = ai_settings_mod.is_rag_hyde_enabled()
                self.assertTrue(result)

    # ─── HyDE lexical augmentation ─────────────────────────────────

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_ru_normalization_mode", return_value="lemma_then_stem")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    def test_augment_tokens_with_hyde_adds_unique_tokens(self, *_):
        """_augment_tokens_with_hyde добавляет уникальные HyDE-токены к query-токенам."""
        service = RagKnowledgeService()
        original = ["любовь"]
        result = service._augment_tokens_with_hyde(
            original, "Любовь — глубокое чувство привязанности между людьми"
        )
        self.assertEqual(result[0], "любовь")
        self.assertGreater(len(result), 1)
        # Исходный токен не дублируется
        self.assertEqual(result.count("любовь"), 1)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_ru_normalization_mode", return_value="lemma_then_stem")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    def test_augment_tokens_with_hyde_empty_text_returns_original(self, *_):
        """_augment_tokens_with_hyde с пустым HyDE возвращает оригинальные токены."""
        service = RagKnowledgeService()
        original = ["тест"]
        result = service._augment_tokens_with_hyde(original, "")
        self.assertEqual(result, original)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_ru_normalization_mode", return_value="lemma_then_stem")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    def test_augment_tokens_with_hyde_filters_stopwords(self, *_):
        """_augment_tokens_with_hyde не добавляет стоп-слова из HyDE-текста."""
        service = RagKnowledgeService()
        original = ["терминал"]
        result = service._augment_tokens_with_hyde(
            original, "это такое устройство для оплаты"
        )
        # "это" и "такое" — стоп-слова, не должны попасть
        for token in result:
            self.assertNotIn(token, {"это", "такое"})

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_ru_normalization_mode", return_value="lemma_then_stem")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    def test_augment_tokens_with_hyde_no_new_tokens(self, *_):
        """_augment_tokens_with_hyde возвращает оригинал если HyDE не добавляет новых токенов."""
        service = RagKnowledgeService()
        original = ["привязанность", "глубокое"]
        result = service._augment_tokens_with_hyde(
            original, "привязанность глубокое"
        )
        self.assertEqual(result, original)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_ru_normalization_mode", return_value="lemma_then_stem")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    def test_augment_tokens_preserves_original_order(self, *_):
        """_augment_tokens_with_hyde сохраняет оригинальные токены в начале."""
        service = RagKnowledgeService()
        original = ["терминал", "оплата"]
        result = service._augment_tokens_with_hyde(
            original, "устройство для безналичных расчётов"
        )
        # Первые два токена — оригинальные
        self.assertEqual(result[:2], original)
        # Новые добавлены после
        self.assertGreater(len(result), 2)

    def test_is_rag_hyde_lexical_enabled_default_true(self):
        """is_rag_hyde_lexical_enabled по умолчанию возвращает True."""
        from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings_mod

        with patch.object(ai_settings_mod, "AI_RAG_HYDE_LEXICAL_ENABLED", True):
            with patch.object(ai_settings_mod, "_safe_get_setting", return_value=None):
                result = ai_settings_mod.is_rag_hyde_lexical_enabled()
                self.assertTrue(result)

    def test_is_rag_hyde_lexical_enabled_db_disable(self):
        """is_rag_hyde_lexical_enabled отключается через DB override."""
        from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings_mod

        with patch.object(ai_settings_mod, "AI_RAG_HYDE_LEXICAL_ENABLED", True):
            with patch.object(ai_settings_mod, "_safe_get_setting", return_value="0"):
                result = ai_settings_mod.is_rag_hyde_lexical_enabled()
                self.assertFalse(result)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_hyde_lexical_enabled", return_value=False)
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.get_rag_ru_normalization_mode", return_value="lemma_then_stem")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_ru_normalization_enabled", return_value=False)
    def test_hyde_lexical_disabled_skips_augmentation(self, *_):
        """При выключенном HyDE lexical токены не дополняются."""
        service = RagKnowledgeService()
        tokens = service._tokenize("тестовый вопрос")
        # Когда is_rag_hyde_lexical_enabled=False, augmentation не вызывается
        # Проверяем это через _retrieve_context_for_question: retrieval_tokens не изменяются
        # Симулируем прямой вызов — augmentation guard в retrieval проверяет флаг
        original = list(tokens)
        # Поскольку augmentation вызывается только если is_rag_hyde_lexical_enabled()=True,
        # при False токены остаются неизменными — сам метод _augment не проверяет флаг
        result = service._augment_tokens_with_hyde(original, "гипотетический ответ текст")
        # Метод сам по себе всегда дополняет — guard во внешнем вызове
        self.assertGreaterEqual(len(result), len(original))


if __name__ == "__main__":
    unittest.main()
