"""
Операции с базой данных для подсистемы Group Knowledge.

Предоставляет функции для хранения и извлечения сообщений,
Q&A-пар, очереди обработки изображений и логов автоответчика.
"""

import logging
import time
from typing import List, Optional, Dict, Any

from src.common.database import get_db_connection, get_cursor
from src.group_knowledge.models import GroupMessage, QAPair

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Сообщения (gk_messages)
# ---------------------------------------------------------------------------

def store_message(msg: GroupMessage) -> int:
    """
    Сохранить сообщение из группы в БД (upsert по group_id + telegram_message_id).

    Args:
        msg: Объект GroupMessage для сохранения.

    Returns:
        ID записи в БД.
    """
    now = int(time.time())
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_messages (
                        telegram_message_id, group_id, group_title,
                        sender_id, sender_name, message_text, caption,
                        has_image, image_path, image_description,
                        reply_to_message_id, message_date, collected_at, processed
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        group_title = VALUES(group_title),
                        sender_id = VALUES(sender_id),
                        message_text = VALUES(message_text),
                        caption = VALUES(caption),
                        has_image = VALUES(has_image),
                        image_path = VALUES(image_path),
                        image_description = VALUES(image_description),
                        reply_to_message_id = VALUES(reply_to_message_id),
                        message_date = VALUES(message_date),
                        collected_at = VALUES(collected_at),
                        sender_name = VALUES(sender_name)
                    """,
                    (
                        msg.telegram_message_id,
                        msg.group_id,
                        msg.group_title[:255] if msg.group_title else "",
                        msg.sender_id,
                        msg.sender_name[:255] if msg.sender_name else "",
                        msg.message_text or "",
                        msg.caption,
                        1 if msg.has_image else 0,
                        msg.image_path,
                        msg.image_description,
                        msg.reply_to_message_id,
                        msg.message_date,
                        now,
                        0,
                    ),
                )
                # Получить ID записи (INSERT или существующая)
                if cursor.lastrowid:
                    return cursor.lastrowid
                cursor.execute(
                    "SELECT id FROM gk_messages WHERE group_id = %s AND telegram_message_id = %s",
                    (msg.group_id, msg.telegram_message_id),
                )
                row = cursor.fetchone()
                return row["id"] if row else 0
    except Exception as exc:
        logger.error("Ошибка сохранения сообщения: %s", exc, exc_info=True)
        raise


def get_message_by_telegram_id(
    group_id: int, telegram_message_id: int
) -> Optional[GroupMessage]:
    """
    Получить сообщение по Telegram ID (для проверки дубликатов).

    Args:
        group_id: ID группы.
        telegram_message_id: ID сообщения в Telegram.

    Returns:
        GroupMessage или None, если не найдено.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT * FROM gk_messages WHERE group_id = %s AND telegram_message_id = %s",
                    (group_id, telegram_message_id),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return _row_to_message(row)
    except Exception as exc:
        logger.error("Ошибка получения сообщения: %s", exc, exc_info=True)
        return None


def get_messages_for_date(group_id: int, date_str: str) -> List[GroupMessage]:
    """
    Получить все сообщения группы за указанную дату.

    Args:
        group_id: ID группы.
        date_str: Дата в формате YYYY-MM-DD.

    Returns:
        Список сообщений, отсортированных по времени.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM gk_messages
                    WHERE group_id = %s
                      AND DATE(FROM_UNIXTIME(message_date)) = %s
                    ORDER BY message_date ASC
                    """,
                    (group_id, date_str),
                )
                rows = cursor.fetchall()
                return [_row_to_message(r) for r in rows]
    except Exception as exc:
        logger.error("Ошибка получения сообщений за дату: %s", exc, exc_info=True)
        return []


def get_unprocessed_messages(group_id: int, date_str: str) -> List[GroupMessage]:
    """
    Получить необработанные сообщения группы за указанную дату.

    Args:
        group_id: ID группы.
        date_str: Дата в формате YYYY-MM-DD.

    Returns:
        Список необработанных сообщений.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM gk_messages
                    WHERE group_id = %s
                      AND processed = 0
                      AND DATE(FROM_UNIXTIME(message_date)) = %s
                    ORDER BY message_date ASC
                    """,
                    (group_id, date_str),
                )
                rows = cursor.fetchall()
                return [_row_to_message(r) for r in rows]
    except Exception as exc:
        logger.error("Ошибка получения необработанных сообщений: %s", exc, exc_info=True)
        return []


def mark_messages_processed(message_ids: List[int]) -> None:
    """
    Отметить сообщения как обработанные.

    Args:
        message_ids: Список ID записей в БД.
    """
    if not message_ids:
        return
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                placeholders = ", ".join(["%s"] * len(message_ids))
                cursor.execute(
                    f"UPDATE gk_messages SET processed = 1 WHERE id IN ({placeholders})",
                    tuple(message_ids),
                )
    except Exception as exc:
        logger.error("Ошибка обновления статуса сообщений: %s", exc, exc_info=True)


def update_message_image_description(message_id: int, description: str) -> None:
    """
    Обновить текстовое описание изображения для сообщения.

    Args:
        message_id: ID записи в БД.
        description: Текстовое описание от GigaChat.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE gk_messages SET image_description = %s WHERE id = %s",
                    (description, message_id),
                )
    except Exception as exc:
        logger.error("Ошибка обновления описания изображения: %s", exc, exc_info=True)


def update_message_image_path(message_id: int, image_path: str) -> None:
    """
    Обновить путь к локально сохранённому изображению для сообщения.

    Args:
        message_id: ID записи в БД.
        image_path: Новый путь к файлу изображения.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE gk_messages SET image_path = %s WHERE id = %s",
                    (image_path, message_id),
                )
    except Exception as exc:
        logger.error("Ошибка обновления пути к изображению: %s", exc, exc_info=True)


def reset_message_image_processing(message_id: int) -> None:
    """
    Сбросить результаты обработки изображения и очистить очередь для сообщения.

    Args:
        message_id: ID записи в БД.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    UPDATE gk_messages
                    SET image_path = NULL, image_description = NULL
                    WHERE id = %s
                    """,
                    (message_id,),
                )
                cursor.execute(
                    "DELETE FROM gk_image_queue WHERE message_id = %s",
                    (message_id,),
                )
    except Exception as exc:
        logger.error("Ошибка сброса обработки изображения: %s", exc, exc_info=True)


def get_message_by_id(message_id: int) -> Optional[GroupMessage]:
    """
    Получить сообщение по ID записи в БД.

    Args:
        message_id: ID записи.

    Returns:
        GroupMessage или None.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute("SELECT * FROM gk_messages WHERE id = %s", (message_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                return _row_to_message(row)
    except Exception as exc:
        logger.error("Ошибка получения сообщения по ID: %s", exc, exc_info=True)
        return None


def get_collected_groups() -> List[Dict[str, Any]]:
    """
    Получить список групп, из которых есть собранные сообщения.

    Returns:
        Список словарей с group_id, group_title и количеством сообщений.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT group_id, group_title, COUNT(*) as message_count,
                           MIN(message_date) as first_message,
                           MAX(message_date) as last_message
                    FROM gk_messages
                    GROUP BY group_id, group_title
                    ORDER BY message_count DESC
                    """
                )
                return cursor.fetchall()
    except Exception as exc:
        logger.error("Ошибка получения списка групп: %s", exc, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Q&A-пары (gk_qa_pairs)
# ---------------------------------------------------------------------------

def store_qa_pair(pair: QAPair) -> int:
    """
    Сохранить Q&A-пару в БД.

    Args:
        pair: Объект QAPair для сохранения.

    Returns:
        ID записи в БД.
    """
    now = int(time.time())
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_qa_pairs (
                        question_text, answer_text,
                        question_message_id, answer_message_id,
                        group_id, extraction_type, confidence,
                        llm_model_used, created_at, approved, vector_indexed
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        pair.question_text,
                        pair.answer_text,
                        pair.question_message_id,
                        pair.answer_message_id,
                        pair.group_id,
                        pair.extraction_type,
                        pair.confidence,
                        pair.llm_model_used[:128] if pair.llm_model_used else "",
                        now,
                        pair.approved,
                        0,
                    ),
                )
                return cursor.lastrowid or 0
    except Exception as exc:
        logger.error("Ошибка сохранения Q&A-пары: %s", exc, exc_info=True)
        raise


def get_qa_pairs(
    limit: int = 50,
    offset: int = 0,
    group_id: Optional[int] = None,
    approved_only: bool = True,
) -> List[QAPair]:
    """
    Получить Q&A-пары из БД.

    Args:
        limit: Максимальное число записей.
        offset: Смещение.
        group_id: Фильтр по группе (None — все группы).
        approved_only: Только одобренные пары.

    Returns:
        Список QAPair.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                conditions = []
                params: list = []

                if approved_only:
                    conditions.append("approved = 1")
                if group_id is not None:
                    conditions.append("group_id = %s")
                    params.append(group_id)

                where_clause = ""
                if conditions:
                    where_clause = "WHERE " + " AND ".join(conditions)

                cursor.execute(
                    f"""
                    SELECT * FROM gk_qa_pairs
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params) + (limit, offset),
                )
                rows = cursor.fetchall()
                return [_row_to_qa_pair(r) for r in rows]
    except Exception as exc:
        logger.error("Ошибка получения Q&A-пар: %s", exc, exc_info=True)
        return []


def get_qa_pair_by_id(pair_id: int) -> Optional[QAPair]:
    """
    Получить Q&A-пару по ID.

    Args:
        pair_id: ID записи.

    Returns:
        QAPair или None.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT * FROM gk_qa_pairs WHERE id = %s",
                    (pair_id,),
                )
                row = cursor.fetchone()
                return _row_to_qa_pair(row) if row else None
    except Exception as exc:
        logger.error("Ошибка получения Q&A-пары по ID: %s", exc, exc_info=True)
        return None


def get_unindexed_qa_pairs() -> List[QAPair]:
    """
    Получить Q&A-пары, ещё не проиндексированные в Qdrant.

    Returns:
        Список QAPair с vector_indexed = 0 и approved = 1.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM gk_qa_pairs
                    WHERE vector_indexed = 0 AND approved = 1
                    ORDER BY created_at ASC
                    """
                )
                rows = cursor.fetchall()
                return [_row_to_qa_pair(r) for r in rows]
    except Exception as exc:
        logger.error("Ошибка получения непроиндексированных Q&A-пар: %s", exc, exc_info=True)
        return []


def mark_qa_pair_indexed(pair_id: int) -> None:
    """
    Отметить Q&A-пару как проиндексированную в Qdrant.

    Args:
        pair_id: ID записи.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE gk_qa_pairs SET vector_indexed = 1 WHERE id = %s",
                    (pair_id,),
                )
    except Exception as exc:
        logger.error("Ошибка обновления индекса Q&A-пары: %s", exc, exc_info=True)


def get_qa_pairs_count(
    group_id: Optional[int] = None,
    approved_only: bool = True,
) -> int:
    """
    Получить общее число Q&A-пар.

    Args:
        group_id: Фильтр по группе.
        approved_only: Только одобренные.

    Returns:
        Количество записей.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                conditions = []
                params: list = []

                if approved_only:
                    conditions.append("approved = 1")
                if group_id is not None:
                    conditions.append("group_id = %s")
                    params.append(group_id)

                where_clause = ""
                if conditions:
                    where_clause = "WHERE " + " AND ".join(conditions)

                cursor.execute(
                    f"SELECT COUNT(*) as cnt FROM gk_qa_pairs {where_clause}",
                    tuple(params),
                )
                row = cursor.fetchone()
                return row["cnt"] if row else 0
    except Exception as exc:
        logger.error("Ошибка подсчёта Q&A-пар: %s", exc, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Очередь обработки изображений (gk_image_queue)
# ---------------------------------------------------------------------------

def enqueue_image(message_id: int, image_path: str) -> int:
    """
    Добавить изображение в очередь обработки.

    Args:
        message_id: FK → gk_messages.id.
        image_path: Путь к файлу изображения.

    Returns:
        ID записи в очереди.
    """
    now = int(time.time())
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_image_queue (message_id, image_path, status, created_at, updated_at)
                    VALUES (%s, %s, 0, %s, %s)
                    """,
                    (message_id, image_path, now, now),
                )
                return cursor.lastrowid or 0
    except Exception as exc:
        logger.error("Ошибка добавления в очередь изображений: %s", exc, exc_info=True)
        raise


def get_pending_images(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Получить необработанные изображения из очереди.

    Args:
        limit: Максимальное число записей.

    Returns:
        Список словарей с данными очереди.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM gk_image_queue
                    WHERE status = 0
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return cursor.fetchall()
    except Exception as exc:
        logger.error("Ошибка получения очереди изображений: %s", exc, exc_info=True)
        return []


def update_image_status(
    queue_id: int,
    status: int,
    error_message: Optional[str] = None,
) -> None:
    """
    Обновить статус обработки изображения.

    Args:
        queue_id: ID записи в очереди.
        status: Новый статус (0=pending, 1=processing, 2=done, 3=error).
        error_message: Текст ошибки (при status=3).
    """
    now = int(time.time())
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    UPDATE gk_image_queue
                    SET status = %s, error_message = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (status, error_message, now, queue_id),
                )
    except Exception as exc:
        logger.error("Ошибка обновления статуса изображения: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Лог автоответчика (gk_responder_log)
# ---------------------------------------------------------------------------

def store_responder_log(
    group_id: int,
    question_message_id: int,
    question_text: str,
    answer_text: str,
    qa_pair_id: Optional[int],
    confidence: float,
    dry_run: bool,
) -> int:
    """
    Сохранить запись лога автоответчика.

    Args:
        group_id: ID группы.
        question_message_id: Telegram message ID вопроса.
        question_text: Текст вопроса.
        answer_text: Текст ответа.
        qa_pair_id: ID использованной Q&A-пары (опционально).
        confidence: Уверенность в ответе.
        dry_run: Был ли ответ в режиме dry-run.

    Returns:
        ID записи в логе.
    """
    now = int(time.time())
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_responder_log (
                        group_id, question_message_id, question_text,
                        answer_text, qa_pair_id, confidence, dry_run, responded_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        group_id,
                        question_message_id,
                        question_text[:8000] if question_text else "",
                        answer_text[:8000] if answer_text else "",
                        qa_pair_id,
                        confidence,
                        1 if dry_run else 0,
                        now,
                    ),
                )
                return cursor.lastrowid or 0
    except Exception as exc:
        logger.error("Ошибка сохранения лога автоответчика: %s", exc, exc_info=True)
        return 0


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _row_to_message(row: Dict[str, Any]) -> GroupMessage:
    """Преобразовать строку из БД в объект GroupMessage."""
    return GroupMessage(
        id=row.get("id"),
        telegram_message_id=row.get("telegram_message_id", 0),
        group_id=row.get("group_id", 0),
        group_title=row.get("group_title", ""),
        sender_id=row.get("sender_id", 0),
        sender_name=row.get("sender_name", ""),
        message_text=row.get("message_text", ""),
        caption=row.get("caption"),
        has_image=bool(row.get("has_image", 0)),
        image_path=row.get("image_path"),
        image_description=row.get("image_description"),
        reply_to_message_id=row.get("reply_to_message_id"),
        message_date=row.get("message_date", 0),
        collected_at=row.get("collected_at", 0),
        processed=row.get("processed", 0),
    )


def _row_to_qa_pair(row: Dict[str, Any]) -> QAPair:
    """Преобразовать строку из БД в объект QAPair."""
    return QAPair(
        id=row.get("id"),
        question_text=row.get("question_text", ""),
        answer_text=row.get("answer_text", ""),
        question_message_id=row.get("question_message_id"),
        answer_message_id=row.get("answer_message_id"),
        group_id=row.get("group_id", 0),
        extraction_type=row.get("extraction_type", "thread_reply"),
        confidence=row.get("confidence"),
        llm_model_used=row.get("llm_model_used", ""),
        created_at=row.get("created_at", 0),
        approved=row.get("approved", 1),
        vector_indexed=row.get("vector_indexed", 0),
    )
