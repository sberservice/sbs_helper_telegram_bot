"""Тесты для даты последнего обновления в модуле КТР."""

import unittest
from unittest.mock import patch

from src.sbs_helper_telegram_bot.ktr import messages
from src.sbs_helper_telegram_bot.ktr import settings
from src.sbs_helper_telegram_bot.ktr import ktr_bot_part


class TestKtrEntryMessage(unittest.TestCase):
    """Проверки стартового сообщения модуля КТР."""

    def test_entry_message_contains_last_update_date(self):
        """Показывает дату обновления, если она задана."""
        text = messages.get_entry_message("15.02.2026")

        self.assertIn("Последнее обновление кодов", text)
        self.assertIn("15\\.02\\.2026", text)
        self.assertIn("📬 Обратная связь", text)

    def test_entry_message_uses_default_when_date_missing(self):
        """Показывает маркер по умолчанию, если дата не задана."""
        text = messages.get_entry_message(None)

        self.assertIn(messages.MESSAGE_KTR_LAST_UPDATE_UNKNOWN, text)
        self.assertIn("более свежий файл КТР", text)


class TestKtrLastUpdateSettingHelpers(unittest.TestCase):
    """Проверки helper-функций чтения/записи даты обновления КТР."""

    @patch("src.sbs_helper_telegram_bot.ktr.ktr_bot_part.bot_settings")
    def test_get_ktr_last_update_date_returns_stripped_value(self, mock_bot_settings):
        """Возвращает дату без лишних пробелов."""
        mock_bot_settings.get_setting.return_value = " 12.01.2026  "

        result = ktr_bot_part.get_ktr_last_update_date()

        self.assertEqual(result, "12.01.2026")
        mock_bot_settings.get_setting.assert_called_once_with(settings.KTR_LAST_UPDATE_SETTING_KEY)

    @patch("src.sbs_helper_telegram_bot.ktr.ktr_bot_part.bot_settings")
    def test_set_ktr_last_update_date_uses_bot_settings_key(self, mock_bot_settings):
        """Сохраняет дату в ожидаемый ключ bot_settings."""
        mock_bot_settings.set_setting.return_value = True

        result = ktr_bot_part.set_ktr_last_update_date("13.01.2026", 777)

        self.assertTrue(result)
        mock_bot_settings.set_setting.assert_called_once_with(
            settings.KTR_LAST_UPDATE_SETTING_KEY,
            "13.01.2026",
            updated_by=777
        )


if __name__ == "__main__":
    unittest.main()
