"""Слой работы с БД: отдельный blind image prompt tester для GK.

Поддерживает:
- CRUD промптов описания изображений
- Сессии сравнения
- Генерации описаний
- Слепые A/B сравнения и голосование
- Результаты (Elo + метрики)
"""

from __future__ import annotations

import json
import logging
import math
import random
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)

_ELO_K = 32.0
_ELO_DEFAULT = 1500.0


def estimate_comparisons(prompt_count: int, image_count: int) -> int:
    """Рассчитать ожидаемое количество A/B-сравнений для image-сессии."""
    if prompt_count < 2 or image_count <= 0:
        return 0
    return (prompt_count * (prompt_count - 1) // 2) * image_count


def _normalize_ids_json(raw_value: Any) -> List[int]:
    """Нормализовать JSON-массив id в список целых."""
    if raw_value is None:
        return []

    value = raw_value
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
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

    result: List[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Ожидаемый результат A по Elo."""
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def _apply_elo_update(rating_a: float, rating_b: float, score_a: float) -> Tuple[float, float]:
    """Обновить Elo A/B после одного сравнения."""
    expected_a = _expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a
    new_a = rating_a + _ELO_K * (score_a - expected_a)
    new_b = rating_b + _ELO_K * (score_b - expected_b)
    return new_a, new_b


def _compute_results(
    votes: List[Dict[str, Any]],
    prompt_labels: Dict[int, str],
) -> List[Dict[str, Any]]:
    """Подсчитать результаты по голосам (Elo + базовые метрики)."""
    prompt_ids = sorted(prompt_labels.keys())
    elo = {pid: float(_ELO_DEFAULT) for pid in prompt_ids}
    wins = {pid: 0 for pid in prompt_ids}
    losses = {pid: 0 for pid in prompt_ids}
    ties = {pid: 0 for pid in prompt_ids}
    skips = {pid: 0 for pid in prompt_ids}

    for vote in votes:
        pa = int(vote.get("prompt_a_id") or 0)
        pb = int(vote.get("prompt_b_id") or 0)
        winner = str(vote.get("winner") or "")
        if pa <= 0 or pb <= 0:
            continue
        if pa not in elo:
            elo[pa] = float(_ELO_DEFAULT)
            wins[pa] = 0
            losses[pa] = 0
            ties[pa] = 0
            skips[pa] = 0
            prompt_labels[pa] = prompt_labels.get(pa) or f"Промпт #{pa}"
        if pb not in elo:
            elo[pb] = float(_ELO_DEFAULT)
            wins[pb] = 0
            losses[pb] = 0
            ties[pb] = 0
            skips[pb] = 0
            prompt_labels[pb] = prompt_labels.get(pb) or f"Промпт #{pb}"

        if winner == "skip":
            skips[pa] += 1
            skips[pb] += 1
            continue

        score_a = 0.5
        if winner == "a":
            wins[pa] += 1
            losses[pb] += 1
            score_a = 1.0
        elif winner == "b":
            wins[pb] += 1
            losses[pa] += 1
            score_a = 0.0
        else:
            ties[pa] += 1
            ties[pb] += 1
            score_a = 0.5

        new_a, new_b = _apply_elo_update(elo[pa], elo[pb], score_a)
        elo[pa] = new_a
        elo[pb] = new_b

    rows: List[Dict[str, Any]] = []
    for pid in sorted(elo.keys()):
        matches = wins[pid] + losses[pid] + ties[pid]
        win_rate = (wins[pid] + ties[pid] * 0.5) / matches if matches > 0 else 0.0
        rows.append(
            {
                "prompt_id": pid,
                "label": prompt_labels.get(pid) or f"Промпт #{pid}",
                "elo": round(elo[pid], 2),
                "elo_delta": round(elo[pid] - _ELO_DEFAULT, 2),
                "wins": wins[pid],
                "losses": losses[pid],
                "ties": ties[pid],
                "skips": skips[pid],
                "matches": matches,
                "score": round(wins[pid] + ties[pid] * 0.5, 2),
                "win_rate": round(win_rate, 4),
            }
        )

    rows.sort(key=lambda item: float(item.get("elo") or 0.0), reverse=True)
    return rows


def _build_shuffled_image_comparisons(by_image: Dict[int, Dict[int, int]]) -> List[Tuple[int, int, int]]:
    """Собрать и перемешать blind-сравнения для каждой картинки."""
    comparisons: List[Tuple[int, int, int]] = []

    for image_queue_id, prompt_to_gen in by_image.items():
        prompt_ids = sorted(prompt_to_gen.keys())
        if len(prompt_ids) < 2:
            continue

        image_pairs: List[Tuple[int, int, int]] = []
        for idx in range(len(prompt_ids)):
            for jdx in range(idx + 1, len(prompt_ids)):
                gen_a = prompt_to_gen[prompt_ids[idx]]
                gen_b = prompt_to_gen[prompt_ids[jdx]]
                if random.random() > 0.5:
                    gen_a, gen_b = gen_b, gen_a
                image_pairs.append((image_queue_id, gen_a, gen_b))

        random.shuffle(image_pairs)
        comparisons.extend(image_pairs)

    random.shuffle(comparisons)
    return comparisons


# ---------------------------------------------------------------------------
# Промпты
# ---------------------------------------------------------------------------


def get_prompts(active_only: bool = True) -> List[Dict[str, Any]]:
    """Получить список image-промптов."""
    cond = "WHERE is_active = 1" if active_only else ""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT id, label, prompt_text, model_name, temperature,
                           created_by_telegram_id, created_at, updated_at, is_active
                    FROM gk_image_prompt_tester_prompts
                    {cond}
                    ORDER BY id
                    """
                )
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения image-промптов: %s", exc, exc_info=True)
        return []


def get_prompt_by_id(prompt_id: int) -> Optional[Dict[str, Any]]:
    """Получить image-промпт по id."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT * FROM gk_image_prompt_tester_prompts WHERE id = %s",
                    (prompt_id,),
                )
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения image-промпта %d: %s", prompt_id, exc, exc_info=True)
        return None


def create_prompt(
    *,
    label: str,
    prompt_text: str,
    model_name: Optional[str] = None,
    temperature: float = 0.3,
    created_by_telegram_id: Optional[int] = None,
) -> int:
    """Создать image-промпт."""
    if not str(prompt_text or "").strip():
        raise ValueError("Промпт не должен быть пустым")

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_image_prompt_tester_prompts
                        (label, prompt_text, model_name, temperature, created_by_telegram_id)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (label, prompt_text, model_name, temperature, created_by_telegram_id),
                )
                return int(cursor.lastrowid or 0)
    except Exception as exc:
        logger.error("Ошибка создания image-промпта: %s", exc, exc_info=True)
        raise


def update_prompt(
    prompt_id: int,
    *,
    label: Optional[str] = None,
    prompt_text: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
) -> bool:
    """Обновить image-промпт."""
    fields: List[str] = []
    params: List[Any] = []

    if label is not None:
        fields.append("label = %s")
        params.append(label)
    if prompt_text is not None:
        fields.append("prompt_text = %s")
        params.append(prompt_text)
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
                    f"UPDATE gk_image_prompt_tester_prompts SET {', '.join(fields)} WHERE id = %s",
                    tuple(params),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка обновления image-промпта %d: %s", prompt_id, exc, exc_info=True)
        raise


def delete_prompt(prompt_id: int) -> bool:
    """Мягко деактивировать image-промпт."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE gk_image_prompt_tester_prompts SET is_active = 0 WHERE id = %s",
                    (prompt_id,),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка деактивации image-промпта %d: %s", prompt_id, exc, exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Исходные изображения
# ---------------------------------------------------------------------------


def get_source_images_for_session(
    *,
    limit: int,
    source_group_id: Optional[int] = None,
    source_date_from: Optional[str] = None,
    source_date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Получить изображения для сессии image prompt tester."""
    if limit <= 0:
        return []

    conditions = ["iq.status = 2", "iq.image_path IS NOT NULL", "iq.image_path <> ''"]
    params: List[Any] = []

    if source_group_id is not None:
        conditions.append("gm.group_id = %s")
        params.append(source_group_id)
    if source_date_from:
        conditions.append("DATE(FROM_UNIXTIME(iq.created_at)) >= %s")
        params.append(source_date_from)
    if source_date_to:
        conditions.append("DATE(FROM_UNIXTIME(iq.created_at)) <= %s")
        params.append(source_date_to)

    where_clause = "WHERE " + " AND ".join(conditions)

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        iq.id,
                        iq.message_id,
                        iq.image_path,
                        iq.created_at,
                        gm.group_id,
                        gm.sender_name,
                        gm.image_description AS source_image_description
                    FROM gk_image_queue iq
                    LEFT JOIN gk_messages gm ON gm.id = iq.message_id
                    {where_clause}
                    ORDER BY RAND()
                    LIMIT %s
                    """,
                    tuple(params + [limit]),
                )
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка выбора исходных изображений для сессии: %s", exc, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Сессии
# ---------------------------------------------------------------------------


def create_session(
    *,
    name: str,
    prompt_ids: List[int],
    source_group_id: Optional[int],
    source_date_from: Optional[str],
    source_date_to: Optional[str],
    image_count: int,
    source_image_ids_snapshot: List[int],
    prompts_config_snapshot: List[Dict[str, Any]],
    created_by_telegram_id: Optional[int],
) -> int:
    """Создать сессию image prompt tester."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_image_prompt_tester_sessions
                        (name, prompt_ids, prompts_config_snapshot,
                         source_group_id, source_date_from, source_date_to,
                         image_count, source_image_ids_snapshot, created_by_telegram_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        name,
                        json.dumps(prompt_ids),
                        json.dumps(prompts_config_snapshot),
                        source_group_id,
                        source_date_from,
                        source_date_to,
                        image_count,
                        json.dumps(source_image_ids_snapshot),
                        created_by_telegram_id,
                    ),
                )
                return int(cursor.lastrowid or 0)
    except Exception as exc:
        logger.error("Ошибка создания image-сессии: %s", exc, exc_info=True)
        raise


def get_sessions() -> List[Dict[str, Any]]:
    """Получить список image-сессий."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        s.id, s.name, s.status, s.prompt_ids,
                        s.source_group_id, s.source_date_from, s.source_date_to,
                        s.image_count, s.created_by_telegram_id,
                        s.created_at, s.updated_at,
                        (SELECT COUNT(*) FROM gk_image_prompt_tester_generations g WHERE g.session_id = s.id) AS generation_count,
                        (SELECT COUNT(*) FROM gk_image_prompt_tester_comparisons c WHERE c.session_id = s.id) AS total_comparisons,
                        (SELECT COUNT(*) FROM gk_image_prompt_tester_comparisons c WHERE c.session_id = s.id AND c.winner IS NOT NULL) AS voted_count
                    FROM gk_image_prompt_tester_sessions s
                    ORDER BY s.created_at DESC
                    """
                )
                rows = cursor.fetchall() or []

                for row in rows:
                    row["prompt_ids"] = _normalize_ids_json(row.get("prompt_ids"))
                    prompt_count = len(row.get("prompt_ids") or [])
                    image_count = int(row.get("image_count") or 0)
                    expected_generations = prompt_count * image_count
                    row["prompt_count"] = prompt_count
                    row["expected_generations"] = expected_generations
                    generation_count = int(row.get("generation_count") or 0)
                    row["generation_progress_pct"] = (
                        round(min(100.0, (generation_count / expected_generations) * 100.0), 1)
                        if expected_generations > 0
                        else 0.0
                    )
                    row["expected_comparisons"] = estimate_comparisons(prompt_count, image_count)

                    total_comparisons = int(row.get("total_comparisons") or 0)
                    voted_count = int(row.get("voted_count") or 0)
                    if total_comparisons > 0 and voted_count >= total_comparisons and row.get("status") == "judging":
                        row["status"] = "completed"

                return rows
    except Exception as exc:
        logger.error("Ошибка получения image-сессий: %s", exc, exc_info=True)
        return []


def get_session_by_id(session_id: int) -> Optional[Dict[str, Any]]:
    """Получить image-сессию по id."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        s.*,
                        (SELECT COUNT(*) FROM gk_image_prompt_tester_generations g WHERE g.session_id = s.id) AS generation_count,
                        (SELECT COUNT(*) FROM gk_image_prompt_tester_comparisons c WHERE c.session_id = s.id) AS total_comparisons,
                        (SELECT COUNT(*) FROM gk_image_prompt_tester_comparisons c WHERE c.session_id = s.id AND c.winner IS NOT NULL) AS voted_count
                    FROM gk_image_prompt_tester_sessions s
                    WHERE s.id = %s
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                row["prompt_ids"] = _normalize_ids_json(row.get("prompt_ids"))
                snapshot = row.get("prompts_config_snapshot")
                if isinstance(snapshot, str):
                    try:
                        row["prompts_config_snapshot"] = json.loads(snapshot)
                    except json.JSONDecodeError:
                        row["prompts_config_snapshot"] = []

                source_snapshot = row.get("source_image_ids_snapshot")
                if isinstance(source_snapshot, str):
                    try:
                        row["source_image_ids_snapshot"] = json.loads(source_snapshot)
                    except json.JSONDecodeError:
                        row["source_image_ids_snapshot"] = []

                prompt_count = len(row.get("prompt_ids") or [])
                image_count = int(row.get("image_count") or 0)
                expected_generations = prompt_count * image_count
                row["prompt_count"] = prompt_count
                row["expected_generations"] = expected_generations
                generation_count = int(row.get("generation_count") or 0)
                row["generation_progress_pct"] = (
                    round(min(100.0, (generation_count / expected_generations) * 100.0), 1)
                    if expected_generations > 0
                    else 0.0
                )
                row["expected_comparisons"] = estimate_comparisons(prompt_count, image_count)

                total_comparisons = int(row.get("total_comparisons") or 0)
                voted_count = int(row.get("voted_count") or 0)
                if total_comparisons > 0 and voted_count >= total_comparisons and row.get("status") == "judging":
                    row["status"] = "completed"

                return row
    except Exception as exc:
        logger.error("Ошибка получения image-сессии %d: %s", session_id, exc, exc_info=True)
        return None


def update_session_status(session_id: int, status: str) -> bool:
    """Обновить статус image-сессии."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE gk_image_prompt_tester_sessions SET status = %s WHERE id = %s",
                    (status, session_id),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка обновления статуса image-сессии %d: %s", session_id, exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Генерации
# ---------------------------------------------------------------------------


def save_generation(
    *,
    session_id: int,
    prompt_id: int,
    image_queue_id: int,
    image_path: str,
    generated_text: str,
    model_used: Optional[str] = None,
    raw_llm_response: Optional[str] = None,
) -> int:
    """Сохранить генерацию описания изображения."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_image_prompt_tester_generations
                        (session_id, prompt_id, image_queue_id, image_path,
                         generated_text, model_used, raw_llm_response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (session_id, prompt_id, image_queue_id, image_path, generated_text, model_used, raw_llm_response),
                )
                return int(cursor.lastrowid or 0)
    except Exception as exc:
        logger.error("Ошибка сохранения image-генерации: %s", exc, exc_info=True)
        raise


def create_comparisons_for_session(session_id: int) -> int:
    """Создать blind A/B сравнения для каждой картинки между всеми промптами."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT id, image_queue_id, prompt_id
                    FROM gk_image_prompt_tester_generations
                    WHERE session_id = %s
                    ORDER BY image_queue_id, prompt_id, id
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall() or []

                by_image: Dict[int, Dict[int, int]] = {}
                for row in rows:
                    image_queue_id = int(row.get("image_queue_id") or 0)
                    prompt_id = int(row.get("prompt_id") or 0)
                    gen_id = int(row.get("id") or 0)
                    if image_queue_id <= 0 or prompt_id <= 0 or gen_id <= 0:
                        continue
                    by_image.setdefault(image_queue_id, {})
                    if prompt_id not in by_image[image_queue_id]:
                        by_image[image_queue_id][prompt_id] = gen_id

                created = 0
                for image_queue_id, gen_a, gen_b in _build_shuffled_image_comparisons(by_image):
                    cursor.execute(
                        """
                        INSERT INTO gk_image_prompt_tester_comparisons
                            (session_id, image_queue_id, generation_a_id, generation_b_id)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (session_id, image_queue_id, gen_a, gen_b),
                    )
                    created += 1

                return created
    except Exception as exc:
        logger.error("Ошибка создания image-сравнений для сессии %d: %s", session_id, exc, exc_info=True)
        return 0


def get_next_comparison(session_id: int) -> Optional[Dict[str, Any]]:
    """Получить следующее неоценённое image-сравнение."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.id AS comparison_id,
                        c.image_queue_id,
                        ga.prompt_id AS prompt_a_id,
                        ga.generated_text AS generated_a,
                        pa.label AS prompt_a_label,
                        gb.prompt_id AS prompt_b_id,
                        gb.generated_text AS generated_b,
                        pb.label AS prompt_b_label
                    FROM gk_image_prompt_tester_comparisons c
                    JOIN gk_image_prompt_tester_generations ga ON ga.id = c.generation_a_id
                    JOIN gk_image_prompt_tester_generations gb ON gb.id = c.generation_b_id
                    JOIN gk_image_prompt_tester_prompts pa ON pa.id = ga.prompt_id
                    JOIN gk_image_prompt_tester_prompts pb ON pb.id = gb.prompt_id
                    WHERE c.session_id = %s AND c.winner IS NULL
                    ORDER BY RAND()
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN winner IS NOT NULL THEN 1 ELSE 0 END) AS voted
                    FROM gk_image_prompt_tester_comparisons
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                progress = cursor.fetchone() or {}

                return {
                    **row,
                    "progress_total": int(progress.get("total") or 0),
                    "progress_voted": int(progress.get("voted") or 0),
                }
    except Exception as exc:
        logger.error("Ошибка получения image-сравнения session=%d: %s", session_id, exc, exc_info=True)
        return None


def submit_vote(
    *,
    comparison_id: int,
    winner: str,
    expected_session_id: Optional[int] = None,
    voter_telegram_id: Optional[int] = None,
) -> bool:
    """Сохранить голос image A/B сравнения."""
    if winner not in {"a", "b", "tie", "skip"}:
        return False

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT session_id FROM gk_image_prompt_tester_comparisons WHERE id = %s",
                    (comparison_id,),
                )
                row = cursor.fetchone() or {}
                session_id = row.get("session_id")
                if expected_session_id is not None and session_id != expected_session_id:
                    return False

                cursor.execute(
                    """
                    UPDATE gk_image_prompt_tester_comparisons
                    SET winner = %s, voter_telegram_id = %s, voter_type = 'human', voted_at = NOW()
                    WHERE id = %s AND winner IS NULL
                    """,
                    (winner, voter_telegram_id, comparison_id),
                )
                updated = cursor.rowcount > 0
                if not updated or not session_id:
                    return updated

                cursor.execute(
                    """
                    SELECT COUNT(*) AS remaining
                    FROM gk_image_prompt_tester_comparisons
                    WHERE session_id = %s AND winner IS NULL
                    """,
                    (session_id,),
                )
                remaining = int((cursor.fetchone() or {}).get("remaining") or 0)
                if remaining == 0:
                    cursor.execute(
                        """
                        UPDATE gk_image_prompt_tester_sessions
                        SET status = 'completed'
                        WHERE id = %s AND status <> 'abandoned'
                        """,
                        (session_id,),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE gk_image_prompt_tester_sessions
                        SET status = 'judging'
                        WHERE id = %s AND status = 'generating'
                        """,
                        (session_id,),
                    )

                return updated
    except Exception as exc:
        logger.error("Ошибка голосования image-сравнения %d: %s", comparison_id, exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Результаты
# ---------------------------------------------------------------------------


def get_session_results(session_id: int) -> Dict[str, Any]:
    """Получить результаты image-сессии."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.winner,
                        ga.prompt_id AS prompt_a_id,
                        gb.prompt_id AS prompt_b_id
                    FROM gk_image_prompt_tester_comparisons c
                    JOIN gk_image_prompt_tester_generations ga ON ga.id = c.generation_a_id
                    JOIN gk_image_prompt_tester_generations gb ON gb.id = c.generation_b_id
                    WHERE c.session_id = %s AND c.winner IS NOT NULL
                    """,
                    (session_id,),
                )
                votes = cursor.fetchall() or []

                cursor.execute(
                    """
                    SELECT DISTINCT g.prompt_id, p.label
                    FROM gk_image_prompt_tester_generations g
                    JOIN gk_image_prompt_tester_prompts p ON p.id = g.prompt_id
                    WHERE g.session_id = %s
                    """,
                    (session_id,),
                )
                label_rows = cursor.fetchall() or []
                labels = {int(row.get("prompt_id") or 0): row.get("label") or "" for row in label_rows}

                results = _compute_results(votes=votes, prompt_labels=labels)
                total_votes = len([v for v in votes if v.get("winner") != "skip"])

                return {
                    "prompt_results": results,
                    "total_votes": total_votes,
                }
    except Exception as exc:
        logger.error("Ошибка расчёта image-результатов session=%d: %s", session_id, exc, exc_info=True)
        return {"prompt_results": [], "total_votes": 0}


def get_global_prompt_stats() -> Dict[str, Any]:
    """Агрегированная статистика image prompt tester по всем сессиям."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.winner,
                        ga.prompt_id AS prompt_a_id,
                        gb.prompt_id AS prompt_b_id
                    FROM gk_image_prompt_tester_comparisons c
                    JOIN gk_image_prompt_tester_generations ga ON ga.id = c.generation_a_id
                    JOIN gk_image_prompt_tester_generations gb ON gb.id = c.generation_b_id
                    JOIN gk_image_prompt_tester_sessions s ON s.id = c.session_id
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
                    FROM gk_image_prompt_tester_prompts p
                    LEFT JOIN gk_image_prompt_tester_generations g ON g.prompt_id = p.id
                    GROUP BY p.id, p.label, p.is_active
                    ORDER BY p.id
                    """
                )
                prompt_rows = cursor.fetchall() or []

                labels = {
                    int(row.get("prompt_id") or 0): row.get("label") or ""
                    for row in prompt_rows
                    if int(row.get("prompt_id") or 0) > 0
                }
                computed = _compute_results(votes=votes, prompt_labels=labels)

                sessions_count_by_prompt = {
                    int(row.get("prompt_id") or 0): int(row.get("sessions_count") or 0)
                    for row in prompt_rows
                }
                is_active_by_prompt = {
                    int(row.get("prompt_id") or 0): bool(row.get("is_active", 1))
                    for row in prompt_rows
                }

                for row in computed:
                    pid = int(row.get("prompt_id") or 0)
                    row["sessions_count"] = sessions_count_by_prompt.get(pid, 0)
                    row["is_active"] = is_active_by_prompt.get(pid, True)

                cursor.execute(
                    """
                    SELECT
                        COUNT(*) AS sessions_total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS sessions_completed,
                        SUM(CASE WHEN status = 'judging' THEN 1 ELSE 0 END) AS sessions_judging,
                        SUM(CASE WHEN status = 'generating' THEN 1 ELSE 0 END) AS sessions_generating
                    FROM gk_image_prompt_tester_sessions
                    WHERE status <> 'abandoned'
                    """
                )
                summary_row = cursor.fetchone() or {}

                return {
                    "summary": {
                        "sessions_total": int(summary_row.get("sessions_total") or 0),
                        "sessions_completed": int(summary_row.get("sessions_completed") or 0),
                        "sessions_judging": int(summary_row.get("sessions_judging") or 0),
                        "sessions_generating": int(summary_row.get("sessions_generating") or 0),
                        "voted_matches": len([v for v in votes if v.get("winner") != "skip"]),
                        "skipped_matches": len([v for v in votes if v.get("winner") == "skip"]),
                        "prompts_total": len(computed),
                    },
                    "prompts": computed,
                }
    except Exception as exc:
        logger.error("Ошибка агрегированной статистики image prompt tester: %s", exc, exc_info=True)
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
