"""Аутентификация через Telegram Login Widget.

Поддерживает два режима:
1. Production: верификация HMAC-хеша от Telegram Login Widget.
2. Dev-режим: аутентификация по telegram_id без проверки (для разработки).

Telegram Login Widget:
https://core.telegram.org/widgets/login
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import logging
import os
import re
import time
from typing import Optional, Tuple

from fastapi import Cookie, HTTPException, Request

from admin_web.core import db as web_db
from admin_web.core.models import PasswordLoginRequest, TelegramAuthData, WebUser

logger = logging.getLogger(__name__)

# Максимально допустимый возраст auth_date (86400 = 24 часа)
_AUTH_DATE_MAX_AGE_SECONDS = 86400

# Имя cookie для токена сессии
SESSION_COOKIE_NAME = "archie_session"

# TTL сессии по умолчанию (часы)
_DEFAULT_SESSION_TTL_HOURS = int(os.getenv("ADMIN_WEB_SESSION_TTL_HOURS", "72"))

# Dev-режим: пропускает проверку Telegram-хеша
_DEV_MODE = os.getenv("ADMIN_WEB_DEV_MODE", "").lower() in ("1", "true", "yes")

# Password auth
_PASSWORD_AUTH_ENABLED = os.getenv("ADMIN_WEB_PASSWORD_AUTH_ENABLED", "true").lower() in (
    "1", "true", "yes"
)
_PASSWORD_MIN_LENGTH = int(os.getenv("ADMIN_WEB_PASSWORD_MIN_LENGTH", "10"))
_PASSWORD_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("ADMIN_WEB_PASSWORD_RATE_LIMIT_WINDOW_SECONDS", "300")
)
_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS = int(
    os.getenv("ADMIN_WEB_PASSWORD_RATE_LIMIT_MAX_ATTEMPTS", "10")
)
_PASSWORD_LOCKOUT_THRESHOLD = int(os.getenv("ADMIN_WEB_PASSWORD_LOCKOUT_THRESHOLD", "5"))
_PASSWORD_LOCKOUT_MINUTES = int(os.getenv("ADMIN_WEB_PASSWORD_LOCKOUT_MINUTES", "15"))


def _get_bot_token() -> str:
    """Получить Telegram bot token для верификации."""
    from src.common.constants.telegram import TELEGRAM_TOKEN
    return TELEGRAM_TOKEN


def verify_telegram_auth(data: TelegramAuthData) -> bool:
    """
    Проверить подлинность данных от Telegram Login Widget.

    Алгоритм верификации:
    1. Собрать data-check-string из всех полей кроме hash, отсортированных по алфавиту.
    2. Вычислить secret_key = SHA256(bot_token).
    3. Вычислить HMAC-SHA-256(secret_key, data_check_string).
    4. Сравнить с полученным hash.

    Также проверяет, что auth_date не слишком старый.
    """
    # Проверка возраста аутентификации
    now = int(time.time())
    if now - data.auth_date > _AUTH_DATE_MAX_AGE_SECONDS:
        logger.warning(
            "Telegram auth слишком старый: auth_date=%d now=%d delta=%ds",
            data.auth_date, now, now - data.auth_date,
        )
        return False

    # Построение data-check-string
    fields = {
        "id": str(data.id),
        "auth_date": str(data.auth_date),
    }
    if data.first_name:
        fields["first_name"] = data.first_name
    if data.last_name:
        fields["last_name"] = data.last_name
    if data.username:
        fields["username"] = data.username
    if data.photo_url:
        fields["photo_url"] = data.photo_url

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(fields.items())
    )

    # HMAC-SHA-256 верификация
    bot_token = _get_bot_token()
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    computed_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, data.hash):
        logger.warning(
            "Telegram auth HMAC mismatch: telegram_id=%d",
            data.id,
        )
        return False

    return True


def create_authenticated_session(
    data: TelegramAuthData,
    request: Optional[Request] = None,
) -> str:
    """
    Создать сессию после успешной верификации.

    Returns:
        Токен сессии.
    """
    user_agent = None
    ip_address = None
    if request:
        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None

    token = web_db.create_session(
        telegram_id=data.id,
        telegram_username=data.username,
        telegram_first_name=data.first_name,
        telegram_last_name=data.last_name,
        telegram_photo_url=data.photo_url,
        ttl_hours=_DEFAULT_SESSION_TTL_HOURS,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    logger.info(
        "Создана web-сессия: telegram_id=%d username=%s",
        data.id, data.username or "N/A",
    )
    return token


def is_password_auth_enabled() -> bool:
    """Проверить, включён ли вход по паролю."""
    return _PASSWORD_AUTH_ENABLED


def validate_password_policy(password: str) -> Optional[str]:
    """Проверить пароль по базовой policy сложности."""
    if len(password) < _PASSWORD_MIN_LENGTH:
        return f"Пароль должен быть не короче {_PASSWORD_MIN_LENGTH} символов"
    if not re.search(r"[a-z]", password):
        return "Пароль должен содержать строчную латинскую букву"
    if not re.search(r"[A-Z]", password):
        return "Пароль должен содержать заглавную латинскую букву"
    if not re.search(r"\d", password):
        return "Пароль должен содержать цифру"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Пароль должен содержать специальный символ"
    return None


def _format_lock_message(locked_until: Optional[datetime]) -> str:
    """Сформировать сообщение о временной блокировке входа."""
    if not locked_until:
        return "Аккаунт временно заблокирован"
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    return f"Аккаунт временно заблокирован до {locked_until.astimezone().strftime('%Y-%m-%d %H:%M:%S')}"


def authenticate_password_login(
    body: PasswordLoginRequest,
    request: Optional[Request] = None,
) -> Tuple[WebUser, str]:
    """Аутентифицировать пользователя по логину/паролю и создать сессию."""
    if not is_password_auth_enabled():
        raise HTTPException(status_code=403, detail="Вход по паролю отключён")

    login = web_db.normalize_login(body.login)
    ip_address = request.client.host if request and request.client else None

    recent_failed = web_db.count_recent_failed_attempts(
        login_identifier=login,
        ip_address=ip_address,
        auth_method="password",
        window_seconds=_PASSWORD_RATE_LIMIT_WINDOW_SECONDS,
    )
    if recent_failed >= _PASSWORD_RATE_LIMIT_MAX_ATTEMPTS:
        web_db.record_auth_attempt(
            login_identifier=login,
            ip_address=ip_address,
            auth_method="password",
            success=False,
            reason="rate_limit",
        )
        raise HTTPException(status_code=429, detail="Слишком много попыток входа. Попробуйте позже")

    account = web_db.get_local_account_by_login(login)
    if not account or not account.get("is_active"):
        web_db.record_auth_attempt(
            login_identifier=login,
            ip_address=ip_address,
            auth_method="password",
            success=False,
            reason="account_not_found_or_inactive",
        )
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    now_utc = datetime.now(timezone.utc)
    locked_until = account.get("locked_until")
    if locked_until:
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now_utc:
            web_db.record_auth_attempt(
                login_identifier=login,
                ip_address=ip_address,
                auth_method="password",
                success=False,
                reason="locked",
                principal_telegram_id=account.get("principal_telegram_id"),
            )
            raise HTTPException(status_code=423, detail=_format_lock_message(locked_until))

    if not web_db.verify_password(body.password, account.get("password_hash", "")):
        new_locked_until = web_db.mark_local_account_auth_failure(
            int(account["id"]),
            lockout_threshold=_PASSWORD_LOCKOUT_THRESHOLD,
            lockout_minutes=_PASSWORD_LOCKOUT_MINUTES,
        )
        web_db.record_auth_attempt(
            login_identifier=login,
            ip_address=ip_address,
            auth_method="password",
            success=False,
            reason="invalid_password",
            principal_telegram_id=account.get("principal_telegram_id"),
        )
        if new_locked_until and (
            (new_locked_until.replace(tzinfo=timezone.utc) if new_locked_until.tzinfo is None else new_locked_until)
            > datetime.now(timezone.utc)
        ):
            raise HTTPException(status_code=423, detail=_format_lock_message(new_locked_until))
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    web_db.mark_local_account_auth_success(int(account["id"]))

    user = web_db.build_web_user(
        telegram_id=int(account["principal_telegram_id"]),
        telegram_first_name=account.get("display_name") or account.get("login"),
        auth_method="password",
        local_account_id=int(account["id"]),
    )

    token = web_db.create_session(
        telegram_id=int(account["principal_telegram_id"]),
        telegram_first_name=account.get("display_name") or account.get("login"),
        ttl_hours=_DEFAULT_SESSION_TTL_HOURS,
        user_agent=request.headers.get("user-agent") if request else None,
        ip_address=ip_address,
        auth_method="password",
        local_account_id=int(account["id"]),
    )

    web_db.record_auth_attempt(
        login_identifier=login,
        ip_address=ip_address,
        auth_method="password",
        success=True,
        reason="ok",
        principal_telegram_id=int(account["principal_telegram_id"]),
    )

    return user, token


async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> WebUser:
    """
    FastAPI dependency: извлечь текущего пользователя из cookie сессии.

    Raises:
        HTTPException 401 если сессия не найдена или истекла.
    """
    # Также проверяем заголовок Authorization (для API-клиентов)
    if not session_token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            session_token = auth_header[7:]

    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="Необходима аутентификация",
        )

    session = web_db.get_session(session_token)
    if not session:
        raise HTTPException(
            status_code=401,
            detail="Сессия истекла или недействительна",
        )

    user = web_db.build_web_user(
        telegram_id=session["telegram_id"],
        telegram_username=session.get("telegram_username"),
        telegram_first_name=session.get("telegram_first_name"),
        telegram_last_name=session.get("telegram_last_name"),
        telegram_photo_url=session.get("telegram_photo_url"),
        auth_method=session.get("auth_method") or "telegram",
        local_account_id=session.get("local_account_id"),
    )
    return user


async def get_optional_user(
    request: Request,
    session_token: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
) -> Optional[WebUser]:
    """
    FastAPI dependency: извлечь текущего пользователя или None.

    Не бросает исключение если пользователь не аутентифицирован.
    """
    try:
        return await get_current_user(request, session_token)
    except HTTPException:
        return None


def is_dev_mode() -> bool:
    """Проверить, включён ли dev-режим (без Telegram-верификации)."""
    return _DEV_MODE
