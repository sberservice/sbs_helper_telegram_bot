"""Тесты фильтрации событий геймификации по модулю-источнику."""

import unittest
from unittest.mock import patch


class TestGamificationEventsFilter(unittest.TestCase):
    """Проверки временного фильтра событий геймификации."""

    def test_non_certification_event_is_ignored(self):
        """События не из аттестации должны игнорироваться полностью."""
        from src.sbs_helper_telegram_bot.gamification import events

        with patch.object(events, '_log_event') as mock_log_event, \
             patch.object(events, '_increment_achievement_progress') as mock_increment, \
             patch.object(events, '_award_score_for_action') as mock_award:
            events.emit_event('ktr.lookup', 1001, {'code': 'KTR-01'})

        mock_log_event.assert_not_called()
        mock_increment.assert_not_called()
        mock_award.assert_not_called()

    def test_certification_event_is_processed(self):
        """События аттестации должны обрабатываться как раньше."""
        from src.sbs_helper_telegram_bot.gamification import events

        with patch.object(events, '_log_event') as mock_log_event, \
             patch.object(events, '_increment_achievement_progress') as mock_increment, \
             patch.object(events, '_award_score_for_action') as mock_award:
            events.emit_event('certification.test_passed', 1002, {'attempt_id': 77})

        mock_log_event.assert_called_once()
        mock_increment.assert_called_once_with(1002, 'cert_test_passed')
        mock_award.assert_called_once_with(1002, 'certification', 'test_passed')


if __name__ == '__main__':
    unittest.main()
