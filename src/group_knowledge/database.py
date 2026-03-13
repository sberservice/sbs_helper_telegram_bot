"""
Операции с базой данных для подсистемы Group Knowledge.

Предоставляет функции для хранения и извлечения сообщений,
Q&A-пар, очереди обработки изображений и логов автоответчика.
"""

import logging
import time
from typing import Iterable, List, Optional, Dict, Any, Tuple

from src.common.database import get_db_connection, get_cursor
from src.group_knowledge.models import GroupMessage, QAPair

logger = logging.getLogger(__name__)

_RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN: Optional[bool] = None
_RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN: Optional[bool] = None


def _responder_log_has_llm_request_payload_column() -> bool:
    """Проверить наличие колонки llm_request_payload в таблице gk_responder_log."""
    global _RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN

    if _RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN is not None:
        return _RESPONDER_LOG_HAS_LLM_REQUEST_PAYLOAD_COLUMN

    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
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
    """Проверить наличие колонки question_message_date в таблице gk_responder_log."""
    global _RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN

    if _RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN is not None:
        return _RESPONDER_LOG_HAS_QUESTION_MESSAGE_DATE_COLUMN

    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
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
                        reply_to_message_id, message_date, collected_at, processed,
                        is_question, question_confidence, question_reason,
                        question_model_used, question_detected_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        sender_name = VALUES(sender_name),
                        is_question = VALUES(is_question),
                        question_confidence = VALUES(question_confidence),
                        question_reason = VALUES(question_reason),
                        question_model_used = VALUES(question_model_used),
                        question_detected_at = VALUES(question_detected_at)
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
                        1 if msg.is_question is True else 0 if msg.is_question is False else None,
                        msg.question_confidence,
                        msg.question_reason,
                        msg.question_model_used,
                        msg.question_detected_at,
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


def get_messages_by_ids(message_ids: Iterable[int]) -> Dict[int, GroupMessage]:
    """
    Получить сообщения по внутренним ID таблицы gk_messages.

    Args:
        message_ids: Идентификаторы записей gk_messages.id.

    Returns:
        Словарь {message_id: GroupMessage} для найденных записей.
    """
    normalized_ids = sorted({int(message_id) for message_id in (message_ids or []) if message_id is not None})
    if not normalized_ids:
        return {}

    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                placeholders = ", ".join(["%s"] * len(normalized_ids))
                cursor.execute(
                    f"SELECT * FROM gk_messages WHERE id IN ({placeholders})",
                    tuple(normalized_ids),
                )
                rows = cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения сообщений по ID: %s", exc, exc_info=True)
        return {}

    messages_by_id: Dict[int, GroupMessage] = {}
    for row in rows:
        message = _row_to_message(row)
        if message.id is None:
            continue
        messages_by_id[int(message.id)] = message
    return messages_by_id


def get_messages_by_telegram_ids(
    group_id: int,
    telegram_message_ids: List[int],
) -> List[GroupMessage]:
    """
    Получить сообщения по списку Telegram message ID для одной группы.

    Используется для кросс-дневного обогащения цепочек: загрузка
    родительских сообщений, на которые ссылаются reply_to_message_id.

    Args:
        group_id: ID группы.
        telegram_message_ids: Список Telegram message ID для поиска.

    Returns:
        Список найденных GroupMessage.
    """
    if not telegram_message_ids:
        return []
    normalized = sorted({int(mid) for mid in telegram_message_ids})
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                placeholders = ", ".join(["%s"] * len(normalized))
                cursor.execute(
                    f"SELECT * FROM gk_messages WHERE group_id = %s AND telegram_message_id IN ({placeholders})",
                    (group_id, *normalized),
                )
                rows = cursor.fetchall() or []
                return [_row_to_message(r) for r in rows]
    except Exception as exc:
        logger.error(
            "Ошибка получения сообщений по telegram_message_ids: %s", exc, exc_info=True,
        )
        return []


def get_replies_to_telegram_messages(
    group_id: int,
    telegram_message_ids: List[int],
    min_timestamp: int = 0,
) -> List[GroupMessage]:
    """
    Получить все ответы (reply_to) на указанные Telegram message ID.

    Используется для кросс-дневного обогащения цепочек: поиск ответов,
    которые были отправлены позже (в другие дни) в ответ на вопросы текущего дня.

    Args:
        group_id: ID группы.
        telegram_message_ids: Список Telegram message ID, ответы на которые ищем.
        min_timestamp: Минимальный UNIX timestamp сообщения (для ограничения глубины).

    Returns:
        Список найденных GroupMessage (ответы на указанные сообщения).
    """
    if not telegram_message_ids:
        return []
    normalized = sorted({int(mid) for mid in telegram_message_ids})
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                placeholders = ", ".join(["%s"] * len(normalized))
                query = (
                    f"SELECT * FROM gk_messages WHERE group_id = %s "
                    f"AND reply_to_message_id IN ({placeholders})"
                )
                params: list = [group_id, *normalized]
                if min_timestamp > 0:
                    query += " AND message_date >= %s"
                    params.append(min_timestamp)
                query += " ORDER BY message_date ASC"
                cursor.execute(query, tuple(params))
                rows = cursor.fetchall() or []
                return [_row_to_message(r) for r in rows]
    except Exception as exc:
        logger.error(
            "Ошибка получения ответов на telegram_message_ids: %s", exc, exc_info=True,
        )
        return []


def get_latest_telegram_message_id(group_id: int) -> Optional[int]:
    """
    Получить максимальный Telegram message ID, уже собранный для группы.

    Args:
        group_id: ID группы.

    Returns:
        Максимальный telegram_message_id или None, если сообщений ещё нет.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT MAX(telegram_message_id) AS latest_message_id FROM gk_messages WHERE group_id = %s",
                    (group_id,),
                )
                row = cursor.fetchone()
                if not row or row.get("latest_message_id") is None:
                    return None
                return int(row["latest_message_id"])
    except Exception as exc:
        logger.error(
            "Ошибка получения последнего Telegram message ID: %s",
            exc,
            exc_info=True,
        )
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


def get_unprocessed_dates(group_id: int) -> List[str]:
    """
    Получить даты, где у группы есть необработанные сообщения.

    Args:
        group_id: ID группы.

    Returns:
        Список дат в формате YYYY-MM-DD.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT DATE(FROM_UNIXTIME(message_date)) AS message_date
                    FROM gk_messages
                    WHERE group_id = %s
                      AND processed = 0
                    ORDER BY message_date ASC
                    """,
                    (group_id,),
                )
                rows = cursor.fetchall()
                return [str(row["message_date"]) for row in rows if row.get("message_date")]
    except Exception as exc:
        logger.error("Ошибка получения дат необработанных сообщений: %s", exc, exc_info=True)
        return []


def get_message_dates(group_id: int) -> List[str]:
    """
    Получить все даты, за которые у группы есть сообщения.

    Args:
        group_id: ID группы.

    Returns:
        Список дат в формате YYYY-MM-DD.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT DISTINCT DATE(FROM_UNIXTIME(message_date)) AS message_date
                    FROM gk_messages
                    WHERE group_id = %s
                    ORDER BY message_date ASC
                    """,
                    (group_id,),
                )
                rows = cursor.fetchall()
                return [str(row["message_date"]) for row in rows if row.get("message_date")]
    except Exception as exc:
        logger.error("Ошибка получения всех дат сообщений: %s", exc, exc_info=True)
        return []


def get_messages_missing_question_classification(
    group_ids: Optional[Iterable[int]] = None,
    newer_than_ts: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[GroupMessage]:
    """
    Получить сообщения, у которых ещё не заполнено поле `is_question`.

    Args:
        group_ids: Ограничить выборку указанными group_id.
        newer_than_ts: Вернуть только сообщения не старше указанного UNIX timestamp.
        limit: Ограничить максимальное число сообщений.

    Returns:
        Список сообщений, отсортированных по времени.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                conditions = ["is_question IS NULL"]
                params: List[Any] = []

                normalized_group_ids = tuple(int(group_id) for group_id in (group_ids or []))
                if normalized_group_ids:
                    placeholders = ", ".join(["%s"] * len(normalized_group_ids))
                    conditions.append(f"group_id IN ({placeholders})")
                    params.extend(normalized_group_ids)

                if newer_than_ts is not None:
                    conditions.append("message_date >= %s")
                    params.append(int(newer_than_ts))

                where_clause = " AND ".join(conditions)
                limit_clause = ""
                if limit is not None:
                    limit_clause = "LIMIT %s"
                    params.append(int(limit))

                cursor.execute(
                    f"""
                    SELECT * FROM gk_messages
                    WHERE {where_clause}
                    ORDER BY message_date ASC, id ASC
                    {limit_clause}
                    """,
                    tuple(params),
                )
                rows = cursor.fetchall()
                return [_row_to_message(row) for row in (rows or [])]
    except Exception as exc:
        logger.error(
            "Ошибка получения сообщений без question-классификации: %s",
            exc,
            exc_info=True,
        )
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


def update_message_question_classification(
    message_id: int,
    is_question: bool,
    confidence: float,
    reason: str,
    model_used: str,
    detected_at: int,
) -> None:
    """
    Обновить LLM-классификацию сообщения как вопроса.

    Args:
        message_id: ID записи в БД.
        is_question: Является ли сообщение вопросом.
        confidence: Уверенность классификатора.
        reason: Краткая причина классификации.
        model_used: Имя модели.
        detected_at: Время классификации.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    UPDATE gk_messages
                    SET is_question = %s,
                        question_confidence = %s,
                        question_reason = %s,
                        question_model_used = %s,
                        question_detected_at = %s
                    WHERE id = %s
                    """,
                    (
                        1 if is_question else 0,
                        confidence,
                        reason[:512] if reason else "",
                        model_used[:128] if model_used else "",
                        detected_at,
                        message_id,
                    ),
                )
    except Exception as exc:
        logger.error("Ошибка обновления классификации вопроса: %s", exc, exc_info=True)


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


def get_qa_pair_ids_by_group(group_id: int) -> List[int]:
    """
    Получить список ID Q&A-пар для указанной группы.

    Args:
        group_id: ID группы.

    Returns:
        Список ID пар.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT id
                    FROM gk_qa_pairs
                    WHERE group_id = %s
                    ORDER BY id ASC
                    """,
                    (group_id,),
                )
                rows = cursor.fetchall()
                return [int(row["id"]) for row in rows if row.get("id") is not None]
    except Exception as exc:
        logger.error("Ошибка получения ID Q&A-пар группы: %s", exc, exc_info=True)
        return []


def delete_qa_pairs_by_group(group_id: int) -> int:
    """
    Удалить все Q&A-пары указанной группы.

    Args:
        group_id: ID группы.

    Returns:
        Число удалённых строк.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    "DELETE FROM gk_qa_pairs WHERE group_id = %s",
                    (group_id,),
                )
                return int(cursor.rowcount or 0)
    except Exception as exc:
        logger.error("Ошибка удаления Q&A-пар группы %s: %s", group_id, exc, exc_info=True)
        raise


def delete_expert_validations_by_group(group_id: int) -> int:
    """
    Удалить все экспертные валидации Q&A-пар указанной группы.

    Args:
        group_id: ID группы.

    Returns:
        Число удалённых строк.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    DELETE ev
                    FROM gk_expert_validations ev
                    INNER JOIN gk_qa_pairs qp ON qp.id = ev.qa_pair_id
                    WHERE qp.group_id = %s
                    """,
                    (group_id,),
                )
                return int(cursor.rowcount or 0)
    except Exception as exc:
        logger.error(
            "Ошибка удаления экспертных валидаций группы %s: %s",
            group_id,
            exc,
            exc_info=True,
        )
        raise


def delete_group_data(group_id: int, dry_run: bool = True) -> Dict[str, int]:
    """
    Удалить данные Group Knowledge для указанной группы.

    Удаляются данные из таблиц:
    - gk_image_queue (через join с сообщениями группы)
    - gk_responder_log
    - gk_qa_pairs
    - gk_messages

    Args:
        group_id: ID группы.
        dry_run: Если True, только вернуть статистику без удаления.

    Returns:
        Словарь со статистикой найденных и удалённых записей.
    """
    stats: Dict[str, int] = {
        "group_id": int(group_id),
        "messages_found": 0,
        "qa_pairs_found": 0,
        "responder_logs_found": 0,
        "image_queue_found": 0,
        "messages_deleted": 0,
        "qa_pairs_deleted": 0,
        "responder_logs_deleted": 0,
        "image_queue_deleted": 0,
        "dry_run": 1 if dry_run else 0,
    }

    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM gk_messages WHERE group_id = %s",
                    (group_id,),
                )
                stats["messages_found"] = int((cursor.fetchone() or {}).get("cnt", 0))

                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM gk_qa_pairs WHERE group_id = %s",
                    (group_id,),
                )
                stats["qa_pairs_found"] = int((cursor.fetchone() or {}).get("cnt", 0))

                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM gk_responder_log WHERE group_id = %s",
                    (group_id,),
                )
                stats["responder_logs_found"] = int((cursor.fetchone() or {}).get("cnt", 0))

                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM gk_image_queue iq
                    INNER JOIN gk_messages gm ON gm.id = iq.message_id
                    WHERE gm.group_id = %s
                    """,
                    (group_id,),
                )
                stats["image_queue_found"] = int((cursor.fetchone() or {}).get("cnt", 0))

                if dry_run:
                    return stats

                cursor.execute(
                    """
                    DELETE iq
                    FROM gk_image_queue iq
                    INNER JOIN gk_messages gm ON gm.id = iq.message_id
                    WHERE gm.group_id = %s
                    """,
                    (group_id,),
                )
                stats["image_queue_deleted"] = int(cursor.rowcount or 0)

                cursor.execute(
                    "DELETE FROM gk_responder_log WHERE group_id = %s",
                    (group_id,),
                )
                stats["responder_logs_deleted"] = int(cursor.rowcount or 0)

                cursor.execute(
                    "DELETE FROM gk_qa_pairs WHERE group_id = %s",
                    (group_id,),
                )
                stats["qa_pairs_deleted"] = int(cursor.rowcount or 0)

                cursor.execute(
                    "DELETE FROM gk_messages WHERE group_id = %s",
                    (group_id,),
                )
                stats["messages_deleted"] = int(cursor.rowcount or 0)

        return stats
    except Exception as exc:
        logger.error("Ошибка удаления данных группы %s: %s", group_id, exc, exc_info=True)
        raise


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
                existing_id = None
                if pair.question_message_id:
                    cursor.execute(
                        """
                        SELECT id
                        FROM gk_qa_pairs
                        WHERE question_message_id = %s
                        ORDER BY id DESC
                        LIMIT 1
                        """,
                        (pair.question_message_id,),
                    )
                    row = cursor.fetchone()
                    existing_id = row["id"] if row else None

                if existing_id is not None:
                    cursor.execute(
                        """
                        UPDATE gk_qa_pairs
                        SET question_text = %s,
                            answer_text = %s,
                            answer_message_id = %s,
                            group_id = %s,
                            extraction_type = %s,
                            confidence = %s,
                            confidence_reason = %s,
                            fullness = %s,
                            llm_model_used = %s,
                            llm_request_payload = %s,
                            approved = %s,
                            vector_indexed = 0
                        WHERE id = %s
                        """,
                        (
                            pair.question_text,
                            pair.answer_text,
                            pair.answer_message_id,
                            pair.group_id,
                            pair.extraction_type,
                            pair.confidence,
                            pair.confidence_reason,
                            pair.fullness,
                            pair.llm_model_used[:128] if pair.llm_model_used else "",
                            pair.llm_request_payload,
                            pair.approved,
                            existing_id,
                        ),
                    )
                    return int(existing_id)

                cursor.execute(
                    """
                    INSERT INTO gk_qa_pairs (
                        question_text, answer_text,
                        question_message_id, answer_message_id,
                        group_id, extraction_type, confidence,
                        confidence_reason, fullness,
                        llm_model_used, llm_request_payload,
                        created_at, approved, vector_indexed
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        pair.question_text,
                        pair.answer_text,
                        pair.question_message_id,
                        pair.answer_message_id,
                        pair.group_id,
                        pair.extraction_type,
                        pair.confidence,
                        pair.confidence_reason,
                        pair.fullness,
                        pair.llm_model_used[:128] if pair.llm_model_used else "",
                        pair.llm_request_payload,
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
    extraction_types: Optional[Iterable[str]] = None,
) -> List[QAPair]:
    """
    Получить Q&A-пары из БД.

    Args:
        limit: Максимальное число записей.
        offset: Смещение.
        group_id: Фильтр по группе (None — все группы).
        approved_only: Только одобренные пары.
        extraction_types: Допустимые типы извлечения (`thread_reply`, `llm_inferred`).

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
                normalized_extraction_types = _normalize_extraction_types(extraction_types)
                if normalized_extraction_types:
                    placeholders = ", ".join(["%s"] * len(normalized_extraction_types))
                    conditions.append(f"extraction_type IN ({placeholders})")
                    params.extend(normalized_extraction_types)

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


def get_all_approved_qa_pairs(
    extraction_types: Optional[Iterable[str]] = None,
    group_id: Optional[int] = None,
) -> List[QAPair]:
    """
    Получить все одобренные Q&A-пары из БД.

    Используется для построения BM25-корпуса при гибридном поиске.

    Args:
        extraction_types: Допустимые типы извлечения (`thread_reply`, `llm_inferred`).
        group_id: Идентификатор группы для фильтрации (None = все группы).

    Returns:
        Список всех QAPair с approved = 1, отсортированных по id.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                normalized_extraction_types = _normalize_extraction_types(extraction_types)
                where_clause = (
                    "WHERE approved = 1"
                    " AND (expert_status IS NULL OR expert_status != 'rejected')"
                )
                params: list = []
                if normalized_extraction_types:
                    placeholders = ", ".join(["%s"] * len(normalized_extraction_types))
                    where_clause += f" AND extraction_type IN ({placeholders})"
                    params.extend(normalized_extraction_types)
                if group_id is not None:
                    where_clause += " AND group_id = %s"
                    params.append(group_id)
                cursor.execute(
                    f"""
                    SELECT * FROM gk_qa_pairs
                    {where_clause}
                    ORDER BY id
                    """,
                    tuple(params),
                )
                rows = cursor.fetchall()
                return [_row_to_qa_pair(row) for row in (rows or [])]
    except Exception as exc:
        logger.error("Ошибка получения одобренных Q&A-пар: %s", exc, exc_info=True)
        return []


def get_approved_qa_pairs_corpus_signature(
    extraction_types: Optional[Iterable[str]] = None,
    group_id: Optional[int] = None,
) -> Optional[Tuple[int, int, int]]:
    """
    Получить сигнатуру (версию) текущего approved-корпуса Q&A.

    Сигнатура используется для быстрого определения изменений корпуса
    без полной перезагрузки кэша BM25.

    Args:
        extraction_types: Допустимые типы извлечения.
        group_id: Идентификатор группы для фильтрации (None = все группы).

    Returns:
        Кортеж (count, max_id, max_created_at) или None при ошибке.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                normalized_extraction_types = _normalize_extraction_types(extraction_types)
                where_clause = (
                    "WHERE approved = 1"
                    " AND (expert_status IS NULL OR expert_status != 'rejected')"
                )
                params: list = []
                if normalized_extraction_types:
                    placeholders = ", ".join(["%s"] * len(normalized_extraction_types))
                    where_clause += f" AND extraction_type IN ({placeholders})"
                    params.extend(normalized_extraction_types)
                if group_id is not None:
                    where_clause += " AND group_id = %s"
                    params.append(group_id)
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS cnt,
                        COALESCE(MAX(id), 0) AS max_id,
                        COALESCE(MAX(created_at), 0) AS max_created_at
                    FROM gk_qa_pairs
                    {where_clause}
                    """,
                    tuple(params),
                )
                row = cursor.fetchone() or {}
                return (
                    int(row.get("cnt") or 0),
                    int(row.get("max_id") or 0),
                    int(row.get("max_created_at") or 0),
                )
    except Exception as exc:
        logger.error("Ошибка получения сигнатуры корпуса Q&A: %s", exc, exc_info=True)
        return None


def _normalize_extraction_types(
    extraction_types: Optional[Iterable[str]],
) -> Optional[Tuple[str, ...]]:
    """Нормализовать список типов извлечения для SQL-фильтрации."""
    if extraction_types is None:
        return None

    normalized = tuple(
        extraction_type.strip()
        for extraction_type in extraction_types
        if extraction_type and extraction_type.strip()
    )
    return normalized or None


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
                      AND (expert_status IS NULL OR expert_status != 'rejected')
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


def reset_qa_pairs_vector_indexed(
    group_id: Optional[int] = None,
    approved_only: bool = True,
) -> int:
    """
    Сбросить флаг vector_indexed у Q&A-пар.

    Args:
        group_id: Если задан, сбросить только для указанной группы.
        approved_only: Если True, сбрасывать только approved-пары.

    Returns:
        Число обновлённых строк.
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
                    where_clause = " WHERE " + " AND ".join(conditions)

                cursor.execute(
                    f"UPDATE gk_qa_pairs SET vector_indexed = 0{where_clause}",
                    tuple(params),
                )
                return int(cursor.rowcount or 0)
    except Exception as exc:
        logger.error("Ошибка сброса флага vector_indexed у Q&A-пар: %s", exc, exc_info=True)
        raise


def get_qa_pairs_count(
    group_id: Optional[int] = None,
    approved_only: bool = True,
    date_str: Optional[str] = None,
) -> int:
    """
    Получить общее число Q&A-пар.

    Args:
        group_id: Фильтр по группе.
        approved_only: Только одобренные.
        date_str: Дата в формате YYYY-MM-DD для фильтрации по дате question_message.

    Returns:
        Количество записей.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                conditions: List[str] = []
                params: List = []

                join_clause = ""
                if date_str:
                    join_clause = " LEFT JOIN gk_messages qm ON qm.id = qp.question_message_id "
                    conditions.append("DATE(FROM_UNIXTIME(qm.message_date)) = %s")
                    params.append(date_str)

                if approved_only:
                    conditions.append("qp.approved = 1")
                if group_id is not None:
                    conditions.append("qp.group_id = %s")
                    params.append(group_id)

                where_clause = ""
                if conditions:
                    where_clause = "WHERE " + " AND ".join(conditions)

                cursor.execute(
                    f"SELECT COUNT(*) as cnt FROM gk_qa_pairs qp {join_clause} {where_clause}",
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
    llm_request_payload: Optional[str] = None,
    question_message_date: Optional[int] = None,
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
        llm_request_payload: Полный JSON запроса к LLM.
        question_message_date: Время исходного вопроса (UNIX timestamp).

    Returns:
        ID записи в логе.
    """
    now = int(time.time())
    has_payload_column = _responder_log_has_llm_request_payload_column()
    has_question_date_column = _responder_log_has_question_message_date_column()
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                columns = [
                    "group_id",
                    "question_message_id",
                    "question_text",
                    "answer_text",
                    "qa_pair_id",
                    "confidence",
                    "dry_run",
                    "responded_at",
                ]
                values: List[Any] = [
                    group_id,
                    question_message_id,
                    question_text[:8000] if question_text else "",
                    answer_text[:8000] if answer_text else "",
                    qa_pair_id,
                    confidence,
                    1 if dry_run else 0,
                    now,
                ]

                if has_question_date_column:
                    columns.append("question_message_date")
                    values.append(question_message_date)

                if has_payload_column:
                    columns.append("llm_request_payload")
                    values.append(llm_request_payload)

                placeholders = ", ".join(["%s"] * len(columns))
                columns_sql = ", ".join(columns)
                cursor.execute(
                    f"INSERT INTO gk_responder_log ({columns_sql}) VALUES ({placeholders})",
                    tuple(values),
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
        is_question=(None if row.get("is_question") is None else bool(row.get("is_question"))),
        question_confidence=row.get("question_confidence"),
        question_reason=row.get("question_reason"),
        question_model_used=row.get("question_model_used"),
        question_detected_at=row.get("question_detected_at"),
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
        confidence_reason=row.get("confidence_reason"),
        fullness=row.get("fullness"),
        llm_model_used=row.get("llm_model_used", ""),
        llm_request_payload=row.get("llm_request_payload"),
        created_at=row.get("created_at", 0),
        approved=row.get("approved", 1),
        vector_indexed=row.get("vector_indexed", 0),
        expert_status=row.get("expert_status"),
    )


# ---------------------------------------------------------------------------
# Термины и аббревиатуры (gk_terms)
# ---------------------------------------------------------------------------

def store_term(term_data: Dict[str, Any]) -> Optional[int]:
    """
    Сохранить термин в БД (upsert по group_id + term).

    Args:
        term_data: Словарь с полями: group_id, term, definition,
                   source, status, confidence, llm_model_used,
                   llm_request_payload, scan_batch_id.

    Returns:
        ID записи или None при ошибке.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                group_id = term_data.get("group_id", 0)
                term = (term_data.get("term") or "").strip().lower()
                cursor.execute(
                    """
                    INSERT INTO gk_terms
                        (group_id, term, definition, source, status,
                         confidence, llm_model_used, llm_request_payload, scan_batch_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        definition = COALESCE(VALUES(definition), definition),
                        confidence = COALESCE(VALUES(confidence), confidence),
                        llm_model_used = COALESCE(VALUES(llm_model_used), llm_model_used),
                        llm_request_payload = COALESCE(VALUES(llm_request_payload), llm_request_payload),
                        scan_batch_id = COALESCE(VALUES(scan_batch_id), scan_batch_id),
                        updated_at = NOW()
                    """,
                    (
                        group_id,
                        term,
                        term_data.get("definition"),
                        term_data.get("source", "llm_discovered"),
                        term_data.get("status", "pending"),
                        term_data.get("confidence"),
                        term_data.get("llm_model_used"),
                        term_data.get("llm_request_payload"),
                        term_data.get("scan_batch_id"),
                    ),
                )
                result_id = cursor.lastrowid
                # lastrowid ненадёжен при ON DUPLICATE KEY UPDATE —
                # запросить явно.
                if not result_id:
                    cursor.execute(
                        """
                        SELECT id FROM gk_terms
                        WHERE group_id = %s AND term = %s
                        """,
                        (group_id, term),
                    )
                    row = cursor.fetchone()
                    result_id = row["id"] if row else None
                return result_id or None
    except Exception as exc:
        logger.error(
            "Ошибка сохранения термина '%s': %s",
            term_data.get("term"), exc, exc_info=True,
        )
        return None


def store_terms_batch(terms: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Сохранить пакет терминов в БД (upsert).

    Пропускает записи, которые уже были рассмотрены экспертом
    (status IN ('approved', 'rejected')), чтобы не перезаписывать
    ранее принятые решения.

    Args:
        terms: Список словарей с данными терминов.

    Returns:
        Словарь с количеством: {"inserted": N, "updated": N, "skipped": N}.
    """
    result = {"inserted": 0, "updated": 0, "skipped": 0}
    if not terms:
        return result

    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                # Предзагрузка ранее рассмотренных терминов для пропуска.
                reviewed_keys = _get_reviewed_term_keys(cursor, terms)

                for term_data in terms:
                    try:
                        term_key = (
                            term_data.get("group_id", 0),
                            (term_data.get("term") or "").strip().lower(),
                        )
                        if term_key in reviewed_keys:
                            result["skipped"] += 1
                            continue

                        cursor.execute(
                            """
                            INSERT INTO gk_terms
                                (group_id, term, definition, source, status,
                                 confidence, llm_model_used, llm_request_payload, scan_batch_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                                definition = COALESCE(VALUES(definition), definition),
                                confidence = COALESCE(VALUES(confidence), confidence),
                                llm_model_used = COALESCE(VALUES(llm_model_used), llm_model_used),
                                llm_request_payload = COALESCE(VALUES(llm_request_payload), llm_request_payload),
                                scan_batch_id = COALESCE(VALUES(scan_batch_id), scan_batch_id),
                                updated_at = NOW()
                            """,
                            (
                                term_data.get("group_id", 0),
                                (term_data.get("term") or "").strip().lower(),
                                term_data.get("definition"),
                                term_data.get("source", "llm_discovered"),
                                term_data.get("status", "pending"),
                                term_data.get("confidence"),
                                term_data.get("llm_model_used"),
                                term_data.get("llm_request_payload"),
                                term_data.get("scan_batch_id"),
                            ),
                        )
                        # MySQL rowcount: 1 = INSERT, 2 = UPDATE (с изменением),
                        # 0 = UPDATE без изменения (но дубликат найден).
                        rowcount = cursor.rowcount
                        if rowcount == 1:
                            result["inserted"] += 1
                        else:
                            result["updated"] += 1
                    except Exception as row_exc:
                        logger.warning(
                            "Ошибка сохранения термина '%s': %s",
                            term_data.get("term"), row_exc,
                        )
        total = result["inserted"] + result["updated"]
        logger.info(
            "Сохранено терминов: %d (новых: %d, обновлено: %d, пропущено: %d) из %d",
            total, result["inserted"], result["updated"],
            result["skipped"], len(terms),
        )
    except Exception as exc:
        logger.error("Ошибка пакетного сохранения терминов: %s", exc, exc_info=True)
    return result


def _get_reviewed_term_keys(
    cursor: Any,
    terms: List[Dict[str, Any]],
) -> set:
    """
    Получить множество ключей (group_id, term) терминов,
    которые уже имеют status approved/rejected в БД.

    Используется для пропуска при повторном сканировании.
    """
    if not terms:
        return set()

    group_ids = {t.get("group_id", 0) for t in terms}
    placeholders = ",".join(["%s"] * len(group_ids))
    try:
        cursor.execute(
            f"""
            SELECT group_id, term
            FROM gk_terms
            WHERE group_id IN ({placeholders})
              AND status IN ('approved', 'rejected')
            """,
            tuple(group_ids),
        )
        rows = cursor.fetchall() or []
        return {
            (row["group_id"], row["term"].strip().lower())
            for row in rows
            if row.get("term")
        }
    except Exception as exc:
        logger.warning(
            "Не удалось загрузить рассмотренные термины: %s", exc,
        )
        return set()


def get_approved_terms(group_id: Optional[int] = None) -> set:
    """
    Получить множество одобренных терминов (для BM25-защиты).

    Всегда включает глобальные термины (group_id=0).
    Если указан group_id — добавляет термины конкретной группы.

    Args:
        group_id: ID группы (None = только глобальные).

    Returns:
        Множество строк (термины в нижнем регистре).
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                if group_id is not None and group_id != 0:
                    cursor.execute(
                        """
                        SELECT term FROM gk_terms
                        WHERE status = 'approved'
                          AND group_id IN (0, %s)
                        """,
                        (group_id,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT term FROM gk_terms
                        WHERE status = 'approved'
                          AND group_id = 0
                        """
                    )
                rows = cursor.fetchall() or []
                return {row["term"].strip().lower() for row in rows if row.get("term")}
    except Exception as exc:
        logger.error("Ошибка загрузки терминов: %s", exc, exc_info=True)
        return set()


def get_terms_for_group(
    group_id: int,
    *,
    status: Optional[str] = None,
    has_definition: Optional[bool] = None,
    # Обратная совместимость: term_type принимается, но игнорируется.
    term_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Получить все термины для группы (включая глобальные).

    Args:
        group_id: ID группы.
        status: Фильтр по статусу (pending/approved/rejected).
        has_definition: True — только с расшифровкой, False — только без.
        term_type: Устаревший параметр (игнорируется). Для обратной
                   совместимости: 'acronym' → has_definition=True.

    Returns:
        Список словарей с данными терминов.
    """
    conditions = ["group_id IN (0, %s)"]
    params: List[Any] = [group_id]

    if status:
        conditions.append("status = %s")
        params.append(status)

    # Обратная совместимость: term_type='acronym' → has_definition=True.
    effective_has_definition = has_definition
    if term_type == "acronym" and has_definition is None:
        effective_has_definition = True

    if effective_has_definition is True:
        conditions.append("definition IS NOT NULL")
    elif effective_has_definition is False:
        conditions.append("definition IS NULL")

    where_clause = " AND ".join(conditions)

    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT * FROM gk_terms
                    WHERE {where_clause}
                    ORDER BY term
                    """,
                    tuple(params),
                )
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения терминов group=%d: %s", group_id, exc, exc_info=True)
        return []


def update_term_status(
    term_id: int,
    status: str,
    *,
    expert_status: Optional[str] = None,
) -> bool:
    """
    Обновить статус термина.

    Args:
        term_id: ID записи термина.
        status: Новый статус (pending/approved/rejected).
        expert_status: Денормализованный статус экспертной валидации.

    Returns:
        True если обновление прошло успешно.
    """
    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                if expert_status:
                    cursor.execute(
                        """
                        UPDATE gk_terms
                        SET status = %s,
                            expert_status = %s,
                            expert_validated_at = NOW()
                        WHERE id = %s
                        """,
                        (status, expert_status, term_id),
                    )
                else:
                    cursor.execute(
                        "UPDATE gk_terms SET status = %s WHERE id = %s",
                        (status, term_id),
                    )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка обновления статуса термина %d: %s", term_id, exc, exc_info=True)
        return False
