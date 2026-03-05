#!/usr/bin/env python3
"""Единый CLI-инструмент для управления RAG-подсистемой.

Поддерживает как интерактивный (`wizard`), так и non-interactive режим.

Субкоманды
----------
  health          — проверка подключения к MySQL и Qdrant
  status          — статистика корпуса (документы, чанки, эмбеддинги)
  setup           — первичная настройка (применение SQL-миграций, первый backfill)
  update docs     — синхронизация директории документов
  update cert     — синхронизация вопросов аттестации
  update vectors  — перестройка векторного индекса
  update all      — полный пересмотр корпуса (docs + cert + vectors)
  sync-remote     — синхронизация Qdrant remote → local
  wizard          — интерактивный guided-режим

Примеры использования
---------------------
  python scripts/rag_ops.py health
  python scripts/rag_ops.py status
  python scripts/rag_ops.py setup --apply-sql --yes
  python scripts/rag_ops.py update docs --directory /path/to/docs --force
  python scripts/rag_ops.py update cert --force --upsert-vectors
  python scripts/rag_ops.py update vectors --target both --batch-size 200
  python scripts/rag_ops.py update all --directory /path/to/docs --force
  python scripts/rag_ops.py sync-remote --dry-run
  python scripts/rag_ops.py wizard
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# sys.path bootstrap — позволяет запускать скрипт из любой директории
# ---------------------------------------------------------------------------

def _bootstrap_project_root() -> Path:
    """Добавить корень проекта в sys.path для прямого запуска скрипта."""
    project_root = Path(__file__).resolve().parents[1]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        sys.path.insert(0, project_root_str)
    return project_root


_PROJECT_ROOT = _bootstrap_project_root()

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rag_ops")

# ---------------------------------------------------------------------------
# Вспомогательные функции вывода
# ---------------------------------------------------------------------------

_ANSI_RESET = "\033[0m"
_ANSI_BOLD = "\033[1m"
_ANSI_GREEN = "\033[32m"
_ANSI_YELLOW = "\033[33m"
_ANSI_RED = "\033[31m"
_ANSI_CYAN = "\033[36m"
_ANSI_DIM = "\033[2m"


def _supports_color() -> bool:
    """Возвращает True, если терминал поддерживает ANSI-цвета."""
    return sys.stdout.isatty()


def _c(text: str, code: str) -> str:
    return f"{code}{text}{_ANSI_RESET}" if _supports_color() else text


def _ok(msg: str) -> None:
    print(_c(f"  ✓  {msg}", _ANSI_GREEN))


def _warn(msg: str) -> None:
    print(_c(f"  ⚠  {msg}", _ANSI_YELLOW))


def _err(msg: str) -> None:
    print(_c(f"  ✗  {msg}", _ANSI_RED))


def _info(msg: str) -> None:
    print(_c(f"  ·  {msg}", _ANSI_CYAN))


def _header(msg: str) -> None:
    print()
    print(_c(f"{'─' * 60}", _ANSI_DIM))
    print(_c(f"  {msg}", _ANSI_BOLD))
    print(_c(f"{'─' * 60}", _ANSI_DIM))


def _step(msg: str) -> None:
    print(_c(f"\n  → {msg}", _ANSI_BOLD))


def _ask(prompt: str, default: str = "") -> str:
    """Интерактивный prompt с дефолтом."""
    hint = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{hint}: ").strip()
        return answer if answer else default
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def _confirm(prompt: str, default: bool = True) -> bool:
    """Запрос подтверждения Y/N."""
    hint = "[Y/n]" if default else "[y/N]"
    answer = _ask(f"{prompt} {hint}", "y" if default else "n").lower()
    return answer in ("y", "yes", "")


# ---------------------------------------------------------------------------
# SQL-миграции, необходимые для RAG
# ---------------------------------------------------------------------------

_RAG_SQL_FILES: List[str] = [
    "sql/ai_rag_setup.sql",
    "sql/ai_rag_document_summaries_setup.sql",
    "sql/ai_rag_vector_setup.sql",
    "sql/ai_rag_summary_vector_setup.sql",
    "sql/ai_rag_certification_signals_setup.sql",
    "sql/rag_document_summaries_fulltext_index.sql",
    "sql/ai_router_setup.sql",
    "sql/ai_model_io_log_retention.sql",
]

# ---------------------------------------------------------------------------
# Команда: health
# ---------------------------------------------------------------------------

def cmd_health(_args: argparse.Namespace) -> int:
    """Проверить подключение к MySQL и Qdrant (если включён vector)."""
    _header("RAG Health Check")
    ok = True

    # --- MySQL ---
    _step("MySQL")
    try:
        from src.common import database  # noqa: PLC0415

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("SELECT COUNT(*) AS cnt FROM rag_documents")
                row = cursor.fetchone()
                cnt = int((row or {}).get("cnt") or 0)
        _ok(f"MySQL подключён. rag_documents: {cnt} записей.")
    except ModuleNotFoundError:
        _warn("rag_documents table ещё не создана — нужно запустить 'setup'.")
    except Exception as exc:
        _err(f"MySQL недоступен: {exc}")
        ok = False

    # --- Qdrant ---
    _step("Qdrant (vector index)")
    try:
        from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings  # noqa: PLC0415

        if not ai_settings.AI_RAG_VECTOR_ENABLED:
            _warn("AI_RAG_VECTOR_ENABLED=0 — векторный слой отключён.")
        else:
            from src.sbs_helper_telegram_bot.ai_router.vector_search import LocalVectorIndex  # noqa: PLC0415

            index = LocalVectorIndex()
            if not index.is_ready():
                _warn("Векторный индекс не инициализирован (возможно, local mode + Qdrant не запущен).")
            else:
                _ok("Qdrant подключён и векторный индекс доступен.")
    except Exception as exc:
        _warn(f"Qdrant недоступен или не сконфигурирован: {exc}")

    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Команда: status
# ---------------------------------------------------------------------------

def cmd_status(_args: argparse.Namespace) -> int:
    """Показать статистику корпуса RAG."""
    _header("RAG Corpus Status")
    try:
        from src.common import database  # noqa: PLC0415
    except Exception as exc:
        _err(f"Не удалось подключиться к БД: {exc}")
        return 1

    queries = {
        "rag_documents (active)": "SELECT COUNT(*) AS cnt FROM rag_documents WHERE status='active'",
        "rag_documents (total)": "SELECT COUNT(*) AS cnt FROM rag_documents",
        "rag_chunks (total)": "SELECT COUNT(*) AS cnt FROM rag_chunks",
        "rag_document_summaries": "SELECT COUNT(*) AS cnt FROM rag_document_summaries WHERE summary_text IS NOT NULL AND summary_text != ''",
        "rag_chunk_embeddings (indexed)": "SELECT COUNT(*) AS cnt FROM rag_chunk_embeddings",
        "rag_summary_embeddings (indexed)": "SELECT COUNT(*) AS cnt FROM rag_summary_embeddings",
    }

    for label, query in queries.items():
        try:
            with database.get_db_connection() as conn:
                with database.get_cursor(conn) as cursor:
                    cursor.execute(query)
                    row = cursor.fetchone()
                    cnt = int((row or {}).get("cnt") or 0)
            _info(f"{label:<40}: {cnt}")
        except Exception:
            _warn(f"{label:<40}: (таблица не существует)")

    # Source-type breakdown
    _step("Документы по source_type:")
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT source_type, status, COUNT(*) AS cnt "
                    "FROM rag_documents GROUP BY source_type, status ORDER BY source_type, status"
                )
                rows = cursor.fetchall() or []
        for row in rows:
            _info(f"  source_type={row.get('source_type')!r:<20} status={row.get('status')!r:<10}: {row.get('cnt')}")
    except Exception:
        _warn("Не удалось получить breakdown по source_type.")

    return 0


# ---------------------------------------------------------------------------
# Команда: setup
# ---------------------------------------------------------------------------

def cmd_setup(args: argparse.Namespace) -> int:
    """Первичная настройка RAG: применить SQL-миграции и сделать первый backfill."""
    _header("RAG First-Time Setup")

    apply_sql = getattr(args, "apply_sql", False)
    yes = getattr(args, "yes", False)

    # --- Проверка .env ---
    _step("Проверка .env / переменных окружения")
    env_file = _PROJECT_ROOT / ".env"
    if not env_file.exists():
        _warn(".env файл не найден. Скопируйте .env.example → .env и заполните значения.")
    else:
        _ok(".env найден.")

    try:
        from src.common.constants import database as db_cfg  # noqa: PLC0415

        _ok(f"MySQL: {db_cfg.MYSQL_HOST}:{db_cfg.MYSQL_PORT}/{db_cfg.MYSQL_DATABASE}")
    except Exception as exc:
        _err(f"Ошибка загрузки MySQL-конфигурации: {exc}")
        return 1

    try:
        from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings  # noqa: PLC0415
        vec_enabled = bool(ai_settings.AI_RAG_VECTOR_ENABLED)
        _info(f"AI_RAG_VECTOR_ENABLED={'1 (векторный слой активен)' if vec_enabled else '0 (только lexical)'}")
    except Exception as exc:
        _warn(f"Не удалось прочитать AI настройки: {exc}")

    # --- SQL-миграции ---
    _step("SQL-миграции")
    pending_files = [
        str(_PROJECT_ROOT / f)
        for f in _RAG_SQL_FILES
        if (_PROJECT_ROOT / f).exists()
    ]
    missing_files = [f for f in _RAG_SQL_FILES if not (_PROJECT_ROOT / f).exists()]
    if missing_files:
        _warn(f"Следующие SQL-файлы не найдены (пропущены): {missing_files}")
    if pending_files:
        _info(f"Найдено SQL-файлов для применения: {len(pending_files)}")
        for f in pending_files:
            print(f"       {Path(f).name}")
    else:
        _warn("Ни один SQL-файл не найден в sql/.")
        return 1

    if apply_sql or (not yes and _confirm("Применить SQL-миграции?", default=True)):
        from src.common.constants import database as db_cfg  # noqa: PLC0415

        for sql_file in pending_files:
            name = Path(sql_file).name
            try:
                result = subprocess.run(
                    [
                        "mysql",
                        f"-h{db_cfg.MYSQL_HOST}",
                        f"-P{db_cfg.MYSQL_PORT}",
                        f"-u{db_cfg.MYSQL_USER}",
                        f"-p{db_cfg.MYSQL_PASSWORD}",
                        db_cfg.MYSQL_DATABASE,
                    ],
                    check=False,
                    input=Path(sql_file).read_text(encoding="utf-8"),
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    _ok(f"Применён: {name}")
                else:
                    _warn(f"Пропущен/частичная ошибка: {name}\n       {result.stderr.strip()[:200]}")
            except FileNotFoundError:
                _warn(f"Команда 'mysql' не найдена. Примените {name} вручную.")
                break
            except Exception as exc:
                _err(f"Ошибка применения {name}: {exc}")
    else:
        _info("SQL-миграции пропущены.")

    # --- Первый backfill ---
    _step("Первичный backfill векторного индекса")
    _info(
        "Если векторный слой включён (AI_RAG_VECTOR_ENABLED=1), "
        "запустите backfill чанков и summary:"
    )
    print()
    print("    python scripts/rag_vector_backfill.py --target both --batch-size 100")
    print()

    try:
        from src.sbs_helper_telegram_bot.ai_router import settings as ai_settings  # noqa: PLC0415
        if not ai_settings.AI_RAG_VECTOR_ENABLED:
            _info("Векторный слой отключён — backfill не требуется.")
        elif not yes and _confirm("Запустить backfill сейчас?", default=False):
            _run_backfill(target="both", batch_size=100, dry_run=False)
        else:
            _info("Backfill пропущен — запустите вручную при необходимости.")
    except Exception:
        _info("Backfill пропущен.")

    print()
    _ok("Setup завершён.")
    return 0


# ---------------------------------------------------------------------------
# Команда: update docs
# ---------------------------------------------------------------------------

def cmd_update_docs(args: argparse.Namespace) -> int:
    """Синхронизировать директорию документов с RAG."""
    _header("Update RAG Documents")
    directory = getattr(args, "directory", None) or ""
    if not directory:
        _err("Укажите директорию: --directory /path/to/docs")
        return 1

    force = getattr(args, "force", False)
    daemon = getattr(args, "daemon", False)
    interval = getattr(args, "interval_seconds", 900)
    dry_run = getattr(args, "dry_run", False)
    regen = getattr(args, "regenerate_summaries", False)
    recursive = not getattr(args, "no_recursive", False)

    cmd = [
        sys.executable,
        str(_PROJECT_ROOT / "scripts" / "rag_directory_ingest.py"),
        "--directory", directory,
    ]
    if force:
        cmd.append("--force-update")
    if daemon:
        cmd += ["--daemon", "--interval-seconds", str(interval)]
    if dry_run:
        cmd.append("--dry-run")
    if regen:
        cmd.append("--regenerate-summaries")
    if not recursive:
        cmd.append("--no-recursive")

    _info(f"Директория : {directory}")
    _info(f"Force update: {'да' if force else 'нет'}")
    _info(f"Dry-run    : {'да' if dry_run else 'нет'}")
    _info(f"Daemon     : {'да' if daemon else 'нет'}")

    return _run_subprocess(cmd)


# ---------------------------------------------------------------------------
# Команда: update cert
# ---------------------------------------------------------------------------

def cmd_update_cert(args: argparse.Namespace) -> int:
    """Синхронизировать вопросы аттестации в RAG."""
    _header("Update Certification Q/A")
    force = getattr(args, "force", False)
    upsert_vectors = getattr(args, "upsert_vectors", False)
    uploaded_by = getattr(args, "uploaded_by", 0)

    cmd = [
        sys.executable,
        str(_PROJECT_ROOT / "scripts" / "rag_certification_sync.py"),
        "--uploaded-by", str(uploaded_by),
    ]
    if upsert_vectors:
        cmd.append("--upsert-vectors")
    if force:
        cmd.append("--force-update")

    _info(f"Uploaded-by   : {uploaded_by}")
    _info(f"Force update  : {'да' if force else 'нет'}")
    _info(f"Upsert vectors: {'да' if upsert_vectors else 'нет'}")
    if not upsert_vectors:
        _warn("Флаг --upsert-vectors не передан. После sync запустите 'update vectors --target summaries'.")

    return _run_subprocess(cmd)


# ---------------------------------------------------------------------------
# Команда: update vectors
# ---------------------------------------------------------------------------

def cmd_update_vectors(args: argparse.Namespace) -> int:
    """Перестроить векторный индекс (чанки и/или summary)."""
    _header("Update Vector Index")
    target = getattr(args, "target", "both")
    batch_size = getattr(args, "batch_size", 100)
    dry_run = getattr(args, "dry_run", False)
    max_docs = getattr(args, "max_documents", None)

    return _run_backfill(target=target, batch_size=batch_size, dry_run=dry_run, max_documents=max_docs)


# ---------------------------------------------------------------------------
# Команда: update all
# ---------------------------------------------------------------------------

def cmd_update_all(args: argparse.Namespace) -> int:
    """Полный update: docs + certification + vectors."""
    _header("Full RAG Update")
    overall_rc = 0

    # 1. Documents directory
    directory = getattr(args, "directory", None) or ""
    if directory:
        _step("1/3  Синхронизация директории документов")
        rc = cmd_update_docs(args)
        if rc != 0:
            _warn("Синхронизация документов завершилась с ошибкой. Продолжаю...")
            overall_rc = rc
    else:
        _info("Директория не указана — синхронизация документов пропущена.")

    # 2. Certification questions
    _step("2/3  Синхронизация вопросов аттестации")
    # Force + upsert_vectors through shared args
    cert_namespace = argparse.Namespace(
        force=getattr(args, "force", False),
        upsert_vectors=True,
        uploaded_by=getattr(args, "uploaded_by", 0),
    )
    rc = cmd_update_cert(cert_namespace)
    if rc != 0:
        _warn("Синхронизация аттестации завершилась с ошибкой. Продолжаю...")
        overall_rc = rc

    # 3. Vector backfill (summaries only — chunks are upserted inline when upsert_vectors=True)
    _step("3/3  Backfill summary-векторов")
    batch_size = getattr(args, "batch_size", 100)
    rc = _run_backfill(target="summaries", batch_size=batch_size, dry_run=False)
    if rc != 0:
        overall_rc = rc

    if overall_rc == 0:
        _ok("Полный update завершён успешно.")
    else:
        _warn("Полный update завершён с ошибками (см. выше).")

    return overall_rc


# ---------------------------------------------------------------------------
# Команда: sync-remote
# ---------------------------------------------------------------------------

def cmd_sync_remote(args: argparse.Namespace) -> int:
    """Синхронизировать Qdrant коллекцию remote → local."""
    _header("Qdrant Remote → Local Sync")
    dry_run = getattr(args, "dry_run", False)
    batch_size = getattr(args, "batch_size", 200)
    max_points = getattr(args, "max_points", None)
    delete_missing = getattr(args, "delete_missing", False)

    cmd = [
        sys.executable,
        str(_PROJECT_ROOT / "scripts" / "rag_qdrant_sync_remote_to_local.py"),
        "--batch-size", str(batch_size),
    ]
    if dry_run:
        cmd.append("--dry-run")
    if max_points:
        cmd += ["--max-points", str(max_points)]
    if delete_missing:
        cmd.append("--delete-missing")

    _info(f"Dry-run       : {'да' if dry_run else 'нет'}")
    _info(f"Batch size    : {batch_size}")
    _info(f"Delete missing: {'да' if delete_missing else 'нет'}")

    return _run_subprocess(cmd)


# ---------------------------------------------------------------------------
# Команда: wizard (интерактивный режим)
# ---------------------------------------------------------------------------

def cmd_wizard(_args: argparse.Namespace) -> int:
    """Интерактивный guided-режим управления RAG."""
    _header("RAG Operations Wizard")
    print(_c(
        textwrap.dedent("""
            Этот мастер поможет вам выполнить операции с RAG-корпусом.
            Выберите нужный пункт или нажмите Ctrl+C для выхода.
        """).strip(),
        _ANSI_DIM,
    ))

    menu = [
        ("health",                  "Проверить подключение (MySQL + Qdrant)"),
        ("status",                  "Показать статистику корпуса"),
        ("setup",                   "Первичная настройка (SQL + первый backfill)"),
        ("update_docs",             "Синхронизировать директорию документов"),
        ("update_cert",             "Синхронизировать вопросы аттестации"),
        ("update_vectors",          "Перестроить векторный индекс"),
        ("update_all",              "Полный update (docs + cert + vectors)"),
        ("sync_remote",             "Синхронизировать Qdrant remote → local"),
        ("exit",                    "Выйти"),
    ]

    while True:
        print()
        for i, (_, label) in enumerate(menu, 1):
            print(f"  {_c(str(i), _ANSI_BOLD)}.  {label}")
        print()

        choice_str = _ask("Выберите пункт (1–9)", "9")
        try:
            choice = int(choice_str) - 1
            if not (0 <= choice < len(menu)):
                raise ValueError
        except ValueError:
            _warn("Неверный выбор. Введите число от 1 до 9.")
            continue

        action = menu[choice][0]

        if action == "exit":
            print(_c("\n  До свидания!\n", _ANSI_DIM))
            return 0

        elif action == "health":
            cmd_health(argparse.Namespace())

        elif action == "status":
            cmd_status(argparse.Namespace())

        elif action == "setup":
            apply_sql = _confirm("Применить SQL-миграции?", default=True)
            cmd_setup(argparse.Namespace(apply_sql=apply_sql, yes=False))

        elif action == "update_docs":
            directory = _ask("Путь к директории документов")
            if not directory:
                _warn("Директория не указана.")
                continue
            force = _confirm("Принудительно переобновить всё (--force-update)?", default=False)
            dry_run = _confirm("Dry-run (без записи)?", default=False)
            cmd_update_docs(argparse.Namespace(
                directory=directory,
                force=force,
                daemon=False,
                interval_seconds=900,
                dry_run=dry_run,
                regenerate_summaries=False,
                no_recursive=False,
            ))

        elif action == "update_cert":
            force = _confirm("Принудительно переобновить (--force-update)?", default=False)
            upsert_vectors = _confirm("Сразу записать эмбеддинги (--upsert-vectors)?", default=True)
            cmd_update_cert(argparse.Namespace(
                force=force,
                upsert_vectors=upsert_vectors,
                uploaded_by=0,
            ))

        elif action == "update_vectors":
            target = _ask("Что перестроить? [chunks / summaries / both]", "both")
            if target not in ("chunks", "summaries", "both"):
                _warn("Допустимые значения: chunks, summaries, both")
                continue
            batch_size = int(_ask("Размер батча?", "100") or "100")
            dry_run = _confirm("Dry-run (без записи)?", default=False)
            cmd_update_vectors(argparse.Namespace(
                target=target,
                batch_size=batch_size,
                dry_run=dry_run,
                max_documents=None,
            ))

        elif action == "update_all":
            directory = _ask("Путь к директории документов (Enter — пропустить)", "")
            force = _confirm("Принудительно переобновить (--force-update)?", default=False)
            cmd_update_all(argparse.Namespace(
                directory=directory or None,
                force=force,
                upsert_vectors=True,
                uploaded_by=0,
                batch_size=100,
            ))

        elif action == "sync_remote":
            dry_run = _confirm("Dry-run?", default=True)
            batch_size = int(_ask("Batch size?", "200") or "200")
            delete_missing = _confirm("Удалять точки, отсутствующие в remote?", default=False)
            cmd_sync_remote(argparse.Namespace(
                dry_run=dry_run,
                batch_size=batch_size,
                max_points=None,
                delete_missing=delete_missing,
            ))

    return 0


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _run_subprocess(cmd: List[str]) -> int:
    """Запустить subprocess и вернуть код возврата."""
    _info(f"Команда: {' '.join(cmd)}")
    print()
    start = time.monotonic()
    try:
        result = subprocess.run(cmd, check=False)
        elapsed = time.monotonic() - start
        rc = result.returncode
        if rc == 0:
            _ok(f"Завершено за {elapsed:.1f}с.")
        else:
            _err(f"Завершено с кодом {rc} за {elapsed:.1f}с.")
        return rc
    except KeyboardInterrupt:
        print()
        _warn("Прервано пользователем.")
        return 130


def _run_backfill(
    target: str = "both",
    batch_size: int = 100,
    dry_run: bool = False,
    max_documents: Optional[int] = None,
) -> int:
    """Запустить rag_vector_backfill.py."""
    cmd = [
        sys.executable,
        str(_PROJECT_ROOT / "scripts" / "rag_vector_backfill.py"),
        "--target", target,
        "--batch-size", str(batch_size),
    ]
    if dry_run:
        cmd.append("--dry-run")
    if max_documents:
        cmd += ["--max-documents", str(max_documents)]

    _info(f"Target     : {target}")
    _info(f"Batch size : {batch_size}")
    _info(f"Dry-run    : {'да' if dry_run else 'нет'}")

    return _run_subprocess(cmd)


# ---------------------------------------------------------------------------
# Построение argparse
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag_ops",
        description="Единый CLI для управления RAG-корпусом.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Примеры:
              python scripts/rag_ops.py health
              python scripts/rag_ops.py status
              python scripts/rag_ops.py setup --apply-sql --yes
              python scripts/rag_ops.py update docs -d /path/to/docs --force
              python scripts/rag_ops.py update cert --force --upsert-vectors
              python scripts/rag_ops.py update vectors --target both
              python scripts/rag_ops.py update all -d /path/to/docs --force
              python scripts/rag_ops.py sync-remote --dry-run
              python scripts/rag_ops.py wizard
        """),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # health
    subparsers.add_parser("health", help="Проверить подключение MySQL + Qdrant")

    # status
    subparsers.add_parser("status", help="Показать статистику RAG-корпуса")

    # setup
    p_setup = subparsers.add_parser("setup", help="Первичная настройка (SQL + backfill)")
    p_setup.add_argument("--apply-sql", action="store_true", help="Применить SQL-миграции без вопросов")
    p_setup.add_argument("--yes", "-y", action="store_true", help="Подтверждать все шаги автоматически")

    # update (docs / cert / vectors / all)
    p_update = subparsers.add_parser("update", help="Обновить часть RAG-корпуса")
    update_sub = p_update.add_subparsers(dest="update_target", required=True)

    # update docs
    p_docs = update_sub.add_parser("docs", help="Синхронизировать директорию документов")
    p_docs.add_argument("-d", "--directory", required=True, metavar="PATH", help="Путь к директории")
    p_docs.add_argument("--force", action="store_true", help="Принудительно переобновить (даже при том же hash)")
    p_docs.add_argument("--daemon", action="store_true", help="Запустить в режиме daemon (бесконечная синхронизация)")
    p_docs.add_argument("--interval-seconds", type=int, default=900, metavar="N", help="Интервал daemon-цикла (сек, по умолчанию 900)")
    p_docs.add_argument("--dry-run", action="store_true", help="Показать изменения без записи в БД")
    p_docs.add_argument("--regenerate-summaries", action="store_true", help="Перегенерировать summary для всех документов")
    p_docs.add_argument("--no-recursive", action="store_true", help="Не сканировать поддиректории рекурсивно")

    # update cert
    p_cert = update_sub.add_parser("cert", help="Синхронизировать вопросы аттестации")
    p_cert.add_argument("--force", action="store_true", help="Переобновить даже неизменённые документы")
    p_cert.add_argument("--upsert-vectors", action="store_true", help="Сразу записать эмбеддинги в Qdrant")
    p_cert.add_argument("--uploaded-by", type=int, default=0, metavar="USER_ID", help="ID пользователя для аудита (по умолчанию: 0)")

    # update vectors
    p_vec = update_sub.add_parser("vectors", help="Перестроить векторный индекс")
    p_vec.add_argument("--target", choices=["chunks", "summaries", "both"], default="both", help="Что перестраивать")
    p_vec.add_argument("--batch-size", type=int, default=100, metavar="N", help="Документов за один батч")
    p_vec.add_argument("--dry-run", action="store_true", help="Только подсчитать, без записи в индекс")
    p_vec.add_argument("--max-documents", type=int, default=None, metavar="N", help="Ограничить число документов")

    # update all
    p_all = update_sub.add_parser("all", help="Полный update (docs + cert + vectors)")
    p_all.add_argument("-d", "--directory", default=None, metavar="PATH", help="Директория документов (опcionально)")
    p_all.add_argument("--force", action="store_true", help="Принудительно переобновить всё")
    p_all.add_argument("--uploaded-by", type=int, default=0, metavar="USER_ID")
    p_all.add_argument("--batch-size", type=int, default=100, metavar="N")
    p_all.add_argument("--no-recursive", action="store_true")

    # sync-remote
    p_sync = subparsers.add_parser("sync-remote", help="Qdrant remote → local sync")
    p_sync.add_argument("--dry-run", action="store_true", help="Без записи/удаления")
    p_sync.add_argument("--batch-size", type=int, default=200, metavar="N")
    p_sync.add_argument("--max-points", type=int, default=None, metavar="N")
    p_sync.add_argument("--delete-missing", action="store_true", help="Удалять точки, отсутствующие в remote")

    # wizard
    subparsers.add_parser("wizard", help="Интерактивный guided-режим")

    return parser


# ---------------------------------------------------------------------------
# Главная точка входа
# ---------------------------------------------------------------------------

_COMMAND_MAP = {
    "health": cmd_health,
    "status": cmd_status,
    "setup": cmd_setup,
    "sync-remote": cmd_sync_remote,
    "wizard": cmd_wizard,
}

_UPDATE_TARGET_MAP = {
    "docs": cmd_update_docs,
    "cert": cmd_update_cert,
    "vectors": cmd_update_vectors,
    "all": cmd_update_all,
}


def main() -> None:
    """Точка входа."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "update":
        handler = _UPDATE_TARGET_MAP.get(args.update_target)
        if handler is None:
            parser.error(f"Неизвестный update target: {args.update_target!r}")
        sys.exit(handler(args))

    handler = _COMMAND_MAP.get(args.command)
    if handler is None:
        parser.error(f"Неизвестная команда: {args.command!r}")

    sys.exit(handler(args))


if __name__ == "__main__":
    main()
