"""
Утилиты для безопасной работы с Telethon-сессиями.

Содержит helpers для создания TelegramClient с более терпимыми
SQLite-настройками и аккуратным завершением без автоматических
повторных попыток подключения.
"""

import logging
import sqlite3
from typing import Any, Optional


TELETHON_SESSION_BUSY_TIMEOUT_MS = 30000
"""Таймаут ожидания SQLite-блокировки для session-файла Telethon."""


def _is_sqlite_locked_error(exc: BaseException) -> bool:
    """Проверить, что ошибка связана именно с блокировкой SQLite."""
    return isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc).lower()


def _configure_sqlite_session(session: Any, logger: logging.Logger) -> None:
    """Применить к Telethon-session более безопасные SQLite-параметры."""
    conn = getattr(session, "_conn", None)
    if conn is None:
        return

    try:
        conn.execute(f"PRAGMA busy_timeout = {TELETHON_SESSION_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.DatabaseError as exc:
        logger.warning("Не удалось применить SQLite PRAGMA к Telethon-сессии: %s", exc)


def build_telegram_client(
    session_path: str,
    api_id: int,
    api_hash: str,
    logger: logging.Logger,
) -> Any:
    """Создать TelegramClient с настроенной SQLiteSession."""
    from telethon import TelegramClient
    from telethon.sessions import SQLiteSession

    session = SQLiteSession(session_path)
    _configure_sqlite_session(session, logger)
    return TelegramClient(session, api_id, api_hash)


async def disconnect_client_quietly(client: Any) -> None:
    """Тихо закрыть Telethon-клиент без выброса вторичных ошибок."""
    if client is None:
        return

    try:
        await client.disconnect()
    except Exception:
        return


async def start_telegram_client_with_logging(
    session_path: str,
    api_id: int,
    api_hash: str,
    logger: logging.Logger,
) -> Optional[Any]:
    """Запустить Telethon-клиент с понятными сообщениями об ошибках."""
    from telethon.errors import (
        ApiIdInvalidError,
        FloodWaitError,
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        PhoneNumberInvalidError,
        SessionPasswordNeededError,
    )

    client = build_telegram_client(session_path, api_id, api_hash, logger)
    try:
        await client.start()
        return client
    except ApiIdInvalidError:
        logger.error("Неверные TELETHON_API_ID или TELETHON_API_HASH. Проверьте значения в .env")
    except PhoneNumberInvalidError:
        logger.error("Неверный номер телефона. Введите номер в международном формате, например +79991234567")
    except PhoneCodeInvalidError:
        logger.error("Введён неверный код подтверждения Telegram")
    except PhoneCodeExpiredError:
        logger.error("Код подтверждения Telegram истёк. Запустите авторизацию заново")
    except SessionPasswordNeededError:
        logger.error(
            "Для этого аккаунта включена двухэтапная аутентификация. "
            "После кода Telegram нужно ввести облачный пароль"
        )
    except FloodWaitError as exc:
        logger.error(
            "Telegram временно ограничил отправку кода. Повторите попытку через %s сек.",
            getattr(exc, "seconds", "несколько"),
        )
    except sqlite3.OperationalError as exc:
        if _is_sqlite_locked_error(exc):
            logger.error(
                "Не удалось открыть Telethon-сессию: session=%s. SQLite заблокирован. "
                "Убедитесь, что другой процесс с этой сессией уже завершился, и повторите запуск вручную.",
                session_path,
            )
        else:
            logger.error("Ошибка авторизации Telethon: %s", exc, exc_info=True)
    except Exception as exc:
        logger.error("Ошибка авторизации Telethon: %s", exc, exc_info=True)

    await disconnect_client_quietly(client)
    return None