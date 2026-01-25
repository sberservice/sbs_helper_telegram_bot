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
    REGEX_NOT_MATCH = "regex_not_match"
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
class KeywordMatch:
    """Represents a keyword match with its details"""
    keyword: str
    count: int
    weight: float = 1.0
    is_negative: bool = False
    
    @property
    def weighted_score(self) -> float:
        score = self.count * self.weight
        return -score if self.is_negative else score


@dataclass
class TicketTypeScore:
    """Score details for a ticket type during detection"""
    ticket_type: TicketType
    total_score: float
    keyword_matches: List[KeywordMatch] = field(default_factory=list)
    matched_keywords_count: int = 0
    total_keywords_count: int = 0
    
    @property
    def match_percentage(self) -> float:
        """Percentage of keywords that matched"""
        if self.total_keywords_count == 0:
            return 0.0
        return (self.matched_keywords_count / self.total_keywords_count) * 100


@dataclass
class DetectionDebugInfo:
    """Debug information for ticket type detection"""
    detected_type: Optional[TicketType]
    all_scores: List[TicketTypeScore] = field(default_factory=list)
    ticket_text_preview: str = ""
    total_types_evaluated: int = 0
    
    def get_summary(self) -> str:
        """Generate a human-readable summary of the detection process"""
        lines = []
        lines.append("=" * 60)
        lines.append("TICKET TYPE DETECTION DEBUG INFO")
        lines.append("=" * 60)
        lines.append(f"Text preview: {self.ticket_text_preview[:100]}...")
        lines.append(f"Total ticket types evaluated: {self.total_types_evaluated}")
        lines.append("")
        
        if self.detected_type:
            lines.append(f"✅ DETECTED TYPE: {self.detected_type.type_name}")
            lines.append(f"   Description: {self.detected_type.description}")
        else:
            lines.append("❌ NO TYPE DETECTED")
        
        lines.append("")
        lines.append("-" * 60)
        lines.append("SCORES BY TICKET TYPE (sorted by score):")
        lines.append("-" * 60)
        
        # Sort by total score descending
        sorted_scores = sorted(self.all_scores, key=lambda x: x.total_score, reverse=True)
        
        for score_info in sorted_scores:
            lines.append("")
            lines.append(f"📋 {score_info.ticket_type.type_name}")
            lines.append(f"   Total Score: {score_info.total_score}")
            lines.append(f"   Keywords matched: {score_info.matched_keywords_count}/{score_info.total_keywords_count} ({score_info.match_percentage:.1f}%)")
            
            if score_info.keyword_matches:
                lines.append("   Matched keywords:")
                for match in score_info.keyword_matches:
                    sign = "-" if match.is_negative else "+"
                    lines.append(f"     {sign} '{match.keyword}': found {match.count}x (weight: {match.weight}, score: {match.weighted_score})")
            else:
                lines.append("   No keywords matched")
        
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


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


def validate_regex_not_match(ticket_text: str, pattern: str) -> bool:
    """
    Validate ticket text against a regex pattern (negated match).
    
    Args:
        ticket_text: The ticket text to validate
        pattern: Regex pattern that should NOT match
        
    Returns:
        True if pattern is NOT found in text, False if pattern matches
    """
    try:
        return not bool(re.search(pattern, ticket_text, re.IGNORECASE | re.MULTILINE))
    except re.error:
        # Invalid regex pattern - treat as not matching
        return True


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


def detect_ticket_type(
    ticket_text: str, 
    ticket_types: List[TicketType],
    debug: bool = False,
    keyword_weights: Optional[Dict[str, float]] = None
) -> tuple[Optional[TicketType], Optional[DetectionDebugInfo]]:
    """
    Detect ticket type from text based on keywords.
    
    Args:
        ticket_text: The ticket text to analyze
        ticket_types: List of available ticket types
        debug: If True, return detailed debug information
        keyword_weights: Optional dict mapping keywords to custom weights (default weight is 1.0)
        
    Returns:
        Tuple of (TicketType that best matches the text or None, DetectionDebugInfo if debug=True else None)
    """
    if not ticket_types:
        if debug:
            return None, DetectionDebugInfo(
                detected_type=None,
                ticket_text_preview=ticket_text[:200] if ticket_text else "",
                total_types_evaluated=0
            )
        return None, None
    
    keyword_weights = keyword_weights or {}
    
    # Score each ticket type based on keyword matches
    scores = {}
    all_scores_debug: List[TicketTypeScore] = []
    ticket_text_lower = ticket_text.lower()
    active_types_count = 0
    
    for ticket_type in ticket_types:
        if not ticket_type.active:
            continue
        
        active_types_count += 1
        score = 0.0
        keyword_matches: List[KeywordMatch] = []
        matched_count = 0
        total_keywords = len(ticket_type.detection_keywords)
        
        for keyword in ticket_type.detection_keywords:
            # Check if keyword is negative (starts with minus sign)
            is_negative = keyword.startswith('-')
            # Remove minus sign for matching
            keyword_to_match = keyword[1:] if is_negative else keyword
            keyword_lower = keyword_to_match.lower()
            
            # Count occurrences of each keyword
            count = ticket_text_lower.count(keyword_lower)
            
            # Get weight for this keyword (default 1.0)
            # For negative keywords, use the original keyword (with minus) as the key
            weight_key = keyword.lower() if is_negative else keyword_lower
            weight = keyword_weights.get(weight_key, 1.0)
            
            # Calculate score (negative for negative keywords)
            weighted_score = count * weight
            if is_negative:
                weighted_score = -weighted_score
            score += weighted_score
            
            if count > 0:
                # Only count positive keywords towards matched_count
                if not is_negative:
                    matched_count += 1
                if debug:
                    keyword_matches.append(KeywordMatch(
                        keyword=keyword_to_match,
                        count=count,
                        weight=weight,
                        is_negative=is_negative
                    ))
        
        if score > 0:
            scores[ticket_type.id] = (score, ticket_type)
        
        if debug:
            all_scores_debug.append(TicketTypeScore(
                ticket_type=ticket_type,
                total_score=score,
                keyword_matches=keyword_matches,
                matched_keywords_count=matched_count,
                total_keywords_count=total_keywords
            ))
    
    # Return ticket type with highest score
    detected_type = None
    if scores:
        best_match = max(scores.values(), key=lambda x: x[0])
        detected_type = best_match[1]
    
    if debug:
        debug_info = DetectionDebugInfo(
            detected_type=detected_type,
            all_scores=all_scores_debug,
            ticket_text_preview=ticket_text[:200] if ticket_text else "",
            total_types_evaluated=active_types_count
        )
        return detected_type, debug_info
    
    return detected_type, None


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
            elif rule_type_value == 'regex_not_match':
                is_valid = validate_regex_not_match(ticket_text, rule.pattern)
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
