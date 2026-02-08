"""
Gamification Events System

Central event bus for tracking user actions across all modules.
Modules emit events, and this system handles achievement/score processing.
"""

import json
import logging
from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field

import src.common.database as database

logger = logging.getLogger(__name__)


@dataclass
class EventHandler:
    """Handler configuration for an event type."""
    achievement_codes: List[str] = field(default_factory=list)  # Achievement codes to increment
    score_action: Optional[str] = None  # Score action to award points for


# Event handlers registry
# Maps event_type -> EventHandler config
_event_handlers: Dict[str, EventHandler] = {}

# Custom handler functions (for complex logic)
_custom_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}


def register_event(
    event_type: str,
    achievement_codes: Optional[List[str]] = None,
    score_action: Optional[str] = None
) -> None:
    """
    Register an event type with its achievement and score mappings.
    
    Args:
        event_type: Event identifier (e.g., "ktr.lookup")
        achievement_codes: List of achievement codes to increment progress for
        score_action: Score action code for awarding points
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
    Register a custom handler function for complex event processing.
    
    Args:
        event_type: Event identifier
        handler: Callable that receives event data dict
    """
    _custom_handlers[event_type] = handler
    logger.debug(f"Registered custom handler: {event_type}")


def emit_event(
    event_type: str,
    userid: int,
    data: Optional[Dict[str, Any]] = None
) -> None:
    """
    Emit an event. This is called by modules when trackable actions occur.
    
    The event is:
    1. Logged to the database for history/analytics
    2. Processed for achievement progress
    3. Processed for score points
    4. Handled by custom handlers if registered
    
    Args:
        event_type: Event identifier (e.g., "ktr.lookup")
        userid: Telegram user ID
        data: Optional additional data payload
    """
    import time
    timestamp = int(time.time())
    
    try:
        # 1. Log event to database
        _log_event(event_type, userid, data, timestamp)
        
        # 2. Get handler config
        handler = _event_handlers.get(event_type)
        
        if handler:
            # 3. Process achievement progress
            for achievement_code in handler.achievement_codes:
                _increment_achievement_progress(userid, achievement_code)
            
            # 4. Award score points
            if handler.score_action:
                _award_score_for_action(userid, event_type.split('.')[0], handler.score_action)
        
        # 5. Run custom handler if registered
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
    """Log event to database."""
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
    Increment achievement progress and check for level unlocks.
    """
    # Import here to avoid circular imports
    from . import gamification_logic
    
    try:
        gamification_logic.increment_achievement_progress(userid, achievement_code)
    except Exception as e:
        logger.error(f"Error incrementing achievement progress: {e}")


def _award_score_for_action(userid: int, module: str, action: str) -> None:
    """
    Award score points based on action configuration.
    """
    # Import here to avoid circular imports
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
    Get count of events for a user.
    
    Args:
        userid: Telegram user ID
        event_type: Event type to count
        since_timestamp: Optional timestamp to count from
    
    Returns:
        Event count
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
    Get count of unique days when user triggered an event.
    Useful for "daily user" type achievements.
    
    Args:
        userid: Telegram user ID
        event_type: Event type to check
        since_timestamp: Optional timestamp to count from
    
    Returns:
        Number of unique days
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


# ===== KTR EVENT REGISTRATION =====
# Register KTR module events

def _init_ktr_events():
    """Initialize KTR module event handlers."""
    
    # Basic lookup event
    register_event(
        event_type="ktr.lookup",
        achievement_codes=["ktr_lookup"],
        score_action="lookup"
    )
    
    # Successful lookup (code found)
    register_event(
        event_type="ktr.lookup_found",
        achievement_codes=["ktr_lookup_found"],
        score_action="lookup_found"
    )
    
    # Daily user achievement (custom handler)
    def handle_ktr_daily(event_data: Dict[str, Any]):
        """Custom handler for daily user achievement."""
        from . import gamification_logic
        
        userid = event_data.get('userid')
        if not userid:
            return
        
        # Count unique days
        unique_days = get_unique_days_count(userid, "ktr.lookup")
        
        # Update progress for daily achievement
        gamification_logic.set_achievement_progress(userid, "ktr_daily_user", unique_days)
    
    register_custom_handler("ktr.lookup", handle_ktr_daily)


# ===== CERTIFICATION EVENT REGISTRATION =====
# Register certification module events

def _init_certification_events():
    """Initialize certification module event handlers."""
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

    def handle_cert_daily(event_data: Dict[str, Any]):
        """Custom handler for certification daily user achievement."""
        from . import gamification_logic

        userid = event_data.get('userid')
        if not userid:
            return

        unique_days = get_unique_days_count(userid, "certification.test_completed")
        gamification_logic.set_achievement_progress(userid, "cert_daily_user", unique_days)

    register_custom_handler("certification.test_completed", handle_cert_daily)


# Initialize events on module load
_init_ktr_events()
_init_certification_events()
