"""
Unit tests for ticket validator module.

Tests cover:
- Validation rule types (regex and fias_check)
- ValidationRule and ValidationResult classes
- Ticket type detection
- Edge cases and error handling
- All validator functions
- FIAS address validation (fias_check rule type)
"""

import unittest
from unittest.mock import patch, MagicMock
from src.sbs_helper_telegram_bot.ticket_validator.validators import (
    ValidationRule,
    ValidationResult,
    RuleType,
    TicketType,
    KeywordMatch,
    TicketTypeScore,
    DetectionDebugInfo,
    validate_regex,
    validate_fias_address,
    validate_ticket,
    detect_ticket_type
)
from src.sbs_helper_telegram_bot.ticket_validator.fias_providers import (
    BaseFIASProvider,
    FIASValidationResult,
    DaDataFIASProvider,
    get_fias_provider,
    reset_fias_provider,
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
            rule_type=RuleType.REGEX,
            error_message="Error",
            active=False,
            priority=0
        )
        
        self.assertEqual(rule.rule_type, RuleType.REGEX)
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
        ]
        
        result = validate_ticket(ticket_text, rules)
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.failed_rules), 0)
        # Check that all rules were evaluated
        self.assertEqual(len(result.validation_details), 5)


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
    
    def test_negative_keywords_lower_score(self):
        """Test that negative keywords (with minus prefix) lower the score."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка", "монтаж", "-ремонт"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт", "поломка"]),
        ]
        
        # Text contains both "установка" and "ремонт"
        # For type 1: +1 (установка) -1 (ремонт negative) = 0
        # For type 2: +1 (ремонт) = 1
        ticket_text = "Установка после ремонта"
        detected, _ = detect_ticket_type(ticket_text, ticket_types)
        
        # Type 2 should win because type 1's score is reduced by negative keyword
        self.assertIsNotNone(detected)
        self.assertEqual(detected.id, 2)
    
    def test_negative_keywords_with_weights(self):
        """Test negative keywords work with custom weights."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка", "-ремонт"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт"]),
        ]
        
        ticket_text = "Установка после ремонта"
        
        # With high weight on negative keyword, type 1 should have negative score
        detected, debug_info = detect_ticket_type(
            ticket_text, ticket_types, 
            debug=True,
            keyword_weights={"-ремонт": 3.0}
        )
        
        install_score = next(s for s in debug_info.all_scores if s.ticket_type.id == 1)
        # установка: +1, -ремонт with weight 3.0: -3 = -2 total
        self.assertEqual(install_score.total_score, -2.0)
        
        # Type 2 should win with positive score
        self.assertEqual(detected.id, 2)
    
    def test_negative_keywords_debug_info(self):
        """Test that debug info correctly shows negative keywords."""
        ticket_types = [
            TicketType(1, "Test", "Test", ["positive", "-negative"]),
        ]
        
        ticket_text = "This has positive and negative words"
        _, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        score_info = debug_info.all_scores[0]
        matches = {m.keyword: m for m in score_info.keyword_matches}
        
        # Check positive keyword
        self.assertIn("positive", matches)
        self.assertFalse(matches["positive"].is_negative)
        self.assertEqual(matches["positive"].weighted_score, 1.0)
        
        # Check negative keyword
        self.assertIn("negative", matches)
        self.assertTrue(matches["negative"].is_negative)
        self.assertEqual(matches["negative"].weighted_score, -1.0)
    
    def test_negative_keywords_not_counted_in_matched(self):
        """Test that negative keywords don't count towards matched_keywords_count."""
        ticket_types = [
            TicketType(1, "Test", "Test", ["keyword1", "-keyword2", "keyword3"]),
        ]
        
        # Contains keyword1 and keyword2 (negative)
        ticket_text = "This has keyword1 and keyword2"
        _, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        score_info = debug_info.all_scores[0]
        # Only positive keywords count towards matched_keywords_count
        self.assertEqual(score_info.matched_keywords_count, 1)  # Only keyword1
        self.assertEqual(score_info.total_keywords_count, 3)
    
    def test_multiple_negative_keywords(self):
        """Test ticket type with multiple negative keywords."""
        ticket_types = [
            TicketType(1, "Установка", "Installation", ["установка", "монтаж", "-ремонт", "-замена"]),
            TicketType(2, "Ремонт", "Repair", ["ремонт"]),
        ]
        
        # Text has "установка" (+1) but also "ремонт" (-1) and "замена" (-1) = -1 total
        ticket_text = "Установка, а не ремонт или замена оборудования"
        detected, debug_info = detect_ticket_type(ticket_text, ticket_types, debug=True)
        
        install_score = next(s for s in debug_info.all_scores if s.ticket_type.id == 1)
        # установка: +1, -ремонт: -1, -замена: -1 = -1 total
        self.assertEqual(install_score.total_score, -1.0)
        
        # Type 2 should win with positive score
        self.assertEqual(detected.id, 2)


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


# ===== FIAS VALIDATION TESTS =====


class TestFIASValidationResult(unittest.TestCase):
    """Tests for FIASValidationResult data class."""

    def test_valid_result(self):
        result = FIASValidationResult(
            is_valid=True,
            address_query="Москва, ул Льва Толстого 16",
            suggested_address="г Москва, ул Льва Толстого, д 16",
            suggestions_count=1,
            provider_name="dadata",
            fias_id="abc-123",
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.suggestions_count, 1)
        self.assertIsNotNone(result.suggested_address)

    def test_invalid_result(self):
        result = FIASValidationResult(
            is_valid=False,
            address_query="абракадабра 999",
            error_message="Адрес не найден",
            provider_name="dadata",
        )
        self.assertFalse(result.is_valid)
        self.assertIsNotNone(result.error_message)


class TestDaDataFIASProvider(unittest.TestCase):
    """Tests for DaDataFIASProvider."""

    def test_is_configured_with_key(self):
        provider = DaDataFIASProvider(api_key="test-key")
        self.assertTrue(provider.is_configured())

    def test_is_not_configured_without_key(self):
        provider = DaDataFIASProvider(api_key="")
        self.assertFalse(provider.is_configured())

    def test_provider_name(self):
        provider = DaDataFIASProvider(api_key="x")
        self.assertEqual(provider.provider_name, "dadata")

    def test_validate_address_no_key_returns_valid(self):
        """When API key is missing, fail-open: result should be valid."""
        provider = DaDataFIASProvider(api_key="")
        result = provider.validate_address("Москва")
        self.assertTrue(result.is_valid)
        self.assertIn("не настроен", result.error_message)

    @patch("src.sbs_helper_telegram_bot.ticket_validator.fias_providers.requests.post")
    def test_validate_address_success_with_suggestions(self, mock_post):
        """API returns suggestions → valid."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "suggestions": [
                {
                    "value": "г Москва, ул Льва Толстого, д 16",
                    "data": {"fias_id": "abc", "fias_level": "8"},
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        provider = DaDataFIASProvider(api_key="test-key")
        result = provider.validate_address("Москва Льва Толстого 16")

        self.assertTrue(result.is_valid)
        self.assertEqual(result.suggestions_count, 1)
        self.assertEqual(result.suggested_address, "г Москва, ул Льва Толстого, д 16")
        self.assertEqual(result.fias_id, "abc")

    @patch("src.sbs_helper_telegram_bot.ticket_validator.fias_providers.requests.post")
    def test_validate_address_empty_suggestions(self, mock_post):
        """API returns empty suggestions → invalid."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"suggestions": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        provider = DaDataFIASProvider(api_key="test-key")
        result = provider.validate_address("абракадабра 999")

        self.assertFalse(result.is_valid)
        self.assertEqual(result.suggestions_count, 0)

    @patch("src.sbs_helper_telegram_bot.ticket_validator.fias_providers.requests.post")
    def test_validate_address_403_fail_open(self, mock_post):
        """403 → fail-open (valid=True)."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_post.return_value = mock_response

        provider = DaDataFIASProvider(api_key="test-key")
        result = provider.validate_address("Москва")

        self.assertTrue(result.is_valid)
        self.assertIn("403", result.error_message)

    @patch("src.sbs_helper_telegram_bot.ticket_validator.fias_providers.requests.post")
    def test_validate_address_429_fail_open(self, mock_post):
        """429 → fail-open (valid=True)."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_post.return_value = mock_response

        provider = DaDataFIASProvider(api_key="test-key")
        result = provider.validate_address("Москва")

        self.assertTrue(result.is_valid)
        self.assertIn("429", result.error_message)

    @patch("src.sbs_helper_telegram_bot.ticket_validator.fias_providers.requests.post")
    def test_validate_address_timeout_fail_open(self, mock_post):
        """Timeout → fail-open."""
        import requests as req
        mock_post.side_effect = req.exceptions.Timeout("timeout")

        provider = DaDataFIASProvider(api_key="test-key")
        result = provider.validate_address("Москва")

        self.assertTrue(result.is_valid)
        self.assertIn("Таймаут", result.error_message)

    @patch("src.sbs_helper_telegram_bot.ticket_validator.fias_providers.requests.post")
    def test_validate_address_network_error_fail_open(self, mock_post):
        """Network error → fail-open."""
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("refused")

        provider = DaDataFIASProvider(api_key="test-key")
        result = provider.validate_address("Москва")

        self.assertTrue(result.is_valid)
        self.assertIn("Ошибка запроса", result.error_message)


class TestGetFIASProvider(unittest.TestCase):
    """Tests for get_fias_provider factory function."""

    def setUp(self):
        reset_fias_provider()

    def tearDown(self):
        reset_fias_provider()

    def test_default_provider_is_dadata(self):
        provider = get_fias_provider()
        self.assertIsInstance(provider, DaDataFIASProvider)

    def test_explicit_provider_name(self):
        provider = get_fias_provider("dadata")
        self.assertIsInstance(provider, DaDataFIASProvider)

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            get_fias_provider("unknown_provider")

    def test_singleton_caching(self):
        p1 = get_fias_provider("dadata")
        p2 = get_fias_provider("dadata")
        self.assertIs(p1, p2)


class TestValidateFIASAddress(unittest.TestCase):
    """Tests for validate_fias_address function in validators.py."""

    SAMPLE_TICKET = (
        "Заявка на установку POS-терминала\n"
        "Адрес установки POS-терминала: г Москва, ул Льва Толстого, д 16\n"
        "Тип пакета: Стандарт"
    )
    PATTERN = r"Адрес установки POS-терминала:\s*([\s\S]*?)(?=Тип пакета:|$)"

    def setUp(self):
        reset_fias_provider()

    def tearDown(self):
        reset_fias_provider()

    @patch("src.sbs_helper_telegram_bot.ticket_validator.fias_providers.requests.post")
    def test_fias_check_passes_when_address_found(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "suggestions": [{"value": "г Москва, ул Льва Толстого, д 16", "data": {}}]
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # Force provider to have a key
        with patch.dict("os.environ", {"DADATA_API_KEY": "test-key"}):
            reset_fias_provider()
            result = validate_fias_address(self.SAMPLE_TICKET, self.PATTERN)
        self.assertTrue(result)

    @patch("src.sbs_helper_telegram_bot.ticket_validator.fias_providers.requests.post")
    def test_fias_check_fails_when_address_not_found(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"suggestions": []}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with patch.dict("os.environ", {"DADATA_API_KEY": "test-key"}):
            reset_fias_provider()
            result = validate_fias_address(self.SAMPLE_TICKET, self.PATTERN)
        self.assertFalse(result)

    def test_fias_check_fails_when_address_not_in_text(self):
        """If the pattern doesn't match, the rule fails."""
        ticket_without_address = "Заявка без адреса\nТип пакета: Стандарт"
        result = validate_fias_address(ticket_without_address, self.PATTERN)
        self.assertFalse(result)

    def test_fias_check_fails_on_empty_address(self):
        """If the capture group is empty/whitespace, the rule fails."""
        ticket_empty_address = (
            "Адрес установки POS-терминала:   \n"
            "Тип пакета: Стандарт"
        )
        result = validate_fias_address(ticket_empty_address, self.PATTERN)
        self.assertFalse(result)

    def test_fias_check_with_invalid_regex(self):
        """Invalid regex → fails (returns False)."""
        result = validate_fias_address(self.SAMPLE_TICKET, "[invalid(")
        self.assertFalse(result)


class TestFIASCheckRuleType(unittest.TestCase):
    """Test that fias_check integrates correctly with validate_ticket."""

    def setUp(self):
        reset_fias_provider()

    def tearDown(self):
        reset_fias_provider()

    def test_rule_type_enum_has_fias_check(self):
        self.assertEqual(RuleType.FIAS_CHECK.value, "fias_check")

    def test_validation_rule_accepts_fias_check(self):
        rule = ValidationRule(
            id=99,
            rule_name="FIAS Address Check",
            pattern=r"Адрес установки POS-терминала:\s*([\s\S]*?)(?=Тип пакета:|$)",
            rule_type="fias_check",
            error_message="Адрес не найден в ФИАС",
        )
        self.assertEqual(rule.rule_type, RuleType.FIAS_CHECK)

    @patch("src.sbs_helper_telegram_bot.ticket_validator.validators.validate_fias_address")
    def test_validate_ticket_dispatches_fias_check(self, mock_fias):
        """validate_ticket should call validate_fias_address for fias_check rules."""
        mock_fias.return_value = True

        rules = [
            ValidationRule(
                id=99,
                rule_name="FIAS check",
                pattern=r"Адрес:\s*(.*)",
                rule_type="fias_check",
                error_message="Адрес не найден",
            )
        ]
        ticket = "Адрес: Москва"
        result = validate_ticket(ticket, rules)

        mock_fias.assert_called_once_with(ticket, r"Адрес:\s*(.*)")
        self.assertTrue(result.is_valid)

    @patch("src.sbs_helper_telegram_bot.ticket_validator.validators.validate_fias_address")
    def test_validate_ticket_fias_check_failure(self, mock_fias):
        """When fias_check fails, it should appear in failed_rules."""
        mock_fias.return_value = False

        rules = [
            ValidationRule(
                id=99,
                rule_name="FIAS check",
                pattern=r"Адрес:\s*(.*)",
                rule_type="fias_check",
                error_message="Адрес не найден в ФИАС",
            )
        ]
        result = validate_ticket("Адрес: xyzxyz", rules)

        self.assertFalse(result.is_valid)
        self.assertIn("FIAS check", result.failed_rules)
        self.assertIn("Адрес не найден в ФИАС", result.error_messages)


if __name__ == '__main__':
    unittest.main()
