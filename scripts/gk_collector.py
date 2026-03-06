#!/usr/bin/env python3
"""
gk_collector — Telethon-скрипт сбора сообщений из групп.

Слушает новые сообщения в настроенных группах, сохраняет их в БД
и обрабатывает изображения через GigaChat Vision.

Режимы:
    python scripts/gk_collector.py                         — запустить слушатель
    python scripts/gk_collector.py --live                  — слушатель + реальные ответы автоответчика
    python scripts/gk_collector.py --test-mode             — слушатель + автоответчик в test mode
    python scripts/gk_collector.py --manage-groups         — управление группами (CLI)
    python scripts/gk_collector.py --backfill --days 7     — загрузить историю
"""

import argparse
import asyncio
import logging
import re
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
from src.group_knowledge.collector_responder import CollectorResponderBridge
from src.group_knowledge.image_processor import ImageProcessor
from src.group_knowledge.message_collector import (
    _get_available_groups,
    MessageCollector,
    load_groups_config,
    manage_groups_interactive,
)
from src.group_knowledge.responder import GroupResponder
from src.group_knowledge.settings import GK_MESSAGE_GROUPING_WINDOW_SECONDS
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

QA_COMMAND_PATTERN = re.compile(r"^/qa(?:@[A-Za-z0-9_]+)?(?:\s+(.+))?$", re.IGNORECASE)


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


def _extract_qa_query(text: str) -> str | None:
    """Извлечь текст вопроса из команды /qa (опционально с @mention)."""
    raw = (text or "").strip()
    if not raw:
        return None
    match = QA_COMMAND_PATTERN.match(raw)
    if not match:
        return None
    query = (match.group(1) or "").strip()
    return query if query else None


def _select_item_from_menu(items, prompt: str, formatter) -> dict | None:
    """Показать консольное меню выбора одного элемента."""
    if not items:
        return None

    print()
    for index, item in enumerate(items, start=1):
        print(f"{index}. {formatter(item)}")
    print("0. Отмена")

    while True:
        raw = input(f"{prompt}: ").strip()
        if not raw.isdigit():
            print("Введите номер пункта меню.")
            continue

        selected_index = int(raw)
        if selected_index == 0:
            return None
        if 1 <= selected_index <= len(items):
            return items[selected_index - 1]

        print("Некорректный номер. Повторите ввод.")


async def _select_test_mode_mapping(client, configured_groups: list[dict]) -> dict | None:
    """Интерактивно выбрать реальную и тестовую группу для daemon test mode."""
    available_groups = await _get_available_groups(client)
    if not configured_groups:
        logger.error("Нет настроенных реальных групп для test mode.")
        return None
    if not available_groups:
        logger.error("Не удалось получить доступные Telegram-группы для test mode.")
        return None

    print("\n=== Test mode Group Knowledge (collector daemon) ===")
    print("Сначала выберите реальную группу, чью базу знаний нужно использовать.")
    real_group = _select_item_from_menu(
        configured_groups,
        prompt="Выберите реальную группу",
        formatter=lambda item: f"{item.get('title', 'Без названия')} (ID: {item['id']})",
    )
    if real_group is None:
        return None

    test_candidates = [group for group in available_groups if group["id"] != real_group["id"]]
    if not test_candidates:
        logger.error("Не найдено доступных тестовых групп, отличных от выбранной реальной группы.")
        return None

    print("\nТеперь выберите тестовую группу, куда будут приходить и отправляться ответы.")
    test_group = _select_item_from_menu(
        test_candidates,
        prompt="Выберите тестовую группу",
        formatter=lambda item: f"{item.get('title', 'Без названия')} (ID: {item['id']}, участников: {item.get('participants', '?')})",
    )
    if test_group is None:
        return None

    return {
        "listen_groups": [test_group],
        "group_mapping": {int(test_group["id"]): int(real_group["id"])},
        "real_group": real_group,
        "test_group": test_group,
    }


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

    listened_groups = list(groups)
    group_mapping = {}
    logger.info("Загружено %d групп: %s", len(groups), {g["id"] for g in groups})
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

    if args.test_mode:
        test_mode_config = await _select_test_mode_mapping(client, groups)
        if not test_mode_config:
            logger.info("Test mode отменён пользователем.")
            await disconnect_client_quietly(client)
            return
        listened_groups = test_mode_config["listen_groups"]
        group_mapping = test_mode_config["group_mapping"]
        logger.info(
            "Test mode активирован: test_group=%s (%s) -> real_group=%s (%s)",
            test_mode_config["test_group"].get("title", "Без названия"),
            test_mode_config["test_group"]["id"],
            test_mode_config["real_group"].get("title", "Без названия"),
            test_mode_config["real_group"]["id"],
        )

    # Инициализировать коллектор
    image_processor = ImageProcessor()
    collector = MessageCollector(
        client=client,
        image_processor=image_processor,
        groups=listened_groups,
    )
    responder = GroupResponder(
        dry_run=not args.live,
        test_group_mapping=group_mapping,
    )
    responder_bridge = CollectorResponderBridge(
        responder=responder,
        group_ids=collector.group_ids,
        grouping_window_seconds=GK_MESSAGE_GROUPING_WINDOW_SECONDS,
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

        missed_count = await collector.sync_missed_messages()
        if missed_count:
            logger.info(
                "Перед запуском слушателя добраны пропущенные сообщения: %d",
                missed_count,
            )
        else:
            logger.info("Перед запуском слушателя пропущенных сообщений не найдено")

        # Режим слушателя
        @client.on(events.NewMessage())
        async def on_new_message(event):
            message_record = await collector.handle_new_message(event)
            if not args.collect_only and message_record is not None:
                raw_text = (event.message.text if event.message else "") or (event.message.message if event.message else "") or ""
                qa_query = _extract_qa_query(raw_text)
                if qa_query is not None:
                    await responder.handle_message(
                        event,
                        collector.group_ids,
                        question_override=qa_query,
                        force_as_question=True,
                    )
                else:
                    await responder_bridge.queue_message(event, message_record)

        # Запустить обработку очереди изображений как фоновую задачу
        image_task = asyncio.create_task(
            image_processor.process_queue_loop(
                poll_interval=10.0,
                stop_event=stop_event,
            )
        )

        logger.info(
            "Коллектор запущен. Отслеживаемые группы: %s",
            [f"{g.get('title', g['id'])} ({g['id']})" for g in listened_groups],
        )
        if args.collect_only:
            logger.info("Автоответчик в daemon collector отключён флагом --collect-only")
        else:
            logger.info(
                "Daemon collector также выполняет автоответчик: режим=%s, окно склейки=%ds",
                "LIVE" if args.live else "DRY-RUN",
                GK_MESSAGE_GROUPING_WINDOW_SECONDS,
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
        await responder_bridge.stop()
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
    parser.add_argument(
        "--live",
        action="store_true",
        help="В daemon-режиме реально отправлять ответы автоответчика (по умолчанию dry-run)",
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="В daemon-режиме интерактивно выбрать test group и real group для ответов в тестовой группе",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Запустить только сборщик без встроенного автоответчика",
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
