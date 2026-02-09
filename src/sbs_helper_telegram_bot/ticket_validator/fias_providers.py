"""
Провайдеры проверки адресов по ФИАС.

Содержит подключаемую архитектуру провайдеров для проверки адресов в ФИАС
(Федеральная информационная адресная система) или похожих базах адресов.

Паттерн провайдера позволяет менять API без изменения логики правил.
Текущие провайдеры:

- **DaDataFIASProvider** — использует DaData Suggestions API (https://dadata.ru/api/suggest/address/).
    Бесплатный тариф: до 10 000 запросов в день. Требуется API-ключ в переменной
    окружения ``DADATA_API_KEY``.

Чтобы добавить новый провайдер, унаследуйтесь от :class:`BaseFIASProvider`
и реализуйте :meth:`validate_address`.

Пример использования::

        from .fias_providers import get_fias_provider

        provider = get_fias_provider()          # возвращает активный провайдер
        result   = provider.validate_address("Москва, ул Льва Толстого 16")
        if result.is_valid:
                print("Адрес найден в ФИАС:", result.suggested_address)
        else:
                print("Адрес не найден:", result.error_message)
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Датаклассы
# ---------------------------------------------------------------------------

@dataclass
class FIASValidationResult:
    """Результат проверки адреса по ФИАС.

    Attributes:
        is_valid: ``True``, если API вернул хотя бы одну подсказку.
        address_query: исходная строка адреса, которую проверяли.
        suggested_address: лучшая подсказка от API (если есть).
        suggestions_count: общее количество подсказок.
        all_suggestions: список сырых подсказок (для отладки).
        error_message: человекочитаемая ошибка при провале проверки или сбое API.
        provider_name: имя провайдера, выполнявшего проверку.
        fias_id: идентификатор ФИАС для лучшей подсказки (если доступно).
        fias_level: уровень детализации ФИАС для лучшей подсказки (если доступно).
    """

    is_valid: bool
    address_query: str = ""
    suggested_address: Optional[str] = None
    suggestions_count: int = 0
    all_suggestions: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    provider_name: str = ""
    fias_id: Optional[str] = None
    fias_level: Optional[str] = None


# ---------------------------------------------------------------------------
# Абстрактный базовый провайдер
# ---------------------------------------------------------------------------

class BaseFIASProvider(ABC):
    """Абстрактный базовый класс для провайдеров проверки адресов по ФИАС.

    Каждый конкретный провайдер **обязан** реализовать :meth:`validate_address`.

    Дополнительно можно переопределить:
    * :attr:`provider_name` — человекочитаемая метка для логов/сообщений.
    * :meth:`is_configured` — возвращает ``False``, если не хватает учётных данных,
        чтобы можно было завершить проверку заранее.
    """

    provider_name: str = "base"

    @abstractmethod
    def validate_address(self, address: str) -> FIASValidationResult:
        """Проверить *address* по базе ФИАС.

        Args:
            address: адрес в свободной форме для поиска.

        Returns:
            :class:`FIASValidationResult` с результатом проверки.
        """

    def is_configured(self) -> bool:  # noqa: D401
        """Вернуть ``True``, если провайдер настроен и есть все ключи."""
        return True


# ---------------------------------------------------------------------------
# Провайдер DaData
# ---------------------------------------------------------------------------

class DaDataFIASProvider(BaseFIASProvider):
    """Проверка ФИАС через DaData Suggestions API.

    Справка по API: https://dadata.ru/api/suggest/address/

    Провайдер отправляет POST-запрос на ``/suggest/address`` и считает адрес
    **валидным**, если массив ``suggestions`` в ответе не пуст.

    Настройка (переменные окружения):
        * ``DADATA_API_KEY`` — **обязательно**. API-ключ DaData.
        * ``DADATA_API_URL`` — *опционально*. Переопределяет базовый URL
          (по умолчанию ``https://suggestions.dadata.ru/suggestions/api/4_1/rs``).

    Лимиты (бесплатный тариф):
        * 10 000 запросов / день
        * 30 запросов / секунду на IP
        * 60 новых соединений / минуту на IP

    Важные HTTP-статусы:
        * 403 — неверный ключ **или** превышена суточная квота
        * 429 — превышение лимита запросов в секунду
    """

    provider_name: str = "dadata"

    # Эндпоинт по умолчанию — подсказки адресов, не только ФИАС,
    # согласно рекомендации DaData (``/suggest/address`` более полный).
    DEFAULT_API_URL = (
        "https://suggestions.dadata.ru/suggestions/api/4_1/rs"
    )

    SUGGEST_ADDRESS_PATH = "/suggest/address"

    # Таймаут каждого HTTP-запроса (сек.).
    REQUEST_TIMEOUT = 10

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("DADATA_API_KEY", "")
        self.api_url = (
            api_url
            or os.getenv("DADATA_API_URL", "")
            or self.DEFAULT_API_URL
        )

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Проверить, что API-ключ задан."""
        return bool(self.api_key)

    def validate_address(self, address: str) -> FIASValidationResult:
        """Запросить DaData и вернуть :class:`FIASValidationResult`.

        Если API-ключ отсутствует или запрос завершился ошибкой, результат
        помечается как *valid* (fail-open), чтобы ошибка конфигурации не
        блокировала все заявки. Детали пишутся в ``error_message``.
        """
        if not self.is_configured():
            logger.warning("DaData API key is not configured — skipping FIAS check")
            return FIASValidationResult(
                is_valid=True,
                address_query=address,
                error_message="DADATA_API_KEY не настроен — проверка ФИАС пропущена",
                provider_name=self.provider_name,
            )

        url = self.api_url.rstrip("/") + self.SUGGEST_ADDRESS_PATH

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Token {self.api_key}",
        }

        payload = {
            "query": address,
            "count": 1,
        }

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.REQUEST_TIMEOUT,
            )

            if response.status_code == 403:
                logger.error(
                    "DaData API returned 403 — invalid key or daily quota exceeded"
                )
                return FIASValidationResult(
                    is_valid=True,  # Разрешаем по умолчанию
                    address_query=address,
                    error_message="Ошибка авторизации DaData (403) — проверка ФИАС пропущена",
                    provider_name=self.provider_name,
                )

            if response.status_code == 429:
                logger.warning("DaData API rate-limit hit (429)")
                return FIASValidationResult(
                    is_valid=True,  # Разрешаем по умолчанию
                    address_query=address,
                    error_message="Превышен лимит запросов DaData (429) — проверка ФИАС пропущена",
                    provider_name=self.provider_name,
                )

            response.raise_for_status()

            data = response.json()
            suggestions = data.get("suggestions", [])

            if suggestions:
                best = suggestions[0]
                return FIASValidationResult(
                    is_valid=True,
                    address_query=address,
                    suggested_address=best.get("value", ""),
                    suggestions_count=len(suggestions),
                    all_suggestions=[s.get("value", "") for s in suggestions],
                    provider_name=self.provider_name,
                    fias_id=(best.get("data") or {}).get("fias_id"),
                    fias_level=str((best.get("data") or {}).get("fias_level", "")),
                )
            else:
                return FIASValidationResult(
                    is_valid=False,
                    address_query=address,
                    suggestions_count=0,
                    error_message="Адрес не найден в базе ФИАС",
                    provider_name=self.provider_name,
                )

        except requests.exceptions.Timeout:
            logger.error("DaData API request timed out")
            return FIASValidationResult(
                is_valid=True,  # Разрешаем по умолчанию
                address_query=address,
                error_message="Таймаут запроса к DaData — проверка ФИАС пропущена",
                provider_name=self.provider_name,
            )

        except requests.exceptions.RequestException as exc:
            logger.error("DaData API request failed: %s", exc)
            return FIASValidationResult(
                is_valid=True,  # Разрешаем по умолчанию
                address_query=address,
                error_message=f"Ошибка запроса к DaData: {exc}",
                provider_name=self.provider_name,
            )

        except (ValueError, KeyError) as exc:
            logger.error("Failed to parse DaData response: %s", exc)
            return FIASValidationResult(
                is_valid=True,  # Разрешаем по умолчанию
                address_query=address,
                error_message=f"Ошибка разбора ответа DaData: {exc}",
                provider_name=self.provider_name,
            )


# ---------------------------------------------------------------------------
# Реестр провайдеров и фабрика
# ---------------------------------------------------------------------------

# Сопоставление имён провайдеров и классов. Расширяйте при добавлении новых.
_PROVIDER_REGISTRY: dict[str, type[BaseFIASProvider]] = {
    "dadata": DaDataFIASProvider,
}

# Синглтон уровня модуля — лениво инициализируется в :func:`get_fias_provider`.
_active_provider: Optional[BaseFIASProvider] = None


def get_fias_provider(
    provider_name: Optional[str] = None,
) -> BaseFIASProvider:
    """Вернуть активный провайдер ФИАС (синглтон).

    Провайдер выбирается в следующем порядке приоритета:

    1. аргумент *provider_name* (явное переопределение).
    2. переменная окружения ``FIAS_PROVIDER``.
    3. значение по умолчанию ``"dadata"``.

    Экземпляр кэшируется, поэтому последующие вызовы возвращают один
    и тот же объект (и одну и ту же HTTP-сессию, если провайдер её использует).
    """
    global _active_provider  # noqa: PLW0603

    desired = (
        provider_name
        or os.getenv("FIAS_PROVIDER", "")
        or "dadata"
    ).lower()

    # Возвращаем кэшированный экземпляр, если имя совпадает
    if _active_provider is not None and _active_provider.provider_name == desired:
        return _active_provider

    provider_cls = _PROVIDER_REGISTRY.get(desired)
    if provider_cls is None:
        raise ValueError(
            f"Unknown FIAS provider '{desired}'. "
            f"Available: {', '.join(_PROVIDER_REGISTRY)}"
        )

    _active_provider = provider_cls()
    logger.info("FIAS provider initialised: %s", _active_provider.provider_name)
    return _active_provider


def reset_fias_provider() -> None:
    """Сбросить кэш провайдера (полезно в тестах)."""
    global _active_provider  # noqa: PLW0603
    _active_provider = None
