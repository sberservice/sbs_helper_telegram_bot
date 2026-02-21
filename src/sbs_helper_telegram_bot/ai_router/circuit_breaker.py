"""
circuit_breaker.py — защита от каскадных отказов LLM-провайдера.

Реализует паттерн Circuit Breaker с тремя состояниями:
- CLOSED: нормальная работа, ошибки считаются
- OPEN: провайдер недоступен, запросы блокируются
- HALF_OPEN: пробный запрос для проверки восстановления

При серии ошибок провайдера автоматически переключается в
deterministic-only режим (OPEN), возвращая управление вызывающему коду.
"""

import logging
import time
from enum import Enum
from typing import Optional

from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Состояния circuit breaker."""

    CLOSED = "closed"
    """Нормальная работа — запросы проходят."""

    OPEN = "open"
    """Провайдер недоступен — запросы блокируются."""

    HALF_OPEN = "half_open"
    """Тестирование восстановления — один пробный запрос."""


class CircuitBreaker:
    """
    Circuit breaker для защиты от каскадных отказов LLM-провайдера.

    При достижении порога последовательных ошибок переходит в состояние
    OPEN, блокируя запросы на заданное время. После истечения времени
    восстановления переходит в HALF_OPEN, пропуская один пробный запрос.
    """

    def __init__(
        self,
        failure_threshold: Optional[int] = None,
        recovery_seconds: Optional[int] = None,
    ):
        """
        Инициализация circuit breaker.

        Args:
            failure_threshold: Число последовательных ошибок для перехода в OPEN.
            recovery_seconds: Время до перехода из OPEN в HALF_OPEN (секунды).
        """
        self._failure_threshold = (
            failure_threshold or ai_settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD
        )
        self._recovery_seconds = (
            recovery_seconds or ai_settings.CIRCUIT_BREAKER_RECOVERY_SECONDS
        )

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._opened_at: float = 0.0

    @property
    def state(self) -> CircuitState:
        """Текущее состояние circuit breaker."""
        # Проверяем, не пора ли перейти из OPEN в HALF_OPEN
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self._recovery_seconds:
                logger.info(
                    "Circuit breaker: OPEN → HALF_OPEN "
                    "(прошло %.1f сек, порог %d сек)",
                    elapsed,
                    self._recovery_seconds,
                )
                self._state = CircuitState.HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        """Текущее число последовательных ошибок."""
        return self._failure_count

    def is_available(self) -> bool:
        """
        Проверить, можно ли отправлять запрос.

        Returns:
            True если circuit breaker в состоянии CLOSED или HALF_OPEN.
        """
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        """
        Зафиксировать успешный запрос.

        Сбрасывает счётчик ошибок. Переводит из HALF_OPEN обратно в CLOSED.
        """
        prev_state = self._state
        self._failure_count = 0
        self._state = CircuitState.CLOSED

        if prev_state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker: HALF_OPEN → CLOSED (провайдер восстановился)")

    def record_failure(self) -> None:
        """
        Зафиксировать ошибку запроса.

        Увеличивает счётчик ошибок. При достижении порога переводит в OPEN.
        Из HALF_OPEN сразу переводит обратно в OPEN.
        """
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            # В HALF_OPEN одна ошибка = обратно в OPEN
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker: HALF_OPEN → OPEN (пробный запрос провалился)"
            )
        elif self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker: CLOSED → OPEN "
                "(последовательных ошибок: %d, порог: %d). "
                "AI-маршрутизация деградирована в deterministic-only режим.",
                self._failure_count,
                self._failure_threshold,
            )

    def reset(self) -> None:
        """Сбросить circuit breaker в начальное состояние."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._opened_at = 0.0
        logger.info("Circuit breaker: сброшен в CLOSED")

    def get_status_info(self) -> dict:
        """
        Получить информацию о текущем состоянии для админ-панели.

        Returns:
            Словарь с состоянием, счётчиком ошибок и оставшимся временем.
        """
        current_state = self.state
        info = {
            "state": current_state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self._failure_threshold,
            "recovery_seconds": self._recovery_seconds,
        }

        if current_state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            remaining = max(0, self._recovery_seconds - elapsed)
            info["recovery_remaining_seconds"] = int(remaining)

        return info
