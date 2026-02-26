"""Тесты резолвера сообщений AI-маршрутизатора."""

import unittest

from src.sbs_helper_telegram_bot.ai_router import messages as ai_messages


class TestAiMessageResolver(unittest.TestCase):
    """Проверки получения сообщений по ключам с fallback."""

    def tearDown(self):
        """Сбросить внешний резолвер после каждого теста."""
        ai_messages.set_ai_message_resolver(None)

    def test_get_ai_message_by_key_uses_default(self):
        """При отсутствии внешнего резолвера возвращается default-текст."""
        value = ai_messages.get_ai_message_by_key(ai_messages.AI_MESSAGE_KEY_PROCESSING)
        self.assertEqual(value, ai_messages.MESSAGE_AI_PROCESSING)

    def test_get_ai_message_by_key_uses_external_resolver(self):
        """Внешний резолвер может переопределять сообщение по ключу."""

        def _resolver(message_key: str):
            if message_key == ai_messages.AI_MESSAGE_KEY_PREFILTERING_DOCUMENTS:
                return "⏳ _Промежуточный текст из внешнего источника_"
            return None

        ai_messages.set_ai_message_resolver(_resolver)

        value = ai_messages.get_ai_message_by_key(ai_messages.AI_MESSAGE_KEY_PREFILTERING_DOCUMENTS)
        self.assertEqual(value, "⏳ _Промежуточный текст из внешнего источника_")

    def test_get_ai_message_by_key_falls_back_on_empty_external_value(self):
        """Пустое значение внешнего резолвера не ломает fallback."""

        def _resolver(_message_key: str):
            return "  "

        ai_messages.set_ai_message_resolver(_resolver)

        value = ai_messages.get_ai_message_by_key(ai_messages.AI_MESSAGE_KEY_REQUESTING_AUGMENTED_PAYLOAD)
        self.assertEqual(value, ai_messages.MESSAGE_AI_REQUESTING_AUGMENTED_PAYLOAD)

    def test_get_ai_status_message_returns_none_for_unknown_status(self):
        """Неизвестный AI-статус возвращает None."""
        value = ai_messages.get_ai_status_message("unknown_status")
        self.assertIsNone(value)


if __name__ == "__main__":
    unittest.main()
