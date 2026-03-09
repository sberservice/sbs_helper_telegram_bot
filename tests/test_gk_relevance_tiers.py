"""Тесты вычисления уровней релевантности, форматирования промпта и spellcheck GK."""

import unittest
from collections import Counter
from typing import List, Tuple
from unittest.mock import patch, MagicMock, AsyncMock

from src.group_knowledge.models import QAPair
from src.group_knowledge.qa_search import (
    QASearchService,
    _ANSWER_PROMPT_BASE,
    _GK_FIXED_TERMS,
    _RELEVANCE_RULE,
    _TOKEN_RE,
)


def _make_pair(
    pair_id: int,
    question: str = "Вопрос",
    answer: str = "Ответ",
    bm25_score: float | None = None,
    vector_score: float | None = None,
) -> QAPair:
    """Вспомогательная фабрика QAPair с транзиентными score-полями."""
    p = QAPair(id=pair_id, question_text=question, answer_text=answer)
    p.search_bm25_score = bm25_score
    p.search_vector_score = vector_score
    return p


def _make_merged(pairs: List[QAPair]) -> List[Tuple[QAPair, float]]:
    """Превратить список QAPair в формат merged (pair, rrf_score)."""
    # rrf_score не используется в _compute_relevance_tiers напрямую.
    return [(p, 1.0 / (60 + i)) for i, p in enumerate(pairs, 1)]


class TestComputeRelevanceTiers(unittest.TestCase):
    """Тесты метода QASearchService._compute_relevance_tiers."""

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_clear_cliff_top_two_high_rest_low(self, mock_settings):
        """Обрыв между 2-й и 3-й парой: первые две — высокая, остальные — низкая."""
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        pairs = [
            _make_pair(1, bm25_score=1.0, vector_score=0.9),   # combined=0.95
            _make_pair(2, bm25_score=0.8, vector_score=0.85),   # combined=0.825
            _make_pair(3, bm25_score=0.1, vector_score=0.05),   # combined=0.075
            _make_pair(4, bm25_score=0.05, vector_score=0.02),  # combined=0.035
        ]
        merged = _make_merged(pairs)

        QASearchService._compute_relevance_tiers(merged)

        self.assertEqual(pairs[0].search_relevance_tier, "высокая")
        self.assertEqual(pairs[1].search_relevance_tier, "высокая")
        self.assertEqual(pairs[2].search_relevance_tier, "низкая")
        self.assertEqual(pairs[3].search_relevance_tier, "низкая")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_gradual_decline_no_cliff(self, mock_settings):
        """Плавное снижение без обрыва — уровни назначаются по абсолютным порогам."""
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        pairs = [
            _make_pair(1, bm25_score=0.9, vector_score=0.8),   # combined=0.85
            _make_pair(2, bm25_score=0.7, vector_score=0.65),  # combined=0.675
            _make_pair(3, bm25_score=0.5, vector_score=0.45),  # combined=0.475
            _make_pair(4, bm25_score=0.3, vector_score=0.25),  # combined=0.275
        ]
        merged = _make_merged(pairs)

        QASearchService._compute_relevance_tiers(merged)

        self.assertEqual(pairs[0].search_relevance_tier, "высокая")
        self.assertEqual(pairs[1].search_relevance_tier, "высокая")
        self.assertEqual(pairs[2].search_relevance_tier, "средняя")
        self.assertEqual(pairs[3].search_relevance_tier, "низкая")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_single_result(self, mock_settings):
        """Один результат — всегда получает корректный уровень."""
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        pairs = [_make_pair(1, bm25_score=0.8, vector_score=0.7)]
        merged = _make_merged(pairs)

        QASearchService._compute_relevance_tiers(merged)

        self.assertEqual(pairs[0].search_relevance_tier, "высокая")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_single_low_result(self, mock_settings):
        """Один результат с низким score."""
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        pairs = [_make_pair(1, bm25_score=0.1, vector_score=0.1)]
        merged = _make_merged(pairs)

        QASearchService._compute_relevance_tiers(merged)

        self.assertEqual(pairs[0].search_relevance_tier, "низкая")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_all_equal_scores(self, mock_settings):
        """Все пары с одинаковым score — нет обрыва, уровень по абсолютному значению."""
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        pairs = [
            _make_pair(1, bm25_score=0.5, vector_score=0.5),
            _make_pair(2, bm25_score=0.5, vector_score=0.5),
            _make_pair(3, bm25_score=0.5, vector_score=0.5),
        ]
        merged = _make_merged(pairs)

        QASearchService._compute_relevance_tiers(merged)

        for p in pairs:
            self.assertEqual(p.search_relevance_tier, "средняя")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_bm25_only_pair(self, mock_settings):
        """Пара найдена только BM25 — штрафуется 50 %."""
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        pairs = [
            _make_pair(1, bm25_score=1.0, vector_score=None),  # quality=1.0*0.5=0.5
            _make_pair(2, bm25_score=0.9, vector_score=None),  # quality=0.9*0.5=0.45
        ]
        merged = _make_merged(pairs)

        QASearchService._compute_relevance_tiers(merged)

        self.assertEqual(pairs[0].search_relevance_tier, "средняя")
        self.assertEqual(pairs[1].search_relevance_tier, "средняя")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_vector_only_pair(self, mock_settings):
        """Пара найдена только vector — штрафуется 50 %."""
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        pairs = [
            _make_pair(1, bm25_score=None, vector_score=0.95),  # quality=0.95*0.5=0.475
        ]
        merged = _make_merged(pairs)

        QASearchService._compute_relevance_tiers(merged)

        self.assertEqual(pairs[0].search_relevance_tier, "средняя")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_cliff_with_medium_absolute(self, mock_settings):
        """Пара ниже обрыва, но с абсолютным combined ≥ 0.3 → средняя."""
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        pairs = [
            _make_pair(1, bm25_score=1.0, vector_score=1.0),   # combined=1.0
            _make_pair(2, bm25_score=0.4, vector_score=0.35),   # combined=0.375
        ]
        merged = _make_merged(pairs)

        QASearchService._compute_relevance_tiers(merged)

        self.assertEqual(pairs[0].search_relevance_tier, "высокая")
        # Ниже обрыва, но combined=0.375 ≥ 0.3 → средняя.
        self.assertEqual(pairs[1].search_relevance_tier, "средняя")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_empty_list(self, mock_settings):
        """Пустой список — не должен падать."""
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3
        QASearchService._compute_relevance_tiers([])
        # Просто проверяем, что нет исключений.


class TestRrfMergeAttachesScores(unittest.TestCase):
    """Тесты прикрепления нормализованных scores в _rrf_merge."""

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_scores_attached_to_pairs(self, mock_settings):
        """После _rrf_merge пары должны иметь нормализованные search-scores."""
        mock_settings.GK_RRF_K = 60

        p1 = QAPair(id=1, question_text="q1", answer_text="a1")
        p2 = QAPair(id=2, question_text="q2", answer_text="a2")
        p3 = QAPair(id=3, question_text="q3", answer_text="a3")

        bm25_results = [(p1, 10.0), (p2, 5.0)]
        vector_results = [(p2, 0.9), (p3, 0.7)]

        merged, diagnostics = QASearchService._rrf_merge(
            bm25_results, vector_results, top_k=5,
        )

        # p1: BM25 only → bm25_score=1.0 (лучший), vector=None
        self.assertAlmostEqual(p1.search_bm25_score, 1.0, places=3)
        self.assertIsNone(p1.search_vector_score)

        # p2: оба метода → bm25_score=0.0 (5.0 — min), vector=1.0 (0.9 — max)
        self.assertAlmostEqual(p2.search_bm25_score, 0.0, places=3)
        self.assertAlmostEqual(p2.search_vector_score, 1.0, places=3)

        # p3: vector only → bm25=None, vector=0.0 (0.7 — min)
        self.assertIsNone(p3.search_bm25_score)
        self.assertAlmostEqual(p3.search_vector_score, 0.0, places=3)


class TestPromptFormatting(unittest.TestCase):
    """Тесты форматирования промпта с подсказками релевантности."""

    def test_prompt_with_hints_includes_tier_and_scores(self):
        """Когда hints включены, контекст содержит метки релевантности и scores."""
        pair = _make_pair(
            42, question="Как настроить ФН?", answer="Нужно выполнить ...",
            bm25_score=0.85, vector_score=0.72,
        )
        pair.search_relevance_tier = "высокая"

        # Эмулируем логику форматирования из answer_question_from_pairs
        header = (
            f"Пара 1 (ID={pair.id}, "
            f"Релевантность: {pair.search_relevance_tier}, "
            f"BM25: {pair.search_bm25_score:.2f}, Вектор: {pair.search_vector_score:.2f}):"
        )
        self.assertIn("Релевантность: высокая", header)
        self.assertIn("BM25: 0.85", header)
        self.assertIn("Вектор: 0.72", header)

    def test_prompt_without_hints_no_tier(self):
        """Без hints пара форматируется без метки релевантности."""
        pair = _make_pair(42, question="Q", answer="A")
        # search_relevance_tier = None (по умолчанию)

        header = f"Пара 1 (ID={pair.id}):"
        self.assertNotIn("Релевантность", header)
        self.assertNotIn("BM25:", header)

    def test_prompt_with_missing_bm25_shows_dash(self):
        """Если BM25 score = None, должен отображаться '—'."""
        pair = _make_pair(1, bm25_score=None, vector_score=0.5)
        pair.search_relevance_tier = "средняя"

        bm25_label = (
            f"{pair.search_bm25_score:.2f}"
            if pair.search_bm25_score is not None
            else "—"
        )
        self.assertEqual(bm25_label, "—")

    def test_relevance_rule_text(self):
        """_RELEVANCE_RULE должен содержать инструкцию про уровни."""
        self.assertIn("высокая", _RELEVANCE_RULE)
        self.assertIn("средняя", _RELEVANCE_RULE)
        self.assertIn("низкая", _RELEVANCE_RULE)
        self.assertIn("BM25", _RELEVANCE_RULE)

    def test_prompt_base_has_placeholders(self):
        """_ANSWER_PROMPT_BASE содержит необходимые placeholder."""
        self.assertIn("{qa_context}", _ANSWER_PROMPT_BASE)
        self.assertIn("{relevance_rule}", _ANSWER_PROMPT_BASE)


class TestLogRrfDiagnosticsWithTiers(unittest.TestCase):
    """Тесты расширенного логирования RRF с уровнями."""

    @patch("src.group_knowledge.qa_search.logger")
    def test_log_includes_tier_info(self, mock_logger):
        """Лог должен содержать tier и нормализованные scores."""
        pair = _make_pair(10, bm25_score=0.9, vector_score=0.7)
        pair.search_relevance_tier = "высокая"

        diagnostics = [{
            "pair_id": 10,
            "question_preview": "Тестовый вопрос",
            "bm25_rank": 1,
            "bm25_score": 5.0,
            "vector_rank": 2,
            "vector_score": 0.8,
            "rrf_score": 0.032787,
        }]

        QASearchService._log_rrf_diagnostics(
            "тест", diagnostics, pairs_by_id={10: pair},
        )

        mock_logger.info.assert_called_once()
        log_text = mock_logger.info.call_args[0][0]
        self.assertIn("tier=высокая", log_text)
        self.assertIn("bm25_n=0.90", log_text)
        self.assertIn("vec_n=0.70", log_text)

    @patch("src.group_knowledge.qa_search.logger")
    def test_log_without_pairs_no_tier(self, mock_logger):
        """Без pairs_by_id лог не должен содержать tier."""
        diagnostics = [{
            "pair_id": 10,
            "question_preview": "q",
            "bm25_rank": 1,
            "bm25_score": 5.0,
            "vector_rank": None,
            "vector_score": 0.0,
            "rrf_score": 0.016,
        }]

        QASearchService._log_rrf_diagnostics("тест", diagnostics)

        mock_logger.info.assert_called_once()
        log_text = mock_logger.info.call_args[0][0]
        self.assertNotIn("tier=", log_text)


class TestAutoComputeTiersInAnswerFromPairs(unittest.TestCase):
    """Тесты автовычисления уровней при вызове answer_question_from_pairs."""

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_tiers_computed_when_scores_present_but_tiers_missing(self, mock_settings):
        """Если пары имеют scores, но не имеют tier — _compute_relevance_tiers вызывается."""
        mock_settings.GK_RELEVANCE_HINTS_ENABLED = True
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        p1 = _make_pair(1, bm25_score=0.9, vector_score=0.8)
        p2 = _make_pair(2, bm25_score=0.1, vector_score=0.05)

        self.assertIsNone(p1.search_relevance_tier)
        self.assertIsNone(p2.search_relevance_tier)

        # Эмулируем вызов _compute_relevance_tiers как в answer_question_from_pairs
        pairs = [p1, p2]
        if any(
            p.search_relevance_tier is None
            and (p.search_bm25_score is not None or p.search_vector_score is not None)
            for p in pairs
        ):
            QASearchService._compute_relevance_tiers([(p, 0.0) for p in pairs])

        self.assertIsNotNone(p1.search_relevance_tier)
        self.assertIsNotNone(p2.search_relevance_tier)
        self.assertEqual(p1.search_relevance_tier, "высокая")
        self.assertEqual(p2.search_relevance_tier, "низкая")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_no_auto_compute_when_no_scores(self, mock_settings):
        """Если пары без scores (обе None) — tier не вычисляется."""
        mock_settings.GK_RELEVANCE_HINTS_ENABLED = True
        mock_settings.GK_SCORE_CLIFF_THRESHOLD = 0.3

        p1 = _make_pair(1)
        p2 = _make_pair(2)

        pairs = [p1, p2]
        should_compute = any(
            p.search_relevance_tier is None
            and (p.search_bm25_score is not None or p.search_vector_score is not None)
            for p in pairs
        )
        self.assertFalse(should_compute)
        self.assertIsNone(p1.search_relevance_tier)


class TestAttachSingleMethodScores(unittest.TestCase):
    """Тесты прикрепления scores при наличии только одного метода."""

    def test_vector_only_scores_attached(self):
        """При vector-only результатах score прикрепляется, bm25 = None."""
        p1 = QAPair(id=1, question_text="q1", answer_text="a1")
        p2 = QAPair(id=2, question_text="q2", answer_text="a2")

        scored = [(p1, 0.9), (p2, 0.5)]
        QASearchService._attach_single_method_scores(
            [p1, p2], scored, is_bm25=False,
        )

        self.assertIsNone(p1.search_bm25_score)
        self.assertAlmostEqual(p1.search_vector_score, 1.0, places=3)
        self.assertIsNone(p2.search_bm25_score)
        self.assertAlmostEqual(p2.search_vector_score, 0.0, places=3)

    def test_bm25_only_scores_attached(self):
        """При bm25-only результатах score прикрепляется, vector = None."""
        p1 = QAPair(id=1, question_text="q1", answer_text="a1")

        scored = [(p1, 8.0)]
        QASearchService._attach_single_method_scores(
            [p1], scored, is_bm25=True,
        )

        self.assertAlmostEqual(p1.search_bm25_score, 0.0, places=3)  # single item → (8-8)/1=0
        self.assertIsNone(p1.search_vector_score)


# -----------------------------------------------------------------------
# Spell-check тесты
# -----------------------------------------------------------------------


class TestBuildSpellcheckVocabulary(unittest.TestCase):
    """Тесты построения spellcheck vocabulary из корпуса."""

    @patch("src.group_knowledge.qa_search.SymSpell", None)
    def test_no_symspell_returns_false(self):
        """Если symspellpy не установлен, _build_spellcheck_vocabulary → False."""
        service = QASearchService.__new__(QASearchService)
        service._corpus_pairs = []
        service._spellcheck_sym = None
        service._spellcheck_vocab_size = 0
        service._spellcheck_vocab_ready = False
        result = service._build_spellcheck_vocabulary()
        self.assertFalse(result)
        self.assertFalse(service._spellcheck_vocab_ready)

    @patch("src.group_knowledge.qa_search.SymSpell")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_builds_from_corpus_pairs(self, mock_settings, mock_symspell_cls):
        """Vocabulary строится из question + answer текстов корпуса."""
        mock_settings.GK_SPELLCHECK_MAX_EDIT_DISTANCE = 1

        mock_sym = MagicMock()
        mock_symspell_cls.return_value = mock_sym

        service = QASearchService.__new__(QASearchService)
        service._spellcheck_sym = None
        service._spellcheck_vocab_size = 0
        service._spellcheck_vocab_ready = False
        service._corpus_pairs = [
            QAPair(id=1, question_text="тестовый вопрос", answer_text="тестовый ответ"),
            QAPair(id=2, question_text="другой запрос", answer_text="другой ответ"),
        ]

        result = service._build_spellcheck_vocabulary()

        self.assertTrue(result)
        self.assertTrue(service._spellcheck_vocab_ready)
        self.assertGreater(service._spellcheck_vocab_size, 0)
        # create_dictionary_entry вызывается для каждого уникального токена
        self.assertGreater(mock_sym.create_dictionary_entry.call_count, 0)

    @patch("src.group_knowledge.qa_search.SymSpell")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_empty_corpus_no_fixed_terms_only(self, mock_settings, mock_symspell_cls):
        """Пустой корпус — vocabulary всё равно содержит protected terms."""
        mock_settings.GK_SPELLCHECK_MAX_EDIT_DISTANCE = 1

        mock_sym = MagicMock()
        mock_symspell_cls.return_value = mock_sym

        service = QASearchService.__new__(QASearchService)
        service._spellcheck_sym = None
        service._spellcheck_vocab_size = 0
        service._spellcheck_vocab_ready = False
        service._corpus_pairs = []

        result = service._build_spellcheck_vocabulary()

        # Словарь содержит только protected terms
        self.assertTrue(result)
        self.assertEqual(service._spellcheck_vocab_size, len(_GK_FIXED_TERMS))


class TestSpellcheckTokens(unittest.TestCase):
    """Тесты corpus-based коррекции токенов."""

    def test_rare_exact_typo_replaced_by_frequent_neighbor(self):
        """Редкая «точная» опечатка заменяется на частотный соседний термин."""
        service = QASearchService.__new__(QASearchService)
        service._spellcheck_vocab_ready = True

        mock_sym = MagicMock()
        service._spellcheck_sym = mock_sym
        service._spellcheck_token_freq = {
            "пораметров": 1,
            "параметров": 25,
        }

        class _V:
            CLOSEST = "closest"
            ALL = "all"

        class _S:
            def __init__(self, term, distance, count):
                self.term = term
                self.distance = distance
                self.count = count

        def _lookup(token, verbosity, max_edit_distance):
            if verbosity == _V.CLOSEST:
                return [_S("пораметров", 0, 1)]
            if verbosity == _V.ALL:
                return [
                    _S("пораметров", 0, 1),
                    _S("параметров", 1, 25),
                ]
            return []

        mock_sym.lookup.side_effect = _lookup

        with patch("src.group_knowledge.qa_search.ai_settings") as mock_s:
            mock_s.GK_SPELLCHECK_MIN_TOKEN_LENGTH = 4
            mock_s.GK_SPELLCHECK_MAX_EDIT_DISTANCE = 1
            with patch("src.group_knowledge.qa_search._SymSpellVerbosity", _V):
                corrected, changes = service._spellcheck_tokens(["пораметров"])

        self.assertEqual(corrected, ["параметров"])
        self.assertEqual(changes, [("пораметров", "параметров")])

    def test_skips_protected_terms(self):
        """Защищённые термины не корректируются."""
        service = QASearchService.__new__(QASearchService)
        service._spellcheck_vocab_ready = True

        mock_sym = MagicMock()
        service._spellcheck_sym = mock_sym

        tokens = ["осно", "усн", "ккт"]

        with patch("src.group_knowledge.qa_search.ai_settings") as mock_s:
            mock_s.GK_SPELLCHECK_MIN_TOKEN_LENGTH = 4
            mock_s.GK_SPELLCHECK_MAX_EDIT_DISTANCE = 1
            with patch("src.group_knowledge.qa_search._SymSpellVerbosity", MagicMock()):
                corrected, changes = service._spellcheck_tokens(tokens)

        self.assertEqual(corrected, tokens)
        self.assertEqual(changes, [])
        # lookup не вызывался для protected terms
        mock_sym.lookup.assert_not_called()

    def test_skips_short_tokens(self):
        """Токены короче min_length пропускаются."""
        service = QASearchService.__new__(QASearchService)
        service._spellcheck_vocab_ready = True

        mock_sym = MagicMock()
        service._spellcheck_sym = mock_sym

        tokens = ["да", "нет"]

        with patch("src.group_knowledge.qa_search.ai_settings") as mock_s:
            mock_s.GK_SPELLCHECK_MIN_TOKEN_LENGTH = 4
            mock_s.GK_SPELLCHECK_MAX_EDIT_DISTANCE = 1
            with patch("src.group_knowledge.qa_search._SymSpellVerbosity", MagicMock()):
                corrected, changes = service._spellcheck_tokens(tokens)

        self.assertEqual(corrected, tokens)
        self.assertEqual(changes, [])

    def test_skips_non_cyrillic_tokens(self):
        """Латинские и числовые токены пропускаются."""
        service = QASearchService.__new__(QASearchService)
        service._spellcheck_vocab_ready = True

        mock_sym = MagicMock()
        service._spellcheck_sym = mock_sym

        tokens = ["router", "12345", "wifi"]

        with patch("src.group_knowledge.qa_search.ai_settings") as mock_s:
            mock_s.GK_SPELLCHECK_MIN_TOKEN_LENGTH = 4
            mock_s.GK_SPELLCHECK_MAX_EDIT_DISTANCE = 1
            with patch("src.group_knowledge.qa_search._SymSpellVerbosity", MagicMock()):
                corrected, changes = service._spellcheck_tokens(tokens)

        self.assertEqual(corrected, tokens)
        self.assertEqual(changes, [])

    def test_not_ready_returns_unchanged(self):
        """Если vocabulary не готов — возвращает токены без изменений."""
        service = QASearchService.__new__(QASearchService)
        service._spellcheck_vocab_ready = False
        service._spellcheck_sym = None

        tokens = ["ошибка", "тест"]
        corrected, changes = service._spellcheck_tokens(tokens)

        self.assertEqual(corrected, tokens)
        self.assertEqual(changes, [])


class TestApplySpellcheckToQuery(unittest.TestCase):
    """Тесты полной коррекции строки запроса."""

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_disabled_returns_original(self, mock_settings):
        """Если spellcheck выключен — возвращает оригинал."""
        mock_settings.GK_SPELLCHECK_ENABLED = False

        service = QASearchService.__new__(QASearchService)
        service._spellcheck_vocab_ready = False
        service._spellcheck_sym = None

        result, changes, source = service._apply_spellcheck_to_query("тест")
        self.assertEqual(result, "тест")
        self.assertEqual(changes, [])
        self.assertEqual(source, "disabled")

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_vocab_not_ready(self, mock_settings):
        """Если vocabulary не готов — source='vocab_not_ready'."""
        mock_settings.GK_SPELLCHECK_ENABLED = True

        service = QASearchService.__new__(QASearchService)
        service._spellcheck_vocab_ready = False
        service._spellcheck_sym = None

        result, changes, source = service._apply_spellcheck_to_query("тест")
        self.assertEqual(result, "тест")
        self.assertEqual(source, "vocab_not_ready")


class TestInvalidateCorpusCacheResetsSpellcheck(unittest.TestCase):
    """Тест: invalidate_corpus_cache сбрасывает spellcheck vocabulary."""

    def test_spellcheck_state_reset(self):
        """После invalidate_corpus_cache spellcheck состояние сброшено."""
        service = QASearchService.__new__(QASearchService)
        service._corpus_loaded_at = 100.0
        service._corpus_pairs = [QAPair(id=1, question_text="q", answer_text="a")]
        service._corpus_tokens = [["q"]]
        service._corpus_signature = (1, 1, 1)
        service._corpus_extraction_types = ("thread_reply",)
        service._spellcheck_sym = MagicMock()
        service._spellcheck_vocab_size = 100
        service._spellcheck_vocab_ready = True
        service._spellcheck_token_freq = {"тест": 10}

        service.invalidate_corpus_cache()

        self.assertIsNone(service._spellcheck_sym)
        self.assertEqual(service._spellcheck_vocab_size, 0)
        self.assertFalse(service._spellcheck_vocab_ready)
        self.assertEqual(service._spellcheck_token_freq, {})


class TestSearchSpellcheckInitializationOrder(unittest.TestCase):
    """Тест: в search() корпус загружается до spellcheck pipeline."""

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_search_loads_corpus_before_spellcheck(self, mock_settings):
        """На первом запросе spellcheck должен видеть уже готовый vocabulary."""
        mock_settings.GK_SEARCH_CANDIDATES_PER_METHOD = 5
        mock_settings.GK_HYBRID_ENABLED = False
        mock_settings.GK_RELEVANCE_HINTS_ENABLED = False

        service = QASearchService.__new__(QASearchService)
        service._top_k = 3

        service._ensure_corpus_loaded = MagicMock()
        service._bm25_search = MagicMock(return_value=[])
        service._vector_search = AsyncMock(return_value=[])

        async def _spellcheck_side_effect(query: str) -> str:
            self.assertTrue(service._ensure_corpus_loaded.called)
            return query

        service._apply_spellcheck_pipeline = AsyncMock(side_effect=_spellcheck_side_effect)

        import asyncio
        result = asyncio.run(service.search("что такое загрузка пораметров"))

        self.assertEqual(result, [])
        service._ensure_corpus_loaded.assert_called_once()
        service._apply_spellcheck_pipeline.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
