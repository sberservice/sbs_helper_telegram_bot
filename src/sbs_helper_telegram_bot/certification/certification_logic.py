"""
Employee Certification Module - Business Logic

Contains all database operations and business logic for the certification module:
- Question and category management
- Test attempt creation and scoring
- Rankings and statistics
- Settings management
"""

import logging
import time
import random
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

import src.common.database as database
from . import settings

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Category:
    """Certification category data class."""
    id: int
    name: str
    description: Optional[str]
    display_order: int
    active: bool
    questions_count: int = 0
    created_timestamp: int = 0
    updated_timestamp: Optional[int] = None


@dataclass
class Question:
    """Certification question data class."""
    id: int
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str
    explanation: Optional[str]
    difficulty: str
    relevance_date: date
    active: bool
    categories: List[int] = None
    created_timestamp: int = 0
    updated_timestamp: Optional[int] = None


@dataclass
class TestAttempt:
    """Test attempt data class."""
    id: int
    userid: int
    category_id: Optional[int]
    total_questions: int
    correct_answers: int
    score_percent: float
    passed: bool
    time_limit_seconds: int
    time_spent_seconds: Optional[int]
    started_timestamp: int
    completed_timestamp: Optional[int]
    status: str


@dataclass
class UserRanking:
    """User ranking data class."""
    rank: int
    userid: int
    first_name: str
    last_name: Optional[str]
    username: Optional[str]
    best_score: float
    tests_count: int


# ============================================================================
# Settings Management
# ============================================================================

def get_setting(key: str, default: Any = None) -> Any:
    """
    Get a certification setting value from database.
    
    Args:
        key: Setting key
        default: Default value if not found
        
    Returns:
        Setting value or default
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT setting_value FROM certification_settings WHERE setting_key = %s",
                    (key,)
                )
                result = cursor.fetchone()
                if result:
                    return result['setting_value']
                return default
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return default


def set_setting(key: str, value: Any, description: str = None) -> bool:
    """
    Set a certification setting value in database.
    
    Args:
        key: Setting key
        value: Setting value
        description: Optional description
        
    Returns:
        True if successful
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """INSERT INTO certification_settings 
                       (setting_key, setting_value, description, updated_timestamp)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE 
                       setting_value = VALUES(setting_value),
                       description = COALESCE(VALUES(description), description),
                       updated_timestamp = VALUES(updated_timestamp)""",
                    (key, str(value), description, int(time.time()))
                )
                return True
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
        return False


def get_test_settings() -> Dict[str, int]:
    """
    Get all test configuration settings.
    
    Returns:
        Dict with questions_count, time_limit_minutes, passing_score_percent, show_correct_answer
    """
    return {
        'questions_count': int(get_setting(
            settings.DB_SETTING_QUESTIONS_COUNT, 
            settings.DEFAULT_QUESTIONS_COUNT
        )),
        'time_limit_minutes': int(get_setting(
            settings.DB_SETTING_TIME_LIMIT, 
            settings.DEFAULT_TIME_LIMIT_MINUTES
        )),
        'passing_score_percent': int(get_setting(
            settings.DB_SETTING_PASSING_SCORE, 
            settings.DEFAULT_PASSING_SCORE_PERCENT
        )),
        'show_correct_answer': get_setting(
            settings.DB_SETTING_SHOW_CORRECT,
            settings.DEFAULT_SHOW_CORRECT
        ) in (True, 'True', 'true', '1', 1),
        'obfuscate_names': get_setting(
            settings.DB_SETTING_OBFUSCATE_NAMES,
            settings.DEFAULT_OBFUSCATE_NAMES
        ) in (True, 'True', 'true', '1', 1)
    }


# ============================================================================
# Category Management
# ============================================================================

def get_all_categories(active_only: bool = False) -> List[Dict]:
    """
    Get all certification categories.
    
    Args:
        active_only: If True, return only active categories
        
    Returns:
        List of category dicts
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                query = """
                    SELECT c.*, 
                           COUNT(DISTINCT qc.question_id) as questions_count
                    FROM certification_categories c
                    LEFT JOIN certification_question_categories qc ON c.id = qc.category_id
                    LEFT JOIN certification_questions q ON qc.question_id = q.id AND q.active = 1
                """
                if active_only:
                    query += " WHERE c.active = 1"
                query += " GROUP BY c.id ORDER BY c.display_order, c.name"
                
                cursor.execute(query)
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        return []


def get_category_by_id(category_id: int) -> Optional[Dict]:
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
                cursor.execute(
                    """SELECT c.*, COUNT(DISTINCT qc.question_id) as questions_count
                       FROM certification_categories c
                       LEFT JOIN certification_question_categories qc ON c.id = qc.category_id
                       WHERE c.id = %s
                       GROUP BY c.id""",
                    (category_id,)
                )
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting category {category_id}: {e}")
        return None


def create_category(name: str, description: str = None, display_order: int = 0) -> Optional[int]:
    """
    Create a new category.
    
    Args:
        name: Category name
        description: Optional description
        display_order: Display order
        
    Returns:
        New category ID or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """INSERT INTO certification_categories 
                       (name, description, display_order, active, created_timestamp)
                       VALUES (%s, %s, %s, 1, %s)""",
                    (name, description, display_order, int(time.time()))
                )
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"Error creating category: {e}")
        return None


def update_category(category_id: int, **kwargs) -> bool:
    """
    Update a category.
    
    Args:
        category_id: Category ID
        **kwargs: Fields to update (name, description, display_order, active)
        
    Returns:
        True if successful
    """
    if not kwargs:
        return False
    
    allowed_fields = {'name', 'description', 'display_order', 'active'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    
    if not updates:
        return False
    
    updates['updated_timestamp'] = int(time.time())
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                set_clause = ", ".join(f"{k} = %s" for k in updates.keys())
                values = list(updates.values()) + [category_id]
                
                cursor.execute(
                    f"UPDATE certification_categories SET {set_clause} WHERE id = %s",
                    values
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating category {category_id}: {e}")
        return False


def delete_category(category_id: int) -> bool:
    """
    Delete a category.
    
    Args:
        category_id: Category ID
        
    Returns:
        True if successful
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "DELETE FROM certification_categories WHERE id = %s",
                    (category_id,)
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting category {category_id}: {e}")
        return False


def toggle_category_active(category_id: int) -> Optional[bool]:
    """
    Toggle category active status.
    
    Args:
        category_id: Category ID
        
    Returns:
        New active status or None on error
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """UPDATE certification_categories 
                       SET active = NOT active, updated_timestamp = %s 
                       WHERE id = %s""",
                    (int(time.time()), category_id)
                )
                if cursor.rowcount > 0:
                    cursor.execute(
                        "SELECT active FROM certification_categories WHERE id = %s",
                        (category_id,)
                    )
                    result = cursor.fetchone()
                    return bool(result['active']) if result else None
                return None
    except Exception as e:
        logger.error(f"Error toggling category {category_id}: {e}")
        return None


def update_category_field(category_id: int, field: str, value: Optional[str]) -> bool:
    """
    Update a specific field of a category.
    
    Args:
        category_id: Category ID
        field: Field name to update (name, description)
        value: New value for the field
        
    Returns:
        True on success, False on error
    """
    # Validate field name to prevent SQL injection
    allowed_fields = {'name', 'description'}
    
    if field not in allowed_fields:
        logger.error(f"Invalid field name for category update: {field}")
        return False
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""UPDATE certification_categories 
                        SET {field} = %s, updated_timestamp = %s 
                        WHERE id = %s""",
                    (value, int(time.time()), category_id)
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating category {category_id} field {field}: {e}")
        return False


# ============================================================================
# Question Management
# ============================================================================

def get_all_questions(
    active_only: bool = False,
    category_id: Optional[int] = None,
    include_outdated: bool = True
) -> List[Dict]:
    """
    Get all questions with optional filtering.
    
    Args:
        active_only: If True, return only active questions
        category_id: Filter by category ID
        include_outdated: If False, exclude questions past relevance date
        
    Returns:
        List of question dicts
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                query = """
                    SELECT DISTINCT q.*
                    FROM certification_questions q
                """
                conditions = []
                params = []
                
                if category_id:
                    query += """
                        JOIN certification_question_categories qc 
                        ON q.id = qc.question_id AND qc.category_id = %s
                    """
                    params.append(category_id)
                
                if active_only:
                    conditions.append("q.active = 1")
                
                if not include_outdated:
                    conditions.append("q.relevance_date >= CURDATE()")
                
                if conditions:
                    query += " WHERE " + " AND ".join(conditions)
                
                query += " ORDER BY q.id DESC"
                
                cursor.execute(query, params)
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting questions: {e}")
        return []


def get_question_by_id(question_id: int) -> Optional[Dict]:
    """
    Get a question by ID with its categories.
    
    Args:
        question_id: Question ID
        
    Returns:
        Question dict with categories list or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT * FROM certification_questions WHERE id = %s",
                    (question_id,)
                )
                question = cursor.fetchone()
                
                if question:
                    cursor.execute(
                        """SELECT c.id, c.name 
                           FROM certification_categories c
                           JOIN certification_question_categories qc ON c.id = qc.category_id
                           WHERE qc.question_id = %s""",
                        (question_id,)
                    )
                    question['categories'] = cursor.fetchall()
                
                return question
    except Exception as e:
        logger.error(f"Error getting question {question_id}: {e}")
        return None


def get_outdated_questions() -> List[Dict]:
    """
    Get all questions with relevance_date in the past.
    
    Returns:
        List of outdated question dicts
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """SELECT * FROM certification_questions 
                       WHERE relevance_date < CURDATE() AND active = 1
                       ORDER BY relevance_date ASC"""
                )
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting outdated questions: {e}")
        return []


def create_question(
    question_text: str,
    option_a: str,
    option_b: str,
    option_c: str,
    option_d: str,
    correct_option: str,
    explanation: str = None,
    difficulty: str = 'medium',
    relevance_months: int = None,
    relevance_date: date = None,
    category_ids: List[int] = None
) -> Optional[int]:
    """
    Create a new question.
    
    Args:
        question_text: Question text
        option_a through option_d: Answer options
        correct_option: Correct answer (A, B, C, D)
        explanation: Optional explanation
        difficulty: easy, medium, or hard
        relevance_months: Months until question becomes outdated
        relevance_date: Explicit relevance date (overrides months)
        category_ids: List of category IDs to link
        
    Returns:
        New question ID or None
    """
    if relevance_date is None:
        months = relevance_months or settings.DEFAULT_RELEVANCE_MONTHS
        relevance_date = date.today() + relativedelta(months=months)
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """INSERT INTO certification_questions 
                       (question_text, option_a, option_b, option_c, option_d,
                        correct_option, explanation, difficulty, relevance_date,
                        active, created_timestamp)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)""",
                    (question_text, option_a, option_b, option_c, option_d,
                     correct_option.upper(), explanation, difficulty,
                     relevance_date, int(time.time()))
                )
                question_id = cursor.lastrowid
                
                # Link to categories
                if category_ids:
                    for cat_id in category_ids:
                        cursor.execute(
                            """INSERT INTO certification_question_categories
                               (question_id, category_id, created_timestamp)
                               VALUES (%s, %s, %s)""",
                            (question_id, cat_id, int(time.time()))
                        )
                
                return question_id
    except Exception as e:
        logger.error(f"Error creating question: {e}")
        return None


def update_question(question_id: int, **kwargs) -> bool:
    """
    Update a question.
    
    Args:
        question_id: Question ID
        **kwargs: Fields to update
        
    Returns:
        True if successful
    """
    allowed_fields = {
        'question_text', 'option_a', 'option_b', 'option_c', 'option_d',
        'correct_option', 'explanation', 'difficulty', 'relevance_date', 'active'
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    category_ids = kwargs.get('category_ids')
    
    if not updates and category_ids is None:
        return False
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if updates:
                    updates['updated_timestamp'] = int(time.time())
                    set_clause = ", ".join(f"{k} = %s" for k in updates.keys())
                    values = list(updates.values()) + [question_id]
                    
                    cursor.execute(
                        f"UPDATE certification_questions SET {set_clause} WHERE id = %s",
                        values
                    )
                
                # Update categories if provided
                if category_ids is not None:
                    cursor.execute(
                        "DELETE FROM certification_question_categories WHERE question_id = %s",
                        (question_id,)
                    )
                    for cat_id in category_ids:
                        cursor.execute(
                            """INSERT INTO certification_question_categories
                               (question_id, category_id, created_timestamp)
                               VALUES (%s, %s, %s)""",
                            (question_id, cat_id, int(time.time()))
                        )
                
                return True
    except Exception as e:
        logger.error(f"Error updating question {question_id}: {e}")
        return False


def delete_question(question_id: int) -> bool:
    """
    Delete a question.
    
    Args:
        question_id: Question ID
        
    Returns:
        True if successful
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "DELETE FROM certification_questions WHERE id = %s",
                    (question_id,)
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting question {question_id}: {e}")
        return False


def toggle_question_active(question_id: int) -> Optional[bool]:
    """
    Toggle question active status.
    
    Args:
        question_id: Question ID
        
    Returns:
        New active status or None on error
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """UPDATE certification_questions 
                       SET active = NOT active, updated_timestamp = %s 
                       WHERE id = %s""",
                    (int(time.time()), question_id)
                )
                if cursor.rowcount > 0:
                    cursor.execute(
                        "SELECT active FROM certification_questions WHERE id = %s",
                        (question_id,)
                    )
                    result = cursor.fetchone()
                    return bool(result['active']) if result else None
                return None
    except Exception as e:
        logger.error(f"Error toggling question {question_id}: {e}")
        return None


def update_question_field(question_id: int, field: str, value: Optional[str]) -> bool:
    """
    Update a specific field of a question.
    
    Args:
        question_id: Question ID
        field: Field name to update (question_text, option_a, option_b, option_c, option_d,
               correct_option, explanation, difficulty)
        value: New value for the field
        
    Returns:
        True on success, False on error
    """
    # Validate field name to prevent SQL injection
    allowed_fields = {
        'question_text', 'option_a', 'option_b', 'option_c', 'option_d',
        'correct_option', 'explanation', 'difficulty'
    }
    
    if field not in allowed_fields:
        logger.error(f"Invalid field name for question update: {field}")
        return False
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""UPDATE certification_questions 
                        SET {field} = %s, updated_timestamp = %s 
                        WHERE id = %s""",
                    (value, int(time.time()), question_id)
                )
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating question {question_id} field {field}: {e}")
        return False


def update_question_relevance(question_id: int, months: int = None, new_date: date = None) -> bool:
    """
    Update question relevance date.
    
    Args:
        question_id: Question ID
        months: Extend by this many months from today
        new_date: Set to this specific date
        
    Returns:
        True if successful
    """
    if new_date is None:
        months = months or settings.DEFAULT_RELEVANCE_MONTHS
        new_date = date.today() + relativedelta(months=months)
    
    return update_question(question_id, relevance_date=new_date)


def update_all_outdated_relevance(months: int = None) -> int:
    """
    Update relevance date for all outdated questions.
    
    Args:
        months: Extend by this many months from today
        
    Returns:
        Number of questions updated
    """
    months = months or settings.DEFAULT_RELEVANCE_MONTHS
    new_date = date.today() + relativedelta(months=months)
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """UPDATE certification_questions 
                       SET relevance_date = %s, updated_timestamp = %s
                       WHERE relevance_date < CURDATE() AND active = 1""",
                    (new_date, int(time.time()))
                )
                return cursor.rowcount
    except Exception as e:
        logger.error(f"Error updating outdated questions: {e}")
        return 0


def search_questions(search_text: str) -> List[Dict]:
    """
    Search questions by text.
    
    Args:
        search_text: Text to search for
        
    Returns:
        List of matching question dicts
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """SELECT * FROM certification_questions 
                       WHERE question_text LIKE %s
                          OR option_a LIKE %s
                          OR option_b LIKE %s
                          OR option_c LIKE %s
                          OR option_d LIKE %s
                       ORDER BY id DESC
                       LIMIT 20""",
                    tuple([f"%{search_text}%"] * 5)
                )
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error searching questions: {e}")
        return []


# ============================================================================
# Test Attempt Management
# ============================================================================

def get_random_questions(
    count: int,
    category_id: Optional[int] = None
) -> List[Dict]:
    """
    Get random questions for a test.
    
    Args:
        count: Number of questions to get
        category_id: Optional category filter
        
    Returns:
        List of question dicts
    """
    questions = get_all_questions(
        active_only=True,
        category_id=category_id,
        include_outdated=False
    )
    
    if len(questions) <= count:
        random.shuffle(questions)
        return questions
    
    return random.sample(questions, count)


def create_test_attempt(
    userid: int,
    total_questions: int,
    time_limit_seconds: int,
    category_id: Optional[int] = None
) -> Optional[int]:
    """
    Create a new test attempt.
    
    Args:
        userid: Telegram user ID
        total_questions: Total number of questions
        time_limit_seconds: Time limit in seconds
        category_id: Optional category ID
        
    Returns:
        New attempt ID or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """INSERT INTO certification_attempts 
                       (userid, category_id, total_questions, time_limit_seconds,
                        started_timestamp, status)
                       VALUES (%s, %s, %s, %s, %s, 'in_progress')""",
                    (userid, category_id, total_questions, time_limit_seconds, int(time.time()))
                )
                return cursor.lastrowid
    except Exception as e:
        logger.error(f"Error creating test attempt: {e}")
        return None


def save_answer(
    attempt_id: int,
    question_id: int,
    question_order: int,
    user_answer: Optional[str],
    is_correct: Optional[bool]
) -> bool:
    """
    Save a user's answer to a question.
    
    Args:
        attempt_id: Attempt ID
        question_id: Question ID
        question_order: Order in test (1-based)
        user_answer: User's answer (A, B, C, D) or None if timed out
        is_correct: Whether answer was correct
        
    Returns:
        True if successful
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """INSERT INTO certification_answers 
                       (attempt_id, question_id, question_order, user_answer, 
                        is_correct, answered_timestamp)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                       user_answer = VALUES(user_answer),
                       is_correct = VALUES(is_correct),
                       answered_timestamp = VALUES(answered_timestamp)""",
                    (attempt_id, question_id, question_order, user_answer,
                     is_correct, int(time.time()) if user_answer else None)
                )
                return True
    except Exception as e:
        logger.error(f"Error saving answer: {e}")
        return False


def complete_test_attempt(
    attempt_id: int,
    status: str = 'completed'
) -> Optional[Dict]:
    """
    Complete a test attempt and calculate results.
    
    Args:
        attempt_id: Attempt ID
        status: Final status ('completed', 'expired', 'cancelled')
        
    Returns:
        Dict with results or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get attempt info
                cursor.execute(
                    "SELECT * FROM certification_attempts WHERE id = %s",
                    (attempt_id,)
                )
                attempt = cursor.fetchone()
                
                if not attempt:
                    return None
                
                # Count correct answers
                cursor.execute(
                    """SELECT COUNT(*) as correct_count 
                       FROM certification_answers 
                       WHERE attempt_id = %s AND is_correct = 1""",
                    (attempt_id,)
                )
                result = cursor.fetchone()
                correct_answers = result['correct_count'] if result else 0
                
                # Calculate score
                total_questions = attempt['total_questions']
                score_percent = (correct_answers / total_questions * 100) if total_questions > 0 else 0
                
                # Get passing score
                test_settings = get_test_settings()
                passed = score_percent >= test_settings['passing_score_percent']
                
                # Calculate time spent
                completed_timestamp = int(time.time())
                time_spent = completed_timestamp - attempt['started_timestamp']
                
                # Update attempt
                cursor.execute(
                    """UPDATE certification_attempts 
                       SET correct_answers = %s,
                           score_percent = %s,
                           passed = %s,
                           time_spent_seconds = %s,
                           completed_timestamp = %s,
                           status = %s
                       WHERE id = %s""",
                    (correct_answers, score_percent, passed, time_spent,
                     completed_timestamp, status, attempt_id)
                )
                
                return {
                    'attempt_id': attempt_id,
                    'correct_answers': correct_answers,
                    'total_questions': total_questions,
                    'score_percent': round(score_percent, 2),
                    'passed': passed,
                    'time_spent_seconds': time_spent,
                    'status': status
                }
    except Exception as e:
        logger.error(f"Error completing test attempt: {e}")
        return None


def get_attempt_by_id(attempt_id: int) -> Optional[Dict]:
    """
    Get a test attempt by ID.
    
    Args:
        attempt_id: Attempt ID
        
    Returns:
        Attempt dict or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT * FROM certification_attempts WHERE id = %s",
                    (attempt_id,)
                )
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting attempt {attempt_id}: {e}")
        return None


def get_user_in_progress_attempt(userid: int) -> Optional[Dict]:
    """
    Get user's current in-progress attempt if any.
    
    Args:
        userid: Telegram user ID
        
    Returns:
        Attempt dict or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """SELECT * FROM certification_attempts 
                       WHERE userid = %s AND status = 'in_progress'
                       ORDER BY started_timestamp DESC LIMIT 1""",
                    (userid,)
                )
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting in-progress attempt: {e}")
        return None


def cancel_user_attempts(userid: int) -> int:
    """
    Cancel all in-progress attempts for a user.
    
    Args:
        userid: Telegram user ID
        
    Returns:
        Number of cancelled attempts
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """UPDATE certification_attempts 
                       SET status = 'cancelled', completed_timestamp = %s
                       WHERE userid = %s AND status = 'in_progress'""",
                    (int(time.time()), userid)
                )
                return cursor.rowcount
    except Exception as e:
        logger.error(f"Error cancelling attempts: {e}")
        return 0


# ============================================================================
# Rankings and Statistics
# ============================================================================

def get_user_test_history(userid: int, limit: int = 10) -> List[Dict]:
    """
    Get user's test history.
    
    Args:
        userid: Telegram user ID
        limit: Maximum number of records
        
    Returns:
        List of attempt dicts
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """SELECT a.*, c.name as category_name
                       FROM certification_attempts a
                       LEFT JOIN certification_categories c ON a.category_id = c.id
                       WHERE a.userid = %s AND a.status IN ('completed', 'expired')
                       ORDER BY a.completed_timestamp DESC
                       LIMIT %s""",
                    (userid, limit)
                )
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting user history: {e}")
        return []


def get_user_stats(userid: int) -> Optional[Dict]:
    """
    Get user's overall statistics.
    
    Args:
        userid: Telegram user ID
        
    Returns:
        Dict with stats or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """SELECT 
                           COUNT(*) as total_tests,
                           SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) as passed_tests,
                           MAX(score_percent) as best_score,
                           MAX(completed_timestamp) as last_test_timestamp
                       FROM certification_attempts 
                       WHERE userid = %s AND status IN ('completed', 'expired')""",
                    (userid,)
                )
                result = cursor.fetchone()
                
                if result and result['total_tests'] > 0:
                    # Get last test details
                    cursor.execute(
                        """SELECT score_percent, completed_timestamp
                           FROM certification_attempts 
                           WHERE userid = %s AND status IN ('completed', 'expired')
                           ORDER BY completed_timestamp DESC LIMIT 1""",
                        (userid,)
                    )
                    last_test = cursor.fetchone()
                    
                    return {
                        'total_tests': result['total_tests'],
                        'passed_tests': result['passed_tests'] or 0,
                        'best_score': float(result['best_score']) if result['best_score'] else 0,
                        'last_test_timestamp': last_test['completed_timestamp'] if last_test else None,
                        'last_test_score': float(last_test['score_percent']) if last_test else None
                    }
                return None
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return None


def get_monthly_ranking(
    year: int = None,
    month: int = None,
    limit: int = 10
) -> List[Dict]:
    """
    Get monthly ranking of top users.
    
    Args:
        year: Year (default: current)
        month: Month (default: current)
        limit: Maximum number of users
        
    Returns:
        List of ranking dicts
    """
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    
    # Calculate month start and end timestamps
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)
    
    start_ts = int(month_start.timestamp())
    end_ts = int(month_end.timestamp())
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """SELECT 
                           a.userid,
                           u.first_name,
                           u.last_name,
                           u.username,
                           MAX(a.score_percent) as best_score,
                           COUNT(*) as tests_count
                       FROM certification_attempts a
                       JOIN users u ON a.userid = u.userid
                       WHERE a.status = 'completed'
                         AND a.passed = 1
                         AND a.completed_timestamp >= %s
                         AND a.completed_timestamp < %s
                       GROUP BY a.userid
                       ORDER BY best_score DESC, tests_count DESC
                       LIMIT %s""",
                    (start_ts, end_ts, limit)
                )
                results = cursor.fetchall()
                
                # Add rank numbers
                for i, row in enumerate(results, 1):
                    row['rank'] = i
                
                return results
    except Exception as e:
        logger.error(f"Error getting monthly ranking: {e}")
        return []


def get_user_monthly_rank(
    userid: int,
    year: int = None,
    month: int = None
) -> Optional[Dict]:
    """
    Get user's rank in monthly ranking.
    
    Args:
        userid: Telegram user ID
        year: Year (default: current)
        month: Month (default: current)
        
    Returns:
        Dict with rank info or None if not in ranking
    """
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)
    
    start_ts = int(month_start.timestamp())
    end_ts = int(month_end.timestamp())
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get user's best score this month
                cursor.execute(
                    """SELECT MAX(score_percent) as best_score, COUNT(*) as tests_count
                       FROM certification_attempts
                       WHERE userid = %s
                         AND status = 'completed'
                         AND passed = 1
                         AND completed_timestamp >= %s
                         AND completed_timestamp < %s""",
                    (userid, start_ts, end_ts)
                )
                user_result = cursor.fetchone()
                
                if not user_result or user_result['best_score'] is None:
                    return None
                
                # Count users with higher score
                cursor.execute(
                    """SELECT COUNT(DISTINCT userid) as higher_count
                       FROM certification_attempts
                       WHERE status = 'completed'
                         AND passed = 1
                         AND completed_timestamp >= %s
                         AND completed_timestamp < %s
                         AND userid != %s
                       GROUP BY userid
                       HAVING MAX(score_percent) > %s""",
                    (start_ts, end_ts, userid, user_result['best_score'])
                )
                
                # User's rank is higher_count + 1
                higher = cursor.fetchall()
                rank = len(higher) + 1
                
                return {
                    'rank': rank,
                    'best_score': float(user_result['best_score']),
                    'tests_count': user_result['tests_count']
                }
    except Exception as e:
        logger.error(f"Error getting user rank: {e}")
        return None


def get_monthly_ranking_by_category(
    category_id: Optional[int] = None,
    year: int = None,
    month: int = None,
    limit: int = 10
) -> List[Dict]:
    """
    Get monthly ranking filtered by category.
    
    Args:
        category_id: Category ID to filter by. None for all tests combined (full test).
                     Use "all" string converted to handle all attempts.
        year: Year (default: current)
        month: Month (default: current)
        limit: Maximum number of users
        
    Returns:
        List of ranking dicts
    """
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    
    # Calculate month start and end timestamps
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)
    
    start_ts = int(month_start.timestamp())
    end_ts = int(month_end.timestamp())
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if category_id is None:
                    # Combined top - all tests regardless of category
                    cursor.execute(
                        """SELECT 
                               a.userid,
                               u.first_name,
                               u.last_name,
                               u.username,
                               MAX(a.score_percent) as best_score,
                               COUNT(*) as tests_count
                           FROM certification_attempts a
                           JOIN users u ON a.userid = u.userid
                           WHERE a.status = 'completed'
                             AND a.passed = 1
                             AND a.completed_timestamp >= %s
                             AND a.completed_timestamp < %s
                           GROUP BY a.userid
                           ORDER BY best_score DESC, tests_count DESC
                           LIMIT %s""",
                        (start_ts, end_ts, limit)
                    )
                else:
                    # Filter by specific category
                    cursor.execute(
                        """SELECT 
                               a.userid,
                               u.first_name,
                               u.last_name,
                               u.username,
                               MAX(a.score_percent) as best_score,
                               COUNT(*) as tests_count
                           FROM certification_attempts a
                           JOIN users u ON a.userid = u.userid
                           WHERE a.status = 'completed'
                             AND a.passed = 1
                             AND a.completed_timestamp >= %s
                             AND a.completed_timestamp < %s
                             AND a.category_id = %s
                           GROUP BY a.userid
                           ORDER BY best_score DESC, tests_count DESC
                           LIMIT %s""",
                        (start_ts, end_ts, category_id, limit)
                    )
                
                results = cursor.fetchall()
                
                # Add rank numbers
                for i, row in enumerate(results, 1):
                    row['rank'] = i
                
                return results
    except Exception as e:
        logger.error(f"Error getting monthly ranking by category: {e}")
        return []


def get_user_monthly_rank_by_category(
    userid: int,
    category_id: Optional[int] = None,
    year: int = None,
    month: int = None
) -> Optional[Dict]:
    """
    Get user's rank in monthly ranking for a specific category.
    
    Args:
        userid: Telegram user ID
        category_id: Category ID to filter by. None for all tests combined.
        year: Year (default: current)
        month: Month (default: current)
        
    Returns:
        Dict with rank info or None if not in ranking
    """
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)
    
    start_ts = int(month_start.timestamp())
    end_ts = int(month_end.timestamp())
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get user's best score this month for the category
                if category_id is None:
                    cursor.execute(
                        """SELECT MAX(score_percent) as best_score, COUNT(*) as tests_count
                           FROM certification_attempts
                           WHERE userid = %s
                             AND status = 'completed'
                             AND passed = 1
                             AND completed_timestamp >= %s
                             AND completed_timestamp < %s""",
                        (userid, start_ts, end_ts)
                    )
                else:
                    cursor.execute(
                        """SELECT MAX(score_percent) as best_score, COUNT(*) as tests_count
                           FROM certification_attempts
                           WHERE userid = %s
                             AND status = 'completed'
                             AND passed = 1
                             AND completed_timestamp >= %s
                             AND completed_timestamp < %s
                             AND category_id = %s""",
                        (userid, start_ts, end_ts, category_id)
                    )
                
                user_result = cursor.fetchone()
                
                if not user_result or user_result['best_score'] is None:
                    return None
                
                # Count users with higher score in this category
                if category_id is None:
                    cursor.execute(
                        """SELECT COUNT(DISTINCT userid) as higher_count
                           FROM certification_attempts
                           WHERE status = 'completed'
                             AND passed = 1
                             AND completed_timestamp >= %s
                             AND completed_timestamp < %s
                             AND userid != %s
                           GROUP BY userid
                           HAVING MAX(score_percent) > %s""",
                        (start_ts, end_ts, userid, user_result['best_score'])
                    )
                else:
                    cursor.execute(
                        """SELECT COUNT(DISTINCT userid) as higher_count
                           FROM certification_attempts
                           WHERE status = 'completed'
                             AND passed = 1
                             AND completed_timestamp >= %s
                             AND completed_timestamp < %s
                             AND userid != %s
                             AND category_id = %s
                           GROUP BY userid
                           HAVING MAX(score_percent) > %s""",
                        (start_ts, end_ts, userid, category_id, user_result['best_score'])
                    )
                
                higher = cursor.fetchall()
                rank = len(higher) + 1
                
                return {
                    'rank': rank,
                    'best_score': float(user_result['best_score']),
                    'tests_count': user_result['tests_count']
                }
    except Exception as e:
        logger.error(f"Error getting user rank by category: {e}")
        return None


def get_user_categories_this_month(
    userid: int,
    year: int = None,
    month: int = None
) -> List[Dict]:
    """
    Get list of categories where user has completed tests this month.
    Includes stats for each category.
    
    Args:
        userid: Telegram user ID
        year: Year (default: current)
        month: Month (default: current)
        
    Returns:
        List of dicts with category info and user stats
    """
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)
    
    start_ts = int(month_start.timestamp())
    end_ts = int(month_end.timestamp())
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get categories where user has attempts this month
                cursor.execute(
                    """SELECT 
                           a.category_id,
                           c.name as category_name,
                           MAX(a.score_percent) as best_score,
                           COUNT(*) as tests_count,
                           SUM(CASE WHEN a.passed = 1 THEN 1 ELSE 0 END) as passed_count
                       FROM certification_attempts a
                       LEFT JOIN certification_categories c ON a.category_id = c.id
                       WHERE a.userid = %s
                         AND a.status = 'completed'
                         AND a.completed_timestamp >= %s
                         AND a.completed_timestamp < %s
                       GROUP BY a.category_id
                       ORDER BY c.display_order, c.name""",
                    (userid, start_ts, end_ts)
                )
                
                results = cursor.fetchall()
                
                # Add rank for each category
                for row in results:
                    rank_info = get_user_monthly_rank_by_category(
                        userid, 
                        row['category_id'], 
                        year, 
                        month
                    )
                    row['rank'] = rank_info['rank'] if rank_info else None
                
                return results
    except Exception as e:
        logger.error(f"Error getting user categories this month: {e}")
        return []


def get_user_stats_by_category(userid: int, category_id: Optional[int] = None) -> Optional[Dict]:
    """
    Get user's statistics for a specific category.
    
    Args:
        userid: Telegram user ID
        category_id: Category ID to filter by. None for all tests combined.
        
    Returns:
        Dict with stats or None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if category_id is None:
                    cursor.execute(
                        """SELECT 
                               COUNT(*) as total_tests,
                               SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) as passed_tests,
                               MAX(score_percent) as best_score,
                               MAX(completed_timestamp) as last_test_timestamp
                           FROM certification_attempts 
                           WHERE userid = %s AND status IN ('completed', 'expired')""",
                        (userid,)
                    )
                else:
                    cursor.execute(
                        """SELECT 
                               COUNT(*) as total_tests,
                               SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) as passed_tests,
                               MAX(score_percent) as best_score,
                               MAX(completed_timestamp) as last_test_timestamp
                           FROM certification_attempts 
                           WHERE userid = %s AND status IN ('completed', 'expired')
                             AND category_id = %s""",
                        (userid, category_id)
                    )
                
                result = cursor.fetchone()
                
                if result and result['total_tests'] > 0:
                    return {
                        'total_tests': result['total_tests'],
                        'passed_tests': result['passed_tests'] or 0,
                        'best_score': float(result['best_score']) if result['best_score'] else 0,
                        'last_test_timestamp': result['last_test_timestamp']
                    }
                return None
    except Exception as e:
        logger.error(f"Error getting user stats by category: {e}")
        return None


# ============================================================================
# Utility Functions
# ============================================================================

def format_time_remaining(seconds: int) -> str:
    """
    Format remaining time as MM:SS.
    
    Args:
        seconds: Remaining seconds
        
    Returns:
        Formatted time string
    """
    if seconds <= 0:
        return "00:00"
    
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def format_time_spent(seconds: int) -> str:
    """
    Format time spent as human-readable string.
    Escaped for MarkdownV2.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string (MarkdownV2 escaped)
    """
    if seconds < 60:
        return f"{seconds} сек\\."
    
    minutes = seconds // 60
    secs = seconds % 60
    
    if minutes < 60:
        return f"{minutes} мин\\. {secs} сек\\."
    
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours} ч\\. {mins} мин\\."


def get_month_name(month: int) -> str:
    """
    Get Russian month name.
    
    Args:
        month: Month number (1-12)
        
    Returns:
        Russian month name
    """
    months = {
        1: "январь", 2: "февраль", 3: "март", 4: "апрель",
        5: "май", 6: "июнь", 7: "июль", 8: "август",
        9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
    }
    return months.get(month, str(month))


def escape_markdown(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    result = str(text)
    for char in special_chars:
        result = result.replace(char, f'\\{char}')
    return result


def get_questions_count() -> int:
    """
    Get total count of active questions.
    
    Returns:
        Number of active questions
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """SELECT COUNT(*) as cnt FROM certification_questions 
                       WHERE active = 1 AND relevance_date >= CURDATE()"""
                )
                result = cursor.fetchone()
                return result['cnt'] if result else 0
    except Exception as e:
        logger.error(f"Error counting questions: {e}")
        return 0


def get_certification_statistics() -> Dict[str, Any]:
    """
    Get comprehensive certification statistics.
    
    Returns:
        Dict with total_questions, total_categories, active_categories,
        and categories_stats (list of category names with question counts)
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Get total active questions count
                cursor.execute(
                    """SELECT COUNT(*) as cnt FROM certification_questions 
                       WHERE active = 1 AND relevance_date >= CURDATE()"""
                )
                total_questions = cursor.fetchone()['cnt'] or 0
                
                # Get total and active categories count
                cursor.execute("SELECT COUNT(*) as total FROM certification_categories")
                total_categories = cursor.fetchone()['total'] or 0
                
                cursor.execute("SELECT COUNT(*) as active FROM certification_categories WHERE active = 1")
                active_categories = cursor.fetchone()['active'] or 0
                
                # Get questions per category
                cursor.execute("""
                    SELECT c.id, c.name, c.active,
                           COUNT(DISTINCT CASE 
                               WHEN q.active = 1 AND q.relevance_date >= CURDATE() 
                               THEN q.id 
                           END) as questions_count
                    FROM certification_categories c
                    LEFT JOIN certification_question_categories qc ON c.id = qc.category_id
                    LEFT JOIN certification_questions q ON qc.question_id = q.id
                    GROUP BY c.id, c.name, c.active
                    ORDER BY c.display_order, c.name
                """)
                categories_stats = cursor.fetchall()
                
                return {
                    'total_questions': total_questions,
                    'total_categories': total_categories,
                    'active_categories': active_categories,
                    'categories_stats': categories_stats
                }
    except Exception as e:
        logger.error(f"Error getting certification statistics: {e}")
        return {
            'total_questions': 0,
            'total_categories': 0,
            'active_categories': 0,
            'categories_stats': []
        }
