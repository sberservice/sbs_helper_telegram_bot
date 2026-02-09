"""
Логика геймификации.

Основная бизнес-логика системы геймификации:
- Управление очками
- Отслеживание прогресса достижений
- Расчёт рейтингов
- Данные профиля пользователя
"""

import time
import logging
from typing import Optional, Dict, List, Tuple, Any
from datetime import datetime, timedelta
from calendar import monthrange

import src.common.database as database
from . import settings

logger = logging.getLogger(__name__)

# ===== ПРОСТЫЕ КЭШИ В ПАМЯТИ =====

_RANKS_CACHE: Optional[List[Dict]] = None
_RANKS_CACHE_TS: float = 0.0
_RANKS_CACHE_TTL_SECONDS = 300

_TOTAL_ACHIEVEMENTS_CACHE: Optional[int] = None
_TOTAL_ACHIEVEMENTS_CACHE_TS: float = 0.0
_TOTAL_ACHIEVEMENTS_CACHE_TTL_SECONDS = 300


# ===== ПОМОЩНИКИ НАСТРОЕК =====

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Получить значение настройки из базы данных."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT value FROM gamification_settings WHERE `key` = %s",
                    (key,)
                )
                result = cursor.fetchone()
                return result['value'] if result else default
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return default


def set_setting(key: str, value: str, description: Optional[str] = None) -> bool:
    """Установить значение настройки в базе данных."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if description:
                    cursor.execute("""
                        INSERT INTO gamification_settings (`key`, value, description, updated_timestamp)
                        VALUES (%s, %s, %s, UNIX_TIMESTAMP())
                        ON DUPLICATE KEY UPDATE value = %s, updated_timestamp = UNIX_TIMESTAMP()
                    """, (key, value, description, value))
                else:
                    cursor.execute("""
                        INSERT INTO gamification_settings (`key`, value, updated_timestamp)
                        VALUES (%s, %s, UNIX_TIMESTAMP())
                        ON DUPLICATE KEY UPDATE value = %s, updated_timestamp = UNIX_TIMESTAMP()
                    """, (key, value, value))
                return True
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
        return False


def get_obfuscate_names() -> bool:
    """Проверить, включено ли скрытие имён."""
    value = get_setting(settings.DB_SETTING_OBFUSCATE_NAMES, 'false')
    return value in (True, 'True', 'true', '1', 1)


# ===== ПОМОЩНИКИ РАНГОВ =====

def get_ranks_config() -> List[Dict]:
    """Получить конфигурацию рангов из базы или значения по умолчанию."""
    global _RANKS_CACHE, _RANKS_CACHE_TS
    now = time.time()
    if _RANKS_CACHE is not None and (now - _RANKS_CACHE_TS) < _RANKS_CACHE_TTL_SECONDS:
        return _RANKS_CACHE

    ranks = []
    for i in range(1, 6):
        name = get_setting(f'rank_{i}_name')
        threshold = get_setting(f'rank_{i}_threshold')
        icon = get_setting(f'rank_{i}_icon')
        
        if name and threshold is not None:
            ranks.append({
                'level': i,
                'name': name,
                'icon': icon or '',
                'threshold': int(threshold)
            })
    
    _RANKS_CACHE = ranks if ranks else settings.DEFAULT_RANKS
    _RANKS_CACHE_TS = now
    return _RANKS_CACHE


def get_rank_for_score(score: int) -> Dict:
    """
    Определить ранг по количеству очков.
    
    Args:
        score: суммарные очки пользователя.
    
    Returns:
        Словарь ранга с level, name, icon, threshold.
    """
    ranks = get_ranks_config()
    current_rank = ranks[0]
    
    for rank in ranks:
        if score >= rank['threshold']:
            current_rank = rank
        else:
            break
    
    return current_rank


def get_next_rank(current_rank_level: int) -> Optional[Dict]:
    """Получить следующий ранг после текущего уровня."""
    ranks = get_ranks_config()
    for rank in ranks:
        if rank['level'] > current_rank_level:
            return rank
    return None


# ===== УПРАВЛЕНИЕ ОЧКАМИ =====

def add_score_points(
    userid: int,
    points: int,
    source: str,
    reason: Optional[str] = None
) -> bool:
    """
    Add score points to a user. This is the main function for external scripts.
    
    Args:
        userid: Telegram user ID
        points: Points to add (can be negative)
        source: Source identifier (module name or 'external')
        reason: Optional reason for the points
    
    Returns:
        True if successful
    """
    try:
        timestamp = int(time.time())
        
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Добавляем запись начисления очков
                cursor.execute("""
                    INSERT INTO gamification_scores (userid, points, source, reason, timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                """, (userid, points, source, reason, timestamp))
                
                # Обновляем или создаём кэш итогов
                cursor.execute("""
                    INSERT INTO gamification_user_totals (userid, total_score, last_updated)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        total_score = total_score + %s,
                        last_updated = %s
                """, (userid, points, timestamp, points, timestamp))
                
                # Обновляем ранг
                _update_user_rank(cursor, userid)
                
                return True
    except Exception as e:
        logger.error(f"Error adding score points: {e}")
        return False


def award_score_for_action(userid: int, module: str, action: str) -> bool:
    """
    Award score points based on configured action.
    
    Args:
        userid: Telegram user ID
        module: Module name
        action: Action identifier
    
    Returns:
        True if points were awarded
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получаем очки для этого действия
                cursor.execute("""
                    SELECT points FROM gamification_score_config
                    WHERE module = %s AND action = %s AND active = 1
                """, (module, action))
                
                result = cursor.fetchone()
                if not result:
                    return False
                
                points = result['points']
        
        # Начисляем очки
        return add_score_points(
            userid=userid,
            points=points,
            source=module,
            reason=f"action:{action}"
        )
    except Exception as e:
        logger.error(f"Error awarding score for action: {e}")
        return False


def get_user_total_score(userid: int) -> int:
    """Получить суммарные очки пользователя."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT total_score FROM gamification_user_totals WHERE userid = %s
                """, (userid,))
                result = cursor.fetchone()
                return result['total_score'] if result else 0
    except Exception as e:
        logger.error(f"Error getting user score: {e}")
        return 0


def _update_user_rank(cursor, userid: int) -> None:
    """Обновить ранг пользователя в таблице итогов."""
    try:
        cursor.execute(
            "SELECT total_score FROM gamification_user_totals WHERE userid = %s",
            (userid,)
        )
        result = cursor.fetchone()
        if result:
            rank = get_rank_for_score(result['total_score'])
            cursor.execute("""
                UPDATE gamification_user_totals 
                SET current_rank = %s 
                WHERE userid = %s
            """, (rank['name'], userid))
    except Exception as e:
        logger.error(f"Error updating user rank: {e}")


# ===== УПРАВЛЕНИЕ ДОСТИЖЕНИЯМИ =====

def get_achievement_by_code(code: str) -> Optional[Dict]:
    """Получить описание достижения по коду."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT * FROM gamification_achievements WHERE code = %s AND active = 1
                """, (code,))
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting achievement: {e}")
        return None


def get_all_achievements(module: Optional[str] = None) -> List[Dict]:
    """Получить все достижения, опционально с фильтром по модулю."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if module:
                    cursor.execute("""
                        SELECT * FROM gamification_achievements 
                        WHERE active = 1 AND module = %s
                        ORDER BY display_order, name
                    """, (module,))
                else:
                    cursor.execute("""
                        SELECT * FROM gamification_achievements 
                        WHERE active = 1
                        ORDER BY module, display_order, name
                    """)
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting achievements: {e}")
        return []


def get_achievement_modules() -> List[str]:
    """Получить список модулей, у которых есть достижения."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT DISTINCT module FROM gamification_achievements WHERE active = 1
                    ORDER BY module
                """)
                return [row['module'] for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Error getting achievement modules: {e}")
        return []


def get_total_achievements_count() -> int:
    """Получить общее число уровней достижений (достижения * 3)."""
    global _TOTAL_ACHIEVEMENTS_CACHE, _TOTAL_ACHIEVEMENTS_CACHE_TS
    now = time.time()
    if (
        _TOTAL_ACHIEVEMENTS_CACHE is not None
        and (now - _TOTAL_ACHIEVEMENTS_CACHE_TS) < _TOTAL_ACHIEVEMENTS_CACHE_TTL_SECONDS
    ):
        return _TOTAL_ACHIEVEMENTS_CACHE

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) * 3 as cnt FROM gamification_achievements WHERE active = 1
                """)
                result = cursor.fetchone()
                _TOTAL_ACHIEVEMENTS_CACHE = result['cnt'] if result else 0
                _TOTAL_ACHIEVEMENTS_CACHE_TS = now
                return _TOTAL_ACHIEVEMENTS_CACHE
    except Exception as e:
        logger.error(f"Error getting total achievements count: {e}")
        return 0


def get_user_main_menu_profile(userid: int) -> Optional[Dict]:
    """
    Get lightweight user profile for main menu.

    Returns:
        Dict with profile data or None if user not found
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT total_score, total_achievements
                    FROM gamification_user_totals
                    WHERE userid = %s
                    """,
                    (userid,)
                )
                totals = cursor.fetchone()

                if not totals:
                    ensure_user_totals_exist(userid)
                    cursor.execute(
                        """
                        SELECT total_score, total_achievements
                        FROM gamification_user_totals
                        WHERE userid = %s
                        """,
                        (userid,)
                    )
                    totals = cursor.fetchone()

                if not totals:
                    return None

                total_score = totals['total_score'] if totals else 0
                total_achievements = totals['total_achievements'] if totals else 0

                rank = get_rank_for_score(total_score)
                next_rank = get_next_rank(rank['level'])
                max_achievements = get_total_achievements_count()

                return {
                    'total_score': total_score,
                    'rank_name': rank['name'],
                    'rank_icon': rank['icon'],
                    'rank_level': rank['level'],
                    'next_rank_name': next_rank['name'] if next_rank else None,
                    'next_rank_threshold': next_rank['threshold'] if next_rank else None,
                    'total_achievements': total_achievements,
                    'max_achievements': max_achievements,
                }
    except Exception as e:
        logger.error(f"Error getting main menu profile: {e}")
        return None


def increment_achievement_progress(userid: int, achievement_code: str) -> Optional[int]:
    """
    Increment achievement progress and check for unlocks.
    
    Args:
        userid: Telegram user ID
        achievement_code: Achievement code
    
    Returns:
        New unlocked level (1-3) or None if no new unlock
    """
    try:
        achievement = get_achievement_by_code(achievement_code)
        if not achievement:
            logger.warning(f"Achievement not found: {achievement_code}")
            return None
        
        achievement_id = achievement['id']
        timestamp = int(time.time())
        
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Увеличиваем прогресс
                cursor.execute("""
                    INSERT INTO gamification_user_progress 
                    (userid, achievement_id, current_count, last_increment_timestamp)
                    VALUES (%s, %s, 1, %s)
                    ON DUPLICATE KEY UPDATE 
                        current_count = current_count + 1,
                        last_increment_timestamp = %s
                """, (userid, achievement_id, timestamp, timestamp))
                
                # Получаем новое значение счётчика
                cursor.execute("""
                    SELECT current_count FROM gamification_user_progress
                    WHERE userid = %s AND achievement_id = %s
                """, (userid, achievement_id))
                
                result = cursor.fetchone()
                if not result:
                    return None
                
                current_count = result['current_count']
                
                # Проверяем, не разблокированы ли уровни
                return _check_and_unlock_levels(
                    cursor, userid, achievement_id, achievement, current_count, timestamp
                )
    except Exception as e:
        logger.error(f"Error incrementing achievement progress: {e}")
        return None


def set_achievement_progress(userid: int, achievement_code: str, count: int) -> Optional[int]:
    """
    Set achievement progress to a specific value (for unique counts like daily user).
    
    Args:
        userid: Telegram user ID
        achievement_code: Achievement code
        count: Progress count to set
    
    Returns:
        New unlocked level (1-3) or None if no new unlock
    """
    try:
        achievement = get_achievement_by_code(achievement_code)
        if not achievement:
            return None
        
        achievement_id = achievement['id']
        timestamp = int(time.time())
        
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Устанавливаем прогресс
                cursor.execute("""
                    INSERT INTO gamification_user_progress 
                    (userid, achievement_id, current_count, last_increment_timestamp)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                        current_count = %s,
                        last_increment_timestamp = %s
                """, (userid, achievement_id, count, timestamp, count, timestamp))
                
                # Проверяем, не разблокированы ли уровни
                return _check_and_unlock_levels(
                    cursor, userid, achievement_id, achievement, count, timestamp
                )
    except Exception as e:
        logger.error(f"Error setting achievement progress: {e}")
        return None


def _check_and_unlock_levels(
    cursor,
    userid: int,
    achievement_id: int,
    achievement: Dict,
    current_count: int,
    timestamp: int
) -> Optional[int]:
    """Проверить пороги и разблокировать новые уровни, если нужно."""
    thresholds = [
        (settings.ACHIEVEMENT_LEVEL_BRONZE, achievement['threshold_bronze']),
        (settings.ACHIEVEMENT_LEVEL_SILVER, achievement['threshold_silver']),
        (settings.ACHIEVEMENT_LEVEL_GOLD, achievement['threshold_gold']),
    ]
    
    new_unlock = None
    
    for level, threshold in thresholds:
        if current_count >= threshold:
            # Проверяем, не разблокирован ли уже
            cursor.execute("""
                SELECT id FROM gamification_user_achievements
                WHERE userid = %s AND achievement_id = %s AND level = %s
            """, (userid, achievement_id, level))
            
            if not cursor.fetchone():
                # Разблокируем этот уровень
                cursor.execute("""
                    INSERT INTO gamification_user_achievements
                    (userid, achievement_id, level, unlocked_timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (userid, achievement_id, level, timestamp))
                
                # Обновляем итоги
                cursor.execute("""
                    INSERT INTO gamification_user_totals (userid, total_achievements, last_updated)
                    VALUES (%s, 1, %s)
                    ON DUPLICATE KEY UPDATE 
                        total_achievements = total_achievements + 1,
                        last_updated = %s
                """, (userid, timestamp, timestamp))
                
                new_unlock = level
                logger.info(f"User {userid} unlocked {achievement['code']} level {level}")
    
    return new_unlock


def get_user_achievement_progress(userid: int, achievement_id: int) -> Dict:
    """Получить прогресс пользователя по конкретному достижению."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получаем прогресс
                cursor.execute("""
                    SELECT current_count FROM gamification_user_progress
                    WHERE userid = %s AND achievement_id = %s
                """, (userid, achievement_id))
                progress = cursor.fetchone()
                current_count = progress['current_count'] if progress else 0
                
                # Получаем разблокированные уровни
                cursor.execute("""
                    SELECT MAX(level) as max_level FROM gamification_user_achievements
                    WHERE userid = %s AND achievement_id = %s
                """, (userid, achievement_id))
                unlocked = cursor.fetchone()
                max_level = unlocked['max_level'] if unlocked and unlocked['max_level'] else 0
                
                return {
                    'current_count': current_count,
                    'unlocked_level': max_level
                }
    except Exception as e:
        logger.error(f"Error getting achievement progress: {e}")
        return {'current_count': 0, 'unlocked_level': 0}


def get_user_achievements_with_progress(
    userid: int,
    module: Optional[str] = None
) -> List[Dict]:
    """Получить все достижения с прогрессом пользователя."""
    achievements = get_all_achievements(module)
    result = []
    
    for ach in achievements:
        progress = get_user_achievement_progress(userid, ach['id'])
        result.append({
            **ach,
            'current_count': progress['current_count'],
            'unlocked_level': progress['unlocked_level']
        })
    
    return result


def get_user_unlocked_achievements_count(userid: int) -> int:
    """Получить общее число уровней достижений, разблокированных пользователем."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT COUNT(*) as cnt FROM gamification_user_achievements WHERE userid = %s
                """, (userid,))
                result = cursor.fetchone()
                return result['cnt'] if result else 0
    except Exception as e:
        logger.error(f"Error getting unlocked count: {e}")
        return 0


def get_user_achievements_by_level(userid: int) -> Dict[int, int]:
    """Получить количество достижений по уровням для пользователя."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT level, COUNT(*) as cnt 
                    FROM gamification_user_achievements 
                    WHERE userid = %s
                    GROUP BY level
                """, (userid,))
                return {row['level']: row['cnt'] for row in cursor.fetchall()}
    except Exception as e:
        logger.error(f"Error getting achievements by level: {e}")
        return {}


# ===== ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ =====

def get_user_profile(userid: int) -> Optional[Dict]:
    """
    Get complete user profile with scores, rank, and achievements.
    
    Returns:
        Dict with profile data or None if user not found
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получаем данные пользователя
                cursor.execute("""
                    SELECT userid, first_name, last_name, username
                    FROM users WHERE userid = %s
                """, (userid,))
                user = cursor.fetchone()
                
                if not user:
                    return None
                
                # Получаем итоги
                cursor.execute("""
                    SELECT total_score, total_achievements, current_rank
                    FROM gamification_user_totals WHERE userid = %s
                """, (userid,))
                totals = cursor.fetchone()
                
                total_score = totals['total_score'] if totals else 0
                total_achievements = totals['total_achievements'] if totals else 0
                
                # Получаем информацию о ранге
                rank = get_rank_for_score(total_score)
                next_rank = get_next_rank(rank['level'])
                
                # Получаем достижения по уровням
                achievements_by_level = get_user_achievements_by_level(userid)
                
                # Получаем максимальное возможное число достижений
                max_achievements = get_total_achievements_count()
                
                return {
                    'userid': user['userid'],
                    'first_name': user['first_name'],
                    'last_name': user['last_name'],
                    'username': user['username'],
                    'total_score': total_score,
                    'rank_name': rank['name'],
                    'rank_icon': rank['icon'],
                    'rank_level': rank['level'],
                    'next_rank_name': next_rank['name'] if next_rank else None,
                    'next_rank_threshold': next_rank['threshold'] if next_rank else None,
                    'total_achievements': total_achievements,
                    'max_achievements': max_achievements,
                    'achievements_by_level': achievements_by_level
                }
    except Exception as e:
        logger.error(f"Error getting user profile: {e}")
        return None


def ensure_user_totals_exist(userid: int) -> None:
    """Убедиться, что у пользователя есть запись итогов (создать при отсутствии)."""
    try:
        timestamp = int(time.time())
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    INSERT IGNORE INTO gamification_user_totals 
                    (userid, total_score, total_achievements, last_updated)
                    VALUES (%s, 0, 0, %s)
                """, (userid, timestamp))
    except Exception as e:
        logger.error(f"Error ensuring user totals: {e}")


# ===== РЕЙТИНГИ =====

def _get_time_range(period: str) -> Tuple[int, int]:
    """Получить диапазон временных меток для периода."""
    now = datetime.now()
    
    if period == settings.RANKING_PERIOD_MONTHLY:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        _, last_day = monthrange(now.year, now.month)
        end = now.replace(day=last_day, hour=23, minute=59, second=59)
    elif period == settings.RANKING_PERIOD_YEARLY:
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(month=12, day=31, hour=23, minute=59, second=59)
    else:  # за всё время
        start = datetime(2020, 1, 1)
        end = now
    
    return int(start.timestamp()), int(end.timestamp())


def get_score_ranking(
    period: str = settings.RANKING_PERIOD_ALL_TIME,
    page: int = 1,
    per_page: int = settings.RANKINGS_PER_PAGE
) -> Tuple[List[Dict], int]:
    """
    Get score ranking for a period.
    
    Args:
        period: 'monthly', 'yearly', or 'all_time'
        page: Page number
        per_page: Results per page
    
    Returns:
        Tuple of (ranking entries, total count)
    """
    offset = (page - 1) * per_page
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if period == settings.RANKING_PERIOD_ALL_TIME:
                    # Для общего рейтинга используем таблицу итогов
                    cursor.execute("""
                        SELECT COUNT(*) as cnt FROM gamification_user_totals 
                        WHERE total_score > 0
                    """)
                    total = cursor.fetchone()['cnt']
                    
                    cursor.execute("""
                        SELECT 
                            t.userid, t.total_score, u.first_name, u.last_name,
                            RANK() OVER (ORDER BY t.total_score DESC) as `rank`
                        FROM gamification_user_totals t
                        JOIN users u ON t.userid = u.userid
                        WHERE t.total_score > 0
                        ORDER BY t.total_score DESC
                        LIMIT %s OFFSET %s
                    """, (per_page, offset))
                else:
                    # Для периода считаем по таблице очков
                    start_ts, end_ts = _get_time_range(period)
                    
                    cursor.execute("""
                        SELECT COUNT(DISTINCT userid) as cnt 
                        FROM gamification_scores 
                        WHERE timestamp BETWEEN %s AND %s
                    """, (start_ts, end_ts))
                    total = cursor.fetchone()['cnt']
                    
                    cursor.execute("""
                        SELECT 
                            s.userid, 
                            SUM(s.points) as total_score,
                            u.first_name, u.last_name,
                            RANK() OVER (ORDER BY SUM(s.points) DESC) as `rank`
                        FROM gamification_scores s
                        JOIN users u ON s.userid = u.userid
                        WHERE s.timestamp BETWEEN %s AND %s
                        GROUP BY s.userid
                        HAVING total_score > 0
                        ORDER BY total_score DESC
                        LIMIT %s OFFSET %s
                    """, (start_ts, end_ts, per_page, offset))
                
                entries = cursor.fetchall()
                return entries, total
    except Exception as e:
        logger.error(f"Error getting score ranking: {e}")
        return [], 0


def get_achievements_ranking(
    period: str = settings.RANKING_PERIOD_ALL_TIME,
    page: int = 1,
    per_page: int = settings.RANKINGS_PER_PAGE
) -> Tuple[List[Dict], int]:
    """
    Get achievements ranking for a period.
    
    Args:
        period: 'monthly', 'yearly', or 'all_time'
        page: Page number
        per_page: Results per page
    
    Returns:
        Tuple of (ranking entries, total count)
    """
    offset = (page - 1) * per_page
    
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if period == settings.RANKING_PERIOD_ALL_TIME:
                    # Используем таблицу итогов
                    cursor.execute("""
                        SELECT COUNT(*) as cnt FROM gamification_user_totals 
                        WHERE total_achievements > 0
                    """)
                    total = cursor.fetchone()['cnt']
                    
                    cursor.execute("""
                        SELECT 
                            t.userid, t.total_achievements, u.first_name, u.last_name,
                            RANK() OVER (ORDER BY t.total_achievements DESC) as `rank`
                        FROM gamification_user_totals t
                        JOIN users u ON t.userid = u.userid
                        WHERE t.total_achievements > 0
                        ORDER BY t.total_achievements DESC
                        LIMIT %s OFFSET %s
                    """, (per_page, offset))
                else:
                    # Для периода считаем по таблице достижений
                    start_ts, end_ts = _get_time_range(period)
                    
                    cursor.execute("""
                        SELECT COUNT(DISTINCT userid) as cnt 
                        FROM gamification_user_achievements 
                        WHERE unlocked_timestamp BETWEEN %s AND %s
                    """, (start_ts, end_ts))
                    total = cursor.fetchone()['cnt']
                    
                    cursor.execute("""
                        SELECT 
                            a.userid, 
                            COUNT(*) as total_achievements,
                            u.first_name, u.last_name,
                            RANK() OVER (ORDER BY COUNT(*) DESC) as `rank`
                        FROM gamification_user_achievements a
                        JOIN users u ON a.userid = u.userid
                        WHERE a.unlocked_timestamp BETWEEN %s AND %s
                        GROUP BY a.userid
                        ORDER BY total_achievements DESC
                        LIMIT %s OFFSET %s
                    """, (start_ts, end_ts, per_page, offset))
                
                entries = cursor.fetchall()
                return entries, total
    except Exception as e:
        logger.error(f"Error getting achievements ranking: {e}")
        return [], 0


def get_user_rank(
    userid: int,
    ranking_type: str,
    period: str = settings.RANKING_PERIOD_ALL_TIME
) -> Optional[Dict]:
    """Получить позицию конкретного пользователя в рейтинге."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if ranking_type == settings.RANKING_TYPE_SCORE:
                    if period == settings.RANKING_PERIOD_ALL_TIME:
                        cursor.execute("""
                            SELECT 
                                userid, total_score,
                                (SELECT COUNT(*) + 1 FROM gamification_user_totals 
                                 WHERE total_score > t.total_score) as `rank`
                            FROM gamification_user_totals t
                            WHERE userid = %s
                        """, (userid,))
                    else:
                        start_ts, end_ts = _get_time_range(period)
                        cursor.execute("""
                            SELECT 
                                %s as userid,
                                COALESCE(SUM(points), 0) as total_score,
                                (SELECT COUNT(DISTINCT s2.userid) + 1 
                                 FROM gamification_scores s2 
                                 WHERE s2.timestamp BETWEEN %s AND %s
                                 GROUP BY s2.userid
                                 HAVING SUM(s2.points) > COALESCE((
                                     SELECT SUM(points) FROM gamification_scores 
                                     WHERE userid = %s AND timestamp BETWEEN %s AND %s
                                 ), 0)) as `rank`
                            FROM gamification_scores
                            WHERE userid = %s AND timestamp BETWEEN %s AND %s
                        """, (userid, start_ts, end_ts, userid, start_ts, end_ts, userid, start_ts, end_ts))
                else:
                    if period == settings.RANKING_PERIOD_ALL_TIME:
                        cursor.execute("""
                            SELECT 
                                userid, total_achievements,
                                (SELECT COUNT(*) + 1 FROM gamification_user_totals 
                                 WHERE total_achievements > t.total_achievements) as `rank`
                            FROM gamification_user_totals t
                            WHERE userid = %s
                        """, (userid,))
                    else:
                        start_ts, end_ts = _get_time_range(period)
                        cursor.execute("""
                            SELECT 
                                %s as userid,
                                COUNT(*) as total_achievements
                            FROM gamification_user_achievements
                            WHERE userid = %s AND unlocked_timestamp BETWEEN %s AND %s
                        """, (userid, userid, start_ts, end_ts))
                
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting user rank: {e}")
        return None


# ===== ПОИСК =====

def search_users(query: str, limit: int = 10) -> List[Dict]:
    """Искать пользователей по имени."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                search_pattern = f"%{query}%"
                cursor.execute("""
                    SELECT userid, first_name, last_name, username
                    FROM users
                    WHERE first_name LIKE %s OR last_name LIKE %s OR username LIKE %s
                    LIMIT %s
                """, (search_pattern, search_pattern, search_pattern, limit))
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error searching users: {e}")
        return []


# ===== ФУНКЦИИ ДЛЯ АДМИНА =====

def get_all_score_configs() -> List[Dict]:
    """Получить все записи конфигурации начисления очков."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT * FROM gamification_score_config
                    ORDER BY module, action
                """)
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting score configs: {e}")
        return []


def update_score_config(config_id: int, points: int) -> bool:
    """Обновить количество очков для конфигурации."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    UPDATE gamification_score_config
                    SET points = %s, updated_timestamp = UNIX_TIMESTAMP()
                    WHERE id = %s
                """, (points, config_id))
                return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating score config: {e}")
        return False


def get_score_config_by_id(config_id: int) -> Optional[Dict]:
    """Получить конфигурацию очков по идентификатору."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT * FROM gamification_score_config WHERE id = %s",
                    (config_id,)
                )
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting score config: {e}")
        return None


def get_system_stats() -> Dict:
    """Получить общую статистику системы для админа."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Всего пользователей с любой активностью
                cursor.execute("SELECT COUNT(*) as cnt FROM gamification_user_totals")
                total_users = cursor.fetchone()['cnt']
                
                # Активные пользователи за последние 7 дней
                week_ago = int(time.time()) - (7 * 24 * 60 * 60)
                cursor.execute("""
                    SELECT COUNT(DISTINCT userid) as cnt 
                    FROM gamification_events 
                    WHERE timestamp > %s
                """, (week_ago,))
                active_7d = cursor.fetchone()['cnt']
                
                # Всего разблокированных достижений
                cursor.execute("SELECT COUNT(*) as cnt FROM gamification_user_achievements")
                total_achievements = cursor.fetchone()['cnt']
                
                # Всего начислено очков
                cursor.execute("SELECT COALESCE(SUM(points), 0) as total FROM gamification_scores")
                total_score = cursor.fetchone()['total']
                
                # Топ по очкам
                cursor.execute("""
                    SELECT t.userid, t.total_score, u.first_name
                    FROM gamification_user_totals t
                    JOIN users u ON t.userid = u.userid
                    ORDER BY t.total_score DESC
                    LIMIT 5
                """)
                top_scorers = cursor.fetchall()
                
                return {
                    'total_users': total_users,
                    'active_users_7d': active_7d,
                    'total_achievements_unlocked': total_achievements,
                    'total_score_awarded': total_score,
                    'top_scorers': top_scorers
                }
    except Exception as e:
        logger.error(f"Error getting system stats: {e}")
        return {
            'total_users': 0,
            'active_users_7d': 0,
            'total_achievements_unlocked': 0,
            'total_score_awarded': 0,
            'top_scorers': []
        }


def get_achievements_with_unlock_counts() -> List[Dict]:
    """Получить все достижения с количеством разблокировок каждого."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT 
                        a.*,
                        (SELECT COUNT(*) FROM gamification_user_achievements ua 
                         WHERE ua.achievement_id = a.id) as unlocked_count
                    FROM gamification_achievements a
                    WHERE a.active = 1
                    ORDER BY a.module, a.display_order
                """)
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Error getting achievements with counts: {e}")
        return []
