"""
Система событий геймификации

Центральная шина событий для отслеживания действий пользователей во всех модулях.
Модули публикуют события, а эта система обрабатывает достижения и начисление очков.
"""

import json
import logging
from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field

import src.common.database as database

logger = logging.getLogger(__name__)


@dataclass
class EventHandler:
    """Конфигурация обработчика для типа события."""
    achievement_codes: List[str] = field(default_factory=list)  # Коды достижений для увеличения прогресса
    score_action: Optional[str] = None  # Действие для начисления очков


# Реестр обработчиков событий
# Сопоставляет event_type -> конфигурацию EventHandler
_event_handlers: Dict[str, EventHandler] = {}

# Пользовательские обработчики (для сложной логики)
_custom_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}


def register_event(
    event_type: str,
    achievement_codes: Optional[List[str]] = None,
    score_action: Optional[str] = None
) -> None:
    """
    Зарегистрировать тип события с его связями по достижениям и очкам.
    
    Args:
        event_type: Идентификатор события (например, "ktr.lookup")
        achievement_codes: Список кодов достижений для увеличения прогресса
        score_action: Код действия для начисления очков
    """
    _event_handlers[event_type] = EventHandler(
        achievement_codes=achievement_codes or [],
        score_action=score_action
    )
    logger.debug(f"Registered event handler: {event_type}")


def register_custom_handler(
    event_type: str,
    handler: Callable[[Dict[str, Any]], None]
) -> None:
    """
    Зарегистрировать пользовательский обработчик для сложной обработки событий.
    
    Args:
        event_type: Идентификатор события
        handler: Функция, принимающая словарь с данными события
    """
    _custom_handlers[event_type] = handler
    logger.debug(f"Registered custom handler: {event_type}")


def emit_event(
    event_type: str,
    userid: int,
    data: Optional[Dict[str, Any]] = None
) -> None:
    """
    Сгенерировать событие. Вызывается модулями при отслеживаемых действиях.
    
    Событие:
    1. Логируется в базе для истории/аналитики
    2. Обрабатывается для прогресса достижений
    3. Обрабатывается для начисления очков
    4. Передаётся в пользовательские обработчики, если они зарегистрированы
    
    Args:
        event_type: Идентификатор события (например, "ktr.lookup")
        userid: ID пользователя Telegram
        data: Дополнительные данные события (необязательно)
    """
    import time
    timestamp = int(time.time())
    
    try:
        # 1. Логируем событие в базу
        _log_event(event_type, userid, data, timestamp)
        
        # 2. Получаем конфигурацию обработчика
        handler = _event_handlers.get(event_type)
        
        if handler:
            # 3. Обрабатываем прогресс достижений
            for achievement_code in handler.achievement_codes:
                _increment_achievement_progress(userid, achievement_code)
            
            # 4. Начисляем очки
            if handler.score_action:
                _award_score_for_action(userid, event_type.split('.')[0], handler.score_action)
        
        # 5. Запускаем пользовательский обработчик, если он зарегистрирован
        custom = _custom_handlers.get(event_type)
        if custom:
            try:
                event_data = {
                    "event_type": event_type,
                    "userid": userid,
                    "timestamp": timestamp,
                    **(data or {})
                }
                custom(event_data)
            except Exception as e:
                logger.error(f"Custom handler error for {event_type}: {e}")
        
        logger.debug(f"Event emitted: {event_type} for user {userid}")
        
    except Exception as e:
        logger.error(f"Error emitting event {event_type}: {e}")


def _log_event(
    event_type: str,
    userid: int,
    data: Optional[Dict[str, Any]],
    timestamp: int
) -> None:
    """Записать событие в базу данных."""
    try:
        data_json = json.dumps(data) if data else None
        
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    INSERT INTO gamification_events 
                    (event_type, userid, data_json, timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (event_type, userid, data_json, timestamp))
    except Exception as e:
        logger.error(f"Error logging event: {e}")


def _increment_achievement_progress(userid: int, achievement_code: str) -> None:
    """
    Увеличить прогресс достижения и проверить разблокировку уровней.
    """
    # Импортируем здесь, чтобы избежать циклических импортов
    from . import gamification_logic
    
    try:
        gamification_logic.increment_achievement_progress(userid, achievement_code)
    except Exception as e:
        logger.error(f"Error incrementing achievement progress: {e}")


def _award_score_for_action(userid: int, module: str, action: str) -> None:
    """
    Начислить очки в соответствии с конфигурацией действия.
    """
    # Импортируем здесь, чтобы избежать циклических импортов
    from . import gamification_logic
    
    try:
        gamification_logic.award_score_for_action(userid, module, action)
    except Exception as e:
        logger.error(f"Error awarding score: {e}")


def get_event_count(
    userid: int,
    event_type: str,
    since_timestamp: Optional[int] = None
) -> int:
    """
    Получить количество событий пользователя.
    
    Args:
        userid: ID пользователя Telegram
        event_type: Тип события для подсчёта
        since_timestamp: Отметка времени, начиная с которой считать (необязательно)
    
    Returns:
        Количество событий
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if since_timestamp:
                    cursor.execute("""
                        SELECT COUNT(*) as cnt 
                        FROM gamification_events 
                        WHERE userid = %s AND event_type = %s AND timestamp >= %s
                    """, (userid, event_type, since_timestamp))
                else:
                    cursor.execute("""
                        SELECT COUNT(*) as cnt 
                        FROM gamification_events 
                        WHERE userid = %s AND event_type = %s
                    """, (userid, event_type))
                
                result = cursor.fetchone()
                return result['cnt'] if result else 0
    except Exception as e:
        logger.error(f"Error getting event count: {e}")
        return 0


def get_unique_days_count(
    userid: int,
    event_type: str,
    since_timestamp: Optional[int] = None
) -> int:
    """
    Получить количество уникальных дней, когда пользователь вызывал событие.
    Полезно для достижений типа «ежедневный пользователь».
    
    Args:
        userid: ID пользователя Telegram
        event_type: Тип события для проверки
        since_timestamp: Отметка времени, начиная с которой считать (необязательно)
    
    Returns:
        Количество уникальных дней
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                if since_timestamp:
                    cursor.execute("""
                        SELECT COUNT(DISTINCT DATE(FROM_UNIXTIME(timestamp))) as cnt 
                        FROM gamification_events 
                        WHERE userid = %s AND event_type = %s AND timestamp >= %s
                    """, (userid, event_type, since_timestamp))
                else:
                    cursor.execute("""
                        SELECT COUNT(DISTINCT DATE(FROM_UNIXTIME(timestamp))) as cnt 
                        FROM gamification_events 
                        WHERE userid = %s AND event_type = %s
                    """, (userid, event_type))
                
                result = cursor.fetchone()
                return result['cnt'] if result else 0
    except Exception as e:
        logger.error(f"Error getting unique days count: {e}")
        return 0


# ===== РЕГИСТРАЦИЯ СОБЫТИЙ KTR =====
# Регистрируем события модуля KTR

def _init_ktr_events():
    """Инициализировать обработчики событий модуля KTR."""
    
    # Базовое событие поиска
    register_event(
        event_type="ktr.lookup",
        achievement_codes=["ktr_lookup"],
        score_action="lookup"
    )
    
    # Успешный поиск (код найден)
    register_event(
        event_type="ktr.lookup_found",
        achievement_codes=["ktr_lookup_found"],
        score_action="lookup_found"
    )
    
    # Достижение «ежедневный пользователь» (пользовательский обработчик)
    def handle_ktr_daily(event_data: Dict[str, Any]):
        """Пользовательский обработчик для достижения «ежедневный пользователь»."""
        from . import gamification_logic
        
        userid = event_data.get('userid')
        if not userid:
            return
        
        # Считаем уникальные дни
        unique_days = get_unique_days_count(userid, "ktr.lookup")
        
        # Обновляем прогресс дневного достижения
        gamification_logic.set_achievement_progress(userid, "ktr_daily_user", unique_days)
    
    register_custom_handler("ktr.lookup", handle_ktr_daily)


# ===== РЕГИСТРАЦИЯ СОБЫТИЙ СЕРТИФИКАЦИИ =====
# Регистрируем события модуля сертификации

def _init_certification_events():
    """Инициализировать обработчики событий модуля сертификации."""
    register_event(
        event_type="certification.test_completed",
        achievement_codes=["cert_test_completed"],
        score_action="test_completed"
    )

    register_event(
        event_type="certification.test_passed",
        achievement_codes=["cert_test_passed"],
        score_action="test_passed"
    )

    register_event(
        event_type="certification.learning_answered",
        achievement_codes=["cert_learning_answered"],
    )

    register_event(
        event_type="certification.learning_completed",
        achievement_codes=["cert_learning_completed"],
    )

    def handle_cert_daily(event_data: Dict[str, Any]):
        """Пользовательский обработчик для дневного достижения сертификации."""
        from . import gamification_logic

        userid = event_data.get('userid')
        if not userid:
            return

        unique_days = get_unique_days_count(userid, "certification.test_completed")
        gamification_logic.set_achievement_progress(userid, "cert_daily_user", unique_days)

    register_custom_handler("certification.test_completed", handle_cert_daily)


# Инициализируем события при загрузке модуля
_init_ktr_events()
_init_certification_events()
