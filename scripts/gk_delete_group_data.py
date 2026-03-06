#!/usr/bin/env python3
"""gk_delete_group_data — безопасная очистка данных Group Knowledge по одной группе."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.ai.vector_search import LocalVectorIndex
from src.group_knowledge import database as gk_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GK_DELETE] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gk_delete_group_data")


def _cleanup_vector_points(pair_ids: list[int]) -> int:
    """Удалить точки Q&A-пар из векторной коллекции Group Knowledge."""
    if not pair_ids:
        return 0

    deleted = 0
    vector_index = LocalVectorIndex(chunk_collection_name="gk_qa_pairs_v1")
    for pair_id in pair_ids:
        try:
            deleted += int(vector_index.delete_document_points(int(pair_id)) or 0)
        except Exception as exc:
            logger.warning("Не удалось удалить векторные точки pair_id=%s: %s", pair_id, exc)
    return deleted


def _print_stats(stats: dict, *, title: str) -> None:
    """Вывести статистику по найденным/удалённым данным группы."""
    logger.info(title)
    logger.info("group_id=%s", stats.get("group_id"))
    logger.info("messages=%s", stats.get("messages_found", 0))
    logger.info("qa_pairs=%s", stats.get("qa_pairs_found", 0))
    logger.info("responder_logs=%s", stats.get("responder_logs_found", 0))
    logger.info("image_queue=%s", stats.get("image_queue_found", 0))


def _select_group_interactively() -> Optional[int]:
    """Показать меню групп и вернуть выбранный group_id."""
    groups = gk_db.get_collected_groups()
    if not groups:
        logger.error("В базе нет собранных групп для удаления.")
        return None

    print("\n=== Удаление данных Group Knowledge: выбор группы ===")
    for index, group in enumerate(groups, start=1):
        title = (group.get("group_title") or "").strip() or "Без названия"
        print(
            f"{index}) group_id={group.get('group_id')} | title={title[:80]} | messages={group.get('message_count', 0)}"
        )
    print("0) Отмена")

    while True:
        raw_value = input("Выберите номер группы: ").strip()
        if not raw_value.isdigit():
            print("Введите номер пункта меню.")
            continue

        selected_index = int(raw_value)
        if selected_index == 0:
            return None

        if 1 <= selected_index <= len(groups):
            return int(groups[selected_index - 1]["group_id"])

        print("Некорректный номер. Повторите ввод.")


def _confirm_interactively(group_id: int) -> bool:
    """Запросить подтверждение удаления данных группы у пользователя."""
    confirmation = input(
        f"Подтвердите удаление данных группы {group_id}. Введите yes для продолжения: "
    ).strip()
    return confirmation.lower() == "yes"


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(
        description="Удаление данных Group Knowledge для конкретной группы",
        allow_abbrev=False,
    )
    parser.add_argument("--group-id", type=int, help="ID группы для очистки")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Интерактивное меню выбора группы и подтверждения удаления",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Подтверждение реального удаления (без флага выполняется только dry-run)",
    )
    parser.add_argument(
        "--no-vector-cleanup",
        action="store_true",
        help="Не удалять векторные точки Q&A-пар из коллекции gk_qa_pairs_v1",
    )
    args = parser.parse_args()

    group_id = args.group_id
    interactive_mode = bool(args.interactive or group_id is None)

    if interactive_mode:
        group_id = _select_group_interactively()
        if group_id is None:
            logger.info("Удаление отменено пользователем.")
            return

    dry_stats = gk_db.delete_group_data(group_id, dry_run=True)
    _print_stats(dry_stats, title="Оценка удаления (dry-run)")

    should_delete = bool(args.yes)
    if interactive_mode and not should_delete:
        should_delete = _confirm_interactively(group_id)

    if not should_delete:
        if interactive_mode:
            logger.info("Удаление отменено пользователем.")
        else:
            logger.info("Удаление не выполнено. Добавьте --yes для подтверждения.")
        return

    pair_ids = gk_db.get_qa_pair_ids_by_group(group_id)
    deleted_stats = gk_db.delete_group_data(group_id, dry_run=False)

    vector_deleted = 0
    if not args.no_vector_cleanup:
        vector_deleted = _cleanup_vector_points(pair_ids)

    logger.info("Удаление выполнено:")
    logger.info("messages_deleted=%s", deleted_stats.get("messages_deleted", 0))
    logger.info("qa_pairs_deleted=%s", deleted_stats.get("qa_pairs_deleted", 0))
    logger.info("responder_logs_deleted=%s", deleted_stats.get("responder_logs_deleted", 0))
    logger.info("image_queue_deleted=%s", deleted_stats.get("image_queue_deleted", 0))
    if args.no_vector_cleanup:
        logger.info("vector_points_deleted=0 (пропущено флагом --no-vector-cleanup)")
    else:
        logger.info("vector_points_deleted=%s", vector_deleted)


if __name__ == "__main__":
    main()
