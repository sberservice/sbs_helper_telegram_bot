import unittest

from src.sbs_helper_telegram_bot.news.messages import (
    escape_markdown_v2,
    format_news_article,
)


class TestNewsMessages(unittest.TestCase):
    """Tests for news messages utilities."""

    def test_escape_markdown_v2_escapes_special_chars(self):
        """All MarkdownV2 special chars should be escaped."""
        text = "_ * [ ] ( ) ~ ` > # + - = | { } . !"
        escaped = escape_markdown_v2(text)

        for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            self.assertIn(f"\\{char}", escaped)

    def test_escape_markdown_v2_escapes_backslashes_first(self):
        """Обратные слэши экранируются перед спецсимволами, чтобы \\! не стало \\\\! (сломанный формат)."""
        # LLM может вернуть текст с обратными слэшами (пред-экранирование)
        text = "Конечно\\! Вот ответ."
        escaped = escape_markdown_v2(text)
        # \\ → \\\\, затем ! → \\!, . → \\.
        # Итог: Конечно\\\\\\! Вот ответ\\.
        self.assertIn("\\\\\\!", escaped, "Backslash перед ! должен быть экранирован")
        self.assertTrue(escaped.endswith("\\."), "Точка должна быть экранирована")

    def test_escape_markdown_v2_plain_backslash(self):
        """Одиночный обратный слэш экранируется."""
        text = "C:\\Users\\test"
        escaped = escape_markdown_v2(text)
        self.assertEqual(escaped, "C:\\\\Users\\\\test")

    def test_escape_markdown_v2_no_double_escape(self):
        """Текст без обратных слэшей не изменяет поведение."""
        text = "Hello! World."
        escaped = escape_markdown_v2(text)
        self.assertEqual(escaped, "Hello\\! World\\.")

    def test_format_news_article_includes_reactions(self):
        """Reactions should be rendered when provided."""
        article = format_news_article(
            title="Title",
            content="Content",
            category_emoji="📰",
            category_name="Category",
            published_date="01.01.2025",
            reactions={"like": 2, "love": 1, "dislike": 3},
        )

        self.assertIn("👍 2", article)
        self.assertIn("❤️ 1", article)
        self.assertIn("👎 3", article)

    def test_format_news_article_without_reactions(self):
        """Reactions section should be omitted when empty or None."""
        article = format_news_article(
            title="Title",
            content="Content",
            category_emoji="📰",
            category_name="Category",
            published_date="01.01.2025",
            reactions=None,
        )

        self.assertNotIn("👍", article)
        self.assertNotIn("❤️", article)
        self.assertNotIn("👎", article)


if __name__ == "__main__":
    unittest.main(verbosity=2)
