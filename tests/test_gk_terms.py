"""Тесты системы терминов GK.

Проверяет:
- build_derived_term_structures — построение производных структур.
- load_fixed_terms — загрузку из БД с TTL-кэшем и fallback.
- QASearchService.reload_terms — обновление instance-level структур.
- QASearchService._ensure_terms_loaded — автоматическая перезагрузка.
- QAAnalyzer._build_acronyms_section — построение секции аббревиатур.
"""

import time
import unittest
from typing import Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch


class TestBuildDerivedTermStructures(unittest.TestCase):
    """Тесты build_derived_term_structures."""

    def test_simple_terms(self):
        from src.group_knowledge.qa_search import build_derived_term_structures

        terms = frozenset({"осно", "усн", "ккт"})
        phrases, t_map, r_map, tokens = build_derived_term_structures(terms)

        # Нет многословных терминов
        self.assertEqual(phrases, ())

        # Все термины присутствуют в maps
        self.assertEqual(len(t_map), 3)
        self.assertEqual(len(r_map), 3)
        self.assertEqual(len(tokens), 3)

        # Токены — нижний регистр, без пробелов
        for term in terms:
            self.assertIn(term, t_map)
            token = t_map[term]
            self.assertIn(token, r_map)
            self.assertEqual(r_map[token], term)

    def test_multiword_phrases(self):
        from src.group_knowledge.qa_search import build_derived_term_structures

        terms = frozenset({"эвотор 6", "1с", "ккт"})
        phrases, t_map, r_map, tokens = build_derived_term_structures(terms)

        # Многословный термин попадает в phrases
        self.assertEqual(len(phrases), 1)
        self.assertEqual(phrases[0], "эвотор 6")

        # Токен для многословного — с подчёркиванием
        self.assertEqual(t_map["эвотор 6"], "эвотор_6")
        self.assertIn("эвотор_6", tokens)

    def test_empty_terms(self):
        from src.group_knowledge.qa_search import build_derived_term_structures

        phrases, t_map, r_map, tokens = build_derived_term_structures(frozenset())
        self.assertEqual(phrases, ())
        self.assertEqual(t_map, {})
        self.assertEqual(r_map, {})
        self.assertEqual(tokens, frozenset())

    def test_phrases_sorted_by_length_desc(self):
        from src.group_knowledge.qa_search import build_derived_term_structures

        terms = frozenset({"а б в г", "а б", "а б в"})
        phrases, _, _, _ = build_derived_term_structures(terms)
        self.assertEqual(phrases[0], "а б в г")
        self.assertEqual(phrases[-1], "а б")


class TestLoadFixedTerms(unittest.TestCase):
    """Тесты load_fixed_terms с кэшем и fallback."""

    def setUp(self):
        # Сбросить глобальный кэш перед каждым тестом
        import src.group_knowledge.qa_search as mod
        mod._terms_cache.clear()

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_loads_from_db(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_terms.return_value = {"осно", "усн", "чз"}

        result = load_fixed_terms(group_id=123)
        self.assertEqual(result, frozenset({"осно", "усн", "чз"}))
        mock_db.get_approved_terms.assert_called_once_with(123)

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_uses_cache_within_ttl(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_terms.return_value = {"осно"}

        result1 = load_fixed_terms(group_id=1)
        result2 = load_fixed_terms(group_id=1)
        # Второй вызов использует кэш
        self.assertEqual(mock_db.get_approved_terms.call_count, 1)
        self.assertEqual(result1, result2)

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_caches_per_group_id(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_terms.return_value = {"осно"}

        load_fixed_terms(group_id=1)
        load_fixed_terms(group_id=2)
        # Разные group_id — оба вызывают БД, но кэш не сбрасывается.
        self.assertEqual(mock_db.get_approved_terms.call_count, 2)
        # Повторный вызов с group_id=1 использует кэш.
        load_fixed_terms(group_id=1)
        self.assertEqual(mock_db.get_approved_terms.call_count, 2)

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_fallback_on_db_error(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms, _GK_FIXED_TERMS_FALLBACK

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_terms.side_effect = Exception("DB error")

        result = load_fixed_terms()
        self.assertEqual(result, _GK_FIXED_TERMS_FALLBACK)

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_fallback_on_empty_db(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms, _GK_FIXED_TERMS_FALLBACK

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_terms.return_value = set()

        result = load_fixed_terms()
        self.assertEqual(result, _GK_FIXED_TERMS_FALLBACK)

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_acronyms_without_confidence_are_ignored(self, mock_settings, mock_db):
        """Все approved-термины загружаются без фильтрации по confidence."""
        from src.group_knowledge.qa_search import load_fixed_terms

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_terms.return_value = {"осно", "чз", "уз", "гз"}

        result = load_fixed_terms(group_id=77)

        self.assertEqual(result, frozenset({"осно", "чз", "уз", "гз"}))


class TestQASearchServiceTerms(unittest.TestCase):
    """Тесты instance-level терминов на QASearchService."""

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_reload_terms_updates_attributes(self, mock_settings):
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300

        svc = QASearchService()

        with patch("src.group_knowledge.qa_search.load_fixed_terms") as mock_load:
            mock_load.return_value = frozenset({"тест1", "тест2"})
            svc.reload_terms(group_id=42)

        self.assertEqual(svc._fixed_terms, frozenset({"тест1", "тест2"}))
        self.assertIn("тест1", svc._fixed_tokens)
        self.assertIn("тест2", svc._fixed_tokens)
        self.assertEqual(len(svc._fixed_term_token_map), 2)
        # Spellcheck vocabulary сброшен
        self.assertFalse(svc._spellcheck_vocab_ready)

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_ensure_terms_loaded_triggers_reload(self, mock_settings):
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 0  # Всегда протухает

        svc = QASearchService()
        svc._fixed_terms_loaded_at = 0  # Заведомо протухший

        with patch.object(svc, "reload_terms") as mock_reload:
            svc._ensure_terms_loaded()
            mock_reload.assert_called_once()

    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_short_acronym_token_is_preserved_after_reload(self, mock_settings):
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_RU_NORMALIZATION_ENABLED = True

        svc = QASearchService()

        with patch("src.group_knowledge.qa_search.load_fixed_terms") as mock_load:
            mock_load.return_value = frozenset({"аб"})
            svc.reload_terms(group_id=42)

        tokens = svc._tokenize("ошибка АБ на кассе")
        self.assertIn("аб", [t.lower() for t in tokens])


class TestQAAnalyzerAcronyms(unittest.TestCase):
    """Тесты _build_acronyms_section QAAnalyzer."""

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_builds_section_from_db(self, mock_db, mock_settings):
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9
        mock_settings.GK_ACRONYMS_MAX_PROMPT_TERMS = 50

        mock_db.get_terms_for_group.return_value = [
            {"term": "ГЗ", "definition": "Горячая замена", "status": "approved", "confidence": 0.95},
            {"term": "ЧЗ", "definition": "Честный Знак", "status": "approved", "confidence": 0.95},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(123)

        self.assertIn("ГЗ - Горячая замена.", section)
        self.assertIn("ЧЗ - Честный Знак.", section)
        mock_db.get_terms_for_group.assert_called_once_with(123, has_definition=True)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_uses_cache(self, mock_db, mock_settings):
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"term": "ГЗ", "definition": "Горячая замена", "status": "approved", "confidence": 0.95},
        ]

        analyzer = QAAnalyzer()
        analyzer._build_acronyms_section(123)
        analyzer._build_acronyms_section(123)
        self.assertEqual(mock_db.get_terms_for_group.call_count, 1)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_fallback_on_db_error(self, mock_db, mock_settings):
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.side_effect = Exception("DB error")

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(0)

        # Должен вернуть fallback
        self.assertIn("ГЗ означает Горячая замена", section)
        self.assertIn("ФИАС", section)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_term_without_definition(self, mock_db, mock_settings):
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9
        mock_settings.GK_ACRONYMS_MAX_PROMPT_TERMS = 50

        mock_db.get_terms_for_group.return_value = [
            {"term": "ABC", "definition": "", "status": "approved", "confidence": 0.95},
            {"term": "DEF", "definition": "Full Name", "status": "approved", "confidence": 0.95},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        # Термины без definition не включаются.
        self.assertNotIn("ABC", section)
        self.assertIn("DEF - Full Name.", section)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_filters_by_approved_status_only(self, mock_db, mock_settings):
        """QAAnalyzer теперь использует только approved-аббревиатуры (как и QASearchService)."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"term": "APP", "definition": "Approved", "status": "approved", "confidence": 0.95},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        self.assertIn("APP - Approved.", section)
        mock_db.get_terms_for_group.assert_called_once_with(
            1, has_definition=True,
        )

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_filters_by_min_confidence(self, mock_db, mock_settings):
        """Approved-термины ниже порога confidence не включаются."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"term": "HI", "definition": "HighConfidence", "confidence": 0.95, "status": "approved"},
            {"term": "LOW", "definition": "LowConfidence", "confidence": 0.89, "status": "approved"},
            {"term": "NON", "definition": "NoConfidence", "status": "approved"},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        self.assertIn("HI - HighConfidence.", section)
        self.assertNotIn("LOW - LowConfidence.", section)
        self.assertNotIn("NON - NoConfidence.", section)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_expert_approved_bypasses_confidence(self, mock_db, mock_settings):
        """Термины с expert_status='approved' включаются без проверки confidence."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"term": "HI", "definition": "HighConf", "confidence": 0.95, "status": "approved", "expert_status": None},
            {"term": "LOW", "definition": "LowConf", "confidence": 0.5, "status": "approved", "expert_status": "approved"},
            {"term": "NON", "definition": "NoConf", "confidence": None, "status": "approved", "expert_status": "approved"},
            {"term": "REJ", "definition": "Rejected", "confidence": 0.3, "status": "approved", "expert_status": "rejected"},
            {"term": "SKIP", "definition": "Skipped", "confidence": 0.4, "status": "approved", "expert_status": None},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        self.assertIn("HI - HighConf.", section)
        self.assertIn("LOW - LowConf.", section)
        self.assertIn("NON - NoConf.", section)
        self.assertNotIn("REJ - Rejected.", section)
        self.assertNotIn("SKIP - Skipped.", section)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_formats_acronyms_uppercase(self, mock_db, mock_settings):
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"term": "чз", "definition": "Честный Знак", "status": "approved", "confidence": 0.95},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        self.assertIn("ЧЗ - Честный Знак.", section)
        self.assertNotIn("чз - Честный Знак.", section)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_deduplicates_global_and_group_acronyms(self, mock_db, mock_settings):
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"id": 1, "group_id": 0, "term": "чз", "definition": "Глобальный", "confidence": 0.95, "status": "approved"},
            {"id": 2, "group_id": 1, "term": "ЧЗ", "definition": "Групповой", "confidence": 0.91, "status": "approved"},
            {"id": 3, "group_id": 0, "term": "ОФД", "definition": "Оператор", "confidence": 0.99, "status": "approved"},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        self.assertEqual(section.count("ЧЗ -"), 1)
        self.assertIn("ЧЗ - Групповой.", section)
        self.assertNotIn("ЧЗ - Глобальный.", section)
        self.assertIn("ОФД - Оператор.", section)


class TestQASearchAcronyms(unittest.TestCase):
    """Тесты acronyms_section в QASearchService."""

    @patch("src.group_knowledge.qa_search.ai_settings")
    @patch("src.group_knowledge.qa_search.gk_db")
    def test_builds_section_with_min_confidence_filter(self, mock_db, mock_settings):
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9
        mock_settings.GK_ACRONYMS_MAX_PROMPT_TERMS = 50

        mock_db.get_terms_for_group.return_value = [
            {"term": "ГЗ", "definition": "Горячая замена", "confidence": 0.95},
            {"term": "ЧЗ", "definition": "Честный Знак", "confidence": 0.89},
            {"term": "ОФД", "definition": "Оператор фискальных данных", "confidence": None},
        ]

        service = QASearchService()
        section = service._build_acronyms_section(123)

        self.assertIn("ГЗ - Горячая замена.", section)
        self.assertNotIn("ЧЗ", section)
        self.assertNotIn("ОФД", section)
        mock_db.get_terms_for_group.assert_called_once_with(
            123,
            has_definition=True,
        )

    @patch("src.group_knowledge.qa_search.ai_settings")
    @patch("src.group_knowledge.qa_search.gk_db")
    def test_fallback_when_no_acronyms_pass_threshold(self, mock_db, mock_settings):
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"term": "ЧЗ", "definition": "Честный Знак", "confidence": 0.5},
        ]

        service = QASearchService()
        section = service._build_acronyms_section(123)

        self.assertIn("ГЗ означает Горячая замена", section)
        self.assertIn("ФИАС", section)

    @patch("src.group_knowledge.qa_search.ai_settings")
    @patch("src.group_knowledge.qa_search.gk_db")
    def test_deduplicates_global_and_group_acronyms(self, mock_db, mock_settings):
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"id": 1, "group_id": 0, "term": "ЧЗ", "definition": "Глобальный", "confidence": 0.95},
            {"id": 2, "group_id": 123, "term": "чз", "definition": "Групповой", "confidence": 0.91},
            {"id": 3, "group_id": 0, "term": "ОФД", "definition": "Оператор фискальных данных", "confidence": 0.97},
        ]

        service = QASearchService()
        section = service._build_acronyms_section(123)

        # Дедупликация: групповой ЧЗ приоритетнее глобального (в нижнем регистре, т.к. qa_search).
        section_lower = section.lower()
        self.assertEqual(section_lower.count("чз -"), 1)
        self.assertIn("групповой", section_lower)
        self.assertNotIn("глобальный", section_lower)
        self.assertIn("офд - оператор фискальных данных.", section_lower)

    @patch("src.group_knowledge.qa_search.ai_settings")
    @patch("src.group_knowledge.qa_search.gk_db")
    def test_expert_approved_bypasses_confidence(self, mock_db, mock_settings):
        """Термины с expert_status='approved' включаются без проверки confidence."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"term": "ГЗ", "definition": "Горячая замена", "confidence": 0.95, "expert_status": None},
            {"term": "ЧЗ", "definition": "Честный Знак", "confidence": 0.5, "expert_status": "approved"},
            {"term": "ОФД", "definition": "Оператор фискальных данных", "confidence": None, "expert_status": "approved"},
            {"term": "ФН", "definition": "Фискальный накопитель", "confidence": 0.3, "expert_status": "rejected"},
        ]

        service = QASearchService()
        section = service._build_acronyms_section(123)

        self.assertIn("ГЗ - Горячая замена.", section)
        self.assertIn("ЧЗ - Честный Знак.", section)
        self.assertIn("ОФД - Оператор фискальных данных.", section)
        self.assertNotIn("ФН", section)

    def test_answer_prompt_contains_acronyms_section_placeholder(self):
        from src.group_knowledge.qa_search import _ANSWER_PROMPT_BASE

        self.assertIn("ВОЗМОЖНЫЕ АББРЕВИАТУРЫ", _ANSWER_PROMPT_BASE)
        self.assertIn("{acronyms_section}", _ANSWER_PROMPT_BASE)


class TestCanonicalFixedToken(unittest.TestCase):
    """Тесты _canonical_fixed_token с переданными структурами."""

    def test_with_custom_structures(self):
        from src.group_knowledge.qa_search import _canonical_fixed_token

        custom_tokens = frozenset({"abc", "def"})
        custom_map = {"abc": "abc", "def": "def", "ABC": "abc"}

        result = _canonical_fixed_token("abc", custom_tokens, custom_map)
        self.assertEqual(result, "abc")

    def test_fallback_without_structures(self):
        from src.group_knowledge.qa_search import _canonical_fixed_token

        result = _canonical_fixed_token("осно")
        self.assertEqual(result, "осно")

    def test_empty_token(self):
        from src.group_knowledge.qa_search import _canonical_fixed_token

        self.assertEqual(_canonical_fixed_token(""), "")
        self.assertEqual(_canonical_fixed_token(None), "")


class TestBackwardCompatibility(unittest.TestCase):
    """Тесты обратной совместимости module-level констант."""

    def test_module_level_gk_fixed_terms_exists(self):
        from src.group_knowledge.qa_search import _GK_FIXED_TERMS

        self.assertIsInstance(_GK_FIXED_TERMS, frozenset)
        self.assertIn("осно", _GK_FIXED_TERMS)
        self.assertIn("ккт", _GK_FIXED_TERMS)

    def test_module_level_derived_structures_exist(self):
        from src.group_knowledge.qa_search import (
            _GK_FIXED_PHRASES,
            _GK_FIXED_TERM_TOKEN_MAP,
            _GK_FIXED_TOKEN_TO_TERM_MAP,
            _GK_FIXED_TOKENS,
        )

        self.assertIsInstance(_GK_FIXED_PHRASES, tuple)
        self.assertIsInstance(_GK_FIXED_TERM_TOKEN_MAP, dict)
        self.assertIsInstance(_GK_FIXED_TOKEN_TO_TERM_MAP, dict)
        self.assertIsInstance(_GK_FIXED_TOKENS, frozenset)


class TestTermMinerDeduplicateTerms(unittest.TestCase):
    """Тесты _deduplicate_terms из TermMiner."""

    def _dedup(self, terms):
        from src.group_knowledge.term_miner import TermMiner
        return TermMiner._deduplicate_terms(terms)

    def test_basic_dedup_by_term(self):
        """Одинаковый term — оставить с большим confidence."""
        terms = [
            {"term": "ккт", "definition": None, "confidence": 0.7},
            {"term": "ккт", "definition": None, "confidence": 0.9},
        ]
        result = self._dedup(terms)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], 0.9)

    def test_definition_not_lost_on_replace(self):
        """При замене на запись с definition — она побеждает."""
        terms = [
            {"term": "гз", "definition": "Горячая замена", "confidence": 0.7},
            {"term": "гз", "definition": None, "confidence": 0.9},
        ]
        result = self._dedup(terms)
        self.assertEqual(len(result), 1)
        # Запись с definition побеждает (definition > higher confidence)
        self.assertEqual(result[0]["confidence"], 0.7)
        self.assertEqual(result[0]["definition"], "Горячая замена")

    def test_definition_enriched_from_lower_confidence(self):
        """Если existing не имеет definition, а новый имеет — новый побеждает."""
        terms = [
            {"term": "гз", "definition": None, "confidence": 0.9},
            {"term": "гз", "definition": "Горячая замена", "confidence": 0.5},
        ]
        result = self._dedup(terms)
        self.assertEqual(len(result), 1)
        # Запись с definition побеждает
        self.assertEqual(result[0]["confidence"], 0.5)
        self.assertEqual(result[0]["definition"], "Горячая замена")

    def test_prefer_with_definition_over_without(self):
        """Запись с definition предпочтительнее без."""
        terms = [
            {"term": "гз", "definition": None, "confidence": 0.95},
            {"term": "гз", "definition": "Горячая замена", "confidence": 0.8},
        ]
        result = self._dedup(terms)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["definition"], "Горячая замена")

    def test_without_definition_not_replaced_by_without_definition(self):
        """При отсутствии definition у обоих — побеждает больший confidence."""
        terms = [
            {"term": "гз", "definition": None, "confidence": 0.95},
            {"term": "гз", "definition": None, "confidence": 0.8},
        ]
        result = self._dedup(terms)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], 0.95)

    def test_none_confidence_treated_as_zero(self):
        """confidence=None интерпретируется как 0.0."""
        terms = [
            {"term": "тест", "definition": None, "confidence": None},
            {"term": "тест", "definition": None, "confidence": 0.5},
        ]
        result = self._dedup(terms)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], 0.5)

    def test_unique_terms_preserved(self):
        """Разные термины не дедуплицируются."""
        terms = [
            {"term": "ккт", "definition": None, "confidence": 0.9},
            {"term": "офд", "definition": None, "confidence": 0.8},
        ]
        result = self._dedup(terms)
        self.assertEqual(len(result), 2)


class TestTermMinerParseTermResponse(unittest.TestCase):
    """Тесты _parse_term_response из TermMiner."""

    def _parse(self, raw):
        from src.group_knowledge.term_miner import TermMiner
        return TermMiner._parse_term_response(raw)

    def test_valid_json(self):
        raw = '{"terms": [{"term": "ккт", "confidence": 0.9}]}'
        result = self._parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["term"], "ккт")

    def test_code_fence_json(self):
        """Распарсить JSON, обёрнутый в код-блок."""
        raw = '```json\n{"terms": [{"term": "офд", "confidence": 0.8}]}\n```'
        result = self._parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["term"], "офд")

    def test_preamble_with_code_fence(self):
        """LLM добавил текст перед код-блоком."""
        raw = 'Вот найденные термины:\n```json\n{"terms": [{"term": "фн", "confidence": 0.7}]}\n```'
        result = self._parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["term"], "фн")

    def test_empty_terms(self):
        raw = '{"terms": []}'
        result = self._parse(raw)
        self.assertEqual(result, [])

    def test_empty_string(self):
        self.assertEqual(self._parse(""), [])
        self.assertEqual(self._parse(None), [])

    def test_invalid_json(self):
        result = self._parse("not json at all")
        self.assertEqual(result, [])

    def test_unicode_normalization(self):
        """NFKC-нормализация и схлопывание пробелов."""
        raw = '{"terms": [{"term": "к  к  т", "confidence": 0.5}]}'
        result = self._parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["term"], "к к т")  # Internal spaces collapsed

    def test_term_stripped_and_lowercased(self):
        raw = '{"terms": [{"term": "  ККТ  ", "confidence": 0.5}]}'
        result = self._parse(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["term"], "ккт")

    def test_empty_term_rejected(self):
        raw = '{"terms": [{"term": "  ", "confidence": 0.5}]}'
        result = self._parse(raw)
        self.assertEqual(result, [])

    def test_confidence_clamped(self):
        raw = '{"terms": [{"term": "a", "confidence": 1.5}]}'
        result = self._parse(raw)
        self.assertEqual(result[0]["confidence"], 1.0)

        raw2 = '{"terms": [{"term": "b", "confidence": -0.5}]}'
        result2 = self._parse(raw2)
        self.assertEqual(result2[0]["confidence"], 0.0)


class TestSelectBestAcronymsByTerm(unittest.TestCase):
    """Тесты select_best_acronyms_by_term из acronyms.py."""

    def test_group_over_global(self):
        from src.group_knowledge.acronyms import select_best_acronyms_by_term
        records = [
            {"term": "гз", "group_id": 0, "confidence": 0.99, "id": 1},
            {"term": "гз", "group_id": 5, "confidence": 0.7, "id": 2},
        ]
        best = select_best_acronyms_by_term(records)
        self.assertEqual(best["ГЗ"]["group_id"], 5)

    def test_higher_confidence_wins_same_scope(self):
        from src.group_knowledge.acronyms import select_best_acronyms_by_term
        records = [
            {"term": "гз", "group_id": 5, "confidence": 0.7, "id": 1},
            {"term": "гз", "group_id": 5, "confidence": 0.9, "id": 2},
        ]
        best = select_best_acronyms_by_term(records)
        self.assertEqual(best["ГЗ"]["confidence"], 0.9)

    def test_higher_id_wins_when_equal_confidence(self):
        from src.group_knowledge.acronyms import select_best_acronyms_by_term
        records = [
            {"term": "гз", "group_id": 5, "confidence": 0.9, "id": 1},
            {"term": "гз", "group_id": 5, "confidence": 0.9, "id": 5},
        ]
        best = select_best_acronyms_by_term(records)
        self.assertEqual(best["ГЗ"]["id"], 5)

    def test_empty_term_skipped(self):
        from src.group_knowledge.acronyms import select_best_acronyms_by_term
        records = [
            {"term": "", "group_id": 0, "confidence": 0.9, "id": 1},
            {"term": None, "group_id": 0, "confidence": 0.9, "id": 2},
        ]
        best = select_best_acronyms_by_term(records)
        self.assertEqual(len(best), 0)


class TestNormalizeTerm(unittest.TestCase):
    """Тесты _normalize_term из term_miner.py."""

    def test_basic_normalization(self):
        from src.group_knowledge.term_miner import _normalize_term
        self.assertEqual(_normalize_term("  КкТ  "), "ккт")

    def test_internal_whitespace_collapsed(self):
        from src.group_knowledge.term_miner import _normalize_term
        self.assertEqual(_normalize_term("к  к  т"), "к к т")

    def test_empty_string(self):
        from src.group_knowledge.term_miner import _normalize_term
        self.assertEqual(_normalize_term(""), "")
        self.assertEqual(_normalize_term("   "), "")

    def test_nfkc_normalization(self):
        from src.group_knowledge.term_miner import _normalize_term
        import unicodedata
        # NFKC maps fullwidth to ASCII
        fullwidth_a = "\uff21"  # Ａ (fullwidth A)
        result = _normalize_term(fullwidth_a)
        self.assertEqual(result, "a")


# ---------------------------------------------------------------------------
# Тесты top-N ограничения групповых аббревиатур по message_count
# ---------------------------------------------------------------------------


class TestAcronymsSectionTopNLimit(unittest.TestCase):
    """Тесты ограничения группо-специфичных аббревиатур по message_count."""

    @patch("src.group_knowledge.qa_search.ai_settings")
    @patch("src.group_knowledge.qa_search.gk_db")
    def test_group_terms_limited_by_max_prompt_terms(self, mock_db, mock_settings):
        """Группо-специфичные термины обрезаются до GK_ACRONYMS_MAX_PROMPT_TERMS."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.0
        mock_settings.GK_ACRONYMS_MAX_PROMPT_TERMS = 2

        # 1 глобальный + 3 групповых (лимит = 2 → должно остаться 2 групповых).
        mock_db.get_terms_for_group.return_value = [
            {"id": 1, "group_id": 0, "term": "сбс", "definition": "СберСервис",
             "confidence": 0.95, "message_count": 10},
            {"id": 2, "group_id": 100, "term": "abc", "definition": "Def ABC",
             "confidence": 0.95, "message_count": 50},
            {"id": 3, "group_id": 100, "term": "xyz", "definition": "Def XYZ",
             "confidence": 0.95, "message_count": 30},
            {"id": 4, "group_id": 100, "term": "qqq", "definition": "Def QQQ",
             "confidence": 0.95, "message_count": 5},
        ]

        service = QASearchService()
        section = service._build_acronyms_section(100)

        # Глобальный термин всегда включён.
        self.assertIn("сбс", section.lower())
        # Топ-2 по message_count: abc(50) и xyz(30).
        self.assertIn("abc", section.lower())
        self.assertIn("xyz", section.lower())
        # qqq(5) обрезан.
        self.assertNotIn("qqq", section.lower())

    @patch("src.group_knowledge.qa_search.ai_settings")
    @patch("src.group_knowledge.qa_search.gk_db")
    def test_global_terms_not_limited(self, mock_db, mock_settings):
        """Глобальные термины (group_id=0) не подпадают под лимит."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.0
        mock_settings.GK_ACRONYMS_MAX_PROMPT_TERMS = 1

        # 3 глобальных + 2 групповых, лимит=1 → все глобальные + 1 групповой.
        mock_db.get_terms_for_group.return_value = [
            {"id": 1, "group_id": 0, "term": "гз", "definition": "Горячая замена",
             "confidence": 0.95, "message_count": 0},
            {"id": 2, "group_id": 0, "term": "чз", "definition": "Честный Знак",
             "confidence": 0.95, "message_count": 0},
            {"id": 3, "group_id": 0, "term": "сбс", "definition": "СберСервис",
             "confidence": 0.95, "message_count": 0},
            {"id": 4, "group_id": 100, "term": "top", "definition": "Top Term",
             "confidence": 0.95, "message_count": 100},
            {"id": 5, "group_id": 100, "term": "low", "definition": "Low Term",
             "confidence": 0.95, "message_count": 1},
        ]

        service = QASearchService()
        section = service._build_acronyms_section(100)

        # Все 3 глобальных включены.
        self.assertIn("гз", section.lower())
        self.assertIn("чз", section.lower())
        self.assertIn("сбс", section.lower())
        # Только top(100) включён из групповых (лимит=1).
        self.assertIn("top", section.lower())
        self.assertNotIn("low", section.lower())

    @patch("src.group_knowledge.qa_search.ai_settings")
    @patch("src.group_knowledge.qa_search.gk_db")
    def test_group_terms_sorted_by_message_count_desc(self, mock_db, mock_settings):
        """Групповые термины сортируются по message_count DESC."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.0
        mock_settings.GK_ACRONYMS_MAX_PROMPT_TERMS = 2

        mock_db.get_terms_for_group.return_value = [
            {"id": 1, "group_id": 100, "term": "aaa", "definition": "Lowest",
             "confidence": 0.95, "message_count": 1},
            {"id": 2, "group_id": 100, "term": "bbb", "definition": "Highest",
             "confidence": 0.95, "message_count": 999},
            {"id": 3, "group_id": 100, "term": "ccc", "definition": "Middle",
             "confidence": 0.95, "message_count": 50},
        ]

        service = QASearchService()
        section = service._build_acronyms_section(100)

        # bbb(999) и ccc(50) включены, aaa(1) обрезан.
        self.assertIn("bbb", section.lower())
        self.assertIn("ccc", section.lower())
        self.assertNotIn("aaa", section.lower())

    @patch("src.group_knowledge.qa_search.ai_settings")
    @patch("src.group_knowledge.qa_search.gk_db")
    def test_zero_message_count_terms_included_when_within_limit(self, mock_db, mock_settings):
        """Термины с message_count=0 включаются, если не превышен лимит."""
        from src.group_knowledge.qa_search import QASearchService

        mock_settings.GK_RESPONDER_MODEL = "test"
        mock_settings.GK_RESPONDER_TOP_K = 5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.0
        mock_settings.GK_ACRONYMS_MAX_PROMPT_TERMS = 50

        mock_db.get_terms_for_group.return_value = [
            {"id": 1, "group_id": 100, "term": "new", "definition": "New term",
             "confidence": 0.95, "message_count": 0},
        ]

        service = QASearchService()
        section = service._build_acronyms_section(100)

        self.assertIn("new", section.lower())


class TestQAAnalyzerAcronymsTopN(unittest.TestCase):
    """Тесты top-N ограничения аббревиатур в QAAnalyzer."""

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_group_terms_limited_by_max_prompt_terms(self, mock_db, mock_settings):
        """QAAnalyzer: группо-специфичные термины обрезаются до лимита."""
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 50
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.9
        mock_settings.GK_GENERATE_LLM_INFERRED_QA_PAIRS = False
        mock_settings.GK_ANALYSIS_CROSS_DAY_ENRICHMENT = False
        mock_settings.GK_RAG_IMAGE_GIST_ENABLED = False
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.0
        mock_settings.GK_ACRONYMS_MAX_PROMPT_TERMS = 1

        mock_db.get_terms_for_group.return_value = [
            {"id": 1, "group_id": 0, "term": "гз", "definition": "Горячая замена",
             "confidence": 0.95, "message_count": 0},
            {"id": 2, "group_id": 200, "term": "big", "definition": "Big term",
             "confidence": 0.95, "message_count": 100},
            {"id": 3, "group_id": 200, "term": "small", "definition": "Small term",
             "confidence": 0.95, "message_count": 1},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(200)

        # Глобальный включён всегда.
        self.assertIn("ГЗ", section)
        # Только big включён (лимит=1).
        self.assertIn("BIG", section)
        self.assertNotIn("SMALL", section)


# ---------------------------------------------------------------------------
# Тесты recount_term_usage
# ---------------------------------------------------------------------------


class TestRecountTermUsage(unittest.TestCase):
    """Тесты пересчёта message_count терминов."""

    @patch("src.group_knowledge.term_miner.gk_db")
    @patch("src.group_knowledge.term_miner.ai_settings")
    def test_recount_counts_term_occurrences(self, mock_settings, mock_db):
        """Пересчёт корректно считает вхождения терминов в сообщениях."""
        import asyncio
        from src.group_knowledge.term_miner import recount_term_usage

        mock_settings.GK_TERMS_RECOUNT_BATCH_SIZE = 100

        mock_db.get_terms_for_group.return_value = [
            {"id": 10, "group_id": 5, "term": "ккт",
             "definition": "Контрольно-кассовая техника", "confidence": 0.95},
            {"id": 11, "group_id": 5, "term": "офд",
             "definition": "Оператор фискальных данных", "confidence": 0.9},
        ]
        mock_db.get_message_count_for_group.return_value = 3
        mock_db.get_message_texts_batch.return_value = [
            {"message_text": "Проблема с ККТ и ОФД", "caption": None, "image_description": None},
            {"message_text": "Обновить прошивку", "caption": None, "image_description": None},
            {"message_text": "ккт не отвечает", "caption": "фото ошибки", "image_description": None},
        ]
        mock_db.bulk_update_term_message_counts.return_value = 2

        result = asyncio.run(
            recount_term_usage(5)
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["terms_counted"], 2)
        self.assertEqual(result["messages_scanned"], 3)

        # Проверить, что bulk_update вызван с правильными счётчиками.
        call_args = mock_db.bulk_update_term_message_counts.call_args[0][0]
        self.assertEqual(call_args[10], 2)  # ккт встречается в 2 сообщениях
        self.assertEqual(call_args[11], 1)  # офд встречается в 1 сообщении

    @patch("src.group_knowledge.term_miner.gk_db")
    @patch("src.group_knowledge.term_miner.ai_settings")
    def test_recount_empty_group(self, mock_settings, mock_db):
        """Пересчёт для группы без терминов возвращает пустой результат."""
        import asyncio
        from src.group_knowledge.term_miner import recount_term_usage

        mock_settings.GK_TERMS_RECOUNT_BATCH_SIZE = 100
        mock_db.get_terms_for_group.return_value = []

        result = asyncio.run(
            recount_term_usage(5)
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["terms_counted"], 0)
        mock_db.bulk_update_term_message_counts.assert_not_called()

    @patch("src.group_knowledge.term_miner.gk_db")
    @patch("src.group_knowledge.term_miner.ai_settings")
    def test_recount_skips_global_terms_for_group_recount(self, mock_settings, mock_db):
        """При пересчёте для группы глобальные термины не обновляются."""
        import asyncio
        from src.group_knowledge.term_miner import recount_term_usage

        mock_settings.GK_TERMS_RECOUNT_BATCH_SIZE = 100

        # get_terms_for_group возвращает и глобальные, и групповые.
        mock_db.get_terms_for_group.return_value = [
            {"id": 1, "group_id": 0, "term": "гз",
             "definition": "Горячая замена", "confidence": 0.95},
            {"id": 2, "group_id": 5, "term": "ккт",
             "definition": "Контрольно-кассовая техника", "confidence": 0.95},
        ]
        mock_db.get_message_count_for_group.return_value = 1
        mock_db.get_message_texts_batch.return_value = [
            {"message_text": "гз ккт", "caption": None, "image_description": None},
        ]
        mock_db.bulk_update_term_message_counts.return_value = 1

        result = asyncio.run(
            recount_term_usage(5)
        )

        # Только группо-специфичные термины должны пересчитываться.
        call_args = mock_db.bulk_update_term_message_counts.call_args[0][0]
        self.assertNotIn(1, call_args)  # Глобальный id=1 не обновлён.
        self.assertIn(2, call_args)     # Групповой id=2 обновлён.

    @patch("src.group_knowledge.term_miner.gk_db")
    @patch("src.group_knowledge.term_miner.ai_settings")
    def test_recount_uses_message_text_only(self, mock_settings, mock_db):
        """Пересчёт учитывает только message_text, игнорируя caption/image_description."""
        import asyncio
        from src.group_knowledge.term_miner import recount_term_usage

        mock_settings.GK_TERMS_RECOUNT_BATCH_SIZE = 100

        mock_db.get_terms_for_group.return_value = [
            {"id": 10, "group_id": 5, "term": "тест",
             "definition": "Тестовый термин", "confidence": 0.95},
        ]
        mock_db.get_message_count_for_group.return_value = 3
        mock_db.get_message_texts_batch.return_value = [
            {"message_text": "сообщение с тест", "caption": None, "image_description": None},
            {"message_text": None, "caption": "тест в подписи", "image_description": None},
            {"message_text": None, "caption": None, "image_description": "тест на фото"},
        ]
        mock_db.bulk_update_term_message_counts.return_value = 1

        result = asyncio.run(
            recount_term_usage(5)
        )

        call_args = mock_db.bulk_update_term_message_counts.call_args[0][0]
        self.assertEqual(call_args[10], 1)  # Найден только в message_text.

    @patch("src.group_knowledge.term_miner.gk_db")
    @patch("src.group_knowledge.term_miner.ai_settings")
    def test_recount_uses_term_boundaries_not_substrings(self, mock_settings, mock_db):
        """Короткий термин не должен матчиться как подстрока более длинного."""
        import asyncio
        from src.group_knowledge.term_miner import recount_term_usage

        mock_settings.GK_TERMS_RECOUNT_BATCH_SIZE = 100

        mock_db.get_terms_for_group.return_value = [
            {"id": 7, "group_id": 5, "term": "г",
             "definition": "буква", "confidence": 0.95},
        ]
        mock_db.get_message_count_for_group.return_value = 3
        mock_db.get_message_texts_batch.return_value = [
            {"message_text": "г", "caption": None, "image_description": None},
            {"message_text": "гз", "caption": None, "image_description": None},
            {"message_text": "[г]", "caption": None, "image_description": None},
        ]
        mock_db.bulk_update_term_message_counts.return_value = 1

        result = asyncio.run(recount_term_usage(5))

        self.assertEqual(result["status"], "completed")
        call_args = mock_db.bulk_update_term_message_counts.call_args[0][0]
        # Должны засчитаться только отдельные вхождения: "г" и "[г]".
        self.assertEqual(call_args[7], 2)


if __name__ == "__main__":
    unittest.main()
