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
    REGEX_FULLMATCH = "regex_fullmatch"
    REGEX_NOT_FULLMATCH = "regex_not_fullmatch"
    FIAS_CHECK = "fias_check"
    CUSTOM = "custom"


@dataclass
class TicketType:
    """Represents a ticket type/template"""
    id: int
    type_name: str
    description: str
    detection_keywords: List[str]
    active: bool = True
    keyword_weights: Dict[str, float] = field(default_factory=dict)
    
    def get_keyword_weight(self, keyword: str) -> float:
        """
        Get weight for a keyword.
        
        Args:
            keyword: The keyword to get weight for (case-insensitive)
            
        Returns:
            Weight for the keyword, defaults to 1.0 if not specified
        """
        return self.keyword_weights.get(keyword.lower(), 1.0)


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
    has_ambiguity: bool = False
    ambiguous_types: List[TicketType] = field(default_factory=list)
    
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
            if self.has_ambiguity:
                ambiguous_names = ", ".join([tt.type_name for tt in self.ambiguous_types])
                lines.append(f"⚠️ WARNING: Multiple types have the same score: {ambiguous_names}")
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
    passed_rules: List[str] = field(default_factory=list)
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
        return bool(re.search(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL))
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
        return not bool(re.search(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL))
    except re.error:
        # Invalid regex pattern - treat as not matching
        return True


def validate_regex_fullmatch(ticket_text: str, pattern: str) -> bool:
    """
    Validate ticket text against a regex pattern using fullmatch.
    
    Args:
        ticket_text: The ticket text to validate
        pattern: Regex pattern that must match the entire text
        
    Returns:
        True if pattern matches the entire text, False otherwise
    """
    try:
        return bool(re.fullmatch(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL))
    except re.error:
        # Invalid regex pattern
        return False


def validate_regex_not_fullmatch(ticket_text: str, pattern: str) -> bool:
    """
    Validate ticket text against a regex pattern using fullmatch (negated).
    
    Args:
        ticket_text: The ticket text to validate
        pattern: Regex pattern that must NOT fully match the entire text
        
    Returns:
        True if pattern does NOT match the entire text, False otherwise
    """
    try:
        return not bool(re.fullmatch(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL))
    except re.error:
        # Invalid regex pattern - treat as not matching
        return True


def validate_fias_address(ticket_text: str, pattern: str) -> bool:
    """Validate an address extracted from ticket text against the FIAS database.

    The *pattern* is a regex whose **first capture group** contains the address
    to check.  For example::

        Адрес установки POS-терминала:\\s*([\\s\\S]*?)(?=Тип пакета:|$)

    The extracted address is sent to the currently configured FIAS provider
    (see :mod:`fias_providers`).  The rule **passes** when the provider
    returns at least one suggestion.

    If the address cannot be extracted from the text the rule is considered
    **failed** (returns ``False``).

    Args:
        ticket_text: Full ticket text.
        pattern: Regex with a capture group that extracts the address.

    Returns:
        ``True`` if the address is found in FIAS, ``False`` otherwise.
    """
    try:
        match = re.search(pattern, ticket_text, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL)
        if not match or not match.group(1):
            return False

        address = match.group(1).strip()
        if not address:
            return False

        from .fias_providers import get_fias_provider

        provider = get_fias_provider()
        result = provider.validate_address(address)
        return result.is_valid

    except re.error:
        return False
    except Exception:  # noqa: BLE001 – fail-open for unexpected errors
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
    
    # Normalize keyword_weights keys to lowercase for case-insensitive matching
    keyword_weights = {k.lower(): v for k, v in (keyword_weights or {}).items()}
    
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
            
            # Check if keyword is present (count as 1 if present, 0 if not)
            count = 1 if keyword_lower in ticket_text_lower else 0
            
            # Get weight for this keyword (default 1.0)
            # Priority: 1) keyword_weights parameter, 2) ticket_type.keyword_weights, 3) default 1.0
            # For negative keywords, use the original keyword (with minus) as the key
            weight_key = keyword.lower() if is_negative else keyword_lower
            if weight_key in keyword_weights:
                weight = keyword_weights[weight_key]
            else:
                weight = ticket_type.get_keyword_weight(weight_key)
            
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
    has_ambiguity = False
    ambiguous_types = []
    
    if scores:
        # Find the highest score
        max_score = max(score for score, _ in scores.values())
        
        # Find all types with the highest score
        types_with_max_score = [tt for score, tt in scores.values() if score == max_score]
        
        # Check for ambiguity (multiple types with same max score)
        if len(types_with_max_score) > 1:
            has_ambiguity = True
            ambiguous_types = types_with_max_score
        
        # Still return the first one (or could return None if ambiguous)
        detected_type = types_with_max_score[0]
    
    if debug:
        debug_info = DetectionDebugInfo(
            detected_type=detected_type,
            all_scores=all_scores_debug,
            ticket_text_preview=ticket_text[:200] if ticket_text else "",
            has_ambiguity=has_ambiguity,
            ambiguous_types=ambiguous_types,
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
    passed_rules = []
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
            elif rule_type_value == 'regex_fullmatch':
                is_valid = validate_regex_fullmatch(ticket_text, rule.pattern)
            elif rule_type_value == 'regex_not_fullmatch':
                is_valid = validate_regex_not_fullmatch(ticket_text, rule.pattern)
            elif rule_type_value == 'fias_check':
                is_valid = validate_fias_address(ticket_text, rule.pattern)
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
        
        if is_valid:
            passed_rules.append(rule.rule_name)
        else:
            failed_rules.append(rule.rule_name)
            error_messages.append(rule.error_message)
    
    return ValidationResult(
        is_valid=len(failed_rules) == 0,
        failed_rules=failed_rules,
        passed_rules=passed_rules,
        error_messages=error_messages,
        validation_details=validation_details,
        detected_ticket_type=detected_ticket_type
    )
