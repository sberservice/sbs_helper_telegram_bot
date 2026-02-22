"""
test_ai_placeholder.py — тесты для индикатора загрузки при AI-маршрутизации.

Проверяет, что при маршрутизации текста через AI-модуль:
- Отправляется ChatAction.TYPING
- Отправляется плейсхолдер-сообщение «⏳ Обрабатываю ваш запрос...»
- Плейсхолдер редактируется результатом или сообщением об ошибке
- При невозможности редактирования — отправляется новое сообщение
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from telegram import constants
from telegram.error import BadRequest

from src.sbs_helper_telegram_bot.ai_router.messages import MESSAGE_AI_PROCESSING
from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import (
    _edit_markdown_safe,
    _strip_markdown_v2_escaping,
)


def _make_update_and_context(user_id=12345, text="какой-то произвольный текст", is_admin=False):
    """Создать моки Update и Context для тестирования text_entered."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.first_name = "TestUser"
    update.effective_chat.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    return update, context


class TestEditMarkdownSafe(unittest.IsolatedAsyncioTestCase):
    """Тесты для _edit_markdown_safe — редактирование сообщения с fallback."""

    async def test_edit_success(self):
        """Успешное редактирование сообщения MarkdownV2."""
        sent_message = MagicMock()
        sent_message.edit_text = AsyncMock()

        await _edit_markdown_safe(sent_message, "Новый текст")

        sent_message.edit_text.assert_awaited_once_with(
            "Новый текст",
            parse_mode=constants.ParseMode.MARKDOWN_V2,
        )

    async def test_edit_fallback_on_parse_error(self):
        """При ошибке парсинга MarkdownV2 — повтор без форматирования (plain text)."""
        sent_message = MagicMock()
        sent_message.edit_text = AsyncMock(
            side_effect=[BadRequest("Can't parse entities"), None]
        )

        await _edit_markdown_safe(sent_message, "Текст_с_проблемой")

        self.assertEqual(sent_message.edit_text.await_count, 2)
        # Второй вызов — plain text без parse_mode
        second_call = sent_message.edit_text.call_args_list[1]
        self.assertNotIn("parse_mode", second_call.kwargs)

    async def test_edit_raises_on_other_bad_request(self):
        """Другие BadRequest (не parse error) пробрасываются выше."""
        sent_message = MagicMock()
        sent_message.edit_text = AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )

        with self.assertRaises(BadRequest):
            await _edit_markdown_safe(sent_message, "Текст")


class TestAIPlaceholderFlow(unittest.IsolatedAsyncioTestCase):
    """Тесты потока: typing → плейсхолдер → edit/fallback при AI-маршрутизации."""

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    async def test_typing_and_placeholder_sent_before_ai_route(
        self, mock_edit_safe, mock_keyboard, mock_get_router, mock_auth
    ):
        """ChatAction.TYPING и плейсхолдер отправляются до вызова AI."""
        from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import text_entered

        # Настройка: пользователь авторизован, не админ
        auth = MagicMock()
        auth.is_pre_invited = False
        auth.is_pre_invited_activated = True
        auth.is_invite_blocked = False
        auth.is_legit = True
        auth.is_admin = False
        mock_auth.return_value = auth

        mock_keyboard.return_value = MagicMock()

        # AI-роутер возвращает успешный ответ
        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=("AI ответ", "chat"))
        mock_get_router.return_value = mock_router

        update, context = _make_update_and_context(text="расскажи про ошибку")
        placeholder_msg = MagicMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)

        # Проверяем, что отправлен ChatAction.TYPING
        context.bot.send_chat_action.assert_awaited_once_with(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.TYPING,
        )

        # Проверяем, что отправлен плейсхолдер без reply_markup,
        # чтобы сообщение можно было безопасно редактировать.
        update.message.reply_text.assert_awaited_once_with(
            MESSAGE_AI_PROCESSING,
            parse_mode=constants.ParseMode.MARKDOWN_V2,
        )

        # Проверяем, что плейсхолдер отредактирован AI-ответом
        mock_edit_safe.assert_awaited_once_with(placeholder_msg, "AI ответ")

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    async def test_placeholder_edited_to_unrecognized_on_ai_failure(
        self, mock_edit_safe, mock_keyboard, mock_get_router, mock_auth
    ):
        """При ошибке AI плейсхолдер редактируется сообщением 'нераспознано'."""
        from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import text_entered

        auth = MagicMock()
        auth.is_pre_invited = False
        auth.is_pre_invited_activated = True
        auth.is_invite_blocked = False
        auth.is_legit = True
        auth.is_admin = False
        mock_auth.return_value = auth

        mock_keyboard.return_value = MagicMock()

        # AI-роутер возвращает ошибку
        mock_router = MagicMock()
        mock_router.route = AsyncMock(side_effect=Exception("LLM timeout"))
        mock_get_router.return_value = mock_router

        update, context = _make_update_and_context(text="абракадабра")
        placeholder_msg = MagicMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)

        # Плейсхолдер должен быть отредактирован сообщением об ошибке
        mock_edit_safe.assert_awaited_once()
        call_args = mock_edit_safe.call_args
        self.assertEqual(call_args.args[0], placeholder_msg)

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._reply_markdown_safe", new_callable=AsyncMock)
    async def test_fallback_to_reply_when_edit_fails(
        self, mock_reply_safe, mock_edit_safe, mock_keyboard, mock_get_router, mock_auth
    ):
        """Если edit_text провалился — отправляем новое сообщение через _reply_markdown_safe."""
        from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import text_entered

        auth = MagicMock()
        auth.is_pre_invited = False
        auth.is_pre_invited_activated = True
        auth.is_invite_blocked = False
        auth.is_legit = True
        auth.is_admin = False
        mock_auth.return_value = auth

        mock_keyboard.return_value = MagicMock()

        # AI-роутер возвращает успешный ответ
        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=("AI ответ", "chat"))
        mock_get_router.return_value = mock_router

        # edit_text падает (сообщение удалено пользователем)
        mock_edit_safe.side_effect = Exception("Message to edit not found")

        update, context = _make_update_and_context(text="вопрос")
        placeholder_msg = MagicMock()
        placeholder_msg.delete = AsyncMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)

        # edit пробовали...
        mock_edit_safe.assert_awaited_once()
        # ...но упали, поэтому плейсхолдер удалён и fallback через reply_text
        placeholder_msg.delete.assert_awaited_once()
        mock_reply_safe.assert_awaited_once_with(
            update.message,
            "AI ответ",
            mock_keyboard.return_value,
        )

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    async def test_ai_routed_status_edits_placeholder(
        self, mock_edit_safe, mock_keyboard, mock_get_router, mock_auth
    ):
        """Статус 'routed' — плейсхолдер редактируется результатом обработчика."""
        from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import text_entered

        auth = MagicMock()
        auth.is_pre_invited = False
        auth.is_pre_invited_activated = True
        auth.is_invite_blocked = False
        auth.is_legit = True
        auth.is_admin = False
        mock_auth.return_value = auth

        mock_keyboard.return_value = MagicMock()

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=("Результат модуля", "routed"))
        mock_get_router.return_value = mock_router

        update, context = _make_update_and_context(text="ошибка E001")
        placeholder_msg = MagicMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)

        mock_edit_safe.assert_awaited_once_with(placeholder_msg, "Результат модуля")

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.logger.info")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    async def test_placeholder_profiling_contains_substeps_and_detailed_log(
        self,
        mock_edit_safe,
        mock_keyboard,
        mock_get_router,
        mock_auth,
        mock_logger_info,
    ):
        """Лог профилирования AI содержит подэтапы отправки плейсхолдера."""
        from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import text_entered

        auth = MagicMock()
        auth.is_pre_invited = False
        auth.is_pre_invited_activated = True
        auth.is_invite_blocked = False
        auth.is_legit = True
        auth.is_admin = False
        mock_auth.return_value = auth

        mock_keyboard.return_value = MagicMock()

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=("AI ответ", "chat"))
        mock_get_router.return_value = mock_router

        update, context = _make_update_and_context(text="проверь профиль")
        placeholder_msg = MagicMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)
        mock_edit_safe.assert_awaited_once_with(placeholder_msg, "AI ответ")

        profile_call = None
        placeholder_profile_call = None
        for call in mock_logger_info.call_args_list:
            if call.args and call.args[0] == "Update profiling: user_id=%s result=%s total_ms=%s steps=[%s]":
                profile_call = call
            if call.args and call.args[0] == (
                "AI placeholder profiling: user_id=%s total_ms=%s chat_action_ms=%s "
                "placeholder_reply_ms=%s"
            ):
                placeholder_profile_call = call

        self.assertIsNotNone(profile_call)
        steps = profile_call.args[4]
        self.assertIn("ai_chat_action=", steps)
        self.assertIn("ai_placeholder_reply=", steps)
        self.assertIn("ai_placeholder_sent=", steps)

        self.assertIsNotNone(placeholder_profile_call)
        self.assertEqual(placeholder_profile_call.args[1], update.effective_user.id)
        self.assertIsInstance(placeholder_profile_call.args[2], int)
        self.assertIsInstance(placeholder_profile_call.args[3], int)
        self.assertIsInstance(placeholder_profile_call.args[4], int)


class TestStripMarkdownV2Escaping(unittest.TestCase):
    """Тесты для _strip_markdown_v2_escaping — удаление MarkdownV2-экранирования."""

    def test_strips_escaped_special_chars(self):
        """Убирает обратные слэши перед спецсимволами."""
        text = r"Привет\! Всё хорошо\."
        result = _strip_markdown_v2_escaping(text)
        self.assertEqual(result, "Привет! Всё хорошо.")

    def test_strips_escaped_underscores_and_stars(self):
        """Убирает экранирование подчёркиваний и звёздочек."""
        text = r"\_курсив\_ и \*жирный\*"
        result = _strip_markdown_v2_escaping(text)
        self.assertEqual(result, "_курсив_ и *жирный*")

    def test_preserves_plain_text(self):
        """Обычный текст не меняется."""
        text = "Просто текст без спецсимволов"
        result = _strip_markdown_v2_escaping(text)
        self.assertEqual(result, "Просто текст без спецсимволов")

    def test_ai_chat_response_example(self):
        """Реальный пример ответа AI с экранированием."""
        text = r"🤖 Всё хорошо, спасибо\! Готов помочь\."
        result = _strip_markdown_v2_escaping(text)
        self.assertEqual(result, "🤖 Всё хорошо, спасибо! Готов помочь.")

    def test_strips_double_backslash_before_dot(self):
        """Убирает двойной слэш перед точкой после повторного экранирования."""
        text = r"Работаю в штатном режиме\\."
        result = _strip_markdown_v2_escaping(text)
        self.assertEqual(result, "Работаю в штатном режиме.")

    def test_strips_triple_backslash_before_dot(self):
        """Убирает тройной слэш перед точкой в сложном fallback-сценарии."""
        text = r"Работаю в штатном режиме\\\."
        result = _strip_markdown_v2_escaping(text)
        self.assertEqual(result, "Работаю в штатном режиме.")


if __name__ == "__main__":
    unittest.main()
