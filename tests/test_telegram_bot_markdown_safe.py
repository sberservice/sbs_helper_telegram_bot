"""Тесты безопасной отправки MarkdownV2 в telegram_bot."""

import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch
from types import SimpleNamespace

from telegram import constants
from telegram.error import BadRequest

from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import (
    _reply_markdown_safe,
    _format_profile_steps,
    text_entered,
    BUTTON_MAIN_MENU,
)


class TestReplyMarkdownSafe(unittest.IsolatedAsyncioTestCase):
    """Проверка fallback-логики при ошибках парсинга MarkdownV2."""

    async def test_fallback_to_plain_text_on_parse_entities_error(self):
        """При Can't parse entities выполняется повторная отправка как plain text."""
        message = AsyncMock()
        message.reply_text = AsyncMock(
            side_effect=[
                BadRequest("Can't parse entities: character '(' is reserved and must be escaped with the preceding '\\'"),
                None,
            ]
        )

        await _reply_markdown_safe(message, r"Тест \(скобки\)", reply_markup=None)

        self.assertEqual(message.reply_text.await_count, 2)
        first_call = message.reply_text.await_args_list[0]
        second_call = message.reply_text.await_args_list[1]
        # Первый вызов — с MarkdownV2
        self.assertEqual(first_call.args[0], r"Тест \(скобки\)")
        self.assertEqual(first_call.kwargs.get("parse_mode"), constants.ParseMode.MARKDOWN_V2)
        # Второй вызов — plain text без parse_mode, экранирование снято
        self.assertEqual(second_call.args[0], "Тест (скобки)")
        self.assertNotIn("parse_mode", second_call.kwargs)

    async def test_non_entity_badrequest_is_raised(self):
        """Другие BadRequest-ошибки не подавляются."""
        message = AsyncMock()
        message.reply_text = AsyncMock(side_effect=BadRequest("Message is too long"))

        with self.assertRaises(BadRequest):
            await _reply_markdown_safe(message, "text", reply_markup=None)


class TestUpdateProfiling(unittest.IsolatedAsyncioTestCase):
    """Проверка логирования профилирования обработки update."""

    def test_format_profile_steps(self):
        """Форматтер шагов возвращает ожидаемую компактную строку."""
        self.assertEqual(
            _format_profile_steps([("check_user", 3), ("reply", 12)]),
            "check_user=3ms, reply=12ms",
        )
        self.assertEqual(_format_profile_steps([]), "no_steps")

    async def test_text_entered_logs_total_and_step_timings(self):
        """При обработке текста пишется сводный лог с total_ms и шагами."""
        from src.common.telegram_user import UserAuthStatus
        mock_auth = UserAuthStatus(
            is_pre_invited=True,
            is_pre_invited_activated=True,
            is_manual_user=False,
            is_invite_system_enabled=True,
            has_consumed_invite=False,
            is_admin=False,
            is_legit=True,
            is_invite_blocked=False,
        )

        update = SimpleNamespace(
            message=SimpleNamespace(
                text=BUTTON_MAIN_MENU,
                reply_text=AsyncMock(),
            ),
            effective_user=SimpleNamespace(
                id=777,
                first_name="Ivan",
            ),
        )

        with (
            patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status", return_value=mock_auth),
            patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_message", return_value="menu"),
            patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard", return_value=None),
            patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router") as mock_get_ai_router,
            patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.logger.info") as mock_logger_info,
        ):
            mock_get_ai_router.return_value = SimpleNamespace(clear_context=lambda _user_id: None)
            await text_entered(update, None)

        profile_call = None
        for call in mock_logger_info.call_args_list:
            if call.args and str(call.args[0]).startswith("Update profiling:"):
                profile_call = call
                break

        self.assertIsNotNone(profile_call)
        self.assertEqual(profile_call.args[1], 777)
        self.assertEqual(profile_call.args[2], "main_menu")
        self.assertIsInstance(profile_call.args[3], int)
        self.assertIn("parse_message=", profile_call.args[4])
        self.assertIn("check_pre_invited=", profile_call.args[4])
        self.assertIn("reply_main_menu=", profile_call.args[4])


if __name__ == "__main__":
    unittest.main()
