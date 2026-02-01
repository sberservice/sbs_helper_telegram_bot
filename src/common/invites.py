"""
invites.py

Invite code management utilities.

Functions:
- generate_invite_string(length=6) -> str: Generates an uppercase alphanumeric code (without 0).
- invite_exists(invite) -> bool: Checks if an invite code already exists in the database.
- generate_invite_for_user(user_id) -> str: Creates/stores a unique unused invite code for a user.
- check_if_user_pre_invited(telegram_id) -> bool: Checks if user is in the chat_members table.
- mark_pre_invited_user_activated(telegram_id) -> bool: Sets activated_timestamp for a pre-invited user.
- add_pre_invited_user(telegram_id, added_by_userid, notes) -> bool: Adds user to chat_members.
- remove_pre_invited_user(telegram_id) -> bool: Removes user from chat_members.
- get_pre_invited_users() -> list: Returns all pre-invited users.
- is_pre_invited_user_activated(telegram_id) -> bool: Checks if pre-invited user has activated.
"""

import string
import random
import src.common.database as database
from src.common.constants.errorcodes import InviteStatus

def generate_invite_string(length=6)->str:
    """
        Generate a random invite code of the specified length.

        The code consists only of uppercase Latin letters (A-Z) and digits 1-9
        (digit 0 is excluded to avoid confusion with the letter O).

        Args:
            length: Length of the invite code (default: 6).

        Returns:
            Random invite string of the requested length.
    """
    return ''.join(random.choice(string.ascii_uppercase + string.digits[1:]) for _ in range(length))
def invite_exists(invite)->bool:
    """
    Check whether an invite code already exists in the database.

    Args:
        invite (str): The invite code to look up.

    Returns:
        bool: True if the invite code is already present in the `invites` table,
              False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT count(*) as invites_count from invites where invite=%s"
            val=(invite,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            return result["invites_count"]>0

def generate_invite_for_user(user_id):
    """
        Generates a unique 6-character invite code and assigns it to the given user.

        Keeps generating random codes until a non-existing one is found,
        then inserts it into the `invites` table with the current timestamp.

        Args:
            user_id (int): Telegram user ID to whom the invite will be issued.

        Returns:
            str: The newly created unique invite code.
    """
    while True:
        invite=generate_invite_string(6)
        if invite_exists(invite):
            pass
        else:
            break
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "INSERT INTO invites (userid,invite,issued_timestamp) VALUES (%s,%s,UNIX_TIMESTAMP())"
            val = (user_id,invite)
            cursor.execute(sql, val)
            return invite


# ============================================================================
# Pre-invited users (chat_members table) functions
# ============================================================================

def check_if_user_pre_invited(telegram_id) -> bool:
    """
    Check if a user exists in the chat_members table (pre-invited).
    
    Args:
        telegram_id: Telegram user ID to check.
        
    Returns:
        True if user is in chat_members table, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT COUNT(*) as count FROM chat_members WHERE telegram_id = %s"
            cursor.execute(sql_query, (telegram_id,))
            result = cursor.fetchone()
            return result["count"] > 0


def is_pre_invited_user_activated(telegram_id) -> bool:
    """
    Check if a pre-invited user has already activated (first used the bot).
    
    Args:
        telegram_id: Telegram user ID to check.
        
    Returns:
        True if user is pre-invited AND has activated, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT activated_timestamp FROM chat_members WHERE telegram_id = %s"
            cursor.execute(sql_query, (telegram_id,))
            result = cursor.fetchone()
            if result is None:
                return False
            return result["activated_timestamp"] is not None


def mark_pre_invited_user_activated(telegram_id) -> bool:
    """
    Mark a pre-invited user as activated (first use of the bot).
    Sets activated_timestamp to current time.
    
    Args:
        telegram_id: Telegram user ID to activate.
        
    Returns:
        True if user was found and updated, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "UPDATE chat_members SET activated_timestamp = UNIX_TIMESTAMP() WHERE telegram_id = %s AND activated_timestamp IS NULL"
            cursor.execute(sql, (telegram_id,))
            return cursor.rowcount > 0


def add_pre_invited_user(telegram_id, added_by_userid=None, notes=None) -> bool:
    """
    Add a user to the chat_members table (pre-invite them).
    
    Args:
        telegram_id: Telegram user ID to pre-invite.
        added_by_userid: Admin user ID who is adding this user (optional).
        notes: Optional notes about the user.
        
    Returns:
        True if user was added, False if user already exists.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            try:
                sql = """
                    INSERT INTO chat_members (telegram_id, added_by_userid, notes, created_timestamp)
                    VALUES (%s, %s, %s, UNIX_TIMESTAMP())
                """
                cursor.execute(sql, (telegram_id, added_by_userid, notes))
                return True
            except Exception:
                # User already exists (unique constraint violation)
                return False


def remove_pre_invited_user(telegram_id) -> bool:
    """
    Remove a user from the chat_members table.
    
    Note: If user has also redeemed an invite, they will retain access via the invite.
    
    Args:
        telegram_id: Telegram user ID to remove.
        
    Returns:
        True if user was found and removed, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "DELETE FROM chat_members WHERE telegram_id = %s"
            cursor.execute(sql, (telegram_id,))
            return cursor.rowcount > 0


def get_pre_invited_users(include_activated=True, limit=50, offset=0) -> list:
    """
    Get list of all pre-invited users.
    
    Args:
        include_activated: If True, includes users who have already activated.
                          If False, only returns users who haven't used the bot yet.
        limit: Maximum number of results to return.
        offset: Number of results to skip (for pagination).
        
    Returns:
        List of dicts with user info: telegram_id, added_by_userid, notes,
        created_timestamp, activated_timestamp.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            if include_activated:
                sql = """
                    SELECT telegram_id, added_by_userid, notes, created_timestamp, activated_timestamp
                    FROM chat_members
                    ORDER BY created_timestamp DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (limit, offset))
            else:
                sql = """
                    SELECT telegram_id, added_by_userid, notes, created_timestamp, activated_timestamp
                    FROM chat_members
                    WHERE activated_timestamp IS NULL
                    ORDER BY created_timestamp DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(sql, (limit, offset))
            return cursor.fetchall()


def get_pre_invited_user_count(include_activated=True) -> int:
    """
    Get count of pre-invited users.
    
    Args:
        include_activated: If True, counts all users. If False, only pending.
        
    Returns:
        Number of pre-invited users.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            if include_activated:
                sql = "SELECT COUNT(*) as count FROM chat_members"
                cursor.execute(sql)
            else:
                sql = "SELECT COUNT(*) as count FROM chat_members WHERE activated_timestamp IS NULL"
                cursor.execute(sql)
            result = cursor.fetchone()
            return result["count"]


def get_all_pre_invited_telegram_ids() -> set:
    """
    Get all telegram_ids from chat_members table as a set.
    
    Optimized for bulk comparison during sync operations.
    
    Returns:
        Set of all telegram_id values in chat_members.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "SELECT telegram_id FROM chat_members"
            cursor.execute(sql)
            results = cursor.fetchall()
            return {row["telegram_id"] for row in results}


def bulk_add_pre_invited_users(telegram_ids: list, notes: str = None) -> int:
    """
    Add multiple users to chat_members table in a single transaction.
    
    Skips users that already exist (ON DUPLICATE KEY).
    
    Args:
        telegram_ids: List of Telegram user IDs to add.
        notes: Optional notes to add for all users.
        
    Returns:
        Number of users actually added (excludes duplicates).
    """
    if not telegram_ids:
        return 0
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                INSERT IGNORE INTO chat_members (telegram_id, added_by_userid, notes, created_timestamp)
                VALUES (%s, NULL, %s, UNIX_TIMESTAMP())
            """
            data = [(tid, notes) for tid in telegram_ids]
            cursor.executemany(sql, data)
            return cursor.rowcount


def bulk_remove_pre_invited_users(telegram_ids: list) -> int:
    """
    Remove multiple users from chat_members table in a single transaction.
    
    Args:
        telegram_ids: List of Telegram user IDs to remove.
        
    Returns:
        Number of users actually removed.
    """
    if not telegram_ids:
        return 0
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Use IN clause with parameterized query
            placeholders = ", ".join(["%s"] * len(telegram_ids))
            sql = f"DELETE FROM chat_members WHERE telegram_id IN ({placeholders})"
            cursor.execute(sql, telegram_ids)
            return cursor.rowcount


# ============================================================================
# Manual users (manual_users table) functions
# ============================================================================

def check_if_user_manual(telegram_id) -> bool:
    """
    Check if a user exists in the manual_users table.
    
    Args:
        telegram_id: Telegram user ID to check.
        
    Returns:
        True if user is in manual_users table, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT COUNT(*) as count FROM manual_users WHERE telegram_id = %s"
            cursor.execute(sql_query, (telegram_id,))
            result = cursor.fetchone()
            return result["count"] > 0


def add_manual_user(telegram_id, added_by_userid, notes=None) -> bool:
    """
    Add a user to the manual_users table.
    
    Args:
        telegram_id: Telegram user ID to add.
        added_by_userid: Admin user ID who is adding this user.
        notes: Optional notes about the user.
        
    Returns:
        True if user was added, False if user already exists.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            try:
                sql = """
                    INSERT INTO manual_users (telegram_id, added_by_userid, notes, created_timestamp)
                    VALUES (%s, %s, %s, UNIX_TIMESTAMP())
                """
                cursor.execute(sql, (telegram_id, added_by_userid, notes))
                return True
            except Exception:
                # User already exists (unique constraint violation)
                return False


def remove_manual_user(telegram_id) -> bool:
    """
    Remove a user from the manual_users table.
    
    Args:
        telegram_id: Telegram user ID to remove.
        
    Returns:
        True if user was found and removed, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "DELETE FROM manual_users WHERE telegram_id = %s"
            cursor.execute(sql, (telegram_id,))
            return cursor.rowcount > 0


def get_manual_users(limit=50, offset=0) -> list:
    """
    Get list of all manual users.
    
    Args:
        limit: Maximum number of results to return.
        offset: Number of results to skip (for pagination).
        
    Returns:
        List of dicts with user info: telegram_id, added_by_userid, notes,
        created_timestamp, plus user info from users table if available.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                SELECT 
                    mu.telegram_id,
                    mu.added_by_userid,
                    mu.notes,
                    mu.created_timestamp,
                    u.first_name,
                    u.last_name,
                    u.username
                FROM manual_users mu
                LEFT JOIN users u ON mu.telegram_id = u.userid
                ORDER BY mu.created_timestamp DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(sql, (limit, offset))
            return cursor.fetchall()


def get_manual_user_count() -> int:
    """
    Get count of manual users.
    
    Returns:
        Total number of manual users.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "SELECT COUNT(*) as count FROM manual_users"
            cursor.execute(sql)
            result = cursor.fetchone()
            return result["count"]


def get_manual_user_details(telegram_id) -> dict:
    """
    Get details of a specific manual user.
    
    Args:
        telegram_id: Telegram user ID to look up.
        
    Returns:
        Dict with user info or None if not found.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = """
                SELECT 
                    mu.telegram_id,
                    mu.added_by_userid,
                    mu.notes,
                    mu.created_timestamp,
                    u.first_name,
                    u.last_name,
                    u.username
                FROM manual_users mu
                LEFT JOIN users u ON mu.telegram_id = u.userid
                WHERE mu.telegram_id = %s
            """
            cursor.execute(sql, (telegram_id,))
            return cursor.fetchone()
