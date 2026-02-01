"""
bot_settings.py

Bot-wide settings management utilities.

Functions:
- get_setting(key) -> str | None: Gets a setting value by key.
- set_setting(key, value, updated_by) -> bool: Sets a setting value.
- is_invite_system_enabled() -> bool: Checks if invite system is enabled.
- set_invite_system_enabled(enabled, updated_by) -> bool: Enables/disables invite system.
- is_module_enabled(module_key) -> bool: Checks if a module is enabled.
- set_module_enabled(module_key, enabled, updated_by) -> bool: Enables/disables a module.
- get_all_module_states() -> dict: Gets enabled/disabled state for all modules.
"""

from typing import Optional, Dict, List
import src.common.database as database

# Setting keys
SETTING_INVITE_SYSTEM_ENABLED = 'invite_system_enabled'

# Module configuration
# Each module has:
# - key: unique identifier for the module
# - setting_key: database setting key for enable/disable
# - button_label: text displayed on the module button
# - order: display order (lower numbers appear first)
# - columns: number of buttons per row (1 or 2)
MODULE_CONFIG = [
    {
        'key': 'certification',
        'setting_key': 'module_certification_enabled',
        'button_label': '📝 Аттестация',
        'order': 1,
        'columns': 2
    },
    {
        'key': 'screenshot',
        'setting_key': 'module_screenshot_enabled',
        'button_label': '📸 Обработать скриншот',
        'order': 2,
        'columns': 2
    },
    {
        'key': 'upos_errors',
        'setting_key': 'module_upos_errors_enabled',
        'button_label': '🔢 UPOS Ошибки',
        'order': 3,
        'columns': 2
    },
    {
        'key': 'ticket_validator',
        'setting_key': 'module_ticket_validator_enabled',
        'button_label': '✅ Валидация заявок',
        'order': 4,
        'columns': 2
    },
    {
        'key': 'ktr',
        'setting_key': 'module_ktr_enabled',
        'button_label': '⏱️ КТР',
        'order': 5,
        'columns': 2
    },
    {
        'key': 'feedback',
        'setting_key': 'module_feedback_enabled',
        'button_label': '📬 Обратная связь',
        'order': 6,
        'columns': 2
    },
    {
        'key': 'news',
        'setting_key': 'module_news_enabled',
        'button_label': '📰 Новости',
        'order': 7,
        'columns': 2
    },
]

# Build MODULE_KEYS from MODULE_CONFIG for backward compatibility
MODULE_KEYS = {module['key']: module['setting_key'] for module in MODULE_CONFIG}

# Build MODULE_NAMES from MODULE_CONFIG for backward compatibility
MODULE_NAMES = {module['key']: module['button_label'] for module in MODULE_CONFIG}


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


def is_module_enabled(module_key: str) -> bool:
    """
    Check if a specific module is enabled.
    
    Args:
        module_key: The module key (e.g., 'ticket_validator', 'screenshot', etc.)
        
    Returns:
        True if the module is enabled, False otherwise.
        Defaults to True if setting is not found.
    """
    if module_key not in MODULE_KEYS:
        return True  # Unknown modules are enabled by default
    
    setting_key = MODULE_KEYS[module_key]
    value = get_setting(setting_key)
    # Default to enabled if not set
    if value is None:
        return True
    return value == '1'


def set_module_enabled(module_key: str, enabled: bool, updated_by: Optional[int] = None) -> bool:
    """
    Enable or disable a specific module.
    
    Args:
        module_key: The module key (e.g., 'ticket_validator', 'screenshot', etc.)
        enabled: True to enable, False to disable.
        updated_by: User ID of admin making the change (optional).
        
    Returns:
        True if successful, False if module key is invalid.
    """
    if module_key not in MODULE_KEYS:
        return False
    
    setting_key = MODULE_KEYS[module_key]
    return set_setting(setting_key, '1' if enabled else '0', updated_by)


def get_all_module_states() -> Dict[str, bool]:
    """
    Get enabled/disabled state for all modules.
    
    Returns:
        Dictionary mapping module_key to enabled state (True/False).
    """
    return {key: is_module_enabled(key) for key in MODULE_KEYS.keys()}


def get_enabled_modules() -> List[str]:
    """
    Get list of enabled module keys.
    
    Returns:
        List of module keys that are currently enabled.
    """
    return [key for key, enabled in get_all_module_states().items() if enabled]


def get_modules_config(enabled_only: bool = True) -> List[Dict[str, any]]:
    """
    Get module configuration in display order.
    
    Args:
        enabled_only: If True, return only enabled modules. If False, return all modules.
    
    Returns:
        List of module configuration dictionaries, sorted by order field.
        Each dictionary contains: key, setting_key, button_label, order, columns.
    """
    # Sort modules by order field
    sorted_modules = sorted(MODULE_CONFIG, key=lambda x: x['order'])
    
    if enabled_only:
        # Filter to only enabled modules
        return [module for module in sorted_modules if is_module_enabled(module['key'])]
    
    return sorted_modules


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
