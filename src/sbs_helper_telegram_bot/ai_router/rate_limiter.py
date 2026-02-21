"""
rate_limiter.py — ограничение частоты AI-запросов на пользователя.

Реализует скользящее окно (sliding window) для защиты от спама
и контроля стоимости LLM-запросов. Работает в памяти процесса.
"""

import logging
import time
from collections import defaultdict, deque
from typing import Optional, Tuple

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings

logger = logging.getLogger(__name__)


class AIRateLimiter:
    """
    Rate-limiter на основе скользящего окна.

    Хранит временные метки запросов каждого пользователя в памяти.
    Проверяет, не превышен ли лимит запросов за заданное окно времени.
    """

    def __init__(
        self,
        max_requests: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ):
        """
        Инициализация rate-limiter.

        Args:
            max_requests: Максимальное число запросов за окно.
            window_seconds: Размер окна в секундах.
        """
        self._max_requests = max_requests or ai_settings.RATE_LIMIT_MAX_REQUESTS
        self._window_seconds = window_seconds or ai_settings.RATE_LIMIT_WINDOW_SECONDS
        self._user_timestamps: dict[int, deque[float]] = defaultdict(deque)

    def check(self, user_id: int) -> Tuple[bool, Optional[int]]:
        """
        Проверить, разрешён ли запрос для пользователя.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            Кортеж (разрешено, оставшиеся_секунды).
            Если разрешено — (True, None).
            Если нет — (False, секунды_до_освобождения).
        """
        now = time.monotonic()
        timestamps = self._user_timestamps[user_id]

        # Удаляем устаревшие временные метки за пределами окна
        cutoff = now - self._window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        if len(timestamps) >= self._max_requests:
            # Вычисляем, когда освободится самый старый слот
            oldest = timestamps[0]
            remaining = int(oldest + self._window_seconds - now) + 1
            return False, max(1, remaining)

        return True, None

    def record(self, user_id: int) -> None:
        """
        Записать факт выполнения AI-запроса.

        Args:
            user_id: Telegram ID пользователя.
        """
        now = time.monotonic()
        self._user_timestamps[user_id].append(now)

    def get_usage(self, user_id: int) -> dict:
        """
        Получить текущую статистику использования для пользователя.

        Args:
            user_id: Telegram ID пользователя.

        Returns:
            Словарь с информацией о текущем использовании.
        """
        now = time.monotonic()
        timestamps = self._user_timestamps[user_id]

        # Чистим устаревшие
        cutoff = now - self._window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()

        return {
            "used": len(timestamps),
            "max": self._max_requests,
            "window_seconds": self._window_seconds,
        }

    def reset(self, user_id: Optional[int] = None) -> None:
        """
        Сбросить счётчики. Если user_id указан — только для этого пользователя.

        Args:
            user_id: Telegram ID пользователя (None = сбросить всех).
        """
        if user_id is not None:
            self._user_timestamps.pop(user_id, None)
        else:
            self._user_timestamps.clear()
