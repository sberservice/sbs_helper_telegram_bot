"""
test_intent_handlers.py — тесты для обработчиков намерений AI-маршрутизации.
"""
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

from src.sbs_helper_telegram_bot.ai_router.intent_handlers import (
    HandlerExecutionResult,
    RagQaHandler,
    UposErrorHandler,
    TicketValidatorHandler,
    KtrHandler,
    CertificationHandler,
    NewsHandler,
    get_all_handlers,
)
from src.sbs_helper_telegram_bot.ai_router.rag_service import RagAnswer


class TestHandlerProperties(unittest.TestCase):
    """Тесты свойств обработчиков."""

    def test_upos_handler_properties(self):
        """Свойства UposErrorHandler."""
        h = UposErrorHandler()
        self.assertEqual(h.intent_name, "upos_error_lookup")
        self.assertEqual(h.module_key, "upos_errors")

    def test_rag_handler_properties(self):
        """Свойства RagQaHandler."""
        h = RagQaHandler()
        self.assertEqual(h.intent_name, "rag_qa")
        self.assertEqual(h.module_key, "ai_router")

    def test_ticket_handler_properties(self):
        """Свойства TicketValidatorHandler."""
        h = TicketValidatorHandler()
        self.assertEqual(h.intent_name, "ticket_soos")
        self.assertEqual(h.module_key, "soos")

    def test_ktr_handler_properties(self):
        """Свойства KtrHandler."""
        h = KtrHandler()
        self.assertEqual(h.intent_name, "ktr_lookup")
        self.assertEqual(h.module_key, "ktr")

    def test_certification_handler_properties(self):
        """Свойства CertificationHandler."""
        h = CertificationHandler()
        self.assertEqual(h.intent_name, "certification_info")
        self.assertEqual(h.module_key, "certification")

    def test_news_handler_properties(self):
        """Свойства NewsHandler."""
        h = NewsHandler()
        self.assertEqual(h.intent_name, "news_search")
        self.assertEqual(h.module_key, "news")

    def test_get_all_handlers_returns_six(self):
        """get_all_handlers возвращает 6 обработчиков."""
        handlers = get_all_handlers()
        self.assertEqual(len(handlers), 6)
        intent_names = {h.intent_name for h in handlers}
        self.assertEqual(intent_names, {
            "rag_qa",
            "upos_error_lookup",
            "ticket_soos",
            "ktr_lookup",
            "certification_info",
            "news_search",
        })

    def test_all_handlers_have_unique_intents(self):
        """Все обработчики имеют уникальные intent_name."""
        handlers = get_all_handlers()
        intents = [h.intent_name for h in handlers]
        self.assertEqual(len(intents), len(set(intents)))


class TestUposErrorHandler(unittest.IsolatedAsyncioTestCase):
    """Тесты исполнения UposErrorHandler."""

    @patch(
        "src.sbs_helper_telegram_bot.ai_router.intent_handlers."
        "UposErrorHandler.execute"
    )
    async def test_execute_called(self, mock_execute):
        """execute вызывается с параметрами."""
        mock_execute.return_value = "✅ Код найден"
        h = UposErrorHandler()
        result = await h.execute({"error_code": "1001"}, user_id=123)
        mock_execute.assert_called_once()

    async def test_empty_error_code(self):
        """Пустой код ошибки возвращает предупреждение."""
        h = UposErrorHandler()
        # Мокаем импорты, используемые внутри execute
        with patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.get_error_code_by_code"
        ), patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.record_error_request"
        ), patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.record_unknown_code"
        ):
            result = await h.execute({"error_code": ""}, user_id=123)
            self.assertIn("Не указан код ошибки", result)

    async def test_error_code_found(self):
        """Успешный поиск кода ошибки."""
        mock_result = {
            "error_code": "E001",
            "description": "Тестовая ошибка",
            "suggested_actions": "Перезагрузите",
            "category_name": "Критические",
            "updated_timestamp": None,
        }
        with patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.get_error_code_by_code",
            return_value=mock_result,
        ), patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.record_error_request"
        ) as mock_record, patch(
            "src.sbs_helper_telegram_bot.upos_error.messages.format_error_code_response",
            return_value="✅ E001: Тестовая ошибка",
        ):
            h = UposErrorHandler()
            result = await h.execute({"error_code": "E001"}, user_id=55)
            mock_record.assert_called_once_with(55, "E001", found=True)
            self.assertIn("E001", result)

    async def test_error_code_not_found(self):
        """Код ошибки не найден в базе."""
        with patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.get_error_code_by_code",
            return_value=None,
        ), patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.record_error_request"
        ) as mock_record, patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.record_unknown_code"
        ):
            h = UposErrorHandler()
            result = await h.execute({"error_code": "UNKNOWN"}, user_id=55)
            mock_record.assert_called_once_with(55, "UNKNOWN", found=False)
            self.assertIsInstance(result, HandlerExecutionResult)
            self.assertIn("не найден", result.response)
            self.assertTrue((result.meta or {}).get("upos_not_found"))

    async def test_error_code_trimmed_with_invisible_chars(self):
        """UPOS-код очищается от пробелов и невидимых символов по краям."""
        raw_code = "\u200b\t\n E001 \u00a0\ufeff"
        with patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.get_error_code_by_code",
            return_value=None,
        ) as mock_get, patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.record_error_request"
        ), patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.record_unknown_code"
        ):
            h = UposErrorHandler()
            await h.execute({"error_code": raw_code}, user_id=77)
            mock_get.assert_called_once_with("E001")

    async def test_error_code_none_returns_warning(self):
        """None в error_code приводит к сообщению о пустом коде."""
        with patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.get_error_code_by_code"
        ), patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.record_error_request"
        ), patch(
            "src.sbs_helper_telegram_bot.upos_error.upos_error_bot_part.record_unknown_code"
        ):
            h = UposErrorHandler()
            result = await h.execute({"error_code": None}, user_id=123)
            self.assertIn("Не указан код ошибки", result)


class TestRagQaHandler(unittest.IsolatedAsyncioTestCase):
    """Тесты исполнения RagQaHandler."""

    @patch("src.sbs_helper_telegram_bot.ai_router.settings.AI_RAG_ENABLED", False)
    async def test_rag_disabled(self):
        """При выключенном RAG возвращается сообщение о недоступности."""
        handler = RagQaHandler()
        result = await handler.execute({"question": "Что в регламенте?"}, user_id=1)
        self.assertIn("временно отключён", result)

    async def test_empty_question(self):
        """Пустой вопрос возвращает подсказку пользователю."""
        handler = RagQaHandler()
        result = await handler.execute({"question": "   "}, user_id=1)
        self.assertIn("Уточните вопрос", result)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.get_rag_service")
    async def test_answer_from_rag(self, mock_get_rag_service):
        """Успешный ответ RAG форматируется и возвращается пользователю."""
        mock_service = AsyncMock()
        mock_service.answer_question.return_value = RagAnswer(text="Ответ из базы знаний")
        mock_get_rag_service.return_value = mock_service

        handler = RagQaHandler()
        result = await handler.execute({"question": "Какой SLA?"}, user_id=22)

        self.assertIn("Ответ по базе знаний", result)
        self.assertIn("Ответ из базы знаний", result)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.get_rag_service")
    async def test_answer_from_rag_passes_category_hint(self, mock_get_rag_service):
        """Опциональный category_hint из параметров передаётся в RAG-сервис."""
        mock_service = AsyncMock()
        mock_service.answer_question.return_value = RagAnswer(text="Ответ из базы знаний")
        mock_get_rag_service.return_value = mock_service

        handler = RagQaHandler()
        await handler.execute(
            {
                "question": "Вопрос по аттестации",
                "category_hint": "upos ошибки",
            },
            user_id=22,
        )

        mock_service.answer_question.assert_awaited_once_with(
            "Вопрос по аттестации",
            user_id=22,
            on_progress=None,
            category_hint="upos ошибки",
        )

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.get_rag_service")
    async def test_answer_from_rag_preserves_supported_markdown(self, mock_get_rag_service):
        """RAG-ответ сохраняет поддерживаемый markdown и экранирует остальное."""
        mock_service = AsyncMock()
        mock_service.answer_question.return_value = RagAnswer(text=(
            "1. **Важно**\n"
            "Команда: `echo ok`\n"
            "Ссылка [x](https://example.com)"
        ))
        mock_get_rag_service.return_value = mock_service

        handler = RagQaHandler()
        result = await handler.execute({"question": "Покажи формат"}, user_id=22)

        self.assertIn("*Важно*", result)
        self.assertIn("`echo ok`", result)
        self.assertIn("\\[x\\]\\(https://example\\.com\\)", result)

    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.get_rag_service")
    async def test_not_found_in_rag(self, mock_get_rag_service):
        """Если релевантных чанков нет — возвращается корректный fallback."""
        mock_service = AsyncMock()
        mock_service.answer_question.return_value = RagAnswer(text=None)
        mock_get_rag_service.return_value = mock_service

        handler = RagQaHandler()
        result = await handler.execute({"question": "Неизвестный вопрос"}, user_id=22)
        self.assertIn("не найден точный ответ", result)

    @patch("src.sbs_helper_telegram_bot.ai_router.intent_handlers.logger.exception")
    @patch("src.sbs_helper_telegram_bot.ai_router.rag_service.get_rag_service")
    async def test_rag_exception_with_empty_message_logs_type(
        self,
        mock_get_rag_service,
        mock_logger_exception,
    ):
        """При пустом тексте исключения в логе сохраняется тип ошибки."""
        mock_service = AsyncMock()
        empty_exc = Exception()
        mock_service.answer_question.side_effect = empty_exc
        mock_get_rag_service.return_value = mock_service

        handler = RagQaHandler()
        result = await handler.execute({"question": "Какой SLA?"}, user_id=22)

        self.assertIn("Не удалось получить ответ", result)
        mock_logger_exception.assert_called_once()
        log_args = mock_logger_exception.call_args.args
        self.assertIn("Ошибка RAG-обработчика", log_args[0])
        self.assertEqual(log_args[2], "Exception")
        self.assertIs(log_args[3], empty_exc)


class TestKtrHandler(unittest.IsolatedAsyncioTestCase):
    """Тесты исполнения KtrHandler."""

    async def test_empty_ktr_code(self):
        """Пустой код КТР возвращает предупреждение."""
        with patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.get_ktr_code_by_code"
        ), patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.record_ktr_request"
        ):
            h = KtrHandler()
            result = await h.execute({"ktr_code": ""}, user_id=123)
            self.assertIn("Не указан код КТР", result)

    async def test_ktr_code_found(self):
        """Успешный поиск кода КТР."""
        mock_result = {
            "code": "K001",
            "description": "Тестовый код",
            "minutes": 30,
            "category_name": "Ремонт",
            "updated_timestamp": None,
            "date_updated": None,
        }
        with patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.get_ktr_code_by_code",
            return_value=mock_result,
        ), patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.record_ktr_request"
        ), patch(
            "src.sbs_helper_telegram_bot.ktr.messages.format_ktr_code_response",
            return_value="⏱️ K001: Тестовый код",
        ):
            h = KtrHandler()
            result = await h.execute({"ktr_code": "k001"}, user_id=55)
            self.assertIn("K001", result)

    async def test_ktr_code_uppercased(self):
        """Код КТР преобразуется в верхний регистр."""
        with patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.get_ktr_code_by_code",
            return_value=None,
        ) as mock_get, patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.record_ktr_request"
        ):
            h = KtrHandler()
            await h.execute({"ktr_code": "abc"}, user_id=1)
            mock_get.assert_called_with("ABC")

    async def test_ktr_code_trimmed_with_invisible_chars(self):
        """Код КТР очищается от пробелов и невидимых символов по краям."""
        raw_code = "\ufeff\u200b\n k001 \u00a0\t"
        with patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.get_ktr_code_by_code",
            return_value=None,
        ) as mock_get, patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.record_ktr_request"
        ):
            h = KtrHandler()
            await h.execute({"ktr_code": raw_code}, user_id=1)
            mock_get.assert_called_once_with("K001")

    async def test_ktr_code_none_returns_warning(self):
        """None в ktr_code приводит к сообщению о пустом коде."""
        with patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.get_ktr_code_by_code"
        ), patch(
            "src.sbs_helper_telegram_bot.ktr.ktr_bot_part.record_ktr_request"
        ):
            h = KtrHandler()
            result = await h.execute({"ktr_code": None}, user_id=1)
            self.assertIn("Не указан код КТР", result)


class TestCertificationHandler(unittest.IsolatedAsyncioTestCase):
    """Тесты CertificationHandler."""

    async def test_summary_query_type(self):
        """Запрос типа summary вызывает _format_summary."""
        mock_summary = {
            "rank_icon": "🔰",
            "rank_name": "Новичок",
            "certification_points": 0,
            "max_achievable_points": 100,
            "overall_progress_percent": 0,
            "overall_progress_bar": "░░░░░░░░░░",
            "passed_tests_count": 0,
        }
        mock_logic = MagicMock()
        mock_logic.get_user_certification_summary = MagicMock(return_value=mock_summary)
        mock_logic.get_certification_statistics = MagicMock()
        mock_logic.get_all_categories = MagicMock()
        with patch.dict("sys.modules", {
            "src.sbs_helper_telegram_bot.certification": MagicMock(),
            "src.sbs_helper_telegram_bot.certification.certification_logic": mock_logic,
        }):
            h = CertificationHandler()
            result = await h.execute({"query_type": "summary"}, user_id=123)
            self.assertIn("профиль аттестации", result)

    async def test_stats_query_type(self):
        """Запрос типа stats возвращает статистику."""
        mock_stats = {
            "total_questions": 150,
            "total_categories": 5,
            "active_categories": 3,
        }
        mock_logic = MagicMock()
        mock_logic.get_certification_statistics = MagicMock(return_value=mock_stats)
        with patch.dict("sys.modules", {
            "src.sbs_helper_telegram_bot.certification": MagicMock(),
            "src.sbs_helper_telegram_bot.certification.certification_logic": mock_logic,
        }):
            h = CertificationHandler()
            result = await h.execute({"query_type": "stats"}, user_id=123)
            self.assertIn("Статистика аттестации", result)
            self.assertIn("150", result)

    async def test_categories_query_type(self):
        """Запрос типа categories возвращает список категорий."""
        mock_cats = [
            {"name": "Категория A", "questions_count": 20},
            {"name": "Категория B", "questions_count": 15},
        ]
        mock_logic = MagicMock()
        mock_logic.get_all_categories = MagicMock(return_value=mock_cats)
        with patch.dict("sys.modules", {
            "src.sbs_helper_telegram_bot.certification": MagicMock(),
            "src.sbs_helper_telegram_bot.certification.certification_logic": mock_logic,
        }):
            h = CertificationHandler()
            result = await h.execute({"query_type": "categories"}, user_id=123)
            self.assertIn("Категории аттестации", result)


class TestNewsHandler(unittest.IsolatedAsyncioTestCase):
    """Тесты NewsHandler."""

    async def test_search_no_results(self):
        """Поиск новостей без результатов."""
        with patch(
            "src.sbs_helper_telegram_bot.news.news_logic.search_news",
            return_value=([], 0),
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_published_news"
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_unread_count"
        ):
            h = NewsHandler()
            result = await h.execute({"search_query": "несуществующее"}, user_id=1)
            self.assertIn("не найдено", result)

    async def test_search_with_results(self):
        """Поиск новостей с результатами."""
        mock_articles = [
            {
                "title": "Новость 1",
                "category_emoji": "📰",
                "published_timestamp": 1700000000,
                "content": "Содержание новости",
            }
        ]
        with patch(
            "src.sbs_helper_telegram_bot.news.news_logic.search_news",
            return_value=(mock_articles, 1),
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_published_news"
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_unread_count"
        ):
            h = NewsHandler()
            result = await h.execute({"search_query": "новость"}, user_id=1)
            self.assertIn("Результаты поиска", result)

    async def test_search_results_header_has_escaped_parens(self):
        """Заголовок результатов поиска содержит экранированные скобки."""
        mock_articles = [
            {
                "title": "Тест",
                "category_emoji": "📰",
                "published_timestamp": 1700000000,
                "content": "Текст",
            }
        ]
        with patch(
            "src.sbs_helper_telegram_bot.news.news_logic.search_news",
            return_value=(mock_articles, 5),
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_published_news"
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_unread_count"
        ):
            h = NewsHandler()
            result = await h.execute({"search_query": "тест"}, user_id=1)
            self.assertIn("\\(5\\)", result)
            self.assertNotIn("(5)", result.replace("\\(5\\)", ""))

    async def test_latest_news_header_has_escaped_parens(self):
        """Заголовок последних новостей содержит экранированные скобки."""
        mock_articles = [
            {
                "title": "Новость",
                "category_emoji": "📰",
                "published_timestamp": 1700000000,
                "content": "Текст новости",
            }
        ]
        with patch(
            "src.sbs_helper_telegram_bot.news.news_logic.search_news"
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_published_news",
            return_value=(mock_articles, 3),
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_unread_count",
            return_value=0,
        ):
            h = NewsHandler()
            result = await h.execute({}, user_id=1)
            self.assertIn("\\(3\\)", result)
            self.assertNotIn("(3)", result.replace("\\(3\\)", ""))

    async def test_latest_news_with_unread_count(self):
        """Непрочитанные новости отображаются с экранированными скобками."""
        mock_articles = [
            {
                "title": "Новость",
                "category_emoji": "📰",
                "published_timestamp": 1700000000,
                "content": "Текст",
            }
        ]
        with patch(
            "src.sbs_helper_telegram_bot.news.news_logic.search_news"
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_published_news",
            return_value=(mock_articles, 2),
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_unread_count",
            return_value=5,
        ):
            h = NewsHandler()
            result = await h.execute({}, user_id=1)
            self.assertIn("\\(2\\)", result)
            self.assertIn("Непрочитанных: 5", result)

    async def test_latest_news_empty(self):
        """Нет новостей — соответствующее сообщение."""
        with patch(
            "src.sbs_helper_telegram_bot.news.news_logic.search_news"
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_published_news",
            return_value=([], 0),
        ), patch(
            "src.sbs_helper_telegram_bot.news.news_logic.get_unread_count",
            return_value=0,
        ):
            h = NewsHandler()
            result = await h.execute({}, user_id=1)
            self.assertIn("Новостей пока нет", result)

    async def test_format_articles_no_unescaped_special_chars(self):
        """_format_articles не содержит неэкранированных спецсимволов MarkdownV2 в заголовке."""
        import re
        articles = [
            {
                "title": "Test (title)",
                "category_emoji": "📰",
                "published_timestamp": 1700000000,
                "content": "Line one. Line two.",
            }
        ]
        result = NewsHandler._format_articles(articles, "📰 Новости \\(3\\)")
        # Проверяем, что в результате нет неэкранированных скобок
        # (все ( и ) должны быть предварены \)
        unescaped_parens = re.findall(r'(?<!\\)[()]', result)
        self.assertEqual(unescaped_parens, [], f"Неэкранированные скобки в результате: {result}")


class TestTicketValidatorHandler(unittest.IsolatedAsyncioTestCase):
    """Тесты TicketValidatorHandler (маршрутизация в СООС)."""

    async def test_empty_ticket_text(self):
        """Пустой текст заявки возвращает предупреждение."""
        h = TicketValidatorHandler()
        result = await h.execute({"ticket_text": ""}, user_id=123)
        self.assertIn("Не указан текст тикета", result)

    async def test_active_soos_job_returns_warning(self):
        """Если есть активная задача СООС, handler возвращает предупреждение."""
        with patch(
            "src.sbs_helper_telegram_bot.soos.soos_bot_part.check_if_user_has_unprocessed_job",
            return_value=True,
        ):
            h = TicketValidatorHandler()
            result = await h.execute({"ticket_text": "Текст заявки"}, user_id=1)
            self.assertIn("активная задача СООС", result)

    async def test_missing_fields_returns_details(self):
        """При отсутствии обязательных полей возвращается список недостающих полей."""
        with patch(
            "src.sbs_helper_telegram_bot.soos.soos_bot_part.check_if_user_has_unprocessed_job",
            return_value=False,
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_parser.extract_ticket_fields",
            return_value={},
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_parser.get_missing_required_fields",
            return_value=["TID", "merchant/MID"],
        ):
            h = TicketValidatorHandler()
            result = await h.execute({"ticket_text": "Текст заявки"}, user_id=1)
            self.assertIn("Не удалось извлечь обязательные поля", result)
            self.assertIn("TID", result)

    async def test_success_enqueue_to_soos(self):
        """Валидный тикет ставится в очередь СООС и возвращает позицию."""
        with patch(
            "src.sbs_helper_telegram_bot.soos.soos_bot_part.check_if_user_has_unprocessed_job",
            return_value=False,
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_parser.extract_ticket_fields",
            return_value={"tid": "12345678", "phone": "+79991234567"},
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_parser.get_missing_required_fields",
            return_value=[],
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_bot_part.get_number_of_jobs_in_the_queue",
            return_value=2,
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_bot_part.add_to_soos_queue"
        ) as mock_add, patch(
            "src.sbs_helper_telegram_bot.ai_router.intent_handlers.time.time",
            return_value=1700000000,
        ):
            h = TicketValidatorHandler()
            result = await h.execute({"ticket_text": "произвольный текст"}, user_id=1)
            self.assertIn("Позиция в очереди", result)
            self.assertIn("3", result)
            mock_add.assert_called_once_with(1, "произвольный текст", "soos_1_1700000000.png")

    async def test_exception_handling(self):
        """Ошибка внутри handler возвращает сообщение об ошибке."""
        with patch(
            "src.sbs_helper_telegram_bot.soos.soos_bot_part.check_if_user_has_unprocessed_job",
            return_value=False,
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_parser.extract_ticket_fields",
            return_value={"tid": "123"},
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_parser.get_missing_required_fields",
            return_value=[],
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_bot_part.get_number_of_jobs_in_the_queue",
            return_value=0,
        ), patch(
            "src.sbs_helper_telegram_bot.soos.soos_bot_part.add_to_soos_queue",
            side_effect=Exception("DB error"),
        ):
            h = TicketValidatorHandler()
            result = await h.execute({"ticket_text": "Текст заявки"}, user_id=1)
            self.assertIn("Ошибка при постановке тикета в СООС", result)


if __name__ == "__main__":
    unittest.main()
