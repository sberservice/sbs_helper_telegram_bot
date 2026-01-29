"""
Unit tests for Telegram bot and MySQL database operations.

Tests cover:
- Invite validation and consumption
- User legitimacy checks
- Image queue management
- File size validation
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime

from src.common.constants.errorcodes import InviteStatus
from src.sbs_helper_telegram_bot.telegram_bot.telegram_bot import (
    check_if_invite_entered,
)
from src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part import (
    get_number_of_jobs_in_the_queue,
    check_if_user_has_unprocessed_job,
    add_to_image_queue,
)
from src.common.telegram_user import (
    check_if_user_legit,
    update_user_info_from_telegram,
)


class TestCheckIfInviteEntered(unittest.TestCase):
    """Tests for check_if_invite_entered function with race condition fix."""

    @patch('src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.database')
    def test_invite_not_exists(self, mock_database):
        """Test when invite code doesn't exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        # Simulate invite not found
        mock_cursor.fetchone.return_value = None
        
        result = check_if_invite_entered(123456, "invalid_code")
        
        self.assertEqual(result, InviteStatus.NOT_EXISTS)
        mock_cursor.execute.assert_called_once()

    @patch('src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.database')
    def test_invite_already_consumed(self, mock_database):
        """Test when invite code has already been consumed."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        # Simulate invite already consumed
        mock_cursor.fetchone.return_value = {"consumed_userid": 999999}
        
        result = check_if_invite_entered(123456, "already_used_code")
        
        self.assertEqual(result, InviteStatus.ALREADY_CONSUMED)

    @patch('src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.database')
    def test_invite_successfully_consumed(self, mock_database):
        """Test when invite code is valid and successfully consumed."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        # Simulate valid unused invite
        mock_cursor.fetchone.return_value = {"consumed_userid": None}
        
        result = check_if_invite_entered(123456, "valid_code")
        
        self.assertEqual(result, InviteStatus.SUCCESS)
        # Verify that UPDATE was executed
        calls = mock_cursor.execute.call_args_list
        self.assertEqual(len(calls), 2)  # SELECT FOR UPDATE + UPDATE
        self.assertIn("UPDATE", calls[1][0][0])

    @patch('src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.database')
    def test_invite_uses_select_for_update(self, mock_database):
        """Test that SELECT FOR UPDATE is used to prevent race conditions."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = {"consumed_userid": None}
        
        check_if_invite_entered(123456, "test_code")
        
        # Verify SELECT FOR UPDATE is used
        first_query = mock_cursor.execute.call_args_list[0][0][0]
        self.assertIn("FOR UPDATE", first_query)


class TestCheckIfUserLegit(unittest.TestCase):
    """Tests for check_if_user_legit function."""

    @patch('src.common.invites.database')
    @patch('src.common.telegram_user.database')
    def test_legitimate_user_exists(self, mock_database, mock_invites_database):
        """Test when user has consumed invite."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        # User has consumed an invite
        mock_cursor.fetchone.return_value = {"invite_consumed": 1}
        
        result = check_if_user_legit(123456)
        
        self.assertTrue(result)

    @patch('src.common.invites.check_if_user_pre_invited')
    @patch('src.common.telegram_user.database')
    def test_illegitimate_user_not_exists(self, mock_database, mock_pre_invited):
        """Test when user has no consumed invite and not pre-invited."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        # User has not consumed an invite
        mock_cursor.fetchone.return_value = {"invite_consumed": 0}
        # User is not pre-invited
        mock_pre_invited.return_value = False
        
        result = check_if_user_legit(123456)
        
        self.assertFalse(result)

    @patch('src.common.invites.check_if_user_pre_invited')
    @patch('src.common.telegram_user.database')
    def test_check_if_user_legit_queries_database(self, mock_database, mock_pre_invited):
        """Test that the function queries the correct table."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        # User has not consumed an invite
        mock_cursor.fetchone.return_value = {"invite_consumed": 0}
        # User is not pre-invited
        mock_pre_invited.return_value = False
        
        check_if_user_legit(123456)
        
        # Verify correct SQL query
        self.assertEqual(mock_cursor.execute.call_count, 1)
        query = mock_cursor.execute.call_args_list[0][0][0]
        self.assertIn("invites", query)
        self.assertIn("consumed_userid", query)


class TestUpdateUserInfoFromTelegram(unittest.TestCase):
    """Tests for update_user_info_from_telegram function."""

    @patch('src.common.telegram_user.database')
    def test_update_user_info_inserts_new_user(self, mock_database):
        """Test that new user is inserted."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_user = Mock()
        mock_user.id = 123456
        mock_user.first_name = "John"
        mock_user.last_name = "Doe"
        mock_user.username = "johndoe"
        
        update_user_info_from_telegram(mock_user)
        
        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        self.assertIn("INSERT", query)
        self.assertIn("users", query)

    @patch('src.common.telegram_user.database')
    def test_update_user_info_uses_duplicate_key_update(self, mock_database):
        """Test that INSERT ... ON DUPLICATE KEY UPDATE is used."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_user = Mock()
        mock_user.id = 123456
        mock_user.first_name = "Jane"
        mock_user.last_name = "Smith"
        mock_user.username = "janesmith"
        
        update_user_info_from_telegram(mock_user)
        
        query = mock_cursor.execute.call_args[0][0]
        self.assertIn("on duplicate key update", query.lower())


class TestGetNumberOfJobsInQueue(unittest.TestCase):
    """Tests for get_number_of_jobs_in_the_queue function."""

    @patch('src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part.database')
    def test_returns_zero_when_no_jobs(self, mock_database):
        """Test returns 0 when queue is empty."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = {"jobs_in_the_queue": 0}
        
        result = get_number_of_jobs_in_the_queue()
        
        self.assertEqual(result, 0)

    @patch('src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part.database')
    def test_returns_job_count(self, mock_database):
        """Test returns correct job count."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = {"jobs_in_the_queue": 5}
        
        result = get_number_of_jobs_in_the_queue()
        
        self.assertEqual(result, 5)

    @patch('src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part.database')
    def test_only_counts_unfinished_jobs(self, mock_database):
        """Test that only unfinished jobs (status < 2) are counted."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = {"jobs_in_the_queue": 3}
        
        get_number_of_jobs_in_the_queue()
        
        query = mock_cursor.execute.call_args[0][0]
        self.assertIn("status <2", query)


class TestCheckIfUserHasUnprocessedJob(unittest.TestCase):
    """Tests for check_if_user_has_unprocessed_job function."""

    @patch('src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part.database')
    def test_returns_false_when_no_unprocessed_jobs(self, mock_database):
        """Test returns False when user has no unprocessed jobs."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = {"number_of_jobs": 0}
        
        result = check_if_user_has_unprocessed_job(123456)
        
        self.assertFalse(result)

    @patch('src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part.database')
    def test_returns_true_when_unprocessed_jobs_exist(self, mock_database):
        """Test returns True when user has unprocessed jobs."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = {"number_of_jobs": 2}
        
        result = check_if_user_has_unprocessed_job(123456)
        
        self.assertTrue(result)

    @patch('src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part.database')
    def test_only_checks_unfinished_jobs(self, mock_database):
        """Test that only unfinished jobs (status <> 2) are checked."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        mock_cursor.fetchone.return_value = {"number_of_jobs": 1}
        
        check_if_user_has_unprocessed_job(123456)
        
        query = mock_cursor.execute.call_args[0][0]
        self.assertIn("status<>2", query)


class TestAddToImageQueue(unittest.TestCase):
    """Tests for add_to_image_queue function."""

    @patch('src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part.database')
    def test_adds_job_to_queue(self, mock_database):
        """Test that job is added to image queue."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        add_to_image_queue(123456, "screenshot.jpg")
        
        mock_cursor.execute.assert_called_once()
        query = mock_cursor.execute.call_args[0][0]
        self.assertIn("INSERT", query)
        self.assertIn("imagequeue", query)

    @patch('src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part.database')
    def test_sets_initial_status_to_zero(self, mock_database):
        """Test that new job has status 0 (pending)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        add_to_image_queue(123456, "screenshot.jpg")
        
        query = mock_cursor.execute.call_args[0][0]
        self.assertIn("0", query)  # status = 0

    @patch('src.sbs_helper_telegram_bot.vyezd_byl.vyezd_byl_bot_part.database')
    def test_includes_user_id_and_file_name(self, mock_database):
        """Test that user_id and file_name are included in insert."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__.return_value = mock_conn
        mock_database.get_cursor.return_value.__enter__.return_value = mock_cursor
        
        add_to_image_queue(123456, "screenshot.jpg")
        
        values = mock_cursor.execute.call_args[0][1]
        self.assertEqual(values[0], 123456)  # user_id
        self.assertEqual(values[1], "screenshot.jpg")  # file_name


class TestDatabaseConnectionHandling(unittest.TestCase):
    """Tests for database connection and transaction handling."""

    @patch('src.sbs_helper_telegram_bot.telegram_bot.telegram_bot.database')
    def test_connection_context_manager_used(self, mock_database):
        """Test that database connection context manager is properly used."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        mock_database.get_db_connection.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_database.get_db_connection.return_value.__exit__ = Mock(return_value=None)
        mock_database.get_cursor.return_value.__enter__ = Mock(return_value=mock_cursor)
        mock_database.get_cursor.return_value.__exit__ = Mock(return_value=None)
        
        mock_cursor.fetchone.return_value = {"consumed_userid": None}
        
        check_if_invite_entered(123456, "test_code")
        
        # Verify context managers are used
        mock_database.get_db_connection.return_value.__enter__.assert_called()
        mock_database.get_db_connection.return_value.__exit__.assert_called()


if __name__ == '__main__':
    unittest.main()
