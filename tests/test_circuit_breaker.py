"""
test_circuit_breaker.py — тесты для circuit breaker AI-маршрутизации.
"""
import time
import unittest
from unittest.mock import patch

from src.sbs_helper_telegram_bot.ai_router.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)


class TestCircuitBreaker(unittest.TestCase):
    """Тесты для CircuitBreaker."""

    def test_initial_state_closed(self):
        """Начальное состояние — CLOSED."""
        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.is_available())

    def test_success_resets_counter(self):
        """Успешный запрос сбрасывает счётчик ошибок."""
        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10)
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.failure_count, 2)

        cb.record_success()
        self.assertEqual(cb.failure_count, 0)
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_threshold_opens_circuit(self):
        """Достижение порога ошибок переводит в OPEN."""
        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10)

        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.CLOSED)

        cb.record_failure()  # 3-я ошибка = порог
        self.assertEqual(cb.state, CircuitState.OPEN)
        self.assertFalse(cb.is_available())

    def test_open_blocks_requests(self):
        """В состоянии OPEN is_available() возвращает False."""
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=300)
        cb.record_failure()
        self.assertFalse(cb.is_available())

    def test_open_to_half_open_after_recovery(self):
        """После recovery_seconds переходит из OPEN в HALF_OPEN."""
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=1)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        # Ждём recovery
        time.sleep(1.1)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertTrue(cb.is_available())

    def test_half_open_success_closes(self):
        """Успех в HALF_OPEN переводит в CLOSED."""
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=1)
        cb.record_failure()
        time.sleep(1.1)
        # Transitions to HALF_OPEN after recovery
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        cb.record_success()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertTrue(cb.is_available())

    def test_half_open_failure_reopens(self):
        """Ошибка в HALF_OPEN возвращает в OPEN."""
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=1)
        cb.record_failure()
        time.sleep(1.1)
        # Trigger HALF_OPEN transition
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)

        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_reset(self):
        """Полный сброс возвращает в начальное состояние."""
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=300)
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)

        cb.reset()
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.failure_count, 0)
        self.assertTrue(cb.is_available())

    def test_get_status_info(self):
        """Информация для админ-панели содержит обязательные поля."""
        cb = CircuitBreaker(failure_threshold=5, recovery_seconds=300)
        info = cb.get_status_info()

        self.assertEqual(info["state"], "closed")
        self.assertEqual(info["failure_count"], 0)
        self.assertEqual(info["failure_threshold"], 5)
        self.assertEqual(info["recovery_seconds"], 300)

    def test_get_status_info_open_has_remaining(self):
        """В OPEN-состоянии информация содержит оставшееся время."""
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=300)
        cb.record_failure()

        info = cb.get_status_info()
        self.assertEqual(info["state"], "open")
        self.assertIn("recovery_remaining_seconds", info)
        self.assertGreater(info["recovery_remaining_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
