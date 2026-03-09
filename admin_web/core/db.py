"""Слой работы с БД для веб-платформы: сессии, роли, права доступа.

Использует пул подключений из src.common.database.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from src.common import database
from admin_web.core.models import ModulePermission, WebRole, WebUser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Сессии
# ---------------------------------------------------------------------------


def create_session(
    *,
    telegram_id: int,
    telegram_username: Optional[str] = None,
    telegram_first_name: Optional[str] = None,
    telegram_last_name: Optional[str] = None,
    telegram_photo_url: Optional[str] = None,
    ttl_hours: int = 24,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None,
    auth_method: str = "telegram",
    local_account_id: Optional[int] = None,
) -> str:
    """
    Создать новую сессию аутентификации.

    Returns:
        Токен сессии (64 символа URL-safe).
    """
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    query = """
        INSERT INTO web_sessions
            (id, telegram_id, telegram_username, telegram_first_name,
             telegram_last_name, telegram_photo_url, expires_at,
             user_agent, ip_address, auth_method, local_account_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (
                    token,
                    telegram_id,
                    telegram_username,
                    telegram_first_name,
                    telegram_last_name,
                    telegram_photo_url,
                    expires_at,
                    user_agent,
                    ip_address,
                    auth_method,
                    local_account_id,
                ))
        return token
    except Exception as exc:
        logger.error("Ошибка создания web-сессии: %s", exc, exc_info=True)
        raise


def get_session(token: str) -> Optional[Dict[str, Any]]:
    """
    Получить активную сессию по токену.

    Returns:
        Данные сессии или None если сессия не найдена / истекла / неактивна.
    """
    query = """
        SELECT id, telegram_id, telegram_username, telegram_first_name,
               telegram_last_name, telegram_photo_url,
               created_at, expires_at, is_active, auth_method, local_account_id
        FROM web_sessions
        WHERE id = %s AND is_active = TRUE AND expires_at > NOW()
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (token,))
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения web-сессии: %s", exc, exc_info=True)
        return None


def invalidate_session(token: str) -> bool:
    """Деактивировать сессию (выход)."""
    query = "UPDATE web_sessions SET is_active = FALSE WHERE id = %s"
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (token,))
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка деактивации web-сессии: %s", exc, exc_info=True)
        return False


def cleanup_expired_sessions() -> int:
    """Удалить истёкшие сессии. Возвращает количество удалённых."""
    query = "DELETE FROM web_sessions WHERE expires_at < NOW() OR is_active = FALSE"
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query)
                deleted = cursor.rowcount
                if deleted > 0:
                    logger.info("Удалено %d истёкших web-сессий", deleted)
                return deleted
    except Exception as exc:
        logger.error("Ошибка очистки web-сессий: %s", exc, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Роли пользователей
# ---------------------------------------------------------------------------


def get_user_role(telegram_id: int) -> Optional[WebRole]:
    """Получить роль пользователя. Возвращает None если роль не назначена."""
    query = "SELECT role FROM web_user_roles WHERE telegram_id = %s"
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (telegram_id,))
                row = cursor.fetchone()
                if row:
                    return WebRole(row["role"])
                return None
    except Exception as exc:
        logger.error("Ошибка получения роли пользователя: %s", exc, exc_info=True)
        return None


def set_user_role(
    telegram_id: int,
    role: WebRole,
    created_by: Optional[int] = None,
) -> bool:
    """Назначить или обновить роль пользователя."""
    query = """
        INSERT INTO web_user_roles (telegram_id, role, created_by)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE role = VALUES(role), created_by = VALUES(created_by)
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (telegram_id, role.value, created_by))
                return True
    except Exception as exc:
        logger.error("Ошибка назначения роли: %s", exc, exc_info=True)
        return False


def list_user_roles() -> List[Dict[str, Any]]:
    """Получить список всех пользователей с ролями."""
    query = """
        SELECT telegram_id, role, created_at, updated_at, created_by
        FROM web_user_roles
        ORDER BY updated_at DESC
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query)
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения списка ролей: %s", exc, exc_info=True)
        return []


def delete_user_role(telegram_id: int) -> bool:
    """Удалить роль пользователя."""
    query = "DELETE FROM web_user_roles WHERE telegram_id = %s"
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (telegram_id,))
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка удаления роли: %s", exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Права доступа
# ---------------------------------------------------------------------------


def get_role_permissions(role: WebRole) -> List[ModulePermission]:
    """Получить права доступа для роли."""
    query = """
        SELECT module_key, can_view, can_edit
        FROM web_role_permissions
        WHERE role = %s
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (role.value,))
                rows = cursor.fetchall() or []
                return [
                    ModulePermission(
                        module_key=r["module_key"],
                        can_view=bool(r["can_view"]),
                        can_edit=bool(r["can_edit"]),
                    )
                    for r in rows
                ]
    except Exception as exc:
        logger.error("Ошибка получения прав доступа: %s", exc, exc_info=True)
        return []


def build_web_user(
    telegram_id: int,
    telegram_username: Optional[str] = None,
    telegram_first_name: Optional[str] = None,
    telegram_last_name: Optional[str] = None,
    telegram_photo_url: Optional[str] = None,
    auth_method: str = "telegram",
    local_account_id: Optional[int] = None,
) -> WebUser:
    """
    Построить объект WebUser из telegram_id с ролями и правами из БД.

    Если роль не назначена, проверяет is_admin в таблице users.
    Если is_admin=1, автоматически создаёт роль super_admin.
    """
    role = get_user_role(telegram_id)

    # Автоматическая миграция: бот-админы получают super_admin
    if role is None:
        try:
            from src.common.telegram_user import check_if_user_admin
            if check_if_user_admin(telegram_id):
                role = WebRole.SUPER_ADMIN
                set_user_role(telegram_id, role)
                logger.info(
                    "Автоматически назначена роль super_admin для бот-админа: telegram_id=%d",
                    telegram_id,
                )
        except Exception:
            pass

    if role is None:
        role = WebRole.VIEWER

    permissions = get_role_permissions(role)

    return WebUser(
        telegram_id=telegram_id,
        telegram_username=telegram_username,
        telegram_first_name=telegram_first_name,
        telegram_last_name=telegram_last_name,
        telegram_photo_url=telegram_photo_url,
        auth_method=auth_method,
        local_account_id=local_account_id,
        role=role,
        permissions=permissions,
    )


# ---------------------------------------------------------------------------
# Локальные password-аккаунты
# ---------------------------------------------------------------------------


def normalize_login(login: str) -> str:
    """Нормализовать логин для хранения и поиска."""
    return (login or "").strip().lower()


def hash_password(password: str) -> str:
    """Хешировать пароль с PBKDF2-SHA256."""
    salt = secrets.token_hex(16)
    iterations = 310_000
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    """Проверить пароль против сохранённого PBKDF2-хеша."""
    try:
        algo, iter_str, salt, expected = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _generate_standalone_principal_id(cursor: Any) -> int:
    """Сгенерировать стабильный principal id для standalone-аккаунта."""
    for _ in range(20):
        candidate = 9_000_000_000_000_000 + secrets.randbelow(100_000_000_000_000)
        cursor.execute(
            """
            SELECT 1
            FROM web_local_accounts
            WHERE principal_telegram_id = %s
            LIMIT 1
            """,
            (candidate,),
        )
        if not cursor.fetchone():
            return candidate
    raise RuntimeError("Не удалось сгенерировать уникальный principal id")


def create_local_account(
    *,
    login: str,
    password_hash: str,
    role: WebRole,
    created_by: Optional[int] = None,
    linked_telegram_id: Optional[int] = None,
    display_name: Optional[str] = None,
    is_active: bool = True,
) -> Dict[str, Any]:
    """Создать локальный password-аккаунт и назначить роль."""
    norm_login = normalize_login(login)
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                principal_id = linked_telegram_id
                if principal_id is None:
                    principal_id = _generate_standalone_principal_id(cursor)

                cursor.execute(
                    """
                    INSERT INTO web_local_accounts
                        (login, password_hash, principal_telegram_id, linked_telegram_id,
                         display_name, is_active, created_by, updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        norm_login,
                        password_hash,
                        principal_id,
                        linked_telegram_id,
                        display_name,
                        bool(is_active),
                        created_by,
                        created_by,
                    ),
                )

                local_account_id = cursor.lastrowid

                cursor.execute(
                    """
                    INSERT INTO web_user_roles (telegram_id, role, created_by)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE role = VALUES(role), created_by = VALUES(created_by)
                    """,
                    (principal_id, role.value, created_by),
                )

                cursor.execute(
                    """
                    SELECT id, login, principal_telegram_id, linked_telegram_id,
                           display_name, is_active, failed_attempts, locked_until,
                           created_at, updated_at
                    FROM web_local_accounts
                    WHERE id = %s
                    """,
                    (local_account_id,),
                )
                row = cursor.fetchone() or {}
                row["role"] = role.value
                return row
    except Exception as exc:
        logger.error("Ошибка создания локального аккаунта: %s", exc, exc_info=True)
        raise


def list_local_accounts() -> List[Dict[str, Any]]:
    """Получить список локальных password-аккаунтов."""
    query = """
        SELECT la.id, la.login, la.principal_telegram_id, la.linked_telegram_id,
               la.display_name, la.is_active, la.failed_attempts, la.locked_until,
               la.created_at, la.updated_at, ur.role
        FROM web_local_accounts la
        LEFT JOIN web_user_roles ur ON ur.telegram_id = la.principal_telegram_id
        ORDER BY la.updated_at DESC
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query)
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения списка локальных аккаунтов: %s", exc, exc_info=True)
        return []


def get_local_account_by_login(login: str) -> Optional[Dict[str, Any]]:
    """Получить локальный аккаунт по логину."""
    query = """
        SELECT id, login, password_hash, principal_telegram_id, linked_telegram_id,
               display_name, is_active, failed_attempts, locked_until,
               created_at, updated_at
        FROM web_local_accounts
        WHERE login = %s
        LIMIT 1
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (normalize_login(login),))
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения локального аккаунта по логину: %s", exc, exc_info=True)
        return None


def get_local_account_by_id(local_account_id: int) -> Optional[Dict[str, Any]]:
    """Получить локальный аккаунт по ID."""
    query = """
        SELECT id, login, principal_telegram_id, linked_telegram_id, display_name,
               is_active, failed_attempts, locked_until, created_at, updated_at
        FROM web_local_accounts
        WHERE id = %s
        LIMIT 1
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (local_account_id,))
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения локального аккаунта по id: %s", exc, exc_info=True)
        return None


def record_auth_attempt(
    *,
    login_identifier: Optional[str],
    ip_address: Optional[str],
    auth_method: str,
    success: bool,
    reason: Optional[str] = None,
    principal_telegram_id: Optional[int] = None,
) -> None:
    """Записать попытку аутентификации."""
    query = """
        INSERT INTO web_auth_attempts
            (login_identifier, ip_address, auth_method, success, reason, principal_telegram_id)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    query,
                    (
                        normalize_login(login_identifier) if login_identifier else None,
                        ip_address,
                        auth_method,
                        bool(success),
                        reason,
                        principal_telegram_id,
                    ),
                )
    except Exception as exc:
        logger.warning("Не удалось записать попытку auth: %s", exc)


def count_recent_failed_attempts(
    *,
    login_identifier: Optional[str],
    ip_address: Optional[str],
    auth_method: str,
    window_seconds: int,
) -> int:
    """Посчитать число неуспешных попыток в скользящем окне."""
    login_norm = normalize_login(login_identifier or "")
    query = """
        SELECT COUNT(*) AS total
        FROM web_auth_attempts
        WHERE auth_method = %s
          AND success = FALSE
          AND created_at >= (NOW() - INTERVAL %s SECOND)
          AND (
              (login_identifier IS NOT NULL AND login_identifier = %s)
              OR
              (ip_address IS NOT NULL AND ip_address = %s)
          )
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (auth_method, window_seconds, login_norm, ip_address))
                row = cursor.fetchone() or {"total": 0}
                return int(row.get("total") or 0)
    except Exception as exc:
        logger.error("Ошибка подсчёта неуспешных auth-попыток: %s", exc, exc_info=True)
        return 0


def mark_local_account_auth_failure(
    local_account_id: int,
    *,
    lockout_threshold: int,
    lockout_minutes: int,
) -> Optional[datetime]:
    """Увеличить счётчик неудач и при необходимости установить блокировку."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    UPDATE web_local_accounts
                    SET failed_attempts = failed_attempts + 1,
                        locked_until = CASE
                            WHEN failed_attempts + 1 >= %s
                                THEN (NOW() + INTERVAL %s MINUTE)
                            ELSE locked_until
                        END,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (lockout_threshold, lockout_minutes, local_account_id),
                )

                cursor.execute(
                    "SELECT locked_until FROM web_local_accounts WHERE id = %s",
                    (local_account_id,),
                )
                row = cursor.fetchone() or {}
                return row.get("locked_until")
    except Exception as exc:
        logger.error("Ошибка фиксации auth-failure: %s", exc, exc_info=True)
        return None


def mark_local_account_auth_success(local_account_id: int) -> None:
    """Сбросить счётчики неудач после успешного логина."""
    query = """
        UPDATE web_local_accounts
        SET failed_attempts = 0,
            locked_until = NULL,
            last_login_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (local_account_id,))
    except Exception as exc:
        logger.error("Ошибка фиксации auth-success: %s", exc, exc_info=True)


def update_local_account_password(
    local_account_id: int,
    *,
    password_hash: str,
    updated_by: Optional[int] = None,
) -> bool:
    """Обновить пароль локального аккаунта."""
    query = """
        UPDATE web_local_accounts
        SET password_hash = %s,
            failed_attempts = 0,
            locked_until = NULL,
            updated_by = %s,
            updated_at = NOW()
        WHERE id = %s
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (password_hash, updated_by, local_account_id))
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка обновления пароля локального аккаунта: %s", exc, exc_info=True)
        return False


def set_local_account_active(local_account_id: int, is_active: bool, updated_by: Optional[int] = None) -> bool:
    """Включить/отключить локальный аккаунт."""
    query = """
        UPDATE web_local_accounts
        SET is_active = %s,
            updated_by = %s,
            updated_at = NOW()
        WHERE id = %s
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (bool(is_active), updated_by, local_account_id))
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка изменения статуса локального аккаунта: %s", exc, exc_info=True)
        return False
