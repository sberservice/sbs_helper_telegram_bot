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
    async def test_general_chat_response(self, mock_log, mock_modules, mock_enabled):
        """Intent=general_chat с достаточной confidence — chat fallback."""
        provider = AsyncMock()
        provider.classify.return_value = ClassificationResult(
            intent="general_chat",
            confidence=0.7,
        )
        provider.chat.return_value = "Привет, я AI-помощник!"

        router = _make_router(provider=provider)
        result, status = await router.route("привет", user_id=1)
        self.assertEqual(status, "chat")
        self.assertIsNotNone(result)

    @patch("src.common.bot_settings.is_module_enabled", return_value=True)
    @patch("src.common.bot_settings.get_enabled_modules", return_value=[])
    async def test_classification_error_records_failure(self, mock_modules, mock_enabled):
        """Ошибка LLM — записывается failure в circuit breaker."""
        provider = AsyncMock()
        provider.classify.side_effect = Exception("API error")

        cb = CircuitBreaker(failure_threshold=10)
        router = _make_router(provider=provider, circuit_breaker=cb)
        result, status = await router.route("test", user_id=1)
        self.assertIsNone(result)
        self.assertEqual(status, "error")
        self.assertEqual(cb._failure_count, 1)


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
