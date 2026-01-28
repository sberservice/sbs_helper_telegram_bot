"""
Validation Rules Management Module

Handles loading and managing validation rules from the database.
"""

import json
import re
from typing import List, Optional, Tuple, Dict, Any
import src.common.database as database
from .validators import ValidationRule, TicketType


def _normalize_keyword_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize keyword_weights dictionary keys to lowercase.
    
    Args:
        weights: Dictionary mapping keywords to weights
        
    Returns:
        Dictionary with lowercase keys
    """
    return {k.lower(): v for k, v in weights.items()}


def load_all_ticket_types() -> List[TicketType]:
    """
    Load all active ticket types from the database.
    
    Returns:
        List of TicketType objects
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT id, type_name, description, detection_keywords, keyword_weights
                FROM ticket_validator_ticket_types 
                WHERE active = 1
                ORDER BY type_name
            """
            cursor.execute(sql_query)
            results = cursor.fetchall()
            
            ticket_types = []
            for row in results:
                # Parse detection keywords from JSON
                keywords = []
                if row['detection_keywords']:
                    try:
                        keywords = json.loads(row['detection_keywords'])
                    except json.JSONDecodeError:
                        keywords = []
                
                # Parse keyword weights from JSON (normalize keys to lowercase)
                weights = {}
                if row.get('keyword_weights'):
                    try:
                        weights = _normalize_keyword_weights(json.loads(row['keyword_weights']))
                    except json.JSONDecodeError:
                        weights = {}
                
                ticket_type = TicketType(
                    id=row['id'],
                    type_name=row['type_name'],
                    description=row['description'] or '',
                    detection_keywords=keywords,
                    active=True,
                    keyword_weights=weights
                )
                ticket_types.append(ticket_type)
            
            return ticket_types


def load_ticket_type_by_id(ticket_type_id: int) -> Optional[TicketType]:
    """
    Load a specific ticket type by ID.
    
    Args:
        ticket_type_id: ID of the ticket type
        
    Returns:
        TicketType object or None if not found
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT id, type_name, description, detection_keywords, keyword_weights, active
                FROM ticket_validator_ticket_types 
                WHERE id = %s
            """
            cursor.execute(sql_query, (ticket_type_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            keywords = []
            if row['detection_keywords']:
                try:
                    keywords = json.loads(row['detection_keywords'])
                except json.JSONDecodeError:
                    keywords = []
            
            # Parse keyword weights from JSON (normalize keys to lowercase)
            weights = {}
            if row.get('keyword_weights'):
                try:
                    weights = _normalize_keyword_weights(json.loads(row['keyword_weights']))
                except json.JSONDecodeError:
                    weights = {}
            
            return TicketType(
                id=row['id'],
                type_name=row['type_name'],
                description=row['description'] or '',
                detection_keywords=keywords,
                active=bool(row['active']),
                keyword_weights=weights
            )


def load_rules_from_db(ticket_type_id: Optional[int] = None) -> List[ValidationRule]:
    """
    Load validation rules from the database.
    If ticket_type_id is provided, load only rules for that ticket type.
    Otherwise, load all active rules.
    
    Args:
        ticket_type_id: Optional ticket type ID to filter rules
        
    Returns:
        List of ValidationRule objects sorted by priority
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            if ticket_type_id is not None:
                # Load rules for specific ticket type
                sql_query = """
                    SELECT vr.id, vr.rule_name, vr.pattern, vr.rule_type, vr.error_message, 
                           vr.active, vr.priority, vr.created_timestamp, vr.updated_timestamp
                    FROM ticket_validator_validation_rules vr
                    INNER JOIN ticket_validator_ticket_type_rules ttr ON vr.id = ttr.validation_rule_id
                    WHERE ttr.ticket_type_id = %s AND vr.active = 1
                    ORDER BY vr.priority DESC, vr.id ASC
                """
                cursor.execute(sql_query, (ticket_type_id,))
            else:
                # Load all active rules
                sql_query = """
                    SELECT id, rule_name, pattern, rule_type, error_message, 
                           active, priority, created_timestamp, updated_timestamp
                    FROM ticket_validator_validation_rules 
                    WHERE active = 1
                    ORDER BY priority DESC, id ASC
                """
                cursor.execute(sql_query)
            
            results = cursor.fetchall()
            
            rules = []
            for row in results:
                rule = ValidationRule(
                    id=row['id'],
                    rule_name=row['rule_name'],
                    pattern=row['pattern'],
                    rule_type=row['rule_type'],
                    error_message=row['error_message'],
                    active=bool(row['active']),
                    priority=row['priority']
                )
                rules.append(rule)
            
            return rules


def load_rule_by_id(rule_id: int) -> Optional[ValidationRule]:
    """
    Load a specific validation rule by ID.
    
    Args:
        rule_id: ID of the rule to load
        
    Returns:
        ValidationRule object or None if not found
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT id, rule_name, pattern, rule_type, error_message, 
                       active, priority, created_timestamp, updated_timestamp
                FROM ticket_validator_validation_rules 
                WHERE id = %s
            """
            cursor.execute(sql_query, (rule_id,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return ValidationRule(
                id=row['id'],
                rule_name=row['rule_name'],
                pattern=row['pattern'],
                rule_type=row['rule_type'],
                error_message=row['error_message'],
                active=bool(row['active']),
                priority=row['priority']
            )





def load_template_by_name(template_name: str) -> Optional[dict]:
    """
    Load a ticket template by name.
    
    Args:
        template_name: Name of the template
        
    Returns:
        Template dict or None if not found
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT id, template_name, template_text, description
                FROM ticket_validator_ticket_templates 
                WHERE template_name = %s AND active = 1
            """
            cursor.execute(sql_query, (template_name,))
            return cursor.fetchone()


def list_all_templates() -> List[dict]:
    """
    Get all active ticket templates.
    
    Returns:
        List of template dicts
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT id, template_name, description
                FROM ticket_validator_ticket_templates 
                WHERE active = 1
                ORDER BY template_name
            """
            cursor.execute(sql_query)
            return cursor.fetchall()


# ===== ADMIN CRUD OPERATIONS =====

def test_regex_pattern(pattern: str, test_text: str = None) -> Tuple[bool, str]:
    """
    Test if a regex pattern is valid and optionally test it against sample text.
    
    Args:
        pattern: The regex pattern to test
        test_text: Optional text to test the pattern against
        
    Returns:
        Tuple of (is_valid, message)
    """
    try:
        compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE | re.UNICODE | re.DOTALL)
        if test_text:
            match = compiled.search(test_text)
            if match:
                return True, f"✅ Паттерн валиден. Найдено совпадение: '{match.group()}'"
            else:
                return True, "✅ Паттерн валиден, но совпадений не найдено в тестовом тексте."
        return True, "✅ Паттерн валиден."
    except re.error as e:
        return False, f"❌ Ошибка в регулярном выражении: {str(e)}"


def load_all_rules(include_inactive: bool = False) -> List[ValidationRule]:
    """
    Load all validation rules from database.
    
    Args:
        include_inactive: If True, also load inactive rules
        
    Returns:
        List of ValidationRule objects
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            if include_inactive:
                sql_query = """
                    SELECT id, rule_name, pattern, rule_type, error_message, 
                           active, priority, created_timestamp, updated_timestamp
                    FROM ticket_validator_validation_rules 
                    ORDER BY priority DESC, id ASC
                """
                cursor.execute(sql_query)
            else:
                sql_query = """
                    SELECT id, rule_name, pattern, rule_type, error_message, 
                           active, priority, created_timestamp, updated_timestamp
                    FROM ticket_validator_validation_rules 
                    WHERE active = 1
                    ORDER BY priority DESC, id ASC
                """
                cursor.execute(sql_query)
            
            results = cursor.fetchall()
            rules = []
            for row in results:
                rule = ValidationRule(
                    id=row['id'],
                    rule_name=row['rule_name'],
                    pattern=row['pattern'],
                    rule_type=row['rule_type'],
                    error_message=row['error_message'],
                    active=bool(row['active']),
                    priority=row['priority']
                )
                rules.append(rule)
            return rules


def load_all_ticket_types_admin(include_inactive: bool = False) -> List[TicketType]:
    """
    Load all ticket types from database (admin version includes inactive).
    
    Args:
        include_inactive: If True, also load inactive types
        
    Returns:
        List of TicketType objects
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            if include_inactive:
                sql_query = """
                    SELECT id, type_name, description, detection_keywords, keyword_weights, active
                    FROM ticket_validator_ticket_types 
                    ORDER BY type_name
                """
            else:
                sql_query = """
                    SELECT id, type_name, description, detection_keywords, keyword_weights, active
                    FROM ticket_validator_ticket_types 
                    WHERE active = 1
                    ORDER BY type_name
                """
            cursor.execute(sql_query)
            results = cursor.fetchall()
            
            ticket_types = []
            for row in results:
                keywords = []
                if row['detection_keywords']:
                    try:
                        keywords = json.loads(row['detection_keywords'])
                    except json.JSONDecodeError:
                        keywords = []
                
                # Parse keyword weights from JSON (normalize keys to lowercase)
                weights = {}
                if row.get('keyword_weights'):
                    try:
                        weights = _normalize_keyword_weights(json.loads(row['keyword_weights']))
                    except json.JSONDecodeError:
                        weights = {}
                
                ticket_type = TicketType(
                    id=row['id'],
                    type_name=row['type_name'],
                    description=row['description'] or '',
                    detection_keywords=keywords,
                    active=bool(row['active']),
                    keyword_weights=weights
                )
                ticket_types.append(ticket_type)
            
            return ticket_types


def create_validation_rule(rule_name: str, pattern: str, rule_type: str, 
                           error_message: str, priority: int = 0) -> Optional[int]:
    """
    Create a new validation rule.
    
    Args:
        rule_name: Name of the rule
        pattern: Regex pattern or format specification
        rule_type: Type of rule (regex, required_field, format, length, custom)
        error_message: Error message to show when validation fails
        priority: Rule priority (higher = checked first)
        
    Returns:
        ID of the created rule, or None on failure
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                INSERT INTO ticket_validator_validation_rules 
                (rule_name, pattern, rule_type, error_message, priority, active, created_timestamp) 
                VALUES (%s, %s, %s, %s, %s, 1, UNIX_TIMESTAMP())
            """
            val = (rule_name, pattern, rule_type, error_message, priority)
            cursor.execute(sql, val)
            return cursor.lastrowid


def update_validation_rule(rule_id: int, rule_name: str = None, pattern: str = None,
                           rule_type: str = None, error_message: str = None, 
                           priority: int = None) -> bool:
    """
    Update an existing validation rule.
    
    Args:
        rule_id: ID of the rule to update
        rule_name: New name (optional)
        pattern: New pattern (optional)
        rule_type: New type (optional)
        error_message: New error message (optional)
        priority: New priority (optional)
        
    Returns:
        True if rule was updated, False otherwise
    """
    updates = []
    values = []
    
    if rule_name is not None:
        updates.append("rule_name = %s")
        values.append(rule_name)
    if pattern is not None:
        updates.append("pattern = %s")
        values.append(pattern)
    if rule_type is not None:
        updates.append("rule_type = %s")
        values.append(rule_type)
    if error_message is not None:
        updates.append("error_message = %s")
        values.append(error_message)
    if priority is not None:
        updates.append("priority = %s")
        values.append(priority)
    
    if not updates:
        return False
    
    updates.append("updated_timestamp = UNIX_TIMESTAMP()")
    values.append(rule_id)
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = f"UPDATE ticket_validator_validation_rules SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(sql, tuple(values))
            return cursor.rowcount > 0


def toggle_rule_active(rule_id: int, active: bool) -> bool:
    """
    Enable or disable a validation rule.
    
    Args:
        rule_id: ID of the rule
        active: True to enable, False to disable
        
    Returns:
        True if rule was updated, False otherwise
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                UPDATE ticket_validator_validation_rules 
                SET active = %s, updated_timestamp = UNIX_TIMESTAMP() 
                WHERE id = %s
            """
            cursor.execute(sql, (1 if active else 0, rule_id))
            return cursor.rowcount > 0


def delete_validation_rule(rule_id: int) -> Tuple[bool, int]:
    """
    Delete a validation rule and its associations with ticket types.
    
    Args:
        rule_id: ID of the rule to delete
        
    Returns:
        Tuple of (success, number_of_deleted_associations)
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # First, delete associations
            sql_assoc = "DELETE FROM ticket_validator_ticket_type_rules WHERE validation_rule_id = %s"
            cursor.execute(sql_assoc, (rule_id,))
            deleted_associations = cursor.rowcount
            
            # Then delete the rule
            sql_rule = "DELETE FROM ticket_validator_validation_rules WHERE id = %s"
            cursor.execute(sql_rule, (rule_id,))
            
            return cursor.rowcount > 0, deleted_associations


def get_rules_for_ticket_type(ticket_type_id: int) -> List[ValidationRule]:
    """
    Get all rules assigned to a specific ticket type.
    
    Args:
        ticket_type_id: ID of the ticket type
        
    Returns:
        List of ValidationRule objects
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT vr.id, vr.rule_name, vr.pattern, vr.rule_type, vr.error_message, 
                       vr.active, vr.priority
                FROM ticket_validator_validation_rules vr
                INNER JOIN ticket_validator_ticket_type_rules ttr ON vr.id = ttr.validation_rule_id
                WHERE ttr.ticket_type_id = %s
                ORDER BY vr.priority DESC, vr.id ASC
            """
            cursor.execute(sql_query, (ticket_type_id,))
            results = cursor.fetchall()
            
            rules = []
            for row in results:
                rule = ValidationRule(
                    id=row['id'],
                    rule_name=row['rule_name'],
                    pattern=row['pattern'],
                    rule_type=row['rule_type'],
                    error_message=row['error_message'],
                    active=bool(row['active']),
                    priority=row['priority']
                )
                rules.append(rule)
            return rules


def get_ticket_types_for_rule(rule_id: int) -> List[TicketType]:
    """
    Get all ticket types that use a specific rule.
    
    Args:
        rule_id: ID of the validation rule
        
    Returns:
        List of TicketType objects
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT tt.id, tt.type_name, tt.description, tt.detection_keywords, tt.keyword_weights, tt.active
                FROM ticket_validator_ticket_types tt
                INNER JOIN ticket_validator_ticket_type_rules ttr ON tt.id = ttr.ticket_type_id
                WHERE ttr.validation_rule_id = %s
                ORDER BY tt.type_name
            """
            cursor.execute(sql_query, (rule_id,))
            results = cursor.fetchall()
            
            ticket_types = []
            for row in results:
                keywords = []
                if row['detection_keywords']:
                    try:
                        keywords = json.loads(row['detection_keywords'])
                    except json.JSONDecodeError:
                        keywords = []
                
                # Parse keyword weights from JSON (normalize keys to lowercase)
                weights = {}
                if row.get('keyword_weights'):
                    try:
                        weights = _normalize_keyword_weights(json.loads(row['keyword_weights']))
                    except json.JSONDecodeError:
                        weights = {}
                
                ticket_type = TicketType(
                    id=row['id'],
                    type_name=row['type_name'],
                    description=row['description'] or '',
                    detection_keywords=keywords,
                    active=bool(row['active']),
                    keyword_weights=weights
                )
                ticket_types.append(ticket_type)
            
            return ticket_types


def add_rule_to_ticket_type(rule_id: int, ticket_type_id: int) -> bool:
    """
    Associate a validation rule with a ticket type.
    
    Args:
        rule_id: ID of the validation rule
        ticket_type_id: ID of the ticket type
        
    Returns:
        True if association was created, False if it already exists
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            try:
                sql = """
                    INSERT INTO ticket_validator_ticket_type_rules 
                    (ticket_type_id, validation_rule_id, created_timestamp) 
                    VALUES (%s, %s, UNIX_TIMESTAMP())
                """
                cursor.execute(sql, (ticket_type_id, rule_id))
                return cursor.rowcount > 0
            except Exception:
                # Duplicate key - association already exists
                return False


def remove_rule_from_ticket_type(rule_id: int, ticket_type_id: int) -> bool:
    """
    Remove association between a validation rule and a ticket type.
    
    Args:
        rule_id: ID of the validation rule
        ticket_type_id: ID of the ticket type
        
    Returns:
        True if association was removed, False otherwise
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                DELETE FROM ticket_validator_ticket_type_rules 
                WHERE ticket_type_id = %s AND validation_rule_id = %s
            """
            cursor.execute(sql, (ticket_type_id, rule_id))
            return cursor.rowcount > 0


def get_rule_type_mapping() -> List[Dict[str, Any]]:
    """
    Get all rule-to-ticket-type mappings.
    
    Returns:
        List of dicts with rule_id, rule_name, ticket_type_id, type_name
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT 
                    vr.id as rule_id, 
                    vr.rule_name,
                    tt.id as ticket_type_id,
                    tt.type_name
                FROM ticket_validator_ticket_type_rules ttr
                INNER JOIN ticket_validator_validation_rules vr ON ttr.validation_rule_id = vr.id
                INNER JOIN ticket_validator_ticket_types tt ON ttr.ticket_type_id = tt.id
                ORDER BY vr.rule_name, tt.type_name
            """
            cursor.execute(sql_query)
            return cursor.fetchall()


# ===== TEST TEMPLATE MANAGEMENT =====
# Templates are now used as test cases for validation rules (admin-only)

def create_test_template(
    template_name: str, 
    template_text: str, 
    description: str = None,
    expected_result: str = 'pass',
    ticket_type_id: int = None
) -> Optional[int]:
    """
    Create a new test template for validation rule testing.
    
    Args:
        template_name: Name of the test template
        template_text: Sample ticket text to test
        description: Description of what this template tests
        expected_result: 'pass' or 'fail' - overall expected validation result
        ticket_type_id: Optional ticket type this template is for
        
    Returns:
        ID of created template, or None on failure
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                INSERT INTO ticket_validator_ticket_templates 
                (template_name, template_text, description, expected_result, 
                 ticket_type_id, active, created_timestamp)
                VALUES (%s, %s, %s, %s, %s, 1, UNIX_TIMESTAMP())
            """
            cursor.execute(sql, (
                template_name, template_text, description, 
                expected_result, ticket_type_id
            ))
            return cursor.lastrowid


def update_test_template(
    template_id: int,
    template_name: str = None,
    template_text: str = None,
    description: str = None,
    expected_result: str = None,
    ticket_type_id: int = None
) -> bool:
    """
    Update an existing test template.
    
    Args:
        template_id: ID of the template to update
        template_name: New name (optional)
        template_text: New text (optional)
        description: New description (optional)
        expected_result: New expected result (optional)
        ticket_type_id: New ticket type ID (optional)
        
    Returns:
        True if updated, False otherwise
    """
    updates = []
    values = []
    
    if template_name is not None:
        updates.append("template_name = %s")
        values.append(template_name)
    if template_text is not None:
        updates.append("template_text = %s")
        values.append(template_text)
    if description is not None:
        updates.append("description = %s")
        values.append(description)
    if expected_result is not None:
        updates.append("expected_result = %s")
        values.append(expected_result)
    if ticket_type_id is not None:
        updates.append("ticket_type_id = %s")
        values.append(ticket_type_id)
    
    if not updates:
        return False
    
    updates.append("updated_timestamp = UNIX_TIMESTAMP()")
    values.append(template_id)
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = f"UPDATE ticket_validator_ticket_templates SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(sql, tuple(values))
            return cursor.rowcount > 0


def delete_test_template(template_id: int) -> Tuple[bool, int]:
    """
    Delete a test template and its associated rule expectations.
    
    Args:
        template_id: ID of the template to delete
        
    Returns:
        Tuple of (success, number_of_rule_expectations_deleted)
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # First count the rule expectations
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM ticket_validator_template_rule_tests WHERE template_id = %s",
                (template_id,)
            )
            rule_count = cursor.fetchone()['cnt']
            
            # Delete template (cascade will delete rule expectations)
            cursor.execute(
                "DELETE FROM ticket_validator_ticket_templates WHERE id = %s",
                (template_id,)
            )
            return cursor.rowcount > 0, rule_count


def toggle_test_template_active(template_id: int, active: bool) -> bool:
    """
    Toggle a test template's active status.
    
    Args:
        template_id: ID of the template
        active: New active status
        
    Returns:
        True if updated, False otherwise
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                UPDATE ticket_validator_ticket_templates 
                SET active = %s, updated_timestamp = UNIX_TIMESTAMP()
                WHERE id = %s
            """
            cursor.execute(sql, (1 if active else 0, template_id))
            return cursor.rowcount > 0


def load_test_template_by_id(template_id: int) -> Optional[dict]:
    """
    Load a test template by ID with all details.
    
    Args:
        template_id: ID of the template
        
    Returns:
        Template dict with all fields, or None
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                SELECT t.id, t.template_name, t.template_text, t.description,
                       t.expected_result, t.ticket_type_id, t.active,
                       t.created_timestamp, t.updated_timestamp,
                       tt.type_name as ticket_type_name
                FROM ticket_validator_ticket_templates t
                LEFT JOIN ticket_validator_ticket_types tt ON t.ticket_type_id = tt.id
                WHERE t.id = %s
            """
            cursor.execute(sql, (template_id,))
            return cursor.fetchone()


def list_all_test_templates(include_inactive: bool = False) -> List[dict]:
    """
    Get all test templates with summary info.
    
    Args:
        include_inactive: Whether to include inactive templates
        
    Returns:
        List of template dicts
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            if include_inactive:
                sql = """
                    SELECT t.id, t.template_name, t.description, t.expected_result,
                           t.ticket_type_id, t.active, tt.type_name as ticket_type_name,
                           (SELECT COUNT(*) FROM ticket_validator_template_rule_tests WHERE template_id = t.id) as rule_count
                    FROM ticket_validator_ticket_templates t
                    LEFT JOIN ticket_validator_ticket_types tt ON t.ticket_type_id = tt.id
                    ORDER BY t.template_name
                """
            else:
                sql = """
                    SELECT t.id, t.template_name, t.description, t.expected_result,
                           t.ticket_type_id, t.active, tt.type_name as ticket_type_name,
                           (SELECT COUNT(*) FROM ticket_validator_template_rule_tests WHERE template_id = t.id) as rule_count
                    FROM ticket_validator_ticket_templates t
                    LEFT JOIN ticket_validator_ticket_types tt ON t.ticket_type_id = tt.id
                    WHERE t.active = 1
                    ORDER BY t.template_name
                """
            cursor.execute(sql)
            return cursor.fetchall()


# ===== TEMPLATE RULE EXPECTATIONS =====

def set_template_rule_expectation(
    template_id: int, 
    rule_id: int, 
    expected_pass: bool,
    notes: str = None
) -> bool:
    """
    Set or update the expected result for a rule on a template.
    
    Args:
        template_id: ID of the test template
        rule_id: ID of the validation rule
        expected_pass: True if the rule should pass, False if it should fail
        notes: Optional notes explaining the expectation
        
    Returns:
        True if set successfully
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Use INSERT ... ON DUPLICATE KEY UPDATE for upsert
            sql = """
                INSERT INTO ticket_validator_template_rule_tests 
                (template_id, validation_rule_id, expected_pass, notes, created_timestamp)
                VALUES (%s, %s, %s, %s, UNIX_TIMESTAMP())
                ON DUPLICATE KEY UPDATE 
                    expected_pass = VALUES(expected_pass),
                    notes = VALUES(notes),
                    updated_timestamp = UNIX_TIMESTAMP()
            """
            cursor.execute(sql, (template_id, rule_id, 1 if expected_pass else 0, notes))
            return True


def remove_template_rule_expectation(template_id: int, rule_id: int) -> bool:
    """
    Remove a rule expectation from a template.
    
    Args:
        template_id: ID of the test template
        rule_id: ID of the validation rule
        
    Returns:
        True if removed, False if not found
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                DELETE FROM ticket_validator_template_rule_tests 
                WHERE template_id = %s AND validation_rule_id = %s
            """
            cursor.execute(sql, (template_id, rule_id))
            return cursor.rowcount > 0


def get_template_rule_expectations(template_id: int) -> List[dict]:
    """
    Get all rule expectations for a template.
    
    Args:
        template_id: ID of the test template
        
    Returns:
        List of dicts with rule info and expected_pass
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                SELECT trt.id, trt.validation_rule_id, trt.expected_pass, trt.notes,
                       vr.rule_name, vr.pattern, vr.rule_type, vr.error_message,
                       vr.active as rule_active
                FROM ticket_validator_template_rule_tests trt
                INNER JOIN ticket_validator_validation_rules vr ON trt.validation_rule_id = vr.id
                WHERE trt.template_id = %s
                ORDER BY vr.rule_name
            """
            cursor.execute(sql, (template_id,))
            return cursor.fetchall()


def get_rules_not_in_template(template_id: int) -> List[ValidationRule]:
    """
    Get all active rules that are not yet assigned to a template.
    
    Args:
        template_id: ID of the test template
        
    Returns:
        List of ValidationRule objects not assigned to this template
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                SELECT id, rule_name, pattern, rule_type, error_message, active, priority
                FROM ticket_validator_validation_rules
                WHERE active = 1
                AND id NOT IN (
                    SELECT validation_rule_id FROM ticket_validator_template_rule_tests 
                    WHERE template_id = %s
                )
                ORDER BY rule_name
            """
            cursor.execute(sql, (template_id,))
            results = cursor.fetchall()
            
            return [
                ValidationRule(
                    id=row['id'],
                    rule_name=row['rule_name'],
                    pattern=row['pattern'],
                    rule_type=row['rule_type'],
                    error_message=row['error_message'],
                    active=bool(row['active']),
                    priority=row['priority']
                )
                for row in results
            ]


# ===== VALIDATION TESTING =====

def run_template_validation_test(template_id: int, admin_userid: int) -> Dict[str, Any]:
    """
    Run validation test for a template and compare with expected results.
    
    This function:
    1. Loads the template and its rule expectations
    2. Runs validation on the template text
    3. Compares actual results with expectations
    4. Stores the test result
    5. Returns detailed results
    
    Args:
        template_id: ID of the test template
        admin_userid: ID of the admin running the test
        
    Returns:
        Dict with test results including:
        - overall_pass: bool
        - total_rules_tested: int
        - rules_passed_as_expected: int
        - rules_failed_unexpectedly: int
        - details: list of per-rule results
    """
    from .validators import validate_ticket
    
    # Load template
    template = load_test_template_by_id(template_id)
    if not template:
        return {'error': 'Template not found'}
    
    # Load rule expectations
    expectations = get_template_rule_expectations(template_id)
    if not expectations:
        return {'error': 'No rule expectations defined for this template'}
    
    # Build rules list from expectations
    rules = []
    for exp in expectations:
        rule = ValidationRule(
            id=exp['validation_rule_id'],
            rule_name=exp['rule_name'],
            pattern=exp['pattern'],
            rule_type=exp['rule_type'],
            error_message=exp['error_message'],
            active=True,  # Test all rules regardless of active status
            priority=0
        )
        rules.append(rule)
    
    # Run validation
    result = validate_ticket(template['template_text'], rules)
    
    # Compare with expectations
    details = []
    rules_passed_as_expected = 0
    rules_failed_unexpectedly = 0
    
    # Build set of failed rule IDs from validation result
    failed_rule_ids = set()
    for rule in rules:
        # Check if this rule's error message is in the failed rules
        if rule.rule_name in result.failed_rules or rule.error_message in result.error_messages:
            failed_rule_ids.add(rule.id)
    
    # Also check validation_details if available
    if hasattr(result, 'validation_details') and result.validation_details:
        for rule_name, passed in result.validation_details.items():
            if not passed:
                # Find rule ID by name
                for rule in rules:
                    if rule.rule_name == rule_name:
                        failed_rule_ids.add(rule.id)
    
    for exp in expectations:
        rule_id = exp['validation_rule_id']
        expected_pass = bool(exp['expected_pass'])
        actual_pass = rule_id not in failed_rule_ids
        
        matches_expectation = (expected_pass == actual_pass)
        
        detail = {
            'rule_id': rule_id,
            'rule_name': exp['rule_name'],
            'expected_pass': expected_pass,
            'actual_pass': actual_pass,
            'matches_expectation': matches_expectation,
            'notes': exp['notes']
        }
        details.append(detail)
        
        if matches_expectation:
            rules_passed_as_expected += 1
        else:
            rules_failed_unexpectedly += 1
    
    overall_pass = rules_failed_unexpectedly == 0
    
    # Store test result
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                INSERT INTO ticket_validator_template_test_results
                (template_id, admin_userid, overall_pass, total_rules_tested,
                 rules_passed_as_expected, rules_failed_unexpectedly, 
                 details_json, run_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, UNIX_TIMESTAMP())
            """
            cursor.execute(sql, (
                template_id, admin_userid, 1 if overall_pass else 0,
                len(expectations), rules_passed_as_expected,
                rules_failed_unexpectedly, json.dumps(details, ensure_ascii=False)
            ))
    
    return {
        'overall_pass': overall_pass,
        'total_rules_tested': len(expectations),
        'rules_passed_as_expected': rules_passed_as_expected,
        'rules_failed_unexpectedly': rules_failed_unexpectedly,
        'details': details,
        'template_name': template['template_name'],
        'expected_result': template['expected_result']
    }


def run_all_template_tests(admin_userid: int) -> Dict[str, Any]:
    """
    Run validation tests for all active templates.
    
    Args:
        admin_userid: ID of the admin running the tests
        
    Returns:
        Dict with summary and per-template results
    """
    templates = list_all_test_templates(include_inactive=False)
    
    results = []
    total_passed = 0
    total_failed = 0
    
    for template in templates:
        result = run_template_validation_test(template['id'], admin_userid)
        
        if 'error' in result:
            results.append({
                'template_id': template['id'],
                'template_name': template['template_name'],
                'error': result['error']
            })
        else:
            results.append({
                'template_id': template['id'],
                'template_name': template['template_name'],
                'overall_pass': result['overall_pass'],
                'rules_passed': result['rules_passed_as_expected'],
                'rules_failed': result['rules_failed_unexpectedly']
            })
            
            if result['overall_pass']:
                total_passed += 1
            else:
                total_failed += 1
    
    return {
        'total_templates': len(templates),
        'templates_passed': total_passed,
        'templates_failed': total_failed,
        'results': results
    }


def get_template_test_history(template_id: int, limit: int = 10) -> List[dict]:
    """
    Get test run history for a specific template.
    
    Args:
        template_id: ID of the test template
        limit: Maximum number of results
        
    Returns:
        List of test result dicts
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                SELECT id, admin_userid, overall_pass, total_rules_tested,
                       rules_passed_as_expected, rules_failed_unexpectedly,
                       details_json, run_timestamp
                FROM ticket_validator_template_test_results
                WHERE template_id = %s
                ORDER BY run_timestamp DESC
                LIMIT %s
            """
            cursor.execute(sql, (template_id, limit))
            results = cursor.fetchall()
            
            for result in results:
                if result['details_json']:
                    try:
                        result['details'] = json.loads(result['details_json'])
                    except json.JSONDecodeError:
                        result['details'] = []
            
            return results
