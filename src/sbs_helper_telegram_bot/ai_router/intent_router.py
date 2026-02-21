"""
intent_router.py — маршрутизатор намерений AI.

Координирует весь процесс AI-маршрутизации: rate-limiting, circuit breaker,
классификацию через LLM-провайдер, проверку модулей и вызов обработчиков.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

import src.common.bot_settings as bot_settings
import src.common.database as database

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings
from src.sbs_helper_telegram_bot.ai_router.circuit_breaker import CircuitBreaker
from src.sbs_helper_telegram_bot.ai_router.context_manager import ConversationContextManager
from src.sbs_helper_telegram_bot.ai_router.intent_handlers import IntentHandler, get_all_handlers
from src.sbs_helper_telegram_bot.ai_router.llm_provider import (
    ClassificationResult,
    LLMProvider,
    get_provider,
)
from src.sbs_helper_telegram_bot.ai_router.messages import (
    MESSAGE_AI_UNAVAILABLE,
    MESSAGE_AI_LOW_CONFIDENCE,
    format_ai_chat_response,
    format_module_disabled_message,
    format_rate_limit_message,
)
from src.sbs_helper_telegram_bot.ai_router.prompts import (
    build_chat_prompt,
    build_classification_prompt,
)
from src.sbs_helper_telegram_bot.ai_router.rate_limiter import AIRateLimiter

logger = logging.getLogger(__name__)


class IntentRouter:
    """
    Главный маршрутизатор AI-намерений.

    Координирует процесс:
    1. Rate-limit проверка
    2. Circuit breaker проверка
    3. LLM-классификация с контекстом
    4. Проверка доступности целевого модуля
    5. Вызов обработчика или fallback-ответ
    6. Логирование результатов
    """

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        rate_limiter: Optional[AIRateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        context_manager: Optional[ConversationContextManager] = None,
    ):
        """
        Инициализация маршрутизатора.

        Args:
            provider: LLM-провайдер (по умолчанию создаётся из настроек).
            rate_limiter: Rate-limiter (по умолчанию создаётся из настроек).
            circuit_breaker: Circuit breaker (по умолчанию создаётся из настроек).
            context_manager: Менеджер контекста (по умолчанию создаётся из настроек).
        """
        self._provider = provider
        self._rate_limiter = rate_limiter or AIRateLimiter()
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._context_manager = context_manager or ConversationContextManager()

        # Индексируем обработчики по intent_name
        self._handlers: Dict[str, IntentHandler] = {}
        for handler in get_all_handlers():
            self._handlers[handler.intent_name] = handler

    def _get_provider(self) -> LLMProvider:
        """Ленивая инициализация провайдера."""
        if self._provider is None:
            self._provider = get_provider()
        return self._provider

    async def route(
        self,
        text: str,
        user_id: int,
    ) -> Tuple[Optional[str], str]:
        """
        Маршрутизировать текстовое сообщение пользователя.

        Args:
            text: Текст сообщения пользователя.
            user_id: Telegram ID пользователя.

        Returns:
            Кортеж (ответ_MarkdownV2 | None, статус).
            Статус: "routed", "chat", "rate_limited", "circuit_open",
                     "low_confidence", "error", "disabled".
        """
        start_time = time.monotonic()

        # 1. Проверяем, включён ли AI-модуль
        if not bot_settings.is_module_enabled(ai_settings.AI_MODULE_KEY):
            return None, "disabled"

        # 2. Rate-limit
        allowed, remaining = self._rate_limiter.check(user_id)
        if not allowed:
            logger.info(
                "AI rate limit: user=%s, remaining=%s sec", user_id, remaining
            )
            return format_rate_limit_message(remaining), "rate_limited"

        # 3. Circuit breaker
        if not self._circuit_breaker.is_available():
            logger.warning(
                "AI circuit open: user=%s, state=%s",
                user_id,
                self._circuit_breaker.state.value,
            )
            return None, "circuit_open"

        # 4. Ограничение длины входного текста
        if len(text) > ai_settings.MAX_INPUT_LENGTH:
            text = text[: ai_settings.MAX_INPUT_LENGTH]

        # 5. Получаем контекст диалога
        context_messages = self._context_manager.get_messages(user_id)
        context_messages.append({"role": "user", "content": text})

        # 6. Определяем доступные модули
        enabled_modules = self._get_enabled_routable_modules()

        # 7. Классифицируем через LLM
        try:
            provider = self._get_provider()
            system_prompt = build_classification_prompt(enabled_modules)
            classification = await provider.classify(context_messages, system_prompt)
            self._circuit_breaker.record_success()
        except Exception as exc:
            self._circuit_breaker.record_failure()
            logger.error(
                "AI classification error: user=%s, error=%s", user_id, exc
            )
            return None, "error"

        # 8. Записываем rate-limit
        self._rate_limiter.record(user_id)

        # 9. Логируем результат классификации
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.info(
            "AI classification: user=%s, intent=%s, confidence=%.2f, "
            "explain=%s, elapsed=%dms, provider_ms=%dms",
            user_id,
            classification.intent,
            classification.confidence,
            classification.explain_code,
            elapsed_ms,
            classification.response_time_ms,
        )

        # 10. Логируем в БД
        self._log_to_db(
            user_id=user_id,
            input_text=text[:500],
            classification=classification,
            elapsed_ms=elapsed_ms,
        )

        # 11. Маршрутизация по intent
        response, status = await self._dispatch(
            classification, user_id, text, enabled_modules
        )

        # 12. Обновляем контекст
        self._context_manager.add_message(user_id, "user", text)
        if response:
            # Сохраняем plain-text версию ответа (без MD)
            self._context_manager.add_message(
                user_id, "assistant", response[:500]
            )

        return response, status

    async def _dispatch(
        self,
        classification: ClassificationResult,
        user_id: int,
        original_text: str,
        enabled_modules: List[str],
    ) -> Tuple[Optional[str], str]:
        """Диспетчер: маршрутизировать к handler или fallback."""
        intent = classification.intent
        confidence = classification.confidence

        # Обработчик модуля
        handler = self._handlers.get(intent)
        if handler and confidence >= ai_settings.CONFIDENCE_THRESHOLD:
            # Проверяем, включён ли целевой модуль
            if not bot_settings.is_module_enabled(handler.module_key):
                module_name = bot_settings.MODULE_NAMES.get(
                    handler.module_key, handler.module_key
                )
                logger.info(
                    "AI route blocked: module %s disabled, user=%s",
                    handler.module_key,
                    user_id,
                )
                return format_module_disabled_message(module_name), "module_disabled"

            try:
                # Для ticket_validation передаём оригинальный текст
                params = classification.parameters
                if intent == "ticket_validation" and not params.get("ticket_text"):
                    params["ticket_text"] = original_text

                response = await handler.execute(params, user_id)
                return response, "routed"
            except Exception as exc:
                logger.error(
                    "AI handler error: intent=%s, user=%s, error=%s",
                    intent,
                    user_id,
                    exc,
                )
                return None, "error"

        # General chat — свободный ответ LLM
        if intent == "general_chat" and confidence >= ai_settings.CHAT_CONFIDENCE_THRESHOLD:
            try:
                provider = self._get_provider()
                context_messages = self._context_manager.get_messages(user_id)
                context_messages.append({"role": "user", "content": original_text})
                chat_response = await provider.chat(
                    context_messages, build_chat_prompt()
                )
                return format_ai_chat_response(chat_response), "chat"
            except Exception as exc:
                self._circuit_breaker.record_failure()
                logger.error("AI chat error: user=%s, error=%s", user_id, exc)
                return None, "error"

        # Низкая уверенность
        if confidence < ai_settings.CHAT_CONFIDENCE_THRESHOLD:
            return None, "low_confidence"

        # Средняя уверенность — пробуем chat
        if intent != "unknown":
            try:
                provider = self._get_provider()
                context_messages = self._context_manager.get_messages(user_id)
                context_messages.append({"role": "user", "content": original_text})
                chat_response = await provider.chat(
                    context_messages, build_chat_prompt()
                )
                return format_ai_chat_response(chat_response), "chat"
            except Exception as exc:
                self._circuit_breaker.record_failure()
                logger.error("AI chat fallback error: user=%s, error=%s", user_id, exc)
                return None, "error"

        return None, "low_confidence"

    def clear_context(self, user_id: int) -> None:
        """Очистить контекст диалога для пользователя."""
        self._context_manager.clear(user_id)

    def get_status(self) -> dict:
        """Получить статус компонентов AI для админ-панели."""
        return {
            "circuit_breaker": self._circuit_breaker.get_status_info(),
            "provider": self._get_provider().name if self._provider else ai_settings.AI_PROVIDER,
            "confidence_threshold": ai_settings.CONFIDENCE_THRESHOLD,
            "rate_limit": {
                "max_requests": ai_settings.RATE_LIMIT_MAX_REQUESTS,
                "window_seconds": ai_settings.RATE_LIMIT_WINDOW_SECONDS,
            },
        }

    def _get_enabled_routable_modules(self) -> List[str]:
        """Получить список включённых модулей, для которых есть обработчики."""
        enabled = bot_settings.get_enabled_modules()
        routable = set(h.module_key for h in self._handlers.values())
        return [m for m in enabled if m in routable]

    @staticmethod
    def _log_to_db(
        user_id: int,
        input_text: str,
        classification: ClassificationResult,
        elapsed_ms: int,
    ) -> None:
        """Записать результат маршрутизации в БД для аналитики."""
        try:
            with database.get_db_connection() as conn:
                with database.get_cursor(conn) as cursor:
                    cursor.execute(
                        """
                        INSERT INTO ai_router_log
                            (user_id, input_text, detected_intent, confidence,
                             explain_code, response_time_ms, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            user_id,
                            input_text,
                            classification.intent,
                            classification.confidence,
                            classification.explain_code,
                            elapsed_ms,
                        ),
                    )
        except Exception as exc:
            # Не блокируем основной поток при ошибке логирования
            logger.warning("Ошибка записи в ai_router_log: %s", exc)


# =============================================
# Глобальный экземпляр (singleton для процесса)
# =============================================

_router_instance: Optional[IntentRouter] = None


def get_router() -> IntentRouter:
    """Получить глобальный экземпляр маршрутизатора."""
    global _router_instance
    if _router_instance is None:
        _router_instance = IntentRouter()
    return _router_instance


def reset_router() -> None:
    """Сбросить глобальный экземпляр (для тестирования)."""
    global _router_instance
    _router_instance = None
