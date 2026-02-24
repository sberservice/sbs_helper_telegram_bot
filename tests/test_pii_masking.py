"""test_pii_masking.py — тесты маскировки чувствительных данных."""

import unittest

from src.common.pii_masking import mask_sensitive_data


class TestPiiMasking(unittest.TestCase):
    """Тесты маскировки PII в логируемом тексте."""

    def test_masks_email_phone_inn_snils(self):
        """Email, телефон, ИНН и СНИЛС маскируются предсказуемыми токенами."""
        source = (
            "email: admin@test.ru, phone: +7 (999) 111-22-33, "
            "inn: 7707083893, snils: 112-233-445 95"
        )
        masked = mask_sensitive_data(source)

        self.assertIn("[EMAIL_REDACTED]", masked)
        self.assertIn("[PHONE_REDACTED]", masked)
        self.assertIn("[INN_REDACTED]", masked)
        self.assertIn("[SNILS_REDACTED]", masked)

        self.assertNotIn("admin@test.ru", masked)
        self.assertNotIn("111-22-33", masked)
        self.assertNotIn("7707083893", masked)
        self.assertNotIn("112-233-445 95", masked)

    def test_keeps_regular_text(self):
        """Обычный текст без PII не изменяется."""
        source = "Просто техническое сообщение без персональных данных"
        self.assertEqual(mask_sensitive_data(source), source)


if __name__ == "__main__":
    unittest.main()
