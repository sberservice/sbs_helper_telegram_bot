"""Тесты логики final prompt tester для Group Knowledge."""

from admin_web.modules.gk_knowledge.db_final_prompt_tester import (
    _build_shuffled_question_comparisons,
    _compute_results,
    _normalize_ids_json,
    _normalize_questions_json,
    _truncate_nullable_text,
    estimate_comparisons,
)


def test_normalize_ids_json_handles_valid_and_invalid_values() -> None:
    """Корректно нормализует JSON-массив id и отбрасывает мусор."""
    assert _normalize_ids_json('[1, "2", "x", null, 5]') == [1, 2, 5]
    assert _normalize_ids_json([10, "11", "bad"]) == [10, 11]
    assert _normalize_ids_json('') == []
    assert _normalize_ids_json(None) == []


def test_normalize_questions_json_filters_empty_entries() -> None:
    """Возвращает только непустые вопросы из JSON-списка."""
    assert _normalize_questions_json('[" Где чек? ", "", null, "Ошибка ФН"]') == [
        'Где чек?',
        'Ошибка ФН',
    ]
    assert _normalize_questions_json(['  ', 'Q1', 'Q2']) == ['Q1', 'Q2']
    assert _normalize_questions_json('') == []
    assert _normalize_questions_json(None) == []


def test_estimate_comparisons_uses_n_choose_2_formula() -> None:
    """Оценка количества сравнений считает C(n,2) × число вопросов."""
    assert estimate_comparisons(prompt_count=4, question_count=10) == 60
    assert estimate_comparisons(prompt_count=1, question_count=10) == 0
    assert estimate_comparisons(prompt_count=4, question_count=0) == 0


def test_build_shuffled_question_comparisons_creates_all_pairs_per_question() -> None:
    """Для каждого вопроса строятся все попарные сравнения между промптами."""
    comparisons = _build_shuffled_question_comparisons(
        {
            0: {1: 1001, 2: 1002, 3: 1003},
            1: {1: 2001, 2: 2002, 3: 2003},
        }
    )

    assert len(comparisons) == 6

    grouped = {0: set(), 1: set()}
    for question_index, gen_a, gen_b in comparisons:
        assert question_index in grouped
        grouped[question_index].add(tuple(sorted((gen_a, gen_b))))

    assert grouped[0] == {(1001, 1002), (1001, 1003), (1002, 1003)}
    assert grouped[1] == {(2001, 2002), (2001, 2003), (2002, 2003)}


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


def test_truncate_nullable_text_handles_empty_and_short_values() -> None:
    """Не обрезает короткие значения и возвращает None для пустых."""
    assert _truncate_nullable_text(None, 10) is None
    assert _truncate_nullable_text("   ", 10) is None
    assert _truncate_nullable_text("abc", 10) == "abc"


def test_truncate_nullable_text_truncates_long_values() -> None:
    """Обрезает строку до лимита, чтобы запись не падала с Data too long."""
    assert _truncate_nullable_text("abcdefgh", 5) == "abcde"


def test_truncate_nullable_text_keeps_text_for_unbounded_columns() -> None:
    """Для TEXT-колонок (max_length<=0) возвращает исходный текст без обрезки."""
    long_text = "x" * 2000
    assert _truncate_nullable_text(long_text, 0) == long_text
