from src.common import database
from src.common import invites as invites_module
from src.common import bot_settings

def check_if_user_legit(telegram_id) -> bool:
    """
        Checks whether the user is authorized to use the bot.

        A user is considered legitimate if they have:
        1. Successfully consumed an invite code (only when invite system is enabled), OR
        2. Are pre-registered in the chat_members table

        When the invite system is disabled, users who joined only via invite
        (not pre-invited) lose access.

        Args:
            telegram_id: Telegram user ID to verify.

        Returns:
            True if the user is authorized, False otherwise.
    """
    # Check if user is pre-invited (in chat_members table)
    # Pre-invited users always have access regardless of invite system setting
    if invites_module.check_if_user_pre_invited(telegram_id):
        return True
    
    # If invite system is disabled, only pre-invited users have access
    if not bot_settings.is_invite_system_enabled():
        return False
    
    # Check if user has consumed an invite (only when invite system is enabled)
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT count(consumed_userid) as invite_consumed from invites where consumed_userid=%s"
            val=(telegram_id,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            if result["invite_consumed"] > 0:
                return True
    
    return False


def check_if_invite_user_blocked(telegram_id) -> bool:
    """
        Checks if a user should be blocked due to invite system being disabled.
        
        Returns True if:
        1. User joined via invite (not pre-invited), AND
        2. Invite system is currently disabled
        
        Args:
            telegram_id: Telegram user ID to check.
            
        Returns:
            True if user should see the "invite system disabled" message.
    """
    # If invite system is enabled, no one is blocked
    if bot_settings.is_invite_system_enabled():
        return False
    
    # If user is pre-invited, they're not blocked
    if invites_module.check_if_user_pre_invited(telegram_id):
        return False
    
    # Check if user has consumed an invite (i.e., they joined via invite)
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT count(consumed_userid) as invite_consumed from invites where consumed_userid=%s"
            val=(telegram_id,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            # If they have consumed an invite but invite system is disabled, they're blocked
            return result["invite_consumed"] > 0


def check_if_user_admin(telegram_id) -> bool:
    """
        Checks whether the user is an admin.

        Queries the `users` table to see if the given user_id has is_admin = 1.

        Args:
            telegram_id: Telegram user ID to verify.

        Returns:
            True if the user is an admin, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT is_admin FROM users WHERE userid=%s"
            val = (telegram_id,)
            cursor.execute(sql_query, val)
            result = cursor.fetchone()
            if result and result["is_admin"] == 1:
                return True
            return False


def set_user_admin(telegram_id, is_admin: bool = True) -> bool:
    """
        Sets or removes admin status for a user.

        Args:
            telegram_id: Telegram user ID to modify.
            is_admin: True to grant admin, False to revoke.

        Returns:
            True if operation was successful, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "UPDATE users SET is_admin=%s WHERE userid=%s"
            val = (1 if is_admin else 0, telegram_id)
            cursor.execute(sql_query, val)
            return cursor.rowcount > 0


def update_user_info_from_telegram(user) -> None:
    """
        Updates or inserts user information from a Telegram Update into the `users` table.

        Uses INSERT ... ON DUPLICATE KEY UPDATE to either create a new record
        or refresh first_name, last_name, and username if the user already exists.

        Args:
            user: telegram.User object containing id, first_name, last_name, username.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "INSERT INTO users (userid, timestamp, first_name, last_name, username, is_admin) VALUES (%s, UNIX_TIMESTAMP(), %s, %s, %s, 0) ON DUPLICATE KEY UPDATE first_name=%s, last_name=%s, username=%s"
            val = (user.id, user.first_name, user.last_name, user.username, user.first_name, user.last_name, user.username)
            cursor.execute(sql, val)

class TelegramUser:
    def __init__(self,telegram_id: int):
        self.telegram_id = telegram_id
        self.user_name = None
            
    def get_name(self) -> str:
        return self.user_name
    
