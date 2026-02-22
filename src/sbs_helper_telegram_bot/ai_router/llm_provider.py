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
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - start_time) * 1000)
            logger.error(
                "DeepSeek classify error: %s (elapsed=%dms)", exc, elapsed
            )
            raise

        elapsed = int((time.monotonic() - start_time) * 1000)

        return self._parse_classification(raw, elapsed)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str,
    ) -> str:
        """Получить свободный текстовый ответ через DeepSeek API."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        try:
            raw = await self._call_api(
                full_messages,
                temperature=0.7,
                max_tokens=1024,
                purpose="response",
            )
        except Exception as exc:
            logger.error("DeepSeek chat error: %s", exc)
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
        payload = {
            "model": self._resolve_model(purpose=purpose),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

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
            response.raise_for_status()

        data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            logger.error("Некорректный ответ DeepSeek API: %s", data)
            raise ValueError(f"Некорректная структура ответа API: {exc}") from exc

        return content

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
