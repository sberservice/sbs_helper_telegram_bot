#!/usr/bin/env python3
"""Синхронизация вопросов аттестации в RAG-базу знаний."""

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
    """Точка входа CLI-скрипта синхронизации certification Q/A в RAG."""
    parser = argparse.ArgumentParser(
        description="Синхронизировать вопросы аттестации в RAG-корпус",
    )
    parser.add_argument(
        "--uploaded-by",
        type=int,
        default=0,
        help="ID пользователя для аудита изменений в rag_documents (по умолчанию: 0)",
    )
    parser.add_argument(
        "--upsert-vectors",
        action="store_true",
        help="Сразу записывать эмбеддинги в Qdrant при ingest",
    )
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Принудительно переингестить все certification-документы, даже без изменений content_hash",
    )

    args = parser.parse_args()

    service = RagKnowledgeService()
    stats = service.sync_certification_questions_to_rag(
        uploaded_by=int(args.uploaded_by),
        upsert_vectors=bool(args.upsert_vectors),
        force_update=bool(args.force_update),
    )
    logger.info("Certification->RAG sync завершён: %s", stats)


if __name__ == "__main__":
    main()
