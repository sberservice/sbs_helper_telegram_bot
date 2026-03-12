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
    python scripts/gk_collector.py --fill-missing-is-question --fill-days 30
                                                        — заполнить is_question для уже сохранённых сообщений
"""

import argparse
import asyncio
import logging
import re
import signal
import sys
import threading
from pathlib import Path

# Корень проекта для импортов
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from telethon import events
from telethon.tl import types as tl_types
from config import ai_settings

from src.common.constants.sync import (
    TELETHON_API_ID,
    TELETHON_API_HASH,
    GK_COLLECTOR_SESSION_NAME,
)
from src.group_knowledge import database as gk_db
from src.group_knowledge.collector_responder import CollectorResponderBridge
from src.group_knowledge.image_processor import ImageProcessor
from src.group_knowledge.message_collector import (
    _get_available_groups,
    MessageCollector,
    load_groups_config,
    load_test_target_group_config,
    manage_groups_interactive,
    save_test_target_group_config,
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


def _run_image_queue_in_thread(
    image_processor: ImageProcessor,
    stop_event: threading.Event,
    result_container: list[int],
) -> None:
    """
    Запустить цикл обработки очереди изображений в отдельном потоке.

    Создаёт собственный asyncio event loop и выполняет process_queue_loop,
    пока не будет установлен stop_event. После остановки дообрабатывает
    оставшиеся изображения (drain_remaining=True).

    Args:
        image_processor: Экземпляр ImageProcessor.
        stop_event: threading.Event для сигнала остановки.
        result_container: Одноэлементный список для возврата числа обработанных изображений.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        total = loop.run_until_complete(
            image_processor.process_queue_loop(
                poll_interval=5.0,
                stop_event=stop_event,
                drain_remaining=True,
            )
        )
        result_container.append(total)
    except Exception as exc:
        logger.error(
            "Ошибка в фоновом потоке обработки изображений: %s", exc, exc_info=True
        )
    finally:
        loop.close()


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


async def _select_test_mode_mapping(client, configured_groups: list[dict], *, test_real_group_id: int | None = None, test_group_id: int | None = None) -> dict | None:
    """Выбрать реальную и тестовую группу для daemon test mode.

    Если test_real_group_id и test_group_id заданы — интерактивный выбор
    не производится (неинтерактивный режим для Process Manager).
    """
    # --- Неинтерактивный режим ---
    if test_real_group_id is not None and test_group_id is not None:
        real_group = next(
            (g for g in configured_groups if int(g["id"]) == test_real_group_id),
            None,
        )
        if real_group is None:
            logger.error(
                "Реальная группа %d не найдена в настроенных группах.",
                test_real_group_id,
            )
            return None

        test_group = {"id": test_group_id, "title": f"Group {test_group_id}"}
        # Попытаться получить название из Telegram
        try:
            available = await _get_available_groups(client)
            found = next((g for g in available if int(g["id"]) == test_group_id), None)
            if found:
                test_group = found
        except Exception:
            pass

        logger.info(
            "Test mode (non-interactive): real=%s (%d), test=%s (%d)",
            real_group.get("title", ""), test_real_group_id,
            test_group.get("title", ""), test_group_id,
        )
        return {
            "listen_groups": [test_group],
            "group_mapping": {test_group_id: test_real_group_id},
            "real_group": real_group,
            "test_group": test_group,
        }

    # --- Интерактивный режим ---
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


async def _resolve_redirect_test_group(client, configured_groups: list[dict], *, redirect_group_id: int | None = None) -> dict | None:
    """Получить или интерактивно выбрать глобальную тестовую группу для redirect mode.

    Если redirect_group_id задан — пропускает сохранённую конфигурацию и
    интерактивный выбор (неинтерактивный режим для Process Manager).
    """
    configured_group_ids = {int(group["id"]) for group in configured_groups}

    # --- Неинтерактивный режим ---
    if redirect_group_id is not None:
        if redirect_group_id in configured_group_ids:
            logger.error(
                "Указанная группа (%d) совпадает с боевой отслеживаемой группой.",
                redirect_group_id,
            )
            return None

        group = {"id": redirect_group_id, "title": f"Group {redirect_group_id}"}
        try:
            available = await _get_available_groups(client)
            found = next((g for g in available if int(g["id"]) == redirect_group_id), None)
            if found:
                group = found
        except Exception:
            pass

        logger.info(
            "Redirect test mode (non-interactive): target=%s (%d)",
            group.get("title", ""), redirect_group_id,
        )
        save_test_target_group_config(group)
        return group

    # --- Стандартный режим: проверить сохранённую конфигурацию ---
    saved_group = load_test_target_group_config()
    if saved_group is not None:
        saved_group_id = int(saved_group["id"])
        if saved_group_id in configured_group_ids:
            logger.error(
                "Сохранённая test target group (%s) совпадает с боевой отслеживаемой группой. "
                "Выберите отдельную тестовую группу.",
                saved_group_id,
            )
        else:
            logger.info(
                "Используется сохранённая test target group: %s (%s)",
                saved_group.get("title", "Без названия"),
                saved_group_id,
            )
            return saved_group

    available_groups = await _get_available_groups(client)
    if not available_groups:
        logger.error("Не удалось получить доступные Telegram-группы для redirect test mode.")
        return None

    test_candidates = [
        group for group in available_groups
        if int(group["id"]) not in configured_group_ids
    ]
    if not test_candidates:
        logger.error(
            "Не найдено доступных тестовых групп, отличных от отслеживаемых боевых групп."
        )
        return None

    print("\n=== Redirect test mode Group Knowledge (collector daemon) ===")
    print("Выберите отдельную тестовую группу, куда будут отправляться ответы из боевых групп.")
    test_group = _select_item_from_menu(
        test_candidates,
        prompt="Выберите тестовую группу",
        formatter=lambda item: f"{item.get('title', 'Без названия')} (ID: {item['id']}, участников: {item.get('participants', '?')})",
    )
    if test_group is None:
        return None

    save_test_target_group_config(test_group)
    return test_group


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
    redirect_test_group = None
    logger.info("Загружено %d групп: %s", len(groups), {g["id"] for g in groups})
    _log_auth_hint()

    session_name = _resolve_session_name()
    session_path = str(PROJECT_ROOT / session_name)
    client = await start_telegram_client_with_logging(
        session_path=session_path,
        api_id=TELETHON_API_ID,
        api_hash=TELETHON_API_HASH,
        logger=logger,
        interactive=False,
    )

    if not client:
        return
    logger.info("Telethon-клиент подключен (session=%s)", session_name)

    if args.test_mode:
        test_mode_config = await _select_test_mode_mapping(
            client, groups,
            test_real_group_id=args.test_real_group_id,
            test_group_id=args.test_group_id,
        )
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
    elif args.redirect_test_mode:
        redirect_test_group = await _resolve_redirect_test_group(
            client, groups,
            redirect_group_id=args.redirect_group_id,
        )
        if not redirect_test_group:
            logger.info("Redirect test mode отменён пользователем.")
            await disconnect_client_quietly(client)
            return
        logger.info(
            "Redirect test mode активирован: monitor_groups=%s -> test_group=%s (%s)",
            [group["id"] for group in listened_groups],
            redirect_test_group.get("title", "Без названия"),
            redirect_test_group["id"],
        )

    # Инициализировать коллектор
    image_processor = ImageProcessor()
    collector = MessageCollector(
        client=client,
        image_processor=image_processor,
        groups=listened_groups,
    )

    # Верифицировать group_id через Telegram API (обнаружить миграции Chat → Channel)
    await collector.resolve_group_ids()
    logger.info(
        "Эффективные group_id после верификации: %s",
        sorted(collector.group_ids),
    )

    responder_dry_run = (not args.live) and (not args.test_mode) and (not args.redirect_test_mode)
    responder = GroupResponder(
        dry_run=responder_dry_run,
        test_group_mapping=group_mapping,
        redirect_output_group=redirect_test_group,
    )
    try:
        warmup_stats = responder.preload_search_resources(preload_vector_model=True)
        logger.info(
            "Прогрев GK-поиска завершён: corpus_pairs=%s corpus_signature=%s vector_model_preloaded=%s vector_index_ready=%s",
            warmup_stats.get("corpus_pairs"),
            warmup_stats.get("corpus_signature"),
            warmup_stats.get("vector_model_preloaded"),
            warmup_stats.get("vector_index_ready"),
        )
    except Exception as exc:
        if ai_settings.AI_RAG_VECTOR_EMBEDDING_FAIL_FAST:
            logger.error("Прогрев GK-поиска завершился с критической ошибкой (fail-fast): %s", exc)
            raise
        logger.warning("Прогрев GK-поиска завершился с ошибкой: %s", exc)

    responder_bridge = CollectorResponderBridge(
        responder=responder,
        group_ids=collector.group_ids,
        grouping_window_seconds=GK_MESSAGE_GROUPING_WINDOW_SECONDS,
        test_group_ids=set(group_mapping.keys()),
    )

    stop_event = asyncio.Event()
    # threading.Event для фонового потока обработки изображений (backfill)
    image_thread_stop = threading.Event()

    # Graceful shutdown
    def handle_signal(sig, _frame):
        logger.info("Получен сигнал %s, остановка...", sig)
        stop_event.set()
        image_thread_stop.set()
        collector.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    image_task = None
    try:
        # Режим backfill
        if args.backfill:
            logger.info("Режим backfill: %d дней, force=%s", args.days, args.force)

            # Запустить обработку изображений в фоновом потоке
            image_result: list[int] = []
            image_thread = threading.Thread(
                target=_run_image_queue_in_thread,
                args=(image_processor, image_thread_stop, image_result),
                name="gk-image-processor",
                daemon=True,
            )
            image_thread.start()
            logger.info("Фоновый поток обработки изображений запущен")

            count = await collector.backfill_messages(days=args.days, force=args.force)
            if stop_event.is_set():
                logger.info("Backfill остановлен пользователем: %d сохранённых сообщений", count)
            else:
                logger.info("Backfill завершён: %d сообщений", count)

            # Сообщить потоку, что новых изображений больше не будет —
            # он дообработает оставшуюся очередь и завершится (drain_remaining=True)
            image_thread_stop.set()
            logger.info("Ожидание завершения обработки оставшихся изображений...")
            image_thread.join(timeout=3600)  # макс. 1 час на дообработку
            if image_thread.is_alive():
                logger.warning(
                    "Фоновый поток обработки изображений не завершился за отведённое время"
                )
            else:
                total_images = image_result[0] if image_result else 0
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

        # Обработчик миграции Chat → Channel/Supergroup
        @client.on(events.ChatAction())
        async def on_chat_action(event):
            try:
                if hasattr(event, "action_message") and event.action_message:
                    action = event.action_message.action
                    if isinstance(action, tl_types.MessageActionChatMigrateTo):
                        old_chat_id = -(event.chat_id or 0)
                        new_channel_id = action.channel_id
                        new_chat_id = -int(f"100{new_channel_id}")
                        logger.warning(
                            "Обнаружена миграция группы: old_chat_id=%d -> new_channel_id=%d (peer_id=%d)",
                            -old_chat_id, new_channel_id, new_chat_id,
                        )
                        if collector.handle_chat_migration(-old_chat_id, new_chat_id):
                            logger.info(
                                "Группа успешно мигрирована в runtime. Новые group_ids: %s",
                                sorted(collector.group_ids),
                            )
            except Exception as exc:
                logger.error("Ошибка обработки миграции группы: %s", exc, exc_info=True)

        # Режим слушателя
        @client.on(events.NewMessage())
        async def on_new_message(event):
            message_record = await collector.handle_new_message(event)
            if not args.collect_only and message_record is not None:
                raw_text = (event.message.text if event.message else "") or (event.message.message if event.message else "") or ""
                qa_query = _extract_qa_query(raw_text)
                if qa_query is not None:
                    logger.info(
                        "Daemon responder: обработка /qa команды group=%d msg_tg=%d",
                        message_record.group_id,
                        message_record.telegram_message_id,
                    )
                    await responder.handle_message(
                        event,
                        collector.group_ids,
                        question_override=qa_query,
                        force_as_question=True,
                    )
                else:
                    logger.info(
                        "Daemon responder: передача сообщения в bridge group=%d sender=%d msg_tg=%d",
                        message_record.group_id,
                        message_record.sender_id,
                        message_record.telegram_message_id,
                    )
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
            responder_mode = "LIVE"
            if args.redirect_test_mode:
                responder_mode = "REDIRECT-TEST"
            elif responder_dry_run:
                responder_mode = "DRY-RUN"
            logger.info(
                "Daemon collector также выполняет автоответчик: режим=%s, окно склейки=%ds",
                responder_mode,
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
        collector.stop()
        if image_task is not None:
            image_task.cancel()
            try:
                await image_task
            except asyncio.CancelledError:
                pass
        await responder_bridge.stop()
        await disconnect_client_quietly(client)
        logger.info("Коллектор остановлен")


async def _run_fill_missing_is_question(args: argparse.Namespace) -> None:
    """Запустить backfill question-классификации для сообщений, где `is_question` ещё не заполнен."""
    groups = load_groups_config()
    if args.group_id is not None:
        selected_groups = [
            {
                "id": args.group_id,
                "title": next(
                    (group.get("title", "") for group in groups if int(group.get("id", 0)) == args.group_id),
                    "",
                ),
            }
        ]
    elif groups:
        selected_groups = groups
    else:
        selected_groups = [
            {
                "id": int(group["group_id"]),
                "title": group.get("group_title", ""),
            }
            for group in gk_db.get_collected_groups()
        ]

    collector = MessageCollector(
        client=None,
        groups=selected_groups,
    )
    updated = await collector.fill_missing_question_classification(
        group_id=args.group_id,
        days=args.fill_days,
        limit=args.fill_limit,
    )
    logger.info("Заполнение missing is_question завершено: updated=%d", updated)


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
        "--fill-missing-is-question",
        action="store_true",
        help="Заполнить is_question для уже сохранённых сообщений, где поле ещё NULL",
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
        "--fill-days",
        type=int,
        help="Для --fill-missing-is-question: ограничить обработку последними N днями",
    )
    parser.add_argument(
        "--fill-limit",
        type=int,
        help="Для --fill-missing-is-question: ограничить число сообщений за один запуск",
    )
    parser.add_argument(
        "--group-id",
        type=int,
        help="Для --fill-missing-is-question: ограничить обработку одной группой",
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
        "--redirect-test-mode",
        action="store_true",
        help="Слушать боевые группы, но отправлять ответы в отдельную глобическую тестовую группу",
    )
    parser.add_argument(
        "--test-real-group-id",
        type=int,
        default=None,
        help="ID реальной группы для --test-mode (неинтерактивный режим, для Process Manager)",
    )
    parser.add_argument(
        "--test-group-id",
        type=int,
        default=None,
        help="ID тестовой группы для --test-mode (неинтерактивный режим, для Process Manager)",
    )
    parser.add_argument(
        "--redirect-group-id",
        type=int,
        default=None,
        help="ID тестовой группы для --redirect-test-mode (неинтерактивный режим, для Process Manager)",
    )
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Запустить только сборщик без встроенного автоответчика",
    )
    args = parser.parse_args()

    selected_modes = sum(
        bool(flag)
        for flag in (
            args.manage_groups,
            args.backfill,
            args.fill_missing_is_question,
        )
    )
    if selected_modes > 1:
        parser.error("Флаги --manage-groups, --backfill и --fill-missing-is-question взаимоисключающие")
    if args.test_mode and args.redirect_test_mode:
        parser.error("Флаги --test-mode и --redirect-test-mode нельзя использовать одновременно")
    if args.fill_missing_is_question and args.force:
        parser.error("Флаг --force нельзя использовать вместе с --fill-missing-is-question")

    # Валидация неинтерактивных флагов для test-mode
    if (args.test_real_group_id is not None) != (args.test_group_id is not None):
        parser.error("Флаги --test-real-group-id и --test-group-id должны использоваться вместе")
    if args.test_real_group_id is not None and not args.test_mode:
        parser.error("Флаги --test-real-group-id / --test-group-id требуют --test-mode")
    if args.redirect_group_id is not None and not args.redirect_test_mode:
        parser.error("Флаг --redirect-group-id требует --redirect-test-mode")

    if args.manage_groups:
        if not _validate_telethon_credentials():
            return
        asyncio.run(_run_manage_groups())
        return

    if args.fill_missing_is_question:
        asyncio.run(_run_fill_missing_is_question(args))
        return

    if not _validate_telethon_credentials():
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
