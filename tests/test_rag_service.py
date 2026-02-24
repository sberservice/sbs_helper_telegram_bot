"""
test_rag_service.py — тесты сервиса RAG базы знаний.
"""

import builtins
import unittest
from unittest.mock import AsyncMock, patch

from src.sbs_helper_telegram_bot.ai_router.rag_service import RagKnowledgeService


class TestRagKnowledgeService(unittest.IsolatedAsyncioTestCase):
    """Тесты RagKnowledgeService."""

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

    def test_split_html_payload_uses_header_splitter_when_available(self):
        """HTML-чанкинг использует результат header-splitter, если он вернул чанки."""
        service = RagKnowledgeService()
        html = b"<html><body><h1>SLA</h1><p>4 hours</p></body></html>"

        with patch.object(service, "_split_html_with_header_splitter", return_value=["SLA\n4 hours"]) as mock_splitter:
            with patch.object(service, "_extract_html_text") as mock_extract:
                chunks = service._split_html_payload(html)

        self.assertEqual(chunks, ["SLA\n4 hours"])
        mock_splitter.assert_called_once()
        mock_extract.assert_not_called()

    def test_split_html_payload_falls_back_when_header_splitter_empty(self):
        """При пустом результате header-splitter включается fallback по очищенному тексту."""
        service = RagKnowledgeService()
        html = b"<html><body><h1>SLA</h1><p>4 hours</p></body></html>"

        with patch.object(service, "_split_html_with_header_splitter", return_value=[]):
            with patch.object(service, "_extract_html_text", return_value="SLA 4 hours") as mock_extract:
                with patch.object(service, "_split_text", return_value=["SLA 4 hours"]) as mock_split_text:
                    chunks = service._split_html_payload(html)

        self.assertEqual(chunks, ["SLA 4 hours"])
        mock_extract.assert_called_once()
        mock_split_text.assert_called_once_with("SLA 4 hours")

    def test_split_html_payload_skips_header_splitter_when_disabled_in_settings(self):
        """При выключенном флаге HTML splitter используется только fallback path."""
        service = RagKnowledgeService()
        html = b"<html><body><h1>SLA</h1><p>4 hours</p></body></html>"

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_service.ai_settings.is_rag_html_splitter_enabled", return_value=False):
            with patch.object(service, "_split_html_with_header_splitter") as mock_header_splitter:
                with patch.object(service, "_extract_html_text", return_value="SLA 4 hours") as mock_extract:
                    with patch.object(service, "_split_text", return_value=["SLA 4 hours"]) as mock_split_text:
                        chunks = service._split_html_payload(html)

        self.assertEqual(chunks, ["SLA 4 hours"])
        mock_header_splitter.assert_not_called()
        mock_extract.assert_called_once()
        mock_split_text.assert_called_once_with("SLA 4 hours")

    def test_split_html_with_header_splitter_flattens_headers_into_chunks(self):
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

        with patch.object(service, "_get_html_header_splitter_class", return_value=FakeSplitter):
            with patch.object(service, "_split_text", return_value=["SLA\nКритический\nПодробные условия"]) as mock_split_text:
                chunks = service._split_html_with_header_splitter("<h1>SLA</h1><h2>Критический</h2><p>Подробные условия</p>")

        self.assertEqual(chunks, ["SLA\nКритический\nПодробные условия"])
        mock_split_text.assert_called_once_with("SLA\nКритический\nПодробные условия")

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_search_relevant_chunks_scoring(self, mock_get_cursor, mock_get_db_connection):
        """Retrieval возвращает наиболее релевантный чанк."""
        service = RagKnowledgeService()

        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {"chunk_text": "SLA выезда 4 часа при критическом инциденте", "filename": "reglament.txt"},
            {"chunk_text": "Нерелевантный текст про отпуск", "filename": "other.txt"},
        ]

        result = service._search_relevant_chunks("Какой SLA выезда?", limit=1)
        self.assertEqual(len(result), 1)
        self.assertIn("SLA", result[0][2])

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

    @patch("src.common.database.get_db_connection")
    @patch("src.common.database.get_cursor")
    def test_prefilter_documents_by_summary(self, mock_get_cursor, mock_get_db_connection):
        """Prefilter по summary выбирает документы с максимальной релевантностью."""
        service = RagKnowledgeService()
        cursor = mock_get_cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            {"document_id": 1, "summary_text": "SLA выезда 4 часа и эскалация", "filename": "sla.txt"},
            {"document_id": 2, "summary_text": "Отпуск и график", "filename": "hr.txt"},
        ]

        rows = service._prefilter_documents_by_summary(
            question_tokens=service._tokenize("Какой SLA выезда"),
            limit=2,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][1], "sla.txt")

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


if __name__ == "__main__":
    unittest.main()
