"""Слой работы с БД: тестер финального LLM-промпта для Group Knowledge.

Тестер предназначен для A/B-сравнения шаблонов финального ответа пользователю
(шаблон `_ANSWER_PROMPT_BASE` из `qa_search.py`).
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
_GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN: Optional[int] = None
_MAX_SESSION_NAME_LENGTH = 255


def _normalize_session_name(name: str) -> str:
    """Нормализовать и провалидировать название сессии."""
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError("Название сессии не должно быть пустым")
    if len(normalized) > _MAX_SESSION_NAME_LENGTH:
        raise ValueError(f"Название сессии слишком длинное (максимум {_MAX_SESSION_NAME_LENGTH} символов)")
    return normalized


def _get_generation_confidence_reason_max_length() -> int:
    """Получить максимальную длину колонки confidence_reason с кэшированием."""
    global _GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN

    if _GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN is not None:
        return _GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN

    fallback = 512
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'gk_final_prompt_tester_generations'
                      AND COLUMN_NAME = 'confidence_reason'
                    LIMIT 1
                    """
                )
                row = cursor.fetchone() or {}
                data_type = str(row.get("DATA_TYPE") or "").strip().lower()
                if data_type in {"text", "mediumtext", "longtext"}:
                    _GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN = 0
                    return _GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN

                raw_length = row.get("CHARACTER_MAXIMUM_LENGTH")
                max_length = int(raw_length or 0)
                if max_length > 0:
                    _GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN = max_length
                    return _GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN
    except Exception as exc:
        logger.warning(
            "Не удалось определить длину confidence_reason в gk_final_prompt_tester_generations: %s",
            exc,
        )

    _GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN = fallback
    return _GK_FINAL_GEN_CONFIDENCE_REASON_MAX_LEN


def _truncate_nullable_text(value: Optional[str], max_length: int) -> Optional[str]:
    """Обрезать nullable-текст до допустимой длины для записи в БД."""
    text = str(value or "").strip()
    if not text:
        return None
    if max_length <= 0:
        return text
    if len(text) <= max_length:
        return text

    logger.warning(
        "Поле confidence_reason обрезано до %d символов (фактическая длина=%d)",
        max_length,
        len(text),
    )
    return text[:max_length]


def _expected_score(rating_a: float, rating_b: float) -> float:
    """Рассчитать ожидаемый результат A по формуле Elo."""
    return 1.0 / (1.0 + math.pow(10, (rating_b - rating_a) / 400.0))


def _apply_elo_update(rating_a: float, rating_b: float, score_a: float) -> Tuple[float, float]:
    """Обновить Elo A/B после одного сравнения."""
    expected_a = _expected_score(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a
    return (
        rating_a + _ELO_K * (score_a - expected_a),
        rating_b + _ELO_K * (score_b - expected_b),
    )


def _normalize_ids_json(raw_value: Any) -> List[int]:
    """Нормализовать JSON-массив ID в список целых чисел."""
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


def _normalize_questions_json(raw_value: Any) -> List[str]:
    """Нормализовать JSON-массив вопросов в список непустых строк."""
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

    questions: List[str] = []
    for item in value:
        q = str(item or "").strip()
        if q:
            questions.append(q)
    return questions


def estimate_comparisons(prompt_count: int, question_count: int) -> int:
    """Рассчитать ожидаемое число A/B-сравнений: C(n,2) × question_count."""
    if prompt_count < 2 or question_count <= 0:
        return 0
    return (prompt_count * (prompt_count - 1) // 2) * question_count


def _build_shuffled_question_comparisons(
    by_question: Dict[int, Dict[int, int]],
) -> List[Tuple[int, int, int]]:
    """Собрать и перемешать blind-пары генераций по каждому вопросу.

    Args:
        by_question: question_index -> {prompt_id: generation_id}.

    Returns:
        Список кортежей (question_index, generation_a_id, generation_b_id).
    """
    comparisons: List[Tuple[int, int, int]] = []

    for question_index in sorted(by_question.keys()):
        prompt_map = by_question.get(question_index) or {}
        prompt_ids = sorted(prompt_map.keys())
        if len(prompt_ids) < 2:
            continue

        question_pairs: List[Tuple[int, int, int]] = []
        for i in range(len(prompt_ids)):
            for j in range(i + 1, len(prompt_ids)):
                gen_a = int(prompt_map[prompt_ids[i]])
                gen_b = int(prompt_map[prompt_ids[j]])
                if random.random() > 0.5:
                    gen_a, gen_b = gen_b, gen_a
                question_pairs.append((question_index, gen_a, gen_b))

        random.shuffle(question_pairs)
        comparisons.extend(question_pairs)

    random.shuffle(comparisons)
    return comparisons


def _compute_results(
    *,
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
        if pa <= 0 or pb <= 0 or winner not in {"a", "b", "tie", "skip"}:
            continue

        if pa not in elo:
            elo[pa] = float(_ELO_DEFAULT)
            wins[pa] = 0
            losses[pa] = 0
            ties[pa] = 0
            skips[pa] = 0
        if pb not in elo:
            elo[pb] = float(_ELO_DEFAULT)
            wins[pb] = 0
            losses[pb] = 0
            ties[pb] = 0
            skips[pb] = 0

        if winner == "skip":
            skips[pa] += 1
            skips[pb] += 1
            continue

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
        win_rate = ((wins[pid] + ties[pid] * 0.5) / matches) if matches > 0 else 0.0
        rows.append(
            {
                "prompt_id": pid,
                "label": prompt_labels.get(pid, f"Промпт #{pid}"),
                "elo": round(elo[pid], 2),
                "elo_delta": round(elo[pid] - _ELO_DEFAULT, 2),
                "wins": wins[pid],
                "losses": losses[pid],
                "ties": ties[pid],
                "skips": skips[pid],
                "matches": matches,
                "win_rate": round(win_rate, 4),
                "score": round(wins[pid] + ties[pid] * 0.5, 2),
            }
        )

    rows.sort(key=lambda item: float(item.get("elo") or 0.0), reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Промпты CRUD
# ---------------------------------------------------------------------------


def get_prompts(active_only: bool = True) -> List[Dict[str, Any]]:
    """Получить список промптов тестера финального ответа."""
    cond = "WHERE is_active = 1" if active_only else ""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        id, label, prompt_template,
                        model_name, temperature,
                        created_by_telegram_id,
                        created_at, updated_at,
                        is_active
                    FROM gk_final_prompt_tester_prompts
                    {cond}
                    ORDER BY id
                    """
                )
                return cursor.fetchall() or []
    except Exception as exc:
        logger.error("Ошибка получения финальных промптов: %s", exc, exc_info=True)
        return []


def get_prompt_by_id(prompt_id: int) -> Optional[Dict[str, Any]]:
    """Получить финальный промпт по ID."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "SELECT * FROM gk_final_prompt_tester_prompts WHERE id = %s",
                    (prompt_id,),
                )
                return cursor.fetchone()
    except Exception as exc:
        logger.error("Ошибка получения финального промпта %d: %s", prompt_id, exc, exc_info=True)
        return None


def create_prompt(
    *,
    label: str,
    prompt_template: str,
    model_name: Optional[str] = None,
    temperature: float = 0.3,
    created_by_telegram_id: Optional[int] = None,
) -> int:
    """Создать новый финальный промпт. Возвращает ID."""
    prompt_text = str(prompt_template or "").strip()
    if not prompt_text:
        raise ValueError("Шаблон промпта не должен быть пустым")

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_final_prompt_tester_prompts
                        (label, prompt_template, model_name, temperature, created_by_telegram_id)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (label, prompt_text, model_name, temperature, created_by_telegram_id),
                )
                return int(cursor.lastrowid or 0)
    except Exception as exc:
        logger.error("Ошибка создания финального промпта: %s", exc, exc_info=True)
        raise


def clone_prompt(prompt_id: int, *, created_by_telegram_id: Optional[int] = None) -> int:
    """Клонировать существующий промпт и вернуть ID копии."""
    source = get_prompt_by_id(prompt_id)
    if not source:
        raise ValueError(f"Промпт #{prompt_id} не найден")

    base_label = str(source.get("label") or f"Промпт #{prompt_id}").strip() or f"Промпт #{prompt_id}"
    cloned_label = f"{base_label} (clone)"
    return create_prompt(
        label=cloned_label,
        prompt_template=str(source.get("prompt_template") or ""),
        model_name=(str(source.get("model_name") or "").strip() or None),
        temperature=float(source.get("temperature") or 0.3),
        created_by_telegram_id=created_by_telegram_id,
    )


def update_prompt(
    prompt_id: int,
    *,
    label: Optional[str] = None,
    prompt_template: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
) -> bool:
    """Обновить существующий финальный промпт."""
    fields: List[str] = []
    params: List[Any] = []

    if label is not None:
        fields.append("label = %s")
        params.append(label)
    if prompt_template is not None:
        fields.append("prompt_template = %s")
        params.append(prompt_template)
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
                    f"UPDATE gk_final_prompt_tester_prompts SET {', '.join(fields)} WHERE id = %s",
                    tuple(params),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка обновления финального промпта %d: %s", prompt_id, exc, exc_info=True)
        raise


def delete_prompt(prompt_id: int) -> bool:
    """Деактивировать финальный промпт (мягкое удаление)."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE gk_final_prompt_tester_prompts SET is_active = 0 WHERE id = %s",
                    (prompt_id,),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка деактивации финального промпта %d: %s", prompt_id, exc, exc_info=True)
        raise


def get_prompt_dependencies(prompt_id: int) -> Dict[str, int]:
    """Получить количество зависимостей промпта в генерациях и сессиях."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM gk_final_prompt_tester_generations
                    WHERE prompt_id = %s
                    """,
                    (prompt_id,),
                )
                gen_row = cursor.fetchone() or {}
                generations_count = int(gen_row.get("cnt") or 0)

                cursor.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM gk_final_prompt_tester_sessions
                    WHERE JSON_CONTAINS(prompt_ids, JSON_ARRAY(%s))
                    """,
                    (prompt_id,),
                )
                ses_row = cursor.fetchone() or {}
                sessions_count = int(ses_row.get("cnt") or 0)

                return {
                    "generations_count": generations_count,
                    "sessions_count": sessions_count,
                }
    except Exception as exc:
        logger.error("Ошибка проверки зависимостей промпта %d: %s", prompt_id, exc, exc_info=True)
        return {"generations_count": 0, "sessions_count": 0}


def purge_inactive_prompt(prompt_id: int) -> bool:
    """Удалить промпт навсегда, если он неактивен и не имеет зависимостей."""
    prompt = get_prompt_by_id(prompt_id)
    if not prompt:
        raise ValueError(f"Промпт #{prompt_id} не найден")

    if bool(prompt.get("is_active")):
        raise ValueError("Удалять навсегда можно только неактивный промпт")

    deps = get_prompt_dependencies(prompt_id)
    if int(deps.get("generations_count") or 0) > 0 or int(deps.get("sessions_count") or 0) > 0:
        raise ValueError(
            "Нельзя удалить промпт: есть зависимости "
            f"(generations={int(deps.get('generations_count') or 0)}, "
            f"sessions={int(deps.get('sessions_count') or 0)})"
        )

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "DELETE FROM gk_final_prompt_tester_prompts WHERE id = %s AND is_active = 0",
                    (prompt_id,),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка полного удаления промпта %d: %s", prompt_id, exc, exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Сессии
# ---------------------------------------------------------------------------


def create_session(
    *,
    name: str,
    prompt_ids: List[int],
    questions_snapshot: List[str],
    source_group_id: Optional[int] = None,
    status: str = "generating",
    judge_mode: str = "human",
    prompts_config_snapshot: Optional[List[Dict[str, Any]]] = None,
    created_by_telegram_id: Optional[int] = None,
) -> int:
    """Создать новую сессию тестирования финального ответа."""
    safe_name = _normalize_session_name(name)
    question_count = len(questions_snapshot)
    if question_count < 1:
        raise ValueError("Необходимо минимум 1 вопрос")

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_final_prompt_tester_sessions
                        (name, status, prompt_ids, prompts_config_snapshot, judge_mode,
                         source_group_id, question_count, questions_snapshot,
                         created_by_telegram_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        safe_name,
                        status,
                        json.dumps(prompt_ids),
                        json.dumps(prompts_config_snapshot or []),
                        judge_mode,
                        source_group_id,
                        question_count,
                        json.dumps(questions_snapshot),
                        created_by_telegram_id,
                    ),
                )
                return int(cursor.lastrowid or 0)
    except Exception as exc:
        logger.error("Ошибка создания финальной сессии: %s", exc, exc_info=True)
        raise


def get_sessions() -> List[Dict[str, Any]]:
    """Получить список финальных сессий тестирования."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        s.id, s.name, s.status, s.prompt_ids,
                        s.judge_mode, s.source_group_id,
                        s.question_count,
                        s.created_by_telegram_id,
                        s.created_at, s.updated_at,
                        (SELECT COUNT(*) FROM gk_final_prompt_tester_generations g WHERE g.session_id = s.id) AS generation_count,
                        (SELECT COUNT(*) FROM gk_final_prompt_tester_comparisons c WHERE c.session_id = s.id) AS total_comparisons,
                        (SELECT COUNT(*) FROM gk_final_prompt_tester_comparisons c WHERE c.session_id = s.id AND c.winner IS NOT NULL) AS voted_count
                    FROM gk_final_prompt_tester_sessions s
                    ORDER BY s.created_at DESC
                    """
                )
                rows = cursor.fetchall() or []
                for row in rows:
                    row["prompt_ids"] = _normalize_ids_json(row.get("prompt_ids"))
                    prompt_count = len(row.get("prompt_ids") or [])
                    question_count = int(row.get("question_count") or 0)
                    row["prompt_count"] = prompt_count
                    row["expected_generations"] = prompt_count * question_count
                    generation_count = int(row.get("generation_count") or 0)
                    expected_generations = int(row.get("expected_generations") or 0)
                    if expected_generations > 0:
                        row["generation_progress_pct"] = round(
                            min(100.0, (generation_count / expected_generations) * 100.0),
                            1,
                        )
                    else:
                        row["generation_progress_pct"] = 0.0

                    row["expected_comparisons"] = estimate_comparisons(prompt_count, question_count)

                    total = int(row.get("total_comparisons") or 0)
                    voted = int(row.get("voted_count") or 0)
                    if total > 0 and voted >= total and row.get("status") == "judging":
                        row["status"] = "completed"
                return rows
    except Exception as exc:
        logger.error("Ошибка получения финальных сессий: %s", exc, exc_info=True)
        return []


def get_session_by_id(session_id: int) -> Optional[Dict[str, Any]]:
    """Получить сессию по ID с вычисленными полями прогресса."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        s.*,
                        (SELECT COUNT(*) FROM gk_final_prompt_tester_generations g WHERE g.session_id = s.id) AS generation_count,
                        (SELECT COUNT(*) FROM gk_final_prompt_tester_comparisons c WHERE c.session_id = s.id) AS total_comparisons,
                        (SELECT COUNT(*) FROM gk_final_prompt_tester_comparisons c WHERE c.session_id = s.id AND c.winner IS NOT NULL) AS voted_count
                    FROM gk_final_prompt_tester_sessions s
                    WHERE s.id = %s
                    """,
                    (session_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None

                row["prompt_ids"] = _normalize_ids_json(row.get("prompt_ids"))
                row["questions_snapshot"] = _normalize_questions_json(row.get("questions_snapshot"))

                if isinstance(row.get("prompts_config_snapshot"), str):
                    try:
                        row["prompts_config_snapshot"] = json.loads(row["prompts_config_snapshot"])
                    except Exception:
                        row["prompts_config_snapshot"] = []

                prompt_count = len(row.get("prompt_ids") or [])
                question_count = int(row.get("question_count") or 0)
                row["prompt_count"] = prompt_count
                row["expected_generations"] = prompt_count * question_count
                generation_count = int(row.get("generation_count") or 0)
                expected_generations = int(row.get("expected_generations") or 0)
                if expected_generations > 0:
                    row["generation_progress_pct"] = round(
                        min(100.0, (generation_count / expected_generations) * 100.0),
                        1,
                    )
                else:
                    row["generation_progress_pct"] = 0.0

                row["expected_comparisons"] = estimate_comparisons(prompt_count, question_count)
                total = int(row.get("total_comparisons") or 0)
                voted = int(row.get("voted_count") or 0)
                if total > 0 and voted >= total and row.get("status") == "judging":
                    row["status"] = "completed"

                return row
    except Exception as exc:
        logger.error("Ошибка получения финальной сессии %d: %s", session_id, exc, exc_info=True)
        return None


def update_session_status(session_id: int, status: str) -> bool:
    """Обновить статус сессии."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "UPDATE gk_final_prompt_tester_sessions SET status = %s WHERE id = %s",
                    (status, session_id),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка обновления статуса финальной сессии %d: %s", session_id, exc, exc_info=True)
        return False


def update_draft_session(
    *,
    session_id: int,
    name: str,
    prompt_ids: List[int],
    questions_snapshot: List[str],
    source_group_id: Optional[int],
    prompts_config_snapshot: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Обновить draft-сессию final prompt tester."""
    safe_name = _normalize_session_name(name)
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    UPDATE gk_final_prompt_tester_sessions
                    SET
                        name = %s,
                        prompt_ids = %s,
                        prompts_config_snapshot = %s,
                        source_group_id = %s,
                        question_count = %s,
                        questions_snapshot = %s
                    WHERE id = %s AND status = 'draft'
                    """,
                    (
                        safe_name,
                        json.dumps(prompt_ids),
                        json.dumps(prompts_config_snapshot or []),
                        source_group_id,
                        len(questions_snapshot),
                        json.dumps(questions_snapshot),
                        session_id,
                    ),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка обновления draft-сессии %d: %s", session_id, exc, exc_info=True)
        return False


def delete_session(session_id: int) -> bool:
    """Удалить сессию final prompt tester (каскадно удалятся сравнения/генерации)."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    "DELETE FROM gk_final_prompt_tester_sessions WHERE id = %s",
                    (session_id,),
                )
                return cursor.rowcount > 0
    except Exception as exc:
        logger.error("Ошибка удаления финальной сессии %d: %s", session_id, exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Генерации
# ---------------------------------------------------------------------------


def save_generation(
    *,
    session_id: int,
    prompt_id: int,
    question_index: int,
    user_question: str,
    retrieved_pair_ids: Optional[List[int]],
    answer_text: Optional[str],
    is_relevant: bool,
    confidence: Optional[float],
    confidence_reason: Optional[str],
    used_pair_ids: Optional[List[int]],
    model_used: Optional[str],
    temperature_used: Optional[float],
    llm_request_payload: Optional[str],
    raw_llm_response: Optional[str] = None,
) -> int:
    """Сохранить генерацию финального ответа. Возвращает ID."""
    confidence_reason_safe = _truncate_nullable_text(
        confidence_reason,
        _get_generation_confidence_reason_max_length(),
    )

    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    INSERT INTO gk_final_prompt_tester_generations
                        (session_id, prompt_id, question_index, user_question,
                         retrieved_pair_ids, answer_text, is_relevant,
                         confidence, confidence_reason, used_pair_ids,
                         model_used, temperature_used,
                         llm_request_payload, raw_llm_response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        session_id,
                        prompt_id,
                        question_index,
                        user_question,
                        json.dumps(retrieved_pair_ids or []),
                        answer_text,
                        1 if is_relevant else 0,
                        confidence,
                        confidence_reason_safe,
                        json.dumps(used_pair_ids or []),
                        model_used,
                        temperature_used,
                        llm_request_payload,
                        raw_llm_response,
                    ),
                )
                return int(cursor.lastrowid or 0)
    except Exception as exc:
        logger.error("Ошибка сохранения финальной генерации: %s", exc, exc_info=True)
        raise


def create_comparisons_for_session(session_id: int) -> int:
    """Создать blind A/B-сравнения между промптами по каждому вопросу."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT id, prompt_id, question_index
                    FROM gk_final_prompt_tester_generations
                    WHERE session_id = %s
                    ORDER BY question_index, prompt_id, id
                    """,
                    (session_id,),
                )
                rows = cursor.fetchall() or []
                if not rows:
                    return 0

                by_question: Dict[int, Dict[int, int]] = {}
                for row in rows:
                    question_index = int(row.get("question_index") or 0)
                    prompt_id = int(row.get("prompt_id") or 0)
                    generation_id = int(row.get("id") or 0)
                    if prompt_id <= 0 or generation_id <= 0:
                        continue
                    by_question.setdefault(question_index, {})
                    if prompt_id not in by_question[question_index]:
                        by_question[question_index][prompt_id] = generation_id

                count = 0
                for question_index, generation_a_id, generation_b_id in _build_shuffled_question_comparisons(by_question):
                    cursor.execute(
                        """
                        INSERT INTO gk_final_prompt_tester_comparisons
                            (session_id, question_index, generation_a_id, generation_b_id)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (session_id, question_index, generation_a_id, generation_b_id),
                    )
                    count += 1

                return count
    except Exception as exc:
        logger.error("Ошибка создания финальных сравнений для сессии %d: %s", session_id, exc, exc_info=True)
        return 0


def get_next_comparison(
    session_id: int,
    voter_telegram_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Получить следующее неоценённое сравнение для голосования."""
    _ = voter_telegram_id
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.id AS comparison_id,
                        c.question_index,
                        ga.prompt_id AS prompt_a_id,
                        ga.user_question AS user_question,
                        ga.answer_text AS answer_a,
                        ga.confidence AS confidence_a,
                        ga.is_relevant AS is_relevant_a,
                        gb.prompt_id AS prompt_b_id,
                        gb.answer_text AS answer_b,
                        gb.confidence AS confidence_b,
                        gb.is_relevant AS is_relevant_b
                    FROM gk_final_prompt_tester_comparisons c
                    JOIN gk_final_prompt_tester_generations ga ON ga.id = c.generation_a_id
                    JOIN gk_final_prompt_tester_generations gb ON gb.id = c.generation_b_id
                    WHERE c.session_id = %s
                      AND c.winner IS NULL
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
                    SELECT COUNT(*) AS total,
                           SUM(CASE WHEN winner IS NOT NULL THEN 1 ELSE 0 END) AS voted
                    FROM gk_final_prompt_tester_comparisons
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
        logger.error("Ошибка получения финального сравнения для сессии %d: %s", session_id, exc, exc_info=True)
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
                    "SELECT session_id FROM gk_final_prompt_tester_comparisons WHERE id = %s",
                    (comparison_id,),
                )
                row = cursor.fetchone() or {}
                session_id = row.get("session_id")
                if expected_session_id is not None and session_id != expected_session_id:
                    return False

                cursor.execute(
                    """
                    UPDATE gk_final_prompt_tester_comparisons
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
                    FROM gk_final_prompt_tester_comparisons
                    WHERE session_id = %s AND winner IS NULL
                    """,
                    (session_id,),
                )
                remaining = int((cursor.fetchone() or {}).get("remaining") or 0)
                if remaining == 0:
                    cursor.execute(
                        """
                        UPDATE gk_final_prompt_tester_sessions
                        SET status = 'completed'
                        WHERE id = %s AND status <> 'abandoned'
                        """,
                        (session_id,),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE gk_final_prompt_tester_sessions
                        SET status = 'judging'
                        WHERE id = %s AND status = 'generating'
                        """,
                        (session_id,),
                    )

                return updated
    except Exception as exc:
        logger.error("Ошибка голосования по финальному сравнению %d: %s", comparison_id, exc, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Результаты и статистика
# ---------------------------------------------------------------------------


def get_session_results(session_id: int) -> Dict[str, Any]:
    """Получить результаты сессии (Elo + WinRate)."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.winner,
                        ga.prompt_id AS prompt_a_id,
                        gb.prompt_id AS prompt_b_id
                    FROM gk_final_prompt_tester_comparisons c
                    JOIN gk_final_prompt_tester_generations ga ON ga.id = c.generation_a_id
                    JOIN gk_final_prompt_tester_generations gb ON gb.id = c.generation_b_id
                    WHERE c.session_id = %s
                      AND c.winner IS NOT NULL
                    """,
                    (session_id,),
                )
                votes = cursor.fetchall() or []

                cursor.execute(
                    """
                    SELECT DISTINCT g.prompt_id, p.label
                    FROM gk_final_prompt_tester_generations g
                    JOIN gk_final_prompt_tester_prompts p ON p.id = g.prompt_id
                    WHERE g.session_id = %s
                    """,
                    (session_id,),
                )
                labels = {
                    int(row.get("prompt_id") or 0): str(row.get("label") or "")
                    for row in (cursor.fetchall() or [])
                    if int(row.get("prompt_id") or 0) > 0
                }

                results = _compute_results(votes=votes, prompt_labels=labels)
                total_votes = len([v for v in votes if v.get("winner") != "skip"])
                return {
                    "prompt_results": results,
                    "total_votes": total_votes,
                }
    except Exception as exc:
        logger.error("Ошибка расчёта результатов финальной сессии %d: %s", session_id, exc, exc_info=True)
        return {"prompt_results": [], "total_votes": 0}


def get_global_prompt_stats() -> Dict[str, Any]:
    """Вернуть агрегированную статистику финального prompt tester по всем сессиям."""
    try:
        with database.get_db_connection() as conn:
            with database.get_cursor(conn) as cursor:
                cursor.execute(
                    """
                    SELECT
                        c.winner,
                        ga.prompt_id AS prompt_a_id,
                        gb.prompt_id AS prompt_b_id
                    FROM gk_final_prompt_tester_comparisons c
                    JOIN gk_final_prompt_tester_generations ga ON ga.id = c.generation_a_id
                    JOIN gk_final_prompt_tester_generations gb ON gb.id = c.generation_b_id
                    JOIN gk_final_prompt_tester_sessions s ON s.id = c.session_id
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
                    FROM gk_final_prompt_tester_prompts p
                    LEFT JOIN gk_final_prompt_tester_generations g ON g.prompt_id = p.id
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
                    FROM gk_final_prompt_tester_sessions
                    WHERE status <> 'abandoned'
                    """
                )
                summary_row = cursor.fetchone() or {}

                labels = {
                    int(row.get("prompt_id") or 0): str(row.get("label") or "")
                    for row in prompt_rows
                    if int(row.get("prompt_id") or 0) > 0
                }
                computed = _compute_results(votes=votes, prompt_labels=labels)
                by_prompt_id = {int(item.get("prompt_id") or 0): item for item in computed}
                prompt_row_by_id = {
                    int(row.get("prompt_id") or 0): row
                    for row in prompt_rows
                    if int(row.get("prompt_id") or 0) > 0
                }

                prompt_stats: List[Dict[str, Any]] = []
                for prompt_id in sorted(set(by_prompt_id.keys()) | set(prompt_row_by_id.keys())):
                    item = by_prompt_id.get(prompt_id, {
                        "prompt_id": prompt_id,
                        "label": labels.get(prompt_id, f"Промпт #{prompt_id}"),
                        "elo": _ELO_DEFAULT,
                        "elo_delta": 0.0,
                        "wins": 0,
                        "losses": 0,
                        "ties": 0,
                        "skips": 0,
                        "matches": 0,
                        "win_rate": 0.0,
                    })
                    row = prompt_row_by_id.get(prompt_id, {})
                    prompt_stats.append(
                        {
                            "prompt_id": prompt_id,
                            "label": item.get("label") or row.get("label") or f"Промпт #{prompt_id}",
                            "is_active": bool(row.get("is_active", 1)),
                            "sessions_count": int(row.get("sessions_count") or 0),
                            "elo": float(item.get("elo") or 0.0),
                            "elo_delta": float(item.get("elo_delta") or 0.0),
                            "wins": int(item.get("wins") or 0),
                            "losses": int(item.get("losses") or 0),
                            "ties": int(item.get("ties") or 0),
                            "skips": int(item.get("skips") or 0),
                            "matches": int(item.get("matches") or 0),
                            "win_rate": float(item.get("win_rate") or 0.0),
                        }
                    )

                prompt_stats.sort(key=lambda item: float(item.get("elo") or 0.0), reverse=True)

                voted_matches = len([v for v in votes if v.get("winner") != "skip"])
                skipped_matches = len([v for v in votes if v.get("winner") == "skip"])

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
        logger.error("Ошибка агрегированной статистики финального prompt tester: %s", exc, exc_info=True)
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
