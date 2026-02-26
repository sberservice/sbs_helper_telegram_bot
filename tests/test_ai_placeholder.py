"""
test_ai_placeholder.py — тесты для индикатора загрузки при AI-маршрутизации.

Проверяет, что при маршрутизации текста через AI-модуль:
- Отправляется ChatAction.TYPING
- Отправляется плейсхолдер-сообщение «⏳ Обрабатываю ваш запрос...»
- Для RAG-запросов плейсхолдер проходит этапы ожидания/префильтрации/запроса к ИИ
- Плейсхолдер редактируется результатом или сообщением об ошибке
- При невозможности редактирования — отправляется новое сообщение
"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from telegram import constants, ReplyKeyboardMarkup
from telegram.error import BadRequest

from src.sbs_helper_telegram_bot.ai_router.messages import (
    MESSAGE_AI_PROCESSING,
    MESSAGE_AI_WAITING_FOR_AI,
    MESSAGE_AI_PREFILTERING_DOCUMENTS,
    MESSAGE_AI_REQUESTING_AUGMENTED_PAYLOAD,
    AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED,
    AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED,
    MESSAGE_AI_LOW_CONFIDENCE,
    MESSAGE_AI_UNAVAILABLE,
)
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
    context.user_data = {}

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
        first_reply_call = update.message.reply_text.await_args_list[0]
        self.assertEqual(first_reply_call.args[0], MESSAGE_AI_PROCESSING)
        self.assertEqual(
            first_reply_call.kwargs.get("parse_mode"),
            constants.ParseMode.MARKDOWN_V2,
        )
        self.assertNotIn("reply_markup", first_reply_call.kwargs)

        # После успешного AI-ответа бот отдельным сообщением восстанавливает меню.
        update.message.reply_text.assert_any_await(
            "Выберите действие из меню или введите произвольный запрос:",
            reply_markup=mock_keyboard.return_value,
        )

        # Первый вызов всегда остаётся плейсхолдером.
        update.message.reply_text.assert_any_await(
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
    async def test_status_specific_ai_fallback_messages(
        self,
        mock_edit_safe,
        mock_keyboard,
        mock_get_router,
        mock_auth,
    ):
        """Для low_confidence/error/circuit_open используются специальные AI-сообщения."""
        from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import text_entered

        auth = MagicMock()
        auth.is_pre_invited = False
        auth.is_pre_invited_activated = True
        auth.is_invite_blocked = False
        auth.is_legit = True
        auth.is_admin = False
        mock_auth.return_value = auth

        mock_keyboard.return_value = MagicMock()

        cases = [
            ("low_confidence", MESSAGE_AI_LOW_CONFIDENCE),
            ("error", MESSAGE_AI_UNAVAILABLE),
            ("circuit_open", MESSAGE_AI_UNAVAILABLE),
        ]

        for status, expected_message in cases:
            with self.subTest(status=status):
                mock_edit_safe.reset_mock()
                mock_router = MagicMock()
                mock_router.route = AsyncMock(return_value=(None, status))
                mock_get_router.return_value = mock_router

                update, context = _make_update_and_context(text="произвольный текст")
                placeholder_msg = MagicMock()
                update.message.reply_text.return_value = placeholder_msg

                await text_entered(update, context)

                mock_edit_safe.assert_any_await(placeholder_msg, expected_message)

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    async def test_placeholder_switched_to_waiting_message_for_rag(
        self, mock_edit_safe, mock_keyboard, mock_get_router, mock_auth
    ):
        """Для intent=rag_qa плейсхолдер проходит этапы ожидания и RAG-прогресса."""
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

        async def _route_with_rag_callback(_text, _user_id, on_classified=None, on_progress=None):
            if on_classified is not None:
                await on_classified(SimpleNamespace(intent="rag_qa"))
            if on_progress is not None:
                await on_progress(AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED, {"intent": "rag_qa"})
                await on_progress(AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED, {"intent": "rag_qa"})
            return "RAG ответ", "routed"

        mock_router.route = AsyncMock(side_effect=_route_with_rag_callback)
        mock_get_router.return_value = mock_router

        update, context = _make_update_and_context(text="вопрос по регламенту")
        placeholder_msg = MagicMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)

        self.assertGreaterEqual(mock_edit_safe.await_count, 4)
        self.assertEqual(mock_edit_safe.await_args_list[0].args[0], placeholder_msg)
        self.assertEqual(mock_edit_safe.await_args_list[0].args[1], MESSAGE_AI_WAITING_FOR_AI)
        self.assertEqual(mock_edit_safe.await_args_list[1].args[0], placeholder_msg)
        self.assertEqual(mock_edit_safe.await_args_list[1].args[1], MESSAGE_AI_PREFILTERING_DOCUMENTS)
        self.assertEqual(mock_edit_safe.await_args_list[2].args[0], placeholder_msg)
        self.assertEqual(mock_edit_safe.await_args_list[2].args[1], MESSAGE_AI_REQUESTING_AUGMENTED_PAYLOAD)
        self.assertEqual(mock_edit_safe.await_args_list[3].args[0], placeholder_msg)
        self.assertEqual(mock_edit_safe.await_args_list[3].args[1], "RAG ответ")

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    async def test_reroute_to_rag_uses_progress_placeholder_stages(
        self, mock_edit_safe, mock_keyboard, mock_get_router, mock_auth
    ):
        """При reroute general_chat→rag показываются промежуточные RAG-этапы."""
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

        async def _route_with_rag_progress(_text, _user_id, on_classified=None, on_progress=None):
            if on_classified is not None:
                await on_classified(SimpleNamespace(intent="general_chat"))
            if on_progress is not None:
                await on_progress(AI_PROGRESS_STAGE_RAG_PREFILTER_STARTED, {"route_path": "general_chat_to_rag"})
                await on_progress(AI_PROGRESS_STAGE_RAG_AUGMENTED_REQUEST_STARTED, {"route_path": "general_chat_to_rag"})
            return "RAG ответ после reroute", "routed"

        mock_router.route = AsyncMock(side_effect=_route_with_rag_progress)
        mock_get_router.return_value = mock_router

        update, context = _make_update_and_context(text="как по регламенту")
        placeholder_msg = MagicMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)

        self.assertEqual(mock_edit_safe.await_args_list[0].args[1], MESSAGE_AI_PREFILTERING_DOCUMENTS)
        self.assertEqual(mock_edit_safe.await_args_list[1].args[1], MESSAGE_AI_REQUESTING_AUGMENTED_PAYLOAD)
        self.assertEqual(mock_edit_safe.await_args_list[2].args[1], "RAG ответ после reroute")

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
        update.message.reply_text.assert_any_await(
            "Выберите действие из меню или введите произвольный запрос:",
            reply_markup=mock_keyboard.return_value,
        )

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    async def test_restores_previous_keyboard_instead_of_main_menu(
        self, mock_edit_safe, mock_keyboard, mock_get_router, mock_auth
    ):
        """После AI-ответа восстанавливается последняя сохранённая клавиатура, а не main menu."""
        from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import text_entered

        auth = MagicMock()
        auth.is_pre_invited = False
        auth.is_pre_invited_activated = True
        auth.is_invite_blocked = False
        auth.is_legit = True
        auth.is_admin = False
        mock_auth.return_value = auth

        main_keyboard = MagicMock()
        mock_keyboard.return_value = main_keyboard

        mock_router = MagicMock()
        mock_router.route = AsyncMock(return_value=("AI ответ", "chat"))
        mock_get_router.return_value = mock_router

        update, context = _make_update_and_context(text="произвольный запрос")
        previous_keyboard = ReplyKeyboardMarkup([["Кнопка 1"]], resize_keyboard=True)
        context.user_data["last_reply_keyboard"] = previous_keyboard

        placeholder_msg = MagicMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)

        mock_edit_safe.assert_awaited_once_with(placeholder_msg, "AI ответ")
        update.message.reply_text.assert_any_await(
            "Выберите действие из меню или введите произвольный запрос:",
            reply_markup=previous_keyboard,
        )

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

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.clear_all_states")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.enter_certification_module", new_callable=AsyncMock)
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    async def test_certification_intent_switches_to_certification_module_with_state_reset(
        self,
        mock_edit_safe,
        mock_enter_certification_module,
        mock_clear_all_states,
        mock_keyboard,
        mock_get_router,
        mock_auth,
    ):
        """Для intent=certification_info бот сбрасывает состояния и открывает меню аттестации."""
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

        async def _route_with_certification_intent(_text, _user_id, on_classified=None, on_progress=None):
            if on_classified is not None:
                await on_classified(SimpleNamespace(intent="certification_info"))
            return "Сводка аттестации", "routed"

        mock_router.route = AsyncMock(side_effect=_route_with_certification_intent)
        mock_get_router.return_value = mock_router

        update, context = _make_update_and_context(text="как у меня с аттестацией")
        placeholder_msg = MagicMock()
        placeholder_msg.delete = AsyncMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)

        mock_clear_all_states.assert_called_once_with(context)
        mock_enter_certification_module.assert_awaited_once_with(update, context)
        placeholder_msg.delete.assert_awaited_once()
        mock_edit_safe.assert_not_awaited()

    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_user_auth_status")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_ai_router")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.get_main_menu_keyboard")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.clear_all_states")
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.enter_certification_module", new_callable=AsyncMock)
    @patch("src.sbs_helper_telegram_bot.telegram_bot.telegram_bot._edit_markdown_safe", new_callable=AsyncMock)
    async def test_certification_intent_does_not_switch_if_already_in_certification_module(
        self,
        mock_edit_safe,
        mock_enter_certification_module,
        mock_clear_all_states,
        mock_keyboard,
        mock_get_router,
        mock_auth,
    ):
        """Если уже открыто меню аттестации, повторного переключения и сброса не происходит."""
        from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import text_entered
        from src.sbs_helper_telegram_bot.certification import keyboards as cert_keyboards

        auth = MagicMock()
        auth.is_pre_invited = False
        auth.is_pre_invited_activated = True
        auth.is_invite_blocked = False
        auth.is_legit = True
        auth.is_admin = False
        mock_auth.return_value = auth

        mock_keyboard.return_value = MagicMock()

        mock_router = MagicMock()

        async def _route_with_certification_intent(_text, _user_id, on_classified=None, on_progress=None):
            if on_classified is not None:
                await on_classified(SimpleNamespace(intent="certification_info"))
            return "Сводка аттестации", "routed"

        mock_router.route = AsyncMock(side_effect=_route_with_certification_intent)
        mock_get_router.return_value = mock_router

        update, context = _make_update_and_context(text="покажи мой прогресс")
        context.user_data["last_reply_keyboard"] = cert_keyboards.get_submenu_keyboard()

        placeholder_msg = MagicMock()
        update.message.reply_text.return_value = placeholder_msg

        await text_entered(update, context)

        mock_clear_all_states.assert_not_called()
        mock_enter_certification_module.assert_not_awaited()
        mock_edit_safe.assert_awaited_once_with(placeholder_msg, "Сводка аттестации")


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
