#!/usr/bin/env python3
"""
gk_responder — Telethon-скрипт автоответчика для групп.

Слушает новые сообщения в настроенных группах, определяет вопросы
и отвечает на них из базы Q&A-пар.

По умолчанию работает в dry-run режиме (только логирование).

Режимы:
    python scripts/gk_responder.py                  — dry-run (только логи)
    python scripts/gk_responder.py --live            — реальная отправка ответов
    python scripts/gk_responder.py --manage-groups   — управление группами (CLI)
"""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

# Корень проекта для импортов
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from telethon import events

from src.common.constants.sync import (
    TELETHON_API_ID,
    TELETHON_API_HASH,
    GK_RESPONDER_SESSION_NAME,
)
from src.group_knowledge.message_collector import (
    load_groups_config,
    manage_groups_interactive,
)
from src.group_knowledge.responder import GroupResponder
from src.group_knowledge.telethon_session import (
    disconnect_client_quietly,
    start_telegram_client_with_logging,
)

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GK_RESPONDER] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gk_responder")


def _validate_telethon_credentials() -> bool:
    """Проверить наличие обязательных Telethon-параметров."""
    if not TELETHON_API_ID or TELETHON_API_ID == 0 or not TELETHON_API_HASH:
        logger.error(
            "TELETHON_API_ID и TELETHON_API_HASH должны быть заданы в .env"
        )
        return False
    return True


def _log_auth_hint() -> None:
    """Вывести подсказку по получению кода авторизации Telegram."""
    logger.info(
        "Код авторизации обычно приходит в приложение Telegram (чат 'Telegram'), "
        "а не по SMS."
    )
    logger.info(
        "Номер телефона нужно вводить в международном формате, например: +79991234567"
    )


def _resolve_session_name() -> str:
    """Вернуть выделенную Telethon-сессию автоответчика."""
    return GK_RESPONDER_SESSION_NAME


async def run_responder(args: argparse.Namespace) -> None:
    """
    Основной цикл автоответчика.

    Args:
        args: Аргументы командной строки.
    """
    groups = load_groups_config()
    if not groups:
        logger.error(
            "Нет настроенных групп. Запустите: python scripts/gk_collector.py --manage-groups"
        )
        return

    group_ids = {g["id"] for g in groups}
    dry_run = not args.live

    logger.info(
        "Загружено %d групп: %s (режим: %s)",
        len(groups),
        group_ids,
        "DRY-RUN" if dry_run else "LIVE",
    )

    if not dry_run:
        logger.warning(
            "⚠️ Автоответчик запущен в LIVE-режиме! "
            "Ответы будут отправляться в группы."
        )

    _log_auth_hint()

    session_name = _resolve_session_name()
    session_path = str(PROJECT_ROOT / session_name)
    client = await start_telegram_client_with_logging(
        session_path=session_path,
        api_id=TELETHON_API_ID,
        api_hash=TELETHON_API_HASH,
        logger=logger,
    )

    if not client:
        return
    logger.info("Telethon-клиент подключен (session=%s)", session_name)

    # Инициализировать автоответчик
    responder = GroupResponder(dry_run=dry_run)

    stop_event = asyncio.Event()

    # Graceful shutdown
    def handle_signal(sig, _frame):
        logger.info("Получен сигнал %s, остановка...", sig)
        stop_event.set()
        responder.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Счётчики
    stats = {"handled": 0, "answered": 0, "dry_run": 0}

    @client.on(events.NewMessage())
    async def on_new_message(event):
        try:
            result = await responder.handle_message(event, group_ids)
            if result:
                stats["handled"] += 1
                if result.dry_run:
                    stats["dry_run"] += 1
                elif result.responded:
                    stats["answered"] += 1
        except Exception as exc:
            logger.error(
                "Ошибка обработки сообщения: %s", exc, exc_info=True,
            )

    logger.info(
        "Автоответчик запущен. Отслеживаемые группы: %s",
        [f"{g.get('title', g['id'])} ({g['id']})" for g in groups],
    )
    logger.info("Нажмите Ctrl+C для остановки")

    try:
        while not stop_event.is_set():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Получен Ctrl+C, остановка автоответчика...")
    except asyncio.CancelledError:
        pass
    finally:
        logger.info(
            "Остановка автоответчика. Статистика: обработано=%d ответов=%d dry_run=%d",
            stats["handled"], stats["answered"], stats["dry_run"],
        )
        await disconnect_client_quietly(client)
        logger.info("Автоответчик остановлен")


def main() -> None:
    """Точка входа."""
    parser = argparse.ArgumentParser(
        description="GK Responder — автоответчик для Telegram-групп",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Включить реальную отправку ответов (по умолчанию dry-run)",
    )
    parser.add_argument(
        "--manage-groups",
        action="store_true",
        help="Управление списком отслеживаемых групп (CLI)",
    )
    args = parser.parse_args()

    if not _validate_telethon_credentials():
        return

    if args.manage_groups:
        asyncio.run(_run_manage_groups())
        return

    asyncio.run(run_responder(args))


async def _run_manage_groups() -> None:
    """Запустить интерактивное управление группами с Telethon-клиентом."""
    _log_auth_hint()
    session_name = _resolve_session_name()
    session_path = str(PROJECT_ROOT / session_name)
    client = await start_telegram_client_with_logging(
        session_path=session_path,
        api_id=TELETHON_API_ID,
        api_hash=TELETHON_API_HASH,
        logger=logger,
    )
    if not client:
        return
    try:
        await manage_groups_interactive(client)
    finally:
        await disconnect_client_quietly(client)


if __name__ == "__main__":
    main()
