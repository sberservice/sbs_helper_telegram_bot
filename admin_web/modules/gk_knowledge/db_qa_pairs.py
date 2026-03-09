"""Слой работы с БД: список Q&A-пар с фильтрацией и пагинацией.

Отдельный подмодуль для вкладки «Q&A пары» — без экспертной валидации.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)


def get_qa_pairs_list(
    *,
    page: int = 1,
    page_size: int = 20,
    group_id: Optional[int] = None,
    extraction_type: Optional[str] = None,
    search_text: Optional[str] = None,
    expert_status: Optional[str] = None,
    approved: Optional[bool] = None,
    vector_indexed: Optional[bool] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Получить список Q&A-пар с фильтрацией и пагинацией.

    Returns:
        Кортеж (строки, общее количество).
    """
    conditions: List[str] = []
    params: List[Any] = []

    if group_id is not None:
        conditions.append("qp.group_id = %s")
        params.append(group_id)

    if extraction_type:
        conditions.append("qp.extraction_type = %s")
        params.append(extraction_type)

    if search_text:
        normalized = search_text.strip()
        if normalized:
            escaped = (
                normalized
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append("(qp.question_text LIKE %s ESCAPE '\\\\' OR qp.answer_text LIKE %s ESCAPE '\\\\')")
            params.extend([f"%{escaped}%", f"%{escaped}%"])

    if expert_status == "unvalidated":
        conditions.append("qp.expert_status IS NULL")
    elif expert_status in ("approved", "rejected"):
        conditions.append("qp.expert_status = %s")
        params.append(expert_status)

    if approved is not None:
        conditions.append("qp.approved = %s")
        params.append(1 if approved else 0)

    if vector_indexed is not None:
        conditions.append("qp.vector_indexed = %s")
        params.append(1 if vector_indexed else 0)

    if min_confidence is not None:
        conditions.append("qp.confidence >= %s")
        params.append(min_confidence)

    if max_confidence is not None:
        conditions.append("qp.confidence <= %s")
        params.append(max_confidence)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    # Безопасная сортировка
    allowed_sort_fields = {
        "created_at": "qp.created_at",
        "confidence": "qp.confidence",
        "id": "qp.id",
        "group_id": "qp.group_id",
        "expert_status": "qp.expert_status",
        "extraction_type": "qp.extraction_type",
    }
    sort_field = allowed_sort_fields.get(sort_by, "qp.created_at")
    sort_dir = "ASC" if sort_order.lower() == "asc" else "DESC"

    offset = (page - 1) * page_size

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Подсчёт
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM gk_qa_pairs qp {where_clause}",
                    tuple(params),
                )
                total = (cursor.fetchone() or {}).get("total", 0)

                # Данные
                cursor.execute(
                    f"""
                    SELECT
                        qp.id, qp.question_text, qp.answer_text,
                        qp.question_message_id, qp.answer_message_id,
                        qp.group_id, qp.extraction_type, qp.confidence,
                        qp.llm_model_used, qp.created_at, qp.approved,
                        qp.vector_indexed, qp.expert_status, qp.expert_validated_at
                    FROM gk_qa_pairs qp
                    {where_clause}
                    ORDER BY {sort_field} {sort_dir}
                    LIMIT %s OFFSET %s
                    """,
                    (*params, page_size, offset),
                )
                rows = cursor.fetchall() or []
                return rows, total

    except Exception as exc:
        logger.error("Ошибка получения списка Q&A-пар: %s", exc, exc_info=True)
        return [], 0


def get_qa_pair_detail(pair_id: int) -> Optional[Dict[str, Any]]:
    """Получить детальные данные одной Q&A-пары."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        qp.id, qp.question_text, qp.answer_text,
                        qp.question_message_id, qp.answer_message_id,
                        qp.group_id, qp.extraction_type, qp.confidence,
                        qp.llm_model_used, qp.llm_request_payload,
                        qp.created_at, qp.approved,
                        qp.vector_indexed, qp.expert_status, qp.expert_validated_at
                    FROM gk_qa_pairs qp
                    WHERE qp.id = %s
                    """,
                    (pair_id,),
                )
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения детальной Q&A-пары %d: %s", pair_id, exc, exc_info=True)
        return None
