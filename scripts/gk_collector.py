#!/usr/bin/env python3
"""
gk_collector — Telethon-скрипт сбора сообщений из групп.

Слушает новые сообщения в настроенных группах, сохраняет их в БД
и обрабатывает изображения через GigaChat Vision.

Режимы:
    python scripts/gk_collector.py                         — запустить слушатель
    python scripts/gk_collector.py --manage-groups         — управление группами (CLI)
    python scripts/gk_collector.py --backfill --days 7     — загрузить историю
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
    GK_COLLECTOR_SESSION_NAME,
)
from src.group_knowledge.image_processor import ImageProcessor
from src.group_knowledge.message_collector import (
    MessageCollector,
    load_groups_config,
    manage_groups_interactive,
)
from src.group_knowledge.telethon_session import (
    disconnect_client_quietly,
    start_telegram_client_with_logging,
)

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GK_COLLECTOR] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gk_collector")


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
    """Вернуть выделенную Telethon-сессию коллектора."""
    return GK_COLLECTOR_SESSION_NAME


async def run_collector(args: argparse.Namespace) -> None:
    """
    Основной цикл коллектора.

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
    logger.info("Загружено %d групп: %s", len(groups), group_ids)
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

    # Инициализировать коллектор
    image_processor = ImageProcessor()
    collector = MessageCollector(
        client=client,
        image_processor=image_processor,
        groups=groups,
    )

    stop_event = asyncio.Event()

    # Graceful shutdown
    def handle_signal(sig, _frame):
        logger.info("Получен сигнал %s, остановка...", sig)
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    image_task = None
    try:
        # Режим backfill
        if args.backfill:
            logger.info("Режим backfill: %d дней, force=%s", args.days, args.force)
            count = await collector.backfill_messages(days=args.days, force=args.force)
            logger.info("Backfill завершён: %d сообщений", count)

            # Обработать скачанные изображения
            logger.info("Обработка очереди изображений...")
            total_images = 0
            while True:
                processed = await image_processor.process_queue(batch_size=10)
                if processed == 0:
                    break
                total_images += processed
            logger.info("Обработано изображений: %d", total_images)
            return

        # Режим слушателя
        @client.on(events.NewMessage())
        async def on_new_message(event):
            await collector.handle_new_message(event)

        # Запустить обработку очереди изображений как фоновую задачу
        image_task = asyncio.create_task(
            image_processor.process_queue_loop(
                poll_interval=10.0,
                stop_event=stop_event,
            )
        )

        logger.info(
            "Коллектор запущен. Отслеживаемые группы: %s",
            [f"{g.get('title', g['id'])} ({g['id']})" for g in groups],
        )
        logger.info("Нажмите Ctrl+C для остановки")

        while not stop_event.is_set():
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Получен Ctrl+C, остановка коллектора...")
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Остановка коллектора...")
        stop_event.set()
        if image_task is not None:
            image_task.cancel()
            try:
                await image_task
            except asyncio.CancelledError:
                pass
        await disconnect_client_quietly(client)
        logger.info("Коллектор остановлен")


def main() -> None:
    """Точка входа."""
    parser = argparse.ArgumentParser(
        description="GK Collector — сбор сообщений из Telegram-групп",
    )
    parser.add_argument(
        "--manage-groups",
        action="store_true",
        help="Управление списком отслеживаемых групп (CLI)",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Загрузить историю сообщений",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Число дней для backfill (по умолчанию 7)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Для backfill: принудительно обновить уже собранные сообщения, заново скачать изображения и пересоздать их описания",
    )
    args = parser.parse_args()

    if not _validate_telethon_credentials():
        return

    if args.manage_groups:
        asyncio.run(_run_manage_groups())
        return

    asyncio.run(run_collector(args))


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
