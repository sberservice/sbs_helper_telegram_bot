"""Тесты системы терминов и аббревиатур GK.

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
        mod._terms_cache_data = None
        mod._terms_cache_ts = 0.0
        mod._terms_cache_group_id = None

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_loads_from_db(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_fixed_terms.return_value = {"осно", "усн"}

        result = load_fixed_terms(group_id=123)
        self.assertEqual(result, frozenset({"осно", "усн"}))
        mock_db.get_approved_fixed_terms.assert_called_once_with(123)

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_uses_cache_within_ttl(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_fixed_terms.return_value = {"осно"}

        result1 = load_fixed_terms(group_id=1)
        result2 = load_fixed_terms(group_id=1)
        # Второй вызов использует кэш
        self.assertEqual(mock_db.get_approved_fixed_terms.call_count, 1)
        self.assertEqual(result1, result2)

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_invalidates_cache_on_group_change(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_fixed_terms.return_value = {"осно"}

        load_fixed_terms(group_id=1)
        load_fixed_terms(group_id=2)
        self.assertEqual(mock_db.get_approved_fixed_terms.call_count, 2)

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_fallback_on_db_error(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms, _GK_FIXED_TERMS_FALLBACK

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_fixed_terms.side_effect = Exception("DB error")

        result = load_fixed_terms()
        self.assertEqual(result, _GK_FIXED_TERMS_FALLBACK)

    @patch("src.group_knowledge.qa_search.gk_db")
    @patch("src.group_knowledge.qa_search.ai_settings")
    def test_fallback_on_empty_db(self, mock_settings, mock_db):
        from src.group_knowledge.qa_search import load_fixed_terms, _GK_FIXED_TERMS_FALLBACK

        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_db.get_approved_fixed_terms.return_value = set()

        result = load_fixed_terms()
        self.assertEqual(result, _GK_FIXED_TERMS_FALLBACK)


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

        mock_db.get_terms_for_group.return_value = [
            {"term": "ГЗ", "definition": "Горячая замена", "status": "approved", "confidence": 0.1},
            {"term": "ЧЗ", "definition": "Честный Знак", "confidence": 0.95},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(123)

        self.assertIn("ГЗ означает Горячая замена.", section)
        self.assertIn("ЧЗ означает Честный Знак.", section)
        mock_db.get_terms_for_group.assert_called_once_with(123, term_type="acronym")

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
            {"term": "ГЗ", "definition": "Горячая замена"},
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

        mock_db.get_terms_for_group.return_value = [
            {"term": "ABC", "definition": "", "status": "approved"},
            {"term": "DEF", "definition": "Full Name", "status": "approved"},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        self.assertIn("ABC.", section)
        self.assertIn("DEF означает Full Name.", section)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_filters_only_rejected_terms(self, mock_db, mock_settings):
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"term": "APP", "definition": "Approved", "status": "approved", "confidence": 0.01},
            {"term": "PND", "definition": "Pending", "status": "pending", "confidence": 0.95},
            {"term": "R1", "definition": "Rejected", "status": "rejected"},
            {"term": "R2", "definition": "RejectedByExpert", "expert_status": "rejected"},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        self.assertIn("APP означает Approved.", section)
        self.assertIn("PND означает Pending.", section)
        self.assertNotIn("R1 означает Rejected.", section)
        self.assertNotIn("R2 означает RejectedByExpert.", section)

    @patch("src.group_knowledge.qa_analyzer.ai_settings")
    @patch("src.group_knowledge.qa_analyzer.gk_db")
    def test_filters_by_min_confidence_unless_approved(self, mock_db, mock_settings):
        from src.group_knowledge.qa_analyzer import QAAnalyzer

        mock_settings.GK_ANALYSIS_MODEL = "test"
        mock_settings.GK_ANALYSIS_BATCH_SIZE = 10
        mock_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD = 0.5
        mock_settings.GK_TERMS_CACHE_TTL_SECONDS = 300
        mock_settings.GK_ACRONYMS_MIN_CONFIDENCE = 0.9

        mock_db.get_terms_for_group.return_value = [
            {"term": "HI", "definition": "HighConfidence", "confidence": 0.95, "status": "pending"},
            {"term": "LOW", "definition": "LowConfidence", "confidence": 0.89, "status": "pending"},
            {"term": "APR", "definition": "ApprovedLowConf", "confidence": 0.2, "status": "approved"},
            {"term": "NON", "definition": "NoConfidence", "status": "pending"},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        self.assertIn("HI означает HighConfidence.", section)
        self.assertIn("APR означает ApprovedLowConf.", section)
        self.assertNotIn("LOW означает LowConfidence.", section)
        self.assertNotIn("NON означает NoConfidence.", section)

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
            {"term": "чз", "definition": "Честный Знак", "status": "approved"},
        ]

        analyzer = QAAnalyzer()
        section = analyzer._build_acronyms_section(1)

        self.assertIn("ЧЗ означает Честный Знак.", section)
        self.assertNotIn("чз означает Честный Знак.", section)

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

        self.assertEqual(section.count("ЧЗ означает"), 1)
        self.assertIn("ЧЗ означает Групповой.", section)
        self.assertNotIn("ЧЗ означает Глобальный.", section)
        self.assertIn("ОФД означает Оператор.", section)


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

        mock_db.get_terms_for_group.return_value = [
            {"term": "ГЗ", "definition": "Горячая замена", "confidence": 0.95},
            {"term": "ЧЗ", "definition": "Честный Знак", "confidence": 0.89},
            {"term": "ОФД", "definition": "Оператор фискальных данных", "confidence": None},
        ]

        service = QASearchService()
        section = service._build_acronyms_section(123)

        self.assertIn("ГЗ означает Горячая замена.", section)
        self.assertNotIn("ЧЗ означает Честный Знак.", section)
        self.assertNotIn("ОФД означает Оператор фискальных данных.", section)
        mock_db.get_terms_for_group.assert_called_once_with(
            123,
            status="approved",
            term_type="acronym",
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

        self.assertEqual(section.lower().count("чз означает"), 1)
        self.assertIn("чз означает Групповой.", section)
        self.assertNotIn("ЧЗ означает Глобальный.", section)
        self.assertIn("ОФД означает Оператор фискальных данных.", section)

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


if __name__ == "__main__":
    unittest.main()
