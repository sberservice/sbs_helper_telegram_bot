"""
llm_provider.py — абстракция и реализации LLM-провайдеров.

Предоставляет базовый класс LLMProvider и конкретную реализацию
DeepSeekProvider для классификации намерений и свободного диалога.
Поддерживает расширение на другие модели (OpenAI, Anthropic, и т.д.).
"""

import json
import logging
import re
import time
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import src.common.database as database
from src.common.pii_masking import mask_sensitive_data

from config import ai_settings

logger = logging.getLogger(__name__)


ALLOWED_CLASSIFICATION_INTENTS = {
    "certification_info",
    "ticket_soos",
    "ticket_validation",
    "upos_error_lookup",
    "ktr_lookup",
    "rag_qa",
    "news_search",
    "general_chat",
    "unknown",
}


# =============================================
# Результат классификации
# =============================================

@dataclass
class ClassificationResult:
    """Результат классификации пользовательского сообщения."""

    intent: str
    """Определённое намерение (upos_error_lookup, ticket_soos, и т.д.)."""

    confidence: float
    """Уровень уверенности от 0.0 до 1.0."""

    parameters: Dict[str, Any] = field(default_factory=dict)
    """Извлечённые параметры для обработчика намерения."""

    explain_code: str = "UNKNOWN"
    """Короткий мнемонический код для логирования причин маршрутизации."""

    raw_response: Optional[str] = None
    """Сырой ответ от LLM для отладки."""

    response_time_ms: int = 0
    """Время ответа LLM в миллисекундах."""


class LLMProviderTemporaryError(RuntimeError):
    """Временная ошибка LLM-провайдера (таймаут/сетевая деградация)."""


# =============================================
# Базовый класс провайдера
# =============================================

class LLMProvider(ABC):
    """Абстрактный базовый класс для LLM-провайдеров."""

    @abstractmethod
    async def classify(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        user_id: Optional[int] = None,
    ) -> ClassificationResult:
        """
        Классифицировать пользовательское сообщение.

        Args:
            messages: Список сообщений диалога [{role, content}, ...].
            system_prompt: Системный промпт с инструкциями классификации.

        Returns:
            ClassificationResult с определённым намерением и параметрами.
        """
        ...

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        user_id: Optional[int] = None,
        purpose: str = "response",
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        allow_model_fallback: bool = True,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Получить свободный текстовый ответ от LLM.

        Args:
            messages: Список сообщений диалога [{role, content}, ...].
            system_prompt: Системный промпт.
            response_format: Опциональный формат ответа (например, {"type": "json_object"}).

        Returns:
            Текстовый ответ LLM.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Проверить доступность провайдера.

        Returns:
            True если провайдер доступен, иначе False.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Имя провайдера для логирования."""
        ...

    def get_model_name(self, purpose: str = "response") -> Optional[str]:
        """Вернуть имя активной модели для указанной цели запроса."""
        return None


# =============================================
# DeepSeek-провайдер (OpenAI-совместимый API)
# =============================================

class DeepSeekProvider(LLMProvider):
    """
    Провайдер на основе DeepSeek API (OpenAI-совместимый).

    Использует endpoint /v1/chat/completions для классификации и
    свободного диалога.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """
        Инициализация DeepSeek-провайдера.

        Args:
            api_key: API-ключ (по умолчанию из настроек).
            base_url: Базовый URL API (по умолчанию из настроек).
            model: Название модели (по умолчанию из настроек).
            timeout: Таймаут запроса в секундах.
        """
        self._api_key = api_key or ai_settings.DEEPSEEK_API_KEY
        self._base_url = (base_url or ai_settings.DEEPSEEK_BASE_URL).rstrip("/")
        # Если model задан явно — используем его, иначе берём текущую модель из bot_settings.
        self._model = model
        self._timeout = timeout or ai_settings.LLM_REQUEST_TIMEOUT

        if not self._api_key:
            logger.warning("DeepSeek API key не задан. AI-маршрутизация будет недоступна.")

    def _resolve_model(self, purpose: str = "response") -> str:
        """Определить активную модель DeepSeek для текущего запроса."""
        if self._model:
            return ai_settings.normalize_deepseek_model(self._model)
        if purpose == "classification":
            return ai_settings.get_active_deepseek_model_for_classification()
        return ai_settings.get_active_deepseek_model_for_response()

    @property
    def name(self) -> str:
        return "deepseek"

    def get_model_name(self, purpose: str = "response") -> Optional[str]:
        """Вернуть имя модели DeepSeek для указанной цели запроса."""
        return self._resolve_model(purpose=purpose)

    async def classify(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        user_id: Optional[int] = None,
    ) -> ClassificationResult:
        """Классифицировать сообщение через DeepSeek API."""
        start_time = time.monotonic()

        full_messages = [{"role": "system", "content": system_prompt}] + messages

        try:
            # Для длинных заявок (ticket_soos) увеличиваем бюджет токенов,
            # чтобы JSON-ответ не обрезался до закрывающих скобок.
            raw = await self._call_api(
                full_messages,
                temperature=ai_settings.LLM_CLASSIFICATION_TEMPERATURE,
                max_tokens=ai_settings.LLM_CLASSIFICATION_MAX_TOKENS,
                purpose="classification",
                user_id=user_id,
                response_format={"type": "json_object"},
            )
        except LLMProviderTemporaryError as exc:
            elapsed = int((time.monotonic() - start_time) * 1000)
            logger.warning(
                "DeepSeek classify temporary error: type=%s repr=%r (elapsed=%dms)",
                type(exc).__name__,
                exc,
                elapsed,
            )
            raise
        except Exception as exc:
            elapsed = int((time.monotonic() - start_time) * 1000)
            logger.exception(
                "DeepSeek classify error: type=%s repr=%r (elapsed=%dms)",
                type(exc).__name__,
                exc,
                elapsed,
            )
            raise

        elapsed = int((time.monotonic() - start_time) * 1000)

        return self._parse_classification(raw, elapsed)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        user_id: Optional[int] = None,
        purpose: str = "response",
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        allow_model_fallback: bool = True,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Получить свободный текстовый ответ через DeepSeek API."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        temperature = ai_settings.LLM_CHAT_TEMPERATURE
        if temperature_override is not None:
            try:
                temperature = float(temperature_override)
            except (TypeError, ValueError):
                logger.warning(
                    "Некорректный temperature_override=%r, используется дефолт %.3f",
                    temperature_override,
                    ai_settings.LLM_CHAT_TEMPERATURE,
                )

        try:
            retry_attempts = 4 if model_override and purpose in {"gk_inference", "gk_prompt_tester"} else 2
            raw = await self._call_api(
                full_messages,
                temperature=temperature,
                max_tokens=ai_settings.LLM_CHAT_MAX_TOKENS,
                purpose=purpose,
                user_id=user_id,
                force_model=model_override,
                allow_empty_content_retry=allow_model_fallback and model_override is None,
                max_attempts=retry_attempts,
                response_format=response_format,
            )
        except LLMProviderTemporaryError as exc:
            logger.warning(
                "DeepSeek chat temporary error: type=%s repr=%r",
                type(exc).__name__,
                exc,
            )
            raise
        except Exception as exc:
            logger.exception(
                "DeepSeek chat error: type=%s repr=%r",
                type(exc).__name__,
                exc,
            )
            raise

        return raw

    async def health_check(self) -> bool:
        """Проверить доступность DeepSeek API."""
        if not self._api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base_url}/v1/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("DeepSeek health check failed: %s", exc)
            return False

    # ----- Внутренние методы -----

    async def _call_api(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 512,
        purpose: str = "response",
        user_id: Optional[int] = None,
        force_model: Optional[str] = None,
        allow_empty_content_retry: bool = True,
        max_attempts: int = 2,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Выполнить вызов к DeepSeek /v1/chat/completions.

        Args:
            messages: Полный список сообщений (включая system).
            temperature: Температура генерации.
            max_tokens: Максимальное число токенов ответа.

        Returns:
            Текстовый контент ответа модели.

        Raises:
            httpx.HTTPStatusError: при HTTP-ошибках.
            ValueError: при некорректном ответе API.
        """
        model_name = ai_settings.normalize_deepseek_model(force_model) if force_model else self._resolve_model(purpose=purpose)

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        request_payload_text = json.dumps(messages, ensure_ascii=False)

        self._log_model_request(
            purpose=purpose,
            model_name=str(payload.get("model") or ""),
            temperature=temperature,
            max_tokens=max_tokens,
            messages=messages,
            response_format=response_format,
        )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        max_attempts = max(1, int(max_attempts))
        response: Optional[httpx.Response] = None
        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=self._timeout,
                        read=ai_settings.LLM_READ_TIMEOUT,
                        write=self._timeout,
                        pool=self._timeout,
                    )
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/v1/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError:
                        response_body = str(response.text or "")
                        logger.error(
                            "DeepSeek HTTP error: status=%s purpose=%s model=%s body=%s",
                            response.status_code,
                            purpose,
                            payload.get("model"),
                            self._truncate_for_log(response_body),
                        )
                        self._log_model_io_to_db(
                            user_id=user_id,
                            purpose=purpose,
                            model_name=str(payload.get("model") or ""),
                            request_text=request_payload_text,
                            response_text="",
                            status="http_error",
                            response_time_ms=None,
                            error_text=response_body,
                        )
                        raise
                break
            except httpx.TimeoutException as exc:
                error_text = str(exc) or type(exc).__name__
                logger.warning(
                    "DeepSeek timeout: purpose=%s model=%s attempt=%d/%d error=%s",
                    purpose,
                    payload.get("model"),
                    attempt,
                    max_attempts,
                    error_text,
                )
                self._log_model_io_to_db(
                    user_id=user_id,
                    purpose=purpose,
                    model_name=str(payload.get("model") or ""),
                    request_text=request_payload_text,
                    response_text="",
                    status="timeout",
                    response_time_ms=None,
                    error_text=error_text,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(0.2 * attempt)
                    continue
                raise LLMProviderTemporaryError(
                    "Временная ошибка AI-сервиса: истекло время ожидания ответа."
                ) from None
            except httpx.RequestError as exc:
                error_text = str(exc) or type(exc).__name__
                logger.warning(
                    "DeepSeek network error: purpose=%s model=%s type=%s attempt=%d/%d error=%s",
                    purpose,
                    payload.get("model"),
                    type(exc).__name__,
                    attempt,
                    max_attempts,
                    error_text,
                )
                self._log_model_io_to_db(
                    user_id=user_id,
                    purpose=purpose,
                    model_name=str(payload.get("model") or ""),
                    request_text=request_payload_text,
                    response_text="",
                    status="request_error",
                    response_time_ms=None,
                    error_text=error_text,
                )
                if attempt < max_attempts:
                    await asyncio.sleep(0.2 * attempt)
                    continue
                raise LLMProviderTemporaryError(
                    "Временная ошибка AI-сервиса: проблемы с сетевым подключением."
                ) from None

        if response is None:
            raise LLMProviderTemporaryError("Временная ошибка AI-сервиса.")

        data = response.json()

        try:
            message = data["choices"][0]["message"]
            content = self._extract_message_content(message)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.error("Некорректный ответ DeepSeek API: %s", data)
            self._log_model_io_to_db(
                user_id=user_id,
                purpose=purpose,
                model_name=str(payload.get("model") or ""),
                request_text=request_payload_text,
                response_text=json.dumps(data, ensure_ascii=False),
                status="parse_error",
                response_time_ms=None,
                error_text=str(exc),
            )
            raise ValueError(f"Некорректная структура ответа API: {exc}") from exc

        is_empty_content = not str(content or "").strip()

        if is_empty_content:
            diagnostics = self._build_empty_content_diagnostics(
                response_data=data,
                message=message,
                content=content,
                response=response,
            )
            diagnostics_json = self._serialize_empty_content_diagnostics(diagnostics)
            logger.warning(
                "DeepSeek returned empty content: purpose=%s model=%s diagnostics=%s",
                purpose,
                model_name,
                self._truncate_for_log(diagnostics_json),
            )
            self._log_model_io_to_db(
                user_id=user_id,
                purpose=purpose,
                model_name=str(payload.get("model") or ""),
                request_text=request_payload_text,
                response_text=json.dumps(data, ensure_ascii=False),
                status="empty_content",
                response_time_ms=self._extract_response_time_ms(response),
                error_text=diagnostics_json,
            )

        if (
            allow_empty_content_retry
            and is_empty_content
            and model_name == ai_settings.DEEPSEEK_MODEL_REASONER
            and purpose != "classification"
        ):
            fallback_model = ai_settings.DEEPSEEK_MODEL_CHAT
            logger.warning(
                "DeepSeek returned empty content, retry with fallback model: purpose=%s from_model=%s to_model=%s",
                purpose,
                model_name,
                fallback_model,
            )
            return await self._call_api(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                purpose=purpose,
                user_id=user_id,
                force_model=fallback_model,
                allow_empty_content_retry=False,
                max_attempts=max_attempts,
                response_format=response_format,
            )

        if not is_empty_content:
            self._log_model_response(
                purpose=purpose,
                model_name=str(payload.get("model") or ""),
                raw_content=str(content or ""),
            )

            self._log_model_io_to_db(
                user_id=user_id,
                purpose=purpose,
                model_name=str(payload.get("model") or ""),
                request_text=request_payload_text,
                response_text=str(content or ""),
                status="ok",
                response_time_ms=self._extract_response_time_ms(response),
                error_text="",
            )

        return content

    @staticmethod
    def _extract_message_content(message: Any) -> str:
        """Извлечь текстовый content из message OpenAI-совместимого формата."""
        if not isinstance(message, dict):
            raise ValueError("message must be dict")

        content = message.get("content", "")
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text_value = item.get("text", "")
                    if isinstance(text_value, str) and text_value:
                        parts.append(text_value)
            return "\n".join(parts).strip()

        return str(content or "")

    @staticmethod
    def _build_empty_content_diagnostics(
        response_data: Any,
        message: Any,
        content: Any,
        response: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Собрать диагностические поля для случая пустого content в ответе модели."""
        choice: Dict[str, Any] = {}
        if isinstance(response_data, dict):
            choices = response_data.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                choice = choices[0]

        message_dict = message if isinstance(message, dict) else {}

        content_type = type(content).__name__
        if isinstance(content, str):
            content_length = len(content)
        elif content is None:
            content_length = 0
        else:
            content_length = len(str(content))

        has_reasoning = bool(message_dict.get("reasoning_content") or message_dict.get("reasoning"))
        has_refusal = bool(message_dict.get("refusal"))
        has_tool_calls = bool(message_dict.get("tool_calls"))

        diagnostics: Dict[str, Any] = {
            "response_id": response_data.get("id") if isinstance(response_data, dict) else None,
            "finish_reason": choice.get("finish_reason"),
            "usage": response_data.get("usage") if isinstance(response_data, dict) else None,
            "http_status": getattr(response, "status_code", None),
            "message_keys": sorted(message_dict.keys()),
            "content_type": content_type,
            "content_length": content_length,
            "has_reasoning": has_reasoning,
            "has_refusal": has_refusal,
            "has_tool_calls": has_tool_calls,
        }
        return diagnostics

    @staticmethod
    def _serialize_empty_content_diagnostics(diagnostics: Dict[str, Any]) -> str:
        """Сериализовать диагностику пустого ответа в JSON для логов и БД."""
        try:
            return json.dumps(diagnostics, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return json.dumps({"serialization_error": "diagnostics_not_serializable"}, ensure_ascii=False)

    @staticmethod
    def _extract_response_time_ms(response: Any) -> Optional[int]:
        """Извлечь длительность HTTP-запроса в миллисекундах, если доступна."""
        elapsed = getattr(response, "elapsed", None)
        if elapsed is None:
            return None

        total_seconds = getattr(elapsed, "total_seconds", None)
        if callable(total_seconds):
            try:
                return int(float(total_seconds()) * 1000)
            except (TypeError, ValueError):
                return None
        return None

    @staticmethod
    def _is_db_model_io_logging_enabled() -> bool:
        """Проверить, включено ли хранение полного model I/O в БД."""
        return bool(ai_settings.AI_MODEL_IO_DB_LOG_ENABLED)

    @staticmethod
    def _truncate_db_text(value: str, max_chars: int = 200_000) -> str:
        """Ограничить объём сохраняемого текста в БД."""
        text = str(value or "")
        if len(text) <= max_chars:
            return text
        return text[:max_chars]

    def _log_model_io_to_db(
        self,
        user_id: Optional[int],
        purpose: str,
        model_name: str,
        request_text: str,
        response_text: str,
        status: str,
        response_time_ms: Optional[int],
        error_text: str,
    ) -> None:
        """Запланировать сохранение model I/O в БД в отдельном потоке (fire-and-forget)."""
        if not self._is_db_model_io_logging_enabled():
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Нет event loop — вызываем синхронно (скрипты, тесты)
            self._log_model_io_to_db_sync(
                user_id=user_id,
                purpose=purpose,
                model_name=model_name,
                request_text=request_text,
                response_text=response_text,
                status=status,
                response_time_ms=response_time_ms,
                error_text=error_text,
            )
            return

        loop.call_soon(
            lambda: asyncio.ensure_future(
                asyncio.to_thread(
                    self._log_model_io_to_db_sync,
                    user_id=user_id,
                    purpose=purpose,
                    model_name=model_name,
                    request_text=request_text,
                    response_text=response_text,
                    status=status,
                    response_time_ms=response_time_ms,
                    error_text=error_text,
                )
            )
        )

    def _log_model_io_to_db_sync(
        self,
        user_id: Optional[int],
        purpose: str,
        model_name: str,
        request_text: str,
        response_text: str,
        status: str,
        response_time_ms: Optional[int],
        error_text: str,
    ) -> None:
        """Сохранить полный prompt/response модели в БД с маскированием PII."""
        safe_request = self._truncate_db_text(mask_sensitive_data(request_text))
        safe_response = self._truncate_db_text(mask_sensitive_data(response_text))
        safe_error = self._truncate_db_text(mask_sensitive_data(error_text), max_chars=50_000)

        try:
            with database.get_db_connection() as conn:
                with database.get_cursor(conn) as cursor:
                    cursor.execute(
                        """
                        INSERT INTO ai_model_io_log (
                            user_id,
                            provider,
                            model_name,
                            purpose,
                            request_text_full,
                            response_text_full,
                            error_text,
                            status,
                            response_time_ms,
                            created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            user_id,
                            self.name,
                            model_name[:64],
                            str(purpose or "response")[:64],
                            safe_request,
                            safe_response,
                            safe_error,
                            str(status or "ok")[:32],
                            response_time_ms,
                        ),
                    )
        except Exception as exc:
            logger.warning("Ошибка записи в ai_model_io_log: %s", exc)

    @staticmethod
    def _is_model_io_logging_enabled() -> bool:
        """Проверить, включено ли логирование prompt/response для модели."""
        return bool(ai_settings.AI_LOG_MODEL_IO)

    @staticmethod
    def _truncate_for_log(value: str) -> str:
        """Ограничить длину логируемого текста, чтобы не засорять логи."""
        text = str(value or "")
        max_chars = max(200, int(ai_settings.AI_LOG_MODEL_IO_MAX_CHARS))
        if len(text) <= max_chars:
            return text
        suffix = f"... [truncated {len(text) - max_chars} chars]"
        return text[:max_chars] + suffix

    def _log_model_request(
        self,
        purpose: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Записать в лог payload, отправляемый в модель."""
        if not self._is_model_io_logging_enabled():
            return

        serialized_messages = self._truncate_for_log(
            json.dumps(messages, ensure_ascii=False)
        )
        logger.info(
            "LLM request payload: provider=%s purpose=%s model=%s temperature=%.2f max_tokens=%s response_format=%s messages=%s",
            self.name,
            purpose,
            model_name,
            temperature,
            max_tokens,
            response_format,
            serialized_messages,
        )

    def _log_model_response(
        self,
        purpose: str,
        model_name: str,
        raw_content: str,
    ) -> None:
        """Записать в лог сырой ответ модели."""
        if not self._is_model_io_logging_enabled():
            return

        logger.info(
            "LLM raw response: provider=%s purpose=%s model=%s content=%s",
            self.name,
            purpose,
            model_name,
            self._truncate_for_log(raw_content),
        )

    @staticmethod
    def _parse_classification(raw: str, elapsed_ms: int) -> ClassificationResult:
        """
        Извлечь структурированный результат из текстового ответа LLM.

        Пытается найти JSON-объект в ответе. При неудаче возвращает
        результат с intent=unknown и низкой уверенностью.
        """
        if not str(raw or "").strip():
            logger.warning("Пустой ответ классификатора LLM")
            return ClassificationResult(
                intent="unknown",
                confidence=0.0,
                explain_code="EMPTY_RESPONSE",
                raw_response=raw,
                response_time_ms=elapsed_ms,
            )

        # Пробуем извлечь JSON из ответа (LLM может обернуть его в ```json ... ```)
        json_str = raw.strip()

        # Удаляем markdown code-блок, если есть
        if json_str.startswith("```"):
            # Убираем первую строку (```json) и последнюю (```)
            lines = json_str.split("\n")
            if len(lines) >= 3:
                json_str = "\n".join(lines[1:-1])
            else:
                json_str = json_str.strip("`").strip()

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            # Пробуем найти первый {...} в тексте
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    partial = DeepSeekProvider._extract_partial_classification(raw, elapsed_ms)
                    if partial is not None:
                        return partial
                    logger.warning(
                        "Не удалось распарсить JSON из ответа LLM: %s",
                        raw[:200],
                    )
                    return ClassificationResult(
                        intent="unknown",
                        confidence=0.0,
                        explain_code="JSON_PARSE_FAIL",
                        raw_response=raw,
                        response_time_ms=elapsed_ms,
                    )
            else:
                partial = DeepSeekProvider._extract_partial_classification(raw, elapsed_ms)
                if partial is not None:
                    return partial
                logger.warning(
                    "JSON не найден в ответе LLM: %s", raw[:200]
                )
                return ClassificationResult(
                    intent="unknown",
                    confidence=0.0,
                    explain_code="NO_JSON_IN_RESPONSE",
                    raw_response=raw,
                    response_time_ms=elapsed_ms,
                )

        return DeepSeekProvider._validate_and_normalize_classification(
            parsed=parsed,
            raw=raw,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _validate_and_normalize_classification(
        parsed: Any,
        raw: str,
        elapsed_ms: int,
    ) -> ClassificationResult:
        """
        Валидировать и нормализовать JSON классификации.

        Приводит результат к безопасной структуре и отбрасывает
        некорректные intent/поля.
        """
        if not isinstance(parsed, dict):
            return ClassificationResult(
                intent="unknown",
                confidence=0.0,
                explain_code="INVALID_JSON_TYPE",
                raw_response=raw,
                response_time_ms=elapsed_ms,
            )

        intent = str(parsed.get("intent", "unknown")).strip().lower()
        if not intent:
            intent = "unknown"

        if intent not in ALLOWED_CLASSIFICATION_INTENTS:
            logger.warning("LLM classification returned unsupported intent: %s", intent)
            return ClassificationResult(
                intent="unknown",
                confidence=0.0,
                parameters={},
                explain_code="INVALID_INTENT",
                raw_response=raw,
                response_time_ms=elapsed_ms,
            )

        raw_confidence = parsed.get("confidence", 0.0)
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = 0.0
            logger.warning(
                "LLM classification returned invalid confidence type: %r",
                raw_confidence,
            )
        confidence = max(0.0, min(1.0, confidence))

        parameters = parsed.get("parameters", {})
        if not isinstance(parameters, dict):
            parameters = {}

        explain_code = str(parsed.get("explain_code", "PARSED_OK")).strip()
        if not explain_code:
            explain_code = "PARSED_OK"

        return ClassificationResult(
            intent=intent,
            confidence=confidence,
            parameters=parameters,
            explain_code=explain_code,
            raw_response=raw,
            response_time_ms=elapsed_ms,
        )

    @staticmethod
    def _extract_partial_classification(
        raw: str,
        elapsed_ms: int,
    ) -> Optional[ClassificationResult]:
        """
        Попытаться извлечь intent/confidence из частично обрезанного JSON.

        Нужен для случаев, когда LLM вернул начало JSON-объекта, но ответ
        обрезался по длине (например, длинный `ticket_text`), и закрывающих
        скобок уже нет.
        """
        if '"intent"' not in raw:
            return None

        intent_match = re.search(r'"intent"\s*:\s*"([^"]+)"', raw)
        if not intent_match:
            return None

        confidence_match = re.search(
            r'"confidence"\s*:\s*([0-9]*\.?[0-9]+)',
            raw,
        )
        explain_match = re.search(r'"explain_code"\s*:\s*"([^"]+)"', raw)

        intent = intent_match.group(1)
        confidence = float(confidence_match.group(1)) if confidence_match else 0.0
        confidence = max(0.0, min(1.0, confidence))
        explain_code = explain_match.group(1) if explain_match else "PARTIAL_JSON_FALLBACK"

        logger.warning(
            "Использован fallback-парсинг частичного JSON: intent=%s, confidence=%.2f",
            intent,
            confidence,
        )

        return ClassificationResult(
            intent=intent,
            confidence=confidence,
            parameters={},
            explain_code=explain_code,
            raw_response=raw,
            response_time_ms=elapsed_ms,
        )


# =============================================
# GigaChat-провайдер (Sber GigaChat API)
# =============================================

class GigaChatProvider(LLMProvider):
    """
    Провайдер на основе GigaChat API (Sber).

    Поддерживает текстовый чат и описание изображений (vision).
    Использует библиотеку gigachat для взаимодействия с API.
    """

    def __init__(
        self,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        verify_ssl_certs: Optional[bool] = None,
        ca_bundle_file: Optional[str] = None,
        max_retries: Optional[int] = None,
    ):
        """
        Инициализация GigaChat-провайдера.

        Args:
            credentials: Авторизационный ключ (по умолчанию из настроек).
            scope: Область доступа API (по умолчанию из настроек).
            model: Модель GigaChat (по умолчанию из настроек).
            timeout: Таймаут запросов (по умолчанию из настроек).
            verify_ssl_certs: Проверять ли SSL (по умолчанию из настроек).
            ca_bundle_file: Путь к CA-сертификату (по умолчанию из настроек).
            max_retries: Число повторных попыток (по умолчанию из настроек).
        """
        self._credentials = credentials or ai_settings.GIGACHAT_CREDENTIALS
        self._scope = scope or ai_settings.GIGACHAT_SCOPE
        self._model = model or ai_settings.GIGACHAT_MODEL
        self._timeout = timeout if timeout is not None else ai_settings.GIGACHAT_TIMEOUT
        self._verify_ssl_certs = (
            verify_ssl_certs if verify_ssl_certs is not None
            else ai_settings.GIGACHAT_VERIFY_SSL_CERTS
        )
        self._ca_bundle_file = ca_bundle_file or ai_settings.GIGACHAT_CA_BUNDLE_FILE or None
        self._max_retries = max_retries if max_retries is not None else ai_settings.GIGACHAT_MAX_RETRIES

        if not self._credentials:
            logger.warning("GigaChat credentials не заданы. GigaChat-провайдер будет недоступен.")

    def _create_client_kwargs(self) -> Dict[str, Any]:
        """Получить словарь аргументов для создания GigaChat-клиента."""
        kwargs: Dict[str, Any] = {
            "credentials": self._credentials,
            "scope": self._scope,
            "model": self._model,
            "timeout": self._timeout,
            "verify_ssl_certs": self._verify_ssl_certs,
            "max_retries": self._max_retries,
        }
        if self._ca_bundle_file:
            kwargs["ca_bundle_file"] = self._ca_bundle_file
        return kwargs

    @staticmethod
    def _format_gigachat_error(exc: Exception) -> str:
        """Преобразовать ошибку GigaChat в понятное сообщение для пользователя."""
        message = str(exc)
        normalized = message.lower()

        if "authorization error: header is incorrect" in normalized:
            return (
                "Неверный формат GIGACHAT_CREDENTIALS. Для GigaChat нужен не access token и не просто API key, "
                "а авторизационный ключ для OAuth (Authorization key / Basic key) из кабинета Sber Developers. "
                "Проверьте GIGACHAT_CREDENTIALS и GIGACHAT_SCOPE в .env"
            )
        if "401" in normalized and "oauth" in normalized:
            return (
                "Ошибка авторизации GigaChat OAuth. Проверьте корректность GIGACHAT_CREDENTIALS, "
                "GIGACHAT_SCOPE и доступ к проекту GigaChat в кабинете Sber Developers"
            )
        return message

    @property
    def name(self) -> str:
        return "gigachat"

    def get_model_name(self, purpose: str = "response") -> Optional[str]:
        """Вернуть имя модели GigaChat."""
        return self._model

    async def classify(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        user_id: Optional[int] = None,
    ) -> ClassificationResult:
        """Классифицировать сообщение через GigaChat API (делегирует к chat)."""
        start_time = time.monotonic()

        full_messages = [{"role": "system", "content": system_prompt}] + messages

        try:
            raw = await self._call_gigachat(
                full_messages,
                temperature=0.1,
                user_id=user_id,
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - start_time) * 1000)
            logger.exception(
                "GigaChat classify error: type=%s repr=%r (elapsed=%dms)",
                type(exc).__name__,
                exc,
                elapsed,
            )
            raise

        elapsed = int((time.monotonic() - start_time) * 1000)
        return DeepSeekProvider._parse_classification(raw, elapsed)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
        user_id: Optional[int] = None,
        purpose: str = "response",
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
        allow_model_fallback: bool = True,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Получить свободный текстовый ответ через GigaChat API."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        temperature = 0.7
        if temperature_override is not None:
            try:
                temperature = float(temperature_override)
            except (TypeError, ValueError):
                logger.warning(
                    "Некорректный temperature_override=%r, используется дефолт %.3f",
                    temperature_override,
                    0.7,
                )

        try:
            raw = await self._call_gigachat(
                full_messages,
                temperature=temperature,
                model_override=model_override,
                user_id=user_id,
            )
        except Exception as exc:
            logger.exception(
                "GigaChat chat error: type=%s repr=%r",
                type(exc).__name__,
                exc,
            )
            raise

        return raw

    async def health_check(self) -> bool:
        """Проверить доступность GigaChat API."""
        if not self._credentials:
            return False
        try:
            from gigachat import GigaChat

            with GigaChat(**self._create_client_kwargs()) as client:
                models = client.get_models()
                return bool(models and models.data)
        except Exception as exc:
            logger.warning("GigaChat health check failed: %s", exc)
            return False

    async def describe_image(
        self,
        image_path: str,
        prompt: Optional[str] = None,
    ) -> str:
        """
        Описать изображение через GigaChat Vision API.

        Загружает изображение в хранилище GigaChat, отправляет запрос
        с attachment'ом и возвращает текстовое описание.

        Args:
            image_path: Путь к файлу изображения.
            prompt: Промпт для описания (по умолчанию из настроек).

        Returns:
            Текстовое описание изображения.

        Raises:
            FileNotFoundError: если файл не найден.
            RuntimeError: при ошибках GigaChat API.
        """
        import os as _os
        if not _os.path.exists(image_path):
            raise FileNotFoundError(f"Файл изображения не найден: {image_path}")

        if not prompt:
            prompt = ai_settings.GK_IMAGE_DESCRIPTION_PROMPT

        logger.info(
            "GigaChat describe_image: path=%s model=%s",
            image_path,
            self._model,
        )

        try:
            result = await asyncio.to_thread(
                self._describe_image_sync, image_path, prompt
            )
            logger.info(
                "GigaChat describe_image success: path=%s result_length=%d",
                image_path,
                len(result),
            )
            return result
        except Exception as exc:
            logger.error(
                "GigaChat describe_image error: path=%s error=%s",
                image_path,
                exc,
                exc_info=True,
            )
            raise RuntimeError(
                f"Ошибка описания изображения через GigaChat: {self._format_gigachat_error(exc)}"
            ) from exc

    def _describe_image_sync(self, image_path: str, prompt: str) -> str:
        """Синхронная обёртка описания изображения через GigaChat SDK."""
        from gigachat import GigaChat

        with GigaChat(**self._create_client_kwargs()) as client:
            # Загрузить изображение в хранилище GigaChat
            with open(image_path, "rb") as f:
                uploaded = client.upload_file(f, purpose="general")

            file_id = self._extract_uploaded_file_id(uploaded)
            logger.debug("GigaChat file uploaded: id=%s", file_id)

            # Отправить запрос с attachment
            result = client.chat({
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "attachments": [file_id],
                    }
                ],
                "temperature": 0.1,
            })

            content = result.choices[0].message.content

            # Удалить файл из хранилища после использования
            try:
                client.delete_file(file_id)
            except Exception as del_exc:
                logger.warning("Не удалось удалить файл из GigaChat: %s", del_exc)

            return content

    @staticmethod
    def _extract_uploaded_file_id(uploaded: Any) -> str:
        """Достать идентификатор файла из ответа SDK с учётом разных версий моделей."""
        file_id = getattr(uploaded, "id", None) or getattr(uploaded, "id_", None)

        if not file_id and hasattr(uploaded, "model_dump"):
            try:
                payload = uploaded.model_dump()
                file_id = payload.get("id") or payload.get("id_")
            except Exception:
                file_id = None

        if not file_id and hasattr(uploaded, "dict"):
            try:
                payload = uploaded.dict()
                file_id = payload.get("id") or payload.get("id_")
            except Exception:
                file_id = None

        if not file_id:
            raise AttributeError("Не удалось определить идентификатор загруженного файла GigaChat")

        return str(file_id)

    async def _call_gigachat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        model_override: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> str:
        """
        Выполнить вызов к GigaChat API через библиотеку gigachat.

        Args:
            messages: Список сообщений диалога.
            temperature: Температура генерации.
            model_override: Переопределение модели.
            user_id: ID пользователя для логирования.

        Returns:
            Текстовый контент ответа.
        """
        from gigachat import GigaChat
        from gigachat.models import Chat, Messages, MessagesRole

        client_kwargs = self._create_client_kwargs()
        if model_override:
            client_kwargs["model"] = model_override

        # Конвертируем формат сообщений
        giga_messages = []
        for msg in messages:
            role_str = msg.get("role", "user")
            role = {
                "system": MessagesRole.SYSTEM,
                "user": MessagesRole.USER,
                "assistant": MessagesRole.ASSISTANT,
            }.get(role_str, MessagesRole.USER)
            giga_messages.append(Messages(role=role, content=msg.get("content", "")))

        chat_request = Chat(
            messages=giga_messages,
            temperature=temperature,
        )

        request_text = json.dumps(messages, ensure_ascii=False)

        try:
            result = await asyncio.to_thread(
                self._call_gigachat_sync, client_kwargs, chat_request
            )
        except Exception as exc:
            logger.error(
                "GigaChat API error: type=%s error=%s",
                type(exc).__name__,
                exc,
            )
            raise LLMProviderTemporaryError(
                f"Временная ошибка GigaChat: {exc}"
            ) from exc

        return result

    @staticmethod
    def _call_gigachat_sync(client_kwargs: Dict[str, Any], chat_request: Any) -> str:
        """Синхронный вызов GigaChat API."""
        from gigachat import GigaChat

        with GigaChat(**client_kwargs) as client:
            response = client.chat(chat_request)
            content = response.choices[0].message.content
            return content or ""


# =============================================
# Фабрика провайдеров
# =============================================

_providers: Dict[str, type] = {
    "deepseek": DeepSeekProvider,
    "gigachat": GigaChatProvider,
}


def register_provider(name: str, provider_class: type) -> None:
    """
    Зарегистрировать новый LLM-провайдер.

    Args:
        name: Уникальное имя провайдера.
        provider_class: Класс, наследующий LLMProvider.
    """
    _providers[name] = provider_class


def get_provider(provider_name: Optional[str] = None) -> LLMProvider:
    """
    Получить экземпляр LLM-провайдера по имени.

    Args:
        provider_name: Имя провайдера (по умолчанию из настроек AI_PROVIDER).

    Returns:
        Экземпляр LLMProvider.

    Raises:
        ValueError: если провайдер не зарегистрирован.
    """
    name = provider_name or ai_settings.AI_PROVIDER
    provider_class = _providers.get(name)

    if provider_class is None:
        available = ", ".join(_providers.keys())
        raise ValueError(
            f"LLM-провайдер '{name}' не найден. Доступные: {available}"
        )

    return provider_class()
