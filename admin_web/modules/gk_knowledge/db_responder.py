"""Слой работы с БД: лог автоответчика Group Knowledge."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)


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
                        rl.question_text, rl.answer_text,
                        rl.qa_pair_id, rl.confidence,
                        rl.dry_run, rl.responded_at
                    FROM gk_responder_log rl
                    {where_clause}
                    ORDER BY {sort_field} {sort_dir}
                    LIMIT %s OFFSET %s
                    """,
                    (*params, page_size, offset),
                )
                rows = cursor.fetchall() or []
                return rows, total

    except Exception as exc:
        logger.error("Ошибка получения лога автоответчика: %s", exc, exc_info=True)
        return [], 0


def get_responder_summary(group_id: Optional[int] = None) -> Dict[str, Any]:
    """Получить сводную статистику автоответчика."""
    cond = "WHERE group_id = %s" if group_id else ""
    params = (group_id,) if group_id else ()

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
                    params,
                )
                row = cursor.fetchone() or {}
                return {
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
