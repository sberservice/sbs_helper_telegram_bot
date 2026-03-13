"""Слой работы с БД: лог автоответчика Group Knowledge."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)

_GK_GROUPS_JSON = Path(__file__).resolve().parents[3] / "config" / "gk_groups.json"
_RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN: Optional[bool] = None
_RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN: Optional[bool] = None


def _responder_log_has_llm_request_payload_column() -> bool:
    """Проверить наличие колонки llm_request_payload в gk_responder_log."""
    global _RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN

    if _RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN is not None:
        return _RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT 1
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'gk_responder_log'
                      AND COLUMN_NAME = 'llm_request_payload'
                    LIMIT 1
                    """
                )
                _RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN = cursor.fetchone() is not None
    except Exception as exc:
        logger.warning(
            "Не удалось проверить колонку llm_request_payload в gk_responder_log: %s",
            exc,
        )
        _RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN = False

    return _RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN


def _responder_log_has_question_message_date_column() -> bool:
    """Проверить наличие колонки question_message_date в gk_responder_log."""
    global _RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN

    if _RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN is not None:
        return _RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT 1
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'gk_responder_log'
                      AND COLUMN_NAME = 'question_message_date'
                    LIMIT 1
                    """
                )
                _RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN = cursor.fetchone() is not None
    except Exception as exc:
        logger.warning(
            "Не удалось проверить колонку question_message_date в gk_responder_log: %s",
            exc,
        )
        _RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN = False

    return _RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN


def _load_group_titles() -> Dict[int, str]:
    """Загрузить маппинг group_id → title из config/gk_groups.json."""
    titles: Dict[int, str] = {0: "Глобальные (legacy)"}
    try:
        if _GK_GROUPS_JSON.exists():
            data = json.loads(_GK_GROUPS_JSON.read_text(encoding="utf-8"))
            for g in data.get("groups", []):
                gid = g.get("id")
                gtitle = g.get("title")
                if gid is not None and gtitle:
                    titles[int(gid)] = gtitle
    except Exception as exc:
        logger.warning("Не удалось загрузить gk_groups.json: %s", exc)
    return titles


def get_responder_log(
    *,
    page: int = 1,
    page_size: int = 20,
    group_id: Optional[int] = None,
    dry_run: Optional[bool] = None,
    min_confidence: Optional[float] = None,
    sort_by: str = "responded_at",
    sort_order: str = "desc",
) -> Tuple[List[Dict[str, Any]], int]:
    """Получить лог автоответчика с фильтрацией и пагинацией."""
    conditions: List[str] = []
    params: List[Any] = []

    if group_id is not None:
        conditions.append("rl.group_id = %s")
        params.append(group_id)

    if dry_run is not None:
        conditions.append("rl.dry_run = %s")
        params.append(1 if dry_run else 0)

    if min_confidence is not None:
        conditions.append("rl.confidence >= %s")
        params.append(min_confidence)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    allowed_sort = {
        "responded_at": "rl.responded_at",
        "confidence": "rl.confidence",
        "id": "rl.id",
    }
    sort_field = allowed_sort.get(sort_by, "rl.responded_at")
    sort_dir = "ASC" if sort_order.lower() == "asc" else "DESC"

    offset = (page - 1) * page_size
    llm_request_payload_field = (
        "rl.llm_request_payload"
        if _responder_log_has_llm_request_payload_column()
        else "NULL AS llm_request_payload"
    )
    question_message_date_field = (
        "rl.question_message_date"
        if _responder_log_has_question_message_date_column()
        else "NULL AS question_message_date"
    )

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM gk_responder_log rl {where_clause}",
                    tuple(params),
                )
                total = (cursor.fetchone() or {}).get("total", 0)

                cursor.execute(
                    f"""
                    SELECT
                        rl.id, rl.group_id, rl.question_message_id,
                        {question_message_date_field},
                        rl.question_text, rl.answer_text,
                        {llm_request_payload_field},
                        rl.qa_pair_id AS matched_qa_pair_id,
                        rl.confidence,
                        rl.dry_run, rl.responded_at
                    FROM gk_responder_log rl
                    {where_clause}
                    ORDER BY {sort_field} {sort_dir}
                    LIMIT %s OFFSET %s
                    """,
                    (*params, page_size, offset),
                )
                rows = cursor.fetchall() or []

                # Разрешить названия групп из config без JOIN к gk_messages
                titles = _load_group_titles()
                for row in rows:
                    row["group_title"] = titles.get(row["group_id"], str(row["group_id"]))

                return rows, total

    except Exception as exc:
        logger.error("Ошибка получения лога автоответчика: %s", exc, exc_info=True)
        return [], 0


def get_responder_summary(
    group_id: Optional[int] = None,
    date_from_ts: Optional[int] = None,
    date_to_ts: Optional[int] = None,
) -> Dict[str, Any]:
    """Получить сводную статистику автоответчика."""
    conditions: List[str] = []
    params: List[Any] = []

    if group_id is not None:
        conditions.append("group_id = %s")
        params.append(group_id)

    if date_from_ts is not None:
        conditions.append("responded_at >= %s")
        params.append(date_from_ts)

    if date_to_ts is not None:
        conditions.append("responded_at <= %s")
        params.append(date_to_ts)

    cond = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN dry_run = 0 THEN 1 ELSE 0 END) AS live_count,
                        SUM(CASE WHEN dry_run = 1 THEN 1 ELSE 0 END) AS dry_run_count,
                        AVG(confidence) AS avg_confidence,
                        MIN(responded_at) AS first_response_ts,
                        MAX(responded_at) AS last_response_ts
                    FROM gk_responder_log
                    {cond}
                    """,
                    tuple(params),
                )
                row = cursor.fetchone() or {}
                return {
                    "total_entries": row.get("total", 0) or 0,
                    "total": row.get("total", 0) or 0,
                    "live_count": row.get("live_count", 0) or 0,
                    "dry_run_count": row.get("dry_run_count", 0) or 0,
                    "avg_confidence": round(float(row.get("avg_confidence") or 0), 3),
                    "first_response_ts": row.get("first_response_ts"),
                    "last_response_ts": row.get("last_response_ts"),
                }

    except Exception as exc:
        logger.error("Ошибка получения сводки автоответчика: %s", exc, exc_info=True)
        return {"total": 0, "live_count": 0, "dry_run_count": 0, "avg_confidence": 0}
