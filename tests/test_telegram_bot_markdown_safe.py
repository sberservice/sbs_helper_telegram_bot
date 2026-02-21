"""Тесты безопасной отправки MarkdownV2 в telegram_bot."""

import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch
from types import SimpleNamespace

from telegram.error import BadRequest

from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import (
    _reply_markdown_safe,
    _format_profile_steps,
    text_entered,
    BUTTON_MAIN_MENU,
)


class TestReplyMarkdownSafe(unittest.IsolatedAsyncioTestCase):
    """Проверка fallback-логики при ошибках парсинга MarkdownV2."""

    async def test_fallback_to_escaped_text_on_parse_entities_error(self):
        """При Can't parse entities выполняется повторная отправка с escaping."""
        message = AsyncMock()
        message.reply_text = AsyncMock(
            side_effect=[
                BadRequest("Can't parse entities: character '(' is reserved and must be escaped with the preceding '\\'"),
                None,
            ]
        )

        await _reply_markdown_safe(message, "Тест (скобки)", reply_markup=None)

        self.assertEqual(message.reply_text.await_count, 2)
        first_call = message.reply_text.await_args_list[0]
        second_call = message.reply_text.await_args_list[1]
        self.assertEqual(first_call.args[0], "Тест (скобки)")
        self.assertEqual(second_call.args[0], "Тест \\(скобки\\)")

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
            patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.invites.check_if_user_pre_invited", return_value=False),
            patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.check_if_invite_user_blocked", return_value=False),
            patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.check_if_user_legit", return_value=True),
            patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.check_if_user_admin", return_value=False),
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
