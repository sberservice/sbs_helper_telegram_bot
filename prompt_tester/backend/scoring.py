"""Подсчёт результатов тестирования промптов: Win Rate и Elo-рейтинг.

Elo-рейтинг позволяет агрегировать результаты между сессиями
и сравнивать промпты, которые не встречались напрямую.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Elo-параметры
_ELO_INITIAL = 1500.0
_ELO_K = 32.0


def _elo_expected(rating_a: float, rating_b: float) -> float:
    """Ожидаемый результат игрока A против игрока B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _elo_update(
    rating_a: float,
    rating_b: float,
    score_a: float,
) -> Tuple[float, float]:
    """Обновить Elo-рейтинги после одного матча.

    Args:
        rating_a: Текущий рейтинг A.
        rating_b: Текущий рейтинг B.
        score_a: Результат A (1.0 = победа, 0.5 = ничья, 0.0 = поражение).

    Returns:
        Кортеж (новый_рейтинг_A, новый_рейтинг_B).
    """
    expected_a = _elo_expected(rating_a, rating_b)
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a

    new_a = rating_a + _ELO_K * (score_a - expected_a)
    new_b = rating_b + _ELO_K * (score_b - expected_b)
    return new_a, new_b


def compute_results(
    votes: List[Dict[str, Any]],
    prompts_config: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Подсчитать результаты по списку голосов.

    Args:
        votes: Список голосов из БД (с полями prompt_a_id, prompt_b_id, winner).
        prompts_config: Snapshot конфигурации промптов (для label, model, temperature).

    Returns:
        Список результатов по каждому промпту, отсортированный по Elo убыванию.
    """
    # Построение справочника промптов из snapshot
    prompt_info: Dict[int, Dict[str, Any]] = {}
    if prompts_config:
        for p in prompts_config:
            pid = p.get("id")
            if pid is not None:
                prompt_info[pid] = p

    # Статистика побед/поражений
    stats: Dict[int, Dict[str, int]] = defaultdict(lambda: {
        "wins": 0, "losses": 0, "ties": 0, "skips": 0,
    })
    # Elo-рейтинги
    elos: Dict[int, float] = defaultdict(lambda: _ELO_INITIAL)

    # Собираем все prompt_id из голосов
    seen_prompt_ids: set = set()

    for vote in votes:
        prompt_a_id = vote.get("prompt_a_id")
        prompt_b_id = vote.get("prompt_b_id")
        winner = vote.get("winner", "skip")

        if prompt_a_id is None or prompt_b_id is None:
            continue

        seen_prompt_ids.add(prompt_a_id)
        seen_prompt_ids.add(prompt_b_id)

        if winner == "skip":
            stats[prompt_a_id]["skips"] += 1
            stats[prompt_b_id]["skips"] += 1
            continue

        if winner == "a":
            stats[prompt_a_id]["wins"] += 1
            stats[prompt_b_id]["losses"] += 1
            score_a = 1.0
        elif winner == "b":
            stats[prompt_a_id]["losses"] += 1
            stats[prompt_b_id]["wins"] += 1
            score_a = 0.0
        else:  # tie
            stats[prompt_a_id]["ties"] += 1
            stats[prompt_b_id]["ties"] += 1
            score_a = 0.5

        # Обновляем Elo
        new_a, new_b = _elo_update(elos[prompt_a_id], elos[prompt_b_id], score_a)
        elos[prompt_a_id] = new_a
        elos[prompt_b_id] = new_b

    # Формируем результаты
    results: List[Dict[str, Any]] = []
    for pid in sorted(seen_prompt_ids):
        s = stats[pid]
        total_decisive = s["wins"] + s["losses"]
        win_rate = 0.0
        if total_decisive > 0:
            # Ничьи считаются как 0.5 для win rate
            win_rate = (s["wins"] + s["ties"] * 0.5) / (total_decisive + s["ties"])

        info = prompt_info.get(pid, {})
        results.append({
            "prompt_id": pid,
            "label": info.get("label", f"Prompt #{pid}"),
            "model_name": info.get("model_name"),
            "temperature": info.get("temperature"),
            "wins": s["wins"],
            "losses": s["losses"],
            "ties": s["ties"],
            "skips": s["skips"],
            "win_rate": round(win_rate, 4),
            "elo": round(elos[pid], 1),
        })

    # Сортировка по Elo убыванию
    results.sort(key=lambda r: r["elo"], reverse=True)
    return results


def compute_document_breakdown(
    votes: List[Dict[str, Any]],
    prompts_config: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Результаты в разбивке по документам.

    Returns:
        Список словарей:
        - document_id: int
        - comparisons: [{prompt_a_label, prompt_b_label, winner}]
    """
    prompt_info: Dict[int, str] = {}
    if prompts_config:
        for p in prompts_config:
            pid = p.get("id")
            if pid is not None:
                prompt_info[pid] = p.get("label", f"Prompt #{pid}")

    by_doc: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    for vote in votes:
        doc_id = vote.get("document_id")
        if doc_id is None:
            continue

        prompt_a_id = vote.get("prompt_a_id")
        prompt_b_id = vote.get("prompt_b_id")
        winner = vote.get("winner", "skip")

        by_doc[doc_id].append({
            "prompt_a_id": prompt_a_id,
            "prompt_a_label": prompt_info.get(prompt_a_id, vote.get("prompt_a_label", f"#{prompt_a_id}")),
            "prompt_b_id": prompt_b_id,
            "prompt_b_label": prompt_info.get(prompt_b_id, vote.get("prompt_b_label", f"#{prompt_b_id}")),
            "winner": winner,
        })

    return [
        {"document_id": doc_id, "comparisons": comps}
        for doc_id, comps in sorted(by_doc.items())
    ]


def compute_aggregate_results(
    all_votes: List[Dict[str, Any]],
    all_prompts_configs: List[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Агрегированные результаты по нескольким сессиям.

    Args:
        all_votes: Все голоса из всех сессий.
        all_prompts_configs: Список snapshot-ов промптов из каждой сессии.

    Returns:
        Словарь с агрегированными результатами.
    """
    # Объединяем все конфигурации промптов (последняя версия приоритетнее)
    merged_config: Dict[int, Dict[str, Any]] = {}
    for config in all_prompts_configs:
        for p in config:
            pid = p.get("id")
            if pid is not None:
                merged_config[pid] = p

    merged_list = list(merged_config.values())
    results = compute_results(all_votes, merged_list)

    return {
        "prompt_results": results,
        "sessions_count": len(all_prompts_configs),
        "total_votes": len([v for v in all_votes if v.get("winner") != "skip"]),
    }
