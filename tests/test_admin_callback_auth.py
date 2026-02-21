"""
test_admin_callback_auth.py — тесты повторной проверки admin-прав в callback-ветках.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram import constants
from telegram.ext import ConversationHandler


class TestAdminCallbackAuth(unittest.IsolatedAsyncioTestCase):
    """Тесты проверки прав администратора в callback handler."""

    def _make_update(self, user_id: int, callback_data: str = "bot_admin_menu"):
        """Создать мок Update с callback_query."""
        update = MagicMock()
        query = AsyncMock()
        query.data = callback_data
        query.from_user = MagicMock()
        query.from_user.id = user_id
        query.message = AsyncMock()
        query.answer = AsyncMock()
        update.callback_query = query
        update.effective_user = MagicMock()
        update.effective_user.id = user_id
        return update

    @patch("src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.check_if_user_admin")
    async def test_non_admin_rejected(self, mock_check):
        """Не-admin пользователь отклоняется с сообщением об ошибке."""
        mock_check.return_value = False

        from src.sbs_helper_telegram_bot.bot_admin.admin_bot_part import handle_callback

        update = self._make_update(user_id=999)
        context = MagicMock()

        result = await handle_callback(update, context)

        self.assertEqual(result, ConversationHandler.END)
        update.callback_query.message.reply_text.assert_called_once()
        call_args = update.callback_query.message.reply_text.call_args
        self.assertIn("Доступ запрещён", call_args[0][0])

    @patch("src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.check_if_user_admin")
    async def test_admin_allowed_through(self, mock_check):
        """Admin-пользователь проходит проверку и обрабатывается."""
        mock_check.return_value = True

        from src.sbs_helper_telegram_bot.bot_admin.admin_bot_part import handle_callback

        update = self._make_update(user_id=1, callback_data="bot_admin_noop")
        context = MagicMock()

        result = await handle_callback(update, context)

        # Для noop возвращает None
        self.assertIsNone(result)

    @patch("src.sbs_helper_telegram_bot.bot_admin.admin_bot_part.check_if_user_admin")
    async def test_answer_called_before_check(self, mock_check):
        """query.answer() вызывается даже при отказе в доступе."""
        mock_check.return_value = False

        from src.sbs_helper_telegram_bot.bot_admin.admin_bot_part import handle_callback

        update = self._make_update(user_id=999)
        context = MagicMock()

        await handle_callback(update, context)
        update.callback_query.answer.assert_called_once()


if __name__ == "__main__":
    unittest.main()
