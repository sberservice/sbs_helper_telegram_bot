"""
test_rag_admin_bot_part.py — тесты CRUD-команд админ-управления RAG.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part import (
    handle_rag_admin_command,
)


class TestRagAdminCommands(unittest.IsolatedAsyncioTestCase):
    """Тесты текстовых команд #rag ..."""

    async def test_non_admin_rejected(self):
        """Не-админ не может выполнять RAG-команды."""
        update = SimpleNamespace(
            message=SimpleNamespace(text="#rag list", reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=123),
        )

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part.check_if_user_admin", return_value=False):
            await handle_rag_admin_command(update, context=MagicMock())

        update.message.reply_text.assert_awaited_once()
        self.assertIn("нет прав", update.message.reply_text.await_args.args[0])

    async def test_help_command(self):
        """Команда help возвращает справку."""
        update = SimpleNamespace(
            message=SimpleNamespace(text="#rag help", reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=1),
        )

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part.check_if_user_admin", return_value=True):
            await handle_rag_admin_command(update, context=MagicMock())

        update.message.reply_text.assert_awaited_once()
        self.assertIn("Команды RAG", update.message.reply_text.await_args.args[0])

    async def test_list_command(self):
        """Команда list выводит список документов."""
        update = SimpleNamespace(
            message=SimpleNamespace(text="#rag list active 5", reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=1),
        )

        mock_service = MagicMock()
        mock_service.list_documents.return_value = [
            {"id": 7, "status": "active", "filename": "kb.pdf", "chunks_count": 12}
        ]

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part.check_if_user_admin", return_value=True), \
             patch("src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part.get_rag_service", return_value=mock_service):
            await handle_rag_admin_command(update, context=MagicMock())

        mock_service.list_documents.assert_called_once_with(status="active", limit=5)
        self.assertIn("kb.pdf", update.message.reply_text.await_args.args[0])

    async def test_archive_command(self):
        """Команда archive меняет статус документа на archived."""
        update = SimpleNamespace(
            message=SimpleNamespace(text="#rag archive 10", reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=55),
        )

        mock_service = MagicMock()
        mock_service.set_document_status.return_value = True

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part.check_if_user_admin", return_value=True), \
             patch("src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part.get_rag_service", return_value=mock_service):
            await handle_rag_admin_command(update, context=MagicMock())

        mock_service.set_document_status.assert_called_once_with(10, "archived", updated_by=55)
        self.assertIn("архивирован", update.message.reply_text.await_args.args[0])

    async def test_delete_command_soft(self):
        """Команда delete выполняет мягкое удаление."""
        update = SimpleNamespace(
            message=SimpleNamespace(text="#rag delete 10", reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=55),
        )

        mock_service = MagicMock()
        mock_service.delete_document.return_value = True

        with patch("src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part.check_if_user_admin", return_value=True), \
             patch("src.sbs_helper_telegram_bot.ai_router.rag_admin_bot_part.get_rag_service", return_value=mock_service):
            await handle_rag_admin_command(update, context=MagicMock())

        mock_service.delete_document.assert_called_once_with(10, updated_by=55, hard_delete=False)
        self.assertIn("deleted", update.message.reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
