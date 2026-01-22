"""
Validation Rules Management Module

Handles loading and managing validation rules from the database.
"""

import json
from typing import List, Optional
import src.common.database as database
from .validators import ValidationRule, TicketType


def load_all_ticket_types() -> List[TicketType]:
    """
    Load all active ticket types from the database.
    
    Returns:
        List of TicketType objects
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT id, type_name, description, detection_keywords
                FROM ticket_types 
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
                
                ticket_type = TicketType(
                    id=row['id'],
                    type_name=row['type_name'],
                    description=row['description'] or '',
                    detection_keywords=keywords,
                    active=True
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
                SELECT id, type_name, description, detection_keywords, active
                FROM ticket_types 
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
            
            return TicketType(
                id=row['id'],
                type_name=row['type_name'],
                description=row['description'] or '',
                detection_keywords=keywords,
                active=bool(row['active'])
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
                    FROM validation_rules vr
                    INNER JOIN ticket_type_rules ttr ON vr.id = ttr.validation_rule_id
                    WHERE ttr.ticket_type_id = %s AND vr.active = 1
                    ORDER BY vr.priority DESC, vr.id ASC
                """
                cursor.execute(sql_query, (ticket_type_id,))
            else:
                # Load all active rules
                sql_query = """
                    SELECT id, rule_name, pattern, rule_type, error_message, 
                           active, priority, created_timestamp, updated_timestamp
                    FROM validation_rules 
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
                FROM validation_rules 
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


def store_validation_result(userid: int, ticket_text: str, is_valid: bool, failed_rules: List[str], 
                           ticket_type_id: Optional[int] = None) -> int:
    """
    Store validation attempt in history.
    
    Args:
        userid: Telegram user ID
        ticket_text: The ticket text that was validated
        is_valid: Whether validation passed
        failed_rules: List of rule names that failed
        ticket_type_id: Optional ID of detected ticket type
        
    Returns:
        ID of the created history record
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                INSERT INTO validation_history 
                (userid, ticket_type_id, ticket_text, validation_result, failed_rules, timestamp) 
                VALUES (%s, %s, %s, %s, %s, UNIX_TIMESTAMP())
            """
            val = (
                userid,
                ticket_type_id,
                ticket_text, 
                'valid' if is_valid else 'invalid',
                json.dumps(failed_rules, ensure_ascii=False) if failed_rules else None
            )
            cursor.execute(sql, val)
            return cursor.lastrowid


def get_validation_history(userid: int, limit: int = 10) -> List[dict]:
    """
    Get validation history for a user.
    
    Args:
        userid: Telegram user ID
        limit: Maximum number of records to return
        
    Returns:
        List of validation history records
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = """
                SELECT id, ticket_text, validation_result, failed_rules, timestamp
                FROM validation_history 
                WHERE userid = %s
                ORDER BY timestamp DESC
                LIMIT %s
            """
            cursor.execute(sql_query, (userid, limit))
            results = cursor.fetchall()
            
            for result in results:
                if result['failed_rules']:
                    try:
                        result['failed_rules'] = json.loads(result['failed_rules'])
                    except json.JSONDecodeError:
                        result['failed_rules'] = []
            
            return results


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
                FROM ticket_templates 
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
                FROM ticket_templates 
                WHERE active = 1
                ORDER BY template_name
            """
            cursor.execute(sql_query)
            return cursor.fetchall()
