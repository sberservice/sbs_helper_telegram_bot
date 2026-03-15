"""Слой БД для вкладки Message Browser (Group Knowledge)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)


def _build_filters(
    *,
    group_id: Optional[int],
    sender_id: Optional[int],
    processed: Optional[bool],
    analyzed: Optional[bool],
    in_chain: Optional[bool],
    search: Optional[str],
    message_date_from: Optional[int],
    message_date_to: Optional[int],
) -> Tuple[List[str], List[Any]]:
    """Собрать SQL-условия фильтрации и параметры."""
    conditions: List[str] = []
    params: List[Any] = []

    if group_id is not None:
        conditions.append("m.group_id = %s")
        params.append(group_id)

    if sender_id is not None:
        conditions.append("m.sender_id = %s")
        params.append(sender_id)

    if processed is not None:
        conditions.append("m.processed = %s")
        params.append(1 if processed else 0)

    if message_date_from is not None:
        conditions.append("m.message_date >= %s")
        params.append(message_date_from)

    if message_date_to is not None:
        conditions.append("m.message_date <= %s")
        params.append(message_date_to)

    if search:
        conditions.append(
            "(" 
            "LOWER(COALESCE(m.message_text, '')) LIKE %s "
            "OR LOWER(COALESCE(m.caption, '')) LIKE %s "
            "OR LOWER(COALESCE(m.sender_name, '')) LIKE %s"
            ")"
        )
        like = f"%{search.strip().lower()}%"
        params.extend([like, like, like])

    chain_expr = (
        "(m.reply_to_message_id IS NOT NULL OR EXISTS ("
        "SELECT 1 FROM gk_messages c "
        "WHERE c.group_id = m.group_id AND c.reply_to_message_id = m.telegram_message_id"
        "))"
    )
    if in_chain is True:
        conditions.append(chain_expr)
    elif in_chain is False:
        conditions.append(f"NOT {chain_expr}")

    analyzed_expr = (
        "EXISTS ("
        "SELECT 1 FROM gk_qa_pairs q "
        "WHERE q.question_message_id = m.id OR q.answer_message_id = m.id"
        ")"
    )
    if analyzed is True:
        conditions.append(analyzed_expr)
    elif analyzed is False:
        conditions.append(f"NOT {analyzed_expr}")

    return conditions, params


def list_messages(
    *,
    page: int = 1,
    page_size: int = 50,
    group_id: Optional[int] = None,
    sender_id: Optional[int] = None,
    processed: Optional[bool] = None,
    analyzed: Optional[bool] = None,
    in_chain: Optional[bool] = None,
    search: Optional[str] = None,
    message_date_from: Optional[int] = None,
    message_date_to: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Получить страницу сообщений с фильтрами и total."""
    conditions, params = _build_filters(
        group_id=group_id,
        sender_id=sender_id,
        processed=processed,
        analyzed=analyzed,
        in_chain=in_chain,
        search=search,
        message_date_from=message_date_from,
        message_date_to=message_date_to,
    )
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    safe_page = max(1, int(page))
    safe_page_size = max(10, min(200, int(page_size)))
    offset = (safe_page - 1) * safe_page_size

    chain_expr = (
        "(m.reply_to_message_id IS NOT NULL OR EXISTS ("
        "SELECT 1 FROM gk_messages c "
        "WHERE c.group_id = m.group_id AND c.reply_to_message_id = m.telegram_message_id"
        "))"
    )
    analyzed_expr = (
        "EXISTS ("
        "SELECT 1 FROM gk_qa_pairs q "
        "WHERE q.question_message_id = m.id OR q.answer_message_id = m.id"
        ")"
    )

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM gk_messages m
                    {where_clause}
                    """,
                    tuple(params),
                )
                total_row = cursor.fetchone() or {}
                total = int(total_row.get("total") or 0)

                cursor.execute(
                    f"""
                    SELECT
                        m.id,
                        m.telegram_message_id,
                        m.group_id,
                        m.group_title,
                        m.sender_id,
                        m.sender_name,
                        m.message_text,
                        m.caption,
                        m.has_image,
                        m.reply_to_message_id,
                        m.message_date,
                        m.processed,
                        {chain_expr} AS is_in_chain,
                        {analyzed_expr} AS is_analyzed
                    FROM gk_messages m
                    {where_clause}
                    ORDER BY m.message_date DESC, m.id DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params + [safe_page_size, offset]),
                )
                rows = cursor.fetchall() or []

                for row in rows:
                    row["processed"] = bool(row.get("processed"))
                    row["is_in_chain"] = bool(row.get("is_in_chain"))
                    row["is_analyzed"] = bool(row.get("is_analyzed"))
                    row["has_image"] = bool(row.get("has_image"))

                return rows, total
    except Exception as exc:
        logger.error("Ошибка загрузки сообщений Message Browser: %s", exc, exc_info=True)
        return [], 0


def list_senders(
    *,
    group_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Получить список отправителей для фильтра в Message Browser."""
    conditions: List[str] = []
    params: List[Any] = []

    if group_id is not None:
        conditions.append("group_id = %s")
        params.append(group_id)

    if search:
        conditions.append("LOWER(COALESCE(sender_name, '')) LIKE %s")
        params.append(f"%{search.strip().lower()}%")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    safe_limit = max(20, min(500, int(limit)))

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        sender_id,
                        MAX(sender_name) AS sender_name,
                        COUNT(*) AS message_count
                    FROM gk_messages
                    {where_clause}
                    GROUP BY sender_id
                    ORDER BY message_count DESC, sender_id DESC
                    LIMIT %s
                    """,
                    tuple(params + [safe_limit]),
                )
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка загрузки отправителей Message Browser: %s", exc, exc_info=True)
        return []
