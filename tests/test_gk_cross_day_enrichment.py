"""Тесты кросс-дневного обогащения цепочек в QAAnalyzer."""

import unittest
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import patch

from src.group_knowledge.models import GroupMessage
from src.group_knowledge.qa_analyzer import QAAnalyzer


def _make_msg(
    telegram_message_id: int,
    group_id: int = -1001,
    sender_id: int = 100,
    sender_name: str = "User",
    message_text: str = "text",
    reply_to_message_id: Optional[int] = None,
    message_date: int = 1_700_000_000,
    db_id: Optional[int] = None,
    is_question: Optional[bool] = None,
    question_confidence: Optional[float] = None,
) -> GroupMessage:
    """Вспомогательная фабрика для GroupMessage."""
    return GroupMessage(
        id=db_id or telegram_message_id,
        telegram_message_id=telegram_message_id,
        group_id=group_id,
        sender_id=sender_id,
        sender_name=sender_name,
        message_text=message_text,
        reply_to_message_id=reply_to_message_id,
        message_date=message_date,
        collected_at=message_date,
        is_question=is_question,
        question_confidence=question_confidence,
    )


class TestEnrichWithCrossDayContext(unittest.TestCase):
    """Тесты метода QAAnalyzer._enrich_with_cross_day_context."""

    def setUp(self):
        self.analyzer = QAAnalyzer.__new__(QAAnalyzer)
        self.analyzer._model_name = "test-model"
        self.analyzer._batch_size = 50
        self.analyzer._question_confidence_threshold = 0.9

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_late_reply_enriched(self, mock_db, mock_settings):
        """Ответ из другого дня должен подгружаться в рабочий набор."""
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DEPTH = 2
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DAYS = 30

        # Сообщения текущего дня (29 янв)
        question = _make_msg(565318, message_date=1_706_511_064, sender_id=1,
                             message_text="Эвотор крутит кружок")
        reply_same_day = _make_msg(565335, message_date=1_706_515_757, sender_id=2,
                                   reply_to_message_id=565318,
                                   message_text="Новую фн вставить")
        day_messages = [question, reply_same_day]

        # Ответ из другого дня (31 янв), reply на 565318
        late_reply = _make_msg(565842, message_date=1_706_720_160, sender_id=3,
                               reply_to_message_id=565318,
                               message_text="Вставить сим и запустить")

        mock_db.get_messages_by_telegram_ids.return_value = []
        mock_db.get_replies_to_telegram_messages.return_value = [
            reply_same_day, late_reply,
        ]

        result = self.analyzer._enrich_with_cross_day_context(day_messages)

        tg_ids = {msg.telegram_message_id for msg in result}
        self.assertIn(565842, tg_ids, "Поздний ответ должен быть в результате")
        self.assertIn(565318, tg_ids)
        self.assertIn(565335, tg_ids)
        self.assertEqual(len(result), 3)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_parent_message_enriched(self, mock_db, mock_settings):
        """Родительское сообщение из другого дня загружается при наличии reply_to."""
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DEPTH = 2
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DAYS = 30

        # Текущий день содержит только ответ, но не оригинальный вопрос.
        reply_msg = _make_msg(565842, message_date=1_706_720_160, sender_id=3,
                              reply_to_message_id=565318,
                              message_text="Вставить сим")
        day_messages = [reply_msg]

        parent_msg = _make_msg(565318, message_date=1_706_511_064, sender_id=1,
                               message_text="Эвотор крутит кружок")

        mock_db.get_messages_by_telegram_ids.return_value = [parent_msg]
        mock_db.get_replies_to_telegram_messages.return_value = []

        result = self.analyzer._enrich_with_cross_day_context(day_messages)

        tg_ids = {msg.telegram_message_id for msg in result}
        self.assertIn(565318, tg_ids, "Родительское сообщение должно быть загружено")
        self.assertIn(565842, tg_ids)
        self.assertEqual(len(result), 2)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_no_cross_day_messages(self, mock_db, mock_settings):
        """Если нет кросс-дневных сообщений, набор не изменяется."""
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DEPTH = 2
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DAYS = 30

        msg1 = _make_msg(100, message_date=1_706_511_064, sender_id=1)
        msg2 = _make_msg(101, message_date=1_706_511_100, sender_id=2,
                         reply_to_message_id=100)
        day_messages = [msg1, msg2]

        mock_db.get_messages_by_telegram_ids.return_value = []
        mock_db.get_replies_to_telegram_messages.return_value = [msg1, msg2]

        result = self.analyzer._enrich_with_cross_day_context(day_messages)

        self.assertEqual(len(result), 2)
        self.assertEqual(
            {m.telegram_message_id for m in result},
            {100, 101},
        )

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_depth_limit_stops_expansion(self, mock_db, mock_settings):
        """Глубина обогащения ограничивается GK_ANALYSIS_CROSS_DAY_MAX_DEPTH."""
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DEPTH = 1
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DAYS = 30

        msg1 = _make_msg(100, message_date=1_706_511_064, sender_id=1)
        day_messages = [msg1]

        # Первый раунд вернёт msg 200, у которого reply_to=300 (ещё один уровень).
        reply_200 = _make_msg(200, message_date=1_706_600_000, sender_id=2,
                              reply_to_message_id=100)
        # Второй раунд — depth=1, не будет вызван из-за max_depth=1.
        reply_300 = _make_msg(300, message_date=1_706_700_000, sender_id=3,
                              reply_to_message_id=200)

        mock_db.get_messages_by_telegram_ids.return_value = []
        mock_db.get_replies_to_telegram_messages.return_value = [reply_200]

        result = self.analyzer._enrich_with_cross_day_context(day_messages)

        tg_ids = {msg.telegram_message_id for msg in result}
        self.assertIn(200, tg_ids, "Ответ из первого раунда должен быть добавлен")
        self.assertNotIn(300, tg_ids, "Ответ из второго раунда не должен быть — depth=1")
        self.assertEqual(len(result), 2)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_empty_messages_returns_empty(self, mock_db, mock_settings):
        """Пустой список сообщений возвращается без изменений."""
        result = self.analyzer._enrich_with_cross_day_context([])
        self.assertEqual(result, [])
        mock_db.get_messages_by_telegram_ids.assert_not_called()

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_result_sorted_by_date(self, mock_db, mock_settings):
        """Результат должен быть отсортирован по message_date."""
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DEPTH = 1
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DAYS = 30

        msg_late = _make_msg(200, message_date=1_706_600_000, sender_id=1)
        msg_early = _make_msg(100, message_date=1_706_500_000, sender_id=2,
                              reply_to_message_id=50)
        day_messages = [msg_late, msg_early]

        parent = _make_msg(50, message_date=1_706_400_000, sender_id=3,
                           message_text="Исходный вопрос")
        mock_db.get_messages_by_telegram_ids.return_value = [parent]
        mock_db.get_replies_to_telegram_messages.return_value = []

        result = self.analyzer._enrich_with_cross_day_context(day_messages)

        dates = [m.message_date for m in result]
        self.assertEqual(dates, sorted(dates), "Результат должен быть отсортирован по дате")

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_bidirectional_enrichment(self, mock_db, mock_settings):
        """Обогащение работает в обе стороны: вверх (родители) и вниз (ответы)."""
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DEPTH = 2
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DAYS = 30

        # Сообщение текущего дня с reply_to и потенциальным ответом.
        msg = _make_msg(200, message_date=1_706_600_000, sender_id=1,
                        reply_to_message_id=100)
        day_messages = [msg]

        parent = _make_msg(100, message_date=1_706_500_000, sender_id=2,
                           message_text="Вопрос")
        child = _make_msg(300, message_date=1_706_700_000, sender_id=3,
                          reply_to_message_id=200, message_text="Ещё ответ")

        def fake_parents(group_id, tg_ids):
            return [parent] if 100 in tg_ids else []

        # Первый вызов replies: ответы на [200] → child.
        # Второй вызов replies: ответы на [100, 200, 300] → child+msg (уже в наборе).
        replies_calls = [0]

        def fake_replies(group_id, tg_ids, min_timestamp=0):
            replies_calls[0] += 1
            if replies_calls[0] == 1:
                return [child]
            return [msg, child]

        mock_db.get_messages_by_telegram_ids.side_effect = fake_parents
        mock_db.get_replies_to_telegram_messages.side_effect = fake_replies

        result = self.analyzer._enrich_with_cross_day_context(day_messages)

        tg_ids = {m.telegram_message_id for m in result}
        self.assertIn(100, tg_ids, "Родитель должен быть загружен")
        self.assertIn(200, tg_ids, "Исходное сообщение должно остаться")
        self.assertIn(300, tg_ids, "Ответ должен быть загружен")
        self.assertEqual(len(result), 3)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_multiple_groups_skipped(self, mock_db, mock_settings):
        """Если сообщения из разных групп — обогащение пропускается."""
        msg1 = _make_msg(100, group_id=-1001, message_date=1_706_500_000)
        msg2 = _make_msg(200, group_id=-1002, message_date=1_706_600_000)

        result = self.analyzer._enrich_with_cross_day_context([msg1, msg2])

        self.assertEqual(len(result), 2)
        mock_db.get_messages_by_telegram_ids.assert_not_called()


class TestExtractThreadPairsWithEnrichment(unittest.TestCase):
    """Тесты интеграции обогащения в _extract_thread_pairs."""

    def setUp(self):
        self.analyzer = QAAnalyzer.__new__(QAAnalyzer)
        self.analyzer._model_name = "test-model"
        self.analyzer._batch_size = 50
        self.analyzer._question_confidence_threshold = 0.9

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    def test_enrichment_called_when_enabled(self, mock_settings):
        """_enrich_with_cross_day_context вызывается при включённой настройке."""
        mock_settings.GK_ANALYSIS_CROSS_DAY_ENRICHMENT = True
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DEPTH = 1
        mock_settings.GK_ANALYSIS_CROSS_DAY_MAX_DAYS = 30

        messages = [
            _make_msg(100, message_date=1_706_500_000, sender_id=1),
        ]

        with patch.object(
            self.analyzer, "_enrich_with_cross_day_context", return_value=messages,
        ) as mock_enrich:
            import asyncio
            result = asyncio.run(
                self.analyzer._extract_thread_pairs(messages)
            )
            mock_enrich.assert_called_once_with(messages)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    def test_enrichment_skipped_when_disabled(self, mock_settings):
        """_enrich_with_cross_day_context НЕ вызывается при выключенной настройке."""
        mock_settings.GK_ANALYSIS_CROSS_DAY_ENRICHMENT = False

        messages = [
            _make_msg(100, message_date=1_706_500_000, sender_id=1),
        ]

        with patch.object(
            self.analyzer, "_enrich_with_cross_day_context", return_value=messages,
        ) as mock_enrich:
            import asyncio
            result = asyncio.run(
                self.analyzer._extract_thread_pairs(messages)
            )
            mock_enrich.assert_not_called()


class TestAppendNearbySequentialMessages(unittest.TestCase):
    """Тесты фильтрации в _append_nearby_sequential_messages."""

    def test_skip_independent_question_messages(self):
        """Сообщения, классифицированные как самостоятельные вопросы, не поглощаются."""
        # Цепочка: вопрос 565318 + ответ 565335.
        root = _make_msg(565318, message_date=1_706_511_064, sender_id=1,
                         message_text="Эвотор крутит кружок")
        reply = _make_msg(565335, message_date=1_706_515_757, sender_id=2,
                          reply_to_message_id=565318, message_text="Новую фн вставить")

        # Отдельный вопрос от того же отправителя, рядом по времени.
        independent_question = _make_msg(
            565408, message_date=1_706_531_017, sender_id=1,
            message_text="как долго добавляется организация в егаис?",
            is_question=True, question_confidence=1.0,
        )

        collected = [root, reply]
        visited = {root.telegram_message_id, reply.telegram_message_id}
        all_messages = [root, reply, independent_question]

        result = QAAnalyzer._append_nearby_sequential_messages(
            collected=collected,
            all_messages=all_messages,
            visited_ids=visited,
            question_confidence_threshold=0.90,
        )

        tg_ids = {m.telegram_message_id for m in result}
        self.assertNotIn(
            565408, tg_ids,
            "Самостоятельный вопрос не должен поглощаться в чужую цепочку",
        )

    def test_skip_foreign_reply_messages(self):
        """Сообщения с reply_to на другую цепочку не поглощаются."""
        root = _make_msg(100, message_date=1_706_500_000, sender_id=1,
                         message_text="Вопрос про Эвотор")
        reply = _make_msg(101, message_date=1_706_500_060, sender_id=2,
                          reply_to_message_id=100, message_text="Ответ")

        # Сообщение того же отправителя, рядом по времени, но reply_to на чужое сообщение.
        foreign_reply = _make_msg(
            102, message_date=1_706_500_100, sender_id=1,
            reply_to_message_id=999,  # Не в текущей цепочке.
            message_text="За 10 минут регал плакса назад",
        )

        collected = [root, reply]
        visited = {100, 101}
        all_messages = [root, reply, foreign_reply]

        result = QAAnalyzer._append_nearby_sequential_messages(
            collected=collected,
            all_messages=all_messages,
            visited_ids=visited,
            question_confidence_threshold=0.90,
        )

        tg_ids = {m.telegram_message_id for m in result}
        self.assertNotIn(
            102, tg_ids,
            "Сообщение с reply_to на чужую цепочку не должно поглощаться",
        )

    def test_allow_reply_to_own_thread(self):
        """Сообщения с reply_to внутри текущей цепочки не фильтруются."""
        root = _make_msg(100, message_date=1_706_500_000, sender_id=1)
        reply = _make_msg(101, message_date=1_706_500_060, sender_id=2,
                          reply_to_message_id=100)

        # Ещё одно сообщение от sender_id=1 с reply_to на root (100 — в visited).
        follow_up = _make_msg(
            102, message_date=1_706_500_120, sender_id=1,
            reply_to_message_id=100,
            message_text="Уточнение",
        )

        collected = [root, reply]
        visited = {100, 101}
        all_messages = [root, reply, follow_up]

        result = QAAnalyzer._append_nearby_sequential_messages(
            collected=collected,
            all_messages=all_messages,
            visited_ids=visited,
            question_confidence_threshold=0.90,
        )

        tg_ids = {m.telegram_message_id for m in result}
        self.assertIn(
            102, tg_ids,
            "Сообщение с reply_to внутри цепочки должно быть добавлено",
        )

    def test_allow_low_confidence_question(self):
        """Сообщения с is_question=True, но низкой уверенностью, допускаются."""
        root = _make_msg(100, message_date=1_706_500_000, sender_id=1)
        reply = _make_msg(101, message_date=1_706_500_060, sender_id=2,
                          reply_to_message_id=100)

        low_conf_question = _make_msg(
            102, message_date=1_706_500_120, sender_id=1,
            message_text="А это нормально?",
            is_question=True, question_confidence=0.55,
        )

        collected = [root, reply]
        visited = {100, 101}
        all_messages = [root, reply, low_conf_question]

        result = QAAnalyzer._append_nearby_sequential_messages(
            collected=collected,
            all_messages=all_messages,
            visited_ids=visited,
            question_confidence_threshold=0.90,
        )

        tg_ids = {m.telegram_message_id for m in result}
        self.assertIn(
            102, tg_ids,
            "Вопрос с уверенностью ниже порога может быть добавлен",
        )

    def test_no_reply_no_question_message_allowed(self):
        """Обычное сообщение без reply и без is_question поглощается как раньше."""
        root = _make_msg(100, message_date=1_706_500_000, sender_id=1)

        normal = _make_msg(
            101, message_date=1_706_500_060, sender_id=1,
            message_text="Ещё подробности",
        )

        collected = [root]
        visited = {100}
        all_messages = [root, normal]

        result = QAAnalyzer._append_nearby_sequential_messages(
            collected=collected,
            all_messages=all_messages,
            visited_ids=visited,
            question_confidence_threshold=0.90,
        )

        tg_ids = {m.telegram_message_id for m in result}
        self.assertIn(101, tg_ids)

    def test_real_scenario_two_separate_questions(self):
        """Реальный сценарий: два раздельных вопроса от одного пользователя."""
        # Вопрос 1: Про Эвотор.
        q1 = _make_msg(565318, message_date=1_706_511_064, sender_id=1,
                        message_text="Эвотор новый из коробки 7.3...")
        a1 = _make_msg(565335, message_date=1_706_515_757, sender_id=2,
                        reply_to_message_id=565318,
                        message_text="Новую фн вставить")
        a1_late = _make_msg(565842, message_date=1_706_720_160, sender_id=3,
                            reply_to_message_id=565318,
                            message_text="Помогло вставить сим")

        # Вопрос 2: Про ЕГАИС (другая тема, тот же отправитель).
        q2 = _make_msg(565408, message_date=1_706_531_017, sender_id=1,
                        message_text="как долго добавляется организация в егаис?",
                        is_question=True, question_confidence=1.0)
        # Ответ на q2 через другую цепочку.
        reply_q2 = _make_msg(565412, message_date=1_706_532_374, sender_id=1,
                             reply_to_message_id=565410,
                             message_text="Ожренеть..")
        reply_q2_2 = _make_msg(565416, message_date=1_706_532_499, sender_id=1,
                               reply_to_message_id=565415,
                               message_text="Ладно, спасибо")
        # Не связанное reply от того же пользователя на другую цепочку.
        unrelated = _make_msg(565320, message_date=1_706_511_922, sender_id=1,
                              reply_to_message_id=565319,
                              message_text="За 10 минут регал плакса назад")

        collected = [q1, a1, a1_late]
        visited = {q1.telegram_message_id, a1.telegram_message_id, a1_late.telegram_message_id}
        all_messages = [q1, unrelated, a1, q2, reply_q2, reply_q2_2, a1_late]

        result = QAAnalyzer._append_nearby_sequential_messages(
            collected=collected,
            all_messages=all_messages,
            visited_ids=visited,
            question_confidence_threshold=0.90,
        )

        tg_ids = {m.telegram_message_id for m in result}
        # Вопрос 2 и его ответы не должны попасть в цепочку вопроса 1.
        self.assertNotIn(565408, tg_ids, "Вопрос про ЕГАИС не в цепочке Эвотора")
        self.assertNotIn(565412, tg_ids, "Ответ на 565410 (чужой) не в цепочке Эвотора")
        self.assertNotIn(565416, tg_ids, "Ответ на 565415 (чужой) не в цепочке Эвотора")
        self.assertNotIn(565320, tg_ids, "Ответ на 565319 (чужой) не в цепочке Эвотора")
        # Оригинальные сообщения цепочки остаются.
        self.assertIn(565318, tg_ids)
        self.assertIn(565335, tg_ids)
        self.assertIn(565842, tg_ids)


if __name__ == "__main__":
    unittest.main()
