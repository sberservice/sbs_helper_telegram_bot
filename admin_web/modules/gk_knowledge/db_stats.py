"""Слой работы с БД: агрегированная статистика Group Knowledge.

Запросы к gk_messages, gk_qa_pairs, gk_responder_log, gk_image_queue,
gk_expert_validations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.common import database

logger = logging.getLogger(__name__)


def get_overview_stats(group_id: Optional[int] = None) -> Dict[str, Any]:
    """Получить обзорную статистику GK: сообщения, Q&A-пары, респондер, изображения."""
    cond_msg = "WHERE group_id = %s" if group_id else ""
    cond_qa = "WHERE group_id = %s" if group_id else ""
    cond_resp = "WHERE group_id = %s" if group_id else ""

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # --- Сообщения ---
                params_msg = (group_id,) if group_id else ()
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total_messages,
                        SUM(CASE WHEN is_question = 1 THEN 1 ELSE 0 END) AS question_messages,
                        SUM(CASE WHEN has_image = 1 THEN 1 ELSE 0 END) AS image_messages,
                        SUM(CASE WHEN processed = 0 THEN 1 ELSE 0 END) AS unprocessed_messages,
                        COUNT(DISTINCT sender_id) AS unique_senders,
                        COUNT(DISTINCT group_id) AS group_count,
                        MIN(message_date) AS first_message_ts,
                        MAX(message_date) AS last_message_ts
                    FROM gk_messages
                    {cond_msg}
                    """,
                    params_msg,
                )
                msg_row = cursor.fetchone() or {}

                # --- Q&A-пары ---
                params_qa = (group_id,) if group_id else ()
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total_qa_pairs,
                        SUM(CASE WHEN extraction_type = 'thread_reply' THEN 1 ELSE 0 END) AS thread_reply_pairs,
                        SUM(CASE WHEN extraction_type = 'llm_inferred' THEN 1 ELSE 0 END) AS llm_inferred_pairs,
                        SUM(CASE WHEN approved = 1 THEN 1 ELSE 0 END) AS approved_pairs,
                        SUM(CASE WHEN vector_indexed = 1 THEN 1 ELSE 0 END) AS vector_indexed_pairs,
                        SUM(CASE WHEN expert_status = 'approved' THEN 1 ELSE 0 END) AS expert_approved_pairs,
                        SUM(CASE WHEN expert_status = 'rejected' THEN 1 ELSE 0 END) AS expert_rejected_pairs,
                        SUM(CASE WHEN expert_status IS NULL THEN 1 ELSE 0 END) AS expert_unvalidated_pairs,
                        AVG(confidence) AS avg_confidence
                    FROM gk_qa_pairs
                    {cond_qa}
                    """,
                    params_qa,
                )
                qa_row = cursor.fetchone() or {}

                # --- Автоответчик ---
                params_resp = (group_id,) if group_id else ()
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total_responses,
                        SUM(CASE WHEN dry_run = 0 THEN 1 ELSE 0 END) AS live_responses,
                        SUM(CASE WHEN dry_run = 1 THEN 1 ELSE 0 END) AS dry_run_responses,
                        AVG(confidence) AS avg_response_confidence
                    FROM gk_responder_log
                    {cond_resp}
                    """,
                    params_resp,
                )
                resp_row = cursor.fetchone() or {}

                # --- Очередь изображений (без группового фильтра) ---
                cursor.execute("""
                    SELECT
                        COUNT(*) AS total_images,
                        SUM(CASE WHEN status = 0 THEN 1 ELSE 0 END) AS pending_images,
                        SUM(CASE WHEN status = 1 THEN 1 ELSE 0 END) AS processing_images,
                        SUM(CASE WHEN status = 2 THEN 1 ELSE 0 END) AS done_images,
                        SUM(CASE WHEN status = 3 THEN 1 ELSE 0 END) AS error_images
                    FROM gk_image_queue
                """)
                img_row = cursor.fetchone() or {}

                return {
                    "messages": {
                        "total": msg_row.get("total_messages", 0) or 0,
                        "questions": msg_row.get("question_messages", 0) or 0,
                        "with_images": msg_row.get("image_messages", 0) or 0,
                        "unprocessed": msg_row.get("unprocessed_messages", 0) or 0,
                        "unique_senders": msg_row.get("unique_senders", 0) or 0,
                        "group_count": msg_row.get("group_count", 0) or 0,
                        "first_message_ts": msg_row.get("first_message_ts"),
                        "last_message_ts": msg_row.get("last_message_ts"),
                    },
                    "qa_pairs": {
                        "total": qa_row.get("total_qa_pairs", 0) or 0,
                        "thread_reply": qa_row.get("thread_reply_pairs", 0) or 0,
                        "llm_inferred": qa_row.get("llm_inferred_pairs", 0) or 0,
                        "approved": qa_row.get("approved_pairs", 0) or 0,
                        "vector_indexed": qa_row.get("vector_indexed_pairs", 0) or 0,
                        "expert_approved": qa_row.get("expert_approved_pairs", 0) or 0,
                        "expert_rejected": qa_row.get("expert_rejected_pairs", 0) or 0,
                        "expert_unvalidated": qa_row.get("expert_unvalidated_pairs", 0) or 0,
                        "avg_confidence": round(float(qa_row.get("avg_confidence") or 0), 3),
                    },
                    "responder": {
                        "total": resp_row.get("total_responses", 0) or 0,
                        "live": resp_row.get("live_responses", 0) or 0,
                        "dry_run": resp_row.get("dry_run_responses", 0) or 0,
                        "avg_confidence": round(float(resp_row.get("avg_response_confidence") or 0), 3),
                    },
                    "images": {
                        "total": img_row.get("total_images", 0) or 0,
                        "pending": img_row.get("pending_images", 0) or 0,
                        "processing": img_row.get("processing_images", 0) or 0,
                        "done": img_row.get("done_images", 0) or 0,
                        "error": img_row.get("error_images", 0) or 0,
                    },
                }

    except Exception as exc:
        logger.error("Ошибка получения обзорной статистики GK: %s", exc, exc_info=True)
        return {
            "messages": {},
            "qa_pairs": {},
            "responder": {},
            "images": {},
        }


def get_timeline_stats(
    group_id: Optional[int] = None,
    days: int = 30,
) -> Dict[str, List[Dict[str, Any]]]:
    """Получить временные ряды: сообщения и Q&A-пары по дням."""
    cond_msg = "AND group_id = %s" if group_id else ""
    cond_qa = "AND group_id = %s" if group_id else ""

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Сообщения по дням
                params_msg: list = [days]
                if group_id:
                    params_msg.append(group_id)
                cursor.execute(
                    f"""
                    SELECT
                        DATE(FROM_UNIXTIME(message_date)) AS day,
                        COUNT(*) AS message_count,
                        SUM(CASE WHEN is_question = 1 THEN 1 ELSE 0 END) AS question_count
                    FROM gk_messages
                    WHERE message_date >= UNIX_TIMESTAMP(DATE_SUB(CURDATE(), INTERVAL %s DAY))
                    {cond_msg}
                    GROUP BY day
                    ORDER BY day
                    """,
                    tuple(params_msg),
                )
                messages_timeline = []
                for row in cursor.fetchall() or []:
                    messages_timeline.append({
                        "day": str(row["day"]),
                        "message_count": row["message_count"],
                        "question_count": row["question_count"],
                    })

                # Q&A-пары по дням
                params_qa: list = [days]
                if group_id:
                    params_qa.append(group_id)
                cursor.execute(
                    f"""
                    SELECT
                        DATE(FROM_UNIXTIME(created_at)) AS day,
                        COUNT(*) AS pair_count,
                        SUM(CASE WHEN extraction_type = 'thread_reply' THEN 1 ELSE 0 END) AS thread_count,
                        SUM(CASE WHEN extraction_type = 'llm_inferred' THEN 1 ELSE 0 END) AS llm_count
                    FROM gk_qa_pairs
                    WHERE created_at >= UNIX_TIMESTAMP(DATE_SUB(CURDATE(), INTERVAL %s DAY))
                    {cond_qa}
                    GROUP BY day
                    ORDER BY day
                    """,
                    tuple(params_qa),
                )
                qa_timeline = []
                for row in cursor.fetchall() or []:
                    qa_timeline.append({
                        "day": str(row["day"]),
                        "pair_count": row["pair_count"],
                        "thread_count": row["thread_count"],
                        "llm_count": row["llm_count"],
                    })

                return {
                    "messages": messages_timeline,
                    "qa_pairs": qa_timeline,
                }

    except Exception as exc:
        logger.error("Ошибка получения временных рядов GK: %s", exc, exc_info=True)
        return {"messages": [], "qa_pairs": []}


def get_confidence_distribution(group_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Получить распределение Q&A-пар по диапазонам уверенности."""
    cond = "WHERE group_id = %s" if group_id else ""
    params = (group_id,) if group_id else ()

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        CASE
                            WHEN confidence >= 0.9 THEN '0.9-1.0'
                            WHEN confidence >= 0.8 THEN '0.8-0.9'
                            WHEN confidence >= 0.7 THEN '0.7-0.8'
                            WHEN confidence >= 0.6 THEN '0.6-0.7'
                            WHEN confidence >= 0.5 THEN '0.5-0.6'
                            ELSE '< 0.5'
                        END AS confidence_range,
                        COUNT(*) AS count
                    FROM gk_qa_pairs
                    {cond}
                    GROUP BY confidence_range
                    ORDER BY confidence_range DESC
                    """,
                    params,
                )
                return cursor.fetchall() or []

    except Exception as exc:
        logger.error("Ошибка получения распределения уверенности: %s", exc, exc_info=True)
        return []
