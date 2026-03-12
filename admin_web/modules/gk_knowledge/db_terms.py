"""Слой работы с БД: термины (gk_terms).

Запросы к gk_terms и gk_term_validations для админ-панели.
Включает пагинацию, фильтрацию, экспертную валидацию и статистику.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Кэш групп с количеством терминов (TTL = 60 с)
# ---------------------------------------------------------------------------

_GK_GROUPS_JSON = Path(__file__).resolve().parents[3] / "config" / "gk_groups.json"
_GROUPS_CACHE: Dict[str, Any] = {"data": None, "ts": 0.0}
_GROUPS_CACHE_TTL = 60  # секунд


def _load_group_titles() -> Dict[int, str]:
    """Загрузить маппинг group_id → title из config/gk_groups.json."""
    titles: Dict[int, str] = {0: "Глобальные (legacy)"}
    try:
        if _GK_GROUPS_JSON.exists():
            data = json.loads(_GK_GROUPS_JSON.read_text(encoding="utf-8"))
            for g in data.get("groups", []):
                gid = g.get("id")
                gtitle = g.get("title")
                if gid is not None and gtitle:
                    titles[int(gid)] = gtitle
    except Exception as exc:
        logger.warning("Не удалось загрузить gk_groups.json: %s", exc)
    return titles


def invalidate_groups_cache() -> None:
    """Сбросить кэш групп (вызывать при изменении статуса терминов)."""
    _GROUPS_CACHE["data"] = None
    _GROUPS_CACHE["ts"] = 0.0


# ---------------------------------------------------------------------------
# Получение терминов для списка / валидации
# ---------------------------------------------------------------------------


def get_terms_for_validation(
    *,
    page: int = 1,
    page_size: int = 20,
    group_id: Optional[int] = None,
    has_definition: Optional[bool] = None,
    status: Optional[str] = None,
    search_text: Optional[str] = None,
    min_confidence: Optional[float] = None,
    expert_status: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    expert_telegram_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Получить термины с фильтрами и пагинацией.

    Args:
        page: Номер страницы (1-based).
        page_size: Размер страницы.
        group_id: Фильтр по группе (None = все).
        has_definition: Фильтр: True = с определением, False = без.
        status: Фильтр по статусу (pending / approved / rejected).
        search_text: Поиск подстроки в термине или определении.
        min_confidence: Минимальный порог confidence (0.0–1.0).
        expert_status: Фильтр по статусу экспертной валидации (approved / rejected / unvalidated).
        sort_by: Поле для сортировки.
        sort_order: Направление (asc / desc).
        expert_telegram_id: Telegram ID эксперта для получения его вердикта.

    Returns:
        Кортеж (список терминов, общее количество).
    """
    conditions: List[str] = []
    params: List[Any] = []

    if group_id is not None:
        conditions.append("t.group_id = %s")
        params.append(group_id)

    if has_definition is True:
        conditions.append("t.definition IS NOT NULL")
    elif has_definition is False:
        conditions.append("t.definition IS NULL")

    if status:
        conditions.append("t.status = %s")
        params.append(status)

    if search_text:
        normalized = search_text.strip()
        if normalized:
            escaped = (
                normalized
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append(
                "(t.term LIKE %s ESCAPE '\\\\' OR t.definition LIKE %s ESCAPE '\\\\')"
            )
            params.extend([f"%{escaped}%", f"%{escaped}%"])

    if min_confidence is not None:
        conditions.append("t.confidence IS NOT NULL AND t.confidence >= %s")
        params.append(float(min_confidence))

    if expert_status == "unvalidated":
        conditions.append("t.expert_status IS NULL")
    elif expert_status in ("approved", "rejected"):
        conditions.append("t.expert_status = %s")
        params.append(expert_status)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    allowed_sort_fields = {
        "created_at": "t.created_at",
        "term": "t.term",
        "confidence": "t.confidence",
        "id": "t.id",
        "group_id": "t.group_id",
        "status": "t.status",
    }
    sort_field = allowed_sort_fields.get(sort_by, "t.created_at")
    safe_order = "ASC" if sort_order.upper() == "ASC" else "DESC"

    offset = (page - 1) * page_size

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Общее количество + статистика за один запрос
                cursor.execute(
                    f"""SELECT COUNT(*) AS cnt,
                              SUM(t.status = 'pending')       AS pending,
                              SUM(t.status = 'approved')      AS approved,
                              SUM(t.status = 'rejected')      AS rejected,
                              SUM(t.definition IS NOT NULL)   AS with_definition,
                              SUM(t.definition IS NULL)       AS without_definition
                       FROM gk_terms t WHERE {where_clause}""",
                    tuple(params),
                )
                count_row = cursor.fetchone()
                total = int(count_row["cnt"]) if count_row else 0
                inline_stats = {
                    "total": total,
                    "pending": int(count_row["pending"] or 0) if count_row else 0,
                    "approved": int(count_row["approved"] or 0) if count_row else 0,
                    "rejected": int(count_row["rejected"] or 0) if count_row else 0,
                    "with_definition": int(count_row["with_definition"] or 0) if count_row else 0,
                    "without_definition": int(count_row["without_definition"] or 0) if count_row else 0,
                }

                # Данные страницы
                query = f"""
                    SELECT t.*
                    FROM gk_terms t
                    WHERE {where_clause}
                    ORDER BY {sort_field} {safe_order}
                    LIMIT %s OFFSET %s
                """
                cursor.execute(query, (*params, page_size, offset))
                rows = cursor.fetchall() or []

                # Подгрузить вердикт текущего эксперта (если указан)
                if expert_telegram_id and rows:
                    term_ids = [r["id"] for r in rows]
                    placeholders = ",".join(["%s"] * len(term_ids))
                    cursor.execute(
                        f"""
                        SELECT term_id, verdict, comment, edited_term, edited_definition
                        FROM gk_term_validations
                        WHERE term_id IN ({placeholders})
                          AND expert_telegram_id = %s
                        """,
                        (*term_ids, expert_telegram_id),
                    )
                    verdicts = {v["term_id"]: v for v in (cursor.fetchall() or [])}
                    for row in rows:
                        v = verdicts.get(row["id"])
                        if v:
                            row["existing_verdict"] = v["verdict"]
                            row["existing_comment"] = v.get("comment")
                        else:
                            row["existing_verdict"] = None
                            row["existing_comment"] = None
                else:
                    for row in rows:
                        row["existing_verdict"] = None
                        row["existing_comment"] = None

                return rows, total, inline_stats

    except Exception as exc:
        logger.error(
            "Ошибка получения терминов для валидации: %s", exc, exc_info=True,
        )
        return [], 0, {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "with_definition": 0, "without_definition": 0}


def get_term_detail(term_id: int) -> Optional[Dict[str, Any]]:
    """Получить детали термина по ID."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("SELECT * FROM gk_terms WHERE id = %s", (term_id,))
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения термина %d: %s", term_id, exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Экспертная валидация терминов
# ---------------------------------------------------------------------------


def store_term_verdict(
    *,
    term_id: int,
    expert_telegram_id: int,
    verdict: str,
    comment: Optional[str] = None,
    edited_term: Optional[str] = None,
    edited_definition: Optional[str] = None,
) -> int:
    """
    Сохранить вердикт эксперта по термину.

    При verdict='edited' обновляет term/definition в gk_terms.
    Автоматически обновляет expert_status и status в gk_terms.

    Returns:
        ID записи валидации.
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Сохранить вердикт
                cursor.execute(
                    """
                    INSERT INTO gk_term_validations
                        (term_id, expert_telegram_id, verdict, comment,
                         edited_term, edited_definition)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        verdict = VALUES(verdict),
                        comment = VALUES(comment),
                        edited_term = VALUES(edited_term),
                        edited_definition = VALUES(edited_definition),
                        updated_at = NOW()
                    """,
                    (term_id, expert_telegram_id, verdict, comment,
                     edited_term, edited_definition),
                )
                validation_id = cursor.lastrowid or 0

                # Обновить основную таблицу терминов
                effective_verdict = verdict
                if verdict == "edited":
                    effective_verdict = "approved"

                    # Применить правки к термину
                    update_parts = []
                    update_params: List[Any] = []
                    if edited_term:
                        update_parts.append("term = %s")
                        update_params.append(edited_term.strip().lower())
                    if edited_definition is not None:
                        update_parts.append("definition = %s")
                        update_params.append(edited_definition.strip() if edited_definition else None)

                    if update_parts:
                        update_parts.append("updated_at = NOW()")
                        update_params.append(term_id)
                        cursor.execute(
                            f"UPDATE gk_terms SET {', '.join(update_parts)} WHERE id = %s",
                            tuple(update_params),
                        )

                if effective_verdict in ("approved", "rejected"):
                    cursor.execute(
                        """
                        UPDATE gk_terms
                        SET status = %s,
                            expert_status = %s,
                            expert_validated_at = NOW()
                        WHERE id = %s
                        """,
                        (effective_verdict, effective_verdict, term_id),
                    )

                logger.info(
                    "Вердикт по термину сохранён: term_id=%d expert=%d verdict=%s",
                    term_id, expert_telegram_id, verdict,
                )
                return validation_id

    except Exception as exc:
        logger.error(
            "Ошибка сохранения вердикта по термину: term_id=%d expert=%d error=%s",
            term_id, expert_telegram_id, exc, exc_info=True,
        )
        raise


def get_term_verdict(
    term_id: int,
    expert_telegram_id: int,
) -> Optional[Dict[str, Any]]:
    """Получить существующий вердикт эксперта по термину."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM gk_term_validations
                    WHERE term_id = %s AND expert_telegram_id = %s
                    """,
                    (term_id, expert_telegram_id),
                )
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения вердикта по термину: %s", exc, exc_info=True)
        return None


def get_term_validation_history(term_id: int) -> List[Dict[str, Any]]:
    """Получить все экспертные вердикты по термину."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM gk_term_validations
                    WHERE term_id = %s
                    ORDER BY created_at DESC
                    """,
                    (term_id,),
                )
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения истории валидации термина: %s", exc, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Статистика
# ---------------------------------------------------------------------------


def get_term_validation_stats(
    group_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Получить агрегированную статистику по терминам.

    Returns:
        Словарь: total, pending, approved, rejected, with_definition, without_definition.
    """
    defaults = {
        "total": 0,
        "pending": 0,
        "approved": 0,
        "rejected": 0,
        "with_definition": 0,
        "without_definition": 0,
    }

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                group_filter = ""
                params: tuple = ()
                if group_id is not None:
                    group_filter = "WHERE group_id = %s"
                    params = (group_id,)

                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total,
                        SUM(status = 'pending') AS pending,
                        SUM(status = 'approved') AS approved,
                        SUM(status = 'rejected') AS rejected,
                        SUM(definition IS NOT NULL) AS with_definition,
                        SUM(definition IS NULL) AS without_definition
                    FROM gk_terms
                    {group_filter}
                    """,
                    params,
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "total": int(row.get("total") or 0),
                        "pending": int(row.get("pending") or 0),
                        "approved": int(row.get("approved") or 0),
                        "rejected": int(row.get("rejected") or 0),
                        "with_definition": int(row.get("with_definition") or 0),
                        "without_definition": int(row.get("without_definition") or 0),
                    }
                return defaults

    except Exception as exc:
        logger.error("Ошибка получения статистики терминов: %s", exc, exc_info=True)
        return defaults


def get_groups_with_term_counts() -> List[Dict[str, Any]]:
    """Получить список групп с количеством терминов.

    Результат кэшируется на 60 секунд. Названия групп берутся из
    config/gk_groups.json вместо дорогого коррелированного подзапроса
    к gk_messages.
    """
    now = time.monotonic()
    if _GROUPS_CACHE["data"] is not None and (now - _GROUPS_CACHE["ts"]) < _GROUPS_CACHE_TTL:
        return _GROUPS_CACHE["data"]  # type: ignore[return-value]

    try:
        titles = _load_group_titles()
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        t.group_id,
                        COUNT(*)                              AS total_terms,
                        SUM(t.status = 'pending')             AS pending_terms,
                        SUM(t.status = 'approved')            AS approved_terms,
                        SUM(t.status = 'rejected')            AS rejected_terms,
                        SUM(t.definition IS NOT NULL)         AS with_definition,
                        SUM(t.definition IS NULL)             AS without_definition
                    FROM gk_terms t
                    GROUP BY t.group_id
                    ORDER BY total_terms DESC
                    """
                )
                rows = cursor.fetchall() or []
                result = [
                    {
                        "group_id": r["group_id"],
                        "group_title": titles.get(r["group_id"], str(r["group_id"])),
                        "total_terms": int(r.get("total_terms") or 0),
                        "pending_terms": int(r.get("pending_terms") or 0),
                        "approved_terms": int(r.get("approved_terms") or 0),
                        "rejected_terms": int(r.get("rejected_terms") or 0),
                        "with_definition": int(r.get("with_definition") or 0),
                        "without_definition": int(r.get("without_definition") or 0),
                    }
                    for r in rows
                ]
                _GROUPS_CACHE["data"] = result
                _GROUPS_CACHE["ts"] = now
                return result
    except Exception as exc:
        logger.error("Ошибка получения групп с терминами: %s", exc, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Управление терминами
# ---------------------------------------------------------------------------


def add_term_manually(
    *,
    group_id: int,
    term: str,
    definition: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Добавить термин вручную.

    Returns:
        Словарь: {"term_id": int, "was_duplicate": bool} или None при ошибке.
    """
    normalized_term = term.strip().lower()
    if not normalized_term:
        logger.warning("Попытка добавить пустой термин")
        return None
    if len(normalized_term) > 100:
        logger.warning("Термин превышает 100 символов: '%s'", normalized_term[:30])
        return None
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_terms
                        (group_id, term, definition, source, status)
                    VALUES (%s, %s, %s, 'manual', 'pending')
                    ON DUPLICATE KEY UPDATE
                        definition = COALESCE(VALUES(definition), definition),
                        source = 'manual',
                        updated_at = NOW()
                    """,
                    (group_id, normalized_term, definition),
                )
                # rowcount: 1 = INSERT, 2 = UPDATE с изменением, 0 = дубликат без изменений.
                was_insert = cursor.rowcount == 1
                term_id = cursor.lastrowid
                # lastrowid ненадёжен при ON DUPLICATE KEY UPDATE —
                # запросить явно.
                if not term_id:
                    cursor.execute(
                        """
                        SELECT id FROM gk_terms
                        WHERE group_id = %s AND term = %s
                        """,
                        (group_id, normalized_term),
                    )
                    row = cursor.fetchone()
                    term_id = row["id"] if row else None
                logger.info(
                    "Термин %s вручную: id=%s term='%s' group=%d",
                    "добавлен" if was_insert else "обновлён",
                    term_id, normalized_term, group_id,
                )
                return {"term_id": term_id, "was_duplicate": not was_insert}
    except Exception as exc:
        logger.error(
            "Ошибка ручного добавления термина '%s': %s",
            term, exc, exc_info=True,
        )
        return None


def delete_term(term_id: int) -> bool:
    """
    Удалить термин (каскадно удалит вердикты через FK).

    Returns:
        True если удаление прошло.
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("DELETE FROM gk_terms WHERE id = %s", (term_id,))
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.info("Термин удалён: id=%d", term_id)
                return deleted
    except Exception as exc:
        logger.error("Ошибка удаления термина %d: %s", term_id, exc, exc_info=True)
        return False
