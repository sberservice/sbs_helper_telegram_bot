"""Тесты redirect-форматирования GroupResponder."""

import unittest

from src.group_knowledge.responder import GroupResponder


class TestGKResponderRedirectFormatting(unittest.TestCase):
    """Проверка формата question/answer для redirect test mode."""

    def setUp(self):
        """Подготовить responder с заглушкой конфигурации."""
        self.responder = GroupResponder(
            dry_run=True,
            qa_service=object(),
            redirect_output_group={"id": -1001234567890},
        )

    def test_build_redirect_question_message_contains_source_and_question(self):
        """Сообщение вопроса содержит метаданные источника и блок вопроса."""
        text = self.responder._build_redirect_question_message(
            question_text="Почему касса не печатает чек?",
            source_group_id=-100500,
            source_group_title="Тестовая группа",
            sender_label="Иван Иванов",
            source_message_id=42,
        )

        self.assertIn("GK REDIRECT TEST MODE", text)
        self.assertIn("Источник: Тестовая группа (-100500)", text)
        self.assertIn("Отправитель: Иван Иванов", text)
        self.assertIn("Вопрос:", text)
        self.assertIn("Почему касса не печатает чек?", text)
        self.assertNotIn("\nОтвет:\n", text)

    def test_build_redirect_answer_message_contains_only_answer_block(self):
        """Сообщение ответа содержит только ответный блок."""
        text = self.responder._build_redirect_answer_message("Перезапустите ККТ и проверьте ФН")
        self.assertTrue(text.startswith("Ответ:\n"))
        self.assertIn("Перезапустите ККТ", text)


if __name__ == "__main__":
    unittest.main()
