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


class TestQuestionClassifierService(unittest.TestCase):
    """Тесты общего LLM-классификатора вопросов."""

    def test_classify_message_as_question(self):
        """Классификатор возвращает parsed JSON как объект результата."""
        from src.group_knowledge.question_classifier import QuestionClassifierService

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "is_question": True,
            "confidence": 0.87,
            "reason": "Пользователь описывает проблему и просит решение",
        }))

        service = QuestionClassifierService(model_name="deepseek-test")
        with patch("src.group_knowledge.question_classifier.get_provider", return_value=mock_provider):
            result = _run_async(service.classify("терминал не включается после обновления"))

        self.assertTrue(result.is_question)
        self.assertAlmostEqual(result.confidence, 0.87, places=2)
        self.assertEqual(result.model_used, "deepseek-test")

    def test_classify_short_message_without_llm(self):
        """Слишком короткое сообщение не отправляется в LLM."""
        from src.group_knowledge.question_classifier import QuestionClassifierService

        service = QuestionClassifierService()
        with patch("src.group_knowledge.question_classifier.get_provider") as mock_get_provider:
            result = _run_async(service.classify("ok"))

        self.assertFalse(result.is_question)
        mock_get_provider.assert_not_called()


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


class TestQAAnalyzerAnalyzeDay(unittest.TestCase):
    """Тесты поведения analyze_day с учётом processed-флага."""

    def test_analyze_day_reads_only_unprocessed_messages(self):
        """Повторный запуск анализирует только processed=0 сообщения."""
        from src.group_knowledge.models import GroupMessage
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        messages = [
            GroupMessage(
                id=1,
                telegram_message_id=101,
                group_id=-1001234,
                sender_id=11,
                sender_name="User 11",
                message_text="Не работает терминал, как починить?",
                message_date=1000,
                processed=0,
            ),
            GroupMessage(
                id=2,
                telegram_message_id=102,
                group_id=-1001234,
                sender_id=22,
                sender_name="User 22",
                message_text="Перезапустите сервис",
                reply_to_message_id=101,
                message_date=1001,
                processed=0,
            ),
        ]

        with patch(
            "src.group_knowledge.qa_analyzer.gk_db.get_unprocessed_messages",
            return_value=messages,
        ) as mock_get_unprocessed:
            with patch.object(analyzer, "_extract_thread_pairs", new=AsyncMock(return_value=[])) as mock_thread:
                with patch.object(analyzer, "_extract_llm_inferred_pairs", new=AsyncMock(return_value=[])) as mock_llm:
                    with patch("src.group_knowledge.qa_analyzer.gk_db.mark_messages_processed") as mock_mark:
                        result = _run_async(analyzer.analyze_day(-1001234, "2026-03-06"))

        self.assertEqual(result.total_messages, 2)
        mock_get_unprocessed.assert_called_once_with(-1001234, "2026-03-06")
        mock_thread.assert_awaited_once()
        mock_llm.assert_awaited_once()
        mock_mark.assert_called_once_with([1, 2])

    def test_analyze_day_skips_when_no_unprocessed_messages(self):
        """Если новых сообщений нет, пары повторно не генерируются."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()

        with patch(
            "src.group_knowledge.qa_analyzer.gk_db.get_unprocessed_messages",
            return_value=[],
        ) as mock_get_unprocessed:
            with patch.object(analyzer, "_extract_thread_pairs", new=AsyncMock()) as mock_thread:
                with patch.object(analyzer, "_extract_llm_inferred_pairs", new=AsyncMock()) as mock_llm:
                    with patch("src.group_knowledge.qa_analyzer.gk_db.mark_messages_processed") as mock_mark:
                        result = _run_async(analyzer.analyze_day(-1001234, "2026-03-06"))

        self.assertEqual(result.total_messages, 0)
        self.assertEqual(result.thread_pairs_found, 0)
        self.assertEqual(result.llm_pairs_found, 0)
        mock_get_unprocessed.assert_called_once_with(-1001234, "2026-03-06")
        mock_thread.assert_not_awaited()
        mock_llm.assert_not_awaited()
        mock_mark.assert_not_called()

    def test_analyze_day_force_reanalyze_reads_all_messages(self):
        """С force_reanalyze анализатор берёт все сообщения за дату."""
        from src.group_knowledge.models import GroupMessage
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        messages = [
            GroupMessage(
                id=10,
                telegram_message_id=201,
                group_id=-1001234,
                sender_id=101,
                sender_name="User 101",
                message_text="Старое, но нужное сообщение",
                message_date=2000,
                processed=1,
            )
        ]

        with patch(
            "src.group_knowledge.qa_analyzer.gk_db.get_messages_for_date",
            return_value=messages,
        ) as mock_get_all:
            with patch("src.group_knowledge.qa_analyzer.gk_db.get_unprocessed_messages") as mock_get_unprocessed:
                with patch.object(analyzer, "_extract_thread_pairs", new=AsyncMock(return_value=[])) as mock_thread:
                    with patch.object(analyzer, "_extract_llm_inferred_pairs", new=AsyncMock(return_value=[])) as mock_llm:
                        with patch("src.group_knowledge.qa_analyzer.gk_db.mark_messages_processed") as mock_mark:
                            result = _run_async(
                                analyzer.analyze_day(
                                    -1001234,
                                    "2026-03-06",
                                    force_reanalyze=True,
                                )
                            )

        self.assertEqual(result.total_messages, 1)
        mock_get_all.assert_called_once_with(-1001234, "2026-03-06")
        mock_get_unprocessed.assert_not_called()
        mock_thread.assert_awaited_once()
        mock_llm.assert_awaited_once()
        mock_mark.assert_called_once_with([10])


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
    def test_store_qa_pair_updates_existing_by_question_message_id(self, mock_conn_ctx):
        """Повторная пара с тем же question_message_id обновляет запись, а не вставляет новую."""
        from src.group_knowledge.database import store_qa_pair
        from src.group_knowledge.models import QAPair

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            mock_cursor.fetchone.return_value = {"id": 55}

            pair = QAPair(
                question_text="Вопрос (обновлён)",
                answer_text="Ответ (обновлён)",
                question_message_id=123,
                answer_message_id=124,
                group_id=-100,
                extraction_type="thread_reply",
                confidence=0.95,
                llm_model_used="deepseek-chat",
            )

            result = store_qa_pair(pair)

            self.assertEqual(result, 55)
            self.assertEqual(mock_cursor.execute.call_count, 2)
            self.assertIn("SELECT id", mock_cursor.execute.call_args_list[0][0][0])
            self.assertIn("UPDATE gk_qa_pairs", mock_cursor.execute.call_args_list[1][0][0])

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

    @patch("src.group_knowledge.database.get_db_connection")
    def test_get_unprocessed_dates(self, mock_conn_ctx):
        """Возвращает все даты с необработанными сообщениями в хронологическом порядке."""
        from src.group_knowledge.database import get_unprocessed_dates

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"message_date": "2024-01-14"},
            {"message_date": "2024-01-15"},
        ]
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            dates = get_unprocessed_dates(-1001234)

        self.assertEqual(dates, ["2024-01-14", "2024-01-15"])
        mock_cursor.execute.assert_called_once()

    @patch("src.group_knowledge.database.get_db_connection")
    def test_get_qa_pair_ids_by_group(self, mock_conn_ctx):
        """Возвращает список ID Q&A-пар по группе."""
        from src.group_knowledge.database import get_qa_pair_ids_by_group

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [{"id": 10}, {"id": 11}]
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            pair_ids = get_qa_pair_ids_by_group(-1001234)

        self.assertEqual(pair_ids, [10, 11])
        mock_cursor.execute.assert_called_once()

    @patch("src.group_knowledge.database.get_db_connection")
    def test_delete_group_data_dry_run(self, mock_conn_ctx):
        """Dry-run возвращает статистику и не выполняет DELETE-запросы."""
        from src.group_knowledge.database import delete_group_data

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {"cnt": 5},
            {"cnt": 3},
            {"cnt": 2},
            {"cnt": 1},
        ]
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            stats = delete_group_data(-1001234, dry_run=True)

        self.assertEqual(stats["messages_found"], 5)
        self.assertEqual(stats["qa_pairs_found"], 3)
        self.assertEqual(stats["responder_logs_found"], 2)
        self.assertEqual(stats["image_queue_found"], 1)
        self.assertEqual(stats["messages_deleted"], 0)
        self.assertEqual(stats["dry_run"], 1)
        self.assertEqual(mock_cursor.execute.call_count, 4)

    @patch("src.group_knowledge.database.get_db_connection")
    def test_delete_group_data_executes_delete_queries(self, mock_conn_ctx):
        """Реальный запуск удаляет данные группы из всех целевых таблиц."""
        from src.group_knowledge.database import delete_group_data

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {"cnt": 4},
            {"cnt": 6},
            {"cnt": 2},
            {"cnt": 1},
        ]
        mock_cursor.rowcount = 0

        executed_queries = []
        delete_rowcounts = iter([1, 2, 6, 4])

        def _execute_side_effect(query, _params=None):
            normalized = " ".join(query.split())
            executed_queries.append(normalized)
            if normalized.startswith("DELETE"):
                mock_cursor.rowcount = next(delete_rowcounts)

        mock_cursor.execute.side_effect = _execute_side_effect

        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            stats = delete_group_data(-1001234, dry_run=False)

        self.assertEqual(stats["image_queue_deleted"], 1)
        self.assertEqual(stats["responder_logs_deleted"], 2)
        self.assertEqual(stats["qa_pairs_deleted"], 6)
        self.assertEqual(stats["messages_deleted"], 4)
        self.assertEqual(stats["dry_run"], 0)
        self.assertTrue(any("DELETE iq" in query for query in executed_queries))
        self.assertTrue(any("DELETE FROM gk_responder_log" in query for query in executed_queries))
        self.assertTrue(any("DELETE FROM gk_qa_pairs" in query for query in executed_queries))
        self.assertTrue(any("DELETE FROM gk_messages" in query for query in executed_queries))


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

class TestMessageCollectorQuestionClassification(unittest.TestCase):
    """Тесты классификации вопросов на этапе сбора сообщений."""

    def test_classify_message_question_marks_message_with_question_mark(self):
        """Сообщение с '?' помечается как вопрос без вызова LLM."""
        from src.group_knowledge.message_collector import MessageCollector
        from src.group_knowledge.models import GroupMessage

        collector = MessageCollector(client=MagicMock(), groups=[])
        msg = GroupMessage(message_text="Почему терминал не печатает?")

        with patch.object(collector._question_classifier, "classify", new=AsyncMock()) as mock_classify:
            _run_async(collector._classify_message_question(msg))

        self.assertTrue(msg.is_question)
        self.assertEqual(msg.question_model_used, "rule:question_mark")
        mock_classify.assert_not_called()

    def test_classify_message_without_question_mark_uses_llm(self):
        """Сообщение без '?' классифицируется через общий сервис."""
        from src.group_knowledge.message_collector import MessageCollector
        from src.group_knowledge.models import GroupMessage
        from src.group_knowledge.question_classifier import QuestionClassificationResult

        collector = MessageCollector(client=MagicMock(), groups=[])
        msg = GroupMessage(
            group_id=-1001234,
            telegram_message_id=555,
            message_text="терминал не видит сеть после обновления",
        )

        with patch.object(
            collector._question_classifier,
            "classify",
            new=AsyncMock(return_value=QuestionClassificationResult(
                is_question=True,
                confidence=0.91,
                reason="Похоже на описание технической проблемы",
                model_used="deepseek-test",
                detected_at=123456,
            )),
        ):
            _run_async(collector._classify_message_question(msg))

        self.assertTrue(msg.is_question)
        self.assertAlmostEqual(msg.question_confidence, 0.91, places=2)
        self.assertEqual(msg.question_model_used, "deepseek-test")


class TestMessageCollectorLogging(unittest.TestCase):
    """Тесты логирования collector."""

    def test_handle_new_message_logs_message_timestamp(self):
        """При live-сборе в лог пишется timestamp исходного сообщения."""
        from src.group_knowledge.message_collector import MessageCollector

        fixed_ts = int(time.time())
        message = types.SimpleNamespace(
            id=7001,
            text="Тестовое сообщение",
            message="Тестовое сообщение",
            media=None,
            action=None,
            reply_to=None,
            date=datetime.fromtimestamp(fixed_ts),
        )
        event = types.SimpleNamespace(
            message=message,
            chat=types.SimpleNamespace(id=-1001234),
            get_sender=AsyncMock(return_value=types.SimpleNamespace(id=123, bot=False, first_name="Иван", last_name="")),
        )

        collector = MessageCollector(client=MagicMock(), groups=[{"id": -1001234, "title": "Test Group"}])

        with patch("src.group_knowledge.message_collector.gk_db.store_message", return_value=55), \
             patch.object(collector, "_classify_message_question", new=AsyncMock()), \
             patch.object(collector, "_message_has_image", return_value=False), \
             patch("src.group_knowledge.message_collector.logger.info") as mock_logger_info, \
             patch("src.group_knowledge.message_collector.time.time", return_value=fixed_ts):
            result = _run_async(collector.handle_new_message(event))

        self.assertIsNotNone(result)
        self.assertTrue(any(
            call.args
            and call.args[0] == "Сообщение сохранено: group=%d msg_tg=%d db_id=%d sender=%s has_image=%s message_ts=%s"
            and call.args[1] == -1001234
            and call.args[2] == 7001
            and call.args[3] == 55
            and call.args[6] == datetime.fromtimestamp(fixed_ts).strftime("%Y-%m-%d %H:%M:%S")
            for call in mock_logger_info.call_args_list
        ))


class TestCollectorResponderBridge(unittest.TestCase):
    """Тесты склейки сообщений пользователя перед автоответом."""

    def test_build_combined_question_merges_text_and_image_marker(self):
        """Склейка собирает текст и маркер изображения в один вопрос."""
        from src.group_knowledge.collector_responder import CollectorResponderBridge
        from src.group_knowledge.models import GroupMessage

        messages = [
            GroupMessage(
                telegram_message_id=1,
                group_id=-1001,
                sender_id=10,
                message_text="терминал не печатает",
                message_date=100,
            ),
            GroupMessage(
                telegram_message_id=2,
                group_id=-1001,
                sender_id=10,
                has_image=True,
                message_date=101,
            ),
        ]

        combined = CollectorResponderBridge._build_combined_question(messages)

        self.assertIn("терминал не печатает", combined)
        self.assertIn("[Пользователь приложил изображение без подписи]", combined)

    def test_flush_after_delay_sends_one_combined_question(self):
        """Несколько сообщений одного пользователя уходят в responder как один вопрос."""
        from src.group_knowledge.collector_responder import CollectorResponderBridge, PendingQuestionBundle
        from src.group_knowledge.models import GroupMessage, ResponderResult

        responder = MagicMock()
        responder.handle_message = AsyncMock(return_value=ResponderResult(dry_run=True))
        bridge = CollectorResponderBridge(
            responder=responder,
            group_ids={-1001},
            grouping_window_seconds=1,
        )

        event = MagicMock()
        bridge._pending[(-1001, 10)] = PendingQuestionBundle(
            root_event=event,
            latest_event=event,
            messages=[
                GroupMessage(
                    telegram_message_id=1,
                    group_id=-1001,
                    sender_id=10,
                    message_text="терминал не печатает",
                    message_date=100,
                    is_question=True,
                ),
                GroupMessage(
                    telegram_message_id=2,
                    group_id=-1001,
                    sender_id=10,
                    has_image=True,
                    message_date=101,
                ),
            ],
        )

        with patch("src.group_knowledge.collector_responder.asyncio.sleep", new=AsyncMock()), \
            patch("src.group_knowledge.collector_responder.gk_db.get_message_by_telegram_id", return_value=None), \
            patch("src.group_knowledge.collector_responder.logger.info") as mock_log_info:
            _run_async(bridge._flush_after_delay((-1001, 10)))

        responder.handle_message.assert_awaited_once()
        self.assertIn("терминал не печатает", responder.handle_message.await_args.kwargs["question_override"])
        self.assertTrue(responder.handle_message.await_args.kwargs["force_as_question"])
        self.assertTrue(any(
            call.args
            and call.args[0] == "Bridge запускает автоответчик: group=%d sender=%d messages=%d text=%s"
            and call.args[1] == -1001
            and call.args[2] == 10
            for call in mock_log_info.call_args_list
        ))

    def test_flush_after_delay_uses_image_description_from_db_refresh(self):
        """Bridge перед flush подтягивает image_description из БД и включает его в question_override."""
        from src.group_knowledge.collector_responder import CollectorResponderBridge, PendingQuestionBundle
        from src.group_knowledge.models import GroupMessage, ResponderResult

        responder = MagicMock()
        responder.handle_message = AsyncMock(return_value=ResponderResult(dry_run=True))
        bridge = CollectorResponderBridge(responder=responder, group_ids={-1001}, grouping_window_seconds=1)

        event = MagicMock()
        original_text_message = GroupMessage(
            telegram_message_id=10,
            group_id=-1001,
            sender_id=77,
            message_text="не проходит оплата",
            message_date=100,
            is_question=True,
        )
        original_image_message = GroupMessage(
            telegram_message_id=11,
            group_id=-1001,
            sender_id=77,
            has_image=True,
            message_date=101,
        )

        bridge._pending[(-1001, 77)] = PendingQuestionBundle(
            root_event=event,
            latest_event=event,
            messages=[original_text_message, original_image_message],
        )

        enriched_image_message = GroupMessage(
            telegram_message_id=11,
            group_id=-1001,
            sender_id=77,
            has_image=True,
            image_description="На экране ошибка: Отказ в авторизации терминала",
            message_date=101,
        )

        def _db_message_side_effect(group_id, telegram_message_id):
            if group_id == -1001 and telegram_message_id == 11:
                return enriched_image_message
            return None

        with patch("src.group_knowledge.collector_responder.asyncio.sleep", new=AsyncMock()), \
             patch(
                 "src.group_knowledge.collector_responder.gk_db.get_message_by_telegram_id",
                 side_effect=_db_message_side_effect,
             ), \
             patch("src.group_knowledge.collector_responder.logger.info"):
            _run_async(bridge._flush_after_delay((-1001, 77)))

        responder.handle_message.assert_awaited_once()
        question_override = responder.handle_message.await_args.kwargs["question_override"]
        self.assertIn("не проходит оплата", question_override)
        self.assertIn("[Изображение: На экране ошибка: Отказ в авторизации терминала]", question_override)

    def test_queue_message_logs_skip_for_ignored_sender(self):
        """Bridge пишет явный лог при пропуске sender из ignored списка."""
        from src.group_knowledge.collector_responder import CollectorResponderBridge
        from src.group_knowledge.models import GroupMessage

        responder = MagicMock()
        bridge = CollectorResponderBridge(responder=responder, group_ids={-1001}, grouping_window_seconds=1)
        event = MagicMock()
        message = GroupMessage(
            telegram_message_id=55,
            group_id=-1001,
            sender_id=12345,
            message_text="Тест",
            message_date=100,
        )

        with patch("src.group_knowledge.collector_responder.GK_IGNORED_SENDER_IDS", new=(12345,)), \
             patch("src.group_knowledge.collector_responder.logger.info") as mock_log_info:
            _run_async(bridge.queue_message(event, message))

        self.assertTrue(any(
            call.args
            and call.args[0] == "Буфер автоответчика: пропуск — sender в GK_IGNORED_SENDER_IDS sender=%d ignored=%s"
            and call.args[1] == 12345
            for call in mock_log_info.call_args_list
        ))

    def test_queue_message_does_not_skip_ignored_sender_for_test_group(self):
        """В test-mode bridge не отбрасывает sender из ignored списка."""
        from src.group_knowledge.collector_responder import CollectorResponderBridge
        from src.group_knowledge.models import GroupMessage

        responder = MagicMock()
        bridge = CollectorResponderBridge(
            responder=responder,
            group_ids={-1001},
            grouping_window_seconds=1,
            test_group_ids={-1001},
        )
        event = MagicMock()
        message = GroupMessage(
            telegram_message_id=56,
            group_id=-1001,
            sender_id=12345,
            message_text="Тест",
            message_date=100,
        )

        fake_task = MagicMock()
        with patch("src.group_knowledge.collector_responder.GK_IGNORED_SENDER_IDS", new=(12345,)), \
             patch("src.group_knowledge.collector_responder.asyncio.create_task", return_value=fake_task), \
             patch("src.group_knowledge.collector_responder.logger.info") as mock_log_info:
            _run_async(bridge.queue_message(event, message))

        self.assertEqual(bridge.stats["scheduled"], 1)
        self.assertTrue(any(
            call.args
            and call.args[0] == "Буфер автоответчика: sender=%d в ignored, но группа %d помечена как test-mode — пропуск отключён"
            and call.args[1] == 12345
            and call.args[2] == -1001
            for call in mock_log_info.call_args_list
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
        """Обычный backfill пропускает уже собранные сообщения без повторной LLM-классификации."""
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
             patch.object(collector, "_classify_message_question", new=AsyncMock()) as mock_classify, \
             patch.object(collector, "_message_has_image", return_value=True):
            result = _run_async(collector.backfill_messages(days=1, force=False))

        self.assertEqual(result, 0)
        mock_store.assert_not_called()
        mock_enqueue.assert_not_called()
        mock_classify.assert_not_called()
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

    def test_backfill_stops_quickly_after_stop_request(self):
        """Backfill прерывается сразу после запроса на остановку."""
        from src.group_knowledge.message_collector import MessageCollector
        from src.group_knowledge.models import GroupMessage

        client = MagicMock()
        client.get_entity = AsyncMock(return_value=object())
        messages = [
            self._make_message(5101),
            self._make_message(5102),
            self._make_message(5103),
        ]
        client.iter_messages = MagicMock(return_value=self._iter_messages(messages))

        collector = MessageCollector(
            client=client,
            image_processor=MagicMock(),
            groups=[{"id": -1001234, "title": "Test Group"}],
        )
        existing = GroupMessage(
            id=90,
            telegram_message_id=5101,
            group_id=-1001234,
        )
        lookup_calls = 0

        def lookup_message(_group_id, _message_id):
            nonlocal lookup_calls
            lookup_calls += 1
            collector.stop()
            return existing

        with patch("src.group_knowledge.message_collector.gk_db.get_message_by_telegram_id", side_effect=lookup_message):
            result = _run_async(collector.backfill_messages(days=1, force=False))

        self.assertEqual(result, 0)
        self.assertEqual(lookup_calls, 1)

    def test_backfill_logs_progress_even_when_messages_are_skipped(self):
        """Backfill пишет прогресс по просмотренным сообщениям, даже если все они пропущены."""
        from src.group_knowledge.message_collector import MessageCollector
        from src.group_knowledge.models import GroupMessage

        client = MagicMock()
        client.get_entity = AsyncMock(return_value=object())
        messages = [self._make_message(5200 + index) for index in range(100)]
        client.iter_messages = MagicMock(return_value=self._iter_messages(messages))

        collector = MessageCollector(
            client=client,
            image_processor=MagicMock(),
            groups=[{"id": -1001234, "title": "Test Group"}],
        )
        existing = GroupMessage(
            id=91,
            telegram_message_id=5200,
            group_id=-1001234,
        )

        with patch("src.group_knowledge.message_collector.gk_db.get_message_by_telegram_id", return_value=existing), \
             patch("src.group_knowledge.message_collector.logger.info") as mock_log_info:
            result = _run_async(collector.backfill_messages(days=1, force=False))

        self.assertEqual(result, 0)
        self.assertTrue(any(
            call.args
            and call.args[0] == (
                "Backfill %s: группа %d (%s) — просмотрено=%d сохранено=%d пропущено=%d "
                "(existing=%d service=%d bots=%d)"
            )
            and call.args[1] == "progress"
            and call.args[2] == -1001234
            and call.args[3] == "Test Group"
            and call.args[4] == 100
            and call.args[5] == 0
            and call.args[6] == 100
            and call.args[7] == 100
            and call.args[8] == 0
            and call.args[9] == 0
            for call in mock_log_info.call_args_list
        ))

    def test_sync_missed_messages_uses_last_saved_telegram_id(self):
        """Добор пропущенных сообщений стартует от последнего сохранённого Telegram ID."""
        from src.group_knowledge.message_collector import MessageCollector

        client = MagicMock()
        client.get_entity = AsyncMock(return_value=object())
        message1 = self._make_message(5002, text="Пропущенное сообщение 1")
        message2 = self._make_message(5003, text="Пропущенное сообщение 2")
        client.iter_messages = MagicMock(return_value=self._iter_messages([message1, message2]))

        collector = MessageCollector(
            client=client,
            image_processor=MagicMock(),
            groups=[{"id": -1001234, "title": "Test Group"}],
        )

        with patch("src.group_knowledge.message_collector.gk_db.get_latest_telegram_message_id", return_value=5001), \
             patch("src.group_knowledge.message_collector.gk_db.get_message_by_telegram_id", return_value=None), \
             patch("src.group_knowledge.message_collector.gk_db.store_message", side_effect=[101, 102]) as mock_store, \
             patch.object(collector, "_message_has_image", return_value=False), \
             patch.object(collector, "_classify_message_question", new=AsyncMock()):
            result = _run_async(collector.sync_missed_messages())

        self.assertEqual(result, 2)
        client.iter_messages.assert_called_once_with(
            unittest.mock.ANY,
            min_id=5001,
            reverse=True,
        )
        self.assertEqual(mock_store.call_count, 2)

    def test_sync_missed_messages_skips_group_without_checkpoint(self):
        """Если для группы нет локальной контрольной точки, добор не запускается."""
        from src.group_knowledge.message_collector import MessageCollector

        client = MagicMock()
        collector = MessageCollector(
            client=client,
            image_processor=MagicMock(),
            groups=[{"id": -1001234, "title": "Test Group"}],
        )

        with patch("src.group_knowledge.message_collector.gk_db.get_latest_telegram_message_id", return_value=None):
            result = _run_async(collector.sync_missed_messages())

        self.assertEqual(result, 0)
        client.get_entity.assert_not_called()

    def test_handle_new_message_skips_existing_message_without_llm(self):
        """Live-сбор пропускает уже сохранённое сообщение без повторной LLM-классификации."""
        from src.group_knowledge.message_collector import MessageCollector
        from src.group_knowledge.models import GroupMessage

        fixed_ts = int(time.time())
        message = types.SimpleNamespace(
            id=7002,
            text="Тестовое сообщение",
            message="Тестовое сообщение",
            media=None,
            action=None,
            reply_to=None,
            date=datetime.fromtimestamp(fixed_ts),
        )
        event = types.SimpleNamespace(
            message=message,
            chat=types.SimpleNamespace(id=-1001234),
            get_sender=AsyncMock(return_value=types.SimpleNamespace(id=123, bot=False, first_name="Иван", last_name="")),
        )

        collector = MessageCollector(client=MagicMock(), groups=[{"id": -1001234, "title": "Test Group"}])
        existing = GroupMessage(id=55, telegram_message_id=7002, group_id=-1001234)

        with patch("src.group_knowledge.message_collector.gk_db.get_message_by_telegram_id", return_value=existing), \
             patch("src.group_knowledge.message_collector.gk_db.store_message") as mock_store, \
             patch.object(collector, "_classify_message_question", new=AsyncMock()) as mock_classify:
            result = _run_async(collector.handle_new_message(event))

        self.assertIsNone(result)
        mock_store.assert_not_called()
        mock_classify.assert_not_called()
        event.get_sender.assert_not_called()


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

    def test_validate_thread_chain_rejects_empty_clean_fields(self):
        """Пустые clean_question/clean_answer не проходят валидацию."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "is_valid_qa": True,
            "confidence": 0.9,
            "clean_question": "   ",
            "clean_answer": "",
            "answer_message_id": None,
        }))

        analyzer = QAAnalyzer()
        messages = [
            self._make_message(1, 101, 1, "Что-то сломалось?"),
            self._make_message(2, 102, 2, "Проверьте настройки.", reply_to=101, date_offset=1),
        ]

        with patch("src.group_knowledge.qa_analyzer.get_provider", return_value=mock_provider):
            result = _run_async(analyzer._validate_thread_chain(messages[0], messages))

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

    def test_collect_thread_messages_appends_nearby_same_participants(self):
        """В цепочку добавляются соседние сообщения тех же участников без reply-связи."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        root = self._make_message(1, 101, 1, "Не работает терминал")
        reply = self._make_message(2, 102, 2, "Какая ошибка?", reply_to=101, date_offset=1)
        unlinked_same_user = self._make_message(3, 103, 1, "Ошибка 1001 на экране", date_offset=2)
        unlinked_same_helper = self._make_message(4, 104, 2, "Перезапустите сервис", date_offset=3)
        unrelated = self._make_message(5, 105, 999, "У нас всё ок", date_offset=2)

        messages = [root, reply, unlinked_same_user, unlinked_same_helper, unrelated]
        children_index = analyzer._build_reply_children_index(messages)

        collected = analyzer._collect_thread_messages(
            root,
            children_index,
            all_messages=messages,
        )

        collected_ids = [msg.telegram_message_id for msg in collected]
        self.assertIn(103, collected_ids)
        self.assertIn(104, collected_ids)
        self.assertNotIn(105, collected_ids)

    def test_collect_thread_messages_logs_added_nearby_messages(self):
        """При добавлении соседних сообщений пишется явный лог о расширении цепочки."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        root = self._make_message(1, 101, 1, "Не работает терминал")
        reply = self._make_message(2, 102, 2, "Какая ошибка?", reply_to=101, date_offset=1)
        unlinked_same_user = self._make_message(3, 103, 1, "Ошибка 1001 на экране", date_offset=2)
        messages = [root, reply, unlinked_same_user]
        children_index = analyzer._build_reply_children_index(messages)

        with patch("src.group_knowledge.qa_analyzer.logger.info") as mock_log_info:
            analyzer._collect_thread_messages(
                root,
                children_index,
                all_messages=messages,
            )

        self.assertTrue(any(
            call.args and call.args[0] == "Найдены дополнительные последовательные сообщения: root_msg=%d added=%d total=%d"
            for call in mock_log_info.call_args_list
        ))

    def test_format_thread_context_includes_timestamp_and_sender(self):
        """Контекст для LLM содержит время сообщения и имя автора."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        messages = [
            self._make_message(1, 101, 1, "Не работает терминал"),
            self._make_message(2, 102, 2, "Какая ошибка?", reply_to=101, date_offset=1),
        ]

        context = analyzer._format_thread_context(messages)

        self.assertIn("User 1", context)
        self.assertIn("User 2", context)
        self.assertIn("1970-01-01 00:16:40 UTC", context)
        self.assertIn("1970-01-01 00:16:41 UTC", context)
        self.assertIn("reply_to:101", context)

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

    def test_extract_thread_pairs_adds_image_gist_to_stored_question(self):
        """При сохранении thread-пары gist из изображения добавляется в вопрос."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        messages = [
            self._make_message(1, 101, 1, "Что с ошибкой на экране?"),
            self._make_message(2, 102, 2, "Это ошибка сети, перезапустите модем.", reply_to=101, date_offset=1),
        ]
        messages[0].has_image = True
        messages[0].image_description = "На скриншоте видно сообщение 'Нет связи с хостом' и красный статус сети."

        with patch.object(
            analyzer,
            "_validate_thread_chain",
            new=AsyncMock(return_value=(
                "Как исправить ошибку связи на терминале?",
                "Проверьте сетевое подключение и перезапустите модем.",
                0.92,
                102,
            )),
        ):
            with patch("src.group_knowledge.qa_analyzer.gk_db.store_qa_pair", return_value=78):
                with patch("src.group_knowledge.qa_analyzer.asyncio.sleep", new=AsyncMock()):
                    pairs = _run_async(analyzer._extract_thread_pairs(messages))

        self.assertEqual(len(pairs), 1)
        self.assertIn("Как исправить ошибку связи на терминале?", pairs[0].question_text)
        self.assertIn("Суть по изображению", pairs[0].question_text)
        self.assertIn("Нет связи с хостом", pairs[0].question_text)

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

    def test_analyze_day_ignores_configured_bot_sender(self):
        """Анализатор исключает сообщения bot-user из анализа по sender_id."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer
        from src.group_knowledge.models import GroupMessage

        analyzer = QAAnalyzer()
        messages = [
            GroupMessage(id=1, telegram_message_id=101, group_id=-1001, sender_id=6627254238, message_text="служебный ответ", message_date=100),
            GroupMessage(id=2, telegram_message_id=102, group_id=-1001, sender_id=123, message_text="Как починить терминал?", message_date=101),
        ]

        with patch("src.group_knowledge.qa_analyzer.gk_db.get_unprocessed_messages", return_value=messages):
            with patch.object(analyzer, "_extract_thread_pairs", new=AsyncMock(return_value=[])) as mock_thread:
                with patch.object(analyzer, "_extract_llm_inferred_pairs", new=AsyncMock(return_value=[])) as mock_llm:
                    with patch("src.group_knowledge.qa_analyzer.gk_db.mark_messages_processed"):
                        result = _run_async(analyzer.analyze_day(-1001, "2026-03-06"))

        self.assertEqual(result.total_messages, 1)
        self.assertEqual(len(mock_thread.await_args.args[0]), 1)
        self.assertEqual(len(mock_llm.await_args.args[0]), 1)

    def test_extract_thread_pairs_merges_overlapping_chains(self):
        """При сильном overlap несколько цепочек объединяются в одну перед LLM."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        root_a = self._make_message(1, 101, 1, "Проблема А", date_offset=0)
        root_b = self._make_message(2, 201, 2, "Проблема Б", date_offset=1)
        shared_1 = self._make_message(3, 301, 3, "Общий контекст 1", date_offset=2)
        shared_2 = self._make_message(4, 302, 3, "Общий контекст 2", date_offset=3)
        shared_3 = self._make_message(5, 303, 2, "Общий контекст 3", date_offset=4)
        extra_for_a = self._make_message(6, 304, 2, "Дополнительное сообщение для А", date_offset=5)

        messages = [root_a, root_b, shared_1, shared_2, shared_3, extra_for_a]

        chain_a = [root_a, shared_1, shared_2, shared_3, extra_for_a]
        chain_b = [root_b, shared_1, shared_2, shared_3]

        with patch.object(analyzer, "_find_thread_roots", return_value=[root_a, root_b]):
            with patch.object(analyzer, "_collect_thread_messages", side_effect=[chain_a, chain_b]):
                with patch.object(
                    analyzer,
                    "_validate_thread_chain",
                    new=AsyncMock(return_value=(
                        "Как решить проблему А?",
                        "Сделайте шаги из shared_2.",
                        0.9,
                        302,
                    )),
                ) as mock_validate:
                    with patch("src.group_knowledge.qa_analyzer.gk_db.store_qa_pair", return_value=701):
                        with patch("src.group_knowledge.qa_analyzer.asyncio.sleep", new=AsyncMock()):
                            pairs = _run_async(analyzer._extract_thread_pairs(messages))

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].question_message_id, 1)
        self.assertEqual(pairs[0].answer_message_id, 4)
        mock_validate.assert_awaited_once()
        validate_root, validate_chain = mock_validate.await_args.args
        self.assertEqual(validate_root.telegram_message_id, 101)
        self.assertEqual(
            {msg.telegram_message_id for msg in validate_chain},
            {101, 201, 301, 302, 303, 304},
        )

    def test_merge_overlapping_candidates_tie_prefers_earlier_root(self):
        """При равной длине и сильном overlap root объединённой цепочки — более ранний."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        early_root = self._make_message(1, 101, 1, "Ранний root", date_offset=0)
        late_root = self._make_message(2, 202, 2, "Поздний root", date_offset=10)

        candidates = [
            {
                "root": late_root,
                "thread_messages": [late_root, self._make_message(3, 301, 3, "x"), self._make_message(4, 302, 3, "y"), self._make_message(5, 303, 2, "z")],
                "message_ids": {202, 301, 302, 303},
            },
            {
                "root": early_root,
                "thread_messages": [early_root, self._make_message(6, 301, 3, "x"), self._make_message(7, 302, 3, "y"), self._make_message(8, 303, 2, "z")],
                "message_ids": {101, 301, 302, 303},
            },
        ]

        selected = analyzer._merge_overlapping_candidates(candidates)

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["root"].telegram_message_id, 101)
        self.assertEqual(selected[0]["message_ids"], {101, 202, 301, 302, 303})

    def test_analyze_batch_for_pairs_includes_question_hint_from_db(self):
        """LLM-inference получает QUESTION_HINT из сохранённой классификации сообщения."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        batch = [
            self._make_message(1, 101, 1, "терминал не видит сеть", date_offset=0),
            self._make_message(2, 102, 2, "Проверьте сетевой кабель", date_offset=1),
        ]
        batch[0].is_question = True
        batch[0].question_confidence = 0.88

        captured_prompt = {}
        mock_provider = MagicMock()

        async def _chat(**kwargs):
            captured_prompt["prompt"] = kwargs["messages"][0]["content"]
            return json.dumps({"pairs": []})

        mock_provider.chat = _chat

        with patch("src.group_knowledge.qa_analyzer.get_provider", return_value=mock_provider):
            pairs = _run_async(analyzer._analyze_batch_for_pairs(batch, -1001234, batch))

        self.assertEqual(pairs, [])
        self.assertIn("[QUESTION_HINT conf=0.88]", captured_prompt["prompt"])


class TestQAAnalyzerIndexing(unittest.TestCase):
    """Тесты индексации Q&A пар в Group Knowledge."""

    def test_index_new_pairs_uses_current_vector_api(self):
        """Индексация использует актуальный интерфейс vector_search."""
        from src.group_knowledge.models import QAPair
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        pair = QAPair(
            id=42,
            question_text="Почему не печатает терминал?",
            answer_text="Проверьте бумагу и перезапустите сервис печати.",
            group_id=-100123,
            extraction_type="thread_reply",
            confidence=0.91,
        )

        mock_embedding_provider = MagicMock()
        mock_embedding_provider.encode.return_value = [0.1, 0.2, 0.3]

        mock_vector_index = MagicMock()
        mock_vector_index.upsert_chunks.return_value = 1

        analyzer = QAAnalyzer()

        with patch("src.group_knowledge.qa_analyzer.gk_db.get_unindexed_qa_pairs", return_value=[pair]):
            with patch("src.group_knowledge.qa_analyzer.gk_db.mark_qa_pair_indexed") as mock_mark:
                with patch(
                    "src.core.ai.vector_search.LocalEmbeddingProvider",
                    return_value=mock_embedding_provider,
                ):
                    with patch(
                        "src.core.ai.vector_search.LocalVectorIndex",
                        return_value=mock_vector_index,
                    ) as mock_index_cls:
                        indexed = _run_async(analyzer.index_new_pairs())

        self.assertEqual(indexed, 1)
        mock_index_cls.assert_called_once_with(chunk_collection_name="gk_qa_pairs_v1")
        mock_embedding_provider.encode.assert_called_once()
        mock_vector_index.upsert_chunks.assert_called_once_with(
            chunks=[{
                "document_id": 42,
                "chunk_index": 0,
                "filename": "gk_qa_pair_42",
                "chunk_text": "Вопрос: Почему не печатает терминал?\nОтвет: Проверьте бумагу и перезапустите сервис печати.",
                "status": "active",
            }],
            embeddings=[[0.1, 0.2, 0.3]],
        )
        mock_mark.assert_called_once_with(42)

    def test_llm_inferred_pair_adds_image_gist_to_question(self):
        """LLM-inferred пара сохраняет gist изображения внутри вопроса."""
        from src.group_knowledge.models import GroupMessage
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        question_msg = GroupMessage(
            id=1,
            telegram_message_id=201,
            group_id=-1001234,
            sender_id=1,
            sender_name="User 1",
            message_text="Что означает эта ошибка?",
            message_date=1000,
        )
        question_msg.has_image = True
        question_msg.image_description = "На скриншоте код 445 и текст 'Касса не отвечает'."
        answer_msg = GroupMessage(
            id=2,
            telegram_message_id=202,
            group_id=-1001234,
            sender_id=2,
            sender_name="User 2",
            message_text="Перезапустите кассовый сервис.",
            message_date=1001,
        )

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "pairs": [
                {
                    "question_msg_id": 201,
                    "answer_msg_id": 202,
                    "question": "Что означает ошибка 445?",
                    "answer": "Перезапустите кассовый сервис.",
                    "confidence": 0.84,
                }
            ]
        }))

        stored_pairs = []

        def _store_pair(pair):
            stored_pairs.append(pair)
            return 901

        with patch("src.group_knowledge.qa_analyzer.get_provider", return_value=mock_provider):
            with patch("src.group_knowledge.qa_analyzer.gk_db.store_qa_pair", side_effect=_store_pair):
                pairs = _run_async(
                    analyzer._analyze_batch_for_pairs([question_msg, answer_msg], -1001234, [question_msg, answer_msg])
                )

        self.assertEqual(len(pairs), 1)
        self.assertEqual(len(stored_pairs), 1)
        self.assertIn("Что означает ошибка 445?", stored_pairs[0].question_text)
        self.assertIn("Суть по изображению", stored_pairs[0].question_text)
        self.assertIn("Касса не отвечает", stored_pairs[0].question_text)

    def test_llm_inferred_skips_empty_pairs_from_model(self):
        """LLM-inferred не сохраняет пары с пустыми question/answer."""
        from src.group_knowledge.models import GroupMessage
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        analyzer = QAAnalyzer()
        question_msg = GroupMessage(
            id=1,
            telegram_message_id=201,
            group_id=-1001234,
            sender_id=1,
            sender_name="User 1",
            message_text="Что означает эта ошибка?",
            message_date=1000,
        )
        answer_msg = GroupMessage(
            id=2,
            telegram_message_id=202,
            group_id=-1001234,
            sender_id=2,
            sender_name="User 2",
            message_text="Перезапустите сервис.",
            message_date=1001,
        )

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value=json.dumps({
            "pairs": [
                {
                    "question_msg_id": 201,
                    "answer_msg_id": 202,
                    "question": "   ",
                    "answer": "",
                    "confidence": 0.8,
                }
            ]
        }))

        with patch("src.group_knowledge.qa_analyzer.get_provider", return_value=mock_provider):
            with patch("src.group_knowledge.qa_analyzer.gk_db.store_qa_pair") as mock_store:
                pairs = _run_async(
                    analyzer._analyze_batch_for_pairs([question_msg, answer_msg], -1001234, [question_msg, answer_msg])
                )

        self.assertEqual(pairs, [])
        mock_store.assert_not_called()


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

    def test_vector_search_uses_pair_ids_from_vector_candidates(self):
        """Векторный поиск поднимает полные пары из БД по document_id кандидата."""
        from src.group_knowledge.models import QAPair
        from src.group_knowledge.qa_search import QASearchService

        pair = QAPair(
            id=17,
            question_text="Как включить NFC?",
            answer_text="Откройте настройки терминала и активируйте NFC.",
            group_id=-100555,
            extraction_type="thread_reply",
            confidence=0.93,
        )

        vector_hit = types.SimpleNamespace(document_id=17, score=0.87)
        mock_embedding_provider = MagicMock()
        mock_embedding_provider.encode.return_value = [0.4, 0.5, 0.6]
        mock_vector_index = MagicMock()
        mock_vector_index.search.return_value = [vector_hit]

        service = QASearchService()

        with patch(
            "src.core.ai.vector_search.LocalEmbeddingProvider",
            return_value=mock_embedding_provider,
        ):
            with patch(
                "src.core.ai.vector_search.LocalVectorIndex",
                return_value=mock_vector_index,
            ) as mock_index_cls:
                with patch("src.group_knowledge.qa_search.gk_db.get_qa_pair_by_id", return_value=pair):
                    results = _run_async(service._vector_search("Как включить NFC?", 3))

        self.assertEqual(results, [(pair, 0.87)])
        mock_index_cls.assert_called_once_with(chunk_collection_name="gk_qa_pairs_v1")
        mock_embedding_provider.encode.assert_called_once_with("Как включить NFC?")
        mock_vector_index.search.assert_called_once_with(
            query_vector=[0.4, 0.5, 0.6],
            limit=3,
        )


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
        event.reply = AsyncMock()
        event.client = MagicMock()
        event.client.send_message = AsyncMock()

        return event

    def test_skip_non_question(self):
        """Пропуск не-вопросных сообщений."""
        from src.group_knowledge.responder import GroupResponder

        responder = GroupResponder(dry_run=True)
        event = self._make_event("Спасибо всем за помощь, всё починил", -1001234)

        with patch.object(responder, "_classify_message_as_question", new=AsyncMock(return_value=False)):
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

    def test_message_without_question_mark_is_checked_by_llm(self):
        """Сообщение без '?' отправляется в LLM-классификатор вопроса."""
        from src.group_knowledge.responder import GroupResponder

        mock_qa = MagicMock()
        mock_qa.answer_question = AsyncMock(return_value={
            "answer": "Проверьте питание и сетевой кабель.",
            "confidence": 0.95,
            "source_pair_ids": [5],
            "is_relevant": True,
        })

        responder = GroupResponder(dry_run=True, qa_service=mock_qa)
        event = self._make_event("терминал не включается после перезагрузки", -1001234)

        with patch.object(responder, "_classify_message_as_question", new=AsyncMock(return_value=True)) as mock_classify:
            with patch("src.group_knowledge.responder.gk_db"):
                result = _run_async(responder.handle_message(event, {-1001001234}))

        self.assertIsNotNone(result)
        mock_classify.assert_awaited_once_with("терминал не включается после перезагрузки")

    def test_question_mark_skips_llm_question_classifier(self):
        """Сообщение с '?' не отправляется в LLM-классификатор вопроса."""
        from src.group_knowledge.responder import GroupResponder

        mock_qa = MagicMock()
        mock_qa.answer_question = AsyncMock(return_value={
            "answer": "Перезапустите сервис.",
            "confidence": 0.9,
            "source_pair_ids": [7],
            "is_relevant": True,
        })

        responder = GroupResponder(dry_run=True, qa_service=mock_qa)
        event = self._make_event("Почему терминал не печатает?", -1001234)

        with patch.object(responder, "_classify_message_as_question", new=AsyncMock()) as mock_classify:
            with patch("src.group_knowledge.responder.gk_db"):
                result = _run_async(responder.handle_message(event, {-1001001234}))

        self.assertIsNotNone(result)
        mock_classify.assert_not_called()

    def test_test_group_mapping_uses_real_group_for_logs(self):
        """В test mode логирование и лимиты используют real group, а ответ уходит в test group."""
        from src.group_knowledge.responder import GroupResponder

        mock_qa = MagicMock()
        mock_qa.answer_question = AsyncMock(return_value={
            "answer": "Проверьте настройки сети.",
            "confidence": 0.92,
            "source_pair_ids": [12],
            "is_relevant": True,
        })

        responder = GroupResponder(
            dry_run=True,
            qa_service=mock_qa,
            test_group_mapping={-1001001234: -1002005678},
        )
        event = self._make_event("терминал не видит сеть", -1001234)

        with patch.object(responder, "_classify_message_as_question", new=AsyncMock(return_value=True)):
            with patch("src.group_knowledge.responder.gk_db.store_responder_log") as mock_store_log:
                result = _run_async(responder.handle_message(event, {-1001001234}))

        self.assertIsNotNone(result)
        mock_store_log.assert_called_once()
        self.assertEqual(mock_store_log.call_args.kwargs["group_id"], -1002005678)

    def test_test_mode_does_not_skip_ignored_sender(self):
        """В test-mode sender из ignored списка не блокируется."""
        from src.group_knowledge.responder import GroupResponder

        mock_qa = MagicMock()
        mock_qa.answer_question = AsyncMock(return_value={
            "answer": "Проверьте настройки сети.",
            "confidence": 0.92,
            "source_pair_ids": [12],
            "is_relevant": True,
        })

        responder = GroupResponder(
            dry_run=True,
            qa_service=mock_qa,
            test_group_mapping={-1001001234: -1002005678},
        )
        event = self._make_event("терминал не видит сеть", -1001234, sender_id=777)

        with patch("src.group_knowledge.responder.GK_IGNORED_SENDER_IDS", new=(777,)):
            with patch.object(responder, "_classify_message_as_question", new=AsyncMock(return_value=True)):
                with patch("src.group_knowledge.responder.gk_db.store_responder_log") as mock_store_log:
                    result = _run_async(responder.handle_message(event, {-1001001234}))

        self.assertIsNotNone(result)
        mock_qa.answer_question.assert_awaited_once()
        mock_store_log.assert_called_once()

    def test_handle_message_with_question_override(self):
        """question_override позволяет обработать /qa-команду как обычный вопрос."""
        from src.group_knowledge.responder import GroupResponder

        mock_qa = MagicMock()
        mock_qa.answer_question = AsyncMock(return_value={
            "answer": "Проверьте сетевой кабель и перезапустите терминал.",
            "confidence": 0.91,
            "source_pair_ids": [10],
            "is_relevant": True,
        })

        responder = GroupResponder(dry_run=True, qa_service=mock_qa)
        event = self._make_event("/qa как устранить ошибку сети", -1001234)

        with patch("src.group_knowledge.responder.gk_db"):
            result = _run_async(
                responder.handle_message(
                    event,
                    {-1001001234},
                    question_override="как устранить ошибку сети",
                )
            )

        self.assertIsNotNone(result)
        mock_qa.answer_question.assert_awaited_once_with("как устранить ошибку сети")

    def test_redirect_test_mode_sends_to_external_group(self):
        """Redirect test mode отправляет ответ в отдельную тестовую группу с метаданными источника."""
        from src.group_knowledge.responder import GroupResponder

        mock_qa = MagicMock()
        mock_qa.answer_question = AsyncMock(return_value={
            "answer": "Проверьте сетевой кабель и перезапустите сервис.",
            "confidence": 0.91,
            "source_pair_ids": [42],
            "is_relevant": True,
        })

        responder = GroupResponder(
            dry_run=False,
            qa_service=mock_qa,
            redirect_output_group={"id": -1003004005, "title": "GK Test Output"},
        )
        event = self._make_event("Почему терминал не видит сеть?", -1001234, sender_id=555)
        event.chat.title = "Боевая группа"
        awaitable_sender = MagicMock()
        awaitable_sender.id = 555
        awaitable_sender.bot = False
        awaitable_sender.first_name = "Иван"
        awaitable_sender.last_name = "Петров"
        awaitable_sender.username = "ivanpetrov"
        event.get_sender = AsyncMock(return_value=awaitable_sender)

        with patch("src.group_knowledge.responder.gk_db.store_responder_log"):
            result = _run_async(responder.handle_message(event, {-1001001234}))

        self.assertIsNotNone(result)
        self.assertTrue(result.responded)
        event.reply.assert_not_awaited()
        event.client.send_message.assert_awaited_once()
        send_args = event.client.send_message.await_args.args
        self.assertEqual(send_args[0], -1003004005)
        self.assertIn("Источник: Боевая группа (-1001001234)", send_args[1])
        self.assertIn("Отправитель: Иван Петров (@ivanpetrov, id=555)", send_args[1])
        self.assertIn("Вопрос:", send_args[1])
        self.assertIn("Ответ:", send_args[1])

    def test_logs_rag_start_and_no_answer(self):
        """При отсутствии ответа в логах видно запуск RAG и отрицательный результат."""
        from src.group_knowledge.responder import GroupResponder

        mock_qa = MagicMock()
        mock_qa.answer_question = AsyncMock(return_value=None)

        responder = GroupResponder(dry_run=True, qa_service=mock_qa)
        event = self._make_event("Как исправить ошибку 1001?", -1001234)

        with patch("src.group_knowledge.responder.logger.info") as mock_log_info:
            result = _run_async(
                responder.handle_message(
                    event,
                    {-1001001234},
                    question_override="Как исправить ошибку 1001?",
                    force_as_question=True,
                )
            )

        self.assertIsNone(result)
        self.assertTrue(any(
            call.args
            and call.args[0] == "Запуск RAG-поиска: group=%d actual_group=%d msg=%d dry_run=%s text=%s"
            for call in mock_log_info.call_args_list
        ))
        self.assertTrue(any(
            call.args
            and call.args[0] == "RAG не нашёл ответ: group=%d actual_group=%d msg=%d text=%s"
            for call in mock_log_info.call_args_list
        ))


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

    def test_responder_extract_qa_query(self):
        """gk_responder извлекает вопрос только из команды /qa."""
        gk_responder = self._import_script_module("scripts.gk_responder")

        self.assertEqual(
            gk_responder._extract_qa_query("/qa как перезагрузить терминал?"),
            "как перезагрузить терминал?",
        )
        self.assertEqual(
            gk_responder._extract_qa_query("/qa@SbsArchieBot что делать с ошибкой 1001"),
            "что делать с ошибкой 1001",
        )
        self.assertIsNone(gk_responder._extract_qa_query("/qa"))
        self.assertIsNone(gk_responder._extract_qa_query("как починить?"))


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


# ===========================================================================
# QASearchService — Tokenize
# ===========================================================================

class TestGKTokenize(unittest.TestCase):
    """Тесты для QASearchService._tokenize."""

    def setUp(self):
        from src.group_knowledge.qa_search import QASearchService
        self.service = QASearchService()

    def test_basic_tokenization(self):
        """Базовая токенизация разбивает текст на слова."""
        tokens = self.service._tokenize("Как включить NFC на терминале?")
        self.assertIsInstance(tokens, list)
        self.assertGreater(len(tokens), 0)
        # 'как' должен быть отфильтрован как стоп-слово
        lower_tokens = [t.lower() for t in tokens]
        self.assertNotIn("как", lower_tokens)

    def test_empty_text(self):
        """Пустой текст возвращает пустой список."""
        self.assertEqual(self.service._tokenize(""), [])
        self.assertEqual(self.service._tokenize(None), [])

    def test_fixed_terms_preserved(self):
        """Защищённые термины (nfc, pos, ккт) сохраняются дословно."""
        tokens = self.service._tokenize("ККТ не работает NFC")
        lower_tokens = [t.lower() for t in tokens]
        self.assertIn("ккт", lower_tokens)
        self.assertIn("nfc", lower_tokens)

    def test_short_tokens_filtered(self):
        """Токены короче 3 символов фильтруются (кроме защищённых)."""
        tokens = self.service._tokenize("я и он тут")
        # 'я', 'и', 'он' — все < 3 символов и не в fixed_terms → отфильтрованы
        # 'тут' — 3 символа → должен остаться
        for t in tokens:
            self.assertTrue(
                len(t) >= 3 or t in {"я", "и", "он"},
                f"Неожиданный короткий токен: {t}",
            )

    def test_stopwords_removed(self):
        """Стоп-слова удаляются из результата, если остаются предметные токены."""
        tokens = self.service._tokenize("что такое терминал для чего настройка")
        lower_tokens = [t.lower() for t in tokens]
        # Стоп-слова должны быть отфильтрованы
        for sw in ["что", "для"]:
            self.assertNotIn(sw, lower_tokens)
        # Предметные слова должны остаться (возможно, нормализованы)
        self.assertGreater(len(tokens), 0)

    def test_all_stopwords_safety_guard(self):
        """Если все токены — стоп-слова, возвращается исходный список."""
        # 'что это как' — все стоп-слова
        tokens = self.service._tokenize("что это как")
        # safety guard: не должен вернуть пустой список
        self.assertGreater(len(tokens), 0)

    def test_tokenize_with_diagnostics_reports_removed_tokens(self):
        """Диагностика токенизации показывает удалённые короткие токены и стоп-слова."""
        diag = self.service._tokenize_with_diagnostics("ошибка при продаже почему? фн")

        self.assertIn("tokens", diag)
        self.assertIn("raw_tokens_total", diag)
        self.assertIn("removed_short_tokens", diag)
        self.assertIn("removed_stopwords", diag)
        self.assertIn("removed_stopwords_count", diag)

        self.assertGreaterEqual(diag["raw_tokens_total"], 5)
        self.assertGreaterEqual(diag["removed_stopwords_count"], 2)
        self.assertIn("при", diag["removed_stopwords"])
        self.assertIn("почему", diag["removed_stopwords"])


# ===========================================================================
# QASearchService — BM25 scoring
# ===========================================================================

class TestGKBM25Scoring(unittest.TestCase):
    """Тесты для QASearchService._score_corpus_bm25."""

    def test_basic_scoring(self):
        """BM25 даёт ненулевой score для релевантного документа."""
        from src.group_knowledge.qa_search import QASearchService

        corpus = [
            ["включить", "nfc", "терминал", "настройк"],
            ["замена", "бумага", "чековый", "лента"],
            ["nfc", "ошибка", "подключен", "модуль"],
        ]
        query = ["nfc", "включить"]
        scores = QASearchService._score_corpus_bm25(corpus, query)

        self.assertEqual(len(scores), 3)
        # Первый и третий документы содержат "nfc"
        self.assertGreater(scores[0], 0.0)
        self.assertGreater(scores[2], 0.0)
        # Первый документ релевантнее (содержит оба токена)
        self.assertGreater(scores[0], scores[2])
        # Второй документ нерелевантен
        self.assertAlmostEqual(scores[1], 0.0)

    def test_empty_corpus(self):
        """Пустой корпус возвращает пустой список."""
        from src.group_knowledge.qa_search import QASearchService

        scores = QASearchService._score_corpus_bm25([], ["test"])
        self.assertEqual(scores, [])

    def test_empty_query(self):
        """Пустой запрос возвращает нулевые score."""
        from src.group_knowledge.qa_search import QASearchService

        scores = QASearchService._score_corpus_bm25([["a", "b"]], [])
        self.assertEqual(scores, [0.0])


# ===========================================================================
# QASearchService — BM25 search (end-to-end with mocked DB)
# ===========================================================================

class TestGKBM25Search(unittest.TestCase):
    """Тесты для QASearchService._bm25_search с мок-корпусом."""

    def test_bm25_search_returns_ranked_pairs(self):
        """BM25-поиск возвращает пары, ранжированные по score."""
        from src.group_knowledge.qa_search import QASearchService
        from src.group_knowledge.models import QAPair

        service = QASearchService()

        pairs = [
            QAPair(id=1, question_text="Как включить NFC на терминале?",
                   answer_text="Откройте настройки и активируйте NFC.",
                   group_id=-100, approved=1),
            QAPair(id=2, question_text="Как заменить чековую ленту?",
                   answer_text="Откройте крышку и вставьте новый рулон.",
                   group_id=-100, approved=1),
            QAPair(id=3, question_text="NFC модуль не отвечает, ошибка подключения",
                   answer_text="Перезагрузите терминал и проверьте NFC-антенну.",
                   group_id=-100, approved=1),
        ]

        with patch("src.group_knowledge.qa_search.gk_db.get_all_approved_qa_pairs", return_value=pairs):
            results = service._bm25_search("Как включить NFC?", top_k=3)

        self.assertGreater(len(results), 0)
        # Все результаты — кортежи (QAPair, score)
        for pair, score in results:
            self.assertIsInstance(pair, QAPair)
            self.assertGreater(score, 0.0)

        # Результаты отсортированы по score desc
        scores = [s for _, s in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_bm25_search_empty_corpus(self):
        """BM25-поиск по пустому корпусу возвращает пустой список."""
        from src.group_knowledge.qa_search import QASearchService

        service = QASearchService()
        with patch("src.group_knowledge.qa_search.gk_db.get_all_approved_qa_pairs", return_value=[]):
            results = service._bm25_search("Как включить NFC?", top_k=5)
        self.assertEqual(results, [])

    def test_corpus_caching(self):
        """Корпус кэшируется и не перезагружается на каждый запрос."""
        from src.group_knowledge.qa_search import QASearchService
        from src.group_knowledge.models import QAPair

        service = QASearchService()
        pairs = [
            QAPair(id=1, question_text="Тестовый вопрос",
                   answer_text="Тестовый ответ", group_id=-100, approved=1),
        ]

        with patch("src.group_knowledge.qa_search.gk_db.get_all_approved_qa_pairs", return_value=pairs) as mock_get:
            service._bm25_search("тест", top_k=5)
            service._bm25_search("другой запрос", top_k=5)

        # get_all_approved_qa_pairs вызывается только 1 раз (кэш)
        mock_get.assert_called_once()

    def test_invalidate_corpus_cache(self):
        """invalidate_corpus_cache сбрасывает кэш."""
        from src.group_knowledge.qa_search import QASearchService
        from src.group_knowledge.models import QAPair

        service = QASearchService()
        pairs = [
            QAPair(id=1, question_text="Вопрос", answer_text="Ответ",
                   group_id=-100, approved=1),
        ]

        with patch("src.group_knowledge.qa_search.gk_db.get_all_approved_qa_pairs", return_value=pairs) as mock_get:
            service._bm25_search("тест", top_k=5)
            service.invalidate_corpus_cache()
            service._bm25_search("тест", top_k=5)

        # После инвалидации — загрузка повторяется
        self.assertEqual(mock_get.call_count, 2)

    def test_corpus_reloads_when_signature_changes(self):
        """BM25-кэш перезагружается, если изменилась сигнатура корпуса."""
        from src.group_knowledge.qa_search import QASearchService
        from src.group_knowledge.models import QAPair

        service = QASearchService()
        pairs_v1 = [
            QAPair(id=1, question_text="Ошибка продажи", answer_text="Проверьте ФН", group_id=-100, approved=1, created_at=100),
        ]
        pairs_v2 = [
            QAPair(id=1, question_text="Ошибка продажи", answer_text="Проверьте ФН", group_id=-100, approved=1, created_at=100),
            QAPair(id=2, question_text="Ошибка печати", answer_text="Проверьте бумагу", group_id=-100, approved=1, created_at=200),
        ]

        with patch("src.group_knowledge.qa_search.gk_db.get_approved_qa_pairs_corpus_signature", side_effect=[(1, 1, 100), (2, 2, 200)]), \
             patch("src.group_knowledge.qa_search.gk_db.get_all_approved_qa_pairs", side_effect=[pairs_v1, pairs_v2]) as mock_get:
            service._bm25_search("ошибка продажи", top_k=5)
            service._bm25_search("ошибка печати", top_k=5)

        self.assertEqual(mock_get.call_count, 2)

    def test_warmup_preloads_corpus_and_vector_model(self):
        """warmup прогревает корпус и vector модель, возвращая диагностику."""
        from src.group_knowledge.qa_search import QASearchService
        from src.group_knowledge.models import QAPair

        service = QASearchService()
        pairs = [
            QAPair(id=1, question_text="Ошибка продажи", answer_text="Проверьте ФН", group_id=-100, approved=1, created_at=100),
        ]

        mock_embedding_provider = MagicMock()
        mock_embedding_provider.encode.return_value = [0.1, 0.2, 0.3]

        with patch("src.group_knowledge.qa_search.gk_db.get_approved_qa_pairs_corpus_signature", return_value=(1, 1, 100)), \
             patch("src.group_knowledge.qa_search.gk_db.get_all_approved_qa_pairs", return_value=pairs), \
             patch("src.core.ai.vector_search.LocalEmbeddingProvider", return_value=mock_embedding_provider), \
             patch("src.core.ai.vector_search.LocalVectorIndex"):
            diagnostics = service.warmup(preload_vector_model=True)

        self.assertEqual(diagnostics["corpus_pairs"], 1)
        self.assertEqual(diagnostics["corpus_signature"], (1, 1, 100))
        self.assertTrue(diagnostics["vector_model_preloaded"])
        mock_embedding_provider.encode.assert_called_once()

    def test_bm25_log_contains_token_diagnostics(self):
        """Лог BM25 содержит расширенную диагностику токенизации запроса."""
        from src.group_knowledge.qa_search import QASearchService
        from src.group_knowledge.models import QAPair

        service = QASearchService()
        pairs = [
            QAPair(
                id=1,
                question_text="Ошибка при продаже",
                answer_text="Проверьте ФН и перезапустите терминал",
                group_id=-100,
                approved=1,
            ),
        ]

        with patch("src.group_knowledge.qa_search.gk_db.get_all_approved_qa_pairs", return_value=pairs), \
             patch("src.group_knowledge.qa_search.logger.info") as mock_log_info:
            service._bm25_search("ошибка при продаже почему?", top_k=3)

        self.assertTrue(any(
            call.args
            and isinstance(call.args[0], str)
            and "query_tokens_total=" in call.args[0]
            and "removed_stopwords_count=" in call.args[0]
            and "query_tokens_head=" in call.args[0]
            for call in mock_log_info.call_args_list
        ))


# ===========================================================================
# QASearchService — RRF merge
# ===========================================================================

class TestGKRRFMerge(unittest.TestCase):
    """Тесты для QASearchService._rrf_merge."""

    def _make_pair(self, pair_id, question="q"):
        from src.group_knowledge.models import QAPair
        return QAPair(id=pair_id, question_text=question, answer_text="a",
                      group_id=-100, approved=1)

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_overlapping_results(self, mock_settings):
        """Пары, присутствующие в обоих списках, получают более высокий RRF-score."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RRF_K = 60

        pair_a = self._make_pair(1, "Общая пара")
        pair_b = self._make_pair(2, "Только BM25")
        pair_c = self._make_pair(3, "Только vector")

        bm25_results = [(pair_a, 5.0), (pair_b, 3.0)]
        vector_results = [(pair_c, 0.9), (pair_a, 0.85)]

        merged, diagnostics = QASearchService._rrf_merge(bm25_results, vector_results, top_k=5)

        # pair_a должна быть первой (присутствует в обоих списках)
        self.assertEqual(merged[0][0].id, 1)
        # Все 3 пары в результатах
        result_ids = {p.id for p, _ in merged}
        self.assertEqual(result_ids, {1, 2, 3})

        # RRF-score пары A > любой одиночной пары
        pair_a_score = next(s for p, s in merged if p.id == 1)
        for p, s in merged:
            if p.id != 1:
                self.assertGreater(pair_a_score, s)

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_diagnostics_format(self, mock_settings):
        """Диагностический словарь содержит все обязательные ключи."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RRF_K = 60

        pair = self._make_pair(10, "Тестовый вопрос")
        bm25_results = [(pair, 4.5)]
        vector_results = [(pair, 0.92)]

        _, diagnostics = QASearchService._rrf_merge(bm25_results, vector_results, top_k=5)

        self.assertEqual(len(diagnostics), 1)
        d = diagnostics[0]
        self.assertIn("pair_id", d)
        self.assertIn("question_preview", d)
        self.assertIn("bm25_rank", d)
        self.assertIn("bm25_score", d)
        self.assertIn("vector_rank", d)
        self.assertIn("vector_score", d)
        self.assertIn("rrf_score", d)
        self.assertEqual(d["pair_id"], 10)
        self.assertEqual(d["bm25_rank"], 1)
        self.assertEqual(d["vector_rank"], 1)

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_rrf_formula_correctness(self, mock_settings):
        """RRF-score вычисляется по формуле 1/(k + rank)."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RRF_K = 60

        pair = self._make_pair(1)
        bm25_results = [(pair, 5.0)]
        vector_results = [(pair, 0.9)]

        merged, _ = QASearchService._rrf_merge(bm25_results, vector_results, top_k=1)

        expected_rrf = 1.0 / (60 + 1) + 1.0 / (60 + 1)
        self.assertAlmostEqual(merged[0][1], expected_rrf, places=6)

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_bm25_only_pair(self, mock_settings):
        """Пара, присутствующая только в BM25, получает score от одного источника."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RRF_K = 60

        pair = self._make_pair(1)
        bm25_results = [(pair, 5.0)]
        vector_results = []

        merged, diagnostics = QASearchService._rrf_merge(bm25_results, vector_results, top_k=5)

        self.assertEqual(len(merged), 1)
        expected_rrf = 1.0 / (60 + 1)
        self.assertAlmostEqual(merged[0][1], expected_rrf, places=6)
        self.assertIsNone(diagnostics[0]["vector_rank"])

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_top_k_limits_output(self, mock_settings):
        """top_k ограничивает количество выходных результатов."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RRF_K = 60

        pairs = [self._make_pair(i) for i in range(1, 11)]
        bm25_results = [(p, 10.0 - i) for i, p in enumerate(pairs)]
        vector_results = [(p, 1.0 - i * 0.05) for i, p in enumerate(pairs)]

        merged, diagnostics = QASearchService._rrf_merge(bm25_results, vector_results, top_k=3)

        self.assertEqual(len(merged), 3)
        self.assertEqual(len(diagnostics), 3)


# ===========================================================================
# QASearchService — Hybrid search (integration with mocked methods)
# ===========================================================================

class TestGKHybridSearch(unittest.TestCase):
    """Тесты для QASearchService.search (гибридный BM25+Vector+RRF)."""

    def _make_pair(self, pair_id, question="q"):
        from src.group_knowledge.models import QAPair
        return QAPair(id=pair_id, question_text=question, answer_text="a",
                      group_id=-100, approved=1)

    def test_hybrid_search_calls_both_methods(self):
        """search() вызывает и BM25, и vector поиск."""
        from src.group_knowledge.qa_search import QASearchService

        service = QASearchService()
        pair1 = self._make_pair(1, "BM25 пара")
        pair2 = self._make_pair(2, "Vector пара")

        with patch.object(service, "_bm25_search", return_value=[(pair1, 5.0)]) as mock_bm25, \
             patch.object(service, "_vector_search", new=AsyncMock(return_value=[(pair2, 0.9)])) as mock_vec:
            results = _run_async(service.search("test query"))

        mock_bm25.assert_called_once()
        mock_vec.assert_called_once()
        self.assertGreater(len(results), 0)

    def test_hybrid_search_rrf_order(self):
        """Пары из обоих списков ранжируются выше одиночных."""
        from src.group_knowledge.qa_search import QASearchService

        service = QASearchService()
        shared_pair = self._make_pair(1, "Общая")
        bm25_only = self._make_pair(2, "Только BM25")
        vec_only = self._make_pair(3, "Только vector")

        bm25_results = [(shared_pair, 5.0), (bm25_only, 3.0)]
        vector_results = [(vec_only, 0.95), (shared_pair, 0.85)]

        with patch.object(service, "_bm25_search", return_value=bm25_results), \
             patch.object(service, "_vector_search", new=AsyncMock(return_value=vector_results)):
            results = _run_async(service.search("test", top_k=5))

        # Shared pair должна быть первой
        self.assertEqual(results[0].id, 1)

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_hybrid_disabled_uses_vector_only(self, mock_settings):
        """Когда GK_HYBRID_ENABLED=False, используются только vector результаты."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_HYBRID_ENABLED = False
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_RESPONDER_MODEL = "deepseek-chat"
        mock_settings.GK_SEARCH_CANDIDATES_PER_METHOD = 20

        service = QASearchService()
        bm25_pair = self._make_pair(1, "BM25")
        vec_pair = self._make_pair(2, "Vector")

        with patch.object(service, "_bm25_search", return_value=[(bm25_pair, 5.0)]), \
             patch.object(service, "_vector_search", new=AsyncMock(return_value=[(vec_pair, 0.9)])):
            results = _run_async(service.search("test"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, 2)

    def test_fallback_bm25_only_when_no_vector(self):
        """Если vector пуст, используются только BM25 результаты."""
        from src.group_knowledge.qa_search import QASearchService

        service = QASearchService()
        pair = self._make_pair(1, "BM25 пара")

        with patch.object(service, "_bm25_search", return_value=[(pair, 5.0)]), \
             patch.object(service, "_vector_search", new=AsyncMock(return_value=[])):
            results = _run_async(service.search("test"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, 1)

    def test_fallback_vector_only_when_no_bm25(self):
        """Если BM25 пуст, используются только vector результаты."""
        from src.group_knowledge.qa_search import QASearchService

        service = QASearchService()
        pair = self._make_pair(1, "Vector пара")

        with patch.object(service, "_bm25_search", return_value=[]), \
             patch.object(service, "_vector_search", new=AsyncMock(return_value=[(pair, 0.9)])):
            results = _run_async(service.search("test"))

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, 1)


# ===========================================================================
# Database — get_all_approved_qa_pairs
# ===========================================================================

class TestGetAllApprovedQAPairs(unittest.TestCase):
    """Тесты для database.get_all_approved_qa_pairs."""

    @patch("src.group_knowledge.database.get_db_connection")
    def test_returns_approved_pairs(self, mock_conn_ctx):
        """Возвращает только одобренные Q&A-пары."""
        from src.group_knowledge.database import get_all_approved_qa_pairs

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "id": 1, "question_text": "Q1", "answer_text": "A1",
                "question_message_id": None, "answer_message_id": None,
                "group_id": -100, "extraction_type": "thread_reply",
                "confidence": 0.9, "llm_model_used": "", "created_at": 0,
                "approved": 1, "vector_indexed": 0,
            },
        ]
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            pairs = get_all_approved_qa_pairs()

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].question_text, "Q1")

    @patch("src.group_knowledge.database.get_db_connection")
    def test_empty_table(self, mock_conn_ctx):
        """Пустая таблица возвращает пустой список."""
        from src.group_knowledge.database import get_all_approved_qa_pairs

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            pairs = get_all_approved_qa_pairs()

        self.assertEqual(pairs, [])

    @patch("src.group_knowledge.database.get_db_connection")
    def test_get_approved_qa_pairs_corpus_signature(self, mock_conn_ctx):
        """Сигнатура корпуса возвращает count/max_id/max_created_at."""
        from src.group_knowledge.database import get_approved_qa_pairs_corpus_signature

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            "cnt": 42,
            "max_id": 123,
            "max_created_at": 1700000000,
        }
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.return_value = mock_conn

        with patch("src.group_knowledge.database.get_cursor") as mock_cur_ctx:
            mock_cur_ctx.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cur_ctx.return_value.__exit__ = MagicMock(return_value=False)

            signature = get_approved_qa_pairs_corpus_signature()

        self.assertEqual(signature, (42, 123, 1700000000))


if __name__ == "__main__":
    unittest.main()
