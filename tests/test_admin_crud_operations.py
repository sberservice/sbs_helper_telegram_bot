"""
Unit tests for admin CRUD operations in validation_rules.py.

Tests cover:
- test_regex_pattern() - regex validation
- load_all_rules() - loading rules with include_inactive option
- load_all_ticket_types_admin() - loading ticket types for admin
- create_validation_rule() - creating new rules
- update_validation_rule() - updating existing rules
- toggle_rule_active() - enabling/disabling rules
- delete_validation_rule() - deleting rules with cascade
- get_rules_for_ticket_type() - rules by ticket type
- get_ticket_types_for_rule() - ticket types by rule
- add_rule_to_ticket_type() - creating associations
- remove_rule_from_ticket_type() - removing associations
- get_rule_type_mapping() - all mappings
"""

import unittest
from unittest.mock import patch, MagicMock
from src.sbs_helper_telegram_bot.ticket_validator.validators import ValidationRule, TicketType


class TestTestRegexPattern(unittest.TestCase):
    """Tests for test_regex_pattern function."""

    def test_valid_regex_without_test_text(self):
        """Test valid regex pattern validation without test text."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import test_regex_pattern
        
        is_valid, message = test_regex_pattern(r'\d{10,12}')
        
        self.assertTrue(is_valid)
        self.assertIn("✅", message)
        self.assertIn("валиден", message.lower())

    def test_valid_regex_with_matching_text(self):
        """Test valid regex with test text that matches."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import test_regex_pattern
        
        is_valid, message = test_regex_pattern(r'ИНН\s*:\s*\d{10}', 'ИНН: 1234567890')
        
        self.assertTrue(is_valid)
        self.assertIn("✅", message)
        self.assertIn("совпадение", message.lower())

    def test_valid_regex_with_non_matching_text(self):
        """Test valid regex with test text that doesn't match."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import test_regex_pattern
        
        is_valid, message = test_regex_pattern(r'ИНН\s*:\s*\d{10}', 'КПП: abcdefg')
        
        self.assertTrue(is_valid)
        self.assertIn("✅", message)
        self.assertIn("не найдено", message.lower())

    def test_invalid_regex_pattern(self):
        """Test invalid regex pattern returns error."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import test_regex_pattern
        
        is_valid, message = test_regex_pattern(r'[invalid(')
        
        self.assertFalse(is_valid)
        self.assertIn("❌", message)
        self.assertIn("ошибка", message.lower())

    def test_complex_valid_regex(self):
        """Test complex valid regex pattern."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import test_regex_pattern
        
        complex_pattern = r'(?i)(ИНН|инн|inn)\s*[:\-]?\s*\d{10,12}'
        is_valid, message = test_regex_pattern(complex_pattern, 'ИНН-1234567890')
        
        self.assertTrue(is_valid)
        self.assertIn("✅", message)

    def test_empty_pattern(self):
        """Test empty pattern (valid in regex)."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import test_regex_pattern
        
        is_valid, message = test_regex_pattern('')
        
        self.assertTrue(is_valid)


class TestLoadAllRules(unittest.TestCase):
    """Tests for load_all_rules function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_load_all_rules_active_only(self, mock_get_cursor, mock_get_conn):
        """Test loading only active rules."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import load_all_rules
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'rule_name': 'test_rule',
                'pattern': r'\d+',
                'rule_type': 'regex',
                'error_message': 'Error',
                'active': 1,
                'priority': 5
            }
        ]
        
        rules = load_all_rules(include_inactive=False)
        
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].rule_name, 'test_rule')
        self.assertTrue(rules[0].active)
        
        # Check SQL contains active = 1
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        self.assertIn("active = 1", sql.lower())

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_load_all_rules_including_inactive(self, mock_get_cursor, mock_get_conn):
        """Test loading all rules including inactive."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import load_all_rules
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_cursor.fetchall.return_value = [
            {
                'id': 1, 'rule_name': 'active_rule', 'pattern': r'\d+',
                'rule_type': 'regex', 'error_message': 'Error', 'active': 1, 'priority': 5
            },
            {
                'id': 2, 'rule_name': 'inactive_rule', 'pattern': r'\w+',
                'rule_type': 'regex', 'error_message': 'Error 2', 'active': 0, 'priority': 3
            }
        ]
        
        rules = load_all_rules(include_inactive=True)
        
        self.assertEqual(len(rules), 2)
        
        # Check SQL does NOT contain active = 1 filter
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        self.assertNotIn("where", sql.lower())

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_load_all_rules_empty_result(self, mock_get_cursor, mock_get_conn):
        """Test loading rules when none exist."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import load_all_rules
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        
        rules = load_all_rules()
        
        self.assertEqual(len(rules), 0)
        self.assertIsInstance(rules, list)


class TestLoadAllTicketTypesAdmin(unittest.TestCase):
    """Tests for load_all_ticket_types_admin function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_load_ticket_types_active_only(self, mock_get_cursor, mock_get_conn):
        """Test loading only active ticket types."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import load_all_ticket_types_admin
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'type_name': 'Выезд на диагностику',
                'description': 'Test description',
                'detection_keywords': '["выезд", "диагностика"]',
                'active': 1
            }
        ]
        
        types = load_all_ticket_types_admin(include_inactive=False)
        
        self.assertEqual(len(types), 1)
        self.assertEqual(types[0].type_name, 'Выезд на диагностику')
        self.assertTrue(types[0].active)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_load_ticket_types_including_inactive(self, mock_get_cursor, mock_get_conn):
        """Test loading all ticket types including inactive."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import load_all_ticket_types_admin
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'type_name': 'Active', 'description': '', 'detection_keywords': '[]', 'active': 1},
            {'id': 2, 'type_name': 'Inactive', 'description': '', 'detection_keywords': '[]', 'active': 0}
        ]
        
        types = load_all_ticket_types_admin(include_inactive=True)
        
        self.assertEqual(len(types), 2)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_load_ticket_types_with_invalid_json_keywords(self, mock_get_cursor, mock_get_conn):
        """Test that invalid JSON in detection_keywords is handled gracefully."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import load_all_ticket_types_admin
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'type_name': 'Test', 'description': '', 'detection_keywords': 'invalid json', 'active': 1}
        ]
        
        types = load_all_ticket_types_admin()
        
        self.assertEqual(len(types), 1)
        self.assertEqual(types[0].detection_keywords, [])  # Should default to empty list


class TestCreateValidationRule(unittest.TestCase):
    """Tests for create_validation_rule function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_create_rule_success(self, mock_get_cursor, mock_get_conn):
        """Test creating a new validation rule."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import create_validation_rule
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.lastrowid = 42
        
        rule_id = create_validation_rule(
            rule_name='new_rule',
            pattern=r'\d{10}',
            rule_type='regex',
            error_message='Must contain 10 digits',
            priority=5
        )
        
        self.assertEqual(rule_id, 42)
        mock_cursor.execute.assert_called_once()

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_create_rule_with_default_priority(self, mock_get_cursor, mock_get_conn):
        """Test creating rule with default priority."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import create_validation_rule
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.lastrowid = 1
        
        create_validation_rule(
            rule_name='rule',
            pattern='pattern',
            rule_type='regex',
            error_message='Error'
        )
        
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[4], 0)  # Default priority


class TestUpdateValidationRule(unittest.TestCase):
    """Tests for update_validation_rule function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_update_rule_name(self, mock_get_cursor, mock_get_conn):
        """Test updating only rule name."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import update_validation_rule
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        
        result = update_validation_rule(rule_id=1, rule_name='new_name')
        
        self.assertTrue(result)
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        self.assertIn("rule_name", sql)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_update_multiple_fields(self, mock_get_cursor, mock_get_conn):
        """Test updating multiple fields at once."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import update_validation_rule
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        
        result = update_validation_rule(
            rule_id=1,
            rule_name='updated',
            pattern=r'\d+',
            error_message='New error'
        )
        
        self.assertTrue(result)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_update_no_fields_returns_false(self, mock_get_cursor, mock_get_conn):
        """Test updating with no fields returns False."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import update_validation_rule
        
        result = update_validation_rule(rule_id=1)
        
        self.assertFalse(result)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_update_nonexistent_rule(self, mock_get_cursor, mock_get_conn):
        """Test updating nonexistent rule returns False."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import update_validation_rule
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 0
        
        result = update_validation_rule(rule_id=999, rule_name='new')
        
        self.assertFalse(result)


class TestToggleRuleActive(unittest.TestCase):
    """Tests for toggle_rule_active function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_enable_rule(self, mock_get_cursor, mock_get_conn):
        """Test enabling a rule."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import toggle_rule_active
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        
        result = toggle_rule_active(rule_id=1, active=True)
        
        self.assertTrue(result)
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[0], 1)  # active = 1

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_disable_rule(self, mock_get_cursor, mock_get_conn):
        """Test disabling a rule."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import toggle_rule_active
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        
        result = toggle_rule_active(rule_id=1, active=False)
        
        self.assertTrue(result)
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        self.assertEqual(params[0], 0)  # active = 0


class TestDeleteValidationRule(unittest.TestCase):
    """Tests for delete_validation_rule function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_delete_rule_with_associations(self, mock_get_cursor, mock_get_conn):
        """Test deleting rule that has ticket type associations."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import delete_validation_rule
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        # First call deletes associations, second deletes rule
        mock_cursor.rowcount = 3  # 3 associations deleted, then 1 rule
        
        success, deleted_assoc = delete_validation_rule(rule_id=1)
        
        self.assertTrue(success)
        self.assertEqual(deleted_assoc, 3)
        # Verify two SQL calls - first for associations, then for rule
        self.assertEqual(mock_cursor.execute.call_count, 2)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_delete_rule_without_associations(self, mock_get_cursor, mock_get_conn):
        """Test deleting rule that has no associations."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import delete_validation_rule
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        # No associations, then rule deleted
        mock_cursor.rowcount = 0
        
        def side_effect(*args):
            # First call returns 0 (no associations), second returns 1 (rule deleted)
            if mock_cursor.execute.call_count == 2:
                mock_cursor.rowcount = 1
        
        mock_cursor.execute.side_effect = side_effect
        
        success, deleted_assoc = delete_validation_rule(rule_id=1)
        
        self.assertEqual(deleted_assoc, 0)


class TestGetRulesForTicketType(unittest.TestCase):
    """Tests for get_rules_for_ticket_type function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_get_rules_for_ticket_type(self, mock_get_cursor, mock_get_conn):
        """Test getting rules for a specific ticket type."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import get_rules_for_ticket_type
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'rule_name': 'rule1', 'pattern': r'\d+', 'rule_type': 'regex',
             'error_message': 'Error', 'active': 1, 'priority': 5}
        ]
        
        rules = get_rules_for_ticket_type(ticket_type_id=1)
        
        self.assertEqual(len(rules), 1)
        self.assertIsInstance(rules[0], ValidationRule)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_get_rules_for_nonexistent_ticket_type(self, mock_get_cursor, mock_get_conn):
        """Test getting rules for nonexistent ticket type returns empty list."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import get_rules_for_ticket_type
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        
        rules = get_rules_for_ticket_type(ticket_type_id=999)
        
        self.assertEqual(rules, [])


class TestGetTicketTypesForRule(unittest.TestCase):
    """Tests for get_ticket_types_for_rule function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_get_ticket_types_for_rule(self, mock_get_cursor, mock_get_conn):
        """Test getting ticket types that use a rule."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import get_ticket_types_for_rule
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_cursor.fetchall.return_value = [
            {'id': 1, 'type_name': 'Выезд', 'description': '', 'detection_keywords': '[]', 'active': 1}
        ]
        
        types = get_ticket_types_for_rule(rule_id=1)
        
        self.assertEqual(len(types), 1)
        self.assertIsInstance(types[0], TicketType)


class TestAddRuleToTicketType(unittest.TestCase):
    """Tests for add_rule_to_ticket_type function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_add_rule_to_ticket_type_success(self, mock_get_cursor, mock_get_conn):
        """Test successfully adding rule to ticket type."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import add_rule_to_ticket_type
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        
        result = add_rule_to_ticket_type(rule_id=1, ticket_type_id=1)
        
        self.assertTrue(result)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_add_duplicate_association_returns_false(self, mock_get_cursor, mock_get_conn):
        """Test adding duplicate association returns False."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import add_rule_to_ticket_type
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.execute.side_effect = Exception("Duplicate entry")
        
        result = add_rule_to_ticket_type(rule_id=1, ticket_type_id=1)
        
        self.assertFalse(result)


class TestRemoveRuleFromTicketType(unittest.TestCase):
    """Tests for remove_rule_from_ticket_type function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_remove_rule_from_ticket_type_success(self, mock_get_cursor, mock_get_conn):
        """Test successfully removing rule from ticket type."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import remove_rule_from_ticket_type
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 1
        
        result = remove_rule_from_ticket_type(rule_id=1, ticket_type_id=1)
        
        self.assertTrue(result)

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_remove_nonexistent_association_returns_false(self, mock_get_cursor, mock_get_conn):
        """Test removing nonexistent association returns False."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import remove_rule_from_ticket_type
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.rowcount = 0
        
        result = remove_rule_from_ticket_type(rule_id=999, ticket_type_id=999)
        
        self.assertFalse(result)


class TestGetRuleTypeMapping(unittest.TestCase):
    """Tests for get_rule_type_mapping function."""

    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_db_connection')
    @patch('src.sbs_helper_telegram_bot.ticket_validator.validation_rules.database.get_cursor')
    def test_get_rule_type_mapping(self, mock_get_cursor, mock_get_conn):
        """Test getting all rule-to-type mappings."""
        from src.sbs_helper_telegram_bot.ticket_validator.validation_rules import get_rule_type_mapping
        
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)
        mock_get_cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_get_cursor.return_value.__exit__ = MagicMock(return_value=False)
        
        mock_cursor.fetchall.return_value = [
            {'rule_id': 1, 'rule_name': 'rule1', 'ticket_type_id': 1, 'type_name': 'Type1'},
            {'rule_id': 1, 'rule_name': 'rule1', 'ticket_type_id': 2, 'type_name': 'Type2'},
        ]
        
        mappings = get_rule_type_mapping()
        
        self.assertEqual(len(mappings), 2)
        self.assertIn('rule_id', mappings[0])
        self.assertIn('type_name', mappings[0])


if __name__ == '__main__':
    unittest.main()
