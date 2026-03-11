"""
БД-слой для песочницы анализатора Q&A.

Предоставляет поиск сообщений по тексту и реконструкцию цепочек
с использованием того же алгоритма, что и QAAnalyzer.
"""

import logging
from typing import Any, Dict, List, Optional

from src.common.database import get_db_connection, get_cursor
from src.group_knowledge.models import GroupMessage
from src.group_knowledge import database as gk_db

logger = logging.getLogger(__name__)

# Максимальное число результатов текстового поиска.
_SEARCH_MAX_RESULTS = 100
# Минимальная длина поискового запроса.
_SEARCH_MIN_QUERY_LENGTH = 3


def search_messages(
    query: str,
    group_id: Optional[int] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Поиск сообщений по тексту (LIKE) в таблице gk_messages.

    Args:
        query: Поисковая строка (минимум 3 символа).
        group_id: Ограничить поиск конкретной группой (опционально).
        limit: Максимальное число результатов.

    Returns:
        Список словарей с полями сообщения.
    """
    query = (query or "").strip()
    if len(query) < _SEARCH_MIN_QUERY_LENGTH:
        return []

    limit = min(max(1, limit), _SEARCH_MAX_RESULTS)
    like_pattern = f"%{query}%"

    try:
        with get_db_connection() as conn:
            with get_cursor(conn) as cursor:
                sql = """
                    SELECT
                        id, telegram_message_id, group_id, group_title,
                        sender_id, sender_name, message_text, caption,
                        has_image, image_description, reply_to_message_id,
                        message_date, is_question, question_confidence
                    FROM gk_messages
                    WHERE (message_text LIKE %s OR caption LIKE %s)
                """
                params: list = [like_pattern, like_pattern]

                if group_id is not None:
                    sql += " AND group_id = %s"
                    params.append(group_id)

                sql += " ORDER BY message_date DESC LIMIT %s"
                params.append(limit)

                cursor.execute(sql, tuple(params))
                rows = cursor.fetchall() or []

                return [
                    {
                        "id": row["id"],
                        "telegram_message_id": row["telegram_message_id"],
                        "group_id": row["group_id"],
                        "group_title": row["group_title"],
                        "sender_id": row["sender_id"],
                        "sender_name": row["sender_name"],
                        "message_text": row["message_text"],
                        "caption": row["caption"],
                        "has_image": bool(row.get("has_image")),
                        "image_description": row.get("image_description"),
                        "reply_to_message_id": row["reply_to_message_id"],
                        "message_date": row["message_date"],
                        "is_question": bool(row["is_question"]) if row["is_question"] is not None else None,
                        "question_confidence": float(row["question_confidence"]) if row["question_confidence"] is not None else None,
                    }
                    for row in rows
                ]
    except Exception as exc:
        logger.error("Ошибка поиска сообщений: %s", exc, exc_info=True)
        return []


def get_chain_for_message(
    group_id: int,
    telegram_message_id: int,
) -> List[Dict[str, Any]]:
    """
    Реконструировать цепочку обсуждения для сообщения.

    Использует тот же алгоритм, что и QAAnalyzer:
    1. Загружает сообщение по telegram_message_id.
    2. Выполняет кросс-дневное обогащение (вверх по reply + вниз к ответам).
    3. Строит индексы reply-дерева, находит корень.
    4. Собирает всю цепочку с nearby-сообщениями участников.

    Args:
        group_id: ID группы.
        telegram_message_id: Telegram message ID начального сообщения.

    Returns:
        Список словарей с полями сообщения (ChainMessage-совместимый формат).
    """
    from config import ai_settings
    from src.group_knowledge.qa_analyzer import (
        QAAnalyzer,
        THREAD_NEARBY_WINDOW_SECONDS,
        THREAD_MAX_NEARBY_MESSAGES,
    )

    # 1. Загрузить начальное сообщение.
    start_message = gk_db.get_message_by_telegram_id(group_id, telegram_message_id)
    if not start_message:
        return []

    # 2. Загрузить все сообщения за ту же дату (необходимо для nearby-расширения).
    from datetime import datetime, timezone

    msg_date = datetime.fromtimestamp(start_message.message_date, tz=timezone.utc)
    date_str = msg_date.strftime("%Y-%m-%d")
    day_messages = gk_db.get_messages_for_date(group_id, date_str)

    if not day_messages:
        day_messages = [start_message]

    # Убедиться, что начальное сообщение есть в списке.
    day_tg_ids = {m.telegram_message_id for m in day_messages}
    if start_message.telegram_message_id not in day_tg_ids:
        day_messages.append(start_message)

    # 3. Кросс-дневное обогащение (тот же код, что в QAAnalyzer._extract_thread_pairs).
    analyzer = QAAnalyzer()
    if ai_settings.GK_ANALYSIS_CROSS_DAY_ENRICHMENT:
        day_messages = analyzer._enrich_with_cross_day_context(day_messages)

    # 4. Построить индексы.
    msg_index = {msg.telegram_message_id: msg for msg in day_messages}
    children_index = QAAnalyzer._build_reply_children_index(day_messages)

    # 5. Найти корень цепочки, начиная с целевого сообщения.
    current = msg_index.get(telegram_message_id, start_message)
    visited = set()
    while current.reply_to_message_id and current.reply_to_message_id in msg_index:
        if current.telegram_message_id in visited:
            break
        visited.add(current.telegram_message_id)
        current = msg_index[current.reply_to_message_id]

    root_message = current

    # 6. Собрать цепочку (BFS по reply-дереву + nearby sequential messages).
    thread_messages = analyzer._collect_thread_messages(
        root_message,
        children_index,
        all_messages=day_messages,
    )

    # 7. Преобразовать в ChainMessage-формат.
    return [_message_to_chain_dict(msg) for msg in thread_messages]


def _message_to_chain_dict(msg: GroupMessage) -> Dict[str, Any]:
    """Преобразовать GroupMessage в ChainMessage-совместимый словарь."""
    return {
        "telegram_message_id": msg.telegram_message_id,
        "sender_name": msg.sender_name,
        "sender_id": msg.sender_id,
        "message_text": msg.message_text,
        "caption": msg.caption,
        "image_description": getattr(msg, "image_description", None),
        "has_image": bool(msg.has_image),
        "reply_to_message_id": msg.reply_to_message_id,
        "message_date": msg.message_date,
        "is_question": msg.is_question,
        "question_confidence": float(msg.question_confidence) if msg.question_confidence is not None else None,
    }
