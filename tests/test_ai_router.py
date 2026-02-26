"""
test_ai_router.py — тесты для IntentRouter AI-маршрутизации.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.sbs_helper_telegram_bot.ai_router.circuit_breaker import CircuitBreaker
from src.sbs_helper_telegram_bot.ai_router.context_manager import ConversationContextManager
from src.sbs_helper_telegram_bot.ai_router.intent_router import (
    IntentRouter,
    get_router,
    reset_router,
)
from src.sbs_helper_telegram_bot.ai_router.llm_provider import (
    ClassificationResult,
)
from src.sbs_helper_telegram_bot.ai_router.messages import (
    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED,
    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED,
)
from src.sbs_helper_telegram_bot.ai_router.rate_limiter import AIRateLimiter


def _make_router(
    provider=None,
    rate_limiter=None,
    circuit_breaker=None,
    context_manager=None,
):
    """Создать роутер с мок-зависимостями."""
    return IntentRouter(
        provider=provider or AsyncMock(),
        rate_limiter=rate_limiter or AIRateLimiter(max_requests=100, window_seconds=60),
        circuit_breaker=circuit_breaker or CircuitBreaker(failure_threshold=10),
        context_manager=context_manager or ConversationContextManager(),
    )


class TestIntentRouterDisabled(unittest.IsolatedAsyncioTestCase):
    """Тесты: AI-модуль выключен."""

    @patch("src.common.bot_settings.is_module_enabled", return_value=False)
    async def test_disabled_returns_none(self, mock_enabled):
        """Когда AI-модуль выключен, возвращает (None, 'disabled')."""
        router = _make_router()
        result, status = await router.route("test", user_id=1)
        self.assertIsNone(result)
        self.assertEqual(status, "disabled")


class TestIntentRouterRateLimit(unittest.IsolatedAsyncioTestCase):
    """Тесты: rate-limiting."""

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    async def test_rate_limited(self, mock_enabled):
        """Пользователь превысил лимит запросов."""
        limiter = AIRateLimiter(max_requests=1, window_seconds=60)
        limiter.record(1)  # Записываем 1 запрос (лимит исчерпан)

        router = _make_router(rate_limiter=limiter)
        result, status = await router.route("test", user_id=1)
        self.assertIsNotNone(result)
        self.assertEqual(status, "rate_limited")
        self.assertIn("Слишком много запросов", result)


class TestIntentRouterCircuitBreaker(unittest.IsolatedAsyncioTestCase):
    """Тесты: circuit breaker."""

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    async def test_circuit_open(self, mock_enabled):
        """Circuit breaker открыт — возвращает circuit_open."""
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=300)
        cb.record_failure()  # Открываем circuit

        router = _make_router(circuit_breaker=cb)
        result, status = await router.route("test", user_id=1)
        self.assertIsNone(result)
        self.assertEqual(status, "circuit_open")


class TestIntentRouterClassification(unittest.IsolatedAsyncioTestCase):
    """Тесты: классификация и маршрутизация."""

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["upos_errors", "ktr"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_routed_to_handler(self, mock_log, mock_modules, mock_enabled):
        """Успешная маршрутизация к обработчику."""
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="upos_error_lookup",
            confidence=0.95,
            parameters={"error_code": "E001"},
            explain_code="UPOS_EXACT",
        )

        router = _make_router(provider=provider)

        # Мокаем обработчик
        mock_handler = AsyncMock()
        mock_handler.intent_name = "upos_error_lookup"
        mock_handler.module_key = "upos_errors"
        mock_handler.execute.return_value = "✅ Код найден"
        router._handlers["upos_error_lookup"] = mock_handler

        result, status = await router.route("ошибка E001", user_id=1)
        self.assertEqual(status, "routed")
        self.assertEqual(result, "✅ Код найден")
        mock_handler.execute.assert_awaited_once()

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["ai_router"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_rag_qa_uses_original_text_when_question_missing(self, mock_log, mock_modules, mock_enabled):
        """Для intent=rag_qa вопрос берётся из original_text, если parameters.question пустой."""
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="rag_qa",
            confidence=0.95,
            parameters={},
            explain_code="RAG_QA",
        )

        router = _make_router(provider=provider)
        rag_handler = AsyncMock()
        rag_handler.intent_name = "rag_qa"
        rag_handler.module_key = "ai_router"
        rag_handler.execute.return_value = "📚 *Ответ по базе знаний*\n\nТест"
        router._handlers["rag_qa"] = rag_handler

        result, status = await router.route("Прошивка d200 с флешки", user_id=2)

        self.assertEqual(status, "routed")
        self.assertIn("Ответ по базе знаний", result)
        rag_handler.execute.assert_awaited_once_with(
            {"question": "Прошивка d200 с флешки"},
            2,
        )

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["soos"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_ticket_soos_uses_original_text_when_ticket_text_missing(
        self,
        mock_log,
        mock_modules,
        mock_enabled,
    ):
        """Для intent=ticket_soos берётся original_text, если parameters.ticket_text пустой."""
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="ticket_soos",
            confidence=0.95,
            parameters={},
            explain_code="SOOS_TICKET_MULTILINE",
        )

        router = _make_router(provider=provider)
        ticket_handler = AsyncMock()
        ticket_handler.intent_name = "ticket_soos"
        ticket_handler.module_key = "soos"
        ticket_handler.execute.return_value = "Тикет получен"
        router._handlers["ticket_soos"] = ticket_handler

        result, status = await router.route("Текст тикета из чата", user_id=2)

        self.assertEqual(status, "routed")
        self.assertEqual(result, "Тикет получен")
        ticket_handler.execute.assert_awaited_once_with(
            {"ticket_text": "Текст тикета из чата"},
            2,
        )

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["soos"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_ticket_soos_overrides_truncated_ticket_text_with_full_original(
        self,
        mock_log,
        mock_modules,
        mock_enabled,
    ):
        """Для intent=ticket_soos в handler всегда передаётся полный original_text."""
        full_text = "A" * 5500
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="ticket_soos",
            confidence=0.95,
            parameters={"ticket_text": "short truncated"},
            explain_code="SOOS_TICKET_STRUCTURE",
        )

        router = _make_router(provider=provider)
        ticket_handler = AsyncMock()
        ticket_handler.intent_name = "ticket_soos"
        ticket_handler.module_key = "soos"
        ticket_handler.execute.return_value = "Тикет получен"
        router._handlers["ticket_soos"] = ticket_handler

        result, status = await router.route(full_text, user_id=3)

        self.assertEqual(status, "routed")
        self.assertEqual(result, "Тикет получен")
        ticket_handler.execute.assert_awaited_once_with(
            {"ticket_text": full_text},
            3,
        )

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["soos"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_legacy_ticket_validation_intent_normalized_to_ticket_soos(
        self,
        mock_log,
        mock_modules,
        mock_enabled,
    ):
        """Legacy intent=ticket_validation маппится в ticket_soos для обратной совместимости."""
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="ticket_validation",
            confidence=0.95,
            parameters={},
            explain_code="SOOS_TICKET_MULTILINE",
        )

        router = _make_router(provider=provider)
        ticket_handler = AsyncMock()
        ticket_handler.intent_name = "ticket_soos"
        ticket_handler.module_key = "soos"
        ticket_handler.execute.return_value = "Тикет получен"
        router._handlers["ticket_soos"] = ticket_handler

        result, status = await router.route("Текст тикета", user_id=4)

        self.assertEqual(status, "routed")
        self.assertEqual(result, "Тикет получен")
        ticket_handler.execute.assert_awaited_once_with(
            {"ticket_text": "Текст тикета"},
            4,
        )

    @patch("src.common.bot_settings.is_module_enabled")
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["upos_errors"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_module_disabled_at_dispatch(self, mock_log, mock_modules, mock_enabled):
        """Модуль выключен во время dispatch — module_disabled статус."""
        # AI-модуль включён, но целевой модуль — нет
        def side_effect(key):
            if key == "ai_router":
                return True
            return False  # upos_errors выключен

        mock_enabled.side_effect = side_effect

        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="upos_error_lookup",
            confidence=0.95,
            parameters={"error_code": "E001"},
        )

        router = _make_router(provider=provider)
        result, status = await router.route("ошибка E001", user_id=1)
        self.assertEqual(status, "module_disabled")
        self.assertIn("отключён", result)

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=[])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_low_confidence_returns_none(self, mock_log, mock_modules, mock_enabled):
        """Низкая уверенность — low_confidence статус."""
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="unknown",
            confidence=0.1,
        )

        router = _make_router(provider=provider)
        result, status = await router.route("что-то странное", user_id=1)
        self.assertEqual(status, "low_confidence")

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=[])
    @patch.object(IntentRouter, "_log_to_db")
    @patch("src.sbs_helper_telegram_bot.ai_router.intent_router.logger.info")
    async def test_general_chat_response(self, mock_logger_info, mock_log_to_db, mock_modules, mock_enabled):
        """Intent=general_chat с достаточной confidence — chat fallback."""
        provider = AsyncMock()
        provider.name = "deepseek"
        provider.get_model_name = MagicMock(side_effect=lambda purpose="response": (
            "deepseek-reasoner" if purpose == "classification" else "deepseek-chat"
        ))
        provider.classify.return_value = ClassificationResult(
            intent="general_chat",
            confidence=0.7,
            response_time_ms=900,
        )
        provider.chat.return_value = "Привет, я AI-помощник!"

        router = _make_router(provider=provider)
        result, status = await router.route("привет", user_id=1)
        self.assertEqual(status, "chat")
        self.assertIsNotNone(result)

        # Проверяем, что есть детальный лог профилирования AI-маршрута
        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("AI route profiling:")
                for call in mock_logger_info.call_args_list
            )
        )

        self.assertTrue(
            any(
                call.args
                and isinstance(call.args[0], str)
                and call.args[0].startswith("AI classification:")
                and "provider=%s, model=%s" in call.args[0]
                and "deepseek" in call.args
                and "deepseek-reasoner" in call.args
                for call in mock_logger_info.call_args_list
            )
        )

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["ai_router"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_general_chat_rerouted_to_rag(self, mock_log_to_db, mock_modules, mock_enabled):
        """Intent=general_chat для вопроса маршрутизируется в rag_qa при доступном модуле."""
        provider = AsyncMock()
        provider.name = "deepseek"
        provider.get_model_name = MagicMock(return_value="deepseek-chat")
        provider.classify.return_value = ClassificationResult(
            intent="general_chat",
            confidence=0.92,
            response_time_ms=700,
        )

        router = _make_router(provider=provider)
        rag_handler = AsyncMock()
        rag_handler.intent_name = "rag_qa"
        rag_handler.module_key = "ai_router"
        rag_handler.execute.return_value = "📚 *Ответ по базе знаний*\n\nТест"
        router._handlers["rag_qa"] = rag_handler

        result, status = await router.route("как оформить заявку по регламенту?", user_id=1)

        self.assertEqual(status, "routed")
        self.assertIn("Ответ по базе знаний", result)
        rag_handler.execute.assert_awaited_once_with(
            {"question": "как оформить заявку по регламенту?"},
            1,
        )
        provider.chat.assert_not_called()

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["ai_router"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_general_chat_rerouted_to_rag_forwards_progress(
        self,
        mock_log_to_db,
        mock_modules,
        mock_enabled,
    ):
        """При reroute general_chat→rag колбэк прогресса получает RAG-этапы."""
        provider = AsyncMock()
        provider.name = "deepseek"
        provider.get_model_name = MagicMock(return_value="deepseek-chat")
        provider.classify.return_value = ClassificationResult(
            intent="general_chat",
            confidence=0.92,
            response_time_ms=700,
        )

        router = _make_router(provider=provider)
        rag_handler = MagicMock()
        rag_handler.intent_name = "rag_qa"
        rag_handler.module_key = "ai_router"

        async def _execute_with_progress(_params, _user_id, on_progress=None):
            if on_progress is not None:
                await on_progress(AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED, {"marker": "prefilter"})
                await on_progress(AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED, {"marker": "llm"})
            return "📚 *Ответ по базе знаний*\n\nТест"

        rag_handler.execute = AsyncMock(side_effect=_execute_with_progress)
        router._handlers["rag_qa"] = rag_handler

        on_progress = AsyncMock()
        result, status = await router.route(
            "как оформить заявку по регламенту?",
            user_id=1,
            on_progress=on_progress,
        )

        self.assertEqual(status, "routed")
        self.assertIn("Ответ по базе знаний", result)
        self.assertEqual(on_progress.await_count, 2)
        self.assertEqual(on_progress.await_args_list[0].args[0], AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED)
        self.assertEqual(on_progress.await_args_list[1].args[0], AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED)
        self.assertEqual(on_progress.await_args_list[0].args[1].get("route_path"), "general_chat_to_rag")
        self.assertEqual(on_progress.await_args_list[1].args[1].get("route_path"), "general_chat_to_rag")

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["ai_router"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_small_talk_keeps_general_chat(self, mock_log_to_db, mock_modules, mock_enabled):
        """Явный small-talk остаётся в general_chat и не уходит в rag_qa."""
        provider = AsyncMock()
        provider.name = "deepseek"
        provider.get_model_name = MagicMock(return_value="deepseek-chat")
        provider.classify.return_value = ClassificationResult(
            intent="general_chat",
            confidence=0.91,
            response_time_ms=650,
        )
        provider.chat.return_value = "Привет!"

        router = _make_router(provider=provider)
        rag_handler = AsyncMock()
        rag_handler.intent_name = "rag_qa"
        rag_handler.module_key = "ai_router"
        router._handlers["rag_qa"] = rag_handler

        result, status = await router.route("привет", user_id=1)

        self.assertEqual(status, "chat")
        self.assertIsNotNone(result)
        rag_handler.execute.assert_not_called()
        provider.chat.assert_awaited_once()

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=[])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_direct_answer_fallback_response(self, mock_log_to_db, mock_modules, mock_enabled):
        """Direct-answer fallback из классификации возвращается как chat-ответ."""
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="general_chat",
            confidence=0.85,
            parameters={"direct_answer": "Готовый ответ из fallback"},
            explain_code="DIRECT_TEXT_FALLBACK",
        )

        router = _make_router(provider=provider)
        result, status = await router.route("как прошить D200", user_id=1)

        self.assertEqual(status, "chat")
        self.assertIn("Готовый ответ", result)
        provider.chat.assert_not_called()

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=["upos_errors"])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_retry_no_json_classification_success(self, mock_log_to_db, mock_modules, mock_enabled):
        """При no-JSON на первой попытке роутер делает retry и использует успешный второй результат."""
        provider = AsyncMock()
        provider.classify.side_effect = [
            ClassificationResult(
                intent="general_chat",
                confidence=0.85,
                parameters={"direct_answer": "Текст вместо JSON"},
                explain_code="DIRECT_TEXT_FALLBACK",
            ),
            ClassificationResult(
                intent="upos_error_lookup",
                confidence=0.95,
                parameters={"error_code": "E001"},
                explain_code="UPOS_EXACT",
            ),
        ]

        router = _make_router(provider=provider)
        mock_handler = AsyncMock()
        mock_handler.intent_name = "upos_error_lookup"
        mock_handler.module_key = "upos_errors"
        mock_handler.execute.return_value = "✅ Код найден"
        router._handlers["upos_error_lookup"] = mock_handler

        result, status = await router.route("ошибка E001", user_id=1)

        self.assertEqual(status, "routed")
        self.assertEqual(result, "✅ Код найден")
        self.assertEqual(provider.classify.await_count, 2)
        provider.chat.assert_not_called()

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=[])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_retry_no_json_classification_fails_keeps_first_result(
        self,
        mock_log_to_db,
        mock_modules,
        mock_enabled,
    ):
        """Если retry снова no-JSON, сохраняется первый direct-answer fallback."""
        provider = AsyncMock()
        provider.classify.side_effect = [
            ClassificationResult(
                intent="general_chat",
                confidence=0.85,
                parameters={"direct_answer": "Готовый ответ из первого fallback"},
                explain_code="DIRECT_TEXT_FALLBACK",
            ),
            ClassificationResult(
                intent="unknown",
                confidence=0.0,
                parameters={},
                explain_code="NO_JSON_IN_RESPONSE",
            ),
        ]

        router = _make_router(provider=provider)
        result, status = await router.route("любой текст", user_id=1)

        self.assertEqual(status, "chat")
        self.assertIn("Готовый ответ", result)
        self.assertEqual(provider.classify.await_count, 2)
        provider.chat.assert_not_called()

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=[])
    @patch("src.sbs_helper_telegram_bot.ai_router.intent_router.logger.exception")
    async def test_classification_error_records_failure(self, mock_logger_exception, mock_modules, mock_enabled):
        """Ошибка LLM — записывается failure в circuit breaker."""
        provider = AsyncMock()
        empty_exc = Exception()
        provider.classify.side_effect = empty_exc

        cb = CircuitBreaker(failure_threshold=10)
        router = _make_router(provider=provider, circuit_breaker=cb)
        result, status = await router.route("test", user_id=1)
        self.assertIsNone(result)
        self.assertEqual(status, "error")
        self.assertEqual(cb._failure_count, 1)
        mock_logger_exception.assert_called_once()
        log_args = mock_logger_exception.call_args.args
        self.assertIn("AI classification error", log_args[0])
        self.assertEqual(log_args[2], "Exception")
        self.assertIs(log_args[3], empty_exc)

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=[])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_on_classified_callback_called(self, mock_log, mock_modules, mock_enabled):
        """После успешной классификации вызывается on_classified callback."""
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="general_chat",
            confidence=0.8,
        )
        provider.chat.return_value = "Ответ AI"

        on_classified = AsyncMock()
        router = _make_router(provider=provider)

        await router.route("привет", user_id=1, on_classified=on_classified)

        on_classified.assert_awaited_once()
        callback_arg = on_classified.await_args.args[0]
        self.assertEqual(callback_arg.intent, "general_chat")


class TestIntentRouterContext(unittest.IsolatedAsyncioTestCase):
    """Тесты: контекст диалога."""

    def test_clear_context(self):
        """clear_context очищает контекст пользователя."""
        cm = ConversationContextManager()
        cm.add_message(1, "user", "test")
        router = _make_router(context_manager=cm)
        router.clear_context(1)
        self.assertFalse(cm.has_context(1))

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=[])
    @patch.object(IntentRouter, "_log_to_db")
    async def test_context_updated_after_route(self, mock_log, mock_modules, mock_enabled):
        """Контекст обновляется после маршрутизации."""
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="general_chat",
            confidence=0.7,
        )
        provider.chat.return_value = "Ответ AI"

        cm = ConversationContextManager()
        router = _make_router(provider=provider, context_manager=cm)
        await router.route("вопрос", user_id=1)

        messages = cm.get_messages(1)
        self.assertTrue(len(messages) >= 1)


class TestIntentRouterStatus(unittest.TestCase):
    """Тесты: информация о статусе."""

    def test_get_status(self):
        """get_status возвращает словарь с информацией."""
        provider = MagicMock()
        provider.name = "deepseek"
        router = _make_router(provider=provider)
        status = router.get_status()
        self.assertIn("circuit_breaker", status)
        self.assertIn("provider", status)
        self.assertIn("confidence_threshold", status)
        self.assertIn("rate_limit", status)


class TestSingleton(unittest.TestCase):
    """Тесты: singleton-паттерн."""

    def test_get_router_singleton(self):
        """get_router возвращает один и тот же экземпляр."""
        reset_router()
        r1 = get_router()
        r2 = get_router()
        self.assertIs(r1, r2)
        reset_router()

    def test_reset_router(self):
        """reset_router сбрасывает singleton."""
        reset_router()
        r1 = get_router()
        reset_router()
        r2 = get_router()
        self.assertIsNot(r1, r2)
        reset_router()


if __name__ == "__main__":
    unittest.main()
