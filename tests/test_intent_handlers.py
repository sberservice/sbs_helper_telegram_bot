"""
test_intent_handlers.py — тесты для обработчиков намерений AI-маршрутизации.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, AsyncMock

from src.sbs_helper_telegram_bot.ai_router.intent_handlers import (
    UposErrorHandler,
    TicketValidatorHandler,
    KtrHandler,
    CertificationHandler,
    NewsHandler,
    get_all_handlers,
)


class TestHandlerProperties(unittest.TestCase):
    """Тесты свойств обработчиков."""

    def test_upos_handler_properties(self):
        """Свойства UposErrorHandler."""
        h = UposErrorHandler()
        self.assertEqual(h.intent_name, "upos_error_lookup")
        self.assertEqual(h.module_key, "upos_errors")

    def test_ticket_handler_properties(self):
        """Свойства TicketValidatorHandler."""
        h = TicketValidatorHandler()
        self.assertEqual(h.intent_name, "ticket_validation")
        self.assertEqual(h.module_key, "ticket_validator")

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

    def test_get_all_handlers_returns_five(self):
        """get_all_handlers возвращает 5 обработчиков."""
        handlers = get_all_handlers()
        self.assertEqual(len(handlers), 5)
        intent_names = {h.intent_name for h in handlers}
        self.assertEqual(intent_names, {
            "upos_error_lookup",
            "ticket_validation",
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
            self.assertIn("не найден", result)


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
    """Тесты TicketValidatorHandler."""

    async def test_empty_ticket_text(self):
        """Пустой текст заявки возвращает предупреждение."""
        h = TicketValidatorHandler()
        result = await h.execute({"ticket_text": ""}, user_id=123)
        self.assertIn("Не указан текст заявки", result)

    async def test_exception_handling(self):
        """Ошибка внутри handler возвращает сообщение об ошибке."""
        with patch(
            "src.sbs_helper_telegram_bot.ticket_validator.validation_rules.load_all_ticket_types",
            side_effect=Exception("DB error"),
        ):
            h = TicketValidatorHandler()
            result = await h.execute({"ticket_text": "Текст заявки"}, user_id=1)
            self.assertIn("Ошибка", result)

    async def test_undefined_type_uses_type_name_without_attribute_error(self):
        """Список типов формируется через type_name без обращения к несуществующему name."""
        from src.sbs_helper_telegram_bot.ticket_validator.validators import TicketType

        ticket_types = [
            TicketType(
                id=1,
                type_name="Установка",
                description="",
                detection_keywords=["установка"],
                active=True,
            ),
            TicketType(
                id=2,
                type_name="Ремонт",
                description="",
                detection_keywords=["ремонт"],
                active=True,
            ),
        ]

        with patch(
            "src.sbs_helper_telegram_bot.ticket_validator.validation_rules.load_all_ticket_types",
            return_value=ticket_types,
        ), patch(
            "src.sbs_helper_telegram_bot.ticket_validator.validators.detect_ticket_type",
            return_value=(None, None),
        ):
            h = TicketValidatorHandler()
            result = await h.execute({"ticket_text": "произвольный текст"}, user_id=1)
            self.assertIn("Тип заявки не определён", result)
            self.assertIn("Установка", result)
            self.assertIn("Ремонт", result)

    async def test_format_result_uses_type_name(self):
        """Результат валидации отображает type_name у найденного типа заявки."""
        from src.sbs_helper_telegram_bot.ticket_validator.validators import TicketType

        detected_type = TicketType(
            id=3,
            type_name="Техническое обслуживание",
            description="",
            detection_keywords=["обслуживание"],
            active=True,
        )
        validation_result = SimpleNamespace(is_valid=True, error_messages=[])

        with patch(
            "src.sbs_helper_telegram_bot.ticket_validator.validation_rules.load_all_ticket_types",
            return_value=[detected_type],
        ), patch(
            "src.sbs_helper_telegram_bot.ticket_validator.validators.detect_ticket_type",
            return_value=(detected_type, None),
        ), patch(
            "src.sbs_helper_telegram_bot.ticket_validator.validation_rules.load_rules_from_db",
            return_value=[],
        ), patch(
            "src.sbs_helper_telegram_bot.ticket_validator.validators.validate_ticket",
            return_value=validation_result,
        ):
            h = TicketValidatorHandler()
            result = await h.execute({"ticket_text": "текст заявки"}, user_id=1)
            self.assertIn("Тип заявки", result)
            self.assertIn("Техническое обслуживание", result)


if __name__ == "__main__":
    unittest.main()
