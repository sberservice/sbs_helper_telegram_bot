"""
test_ai_router_escape.py — тесты экранирования MarkdownV2 для AI-ответов.

Проверяет корректную обработку спецсимволов и обратных слэшей
в ответах LLM перед отправкой через Telegram API.
"""

import unittest

from src.sbs_helper_telegram_bot.ai_router.messages import (
    escape_markdown_v2,
    format_ai_chat_response,
    format_rag_answer_markdown_v2,
)


class TestEscapeMarkdownV2(unittest.TestCase):
    """Тесты экранирования спецсимволов MarkdownV2 в AI-ответах."""

    def test_escape_all_special_chars(self):
        """Все спецсимволы MarkdownV2 экранируются обратным слэшем."""
        text = "_ * [ ] ( ) ~ ` > # + - = | { } . !"
        escaped = escape_markdown_v2(text)
        for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#',
                      '+', '-', '=', '|', '{', '}', '.', '!']:
            self.assertIn(f"\\{char}", escaped)

    def test_escape_backslash_before_special(self):
        """Обратный слэш перед спецсимволом экранируется отдельно от спецсимвола.

        Без этого фикса: \\! → \\\\! (сломанный MarkdownV2 — ! неэкранирован).
        С фиксом:        \\! → \\\\\\! (\\\\=экранированный бэкслеш, \\!=экранированный !).
        """
        text = "Конечно\\! Вот ответ."
        escaped = escape_markdown_v2(text)
        # В MarkdownV2: \\\\ = литеральный \, \\! = литеральный !
        self.assertIn("\\\\\\!", escaped)
        self.assertTrue(escaped.endswith("\\."))

    def test_escape_backslash_before_dot(self):
        """Обратный слэш перед точкой: \\. → \\\\\\.  (оба экранированы)."""
        text = "Пункт 1\\. Сделай это"
        escaped = escape_markdown_v2(text)
        self.assertIn("\\\\\\.", escaped)

    def test_escape_multiple_backslashes(self):
        """Обратные слэши в путях экранируются."""
        text = "C:\\Users\\test"
        escaped = escape_markdown_v2(text)
        self.assertEqual(escaped, "C:\\\\Users\\\\test")

    def test_escape_plain_text_no_change(self):
        """Текст без спецсимволов остаётся без изменений."""
        text = "Просто обычный текст"
        escaped = escape_markdown_v2(text)
        self.assertEqual(escaped, text)

    def test_escape_exclamation_mark(self):
        """Восклицательный знак экранируется."""
        text = "Важно!"
        escaped = escape_markdown_v2(text)
        self.assertEqual(escaped, "Важно\\!")

    def test_escape_dot(self):
        """Точка экранируется."""
        text = "Конец."
        escaped = escape_markdown_v2(text)
        self.assertEqual(escaped, "Конец\\.")

    def test_escape_llm_pre_escaped_markdown(self):
        """LLM иногда возвращает уже экранированный текст — не ломаем его."""
        text = "Use \\*bold\\* for emphasis!"
        escaped = escape_markdown_v2(text)
        # \\* → \\\\\\* (экранированный бэкслеш + экранированная звёздочка)
        self.assertIn("\\\\\\*", escaped)
        self.assertTrue(escaped.endswith("\\!"))

    def test_escape_mixed_content(self):
        """Смешанный контент: обычный текст + спецсимволы + бэкслеши."""
        text = "Ответ: 1. Да! 2. Нет\\?"
        escaped = escape_markdown_v2(text)
        self.assertIn("1\\.", escaped)
        self.assertIn("Да\\!", escaped)
        # \\ перед ? (? — не спецсимвол MarkdownV2)
        self.assertIn("Нет\\\\?", escaped)


class TestFormatAIChatResponse(unittest.TestCase):
    """Тесты форматирования AI-ответа для отправки в Telegram."""

    def test_format_adds_prefix(self):
        """Ответ содержит эмодзи-префикс 🤖."""
        result = format_ai_chat_response("Привет")
        self.assertTrue(result.startswith("🤖 "))

    def test_format_escapes_special_chars(self):
        """Спецсимволы в ответе LLM экранируются."""
        result = format_ai_chat_response("Используй (скобки)!")
        self.assertIn("\\(скобки\\)", result)
        self.assertIn("\\!", result)

    def test_format_escapes_backslash_in_llm_output(self):
        """Бэкслеши в ответе LLM корректно экранируются."""
        result = format_ai_chat_response("Конечно\\! Вот ответ.")
        # В итоге: 🤖 Конечно\\\\\\! Вот ответ\\.
        self.assertIn("\\\\\\!", result)
        self.assertTrue(result.endswith("\\."))

    def test_format_plain_text(self):
        """Обычный текст без спецсимволов — только добавляется префикс."""
        result = format_ai_chat_response("Привет мир")
        self.assertEqual(result, "🤖 Привет мир")


class TestFormatRagAnswerMarkdownV2(unittest.TestCase):
    """Тесты ограниченного markdown-форматирования RAG-ответов."""

    def test_preserves_bold_inline_code_and_lists(self):
        """Сохраняются **bold** и `code`, а остальное экранируется."""
        text = (
            "1. **Символьная ссылка по by-id**\n"
            "Выполните: `sudo ln -s /dev/ttyACM0 ttyS99`"
        )
        result = format_rag_answer_markdown_v2(text)

        self.assertIn("1\\.", result)
        self.assertIn("*Символьная ссылка по by\-id*", result)
        self.assertIn("`sudo ln -s /dev/ttyACM0 ttyS99`", result)

    def test_escapes_unsupported_markup(self):
        """Неподдерживаемая markdown-разметка экранируется безопасно."""
        text = "[ссылка](https://example.com) и _курсив_"
        result = format_rag_answer_markdown_v2(text)

        self.assertIn("\\[ссылка\\]\\(https://example\\.com\\)", result)
        self.assertIn("\\_курсив\\_", result)


if __name__ == "__main__":
    unittest.main()
