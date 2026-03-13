"""Тесты для scripts.telethon_login_debug."""

import unittest

from scripts.telethon_login_debug import _normalize_phone


class TestTelethonLoginDebug(unittest.TestCase):
    """Проверки нормализации номера телефона для Telethon-диагностики."""

    def test_normalize_phone_valid_with_spaces(self):
        """Корректный номер с пробелами нормализуется в E.164."""
        self.assertEqual(_normalize_phone(" +7 999 123 45 67 "), "+79991234567")

    def test_normalize_phone_invalid_without_plus(self):
        """Номер без + отклоняется с понятной ошибкой."""
        with self.assertRaises(ValueError):
            _normalize_phone("79991234567")

    def test_normalize_phone_invalid_too_short(self):
        """Слишком короткий номер отклоняется."""
        with self.assertRaises(ValueError):
            _normalize_phone("+12345")


if __name__ == "__main__":
    unittest.main()
