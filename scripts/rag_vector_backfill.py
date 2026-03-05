#!/usr/bin/env python3
"""Пакетное заполнение локального векторного индекса по RAG-чанкам и summary документов."""

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

from src.core.ai.rag_service import RagKnowledgeService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Точка входа CLI-скрипта backfill векторного индекса."""
    parser = argparse.ArgumentParser(
        description="Backfill локального векторного индекса Qdrant из rag_chunks и/или rag_document_summaries",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Размер батча чанков для одного upsert (по умолчанию: 100)",
    )
    parser.add_argument(
        "--source-type",
        default="",
        help="Ограничить backfill документами с заданным source_type",
    )
    parser.add_argument(
        "--max-documents",
        type=int,
        default=0,
        help="Ограничить число документов для обработки",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Оценить объём работ без записи в индекс",
    )
    parser.add_argument(
        "--target",
        choices=("chunks", "summaries", "both"),
        default="both",
        help="Что индексировать: только чанки, только summary или оба типа (по умолчанию: both)",
    )
    args = parser.parse_args()

    if args.batch_size <= 0:
        logger.error("--batch-size должен быть положительным")
        raise SystemExit(1)

    service = RagKnowledgeService()
    stats = service.backfill_vector_index(
        batch_size=args.batch_size,
        source_type=(args.source_type or None),
        dry_run=args.dry_run,
        max_documents=(args.max_documents if args.max_documents > 0 else None),
        target=args.target,
    )

    logger.info("Backfill vector index завершён: %s", stats)


if __name__ == "__main__":
    main()
