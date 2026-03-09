"""Сервис гибридного поиска по Q&A-парам для песочницы поиска.

Тонкая обёртка вокруг src/group_knowledge/qa_search.py.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from config import ai_settings

logger = logging.getLogger(__name__)


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
            "extraction_type": getattr(pair, "extraction_type", "") or "",
            "group_id": getattr(pair, "group_id", None),
        })
    return formatted


async def hybrid_search(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Выполнить гибридный поиск (BM25 + Vector + RRF) по Q&A-корпусу.

    Args:
        query: Поисковый запрос.
        top_k: Количество результатов.

    Returns:
        Список результатов с полями: qa_pair_id, question_text, answer_text,
        score, bm25_score, vector_score, rrf_score.
    """
    try:
        from src.group_knowledge.qa_search import QASearchService

        service = QASearchService()
        pairs = await service.search(query, top_k=top_k)
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


async def hybrid_search_with_answer(query: str, top_k: int = 10) -> Dict[str, Any]:
    """Вернуть top документов и итоговый ответ так, как его увидел бы пользователь."""
    try:
        from src.group_knowledge.qa_search import QASearchService

        service = QASearchService()
        pairs = await service.search(query, top_k=top_k)
        ranked_results = _build_ranked_results_from_pairs(pairs)
        formatted_results = _format_results(ranked_results)

        relevant_pairs = [item["pair"] for item in ranked_results]
        answer_result = await service.answer_question_from_pairs(query, relevant_pairs)
        final_answer_text = service.format_answer_for_user(answer_result)
        confidence = float(answer_result.get("confidence", 0.0)) if answer_result else None
        threshold = float(ai_settings.GK_RESPONDER_CONFIDENCE_THRESHOLD)

        return {
            "results": formatted_results,
            "answer_preview": {
                "raw_answer_text": answer_result.get("answer") if answer_result else None,
                "final_answer_text": final_answer_text or None,
                "confidence": confidence,
                "would_send": bool(final_answer_text and confidence is not None and confidence >= threshold),
                "threshold": threshold,
                "primary_source_link": answer_result.get("primary_source_link") if answer_result else None,
                "source_pair_ids": answer_result.get("source_pair_ids", []) if answer_result else [],
                "source_message_links": answer_result.get("source_message_links", []) if answer_result else [],
            },
        }
    except ImportError as exc:
        logger.warning(
            "QASearchService недоступен — для песочницы поиска требуется "
            "src.group_knowledge.qa_search: %s",
            exc,
        )
        return {
            "results": [],
            "answer_preview": {
                "raw_answer_text": None,
                "final_answer_text": None,
                "confidence": None,
                "would_send": False,
                "threshold": float(ai_settings.GK_RESPONDER_CONFIDENCE_THRESHOLD),
                "primary_source_link": None,
                "source_pair_ids": [],
                "source_message_links": [],
            },
        }
    except Exception as exc:
        logger.error("Ошибка гибридного поиска с ответом: %s", exc, exc_info=True)
        return {
            "results": [],
            "answer_preview": {
                "raw_answer_text": None,
                "final_answer_text": None,
                "confidence": None,
                "would_send": False,
                "threshold": float(ai_settings.GK_RESPONDER_CONFIDENCE_THRESHOLD),
                "primary_source_link": None,
                "source_pair_ids": [],
                "source_message_links": [],
            },
        }
