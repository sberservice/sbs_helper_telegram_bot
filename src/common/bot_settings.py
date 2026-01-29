"""
bot_settings.py

Bot-wide settings management utilities.

Functions:
- get_setting(key) -> str | None: Gets a setting value by key.
- set_setting(key, value, updated_by) -> bool: Sets a setting value.
- is_invite_system_enabled() -> bool: Checks if invite system is enabled.
- set_invite_system_enabled(enabled, updated_by) -> bool: Enables/disables invite system.
"""

from typing import Optional
import src.common.database as database

# Setting keys
SETTING_INVITE_SYSTEM_ENABLED = 'invite_system_enabled'


def get_setting(key: str) -> Optional[str]:
    """
    Get a setting value by key.
    
    Args:
        key: The setting key to retrieve.
        
    Returns:
        The setting value as string, or None if not found.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT setting_value FROM bot_settings WHERE setting_key = %s",
                (key,)
            )
            result = cursor.fetchone()
            return result['setting_value'] if result else None


def set_setting(key: str, value: str, updated_by: Optional[int] = None) -> bool:
    """
    Set a setting value (insert or update).
    
    Args:
        key: The setting key.
        value: The setting value as string.
        updated_by: User ID of admin making the change (optional).
        
    Returns:
        True if successful, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                INSERT INTO bot_settings (setting_key, setting_value, updated_timestamp, updated_by_userid)
                VALUES (%s, %s, UNIX_TIMESTAMP(), %s)
                ON DUPLICATE KEY UPDATE 
                    setting_value = VALUES(setting_value),
                    updated_timestamp = UNIX_TIMESTAMP(),
                    updated_by_userid = VALUES(updated_by_userid)
                """,
                (key, value, updated_by)
            )
            return True


def is_invite_system_enabled() -> bool:
    """
    Check if the invite system is enabled.
    
    When enabled: users who joined via invite have access.
    When disabled: only users from chat_members (Telegram group) have access.
    
    Returns:
        True if invite system is enabled, False otherwise.
        Defaults to True if setting is not found.
    """
    value = get_setting(SETTING_INVITE_SYSTEM_ENABLED)
    # Default to enabled if not set
    if value is None:
        return True
    return value == '1'


def set_invite_system_enabled(enabled: bool, updated_by: Optional[int] = None) -> bool:
    """
    Enable or disable the invite system.
    
    Args:
        enabled: True to enable, False to disable.
        updated_by: User ID of admin making the change (optional).
        
    Returns:
        True if successful.
    """
    return set_setting(SETTING_INVITE_SYSTEM_ENABLED, '1' if enabled else '0', updated_by)


def check_if_user_from_invite(telegram_id: int) -> bool:
    """
    Check if a user gained access through the invite system (not pre-invited).
    
    A user is considered "from invite" if:
    1. They consumed an invite code, AND
    2. They are NOT in the chat_members table (pre-invited)
    
    Args:
        telegram_id: The user's Telegram ID.
        
    Returns:
        True if user is from invite system only, False otherwise.
    """
    # Check if user has consumed an invite
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM invites WHERE consumed_userid = %s",
                (telegram_id,)
            )
            result = cursor.fetchone()
            has_consumed_invite = result['count'] > 0

    # Check if user is pre-invited (in chat_members table)
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                "SELECT COUNT(*) as count FROM chat_members WHERE telegram_id = %s",
                (telegram_id,)
            )
            result = cursor.fetchone()
            is_pre_invited = result['count'] > 0
    
    # User is "from invite" if they used invite AND are not pre-invited
    return has_consumed_invite and not is_pre_invited
