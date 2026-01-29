"""
Feedback Module Logic

Business logic, database operations, link detection, and rate limiting.
"""

import re
import time
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

import src.common.database as database
from . import settings

logger = logging.getLogger(__name__)


# ===== LINK DETECTION =====


def contains_links(text: str) -> bool:
    """
    Check if text contains any links/URLs.
    
    Args:
        text: Text to check
        
    Returns:
        True if links are detected, False otherwise
    """
    for pattern in settings.LINK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# ===== RATE LIMITING =====


def check_rate_limit(user_id: int) -> Tuple[bool, int]:
    """
    Check if user is rate limited.
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Tuple of (is_allowed, seconds_remaining)
        - is_allowed: True if user can submit, False if rate limited
        - seconds_remaining: Seconds until next submission allowed (0 if allowed)
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get most recent feedback submission
                cursor.execute("""
                    SELECT created_timestamp
                    FROM feedback_entries
                    WHERE user_id = %s
                    ORDER BY created_timestamp DESC
                    LIMIT 1
                """, (user_id,))
                
                result = cursor.fetchone()
                
                if not result:
                    return (True, 0)
                
                last_submission = result['created_timestamp']
                current_time = int(time.time())
                time_diff = current_time - last_submission
                
                if time_diff >= settings.RATE_LIMIT_SECONDS:
                    return (True, 0)
                
                seconds_remaining = settings.RATE_LIMIT_SECONDS - time_diff
                return (False, seconds_remaining)
                
    except Exception as e:
        logger.error("Error checking rate limit for user %s: %s", user_id, e)
        # On error, allow submission to not block users
        return (True, 0)


# ===== CATEGORIES =====


def get_active_categories() -> List[Dict[str, Any]]:
    """
    Get all active feedback categories.
    
    Returns:
        List of category dicts with id, name, description, emoji
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT id, name, description, emoji
                    FROM feedback_categories
                    WHERE active = 1
                    ORDER BY display_order ASC, id ASC
                """)
                
                return cursor.fetchall() or []
                
    except Exception as e:
        logger.error("Error getting feedback categories: %s", e)
        return []


def get_category_by_id(category_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a category by ID.
    
    Args:
        category_id: Category ID
        
    Returns:
        Category dict or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT id, name, description, emoji
                    FROM feedback_categories
                    WHERE id = %s AND active = 1
                """, (category_id,))
                
                return cursor.fetchone()
                
    except Exception as e:
        logger.error("Error getting category %s: %s", category_id, e)
        return None


def get_categories_with_counts() -> List[Dict[str, Any]]:
    """
    Get all active categories with entry counts.
    
    Returns:
        List of category dicts with id, name, emoji, count
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT 
                        c.id, 
                        c.name, 
                        c.emoji,
                        COUNT(e.id) as count
                    FROM feedback_categories c
                    LEFT JOIN feedback_entries e ON c.id = e.category_id
                    WHERE c.active = 1
                    GROUP BY c.id, c.name, c.emoji
                    ORDER BY c.display_order ASC, c.id ASC
                """)
                
                return cursor.fetchall() or []
                
    except Exception as e:
        logger.error("Error getting categories with counts: %s", e)
        return []


# ===== FEEDBACK ENTRIES =====


def create_feedback_entry(
    user_id: int,
    category_id: int,
    message: str
) -> Optional[int]:
    """
    Create a new feedback entry.
    
    Args:
        user_id: Telegram user ID
        category_id: Category ID
        message: User's feedback message
        
    Returns:
        Created entry ID or None on error
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                current_time = int(time.time())
                
                cursor.execute("""
                    INSERT INTO feedback_entries 
                    (user_id, category_id, message, status, created_timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                """, (user_id, category_id, message, settings.STATUS_NEW, current_time))
                
                conn.commit()
                return cursor.lastrowid
                
    except Exception as e:
        logger.error("Error creating feedback entry: %s", e)
        return None


def get_user_feedback_entries(
    user_id: int,
    page: int = 0,
    per_page: int = None
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Get feedback entries for a user with pagination.
    
    Args:
        user_id: Telegram user ID
        page: Page number (0-indexed)
        per_page: Items per page (default from settings)
        
    Returns:
        Tuple of (entries list, total count)
    """
    if per_page is None:
        per_page = settings.ITEMS_PER_PAGE
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get total count
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM feedback_entries
                    WHERE user_id = %s
                """, (user_id,))
                total = cursor.fetchone()['count']
                
                # Get entries
                offset = page * per_page
                cursor.execute("""
                    SELECT 
                        e.id,
                        e.status,
                        e.created_timestamp,
                        COALESCE(c.name, 'Без категории') as category
                    FROM feedback_entries e
                    LEFT JOIN feedback_categories c ON e.category_id = c.id
                    WHERE e.user_id = %s
                    ORDER BY e.created_timestamp DESC
                    LIMIT %s OFFSET %s
                """, (user_id, per_page, offset))
                
                entries = cursor.fetchall() or []
                
                # Format dates
                for entry in entries:
                    entry['date'] = _format_timestamp(entry['created_timestamp'])
                
                return (entries, total)
                
    except Exception as e:
        logger.error("Error getting user feedback: %s", e)
        return ([], 0)


def get_feedback_entry(entry_id: int, user_id: int = None) -> Optional[Dict[str, Any]]:
    """
    Get a single feedback entry with responses.
    
    Args:
        entry_id: Entry ID
        user_id: Optional user ID for ownership verification
        
    Returns:
        Entry dict with responses or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Build query
                query = """
                    SELECT 
                        e.id,
                        e.user_id,
                        e.message,
                        e.status,
                        e.created_timestamp,
                        COALESCE(c.name, 'Без категории') as category
                    FROM feedback_entries e
                    LEFT JOIN feedback_categories c ON e.category_id = c.id
                    WHERE e.id = %s
                """
                params = [entry_id]
                
                if user_id is not None:
                    query += " AND e.user_id = %s"
                    params.append(user_id)
                
                cursor.execute(query, params)
                entry = cursor.fetchone()
                
                if not entry:
                    return None
                
                # Format date
                entry['date'] = _format_timestamp(entry['created_timestamp'])
                
                # Get responses (NO admin_id exposed!)
                cursor.execute("""
                    SELECT 
                        response_text,
                        created_timestamp
                    FROM feedback_responses
                    WHERE entry_id = %s
                    ORDER BY created_timestamp ASC
                """, (entry_id,))
                
                responses = cursor.fetchall() or []
                entry['responses'] = [
                    {
                        'text': r['response_text'],
                        'date': _format_timestamp(r['created_timestamp'])
                    }
                    for r in responses
                ]
                
                return entry
                
    except Exception as e:
        logger.error("Error getting feedback entry %s: %s", entry_id, e)
        return None


# ===== ADMIN FUNCTIONS =====


def get_feedback_entries_by_status(
    status: str = None,
    category_id: int = None,
    page: int = 0,
    per_page: int = None
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Get feedback entries with optional filters (admin function).
    
    Args:
        status: Filter by status (None for all)
        category_id: Filter by category (None for all)
        page: Page number (0-indexed)
        per_page: Items per page
        
    Returns:
        Tuple of (entries list, total count)
    """
    if per_page is None:
        per_page = settings.ITEMS_PER_PAGE
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Build WHERE clause
                conditions = []
                params = []
                
                if status:
                    conditions.append("e.status = %s")
                    params.append(status)
                
                if category_id:
                    conditions.append("e.category_id = %s")
                    params.append(category_id)
                
                where_clause = ""
                if conditions:
                    where_clause = "WHERE " + " AND ".join(conditions)
                
                # Get total count
                cursor.execute(f"""
                    SELECT COUNT(*) as count
                    FROM feedback_entries e
                    {where_clause}
                """, params)
                total = cursor.fetchone()['count']
                
                # Get entries
                offset = page * per_page
                cursor.execute(f"""
                    SELECT 
                        e.id,
                        e.user_id,
                        e.status,
                        e.created_timestamp,
                        COALESCE(c.name, 'Без категории') as category
                    FROM feedback_entries e
                    LEFT JOIN feedback_categories c ON e.category_id = c.id
                    {where_clause}
                    ORDER BY 
                        CASE e.status WHEN 'new' THEN 0 ELSE 1 END,
                        e.created_timestamp DESC
                    LIMIT %s OFFSET %s
                """, params + [per_page, offset])
                
                entries = cursor.fetchall() or []
                
                # Format dates
                for entry in entries:
                    entry['date'] = _format_timestamp(entry['created_timestamp'])
                
                return (entries, total)
                
    except Exception as e:
        logger.error("Error getting admin feedback entries: %s", e)
        return ([], 0)


def get_new_entries_count() -> int:
    """
    Get count of new (unread) feedback entries.
    
    Returns:
        Count of new entries
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM feedback_entries
                    WHERE status = %s
                """, (settings.STATUS_NEW,))
                
                return cursor.fetchone()['count']
                
    except Exception as e:
        logger.error("Error getting new entries count: %s", e)
        return 0


def create_admin_response(
    entry_id: int,
    admin_id: int,
    response_text: str
) -> bool:
    """
    Create an admin response to a feedback entry.
    NOTE: admin_id is stored but NEVER exposed to users.
    
    Args:
        entry_id: Feedback entry ID
        admin_id: Admin's Telegram user ID (stored internally only)
        response_text: Response text
        
    Returns:
        True on success, False on error
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                current_time = int(time.time())
                
                # Create response
                cursor.execute("""
                    INSERT INTO feedback_responses 
                    (entry_id, admin_id, response_text, created_timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (entry_id, admin_id, response_text, current_time))
                
                # Update entry status to in_progress if it was new
                cursor.execute("""
                    UPDATE feedback_entries
                    SET status = %s, updated_timestamp = %s
                    WHERE id = %s AND status = %s
                """, (settings.STATUS_IN_PROGRESS, current_time, entry_id, settings.STATUS_NEW))
                
                conn.commit()
                return True
                
    except Exception as e:
        logger.error("Error creating admin response: %s", e)
        return False


def update_entry_status(entry_id: int, new_status: str) -> bool:
    """
    Update feedback entry status.
    
    Args:
        entry_id: Entry ID
        new_status: New status value
        
    Returns:
        True on success, False on error
    """
    if new_status not in settings.STATUS_NAMES:
        return False
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                current_time = int(time.time())
                
                cursor.execute("""
                    UPDATE feedback_entries
                    SET status = %s, updated_timestamp = %s
                    WHERE id = %s
                """, (new_status, current_time, entry_id))
                
                conn.commit()
                return cursor.rowcount > 0
                
    except Exception as e:
        logger.error("Error updating entry status: %s", e)
        return False


def get_entry_user_id(entry_id: int) -> Optional[int]:
    """
    Get the user ID for a feedback entry (for sending notifications).
    
    Args:
        entry_id: Entry ID
        
    Returns:
        User ID or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT user_id
                    FROM feedback_entries
                    WHERE id = %s
                """, (entry_id,))
                
                result = cursor.fetchone()
                return result['user_id'] if result else None
                
    except Exception as e:
        logger.error("Error getting entry user_id: %s", e)
        return None


# ===== HELPER FUNCTIONS =====


def _format_timestamp(timestamp: int) -> str:
    """
    Format Unix timestamp to human-readable date.
    
    Args:
        timestamp: Unix timestamp
        
    Returns:
        Formatted date string (DD.MM.YYYY)
    """
    try:
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return "N/A"


def get_status_display_name(status: str) -> str:
    """
    Get human-readable status name.
    
    Args:
        status: Status key
        
    Returns:
        Display name with emoji
    """
    return settings.STATUS_NAMES.get(status, "📝 Неизвестно")
