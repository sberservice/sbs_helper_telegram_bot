"""
invites.py

Утилиты управления инвайт-кодами.

Функции:
- generate_invite_string(length=6) -> str: Генерирует алфавитно-цифровой код в верхнем регистре (без 0).
- invite_exists(invite) -> bool: Проверяет, существует ли инвайт-код в базе.
- generate_invite_for_user(user_id) -> str: Создаёт/сохраняет уникальный неиспользованный инвайт для пользователя.
- check_if_user_pre_invited(telegram_id) -> bool: Проверяет, есть ли пользователь в таблице chat_members.
- mark_pre_invited_user_activated(telegram_id) -> bool: Устанавливает activated_timestamp для пред-добавленного пользователя.
- add_pre_invited_user(telegram_id, added_by_userid, notes) -> bool: Добавляет пользователя в chat_members.
- remove_pre_invited_user(telegram_id) -> bool: Удаляет пользователя из chat_members.
- get_pre_invited_users() -> list: Возвращает всех пред-добавленных пользователей.
- is_pre_invited_user_activated(telegram_id) -> bool: Проверяет, активировался ли пред-добавленный пользователь.
"""

import string
import random
import src.common.database as database
from src.common.constants.errorcodes import InviteStatus

def generate_invite_string(length=6)->str:
    """
        Сгенерировать случайный инвайт-код указанной длины.

        Код состоит только из заглавных латинских букв (A-Z) и цифр 1-9
        (цифра 0 исключена, чтобы не путать её с буквой O).

        Args:
            length: Длина инвайт-кода (по умолчанию: 6).

        Returns:
            Случайная строка-инвайт запрошенной длины.
    """
    return ''.join(random.choice(string.ascii_uppercase + string.digits[1:]) for _ in range(length))
def invite_exists(invite)->bool:
    """
    Проверить, существует ли инвайт-код в базе данных.

    Args:
        invite (str): Инвайт-код для поиска.

    Returns:
        bool: True, если инвайт уже есть в таблице `invites`, иначе False.
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
        Сгенерировать уникальный 6-символьный инвайт-код и назначить его пользователю.

        Генерирует случайные коды, пока не найдёт свободный,
        затем вставляет его в таблицу `invites` с текущим временем.

        Args:
            user_id (int): Telegram ID пользователя, которому выдаётся инвайт.

        Returns:
            str: Новый уникальный инвайт-код.
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
# Функции для пред-добавленных пользователей (таблица chat_members)
# ============================================================================

def check_if_user_pre_invited(telegram_id) -> bool:
    """
    Проверить, есть ли пользователь в таблице chat_members (пред-добавлен).

    Args:
        telegram_id: Telegram ID пользователя для проверки.

    Returns:
        True, если пользователь есть в chat_members, иначе False.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT COUNT(*) as count FROM chat_members WHERE telegram_id = %s"
            cursor.execute(sql_query, (telegram_id,))
            result = cursor.fetchone()
            return result["count"] > 0


def is_pre_invited_user_activated(telegram_id) -> bool:
    """
    Проверить, активировался ли пред-добавленный пользователь (первое использование бота).

    Args:
        telegram_id: Telegram ID пользователя для проверки.

    Returns:
        True, если пользователь пред-добавлен и активировался, иначе False.
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
    Отметить пред-добавленного пользователя как активировавшегося (первое использование бота).
    Устанавливает activated_timestamp в текущее время.

    Args:
        telegram_id: Telegram ID пользователя для активации.

    Returns:
        True, если пользователь найден и обновлён, иначе False.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "UPDATE chat_members SET activated_timestamp = UNIX_TIMESTAMP() WHERE telegram_id = %s AND activated_timestamp IS NULL"
            cursor.execute(sql, (telegram_id,))
            return cursor.rowcount > 0


def add_pre_invited_user(telegram_id, added_by_userid=None, notes=None) -> bool:
    """
    Добавить пользователя в таблицу chat_members (пред-добавить).

    Args:
        telegram_id: Telegram ID пользователя.
        added_by_userid: ID администратора, добавляющего пользователя (опционально).
        notes: Дополнительные заметки о пользователе.

    Returns:
        True, если пользователь добавлен, False если уже существует.
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
                # Пользователь уже существует (нарушение уникального ограничения)
                return False


def remove_pre_invited_user(telegram_id) -> bool:
    """
    Удалить пользователя из таблицы chat_members.

    Примечание: если пользователь также использовал инвайт, доступ сохраняется через инвайт.

    Args:
        telegram_id: Telegram ID пользователя для удаления.

    Returns:
        True, если пользователь найден и удалён, иначе False.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "DELETE FROM chat_members WHERE telegram_id = %s"
            cursor.execute(sql, (telegram_id,))
            return cursor.rowcount > 0


def get_pre_invited_users(include_activated=True, limit=50, offset=0) -> list:
    """
    Получить список всех пред-добавленных пользователей.

    Args:
        include_activated: Если True, включает пользователей, уже активировавшихся.
                           Если False, возвращает только тех, кто ещё не использовал бота.
        limit: Максимальное число результатов.
        offset: Сколько результатов пропустить (для пагинации).

    Returns:
        Список словарей с данными: telegram_id, added_by_userid, notes,
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
    Получить количество пред-добавленных пользователей.

    Args:
        include_activated: Если True, считать всех. Если False — только ожидающих.

    Returns:
        Количество пред-добавленных пользователей.
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
    Получить все telegram_id из таблицы chat_members в виде множества.

    Оптимизировано для массового сравнения при синхронизации.

    Returns:
        Множество всех telegram_id в chat_members.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "SELECT telegram_id FROM chat_members"
            cursor.execute(sql)
            results = cursor.fetchall()
            return {row["telegram_id"] for row in results}


def bulk_add_pre_invited_users(telegram_ids: list, notes: str = None) -> int:
    """
    Добавить несколько пользователей в таблицу chat_members в одной транзакции.

    Пропускает пользователей, которые уже существуют (ON DUPLICATE KEY).

    Args:
        telegram_ids: Список Telegram ID для добавления.
        notes: Общая заметка для всех добавляемых пользователей (опционально).

    Returns:
        Количество реально добавленных пользователей (без дубликатов).
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
    Удалить несколько пользователей из таблицы chat_members в одной транзакции.

    Args:
        telegram_ids: Список Telegram ID для удаления.

    Returns:
        Количество реально удалённых пользователей.
    """
    if not telegram_ids:
        return 0
    
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            # Используем IN с параметризованным запросом
            placeholders = ", ".join(["%s"] * len(telegram_ids))
            sql = f"DELETE FROM chat_members WHERE telegram_id IN ({placeholders})"
            cursor.execute(sql, telegram_ids)
            return cursor.rowcount


# ============================================================================
# Функции для ручных пользователей (таблица manual_users)
# ============================================================================

def check_if_user_manual(telegram_id) -> bool:
    """
    Проверить, есть ли пользователь в таблице manual_users.

    Args:
        telegram_id: Telegram ID пользователя для проверки.

    Returns:
        True, если пользователь есть в manual_users, иначе False.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql_query = "SELECT COUNT(*) as count FROM manual_users WHERE telegram_id = %s"
            cursor.execute(sql_query, (telegram_id,))
            result = cursor.fetchone()
            return result["count"] > 0


def add_manual_user(telegram_id, added_by_userid, notes=None) -> bool:
    """
    Добавить пользователя в таблицу manual_users.

    Args:
        telegram_id: Telegram ID пользователя для добавления.
        added_by_userid: ID администратора, добавляющего пользователя.
        notes: Дополнительные заметки о пользователе.

    Returns:
        True, если пользователь добавлен, False если уже существует.
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
                # Пользователь уже существует (нарушение уникального ограничения)
                return False


def remove_manual_user(telegram_id) -> bool:
    """
    Удалить пользователя из таблицы manual_users.

    Args:
        telegram_id: Telegram ID пользователя для удаления.

    Returns:
        True, если пользователь найден и удалён, иначе False.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "DELETE FROM manual_users WHERE telegram_id = %s"
            cursor.execute(sql, (telegram_id,))
            return cursor.rowcount > 0


def get_manual_users(limit=50, offset=0) -> list:
    """
    Получить список всех ручных пользователей.

    Args:
        limit: Максимальное число результатов.
        offset: Сколько результатов пропустить (для пагинации).

    Returns:
        Список словарей с данными: telegram_id, added_by_userid, notes,
        created_timestamp, а также данные из users (если есть).
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
    Получить количество ручных пользователей.

    Returns:
        Общее число ручных пользователей.
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            sql = "SELECT COUNT(*) as count FROM manual_users"
            cursor.execute(sql)
            result = cursor.fetchone()
            return result["count"]


def get_manual_user_details(telegram_id) -> dict:
    """
    Получить данные конкретного ручного пользователя.

    Args:
        telegram_id: Telegram ID пользователя для поиска.

    Returns:
        Словарь с данными пользователя или None, если не найден.
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
