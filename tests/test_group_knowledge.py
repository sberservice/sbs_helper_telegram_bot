"""
Тесты для подсистемы Group Knowledge.

Покрывает: модели данных, эвристику вопросов, rate limiter,
парсинг JSON из LLM, анализатор Q&A, сервис поиска.
"""

import asyncio
import json
import importlib
import logging
import sqlite3
import types
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _run_async(coro):
    """Запустить корутину в новом event loop (совместимо с Python 3.10+)."""
    return asyncio.run(coro)


# ===========================================================================
# Models
# ===========================================================================

class TestGroupMessage(unittest.TestCase):
    """Тесты для GroupMessage dataclass."""

    def test_default_values(self):
        """Значения по умолчанию."""
        from src.group_knowledge.models import GroupMessage
        msg = GroupMessage(
            telegram_message_id=100,
            group_id=-1001234,
            sender_id=555,
            message_text="привет",
            message_date=int(time.time()),
        )
        self.assertEqual(msg.telegram_message_id, 100)
        self.assertEqual(msg.group_id, -1001234)
        self.assertIsNone(msg.id)
        self.assertIsNone(msg.caption)
        self.assertFalse(msg.has_image)
        self.assertFalse(msg.processed)

    def test_full_text_only_message(self):
        """full_text с только message_text."""
        from src.group_knowledge.models import GroupMessage
        msg = GroupMessage(
            telegram_message_id=1,
            group_id=-100,
            sender_id=1,
            message_text="Текст сообщения",
            message_date=0,
        )
        self.assertEqual(msg.full_text, "Текст сообщения")

    def test_full_text_with_caption(self):
        """full_text с message_text и caption."""
        from src.group_knowledge.models import GroupMessage
        msg = GroupMessage(
            telegram_message_id=1,
            group_id=-100,
            sender_id=1,
            message_text="Текст",
            caption="Подпись к фото",
            message_date=0,
        )
        self.assertEqual(msg.full_text, "Текст\nПодпись к фото")

    def test_full_text_only_caption(self):
        """full_text с только caption."""
        from src.group_knowledge.models import GroupMessage
        msg = GroupMessage(
            telegram_message_id=1,
            group_id=-100,
            sender_id=1,
            message_text="",
            caption="Подпись",
            message_date=0,
        )
        self.assertEqual(msg.full_text, "Подпись")

    def test_full_text_with_image_description(self):
        """full_text с описанием изображения."""
        from src.group_knowledge.models import GroupMessage
        msg = GroupMessage(
            telegram_message_id=1,
            group_id=-100,
            sender_id=1,
            message_text="Смотри ошибку",
            has_image=True,
            image_description="Скриншот с кодом ошибки 1001",
            message_date=0,
        )
        self.assertIn("Смотри ошибку", msg.full_text)
        self.assertIn("Скриншот с кодом ошибки 1001", msg.full_text)


class TestQAPair(unittest.TestCase):
    """Тесты для QAPair dataclass."""

    def test_creation(self):
        """Создание QAPair."""
        from src.group_knowledge.models import QAPair
        pair = QAPair(
            question_text="Как перезагрузить UPOS?",
            answer_text="Зажмите кнопку питания на 10 секунд",
            group_id=-1001234,
            extraction_type="thread_reply",
            confidence=0.85,
        )
        self.assertEqual(pair.extraction_type, "thread_reply")
        self.assertEqual(pair.confidence, 0.85)
        self.assertTrue(pair.approved)

    def test_default_approved(self):
        """По умолчанию approved=True."""
        from src.group_knowledge.models import QAPair
        pair = QAPair(
            question_text="q", answer_text="a",
            group_id=0, extraction_type="thread_reply",
        )
        self.assertTrue(pair.approved)


class TestAnalysisResult(unittest.TestCase):
    """Тесты для AnalysisResult."""

    def test_defaults(self):
        from src.group_knowledge.models import AnalysisResult
        result = AnalysisResult(date="2024-01-15", group_id=-100)
        self.assertEqual(result.total_messages, 0)
        self.assertEqual(result.thread_pairs_found, 0)
        self.assertEqual(result.llm_pairs_found, 0)
        self.assertEqual(result.errors, [])

    def test_error_accumulation(self):
        from src.group_knowledge.models import AnalysisResult
        result = AnalysisResult(date="2024-01-15", group_id=-100)
        result.errors.append("error1")
        result.errors.append("error2")
        self.assertEqual(len(result.errors), 2)


class TestResponderResult(unittest.TestCase):
    """Тесты для ResponderResult."""

    def test_creation(self):
        from src.group_knowledge.models import ResponderResult
        result = ResponderResult(
            question_text="Как настроить NFC?",
            answer_text="Нужно включить NFC в настройках",
            confidence=0.9,
            dry_run=True,
        )
        self.assertTrue(result.dry_run)
        self.assertFalse(result.responded)


# ===========================================================================
# Settings
# ===========================================================================

class TestSettings(unittest.TestCase):
    """Тесты для настроек модуля."""

    def test_question_keywords_are_tuple(self):
        from src.group_knowledge.settings import QUESTION_KEYWORDS_RU
        self.assertIsInstance(QUESTION_KEYWORDS_RU, tuple)
        self.assertIn("как", QUESTION_KEYWORDS_RU)
        self.assertIn("почему", QUESTION_KEYWORDS_RU)

    def test_min_question_length(self):
        from src.group_knowledge.settings import MIN_QUESTION_LENGTH
        self.assertGreater(MIN_QUESTION_LENGTH, 0)
        self.assertLessEqual(MIN_QUESTION_LENGTH, 50)


# ===========================================================================
# Responder — question detection heuristic
# ===========================================================================

class TestLooksLikeQuestion(unittest.TestCase):
    """Тесты для GroupResponder._looks_like_question."""

    def setUp(self):
        from src.group_knowledge.responder import GroupResponder
        self._check = GroupResponder._looks_like_question

    def test_question_mark(self):
        """Вопросительный знак."""
        self.assertTrue(self._check("Как починить терминал? Очень срочно"))

    def test_starts_with_keyword(self):
        """Начинается с вопросительного слова."""
        self.assertTrue(self._check("Как настроить NFC модуль терминала"))
        self.assertTrue(self._check("Почему терминал не включается при подключении"))
        self.assertTrue(self._check("Где найти логи ошибок в терминале"))

    def test_question_patterns(self):
        """Паттерны вопросов."""
        self.assertTrue(self._check("терминал не работает после обновления прошивки"))
        self.assertTrue(self._check("что делать если появилась ошибка при загрузке"))
        self.assertTrue(self._check("подскажите как подключить принтер к терминалу"))

    def test_too_short(self):
        """Слишком короткое — не вопрос."""
        self.assertFalse(self._check("привет"))
        self.assertFalse(self._check("ok"))
        self.assertFalse(self._check(""))

    def test_not_question(self):
        """Обычные утверждения."""
        self.assertFalse(self._check("Спасибо за ответ, всё понял"))
        self.assertFalse(self._check("Отлично работает, отличная штука для работы"))

    def test_none_or_empty(self):
        """None или пустая строка."""
        self.assertFalse(self._check(""))
        self.assertFalse(self._check(None))


# ===========================================================================
# Responder — rate limiter
# ===========================================================================

class TestGKRateLimiter(unittest.TestCase):
    """Тесты для GKRateLimiter."""

    def test_user_allowed_within_limit(self):
        from src.group_knowledge.responder import GKRateLimiter
        rl = GKRateLimiter()
        # Первый запрос должен быть разрешён
        self.assertIsNone(rl.check_user(123))

    def test_user_blocked_over_limit(self):
        from src.group_knowledge.responder import GKRateLimiter
        rl = GKRateLimiter()
        # Заполнить до лимита
        for _ in range(20):
            rl.record(123, -100)
        result = rl.check_user(123)
        self.assertIsNotNone(result)
        self.assertGreater(result, 0)

    def test_group_limit(self):
        from src.group_knowledge.responder import GKRateLimiter
        rl = GKRateLimiter()
        for i in range(50):
            rl.record(i, -100)
        result = rl.check_group(-100)
        self.assertIsNotNone(result)

    def test_different_users_independent(self):
        from src.group_knowledge.responder import GKRateLimiter
        rl = GKRateLimiter()
        for _ in range(20):
            rl.record(111, -100)
        # User 222 не затронут
        self.assertIsNone(rl.check_user(222))

    def test_window_expiry(self):
        from src.group_knowledge.responder import GKRateLimiter
        rl = GKRateLimiter()
        # Подменить таймстампы на старые
        old_time = time.time() - 300
        for _ in range(20):
            rl._user_timestamps[123].append(old_time)
        # После очистки должен быть разрешён
        self.assertIsNone(rl.check_user(123))


# ===========================================================================
# QA Analyzer — JSON parsing
# ===========================================================================

class TestQAAnalyzerJsonParsing(unittest.TestCase):
    """Тесты для QAAnalyzer._parse_json_response."""

    def setUp(self):
        from src.group_knowledge.qa_analyzer import QAAnalyzer
        self._parse = QAAnalyzer._parse_json_response

    def test_clean_json(self):
        """Чистый JSON."""
        raw = '{"is_valid_qa": true, "confidence": 0.9}'
        result = self._parse(raw)
        self.assertTrue(result["is_valid_qa"])

    def test_markdown_code_block(self):
        """JSON в markdown code-блоке."""
        raw = '```json\n{"key": "value"}\n```'
        result = self._parse(raw)
        self.assertEqual(result["key"], "value")

    def test_json_with_text_around(self):
        """JSON с текстом вокруг."""
        raw = 'Результат: {"pairs": []} конец'
        result = self._parse(raw)
        self.assertEqual(result["pairs"], [])

    def test_empty_string(self):
        """Пустая строка."""
        self.assertIsNone(self._parse(""))
        self.assertIsNone(self._parse(None))

    def test_invalid_json(self):
        """Невалидный JSON."""
        self.assertIsNone(self._parse("not json at all"))


# ===========================================================================
# QA Search — JSON parsing
# ===========================================================================

class TestQASearchJsonParsing(unittest.TestCase):
    """Тесты для QASearchService._parse_json_response."""

    def setUp(self):
        from src.group_knowledge.qa_search import QASearchService
        self._parse = QASearchService._parse_json_response

    def test_clean_json(self):
        raw = '{"answer": "test", "is_relevant": true, "confidence": 0.8}'
        result = self._parse(raw)
        self.assertEqual(result["answer"], "test")

    def test_malformed(self):
        self.assertIsNone(self._parse("broken{"))


# ===========================================================================
# Database — store_message & query (mocked)
# ===========================================================================

class TestDatabaseLayer(unittest.TestCase):
    """Тесты для database.py с моками MySQL."""

    @patch("src.group_knowledge.database.get_db_connection")
    def test_store_message(self, mock_conn_ctx):
        """Сохранение сообщения выполняет INSERT."""
        from src.group_knowledge.database import store_message
        from src.group_knowledge.models import GroupMessage

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 42
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            msg = GroupMessage(
                telegram_message_id=100,
                group_id=-1001234,
                sender_id=555,
                sender_name="Test User",
                message_text="Тестовое сообщение",
                message_date=int(time.time()),
            )

            result = store_message(msg)
            self.assertEqual(result, 42)
            mock_cursor.execute.assert_called_once()

    @patch("src.group_knowledge.database.get_db_connection")
    def test_store_qa_pair(self, mock_conn_ctx):
        """Сохранение QA-пары."""
        from src.group_knowledge.database import store_qa_pair
        from src.group_knowledge.models import QAPair

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.lastrowid = 7
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            pair = QAPair(
                question_text="Вопрос",
                answer_text="Ответ",
                group_id=-100,
                extraction_type="thread_reply",
                confidence=0.9,
                llm_model_used="deepseek-chat",
            )

            result = store_qa_pair(pair)
            self.assertEqual(result, 7)

    @patch("src.group_knowledge.database.get_db_connection")
    def test_get_messages_for_date(self, mock_conn_ctx):
        """Запрос сообщений за дату."""
        from src.group_knowledge.database import get_messages_for_date

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1,
                "telegram_message_id": 100,
                "group_id": -1001234,
                "group_title": "Test Group",
                "sender_id": 555,
                "sender_name": "User",
                "message_text": "Hello",
                "caption": None,
                "has_image": 0,
                "image_description": None,
                "image_path": None,
                "reply_to_message_id": None,
                "message_date": int(time.time()),
                "processed": 0,
                "date_collected": "2024-01-15 10:00:00",
            }
        ]
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            messages = get_messages_for_date(-1001234, "2024-01-15")
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0].telegram_message_id, 100)


# ===========================================================================
# Image Processor
# ===========================================================================

class TestImageProcessor(unittest.TestCase):
    """Тесты для ImageProcessor."""

    def test_describe_image_file_not_found(self):
        """Описание несуществующего файла возвращает ошибку."""
        from src.group_knowledge.image_processor import ImageProcessor

        with patch("src.group_knowledge.image_processor.GigaChatProvider"):
            processor = ImageProcessor()
            result = _run_async(processor.describe_image("/nonexistent/image.jpg"))
            self.assertFalse(result.success)
            self.assertIn("Файл не найден", result.error)

    def test_describe_image_success(self):
        """Успешное описание изображения."""
        from src.group_knowledge.image_processor import ImageProcessor

        mock_provider = MagicMock()
        mock_provider.describe_image = AsyncMock(return_value="Скриншот ошибки")
        mock_provider.get_model_name.return_value = "GigaChat-Pro"

        processor = ImageProcessor(gigachat_provider=mock_provider)
        with patch("os.path.exists", return_value=True):
            result = _run_async(processor.describe_image("/fake/image.jpg"))
        self.assertTrue(result.success)
        self.assertEqual(result.description, "Скриншот ошибки")
        self.assertEqual(result.model_used, "GigaChat-Pro")

    def test_process_queue_logs_gigachat_description(self):
        """Логирует текстовое описание изображения от GigaChat."""
        from src.group_knowledge.image_processor import ImageProcessor

        mock_provider = MagicMock()
        mock_provider.get_model_name.return_value = "GigaChat-Pro"

        processor = ImageProcessor(gigachat_provider=mock_provider)

        with patch("src.group_knowledge.image_processor.gk_db.get_pending_images", return_value=[
            {"id": 10, "message_id": 20, "image_path": "/fake/image.jpg"}
        ]), patch(
            "src.group_knowledge.image_processor.gk_db.update_image_status"
        ) as mock_update_status, patch(
            "src.group_knowledge.image_processor.gk_db.update_message_image_description"
        ) as mock_update_description, patch.object(
            processor,
            "describe_image",
            AsyncMock(return_value=types.SimpleNamespace(
                success=True,
                description="На скриншоте ошибка подключения к серверу",
                error=None,
            )),
        ), patch(
            "src.group_knowledge.image_processor.asyncio.sleep",
            AsyncMock(),
        ), patch(
            "src.group_knowledge.image_processor.logger.info"
        ) as mock_logger_info:
            processed = _run_async(processor.process_queue(batch_size=1))

        self.assertEqual(processed, 1)
        mock_update_description.assert_called_once_with(
            20, "На скриншоте ошибка подключения к серверу"
        )
        self.assertTrue(mock_update_status.called)
        self.assertTrue(any(
            call.args and call.args[0] == "GigaChat видит на изображении: queue_id=%d message_id=%d description=%s"
            and call.args[1] == 10
            and call.args[2] == 20
            and call.args[3] == "На скриншоте ошибка подключения к серверу"
            for call in mock_logger_info.call_args_list
        ))


class TestMessageCollectorBackfill(unittest.TestCase):
    """Тесты backfill-режима коллектора."""

    @staticmethod
    def _make_message(message_id: int, text: str = "Текст", has_image: bool = False):
        """Создать фейковое сообщение Telethon для backfill."""
        sender = types.SimpleNamespace(id=101, bot=False, first_name="Иван", last_name="")
        message = types.SimpleNamespace(
            id=message_id,
            text=text,
            message=text,
            media=object() if has_image else None,
            action=None,
            reply_to=None,
            date=datetime.now(),
        )
        message.get_sender = AsyncMock(return_value=sender)
        return message

    @staticmethod
    async def _iter_messages(messages):
        """Асинхронный генератор сообщений Telethon."""
        for message in messages:
            yield message

    def test_backfill_skips_existing_messages_without_force(self):
        """Обычный backfill пропускает уже собранные сообщения."""
        from src.group_knowledge.message_collector import MessageCollector
        from src.group_knowledge.models import GroupMessage

        client = MagicMock()
        client.get_entity = AsyncMock(return_value=object())
        message = self._make_message(5001, has_image=True)
        client.iter_messages = MagicMock(return_value=self._iter_messages([message]))

        image_processor = MagicMock()
        image_processor.download_image = AsyncMock(return_value="/tmp/new.jpg")

        collector = MessageCollector(
            client=client,
            image_processor=image_processor,
            groups=[{"id": -1001234, "title": "Test Group"}],
        )

        existing = GroupMessage(
            id=77,
            telegram_message_id=5001,
            group_id=-1001234,
            has_image=True,
            image_path="/tmp/old.jpg",
        )

        with patch("src.group_knowledge.message_collector.gk_db.get_message_by_telegram_id", return_value=existing), \
             patch("src.group_knowledge.message_collector.gk_db.store_message") as mock_store, \
               patch("src.group_knowledge.message_collector.gk_db.enqueue_image") as mock_enqueue, \
               patch.object(collector, "_message_has_image", return_value=True):
            result = _run_async(collector.backfill_messages(days=1, force=False))

        self.assertEqual(result, 0)
        mock_store.assert_not_called()
        mock_enqueue.assert_not_called()
        image_processor.download_image.assert_not_called()

    def test_backfill_force_redownloads_and_requeues_images(self):
        """Force-backfill сбрасывает старую обработку и заново качает изображение."""
        from src.group_knowledge.message_collector import MessageCollector
        from src.group_knowledge.models import GroupMessage

        client = MagicMock()
        client.get_entity = AsyncMock(return_value=object())
        message = self._make_message(5002, has_image=True)
        client.iter_messages = MagicMock(return_value=self._iter_messages([message]))

        image_processor = MagicMock()
        image_processor.download_image = AsyncMock(return_value="/tmp/new.jpg")

        collector = MessageCollector(
            client=client,
            image_processor=image_processor,
            groups=[{"id": -1001234, "title": "Test Group"}],
        )

        existing = GroupMessage(
            id=88,
            telegram_message_id=5002,
            group_id=-1001234,
            has_image=True,
            image_path="/tmp/old.jpg",
        )

        with patch("src.group_knowledge.message_collector.gk_db.get_message_by_telegram_id", return_value=existing), \
             patch("src.group_knowledge.message_collector.gk_db.store_message", return_value=88) as mock_store, \
             patch("src.group_knowledge.message_collector.gk_db.reset_message_image_processing") as mock_reset, \
             patch("src.group_knowledge.message_collector.gk_db.update_message_image_path") as mock_update_path, \
             patch("src.group_knowledge.message_collector.gk_db.enqueue_image") as mock_enqueue, \
             patch("src.group_knowledge.message_collector.os.path.exists", return_value=True), \
               patch("src.group_knowledge.message_collector.os.remove") as mock_remove, \
               patch.object(collector, "_message_has_image", return_value=True):
            result = _run_async(collector.backfill_messages(days=1, force=True))

        self.assertEqual(result, 1)
        mock_store.assert_called_once()
        mock_reset.assert_called_once_with(88)
        mock_remove.assert_called_once_with("/tmp/old.jpg")
        mock_update_path.assert_called_once_with(88, "/tmp/new.jpg")
        mock_enqueue.assert_called_once_with(88, "/tmp/new.jpg")
        image_processor.download_image.assert_awaited_once()


# ===========================================================================
# QA Analyzer — thread pair extraction (mocked LLM)
# ===========================================================================

class TestQAAnalyzerThreadExtraction(unittest.TestCase):
    """Тесты для thread-based Q&A извлечения."""

    def _make_message(
        self,
        db_id,
        telegram_id,
        sender_id,
        text,
        reply_to=None,
        date_offset=0,
    ):
        """Создать тестовое сообщение для reply-цепочки."""
        from src.group_knowledge.models import GroupMessage

        return GroupMessage(
            id=db_id,
            telegram_message_id=telegram_id,
            group_id=-1001234,
            sender_id=sender_id,
            sender_name=f"User {sender_id}",
            message_text=text,
            reply_to_message_id=reply_to,
            message_date=1000 + date_offset,
        )

    def test_validate_qa_pair_valid(self):
        """Валидная пара проходит LLM-валидацию."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "is_valid_qa": True,
            "confidence": 0.85,
            "clean_question": "Как перезагрузить терминал?",
            "clean_answer": "Зажмите кнопку питания на 10 секунд",
        }))

        analyzer = QAAnalyzer()
        with patch("src.group_knowledge.qa_analyzer.get_provider", return_value=mock_provider):
            result = _run_async(
                analyzer._validate_qa_pair("как перезагружать", "зажми кнопку")
            )
        self.assertIsNotNone(result)
        q, a, conf = result
        self.assertEqual(q, "Как перезагрузить терминал?")
        self.assertAlmostEqual(conf, 0.85, places=2)

    def test_validate_qa_pair_invalid(self):
        """Невалидная пара отклоняется."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "is_valid_qa": False,
            "confidence": 0.1,
        }))

        analyzer = QAAnalyzer()
        with patch("src.group_knowledge.qa_analyzer.get_provider", return_value=mock_provider):
            result = _run_async(
                analyzer._validate_qa_pair("привет", "привет!")
            )
        self.assertIsNone(result)

    def test_validate_qa_pair_llm_error(self):
        """Ошибка LLM возвращает None."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(side_effect=Exception("API error"))

        analyzer = QAAnalyzer()
        with patch("src.group_knowledge.qa_analyzer.get_provider", return_value=mock_provider):
            result = _run_async(
                analyzer._validate_qa_pair("вопрос", "ответ")
            )
        self.assertIsNone(result)

    def test_collect_thread_messages_recursive_chain(self):
        """Сбор полной цепочки включает вложенные reply-сообщения."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        messages = [
            self._make_message(1, 101, 1, "Не работает терминал"),
            self._make_message(2, 102, 2, "Какая ошибка?", reply_to=101, date_offset=1),
            self._make_message(3, 103, 1, "Ошибка 1001", reply_to=102, date_offset=2),
            self._make_message(4, 104, 2, "Перезагрузите и обновите конфиг", reply_to=103, date_offset=3),
            self._make_message(5, 105, 1, "Спасибо, помогло", reply_to=104, date_offset=4),
        ]
        children_index = analyzer._build_reply_children_index(messages)
        collected = analyzer._collect_thread_messages(messages[0], children_index)

        self.assertEqual([msg.telegram_message_id for msg in collected], [101, 102, 103, 104, 105])

    def test_find_last_meaningful_message_skips_thanks(self):
        """Последнее осмысленное сообщение выбирается до благодарности."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        messages = [
            self._make_message(1, 101, 1, "Как исправить ошибку 1001?"),
            self._make_message(2, 102, 2, "Проверьте логи", reply_to=101, date_offset=1),
            self._make_message(3, 103, 2, "Перезагрузите терминал и обновите конфиг", reply_to=102, date_offset=2),
            self._make_message(4, 104, 1, "Спасибо, всё заработало", reply_to=103, date_offset=3),
        ]

        result = analyzer._find_last_meaningful_message(messages, question_sender_id=1)
        self.assertIsNotNone(result)
        self.assertEqual(result.telegram_message_id, 103)

    def test_extract_thread_pairs_from_chain(self):
        """Из reply-цепочки извлекается одна итоговая Q&A-пара."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        messages = [
            self._make_message(1, 101, 1, "Не работает терминал, ошибка 1001"),
            self._make_message(2, 102, 2, "Какая версия прошивки?", reply_to=101, date_offset=1),
            self._make_message(3, 103, 1, "Версия 3.1.4", reply_to=102, date_offset=2),
            self._make_message(4, 104, 2, "Нужно перезагрузить терминал и обновить конфиг", reply_to=103, date_offset=3),
            self._make_message(5, 105, 1, "Спасибо, помогло", reply_to=104, date_offset=4),
        ]

        with patch.object(
            analyzer,
            "_validate_thread_chain",
            new=AsyncMock(return_value=(
                "Как исправить ошибку 1001 на терминале?",
                "Перезагрузите терминал и обновите конфиг.",
                0.93,
                104,
            )),
        ):
            with patch("src.group_knowledge.qa_analyzer.gk_db.store_qa_pair", return_value=77):
                with patch("src.group_knowledge.qa_analyzer.asyncio.sleep", new=AsyncMock()):
                    pairs = _run_async(analyzer._extract_thread_pairs(messages))

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].id, 77)
        self.assertEqual(pairs[0].question_message_id, 1)
        self.assertEqual(pairs[0].answer_message_id, 4)
        self.assertEqual(pairs[0].extraction_type, "thread_reply")

    def test_extract_thread_pairs_skips_single_sender_chain(self):
        """Цепочка одного отправителя не считается Q&A."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        messages = [
            self._make_message(1, 101, 1, "Не работает"),
            self._make_message(2, 102, 1, "Дополнение к проблеме", reply_to=101, date_offset=1),
        ]

        with patch.object(analyzer, "_validate_thread_chain", new=AsyncMock()) as mock_validate:
            pairs = _run_async(analyzer._extract_thread_pairs(messages))

        self.assertEqual(pairs, [])
        mock_validate.assert_not_called()


# ===========================================================================
# QA Search — answer_question (mocked)
# ===========================================================================

class TestQASearchAnswer(unittest.TestCase):
    """Тесты для QASearchService.answer_question."""

    def test_build_group_message_link(self):
        """Ссылка на сообщение в супергруппе строится корректно."""
        from src.group_knowledge.qa_search import QASearchService

        link = QASearchService._build_group_message_link(-1001234567890, 321)
        self.assertEqual(link, "https://t.me/c/1234567890/321")

    def test_no_pairs_found(self):
        """Не найдено пар — возвращает None."""
        from src.group_knowledge.qa_search import QASearchService

        service = QASearchService()
        with patch.object(service, "search", new=AsyncMock(return_value=[])):
            result = _run_async(service.answer_question("Как починить NFC?"))
        self.assertIsNone(result)

    def test_answer_generated(self):
        """Ответ успешно сгенерирован."""
        from src.group_knowledge.qa_search import QASearchService
        from src.group_knowledge.models import QAPair

        mock_pairs = [
            QAPair(
                id=1,
                question_text="Как настроить NFC?",
                answer_text="Включите NFC в разделе настроек терминала",
                group_id=-100,
                extraction_type="thread_reply",
                confidence=0.9,
            )
        ]

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "answer": "Включите NFC в настройках терминала",
            "is_relevant": True,
            "confidence": 0.88,
            "used_pair_ids": [1],
        }))

        service = QASearchService()
        with patch.object(service, "search", new=AsyncMock(return_value=mock_pairs)):
            with patch("src.group_knowledge.qa_search.get_provider", return_value=mock_provider):
                result = _run_async(service.answer_question("Как включить NFC?"))

        self.assertIsNotNone(result)
        self.assertEqual(result["answer"], "Включите NFC в настройках терминала")
        self.assertAlmostEqual(result["confidence"], 0.88)
        self.assertTrue(result["is_relevant"])

    def test_answer_generated_with_source_link(self):
        """В ответ возвращается ссылка на похожий кейс из группы."""
        from src.group_knowledge.qa_search import QASearchService
        from src.group_knowledge.models import GroupMessage, QAPair

        mock_pairs = [
            QAPair(
                id=1,
                question_text="Как настроить NFC?",
                answer_text="Включите NFC в разделе настроек терминала",
                group_id=-1001234567890,
                extraction_type="thread_reply",
                confidence=0.9,
            )
        ]

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "answer": "Включите NFC в настройках терминала",
            "is_relevant": True,
            "confidence": 0.88,
            "used_pair_ids": [1],
        }))

        full_pair = QAPair(
            id=1,
            question_text="Как настроить NFC?",
            answer_text="Включите NFC в разделе настроек терминала",
            question_message_id=10,
            answer_message_id=11,
            group_id=-1001234567890,
            extraction_type="thread_reply",
        )
        answer_message = GroupMessage(
            id=11,
            telegram_message_id=555,
            group_id=-1001234567890,
            sender_id=2,
            message_text="Включите NFC в настройках",
            message_date=1,
        )

        service = QASearchService()
        with patch.object(service, "search", new=AsyncMock(return_value=mock_pairs)):
            with patch("src.group_knowledge.qa_search.get_provider", return_value=mock_provider):
                with patch("src.group_knowledge.qa_search.gk_db.get_qa_pair_by_id", return_value=full_pair):
                    with patch("src.group_knowledge.qa_search.gk_db.get_message_by_id", return_value=answer_message):
                        result = _run_async(service.answer_question("Как включить NFC?"))

        self.assertIsNotNone(result)
        self.assertEqual(
            result["primary_source_link"],
            "https://t.me/c/1234567890/555",
        )
        self.assertEqual(
            result["source_message_links"],
            ["https://t.me/c/1234567890/555"],
        )

    def test_answer_not_relevant(self):
        """LLM считает пары нерелевантными."""
        from src.group_knowledge.qa_search import QASearchService
        from src.group_knowledge.models import QAPair

        mock_pairs = [
            QAPair(id=1, question_text="q", answer_text="a",
                   group_id=-100, extraction_type="thread_reply")
        ]

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "answer": "",
            "is_relevant": False,
            "confidence": 0.1,
        }))

        service = QASearchService()
        with patch.object(service, "search", new=AsyncMock(return_value=mock_pairs)):
            with patch("src.group_knowledge.qa_search.get_provider", return_value=mock_provider):
                result = _run_async(service.answer_question("Что-то совсем другое"))
        self.assertIsNone(result)


# ===========================================================================
# Responder — handle_message (integration-like with mocks)
# ===========================================================================

class TestGroupResponderHandleMessage(unittest.TestCase):
    """Тесты для GroupResponder.handle_message."""

    def _make_event(self, text, chat_id, sender_id=123, is_bot=False,
                    is_reply=False, is_action=False, msg_age=5):
        """Создать мок Telethon NewMessage event."""
        from datetime import datetime, timezone

        event = MagicMock()
        message = MagicMock()
        message.text = text
        message.message = text
        message.id = 999
        message.action = MagicMock() if is_action else None
        message.date = datetime.fromtimestamp(
            time.time() - msg_age, tz=timezone.utc
        )
        message.reply_to = MagicMock() if is_reply else None

        event.message = message if not is_action else None
        if is_action:
            event.message = message

        chat = MagicMock()
        chat.id = abs(chat_id)
        chat.megagroup = True
        chat.broadcast = False
        event.chat = chat

        sender = MagicMock()
        sender.id = sender_id
        sender.bot = is_bot
        event.get_sender = AsyncMock(return_value=sender)

        return event

    def test_skip_non_question(self):
        """Пропуск не-вопросных сообщений."""
        from src.group_knowledge.responder import GroupResponder

        responder = GroupResponder(dry_run=True)
        event = self._make_event("Спасибо всем за помощь, всё починил", -1001234)

        result = _run_async(responder.handle_message(event, {-1001001234}))
        self.assertIsNone(result)

    def test_skip_bot(self):
        """Пропуск сообщений от ботов."""
        from src.group_knowledge.responder import GroupResponder

        responder = GroupResponder(dry_run=True)
        event = self._make_event("Как починить?", -1001234, is_bot=True)

        result = _run_async(responder.handle_message(event, {-1001001234}))
        self.assertIsNone(result)

    def test_skip_reply(self):
        """Пропуск reply (ответов на другие сообщения)."""
        from src.group_knowledge.responder import GroupResponder

        responder = GroupResponder(dry_run=True)
        event = self._make_event("Как починить?", -1001234, is_reply=True)

        result = _run_async(responder.handle_message(event, {-1001001234}))
        self.assertIsNone(result)

    def test_skip_old_message(self):
        """Пропуск слишком старых сообщений."""
        from src.group_knowledge.responder import GroupResponder

        responder = GroupResponder(dry_run=True)
        event = self._make_event("Как починить?", -1001234, msg_age=300)

        result = _run_async(responder.handle_message(event, {-1001001234}))
        self.assertIsNone(result)

    def test_skip_command(self):
        """Пропуск команд (/...)."""
        from src.group_knowledge.responder import GroupResponder

        responder = GroupResponder(dry_run=True)
        event = self._make_event("/help", -1001234)

        result = _run_async(responder.handle_message(event, {-1001001234}))
        self.assertIsNone(result)

    def test_dry_run_response(self):
        """В dry-run режиме ответ формируется но не отправляется."""
        from src.group_knowledge.responder import GroupResponder

        mock_qa = MagicMock()
        mock_qa.answer_question = AsyncMock(return_value={
            "answer": "Включите NFC в настройках",
            "confidence": 0.9,
            "source_pair_ids": [1],
            "is_relevant": True,
            "primary_source_link": "https://t.me/c/1234567890/555",
        })

        responder = GroupResponder(dry_run=True, qa_service=mock_qa)
        event = self._make_event(
            "Как настроить NFC модуль на терминале?", -1001234,
        )

        with patch("src.group_knowledge.responder.gk_db") as mock_db:
            result = _run_async(responder.handle_message(event, {-1001001234}))

        self.assertIsNotNone(result)
        self.assertTrue(result.dry_run)
        self.assertFalse(result.responded)
        self.assertAlmostEqual(result.confidence, 0.9)
        self.assertIn("https://t.me/c/1234567890/555", result.answer_text)

    def test_low_confidence_skipped(self):
        """Низкая уверенность — ответ не отправляется."""
        from src.group_knowledge.responder import GroupResponder

        mock_qa = MagicMock()
        mock_qa.answer_question = AsyncMock(return_value={
            "answer": "Может быть...",
            "confidence": 0.3,
            "source_pair_ids": [],
            "is_relevant": True,
        })

        responder = GroupResponder(
            dry_run=True,
            qa_service=mock_qa,
            confidence_threshold=0.7,
        )
        event = self._make_event(
            "Как настроить что-то там в терминале?", -1001234,
        )

        result = _run_async(responder.handle_message(event, {-1001001234}))
        self.assertIsNone(result)


# ===========================================================================
# GigaChatProvider
# ===========================================================================

class TestGigaChatProvider(unittest.TestCase):
    """Тесты для GigaChatProvider."""

    def test_provider_registered(self):
        """GigaChatProvider зарегистрирован в фабрике."""
        from src.core.ai.llm_provider import get_provider
        provider = get_provider("gigachat")
        self.assertIsNotNone(provider)

    def test_get_model_name(self):
        """Модель по умолчанию из настроек."""
        from src.core.ai.llm_provider import GigaChatProvider
        provider = GigaChatProvider()
        model = provider.get_model_name()
        self.assertIsNotNone(model)
        self.assertIn("GigaChat", model)

    def test_describe_image_no_path(self):
        """describe_image с несуществующим файлом выбрасывает ошибку."""
        from src.core.ai.llm_provider import GigaChatProvider
        provider = GigaChatProvider()

        with self.assertRaises(Exception):
            _run_async(provider.describe_image("/nonexistent/file.jpg"))


# ===========================================================================
# Message Collector — group config
# ===========================================================================

class TestGroupConfig(unittest.TestCase):
    """Тесты для load/save group config."""

    def test_load_nonexistent(self):
        """Загрузка несуществующего файла возвращает пустой список."""
        from src.group_knowledge.message_collector import load_groups_config
        with patch(
            "src.group_knowledge.message_collector.GK_GROUPS_CONFIG_PATH",
            Path("/nonexistent/gk_groups.json"),
        ):
            result = load_groups_config()
            self.assertEqual(result, [])

    def test_load_valid_config(self):
        """Загрузка валидного конфига."""
        import tempfile
        from src.group_knowledge.message_collector import load_groups_config

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump({"groups": [{"id": -100, "title": "Test"}]}, f)
            tmp_path = f.name

        try:
            with patch(
                "src.group_knowledge.message_collector.GK_GROUPS_CONFIG_PATH",
                Path(tmp_path),
            ):
                result = load_groups_config()
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["id"], -100)
        finally:
            import os
            os.unlink(tmp_path)


class TestGroupSelectionHelpers(unittest.TestCase):
    """Тесты интерактивного выбора групп из списка."""

    def test_parse_selection_numbers_single_and_range(self):
        """Парсинг одиночных номеров и диапазонов."""
        from src.group_knowledge.message_collector import _parse_selection_numbers

        result = _parse_selection_numbers("1,3,5-7", 10)
        self.assertEqual(result, [1, 3, 5, 6, 7])

    def test_parse_selection_numbers_deduplicates(self):
        """Повторяющиеся номера схлопываются."""
        from src.group_knowledge.message_collector import _parse_selection_numbers

        result = _parse_selection_numbers("1,2,2,1-3", 5)
        self.assertEqual(result, [1, 2, 3])

    def test_parse_selection_numbers_invalid_range(self):
        """Некорректный диапазон вызывает ошибку."""
        from src.group_knowledge.message_collector import _parse_selection_numbers

        with self.assertRaises(ValueError):
            _parse_selection_numbers("5-2", 10)

    def test_parse_selection_numbers_out_of_range(self):
        """Номер вне диапазона вызывает ошибку."""
        from src.group_knowledge.message_collector import _parse_selection_numbers

        with self.assertRaises(ValueError):
            _parse_selection_numbers("1,99", 5)

    @patch("builtins.input", return_value="1,3")
    @patch("src.group_knowledge.message_collector.save_groups_config")
    def test_add_groups_from_selection(self, mock_save, _mock_input):
        """Добавление нескольких групп из списка доступных."""
        from src.group_knowledge.message_collector import _add_groups_from_selection

        groups = [{"id": -1001, "title": "Уже есть"}]
        available = [
            {"id": -1002, "title": "Группа 2", "participants": 10},
            {"id": -1003, "title": "Группа 3", "participants": 20},
            {"id": -1004, "title": "Группа 4", "participants": 30},
        ]

        _add_groups_from_selection(groups, available)

        self.assertEqual(len(groups), 3)
        self.assertEqual(groups[1]["id"], -1002)
        self.assertEqual(groups[2]["id"], -1004)
        mock_save.assert_called_once()

    @patch("builtins.input", return_value="1")
    @patch("src.group_knowledge.message_collector.save_groups_config")
    def test_add_groups_from_selection_skips_existing(self, mock_save, _mock_input):
        """Уже добавленные группы не дублируются."""
        from src.group_knowledge.message_collector import _add_groups_from_selection

        groups = [{"id": -1002, "title": "Группа 2"}]
        available = [
            {"id": -1002, "title": "Группа 2", "participants": 10},
        ]

        _add_groups_from_selection(groups, available)

        self.assertEqual(len(groups), 1)
        mock_save.assert_not_called()


class TestGKSessionSelection(unittest.TestCase):
    """Тесты выбора выделенной Telethon-сессии."""

    @staticmethod
    def _import_script_module(module_name: str):
        """Импортировать скриптовый модуль с замоканным Telethon."""
        import sys

        fake_telethon = types.ModuleType("telethon")
        fake_telethon.TelegramClient = MagicMock()
        fake_telethon.events = MagicMock()

        fake_errors = types.ModuleType("telethon.errors")
        fake_errors.ApiIdInvalidError = type("ApiIdInvalidError", (Exception,), {})
        fake_errors.FloodWaitError = type("FloodWaitError", (Exception,), {})
        fake_errors.PhoneCodeExpiredError = type("PhoneCodeExpiredError", (Exception,), {})
        fake_errors.PhoneCodeInvalidError = type("PhoneCodeInvalidError", (Exception,), {})
        fake_errors.PhoneNumberInvalidError = type("PhoneNumberInvalidError", (Exception,), {})
        fake_errors.SessionPasswordNeededError = type("SessionPasswordNeededError", (Exception,), {})

        with patch.dict(
            sys.modules,
            {
                "telethon": fake_telethon,
                "telethon.errors": fake_errors,
            },
        ):
            return importlib.import_module(module_name)

    def test_collector_uses_dedicated_session(self):
        """Коллектор всегда использует собственную сессию."""
        gk_collector = self._import_script_module("scripts.gk_collector")

        resolved = gk_collector._resolve_session_name()

        self.assertEqual(resolved, gk_collector.GK_COLLECTOR_SESSION_NAME)

    def test_responder_uses_dedicated_session(self):
        """Автоответчик всегда использует собственную сессию."""
        gk_responder = self._import_script_module("scripts.gk_responder")

        resolved = gk_responder._resolve_session_name()

        self.assertEqual(resolved, gk_responder.GK_RESPONDER_SESSION_NAME)


class TestTelethonSessionHelpers(unittest.TestCase):
    """Тесты безопасного запуска Telethon-сессий."""

    def test_start_telegram_client_returns_none_on_sqlite_lock(self):
        """При SQLite-блокировке повторные попытки не выполняются."""
        from src.group_knowledge import telethon_session

        locked_client = MagicMock()
        locked_client.start = AsyncMock(side_effect=sqlite3.OperationalError("database is locked"))
        locked_client.disconnect = AsyncMock()

        fake_errors = types.ModuleType("telethon.errors")
        fake_errors.ApiIdInvalidError = type("ApiIdInvalidError", (Exception,), {})
        fake_errors.FloodWaitError = type("FloodWaitError", (Exception,), {})
        fake_errors.PhoneCodeExpiredError = type("PhoneCodeExpiredError", (Exception,), {})
        fake_errors.PhoneCodeInvalidError = type("PhoneCodeInvalidError", (Exception,), {})
        fake_errors.PhoneNumberInvalidError = type("PhoneNumberInvalidError", (Exception,), {})
        fake_errors.SessionPasswordNeededError = type("SessionPasswordNeededError", (Exception,), {})

        with patch.dict(sys.modules, {"telethon.errors": fake_errors}), \
             patch.object(telethon_session, "build_telegram_client", return_value=locked_client) as mock_build:
            result = _run_async(
                telethon_session.start_telegram_client_with_logging(
                    session_path="/tmp/test-session",
                    api_id=1,
                    api_hash="hash",
                    logger=logging.getLogger("test.telethon_session"),
                )
            )

        self.assertIsNone(result)
        mock_build.assert_called_once()
        locked_client.disconnect.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
