"""Тесты логики отдельного image prompt tester для Group Knowledge."""

from admin_web.modules.gk_knowledge.db_image_prompt_tester import (
    _build_shuffled_image_comparisons,
    _compute_results,
    _normalize_ids_json,
    estimate_comparisons,
)


def test_normalize_ids_json_handles_valid_and_invalid_values() -> None:
    """Корректно нормализует JSON-массив id и отбрасывает мусор."""
    assert _normalize_ids_json('[1, "2", "x", null, 5]') == [1, 2, 5]
    assert _normalize_ids_json([10, "11", "bad"]) == [10, 11]
    assert _normalize_ids_json('') == []
    assert _normalize_ids_json(None) == []


def test_compute_results_applies_elo_and_metrics() -> None:
    """Считает Elo/метрики по blind-голосам и сортирует по рейтингу."""
    prompt_labels = {
        1: 'Prompt A',
        2: 'Prompt B',
        3: 'Prompt C',
    }
    votes = [
        {'prompt_a_id': 1, 'prompt_b_id': 2, 'winner': 'a'},
        {'prompt_a_id': 1, 'prompt_b_id': 3, 'winner': 'tie'},
        {'prompt_a_id': 2, 'prompt_b_id': 3, 'winner': 'b'},
        {'prompt_a_id': 1, 'prompt_b_id': 2, 'winner': 'skip'},
    ]

    rows = _compute_results(votes=votes, prompt_labels=prompt_labels)

    assert len(rows) == 3
    assert rows[0]['elo'] >= rows[1]['elo'] >= rows[2]['elo']

    by_id = {int(row['prompt_id']): row for row in rows}
    assert by_id[1]['wins'] == 1
    assert by_id[1]['ties'] == 1
    assert by_id[1]['skips'] == 1
    assert by_id[1]['matches'] == 2

    assert by_id[2]['losses'] >= 1
    assert by_id[3]['wins'] >= 1
    assert 0.0 <= by_id[1]['win_rate'] <= 1.0


def test_estimate_comparisons_uses_n_choose_2_formula() -> None:
    """Оценка количества сравнений считает C(n,2) × число изображений."""
    assert estimate_comparisons(prompt_count=4, image_count=10) == 60
    assert estimate_comparisons(prompt_count=1, image_count=10) == 0
    assert estimate_comparisons(prompt_count=4, image_count=0) == 0


def test_build_shuffled_image_comparisons_creates_all_pairs_per_image() -> None:
    """Для каждой картинки строятся все попарные сравнения между промптами."""
    comparisons = _build_shuffled_image_comparisons(
        {
            101: {1: 1001, 2: 1002, 3: 1003},
            102: {1: 2001, 2: 2002, 3: 2003},
        }
    )

    assert len(comparisons) == 6

    grouped = {101: set(), 102: set()}
    for image_queue_id, gen_a, gen_b in comparisons:
        assert image_queue_id in grouped
        grouped[image_queue_id].add(tuple(sorted((gen_a, gen_b))))

    assert grouped[101] == {(1001, 1002), (1001, 1003), (1002, 1003)}
    assert grouped[102] == {(2001, 2002), (2001, 2003), (2002, 2003)}
