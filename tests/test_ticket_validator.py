"""
Unit tests for ticket validator module.

Tests cover:
- Validation rule types (regex, required_field, format, length)
- ValidationRule and ValidationResult classes
- Ticket type detection
- Edge cases and error handling
- All validator functions
"""

import unittest
from src.sbs_helper_telegram_bot.ticket_validator.validators import (
    ValidationRule,
    ValidationResult,
    RuleType,
    TicketType,
    KeywordMatch,
    TicketTypeScore,
    DetectionDebugInfo,
    validate_regex,
    validate_required_field,
    validate_format,
    validate_length,
    validate_ticket,
    detect_ticket_type
)


class TestValidationRule(unittest.TestCase):
    """Tests for ValidationRule class."""

    def test_validation_rule_creation(self):
        """Test creating a ValidationRule with all fields."""
        rule = ValidationRule(
            id=1,
            rule_name="test_rule",
            pattern="test_pattern",
            rule_type="regex",
            error_message="Test error",
            active=True,
            priority=5
        )
        
        self.assertEqual(rule.id, 1)
        self.assertEqual(rule.rule_name, "test_rule")
        self.assertEqual(rule.pattern, "test_pattern")
        self.assertEqual(rule.rule_type, RuleType.REGEX)
        self.assertTrue(rule.active)
        self.assertEqual(rule.priority, 5)

    def test_validation_rule_with_enum_type(self):
        """Test creating a ValidationRule with RuleType enum."""
        rule = ValidationRule(
            id=2,
            rule_name="enum_rule",
            pattern="pattern",
            rule_type=RuleType.REQUIRED_FIELD,
            error_message="Error",
            active=False,
            priority=0
        )
        
        self.assertEqual(rule.rule_type, RuleType.REQUIRED_FIELD)
        self.assertFalse(rule.active)


class TestValidationResult(unittest.TestCase):
    """Tests for ValidationResult class."""

    def test_validation_result_valid(self):
        """Test creating a valid ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            failed_rules=[],
            error_messages=[]
        )
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.failed_rules), 0)
        self.assertEqual(len(result.error_messages), 0)

    def test_validation_result_invalid(self):
        """Test creating an invalid ValidationResult."""
        result = ValidationResult(
            is_valid=False,
            failed_rules=["rule1", "rule2"],
            error_messages=["Error 1", "Error 2"]
        )
        
        self.assertFalse(result.is_valid)
        self.assertEqual(len(result.failed_rules), 2)
        self.assertEqual(len(result.error_messages), 2)


class TestValidateRegex(unittest.TestCase):
    """Tests for validate_regex function."""

    def test_regex_match_found(self):
        """Test regex validation when pattern is found."""
        text = "ИНН: 1234567890"
        pattern = r'(?i)(ИНН|инн)\s*[:\-]?\s*\d{10,12}'
        
        result = validate_regex(text, pattern)
        self.assertTrue(result)

    def test_regex_match_not_found(self):
        """Test regex validation when pattern is not found."""
        text = "Система налогообложения: УСН"
        pattern = r'(?i)(ИНН|инн)\s*[:\-]?\s*\d{10,12}'
        
        result = validate_regex(text, pattern)
        self.assertFalse(result)

    def test_regex_case_insensitive(self):
        """Test regex validation with case insensitive flag."""
        text = "инн: 1234567890"
        pattern = r'(?i)(ИНН|инн)\s*[:\-]?\s*\d{10,12}'
        
        result = validate_regex(text, pattern)
        self.assertTrue(result)

    def test_regex_multiline(self):
        """Test regex validation with multiline text."""
        text = """
        Организация: ООО Тест
        ИНН: 1234567890
        Адрес: г. Москва
        """
        pattern = r'(?i)(ИНН|инн)\s*[:\-]?\s*\d{10,12}'
        
        result = validate_regex(text, pattern)
        self.assertTrue(result)

    def test_regex_invalid_pattern(self):
        """Test regex validation with invalid pattern."""
        text = "Some text"
        pattern = r'(?P<invalid'  # Invalid regex
        
        result = validate_regex(text, pattern)
        self.assertFalse(result)  # Should return False on error


class TestValidateRequiredField(unittest.TestCase):
    """Tests for validate_required_field function."""

    def test_required_field_with_colon(self):
        """Test required field validation with colon separator."""
        text = "Система налогообложения: УСН"
        field_name = "Система налогообложения"
        
        result = validate_required_field(text, field_name)
        self.assertTrue(result)

    def test_required_field_with_dash(self):
        """Test required field validation with dash separator."""
        text = "Контактное лицо - Иванов Иван"
        field_name = "Контактное лицо"
        
        result = validate_required_field(text, field_name)
        self.assertTrue(result)

    def test_required_field_case_insensitive(self):
        """Test required field validation is case insensitive."""
        text = "система налогообложения: осно"
        field_name = "Система Налогообложения"
        
        result = validate_required_field(text, field_name)
        self.assertTrue(result)

    def test_required_field_not_found(self):
        """Test required field validation when field is missing."""
        text = "ИНН: 1234567890"
        field_name = "Система налогообложения"
        
        result = validate_required_field(text, field_name)
        self.assertFalse(result)

    def test_required_field_with_special_chars(self):
        """Test required field with special characters in name."""
        text = "E-mail: test@example.com"
        field_name = "E-mail"
        
        result = validate_required_field(text, field_name)
        self.assertTrue(result)


class TestValidateFormat(unittest.TestCase):
    """Tests for validate_format function."""

    def test_format_phone_valid(self):
        """Test phone format validation with valid number."""
        text = "Телефон: +7 (999) 123-45-67"
        
        result = validate_format(text, "phone")
        self.assertTrue(result)

    def test_format_phone_alternative(self):
        """Test phone format with alternative format."""
        text = "Контакт: 8 495 123 45 67"
        
        result = validate_format(text, "phone")
        self.assertTrue(result)

    def test_format_phone_invalid(self):
        """Test phone format with invalid number."""
        text = "Телефон: 123"
        
        result = validate_format(text, "phone")
        self.assertFalse(result)

    def test_format_email_valid(self):
        """Test email format validation with valid email."""
        text = "Email: test@example.com"
        
        result = validate_format(text, "email")
        self.assertTrue(result)

    def test_format_email_invalid(self):
        """Test email format with invalid email."""
        text = "Email: invalid-email"
        
        result = validate_format(text, "email")
        self.assertFalse(result)

    def test_format_date_valid(self):
        """Test date format validation with valid date."""
        text = "Дата: 20.01.2026"
        
        result = validate_format(text, "date")
        self.assertTrue(result)

    def test_format_date_alternative_separators(self):
        """Test date format with different separators."""
        text1 = "Дата: 20/01/2026"
        text2 = "Дата: 20-01-2026"
        
        self.assertTrue(validate_format(text1, "date"))
        self.assertTrue(validate_format(text2, "date"))

    def test_format_inn_10_digits(self):
        """Test INN format with 10 digits."""
        text = "ИНН: 1234567890"
        
        result = validate_format(text, "inn_10")
        self.assertTrue(result)

    def test_format_inn_12_digits(self):
        """Test INN format with 12 digits."""
        text = "ИНН: 123456789012"
        
        result = validate_format(text, "inn_12")
        self.assertTrue(result)

    def test_format_inn_any(self):
        """Test INN format accepting both 10 and 12 digits."""
        text1 = "ИНН: 1234567890"
        text2 = "ИНН: 123456789012"
        
        self.assertTrue(validate_format(text1, "inn"))
        self.assertTrue(validate_format(text2, "inn"))

    def test_format_inn_invalid(self):
        """Test INN format with invalid digit count."""
        text = "ИНН: 12345"
        
        result = validate_format(text, "inn")
        self.assertFalse(result)

    def test_format_unknown_type(self):
        """Test format validation with unknown type."""
        text = "Some text"
        
        result = validate_format(text, "unknown_format")
        self.assertFalse(result)


class TestValidateLength(unittest.TestCase):
    """Tests for validate_length function."""

    def test_length_minimum_valid(self):
        """Test minimum length validation when valid."""
        text = "This is a test text with more than 10 characters"
        
        result = validate_length(text, "min:10")
        self.assertTrue(result)

    def test_length_minimum_invalid(self):
        """Test minimum length validation when too short."""
        text = "Short"
        
        result = validate_length(text, "min:10")
        self.assertFalse(result)

    def test_length_maximum_valid(self):
        """Test maximum length validation when valid."""
        text = "Short text"
        
        result = validate_length(text, "max:100")
        self.assertTrue(result)

    def test_length_maximum_invalid(self):
        """Test maximum length validation when too long."""
        text = "A" * 200
        
        result = validate_length(text, "max:100")
        self.assertFalse(result)

    def test_length_min_and_max_valid(self):
        """Test combined min and max length validation when valid."""
        text = "This text is just right"
        
        result = validate_length(text, "min:10,max:50")
        self.assertTrue(result)

    def test_length_min_and_max_too_short(self):
        """Test combined validation when too short."""
        text = "Short"
        
        result = validate_length(text, "min:10,max:50")
        self.assertFalse(result)

    def test_length_min_and_max_too_long(self):
        """Test combined validation when too long."""
        text = "A" * 100
        
        result = validate_length(text, "min:10,max:50")
        self.assertFalse(result)

    def test_length_exact_boundary(self):
        """Test length validation at exact boundary."""
        text = "A" * 10
        
        self.assertTrue(validate_length(text, "min:10"))
        self.assertTrue(validate_length(text, "max:10"))

    def test_length_invalid_spec(self):
        """Test length validation with invalid specification."""
        text = "Some text"
        
        # Invalid spec should not crash, just return True (no constraints applied)
        result = validate_length(text, "invalid:spec")
        self.assertTrue(result)


class TestValidateTicket(unittest.TestCase):
    """Tests for validate_ticket main function."""

    def test_validate_ticket_all_pass(self):
        """Test ticket validation when all rules pass."""
        ticket_text = """
        Организация: ООО Тест
        ИНН: 1234567890
        Система налогообложения: УСН
        Телефон: +7 (999) 123-45-67
        Адрес: г. Москва, ул. Тестовая, д. 1
        """
        
        rules = [
            ValidationRule(1, "inn", r'(?i)ИНН\s*[:\-]?\s*\d{10,12}', "regex", "ИНН не указан", True, 1),
            ValidationRule(2, "tax", r'(?i)налогообложени', "regex", "Система налогообложения не указана", True, 1),
        ]
        
        result = validate_ticket(ticket_text, rules)
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.failed_rules), 0)
        self.assertEqual(len(result.error_messages), 0)

    def test_validate_ticket_some_fail(self):
        """Test ticket validation when some rules fail."""
        ticket_text = """
        Организация: ООО Тест
        ИНН: 1234567890
        """
        
        rules = [
            ValidationRule(1, "inn", r'(?i)ИНН\s*[:\-]?\s*\d{10,12}', "regex", "ИНН не указан", True, 1),
            ValidationRule(2, "tax", r'(?i)налогообложени', "regex", "Система налогообложения не указана", True, 1),
            ValidationRule(3, "phone", r'(?i)(телефон|тел)\s*[:\-]?\s*\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}', "regex", "Телефон не указан", True, 1),
        ]
        
        result = validate_ticket(ticket_text, rules)
        
        self.assertFalse(result.is_valid)
        self.assertIn("tax", result.failed_rules)
        self.assertIn("phone", result.failed_rules)
        self.assertEqual(len(result.failed_rules), 2)
        self.assertIn("Система налогообложения не указана", result.error_messages)
        self.assertIn("Телефон не указан", result.error_messages)

    def test_validate_ticket_all_fail(self):
        """Test ticket validation when all rules fail."""
        ticket_text = "Пустая заявка"
        
        rules = [
            ValidationRule(1, "inn", r'(?i)ИНН\s*[:\-]?\s*\d{10,12}', "regex", "ИНН не указан", True, 1),
            ValidationRule(2, "tax", r'(?i)налогообложени', "regex", "Система налогообложения не указана", True, 1),
        ]
        
        result = validate_ticket(ticket_text, rules)
        
        self.assertFalse(result.is_valid)
        self.assertEqual(len(result.failed_rules), 2)
        self.assertEqual(len(result.error_messages), 2)

    def test_validate_ticket_inactive_rules_skipped(self):
        """Test that inactive rules are skipped."""
        ticket_text = "ИНН: 1234567890"
        
        rules = [
            ValidationRule(1, "inn", r'(?i)ИНН\s*[:\-]?\s*\d{10,12}', "regex", "ИНН не указан", True, 1),
            ValidationRule(2, "tax", r'(?i)налогообложени', "regex", "Система налогообложения не указана", False, 1),  # Inactive
        ]
        
        result = validate_ticket(ticket_text, rules)
        
        # Should pass because inactive rule is skipped
        self.assertTrue(result.is_valid)
        self.assertNotIn("tax", result.validation_details)

    def test_validate_ticket_priority_ordering(self):
        """Test that rules are evaluated by priority."""
        ticket_text = "Test"
        
        rules = [
            ValidationRule(1, "low", r'missing', "regex", "Low priority error", True, 1),
            ValidationRule(2, "high", r'missing', "regex", "High priority error", True, 10),
            ValidationRule(3, "medium", r'missing', "regex", "Medium priority error", True, 5),
        ]
        
        result = validate_ticket(ticket_text, rules)
        
        # All should fail, but order in error_messages should be by priority
        self.assertEqual(result.error_messages[0], "High priority error")  # Priority 10
        self.assertEqual(result.error_messages[1], "Medium priority error")  # Priority 5
        self.assertEqual(result.error_messages[2], "Low priority error")  # Priority 1

    def test_validate_ticket_required_field_type(self):
        """Test validation with required_field rule type."""
        ticket_text = "Система налогообложения: УСН"
        
        rules = [
            ValidationRule(1, "tax_field", "Система налогообложения", "required_field", "Поле не найдено", True, 1),
        ]
        
        result = validate_ticket(ticket_text, rules)
        self.assertTrue(result.is_valid)

    def test_validate_ticket_format_type(self):
        """Test validation with format rule type."""
        ticket_text = "Email: test@example.com"
        
        rules = [
            ValidationRule(1, "email_format", "email", "format", "Неверный формат email", True, 1),
        ]
        
        result = validate_ticket(ticket_text, rules)
        self.assertTrue(result.is_valid)

    def test_validate_ticket_length_type(self):
        """Test validation with length rule type."""
        ticket_text = "This is a ticket with sufficient length for testing"
        
        rules = [
            ValidationRule(1, "min_length", "min:10", "length", "Слишком короткая заявка", True, 1),
        ]
        
        result = validate_ticket(ticket_text, rules)
        self.assertTrue(result.is_valid)

    def test_validate_ticket_empty_rules(self):
        """Test validation with empty rules list."""
        ticket_text = "Any text"
        rules = []
        
        result = validate_ticket(ticket_text, rules)
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.failed_rules), 0)

    def test_validate_ticket_unknown_rule_type(self):
        """Test validation with unknown rule type."""
        ticket_text = "Test"
        
        rules = [
            ValidationRule(1, "unknown", "pattern", "unknown_type", "Error", True, 1),
        ]
        
        result = validate_ticket(ticket_text, rules)
        
        # Unknown rule type should be skipped, validation should pass
        self.assertTrue(result.is_valid)

    def test_validate_ticket_complex_real_world(self):
        """Test validation with complex real-world ticket."""
        ticket_text = """
        Заявка на установку оборудования
        
        Наименование организации: ООО "Ромашка"
        ИНН: 7701234567
        Система налогообложения: УСН
        
        Контактное лицо: Иванов Иван Иванович
        Контактный телефон: +7 (999) 123-45-67
        Email: ivanov@romashka.ru
        
        Адрес установки: г. Москва, ул. Тверская, д. 10, оф. 205
        Дата установки: 25.01.2026
        
        Тип оборудования: Касса АТОЛ 91Ф
        Код активации: ABC123XYZ789
        
        Дополнительная информация: установка в торговом зале
        """
        
        rules = [
            ValidationRule(1, "inn", r'(?i)ИНН\s*[:\-]?\s*\d{10,12}', "regex", "ИНН не указан", True, 10),
            ValidationRule(2, "tax", r'(?i)налогообложени', "regex", "Система налогообложения не указана", True, 9),
            ValidationRule(3, "phone", r'\+?[78][\s\-]?\(?\d{3}\)?', "regex", "Телефон не указан", True, 8),
            ValidationRule(4, "address", r'(?i)адрес.*установки', "regex", "Адрес не указан", True, 7),
            ValidationRule(5, "activation", r'(?i)код\s+активации', "regex", "Код активации не указан", True, 6),
            ValidationRule(6, "min_len", "min:50", "length", "Заявка слишком короткая", True, 5),
        ]
        
        result = validate_ticket(ticket_text, rules)
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.failed_rules), 0)
        # Check that all rules were evaluated
        self.assertEqual(len(result.validation_details), 6)


class TestTicketTypeDetection(unittest.TestCase):
    """Tests for ticket type detection functionality."""
    
    def test_detect_installation_ticket(self):
        """Test detection of installation ticket type."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка", "монтаж", "подключение"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт", "поломка"]),
            TicketType(3, "ТО", "Maintenance", ["обслуживание", "профилактика"])
        ]
        
        ticket_text = "Заявка на установку нового оборудования и подключение"
        detected, _ = detect_ticket_type(ticket_text, ticket_types)
        
        self.assertIsNotNone(detected)
        self.assertEqual(detected.id, 1)
        self.assertEqual(detected.type_name, "Установка")
    
    def test_detect_repair_ticket(self):
        """Test detection of repair ticket type."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка", "монтаж"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт", "поломка", "не работает"]),
        ]
        
        ticket_text = "Касса сломалась, нужен ремонт, не работает принтер"
        detected, _ = detect_ticket_type(ticket_text, ticket_types)
        
        self.assertIsNotNone(detected)
        self.assertEqual(detected.id, 2)
        self.assertEqual(detected.type_name, "Ремонт")
    
    def test_no_ticket_type_detected(self):
        """Test when no ticket type can be detected."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка", "монтаж"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт", "поломка"]),
        ]
        
        ticket_text = "Какой-то текст без ключевых слов"
        detected, _ = detect_ticket_type(ticket_text, ticket_types)
        
        self.assertIsNone(detected)
    
    def test_empty_ticket_types_list(self):
        """Test detection with empty ticket types list."""
        ticket_text = "Заявка на установку"
        detected, _ = detect_ticket_type(ticket_text, [])
        
        self.assertIsNone(detected)
    
    def test_inactive_ticket_type_ignored(self):
        """Test that inactive ticket types are ignored."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка"], active=False),
            TicketType(2, "Ремонт", "Repair", ["ремонт"]),
        ]
        
        ticket_text = "Заявка на установку оборудования"
        detected, _ = detect_ticket_type(ticket_text, ticket_types)
        
        # Should not detect type 1 (inactive)
        self.assertIsNone(detected)
    
    def test_case_insensitive_detection(self):
        """Test that detection is case-insensitive."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["УстановкА", "МОНТАЖ"]),
        ]
        
        ticket_text = "заявка на установку и монтаж"
        detected, _ = detect_ticket_type(ticket_text, ticket_types)
        
        self.assertIsNotNone(detected)
        self.assertEqual(detected.id, 1)
    
    def test_multiple_keyword_matches(self):
        """Test scoring with multiple keyword matches."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт", "поломка", "сломалось"]),
        ]
        
        # This text has more repair keywords
        ticket_text = "Касса сломалась, нужен ремонт поломки"
        detected, _ = detect_ticket_type(ticket_text, ticket_types)
        
        self.assertEqual(detected.id, 2)
    
    def test_ticket_with_detected_type(self):
        """Test validate_ticket with detected ticket type."""
        ticket_type = TicketType(1, "Установка", "Installation", ["установка"])
        
        ticket_text = "ИНН: 1234567890"
        rules = [
            ValidationRule(1, "inn", r'(?i)ИНН\s*[:\-]?\s*\d{10,12}', "regex", "ИНН не указан", True, 1)
        ]
        
        result = validate_ticket(ticket_text, rules, detected_ticket_type=ticket_type)
        
        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.detected_ticket_type)
        self.assertEqual(result.detected_ticket_type.id, 1)


class TestDetectionDebugMode(unittest.TestCase):
    """Tests for ticket type detection debug mode functionality."""
    
    def test_debug_mode_returns_debug_info(self):
        """Test that debug mode returns DetectionDebugInfo object."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установку", "монтаж"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт", "поломка"]),
        ]
        
        ticket_text = "Заявка на установку нового оборудования"
        detected, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        self.assertIsNotNone(debug_info)
        self.assertIsInstance(debug_info, DetectionDebugInfo)
        self.assertIsNotNone(detected)
        self.assertEqual(detected.id, 1)
        self.assertEqual(debug_info.detected_type.id, 1)
    
    def test_debug_info_contains_all_scores(self):
        """Test that debug info contains scores for all ticket types."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установку", "монтаж"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт", "поломка"]),
            TicketType(3, "ТО", "Maintenance", ["обслуживание"]),
        ]
        
        ticket_text = "Заявка на установку"
        _, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        self.assertEqual(len(debug_info.all_scores), 3)
        self.assertEqual(debug_info.total_types_evaluated, 3)
    
    def test_debug_info_keyword_matches(self):
        """Test that debug info shows which keywords matched."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установку", "монтаж", "подключение"]),
        ]
        
        ticket_text = "Заявка на установку и подключение оборудования"
        _, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        score_info = debug_info.all_scores[0]
        self.assertEqual(score_info.matched_keywords_count, 2)  # установку and подключение
        self.assertEqual(score_info.total_keywords_count, 3)
        self.assertEqual(len(score_info.keyword_matches), 2)
        
        # Check that the matched keywords are correct
        matched_keywords = [m.keyword.lower() for m in score_info.keyword_matches]
        self.assertIn("установку", matched_keywords)
        self.assertIn("подключение", matched_keywords)
    
    def test_debug_info_keyword_count(self):
        """Test that debug info counts keyword occurrences."""
        ticket_types = [
            TicketType(1, "Ремонт", "Repair", ["ремонт"]),
        ]
        
        ticket_text = "Нужен ремонт кассы, ремонт принтера и ремонт монитора"
        _, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        score_info = debug_info.all_scores[0]
        # "ремонт" appears 3 times
        self.assertEqual(score_info.keyword_matches[0].count, 3)
        self.assertEqual(score_info.total_score, 3.0)
    
    def test_debug_info_with_custom_weights(self):
        """Test detection with custom keyword weights."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка", "монтаж"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт"]),
        ]
        
        # Without weights, "установка" (1 occurrence) vs "ремонт" (1 occurrence) ties, first wins
        # With higher weight on "ремонт", it should win
        ticket_text = "Установка и ремонт"
        
        detected_weighted, debug_info = detect_ticket_type(
            ticket_text, ticket_types, 
            debug=True, 
            keyword_weights={"ремонт": 5.0}
        )
        
        # With weight 5.0 on "ремонт", type 2 should win
        self.assertEqual(detected_weighted.id, 2)
        
        # Check the scores
        repair_score = next(s for s in debug_info.all_scores if s.ticket_type.id == 2)
        self.assertEqual(repair_score.total_score, 5.0)  # 1 * 5.0
        
        install_score = next(s for s in debug_info.all_scores if s.ticket_type.id == 1)
        self.assertEqual(install_score.total_score, 1.0)  # 1 * 1.0 (default weight)
    
    def test_debug_info_match_percentage(self):
        """Test match percentage calculation."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка", "монтаж", "подключение", "настройка"]),
        ]
        
        ticket_text = "Установка и подключение"
        _, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        score_info = debug_info.all_scores[0]
        # 2 out of 4 keywords matched = 50%
        self.assertEqual(score_info.match_percentage, 50.0)
    
    def test_debug_info_text_preview(self):
        """Test that debug info includes text preview."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка"]),
        ]
        
        ticket_text = "Заявка на установку оборудования"
        _, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        self.assertTrue(debug_info.ticket_text_preview.startswith("Заявка"))
    
    def test_debug_info_get_summary(self):
        """Test that get_summary returns a formatted string."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установку", "монтаж"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт"]),
        ]
        
        ticket_text = "Заявка на установку"
        _, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        summary = debug_info.get_summary()
        
        self.assertIn("TICKET TYPE DETECTION DEBUG INFO", summary)
        self.assertIn("DETECTED TYPE: Установка", summary)
        self.assertIn("установку", summary)
        self.assertIn("SCORES BY TICKET TYPE", summary)
    
    def test_debug_mode_no_match(self):
        """Test debug mode when no ticket type matches."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка"]),
        ]
        
        ticket_text = "Какой-то текст без ключевых слов"
        detected, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        self.assertIsNone(detected)
        self.assertIsNone(debug_info.detected_type)
        self.assertEqual(debug_info.all_scores[0].total_score, 0.0)
        self.assertEqual(debug_info.all_scores[0].matched_keywords_count, 0)
    
    def test_debug_mode_inactive_types_excluded(self):
        """Test that inactive types are not counted in total_types_evaluated."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка"], active=True),
            TicketType(2, "Ремонт", "Repair", ["ремонт"], active=False),
        ]
        
        ticket_text = "Установка"
        _, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        self.assertEqual(debug_info.total_types_evaluated, 1)
        self.assertEqual(len(debug_info.all_scores), 1)
    
    def test_debug_mode_empty_types(self):
        """Test debug mode with empty ticket types list."""
        ticket_text = "Заявка"
        detected, debug_info = detect_ticket_type(ticket_text, [], debug=True)
        
        self.assertIsNone(detected)
        self.assertIsNone(debug_info.detected_type)
        self.assertEqual(len(debug_info.all_scores), 0)
        self.assertEqual(debug_info.total_types_evaluated, 0)
    
    def test_keyword_match_weighted_score(self):
        """Test KeywordMatch weighted_score property."""
        match = KeywordMatch(keyword="test", count=3, weight=2.0)
        self.assertEqual(match.weighted_score, 6.0)
    
    def test_without_debug_returns_none(self):
        """Test that without debug mode, second return value is None."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка"]),
        ]
        
        ticket_text = "Установка"
        detected, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=False)
        
        self.assertIsNotNone(detected)
        self.assertIsNone(debug_info)


if __name__ == '__main__':
    unittest.main()
