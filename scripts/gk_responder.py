#!/usr/bin/env python3
"""
gk_responder — Telethon-скрипт автоответчика для групп.

Слушает новые сообщения в настроенных группах, определяет вопросы
и отвечает на них из базы Q&A-пар.

По умолчанию работает в dry-run режиме (только логирование).

Режимы:
    python scripts/gk_responder.py                  — dry-run (только логи)
    python scripts/gk_responder.py --live            — реальная отправка ответов
    python scripts/gk_responder.py --test-mode       — тестовый режим с выбором test group → real group
    python scripts/gk_responder.py --manage-groups   — управление группами (CLI)
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
from config import ai_settings

from src.common.constants.sync import (
    TELETHON_API_ID,
    TELETHON_API_HASH,
    GK_RESPONDER_SESSION_NAME,
)
from src.group_knowledge.message_collector import (
    _get_available_groups,
    load_groups_config,
    manage_groups_interactive,
    MessageCollector,
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
    """Вернуть выделенную Telethon-сессию автоответчика."""
    return GK_RESPONDER_SESSION_NAME


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
    """Выбрать реальную и тестовую группу для test mode.

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

    print("\n=== Test mode Group Knowledge ===")
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

    listened_groups = list(groups)
    group_mapping = {}
    dry_run = not args.live

    logger.info(
        "Загружено %d групп: %s (режим: %s)",
        len(groups),
        {g["id"] for g in groups},
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

    # Верифицировать group_id через Telegram API (обнаружить миграции Chat → Channel)
    resolver = MessageCollector(client=client, groups=listened_groups)
    await resolver.resolve_group_ids()
    group_ids = resolver.group_ids
    logger.info("Эффективные group_id после верификации: %s", sorted(group_ids))

    # Инициализировать автоответчик
    responder = GroupResponder(dry_run=dry_run, test_group_mapping=group_mapping)
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
            message = event.message
            raw_text = (message.text if message else "") or (message.message if message else "") or ""
            qa_query = _extract_qa_query(raw_text)
            if qa_query is None and not args.test_mode:
                return

            result = await responder.handle_message(
                event,
                group_ids,
                question_override=qa_query,
            )
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
        [f"{g.get('title', g['id'])} ({g['id']})" for g in listened_groups],
    )
    if args.test_mode:
        logger.info(
            "Test mode: обрабатываются все новые сообщения из тестовой группы; сообщения без '?' проходят LLM-классификацию вопроса"
        )
    else:
        logger.info("Обрабатываются только сообщения, начинающиеся с /qa")
    logger.info("Скрипт работает в daemon-режиме и ждёт новые сообщения")
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
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Интерактивно выбрать test group и real group для ответов в тестовой группе с логикой реальной",
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
    args = parser.parse_args()

    # Валидация неинтерактивных флагов для test-mode
    if (args.test_real_group_id is not None) != (args.test_group_id is not None):
        parser.error("Флаги --test-real-group-id и --test-group-id должны использоваться вместе")
    if args.test_real_group_id is not None and not args.test_mode:
        parser.error("Флаги --test-real-group-id / --test-group-id требуют --test-mode")

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
