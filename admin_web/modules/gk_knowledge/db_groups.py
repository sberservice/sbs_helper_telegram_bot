"""Слой работы с БД: список Telegram-групп с детальной статистикой."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.common import database

logger = logging.getLogger(__name__)


def get_groups_list() -> List[Dict[str, Any]]:
    """Получить список собранных групп с расширенной статистикой."""
    query = """
        SELECT
            m.group_id,
            MAX(m.group_title) AS group_title,
            COUNT(*) AS message_count,
            COUNT(DISTINCT m.sender_id) AS sender_count,
            SUM(CASE WHEN m.is_question = 1 THEN 1 ELSE 0 END) AS question_count,
            SUM(CASE WHEN m.has_image = 1 THEN 1 ELSE 0 END) AS image_count,
            MIN(m.message_date) AS first_message_ts,
            MAX(m.message_date) AS last_message_ts,
            COALESCE(qa.pair_count, 0) AS pair_count,
            COALESCE(qa.validated_count, 0) AS validated_count
        FROM gk_messages m
        LEFT JOIN (
            SELECT
                group_id,
                COUNT(*) AS pair_count,
                SUM(CASE WHEN expert_status IS NOT NULL THEN 1 ELSE 0 END) AS validated_count
            FROM gk_qa_pairs
            GROUP BY group_id
        ) qa ON qa.group_id = m.group_id
        GROUP BY m.group_id
        ORDER BY message_count DESC
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query)
                rows = cursor.fetchall() or []
                result = []
                for r in rows:
                    msg_total = r["message_count"] or 0
                    q_count = r["question_count"] or 0
                    result.append({
                        "group_id": r["group_id"],
                        "group_title": r["group_title"],
                        "message_count": msg_total,
                        "sender_count": r["sender_count"] or 0,
                        "question_count": q_count,
                        "question_pct": round(q_count / msg_total * 100, 1) if msg_total > 0 else 0,
                        "image_count": r["image_count"] or 0,
                        "first_message_ts": r["first_message_ts"],
                        "last_message_ts": r["last_message_ts"],
                        "pair_count": r["pair_count"],
                        "validated_count": r["validated_count"],
                    })
                return result

    except Exception as exc:
        logger.error("Ошибка получения списка GK-групп: %s", exc, exc_info=True)
        return []


def get_group_detail_stats(group_id: int) -> Optional[Dict[str, Any]]:
    """Получить детальную статистику по конкретной группе."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        group_id,
                        MAX(group_title) AS group_title,
                        COUNT(*) AS message_count,
                        COUNT(DISTINCT sender_id) AS sender_count,
                        SUM(CASE WHEN is_question = 1 THEN 1 ELSE 0 END) AS question_count,
                        SUM(CASE WHEN has_image = 1 THEN 1 ELSE 0 END) AS image_count,
                        SUM(CASE WHEN processed = 0 THEN 1 ELSE 0 END) AS unprocessed_count,
                        MIN(message_date) AS first_message_ts,
                        MAX(message_date) AS last_message_ts
                    FROM gk_messages
                    WHERE group_id = %s
                    GROUP BY group_id
                    """,
                    (group_id,),
                )
                msg_row = cursor.fetchone()
                if not msg_row:
                    return None

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total_pairs,
                        SUM(CASE WHEN extraction_type = 'thread_reply' THEN 1 ELSE 0 END) AS thread_pairs,
                        SUM(CASE WHEN extraction_type = 'llm_inferred' THEN 1 ELSE 0 END) AS llm_pairs,
                        SUM(CASE WHEN expert_status = 'approved' THEN 1 ELSE 0 END) AS expert_approved,
                        SUM(CASE WHEN expert_status = 'rejected' THEN 1 ELSE 0 END) AS expert_rejected,
                        SUM(CASE WHEN expert_status IS NULL THEN 1 ELSE 0 END) AS expert_pending,
                        AVG(confidence) AS avg_confidence
                    FROM gk_qa_pairs
                    WHERE group_id = %s
                    """,
                    (group_id,),
                )
                qa_row = cursor.fetchone() or {}

                msg_total = msg_row["message_count"] or 0
                q_count = msg_row["question_count"] or 0

                return {
                    "group_id": msg_row["group_id"],
                    "group_title": msg_row["group_title"],
                    "message_count": msg_total,
                    "sender_count": msg_row["sender_count"] or 0,
                    "question_count": q_count,
                    "question_pct": round(q_count / msg_total * 100, 1) if msg_total > 0 else 0,
                    "image_count": msg_row["image_count"] or 0,
                    "unprocessed_count": msg_row["unprocessed_count"] or 0,
                    "first_message_ts": msg_row["first_message_ts"],
                    "last_message_ts": msg_row["last_message_ts"],
                    "qa_pairs": {
                        "total": qa_row.get("total_pairs", 0) or 0,
                        "thread_reply": qa_row.get("thread_pairs", 0) or 0,
                        "llm_inferred": qa_row.get("llm_pairs", 0) or 0,
                        "expert_approved": qa_row.get("expert_approved", 0) or 0,
                        "expert_rejected": qa_row.get("expert_rejected", 0) or 0,
                        "expert_pending": qa_row.get("expert_pending", 0) or 0,
                        "avg_confidence": round(float(qa_row.get("avg_confidence") or 0), 3),
                    },
                }

    except Exception as exc:
        logger.error("Ошибка получения статистики группы %s: %s", group_id, exc, exc_info=True)
        return None
