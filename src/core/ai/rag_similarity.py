"""CLI и утилиты для сравнения похожести двух предложений в RAG-сценариях."""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
from difflib import SequenceMatcher
from typing import List, Optional

from src.core.ai.vector_search import LocalEmbeddingProvider

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """Нормализовать текст перед сравнением."""
    return " ".join((text or "").strip().split())


def _tokenize(text: str) -> List[str]:
    """Разбить текст на токены для лексической оценки."""
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


def _jaccard_similarity(left: str, right: str) -> float:
    """Посчитать Jaccard similarity по множествам токенов."""
    left_tokens = set(_tokenize(left))
    right_tokens = set(_tokenize(right))
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    intersection_size = len(left_tokens.intersection(right_tokens))
    union_size = len(left_tokens.union(right_tokens))
    if union_size == 0:
        return 0.0
    return float(intersection_size / union_size)


def _cosine_similarity(left: List[float], right: List[float]) -> Optional[float]:
    """Посчитать cosine similarity для двух dense-векторов."""
    if not left or not right or len(left) != len(right):
        return None

    left_norm = math.sqrt(sum(float(value) * float(value) for value in left))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return None

    dot_product = sum(float(left[index]) * float(right[index]) for index in range(len(left)))
    similarity = dot_product / (left_norm * right_norm)
    return float(max(-1.0, min(1.0, similarity)))


def calculate_sentence_similarity(
    sentence_a: str,
    sentence_b: str,
    embedding_provider: Optional[LocalEmbeddingProvider] = None,
) -> dict:
    """Рассчитать набор метрик похожести для двух предложений."""
    normalized_a = _normalize_text(sentence_a)
    normalized_b = _normalize_text(sentence_b)

    if not normalized_a or not normalized_b:
        raise ValueError("Оба предложения должны быть непустыми")

    provider = embedding_provider or LocalEmbeddingProvider()
    semantic_similarity: Optional[float] = None

    try:
        embeddings = provider.encode_texts([normalized_a, normalized_b])
        if len(embeddings) >= 2:
            semantic_similarity = _cosine_similarity(embeddings[0], embeddings[1])
    except Exception as exc:
        logger.warning("Не удалось рассчитать embedding similarity: %s", exc)

    lexical_similarity = _jaccard_similarity(normalized_a, normalized_b)
    sequence_similarity = float(SequenceMatcher(None, normalized_a, normalized_b).ratio())

    available_scores = [lexical_similarity, sequence_similarity]
    if semantic_similarity is not None:
        available_scores.append(semantic_similarity)
    combined_similarity = float(sum(available_scores) / len(available_scores))

    return {
        "sentence_a": normalized_a,
        "sentence_b": normalized_b,
        "semantic_similarity": semantic_similarity,
        "lexical_similarity": lexical_similarity,
        "sequence_similarity": sequence_similarity,
        "combined_similarity": combined_similarity,
    }


def _build_parser() -> argparse.ArgumentParser:
    """Построить парсер аргументов CLI."""
    parser = argparse.ArgumentParser(
        description="Сравнить похожесть двух предложений для оценки качества RAG-модели",
    )
    parser.add_argument(
        "--sentence-a",
        required=True,
        help="Первое предложение для сравнения",
    )
    parser.add_argument(
        "--sentence-b",
        required=True,
        help="Второе предложение для сравнения",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="Порог итоговой похожести для статуса 'похожи' (по умолчанию: 0.7)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывести результат в JSON",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Точка входа CLI-утилиты сравнения предложений."""
    raw_argv = list(argv) if argv is not None else sys.argv[1:]

    if "--interactive" in raw_argv or "-i" in raw_argv:
        filtered_argv = [
            arg for arg in raw_argv
            if arg not in ("--interactive", "-i")
        ]
        from src.core.ai.rag_similarity_interactive import (
            main as interactive_main,
        )
        return interactive_main(filtered_argv)

    parser = _build_parser()
    args = parser.parse_args(raw_argv)

    if args.threshold < -1.0 or args.threshold > 1.0:
        parser.error("--threshold должен быть в диапазоне от -1 до 1")

    try:
        result = calculate_sentence_similarity(args.sentence_a, args.sentence_b)
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    verdict = "похожи" if result["combined_similarity"] >= float(args.threshold) else "не похожи"
    result["threshold"] = float(args.threshold)
    result["verdict"] = verdict

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    semantic_value = result["semantic_similarity"]
    semantic_text = "недоступно" if semantic_value is None else f"{semantic_value:.4f}"
    print("RAG similarity check")
    print(f"- sentence_a: {result['sentence_a']}")
    print(f"- sentence_b: {result['sentence_b']}")
    print(f"- semantic_similarity: {semantic_text}")
    print(f"- lexical_similarity: {result['lexical_similarity']:.4f}")
    print(f"- sequence_similarity: {result['sequence_similarity']:.4f}")
    print(f"- combined_similarity: {result['combined_similarity']:.4f}")
    print(f"- threshold: {result['threshold']:.4f}")
    print(f"- verdict: {result['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
