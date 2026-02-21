"""
test_context_manager.py — тесты для менеджера контекста AI-диалога.
"""
import time
import unittest

from src.sbs_helper_telegram_bot.ai_router.context_manager import (
    ConversationContextManager,
)


class TestConversationContextManager(unittest.TestCase):
    """Тесты для ConversationContextManager."""

    def test_empty_context(self):
        """Пустой контекст для нового пользователя."""
        cm = ConversationContextManager(max_messages=5, ttl_seconds=600)
        messages = cm.get_messages(user_id=1)
        self.assertEqual(messages, [])
        self.assertFalse(cm.has_context(user_id=1))

    def test_add_and_get_messages(self):
        """Добавление и получение сообщений."""
        cm = ConversationContextManager(max_messages=5, ttl_seconds=600)

        cm.add_message(1, "user", "Привет")
        cm.add_message(1, "assistant", "Здравствуйте!")

        messages = cm.get_messages(1)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "Привет")
        self.assertEqual(messages[1]["role"], "assistant")

    def test_max_messages_limit(self):
        """Ограничение по максимальному числу сообщений."""
        cm = ConversationContextManager(max_messages=3, ttl_seconds=600)

        cm.add_message(1, "user", "msg1")
        cm.add_message(1, "assistant", "reply1")
        cm.add_message(1, "user", "msg2")
        cm.add_message(1, "assistant", "reply2")  # 4-е — выталкивает первое

        messages = cm.get_messages(1)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["content"], "reply1")

    def test_ttl_expiry(self):
        """Сообщения устаревают после TTL."""
        cm = ConversationContextManager(max_messages=5, ttl_seconds=1)

        cm.add_message(1, "user", "старое сообщение")
        time.sleep(1.1)

        messages = cm.get_messages(1)
        self.assertEqual(len(messages), 0)
        self.assertFalse(cm.has_context(1))

    def test_clear_user(self):
        """Очистка контекста конкретного пользователя."""
        cm = ConversationContextManager(max_messages=5, ttl_seconds=600)

        cm.add_message(1, "user", "msg1")
        cm.add_message(2, "user", "msg2")

        cm.clear(1)

        self.assertEqual(len(cm.get_messages(1)), 0)
        self.assertEqual(len(cm.get_messages(2)), 1)

    def test_clear_all(self):
        """Полная очистка всех контекстов."""
        cm = ConversationContextManager(max_messages=5, ttl_seconds=600)

        cm.add_message(1, "user", "msg1")
        cm.add_message(2, "user", "msg2")

        cm.clear_all()

        self.assertEqual(len(cm.get_messages(1)), 0)
        self.assertEqual(len(cm.get_messages(2)), 0)

    def test_has_context(self):
        """Проверка наличия контекста."""
        cm = ConversationContextManager(max_messages=5, ttl_seconds=600)

        self.assertFalse(cm.has_context(1))
        cm.add_message(1, "user", "msg")
        self.assertTrue(cm.has_context(1))

    def test_different_users_isolated(self):
        """Контексты разных пользователей изолированы."""
        cm = ConversationContextManager(max_messages=5, ttl_seconds=600)

        cm.add_message(1, "user", "user1_msg")
        cm.add_message(2, "user", "user2_msg")

        msgs_1 = cm.get_messages(1)
        msgs_2 = cm.get_messages(2)

        self.assertEqual(len(msgs_1), 1)
        self.assertEqual(msgs_1[0]["content"], "user1_msg")
        self.assertEqual(len(msgs_2), 1)
        self.assertEqual(msgs_2[0]["content"], "user2_msg")

    def test_message_format(self):
        """Формат сообщений для LLM API."""
        cm = ConversationContextManager(max_messages=5, ttl_seconds=600)
        cm.add_message(1, "user", "test")

        messages = cm.get_messages(1)
        self.assertIn("role", messages[0])
        self.assertIn("content", messages[0])
        self.assertEqual(len(messages[0]), 2)


if __name__ == "__main__":
    unittest.main()
