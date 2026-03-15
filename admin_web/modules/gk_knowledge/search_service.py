"""Сервис гибридного поиска по Q&A-парам для песочницы поиска.

Тонкая обёртка вокруг src/group_knowledge/qa_search.py.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from config import ai_settings

logger = logging.getLogger(__name__)


_SEARCH_SERVICE: Optional[Any] = None
_SEARCH_SERVICE_LOCK = threading.Lock()


def _get_search_service() -> Any:
    """Вернуть singleton-экземпляр QASearchService для admin web."""
    global _SEARCH_SERVICE
    if _SEARCH_SERVICE is not None:
        return _SEARCH_SERVICE

    with _SEARCH_SERVICE_LOCK:
        if _SEARCH_SERVICE is None:
            from src.group_knowledge.qa_search import QASearchService

            _SEARCH_SERVICE = QASearchService()
            diagnostics = _SEARCH_SERVICE.warmup(preload_vector_model=True)
            logger.info(
                "GK search warmup (admin web): corpus_pairs=%s corpus_signature=%s vector_model_preloaded=%s vector_index_ready=%s",
                diagnostics.get("corpus_pairs"),
                diagnostics.get("corpus_signature"),
                diagnostics.get("vector_model_preloaded"),
                diagnostics.get("vector_index_ready"),
            )
            if (
                ai_settings.AI_RAG_VECTOR_EMBEDDING_FAIL_FAST
                and (
                    not diagnostics.get("vector_model_preloaded", False)
                    or not diagnostics.get("vector_index_ready", False)
                )
            ):
                raise RuntimeError(
                    "GK search warmup fail-fast: vector ресурсы недоступны в admin web"
                )
    return _SEARCH_SERVICE


def get_search_service() -> Any:
    """Публичный accessor singleton-экземпляра QASearchService для admin web."""
    return _get_search_service()


def _build_ranked_results_from_pairs(pairs: List[Any]) -> List[Dict[str, Any]]:
    """Собрать результаты из QASearchService.search() с диагностическими score."""
    ranked: List[Dict[str, Any]] = []
    for pair in pairs:
        bm25_score = float(getattr(pair, "search_bm25_score", 0.0) or 0.0)
        vector_score = float(getattr(pair, "search_vector_score", 0.0) or 0.0)
        present_scores = [s for s in (bm25_score, vector_score) if s > 0.0]
        score = sum(present_scores) / len(present_scores) if present_scores else 0.0
        ranked.append(
            {
                "pair": pair,
                "score": score,
                "bm25_score": bm25_score,
                "vector_score": vector_score,
                "rrf_score": score,
            }
        )
    return ranked


def _format_results(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Нормализовать внутренние результаты поиска для фронтенда."""
    formatted: List[Dict[str, Any]] = []
    for item in items:
        pair = item["pair"]
        question_text = getattr(pair, "question_text", "") or ""
        answer_text = getattr(pair, "answer_text", "") or ""
        rrf_score = float(item.get("rrf_score", item.get("score", 0.0)) or 0.0)
        bm25_score = float(item.get("bm25_score", 0.0) or 0.0)
        vector_score = float(item.get("vector_score", 0.0) or 0.0)
        formatted.append({
            "qa_pair_id": getattr(pair, "id", None),
            "question": question_text,
            "question_text": question_text,
            "answer": answer_text,
            "answer_text": answer_text,
            "score": round(rrf_score, 4),
            "bm25_score": round(bm25_score, 4),
            "vector_score": round(vector_score, 4),
            "rrf_score": round(rrf_score, 4),
            "confidence": round(float(getattr(pair, "confidence", 0.0) or 0.0), 3),
            "confidence_reason": str(getattr(pair, "confidence_reason", "") or ""),
            "fullness": (
                round(float(getattr(pair, "fullness", 0.0)), 3)
                if getattr(pair, "fullness", None) is not None
                else None
            ),
            "extraction_type": getattr(pair, "extraction_type", "") or "",
            "group_id": getattr(pair, "group_id", None),
        })
    return formatted


async def hybrid_search(query: str, top_k: int = 10, group_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Выполнить гибридный поиск (BM25 + Vector + RRF) по Q&A-корпусу.

    Args:
        query: Поисковый запрос.
        top_k: Количество результатов.
        group_id: Идентификатор группы для фильтрации (None = все группы).

    Returns:
        Список результатов с полями: qa_pair_id, question_text, answer_text,
        score, bm25_score, vector_score, rrf_score.
    """
    try:
        service = _get_search_service()
        pairs = await service.search(query, top_k=top_k, group_id=group_id)
        ranked_results = _build_ranked_results_from_pairs(pairs)
        return _format_results(ranked_results)

    except ImportError as exc:
        logger.warning(
            "QASearchService недоступен — для песочницы поиска требуется "
            "src.group_knowledge.qa_search: %s",
            exc,
        )
        return []
    except Exception as exc:
        logger.error("Ошибка гибридного поиска: %s", exc, exc_info=True)
        return []


async def hybrid_search_with_answer(
    query: str,
    top_k: int = 10,
    group_id: Optional[int] = None,
    model_override: Optional[str] = None,
    temperature_override: Optional[float] = None,
) -> Dict[str, Any]:
    """Вернуть top документов и итоговый ответ так, как его увидел бы пользователь."""
    started = time.perf_counter()
    progress_stages: List[Dict[str, Any]] = [
        {"key": "init", "label": "Подготовка запроса", "status": "done", "duration_ms": 0},
        {"key": "retrieve", "label": "Гибридный поиск по Q&A", "status": "running", "duration_ms": 0},
        {"key": "answer", "label": "Генерация итогового ответа", "status": "pending", "duration_ms": 0},
    ]

    retrieval_started = time.perf_counter()
    try:
        service = _get_search_service()
        pairs = await service.search(query, top_k=top_k, group_id=group_id)
        progress_stages[1]["status"] = "done"
        progress_stages[1]["duration_ms"] = int((time.perf_counter() - retrieval_started) * 1000)
        progress_stages[2]["status"] = "running"

        answer_started = time.perf_counter()
        ranked_results = _build_ranked_results_from_pairs(pairs)
        formatted_results = _format_results(ranked_results)

        relevant_pairs = [item["pair"] for item in ranked_results]
        answer_result = await service.answer_question_from_pairs(
            query,
            relevant_pairs,
            group_id=group_id,
            model_override=model_override,
            temperature_override=temperature_override,
        )
        final_answer_text = service.format_answer_for_user(answer_result)
        confidence = float(answer_result.get("confidence", 0.0)) if answer_result else None
        threshold = float(ai_settings.get_active_gk_responder_confidence_threshold())

        progress_stages[2]["status"] = "done"
        progress_stages[2]["duration_ms"] = int((time.perf_counter() - answer_started) * 1000)

        return {
            "results": formatted_results,
            "answer_preview": {
                "raw_answer_text": answer_result.get("answer") if answer_result else None,
                "final_answer_text": final_answer_text or None,
                "confidence": confidence,
                "confidence_reason": (
                    str(answer_result.get("confidence_reason") or "").strip() or None
                ) if answer_result else None,
                "would_send": bool(final_answer_text and confidence is not None and confidence >= threshold),
                "threshold": threshold,
                "primary_source_link": answer_result.get("primary_source_link") if answer_result else None,
                "source_pair_ids": answer_result.get("source_pair_ids", []) if answer_result else [],
                "source_message_links": answer_result.get("source_message_links", []) if answer_result else [],
            },
            "progress_stages": progress_stages,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    except ImportError as exc:
        logger.warning(
            "QASearchService недоступен — для песочницы поиска требуется "
            "src.group_knowledge.qa_search: %s",
            exc,
        )
        progress_stages[1]["status"] = "error"
        progress_stages[1]["duration_ms"] = int((time.perf_counter() - retrieval_started) * 1000)
        progress_stages[2]["status"] = "skipped"
        return {
            "results": [],
            "answer_preview": {
                "raw_answer_text": None,
                "final_answer_text": None,
                "confidence": None,
                "confidence_reason": None,
                "would_send": False,
                "threshold": float(ai_settings.get_active_gk_responder_confidence_threshold()),
                "primary_source_link": None,
                "source_pair_ids": [],
                "source_message_links": [],
            },
            "progress_stages": progress_stages,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:
        logger.error("Ошибка гибридного поиска с ответом: %s", exc, exc_info=True)
        progress_stages[1]["status"] = "error"
        progress_stages[1]["duration_ms"] = int((time.perf_counter() - retrieval_started) * 1000)
        progress_stages[2]["status"] = "skipped"
        return {
            "results": [],
            "answer_preview": {
                "raw_answer_text": None,
                "final_answer_text": None,
                "confidence": None,
                "confidence_reason": None,
                "would_send": False,
                "threshold": float(ai_settings.get_active_gk_responder_confidence_threshold()),
                "primary_source_link": None,
                "source_pair_ids": [],
                "source_message_links": [],
            },
            "progress_stages": progress_stages,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
