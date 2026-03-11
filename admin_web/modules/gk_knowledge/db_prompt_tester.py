"""Слой работы с БД: тестер промптов для Q&A-извлечения.

Управление промптами, сессиями, генерациями и A/B-сравнениями.
Scoring: Elo + Win Rate по аналогии с prompt_tester/backend/scoring.py.
"""

from __future__ import annotations

import json
import logging
import math
import random
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)

# Elo-параметры
_ELO_K = 32
_ELO_DEFAULT = 1500


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Рассчитать ожидаемый результат A по формуле Elo."""
    return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / 400.0))


def _apply_elo_update(
    ratings: Dict[int, float],
    prompt_a_id: int,
    prompt_b_id: int,
    score_a: float,
    score_b: float,
) -> None:
    """Обновить Elo для двух промптов по результату матча."""
    rating_a = ratings.get(prompt_a_id, float(_ELO_DEFAULT))
    rating_b = ratings.get(prompt_b_id, float(_ELO_DEFAULT))
    expected_a = _expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    ratings[prompt_a_id] = rating_a + _ELO_K * (score_a - expected_a)
    ratings[prompt_b_id] = rating_b + _ELO_K * (score_b - expected_b)


def _normalize_prompt_ids(raw_value: Any) -> List[int]:
    """Нормализовать prompt_ids из JSON-поля MySQL в список целых ID."""
    if raw_value is None:
        return []

    value = raw_value
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except Exception:
            return []

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return []

    if not isinstance(value, list):
        return []

    normalized: List[int] = []
    for item in value:
        try:
            normalized.append(int(item))
        except (TypeError, ValueError):
            continue
    return normalized


def estimate_comparisons(prompt_count: int, chains_count: int) -> int:
    """Рассчитать ожидаемое количество A/B-сравнений."""
    if prompt_count < 2 or chains_count <= 0:
        return 0
    return (prompt_count * (prompt_count - 1) // 2) * chains_count


def _build_shuffled_comparison_pairs(by_prompt: Dict[int, List[int]]) -> List[Tuple[int, int]]:
    """Собрать и перемешать blind-пары генераций между промптами."""
    prompt_ids = sorted(by_prompt.keys())
    if len(prompt_ids) < 2:
        return []

    pairs_to_insert: List[Tuple[int, int]] = []
    for i in range(len(prompt_ids)):
        for j in range(i + 1, len(prompt_ids)):
            gens_a = by_prompt[prompt_ids[i]]
            gens_b = by_prompt[prompt_ids[j]]
            prompt_pairs = list(zip(gens_a, gens_b))
            random.shuffle(prompt_pairs)
            for gen_a_id, gen_b_id in prompt_pairs:
                if random.random() > 0.5:
                    gen_a_id, gen_b_id = gen_b_id, gen_a_id
                pairs_to_insert.append((gen_a_id, gen_b_id))

    random.shuffle(pairs_to_insert)
    return pairs_to_insert


# ---------------------------------------------------------------------------
# Промпты CRUD
# ---------------------------------------------------------------------------


def get_prompts(active_only: bool = True) -> List[Dict[str, Any]]:
    """Получить список промптов."""
    cond = "WHERE is_active = 1" if active_only else ""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                      SELECT id, label,
                          system_prompt AS user_prompt,
                          system_prompt,
                          extraction_type,
                           model_name, temperature, created_by_telegram_id,
                           created_at, updated_at, is_active
                    FROM gk_prompt_tester_prompts
                    {cond}
                    ORDER BY id
                    """
                )
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения промптов: %s", exc, exc_info=True)
        return []


def create_prompt(
    *,
    label: str,
    user_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    extraction_type: str = "llm_inferred",
    model_name: Optional[str] = None,
    temperature: float = 0.3,
    created_by_telegram_id: Optional[int] = None,
) -> int:
    """Создать новый промпт. Возвращает ID."""
    prompt_text = (user_prompt if user_prompt is not None else system_prompt or "").strip()
    if not prompt_text:
        raise ValueError("Пользовательский промпт не должен быть пустым")

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_prompt_tester_prompts
                        (label, system_prompt, extraction_type, model_name, temperature, created_by_telegram_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (label, prompt_text, extraction_type, model_name, temperature, created_by_telegram_id),
                )
                return cursor.lastrowid or 0
    except Exception as exc:
        logger.error("Ошибка создания промпта: %s", exc, exc_info=True)
        raise


def update_prompt(
    prompt_id: int,
    *,
    label: Optional[str] = None,
    user_prompt: Optional[str] = None,
    system_prompt: Optional[str] = None,
    extraction_type: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
) -> bool:
    """Обновить существующий промпт."""
    fields: List[str] = []
    params: List[Any] = []
    if label is not None:
        fields.append("label = %s")
        params.append(label)
    prompt_text = user_prompt if user_prompt is not None else system_prompt
    if prompt_text is not None:
        fields.append("system_prompt = %s")
        params.append(prompt_text)
    if extraction_type is not None:
        fields.append("extraction_type = %s")
        params.append(extraction_type)
    if model_name is not None:
        fields.append("model_name = %s")
        params.append(model_name)
    if temperature is not None:
        fields.append("temperature = %s")
        params.append(temperature)
    if not fields:
        return False

    params.append(prompt_id)
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"UPDATE gk_prompt_tester_prompts SET {', '.join(fields)} WHERE id = %s",
                    tuple(params),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка обновления промпта %d: %s", prompt_id, exc, exc_info=True)
        raise


def delete_prompt(prompt_id: int) -> bool:
    """Деактивировать промпт (мягкое удаление)."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE gk_prompt_tester_prompts SET is_active = 0 WHERE id = %s",
                    (prompt_id,),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка удаления промпта %d: %s", prompt_id, exc, exc_info=True)
        raise


def get_prompt_by_id(prompt_id: int) -> Optional[Dict[str, Any]]:
    """Получить промпт по ID."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT * FROM gk_prompt_tester_prompts WHERE id = %s",
                    (prompt_id,),
                )
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения промпта %d: %s", prompt_id, exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Сессии
# ---------------------------------------------------------------------------


def get_source_pairs_for_session(
    *,
    limit: int,
    source_group_id: Optional[int] = None,
    source_date_from: Optional[str] = None,
    source_date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Получить исходные Q&A-цепочки для сессии тестирования.

    Приоритетно выбирает одобренные пары; если их недостаточно,
    добирает оставшиеся из общего пула.
    """

    if limit <= 0:
        return []

    def _fetch(approved_only: bool, exclude_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        conditions: List[str] = []
        params: List[Any] = []

        if approved_only:
            conditions.append("approved = 1")
        if source_group_id is not None:
            conditions.append("group_id = %s")
            params.append(source_group_id)
        if source_date_from:
            conditions.append("DATE(FROM_UNIXTIME(created_at)) >= %s")
            params.append(source_date_from)
        if source_date_to:
            conditions.append("DATE(FROM_UNIXTIME(created_at)) <= %s")
            params.append(source_date_to)
        if exclude_ids:
            placeholders = ", ".join(["%s"] * len(exclude_ids))
            conditions.append(f"id NOT IN ({placeholders})")
            params.extend(exclude_ids)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        remaining = max(0, limit - len(exclude_ids or []))

        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT id, question_text, answer_text,
                           question_message_id, answer_message_id,
                           group_id, extraction_type, confidence, created_at
                    FROM gk_qa_pairs
                    {where_clause}
                    ORDER BY RAND()
                    LIMIT %s
                    """,
                    tuple(params + [remaining]),
                )
                return cursor.fetchall() or []

    try:
        selected = _fetch(approved_only=True)
        if len(selected) >= limit:
            return selected[:limit]

        existing_ids = [int(row["id"]) for row in selected if row.get("id") is not None]
        selected.extend(_fetch(approved_only=False, exclude_ids=existing_ids))
        return selected[:limit]
    except Exception as exc:
        logger.error("Ошибка выбора исходных цепочек для сессии: %s", exc, exc_info=True)
        return []


def get_sessions() -> List[Dict[str, Any]]:
    """Получить список сессий тестирования."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute("""
                    SELECT
                        s.id, s.name, s.status, s.prompt_ids,
                        s.judge_mode, s.source_group_id,
                        s.source_date_from, s.source_date_to,
                        s.message_count,
                        s.created_by_telegram_id,
                        s.created_at, s.updated_at,
                        (SELECT COUNT(*) FROM gk_prompt_tester_generations g WHERE g.session_id = s.id) AS generation_count,
                        (SELECT COUNT(*) FROM gk_prompt_tester_comparisons c WHERE c.session_id = s.id AND c.winner IS NOT NULL) AS voted_count,
                        (SELECT COUNT(*) FROM gk_prompt_tester_comparisons c WHERE c.session_id = s.id) AS total_comparisons
                    FROM gk_prompt_tester_sessions s
                    ORDER BY s.created_at DESC
                """)
                rows = cursor.fetchall() or []
                for r in rows:
                    r["prompt_ids"] = _normalize_prompt_ids(r.get("prompt_ids"))
                    prompt_count = len(r.get("prompt_ids") or [])
                    chains_count = int(r.get("message_count") or 0)
                    r["prompt_count"] = prompt_count
                    r["chains_count"] = int(r.get("message_count") or 0)
                    expected_generations = prompt_count * chains_count
                    r["expected_generations"] = expected_generations
                    generation_count = int(r.get("generation_count") or 0)
                    if expected_generations > 0:
                        r["generation_progress_pct"] = round(
                            min(100.0, (generation_count / expected_generations) * 100.0),
                            1,
                        )
                    else:
                        r["generation_progress_pct"] = 0.0

                    r["expected_comparisons"] = estimate_comparisons(prompt_count, chains_count)

                    total_comparisons = int(r.get("total_comparisons") or 0)
                    voted_count = int(r.get("voted_count") or 0)
                    if total_comparisons > 0 and voted_count >= total_comparisons and r.get("status") == "judging":
                        r["status"] = "completed"
                return rows
    except Exception as exc:
        logger.error("Ошибка получения сессий: %s", exc, exc_info=True)
        return []


def create_session(
    *,
    name: str,
    prompt_ids: List[int],
    judge_mode: str = "human",
    source_group_id: Optional[int] = None,
    source_date_from: Optional[str] = None,
    source_date_to: Optional[str] = None,
    chains_count: int = 20,
    message_count: Optional[int] = None,
    source_messages_snapshot: Optional[List[int]] = None,
    prompts_config_snapshot: Optional[List[Dict[str, Any]]] = None,
    created_by_telegram_id: Optional[int] = None,
) -> int:
    """Создать новую сессию тестирования. Возвращает ID."""
    resolved_chains_count = int(message_count) if message_count is not None else int(chains_count)
    if resolved_chains_count < 1:
        resolved_chains_count = 1

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_prompt_tester_sessions
                        (name, prompt_ids, prompts_config_snapshot, judge_mode,
                         source_group_id, source_date_from, source_date_to,
                         message_count, source_messages_snapshot, created_by_telegram_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        name,
                        json.dumps(prompt_ids),
                        json.dumps(prompts_config_snapshot) if prompts_config_snapshot else None,
                        judge_mode,
                        source_group_id,
                        source_date_from,
                        source_date_to,
                        resolved_chains_count,
                        json.dumps(source_messages_snapshot) if source_messages_snapshot else None,
                        created_by_telegram_id,
                    ),
                )
                return cursor.lastrowid or 0
    except Exception as exc:
        logger.error("Ошибка создания сессии: %s", exc, exc_info=True)
        raise


def get_session_by_id(session_id: int) -> Optional[Dict[str, Any]]:
    """Получить сессию по ID с подсчётами."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        s.*,
                        (SELECT COUNT(*) FROM gk_prompt_tester_generations g WHERE g.session_id = s.id) AS generation_count,
                        (SELECT COUNT(*) FROM gk_prompt_tester_comparisons c WHERE c.session_id = s.id AND c.winner IS NOT NULL) AS voted_count,
                        (SELECT COUNT(*) FROM gk_prompt_tester_comparisons c WHERE c.session_id = s.id) AS total_comparisons
                    FROM gk_prompt_tester_sessions s
                    WHERE s.id = %s
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
                if row:
                    row["prompt_ids"] = _normalize_prompt_ids(row.get("prompt_ids"))
                if row and isinstance(row.get("prompts_config_snapshot"), str):
                    row["prompts_config_snapshot"] = json.loads(row["prompts_config_snapshot"])
                if row and isinstance(row.get("source_messages_snapshot"), str):
                    row["source_messages_snapshot"] = json.loads(row["source_messages_snapshot"])
                if row:
                    prompt_count = len(row.get("prompt_ids") or [])
                    chains_count = int(row.get("message_count") or 0)
                    row["prompt_count"] = prompt_count
                    row["chains_count"] = int(row.get("message_count") or 0)
                    expected_generations = prompt_count * chains_count
                    row["expected_generations"] = expected_generations
                    generation_count = int(row.get("generation_count") or 0)
                    if expected_generations > 0:
                        row["generation_progress_pct"] = round(
                            min(100.0, (generation_count / expected_generations) * 100.0),
                            1,
                        )
                    else:
                        row["generation_progress_pct"] = 0.0

                    row["expected_comparisons"] = estimate_comparisons(prompt_count, chains_count)
                    total_comparisons = int(row.get("total_comparisons") or 0)
                    voted_count = int(row.get("voted_count") or 0)
                    if total_comparisons > 0 and voted_count >= total_comparisons and row.get("status") == "judging":
                        row["status"] = "completed"
                return row
    except Exception as exc:
        logger.error("Ошибка получения сессии %d: %s", session_id, exc, exc_info=True)
        return None


def update_session_status(session_id: int, status: str) -> bool:
    """Обновить статус сессии."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE gk_prompt_tester_sessions SET status = %s WHERE id = %s",
                    (status, session_id),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка обновления статуса сессии %d: %s", session_id, exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Генерации
# ---------------------------------------------------------------------------


def save_generation(
    *,
    session_id: int,
    prompt_id: int,
    question_text: str,
    answer_text: str,
    confidence: Optional[float] = None,
    extraction_type: Optional[str] = None,
    raw_llm_response: Optional[str] = None,
) -> int:
    """Сохранить сгенерированную Q&A-пару. Возвращает ID."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_prompt_tester_generations
                        (session_id, prompt_id, question_text, answer_text,
                         confidence, extraction_type, raw_llm_response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (session_id, prompt_id, question_text, answer_text,
                     confidence, extraction_type, raw_llm_response),
                )
                return cursor.lastrowid or 0
    except Exception as exc:
        logger.error("Ошибка сохранения генерации: %s", exc, exc_info=True)
        raise


def get_generations_for_session(session_id: int) -> List[Dict[str, Any]]:
    """Получить все генерации для сессии."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT g.*, p.label AS prompt_label
                    FROM gk_prompt_tester_generations g
                    LEFT JOIN gk_prompt_tester_prompts p ON p.id = g.prompt_id
                    WHERE g.session_id = %s
                    ORDER BY g.prompt_id, g.id
                    """,
                    (session_id,),
                )
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения генераций сессии %d: %s", session_id, exc, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Сравнения и голосование
# ---------------------------------------------------------------------------


def create_comparisons_for_session(session_id: int) -> int:
    """
    Создать попарные сравнения между генерациями разных промптов.

    Для каждого Q&A-спота (одинаковый порядковый номер) создаём пару (A, B)
    со случайным порядком. Возвращает количество созданных сравнений.
    """
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получить генерации, сгруппированные по промпту
                cursor.execute(
                    """
                    SELECT id, prompt_id
                    FROM gk_prompt_tester_generations
                    WHERE session_id = %s
                    ORDER BY prompt_id, id
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall() or []

                # Группировать по prompt_id
                by_prompt: Dict[int, List[int]] = {}
                for r in rows:
                    pid = r["prompt_id"]
                    by_prompt.setdefault(pid, []).append(r["id"])

                prompt_ids = sorted(by_prompt.keys())
                if len(prompt_ids) < 2:
                    return 0

                # Создать и перемешать blind-пары между промптами
                count = 0
                for gen_a_id, gen_b_id in _build_shuffled_comparison_pairs(by_prompt):
                    cursor.execute(
                        """
                        INSERT INTO gk_prompt_tester_comparisons
                            (session_id, generation_a_id, generation_b_id)
                        VALUES (%s, %s, %s)
                        """,
                        (session_id, gen_a_id, gen_b_id),
                    )
                    count += 1

                return count

    except Exception as exc:
        logger.error("Ошибка создания сравнений для сессии %d: %s", session_id, exc, exc_info=True)
        return 0


def get_next_comparison(
    session_id: int,
    voter_telegram_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Получить следующее неоценённое сравнение для голосования."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.id AS comparison_id,
                        c.generation_a_id, c.generation_b_id,
                        ga.prompt_id AS prompt_a_id,
                        ga.question_text AS question_a, ga.answer_text AS answer_a,
                        ga.confidence AS confidence_a,
                        gb.prompt_id AS prompt_b_id,
                        gb.question_text AS question_b, gb.answer_text AS answer_b,
                        gb.confidence AS confidence_b
                    FROM gk_prompt_tester_comparisons c
                    JOIN gk_prompt_tester_generations ga ON ga.id = c.generation_a_id
                    JOIN gk_prompt_tester_generations gb ON gb.id = c.generation_b_id
                    WHERE c.session_id = %s AND c.winner IS NULL
                    ORDER BY RAND()
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                source_pair_id: Optional[int] = None
                try:
                    cursor.execute(
                        """
                        SELECT source_messages_snapshot
                        FROM gk_prompt_tester_sessions
                        WHERE id = %s
                        """,
                        (session_id,),
                    )
                    session_row = cursor.fetchone() or {}
                    source_snapshot = _normalize_prompt_ids(session_row.get("source_messages_snapshot"))

                    cursor.execute(
                        """
                        SELECT id, prompt_id
                        FROM gk_prompt_tester_generations
                        WHERE session_id = %s
                        ORDER BY prompt_id, id
                        """,
                        (session_id,),
                    )
                    generation_rows = cursor.fetchall() or []

                    by_prompt: Dict[int, List[int]] = {}
                    for generation_row in generation_rows:
                        prompt_id = int(generation_row.get("prompt_id") or 0)
                        generation_id = int(generation_row.get("id") or 0)
                        if prompt_id <= 0 or generation_id <= 0:
                            continue
                        by_prompt.setdefault(prompt_id, []).append(generation_id)

                    prompt_a_id = int(row.get("prompt_a_id") or 0)
                    prompt_b_id = int(row.get("prompt_b_id") or 0)
                    generation_a_id = int(row.get("generation_a_id") or 0)
                    generation_b_id = int(row.get("generation_b_id") or 0)

                    slot_a: Optional[int] = None
                    slot_b: Optional[int] = None
                    if prompt_a_id in by_prompt:
                        try:
                            slot_a = by_prompt[prompt_a_id].index(generation_a_id)
                        except ValueError:
                            slot_a = None
                    if prompt_b_id in by_prompt:
                        try:
                            slot_b = by_prompt[prompt_b_id].index(generation_b_id)
                        except ValueError:
                            slot_b = None

                    slot_index = slot_a if slot_a is not None and slot_a == slot_b else slot_a
                    if slot_index is not None and 0 <= slot_index < len(source_snapshot):
                        source_pair_id = int(source_snapshot[slot_index])
                except Exception as exc:
                    logger.debug(
                        "Не удалось определить source_pair_id для сравнения: session=%d comparison=%s error=%s",
                        session_id,
                        row.get("comparison_id"),
                        exc,
                    )

                # Подсчёт прогресса
                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN winner IS NOT NULL THEN 1 ELSE 0 END) AS voted
                    FROM gk_prompt_tester_comparisons
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                progress = cursor.fetchone() or {}

                return {
                    **row,
                    "source_pair_id": source_pair_id,
                    "progress_total": progress.get("total", 0),
                    "progress_voted": progress.get("voted", 0),
                }

    except Exception as exc:
        logger.error("Ошибка получения сравнения для сессии %d: %s", session_id, exc, exc_info=True)
        return None


def submit_vote(
    comparison_id: int,
    winner: str,
    expected_session_id: Optional[int] = None,
    voter_telegram_id: Optional[int] = None,
    voter_type: str = "human",
) -> bool:
    """Сохранить голос за сравнение."""
    if winner not in ("a", "b", "tie", "skip"):
        return False

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT session_id
                    FROM gk_prompt_tester_comparisons
                    WHERE id = %s
                    """,
                    (comparison_id,),
                )
                comparison_row = cursor.fetchone() or {}
                session_id = comparison_row.get("session_id")
                if expected_session_id is not None and session_id != expected_session_id:
                    return False

                cursor.execute(
                    """
                    UPDATE gk_prompt_tester_comparisons
                    SET winner = %s, voter_telegram_id = %s, voter_type = %s, voted_at = NOW()
                    WHERE id = %s AND winner IS NULL
                    """,
                    (winner, voter_telegram_id, voter_type, comparison_id),
                )
                updated = cursor.rowcount > 0
                if not updated or not session_id:
                    return updated

                cursor.execute(
                    """
                    SELECT COUNT(*) AS remaining
                    FROM gk_prompt_tester_comparisons
                    WHERE session_id = %s AND winner IS NULL
                    """,
                    (session_id,),
                )
                remaining = int((cursor.fetchone() or {}).get("remaining") or 0)
                if remaining == 0:
                    cursor.execute(
                        """
                        UPDATE gk_prompt_tester_sessions
                        SET status = 'completed'
                        WHERE id = %s AND status <> 'abandoned'
                        """,
                        (session_id,),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE gk_prompt_tester_sessions
                        SET status = 'judging'
                        WHERE id = %s AND status = 'generating'
                        """,
                        (session_id,),
                    )
                return updated

    except Exception as exc:
        logger.error("Ошибка голосования по сравнению %d: %s", comparison_id, exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Результаты и Elo-скоринг
# ---------------------------------------------------------------------------


def get_session_results(session_id: int) -> Dict[str, Any]:
    """Рассчитать результаты сессии: Elo + Win Rate по промптам."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                # Получить все голоса
                cursor.execute(
                    """
                    SELECT
                        c.winner, c.voter_type,
                        ga.prompt_id AS prompt_a_id,
                        gb.prompt_id AS prompt_b_id
                    FROM gk_prompt_tester_comparisons c
                    JOIN gk_prompt_tester_generations ga ON ga.id = c.generation_a_id
                    JOIN gk_prompt_tester_generations gb ON gb.id = c.generation_b_id
                    WHERE c.session_id = %s AND c.winner IS NOT NULL
                    """,
                    (session_id,),
                )
                votes = cursor.fetchall() or []

                # Получить названия промптов
                cursor.execute(
                    """
                    SELECT DISTINCT g.prompt_id, p.label
                    FROM gk_prompt_tester_generations g
                    JOIN gk_prompt_tester_prompts p ON p.id = g.prompt_id
                    WHERE g.session_id = %s
                    """,
                    (session_id,),
                )
                prompt_labels = {r["prompt_id"]: r["label"] for r in (cursor.fetchall() or [])}

                # Рассчитать Elo и Win Rate
                prompt_ids = sorted(prompt_labels.keys())
                elo: Dict[int, float] = {pid: _ELO_DEFAULT for pid in prompt_ids}
                wins: Dict[int, int] = {pid: 0 for pid in prompt_ids}
                losses: Dict[int, int] = {pid: 0 for pid in prompt_ids}
                ties: Dict[int, int] = {pid: 0 for pid in prompt_ids}
                skips: Dict[int, int] = {pid: 0 for pid in prompt_ids}

                for vote in votes:
                    pa = vote["prompt_a_id"]
                    pb = vote["prompt_b_id"]
                    w = vote["winner"]

                    if w == "skip":
                        skips[pa] = skips.get(pa, 0) + 1
                        skips[pb] = skips.get(pb, 0) + 1
                        continue

                    if w == "a":
                        wins[pa] = wins.get(pa, 0) + 1
                        losses[pb] = losses.get(pb, 0) + 1
                        sa, sb = 1.0, 0.0
                    elif w == "b":
                        wins[pb] = wins.get(pb, 0) + 1
                        losses[pa] = losses.get(pa, 0) + 1
                        sa, sb = 0.0, 1.0
                    else:  # tie
                        ties[pa] = ties.get(pa, 0) + 1
                        ties[pb] = ties.get(pb, 0) + 1
                        sa, sb = 0.5, 0.5

                    _apply_elo_update(elo, pa, pb, sa, sb)

                results = []
                for pid in prompt_ids:
                    total_matches = wins[pid] + losses[pid] + ties[pid]
                    win_rate = ((wins[pid] + ties[pid] * 0.5) / total_matches * 100) if total_matches > 0 else 0
                    score = wins[pid] + ties[pid] * 0.5
                    loss_rate = (losses[pid] / total_matches * 100) if total_matches > 0 else 0
                    results.append({
                        "prompt_id": pid,
                        "prompt_label": prompt_labels.get(pid, f"Промпт #{pid}"),
                        "elo": round(elo[pid]),
                        "elo_delta": round(elo[pid] - _ELO_DEFAULT),
                        "wins": wins[pid],
                        "losses": losses[pid],
                        "ties": ties[pid],
                        "skips": skips[pid],
                        "matches": total_matches,
                        "score": round(score, 2),
                        "win_rate": round(win_rate, 1),
                        "loss_rate": round(loss_rate, 1),
                    })

                results.sort(key=lambda x: x["elo"], reverse=True)

                return {
                    "prompt_results": results,
                    "total_votes": len(votes),
                }

    except Exception as exc:
        logger.error("Ошибка расчёта результатов сессии %d: %s", session_id, exc, exc_info=True)
        return {"prompt_results": [], "total_votes": 0}


def get_global_prompt_stats() -> Dict[str, Any]:
    """Вернуть агрегированную статистику Prompt Tester по всем сессиям."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.winner,
                        ga.prompt_id AS prompt_a_id,
                        gb.prompt_id AS prompt_b_id
                    FROM gk_prompt_tester_comparisons c
                    JOIN gk_prompt_tester_generations ga ON ga.id = c.generation_a_id
                    JOIN gk_prompt_tester_generations gb ON gb.id = c.generation_b_id
                    JOIN gk_prompt_tester_sessions s ON s.id = c.session_id
                    WHERE c.winner IS NOT NULL
                      AND s.status <> 'abandoned'
                    """
                )
                votes = cursor.fetchall() or []

                cursor.execute(
                    """
                    SELECT
                        p.id AS prompt_id,
                        p.label,
                        p.is_active,
                        COUNT(DISTINCT g.session_id) AS sessions_count
                    FROM gk_prompt_tester_prompts p
                    LEFT JOIN gk_prompt_tester_generations g ON g.prompt_id = p.id
                    GROUP BY p.id, p.label, p.is_active
                    ORDER BY p.id
                    """
                )
                prompt_rows = cursor.fetchall() or []

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS sessions_total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS sessions_completed,
                        SUM(CASE WHEN status = 'judging' THEN 1 ELSE 0 END) AS sessions_judging,
                        SUM(CASE WHEN status = 'generating' THEN 1 ELSE 0 END) AS sessions_generating
                    FROM gk_prompt_tester_sessions
                    WHERE status <> 'abandoned'
                    """
                )
                summary_row = cursor.fetchone() or {}

                all_prompt_ids = sorted({
                    int(row.get("prompt_id") or 0)
                    for row in prompt_rows
                    if int(row.get("prompt_id") or 0) > 0
                })

                elo: Dict[int, float] = {pid: float(_ELO_DEFAULT) for pid in all_prompt_ids}
                wins: Dict[int, int] = {pid: 0 for pid in all_prompt_ids}
                losses: Dict[int, int] = {pid: 0 for pid in all_prompt_ids}
                ties: Dict[int, int] = {pid: 0 for pid in all_prompt_ids}
                skips: Dict[int, int] = {pid: 0 for pid in all_prompt_ids}

                voted_matches = 0
                skipped_matches = 0

                for vote in votes:
                    winner = vote.get("winner")
                    prompt_a_id = int(vote.get("prompt_a_id") or 0)
                    prompt_b_id = int(vote.get("prompt_b_id") or 0)
                    if prompt_a_id <= 0 or prompt_b_id <= 0:
                        continue

                    for pid in (prompt_a_id, prompt_b_id):
                        if pid not in elo:
                            elo[pid] = float(_ELO_DEFAULT)
                            wins[pid] = 0
                            losses[pid] = 0
                            ties[pid] = 0
                            skips[pid] = 0

                    if winner == "skip":
                        skips[prompt_a_id] += 1
                        skips[prompt_b_id] += 1
                        skipped_matches += 1
                        continue

                    voted_matches += 1
                    if winner == "a":
                        wins[prompt_a_id] += 1
                        losses[prompt_b_id] += 1
                        _apply_elo_update(elo, prompt_a_id, prompt_b_id, 1.0, 0.0)
                    elif winner == "b":
                        wins[prompt_b_id] += 1
                        losses[prompt_a_id] += 1
                        _apply_elo_update(elo, prompt_a_id, prompt_b_id, 0.0, 1.0)
                    else:
                        ties[prompt_a_id] += 1
                        ties[prompt_b_id] += 1
                        _apply_elo_update(elo, prompt_a_id, prompt_b_id, 0.5, 0.5)

                row_by_prompt_id = {
                    int(row.get("prompt_id") or 0): row
                    for row in prompt_rows
                }

                prompt_stats: List[Dict[str, Any]] = []
                for prompt_id in sorted(elo.keys()):
                    row = row_by_prompt_id.get(prompt_id, {})
                    total_matches = wins[prompt_id] + losses[prompt_id] + ties[prompt_id]
                    win_rate = (wins[prompt_id] + ties[prompt_id] * 0.5) / total_matches if total_matches > 0 else 0.0
                    prompt_stats.append(
                        {
                            "prompt_id": prompt_id,
                            "label": row.get("label") or f"Промпт #{prompt_id}",
                            "is_active": bool(row.get("is_active", 1)),
                            "sessions_count": int(row.get("sessions_count") or 0),
                            "elo": round(float(elo[prompt_id]), 2),
                            "elo_delta": round(float(elo[prompt_id]) - _ELO_DEFAULT, 2),
                            "wins": int(wins[prompt_id]),
                            "losses": int(losses[prompt_id]),
                            "ties": int(ties[prompt_id]),
                            "skips": int(skips[prompt_id]),
                            "matches": int(total_matches),
                            "win_rate": round(win_rate, 4),
                        }
                    )

                prompt_stats.sort(key=lambda item: float(item.get("elo") or 0.0), reverse=True)

                return {
                    "summary": {
                        "sessions_total": int(summary_row.get("sessions_total") or 0),
                        "sessions_completed": int(summary_row.get("sessions_completed") or 0),
                        "sessions_judging": int(summary_row.get("sessions_judging") or 0),
                        "sessions_generating": int(summary_row.get("sessions_generating") or 0),
                        "voted_matches": voted_matches,
                        "skipped_matches": skipped_matches,
                        "prompts_total": len(prompt_stats),
                    },
                    "prompts": prompt_stats,
                }

    except Exception as exc:
        logger.error("Ошибка получения агрегированной статистики промптов: %s", exc, exc_info=True)
        return {
            "summary": {
                "sessions_total": 0,
                "sessions_completed": 0,
                "sessions_judging": 0,
                "sessions_generating": 0,
                "voted_matches": 0,
                "skipped_matches": 0,
                "prompts_total": 0,
            },
            "prompts": [],
        }
