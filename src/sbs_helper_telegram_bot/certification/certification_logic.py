"""
Модуль аттестации сотрудников — бизнес-логика

Содержит операции с БД и бизнес-логику модуля аттестации:
- Управление вопросами и категориями
- Создание попыток и расчёт результатов
- Рейтинги и статистика
- Управление настройками
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

CERTIFICATION_RANKS = [
    {
        'name': 'Новичок',
        'icon': '🌱',
        'min_points': 0,
    },
    {
        'name': 'Практик',
        'icon': '📘',
        'min_points': 80,
    },
    {
        'name': 'Специалист',
        'icon': '⭐',
        'min_points': 180,
    },
    {
        'name': 'Эксперт',
        'icon': '🏅',
        'min_points': 320,
    },
    {
        'name': 'Мастер аттестации',
        'icon': '👑',
        'min_points': 500,
    },
]

QUESTION_DIFFICULTY_ORDER = ['easy', 'medium', 'hard']


# ============================================================================
# Классы данных
# ============================================================================

@dataclass
class Category:
    """Класс данных категории аттестации."""
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
    """Класс данных вопроса аттестации."""
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
    """Класс данных попытки теста."""
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
    """Класс данных рейтинга пользователя."""
    rank: int
    userid: int
    first_name: str
    last_name: Optional[str]
    username: Optional[str]
    best_score: float
    tests_count: int


# ============================================================================
# Управление настройками
# ============================================================================

def get_setting(key: str, default: Any = None) -> Any:
    """
    Получить значение настройки аттестации из БД.
    
    Аргументы:
        key: Ключ настройки
        default: Значение по умолчанию, если запись не найдена
        
    Возвращает:
        Значение настройки или default
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
    Установить значение настройки аттестации в БД.
    
    Аргументы:
        key: Ключ настройки
        value: Значение настройки
        description: Необязательное описание
        
    Возвращает:
        True при успехе
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
    Получить все настройки теста.
    
    Возвращает:
        Словарь с questions_count, time_limit_minutes, passing_score_percent, show_correct_answer
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
# Управление категориями
# ============================================================================

def get_all_categories(active_only: bool = False) -> List[Dict]:
    """
    Получить все категории аттестации.
    
    Аргументы:
        active_only: Если True, вернуть только активные категории
        
    Возвращает:
        Список словарей категорий
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
    Получить категорию по ID.
    
    Аргументы:
        category_id: ID категории
        
    Возвращает:
        Словарь категории или None
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
    Создать новую категорию.
    
    Аргументы:
        name: Название категории
        description: Описание (необязательно)
        display_order: Порядок отображения
        
    Возвращает:
        ID новой категории или None
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
    Обновить категорию.
    
    Аргументы:
        category_id: ID категории
        **kwargs: Поля для обновления (name, description, display_order, active)
        
    Возвращает:
        True при успехе
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
    Удалить категорию.
    
    Аргументы:
        category_id: ID категории
        
    Возвращает:
        True при успехе
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
    Переключить статус активности категории.
    
    Аргументы:
        category_id: ID категории
        
    Возвращает:
        Новый статус активности или None при ошибке
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
    Обновить конкретное поле категории.
    
    Аргументы:
        category_id: ID категории
        field: Имя поля (name, description)
        value: Новое значение поля
        
    Возвращает:
        True при успехе, False при ошибке
    """
    # Проверить имя поля для защиты от SQL-инъекций
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
# Управление вопросами
# ============================================================================

def get_all_questions(
    active_only: bool = False,
    category_id: Optional[int] = None,
    include_outdated: bool = True,
    difficulty: Optional[str] = None
) -> List[Dict]:
    """
    Получить все вопросы с дополнительными фильтрами.
    
    Аргументы:
        active_only: Если True, вернуть только активные вопросы
        category_id: Фильтр по ID категории
        include_outdated: Если False, исключить устаревшие вопросы
        difficulty: Необязательный фильтр сложности (easy, medium, hard)
        
    Возвращает:
        Список словарей вопросов
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

                if difficulty:
                    conditions.append("q.difficulty = %s")
                    params.append(difficulty)
                
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
    Получить вопрос по ID вместе со списком категорий.
    
    Аргументы:
        question_id: ID вопроса
        
    Возвращает:
        Словарь вопроса с категориями или None
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
    Получить все вопросы с истёкшей датой актуальности.
    
    Возвращает:
        Список словарей устаревших вопросов
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
    Создать новый вопрос.
    
    Аргументы:
        question_text: Текст вопроса
        option_a–option_d: Варианты ответа
        correct_option: Правильный ответ (A, B, C, D)
        explanation: Пояснение (необязательно)
        difficulty: easy, medium или hard
        relevance_months: Количество месяцев до устаревания
        relevance_date: Явная дата актуальности (переопределяет months)
        category_ids: Список ID категорий для привязки
        
    Возвращает:
        ID нового вопроса или None
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
                
                # Привязать к категориям
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
    Обновить вопрос.
    
    Аргументы:
        question_id: ID вопроса
        **kwargs: Поля для обновления
        
    Возвращает:
        True при успехе
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
                
                # Обновить категории при необходимости
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
    Удалить вопрос.
    
    Аргументы:
        question_id: ID вопроса
        
    Возвращает:
        True при успехе
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
    Переключить статус активности вопроса.
    
    Аргументы:
        question_id: ID вопроса
        
    Возвращает:
        Новый статус активности или None при ошибке
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
    Обновить конкретное поле вопроса.
    
    Аргументы:
        question_id: ID вопроса
        field: Имя поля (question_text, option_a, option_b, option_c, option_d,
               correct_option, explanation, difficulty)
        value: Новое значение поля
        
    Возвращает:
        True при успехе, False при ошибке
    """
    # Проверить имя поля для защиты от SQL-инъекций
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
    Обновить дату актуальности вопроса.
    
    Аргументы:
        question_id: ID вопроса
        months: Продлить на указанное число месяцев от текущей даты
        new_date: Установить конкретную дату
        
    Возвращает:
        True при успехе
    """
    if new_date is None:
        months = months or settings.DEFAULT_RELEVANCE_MONTHS
        new_date = date.today() + relativedelta(months=months)
    
    return update_question(question_id, relevance_date=new_date)


def update_all_outdated_relevance(months: int = None) -> int:
    """
    Обновить дату актуальности для всех устаревших вопросов.
    
    Аргументы:
        months: Продлить на указанное число месяцев от текущей даты
        
    Возвращает:
        Количество обновлённых вопросов
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
    Поиск вопросов по тексту.
    
    Аргументы:
        search_text: Текст для поиска
        
    Возвращает:
        Список подходящих вопросов
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


def get_uncategorized_questions() -> List[Dict]:
    """
    Получить все вопросы без категорий.
    
    Возвращает:
        Список вопросов без привязки к категориям
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """SELECT q.* FROM certification_questions q
                       LEFT JOIN certification_question_categories qc ON q.id = qc.question_id
                       WHERE qc.question_id IS NULL
                       ORDER BY q.id DESC"""
                )
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting uncategorized questions: {e}")
        return []


# ============================================================================
# Управление попытками теста
# ============================================================================

def get_random_questions(
    count: int,
    category_id: Optional[int] = None,
    difficulty: Optional[str] = None
) -> List[Dict]:
    """
    Получить случайные вопросы для теста.
    
    Аргументы:
        count: Количество вопросов
        category_id: Фильтр по категории (необязательно)
        difficulty: Фильтр сложности (easy, medium, hard)
        
    Возвращает:
        Список вопросов
    """
    questions = get_all_questions(
        active_only=True,
        category_id=category_id,
        include_outdated=False,
        difficulty=difficulty
    )
    
    if len(questions) <= count:
        random.shuffle(questions)
        return questions
    
    return random.sample(questions, count)


def _calculate_difficulty_targets(count: int) -> Dict[str, int]:
    """
    Рассчитать целевые квоты по сложностям с равномерным распределением.

    Аргументы:
        count: Общее количество вопросов в тесте

    Возвращает:
        Словарь с целевыми квотами easy/medium/hard
    """
    if count <= 0:
        return {difficulty: 0 for difficulty in QUESTION_DIFFICULTY_ORDER}

    base = count // len(QUESTION_DIFFICULTY_ORDER)
    remainder = count % len(QUESTION_DIFFICULTY_ORDER)

    targets = {difficulty: base for difficulty in QUESTION_DIFFICULTY_ORDER}

    for index in range(remainder):
        targets[QUESTION_DIFFICULTY_ORDER[index]] += 1

    return targets


def build_fair_test_questions(
    count: int,
    category_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Получить набор вопросов для теста с целевым балансом 33/33/33 по сложности.

    Аргументы:
        count: Требуемое количество вопросов
        category_id: Фильтр по категории (необязательно)

    Возвращает:
        Словарь с полями questions, target_distribution, actual_distribution,
        fallback_used, requested_count, selected_count
    """
    target_distribution = _calculate_difficulty_targets(count)
    if count <= 0:
        return {
            'questions': [],
            'target_distribution': target_distribution,
            'actual_distribution': {difficulty: 0 for difficulty in QUESTION_DIFFICULTY_ORDER},
            'fallback_used': False,
            'requested_count': count,
            'selected_count': 0,
        }

    pools: Dict[str, List[Dict]] = {}
    for difficulty in QUESTION_DIFFICULTY_ORDER:
        pools[difficulty] = get_all_questions(
            active_only=True,
            category_id=category_id,
            include_outdated=False,
            difficulty=difficulty
        )

    selected_questions: List[Dict] = []
    selected_ids = set()
    actual_distribution = {difficulty: 0 for difficulty in QUESTION_DIFFICULTY_ORDER}

    for difficulty in QUESTION_DIFFICULTY_ORDER:
        target_count = target_distribution[difficulty]
        available = pools[difficulty]
        take_count = min(target_count, len(available))
        if take_count <= 0:
            continue

        chosen = random.sample(available, take_count)
        selected_questions.extend(chosen)
        selected_ids.update(question['id'] for question in chosen)
        actual_distribution[difficulty] = take_count

    fallback_used = len(selected_questions) < count
    if fallback_used:
        fallback_pool: List[Dict] = []
        for difficulty in QUESTION_DIFFICULTY_ORDER:
            for question in pools[difficulty]:
                if question['id'] not in selected_ids:
                    fallback_pool.append(question)

        missing = count - len(selected_questions)
        if fallback_pool and missing > 0:
            add_count = min(missing, len(fallback_pool))
            additional_questions = random.sample(fallback_pool, add_count)
            selected_questions.extend(additional_questions)
            for question in additional_questions:
                selected_ids.add(question['id'])
                question_difficulty = question.get('difficulty', 'medium')
                if question_difficulty not in actual_distribution:
                    actual_distribution[question_difficulty] = 0
                actual_distribution[question_difficulty] += 1

    random.shuffle(selected_questions)

    logger.info(
        "Fair test distribution built: requested=%s, selected=%s, category_id=%s, target=%s, actual=%s, fallback_used=%s",
        count,
        len(selected_questions),
        category_id,
        target_distribution,
        actual_distribution,
        fallback_used,
    )

    return {
        'questions': selected_questions,
        'target_distribution': target_distribution,
        'actual_distribution': actual_distribution,
        'fallback_used': fallback_used,
        'requested_count': count,
        'selected_count': len(selected_questions),
    }


def _get_certification_rank_by_points(points: int) -> Dict[str, Any]:
    """
    Получить данные ранга по количеству сертификационных баллов.

    Аргументы:
        points: Количество сертификационных баллов

    Возвращает:
        Словарь с текущим и следующим рангом, а также прогрессом
    """
    current_rank = CERTIFICATION_RANKS[0]
    next_rank = None

    for rank in CERTIFICATION_RANKS:
        if points >= rank['min_points']:
            current_rank = rank
            continue
        next_rank = rank
        break

    points_to_next = None
    progress_percent = 100
    if next_rank:
        points_to_next = max(next_rank['min_points'] - points, 0)
        current_floor = current_rank['min_points']
        next_floor = next_rank['min_points']
        denominator = max(next_floor - current_floor, 1)
        progress_percent = int(min(max(((points - current_floor) / denominator) * 100, 0), 100))

    return {
        'rank_name': current_rank['name'],
        'rank_icon': current_rank['icon'],
        'next_rank_name': next_rank['name'] if next_rank else None,
        'next_rank_icon': next_rank['icon'] if next_rank else None,
        'next_rank_threshold': next_rank['min_points'] if next_rank else None,
        'points_to_next_rank': points_to_next,
        'rank_progress_percent': progress_percent,
    }


def get_user_certification_summary(userid: int) -> Dict[str, Any]:
    """
    Получить единый профиль достижений и ранга пользователя по аттестации.

    Аргументы:
        userid: Telegram ID пользователя

    Возвращает:
        Словарь с метриками passed тестов/категорий и сертификационным рангом
    """
    default = {
        'passed_tests_count': 0,
        'passed_categories_count': 0,
        'certification_points': 0,
        'rank_name': CERTIFICATION_RANKS[0]['name'],
        'rank_icon': CERTIFICATION_RANKS[0]['icon'],
        'next_rank_name': CERTIFICATION_RANKS[1]['name'],
        'next_rank_icon': CERTIFICATION_RANKS[1]['icon'],
        'next_rank_threshold': CERTIFICATION_RANKS[1]['min_points'],
        'points_to_next_rank': CERTIFICATION_RANKS[1]['min_points'],
        'rank_progress_percent': 0,
        'last_passed_score': None,
        'last_passed_timestamp': None,
    }

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as passed_tests_count,
                        COUNT(DISTINCT category_id) as passed_categories_count,
                        MAX(completed_timestamp) as last_passed_timestamp,
                        (
                            SELECT a2.score_percent
                            FROM certification_attempts a2
                            WHERE a2.userid = %s
                              AND a2.status = 'completed'
                              AND a2.passed = 1
                            ORDER BY a2.completed_timestamp DESC
                            LIMIT 1
                        ) as last_passed_score
                    FROM certification_attempts a
                    WHERE a.userid = %s
                      AND a.status = 'completed'
                      AND a.passed = 1
                    """,
                    (userid, userid)
                )
                result = cursor.fetchone() or {}

        passed_tests_count = int(result.get('passed_tests_count') or 0)
        passed_categories_count = int(result.get('passed_categories_count') or 0)

        certification_points = passed_tests_count * 10 + passed_categories_count * 40
        rank_data = _get_certification_rank_by_points(certification_points)

        summary = {
            'passed_tests_count': passed_tests_count,
            'passed_categories_count': passed_categories_count,
            'certification_points': certification_points,
            'last_passed_score': float(result['last_passed_score']) if result.get('last_passed_score') is not None else None,
            'last_passed_timestamp': result.get('last_passed_timestamp'),
        }
        summary.update(rank_data)
        return summary
    except Exception as e:
        logger.error("Error getting certification summary for user %s: %s", userid, e)
        return default


def create_test_attempt(
    userid: int,
    total_questions: int,
    time_limit_seconds: int,
    category_id: Optional[int] = None
) -> Optional[int]:
    """
    Создать новую попытку теста.
    
    Аргументы:
        userid: Telegram ID пользователя
        total_questions: Общее количество вопросов
        time_limit_seconds: Лимит времени в секундах
        category_id: ID категории (необязательно)
        
    Возвращает:
        ID новой попытки или None
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
    Сохранить ответ пользователя на вопрос.
    
    Аргументы:
        attempt_id: ID попытки
        question_id: ID вопроса
        question_order: Порядок вопроса в тесте (с 1)
        user_answer: Ответ пользователя (A, B, C, D) или None при таймауте
        is_correct: Был ли ответ правильным
        
    Возвращает:
        True при успехе
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
    Завершить попытку теста и рассчитать результат.
    
    Аргументы:
        attempt_id: ID попытки
        status: Итоговый статус ('completed', 'expired', 'cancelled')
        
    Возвращает:
        Словарь с результатом или None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получить данные попытки
                cursor.execute(
                    "SELECT * FROM certification_attempts WHERE id = %s",
                    (attempt_id,)
                )
                attempt = cursor.fetchone()
                
                if not attempt:
                    return None
                
                # Посчитать правильные ответы
                cursor.execute(
                    """SELECT COUNT(*) as correct_count 
                       FROM certification_answers 
                       WHERE attempt_id = %s AND is_correct = 1""",
                    (attempt_id,)
                )
                result = cursor.fetchone()
                correct_answers = result['correct_count'] if result else 0
                
                # Рассчитать результат
                total_questions = attempt['total_questions']
                score_percent = (correct_answers / total_questions * 100) if total_questions > 0 else 0
                
                # Получить проходной балл
                test_settings = get_test_settings()
                passed = score_percent >= test_settings['passing_score_percent']
                
                # Рассчитать затраченное время
                completed_timestamp = int(time.time())
                time_spent = completed_timestamp - attempt['started_timestamp']
                
                # Обновить попытку
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
    Получить попытку теста по ID.
    
    Аргументы:
        attempt_id: ID попытки
        
    Возвращает:
        Словарь попытки или None
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
    Получить текущую активную попытку пользователя, если есть.
    
    Аргументы:
        userid: Telegram ID пользователя
        
    Возвращает:
        Словарь попытки или None
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
    Отменить все активные попытки пользователя.
    
    Аргументы:
        userid: Telegram ID пользователя
        
    Возвращает:
        Количество отменённых попыток
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
# Рейтинги и статистика
# ============================================================================

def get_user_test_history(userid: int, limit: int = 10) -> List[Dict]:
    """
    Получить историю тестов пользователя.
    
    Аргументы:
        userid: Telegram ID пользователя
        limit: Максимальное число записей
        
    Возвращает:
        Список попыток
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
    Получить общую статистику пользователя.
    
    Аргументы:
        userid: Telegram ID пользователя
        
    Возвращает:
        Словарь статистики или None
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
                    # Получить данные последнего теста
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


def get_user_stats_light(userid: int) -> Optional[Dict]:
    """
    Получить облегчённую статистику для главного меню (одним запросом).

    Аргументы:
        userid: Telegram ID пользователя

    Возвращает:
        Словарь статистики или None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) as total_tests,
                        SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) as passed_tests,
                        MAX(score_percent) as best_score,
                        MAX(completed_timestamp) as last_test_timestamp,
                        (
                            SELECT a2.score_percent
                            FROM certification_attempts a2
                            WHERE a2.userid = %s AND a2.status IN ('completed', 'expired')
                            ORDER BY a2.completed_timestamp DESC
                            LIMIT 1
                        ) as last_test_score
                    FROM certification_attempts a
                    WHERE a.userid = %s AND a.status IN ('completed', 'expired')
                    """,
                    (userid, userid)
                )
                result = cursor.fetchone()

                if result and result['total_tests'] > 0:
                    return {
                        'total_tests': result['total_tests'],
                        'passed_tests': result['passed_tests'] or 0,
                        'best_score': float(result['best_score']) if result['best_score'] else 0,
                        'last_test_timestamp': result['last_test_timestamp'],
                        'last_test_score': float(result['last_test_score']) if result['last_test_score'] else None
                    }
                return None
    except Exception as e:
        logger.error(f"Error getting lightweight user stats: {e}")
        return None


def get_monthly_ranking(
    year: int = None,
    month: int = None,
    limit: int = 10
) -> List[Dict]:
    """
    Получить ежемесячный рейтинг лучших пользователей.
    
    Аргументы:
        year: Год (по умолчанию — текущий)
        month: Месяц (по умолчанию — текущий)
        limit: Максимальное число пользователей
        
    Возвращает:
        Список записей рейтинга
    """
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    
    # Рассчитать границы месяца
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
                
                # Добавить номера мест
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
    Получить место пользователя в ежемесячном рейтинге.
    
    Аргументы:
        userid: Telegram ID пользователя
        year: Год (по умолчанию — текущий)
        month: Месяц (по умолчанию — текущий)
        
    Возвращает:
        Словарь с информацией о месте или None
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
                # Получить лучший результат пользователя за месяц
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
                
                # Посчитать пользователей с более высоким результатом
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
                
                # Место пользователя = higher_count + 1
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
    Получить ежемесячный рейтинг с фильтром по категории.
    
    Аргументы:
        category_id: ID категории. None — общий рейтинг (все тесты).
        year: Год (по умолчанию — текущий)
        month: Месяц (по умолчанию — текущий)
        limit: Максимальное число пользователей
        
    Возвращает:
        Список записей рейтинга
    """
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    
    # Рассчитать границы месяца
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
                    # Общий ТОП — все тесты без учёта категории
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
                    # Фильтр по конкретной категории
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
                
                # Добавить номера мест
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
    Получить место пользователя в рейтинге по категории.
    
    Аргументы:
        userid: Telegram ID пользователя
        category_id: ID категории. None — общий рейтинг.
        year: Год (по умолчанию — текущий)
        month: Месяц (по умолчанию — текущий)
        
    Возвращает:
        Словарь с информацией о месте или None
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
                # Получить лучший результат пользователя за месяц по категории
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
                
                # Посчитать пользователей с более высоким результатом в этой категории
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
    Получить список категорий, где пользователь проходил тесты в этом месяце.
    Содержит статистику по каждой категории.
    
    Аргументы:
        userid: Telegram ID пользователя
        year: Год (по умолчанию — текущий)
        month: Месяц (по умолчанию — текущий)
        
    Возвращает:
        Список словарей с информацией о категории и статистике
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
                # Получить категории, где есть попытки за месяц
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
                
                # Добавить место по каждой категории
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
    Получить статистику пользователя по конкретной категории.
    
    Аргументы:
        userid: Telegram ID пользователя
        category_id: ID категории. None — общий вариант.
        
    Возвращает:
        Словарь статистики или None
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
# Вспомогательные функции
# ============================================================================

def format_time_remaining(seconds: int) -> str:
    """
    Сформировать оставшееся время в формате ММ:СС.
    
    Аргументы:
        seconds: Количество оставшихся секунд
        
    Возвращает:
        Строка времени
    """
    if seconds <= 0:
        return "00:00"
    
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"


def format_time_spent(seconds: int) -> str:
    """
    Сформировать затраченное время в читаемом виде.
    Экранировано для MarkdownV2.
    
    Аргументы:
        seconds: Время в секундах
        
    Возвращает:
        Строка времени (MarkdownV2 экранирована)
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
    Получить название месяца по-русски.
    
    Аргументы:
        month: Номер месяца (1-12)
        
    Возвращает:
        Название месяца на русском
    """
    months = {
        1: "январь", 2: "февраль", 3: "март", 4: "апрель",
        5: "май", 6: "июнь", 7: "июль", 8: "август",
        9: "сентябрь", 10: "октябрь", 11: "ноябрь", 12: "декабрь"
    }
    return months.get(month, str(month))


def escape_markdown(text: str) -> str:
    """
    Экранировать специальные символы для Telegram MarkdownV2.
    
    Аргументы:
        text: Текст для экранирования
        
    Возвращает:
        Экранированный текст
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    result = str(text)
    for char in special_chars:
        result = result.replace(char, f'\\{char}')
    return result


def get_questions_count() -> int:
    """
    Получить количество активных вопросов.
    
    Возвращает:
        Число активных вопросов
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
    Получить полную статистику по аттестации.
    
    Возвращает:
        Словарь с total_questions, total_categories, active_categories
        и categories_stats (список категорий с числом вопросов)
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получить общее число активных вопросов
                cursor.execute(
                    """SELECT COUNT(*) as cnt FROM certification_questions 
                       WHERE active = 1 AND relevance_date >= CURDATE()"""
                )
                total_questions = cursor.fetchone()['cnt'] or 0
                
                # Получить общее и активное число категорий
                cursor.execute("SELECT COUNT(*) as total FROM certification_categories")
                total_categories = cursor.fetchone()['total'] or 0
                
                cursor.execute("SELECT COUNT(*) as active FROM certification_categories WHERE active = 1")
                active_categories = cursor.fetchone()['active'] or 0
                
                # Получить количество вопросов по категориям
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
