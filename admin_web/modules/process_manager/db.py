"""Слой работы с БД для модуля управления процессами.

Таблицы: process_runs (история запусков), process_desired_state (персистентное
желаемое состояние для автоматического перезапуска после рестарта системы).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.common import database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# process_runs — история запусков
# ---------------------------------------------------------------------------


def create_run_record(
    *,
    process_key: str,
    pid: int,
    flags_json: Optional[str] = None,
    preset_name: Optional[str] = None,
    started_by: Optional[int] = None,
) -> int:
    """
    Создать запись о запуске процесса.

    Returns:
        ID созданной записи.
    """
    query = """
        INSERT INTO process_runs
            (process_key, pid, flags_json, preset_name, started_by, status)
        VALUES (%s, %s, %s, %s, %s, 'running')
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (
                    process_key, pid, flags_json, preset_name, started_by,
                ))
                return cursor.lastrowid or 0
    except Exception as exc:
        logger.error(
            "Ошибка создания записи process_runs: process_key=%s error=%s",
            process_key, exc, exc_info=True,
        )
        raise


def finish_run_record(
    run_id: int,
    *,
    exit_code: Optional[int] = None,
    status: str = "stopped",
    stop_reason: Optional[str] = None,
) -> None:
    """Обновить запись о завершении процесса."""
    query = """
        UPDATE process_runs
        SET stopped_at = NOW(), exit_code = %s, status = %s, stop_reason = %s
        WHERE id = %s AND stopped_at IS NULL
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (exit_code, status, stop_reason, run_id))
    except Exception as exc:
        logger.error(
            "Ошибка обновления process_runs: run_id=%d error=%s",
            run_id, exc, exc_info=True,
        )


def get_run_history(
    process_key: Optional[str] = None,
    *,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], int]:
    """
    Получить историю запусков с пагинацией.

    Returns:
        Кортеж (список записей, общее количество).
    """
    conditions = []
    params: list = []

    if process_key:
        conditions.append("process_key = %s")
        params.append(process_key)
    if status_filter:
        conditions.append("status = %s")
        params.append(status_filter)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    count_query = f"SELECT COUNT(*) AS cnt FROM process_runs {where_clause}"
    data_query = f"""
        SELECT id, process_key, pid, flags_json, preset_name,
               started_by, started_at, stopped_at, exit_code, status, stop_reason
        FROM process_runs
        {where_clause}
        ORDER BY started_at DESC
        LIMIT %s OFFSET %s
    """

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn, dictionary=True) as cursor:
                cursor.execute(count_query, params)
                row = cursor.fetchone()
                total = row["cnt"] if row else 0

                data_params = params + [page_size, (page - 1) * page_size]
                cursor.execute(data_query, data_params)
                runs = cursor.fetchall() or []

                for run in runs:
                    for ts_field in ("started_at", "stopped_at"):
                        val = run.get(ts_field)
                        if isinstance(val, datetime):
                            run[ts_field] = val.isoformat()

                return runs, total
    except Exception as exc:
        logger.error("Ошибка получения истории процессов: %s", exc, exc_info=True)
        return [], 0


def cleanup_stale_running_records() -> int:
    """
    Пометить как crashed все записи со статусом running.

    Вызывается при старте супервизора — если запись осталась running,
    значит предыдущий процесс упал без корректного завершения.

    Returns:
        Количество обновлённых записей.
    """
    query = """
        UPDATE process_runs
        SET status = 'crashed', stop_reason = 'system_restart',
            stopped_at = NOW()
        WHERE status = 'running'
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query)
                return cursor.rowcount or 0
    except Exception as exc:
        logger.error("Ошибка очистки stale записей process_runs: %s", exc, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# process_desired_state — персистентное желаемое состояние
# ---------------------------------------------------------------------------


def set_desired_state(
    process_key: str,
    *,
    should_run: bool,
    flags_json: Optional[str] = None,
    preset_name: Optional[str] = None,
    started_by: Optional[int] = None,
) -> None:
    """Сохранить желаемое состояние процесса (для восстановления после рестарта)."""
    query = """
        INSERT INTO process_desired_state
            (process_key, should_run, flags_json, preset_name, started_by)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            should_run = VALUES(should_run),
            flags_json = VALUES(flags_json),
            preset_name = VALUES(preset_name),
            started_by = VALUES(started_by),
            updated_at = CURRENT_TIMESTAMP
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (
                    process_key, should_run, flags_json, preset_name, started_by,
                ))
    except Exception as exc:
        logger.error(
            "Ошибка сохранения desired state: process_key=%s error=%s",
            process_key, exc, exc_info=True,
        )


def get_desired_states() -> List[Dict[str, Any]]:
    """Получить все процессы, которые должны быть запущены (should_run=TRUE)."""
    query = """
        SELECT process_key, flags_json, preset_name, started_by
        FROM process_desired_state
        WHERE should_run = TRUE
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn, dictionary=True) as cursor:
                cursor.execute(query)
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения desired states: %s", exc, exc_info=True)
        return []


def get_desired_state(process_key: str) -> Optional[Dict[str, Any]]:
    """Получить желаемое состояние одного процесса."""
    query = """
        SELECT process_key, should_run, flags_json, preset_name, started_by, updated_at
        FROM process_desired_state
        WHERE process_key = %s
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn, dictionary=True) as cursor:
                cursor.execute(query, (process_key,))
                row = cursor.fetchone()
                if row and isinstance(row.get("updated_at"), datetime):
                    row["updated_at"] = row["updated_at"].isoformat()
                return row
    except Exception as exc:
        logger.error(
            "Ошибка получения desired state: process_key=%s error=%s",
            process_key, exc, exc_info=True,
        )
        return None


def clear_desired_state(process_key: str) -> None:
    """Отметить процесс как не требующий запуска."""
    set_desired_state(process_key, should_run=False)
