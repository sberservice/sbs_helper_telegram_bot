#!/usr/bin/env python3
"""One-way синхронизация коллекции Qdrant из remote в local."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _bootstrap_project_root() -> None:
    """Добавить корень проекта в sys.path для прямого запуска скрипта."""
    project_root = Path(__file__).resolve().parents[1]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


_bootstrap_project_root()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Точка входа CLI-скрипта синхронизации remote→local Qdrant."""
    from config import ai_settings
    from src.core.ai.qdrant_sync import QdrantRemoteToLocalSync

    parser = argparse.ArgumentParser(
        description="Синхронизация Qdrant коллекции remote→local (best-effort)",
    )
    parser.add_argument(
        "--collection",
        default=ai_settings.AI_RAG_VECTOR_SYNC_COLLECTION,
        help=(
            "Имя коллекции для синхронизации "
            "(по умолчанию AI_RAG_VECTOR_SYNC_COLLECTION)"
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Размер батча scroll/upsert (по умолчанию: 200)",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=0,
        help="Ограничить количество синхронизируемых точек",
    )
    parser.add_argument(
        "--delete-missing",
        action="store_true",
        help="Удалять из local точки, которых нет в remote",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Проверить объём синхронизации без записи/удаления",
    )
    args = parser.parse_args()

    if args.batch_size <= 0:
        logger.error("--batch-size должен быть положительным")
        raise SystemExit(1)

    if args.max_points < 0:
        logger.error("--max-points не может быть отрицательным")
        raise SystemExit(1)

    syncer = QdrantRemoteToLocalSync(
        collection_name=args.collection,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        delete_missing=args.delete_missing,
        max_points=args.max_points or None,
    )

    try:
        stats = syncer.sync()
    except Exception as exc:
        logger.error("Синхронизация remote→local завершилась с ошибкой: %s", exc)
        raise SystemExit(1) from exc

    logger.info(
        "Синхронизация завершена: collection=%s scanned=%s synced=%s skipped=%s failed=%s deleted=%s batches=%s",
        syncer.collection_name,
        stats.scanned,
        stats.synced,
        stats.skipped,
        stats.failed,
        stats.deleted,
        stats.batches,
    )


if __name__ == "__main__":
    main()
