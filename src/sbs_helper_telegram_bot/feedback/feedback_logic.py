"""
Логика модуля обратной связи

Бизнес-логика, операции с базой, поиск ссылок и ограничение частоты.
"""

import re
import time
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

import src.common.database as database
from . import settings

logger = logging.getLogger(__name__)


# ===== ПОИСК ССЫЛОК =====


def contains_links(text: str) -> bool:
    """
    Проверить, содержит ли текст ссылки/URL.
    
    Args:
        text: Текст для проверки
        
    Returns:
        True, если ссылки найдены, иначе False
    """
    for pattern in settings.LINK_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# ===== ОГРАНИЧЕНИЕ ЧАСТОТЫ =====


def check_rate_limit(user_id: int) -> Tuple[bool, int]:
    """
    Проверить, действует ли ограничение частоты для пользователя.
    
    Args:
        user_id: ID пользователя Telegram
        
    Returns:
        Кортеж (is_allowed, seconds_remaining)
        - is_allowed: True, если можно отправлять, False при ограничении
        - seconds_remaining: Секунды до следующей разрешённой отправки (0, если разрешено)
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получаем последнюю отправку обратной связи
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
        # При ошибке разрешаем отправку, чтобы не блокировать пользователей
        return (True, 0)


# ===== КАТЕГОРИИ =====


def get_active_categories() -> List[Dict[str, Any]]:
    """
    Получить все активные категории обратной связи.
    
    Returns:
        Список словарей категорий с id, name, description, emoji
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
    Получить категорию по ID.
    
    Args:
        category_id: ID категории
        
    Returns:
        Словарь категории или None
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
    Получить все активные категории с количеством записей.
    
    Returns:
        Список словарей категорий с id, name, emoji, count
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


# ===== ЗАПИСИ ОБРАТНОЙ СВЯЗИ =====


def create_feedback_entry(
    user_id: int,
    category_id: int,
    message: str
) -> Optional[int]:
    """
    Создать новую запись обратной связи.
    
    Args:
        user_id: ID пользователя Telegram
        category_id: ID категории
        message: Сообщение пользователя
        
    Returns:
        ID созданной записи или None при ошибке
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
    Получить записи обратной связи пользователя с пагинацией.
    
    Args:
        user_id: ID пользователя Telegram
        page: Номер страницы (с 0)
        per_page: Количество элементов на странице (по умолчанию из настроек)
        
    Returns:
        Кортеж (список_записей, общее_количество)
    """
    if per_page is None:
        per_page = settings.ITEMS_PER_PAGE
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получаем общее количество
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM feedback_entries
                    WHERE user_id = %s
                """, (user_id,))
                total = cursor.fetchone()['count']
                
                # Получаем записи
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
                
                # Форматируем даты
                for entry in entries:
                    entry['date'] = _format_timestamp(entry['created_timestamp'])
                
                return (entries, total)
                
    except Exception as e:
        logger.error("Error getting user feedback: %s", e)
        return ([], 0)


def get_feedback_entry(entry_id: int, user_id: int = None) -> Optional[Dict[str, Any]]:
    """
    Получить одну запись обратной связи вместе с ответами.
    
    Args:
        entry_id: ID записи
        user_id: ID пользователя для проверки владения (необязательно)
        
    Returns:
        Словарь записи с ответами или None
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Формируем запрос
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
                
                # Форматируем дату
                entry['date'] = _format_timestamp(entry['created_timestamp'])
                
                # Получаем ответы (без раскрытия admin_id!)
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


# ===== АДМИНСКИЕ ФУНКЦИИ =====


def get_feedback_entries_by_status(
    status: str = None,
    category_id: int = None,
    page: int = 0,
    per_page: int = None
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Получить записи обратной связи с необязательными фильтрами (админ-функция).
    
    Args:
        status: Фильтр по статусу (None = все)
        category_id: Фильтр по категории (None = все)
        page: Номер страницы (с 0)
        per_page: Количество элементов на странице
        
    Returns:
        Кортеж (список_записей, общее_количество)
    """
    if per_page is None:
        per_page = settings.ITEMS_PER_PAGE
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Собираем WHERE-условие
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
                
                # Получаем общее количество
                cursor.execute(f"""
                    SELECT COUNT(*) as count
                    FROM feedback_entries e
                    {where_clause}
                """, params)
                total = cursor.fetchone()['count']
                
                # Получаем записи
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
                
                # Форматируем даты
                for entry in entries:
                    entry['date'] = _format_timestamp(entry['created_timestamp'])
                
                return (entries, total)
                
    except Exception as e:
        logger.error("Error getting admin feedback entries: %s", e)
        return ([], 0)


def get_new_entries_count() -> int:
    """
    Получить количество новых (непрочитанных) записей обратной связи.
    
    Returns:
        Количество новых записей
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
    Создать ответ администратора на запись обратной связи.
    ПРИМЕЧАНИЕ: admin_id хранится, но НИКОГДА не показывается пользователям.
    
    Args:
        entry_id: ID записи обратной связи
        admin_id: ID администратора Telegram (хранится только внутри)
        response_text: Текст ответа
        
    Returns:
        True при успехе, False при ошибке
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                current_time = int(time.time())
                
                # Создаём ответ
                cursor.execute("""
                    INSERT INTO feedback_responses 
                    (entry_id, admin_id, response_text, created_timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (entry_id, admin_id, response_text, current_time))
                
                # Обновляем статус записи на in_progress, если она была новой
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
    Обновить статус записи обратной связи.
    
    Args:
        entry_id: ID записи
        new_status: Новое значение статуса
        
    Returns:
        True при успехе, False при ошибке
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
    Получить ID пользователя для записи обратной связи (для отправки уведомлений).
    
    Args:
        entry_id: ID записи
        
    Returns:
        ID пользователя или None
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


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====


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
