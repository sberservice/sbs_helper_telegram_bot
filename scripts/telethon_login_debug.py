#!/usr/bin/env python3
"""Утилита диагностики интерактивной авторизации Telethon.

Помогает понять, почему не приходит код Telegram при создании session-файла.
Скрипт выполняет пошаговую проверку: подключение, отправка кода, вход по коду,
при необходимости — вход по 2FA-паролю.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.constants.sync import TELETHON_API_HASH, TELETHON_API_ID
from src.group_knowledge.telethon_session import (
    build_telegram_client,
    disconnect_client_quietly,
)


PHONE_RE = re.compile(r"^\+[1-9]\d{6,14}$")


def _normalize_phone(raw_phone: str) -> str:
    """Нормализовать ввод номера и проверить международный формат E.164."""
    normalized = (raw_phone or "").strip().replace(" ", "")
    if not PHONE_RE.match(normalized):
        raise ValueError(
            "Номер телефона должен быть в международном формате, например +79991234567"
        )
    return normalized


def _build_parser() -> argparse.ArgumentParser:
    """Собрать CLI-парсер аргументов."""
    parser = argparse.ArgumentParser(
        description="Диагностика получения кода Telethon и создания session-файла"
    )
    parser.add_argument(
        "--session-name",
        default="telethon_login_debug",
        help="Базовое имя session-файла в корне проекта (без .session)",
    )
    parser.add_argument(
        "--phone",
        default="",
        help="Номер телефона в формате +79991234567 (если не передан, будет интерактивный ввод)",
    )
    return parser


async def _run_debug(session_name: str, phone_arg: str, logger: logging.Logger) -> int:
    """Запустить пошаговую диагностику Telethon-авторизации."""
    if not TELETHON_API_ID or TELETHON_API_ID == 0 or not TELETHON_API_HASH:
        logger.error("TELETHON_API_ID и TELETHON_API_HASH должны быть заданы в .env")
        return 2

    logger.info(
        "Код авторизации обычно приходит в приложение Telegram (чат 'Telegram' / 777000), а не по SMS."
    )
    logger.info("Используйте номер только в международном формате: +79991234567")

    session_path = str(PROJECT_ROOT / session_name)
    client = build_telegram_client(session_path, TELETHON_API_ID, TELETHON_API_HASH, logger)

    try:
        await client.connect()
        logger.info("Подключение к Telegram API успешно: session=%s.session", session_name)

        if await client.is_user_authorized():
            logger.info("Сессия уже авторизована. Дополнительные действия не требуются.")
            return 0

        raw_phone = phone_arg or input("Введите телефон в формате +79991234567: ").strip()
        try:
            phone = _normalize_phone(raw_phone)
        except ValueError as exc:
            logger.error("%s", exc)
            return 2

        logger.info("Запрашиваю код подтверждения Telegram для %s", phone)
        sent = await client.send_code_request(phone)
        logger.info("Запрос кода отправлен. Проверьте чат Telegram/777000 в приложении Telegram.")

        code = input("Введите код из Telegram (или Enter для отмены): ").strip()
        if not code:
            logger.warning("Код не введён. Диагностика остановлена пользователем.")
            logger.warning("Проверьте архив/mute в приложении Telegram и повторите попытку.")
            return 2

        try:
            await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
        except Exception as sign_in_exc:
            from telethon.errors import SessionPasswordNeededError

            if isinstance(sign_in_exc, SessionPasswordNeededError):
                logger.info("Для аккаунта включён 2FA-пароль. Нужен cloud password.")
                password = getpass.getpass("Введите облачный пароль Telegram 2FA: ")
                await client.sign_in(password=password)
            else:
                raise

        if await client.is_user_authorized():
            logger.info("Авторизация успешна. Session-файл создан: %s.session", session_name)
            return 0

        logger.error("Авторизация не завершена: клиент не авторизован после ввода кода.")
        return 2

    except Exception as exc:
        from telethon.errors import (
            ApiIdInvalidError,
            FloodWaitError,
            PhoneCodeExpiredError,
            PhoneCodeInvalidError,
            PhoneNumberInvalidError,
            PhoneNumberBannedError,
            PhoneNumberFloodError,
        )

        if isinstance(exc, ApiIdInvalidError):
            logger.error("Неверные TELETHON_API_ID/TELETHON_API_HASH. Проверьте значения с my.telegram.org")
            return 2
        if isinstance(exc, PhoneNumberInvalidError):
            logger.error("Неверный формат телефона. Используйте +79991234567")
            return 2
        if isinstance(exc, PhoneCodeInvalidError):
            logger.error("Введён неверный код подтверждения Telegram")
            return 2
        if isinstance(exc, PhoneCodeExpiredError):
            logger.error("Код подтверждения истёк. Запустите диагностику заново")
            return 2
        if isinstance(exc, PhoneNumberBannedError):
            logger.error("Номер телефона заблокирован для использования в Telegram API")
            return 2
        if isinstance(exc, PhoneNumberFloodError):
            logger.error("Слишком много попыток для номера. Подождите и повторите позже")
            return 2
        if isinstance(exc, FloodWaitError):
            logger.error(
                "Telegram временно ограничил попытки. Повторите через %s сек.",
                getattr(exc, "seconds", "несколько"),
            )
            return 2

        logger.error("Неожиданная ошибка диагностики Telethon: %s", exc, exc_info=True)
        return 1
    finally:
        await disconnect_client_quietly(client)


def main() -> int:
    """CLI entrypoint."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [TELETHON_DEBUG] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("scripts.telethon_login_debug")

    args = _build_parser().parse_args()
    return asyncio.run(_run_debug(args.session_name, args.phone, logger))


if __name__ == "__main__":
    raise SystemExit(main())
