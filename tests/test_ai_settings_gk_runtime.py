"""Тесты runtime-accessor'ов настроек моделей Group Knowledge."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from config import ai_settings


class TestGKRuntimeSettingsAccessors(unittest.TestCase):
    """Проверка чтения runtime-настроек GK из bot_settings с fallback в env."""

    def test_get_active_gk_text_provider_prefers_db_value(self):
        """Провайдер текстовых задач берётся из БД, если override задан."""
        with patch.object(ai_settings, "_safe_get_app_setting", return_value="gigachat"):
            value = ai_settings.get_active_gk_text_provider()
        self.assertEqual(value, "gigachat")

    def test_get_active_gk_text_provider_falls_back_to_env_default(self):
        """Если override не задан, используется env-конфиг GK_TEXT_PROVIDER."""
        with patch.object(ai_settings, "_safe_get_app_setting", return_value=None):
            with patch.object(ai_settings, "GK_TEXT_PROVIDER", "deepseek"):
                value = ai_settings.get_active_gk_text_provider()
        self.assertEqual(value, "deepseek")

    def test_get_active_gk_models_read_specific_keys(self):
        """Accessor'ы моделей читают свои ключи и возвращают переопределение из БД."""
        values = {
            ai_settings.GK_ANALYSIS_MODEL_SETTING_KEY: "model-analysis-x",
            ai_settings.GK_RESPONDER_MODEL_SETTING_KEY: "model-responder-y",
            ai_settings.GK_QUESTION_DETECTION_MODEL_SETTING_KEY: "model-question-z",
            ai_settings.GK_TERMS_SCAN_MODEL_SETTING_KEY: "model-terms-k",
            ai_settings.GK_IMAGE_DESCRIPTION_MODEL_SETTING_KEY: "model-image-v",
        }

        def fake_get_setting(setting_key: str):
            return values.get(setting_key)

        with patch.object(ai_settings, "_safe_get_app_setting", side_effect=fake_get_setting):
            self.assertEqual(ai_settings.get_active_gk_analysis_model(), "model-analysis-x")
            self.assertEqual(ai_settings.get_active_gk_responder_model(), "model-responder-y")
            self.assertEqual(ai_settings.get_active_gk_question_detection_model(), "model-question-z")
            self.assertEqual(ai_settings.get_active_gk_terms_scan_model(), "model-terms-k")
            self.assertEqual(ai_settings.get_active_gk_image_description_model(), "model-image-v")

    def test_get_active_gk_main_runtime_settings(self):
        """Accessor'ы главных runtime-настроек читают значения из app_settings."""
        values = {
            ai_settings.GK_RESPONDER_CONFIDENCE_THRESHOLD_SETTING_KEY: "0.83",
            ai_settings.GK_RESPONDER_TOP_K_SETTING_KEY: "17",
            ai_settings.GK_RESPONDER_TEMPERATURE_SETTING_KEY: "0.35",
            ai_settings.GK_INCLUDE_LLM_INFERRED_ANSWERS_SETTING_KEY: "1",
            ai_settings.GK_EXCLUDE_LOW_TIER_FROM_LLM_CONTEXT_SETTING_KEY: "0",
            ai_settings.GK_ANALYSIS_QUESTION_CONFIDENCE_THRESHOLD_SETTING_KEY: "0.91",
            ai_settings.GK_ANALYSIS_TEMPERATURE_SETTING_KEY: "0.25",
            ai_settings.GK_QUESTION_DETECTION_TEMPERATURE_SETTING_KEY: "0.12",
            ai_settings.GK_GENERATE_LLM_INFERRED_QA_PAIRS_SETTING_KEY: "1",
            ai_settings.GK_HYBRID_ENABLED_SETTING_KEY: "1",
            ai_settings.GK_RELEVANCE_HINTS_ENABLED_SETTING_KEY: "0",
            ai_settings.GK_SEARCH_CANDIDATES_PER_METHOD_SETTING_KEY: "42",
            ai_settings.GK_ACRONYMS_MAX_PROMPT_TERMS_SETTING_KEY: "77",
            ai_settings.GK_TERMS_SCAN_TEMPERATURE_SETTING_KEY: "0.28",
            ai_settings.GK_BM25_IDF_DAMPEN_RATIO_SETTING_KEY: "0.72",
            ai_settings.GK_BM25_IDF_DAMPEN_FACTOR_SETTING_KEY: "0.18",
        }

        def fake_get_setting(setting_key: str):
            return values.get(setting_key)

        with patch.object(ai_settings, "_safe_get_app_setting", side_effect=fake_get_setting):
            self.assertEqual(ai_settings.get_active_gk_responder_confidence_threshold(), 0.83)
            self.assertEqual(ai_settings.get_active_gk_responder_top_k(), 17)
            self.assertEqual(ai_settings.get_active_gk_responder_temperature(), 0.35)
            self.assertTrue(ai_settings.get_active_gk_include_llm_inferred_answers())
            self.assertFalse(ai_settings.get_active_gk_exclude_low_tier_from_llm_context())
            self.assertEqual(ai_settings.get_active_gk_analysis_question_confidence_threshold(), 0.91)
            self.assertEqual(ai_settings.get_active_gk_analysis_temperature(), 0.25)
            self.assertEqual(ai_settings.get_active_gk_question_detection_temperature(), 0.12)
            self.assertTrue(ai_settings.get_active_gk_generate_llm_inferred_qa_pairs())
            self.assertTrue(ai_settings.get_active_gk_hybrid_enabled())
            self.assertFalse(ai_settings.get_active_gk_relevance_hints_enabled())
            self.assertEqual(ai_settings.get_active_gk_search_candidates_per_method(), 42)
            self.assertEqual(ai_settings.get_active_gk_acronyms_max_prompt_terms(), 77)
            self.assertEqual(ai_settings.get_active_gk_terms_scan_temperature(), 0.28)
            self.assertEqual(ai_settings.get_active_gk_bm25_idf_dampen_ratio(), 0.72)
            self.assertEqual(ai_settings.get_active_gk_bm25_idf_dampen_factor(), 0.18)


if __name__ == "__main__":
    unittest.main()
