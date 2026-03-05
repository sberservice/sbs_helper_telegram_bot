"""Тесты для prompt_tester — scoring и document_sampler."""

import pytest

from prompt_tester.backend.scoring import (
    _elo_expected,
    _elo_update,
    compute_results,
    compute_document_breakdown,
    compute_aggregate_results,
)


# ─── Elo helpers ────────────────────────────────────────


class TestEloExpected:
    """Тесты ожидаемого результата Elo."""

    def test_equal_ratings(self):
        """Равные рейтинги → ожидание 0.5."""
        assert _elo_expected(1500, 1500) == pytest.approx(0.5)

    def test_higher_beats_lower(self):
        """Более высокий рейтинг → ожидание > 0.5."""
        assert _elo_expected(1700, 1500) > 0.5

    def test_lower_vs_higher(self):
        """Более низкий рейтинг → ожидание < 0.5."""
        assert _elo_expected(1300, 1500) < 0.5

    def test_symmetric(self):
        """Oжидания A и B в сумме = 1."""
        ea = _elo_expected(1600, 1400)
        eb = _elo_expected(1400, 1600)
        assert ea + eb == pytest.approx(1.0)


class TestEloUpdate:
    """Тесты обновления Elo-рейтинга."""

    def test_winner_gains(self):
        """Победитель получает рейтинг."""
        new_a, new_b = _elo_update(1500, 1500, 1.0)
        assert new_a > 1500
        assert new_b < 1500

    def test_loser_loses(self):
        """Проигравший теряет рейтинг."""
        new_a, new_b = _elo_update(1500, 1500, 0.0)
        assert new_a < 1500
        assert new_b > 1500

    def test_tie_no_change_equal(self):
        """Ничья при равных рейтингах → рейтинги не меняются."""
        new_a, new_b = _elo_update(1500, 1500, 0.5)
        assert new_a == pytest.approx(1500.0)
        assert new_b == pytest.approx(1500.0)

    def test_upset_big_change(self):
        """Неожиданная победа слабого → большое изменение."""
        new_a, new_b = _elo_update(1300, 1700, 1.0)
        # A (слабый) победил → его прирост значительный
        assert new_a - 1300 > 20

    def test_conserves_total(self):
        """Сумма рейтингов сохраняется."""
        new_a, new_b = _elo_update(1600, 1400, 1.0)
        assert new_a + new_b == pytest.approx(1600 + 1400)


# ─── compute_results ────────────────────────────────────


class TestComputeResults:
    """Тесты основного подсчёта результатов."""

    def test_empty_votes(self):
        """Пустой список голосов → пустой результат."""
        assert compute_results([]) == []

    def test_single_vote_a_wins(self):
        """Один голос: A побеждает."""
        votes = [{"prompt_a_id": 1, "prompt_b_id": 2, "winner": "a"}]
        results = compute_results(votes)
        assert len(results) == 2

        # Первый по Elo = победитель
        winner = results[0]
        assert winner["prompt_id"] == 1
        assert winner["wins"] == 1
        assert winner["losses"] == 0
        assert winner["elo"] > 1500

        loser = results[1]
        assert loser["prompt_id"] == 2
        assert loser["losses"] == 1
        assert loser["elo"] < 1500

    def test_single_vote_b_wins(self):
        """Один голос: B побеждает."""
        votes = [{"prompt_a_id": 1, "prompt_b_id": 2, "winner": "b"}]
        results = compute_results(votes)
        winner = results[0]
        assert winner["prompt_id"] == 2
        assert winner["wins"] == 1

    def test_tie(self):
        """Ничья учитывается корректно."""
        votes = [{"prompt_a_id": 1, "prompt_b_id": 2, "winner": "tie"}]
        results = compute_results(votes)
        assert all(r["ties"] == 1 for r in results)
        assert all(r["wins"] == 0 for r in results)
        assert all(r["elo"] == pytest.approx(1500.0) for r in results)

    def test_skip_ignored_in_elo(self):
        """Пропуски не влияют на Elo."""
        votes = [{"prompt_a_id": 1, "prompt_b_id": 2, "winner": "skip"}]
        results = compute_results(votes)
        assert all(r["skips"] == 1 for r in results)
        assert all(r["elo"] == pytest.approx(1500.0) for r in results)

    def test_multiple_prompts(self):
        """Три промпта, несколько голосов."""
        votes = [
            {"prompt_a_id": 1, "prompt_b_id": 2, "winner": "a"},
            {"prompt_a_id": 1, "prompt_b_id": 3, "winner": "a"},
            {"prompt_a_id": 2, "prompt_b_id": 3, "winner": "b"},
        ]
        results = compute_results(votes)
        assert len(results) == 3

        # Prompt 1: 2 победы, 0 поражений
        p1 = next(r for r in results if r["prompt_id"] == 1)
        assert p1["wins"] == 2
        assert p1["losses"] == 0

        # Prompt 3: 1 победа, 1 поражение
        p3 = next(r for r in results if r["prompt_id"] == 3)
        assert p3["wins"] == 1
        assert p3["losses"] == 1

        # Промпт 1 должен быть первым по Elo
        assert results[0]["prompt_id"] == 1

    def test_win_rate_calculation(self):
        """Win Rate учитывает ничьи как 0.5."""
        votes = [
            {"prompt_a_id": 1, "prompt_b_id": 2, "winner": "a"},
            {"prompt_a_id": 1, "prompt_b_id": 2, "winner": "tie"},
        ]
        results = compute_results(votes)
        p1 = next(r for r in results if r["prompt_id"] == 1)
        # wins=1, ties=1 → win_rate = (1 + 0.5) / (1 + 0 + 1) = 0.75
        assert p1["win_rate"] == pytest.approx(0.75)

    def test_prompt_config_labels(self):
        """Метки из prompts_config подставляются."""
        votes = [{"prompt_a_id": 10, "prompt_b_id": 20, "winner": "a"}]
        config = [
            {"id": 10, "label": "Formal"},
            {"id": 20, "label": "Casual"},
        ]
        results = compute_results(votes, config)
        r10 = next(r for r in results if r["prompt_id"] == 10)
        assert r10["label"] == "Formal"

    def test_sorted_by_elo_desc(self):
        """Результаты отсортированы по Elo убыванию."""
        votes = [
            {"prompt_a_id": 1, "prompt_b_id": 2, "winner": "b"},
            {"prompt_a_id": 2, "prompt_b_id": 3, "winner": "b"},
        ]
        results = compute_results(votes)
        elos = [r["elo"] for r in results]
        assert elos == sorted(elos, reverse=True)


# ─── compute_document_breakdown ─────────────────────────


class TestComputeDocumentBreakdown:
    """Тесты разбивки результатов по документам."""

    def test_empty(self):
        """Пустых голосов → пустой результат."""
        assert compute_document_breakdown([]) == []

    def test_groups_by_document(self):
        """Голоса группируются по document_id."""
        votes = [
            {"document_id": 1, "prompt_a_id": 10, "prompt_b_id": 20, "winner": "a"},
            {"document_id": 1, "prompt_a_id": 10, "prompt_b_id": 30, "winner": "b"},
            {"document_id": 2, "prompt_a_id": 10, "prompt_b_id": 20, "winner": "tie"},
        ]
        breakdown = compute_document_breakdown(votes)
        assert len(breakdown) == 2
        doc1 = next(d for d in breakdown if d["document_id"] == 1)
        assert len(doc1["comparisons"]) == 2

    def test_labels_from_config(self):
        """Метки берутся из config."""
        votes = [
            {"document_id": 5, "prompt_a_id": 1, "prompt_b_id": 2, "winner": "a"},
        ]
        config = [{"id": 1, "label": "Alpha"}, {"id": 2, "label": "Beta"}]
        breakdown = compute_document_breakdown(votes, config)
        comp = breakdown[0]["comparisons"][0]
        assert comp["prompt_a_label"] == "Alpha"
        assert comp["prompt_b_label"] == "Beta"


# ─── compute_aggregate_results ──────────────────────────


class TestComputeAggregateResults:
    """Тесты агрегированных результатов по нескольким сессиям."""

    def test_empty(self):
        """Нулевые данные → пустой результат."""
        result = compute_aggregate_results([], [])
        assert result["prompt_results"] == []
        assert result["sessions_count"] == 0
        assert result["total_votes"] == 0

    def test_merges_sessions(self):
        """Результаты объединяются из двух сессий."""
        votes = [
            {"prompt_a_id": 1, "prompt_b_id": 2, "winner": "a"},
            {"prompt_a_id": 1, "prompt_b_id": 2, "winner": "a"},
        ]
        configs = [
            [{"id": 1, "label": "P1"}, {"id": 2, "label": "P2"}],
            [{"id": 1, "label": "P1"}, {"id": 2, "label": "P2"}],
        ]
        result = compute_aggregate_results(votes, configs)
        assert result["sessions_count"] == 2
        assert result["total_votes"] == 2
        assert len(result["prompt_results"]) == 2

    def test_skips_not_counted_in_total(self):
        """Пропуски не считаются в total_votes."""
        votes = [
            {"prompt_a_id": 1, "prompt_b_id": 2, "winner": "a"},
            {"prompt_a_id": 1, "prompt_b_id": 2, "winner": "skip"},
        ]
        configs = [[{"id": 1, "label": "P1"}, {"id": 2, "label": "P2"}]]
        result = compute_aggregate_results(votes, configs)
        assert result["total_votes"] == 1
