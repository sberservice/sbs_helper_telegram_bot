"""
test_rate_limiter.py — тесты для rate-limiter AI-маршрутизации.
"""
import time
import unittest

from src.sbs_helper_telegram_bot.ai_router.rate_limiter import AIRateLimiter


class TestAIRateLimiter(unittest.TestCase):
    """Тесты для AIRateLimiter."""

    def test_allows_under_limit(self):
        """Запросы ниже лимита разрешены."""
        limiter = AIRateLimiter(max_requests=5, window_seconds=60)

        for _ in range(5):
            allowed, remaining = limiter.check(user_id=1)
            self.assertTrue(allowed)
            self.assertIsNone(remaining)
            limiter.record(user_id=1)

    def test_blocks_over_limit(self):
        """Запросы сверх лимита блокируются."""
        limiter = AIRateLimiter(max_requests=3, window_seconds=60)

        for _ in range(3):
            limiter.record(user_id=1)

        allowed, remaining = limiter.check(user_id=1)
        self.assertFalse(allowed)
        self.assertIsNotNone(remaining)
        self.assertGreater(remaining, 0)

    def test_different_users_independent(self):
        """Лимиты для разных пользователей независимы."""
        limiter = AIRateLimiter(max_requests=2, window_seconds=60)

        limiter.record(user_id=1)
        limiter.record(user_id=1)

        # User 1 заблокирован
        allowed1, _ = limiter.check(user_id=1)
        self.assertFalse(allowed1)

        # User 2 свободен
        allowed2, _ = limiter.check(user_id=2)
        self.assertTrue(allowed2)

    def test_window_expiry(self):
        """Записи за пределами окна очищаются."""
        limiter = AIRateLimiter(max_requests=1, window_seconds=1)
        limiter.record(user_id=1)

        allowed, _ = limiter.check(user_id=1)
        self.assertFalse(allowed)

        time.sleep(1.1)

        allowed, _ = limiter.check(user_id=1)
        self.assertTrue(allowed)

    def test_get_usage(self):
        """Статистика использования корректна."""
        limiter = AIRateLimiter(max_requests=10, window_seconds=60)
        limiter.record(user_id=1)
        limiter.record(user_id=1)

        usage = limiter.get_usage(user_id=1)
        self.assertEqual(usage["used"], 2)
        self.assertEqual(usage["max"], 10)
        self.assertEqual(usage["window_seconds"], 60)

    def test_reset_user(self):
        """Сброс для конкретного пользователя."""
        limiter = AIRateLimiter(max_requests=1, window_seconds=60)
        limiter.record(user_id=1)
        limiter.record(user_id=2)

        limiter.reset(user_id=1)

        allowed1, _ = limiter.check(user_id=1)
        self.assertTrue(allowed1)

        allowed2, _ = limiter.check(user_id=2)
        self.assertFalse(allowed2)

    def test_reset_all(self):
        """Полный сброс очищает все данные."""
        limiter = AIRateLimiter(max_requests=1, window_seconds=60)
        limiter.record(user_id=1)
        limiter.record(user_id=2)

        limiter.reset()

        allowed1, _ = limiter.check(user_id=1)
        allowed2, _ = limiter.check(user_id=2)
        self.assertTrue(allowed1)
        self.assertTrue(allowed2)

    def test_remaining_seconds_positive(self):
        """Оставшиеся секунды — положительное число."""
        limiter = AIRateLimiter(max_requests=1, window_seconds=30)
        limiter.record(user_id=1)

        allowed, remaining = limiter.check(user_id=1)
        self.assertFalse(allowed)
        self.assertGreater(remaining, 0)
        self.assertLessEqual(remaining, 31)

    def test_empty_user_check(self):
        """Проверка для пользователя без записей — разрешено."""
        limiter = AIRateLimiter(max_requests=5, window_seconds=60)

        allowed, remaining = limiter.check(user_id=999)
        self.assertTrue(allowed)
        self.assertIsNone(remaining)


if __name__ == "__main__":
    unittest.main()
