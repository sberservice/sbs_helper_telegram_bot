"""Тесты БД-утилит тестера промптов Group Knowledge."""

from admin_web.modules.gk_knowledge.db_prompt_tester import (
    _build_shuffled_comparison_pairs,
    estimate_comparisons,
)


def test_estimate_comparisons_uses_n_choose_2_formula() -> None:
    """Оценка количества сравнений считает C(n,2) × число цепочек."""
    assert estimate_comparisons(prompt_count=3, chains_count=10) == 30
    assert estimate_comparisons(prompt_count=1, chains_count=10) == 0
    assert estimate_comparisons(prompt_count=3, chains_count=0) == 0


def test_build_shuffled_comparison_pairs_creates_all_prompt_pairs() -> None:
    """Генерируются все попарные сравнения между промптами по каждому слоту."""
    pairs = _build_shuffled_comparison_pairs(
        {
            11: [101, 102],
            22: [201, 202],
            33: [301, 302],
        }
    )

    assert len(pairs) == 6

    normalized = {tuple(sorted((a, b))) for a, b in pairs}
    assert normalized == {
        (101, 201), (101, 301), (201, 301),
        (102, 202), (102, 302), (202, 302),
    }
