#!/usr/bin/env python3
"""Синхронизация директории документов с RAG-базой знаний."""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional


def _bootstrap_project_root() -> None:
    """Добавить корень проекта в sys.path для прямого запуска скрипта."""
    project_root = Path(__file__).resolve().parents[1]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)


_bootstrap_project_root()

from src.sbs_helper_telegram_bot.ai_router.rag_service import RagKnowledgeService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _normalize_source_url(file_path: Path) -> str:
    """Нормализовать путь файла для хранения в source_url."""
    return file_path.resolve().as_posix()


def _scan_files(root_dir: Path, recursive: bool) -> List[Path]:
    """Собрать список файлов в директории для обработки."""
    pattern = "**/*" if recursive else "*"
    files = [path for path in root_dir.glob(pattern) if path.is_file()]
    return sorted(files)


def _sha256(payload: bytes) -> str:
    """Вычислить SHA-256 для содержимого файла."""
    return hashlib.sha256(payload).hexdigest()


def run_ingest_cycle(
    directory: Path,
    recursive: bool,
    dry_run: bool,
    force_update: bool,
    uploaded_by: int,
    service: Optional[RagKnowledgeService] = None,
) -> Dict[str, int]:
    """Выполнить один цикл синхронизации директории с RAG."""
    rag_service = service or RagKnowledgeService()
    root_dir = directory.resolve()
    root_prefix = root_dir.as_posix().rstrip("/") + "/"

    stats = {
        "scanned_files": 0,
        "supported_files": 0,
        "ingested": 0,
        "duplicates": 0,
        "unchanged": 0,
        "purged": 0,
        "errors": 0,
    }

    files = _scan_files(root_dir, recursive=recursive)
    stats["scanned_files"] = len(files)

    existing_documents = rag_service.list_documents_by_source(
        source_type="filesystem",
        source_url_prefix=root_prefix,
    )
    docs_by_source_url: Dict[str, List[Dict[str, object]]] = {}
    for row in existing_documents:
        source_url = str(row.get("source_url") or "").strip()
        if not source_url:
            continue
        docs_by_source_url.setdefault(source_url, []).append(row)

    current_source_urls = set()

    for file_path in files:
        if not rag_service.is_supported_file(file_path.name):
            continue

        stats["supported_files"] += 1
        source_url = _normalize_source_url(file_path)
        current_source_urls.add(source_url)

        try:
            payload = file_path.read_bytes()
        except OSError as exc:
            stats["errors"] += 1
            logger.error("Не удалось прочитать файл %s: %s", file_path, exc)
            continue

        file_hash = _sha256(payload)
        source_rows = docs_by_source_url.get(source_url, [])

        has_same_active = any(
            str(row.get("status") or "") == "active" and str(row.get("content_hash") or "") == file_hash
            for row in source_rows
        )
        if has_same_active and not force_update:
            stats["unchanged"] += 1
            continue

        if dry_run:
            stats["ingested"] += 1
            stats["purged"] += len(source_rows)
            continue

        for row in source_rows:
            document_id = int(row["id"])
            if rag_service.delete_document(document_id, updated_by=uploaded_by, hard_delete=True):
                stats["purged"] += 1

        try:
            ingest_result = rag_service.ingest_document_from_bytes(
                filename=file_path.name,
                payload=payload,
                uploaded_by=uploaded_by,
                source_type="filesystem",
                source_url=source_url,
            )
            if int(ingest_result.get("is_duplicate", 0)) == 1:
                stats["duplicates"] += 1
            else:
                stats["ingested"] += 1
        except ValueError as exc:
            stats["errors"] += 1
            logger.error("Ошибка ingestion для %s: %s", file_path, exc)

    missing_source_urls = set(docs_by_source_url.keys()) - current_source_urls

    if dry_run:
        stats["purged"] += sum(len(docs_by_source_url[url]) for url in missing_source_urls)
        return stats

    for missing_url in sorted(missing_source_urls):
        for row in docs_by_source_url[missing_url]:
            document_id = int(row["id"])
            if rag_service.delete_document(document_id, updated_by=uploaded_by, hard_delete=True):
                stats["purged"] += 1

    return stats


def daemon_loop(
    directory: Path,
    recursive: bool,
    dry_run: bool,
    force_update: bool,
    uploaded_by: int,
    interval_seconds: int,
) -> None:
    """Запустить непрерывный режим синхронизации."""
    logger.info("Запущен daemon-режим синхронизации RAG (интервал: %s сек)", interval_seconds)

    while True:
        cycle_started_at = time.time()
        try:
            stats = run_ingest_cycle(
                directory=directory,
                recursive=recursive,
                dry_run=dry_run,
                force_update=force_update,
                uploaded_by=uploaded_by,
            )
            logger.info("Цикл синхронизации завершён: %s", stats)
        except (RuntimeError, ValueError, OSError) as exc:
            logger.exception("Фатальная ошибка цикла синхронизации: %s", exc)

        elapsed = time.time() - cycle_started_at
        sleep_seconds = max(1, interval_seconds - int(elapsed))
        logger.info("Следующий цикл через %s сек", sleep_seconds)
        time.sleep(sleep_seconds)


def main() -> None:
    """Точка входа CLI-скрипта синхронизации RAG."""
    parser = argparse.ArgumentParser(
        description="Синхронизация директории документов с RAG-базой знаний",
    )
    parser.add_argument(
        "--directory",
        "-d",
        required=True,
        help="Путь к директории с документами",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Запустить непрерывный режим",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=900,
        help="Интервал в секундах для daemon-режима (по умолчанию: 900)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Показать изменения без записи в БД",
    )
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Принудительно переобновлять файлы даже без изменения content_hash",
    )
    parser.add_argument(
        "--uploaded-by",
        type=int,
        default=0,
        help="Системный ID исполнителя для аудита изменений (по умолчанию: 0)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Сканировать только верхний уровень директории",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Включить подробный лог",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    target_dir = Path(args.directory).expanduser().resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        logger.error("Директория не найдена или недоступна: %s", target_dir)
        raise SystemExit(1)

    if args.interval_seconds <= 0:
        logger.error("Интервал должен быть положительным: %s", args.interval_seconds)
        raise SystemExit(1)

    recursive = not args.no_recursive
    logger.info(
        "Старт синхронизации RAG: directory=%s recursive=%s dry_run=%s force_update=%s",
        target_dir,
        recursive,
        args.dry_run,
        args.force_update,
    )

    try:
        if args.daemon:
            daemon_loop(
                directory=target_dir,
                recursive=recursive,
                dry_run=args.dry_run,
                force_update=args.force_update,
                uploaded_by=args.uploaded_by,
                interval_seconds=args.interval_seconds,
            )
        else:
            stats = run_ingest_cycle(
                directory=target_dir,
                recursive=recursive,
                dry_run=args.dry_run,
                force_update=args.force_update,
                uploaded_by=args.uploaded_by,
            )
            logger.info("Синхронизация завершена: %s", stats)
    except KeyboardInterrupt as exc:
        logger.info("Остановлено пользователем")
        raise SystemExit(0) from exc


if __name__ == "__main__":
    main()
