"""Слой работы с базой данных для тестера промптов.

Все SQL-запросы для CRUD промптов, сессий, генераций и голосов.
Использует пул подключений из src.common.database.
"""

from __future__ import annotations

import json
import logging
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

from src.common import database

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Промпты — CRUD
# ---------------------------------------------------------------------------


def list_prompts(*, active_only: bool = True) -> List[Dict[str, Any]]:
    """Получить список пар промптов с подсчётом использований в сессиях."""
    where = "WHERE p.is_active = TRUE" if active_only else ""
    query = f"""
        SELECT
            p.id,
            p.label,
            p.system_prompt_template,
            p.user_message,
            p.model_name,
            p.temperature,
            p.is_active,
            p.created_at,
            p.updated_at,
            COALESCE(`usage`.cnt, 0) AS usage_count
        FROM prompt_test_prompts p
        LEFT JOIN (
            SELECT
                g.prompt_id,
                COUNT(DISTINCT g.session_id) AS cnt
            FROM prompt_test_generations g
            GROUP BY g.prompt_id
        ) AS `usage` ON `usage`.prompt_id = p.id
        {where}
        ORDER BY p.updated_at DESC
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query)
            return cursor.fetchall() or []


def get_prompt(prompt_id: int) -> Optional[Dict[str, Any]]:
    """Получить одну пару промптов по ID."""
    query = """
        SELECT
            id, label, system_prompt_template, user_message,
            model_name, temperature, is_active, created_at, updated_at
        FROM prompt_test_prompts
        WHERE id = %s
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (prompt_id,))
            return cursor.fetchone()


def create_prompt(
    *,
    label: str,
    system_prompt_template: str,
    user_message: str,
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
) -> int:
    """Создать новую пару промптов. Возвращает ID."""
    query = """
        INSERT INTO prompt_test_prompts
            (label, system_prompt_template, user_message, model_name, temperature)
        VALUES (%s, %s, %s, %s, %s)
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (label, system_prompt_template, user_message, model_name, temperature))
            return cursor.lastrowid


def update_prompt(prompt_id: int, **fields: Any) -> bool:
    """Обновить поля пары промптов. Возвращает True если запись найдена."""
    allowed = {"label", "system_prompt_template", "user_message", "model_name", "temperature", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False

    set_parts = [f"{col} = %s" for col in updates]
    values = list(updates.values()) + [prompt_id]

    query = f"""
        UPDATE prompt_test_prompts
        SET {', '.join(set_parts)}, updated_at = NOW()
        WHERE id = %s
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, tuple(values))
            return cursor.rowcount > 0


def delete_prompt(prompt_id: int) -> bool:
    """Мягкое удаление — is_active = FALSE."""
    return update_prompt(prompt_id, is_active=False)


def duplicate_prompt(prompt_id: int) -> Optional[int]:
    """Клонировать пару промптов. Возвращает ID копии или None."""
    original = get_prompt(prompt_id)
    if not original:
        return None
    return create_prompt(
        label=f"{original['label']} (копия)",
        system_prompt_template=original["system_prompt_template"],
        user_message=original["user_message"],
        model_name=original.get("model_name"),
        temperature=original.get("temperature"),
    )


def get_prompts_by_ids(prompt_ids: List[int]) -> List[Dict[str, Any]]:
    """Получить промпты по списку ID (для создания snapshot)."""
    if not prompt_ids:
        return []
    placeholders = ", ".join(["%s"] * len(prompt_ids))
    query = f"""
        SELECT
            id, label, system_prompt_template, user_message,
            model_name, temperature, is_active, created_at, updated_at
        FROM prompt_test_prompts
        WHERE id IN ({placeholders}) AND is_active = TRUE
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, tuple(prompt_ids))
            return cursor.fetchall() or []


# ---------------------------------------------------------------------------
# Сессии
# ---------------------------------------------------------------------------


def create_session(
    *,
    name: str,
    prompt_ids: List[int],
    prompts_config: List[Dict[str, Any]],
    document_ids: List[int],
    total_comparisons: int,
    judge_mode: str = "human",
) -> int:
    """Создать тестовую сессию. Возвращает session_id."""
    query = """
        INSERT INTO prompt_test_sessions
            (name, prompt_ids_snapshot, prompts_config_snapshot,
             document_ids, total_comparisons, judge_mode, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'generating')
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (
                name,
                json.dumps(prompt_ids),
                json.dumps(prompts_config, ensure_ascii=False, default=str),
                json.dumps(document_ids),
                total_comparisons,
                judge_mode,
            ))
            return cursor.lastrowid


def get_session(session_id: int) -> Optional[Dict[str, Any]]:
    """Получить сессию по ID."""
    query = """
        SELECT
            id, name, status, prompt_ids_snapshot, prompts_config_snapshot,
            document_ids, total_comparisons, completed_comparisons,
            judge_mode, created_at, updated_at
        FROM prompt_test_sessions
        WHERE id = %s
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (session_id,))
            row = cursor.fetchone()
            if row:
                # Десериализуем JSON-поля
                for json_field in ("prompt_ids_snapshot", "prompts_config_snapshot", "document_ids"):
                    val = row.get(json_field)
                    if isinstance(val, str):
                        row[json_field] = json.loads(val)
            return row


def list_sessions() -> List[Dict[str, Any]]:
    """Получить список всех сессий."""
    query = """
        SELECT
            id, name, status, prompt_ids_snapshot, document_ids,
            total_comparisons, completed_comparisons, judge_mode, created_at
        FROM prompt_test_sessions
        ORDER BY created_at DESC
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query)
            rows = cursor.fetchall() or []
            for row in rows:
                for json_field in ("prompt_ids_snapshot", "document_ids"):
                    val = row.get(json_field)
                    if isinstance(val, str):
                        row[json_field] = json.loads(val)
            return rows


def update_session_status(session_id: int, status: str) -> bool:
    """Обновить статус сессии."""
    allowed = {"generating", "judging", "in_progress", "completed", "abandoned"}
    if status not in allowed:
        return False
    query = """
        UPDATE prompt_test_sessions
        SET status = %s, updated_at = NOW()
        WHERE id = %s
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (status, session_id))
            return cursor.rowcount > 0


def increment_completed_comparisons(session_id: int) -> None:
    """Инкрементировать счётчик завершённых сравнений."""
    query = """
        UPDATE prompt_test_sessions
        SET completed_comparisons = completed_comparisons + 1, updated_at = NOW()
        WHERE id = %s
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (session_id,))


# ---------------------------------------------------------------------------
# Генерации
# ---------------------------------------------------------------------------


def count_generations(session_id: int) -> int:
    """Подсчитать количество готовых генераций для сессии."""
    query = """
        SELECT COUNT(*) AS cnt
        FROM prompt_test_generations
        WHERE session_id = %s
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (session_id,))
            row = cursor.fetchone()
            return row["cnt"] if row else 0


def insert_generation(
    *,
    session_id: int,
    document_id: int,
    prompt_id: int,
    prompt_label: str,
    system_prompt_used: str,
    user_message_used: str,
    model_name: Optional[str] = None,
    temperature_used: Optional[float] = None,
    summary_text: Optional[str] = None,
    generation_time_ms: Optional[int] = None,
    error_message: Optional[str] = None,
) -> int:
    """Записать результат генерации summary. Возвращает generation_id."""
    query = """
        INSERT INTO prompt_test_generations
            (session_id, document_id, prompt_id, prompt_label,
             system_prompt_used, user_message_used, model_name, temperature_used,
             summary_text, generation_time_ms, error_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (
                session_id, document_id, prompt_id, prompt_label,
                system_prompt_used, user_message_used, model_name, temperature_used,
                summary_text, generation_time_ms, error_message,
            ))
            return cursor.lastrowid


def get_generations_for_session(session_id: int) -> List[Dict[str, Any]]:
    """Получить все генерации сессии."""
    query = """
        SELECT
            id, session_id, document_id, prompt_id, prompt_label,
            system_prompt_used, user_message_used, model_name, temperature_used,
            summary_text, generation_time_ms, error_message, created_at
        FROM prompt_test_generations
        WHERE session_id = %s
        ORDER BY document_id, prompt_id
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (session_id,))
            return cursor.fetchall() or []


def get_generations_for_document(session_id: int, document_id: int) -> List[Dict[str, Any]]:
    """Получить генерации для конкретного документа в сессии."""
    query = """
        SELECT
            id, prompt_id, prompt_label, summary_text, generation_time_ms, model_name
        FROM prompt_test_generations
        WHERE session_id = %s AND document_id = %s AND summary_text IS NOT NULL
        ORDER BY prompt_id
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (session_id, document_id))
            return cursor.fetchall() or []


# ---------------------------------------------------------------------------
# Голоса
# ---------------------------------------------------------------------------


def insert_vote(
    *,
    session_id: int,
    document_id: int,
    generation_a_id: int,
    generation_b_id: int,
    winner: str,
    judge_type: str = "human",
    llm_judge_reasoning: Optional[str] = None,
) -> int:
    """Записать голос. Возвращает vote_id."""
    query = """
        INSERT INTO prompt_test_votes
            (session_id, document_id, generation_a_id, generation_b_id,
             winner, judge_type, llm_judge_reasoning)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (
                session_id, document_id, generation_a_id, generation_b_id,
                winner, judge_type, llm_judge_reasoning,
            ))
            return cursor.lastrowid


def get_votes_for_session(session_id: int, judge_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Получить голоса сессии, опционально фильтр по типу оценщика."""
    query = """
        SELECT
            v.id, v.session_id, v.document_id,
            v.generation_a_id, v.generation_b_id,
            v.winner, v.judge_type, v.llm_judge_reasoning,
            ga.prompt_id AS prompt_a_id, ga.prompt_label AS prompt_a_label,
            gb.prompt_id AS prompt_b_id, gb.prompt_label AS prompt_b_label,
            v.created_at
        FROM prompt_test_votes v
        JOIN prompt_test_generations ga ON ga.id = v.generation_a_id
        JOIN prompt_test_generations gb ON gb.id = v.generation_b_id
        WHERE v.session_id = %s
    """
    params: list = [session_id]
    if judge_type:
        query += " AND v.judge_type = %s"
        params.append(judge_type)
    query += " ORDER BY v.created_at"

    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, tuple(params))
            return cursor.fetchall() or []


def get_existing_vote_pairs(session_id: int, judge_type: str = "human") -> set:
    """Получить множество уже оценённых пар (gen_a_id, gen_b_id) для сессии."""
    query = """
        SELECT generation_a_id, generation_b_id
        FROM prompt_test_votes
        WHERE session_id = %s AND judge_type = %s
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query, (session_id, judge_type))
            rows = cursor.fetchall() or []
            return {(r["generation_a_id"], r["generation_b_id"]) for r in rows}


def get_next_comparison(session_id: int) -> Optional[Dict[str, Any]]:
    """Получить следующую неоценённую пару для человеческой оценки.

    Алгоритм:
    1. Загрузить все генерации сессии (сгруппированные по document_id)
    2. Построить все возможные пары для каждого документа
    3. Исключить уже оценённые пары
    4. Вернуть первую неоценённую
    """
    generations = get_generations_for_session(session_id)
    if not generations:
        return None

    # Группировка по document_id
    by_doc: Dict[int, List[Dict[str, Any]]] = {}
    for gen in generations:
        if gen.get("summary_text"):  # Пропускаем неудачные генерации
            doc_id = gen["document_id"]
            by_doc.setdefault(doc_id, []).append(gen)

    voted_pairs = get_existing_vote_pairs(session_id, "human")

    for doc_id in sorted(by_doc.keys()):
        doc_gens = by_doc[doc_id]
        if len(doc_gens) < 2:
            continue
        for gen_a, gen_b in combinations(doc_gens, 2):
            pair = (gen_a["id"], gen_b["id"])
            reverse_pair = (gen_b["id"], gen_a["id"])
            if pair not in voted_pairs and reverse_pair not in voted_pairs:
                return {
                    "document_id": doc_id,
                    "generation_a": gen_a,
                    "generation_b": gen_b,
                }

    return None


# ---------------------------------------------------------------------------
# Документы (чтение из rag_documents/rag_chunks)
# ---------------------------------------------------------------------------


def get_document_content(document_id: int) -> Optional[Dict[str, Any]]:
    """Получить метаданные и чанки документа из RAG-хранилища."""
    doc_query = """
        SELECT id, filename, source_type, status
        FROM rag_documents
        WHERE id = %s
    """
    chunks_query = """
        SELECT chunk_text
        FROM rag_chunks
        WHERE document_id = %s
        ORDER BY chunk_index
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(doc_query, (document_id,))
            doc = cursor.fetchone()
            if not doc:
                return None

            cursor.execute(chunks_query, (document_id,))
            chunk_rows = cursor.fetchall() or []

    chunks = [r["chunk_text"] for r in chunk_rows]
    return {
        "document_id": doc["id"],
        "filename": doc["filename"],
        "source_type": doc["source_type"],
        "chunks": chunks,
        "chunks_count": len(chunk_rows),
        "total_chars": sum(len(c) for c in chunks),
    }


def get_random_document_for_preview() -> Optional[Dict[str, Any]]:
    """Получить случайный документ для предпросмотра промпта."""
    query = """
        SELECT d.id, d.filename,
               (SELECT GROUP_CONCAT(c.chunk_text ORDER BY c.chunk_index SEPARATOR '\\n\\n')
                FROM rag_chunks c WHERE c.document_id = d.id) AS excerpt
        FROM rag_documents d
        WHERE d.status = 'active' AND d.source_type != 'certification'
        ORDER BY RAND()
        LIMIT 1
    """
    with database.get_db_connection() as conn:
        with database.get_cursor(conn) as cursor:
            cursor.execute(query)
            return cursor.fetchone()
