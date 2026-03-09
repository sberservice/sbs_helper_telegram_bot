"""Слой работы с БД: очередь обработки изображений GK."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)

# Статусы в gk_image_queue
IMAGE_STATUS_LABELS = {
    0: "pending",
    1: "processing",
    2: "done",
    3: "error",
}


def get_image_queue_status() -> Dict[str, int]:
    """Получить количество изображений по статусам."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT
                        SUM(CASE WHEN status = 0 THEN 1 ELSE 0 END) AS pending,
                        SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) AS processing,
                        SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) AS done,
                        SUM(CASE WHEN status = 3 THEN 1 ELSE 0 END) AS error,
                        COUNT(*) AS total
                    FROM gk_image_queue
                """)
                row = cursor.fetchone() or {}
                return {
                    "pending": row.get("pending", 0) or 0,
                    "processing": row.get("processing", 0) or 0,
                    "done": row.get("done", 0) or 0,
                    "error": row.get("error", 0) or 0,
                    "total": row.get("total", 0) or 0,
                }

    except Exception as exc:
        logger.error("Ошибка получения статуса очереди изображений: %s", exc, exc_info=True)
        return {"pending": 0, "processing": 0, "done": 0, "error": 0, "total": 0}


def get_image_queue_list(
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[int] = None,
    sort_order: str = "desc",
) -> Tuple[List[Dict[str, Any]], int]:
    """Получить список элементов очереди с пагинацией."""
    conditions: List[str] = []
    params: List[Any] = []

    if status is not None:
        conditions.append("iq.status = %s")
        params.append(status)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sort_dir = "ASC" if sort_order.lower() == "asc" else "DESC"
    offset = (page - 1) * page_size

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM gk_image_queue iq {where_clause}",
                    tuple(params),
                )
                total = (cursor.fetchone() or {}).get("total", 0)

                cursor.execute(
                    f"""
                    SELECT
                        iq.id, iq.message_id, iq.image_path,
                        iq.status, iq.error_message,
                        iq.created_at, iq.updated_at,
                        gm.image_description,
                        gm.group_id, gm.sender_name
                    FROM gk_image_queue iq
                    LEFT JOIN gk_messages gm ON gm.id = iq.message_id
                    {where_clause}
                    ORDER BY iq.created_at {sort_dir}
                    LIMIT %s OFFSET %s
                    """,
                    (*params, page_size, offset),
                )
                rows = cursor.fetchall() or []

                result = []
                for r in rows:
                    result.append({
                        "id": r["id"],
                        "message_id": r["message_id"],
                        "image_path": r["image_path"],
                        "status": r["status"],
                        "status_label": IMAGE_STATUS_LABELS.get(r["status"], "unknown"),
                        "error_message": r["error_message"],
                        "created_at": str(r["created_at"]) if r["created_at"] else None,
                        "updated_at": str(r["updated_at"]) if r["updated_at"] else None,
                        "image_description": r.get("image_description"),
                        "group_id": r.get("group_id"),
                        "sender_name": r.get("sender_name"),
                    })

                return result, total

    except Exception as exc:
        logger.error("Ошибка получения очереди изображений: %s", exc, exc_info=True)
        return [], 0
