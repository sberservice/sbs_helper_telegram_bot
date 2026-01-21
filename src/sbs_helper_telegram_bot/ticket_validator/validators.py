"""
Validation Logic Module

Contains validation rules, validators, and result classes for ticket validation.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum


class RuleType(Enum):
    """Validation rule types"""
    REGEX = "regex"
    REQUIRED_FIELD = "required_field"
    FORMAT = "format"
    LENGTH = "length"
    CUSTOM = "custom"


@dataclass
class TicketType:
    """Represents a ticket type/template"""
    id: int
    type_name: str
    description: str
    detection_keywords: List[str]
    active: bool = True


@dataclass
class ValidationRule:
    """Represents a single validation rule"""
    id: int
    rule_name: str
    pattern: str
    rule_type: str
    error_message: str
    active: bool = True
    priority: int = 0
    
    def __post_init__(self):
        """Validate and convert rule_type"""
        if isinstance(self.rule_type, str):
            try:
                self.rule_type = RuleType(self.rule_type)
            except ValueError:
                # Keep as string if not a valid enum value
                pass


@dataclass
class ValidationResult:
    """Result of ticket validation"""
    is_valid: bool
    failed_rules: List[str] = field(default_factory=list)
    error_messages: List[str] = field(default_factory=list)
    validation_details: Dict[str, Any] = field(default_factory=dict)
    detected_ticket_type: Optional[TicketType] = None


def validate_regex(ticket_text: str, pattern: str) -> bool:
    """
    Validate ticket text against a regex pattern.
    
    Args:
        ticket_text: The ticket text to validate
        pattern: Regex pattern to match
        
    Returns:
        True if pattern is found in text, False otherwise
    """
    try:
        return bool(re.search(pattern, ticket_text, re.IGNORECASE | re.MULTILINE))
    except re.error:
        # Invalid regex pattern
        return False


def validate_required_field(ticket_text: str, field_name: str) -> bool:
    """
    Check if a required field is present in the ticket.
    
    Args:
        ticket_text: The ticket text to validate
        field_name: Name of the required field
        
    Returns:
        True if field is found, False otherwise
    """
    # Search for "field_name:" or "field_name -" patterns
    pattern = rf"(?i){re.escape(field_name)}\s*[:\-]"
    return bool(re.search(pattern, ticket_text))


def validate_format(ticket_text: str, format_type: str) -> bool:
    """
    Validate specific format types (phone, email, date, etc.)
    
    Args:
        ticket_text: The ticket text to validate
        format_type: Type of format to validate (phone, email, date, inn)
        
    Returns:
        True if format is valid, False otherwise
    """
    format_patterns = {
        'phone': r'\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'date': r'\d{2}[./\-]\d{2}[./\-]\d{4}',
        'inn_10': r'\b\d{10}\b',
        'inn_12': r'\b\d{12}\b',
        'inn': r'\b\d{10,12}\b',
    }
    
    pattern = format_patterns.get(format_type.lower())
    if not pattern:
        return False
        
    return bool(re.search(pattern, ticket_text))


def validate_length(ticket_text: str, length_spec: str) -> bool:
    """
    Validate text length against specification.
    
    Args:
        ticket_text: The ticket text to validate
        length_spec: Length specification like "min:10", "max:1000", or "min:10,max:1000"
        
    Returns:
        True if length is valid, False otherwise
    """
    text_length = len(ticket_text)
    
    # Parse length specification
    specs = {}
    for spec in length_spec.split(','):
        spec = spec.strip()
        if ':' in spec:
            key, value = spec.split(':', 1)
            try:
                specs[key.strip().lower()] = int(value.strip())
            except ValueError:
                continue
    
    # Check min length
    if 'min' in specs and text_length < specs['min']:
        return False
    
    # Check max length
    if 'max' in specs and text_length > specs['max']:
        return False
    
    return True


def detect_ticket_type(ticket_text: str, ticket_types: List[TicketType]) -> Optional[TicketType]:
    """
    Detect ticket type from text based on keywords.
    
    Args:
        ticket_text: The ticket text to analyze
        ticket_types: List of available ticket types
        
    Returns:
        TicketType that best matches the text, or None if no match
    """
    if not ticket_types:
        return None
    
    # Score each ticket type based on keyword matches
    scores = {}
    ticket_text_lower = ticket_text.lower()
    
    for ticket_type in ticket_types:
        if not ticket_type.active:
            continue
            
        score = 0
        for keyword in ticket_type.detection_keywords:
            keyword_lower = keyword.lower()
            # Count occurrences of each keyword
            count = ticket_text_lower.count(keyword_lower)
            score += count
        
        if score > 0:
            scores[ticket_type.id] = (score, ticket_type)
    
    # Return ticket type with highest score
    if scores:
        best_match = max(scores.values(), key=lambda x: x[0])
        return best_match[1]
    
    return None


def validate_ticket(ticket_text: str, rules: List[ValidationRule], 
                   detected_ticket_type: Optional[TicketType] = None) -> ValidationResult:
    """
    Main validation function that applies all rules to a ticket.
    
    Args:
        ticket_text: The ticket text to validate
        rules: List of validation rules to apply
        detected_ticket_type: Optional detected ticket type
        
    Returns:
        ValidationResult with validation status and details
    """
    failed_rules = []
    error_messages = []
    validation_details = {}
    
    # Sort rules by priority (higher priority first)
    sorted_rules = sorted(rules, key=lambda r: r.priority, reverse=True)
    
    for rule in sorted_rules:
        if not rule.active:
            continue
            
        is_valid = False
        rule_type_value = rule.rule_type.value if isinstance(rule.rule_type, RuleType) else rule.rule_type
        
        try:
            if rule_type_value == 'regex':
                is_valid = validate_regex(ticket_text, rule.pattern)
            elif rule_type_value == 'required_field':
                is_valid = validate_required_field(ticket_text, rule.pattern)
            elif rule_type_value == 'format':
                is_valid = validate_format(ticket_text, rule.pattern)
            elif rule_type_value == 'length':
                is_valid = validate_length(ticket_text, rule.pattern)
            elif rule_type_value == 'custom':
                # Custom validation could be extended in the future
                is_valid = True
            else:
                # Unknown rule type, skip it
                continue
                
        except Exception as e:
            # Log error but continue with other rules
            validation_details[rule.rule_name] = f"Error: {str(e)}"
            continue
        
        validation_details[rule.rule_name] = is_valid
        
        if not is_valid:
            failed_rules.append(rule.rule_name)
            error_messages.append(rule.error_message)
    
    return ValidationResult(
        is_valid=len(failed_rules) == 0,
        failed_rules=failed_rules,
        error_messages=error_messages,
        validation_details=validation_details,
        detected_ticket_type=detected_ticket_type
    )
