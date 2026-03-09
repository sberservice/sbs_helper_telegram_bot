"""Слой работы с БД для экспертной валидации Q&A-пар.

Запросы к gk_qa_pairs, gk_messages, gk_expert_validations.
Включает реконструкцию цепочки сообщений для визуализации.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Q&A-пары: получение для валидации
# ---------------------------------------------------------------------------


def get_qa_pairs_for_validation(
    *,
    page: int = 1,
    page_size: int = 20,
    group_id: Optional[int] = None,
    extraction_type: Optional[str] = None,
    question_text: Optional[str] = None,
    expert_status: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    review_low_confidence_first: bool = False,
    expert_telegram_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Получить Q&A-пары для экспертной валидации с фильтрами и пагинацией.

    Args:
        page: Номер страницы (1-based).
        page_size: Размер страницы.
        group_id: Фильтр по группе.
        extraction_type: Фильтр по типу извлечения.
        question_text: Поиск подстроки в тексте вопроса.
        expert_status: Фильтр по статусу экспертной валидации (None/approved/rejected/unvalidated).
        min_confidence: Минимальная уверенность LLM.
        max_confidence: Максимальная уверенность LLM.
        sort_by: Поле для сортировки.
        sort_order: Направление сортировки.
        review_low_confidence_first: Режим проверки, где сначала
            показываются пары с низкой уверенностью.
        expert_telegram_id: Telegram ID эксперта (для получения его вердикта).

    Returns:
        Кортеж (список пар, общее количество).
    """
    conditions: List[str] = []
    params: List[Any] = []

    if group_id is not None:
        conditions.append("qp.group_id = %s")
        params.append(group_id)

    if extraction_type:
        conditions.append("qp.extraction_type = %s")
        params.append(extraction_type)

    if question_text:
        normalized_question_text = question_text.strip()
        if normalized_question_text:
            escaped_question_text = (
                normalized_question_text
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append("qp.question_text LIKE %s ESCAPE '\\\\'")
            params.append(f"%{escaped_question_text}%")

    if expert_status == "unvalidated":
        conditions.append("qp.expert_status IS NULL")
    elif expert_status in ("approved", "rejected"):
        conditions.append("qp.expert_status = %s")
        params.append(expert_status)

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
    }
    sort_field = allowed_sort_fields.get(sort_by, "qp.created_at")
    sort_dir = "ASC" if sort_order.lower() == "asc" else "DESC"
    if review_low_confidence_first:
        order_clause = "ORDER BY qp.confidence ASC, qp.created_at DESC, qp.id DESC"
    else:
        order_clause = f"ORDER BY {sort_field} {sort_dir}"

    offset = (page - 1) * page_size

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Общее количество
                count_query = f"""
                    SELECT COUNT(*) AS total
                    FROM gk_qa_pairs qp
                    {where_clause}
                """
                cursor.execute(count_query, tuple(params))
                total = cursor.fetchone()["total"]

                # Данные с вердиктом эксперта (если указан)
                expert_join = ""
                expert_select = ", NULL AS existing_verdict, NULL AS existing_comment"
                if expert_telegram_id:
                    expert_join = """
                        LEFT JOIN gk_expert_validations ev
                            ON ev.qa_pair_id = qp.id
                            AND ev.expert_telegram_id = %s
                    """
                    expert_select = ", ev.verdict AS existing_verdict, ev.comment AS existing_comment"

                data_query = f"""
                    SELECT
                        qp.id, qp.question_text, qp.answer_text,
                        qp.question_message_id, qp.answer_message_id,
                        qp.group_id, qp.extraction_type, qp.confidence,
                        qp.llm_model_used, qp.created_at, qp.approved,
                        qp.vector_indexed, qp.expert_status, qp.expert_validated_at
                        {expert_select}
                    FROM gk_qa_pairs qp
                    {expert_join}
                    {where_clause}
                    {order_clause}
                    LIMIT %s OFFSET %s
                """
                query_params = list(params)
                if expert_telegram_id:
                    # expert_join параметр вставляется перед where-параметрами
                    query_params = [expert_telegram_id] + query_params
                query_params.extend([page_size, offset])

                cursor.execute(data_query, tuple(query_params))
                rows = cursor.fetchall() or []

                return rows, total

    except Exception as exc:
        logger.error("Ошибка получения Q&A-пар для валидации: %s", exc, exc_info=True)
        return [], 0


def get_qa_pair_detail(pair_id: int) -> Optional[Dict[str, Any]]:
    """Получить детальные данные Q&A-пары по ID."""
    query = """
        SELECT
            qp.id, qp.question_text, qp.answer_text,
            qp.question_message_id, qp.answer_message_id,
            qp.group_id, qp.extraction_type, qp.confidence,
            qp.llm_model_used, qp.created_at, qp.approved,
            qp.vector_indexed, qp.expert_status, qp.expert_validated_at
        FROM gk_qa_pairs qp
        WHERE qp.id = %s
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (pair_id,))
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения Q&A-пары %d: %s", pair_id, exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Реконструкция цепочки сообщений
# ---------------------------------------------------------------------------


def get_chain_messages(pair_id: int) -> List[Dict[str, Any]]:
    """
    Реконструировать цепочку сообщений, которая привела к генерации Q&A-пары.

    Алгоритм:
    1. Получить question_message (по question_message_id из gk_qa_pairs).
    2. Найти корень reply-цепочки (подниматься по reply_to_message_id).
    3. Собрать все сообщения в цепочке (reply-дерево + соседние по времени
       от тех же участников).

    Returns:
        Список сообщений в хронологическом порядке.
    """
    pair = get_qa_pair_detail(pair_id)
    if not pair:
        return []

    question_msg_id = pair.get("question_message_id")
    answer_msg_id = pair.get("answer_message_id")
    if not question_msg_id:
        return []

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получить вопросное сообщение (с fallback на telegram_message_id)
                cursor.execute(
                    "SELECT * FROM gk_messages WHERE id = %s",
                    (question_msg_id,),
                )
                question_msg = cursor.fetchone()
                if not question_msg and pair.get("group_id") is not None:
                    cursor.execute(
                        """
                        SELECT * FROM gk_messages
                        WHERE group_id = %s AND telegram_message_id = %s
                        LIMIT 1
                        """,
                        (pair.get("group_id"), question_msg_id),
                    )
                    question_msg = cursor.fetchone()
                if not question_msg:
                    return []

                group_id = question_msg["group_id"]
                question_tg_id = question_msg["telegram_message_id"]

                # Найти корень reply-цепочки
                root_tg_id = question_tg_id
                visited = set()
                current_msg = question_msg
                while current_msg and current_msg.get("reply_to_message_id"):
                    if current_msg["telegram_message_id"] in visited:
                        break
                    visited.add(current_msg["telegram_message_id"])
                    reply_to = current_msg["reply_to_message_id"]
                    cursor.execute(
                        """
                        SELECT * FROM gk_messages
                        WHERE group_id = %s AND telegram_message_id = %s
                        """,
                        (group_id, reply_to),
                    )
                    parent = cursor.fetchone()
                    if parent:
                        root_tg_id = parent["telegram_message_id"]
                        current_msg = parent
                    else:
                        break

                # Построить полное reply-дерево по всей группе (не ограничиваемся окном времени)
                chain_tg_ids = {question_tg_id, root_tg_id}
                queue = [root_tg_id]
                max_chain_nodes = 500

                while queue and len(chain_tg_ids) < max_chain_nodes:
                    parent_id = queue.pop(0)
                    cursor.execute(
                        """
                        SELECT telegram_message_id
                        FROM gk_messages
                        WHERE group_id = %s AND reply_to_message_id = %s
                        """,
                        (group_id, parent_id),
                    )
                    child_rows = cursor.fetchall() or []
                    for row in child_rows:
                        child_tg_id = row["telegram_message_id"]
                        if child_tg_id not in chain_tg_ids:
                            chain_tg_ids.add(child_tg_id)
                            queue.append(child_tg_id)

                # Добавить answer_message если известен
                answer_tg_id: Optional[int] = None
                if answer_msg_id:
                    cursor.execute(
                        "SELECT telegram_message_id FROM gk_messages WHERE id = %s",
                        (answer_msg_id,),
                    )
                    answer_row = cursor.fetchone()
                    if answer_row:
                        answer_tg_id = answer_row["telegram_message_id"]
                        chain_tg_ids.add(answer_tg_id)

                # Загрузить ядро цепочки по telegram_message_id
                placeholders = ",".join(["%s"] * len(chain_tg_ids))
                cursor.execute(
                    f"""
                    SELECT * FROM gk_messages
                    WHERE group_id = %s
                      AND telegram_message_id IN ({placeholders})
                    ORDER BY message_date, telegram_message_id
                    """,
                    (group_id, *sorted(chain_tg_ids)),
                )
                core_chain = cursor.fetchall() or []

                # Добавить соседние сообщения от участников цепочки в окне ±5 минут от вопроса
                msg_date = question_msg["message_date"]
                window = 300  # 5 минут
                cursor.execute(
                    """
                    SELECT * FROM gk_messages
                    WHERE group_id = %s
                      AND message_date BETWEEN %s AND %s
                    ORDER BY message_date, telegram_message_id
                    """,
                    (group_id, msg_date - window, msg_date + window),
                )
                nearby_messages = cursor.fetchall() or []

                participant_ids = {
                    m.get("sender_id") for m in core_chain if m.get("sender_id")
                }
                combined_by_tg_id = {
                    m["telegram_message_id"]: m for m in core_chain
                }

                for m in nearby_messages:
                    tg_id = m["telegram_message_id"]
                    if tg_id in combined_by_tg_id:
                        continue
                    if m.get("sender_id") in participant_ids:
                        combined_by_tg_id[tg_id] = m

                # На всякий случай принудительно добавляем ответ, если он найден и не попал в core_chain
                if answer_tg_id is not None and answer_tg_id not in combined_by_tg_id:
                    cursor.execute(
                        """
                        SELECT * FROM gk_messages
                        WHERE group_id = %s AND telegram_message_id = %s
                        LIMIT 1
                        """,
                        (group_id, answer_tg_id),
                    )
                    answer_full = cursor.fetchone()
                    if answer_full:
                        combined_by_tg_id[answer_tg_id] = answer_full

                # Собрать финальную цепочку
                chain = list(combined_by_tg_id.values())

                # Сортировка по времени
                chain.sort(
                    key=lambda m: (m["message_date"], m["telegram_message_id"])
                )

                return chain

    except Exception as exc:
        logger.error(
            "Ошибка реконструкции цепочки для пары %d: %s",
            pair_id, exc, exc_info=True,
        )
        return []


def get_group_title(group_id: int) -> Optional[str]:
    """Получить название группы из последнего собранного сообщения."""
    query = """
        SELECT group_title
        FROM gk_messages
        WHERE group_id = %s AND group_title IS NOT NULL AND group_title != ''
        ORDER BY message_date DESC
        LIMIT 1
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (group_id,))
                row = cursor.fetchone()
                return row["group_title"] if row else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Экспертные вердикты
# ---------------------------------------------------------------------------


def store_expert_verdict(
    qa_pair_id: int,
    expert_telegram_id: int,
    verdict: str,
    comment: Optional[str] = None,
) -> int:
    """
    Сохранить вердикт эксперта по Q&A-паре.

    Использует INSERT ... ON DUPLICATE KEY UPDATE для идемпотентности.
    Автоматически обновляет expert_status в gk_qa_pairs.

    Returns:
        ID записи валидации.
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Сохранить вердикт
                cursor.execute(
                    """
                    INSERT INTO gk_expert_validations
                        (qa_pair_id, expert_telegram_id, verdict, comment)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        verdict = VALUES(verdict),
                        comment = VALUES(comment),
                        updated_at = NOW()
                    """,
                    (qa_pair_id, expert_telegram_id, verdict, comment),
                )
                validation_id = cursor.lastrowid or 0

                # Обновить сводный статус в gk_qa_pairs
                # (используем вердикт текущего эксперта как основной)
                if verdict in ("approved", "rejected"):
                    cursor.execute(
                        """
                        UPDATE gk_qa_pairs
                        SET expert_status = %s,
                            expert_validated_at = NOW()
                        WHERE id = %s
                        """,
                        (verdict, qa_pair_id),
                    )

                logger.info(
                    "Экспертный вердикт сохранён: pair_id=%d expert=%d verdict=%s",
                    qa_pair_id, expert_telegram_id, verdict,
                )
                return validation_id

    except Exception as exc:
        logger.error(
            "Ошибка сохранения экспертного вердикта: pair_id=%d expert=%d error=%s",
            qa_pair_id, expert_telegram_id, exc, exc_info=True,
        )
        raise


def get_expert_verdict(
    qa_pair_id: int,
    expert_telegram_id: int,
) -> Optional[Dict[str, Any]]:
    """Получить существующий вердикт эксперта по паре."""
    query = """
        SELECT id, qa_pair_id, expert_telegram_id, verdict, comment,
               created_at, updated_at
        FROM gk_expert_validations
        WHERE qa_pair_id = %s AND expert_telegram_id = %s
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (qa_pair_id, expert_telegram_id))
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения вердикта: %s", exc, exc_info=True)
        return None


def get_validation_history(qa_pair_id: int) -> List[Dict[str, Any]]:
    """Получить все вердикты по Q&A-паре (от всех экспертов)."""
    query = """
        SELECT ev.id, ev.expert_telegram_id, ev.verdict, ev.comment,
               ev.created_at, ev.updated_at
        FROM gk_expert_validations ev
        WHERE ev.qa_pair_id = %s
        ORDER BY ev.updated_at DESC
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query, (qa_pair_id,))
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения истории валидации: %s", exc, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------


def get_validation_stats(
    group_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Получить статистику экспертной валидации."""
    conditions = []
    params: List[Any] = []

    if group_id is not None:
        conditions.append("group_id = %s")
        params.append(group_id)

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total_pairs,
                        SUM(CASE WHEN expert_status IS NOT NULL THEN 1 ELSE 0 END) AS validated_pairs,
                        SUM(CASE WHEN expert_status = 'approved' THEN 1 ELSE 0 END) AS approved_pairs,
                        SUM(CASE WHEN expert_status = 'rejected' THEN 1 ELSE 0 END) AS rejected_pairs,
                        SUM(CASE WHEN expert_status IS NULL THEN 1 ELSE 0 END) AS unvalidated_pairs
                    FROM gk_qa_pairs
                    {where}
                    """,
                    tuple(params),
                )
                row = cursor.fetchone()
                if not row:
                    return {
                        "total_pairs": 0,
                        "validated_pairs": 0,
                        "approved_pairs": 0,
                        "rejected_pairs": 0,
                        "skipped_pairs": 0,
                        "unvalidated_pairs": 0,
                        "approval_rate": 0.0,
                    }

                total = row["total_pairs"] or 0
                validated = row["validated_pairs"] or 0
                approved = row["approved_pairs"] or 0
                rejected = row["rejected_pairs"] or 0
                unvalidated = row["unvalidated_pairs"] or 0

                # Подсчитать skipped из отдельной таблицы
                skip_where = ""
                skip_params: List[Any] = []
                if group_id is not None:
                    skip_where = """
                        WHERE ev.qa_pair_id IN (
                            SELECT id FROM gk_qa_pairs WHERE group_id = %s
                        )
                    """
                    skip_params.append(group_id)

                cursor.execute(
                    f"""
                    SELECT COUNT(*) AS skipped
                    FROM gk_expert_validations ev
                    {skip_where}
                    AND ev.verdict = 'skipped'
                    """ if skip_where else """
                    SELECT COUNT(*) AS skipped
                    FROM gk_expert_validations ev
                    WHERE ev.verdict = 'skipped'
                    """,
                    tuple(skip_params) if skip_params else (),
                )
                skip_row = cursor.fetchone()
                skipped = skip_row["skipped"] if skip_row else 0

                approval_rate = (approved / validated * 100) if validated > 0 else 0.0

                return {
                    "total_pairs": total,
                    "validated_pairs": validated,
                    "approved_pairs": approved,
                    "rejected_pairs": rejected,
                    "skipped_pairs": skipped,
                    "unvalidated_pairs": unvalidated,
                    "approval_rate": round(approval_rate, 1),
                }

    except Exception as exc:
        logger.error("Ошибка получения статистики валидации: %s", exc, exc_info=True)
        return {
            "total_pairs": 0,
            "validated_pairs": 0,
            "approved_pairs": 0,
            "rejected_pairs": 0,
            "skipped_pairs": 0,
            "unvalidated_pairs": 0,
            "approval_rate": 0.0,
        }


def get_collected_groups() -> List[Dict[str, Any]]:
    """Получить список групп с количеством Q&A-пар."""
    query = """
        SELECT
            qp.group_id,
            MAX(gm.group_title) AS group_title,
            COUNT(*) AS pair_count,
            SUM(CASE WHEN qp.expert_status IS NOT NULL THEN 1 ELSE 0 END) AS validated_count
        FROM gk_qa_pairs qp
        LEFT JOIN gk_messages gm
            ON gm.group_id = qp.group_id
            AND gm.group_title IS NOT NULL
            AND gm.group_title != ''
        GROUP BY qp.group_id
        ORDER BY pair_count DESC
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(query)
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения списка групп: %s", exc, exc_info=True)
        return []
