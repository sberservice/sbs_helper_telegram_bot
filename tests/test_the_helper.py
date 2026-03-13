"""
Тесты для THE_HELPER — Telethon-скрипт мониторинга /helpme в группах.

Покрывает: rate-limiter, парсинг команды, обработку ошибок,
разбиение сообщений, fallback-сообщения.
"""

import asyncio
import json
import re
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import sys
from pathlib import Path


def _run_async(coro):
    """Запустить корутину в новом event loop (совместимо с Python 3.10+)."""
    return asyncio.run(coro)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.the_helper import (
    HelperRateLimiter,
    HELP_COMMAND_RE,
    split_message,
    _strip_markdown_v2_escaping,
    parse_index_selection,
    MSG_PROCESSING,
    MSG_ERROR,
    MSG_USAGE_HINT,
    MSG_RATE_LIMIT_USER,
    MSG_RATE_LIMIT_GROUP,
    MAX_MESSAGE_AGE_SECONDS,
    handle_help,
    load_groups,
    save_groups,
    get_group_ids,
    run_listener,
    PROJECT_ROOT,
    HELPER_SESSION_NAME,
)


# ===========================================================================
# Rate Limiter
# ===========================================================================

class TestHelperRateLimiter(unittest.TestCase):
    """Тесты HelperRateLimiter — per-user и per-group sliding window."""

    def test_user_allowed_within_limit(self):
        """Запросы в пределах лимита разрешены."""
        rl = HelperRateLimiter(user_max=3, user_window=60, group_max=100, group_window=60)
        for _ in range(3):
            ok, remaining = rl.check_user(123)
            self.assertTrue(ok)
            self.assertIsNone(remaining)
            rl.record(123, -100)

    def test_user_blocked_over_limit(self):
        """Запрос сверх лимита блокируется."""
        rl = HelperRateLimiter(user_max=2, user_window=60, group_max=100, group_window=60)
        rl.record(123, -100)
        rl.record(123, -100)
        ok, remaining = rl.check_user(123)
        self.assertFalse(ok)
        self.assertIsNotNone(remaining)
        self.assertGreater(remaining, 0)

    def test_user_different_users_independent(self):
        """Rate-limit для разных пользователей независим."""
        rl = HelperRateLimiter(user_max=1, user_window=60, group_max=100, group_window=60)
        rl.record(111, -100)
        ok, _ = rl.check_user(111)
        self.assertFalse(ok)
        ok2, _ = rl.check_user(222)
        self.assertTrue(ok2)

    def test_user_window_expiry(self):
        """Запросы разрешены после истечения окна."""
        rl = HelperRateLimiter(user_max=1, user_window=1, group_max=100, group_window=60)
        rl.record(123, -100)
        ok, _ = rl.check_user(123)
        self.assertFalse(ok)
        # Подменяем время: сдвигаем записи в прошлое
        rl._user_requests[123] = [time.time() - 2]
        ok2, _ = rl.check_user(123)
        self.assertTrue(ok2)

    def test_group_allowed_within_limit(self):
        """Групповой лимит: запросы в пределах нормы."""
        rl = HelperRateLimiter(user_max=100, user_window=60, group_max=2, group_window=60)
        rl.record(1, -100)
        rl.record(2, -100)
        ok, _ = rl.check_group(-100)
        self.assertFalse(ok)

    def test_group_blocked_over_limit(self):
        """Групповой лимит: блокировка при превышении."""
        rl = HelperRateLimiter(user_max=100, user_window=60, group_max=1, group_window=60)
        rl.record(1, -200)
        ok, remaining = rl.check_group(-200)
        self.assertFalse(ok)
        self.assertGreater(remaining, 0)

    def test_group_different_groups_independent(self):
        """Rate-limit для разных групп независим."""
        rl = HelperRateLimiter(user_max=100, user_window=60, group_max=1, group_window=60)
        rl.record(1, -100)
        ok, _ = rl.check_group(-100)
        self.assertFalse(ok)
        ok2, _ = rl.check_group(-200)
        self.assertTrue(ok2)

    def test_group_window_expiry(self):
        """Групповой лимит: запросы разрешены после истечения окна."""
        rl = HelperRateLimiter(user_max=100, user_window=60, group_max=1, group_window=1)
        rl.record(1, -100)
        ok, _ = rl.check_group(-100)
        self.assertFalse(ok)
        rl._group_requests[-100] = [time.time() - 2]
        ok2, _ = rl.check_group(-100)
        self.assertTrue(ok2)

    def test_remaining_seconds_positive(self):
        """Оставшееся время всегда ≥ 1."""
        rl = HelperRateLimiter(user_max=1, user_window=30, group_max=100, group_window=60)
        rl.record(1, -100)
        ok, remaining = rl.check_user(1)
        self.assertFalse(ok)
        self.assertGreaterEqual(remaining, 1)


# ===========================================================================
# Парсинг команды /helpme
# ===========================================================================

class TestHelpCommandRegex(unittest.TestCase):
    """Тесты регулярного выражения команды /helpme."""

    def test_bare_help(self):
        """Голый /helpme."""
        m = HELP_COMMAND_RE.match("/helpme")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "")

    def test_help_with_text(self):
        """/helpme с вопросом."""
        m = HELP_COMMAND_RE.match("/helpme как проверить код ошибки")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "как проверить код ошибки")

    def test_help_with_bot_username(self):
        """/helpme@botname."""
        m = HELP_COMMAND_RE.match("/helpme@my_test_bot")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "")

    def test_help_with_bot_username_and_text(self):
        """/helpme@botname с текстом."""
        m = HELP_COMMAND_RE.match("/helpme@bot вопрос тут")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "вопрос тут")

    def test_no_match_other_command(self):
        """Другие команды не подходят."""
        m = HELP_COMMAND_RE.match("/start")
        self.assertIsNone(m)

    def test_no_match_legacy_help_command(self):
        """Старая команда /help больше не должна распознаваться."""
        m = HELP_COMMAND_RE.match("/help вопрос")
        self.assertIsNone(m)

    def test_no_match_help_inside_text(self):
        """Команда должна быть в начале строки."""
        m = HELP_COMMAND_RE.match("some text /helpme")
        self.assertIsNone(m)

    def test_case_insensitive(self):
        """/HelpMe, /HELPME тоже распознаются."""
        m = HELP_COMMAND_RE.match("/HELPME вопрос")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "вопрос")

    def test_multiline_text(self):
        """/helpme с многострочным вопросом."""
        m = HELP_COMMAND_RE.match("/helpme строка 1\nстрока 2")
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "строка 1\nстрока 2")


# ===========================================================================
# Разбиение сообщений
# ===========================================================================

class TestSplitMessage(unittest.TestCase):
    """Тесты split_message — разбиение длинных MarkdownV2-текстов."""

    def test_short_message_not_split(self):
        """Короткое сообщение не разбивается."""
        self.assertEqual(split_message("hello", max_len=100), ["hello"])

    def test_exact_limit_not_split(self):
        """Сообщение точно по лимиту не разбивается."""
        text = "a" * 100
        self.assertEqual(split_message(text, max_len=100), [text])

    def test_long_message_split_by_newline(self):
        """Разбиение по переносу строки."""
        text = "AAAA\nBBBB\nCCCC"
        chunks = split_message(text, max_len=10)
        self.assertTrue(len(chunks) > 1)
        joined = "".join(chunks)
        # Все символы из оригинала должны присутствовать
        for ch in "AAAA":
            self.assertIn(ch, joined)

    def test_long_message_split_by_space(self):
        """Разбиение по пробелу, если переносы далеко."""
        text = "word1 word2 word3 word4"
        chunks = split_message(text, max_len=12)
        self.assertTrue(len(chunks) > 1)

    def test_no_trailing_backslash(self):
        """Чанк не заканчивается на одинарный обратный слэш."""
        text = "abc\\" + "d" * 20
        chunks = split_message(text, max_len=4)
        for chunk in chunks[:-1]:
            self.assertFalse(chunk.endswith("\\"))

    def test_empty_text(self):
        """Пустой текст → список с пустой строкой."""
        result = split_message("")
        self.assertEqual(result, [""])


# ===========================================================================
# MarkdownV2 stripping
# ===========================================================================

class TestStripMarkdownV2(unittest.TestCase):
    """Тесты _strip_markdown_v2_escaping."""

    def test_removes_single_escape(self):
        """Снимает одиночное экранирование."""
        self.assertEqual(_strip_markdown_v2_escaping("hello\\.world"), "hello.world")

    def test_removes_double_escape(self):
        """Снимает двойное экранирование."""
        self.assertEqual(_strip_markdown_v2_escaping("test\\\\."), "test.")

    def test_preserves_regular_text(self):
        """Обычный текст без спецсимволов не меняется."""
        self.assertEqual(_strip_markdown_v2_escaping("hello world"), "hello world")


# ===========================================================================
# handle_help — интеграционные тесты с моками
# ===========================================================================

class TestHandleHelp(unittest.TestCase):
    """Тесты обработчика handle_help с мок-объектами."""

    def _make_event(
        self,
        raw_text="/helpme",
        sender_id=123,
        chat_id=-100999,
        is_bot=False,
        reply_to_msg_id=None,
        message_date=None,
    ):
        """Создать мок-объект события Telethon."""
        event = AsyncMock()
        event.raw_text = raw_text
        event.sender_id = sender_id
        event.chat_id = chat_id

        sender = MagicMock()
        sender.bot = is_bot
        event.get_sender = AsyncMock(return_value=sender)

        event.message = MagicMock()
        event.message.id = 42
        event.message.date = message_date or datetime.now(timezone.utc)

        if reply_to_msg_id:
            event.message.reply_to = MagicMock()
            event.message.reply_to.reply_to_msg_id = reply_to_msg_id
        else:
            event.message.reply_to = None

        # event.reply возвращает мок сообщения с .id
        reply_msg = MagicMock()
        reply_msg.id = 999
        event.reply = AsyncMock(return_value=reply_msg)

        return event

    def test_usage_hint_bare_help_no_reply(self):
        """Голый /helpme без ответа → подсказка."""
        event = self._make_event(raw_text="/helpme")
        client = AsyncMock()
        rl = HelperRateLimiter(user_max=10, user_window=60, group_max=100, group_window=60)

        _run_async(handle_help(event, client, rl))

        # Должен быть вызван event.reply с подсказкой
        event.reply.assert_called()
        first_reply = event.reply.call_args_list[0]
        self.assertIn("Как пользоваться", _strip_markdown_v2_escaping(first_reply[0][0]))

    def test_skip_old_message(self):
        """Старые сообщения (> MAX_MESSAGE_AGE_SECONDS) пропускаются."""
        old_date = datetime.now(timezone.utc) - timedelta(seconds=MAX_MESSAGE_AGE_SECONDS + 10)
        event = self._make_event(raw_text="/helpme вопрос", message_date=old_date)
        client = AsyncMock()
        rl = HelperRateLimiter()

        _run_async(handle_help(event, client, rl))

        # Не должно быть вызовов reply
        event.reply.assert_not_called()

    def test_skip_bot_sender(self):
        """Сообщения от ботов пропускаются."""
        event = self._make_event(raw_text="/helpme вопрос", is_bot=True)
        client = AsyncMock()
        rl = HelperRateLimiter()

        _run_async(handle_help(event, client, rl))

        event.reply.assert_not_called()

    def test_rate_limit_user(self):
        """При превышении пользовательского лимита — сообщение об ограничении."""
        event = self._make_event(raw_text="/helpme вопрос")
        client = AsyncMock()
        rl = HelperRateLimiter(user_max=1, user_window=60, group_max=100, group_window=60)
        rl.record(123, -100999)

        _run_async(handle_help(event, client, rl))

        event.reply.assert_called_once()
        reply_text = event.reply.call_args[0][0]
        self.assertIn("Слишком много запросов", _strip_markdown_v2_escaping(reply_text))

    def test_rate_limit_group(self):
        """При превышении группового лимита — сообщение об ограничении."""
        event = self._make_event(raw_text="/helpme вопрос")
        client = AsyncMock()
        rl = HelperRateLimiter(user_max=100, user_window=60, group_max=1, group_window=60)
        rl.record(999, -100999)  # другой user заполнил групповой лимит

        _run_async(handle_help(event, client, rl))

        event.reply.assert_called_once()
        reply_text = event.reply.call_args[0][0]
        self.assertIn("Слишком много запросов в этой группе",
                       _strip_markdown_v2_escaping(reply_text))

    @patch("scripts.the_helper._edit_safe", new_callable=AsyncMock)
    def test_help_with_text_calls_router(self, mock_edit_safe):
        """/helpme с текстом вызывает intent router."""
        event = self._make_event(raw_text="/helpme код ошибки 4119")
        client = AsyncMock()
        rl = HelperRateLimiter(user_max=10, user_window=60, group_max=100, group_window=60)

        mock_router = AsyncMock()
        mock_router.route = AsyncMock(
            return_value=("✅ Тестовый ответ", "routed")
        )

        with patch(
            "src.sbs_helper_telegram_bot.ai_router.intent_router.get_router",
            return_value=mock_router,
        ):
            _run_async(handle_help(event, client, rl))

        # Плейсхолдер отправлен
        event.reply.assert_called()
        # Роутер вызван
        mock_router.route.assert_awaited_once()
        call_args = mock_router.route.call_args
        self.assertIn("код ошибки 4119", call_args[0][0])

    @patch("scripts.the_helper._edit_safe", new_callable=AsyncMock)
    def test_help_reply_to_message_calls_rag(self, mock_edit_safe):
        """/helpme в ответ на сообщение → RAG напрямую."""
        event = self._make_event(raw_text="/helpme", reply_to_msg_id=55)
        client = AsyncMock()
        rl = HelperRateLimiter(user_max=10, user_window=60, group_max=100, group_window=60)

        # Мок получения сообщения-оригинала
        replied_msg = MagicMock()
        replied_msg.text = "Как настроить ККТ?"
        client.get_messages = AsyncMock(return_value=replied_msg)

        mock_rag_service = AsyncMock()
        mock_rag_answer = MagicMock()
        mock_rag_answer.text = "Вот как настроить ККТ..."
        mock_rag_service.answer_question = AsyncMock(return_value=mock_rag_answer)

        with patch(
            "src.core.ai.rag_service.get_rag_service",
            return_value=mock_rag_service,
        ), patch(
            "src.sbs_helper_telegram_bot.ai_router.messages.format_rag_answer_markdown_v2",
            return_value="Вот как настроить ККТ\\.\\.\\.",
        ):
            _run_async(handle_help(event, client, rl))

        # RAG-сервис вызван
        mock_rag_service.answer_question.assert_awaited_once()
        call_args = mock_rag_service.answer_question.call_args
        self.assertIn("Как настроить ККТ?", call_args[1].get("question", call_args[0][0]))

    @patch("scripts.the_helper._edit_safe", new_callable=AsyncMock)
    def test_router_exception_shows_error(self, mock_edit_safe):
        """Исключение в роутере → плейсхолдер обновляется ошибкой."""
        event = self._make_event(raw_text="/helpme вопрос")
        client = AsyncMock()
        rl = HelperRateLimiter(user_max=10, user_window=60, group_max=100, group_window=60)

        mock_router = AsyncMock()
        mock_router.route = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        with patch(
            "src.sbs_helper_telegram_bot.ai_router.intent_router.get_router",
            return_value=mock_router,
        ):
            _run_async(handle_help(event, client, rl))

        # Проверяем, что edit_safe вызван с ошибкой
        edit_calls = mock_edit_safe.call_args_list
        # Последний вызов должен быть с MSG_ERROR или fallback
        last_edit_text = edit_calls[-1][0][3] if len(edit_calls[-1][0]) >= 4 else ""
        error_plain = _strip_markdown_v2_escaping(last_edit_text)
        self.assertTrue(
            "ошибка" in error_plain.lower()
            or "Произошла" in error_plain
            or "недоступен" in error_plain.lower(),
            f"Ожидалось сообщение об ошибке, получено: {error_plain}",
        )

    @patch("scripts.the_helper._edit_safe", new_callable=AsyncMock)
    def test_disallowed_intent_fallbacks_to_rag(self, mock_edit_safe):
        """Неразрешённый intent в THE_HELPER принудительно отправляется в RAG."""
        event = self._make_event(raw_text="/helpme вопрос по сертификации")
        client = AsyncMock()
        rl = HelperRateLimiter(user_max=10, user_window=60, group_max=100, group_window=60)

        mock_router = AsyncMock()

        async def _route_side_effect(*args, **kwargs):
            on_classified = kwargs.get("on_classified")
            if on_classified is not None:
                classification = MagicMock()
                classification.intent = "certification_info"
                await on_classified(classification)
            return "Ответ модуля сертификации", "routed"

        mock_router.route = AsyncMock(side_effect=_route_side_effect)

        mock_rag_service = AsyncMock()
        mock_rag_answer = MagicMock()
        mock_rag_answer.text = "RAG fallback ответ"
        mock_rag_service.answer_question = AsyncMock(return_value=mock_rag_answer)

        with patch(
            "src.sbs_helper_telegram_bot.ai_router.intent_router.get_router",
            return_value=mock_router,
        ), patch(
            "src.core.ai.rag_service.get_rag_service",
            return_value=mock_rag_service,
        ), patch(
            "src.sbs_helper_telegram_bot.ai_router.messages.format_rag_answer_markdown_v2",
            return_value="RAG fallback ответ",
        ):
            _run_async(handle_help(event, client, rl))

        mock_router.route.assert_awaited_once()
        mock_rag_service.answer_question.assert_awaited_once()


# ===========================================================================
# Конфигурация групп
# ===========================================================================

class TestGroupConfig(unittest.TestCase):
    """Тесты загрузки и сохранения конфигурации групп."""

    def test_get_group_ids(self):
        """get_group_ids извлекает ID из списка групп."""
        groups = [
            {"id": -100111, "title": "Group A"},
            {"id": -100222, "title": "Group B"},
        ]
        self.assertEqual(get_group_ids(groups), [-100111, -100222])

    def test_get_group_ids_empty(self):
        """Пустой список → пустой результат."""
        self.assertEqual(get_group_ids([]), [])

    def test_get_group_ids_skips_invalid(self):
        """Пропускает записи без числового id."""
        groups = [
            {"id": -100111, "title": "OK"},
            {"title": "No ID"},
            {"id": "not_int", "title": "String ID"},
        ]
        self.assertEqual(get_group_ids(groups), [-100111])

    @patch("scripts.the_helper.GROUPS_CONFIG_PATH")
    def test_load_groups_missing_file(self, mock_path):
        """Отсутствующий файл → пустой список."""
        mock_path.exists.return_value = False
        result = load_groups()
        self.assertEqual(result, [])

    def test_load_groups_filters_disabled(self):
        """load_groups исключает группы с disabled=true."""
        import tempfile
        config = {
            "groups": [
                {"id": -100, "title": "Active"},
                {"id": -200, "title": "Disabled", "disabled": True},
                {"id": -300, "title": "Also active", "disabled": False},
            ]
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(config, f)
            tmp_path = f.name

        try:
            with patch("scripts.the_helper.GROUPS_CONFIG_PATH", Path(tmp_path)):
                result = load_groups()
                self.assertEqual(len(result), 2)
                ids = [g["id"] for g in result]
                self.assertIn(-100, ids)
                self.assertIn(-300, ids)
                self.assertNotIn(-200, ids)
        finally:
            import os
            os.unlink(tmp_path)


class TestParseIndexSelection(unittest.TestCase):
    """Тесты parse_index_selection для CLI-выбора групп."""

    def test_empty_input(self):
        """Пустой ввод возвращает пустой список."""
        self.assertEqual(parse_index_selection("", 10), [])

    def test_parse_comma_numbers(self):
        """Парсинг списка номеров через запятую."""
        self.assertEqual(parse_index_selection("1,3,2", 5), [1, 2, 3])

    def test_parse_range(self):
        """Парсинг диапазона номеров."""
        self.assertEqual(parse_index_selection("2-4", 10), [2, 3, 4])

    def test_parse_mixed(self):
        """Парсинг смешанного формата: числа + диапазон."""
        self.assertEqual(parse_index_selection("1,3-5,7", 10), [1, 3, 4, 5, 7])

    def test_out_of_range(self):
        """Номер вне диапазона вызывает ValueError."""
        with self.assertRaises(ValueError):
            parse_index_selection("11", 10)

    def test_bad_range_order(self):
        """Диапазон с обратным порядком вызывает ValueError."""
        with self.assertRaises(ValueError):
            parse_index_selection("5-2", 10)

    def test_bad_token(self):
        """Некорректный токен вызывает ValueError."""
        with self.assertRaises(ValueError):
            parse_index_selection("1,abc", 10)


class TestListenerStartup(unittest.TestCase):
    """Тесты старта run_listener: валидация групп и Telethon-сессии."""

    @patch("scripts.the_helper.asyncio.to_thread", new_callable=AsyncMock)
    @patch("scripts.the_helper.start_telegram_client_with_logging", new_callable=AsyncMock)
    @patch("scripts.the_helper.get_group_ids")
    @patch("scripts.the_helper.load_groups")
    def test_run_listener_exits_when_no_groups(
        self,
        mock_load_groups,
        mock_get_group_ids,
        mock_start_client,
        mock_to_thread,
    ):
        """При пустом списке групп listener завершает работу с ошибкой."""
        mock_load_groups.return_value = []
        mock_get_group_ids.return_value = []
        mock_to_thread.return_value = None

        with self.assertRaises(SystemExit) as cm:
            _run_async(run_listener())

        self.assertEqual(cm.exception.code, 1)
        mock_start_client.assert_not_called()

    @patch("scripts.the_helper.asyncio.to_thread", new_callable=AsyncMock)
    @patch("scripts.the_helper.start_telegram_client_with_logging", new_callable=AsyncMock)
    @patch("scripts.the_helper.get_group_ids")
    @patch("scripts.the_helper.load_groups")
    def test_run_listener_exits_on_unauthorized_session(
        self,
        mock_load_groups,
        mock_get_group_ids,
        mock_start_client,
        mock_to_thread,
    ):
        """Если сессия не авторизована, listener завершает работу до старта событий."""
        mock_load_groups.return_value = [{"id": -100111, "title": "Test Group"}]
        mock_get_group_ids.return_value = [-100111]
        mock_start_client.return_value = None
        mock_to_thread.return_value = None

        with patch("scripts.the_helper.TELETHON_API_ID", 123456), patch(
            "scripts.the_helper.TELETHON_API_HASH", "abc123hash"
        ):
            with self.assertRaises(SystemExit) as cm:
                _run_async(run_listener())

        self.assertEqual(cm.exception.code, 1)
        mock_start_client.assert_awaited_once_with(
            session_path=str(PROJECT_ROOT / HELPER_SESSION_NAME),
            api_id=123456,
            api_hash="abc123hash",
            logger=unittest.mock.ANY,
            interactive=False,
        )


# ===========================================================================
# Сообщения
# ===========================================================================

class TestMessages(unittest.TestCase):
    """Тесты корректности MarkdownV2-сообщений."""

    def test_rate_limit_user_format(self):
        """Сообщение rate-limit пользователя форматируется."""
        msg = MSG_RATE_LIMIT_USER.format(seconds="30")
        self.assertIn("30", msg)

    def test_rate_limit_group_format(self):
        """Сообщение rate-limit группы форматируется."""
        msg = MSG_RATE_LIMIT_GROUP.format(seconds="15")
        self.assertIn("15", msg)

    def test_usage_hint_contains_help(self):
        """Подсказка содержит /helpme."""
        plain = _strip_markdown_v2_escaping(MSG_USAGE_HINT)
        self.assertIn("/helpme", plain)

    def test_error_message_not_empty(self):
        """Сообщение об ошибке не пустое."""
        self.assertTrue(len(MSG_ERROR) > 10)


if __name__ == "__main__":
    unittest.main()
