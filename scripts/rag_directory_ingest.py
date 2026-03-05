#!/usr/bin/env python3
"""Синхронизация директории документов с RAG-базой знаний.

Примеры использования:
    # Однократная синхронизация директории
    python scripts/rag_directory_ingest.py -d ~/docs/knowledge_base

    # Dry-run (показать изменения без записи в БД)
    python scripts/rag_directory_ingest.py -d ~/docs/knowledge_base --dry-run

    # Принудительное обновление всех файлов
    python scripts/rag_directory_ingest.py -d ~/docs/knowledge_base --force-update

    # Регенерация summary для всех документов (при изменении промпта)
    python scripts/rag_directory_ingest.py -d ~/docs/knowledge_base --regenerate-summaries

    # Daemon-режим (непрерывная синхронизация)
    python scripts/rag_directory_ingest.py -d ~/docs/knowledge_base --daemon

    # Daemon-режим с кастомным интервалом (5 минут)
    python scripts/rag_directory_ingest.py -d ~/docs/knowledge_base --daemon --interval-seconds 300

    # Только верхний уровень директории (без рекурсии)
    python scripts/rag_directory_ingest.py -d ~/docs/knowledge_base --no-recursive

    # Показать текущий режим ingestion (сплиттер, настройки, статистика)
    python scripts/rag_directory_ingest.py -d ~/docs/knowledge_base --info

    # Подробный лог
    python scripts/rag_directory_ingest.py -d ~/docs/knowledge_base -v
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib
import importlib.metadata
import logging
import os
import sys
import tempfile
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

from src.common import database
from src.core.ai.rag_service import RagKnowledgeService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _resolve_package_version(import_name: str, dist_name: Optional[str] = None) -> str:
    """Безопасно получить версию установленного Python-пакета.

    Сначала пытается взять ``__version__`` из импортированного модуля,
    затем fallback на ``importlib.metadata.version`` по имени дистрибутива.
    """
    distribution_name = dist_name or import_name.replace("_", "-")

    try:
        module = importlib.import_module(import_name)
    except ImportError:
        return "недоступен"

    module_version = getattr(module, "__version__", None)
    if module_version:
        return str(module_version)

    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return "неизвестна"
    except Exception:
        return "неизвестна"


def _build_lock_file_path(directory: Path) -> Path:
    """Построить путь lock-файла для конкретной директории синхронизации."""
    digest = hashlib.sha256(directory.resolve().as_posix().encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"rag_directory_ingest_{digest}.lock"


def _acquire_single_instance_lock(lock_file_path: Path) -> int:
    """Захватить lock-файл single-instance.

    Возвращает файловый дескриптор lock-файла, который нужно закрыть
    после завершения работы процесса.
    """
    current_pid = os.getpid()
    lock_file_path.parent.mkdir(parents=True, exist_ok=True)

    def _try_create_lock() -> int:
        fd = os.open(str(lock_file_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, f"{current_pid}\n".encode("utf-8"))
        os.fsync(fd)
        return fd

    try:
        return _try_create_lock()
    except FileExistsError:
        existing_pid: Optional[int] = None
        try:
            raw_pid = lock_file_path.read_text(encoding="utf-8").strip()
            if raw_pid:
                existing_pid = int(raw_pid)
        except (OSError, ValueError):
            existing_pid = None

        if existing_pid == current_pid:
            raise RuntimeError(
                "Текущий процесс уже удерживает lock синхронизации для этой директории."
            )

        if existing_pid and existing_pid != current_pid:
            try:
                os.kill(existing_pid, 0)
                raise RuntimeError(
                    f"Уже запущен другой процесс синхронизации (pid={existing_pid}). "
                    "Остановите его или удалите stale lock-файл."
                )
            except ProcessLookupError:
                logger.warning(
                    "Обнаружен stale lock-файл %s (pid=%s), выполняется очистка",
                    lock_file_path,
                    existing_pid,
                )
            except PermissionError:
                raise RuntimeError(
                    f"Невозможно проверить процесс-владелец lock-файла (pid={existing_pid}). "
                    "Проверьте процессы вручную."
                )

        try:
            lock_file_path.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"Не удалось очистить lock-файл {lock_file_path}: {exc}") from exc

        return _try_create_lock()


def _release_single_instance_lock(lock_file_path: Path, lock_fd: Optional[int]) -> None:
    """Освободить single-instance lock-файл."""
    try:
        if lock_fd is not None:
            os.close(lock_fd)
    except OSError:
        pass

    try:
        lock_file_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Не удалось удалить lock-файл %s: %s", lock_file_path, exc)


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


def _get_document_chunks(document_id: int) -> List[str]:
    """Получить все чанки документа из базы данных."""
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(
                """
                SELECT chunk_text
                FROM rag_chunks
                WHERE document_id = %s
                ORDER BY chunk_index
                """,
                (document_id,),
            )
            rows = cursor.fetchall() or []
    return [str(row.get("chunk_text") or "") for row in rows]


def regenerate_document_summaries(
    directory: Path,
    recursive: bool,
    dry_run: bool,
    uploaded_by: int,
    service: Optional[RagKnowledgeService] = None,
) -> Dict[str, int]:
    """
    Перегенерировать summary для всех документов директории.

    Используется при изменении промпта суммаризации или модели.

    Args:
        directory: Директория с документами.
        recursive: Сканировать рекурсивно (если False — только верхний уровень).
        dry_run: Только показать, какие документы будут обновлены.
        uploaded_by: ID пользователя для аудита.
        service: Экземпляр RagKnowledgeService (опционально).

    Returns:
        Статистика по регенерации.
    """
    rag_service = service or RagKnowledgeService()
    root_dir = directory.resolve()
    root_prefix = root_dir.as_posix().rstrip("/") + "/"

    stats = {
        "documents_found": 0,
        "summaries_regenerated": 0,
        "skipped_no_chunks": 0,
        "skipped_subdirectory": 0,
        "errors": 0,
    }

    existing_documents = rag_service.list_documents_by_source(
        source_type="filesystem",
        source_url_prefix=root_prefix,
    )

    # Фильтрация для non-recursive режима
    if not recursive:
        filtered_docs = []
        for doc in existing_documents:
            source_url = str(doc.get("source_url") or "")
            relative_path = source_url[len(root_prefix):] if source_url.startswith(root_prefix) else source_url
            # Если в относительном пути есть /, значит файл в поддиректории
            if "/" not in relative_path:
                filtered_docs.append(doc)
            else:
                stats["skipped_subdirectory"] += 1
        existing_documents = filtered_docs

    stats["documents_found"] = len(existing_documents)

    logger.info(
        "Найдено %d документов для регенерации summary (prefix=%s recursive=%s)",
        len(existing_documents),
        root_prefix,
        recursive,
    )

    for doc in existing_documents:
        document_id = int(doc.get("id") or 0)
        filename = str(doc.get("filename") or "")
        status = str(doc.get("status") or "")

        if status != "active":
            logger.debug("Пропуск документа id=%d (status=%s)", document_id, status)
            continue

        if dry_run:
            logger.info("[DRY-RUN] Будет перегенерировано summary: id=%d filename=%s", document_id, filename)
            stats["summaries_regenerated"] += 1
            continue

        try:
            chunks = _get_document_chunks(document_id)
            if not chunks:
                logger.warning("Документ id=%d не имеет чанков, пропуск", document_id)
                stats["skipped_no_chunks"] += 1
                continue

            # Используем приватный метод для генерации summary
            summary_text, model_name = rag_service._generate_document_summary(
                filename=filename,
                chunks=chunks,
                user_id=uploaded_by,
                summary_model_scope="directory_ingest",
            )

            if not summary_text:
                logger.warning("Не удалось сгенерировать summary для id=%d", document_id)
                stats["errors"] += 1
                continue

            # Обновляем summary в БД
            with database.get_db_connection() as conn:
                with database.get_cursor(conn) as cursor:
                    rag_service._upsert_document_summary(
                        cursor=cursor,
                        document_id=document_id,
                        summary_text=summary_text,
                        model_name=model_name,
                    )

            logger.info(
                "Перегенерировано summary: id=%d filename=%s model=%s",
                document_id,
                filename,
                model_name or "unknown",
            )
            stats["summaries_regenerated"] += 1

        except Exception as exc:
            logger.error("Ошибка регенерации summary для id=%d: %s", document_id, exc)
            stats["errors"] += 1

    return stats


def _log_chunking_diagnostics(rag_service: RagKnowledgeService) -> None:
    """Записать в лог активную конфигурацию chunking перед синхронизацией."""
    if not hasattr(rag_service, "get_chunking_diagnostics"):
        logger.info("Chunking конфигурация: диагностика недоступна для текущего сервиса")
        return

    try:
        diagnostics = rag_service.get_chunking_diagnostics()
    except Exception as exc:
        logger.warning("Не удалось получить chunking-диагностику: %s", exc)
        return

    logger.info(
        "Chunking конфигурация: html_strategy=%s plain_text_strategy=%s slicer=%s chunk_size=%s chunk_overlap=%s html_splitter_enabled=%s langchain_splitter_supported=%s",
        diagnostics.get("html_strategy"),
        diagnostics.get("plain_text_strategy"),
        diagnostics.get("text_slicer"),
        diagnostics.get("chunk_size"),
        diagnostics.get("chunk_overlap"),
        diagnostics.get("html_splitter_enabled"),
        diagnostics.get("langchain_splitter_supported"),
    )


def display_ingest_info(directory: Path, recursive: bool) -> None:
    """Вывести подробную информацию о текущем режиме ingestion.

    Показывает доступность LangChain, активный сплиттер,
    параметры чанкинга, поддерживаемые форматы и статистику директории.
    """
    rag_service = RagKnowledgeService()

    # Диагностика chunking
    diagnostics = rag_service.get_chunking_diagnostics()

    # Поддерживаемые расширения
    supported_ext = sorted({".pdf", ".txt", ".docx", ".md", ".html", ".htm"})

    # Статистика директории
    root_dir = directory.resolve()
    files = _scan_files(root_dir, recursive=recursive)
    supported_files = [f for f in files if rag_service.is_supported_file(f.name)]
    ext_counts: Dict[str, int] = {}
    for f in supported_files:
        ext = f.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    # Версии LangChain
    langchain_version = _resolve_package_version("langchain", "langchain")
    langchain_text_splitters_version = _resolve_package_version(
        "langchain_text_splitters",
        "langchain-text-splitters",
    )

    # HTML splitter class
    html_splitter_class = "недоступен"
    try:
        splitter_cls = rag_service._get_html_splitter_class()
        html_splitter_class = f"{splitter_cls.__module__}.{splitter_cls.__name__}"
    except Exception:
        pass

    # Python version
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    print("\n" + "=" * 60)
    print("ИНФОРМАЦИЯ О РЕЖИМЕ INGESTION")
    print("=" * 60)

    print(f"\n--- Среда ---")
    print(f"  Python:                      {py_version}")
    print(f"  langchain:                   {langchain_version}")
    print(f"  langchain-text-splitters:    {langchain_text_splitters_version}")

    print(f"\n--- Сплиттеры ---")
    print(f"  LangChain доступен:         {'да' if diagnostics.get('langchain_splitter_supported') else 'нет'}")
    print(f"  Text slicer:                 {diagnostics.get('text_slicer')}")
    print(f"  HTML splitter включён:      {'да' if diagnostics.get('html_splitter_enabled') else 'нет'}")
    print(f"  HTML splitter class:         {html_splitter_class}")
    print(f"  HTML стратегия:             {diagnostics.get('html_strategy')}")
    print(f"  Plain text стратегия:       {diagnostics.get('plain_text_strategy')}")

    print(f"\n--- Параметры чанкинга ---")
    print(f"  chunk_size:                  {diagnostics.get('chunk_size')}")
    print(f"  chunk_overlap:               {diagnostics.get('chunk_overlap')}")
    print(f"  max_chunks_per_doc:          {getattr(__import__('config.ai_settings', fromlist=['AI_RAG_MAX_CHUNKS_PER_DOC']), 'AI_RAG_MAX_CHUNKS_PER_DOC', 'N/A')}")
    print(f"  max_file_size_mb:            {getattr(__import__('config.ai_settings', fromlist=['AI_RAG_MAX_FILE_SIZE_MB']), 'AI_RAG_MAX_FILE_SIZE_MB', 'N/A')}")
    # Сепараторы
    separators = getattr(rag_service, '_RU_SEPARATORS', None)
    if separators:
        separator_names = []
        for sep in separators:
            if sep == "\n\n":
                separator_names.append("\\n\\n")
            elif sep == "\n":
                separator_names.append("\\n")
            elif sep == "":
                separator_names.append('""')
            else:
                separator_names.append(repr(sep))
        print(f"  сепараторы:                 {', '.join(separator_names)}")

    print(f"\n--- Поддерживаемые форматы ---")
    print(f"  Расширения:                 {', '.join(supported_ext)}")

    print(f"\n--- Директория ---")
    print(f"  Путь:                        {root_dir}")
    print(f"  Рекурсивный скан:          {'да' if recursive else 'нет'}")
    print(f"  Всего файлов:              {len(files)}")
    print(f"  Поддерживаемых файлов:    {len(supported_files)}")
    if ext_counts:
        for ext, count in sorted(ext_counts.items()):
            print(f"    {ext}: {count}")

    print("\n" + "=" * 60 + "\n")


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
    _log_chunking_diagnostics(rag_service)
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
            ingest_result = rag_service.ingest_document_from_bytes_sync(
                filename=file_path.name,
                payload=payload,
                uploaded_by=uploaded_by,
                source_type="filesystem",
                source_url=source_url,
                upsert_vectors=False,
                summary_model_scope="directory_ingest",
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
        "--regenerate-summaries",
        action="store_true",
        help="Перегенерировать summary для всех документов (при изменении промпта)",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Показать текущий режим ingestion (сплиттеры, настройки, статистика) и выйти",
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

    if args.info:
        display_ingest_info(
            directory=target_dir,
            recursive=recursive,
        )
        raise SystemExit(0)

    lock_file_path = _build_lock_file_path(target_dir)
    lock_fd: Optional[int] = None

    try:
        lock_fd = _acquire_single_instance_lock(lock_file_path)
    except RuntimeError as exc:
        logger.error("Запуск синхронизации отклонён: %s", exc)
        raise SystemExit(1) from exc

    def _cleanup_lock() -> None:
        _release_single_instance_lock(lock_file_path, lock_fd)

    atexit.register(_cleanup_lock)

    logger.info(
        "Старт синхронизации RAG: directory=%s recursive=%s dry_run=%s force_update=%s regenerate_summaries=%s",
        target_dir,
        recursive,
        args.dry_run,
        args.force_update,
        args.regenerate_summaries,
    )

    try:
        if args.regenerate_summaries:
            if args.daemon:
                logger.error("--regenerate-summaries несовместим с --daemon")
                raise SystemExit(1)
            stats = regenerate_document_summaries(
                directory=target_dir,
                recursive=recursive,
                dry_run=args.dry_run,
                uploaded_by=args.uploaded_by,
            )
            logger.info("Регенерация summary завершена: %s", stats)
        elif args.daemon:
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
    finally:
        _release_single_instance_lock(lock_file_path, lock_fd)


if __name__ == "__main__":
    main()
