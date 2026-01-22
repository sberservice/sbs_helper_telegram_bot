from src.common import database

def check_if_user_legit(telegram_id) -> bool: #did the user use an invite
    """
        Checks whether the user has successfully used an invite.

        Queries the `invites` table to see if the given user_id appears as a
        `consumed_userid`. Returns True if at least one active invite has been
        consumed by this user, False otherwise.

        Args:
            user_id: Telegram user ID to verify.

        Returns:
            True if the user has a consumed invite (i.e., is legitimate), False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT count(consumed_userid) as invite_consumed from invites where consumed_userid=%s"
            val=(telegram_id,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            if result["invite_consumed"]>0:
                return True
            else:
                return False

def check_if_user_admin(telegram_id) -> bool:
    """
        Checks whether the user has admin privileges.

        Args:
            telegram_id: Telegram user ID to verify.

        Returns:
            True if the user is an admin, False otherwise.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT is_admin FROM users WHERE userid=%s"
            val=(telegram_id,)
            cursor.execute(sql_query,val)
            result = cursor.fetchone()
            if result and result.get("is_admin"):
                return True
            return False

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
            sql = "INSERT INTO users (userid, timestamp,first_name,last_name,username) VALUES (%s,UNIX_TIMESTAMP(), %s, %s, %s) on duplicate key update first_name=%s, last_name=%s, username=%s"
            val = (user.id,user.first_name,user.last_name,user.username,user.first_name,user.last_name,user.username)
            cursor.execute(sql, val)

class TelegramUser:
    def __init__(self,telegram_id: int):
        self.telegram_id = telegram_id
        self.user_name = None
            
    def get_name(self) -> str:
        return self.user_name
    
