from src.common import database
from src.common import invites as invites_module
from src.common import bot_settings
from src.common.messages import MESSAGE_PLEASE_ENTER_INVITE, MESSAGE_INVITE_SYSTEM_DISABLED

def check_if_user_legit(telegram_id) -> bool:
    """
        Проверить, авторизован ли пользователь для работы с ботом.

        Пользователь считается легитимным, если:
        1. Он успешно использовал инвайт (только когда инвайт-система включена), ИЛИ
        2. Он пред-добавлен в таблицу chat_members, ИЛИ
        3. Он находится в таблице manual_users (добавлен администратором).

        Когда инвайт-система выключена, пользователи, вошедшие только по инвайту
        (не пред-добавленные и не вручную добавленные), теряют доступ.

        Args:
            telegram_id: Telegram ID пользователя для проверки.

        Returns:
            True, если пользователь авторизован, иначе False.
    """
    # Проверяем, пред-добавлен ли пользователь (таблица chat_members)
    # Пред-добавленные пользователи всегда имеют доступ независимо от настроек инвайтов
    if invites_module.check_if_user_pre_invited(telegram_id):
        return True
    
    # Проверяем, добавлен ли пользователь вручную (таблица manual_users)
    # Вручную добавленные пользователи всегда имеют доступ независимо от настроек инвайтов
    if invites_module.check_if_user_manual(telegram_id):
        return True
    
    # Если инвайт-система выключена, доступ есть только у пред-добавленных и ручных пользователей
    if not bot_settings.is_invite_system_enabled():
        return False
    
    # Проверяем, использовал ли пользователь инвайт (только когда инвайт-система включена)
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
        Проверить, должен ли пользователь быть заблокирован из-за выключенной инвайт-системы.

        Возвращает True, если:
        1. Инвайт-система сейчас выключена, И
        2. Пользователя НЕТ в chat_members (пред-добавленные), И
        3. Пользователя НЕТ в manual_users (вручную добавленные).

        Когда инвайт-система выключена, доступ есть только у chat_members и manual_users.

        Args:
            telegram_id: Telegram ID пользователя для проверки.

        Returns:
            True, если пользователю нужно показать сообщение о выключенной инвайт-системе.
    """
    # Если инвайт-система включена, никто не блокируется
    if bot_settings.is_invite_system_enabled():
        return False
    
    # Если пользователь пред-добавлен (chat_members), он не блокируется
    if invites_module.check_if_user_pre_invited(telegram_id):
        return False
    
    # Если пользователь добавлен вручную (manual_users), он не блокируется
    if invites_module.check_if_user_manual(telegram_id):
        return False
    
    # При выключенной инвайт-системе блокируется любой, кто не в chat_members или manual_users
    return True


def get_unauthorized_message(telegram_id) -> str:
    """
        Вернуть подходящее сообщение, когда пользователь не авторизован.

        Если инвайт-система выключена и пользователь заблокирован,
        возвращает сообщение о выключенной инвайт-системе. Иначе — приглашение ввести инвайт.

        Args:
            telegram_id: Telegram ID пользователя для проверки.

        Returns:
            Строка сообщения, подходящая для reply_text.
    """
    if check_if_invite_user_blocked(telegram_id):
        return MESSAGE_INVITE_SYSTEM_DISABLED
    return MESSAGE_PLEASE_ENTER_INVITE


def check_if_user_admin(telegram_id) -> bool:
    """
        Проверить, является ли пользователь администратором.

        Проверяет таблицу `users` на наличие is_admin = 1 для указанного user_id.

        Args:
            telegram_id: Telegram ID пользователя для проверки.

        Returns:
            True, если пользователь администратор, иначе False.
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


def get_all_admin_ids() -> list:
    """
        Получить все ID администраторов из таблицы users.

        Returns:
            Список Telegram ID пользователей со статусом администратора.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT userid FROM users WHERE is_admin = 1"
            cursor.execute(sql_query)
            results = cursor.fetchall()
            return [row["userid"] for row in results]


def set_user_admin(telegram_id, is_admin: bool = True) -> bool:
    """
        Назначить или снять администраторские права у пользователя.

        Args:
            telegram_id: Telegram ID пользователя.
            is_admin: True — назначить админом, False — снять права.

        Returns:
            True при успехе, иначе False.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "UPDATE users SET is_admin=%s WHERE userid=%s"
            val = (1 if is_admin else 0, telegram_id)
            cursor.execute(sql_query, val)
            return cursor.rowcount > 0


def update_user_info_from_telegram(user) -> None:
    """
        Обновить или вставить данные пользователя из Telegram Update в таблицу `users`.

        Использует INSERT ... ON DUPLICATE KEY UPDATE для создания записи
        или обновления first_name, last_name и username, если пользователь уже существует.

        Args:
            user: объект telegram.User с полями id, first_name, last_name, username.
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
    
