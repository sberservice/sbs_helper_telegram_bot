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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import src.common.database as database
from src.common.pii_masking import mask_sensitive_data

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings

logger = logging.getLogger(__name__)


# =============================================
# Результат классификации
# =============================================

@dataclass
class ClassificationResult:
    """Результат классификации пользовательского сообщения."""

    intent: str
    """Определённое намерение (upos_error_lookup, ticket_validation, и т.д.)."""

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
    ) -> str:
        """
        Получить свободный текстовый ответ от LLM.

        Args:
            messages: Список сообщений диалога [{role, content}, ...].
            system_prompt: Системный промпт.

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
            # Для длинных заявок (ticket_validation) увеличиваем бюджет токенов,
            # чтобы JSON-ответ не обрезался до закрывающих скобок.
            raw = await self._call_api(
                full_messages,
                temperature=0.1,
                max_tokens=1024,
                purpose="classification",
                user_id=user_id,
            )
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
    ) -> str:
        """Получить свободный текстовый ответ через DeepSeek API."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        try:
            raw = await self._call_api(
                full_messages,
                temperature=0.7,
                max_tokens=1024,
                purpose=purpose,
                user_id=user_id,
            )
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

        request_payload_text = json.dumps(messages, ensure_ascii=False)

        self._log_model_request(
            purpose=purpose,
            model_name=str(payload.get("model") or ""),
            temperature=temperature,
            max_tokens=max_tokens,
            messages=messages,
        )

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
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

        if (
            allow_empty_content_retry
            and not str(content or "").strip()
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
            )

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
        """Сохранить полный prompt/response модели в БД с маскированием PII."""
        if not self._is_db_model_io_logging_enabled():
            return

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
    ) -> None:
        """Записать в лог payload, отправляемый в модель."""
        if not self._is_model_io_logging_enabled():
            return

        serialized_messages = self._truncate_for_log(
            json.dumps(messages, ensure_ascii=False)
        )
        logger.info(
            "LLM request payload: provider=%s purpose=%s model=%s temperature=%.2f max_tokens=%s messages=%s",
            self.name,
            purpose,
            model_name,
            temperature,
            max_tokens,
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
                    direct = DeepSeekProvider._extract_direct_answer_fallback(raw, elapsed_ms)
                    if direct is not None:
                        return direct
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
                direct = DeepSeekProvider._extract_direct_answer_fallback(raw, elapsed_ms)
                if direct is not None:
                    return direct
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

        intent = str(parsed.get("intent", "unknown"))
        confidence = float(parsed.get("confidence", 0.0))
        parameters = parsed.get("parameters", {})
        explain_code = str(parsed.get("explain_code", "PARSED_OK"))

        # Ограничиваем confidence диапазоном [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        if not isinstance(parameters, dict):
            parameters = {}

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

    @staticmethod
    def _extract_direct_answer_fallback(
        raw: str,
        elapsed_ms: int,
    ) -> Optional[ClassificationResult]:
        """
        Обработать fallback, когда вместо JSON пришёл готовый текстовый ответ.

        Применяется только для достаточно длинных ответов, чтобы не подменять
        короткие системные фразы/ошибки.
        """
        candidate = (raw or "").strip()
        if not candidate:
            return None

        # Не перехватываем короткие служебные ответы и потенциальные JSON-куски.
        if len(candidate) < 80:
            return None
        if candidate.startswith("{") or candidate.startswith("```"):
            return None

        # Должны присутствовать пробелы и буквы (похоже на нормальный текст).
        if " " not in candidate or not re.search(r"[A-Za-zА-Яа-яЁё]", candidate):
            return None

        logger.warning(
            "Использован direct-text fallback для классификации (len=%d)",
            len(candidate),
        )

        return ClassificationResult(
            intent="general_chat",
            confidence=0.85,
            parameters={"direct_answer": candidate[:4000]},
            explain_code="DIRECT_TEXT_FALLBACK",
            raw_response=raw,
            response_time_ms=elapsed_ms,
        )


# =============================================
# Фабрика провайдеров
# =============================================

_providers: Dict[str, type] = {
    "deepseek": DeepSeekProvider,
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
